"""SQLite store for API data.

Not a throwaway cache: this is the persistent local copy of MangaUpdates data.
Entries carry an `expires_at` deadline; when it lives and by how much is the
caller's policy (see logic.py), the store only persists and filters by it.
"""

import json
import sqlite3
import time


class Database:
    """One SQLite file holding all fetched API data.

    entities: (kind, id) -> JSON blob with a jittered refresh deadline.
    kv:       small singletons like the raw search-result list.
    """

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute('PRAGMA journal_mode=WAL')
        # Wait out other writers (e.g. the refresh thread) instead of raising
        # "database is locked" immediately.
        self.conn.execute('PRAGMA busy_timeout=15000')
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
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS listed (
                series_id  INTEGER PRIMARY KEY,
                list_id    INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS lists (
                list_id    INTEGER PRIMARY KEY,
                title      TEXT NOT NULL,
                icon       TEXT NOT NULL DEFAULT '',
                custom     INTEGER NOT NULL DEFAULT 0,
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

    def put(self, kind, id_, value, expires_at):
        self.conn.execute(
            'INSERT OR REPLACE INTO entities (kind, id, data, expires_at) '
            'VALUES (?, ?, ?, ?)', (kind, id_, json.dumps(value), expires_at))

    def kv_get(self, key, max_age_secs):
        row = self.conn.execute(
            'SELECT data, updated_at FROM kv WHERE key = ?', (key,)).fetchone()
        if row and time.time() - row[1] < max_age_secs:
            return json.loads(row[0])
        return None

    def kv_age(self, key):
        """Seconds since the kv entry was written, or None if absent."""
        row = self.conn.execute(
            'SELECT updated_at FROM kv WHERE key = ?', (key,)).fetchone()
        return time.time() - row[0] if row else None

    def kv_put(self, key, value):
        self.conn.execute(
            'INSERT OR REPLACE INTO kv (key, data, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), time.time()))
        self.conn.commit()

    def commit(self):
        self.conn.commit()

    def entity_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM entities').fetchone()[0]

    def save_listed(self, pairs):
        """Replace the map of which series sit on which of my lists."""
        now = time.time()
        self.conn.execute('DELETE FROM listed')
        self.conn.executemany(
            'INSERT OR REPLACE INTO listed (series_id, list_id, updated_at) '
            'VALUES (?, ?, ?)', [(s_id, l_id, now) for s_id, l_id in pairs])
        self.conn.commit()

    def upsert_listed(self, series_id, list_id):
        self.conn.execute(
            'INSERT OR REPLACE INTO listed (series_id, list_id, updated_at) '
            'VALUES (?, ?, ?)', (series_id, list_id, time.time()))
        self.conn.commit()

    def get_listed(self):
        """{series_id: list_id} for every series on any of my lists."""
        return dict(self.conn.execute('SELECT series_id, list_id FROM listed'))

    def save_lists(self, lists):
        """Replace the user-list map (list_id -> title/icon)."""
        now = time.time()
        self.conn.execute('DELETE FROM lists')
        self.conn.executemany(
            'INSERT INTO lists (list_id, title, icon, custom, updated_at) '
            'VALUES (?, ?, ?, ?, ?)',
            [(l['id'], l['title'], l['icon'], int(l['custom']), now) for l in lists])
        self.conn.commit()

    def get_lists(self, max_age_secs):
        """Return the stored user lists, or None if missing/stale."""
        rows = self.conn.execute(
            'SELECT list_id, title, icon, custom, updated_at FROM lists '
            'ORDER BY list_id').fetchall()
        if not rows or time.time() - min(r[4] for r in rows) > max_age_secs:
            return None
        return [{'id': r[0], 'title': r[1], 'icon': r[2], 'custom': bool(r[3])}
                for r in rows]
