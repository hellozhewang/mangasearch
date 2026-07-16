"""Business logic: series search, scoring heuristic, and record assembly."""

import html
import logging
import random
import re
import time
from datetime import datetime

from config import SCORING, SEARCH, TTL

log = logging.getLogger(__name__)


def search_series(client, db, min_rating):
    merged = {}
    # Genres with their own dedicated pass are excluded from the breadth pass
    # so its 10k result window isn't wasted on titles another pass covers.
    dedicated = {g for genres in SEARCH['genre_passes'] for g in genres}
    for genres in SEARCH['genre_passes']:
        label = '+'.join(genres) if genres else 'all-genres'
        exclude = list(SEARCH['exclude_genres'])
        if not genres:
            exclude.extend(sorted(dedicated))
        payload = {
            'page': 1,
            'perpage': 100,
            'include_rank_metadata': False,
            'list': 'none',  # only series not on any of my lists
            'filter': 'no_oneshots',
            'type': SEARCH['types'],
            'exclude_genre': exclude,
            'orderby': 'rating',
        }
        if genres:
            payload['genre'] = genres
        count = 0
        total = None
        lowest = None
        while True:
            response = client.search_page(payload)
            if not response:
                log.warning('[%s] search page %d failed, stopping pass',
                            label, payload['page'])
                break
            if total is None:
                total = response['total_hits']
                log.info('[%s] total hits: %s', label, total)
            page_records = [r['record'] for r in response['results'] if 'record' in r]
            if not page_records:
                # MU stops serving results well before total_hits (~3900).
                log.info('[%s] hit MU paging depth wall at %d results '
                         '(lowest rating %.2f)', label, count, lowest or 0)
                break
            for rec in page_records:
                merged.setdefault(rec['series_id'], rec)
            count += len(page_records)
            log.info('[%s] fetched: %d', label, count)
            lowest = page_records[-1].get('bayesian_rating') or 0
            if count >= total or lowest < min_rating:
                break
            payload['page'] += 1
        log.info('[%s] pass done: %d results, %d unique so far', label, count, len(merged))

    results = list(merged.values())
    db.kv_put('search_results', results)
    return results


def sync_listed(client, db):
    """Pull which series are on which of my MU lists into the listed table."""
    status, lists = client.call('GET', '/lists')
    if status != 200:
        log.warning('listed sync: GET /lists failed: %s', status)
        return
    pairs = []
    for lst in lists:
        list_id = lst['list_id']
        page = 1
        while True:
            status, body = client.call('POST', f'/lists/{list_id}/search',
                                       {'page': page, 'perpage': 100})
            if status != 200:
                log.warning('listed sync: list %s page %d failed: %s',
                            list_id, page, status)
                break
            results = body.get('results') or []
            for item in results:
                rec = item.get('record') or {}
                series_id = (rec.get('series') or {}).get('id')
                if series_id:
                    pairs.append((series_id, rec.get('list_id', list_id)))
            total = body.get('total_hits') or 0
            if not results or page * 100 >= total:
                break
            page += 1
    db.save_listed(pairs)
    log.info('Synced %d listed series across %d lists', len(pairs), len(lists))


def score_record(record, rating, series):
    """Return (score, breakdown, avg_rating, completed) for one series."""
    cfg = SCORING
    base = record.get('bayesian_rating') or 0
    votes = record.get('rating_votes') or 0
    avg_rating = (rating or {}).get('average_rating') or 0
    year_str = str(record.get('year') or '')[:4]
    year = int(year_str) if year_str.isdigit() else 0
    # `or []`: MU can return explicit nulls for these fields.
    genres = {g['genre'] for g in record.get('genres') or []}

    score = base
    breakdown = {}

    # How exceptional the rating is: 0..1 along the 8Club ramp.
    lo, hi = cfg['high_rating_ramp_start'], cfg['high_rating_ramp_end']
    excellence = min(max((base - lo) / (hi - lo), 0.0), 1.0)

    # Trending: credit low-vote upside, fading smoothly to zero (no cliff)
    # and capped so it competes with, but can't dominate, proven ratings.
    fade = max(0.0, 1.0 - votes / cfg['hype_fade_votes'])
    if fade > 0:
        hype = ((votes * avg_rating + cfg['hype_gravity'] * cfg['global_mean'])
                / (votes + cfg['hype_gravity']))
        mod = min(max(0.0, hype - base) * fade, cfg['hype_cap'])
        if mod:
            score += mod
            breakdown['Trending'] = mod

    # Recency penalty on a rolling window.
    year_limit = datetime.now().year - cfg['recency_window_years']
    year_penalty = 0.0
    if 0 < year < year_limit:
        year_penalty = min((year_limit - year) * cfg['year_penalty_per_year'],
                           cfg['year_penalty_cap'])
        score -= year_penalty
        breakdown['Year'] = -year_penalty

    # 8Club: an exceptional rating buys back part of the age penalty (an old
    # masterpiece deserves attention), capped so antiques can't own the top,
    # plus a small flat nudge.
    forgiven = min(year_penalty * cfg['high_rating_year_forgiveness'],
                   cfg['high_rating_forgiveness_cap'])
    club = excellence * (cfg['high_rating_bonus'] + forgiven)
    if club:
        score += club
        breakdown['8Club'] = club

    for genre, weight in cfg['genre_weights'].items():
        if genre in genres:
            score += weight
            breakdown[genre] = weight

    completed = False
    if series:
        categories = {c['category']: c['votes_plus'] for c in series.get('categories') or []}

        for rule in cfg['category_bonuses']:
            if any(c in categories for c in rule['any_of']):
                score += rule['bonus']
                breakdown[rule['label']] = rule['bonus']

        status = str(series.get('status') or '')
        completed = bool(series.get('completed')) or (
            'Complete' in status and 'Ongoing' not in status)
        if completed:
            score += cfg['completed_bonus']
            breakdown['Completed'] = cfg['completed_bonus']

    return score, breakdown, avg_rating, completed


