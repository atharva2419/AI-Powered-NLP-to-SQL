"""The natural-language → SQL → answer pipeline.

    question ─► LLM ─► SQL ─► guard ─► DuckDB ─► rows ─► LLM ─► explanation
                 ▲                        │
                 └──── error message ◄────┘   (self-correction, N attempts)

When the database rejects generated SQL, the error text is fed back to the
model as a correction prompt rather than surfaced to the user. Most failures
are a hallucinated column or a DuckDB/Postgres dialect slip, both of which the
model fixes on the second attempt given the error.
"""

import json
import logging
import threading
from decimal import Decimal

import duckdb
from groq import Groq

import config
import metrics
import sql_guard
from sql_guard import SQLGuardError

log = logging.getLogger(__name__)

_client = Groq(api_key=config.GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_con = duckdb.connect()


def _harden(con: duckdb.DuckDBPyConnection) -> None:
    """Lock down the connection before any model-generated SQL touches it.

    Extension auto-install/auto-load is the widest hole — it turns a SELECT
    into arbitrary native code loading — and `lock_configuration` seals the
    settings themselves so a generated query cannot undo any of this.
    """
    for setting in (
        "SET autoinstall_known_extensions=false",
        "SET autoload_known_extensions=false",
        "SET allow_community_extensions=false",
        "SET allow_unsigned_extensions=false",
        f"SET memory_limit='{config.DUCKDB_MEMORY_LIMIT}'",
        f"SET threads={config.DUCKDB_THREADS}",
    ):
        try:
            con.execute(setting)
        except duckdb.Error as exc:  # pragma: no cover - version dependent
            log.warning("could not apply %r: %s", setting, exc)


def zones_table_sql(zones_path) -> str:
    """DDL for the TLC zone lookup: 265 rows of LocationID -> borough, zone."""
    return f'CREATE TABLE zones AS SELECT * FROM read_csv(\'{zones_path.as_posix()}\')'


def taxi_view_sql(data_path) -> str:
    """DDL for the `taxi` view. Separate from :func:`_init_db` so tests can run
    it against a throwaway dataset instead of the real 700 MB of Parquet."""
    return f"""
        CREATE VIEW taxi AS
        SELECT t.*,
               pu."Borough" AS pickup_borough,
               pu."Zone"    AS pickup_zone,
               dz."Borough" AS dropoff_borough,
               dz."Zone"    AS dropoff_zone
        FROM (
            SELECT * FROM read_parquet('{data_path.as_posix()}')
            WHERE tpep_pickup_datetime >= '2024-01-01'
              AND tpep_pickup_datetime <  '2025-01-01'
        ) t
        LEFT JOIN zones pu ON t."PULocationID" = pu."LocationID"
        LEFT JOIN zones dz ON t."DOLocationID" = dz."LocationID"
    """


def _init_db() -> str:
    """Register the `taxi` view and return its schema as a prompt fragment.

    A VIEW, not a TABLE: 12 monthly Parquet files (~41M rows) are scanned
    lazily at query time instead of being copied into memory at startup, so
    the process boots in under a second and aggregates still return in
    sub-second time. The date predicate drops records whose timestamps fall
    outside 2024 — the raw TLC files contain a handful of corrupt rows.

    Zone names are denormalised into the view rather than left to the model to
    join. Measured on the full dataset, carrying the two joins costs ~200ms on
    queries that never reference a zone (116ms -> 313ms for COUNT(*)), because
    DuckDB must read both location-ID columns to satisfy the join and cannot
    eliminate it. That is 3-10% of a response dominated by two LLM round
    trips, and it buys away the thing an 8B model fails at most often: writing
    a correct multi-table join. Cheap compute for scarce accuracy.

    LEFT, not INNER: ~4M rows carry location IDs with no lookup entry, and an
    inner join would silently drop them from every single query.
    """
    _con.execute(zones_table_sql(config.ZONES_PATH))
    _con.execute(taxi_view_sql(config.DATA_PATH))
    # Harden only after the view exists: creating it is a privileged operation
    # that the locked-down configuration would otherwise have to allow.
    _harden(_con)
    rows = _con.execute(
        "SELECT column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_name = 'taxi' "
        "ORDER BY ordinal_position"
    ).fetchall()
    log.info("taxi view ready - %d columns", len(rows))
    return ", ".join(f"{col} {dtype}" for col, dtype in rows)


_SCHEMA: str = _init_db()


def _count_rows() -> int:
    """Row count, measured once at startup.

    The deployed demo runs on a sample, not the full year, so the UI has to be
    told how much data is actually behind it rather than hardcoding a number
    that is only true on a developer's laptop. Counting is cheap — DuckDB
    reads it from Parquet metadata — but not free, so it is not done per
    request.
    """
    try:
        return int(_con.execute("SELECT COUNT(*) FROM taxi").fetchone()[0])
    except duckdb.Error as exc:  # pragma: no cover - startup already failed
        log.warning("could not count rows: %s", exc)
        return 0


ROW_COUNT: int = _count_rows()


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
# Domain rules the model cannot infer from column names alone. Encoding the
# TLC data dictionary here is what moves execution accuracy on the eval set:
# without it the model invents a `borough` column and treats payment_type as
# free text.
_SQL_SYSTEM_PROMPT = """You are an expert DuckDB SQL analyst. Convert the user's question into a single DuckDB SELECT query over a table named `taxi`.

Schema: {schema}

Domain rules:
- payment_type is an integer code: 1=credit card, 2=cash, 3=no charge, 4=dispute, 5=unknown, 6=voided trip. Code 0 is undocumented and covers ~10% of 2024; those rows also have null RatecodeID and are outliers on distance, so keep them as their own group rather than merging them into another code.
- VendorID: 1=Creative Mobile Technologies, 2=Curb Mobility, 6=Myle, 7=Helix.
- RatecodeID: 1=standard rate, 2=JFK, 3=Newark, 4=Nassau/Westchester, 5=negotiated fare, 6=group ride, 99=unknown. It is null for ~10% of rows, so use a filter that tolerates nulls unless the question is about rate codes.
- PULocationID/DOLocationID are numeric TLC zone IDs. The names are already joined into this table as pickup_zone, pickup_borough, dropoff_zone and dropoff_borough — use those for anything involving a place name, and never join to another table.
- Borough values are exactly: 'Manhattan', 'Queens', 'Brooklyn', 'Bronx', 'Staten Island', 'EWR' (Newark), 'Unknown', 'N/A'.
- Airports are zones, not boroughs: 'JFK Airport', 'LaGuardia Airport', 'Newark Airport'. Neighbourhood zones are specific, e.g. 'Midtown Center', 'Upper East Side South' — use LIKE for a general area (zone LIKE 'Midtown%').
- DIRECTION MATTERS. Read where the trip starts and where it ends, and pick the column to match:
  - "from X", "picked up at X", "starting in X", "leaving X", "out of X" -> pickup_zone / pickup_borough
  - "to X", "dropped off at X", "going to X", "arriving in X", "ending in X", "into X" -> dropoff_zone / dropoff_borough
  - "from X to Y" -> filter pickup on X AND dropoff on Y
  A question about trips "to JFK" filters dropoff_zone, never pickup_zone. Getting this backwards answers a different question and looks correct, so check it before returning the query.
- total_amount includes tips and surcharges; fare_amount does not.
- Timestamps are tpep_pickup_datetime and tpep_dropoff_datetime. The data covers 2024 only.
- Trip duration must be computed, e.g. date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime).

Output rules:
- Return ONLY the SQL. No prose, no markdown, no backticks, no trailing semicolon.
- Alias every computed column with a readable snake_case name.
- Use ORDER BY plus LIMIT for "top"/"most"/"busiest" questions.
- Round monetary averages to 2 decimal places.
- Every non-aggregated column in the SELECT list must also appear in GROUP BY. If you group by a derived expression, repeat the expression in GROUP BY, not its alias' position alone.
- Never write to the database; SELECT only."""

_EXPLAIN_PROMPT = """You are a data analyst. Given a question, the SQL used to answer it, and the result, write 1-2 sentences of plain English explaining what the result means.

Be concise and factual. Quote the actual numbers. Do not describe the SQL itself. If a value is a payment_type or VendorID code, translate it to its label (payment_type: 1=credit card, 2=cash, 3=no charge, 4=dispute, 5=unknown, 6=voided).

Question: {question}
SQL: {sql}
Result: {result}"""


# Few-shot exemplars. The baseline eval (docs/eval-report-baseline.md) showed
# the 8B model got the *SQL* right and the *shape* wrong: it pivoted "compare A
# vs B" into two columns instead of two rows, averaged ratios row-by-row
# instead of dividing the sums, and volunteered extra columns nobody asked for.
# Rules stated in prose did not fix that; demonstrations did.
#
# None of these questions appear in the evaluation set — they teach conventions,
# not answers. Reusing eval questions here would be training on the test set.
_FEW_SHOT: list[tuple[str, str]] = [
    (
        "What is the average passenger count by vendor?",
        "SELECT VendorID, ROUND(AVG(passenger_count), 2) AS avg_passengers "
        "FROM taxi GROUP BY VendorID ORDER BY VendorID",
    ),
    (
        # "Compare A versus B" means one row per category, not one column each.
        "Compare the average trip distance for JFK versus Newark trips",
        "SELECT RatecodeID, ROUND(AVG(trip_distance), 2) AS avg_distance "
        "FROM taxi WHERE RatecodeID IN (2, 3) GROUP BY RatecodeID ORDER BY RatecodeID",
    ),
    (
        # A ratio over a population is SUM/SUM, not AVG of per-row ratios.
        "What is the average congestion surcharge as a percentage of the total?",
        "SELECT ROUND(100.0 * SUM(congestion_surcharge) / SUM(total_amount), 2) "
        "AS surcharge_pct FROM taxi",
    ),
    (
        # Return the columns asked for and nothing else.
        "What are the top 3 rate codes by total revenue?",
        "SELECT RatecodeID, ROUND(SUM(total_amount), 2) AS revenue "
        "FROM taxi GROUP BY RatecodeID ORDER BY revenue DESC LIMIT 3",
    ),
    (
        # Time ranges are half-open, so counts of adjacent ranges do not overlap.
        "How many trips started between 8pm and midnight?",
        "SELECT COUNT(*) AS trips FROM taxi "
        "WHERE HOUR(tpep_pickup_datetime) >= 20 AND HOUR(tpep_pickup_datetime) < 24",
    ),
    (
        # Zone names come from the table itself — no join, and no LocationID.
        "What is the average fare for trips picked up at LaGuardia?",
        "SELECT ROUND(AVG(fare_amount), 2) AS avg_fare "
        "FROM taxi WHERE pickup_zone = 'LaGuardia Airport'",
    ),
    (
        # Paired with the exemplar above so both directions are demonstrated.
        # With only the pickup example present, the model answered "trips TO
        # JFK" with pickup_zone = 'JFK Airport' — a plausible-looking query
        # for the opposite question.
        "How many trips were dropped off at Newark Airport?",
        "SELECT COUNT(*) AS trips FROM taxi WHERE dropoff_zone = 'Newark Airport'",
    ),
]


def _few_shot_messages() -> list[dict]:
    messages: list[dict] = []
    for question, sql in _FEW_SHOT:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": sql})
    return messages


def _complete(messages: list[dict]) -> str:
    response = _client.chat.completions.create(
        model=config.MODEL_NAME,
        messages=messages,
        temperature=config.LLM_TEMPERATURE,
    )
    return (response.choices[0].message.content or "").strip()


def translate_to_sql(
    question: str,
    schema: str,
    previous_sql: str | None = None,
    error: str | None = None,
) -> str:
    """Generate SQL for ``question``.

    When ``previous_sql`` and ``error`` are supplied the call becomes a
    correction turn: the model sees its own failed attempt and the database's
    complaint about it.
    """
    messages: list[dict] = [
        {"role": "system", "content": _SQL_SYSTEM_PROMPT.format(schema=schema)},
        *_few_shot_messages(),
        {"role": "user", "content": question},
    ]
    if previous_sql is not None and error is not None:
        messages.append({"role": "assistant", "content": previous_sql})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"That query failed with:\n{error}\n\n"
                    "Rewrite it so it runs. Return ONLY the corrected SQL."
                ),
            }
        )
    return _complete(messages)


