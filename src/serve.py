#!/usr/bin/env python3
"""MangaSearch web server.

Serves the generated page (docs/), a small JSON API that proxies list actions
to MangaUpdates, and rebuilds the list on a schedule (a background thread runs
the full refresh pipeline hourly, anchored to the last search-fetch time).
Credentials stay on this machine: the browser only ever talks to this server,
which attaches the MU session token itself.

    GET  /api/records -> {"updated": "...", "records": [...]} straight from the DB
    GET  /api/lists   -> {"lists": [{"id", "title", "icon", "custom"}, ...]}
    GET  /api/status  -> refresh state: running / last_success / last_error / next_run
    GET  /api/logs    -> {"lines": [...]} tail of logs/mangasearch.log (?lines=N)
    GET  /api/comments?series=ID -> 25 most recent MU user comments (cached 1-2d)
    POST /api/list    <- {"series_id": int, "list_id": int}

Usage: python3 serve.py [port]        (default 8000; started via serve.sh)
"""

import json
import logging
import random
import sys
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import log as logsetup
from api import MangaUpdatesClient, load_credentials
from config import DB_PATH, LOG_DIR, PROJECT_ROOT, REFRESH_INTERVAL_SECS, TTL
from db import Database
from logic import clean_description
from main import refresh

log = logging.getLogger(__name__)

DOCS_DIR = PROJECT_ROOT / 'docs'
LISTS_MAX_AGE_SECS = 3600 * 24  # refresh the list map from MU daily

# One shared MU client; a lock serializes calls (MU throttles writes anyway).
_mu_lock = threading.Lock()
_mu_client = None

# Refresh-thread state, exposed at /api/status for the frontend.
_refresh_lock = threading.Lock()
_refresh_state = {'running': False, 'last_success': None,
                  'last_error': None, 'last_error_at': None, 'next_run': None}


def _set_refresh_state(**kwargs):
    with _refresh_lock:
        _refresh_state.update(kwargs)


