"""De la lista de asientos a lo que hay en cartera, día a día.

Nada de este módulo guarda estado. Cada llamada reconstruye desde los asientos,
que es lo que hace imposible que las posiciones y el libro se desincronicen: no
hay dos representaciones que puedan discrepar, hay una y una derivación.

No importa nada de `seguimiento.libro` en tiempo de ejecución a propósito.
`libro.anadir` sí necesita a este módulo —para rechazar una venta que no se
puede pagar con lo que hay— y hacerlo en los dos sentidos crearía un ciclo de
importación.
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from seguimiento.precios import Historia

if TYPE_CHECKING:  # pragma: no cover
    from seguimiento.libro import Asiento

# Por debajo de esto, una posición es polvo de redondeo de una venta total, no
# una participación. Sin el corte, vender las 40 acciones que se compraron
# puede dejar 3.55e-15 en cartera y una fila fantasma en la tabla.
_POLVO = 1e-9


@dataclass(frozen=True)
class Estado:
    """Lo que hay en cartera en un momento: acciones por ticker y efectivo."""

    acciones: dict[str, float]
    efectivo: float


def vigentes(asientos: "list[Asiento]") -> "list[Asiento]":
    """Entries still standing: drops the annulled ones and the annulments.

    Se resuelve antes de ordenar por fecha porque una anulación puede llevar
    fecha anterior al asiento que anula —se corrige un error el martes sobre
    algo fechado el lunes— y filtrar por fecha primero la dejaría fuera.
    """
    anulados = {a.anula for a in asientos if a.tipo == "anulacion" and a.anula}
    return [
        a for a in asientos if a.tipo != "anulacion" and a.id not in anulados
    ]


def ordenados(asientos: "list[Asiento]") -> "list[Asiento]":
    """By date, keeping insertion order as the tie-break.

    `sorted` es estable, así que dos asientos del mismo día conservan el orden
    en que se dieron de alta. Importa: comprar y vender el mismo día en el
    orden contrario dejaría acciones negativas a mitad del recorrido.
    """
    return sorted(asientos, key=lambda a: a.fecha)


def estado(asientos: "list[Asiento]", hasta: str | date | None = None) -> Estado:
    """Shares per ticker and cash, as of `hasta` (default: everything)."""
    limite = hasta.isoformat() if isinstance(hasta, date) else hasta

    acciones: dict[str, float] = {}
    efectivo = 0.0

    for a in ordenados(vigentes(asientos)):
        if limite is not None and a.fecha > limite:
            break
        if a.tipo == "aportacion":
            efectivo += a.importe
        elif a.tipo == "retiro":
            efectivo -= a.importe
        elif a.tipo == "dividendo":
            efectivo += a.importe
        elif a.tipo == "compra":
            efectivo -= a.importe + a.comision
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
        elif a.tipo == "venta":
            efectivo += a.importe - a.comision
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) - a.acciones

    return Estado(
        acciones={t: n for t, n in acciones.items() if abs(n) > _POLVO},
        efectivo=efectivo,
    )


def primer_descubierto(asientos: "list[Asiento]") -> str | None:
    """The first moment the book would go into the red, in words, or None.

    `estado()` responde "qué hay al final". Esta función responde "¿hubo algún
    día en que esto no cuadrara?", que es otra pregunta y la que hace falta
    antes de aceptar un asiento.

    La diferencia importa porque un asiento puede llegar **fechado en el
    pasado**, y es el caso normal: quien empieza a llevar el libro de lo que ya
    tenía comprado mete las operaciones en el orden en que las encuentra en el
    extracto, no en orden cronológico. Comprobar sólo el saldo final acepta una
    venta de julio de acciones compradas en agosto —el final cuadra— y deja la
    cartera con acciones negativas a mitad del recorrido.

    El margen de `_POLVO` en cada comparación es para que vender exactamente lo
    que se tiene siga valiendo: el número de acciones viene de dividir un
    importe entre un precio, así que arrastra error de redondeo y una igualdad
    exacta fallaría por un femtoaccion de diferencia.
    """
    acciones: dict[str, float] = {}
    efectivo = 0.0

    for a in ordenados(vigentes(asientos)):
        if a.tipo == "aportacion":
            efectivo += a.importe
        elif a.tipo == "dividendo":
            efectivo += a.importe
        elif a.tipo == "retiro":
            if a.importe > efectivo + _POLVO:
                return (
                    f"el {a.fecha} no hay efectivo suficiente: harían falta "
                    f"{a.importe:,.2f} y hay {efectivo:,.2f}"
                )
            efectivo -= a.importe
        elif a.tipo == "compra":
            coste = a.importe + a.comision
            if coste > efectivo + _POLVO:
                return (
                    f"el {a.fecha} no hay efectivo suficiente: la compra cuesta "
                    f"{coste:,.2f} y hay {efectivo:,.2f}"
                )
            efectivo -= coste
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
        elif a.tipo == "venta":
            tiene = acciones.get(a.ticker, 0.0)
            if a.acciones > tiene + _POLVO:
                return (
                    f"el {a.fecha} no tienes suficientes acciones de {a.ticker}: "
                    f"harían falta {a.acciones:g} y hay {tiene:g}"
                )
            acciones[a.ticker] = tiene - a.acciones
            efectivo += a.importe - a.comision
    return None


@dataclass(frozen=True)
class Marcha:
    """La cartera día a día: acciones, efectivo, valor y flujos externos.

    `posteriores` son los asientos fechados **después** del último cierre
    disponible, que la serie no puede reflejar porque no hay precio con el que
    valorarlos. Vuelven contados y no en silencio: la tabla por activo sí los
    incluye —sale de los asientos, no de la serie— así que sin este aviso el
    valor de cabecera y la tabla dirían cosas distintas y nada explicaría por
    qué.
    """

    acciones: pd.DataFrame
    efectivo: pd.Series
    valor: pd.Series
    flujos: pd.Series
    dividendos: pd.DataFrame
    posteriores: int = 0


def serie(asientos: "list[Asiento]", historia: Historia) -> Marcha:
    """Walk the ledger forward one trading day at a time.

    El calendario lo pone el índice de precios, no `pandas.bdate_range`: los
    días hábiles de un calendario genérico incluyen festivos de mercado, y un
    día sin cotización valorado con el cierre anterior inventa un día de
    rendimiento cero que nunca existió.

    Los dividendos calculados —acciones en cartera en la fecha ex, por el
    dividendo por acción— se aplican **salvo** que exista un asiento manual de
    `dividendo` para ese ticker y esa fecha. El manual es el neto que llegó de
    verdad; el calculado es teórico y bruto. Sumar los dos contaría el cobro dos
    veces, y el rendimiento saldría alto sin causa visible.

    **El dividendo se paga sobre la tenencia de antes de los movimientos del
    día, no de después.** Para cobrar hay que tener las acciones *antes* de la
    fecha ex: quien compra ese mismo día las compra ya sin el dividendo, y el
    cobro es del vendedor. Aplicar los asientos primero y pagar después le paga
    al comprador — medido: una compra de diez acciones el día ex cobraba 2,40
    que no le tocaban. El reverso también importa y sale gratis con la misma
    foto: quien vende en la fecha ex sí cobra, porque las tenía al cierre
    anterior.
    """
    vivos = ordenados(vigentes(asientos))
    if not vivos:
        vacio = pd.Series(dtype=float)
        return Marcha(pd.DataFrame(), vacio, vacio, vacio, pd.DataFrame())

    calendario = historia.cierres.index
    tickers = list(historia.cierres.columns)
    # Un hueco de precio en un dia que el mercado abrio es un fallo de datos,
    # no una accion que valga cero. Sin esto, `(acciones * cierres).sum()`
    # trata el NaN como cero --su comportamiento por defecto-- y el grafico
    # ensena una caida a plomo que nunca ocurrio. Arrastrar el ultimo cierre
    # conocido es lo que hace cualquier extracto de broker. Esta acotado:
    # `precios.desde_panel` ya aparta los tickers que no traen ningun dato.
    cierres = historia.cierres.ffill()

    acciones = pd.DataFrame(0.0, index=calendario, columns=tickers)
    efectivo = pd.Series(0.0, index=calendario)
    flujos = pd.Series(0.0, index=calendario)
    dividendos = pd.DataFrame(0.0, index=calendario, columns=tickers)

    # Los dividendos que el usuario apunto a mano, indexados para que el
    # calculado sepa cuando callarse.
    manuales = {
        (a.ticker, a.fecha) for a in vivos if a.tipo == "dividendo"
    }

    tenencia: dict[str, float] = {}
    caja = 0.0
    pendientes = list(vivos)

    for dia in calendario:
        clave = dia.strftime("%Y-%m-%d")

        # 1. Los splits del dia parten lo que ya se tenia.
        for ticker in tickers:
            factor = float(historia.splits.at[dia, ticker] or 0.0)
            if factor > 0 and tenencia.get(ticker):
                tenencia[ticker] *= factor

        # 2. La foto de lo que se tenia al cierre de ayer, ya partida por el
        #    split de hoy si lo hubo. Es la que decide quien cobra el dividendo,
        #    y por eso se toma ANTES de los movimientos del dia.
        tenencia_ex = dict(tenencia)

        # 3. Los asientos fechados hasta hoy que aun no se han aplicado.
        while pendientes and pendientes[0].fecha <= clave:
            a = pendientes.pop(0)
            if a.tipo == "aportacion":
                caja += a.importe
                flujos[dia] += a.importe
            elif a.tipo == "retiro":
                caja -= a.importe
                flujos[dia] -= a.importe
            elif a.tipo == "dividendo":
                caja += a.importe
                if a.ticker in dividendos.columns:
                    dividendos.at[dia, a.ticker] += a.importe
            elif a.tipo == "compra":
                caja -= a.importe + a.comision
                tenencia[a.ticker] = tenencia.get(a.ticker, 0.0) + a.acciones
            elif a.tipo == "venta":
                caja += a.importe - a.comision
                tenencia[a.ticker] = tenencia.get(a.ticker, 0.0) - a.acciones

        # 4. Los dividendos calculados, sobre la foto de la fecha ex.
        for ticker in tickers:
            por_accion = float(historia.dividendos.at[dia, ticker] or 0.0)
            if por_accion <= 0 or (ticker, clave) in manuales:
                continue
            cobro = tenencia_ex.get(ticker, 0.0) * por_accion
            if cobro:
                caja += cobro
                dividendos.at[dia, ticker] += cobro

        for ticker in tickers:
            acciones.at[dia, ticker] = tenencia.get(ticker, 0.0)
        efectivo[dia] = caja

    valor = (acciones * cierres).sum(axis=1) + efectivo
    return Marcha(
        acciones=acciones,
        efectivo=efectivo,
        valor=valor,
        flujos=flujos,
        dividendos=dividendos,
        # Lo que quedo en la cola son asientos posteriores al ultimo cierre
        # disponible. No se pierden --la tabla por activo los ve-- pero la serie
        # no puede valorarlos, y quien pinte esto tiene que poder decirlo.
        posteriores=len(pendientes),
    )
