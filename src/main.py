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
import logging

import log as logsetup
from api import MangaUpdatesClient, load_credentials
from config import (DB_PATH, MIN_RATING, SEARCH_RESULTS_TTL_SECS, TOP_N)
from db import Database
from logic import build_records, search_series

log = logging.getLogger(__name__)


def refresh(offline=False, top=TOP_N, min_rating=MIN_RATING):
    """Run the full pipeline: search -> enrich -> score -> render."""
    db = Database(DB_PATH)

    client = None
    if offline:
        results = db.kv_get('search_results', max_age_secs=float('inf'))
        if results is None:
            raise SystemExit(f'--offline needs stored search results in {DB_PATH.name}')
        log.info('Search results from DB: %d', len(results))
    else:
        client = MangaUpdatesClient(*load_credentials())
        results = db.kv_get('search_results', SEARCH_RESULTS_TTL_SECS)
        if results is None:
            results = search_series(client, db, min_rating)
        else:
            log.info('Search results still fresh in DB: %d', len(results))

    records = build_records(client, db, results, offline, top)
    log.info('Publishing %d scored records to the DB', len(records))
    db.kv_put('scored_records', records)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--offline', action='store_true',
                        help='render from the local DB only; no network, no login')
    parser.add_argument('--top', type=int, default=TOP_N,
                        help=f'number of series to render (default: {TOP_N})')
    parser.add_argument('--min-rating', type=float, default=MIN_RATING,
                        help=f'stop paging once ratings drop below this (default: {MIN_RATING})')
    args = parser.parse_args()
    logsetup.setup()
    refresh(args.offline, args.top, args.min_rating)


if __name__ == '__main__':
    main()
