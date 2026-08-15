"""Dataset path resolution.

These cover the deployment bug where `data/bootstrap.py` downloaded the sample
to `taxi_sample.parquet` while the app went looking for the 12-month glob
`yellow_tripdata_2024-*.parquet`. Both halves were individually correct and
disagreed about where the data lived, so the container died at import with
"No files found that match the pattern".
"""

import importlib
from pathlib import Path

import pytest

import config


def _reload_config(monkeypatch, data_dir: Path, configured: str | None):
    """Re-import config with TAXI_DATA_PATH pointed somewhere specific."""
    if configured is None:
        monkeypatch.delenv("TAXI_DATA_PATH", raising=False)
        monkeypatch.setattr(config, "_DATA_DIR", data_dir)
    else:
        monkeypatch.setenv("TAXI_DATA_PATH", configured)
    return importlib.reload(config)


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


def _touch(path: Path) -> Path:
    path.write_bytes(b"")
    return path


class TestResolveDataPath:
    def test_exact_file_is_used_when_it_exists(self, monkeypatch, data_dir):
        target = _touch(data_dir / "taxi.parquet")
        cfg = _reload_config(monkeypatch, data_dir, str(target))
        assert cfg.DATA_PATH == target

    def test_glob_is_used_when_it_matches(self, monkeypatch, data_dir):
        _touch(data_dir / "yellow_tripdata_2024-01.parquet")
        pattern = str(data_dir / "yellow_tripdata_2024-*.parquet")
        cfg = _reload_config(monkeypatch, data_dir, pattern)
        assert cfg.DATA_PATH == Path(pattern)

    def test_falls_back_to_the_bootstrap_sample(self, monkeypatch, data_dir):
        """The hosted case: bootstrap downloaded one file, the glob matches none."""
        sample = _touch(data_dir / config.SAMPLE_FILENAME)
        pattern = str(data_dir / "yellow_tripdata_2024-*.parquet")
        cfg = _reload_config(monkeypatch, data_dir, pattern)
        assert cfg.DATA_PATH == sample

    def test_real_monthly_files_win_over_a_stale_sample(self, monkeypatch, data_dir):
        """A developer with both should get the full year, not the sample."""
        _touch(data_dir / config.SAMPLE_FILENAME)
        _touch(data_dir / "yellow_tripdata_2024-01.parquet")
        pattern = str(data_dir / "yellow_tripdata_2024-*.parquet")
        cfg = _reload_config(monkeypatch, data_dir, pattern)
        assert cfg.DATA_PATH == Path(pattern)

    def test_missing_everything_returns_the_configured_pattern(self, monkeypatch, data_dir):
        """So DuckDB's own error names the pattern the operator configured."""
        pattern = str(data_dir / "yellow_tripdata_2024-*.parquet")
        cfg = _reload_config(monkeypatch, data_dir, pattern)
        assert cfg.DATA_PATH == Path(pattern)

    def test_sample_filename_matches_what_bootstrap_writes(self):
        """The two processes must agree, or the container dies at import."""
        from data import bootstrap

        assert bootstrap.SAMPLE_FILENAME == config.SAMPLE_FILENAME

    def test_sample_name_does_not_collide_with_the_monthly_glob(self):
        """Otherwise a sample plus a full download double-counts January."""
        assert not Path(config.SAMPLE_FILENAME).match("yellow_tripdata_2024-*.parquet")


@pytest.fixture(autouse=True)
def _restore_config(monkeypatch):
    """Leave the module as the rest of the suite expects to find it."""
    yield
    monkeypatch.undo()
    importlib.reload(config)
