import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make backend importable without installing it as a package. This has to come
# before the data.fixture import below.
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.fixture import build_fixture  # noqa: E402

# Must be set before query_engine / history are imported — they read these at
# module level, and query_engine binds the taxi view at import time.
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

_tmp = tempfile.mkdtemp()
_test_parquet = build_fixture(Path(_tmp) / "taxi.parquet")

os.environ["TAXI_DATA_PATH"] = str(_test_parquet)
os.environ["HISTORY_DB_PATH"] = str(Path(_tmp) / "history.db")

import cache  # noqa: E402
import metrics  # noqa: E402
import ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def clean_process_state():
    """Reset all cross-request state so tests cannot leak into each other.

    The cache in particular would otherwise make a second identical question
    return a stale answer from a previous test.
    """
    cache.init_db()
    cache.clear()
    metrics.reset()
    ratelimit.reset()
    yield
    cache.clear()
    metrics.reset()
    ratelimit.reset()
