"""Environment-driven configuration.

Every tunable lives here so behaviour can be changed per-environment (local,
CI, hosted demo) without touching code. Values are read once at import time.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).parent

# Look for .env beside the backend and at the repo root, so `uvicorn main:app`
# from backend/ and `docker compose up` from the root both work.
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR.parent / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Data -------------------------------------------------------------------
_DATA_DIR = _BACKEND_DIR / "data"
# Where data/bootstrap.py deposits a downloaded or generated sample. It is
# deliberately NOT named to match the monthly glob below: a developer who runs
# the container (creating a sample) and later downloads the full year would
# otherwise end up with 13 files matching one pattern, double-counting.
SAMPLE_FILENAME = "taxi_sample.parquet"


def _resolve_data_path() -> Path:
    """Pick the dataset to query.

    The configured pattern wins whenever it matches something. When it matches
    nothing but a bootstrap sample is sitting there, use the sample — this is
    the hosted case, where bootstrap downloads one file and the default
    pattern is a 12-month glob that will never match it. Without this the two
    halves disagree about where the data lives and the app dies at import.
    """
    configured = Path(
        os.getenv("TAXI_DATA_PATH", str(_DATA_DIR / "yellow_tripdata_2024-*.parquet"))
    )
    if list(configured.parent.glob(configured.name)):
        return configured

    sample = configured.parent / SAMPLE_FILENAME
    if sample.exists():
        print(f"config: no match for {configured.name}, using {SAMPLE_FILENAME}")
        return sample

    # Neither exists. Return the configured path so DuckDB raises its own
    # error naming the pattern, which is clearer than anything invented here.
    return configured


DATA_PATH = _resolve_data_path()
HISTORY_DB_PATH = Path(
    os.getenv("HISTORY_DB_PATH", str(_BACKEND_DIR / "data" / "history.db"))
)
# The official TLC zone lookup: 265 rows mapping LocationID -> borough and
# zone name. Committed to the repo rather than downloaded — it is 12 KB and
# changes about once a decade, so a network dependency at boot buys nothing.
ZONES_PATH = Path(
    os.getenv("TAXI_ZONES_PATH", str(_BACKEND_DIR / "data" / "taxi_zone_lookup.csv"))
)

# --- LLM --------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.1-8b-instant")
# Deterministic by default: the same question should produce the same SQL,
# which makes caching meaningful and evaluation reproducible.
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
# How many times to re-prompt the model with the database's error message
# before giving up. 0 disables self-correction.
MAX_SQL_RETRIES = _int("MAX_SQL_RETRIES", 2)

# --- Query execution --------------------------------------------------------
# Rows returned to the browser. Enforced inside the database, not in pandas,
# so a `SELECT *` over 41M rows never materialises.
MAX_RESULT_ROWS = _int("MAX_RESULT_ROWS", 100)
# Wall-clock budget for a single DuckDB query; exceeded queries are interrupted.
QUERY_TIMEOUT_SECONDS = _int("QUERY_TIMEOUT_SECONDS", 30)
DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = _int("DUCKDB_THREADS", 4)

# --- Cache ------------------------------------------------------------------
CACHE_ENABLED = _bool("CACHE_ENABLED", True)
CACHE_TTL_SECONDS = _int("CACHE_TTL_SECONDS", 24 * 60 * 60)

# --- Rate limiting (protects the demo's API key from being drained) ---------
RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", False)
RATE_LIMIT_PER_HOUR = _int("RATE_LIMIT_PER_HOUR", 20)
RATE_LIMIT_GLOBAL_PER_DAY = _int("RATE_LIMIT_GLOBAL_PER_DAY", 1000)
# Re-running hand-edited SQL costs local CPU, not API credit, so the SQL
# editor gets its own much looser allowance. Someone learning SQL will run a
# dozen variations in a minute, and that should not consume the LLM budget.
EXECUTE_RATE_LIMIT_PER_HOUR = _int("EXECUTE_RATE_LIMIT_PER_HOUR", 200)

# --- HTTP -------------------------------------------------------------------
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
# Vercel gives every preview deployment its own hostname, so an exact-match
# origin list breaks any branch that is not production. A regex lets previews
# work without turning CORS off entirely.
# Example: https://.*\.vercel\.app
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX") or None
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
