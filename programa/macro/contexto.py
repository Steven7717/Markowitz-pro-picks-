# macro/contexto.py
"""El contexto de EE. UU.: curva, regla de Sahm e inflación. No entra en la fase.

Son tres lecturas que la pantalla enseña al lado de la fase, solo para EE. UU.
Las otras regiones no tienen las mismas series, y meterlas en la regla haría
que «expansión» significara cosas distintas según la región (ver el spec).

El hueco de la fuente se respeta (FRED no publicó oct 2025): nunca se salta un
mes, y la inflación dice con `mes_inflacion` qué mes ha usado.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from macro.mensual import mensual

UMBRAL_SAHM = 0.5
# Un hueco en la fuente anula tres medias de 3 meses (oct 2025 → oct, nov, dic):
# con 9 de las 12 previas basta para el mínimo.
MIN_MESES_SAHM = 9
MESES_ATRAS_INFLACION = 3
SERIES = {"curva": "T10Y3M", "desempleo": "UNRATE", "ipc": "CPIAUCSL"}


@dataclass(frozen=True)
class ContextoUSA:
    curva: "float | None"
    curva_invertida: "bool | None"
    sahm: "float | None"
    sahm_activada: "bool | None"
    inflacion: "float | None"
    mes_inflacion: "date | None" = None


def _sahm(desempleo: "pd.Series | None") -> "float | None":
    """Media de 3 meses menos el mínimo de esa media en los 12 meses anteriores.

    En meses de calendario: una media con un hueco es NaN, no se salta.
    """
    if desempleo is None:
        return None
    media = mensual(desempleo).rolling(3).mean()
    if len(media) < 13 or np.isnan(media.iloc[-1]):
        return None
    previos = media.iloc[-13:-1].dropna()
    if len(previos) < MIN_MESES_SAHM:
        return None
    return float(media.iloc[-1] - previos.min())


def _inflacion(ipc: "pd.Series | None") -> "tuple[float | None, date | None]":
    """Último mes (de los 4 últimos) con dato en t y en t-12, por fecha."""
    if ipc is None:
        return None, None
    m = mensual(ipc)
    for k in range(1, MESES_ATRAS_INFLACION + 2):
        if len(m) < k + 12:
            break
        if not (np.isnan(m.iloc[-k]) or np.isnan(m.iloc[-k - 12])):
            return float(m.iloc[-k] / m.iloc[-k - 12] - 1), m.index[-k].date()
    return None, None


def calcular(curva, desempleo, ipc) -> ContextoUSA:
    ultima = None if curva is None or curva.dropna().empty else float(curva.dropna().iloc[-1])
    sahm = _sahm(desempleo)
    inflacion, mes_inflacion = _inflacion(ipc)
    return ContextoUSA(
        curva=ultima,
        curva_invertida=None if ultima is None else ultima < 0,
        sahm=sahm,
        sahm_activada=None if sahm is None else sahm >= UMBRAL_SAHM,
        inflacion=inflacion,
        mes_inflacion=mes_inflacion,
    )
