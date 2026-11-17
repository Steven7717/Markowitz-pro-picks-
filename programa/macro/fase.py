# macro/fase.py
"""La fase del ciclo a partir del CLI. Puro: no sabe de dónde viene la serie.

Nivel frente a 100 y dirección a tres meses. Un giro que el último mes
desmiente no es un giro: sale `indeterminada`, y quien llama no inclina nada.
No se elige un lado por defecto, porque un lado por defecto es una fase
inventada.

La serie se lee en meses de calendario: se normaliza a una rejilla mensual
continua y un hueco no se salta (si falta t, t-1 o t-3 no hay fase).

No mira el reloj. Si el dato es demasiado viejo para mover el Top lo decide
`motivo_para_no_inclinar`, que recibe la fecha de hoy como argumento.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from macro.criterio import MAX_ANTIGUEDAD_MESES, MESES_DIRECCION, NIVEL_NEUTRO
from macro.mensual import mensual


@dataclass(frozen=True)
class Fase:
    clave: "str | None"
    motivo: "str | None"
    mes_dato: "date | None"
    nivel: "float | None"
    cambio: "float | None"
    meses_en_fase: int


def _clave(nivel: float, cambio: float, ultimo: float) -> "str | None":
    if cambio == 0 or (ultimo != 0 and (ultimo > 0) != (cambio > 0)):
        return None
    sube = cambio > 0
    if nivel >= NIVEL_NEUTRO:
        return "expansion" if sube else "desaceleracion"
    return "recuperacion" if sube else "contraccion"


def fases_por_mes(serie: pd.Series) -> pd.Series:
    """La clave de cada mes de la rejilla, o None si faltan t, t-1 o t-3 o no decide."""
    rejilla = mensual(serie)
    valores = rejilla.to_numpy()
    claves: list = []
    for i in range(len(valores)):
        if i < MESES_DIRECCION:
            claves.append(None)
            continue
        ahora, previo, hace_n = valores[i], valores[i - 1], valores[i - MESES_DIRECCION]
        if np.isnan(ahora) or np.isnan(previo) or np.isnan(hace_n):
            claves.append(None)
            continue
        claves.append(_clave(ahora, ahora - hace_n, ahora - previo))
    return pd.Series(claves, index=rejilla.index, dtype="object")


def determinar(serie: pd.Series) -> Fase:
    rejilla = mensual(serie)
    if len(rejilla) < MESES_DIRECCION + 1:
        return Fase(None, "serie_corta", None, None, None, 0)

    mes = rejilla.index[-1].date()
    nivel = float(rejilla.iloc[-1])
    previo = rejilla.iloc[-2]
    hace_n = rejilla.iloc[-1 - MESES_DIRECCION]
    if np.isnan(previo) or np.isnan(hace_n):
        return Fase(None, "serie_con_huecos", mes, nivel, None, 0)

    por_mes = fases_por_mes(rejilla)
    clave = por_mes.iloc[-1]
    cambio = float(nivel - hace_n)
    if clave is None:
        return Fase(None, "indeterminada", mes, nivel, cambio, 0)

    seguidos = 0
    for anterior in reversed(por_mes.tolist()):
        if anterior != clave:
            break
        seguidos += 1
    return Fase(clave, None, mes, nivel, cambio, seguidos)


def motivo_para_no_inclinar(fase: Fase, hoy: date) -> "str | None":
    """Por qué esta fase no puede mover el Top, o None si puede."""
    if fase.clave is None:
        return fase.motivo
    meses = (hoy.year * 12 + hoy.month) - (fase.mes_dato.year * 12 + fase.mes_dato.month)
    if meses > MAX_ANTIGUEDAD_MESES:
        return "dato_rancio"
    return None
