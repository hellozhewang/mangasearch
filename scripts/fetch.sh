#!/bin/sh
# Manually run the fetch/score/publish pipeline (same thing the server does
# hourly). Logs stream to the terminal AND to logs/mangasearch.log, and the
# scored list is published to the DB — the web page picks it up on its next
# poll or reload.
#
#   sh fetch.sh                  full refresh (hits the MangaUpdates API)
#   sh fetch.sh --offline        re-score/publish from the local DB only
#   sh fetch.sh --top 100 --min-rating 7.0
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"

exec python3 -u "$ROOT/src/main.py" "$@"
