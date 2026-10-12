"""Lo único de `valoracion/` que toca la red, y lo que interpreta lo que trae.

Las funciones `*_desde_*` son puras: reciben lo que yfinance devolvió y deciden
qué significa. Las de red (más abajo) sólo descargan, guardan en caché y llaman
a las puras. Así los tests de lo que importa no necesitan red, y los `red`
comprueban que la fuente sigue teniendo la forma que las puras esperan.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from valoracion.criterio import BETA_SEMANAS, BETA_SEMANAS_MIN


@dataclass(frozen=True)
class Perfil:
    """Lo que se sabe de un ticker hoy. **No lleva beta, a propósito.**

    La beta de Yahoo no se lee: para WALMEX.MX dio 0,016, porque Yahoo la mide
    contra el S&P 500 con el precio en pesos. Para una empresa de EE. UU. sería
    razonable, pero dos caminos para el mismo dato se separan, y el que se queda
    atrás no da error: da un número plausible. Sin campo, no hay camino.
    """

    ticker: str
    precio: float
    capitalizacion: float
    moneda: str
    moneda_estados: str
    industria: "str | None"
    pais: "str | None"
    payout: "float | None"
    tipo: str
    hora: "str | None"


@dataclass(frozen=True)
class Beta:
    bruta: float
    r2: float
    semanas: int
    indice: str


def _num(valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return math.nan
    return numero if math.isfinite(numero) else math.nan


def _opcional(valor: object) -> "float | None":
    numero = _num(valor)
    return None if math.isnan(numero) else numero


def _texto(valor: object) -> "str | None":
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def perfil_desde_info(ticker: str, info: dict) -> "Perfil | None":
    """El perfil desde `yf.Ticker(t).info`, o `None` si falta precio, capitalización o moneda."""
    precio = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    capitalizacion = _num(info.get("marketCap"))
    moneda = _texto(info.get("currency"))
    if not (precio > 0 and capitalizacion > 0) or moneda is None:
        return None
    momento = _opcional(info.get("regularMarketTime"))
    return Perfil(
        ticker=ticker,
        precio=precio,
        capitalizacion=capitalizacion,
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        payout=_opcional(info.get("payoutRatio")),
        tipo=_texto(info.get("quoteType")) or "EQUITY",
        hora=(
            None
            if momento is None
            else datetime.fromtimestamp(momento, tz=timezone.utc).isoformat()
        ),
    )


def _semanal(cierres: pd.Series) -> pd.Series:
    """Sin zona horaria y al día: Yahoo fecha las velas del activo y del índice
    en zonas que no siempre coinciden, y sin esto el cruce sale vacío."""
    serie = pd.to_numeric(cierres, errors="coerce").dropna()
    indice = pd.DatetimeIndex(serie.index)
    if indice.tz is not None:
        indice = indice.tz_localize(None)
    serie.index = indice.normalize()
    return serie[~serie.index.duplicated(keep="last")]


def regresion_beta(
    activo: pd.Series, indice: pd.Series, nombre_indice: str
) -> "Beta | None":
    """La pendiente de los rendimientos semanales del activo contra los del índice.

    Las últimas `BETA_SEMANAS`; con menos de `BETA_SEMANAS_MIN`, `None`: un año
    de datos semanales ya da una beta ruidosa, y menos no da ninguna.
    """
    juntos = pd.concat([_semanal(activo), _semanal(indice)], axis=1, join="inner").dropna()
    rendimientos = juntos.pct_change(fill_method=None).dropna().tail(BETA_SEMANAS)
    if len(rendimientos) < BETA_SEMANAS_MIN:
        return None
    y, x = rendimientos.iloc[:, 0], rendimientos.iloc[:, 1]
    varianza = x.var()
    if not varianza > 0:
        return None
    return Beta(
        bruta=float(y.cov(x) / varianza),
        r2=float(y.corr(x) ** 2),
        semanas=int(len(rendimientos)),
        indice=nombre_indice,
    )


def tasa_libre_desde_cierres(cierres: pd.Series) -> "float | None":
    """`^TNX` cotiza el rendimiento en puntos: 5,24 es un 5,24 %."""
    validos = pd.to_numeric(cierres, errors="coerce").dropna()
    if validos.empty:
        return None
    return float(validos.iloc[-1]) / 100


def tasa_efectiva_desde_estado(estado: "pd.DataFrame | None") -> "float | None":
    """La tasa efectiva más reciente con dato. yfinance ordena las columnas de
    la más reciente a la más antigua."""
    if estado is None or estado.empty or "Tax Rate For Calcs" not in estado.index:
        return None
    for valor in estado.loc["Tax Rate For Calcs"]:
        numero = _opcional(valor)
        if numero is not None:
            return numero
    return None


def consenso_desde_estimacion(
    estimacion: "pd.DataFrame | None", moneda_estados: str
) -> "float | None":
    """El crecimiento de ingresos que el consenso espera el próximo ejercicio.

    `+1y` y no `0y`, que suele estar ya medio publicado. Y sólo si viene en la
    moneda de los estados: en TSM, `revenue_estimate` viene en TWD y
    `earnings_estimate` en USD **en la misma consulta**, así que la moneda se
    comprueba fila a fila y no se supone.
    """
    if estimacion is None or estimacion.empty or "+1y" not in estimacion.index:
        return None
    fila = estimacion.loc["+1y"]
    if str(fila.get("currency", "")) != moneda_estados:
        return None
    return _opcional(fila.get("growth"))
