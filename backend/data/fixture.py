"""A tiny dataset with the real TLC schema, built without any real data.

Used in two places:

* the pytest suite, as the dataset every test runs against;
* CI, which has no Parquet files at all (they are 700 MB and gitignored) but
  still needs *something* queryable to validate the evaluation set against.

Written with DuckDB rather than pandas.to_parquet: pandas needs pyarrow to
write Parquet, pyarrow links against NumPy's C ABI, and that dragged a NumPy
1.x/2.x incompatibility into a project whose request path uses neither. DuckDB
is already a hard dependency and writes Parquet natively.

Five rows, chosen so assertions are easy to read: fares average exactly 14.2,
and payment_type 1 (credit card) appears three times out of five.
"""

import argparse
from pathlib import Path

import duckdb

_ROWS = """
    (1, TIMESTAMP '2024-01-01 08:00', TIMESTAMP '2024-01-01 08:30',
     2, 5.0, 1, 'N', 1,  2,  1, 15.0, 0.5, 0.5, 3.0, 0.0, 0.3, 19.3, 2.5, 0.0),
    (2, TIMESTAMP '2024-01-01 09:00', TIMESTAMP '2024-01-01 09:20',
     1, 3.0, 1, 'N', 3,  4,  2, 10.0, 0.0, 0.5, 0.0, 0.0, 0.3, 10.8, 0.0, 0.0),
    (1, TIMESTAMP '2024-01-01 10:00', TIMESTAMP '2024-01-01 10:45',
     3, 8.0, 1, 'N', 5,  6,  1, 20.0, 0.5, 0.5, 4.0, 0.0, 0.3, 25.3, 2.5, 0.0),
    (2, TIMESTAMP '2024-01-01 11:00', TIMESTAMP '2024-01-01 11:15',
     1, 2.0, 1, 'N', 7,  8,  2,  8.0, 0.0, 0.5, 0.0, 0.0, 0.3,  8.8, 0.0, 0.0),
    (1, TIMESTAMP '2024-01-01 12:00', TIMESTAMP '2024-01-01 12:50',
     2, 6.0, 1, 'N', 9, 10,  1, 18.0, 0.5, 0.5, 3.5, 0.0, 0.3, 22.8, 2.5, 0.0)
"""

# Quoted so DuckDB preserves the mixed case the real TLC files use — the
# /api/schema endpoint and the generated SQL both depend on `VendorID` not
# arriving as `vendorid`.
_COLUMNS = """
    "VendorID", "tpep_pickup_datetime", "tpep_dropoff_datetime",
    "passenger_count", "trip_distance", "RatecodeID", "store_and_fwd_flag",
    "PULocationID", "DOLocationID", "payment_type", "fare_amount",
    "extra", "mta_tax", "tip_amount", "tolls_amount",
    "improvement_surcharge", "total_amount", "congestion_surcharge",
    "Airport_fee"
"""


def build_fixture(out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(
        f"COPY (SELECT * FROM (VALUES {_ROWS}) AS t({_COLUMNS})) "
        f"TO '{out_path.as_posix()}' (FORMAT PARQUET)"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    path = build_fixture(args.out)
    print(f"wrote fixture: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
