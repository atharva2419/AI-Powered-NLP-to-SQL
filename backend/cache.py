"""Question-level response cache.

Every question costs two LLM round-trips (translate + explain), which is both
the slowest and the only paid part of the pipeline. Because generation runs at
temperature 0, the same question deterministically yields the same SQL — so
the whole response is safe to memoize.

Backed by SQLite rather than a dict so the cache survives restarts and is
shared across worker processes, and by the same file as the query history to
keep the deployment to a single writable path.
"""

import json
import sqlite3
import time
from hashlib import sha256

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_cache (
    key        TEXT    PRIMARY KEY,
    question   TEXT    NOT NULL,
    payload    TEXT    NOT NULL,
    created_at REAL    NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0
)
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(config.HISTORY_DB_PATH)


def init_db() -> None:
    with _connect() as con:
        con.execute(_SCHEMA)


def make_key(question: str) -> str:
    """Normalize a question so trivial variations share a cache entry.

    Case, surrounding whitespace, internal run-length of whitespace and a
    trailing question mark are all insignificant. The model name is part of
    the key so switching models does not serve stale answers.
    """
    normalized = " ".join(question.lower().split()).rstrip("?").strip()
    return sha256(f"{config.MODEL_NAME}::{normalized}".encode()).hexdigest()


def get(question: str) -> dict | None:
    """Return the cached payload for ``question``, or None on miss/expiry."""
    if not config.CACHE_ENABLED:
        return None
    key = make_key(question)
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT payload, created_at FROM query_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            payload, created_at = row
            if time.time() - created_at > config.CACHE_TTL_SECONDS:
                con.execute("DELETE FROM query_cache WHERE key = ?", (key,))
                return None
            con.execute("UPDATE query_cache SET hits = hits + 1 WHERE key = ?", (key,))
            return json.loads(payload)
    except (sqlite3.Error, json.JSONDecodeError):
        # A cache is an optimisation; never let it break a request.
        return None


def put(question: str, payload: dict) -> None:
    if not config.CACHE_ENABLED:
        return
    try:
        with _connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO query_cache (key, question, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (make_key(question), question, json.dumps(payload), time.time()),
            )
    except (sqlite3.Error, TypeError, ValueError):
        pass


def clear() -> None:
    with _connect() as con:
        con.execute("DELETE FROM query_cache")


def stats() -> dict:
    """Entry count and cumulative hit count, for the metrics endpoint."""
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(hits), 0) FROM query_cache"
            ).fetchone()
        return {"entries": row[0], "cumulative_hits": row[1]}
    except sqlite3.Error:
        return {"entries": 0, "cumulative_hits": 0}
