# macro/contexto.py
"""El contexto de EE. UU.: curva, regla de Sahm e inflación. No entra en la fase.

Son tres lecturas que la pantalla enseña al lado de la fase, solo para EE. UU.
Las otras regiones no tienen las mismas series, y meterlas en la regla haría
que «expansión» significara cosas distintas según la región (ver el spec).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro.mensual import mensual

UMBRAL_SAHM = 0.5
SERIES = {"curva": "T10Y3M", "desempleo": "UNRATE", "ipc": "CPIAUCSL"}


@dataclass(frozen=True)
class ContextoUSA:
    curva: "float | None"
    curva_invertida: "bool | None"
    sahm: "float | None"
    sahm_activada: "bool | None"
    inflacion: "float | None"


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
    if len(previos) < 12:
        return None
    return float(media.iloc[-1] - previos.min())


def _inflacion(ipc: "pd.Series | None") -> "float | None":
    """t frente a t-12 por fecha; None si falta cualquiera de los dos."""
    if ipc is None:
        return None
    m = mensual(ipc)
    if len(m) < 13 or np.isnan(m.iloc[-1]) or np.isnan(m.iloc[-13]):
        return None
    return float(m.iloc[-1] / m.iloc[-13] - 1)


def calcular(curva, desempleo, ipc) -> ContextoUSA:
    ultima = None if curva is None or curva.dropna().empty else float(curva.dropna().iloc[-1])
    sahm = _sahm(desempleo)
    return ContextoUSA(
        curva=ultima,
        curva_invertida=None if ultima is None else ultima < 0,
        sahm=sahm,
        sahm_activada=None if sahm is None else sahm >= UMBRAL_SAHM,
        inflacion=_inflacion(ipc),
    )
