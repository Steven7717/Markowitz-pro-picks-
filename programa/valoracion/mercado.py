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
    tipo: "str | None"
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


def _hora(momento: object) -> "str | None":
    """La hora de la cotización en ISO y UTC. La hora es lo único prescindible
    del perfil: si Yahoo cambiase de unidad (milisegundos), `fromtimestamp`
    lanza, y por una marca de tiempo no se tira toda la valoración."""
    segundos = _opcional(momento)
    if segundos is None:
        return None
    try:
        return datetime.fromtimestamp(segundos, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def perfil_desde_info(ticker: str, info: dict) -> "Perfil | None":
    """El perfil desde `yf.Ticker(t).info`, o `None` si falta precio, capitalización o moneda."""
    # `_num` antes que `or`: un NaN es verdadero en Python, y `nan or 50.0` se
    # queda con el NaN en lugar de caer al precio de mercado.
    precio = _num(info.get("currentPrice"))
    if not precio > 0:
        precio = _num(info.get("regularMarketPrice"))
    capitalizacion = _num(info.get("marketCap"))
    moneda = _texto(info.get("currency"))
    if not (precio > 0 and capitalizacion > 0) or moneda is None:
        return None
    return Perfil(
        ticker=ticker,
        precio=precio,
        capitalizacion=capitalizacion,
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        payout=_opcional(info.get("payoutRatio")),
        # Sin tipo no se inventa uno: quien lo necesite decidirá qué hacer con
        # un `None`, y un "EQUITY" falso no se distinguiría de uno verdadero.
        tipo=_texto(info.get("quoteType")),
        hora=_hora(info.get("regularMarketTime")),
    )


def _semanal(cierres: pd.Series) -> pd.Series:
    """Sin zona horaria y al día: Yahoo fecha las velas del activo y del índice
    en zonas que no siempre coinciden, y sin esto el cruce sale vacío."""
    serie = pd.to_numeric(cierres, errors="coerce").dropna()
    indice = pd.DatetimeIndex(serie.index)
    if indice.tz is not None:
        indice = indice.tz_localize(None)
    serie.index = indice.normalize()
    # Ordenada antes de quitar repetidos y de todo lo posicional que viene
    # después (`pct_change`, `tail`); estable para que "la última" de una fecha
    # repetida sea la que llegó última.
    serie = serie.sort_index(kind="stable")
    return serie[~serie.index.duplicated(keep="last")]


def regresion_beta(
    activo: pd.Series, indice: pd.Series, nombre_indice: str
) -> "Beta | None":
    """La pendiente de los rendimientos semanales del activo contra los del índice.

    Las últimas `BETA_SEMANAS`; con menos de `BETA_SEMANAS_MIN`, `None`: un año
    de datos semanales ya da una beta ruidosa, y menos no da ninguna.
    """
    juntos = pd.concat([_semanal(activo), _semanal(indice)], axis=1, join="inner").dropna()
    precios = juntos.tail(BETA_SEMANAS + 1)
    # Un cierre a cero es un dato corrupto: da un -100 % seguido de un
    # rendimiento infinito. Quitar sólo el infinito dejaría el -100 %: una beta
    # finita, plausible y falsa. Con un cero en la ventana no hay beta.
    if (precios <= 0).any().any():
        return None
    rendimientos = precios.pct_change(fill_method=None).dropna()
    if len(rendimientos) < BETA_SEMANAS_MIN:
        return None
    y, x = rendimientos.iloc[:, 0], rendimientos.iloc[:, 1]
    if not (x.var() > 0 and y.var() > 0):
        return None
    bruta = float(y.cov(x) / x.var())
    r2 = float(y.corr(x) ** 2)
    # Última guarda: un NaN aquí envenenaría el coste del capital y la caché.
    if not (math.isfinite(bruta) and math.isfinite(r2)):
        return None
    return Beta(
        bruta=bruta,
        r2=r2,
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