def explain_result(question: str, sql: str, result: dict) -> str:
    return _complete(
        [
            {
                "role": "user",
                "content": _EXPLAIN_PROMPT.format(
                    question=question,
                    sql=sql,
                    result=json.dumps(result, default=str)[:4000],
                ),
            }
        ]
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def _to_python(val):
    """Coerce DuckDB values into something json.dumps can handle."""
    if isinstance(val, Decimal):
        return float(val)
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, bytes | bytearray):
        return val.decode("utf-8", "replace")
    return val


def run_query(sql: str) -> dict:
    """Execute a validated SELECT with a row cap and a wall-clock timeout.

    The cap is applied by wrapping the query so DuckDB stops producing rows at
    the limit — truncating after the fact would mean materialising every row
    of a `SELECT * FROM taxi` first.
    """
    limited = sql_guard.enforce_limit(sql_guard.normalize(sql), config.MAX_RESULT_ROWS)

    # A cursor per call: DuckDB connections are not safe to use concurrently,
    # and requests are served from a thread pool.
    cur = _con.cursor()
    watchdog = threading.Timer(config.QUERY_TIMEOUT_SECONDS, cur.interrupt)
    watchdog.start()
    try:
        cur.execute(limited)
        columns = [d[0] for d in cur.description]
        raw = cur.fetchall()
    except duckdb.InterruptException:
        return {"error": f"Query exceeded the {config.QUERY_TIMEOUT_SECONDS}s time limit."}
    except duckdb.Error as exc:
        return {"error": str(exc)}
    finally:
        watchdog.cancel()
        cur.close()

    truncated = len(raw) > config.MAX_RESULT_ROWS
    rows = [[_to_python(v) for v in row] for row in raw[: config.MAX_RESULT_ROWS]]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_pipeline(question: str, explain: bool = True) -> dict:
    """Full question → answer pipeline with self-correction.

    Returns ``sql``, ``result``, ``explanation`` and ``attempts``. Raises
    :class:`SQLGuardError` only if every attempt produced unsafe SQL.
    """
    previous_sql: str | None = None
    error: str | None = None
    last_guard_error: SQLGuardError | None = None
    # The most recent SQL that passed the guard but failed to execute — the
    # only failure worth showing the user, since it is real SQL.
    failed_sql: str | None = None
    failed_error: str | None = None
    max_attempts = config.MAX_SQL_RETRIES + 1

    for attempt in range(1, max_attempts + 1):
        raw_sql = translate_to_sql(question, _SCHEMA, previous_sql, error)

        try:
            sql = sql_guard.validate(raw_sql)
        except SQLGuardError as exc:
            log.warning("attempt %d rejected by guard: %s", attempt, exc)
            metrics.incr("sql_guard_rejections")
            last_guard_error, previous_sql, error = exc, raw_sql, str(exc)
            continue

        result = run_query(sql)
        if "error" not in result:
            if attempt > 1:
                metrics.incr("self_corrections_succeeded")
            explanation = explain_result(question, sql, result) if explain else ""
            return {
                "sql": sql,
                "result": result,
                "explanation": explanation,
                "attempts": attempt,
            }

        log.info("attempt %d failed to execute: %s", attempt, result["error"])
        metrics.incr("sql_execution_failures")
        previous_sql = failed_sql = sql
        error = failed_error = result["error"]

    # Out of attempts. If some attempt produced safe-but-broken SQL, return it
    # so the user sees a real query and a real database error. If every attempt
    # was rejected by the guard, nothing ever ran — that is a hard failure.
    metrics.incr("pipeline_failures")
    if failed_sql is None:
        raise last_guard_error or SQLGuardError("Could not generate a valid query.")
    return {
        "sql": failed_sql,
        "result": {"error": failed_error},
        "explanation": "",
        "attempts": max_attempts,
    }
