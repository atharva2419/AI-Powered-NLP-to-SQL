"""Build a small, representative sample of the full-year dataset.

The full dataset is ~700 MB across 12 Parquet files — fine on a laptop,
impossible on a free-tier host with 512 MB of RAM and an ephemeral disk. This
produces a single file that is small enough to ship inside a container image
while still answering every question in the demo sensibly.

The sample is **stratified by month**: an equal share is drawn from each of
the 12 files, so "which month had the most trips?" still has a shape to find,
and hour-of-day and payment-mix distributions stay close to the real ones.
A naive head(N) would return January only and make half the demo questions
meaningless.

    python data/make_sample.py --rows 2000000
"""

import argparse
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).parent
DEFAULT_ROWS = 2_000_000


def build_sample(rows: int, source_glob: str, out_path: Path) -> None:
    con = duckdb.connect()
    months = con.execute(
        f"SELECT COUNT(DISTINCT MONTH(tpep_pickup_datetime)) "
        f"FROM read_parquet('{source_glob}') "
        "WHERE tpep_pickup_datetime >= '2024-01-01' AND tpep_pickup_datetime < '2025-01-01'"
    ).fetchone()[0]
    if not months:
        raise SystemExit(f"No 2024 data found at {source_glob}. Run download_data.py first.")

    per_month = rows // months
    print(f"sampling {per_month:,} rows from each of {months} month(s) -> {rows:,} total")

    # ROW_NUMBER over a per-month partition gives an even draw across months.
    #
    # The ORDER BY inside the window is random() and not tpep_pickup_datetime:
    # ordering by time takes the *earliest* rows of each month, which produced
    # a sample covering 12 days and a single hour of the day. Every
    # time-of-day question would then have been answered from a sample that
    # contained no time-of-day variation at all.
    con.execute(
        f"""
        COPY (
            SELECT * EXCLUDE (_rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY MONTH(tpep_pickup_datetime) ORDER BY random()
                ) AS _rn
                FROM read_parquet('{source_glob}')
                WHERE tpep_pickup_datetime >= '2024-01-01'
                  AND tpep_pickup_datetime <  '2025-01-01'
            ) WHERE _rn <= {per_month}
        ) TO '{out_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    size_mb = out_path.stat().st_size / (1024 * 1024)
    actual = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{out_path.as_posix()}')"
    ).fetchone()[0]
    print(f"wrote {out_path.name}: {actual:,} rows, {size_mb:.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help=f"approximate total rows (default {DEFAULT_ROWS:,})")
    parser.add_argument("--source", default=str(DATA_DIR / "yellow_tripdata_2024-*.parquet"),
                        help="glob of source Parquet files")
    parser.add_argument("--out", type=Path, default=DATA_DIR / "taxi_sample.parquet")
    args = parser.parse_args()

    build_sample(args.rows, Path(args.source).as_posix(), args.out)


if __name__ == "__main__":
    main()
