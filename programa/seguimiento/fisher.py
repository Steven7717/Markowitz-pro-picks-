"""Del rendimiento en dolares al rendimiento real en pesos.

Tres pasos, en este orden y no en otro: convertir a pesos con el FIX de cada
fecha, medir con las mismas funciones de `rendimiento`, y descontar la
inflacion con Fisher. Descontar el INPC de un rendimiento en dolares mezcla dos
monedas y da un numero plausible que no mide nada.

Aqui no hay red: las series llegan ya descargadas de `seguimiento/banxico.py`.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from seguimiento import rendimiento


def real(nominal: "float | None", inflacion_anual: "float | None") -> "float | None":
    """Ecuacion de Fisher exacta: `(1 + nominal) / (1 + π) − 1`.

    No `nominal − π`. Con la inflacion mexicana la aproximacion se equivoca en
    decimas, y en pantalla esa diferencia no se veria. Un `None` en cualquiera
    de las dos entradas es «no se puede medir», y lo sigue siendo a la salida.
    """
    if nominal is None or inflacion_anual is None or inflacion_anual <= -1.0:
        return None
    return (1.0 + nominal) / (1.0 + inflacion_anual) - 1.0


def en_pesos(
    valor: pd.Series, flujos: pd.Series, fix: "pd.Series | None"
) -> "tuple[pd.Series, pd.Series] | None":
    """El valor diario y los flujos, en pesos, con el FIX de cada fecha.

    Flujo a flujo y no con el atajo `(1 + r_USD)(1 + Δtc) − 1`: el atajo da la
    TWR bien, pero la TIR sale mal en cuanto hay aportaciones, porque cada una
    entro a un tipo de cambio distinto.

    Un dia sin FIX (fin de semana, o un festivo mexicano que en EE. UU. es habil)
    usa el ultimo publicado. **Hacia atras no se arrastra nada**: si la serie
    empieza antes del primer FIX disponible devuelve `None`, porque el tipo de
    cambio de ese dia no lo sabe nadie aqui.
    """
    if fix is None or fix.empty:
        return None
    fix = fix.sort_index()
    calendario = valor.index.union(flujos.index)
    alineado = fix.reindex(fix.index.union(calendario)).ffill().reindex(calendario)
    if alineado.isna().any():
        return None
    return valor * alineado.reindex(valor.index), flujos * alineado.reindex(flujos.index)
