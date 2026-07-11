#!/usr/bin/env python3
"""MangaSearch — find highly-rated manga you haven't read on MangaUpdates.

Searches series not on any of your MangaUpdates lists, enriches them with
rating/series metadata (cached in SQLite), scores them with a tunable
heuristic, and renders a static, filterable HTML page (docs/index.html).

Credentials come from the MU_USERNAME / MU_PASSWORD environment variables or a
gitignored `.env` file next to this script. Never hardcode them here.

Usage:
    python3 main.py                 # full refresh (hits the API)
    python3 main.py --offline       # re-render from the local cache only
    python3 main.py --top 100 --min-rating 7.0
"""

import argparse
import json
import os
import pickle
import random
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

DB_PATH = PROJECT_ROOT / 'cache.db'
TEMPLATE_PATH = SRC_DIR / 'template.html'
OUTPUT_PATH = PROJECT_ROOT / 'docs' / 'index.html'

# Legacy pickle caches — imported into SQLite once, then no longer touched.
LEGACY_PICKLES = {
    'search': PROJECT_ROOT / 'cache.pickle',
    'series': PROJECT_ROOT / 'series_cache.pickle',
    'rating': PROJECT_ROOT / 'rating_cache.pickle',
}

SEARCH_CACHE_TTL_SECS = 300
REQUEST_DELAY_SECS = 0.75

DAY = 3600 * 24
# TTLs are jittered per entry so refreshes stay spread out over time.
TTL = {
    'series': (15 * DAY, 25 * DAY),
    'rating': (25 * DAY, 40 * DAY),
}

SEARCH = {
    'genres': ['Romance'],
    'exclude_genres': ['Shotacon', 'Shoujo Ai', 'Shounen Ai', 'Yaoi', 'Yuri', 'Hentai'],
    'types': ['Manga', 'Manhwa', 'Manhua'],
}

SCORING = {
    # Graded bonus for very highly rated series. Ramps linearly from 0 at 7.75
    # to the full bonus at 8.25 (the old version was a hard +0.5 cliff at 8.00,
    # so a 7.99 series scored half a point below an 8.00 one).
    'high_rating_ramp_start': 7.75,
    'high_rating_ramp_end': 8.25,
    'high_rating_bonus': 0.5,

    # "Trending" boost for low-vote series: blend the raw average toward the
    # site-wide mean with a small prior, and credit any upside vs the
    # (conservative) bayesian rating.
    'hype_votes_threshold': 30,
    'hype_gravity': 17,
    'global_mean': 6.40,

    # Recency: penalize series older than the rolling window, capped.
    'recency_window_years': 6,
    'year_penalty_per_year': 1 / 9,
    'year_penalty_cap': 2.5,

    'genre_weights': {
        'Seinen': 0.10,
        'Shounen': 0.025,
        'Josei': 0.05,
        'Adult': 0.025,
        'Shoujo': -0.10,
        'Harem': -0.10,
    },

    # Category bonuses: base + per_vote * votes_plus, capped.
    'category_bonuses': {
        'Fast Romance': {'base': 0.02, 'per_vote': 0.02, 'cap': 0.05},
        'Beautiful Artwork': {'base': 0.01, 'per_vote': 0.01, 'cap': 0.05},
    },
    'couple_base': 0.02,
    'couple_per_vote': 0.02,
    'couple_cap': 0.08,

    'completed_bonus': 0.125,
}


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #

class MangaUpdatesClient:
    BASE = 'https://api.mangaupdates.com/v1'

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._token = None

    def _request(self, method, path, payload=None, retries=3):
        headers = {'Content-Type': 'application/json'}
        if self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.BASE + path, data=data,
                                     headers=headers, method=method)
        last_err = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except (urllib.error.URLError, TimeoutError, ValueError) as err:
                last_err = err
                status = getattr(err, 'code', None)
                if status is not None and 400 <= status < 500 and status != 429:
                    break  # client error, retrying won't help
                time.sleep(2 ** attempt)
        print(f'Request failed: {method} {path}: {last_err}')
        return None

    def login(self):
        resp = self._request('PUT', '/account/login',
                             {'username': self._username, 'password': self._password})
        if not resp or resp.get('status') != 'success':
            raise SystemExit(f'Login failed: {resp}')
        self._token = resp['context']['session_token']

    def _ensure_token(self):
        if not self._token:
            self.login()

    def search_page(self, payload):
        self._ensure_token()
        return self._request('POST', '/series/search', payload)

    def get(self, path):
        self._ensure_token()
        resp = self._request('GET', path)
        time.sleep(REQUEST_DELAY_SECS)
        return resp


def load_credentials():
    username = os.environ.get('MU_USERNAME')
    password = os.environ.get('MU_PASSWORD')
    if not (username and password):
        env_path = SRC_DIR / '.env'
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key == 'MU_USERNAME' and not username:
                    username = value
                elif key == 'MU_PASSWORD' and not password:
                    password = value
    if not (username and password):
        raise SystemExit('Set MU_USERNAME / MU_PASSWORD env vars or put them in '
                         f'{SRC_DIR / ".env"} (gitignored). Use --offline to '
                         'render from the cache without logging in.')
    return username, password


# --------------------------------------------------------------------------- #
# SQLite cache
# --------------------------------------------------------------------------- #

