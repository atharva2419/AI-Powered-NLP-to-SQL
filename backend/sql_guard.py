"""Validation layer between LLM-generated SQL and the database.

The model is untrusted input. A keyword denylist is not enough: DuckDB can
write files (`COPY ... TO`), mount other databases (`ATTACH`), load native
extensions (`INSTALL`/`LOAD`) and read arbitrary paths from inside an
otherwise innocent-looking `SELECT` (`read_csv('/etc/passwd')`). Substring
matching also can't see through string literals, comments or stacked
statements.

So validation happens in four layers:

1. **Parse with DuckDB's own parser** (`extract_statements`) and require
   exactly one statement whose type is SELECT. This is the same parser that
   will execute the query, so there is no dialect gap for an attacker to slip
   through, and it settles statement-stacking and comment tricks for free.
2. **Reject a leading PRAGMA**, which DuckDB reports as StatementType.SELECT
   and which layer 1 therefore cannot see.
3. **Reject disallowed identifiers** — filesystem readers, catalog
   introspection, config disclosure — because all of them are perfectly
   ordinary SELECTs as far as the parser is concerned. Checked as bare
   identifiers, not just function calls: `sqlite_master` takes no parentheses.
4. **Enforce a row limit inside the database** by wrapping the query, so a
   `SELECT *` over 41M rows is never materialised into memory.

Together these make the SQL box a read-only window onto the taxi dataset and
nothing else: no writes, no filesystem, no server internals, no unbounded
scans. That is the whole contract, and it holds whether the SQL came from the
model or from a person typing into the editor.
"""

import re

import duckdb

# Functions that reach outside the loaded dataset. All are callable from
# inside a plain SELECT, so the statement-type check above does not cover them.
_BLOCKED_FUNCTIONS = frozenset(
    {
        # Filesystem access, reachable from inside an ordinary SELECT.
        "csv_scan",
        "sniff_csv",
        "glob",
        "install",
        "load",
        "shell",
        # Server introspection: version and configuration disclosure.
        "version",
        "current_setting",
        "getenv",
        # Executes a SQL string, which would sidestep every check above it.
        "query",
        "query_table",
        # Data generators. Nothing to practise on the taxi dataset with, and
        # `SELECT COUNT(*) FROM range(1e10)` is free CPU burn on a public demo.
        "range",
        "generate_series",
    }
)

# Whole families of introspection and remote-access functions, blocked by
# prefix so a DuckDB upgrade that adds `duckdb_something_new()` is covered
# without anyone remembering to update a list.
#
# `duckdb_secrets()` is the one that matters most: it returns nothing today,
# but the moment credentials are configured for remote storage it would hand
# them to anyone with the SQL box open.
_BLOCKED_PREFIXES = (
    "duckdb_",
    "pragma_",
    "sqlite_",
    "read_",
    "parquet_",
    "postgres_",
    "mysql_",
    "iceberg_",
    "delta_",
)

# DuckDB's parser reports `PRAGMA ...` as StatementType.SELECT, so the type
# check below cannot see it. Anything that must not start a query gets caught
# here instead. (CALL/SET/EXPORT already get distinct statement types; they
# are listed for defence in depth, not because the type check misses them.)
_FORBIDDEN_LEADING = frozenset({"PRAGMA", "CALL", "SET", "RESET", "EXPORT", "IMPORT"})

_FENCE_RE = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.IGNORECASE)
_LEADING_WORD_RE = re.compile(r"^\s*(?:/\*.*?\*/\s*|--[^\n]*\n\s*)*([a-zA-Z_]+)", re.DOTALL)
_IDENT_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

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


def _blocked_identifiers_in(sql: str) -> set[str]:
    """Find disallowed names, whether called as functions or read as tables.

    Every identifier is checked, not just the ones followed by "(", because
    some of these are tables rather than functions — `sqlite_master` needs no
    parentheses and exposes the full schema.
    """
    found: set[str] = set()
    for match in _IDENT_RE.finditer(sql):
        name = match.group(1).lower()
        if name in _BLOCKED_FUNCTIONS or name.startswith(_BLOCKED_PREFIXES):
            found.add(name)
    return found


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

    blocked = _blocked_identifiers_in(statement)
    if blocked:
        raise SQLGuardError(
            f"Query references disallowed name(s): {', '.join(sorted(blocked))}. "
            "Only the pre-loaded 'taxi' and 'zones' tables may be read."
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
