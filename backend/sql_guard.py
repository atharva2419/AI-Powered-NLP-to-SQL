"""Validation layer between LLM-generated SQL and the database.

The model is untrusted input. A keyword denylist is not enough: DuckDB can
write files (`COPY ... TO`), mount other databases (`ATTACH`), load native
extensions (`INSTALL`/`LOAD`) and read arbitrary paths from inside an
otherwise innocent-looking `SELECT` (`read_csv('/etc/passwd')`). Substring
matching also can't see through string literals, comments or stacked
statements.

So validation happens in three layers:

1. **Parse with DuckDB's own parser** (`extract_statements`) and require
   exactly one statement whose type is SELECT. This is the same parser that
   will execute the query, so there is no dialect gap for an attacker to slip
   through, and it settles statement-stacking and comment tricks for free.
2. **Reject filesystem/extension functions** by name, since those are
   reachable from within a legitimate SELECT.
3. **Enforce a row limit inside the database** by wrapping the query, so a
   `SELECT *` over 41M rows is never materialised into memory.
"""

import re

import duckdb

# Functions that reach outside the loaded dataset. All are callable from
# inside a plain SELECT, so the statement-type check above does not cover them.
_BLOCKED_FUNCTIONS = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "parquet_scan",
        "read_json",
        "read_json_auto",
        "read_json_objects",
        "read_ndjson",
        "read_ndjson_auto",
        "read_ndjson_objects",
        "read_text",
        "read_blob",
        "csv_scan",
        "sniff_csv",
        "glob",
        "install",
        "load",
        "parquet_metadata",
        "parquet_schema",
        "parquet_file_metadata",
        "duckdb_extensions",
        "duckdb_settings",
        "shell",
    }
)

# DuckDB's parser reports `PRAGMA ...` as StatementType.SELECT, so the type
# check below cannot see it. Anything that must not start a query gets caught
# here instead. (CALL/SET/EXPORT already get distinct statement types; they
# are listed for defence in depth, not because the type check misses them.)
_FORBIDDEN_LEADING = frozenset({"PRAGMA", "CALL", "SET", "RESET", "EXPORT", "IMPORT"})

_FENCE_RE = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.IGNORECASE)
_LEADING_WORD_RE = re.compile(r"^\s*(?:/\*.*?\*/\s*|--[^\n]*\n\s*)*([a-zA-Z_]+)", re.DOTALL)
_FUNC_CALL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

# A dedicated parse-only connection: it never sees the data and is only used
# to reach DuckDB's parser.
_parser = duckdb.connect()


class SQLGuardError(ValueError):
    """Raised when generated SQL is unsafe or unparseable.

    The message is deliberately descriptive — it is fed back to the model as
    the correction prompt in the self-healing retry loop.
    """


def normalize(sql: str) -> str:
    """Strip markdown fences and trailing semicolons the LLM tends to add."""
    cleaned = _FENCE_RE.sub("", sql.strip())
    return cleaned.strip().rstrip(";").strip()


def _blocked_functions_in(sql: str) -> set[str]:
    called = {m.group(1).lower() for m in _FUNC_CALL_RE.finditer(sql)}
    return called & _BLOCKED_FUNCTIONS


def validate(sql: str) -> str:
    """Return normalized SQL, or raise :class:`SQLGuardError`."""
    statement = normalize(sql)
    if not statement:
        raise SQLGuardError("Empty query.")

    leading = _LEADING_WORD_RE.match(statement)
    if leading and leading.group(1).upper() in _FORBIDDEN_LEADING:
        raise SQLGuardError(
            f"Only SELECT queries are permitted; this is a "
            f"{leading.group(1).upper()} statement."
        )

    try:
        parsed = _parser.extract_statements(statement)
    except duckdb.Error as exc:
        raise SQLGuardError(f"Query does not parse: {exc}") from exc

    if len(parsed) == 0:
        raise SQLGuardError("Empty query.")
    if len(parsed) > 1:
        raise SQLGuardError(
            f"Expected a single statement, got {len(parsed)}. "
            "Only one read-only SELECT is permitted."
        )

    stmt_type = parsed[0].type
    if stmt_type != duckdb.StatementType.SELECT:
        name = getattr(stmt_type, "name", str(stmt_type))
        raise SQLGuardError(
            f"Only SELECT queries are permitted; this is a {name} statement."
        )

    blocked = _blocked_functions_in(statement)
    if blocked:
        raise SQLGuardError(
            f"Query calls disallowed function(s): {', '.join(sorted(blocked))}. "
            "Only the pre-loaded 'taxi' table may be read."
        )

    return statement


def enforce_limit(sql: str, max_rows: int) -> str:
    """Wrap a validated SELECT so the database itself caps the row count.

    One extra row is requested so the caller can tell "exactly at the limit"
    apart from "truncated".
    """
    return f"SELECT * FROM ({sql}) AS _guarded LIMIT {max_rows + 1}"


def prepare(sql: str, max_rows: int) -> tuple[str, str]:
    """Validate raw model output and return ``(clean_sql, executable_sql)``.

    ``clean_sql`` is what the user is shown; ``executable_sql`` is the
    row-capped form that actually runs.
    """
    clean = validate(sql)
    return clean, enforce_limit(clean, max_rows)