def clean_description(raw):
    """MU descriptions carry HTML: convert breaks to newlines, drop the rest."""
    text = re.sub(r'<br\s*/?>', '\n', str(raw or ''), flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def build_records(client, db, results, offline, top_n):
    ids = [r['series_id'] for r in results]

    # Two batched queries pull every fresh stored entry up front; only the
    # missing/expired ones go to the network (rate-limited, one call per series).
    ratings = db.get_many('rating', ids, include_expired=offline)
    series_map = db.get_many('series', ids, include_expired=offline)
    log.info('In DB: %d/%d ratings, %d/%d series',
             len(ratings), len(ids), len(series_map), len(ids))

    if not offline:
        missing_ratings = [i for i in ids if i not in ratings]
        missing_series = [i for i in ids if i not in series_map]
        to_fetch = len(missing_ratings) + len(missing_series)
        log.info('Fetching %d ratings, %d series from API',
                 len(missing_ratings), len(missing_series))
        fetched = 0
        for kind, path_tpl, missing, store in (
                ('rating', '/series/{}/ratingrainbow', missing_ratings, ratings),
                ('series', '/series/{}', missing_series, series_map)):
            for id_ in missing:
                resp = client.get(path_tpl.format(id_))
                if resp:
                    store[id_] = resp
                    # Jittered lifetime so refreshes stay spread out over days
                    # instead of the whole corpus expiring at once.
                    expires_at = time.time() + random.randint(*TTL[kind])
                    db.put(kind, id_, resp, expires_at)
                    # Commit per write: batching held SQLite's write lock for
                    # ~50s stretches and starved the API handlers.
                    db.commit()
                fetched += 1
                if fetched % 50 == 0:
                    log.info('Fetched: %d/%d', fetched, to_fetch)
        db.commit()

    records = []
    for record in results:
        series_id = record['series_id']
        rating = ratings.get(series_id)
        series = series_map.get(series_id)

        score, breakdown, avg_rating, completed = score_record(record, rating, series)

        status = str((series or {}).get('status') or '')
        records.append({
            'id': series_id,
            'title': record.get('title') or '',
            'url': record.get('url') or '',
            'image': ((record.get('image') or {}).get('url') or {}).get('thumb') or '',
            'year': str(record.get('year') or ''),
            'genres': sorted({g['genre'] for g in record.get('genres') or []}),
            'status': ' · '.join(s.strip() for s in status.splitlines() if s.strip()),
            'description': clean_description((series or {}).get('description')),
            'completed': completed,
            'votes': record.get('rating_votes') or 0,
            'bayesian': record.get('bayesian_rating') or 0,
            'average': avg_rating,
            'score': round(score, 3),
            'breakdown': {k: round(v, 3) for k, v in breakdown.items()},
        })

    sort_key = lambda r: (r['score'], r['average'], r['bayesian'])
    records.sort(key=sort_key, reverse=True)

    # Take the top N of each slice: one per dedicated genre, plus a breadth
    # slice for everything not covered by a dedicated genre.
    dedicated = {g for genres in SEARCH['genre_passes'] for g in genres}
    slices = [lambda r, g=g: g in r['genres'] for g in sorted(dedicated)]
    slices.append(lambda r: not dedicated & set(r['genres']))
    selected, chosen = [], set()
    for belongs in slices:
        count = 0
        for r in records:
            if count >= top_n:
                break
            if r['id'] not in chosen and belongs(r):
                chosen.add(r['id'])
                selected.append(r)
                count += 1
    selected.sort(key=sort_key, reverse=True)
    for rank, r in enumerate(selected, 1):
        r['rank'] = rank
    return selected
