#!/usr/bin/env python3
"""MangaSearch — find highly-rated manga you haven't read on MangaUpdates.

Searches series not on any of your MangaUpdates lists, enriches them with
rating/series metadata (stored in SQLite, refreshed as entries age out),
scores them with a tunable heuristic, and renders a static, filterable HTML
page (docs/index.html).

Modules: config (settings), db (SQLite store), api (MangaUpdates client),
logic (search + scoring).

Usage:
    python3 main.py                 # full refresh (hits the API)
    python3 main.py --offline       # re-render from the local DB only
    python3 main.py --top 100 --min-rating 7.0
"""

import argparse
import json
from datetime import datetime

from api import MangaUpdatesClient, load_credentials
from config import DB_PATH, OUTPUT_PATH, SEARCH_RESULTS_TTL_SECS, TEMPLATE_PATH
from db import Database
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
                        help='render from the local DB only; no network, no login')
    parser.add_argument('--top', type=int, default=150,
                        help='number of series to render (default: 150)')
    parser.add_argument('--min-rating', type=float, default=6.8,
                        help='stop paging once ratings drop below this (default: 6.8)')
    args = parser.parse_args()

    db = Database(DB_PATH)

    client = None
    if args.offline:
        results = db.kv_get('search_results', max_age_secs=float('inf'))
        if results is None:
            raise SystemExit(f'--offline needs stored search results in {DB_PATH.name}')
        print(f'Search results from DB: {len(results)}')
    else:
        client = MangaUpdatesClient(*load_credentials())
        results = db.kv_get('search_results', SEARCH_RESULTS_TTL_SECS)
        if results is None:
            results = search_series(client, db, args.min_rating)
        else:
            print(f'Search results still fresh in DB: {len(results)}')

    records = build_records(client, db, results, args.offline, args.top)
    render(records)


if __name__ == '__main__':
    main()
