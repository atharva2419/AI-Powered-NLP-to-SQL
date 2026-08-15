"""Boot-time dataset provisioning.

The hosted container starts with an empty disk, so `python -m data.bootstrap`
runs before uvicorn and has to leave a queryable dataset behind — at a path
`config` will then independently agree on.
"""

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from data import bootstrap


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(bootstrap, "DATA_DIR", d)
    monkeypatch.delenv("SAMPLE_DATA_URL", raising=False)
    monkeypatch.setenv("TAXI_DATA_PATH", str(d / "yellow_tripdata_2024-*.parquet"))
    return d


def _fake_download(dest_size_mb=1):
    """Stand in for the network, writing a file of roughly the right size."""
    def _download(url, dest):
        Path(dest).write_bytes(b"x" * int(dest_size_mb * 1024 * 1024))
    return _download


class TestExistingData:
    def test_monthly_files_are_left_alone(self, data_dir, monkeypatch):
        (data_dir / "yellow_tripdata_2024-01.parquet").write_bytes(b"")
        monkeypatch.setenv("SAMPLE_DATA_URL", "http://example.invalid/x.parquet")
        with patch.object(bootstrap, "_download") as dl:
            bootstrap.ensure_data()
        dl.assert_not_called()

    def test_an_existing_sample_is_not_downloaded_again(self, data_dir, monkeypatch):
        """The restart case.

        The configured glob cannot match the sample filename, so without an
        explicit check every restart re-downloads a file already on disk —
        on a host that spins down when idle, that is every cold start.
        """
        (data_dir / bootstrap.SAMPLE_FILENAME).write_bytes(b"x" * 1024)
        monkeypatch.setenv("SAMPLE_DATA_URL", "http://example.invalid/x.parquet")

        with patch.object(bootstrap, "_download") as dl:
            result = bootstrap.ensure_data()

        dl.assert_not_called()
        assert result.name == bootstrap.SAMPLE_FILENAME


class TestColdStart:
    def test_downloads_the_sample_when_the_disk_is_empty(self, data_dir, monkeypatch):
        monkeypatch.setenv("SAMPLE_DATA_URL", "http://example.invalid/x.parquet")
        with patch.object(bootstrap, "_download", side_effect=_fake_download()) as dl:
            result = bootstrap.ensure_data()

        dl.assert_called_once()
        assert result.name == bootstrap.SAMPLE_FILENAME
        assert result.exists()

    def test_downloads_to_a_path_config_will_find(self, data_dir, monkeypatch):
        """The deployment bug in one assertion.

        bootstrap wrote taxi_sample.parquet; the app looked for the 12-month
        glob; the container died at import with "No files found that match
        the pattern".
        """
        monkeypatch.setenv("SAMPLE_DATA_URL", "http://example.invalid/x.parquet")
        with patch.object(bootstrap, "_download", side_effect=_fake_download()):
            written = bootstrap.ensure_data()

        import config

        monkeypatch.setenv("TAXI_DATA_PATH", str(data_dir / "yellow_tripdata_2024-*.parquet"))
        resolved = importlib.reload(config).DATA_PATH
        importlib.reload(config)  # leave the module as the rest of the suite expects

        assert resolved == written

    def test_an_exact_configured_path_is_honoured(self, data_dir, monkeypatch):
        exact = data_dir / "custom.parquet"
        monkeypatch.setenv("TAXI_DATA_PATH", str(exact))
        monkeypatch.setenv("SAMPLE_DATA_URL", "http://example.invalid/x.parquet")

        with patch.object(bootstrap, "_download", side_effect=_fake_download()):
            result = bootstrap.ensure_data()

        assert result == exact
        assert exact.exists()


class TestFilenameContract:
    def test_sample_filename_is_shared_with_config(self):
        import config

        assert bootstrap.SAMPLE_FILENAME == config.SAMPLE_FILENAME
