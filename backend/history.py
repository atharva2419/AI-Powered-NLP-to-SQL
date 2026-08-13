import json
import sqlite3

import config

_DB_PATH = config.HISTORY_DB_PATH


def init_db() -> None:
    with sqlite3.connect(_DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                question    TEXT    NOT NULL,
                sql         TEXT    NOT NULL,
                result      TEXT    NOT NULL,
                explanation TEXT    NOT NULL,
                latency_ms  INTEGER NOT NULL,
                created_at  TEXT    NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
        """)


def save_query(
    question: str,
    sql: str,
    result: dict,
    explanation: str,
    latency_ms: int,
) -> None:
    with sqlite3.connect(_DB_PATH) as con:
        con.execute(
            "INSERT INTO query_history (question, sql, result, explanation, latency_ms) "
            "VALUES (?, ?, ?, ?, ?)",
            (question, sql, json.dumps(result), explanation, latency_ms),
        )


def get_history(limit: int = 20) -> list[dict]:
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, question, sql, result, explanation, latency_ms, created_at "
            "FROM query_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "question": r["question"],
            "sql": r["sql"],
            "result": json.loads(r["result"]),
            "explanation": r["explanation"],
            "latency_ms": r["latency_ms"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
