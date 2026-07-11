#!/bin/sh
# Refresh + push once an hour, forever.
DIR="$(cd "$(dirname "$0")" && pwd)"
set +e
while true; do
    sh "$DIR/commit.sh" r
    echo 'Done! sleeping.....'
    sleep 3600
done
