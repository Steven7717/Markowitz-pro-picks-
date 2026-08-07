import re
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

HORIZON_CONFIG: dict[str, dict] = {
    "1 Semana": {"period": "1y",  "interval": "1d",  "periods_per_year": 252},
    "1 Mes":    {"period": "2y",  "interval": "1d",  "periods_per_year": 252},
    "3 Meses":  {"period": "3y",  "interval": "1wk", "periods_per_year": 52},
    "6 Meses":  {"period": "5y",  "interval": "1wk", "periods_per_year": 52},
    "1 Año":    {"period": "10y", "interval": "1mo", "periods_per_year": 12},
    "3 Años":   {"period": "15y", "interval": "1mo", "periods_per_year": 12},
}

DEFAULT_HORIZON = "1 Mes"
RF_FALLBACK = 0.05


def parse_tickers(raw: str) -> list[str]:
    tokens = re.split(r"[,\s]+", raw.strip())
    return [t.upper() for t in tokens if t]


def compute_rf_rate(irx_prices: pd.Series, periods_per_year: int) -> tuple[float, bool]:
    """Convert the ^IRX yield series into a per-period risk-free rate.

    Uses the average yield over the sample rather than the latest quote. The
    excess returns being measured span the whole estimation window, so pairing
    them with today's spot yield mismatches the two by up to ~1.3pp on the
    longest horizons.

    Returns:
        (rate_per_period, whether ^IRX data was actually available)
    """
    clean = irx_prices.dropna() if irx_prices is not None else pd.Series(dtype=float)
    if clean.empty:
        return RF_FALLBACK / periods_per_year, False
    # ^IRX is quoted in percentage points (5.25 means 5.25% annualised).
    rf_annual = float(clean.mean()) / 100.0
    return rf_annual / periods_per_year, True


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns, without forward-filling missing prices.

    pandas pads gaps by default, which manufactures fake zero-return periods and
    then reports the accumulated move across the gap as a single period. Dropping
    the affected spans keeps every remaining observation a genuine one-period return.
    """
    returns = prices.pct_change(fill_method=None)
    return returns.dropna(how="any")


@st.cache_data(ttl=3600)
def fetch_market_data(tickers: tuple[str, ...], horizon: str) -> dict:
    cfg = HORIZON_CONFIG[horizon]
    period = cfg["period"]
    interval = cfg["interval"]
    periods_per_year = cfg["periods_per_year"]

    all_tickers = list(tickers) + ["^IRX", "^GSPC"]
    raw = yf.download(
        all_tickers,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    # More than one symbol is always requested (^IRX and ^GSPC are appended), so
    # yfinance always returns a MultiIndex here.
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    prices = prices.dropna(how="all")

    invalid = [t for t in tickers if t not in prices.columns or prices[t].isna().all()]
    valid_tickers = [t for t in tickers if t not in invalid]

    irx = prices["^IRX"] if "^IRX" in prices.columns else None
    rf_rate, rf_available = compute_rf_rate(irx, periods_per_year)

    if not valid_tickers:
        return {
            "returns": pd.DataFrame(),
            "rf_rate": rf_rate,
            "rf_available": rf_available,
            "benchmark_returns": pd.Series(dtype=float),
            "invalid_tickers": list(invalid),
            "periods_per_year": periods_per_year,
            "valid_tickers": [],
            "n_obs": 0,
        }

    asset_prices = prices[valid_tickers].dropna(how="all")
    returns = compute_returns(asset_prices)

    benchmark_returns = pd.Series(dtype=float)
    if "^GSPC" in prices.columns and not prices["^GSPC"].isna().all():
        bm = compute_returns(prices[["^GSPC"]])["^GSPC"]
        # Compare like with like: the benchmark must cover the same dates.
        benchmark_returns = bm.reindex(returns.index).dropna()

    return {
        "returns": returns,
        "rf_rate": rf_rate,
        "rf_available": rf_available,
        "benchmark_returns": benchmark_returns,
        "invalid_tickers": list(invalid),
        "periods_per_year": periods_per_year,
        "valid_tickers": valid_tickers,
        "n_obs": len(returns),
    }
