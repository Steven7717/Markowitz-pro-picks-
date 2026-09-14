"""Precios tal como se cotizaron, no como se leen hoy.

`data.py` descarga con `auto_adjust=True` y hace bien: el optimizador sólo usa
retornos, y el ajuste es consistente dentro de una descarga. Pero un precio
ajustado **cambia hacia atrás** cada vez que la empresa reparte un dividendo o
parte la acción, así que el precio al que se compró en enero no es el mismo
número dentro de tres meses. En un libro de posiciones eso produce un coste de
adquisición que se mueve solo, y nadie lo ve, porque el número resultante sigue
siendo plausible.

Módulo aparte y no un interruptor en `data.py`: un interruptor arriesga lo
contrario —que el optimizador reciba algún día precios sin ajustar sin que nadie
lo note— y ese fallo es igual de invisible.
"""

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

CAMPOS = ("Close", "Dividends", "Stock Splits")


@dataclass(frozen=True)
class Historia:
    """Cierres sin ajustar, dividendos por acción y splits, más lo que faltó."""

    cierres: pd.DataFrame
    dividendos: pd.DataFrame
    splits: pd.DataFrame
    sin_datos: list[str]


def descargar(tickers: list[str], desde: str, hasta: str | None = None) -> Historia:
    """Download unadjusted closes plus the corporate actions that move them.

    `auto_adjust=False` es el punto entero de este módulo. `actions=True` trae
    dividendos y splits en la misma petición, que es lo que evita una segunda
    ronda por ticker contra el mismo servidor.
    """
    crudo = yf.download(
        list(tickers),
        start=desde,
        end=hasta,
        auto_adjust=False,
        actions=True,
        progress=False,
    )
    return desde_panel(crudo, list(tickers))


def desde_panel(crudo: pd.DataFrame, tickers: list[str]) -> Historia:
    """Split yfinance's MultiIndex frame into the three tables we need.

    Vive separado de `descargar` para que todo lo de abajo se pueda probar sin
    tocar la red: los tests construyen el panel a mano.
    """
    tablas = {}
    for campo in CAMPOS:
        if campo in crudo.columns.get_level_values(0):
            tabla = crudo[campo]
        else:
            tabla = pd.DataFrame(index=crudo.index, columns=tickers, dtype=float)
        tablas[campo] = tabla.reindex(columns=tickers)

    cierres = tablas["Close"]
    # Un ticker que vuelve entero en blanco no es un ticker con precio cero: es
    # uno que no se descargo. Se aparta y se nombra, porque valorarlo a cero
    # dejaria la cartera mas pobre sin decir por que.
    sin_datos = [t for t in tickers if cierres[t].isna().all()]
    vivos = [t for t in tickers if t not in sin_datos]

    return Historia(
        cierres=cierres[vivos],
        dividendos=tablas["Dividends"][vivos].fillna(0.0),
        splits=tablas["Stock Splits"][vivos].fillna(0.0),
        sin_datos=sin_datos,
    )


def celda(marco: pd.DataFrame, dia, ticker: str) -> float:
    """Un valor de una de estas tablas, con el hueco leído como cero.

    `float(x or 0.0)` no vale, y es el error que hay que no cometer: **NaN es
    truthy**, así que un hueco atraviesa el `or` y sale NaN. Donde eso se
    compara con cero no hace daño —`nan > 0` es `False`— pero donde se
    multiplica por la tenencia envenena el efectivo con un NaN que después borra
    el activo entero de la tabla de posiciones, por el filtro de polvo de
    `seguimiento.posiciones`. El usuario no ve un error: ve una posición que
    desapareció.

    `desde_panel` ya rellena `dividendos` y `splits` con ceros, así que esto es
    sobre todo el cinturón para las `Historia` construidas a mano y para los
    cierres, que sí conservan sus huecos a propósito.
    """
    if ticker not in marco.columns or dia not in marco.index:
        return 0.0
    valor = marco.at[dia, ticker]
    return 0.0 if pd.isna(valor) else float(valor)


def factor_split(
    historia: Historia, ticker: str, desde: str, hasta: str
) -> float:
    """How many shares one share bought on `desde` has become by `hasta`.

    El rango excluye `desde` e incluye `hasta`: una acción comprada **el mismo
    día** del split ya se compró partida, así que aplicarle el factor la
    contaría dos veces.
    """
    if ticker not in historia.splits.columns:
        return 1.0
    tramo = historia.splits[ticker]
    tramo = tramo[(tramo.index > pd.Timestamp(desde)) & (tramo.index <= pd.Timestamp(hasta))]
    factor = 1.0
    for valor in tramo:
        if valor and valor > 0:
            factor *= float(valor)
    return factor


def ultimo(historia: Historia, ticker: str) -> tuple[float | None, str | None]:
    """The most recent close and the day it is from, or (None, None).

    La fecha vuelve siempre con el precio, y no como un extra opcional, porque
    es lo único que separa "vale esto hoy" de "vale esto según un cierre de hace
    un mes que nadie ha vuelto a mirar".
    """
    if ticker not in historia.cierres.columns:
        return (None, None)
    serie = historia.cierres[ticker].dropna()
    if serie.empty:
        return (None, None)
    return (float(serie.iloc[-1]), serie.index[-1].strftime("%Y-%m-%d"))


def cierre_en(historia: Historia, ticker: str, fecha: str) -> float | None:
    """That day's close, or None if the market was shut or the ticker unknown.

    **Nunca el cierre más cercano.** Si el día pedido no cotizó —festivo, fin de
    semana, o una fecha anterior a la salida a bolsa— la respuesta es `None`, y
    quien llama rechaza el asiento. Rellenar con el cierre de otro día dejaría
    registrada una compra a un precio que no existió esa fecha, y el número
    resultante sería perfectamente plausible.
    """
    if ticker not in historia.cierres.columns:
        return None
    try:
        valor = historia.cierres.at[pd.Timestamp(fecha), ticker]
    except KeyError:
        return None
    return None if pd.isna(valor) else float(valor)
