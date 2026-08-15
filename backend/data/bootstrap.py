"""Make sure some data exists before the API starts.

Free-tier hosts give you an ephemeral disk, so the container has to be able to
produce its own dataset on a cold boot. Three sources, in order of preference:

1. Data is already on disk (local development, or a mounted volume) — do nothing.
2. ``SAMPLE_DATA_URL`` is set — download that single Parquet file. This is the
   deployment path: publish `taxi_sample.parquet` as a GitHub Release asset and
   point the host at it. One HTTP fetch, no processing.
3. Neither — download one month from the NYC TLC and sample it down. Slower,
   but it means `docker run` works with nothing pre-arranged.

Run as ``python -m data.bootstrap`` before uvicorn.
"""

import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SAMPLE_FILENAME  # noqa: E402  — single source of truth for the filename

DATA_DIR = Path(__file__).parent
TLC_BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data"
FALLBACK_MONTH = "2024-01"


def _existing_data(pattern: str) -> list[Path]:
    parent = Path(pattern).parent
    name = Path(pattern).name
    if not parent.exists():
        return []
    return sorted(parent.glob(name))


def _download(url: str, dest: Path) -> None:
    print(f"downloading {url} -> {dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)  # atomic: a half-written file is never mistaken for data
    print(f"  saved {dest.name} ({dest.stat().st_size / (1024 * 1024):.1f} MB)")


def ensure_data() -> Path:
    pattern = os.getenv("TAXI_DATA_PATH", str(DATA_DIR / "yellow_tripdata_2024-*.parquet"))

    found = _existing_data(pattern)
    if found:
        print(f"data ready: {len(found)} file(s) matching {Path(pattern).name}")
        return Path(pattern)

    sample_url = os.getenv("SAMPLE_DATA_URL")
    target = Path(pattern)
    if "*" in target.name:
        # The configured path is a glob, so it cannot name a download target.
        # Fall back to the shared sample filename — config._resolve_data_path
        # looks for exactly this when its own pattern matches nothing, which
        # is what keeps the two processes pointing at the same file.
        target = DATA_DIR / SAMPLE_FILENAME

    # The glob above cannot match the sample filename, so a previously
    # downloaded sample has to be checked for separately. Without this, every
    # restart re-downloads a file that is already sitting on disk.
    if target.exists():
        print(f"data ready: {target.name} ({target.stat().st_size / (1024 * 1024):.1f} MB)")
        return target

    if sample_url:
        _download(sample_url, target)
        return target

    print("no data and no SAMPLE_DATA_URL - falling back to one month from the TLC")
    raw = DATA_DIR / f"yellow_tripdata_{FALLBACK_MONTH}.parquet"
    if not raw.exists():
        _download(f"{TLC_BASE}/yellow_tripdata_{FALLBACK_MONTH}.parquet", raw)

    rows = int(os.getenv("SAMPLE_ROWS", "1000000"))
    from data.make_sample import build_sample  # imported late: only this path needs duckdb

    build_sample(rows, raw.as_posix(), target)
    raw.unlink(missing_ok=True)  # free the disk the raw month was using
    return target


if __name__ == "__main__":
    try:
        ensure_data()
    except Exception as exc:
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
