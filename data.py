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