def mu_client():
    global _mu_client
    if _mu_client is None:
        _mu_client = MangaUpdatesClient(*load_credentials())
    return _mu_client


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def do_GET(self):
        if self.path == '/api/records':
            return self.api_records()
        if self.path == '/api/lists':
            return self.api_lists()
        if self.path == '/api/status':
            return self.api_status()
        if self.path.startswith('/api/logs'):
            return self.api_logs()
        if self.path.startswith('/api/comments'):
            return self.api_comments()
        return super().do_GET()

    def api_comments(self):
        try:
            self._api_comments()
        except Exception:
            log.exception('comments handler failed (%s)', self.path)
            self._json(500, {'error': 'internal error, see logs'})

    def _api_comments(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            series_id = int(query['series'][0])
        except (KeyError, ValueError):
            return self._json(400, {'error': 'expected ?series=<id>'})
        db = Database(DB_PATH)
        comments = db.get_many('comments', [series_id]).get(series_id)
        if comments is None:
            with _mu_lock:
                status, body = mu_client().call(
                    'POST', f'/series/{series_id}/comments/search',
                    {'method': 'time_added', 'page': 1, 'perpage': 25})
            if status != 200:
                log.warning('MU comments fetch failed for %s: %s %s',
                            series_id, status, body)
                # MU is down or grumpy: expired comments beat an empty section.
                stale = db.get_many('comments', [series_id],
                                    include_expired=True).get(series_id)
                if stale is not None:
                    return self._json(200, {'comments': stale})
                return self._json(502, {'error': body.get('reason', f'HTTP {status}')})
            comments = []
            for result in body.get('results') or []:
                rec = result.get('record') or {}
                meta = result.get('metadata') or {}
                comments.append({
                    'author': (rec.get('author') or {}).get('name') or 'anonymous',
                    'content': clean_description(rec.get('content')),
                    'useful': rec.get('useful') or 0,
                    'rating': meta.get('author_series_rating'),
                    'time': (rec.get('time_added') or {}).get('as_string') or '',
                })
            db.put('comments', series_id, comments,
                   time.time() + random.randint(*TTL['comments']))
            db.commit()
        self._json(200, {'comments': comments})

    def api_logs(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            n = min(int(query.get('lines', ['300'])[0]), 2000)
        except ValueError:
            n = 300
        log_file = LOG_DIR / 'mangasearch.log'
        try:
            lines = log_file.read_text(errors='replace').splitlines()[-n:]
        except OSError:
            lines = []
        self._json(200, {'lines': lines})

    def api_status(self):
        with _refresh_lock:
            state = dict(_refresh_state)
        state['server_time'] = time.time()
        self._json(200, state)

    def end_headers(self):
        # The built assets are content-hashed; only the entry points must
        # never be cached so refreshes and rebuilds show up immediately.
        if self.path in ('/', '/index.html') or self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def api_records(self):
        db = Database(DB_PATH)  # per-request: handlers run on threads
        records = db.kv_get('scored_records', float('inf'))
        if records is None:
            return self._json(404, {'error': 'no data yet — first refresh pending'})
        age = db.kv_age('scored_records') or 0
        updated = datetime.fromtimestamp(time.time() - age).strftime('%Y-%m-%d %H:%M')
        self._json(200, {'updated': updated, 'records': records})

    def do_POST(self):
        if self.path == '/api/list':
            return self.api_add_to_list()
        self.send_error(404)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api_lists(self):
        db = Database(DB_PATH)  # per-request: handlers run on threads
        lists = db.get_lists(LISTS_MAX_AGE_SECS)
        if lists is None:
            with _mu_lock:
                status, body = mu_client().call('GET', '/lists')
            if status != 200:
                stale = db.get_lists(float('inf'))  # serve stale over nothing
                if stale:
                    return self._json(200, {'lists': stale})
                return self._json(502, {'error': body.get('reason', f'HTTP {status}')})
            lists = [{'id': l['list_id'], 'title': l['title'],
                      'icon': l.get('icon') or '', 'custom': bool(l.get('custom'))}
                     for l in body]
            db.save_lists(lists)
        self._json(200, {'lists': lists})

    def api_add_to_list(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(length) or b'{}')
            series_id = int(data['series_id'])
            list_id = int(data['list_id'])
        except (ValueError, KeyError):
            return self._json(400, {'error': 'expected {"series_id": int, "list_id": int}'})

        with _mu_lock:
            status, body = mu_client().call(
                'POST', '/lists/series',
                [{'series': {'id': series_id}, 'list_id': list_id}])
        if status == 200:
            log.info('Added series %s to list %s', series_id, list_id)
            return self._json(200, {'ok': True})
        log.warning('Add series %s to list %s failed: %s %s',
                    series_id, list_id, status, body)
        if status == 412:
            return self._json(429, {'error': 'MangaUpdates allows one list update '
                                             'every 5 seconds — try again in a moment.'})
        self._json(502, {'error': body.get('reason', f'HTTP {status}')})

    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)


def refresher():
    """Rebuild the list hourly, anchored to the last successful search fetch
    (so a server restart doesn't trigger a redundant refresh)."""
    while True:
        db = Database(DB_PATH)
        # Anchor on the last PUBLISH, not the last search: an interrupted run
        # has fresh search results but no publish, and must resume promptly.
        age = db.kv_age('scored_records')
        db.conn.close()
        wait = 0.0
        if age is not None and age < REFRESH_INTERVAL_SECS:
            wait = REFRESH_INTERVAL_SECS - age
        _set_refresh_state(next_run=time.time() + wait)
        if wait:
            time.sleep(wait)
        log.info('[refresh] starting')
        _set_refresh_state(running=True)
        try:
            refresh()
            _set_refresh_state(running=False, last_success=time.time(),
                               last_error=None, last_error_at=None)
            log.info('[refresh] done')
        except Exception as err:
            log.exception('[refresh] failed')
            # Back off so a persistent failure can't hot-loop.
            _set_refresh_state(running=False,
                               last_error=f'{type(err).__name__}: {err}',
                               last_error_at=time.time(),
                               next_run=time.time() + 600)
            time.sleep(600)


def main():
    logsetup.setup()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    threading.Thread(target=refresher, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    log.info('Serving %s + /api on port %d, hourly refresh enabled', DOCS_DIR, port)
    server.serve_forever()


if __name__ == '__main__':
    main()
