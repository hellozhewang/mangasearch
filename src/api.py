"""MangaUpdates API client (stdlib-only) and credential loading."""

import json
import os
import time
import urllib.error
import urllib.request

from config import PROJECT_ROOT, REQUEST_DELAY_SECS


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
