import urllib.request
from pathlib import Path

URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet"
OUTPUT = Path(__file__).parent / "taxi.parquet"


def download():
    print(f"Downloading {URL} ...")
    urllib.request.urlretrieve(URL, OUTPUT)
    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Saved to {OUTPUT}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    download()