class Cache:
    """One SQLite file holding all cached API responses.

    entities: (kind, id) -> JSON blob with a jittered expiry timestamp.
    kv:       small singletons like the raw search-result list.
    """

    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                kind       TEXT NOT NULL,
                id         INTEGER NOT NULL,
                data       TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (kind, id)
            ) WITHOUT ROWID''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS kv (
                key        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                updated_at REAL NOT NULL
            )''')
        self.db.commit()

    def get_many(self, kind, ids, include_expired=False):
        """Batch-fetch {id: entry} for every cached id in `ids` — one query
        per 500 ids instead of one lookup per record."""
        now = time.time()
        out = {}
        ids = list(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ','.join('?' * len(chunk))
            rows = self.db.execute(
                f'SELECT id, data, expires_at FROM entities '
                f'WHERE kind = ? AND id IN ({marks})', [kind] + chunk)
            for id_, data, expires_at in rows:
                if include_expired or expires_at > now:
                    out[id_] = json.loads(data)
        return out

    def put(self, kind, id_, value):
        expires_at = time.time() + random.randint(*TTL[kind])
        self.db.execute(
            'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
            'VALUES (?, ?, ?, ?)', (kind, id_, json.dumps(value), expires_at))

    def kv_get(self, key, max_age_secs):
        row = self.db.execute(
            'SELECT data, updated_at FROM kv WHERE key = ?', (key,)).fetchone()
        if row and time.time() - row[1] < max_age_secs:
            return json.loads(row[0])
        return None

    def kv_put(self, key, value):
        self.db.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), time.time()))
        self.db.commit()

    def commit(self):
        self.db.commit()

    def entity_count(self):
        return self.db.execute('SELECT COUNT(*) FROM entities').fetchone()[0]


def migrate_legacy_pickles(cache):
    """One-time import of the old pickle caches into SQLite."""
    if cache.entity_count() > 0:
        return
    for kind in ('series', 'rating'):
        path = LEGACY_PICKLES[kind]
        if not path.is_file():
            continue
        with open(path, 'rb') as fh:
            data = pickle.load(fh)
        for id_, entry in data.items():
            # Old stamps were written as write_time + jitter and considered
            # fresh for 10 more days; keep that expiry on import.
            stamp = entry.pop('cache_timestamp', time.time())
            cache.db.execute(
                'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
                'VALUES (?, ?, ?, ?)',
                (kind, id_, json.dumps(entry), stamp + 10 * DAY))
        print(f'Migrated {len(data)} {kind} entries from {path.name}')
    search_path = LEGACY_PICKLES['search']
    if search_path.is_file():
        with open(search_path, 'rb') as fh:
            results = pickle.load(fh)
        cache.db.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            ('search_results', json.dumps(results), search_path.stat().st_mtime))
        print(f'Migrated {len(results)} search results from {search_path.name}')
    cache.commit()


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #

def search_series(client, cache, min_rating):
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
            print(f'Total hits: {total}')
        page_records = [r['record'] for r in response['results'] if 'record' in r]
        if not page_records:
            break
        results.extend(page_records)
        print(f'Fetched: {len(results)}')
        lowest = page_records[-1].get('bayesian_rating') or 0
        if len(results) >= total or lowest < min_rating:
            break
        payload['page'] += 1

    cache.kv_put('search_results', results)
    return results


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

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


def build_records(client, cache, results, offline, top_n):
    ids = [r['series_id'] for r in results]

    # Two batched queries pull every fresh cache hit up front; only the misses
    # go to the network (rate-limited, one call per series).
    ratings = cache.get_many('rating', ids, include_expired=offline)
    series_map = cache.get_many('series', ids, include_expired=offline)
    print(f'Cache hits: {len(ratings)}/{len(ids)} ratings, '
          f'{len(series_map)}/{len(ids)} series')

    if not offline:
        missing_ratings = [i for i in ids if i not in ratings]
        missing_series = [i for i in ids if i not in series_map]
        print(f'Fetching {len(missing_ratings)} ratings, '
              f'{len(missing_series)} series from API')
        fetched = 0
        for id_ in missing_ratings:
            resp = client.get(f'/series/{id_}/ratingrainbow')
            if resp:
                ratings[id_] = resp
                cache.put('rating', id_, resp)
            fetched += 1
            if fetched % 50 == 0:
                cache.commit()
                print(f'Fetched: {fetched}/{len(missing_ratings) + len(missing_series)}')
        for id_ in missing_series:
            resp = client.get(f'/series/{id_}')
            if resp:
                series_map[id_] = resp
                cache.put('series', id_, resp)
            fetched += 1
            if fetched % 50 == 0:
                cache.commit()
                print(f'Fetched: {fetched}/{len(missing_ratings) + len(missing_series)}')
        cache.commit()

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


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #

def render(records):
    print(f'Rendering {len(records)} records -> {OUTPUT_PATH}')
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    # '</' must not appear inside the inline <script> data block.
    data_json = json.dumps(records, ensure_ascii=False).replace('</', '<\\/')
    page = (template
            .replace('__UPDATED__', datetime.now().strftime('%Y-%m-%d %H:%M'))
            .replace('__DATA_JSON__', data_json))
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(page, encoding='utf-8')


# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--offline', action='store_true',
                        help='render from the local cache only; no network, no login')
    parser.add_argument('--top', type=int, default=150,
                        help='number of series to render (default: 150)')
    parser.add_argument('--min-rating', type=float, default=6.8,
                        help='stop paging once ratings drop below this (default: 6.8)')
    args = parser.parse_args()

    cache = Cache(DB_PATH)
    migrate_legacy_pickles(cache)

    client = None
    if args.offline:
        results = cache.kv_get('search_results', max_age_secs=float('inf'))
        if results is None:
            raise SystemExit('--offline needs cached search results in cache.db')
        print(f'Search cache: {len(results)} records')
    else:
        client = MangaUpdatesClient(*load_credentials())
        results = cache.kv_get('search_results', SEARCH_CACHE_TTL_SECS)
        if results is None:
            results = search_series(client, cache, args.min_rating)
        else:
            print(f'Search cache hit: {len(results)} records')

    records = build_records(client, cache, results, args.offline, args.top)
    render(records)


if __name__ == '__main__':
    main()
