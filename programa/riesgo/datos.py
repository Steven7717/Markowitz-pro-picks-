# programa/riesgo/datos.py
"""Retornos diarios para el VaR, aparte de los del horizonte elegido.

El semáforo de Basilea está definido a un día; con el horizonte de un año el
optimizador trabaja con meses, y de ahí no sale un VaR diario.
"""

import pandas as pd
import streamlit as st
import yfinance as yf

from data import compute_returns

# 5 años ≈ 1.255 sesiones: 500 para estimar y ≈ 750 de backtest.
PERIODO_DIARIO = "5y"


@st.cache_data(ttl=3600)
def retornos_diarios(tickers: tuple[str, ...]) -> dict:
    raw = yf.download(list(tickers), period=PERIODO_DIARIO, interval="1d",
                      auto_adjust=True, progress=False)
    precios = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        precios = precios.rename(columns={"Close": tickers[0]})
    precios = precios.reindex(columns=list(tickers)).dropna(how="all")
    return {
        "retornos": compute_returns(precios),
        "sesiones": {t: int(precios[t].notna().sum()) for t in tickers},
    }
