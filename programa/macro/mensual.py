# macro/mensual.py
"""La serie mensual en calendario: la rejilla sobre la que se lee todo en `macro/`.

Comparar por posición convierte «hace tres meses» en «hace cuatro» cuando falta
un mes; por eso fase y contexto leen siempre por aquí.
"""

import numpy as np
import pandas as pd


def mensual(serie: pd.Series) -> pd.Series:
    """Rejilla mensual continua: inicio de mes, sin duplicados, sin inf, ordenada."""
    if len(serie) == 0:
        return pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    valores = pd.to_numeric(serie, errors="coerce").astype(float)
    valores = valores.where(np.isfinite(valores))
    indice = pd.DatetimeIndex(serie.index).to_period("M").to_timestamp()
    valores = pd.Series(valores.to_numpy(), index=indice)
    valores = valores[~valores.index.duplicated(keep="last")].sort_index()
    con_dato = valores.dropna()
    if con_dato.empty:
        return con_dato
    rejilla = pd.date_range(con_dato.index[0], con_dato.index[-1], freq="MS")
    return valores.reindex(rejilla)
