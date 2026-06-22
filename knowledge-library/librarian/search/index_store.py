"""The SQLite vector index: one row per article (metadata + a float32 vector
blob) and a key/value meta table. Vault-agnostic; knows nothing about embeddings
or queries. Vectors are stored exactly as handed in (the indexer L2-normalizes
them first)."""
import sqlite3

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY,
    relative_path TEXT, title TEXT, summary TEXT,
    primary_category TEXT, topics TEXT, content_hash TEXT,
    dim INTEGER, vector BLOB);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_META_KEYS = ("url", "relative_path", "title", "summary",
              "primary_category", "topics", "content_hash")


class IndexStore:
    def __init__(self, conn):
        self.conn = conn

    @classmethod
    def open(cls, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn)

    def upsert(self, records):
        for rec in records:
            vec = np.asarray(rec["vector"], dtype=np.float32)
            self.conn.execute(
                "INSERT INTO articles"
                "(url,relative_path,title,summary,primary_category,topics,"
                " content_hash,dim,vector) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(url) DO UPDATE SET "
                "relative_path=excluded.relative_path,title=excluded.title,"
                "summary=excluded.summary,primary_category=excluded.primary_category,"
                "topics=excluded.topics,content_hash=excluded.content_hash,"
                "dim=excluded.dim,vector=excluded.vector",
                (rec["url"], rec["relative_path"], rec["title"], rec["summary"],
                 rec["primary_category"], rec["topics"], rec["content_hash"],
                 int(vec.shape[0]), vec.tobytes()))
        self.conn.commit()

    def delete(self, urls):
        self.conn.executemany("DELETE FROM articles WHERE url=?",
                              [(u,) for u in urls])
        self.conn.commit()

    def hashes(self):
        return {u: h for u, h in
                self.conn.execute("SELECT url, content_hash FROM articles")}

    def load_matrix(self):
        cur = self.conn.execute(
            "SELECT url,relative_path,title,summary,primary_category,topics,"
            "content_hash,vector FROM articles ORDER BY url")
        metas, vecs = [], []
        for row in cur:
            metas.append(dict(zip(_META_KEYS, row[:7])))
            vecs.append(np.frombuffer(row[7], dtype=np.float32))
        matrix = np.vstack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)
        return metas, matrix

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def get_meta(self, key):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?",
                               (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        self.conn.commit()

    def close(self):
        self.conn.close()
