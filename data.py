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

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

    prices = prices.dropna(how="all")

    invalid = [t for t in tickers if t not in prices.columns or prices[t].isna().all()]
    valid_tickers = [t for t in tickers if t not in invalid]

    if not valid_tickers:
        return {
            "returns": pd.DataFrame(),
            "rf_rate": RF_FALLBACK / periods_per_year,
            "rf_available": False,
            "benchmark_returns": pd.Series(dtype=float),
            "invalid_tickers": list(invalid),
            "periods_per_year": periods_per_year,
            "valid_tickers": [],
        }

    rf_annual = RF_FALLBACK
    rf_available = True
    if "^IRX" in prices.columns and not prices["^IRX"].isna().all():
        rf_annual = prices["^IRX"].dropna().iloc[-1] / 100.0
    else:
        rf_available = False

    rf_rate = rf_annual / periods_per_year

    benchmark_returns = pd.Series(dtype=float)
    if "^GSPC" in prices.columns and not prices["^GSPC"].isna().all():
        benchmark_returns = prices["^GSPC"].pct_change().dropna()

    asset_prices = prices[valid_tickers].dropna(how="all")
    returns = asset_prices.pct_change().dropna()

    return {
        "returns": returns,
        "rf_rate": rf_rate,
        "rf_available": rf_available,
        "benchmark_returns": benchmark_returns,
        "invalid_tickers": list(invalid),
        "periods_per_year": periods_per_year,
        "valid_tickers": valid_tickers,
    }
