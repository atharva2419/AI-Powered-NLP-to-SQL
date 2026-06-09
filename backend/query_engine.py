import json
import os
import re
from pathlib import Path

import duckdb
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

DATA_PATH = Path(
    os.getenv("TAXI_DATA_PATH", str(Path(__file__).parent / "data" / "taxi.parquet"))
)
MODEL_NAME = "llama-3.1-8b-instant"

# ---------------------------------------------------------------------------
# Startup: load parquet, print schema
# ---------------------------------------------------------------------------
_con = duckdb.connect()


def _init_db() -> str:
    _con.execute(f"CREATE TABLE taxi AS SELECT * FROM read_parquet('{DATA_PATH}')")
    rows = _con.execute(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'taxi' "
        "ORDER BY ordinal_position"
    ).fetchall()
    print("taxi schema:")
    for col, dtype in rows:
        print(f"  {col}: {dtype}")
    return ", ".join(f"{col} {dtype}" for col, dtype in rows)


_SCHEMA: str = _init_db()


# ---------------------------------------------------------------------------
# translate_to_sql
# ---------------------------------------------------------------------------
def translate_to_sql(question: str, schema: str) -> str:
    prompt = (
        "You are a SQL expert. Convert the user's question to a DuckDB SQL query "
        f"over a table called 'taxi' with this schema: {schema}. "
        "Return ONLY the SQL query, no explanation, no markdown, no backticks.\n\n"
        f"Question: {question}"
    )
    response = _client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# run_query
# ---------------------------------------------------------------------------
def _to_python(val):
    try:
        import numpy as np
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, np.floating):
            return float(val)
        if isinstance(val, np.bool_):
            return bool(val)
    except ImportError:
        pass
    return str(val) if hasattr(val, "isoformat") else val


def run_query(sql: str) -> dict:
    try:
        df = _con.execute(sql).fetchdf().head(100)
        rows = [
            [_to_python(v) for v in row]
            for row in df.itertuples(index=False, name=None)
        ]
        return {
            "columns": list(df.columns),
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# explain_result  (streaming)
# ---------------------------------------------------------------------------
def explain_result(question: str, sql: str, result: dict) -> str:
    prompt = (
        "You are a helpful data analyst. Given a question, the SQL used to answer "
        "it, and the query result, write 1-2 sentences of plain English explaining "
        "what the result means. Be concise and factual.\n\n"
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"Result: {json.dumps(result, default=str)}"
    )
    full_text = ""
    for chunk in _client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    ):
        text = chunk.choices[0].delta.content or ""
        print(text, end="", flush=True)
        full_text += text
    print()
    return full_text


# ---------------------------------------------------------------------------
# SQL safety validation
# ---------------------------------------------------------------------------
_BLOCKED_KEYWORDS = {"DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER"}


def _validate_sql(statement: str) -> None:
    tokens = set(re.findall(r'\b[A-Za-z_]+\b', statement.upper()))
    blocked = tokens & _BLOCKED_KEYWORDS
    if blocked:
        raise ValueError(
            f"Query contains disallowed operation(s): {', '.join(sorted(blocked))}. "
            "Only SELECT queries are permitted."
        )


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------
def run_pipeline(question: str) -> dict:
    sql = translate_to_sql(question, _SCHEMA)
    _validate_sql(sql)
    result = run_query(sql)
    if "error" in result:
        return {"sql": sql, "result": result, "explanation": ""}
    explanation = explain_result(question, sql, result)
    return {"sql": sql, "result": result, "explanation": explanation}


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    q = "How many taxi trips were there and what was the average fare?"
    out = run_pipeline(q)
    print("\n--- pipeline output ---")
    print("sql        :", out["sql"])
    print("result     :", out["result"])
    print("explanation:", out["explanation"])
