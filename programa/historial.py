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
    # Entre qué fechas cotizó quien corta. `hasta` existe porque «la fuente deja
    # de dar precios suyos» sólo se puede decir con el día en que dejó de
    # darlos, y la pantalla venía pintando ahí `desde` —el día en que la serie
    # empezó—: con AVB anunciaba el 17 de julio cuando el último precio era del
    # 24 de agosto, y mandaba a comprobarlo al mes equivocado.
    desde: str | None
    hasta: str | None


def _fecha(marca) -> str | None:
    """La fecha como la lee un humano, venga como venga del índice."""
    if marca is None:
        return None
    return str(marca.date()) if hasattr(marca, "date") else str(marca)


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
        return Escalon(fuera, len(dentro), comunes, None, None, None, None)

    serie = prices[culpable]
    return Escalon(
        fuera=fuera,
        activos=len(dentro),
        observaciones=comunes,
        corta=culpable,
        motivo=motivo_de(serie, prices.index[-1]),
        desde=_fecha(serie.first_valid_index()),
        hasta=_fecha(serie.last_valid_index()),
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


@dataclass(frozen=True)
class Cobertura:
    """Un activo cuya serie está tan incompleta que hay que nombrarlo."""

    ticker: str
    # Fracción de las fechas del horizonte con precio, tal como la midió
    # `data.tickers_con_huecos`. No se recalcula aquí a propósito: un solo sitio
    # decide qué cuenta como poca cobertura, y es el que tiene el umbral.
    cobertura: float
    motivo: str
    desde: str | None
    hasta: str | None


def avisos_de_cobertura(
    prices: pd.DataFrame,
    coberturas: dict[str, float],
) -> list[Cobertura]:
    """Las series rotas que hay que nombrar una a una, sin contar a las jóvenes.

    La escalera ya nombra a quien más historia cuesta, y en el caso corriente
    con eso basta. Pero **se calla en dos sitios**, los dos alcanzables:

    - Con dos activos no culpa a nadie, porque `_peldano` se para en seco cuando
      quitar a alguien dejaría menos de dos. Dos activos es el mínimo que el
      optimizador acepta, o sea el caso más corriente que existe.
    - Con dos series rotas en las mismas fechas, quitar a cualquiera de ellas no
      gana ni una fecha, así que tampoco hay culpable y el aviso entero
      desaparece — con las dos series igual de rotas.

    En los dos casos el usuario sólo llega a leer «datos insuficientes», que es
    el síntoma, sin saber cuál de sus activos lo provoca.

    El filtro por `motivo_de` no es un detalle de presentación: una cobertura
    baja **no** es una avería cuando la empresa no cotizaba. PLTR cubre el 40%
    de un horizonte de quince años y su serie está entera; llamarla «incompleta»
    manda a buscar un fallo donde no lo hay, y es exactamente el aviso que se
    retiró de esta pantalla. De ese caso ya habla la escalera como lo que es
    —un compromiso entre llevar el activo y tener historial—, y aquí sólo se
    nombra lo que de verdad está roto.

    Args:
        prices: precios de los activos válidos, con las fechas por índice.
        coberturas: `{ticker: cobertura}` de los que bajan del mínimo, tal cual
            sale de `data.tickers_con_huecos`.

    Returns:
        Un aviso por activo roto, del que menos cubre al que más.
    """
    if prices.empty:
        return []

    ultima_fecha = prices.index[-1]
    avisos = []
    for ticker, cobertura in coberturas.items():
        # Los que no traen ni una fila ya los aparta `invalid_tickers`, que se
        # dice por separado y antes que esto.
        if ticker not in prices.columns:
            continue
        serie = prices[ticker]
        motivo = motivo_de(serie, ultima_fecha)
        if motivo in ("arranque", "completa"):
            continue
        avisos.append(Cobertura(
            ticker=str(ticker),
            cobertura=float(cobertura),
            motivo=motivo,
            desde=_fecha(serie.first_valid_index()),
            hasta=_fecha(serie.last_valid_index()),
        ))

    # El peor primero: si el usuario sólo lee una línea, que sea la que más duele.
    return sorted(avisos, key=lambda c: (c.cobertura, c.ticker))
