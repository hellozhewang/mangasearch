#!/usr/bin/env python3
"""MangaSearch — find highly-rated manga you haven't read on MangaUpdates.

Searches series not on any of your MangaUpdates lists, enriches them with
rating/series metadata (cached in SQLite), scores them with a tunable
heuristic, and renders a static, filterable HTML page (docs/index.html).

Modules: config (settings), db (SQLite cache), api (MangaUpdates client),
logic (search + scoring).

Usage:
    python3 main.py                 # full refresh (hits the API)
    python3 main.py --offline       # re-render from the local cache only
    python3 main.py --top 100 --min-rating 7.0
"""

import argparse
import json
from datetime import datetime

from api import MangaUpdatesClient, load_credentials
from config import DB_PATH, OUTPUT_PATH, SEARCH_CACHE_TTL_SECS, TEMPLATE_PATH
from db import Cache, migrate_legacy_pickles
from logic import build_records, search_series


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
