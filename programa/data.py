import re
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

# La clave de cada horizonte y la configuración de descarga que le toca.
#
# **Clave y no etiqueta**, por lo mismo que `optimizer.STRATEGY_LABELS`: estas
# cadenas se escriben en `portafolios/*.json`, en `libros/*.json` y en el fichero
# de preferencias, y lo que va a disco no puede ser una decisión de redacción.
#
# Aquí el defecto era peor que en la estrategia, y por eso se arregló después.
# Allí había dos formas —clave y etiqueta— y el fichero guardaba la equivocada;
# aquí **no había clave ninguna**: la etiqueta ERA la identidad. Reescribir «1
# Año» no habría estropeado una exportación, habría estropeado **la recarga** de
# todo portafolio guardado con él, que es de lo que vive esta aplicación.
HORIZON_CONFIG: dict[str, dict] = {
    "1_semana": {"period": "1y",  "interval": "1d",  "periods_per_year": 252},
    "1_mes":    {"period": "2y",  "interval": "1d",  "periods_per_year": 252},
    "3_meses":  {"period": "3y",  "interval": "1wk", "periods_per_year": 52},
    "6_meses":  {"period": "5y",  "interval": "1wk", "periods_per_year": 52},
    "1_ano":    {"period": "10y", "interval": "1mo", "periods_per_year": 12},
    "3_anos":   {"period": "15y", "interval": "1mo", "periods_per_year": 12},
}

# Cómo se escribe cada uno en pantalla. Se puede reescribir cuando se quiera,
# que es justamente lo que antes no se podía.
HORIZON_LABELS: dict[str, str] = {
    "1_semana": "1 Semana",
    "1_mes": "1 Mes",
    "3_meses": "3 Meses",
    "6_meses": "6 Meses",
    "1_ano": "1 Año",
    "3_anos": "3 Años",
}

# Cómo se llamaban antes de tener clave, para poder leer lo que ya está escrito.
#
# **A mano y congelada, no derivada de `HORIZON_LABELS`.** Derivarla la dejaría
# inservible justo el día que sirve: al reescribir una etiqueta, los ficheros que
# llevan la vieja dentro dejarían de reconocerse, que es el defecto entero otra
# vez y por la puerta de atrás. Esto es historia —la redacción vigente hasta el
# 2026-09-20— y la historia no cambia cuando alguien mejora una frase.
_HEREDADOS: dict[str, str] = {
    "1 Semana": "1_semana",
    "1 Mes": "1_mes",
    "3 Meses": "3_meses",
    "6 Meses": "6_meses",
    "1 Año": "1_ano",
    "3 Años": "3_anos",
}

DEFAULT_HORIZON = "1_mes"
RF_FALLBACK = 0.05


def clave_de_horizonte(valor) -> str | None:
    """La clave del horizonte que `valor` nombra, o None si no se reconoce.

    Acepta la clave y también la etiqueta con la que se guardó antes de que los
    horizontes tuvieran clave, que es lo que permite abrir un portafolio de
    entonces sin migrarlo. `None` significa lo mismo en los dos sitios que
    preguntan —las preferencias y el portafolio que se carga—: esto no se puede
    mostrar, hay que caer al repuesto y decirlo.
    """
    if not isinstance(valor, str):
        return None
    if valor in HORIZON_CONFIG:
        return valor
    return _HEREDADOS.get(valor)


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


# Por debajo de esta cobertura una serie deja de ser "una serie con huecos" y
# pasa a ser "una serie que no está": con `dropna(how="any")` detrás, se lleva
# por delante el historial de todos los demás activos de la cartera.
COBERTURA_MINIMA = 0.80


