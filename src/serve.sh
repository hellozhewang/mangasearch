#!/bin/sh
# Serve the generated page to the local network: http://<this-machine>:8000
# Serves ONLY docs/ (just index.html) — never the repo root, which holds
# .env, the cache DB, and .git.
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
PORT="${1:-8000}"

exec python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$ROOT/docs"
