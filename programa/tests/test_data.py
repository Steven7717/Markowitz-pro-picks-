from data import parse_tickers, HORIZON_CONFIG, DEFAULT_HORIZON


def test_parse_tickers_comma_separated():
    assert parse_tickers("AAPL, MSFT, GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_space_separated():
    assert parse_tickers("AAPL MSFT GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_mixed_delimiters():
    assert parse_tickers("AAPL, MSFT GOOGL,AMZN") == ["AAPL", "MSFT", "GOOGL", "AMZN"]


def test_parse_tickers_converts_to_uppercase():
    assert parse_tickers("aapl msft") == ["AAPL", "MSFT"]


def test_parse_tickers_empty_string():
    assert parse_tickers("") == []


def test_parse_tickers_only_whitespace():
    assert parse_tickers("   ") == []


def test_horizon_config_has_all_six_horizons():
    expected = {"1 Semana", "1 Mes", "3 Meses", "6 Meses", "1 Año", "3 Años"}
    assert set(HORIZON_CONFIG.keys()) == expected


def test_horizon_config_entries_have_required_fields():
    for key, cfg in HORIZON_CONFIG.items():
        assert "period" in cfg, f"{key} missing 'period'"
        assert "interval" in cfg, f"{key} missing 'interval'"
        assert "periods_per_year" in cfg, f"{key} missing 'periods_per_year'"
        assert cfg["periods_per_year"] in (12, 52, 252), f"{key} has unexpected periods_per_year"


def test_default_horizon_exists_in_config():
    assert DEFAULT_HORIZON in HORIZON_CONFIG


from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from data import fetch_market_data, RF_FALLBACK


def _make_mock_download(tickers: list[str], n_rows: int = 100) -> pd.DataFrame:
    """Build a fake yfinance MultiIndex DataFrame."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=n_rows)
    all_tickers = tickers + ["^IRX", "^GSPC"]
    arrays = [["Close"] * len(all_tickers), all_tickers]
    cols = pd.MultiIndex.from_arrays(arrays, names=["Price", "Ticker"])
    data = rng.uniform(100, 200, size=(n_rows, len(all_tickers)))
    # Make ^IRX look like a realistic annualized rate (e.g. 5.25)
    irx_idx = all_tickers.index("^IRX")
    data[:, irx_idx] = 5.25
    return pd.DataFrame(data, index=dates, columns=cols)


@patch("data.yf.download")
def test_fetch_market_data_returns_expected_keys(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"])
    result = fetch_market_data(("AAPL", "MSFT"), "1 Mes")
    assert "returns" in result
    assert "rf_rate" in result
    assert "benchmark_returns" in result
    assert "invalid_tickers" in result
    assert "periods_per_year" in result
    assert "valid_tickers" in result


@patch("data.yf.download")
def test_fetch_market_data_rf_rate_converted_to_period(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"])
    result = fetch_market_data(("AAPL", "MSFT"), "1 Mes")
    # ^IRX = 5.25% annual → per-day ≈ 5.25/100/252
    expected_rf = 5.25 / 100 / 252
    assert abs(result["rf_rate"] - expected_rf) < 1e-6


@patch("data.yf.download")
def test_fetch_market_data_uses_fallback_when_irx_missing(mock_dl):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=100)
    cols = pd.MultiIndex.from_arrays(
        [["Close", "Close", "Close"], ["AAPL", "^IRX", "^GSPC"]],
        names=["Price", "Ticker"],
    )
    data = rng.uniform(100, 200, size=(100, 3))
    data[:, 1] = np.nan  # ^IRX all NaN
    df = pd.DataFrame(data, index=dates, columns=cols)
    mock_dl.return_value = df
    result = fetch_market_data(("AAPL",), "1 Mes")
    assert result["rf_rate"] == RF_FALLBACK / 252
    assert result.get("rf_available") is False


# ── Risk-free rate: audit finding D ───────────────────────────────────────────

import warnings

from data import compute_returns, compute_rf_rate


def test_risk_free_rate_averages_over_the_whole_sample_period():
    """A single spot yield does not describe the decade the returns came from."""
    irx = pd.Series([1.0, 3.0, 5.0])  # percent quotes averaging 3%
    rf, available = compute_rf_rate(irx, periods_per_year=12)
    assert available
    assert np.isclose(rf, 0.03 / 12)


def test_risk_free_rate_ignores_the_last_observation_alone():
    irx = pd.Series([1.0, 1.0, 9.0])
    rf, _ = compute_rf_rate(irx, periods_per_year=1)
    assert not np.isclose(rf, 0.09)


def test_risk_free_rate_falls_back_when_the_series_is_empty():
    rf, available = compute_rf_rate(pd.Series(dtype=float), periods_per_year=12)
    assert available is False
    assert np.isclose(rf, RF_FALLBACK / 12)


def test_risk_free_rate_falls_back_when_every_value_is_missing():
    rf, available = compute_rf_rate(pd.Series([np.nan, np.nan]), periods_per_year=12)
    assert available is False


# ── Return construction: gap handling ─────────────────────────────────────────

def test_returns_do_not_invent_flat_periods_across_price_gaps():
    """Forward-filling missing prices manufactures fake zero-return days."""
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, np.nan, 106.0, 107.0]})
    r = compute_returns(prices)
    assert not (r["A"] == 0.0).any()


def test_returns_drop_the_span_covering_a_gap_instead_of_mislabelling_it():
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, np.nan, 106.0, 107.0]})
    r = compute_returns(prices)
    assert len(r) == 2
    assert np.isclose(r["A"].iloc[0], 0.01)
    assert np.isclose(r["A"].iloc[1], 107.0 / 106.0 - 1.0)


def test_returns_keep_only_dates_where_every_asset_traded():
    prices = pd.DataFrame({
        "A": [100.0, 101.0, 102.0, 103.0],
        "B": [50.0, np.nan, 52.0, 53.0],
    })
    r = compute_returns(prices)
    assert not r.isna().any().any()


def test_return_construction_raises_no_pandas_deprecation_warning():
    """pandas 3.0 removes the implicit pad; this must not rely on it."""
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, 106.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        compute_returns(prices)


@patch("data.yf.download")
def test_fetch_market_data_reports_the_observation_count(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"], n_rows=100)
    result = fetch_market_data(("AAPL", "MSFT"), "1 Mes")
    assert result["n_obs"] == len(result["returns"])
