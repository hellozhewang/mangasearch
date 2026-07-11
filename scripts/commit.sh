#!/bin/sh
# Refresh the page (pass "r") and push the result.
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"

if [ $# -gt 0 ] && [ "$1" = "r" ]; then
    python3 "$ROOT/src/main.py"
fi

git -C "$ROOT" add .
git -C "$ROOT" commit -m "update"
git -C "$ROOT" push origin
