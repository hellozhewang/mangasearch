"""SQLite cache for API responses, plus one-time migration from the old pickles."""

import json
import pickle
import random
import sqlite3
import time

from config import DAY, LEGACY_PICKLES, TTL


class Cache:
    """One SQLite file holding all cached API responses.

    entities: (kind, id) -> JSON blob with a jittered expiry timestamp.
    kv:       small singletons like the raw search-result list.
    """

    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                kind       TEXT NOT NULL,
                id         INTEGER NOT NULL,
                data       TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (kind, id)
            ) WITHOUT ROWID''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS kv (
                key        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                updated_at REAL NOT NULL
            )''')
        self.db.commit()

    def get_many(self, kind, ids, include_expired=False):
        """Batch-fetch {id: entry} for every cached id in `ids` — one query
        per 500 ids instead of one lookup per record."""
        now = time.time()
        out = {}
        ids = list(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ','.join('?' * len(chunk))
            rows = self.db.execute(
                f'SELECT id, data, expires_at FROM entities '
                f'WHERE kind = ? AND id IN ({marks})', [kind] + chunk)
            for id_, data, expires_at in rows:
                if include_expired or expires_at > now:
                    out[id_] = json.loads(data)
        return out

    def put(self, kind, id_, value):
        expires_at = time.time() + random.randint(*TTL[kind])
        self.db.execute(
            'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
            'VALUES (?, ?, ?, ?)', (kind, id_, json.dumps(value), expires_at))

    def kv_get(self, key, max_age_secs):
        row = self.db.execute(
            'SELECT data, updated_at FROM kv WHERE key = ?', (key,)).fetchone()
        if row and time.time() - row[1] < max_age_secs:
            return json.loads(row[0])
        return None

    def kv_put(self, key, value):
        self.db.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), time.time()))
        self.db.commit()

    def commit(self):
        self.db.commit()

    def entity_count(self):
        return self.db.execute('SELECT COUNT(*) FROM entities').fetchone()[0]


def migrate_legacy_pickles(cache):
    """One-time import of the old pickle caches into SQLite."""
    if cache.entity_count() > 0:
        return
    for kind in ('series', 'rating'):
        path = LEGACY_PICKLES[kind]
        if not path.is_file():
            continue
        with open(path, 'rb') as fh:
            data = pickle.load(fh)
        for id_, entry in data.items():
            # Old stamps were written as write_time + jitter and considered
            # fresh for 10 more days; keep that expiry on import.
            stamp = entry.pop('cache_timestamp', time.time())
            cache.db.execute(
                'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
                'VALUES (?, ?, ?, ?)',
                (kind, id_, json.dumps(entry), stamp + 10 * DAY))
        print(f'Migrated {len(data)} {kind} entries from {path.name}')
    search_path = LEGACY_PICKLES['search']
    if search_path.is_file():
        with open(search_path, 'rb') as fh:
            results = pickle.load(fh)
        cache.db.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            ('search_results', json.dumps(results), search_path.stat().st_mtime))
        print(f'Migrated {len(results)} search results from {search_path.name}')
    cache.commit()
