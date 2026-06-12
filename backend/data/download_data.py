import urllib.request
from pathlib import Path

BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]


def download():
    for month in MONTHS:
        out = Path(__file__).parent / f"yellow_tripdata_{month}.parquet"
        if out.exists():
            print(f"{out.name} already present, skipping")
            continue
        print(f"Downloading {month} ...")
        urllib.request.urlretrieve(f"{BASE_URL}/yellow_tripdata_{month}.parquet", out)
        size_mb = out.stat().st_size / (1024 * 1024)
        print(f"  saved {out.name}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    download()
