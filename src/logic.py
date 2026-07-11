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
    payload = {
        'page': 1,
        'perpage': 100,
        'include_rank_metadata': False,
        'genre': SEARCH['genres'],
        'list': 'none',  # only series not on any of my lists
        'filter': 'no_oneshots',
        'type': SEARCH['types'],
        'exclude_genre': SEARCH['exclude_genres'],
        'orderby': 'rating',
    }
    results = []
    total = None
    while True:
        response = client.search_page(payload)
        if not response:
            break
        if total is None:
            total = response['total_hits']
            log.info('Total hits: %s', total)
        page_records = [r['record'] for r in response['results'] if 'record' in r]
        if not page_records:
            break
        results.extend(page_records)
        log.info('Fetched: %d', len(results))
        lowest = page_records[-1].get('bayesian_rating') or 0
        if len(results) >= total or lowest < min_rating:
            break
        payload['page'] += 1

    db.kv_put('search_results', results)
    return results


def score_record(record, rating, series):
    """Return (score, breakdown, avg_rating, completed) for one series."""
    cfg = SCORING
    base = record.get('bayesian_rating') or 0
    votes = record.get('rating_votes') or 0
    avg_rating = (rating or {}).get('average_rating') or 0
    year_str = str(record.get('year') or '')[:4]
    year = int(year_str) if year_str.isdigit() else 0
    genres = {g['genre'] for g in record.get('genres', [])}

    score = base
    breakdown = {}

    # Graded high-rating bonus (smoothed; used to be a cliff at 8.00).
    lo, hi = cfg['high_rating_ramp_start'], cfg['high_rating_ramp_end']
    if base > lo:
        mod = min((base - lo) / (hi - lo), 1.0) * cfg['high_rating_bonus']
        score += mod
        breakdown['8Club'] = mod

    # Trending boost for promising low-vote series.
    if votes < cfg['hype_votes_threshold']:
        hype = ((votes * avg_rating + cfg['hype_gravity'] * cfg['global_mean'])
                / (votes + cfg['hype_gravity']))
        mod = max(0, hype - base)
        if mod:
            score += mod
            breakdown['Trending'] = mod

    # Recency penalty on a rolling window instead of a fixed year.
    year_limit = datetime.now().year - cfg['recency_window_years']
    if 0 < year < year_limit:
        mod = min((year_limit - year) * cfg['year_penalty_per_year'],
                  cfg['year_penalty_cap'])
        score -= mod
        breakdown['Year'] = -mod

    for genre, weight in cfg['genre_weights'].items():
        if genre in genres:
            score += weight
            breakdown[genre] = weight

    completed = False
    if series:
        categories = {c['category']: c['votes_plus'] for c in series.get('categories', [])}

        for name, bonus in cfg['category_bonuses'].items():
            if name in categories:
                mod = min(bonus['base'] + bonus['per_vote'] * categories[name],
                          bonus['cap'])
                score += mod
                breakdown[name] = mod

        couple_votes = [categories[c] for c in ('Married Couple', 'Established Couple')
                        if c in categories]
        if couple_votes:
            mod = min(cfg['couple_base'] + cfg['couple_per_vote'] * sum(couple_votes),
                      cfg['couple_cap'])
            score += mod
            breakdown['Couple'] = mod

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
                fetched += 1
                if fetched % 50 == 0:
                    db.commit()
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
            'genres': sorted({g['genre'] for g in record.get('genres', [])}),
            'status': ' · '.join(s.strip() for s in status.splitlines() if s.strip()),
            'description': clean_description((series or {}).get('description')),
            'completed': completed,
            'votes': record.get('rating_votes') or 0,
            'bayesian': record.get('bayesian_rating') or 0,
            'average': avg_rating,
            'score': round(score, 3),
            'breakdown': {k: round(v, 3) for k, v in breakdown.items()},
        })

    records.sort(key=lambda r: (r['score'], r['average'], r['bayesian']), reverse=True)
    records = records[:top_n]
    for rank, r in enumerate(records, 1):
        r['rank'] = rank
    return records
