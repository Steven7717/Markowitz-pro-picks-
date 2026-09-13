"""Cuánta historia comparten los activos de una cartera, y qué cuesta cada uno.

Los retornos se calculan sobre las fechas en las que **todos** los activos
cotizaron: si a uno le falta el precio de un día, ese día no da un retorno
comparable para nadie. Es lo correcto, y también significa que el activo más
joven de la lista decide el historial de todos los demás.

Medido sobre los candidatos del ranking, 15 años de datos mensuales:

    Top 5 del ranking      72 de 180 fechas (40%)  — lo corta PLTR, desde 2020-10
    Top 8 del ranking      56 de 180 fechas (31%)  — lo corta CEG,  desde 2022-02
    Uno por sector (11)    56 de 180 fechas -> 5 observaciones por activo

Con cinco observaciones por activo la covarianza es ruido, y ninguna
optimización puede ganarle a repartir por igual por mérito propio. Pero **el
dato anterior a la salida a bolsa de PLTR no existe**: no hay nada que reparar,
sólo un compromiso que decidir entre llevar ese activo o tener historial. Este
módulo pone ese compromiso por escrito para que lo decida quien tiene la
cartera, en vez de que lo decida en silencio el `dropna`.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Por debajo de esta cobertura entre su primera y su última cotización, una
# serie está agujereada; un festivo local suelto no cuenta.
_COBERTURA_INTERNA = 0.95

# Cuántas fechas del final puede perderse una serie antes de considerarla
# interrumpida. Se cuenta en períodos, no en días, para que valga igual con
# datos diarios que mensuales: dos es el margen de un puente o de una barra que
# todavía no ha cerrado, y a la tercera la fuente está fallando.
_COLA_TOLERADA = 2


def motivo_de(serie: pd.Series, ultima_fecha) -> str:
    """Por qué esta serie recorta la muestra común, si es que la recorta.

    Cuatro respuestas y no una, porque piden cosas distintas del usuario:

    - ``completa``: no recorta nada.
    - ``arranque``: cotiza desde hace poco. El dato no existe; hay que elegir
      entre el activo y el historial.
    - ``interrumpida``: la fuente dejó de dar precios. Es la firma de un fallo
      de datos, no de la empresa — a AVB le devolvía 27 precios de 251, todos
      entre el 17 de julio y el 24 de agosto de 2026, y nada después.
    - ``huecos``: le faltan fechas dentro de su propio historial.
    """
    vivos = serie.dropna()
    if vivos.empty:
        return "sin datos"

    primera, ultima = vivos.index[0], vivos.index[-1]
    tramo = serie.loc[primera:ultima]
    if len(vivos) / len(tramo) < _COBERTURA_INTERNA:
        return "huecos"

    # El orden importa: una serie puede empezar tarde Y cortarse, y entonces lo
    # que hay que decir es que la fuente falla, no que la empresa sea joven.
    if ultima < ultima_fecha:
        posteriores = serie.loc[serie.index > ultima]
        if len(posteriores) > _COLA_TOLERADA:
            return "interrumpida"

    return "arranque" if primera > serie.index[0] else "completa"


@dataclass(frozen=True)
class Escalon:
    """Un peldaño del compromiso: con estos activos fuera, esta historia queda."""

    fuera: tuple[str, ...]
    activos: int
    observaciones: int
    # Quién manda en este peldaño, o None si ya nadie recorta nada.
    corta: str | None
    motivo: str | None
    desde: str | None


def _comunes(prices: pd.DataFrame, columnas: list[str]) -> int:
    if not columnas:
        return 0
    return int(prices[columnas].notna().all(axis=1).sum())


def _peldano(prices: pd.DataFrame, dentro: list[str], fuera: tuple[str, ...]) -> Escalon:
    """El peldaño que describe esta selección, con quién la está cortando."""
    comunes = _comunes(prices, dentro)
    culpable, ganancia = None, 0
    for t in dentro:
        if len(dentro) - 1 < 2:
            break
        sin_el = _comunes(prices, [c for c in dentro if c != t])
        if sin_el - comunes > ganancia:
            culpable, ganancia = t, sin_el - comunes

    if culpable is None:
        return Escalon(fuera, len(dentro), comunes, None, None, None)

    serie = prices[culpable]
    primera = serie.first_valid_index()
    return Escalon(
        fuera=fuera,
        activos=len(dentro),
        observaciones=comunes,
        corta=culpable,
        motivo=motivo_de(serie, prices.index[-1]),
        desde=str(primera.date()) if hasattr(primera, "date") else str(primera),
    )


def escalera(prices: pd.DataFrame, minimo_activos: int = 2) -> list[Escalon]:
    """El compromiso entre cuántos activos llevas y cuántas fechas comparten.

    Cada peldaño quita al activo que más historia está costando **en ese
    momento**, que no siempre es el más joven: una fuente interrumpida cuesta
    más que una empresa nueva. Se para cuando quitar a alguien ya no da ni una
    fecha más, o cuando quedarían menos de `minimo_activos`.

    Returns:
        Los peldaños de mayor a menor número de activos. El primero es la
        cartera entera. Lista vacía si no hay nada que decidir.
    """
    if prices.empty or len(prices.columns) < 2:
        return []

    dentro = [str(c) for c in prices.columns]
    fuera: tuple[str, ...] = ()
    escalones = [_peldano(prices, dentro, fuera)]

    while len(dentro) > max(2, minimo_activos):
        actual = escalones[-1]
        if actual.corta is None:
            break
        dentro = [c for c in dentro if c != actual.corta]
        fuera = fuera + (actual.corta,)
        escalones.append(_peldano(prices, dentro, fuera))

    return escalones