def tickers_con_huecos(
    prices: pd.DataFrame,
    minimo: float = COBERTURA_MINIMA,
) -> dict[str, float]:
    """Los tickers cuya serie está tan incompleta que recorta la muestra de todos.

    `compute_returns` descarta las fechas donde falte algún precio, y eso es lo
    correcto con un hueco suelto: rellenarlo fabricaría un retorno de cero que
    nadie tuvo. Pero un ticker al 10% de cobertura se lleva por delante el 90%
    del historial de los demás **sin decirlo**, y el único aviso que había —
    `invalid_tickers`— sólo mira los que vienen enteros vacíos.

    Medido con AVB en septiembre de 2026: 27 precios de 252, y una cartera de
    cinco valores se quedaba en 26 observaciones, sin validación posible y sin
    que nada en pantalla dijera cuál de los cinco lo causaba.

    Returns:
        {ticker: cobertura} sólo de los que bajan del mínimo, con la cobertura
        como fracción de las fechas disponibles.
    """
    if prices.empty:
        return {}
    total = len(prices)
    coberturas = prices.notna().sum() / total
    return {
        str(ticker): float(cobertura)
        for ticker, cobertura in coberturas.items()
        if cobertura < minimo
    }


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns, without forward-filling missing prices.

    pandas pads gaps by default, which manufactures fake zero-return periods and
    then reports the accumulated move across the gap as a single period. Dropping
    the affected spans keeps every remaining observation a genuine one-period return.
    """
    returns = prices.pct_change(fill_method=None)
    return returns.dropna(how="any")


def compute_returns_amplios(prices: pd.DataFrame) -> pd.DataFrame:
    """Retornos sin exigir que todos los activos coticen el mismo día.

    Es lo que consume la covarianza por pares: donde `compute_returns` tira la
    fecha entera si a alguien le falta el precio, aquí se conserva y el hueco
    queda como NaN sólo en la columna que lo tiene.

    Lo que sí se descarta, uno a uno, es **el retorno que cruza un hueco**: si a
    un activo le faltan tres días, el movimiento del cuarto es el de cuatro días
    con etiqueta de uno, y metido en una varianza la infla. Se quita ese dato y
    no la fecha, que es de los demás.
    """
    retornos = prices.pct_change(fill_method=None)
    for col in prices.columns:
        posiciones = np.flatnonzero(prices[col].notna().values)
        if posiciones.size < 2:
            continue
        cruzan = posiciones[1:][np.diff(posiciones) > 1]
        if cruzan.size:
            retornos.iloc[cruzan, retornos.columns.get_loc(col)] = np.nan
    return retornos.dropna(how="all")


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
            "returns_amplios": pd.DataFrame(),
            "precios": pd.DataFrame(),
            "rf_rate": rf_rate,
            "rf_available": rf_available,
            "benchmark_returns": pd.Series(dtype=float),
            "invalid_tickers": list(invalid),
            "tickers_con_huecos": {},
            "periods_per_year": periods_per_year,
            "valid_tickers": [],
            "n_obs": 0,
        }

    asset_prices = prices[valid_tickers].dropna(how="all")
    huecos = tickers_con_huecos(asset_prices)
    returns = compute_returns(asset_prices)
    returns_amplios = compute_returns_amplios(asset_prices)

    benchmark_returns = pd.Series(dtype=float)
    if "^GSPC" in prices.columns and not prices["^GSPC"].isna().all():
        bm = compute_returns(prices[["^GSPC"]])["^GSPC"]
        # Compare like with like: the benchmark must cover the same dates.
        benchmark_returns = bm.reindex(returns.index).dropna()

    return {
        "returns": returns,
        # Para la covarianza por pares y para la escalera de historial, que
        # necesitan ver las fechas que `returns` ya ha tirado.
        "returns_amplios": returns_amplios,
        "precios": asset_prices,
        "rf_rate": rf_rate,
        "rf_available": rf_available,
        "benchmark_returns": benchmark_returns,
        "invalid_tickers": list(invalid),
        "tickers_con_huecos": huecos,
        "periods_per_year": periods_per_year,
        "valid_tickers": valid_tickers,
        "n_obs": len(returns),
    }
