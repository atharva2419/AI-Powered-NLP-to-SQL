import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Must be set before query_engine / history are imported — they read these at module level
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

_tmp = tempfile.mkdtemp()
_test_parquet = Path(_tmp) / "taxi.parquet"

pd.DataFrame({
    "VendorID":               [1,    2,    1,    2,    1   ],
    "tpep_pickup_datetime":   pd.to_datetime(["2024-01-01 08:00", "2024-01-01 09:00",
                                              "2024-01-01 10:00", "2024-01-01 11:00",
                                              "2024-01-01 12:00"]),
    "tpep_dropoff_datetime":  pd.to_datetime(["2024-01-01 08:30", "2024-01-01 09:20",
                                              "2024-01-01 10:45", "2024-01-01 11:15",
                                              "2024-01-01 12:50"]),
    "passenger_count":        [2,    1,    3,    1,    2   ],
    "trip_distance":          [5.0,  3.0,  8.0,  2.0,  6.0 ],
    "RatecodeID":             [1,    1,    1,    1,    1   ],
    "store_and_fwd_flag":     ["N",  "N",  "N",  "N",  "N" ],
    "PULocationID":           [1,    3,    5,    7,    9   ],
    "DOLocationID":           [2,    4,    6,    8,    10  ],
    "payment_type":           [1,    2,    1,    2,    1   ],
    "fare_amount":            [15.0, 10.0, 20.0, 8.0,  18.0],
    "extra":                  [0.5,  0.0,  0.5,  0.0,  0.5 ],
    "mta_tax":                [0.5,  0.5,  0.5,  0.5,  0.5 ],
    "tip_amount":             [3.0,  0.0,  4.0,  0.0,  3.5 ],
    "tolls_amount":           [0.0,  0.0,  0.0,  0.0,  0.0 ],
    "improvement_surcharge":  [0.3,  0.3,  0.3,  0.3,  0.3 ],
    "total_amount":           [19.3, 10.8, 25.3, 8.8,  22.8],
    "congestion_surcharge":   [2.5,  0.0,  2.5,  0.0,  2.5 ],
    "Airport_fee":            [0.0,  0.0,  0.0,  0.0,  0.0 ],
}).to_parquet(_test_parquet)

os.environ["TAXI_DATA_PATH"] = str(_test_parquet)
os.environ["HISTORY_DB_PATH"] = str(Path(_tmp) / "history.db")

# Make backend importable without installing it as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

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
