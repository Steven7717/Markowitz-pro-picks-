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
