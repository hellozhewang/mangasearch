"""SQLite store for API data.

Not a throwaway cache: this is the persistent local copy of MangaUpdates data.
Entries carry a jittered `expires_at` so stale ones get refreshed from the API
a few at a time instead of all at once.
"""

import json
import random
import sqlite3
import time

from config import TTL


class Database:
    """One SQLite file holding all fetched API data.

    entities: (kind, id) -> JSON blob with a jittered refresh deadline.
    kv:       small singletons like the raw search-result list.
    """

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                kind       TEXT NOT NULL,
                id         INTEGER NOT NULL,
                data       TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (kind, id)
            ) WITHOUT ROWID''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS kv (
                key        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                updated_at REAL NOT NULL
            )''')
        self.conn.commit()

    def get_many(self, kind, ids, include_expired=False):
        """Batch-fetch {id: entry} for every stored id in `ids` — one query
        per 500 ids instead of one lookup per record."""
        now = time.time()
        out = {}
        ids = list(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ','.join('?' * len(chunk))
            rows = self.conn.execute(
                f'SELECT id, data, expires_at FROM entities '
                f'WHERE kind = ? AND id IN ({marks})', [kind] + chunk)
            for id_, data, expires_at in rows:
                if include_expired or expires_at > now:
                    out[id_] = json.loads(data)
        return out

    def put(self, kind, id_, value):
        expires_at = time.time() + random.randint(*TTL[kind])
        self.conn.execute(
            'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
            'VALUES (?, ?, ?, ?)', (kind, id_, json.dumps(value), expires_at))

    def kv_get(self, key, max_age_secs):
        row = self.conn.execute(
            'SELECT data, updated_at FROM kv WHERE key = ?', (key,)).fetchone()
        if row and time.time() - row[1] < max_age_secs:
            return json.loads(row[0])
        return None

    def kv_put(self, key, value):
        self.conn.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), time.time()))
        self.conn.commit()

    def commit(self):
        self.conn.commit()

    def entity_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
