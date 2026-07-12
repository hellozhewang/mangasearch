"""MangaUpdates API client (stdlib-only) and credential loading."""

import json
import logging
import os
import random
import time
import urllib.error
import urllib.request

from config import PROJECT_ROOT, REQUEST_DELAY_SECS

log = logging.getLogger(__name__)


class MangaUpdatesClient:
    BASE = 'https://api.mangaupdates.com/v1'

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._token = None

    def _attempt(self, method, path, payload=None):
        """One HTTP attempt. Returns (status_code, body_dict); 0 = no response."""
        headers = {'Content-Type': 'application/json'}
        if self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.BASE + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            try:
                body = json.loads(err.read().decode())
            except (ValueError, OSError):
                body = {'status': 'exception', 'reason': str(err)}
            return err.code, body
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            return 0, {'status': 'exception', 'reason': str(err)}

    def _request(self, method, path, payload=None, retries=5):
        for attempt in range(retries):
            status, body = self._attempt(method, path, payload)
            if status == 200:
                return body
            if 400 <= status < 500 and status != 429:
                break  # client error, retrying won't help
            if attempt < retries - 1:
                # Exponential backoff with jitter: ~2s, 4s, 8s, 16s (max 60s).
                delay = min(60, 2 ** (attempt + 1)) * random.uniform(0.75, 1.25)
                log.warning('%s %s -> %s; retry %d/%d in %.1fs',
                            method, path, status or 'network-error',
                            attempt + 1, retries - 1, delay)
                time.sleep(delay)
        log.warning('Request failed permanently: %s %s: %s %s',
                    method, path, status, body)
        return None

    def call(self, method, path, payload=None):
        """Single authenticated call returning (status_code, body) so the
        caller can surface API errors (e.g. the 412 write throttle)."""
        self._ensure_token()
        status, body = self._attempt(method, path, payload)
        if status == 401:  # session expired: re-login once and retry
            self._token = None
            self._ensure_token()
            status, body = self._attempt(method, path, payload)
        return status, body

    def login(self):
        resp = self._request('PUT', '/account/login',
                             {'username': self._username, 'password': self._password})
        if not resp or resp.get('status') != 'success':
            raise RuntimeError(f'Login failed: {resp}')
        self._token = resp['context']['session_token']
        log.info('Logged in to MangaUpdates')

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
        env_path = PROJECT_ROOT / '.env'
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
                         f'{PROJECT_ROOT / ".env"} (gitignored). Use --offline to '
                         'render from the local DB without logging in.')
    return username, password
