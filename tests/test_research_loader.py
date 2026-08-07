from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from research.loader import CoverageReport, load_ohlcv

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def _panel(tickers: list[str], n_rows: int, start: str = "2020-01-01") -> pd.DataFrame:
    """A well-formed OHLCV panel shaped exactly as yfinance returns it."""
    dates = pd.bdate_range(start, periods=n_rows)
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    rng = np.random.default_rng(3)
    values = rng.uniform(10.0, 100.0, size=(n_rows, len(columns)))
    return pd.DataFrame(values, index=dates, columns=columns)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_returns_a_panel_and_a_coverage_report(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA", "BBB"], 400)):
        panel, coverage = load_ohlcv(["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert isinstance(panel, pd.DataFrame)
    assert isinstance(coverage, CoverageReport)


def test_panel_carries_every_ohlcv_field(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        panel, _ = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert sorted(panel.columns.get_level_values(0).unique()) == sorted(FIELDS)


def test_tickers_with_too_little_history_are_excluded(cache_dir):
    short = _panel(["AAA", "BBB"], 400)
    short[("Close", "BBB")] = np.nan
    short.iloc[-50:, short.columns.get_loc(("Close", "BBB"))] = 42.0
    with patch("research.loader._download", return_value=short):
        panel, coverage = load_ohlcv(
            ["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, min_obs=252
        )
    assert "BBB" not in panel.columns.get_level_values(1)
    assert "BBB" in coverage.excluded_short_history


def test_excluded_tickers_are_counted_not_silently_dropped(cache_dir):
    short = _panel(["AAA", "BBB"], 400)
    short[("Close", "BBB")] = np.nan
    with patch("research.loader._download", return_value=short):
        _, coverage = load_ohlcv(
            ["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, min_obs=252
        )
    assert coverage.requested == ["AAA", "BBB"]
    assert coverage.included == ["AAA"]
    assert coverage.excluded_short_history["BBB"] == 0


def test_a_ticker_absent_from_a_successful_batch_is_reported_as_short_history(cache_dir):
    """yfinance can silently omit an invalid or delisted symbol from an otherwise-successful batch."""
    only_aaa = _panel(["AAA"], 400)
    with patch("research.loader._download", return_value=only_aaa):
        _, coverage = load_ohlcv(["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert coverage.excluded_short_history["BBB"] == 0
    assert coverage.failed_download == []


def test_a_permanent_download_failure_is_reported_separately_from_short_history(cache_dir):
    """A network failure and a young company are different problems; conflating them hides outages."""
    with patch("research.loader._download", side_effect=RuntimeError("boom")):
        panel, coverage = load_ohlcv(
            ["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, max_retries=1
        )
    assert coverage.failed_download == ["AAA"]
    assert coverage.excluded_short_history == {}
    assert panel.empty


def test_a_transient_failure_is_retried(cache_dir):
    attempts = {"n": 0}

    def flaky(tickers, start, end):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return _panel(tickers, 400)

    with patch("research.loader._download", side_effect=flaky), patch("research.loader.time.sleep"):
        panel, coverage = load_ohlcv(
            ["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, max_retries=3
        )
    assert attempts["n"] == 2
    assert coverage.included == ["AAA"]


def test_the_second_call_reads_from_cache_without_downloading(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)) as first:
        load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert first.call_count == 1

    with patch("research.loader._download") as second:
        panel, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert second.call_count == 0
    assert coverage.included == ["AAA"]
    assert not panel.empty


def test_a_corrupted_cache_file_is_recovered_by_re_downloading(cache_dir):
    """A run killed mid-write leaves a truncated parquet file on disk.

    The whole point of the cache is that the second run works; a corrupt file
    must be treated as a miss and re-downloaded, not raise on every future run.
    """
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)

    cache_file = next(cache_dir.glob("*.parquet"))
    cache_file.write_bytes(b"not a valid parquet file")

    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        panel, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert coverage.included == ["AAA"]
    assert not panel.empty


def test_downloads_are_split_into_batches(cache_dir):
    tickers = [f"T{i:03d}" for i in range(120)]

    def by_batch(batch, start, end):
        return _panel(list(batch), 400)

    with patch("research.loader._download", side_effect=by_batch) as download:
        load_ohlcv(tickers, "2020-01-01", "2021-12-31", cache_dir=cache_dir, batch_size=50)
    assert download.call_count == 3


def test_the_cache_key_does_not_depend_on_process_local_hashing(cache_dir):
    """Python randomises builtin string hashing per run; a cache keyed on it never hits."""
    import hashlib

    from research.loader import _cache_path

    key = "AAA-BBB_2020-01-01_2021-12-31"
    expected = hashlib.md5(key.encode()).hexdigest()[:12]
    path = _cache_path(cache_dir, ["BBB", "AAA"], "2020-01-01", "2021-12-31")
    assert path.name == f"batch_{expected}.parquet"


def test_coverage_summary_names_every_category(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        _, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    summary = coverage.summary()
    assert "solicitados" in summary
    assert "incluidos" in summary
