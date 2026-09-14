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

from seguimiento.precios import Historia, celda

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


def _corporativas(historia: "Historia | None") -> "dict[str, tuple[dict, dict]]":
    """Lo que la historia dice que pasó, por fecha: splits y dividendos.

    Se recorre por columnas y filtrando los ceros porque estas dos tablas son
    casi todo ceros: una acción reparte cuatro dividendos al año sobre
    doscientas cincuenta sesiones, y un split es un acontecimiento de la
    década. Recorrer el calendario entero día a día sería mil veces más trabajo
    para el mismo resultado.
    """
    eventos: "dict[str, tuple[dict, dict]]" = {}
    if historia is None:
        return eventos
    for marco, hueco in ((historia.splits, 0), (historia.dividendos, 1)):
        if marco is None or marco.empty:
            continue
        for ticker in marco.columns:
            columna = marco[ticker]
            for dia, valor in columna[columna > 0].items():
                clave = dia.strftime("%Y-%m-%d")
                eventos.setdefault(clave, ({}, {}))[hueco][ticker] = float(valor)
    return eventos


# Un split registrado a mano silencia el que trae la historia para ese ticker
# dentro de esta ventana de dias, no solo en la fecha exacta. El broker aplica
# el split un dia y lo notifica otro, asi que apuntarlo con un dia de desfase es
# el caso normal --y con la precedencia por fecha exacta se aplicaban LOS DOS:
# cuarenta acciones donde hay veinte, mil de plusvalia latente inventada y diez
# puntos de TWR de la nada, sin que nada lo dijera. Duplicar la posicion en
# silencio es el peor error posible de este modulo.
#
# Cinco dias cubre un puente largo y sigue siendo mucho menos que la distancia
# entre dos splits reales de la misma empresa, que se cuentan por anos.
_VENTANA_SPLIT_MANUAL = 5


def _silenciado_por_manual(ticker: str, fecha: str, manuales: dict) -> bool:
    """Si el usuario registro un split de ese ticker lo bastante cerca."""
    cercanos = manuales.get(ticker)
    if not cercanos:
        return False
    dia = date.fromisoformat(fecha)
    return any(
        abs((dia - otra).days) <= _VENTANA_SPLIT_MANUAL for otra in cercanos
    )


def cronologia(
    asientos: "list[Asiento]",
    historia: "Historia | None" = None,
    hasta: str | date | None = None,
):
    """Los asientos y las acciones corporativas, en el orden en que ocurrieron.

    Devuelve tuplas `("split", fecha, ticker, factor)`,
    `("dividendo", fecha, ticker, por_accion)` y `("asiento", fecha, asiento)`.
    Existe para que `estado()` y `rendimiento.por_activo()` cuenten los splits y
    los dividendos **exactamente igual que `serie()`**, en vez de cada uno a su
    manera: mientras cada función tuvo su propio recorrido, la misma pantalla
    enseñaba +70,00 en la cabecera y −450,00 en la tabla, del mismo activo.

    El orden dentro de un día es el de `serie()` y no es arbitrario:

    1. **El split primero**, porque parte lo que ya se tenía. Lo comprado hoy se
       compró ya partido, así que no le toca.
    2. **El dividendo después**, sobre esa misma tenencia y todavía **antes de
       los movimientos del día**. Para cobrar hay que tener las acciones antes
       de la fecha ex: quien compra ese mismo día compra ya sin el dividendo, y
       quien vende ese día sí cobra.
    3. **Y por último los asientos del día.**

    Un split o un dividendo registrados a mano mandan sobre los calculados de
    ese ticker y esa fecha, igual que en `serie()`. El manual es lo que ocurrió
    de verdad —el neto que llegó, el factor que aplicó el bróker—; el calculado
    es teórico. Sumar los dos cobraría dos veces o partiría la posición dos
    veces.
    """
    limite = hasta.isoformat() if isinstance(hasta, date) else hasta
    vivos = ordenados(vigentes(asientos))
    corporativas = _corporativas(historia)

    manual_dividendo = {(a.ticker, a.fecha) for a in vivos if a.tipo == "dividendo"}
    manual_split: "dict[str, list[date]]" = {}
    for a in vivos:
        if a.tipo == "split":
            manual_split.setdefault(a.ticker, []).append(date.fromisoformat(a.fecha))

    por_fecha: "dict[str, list[Asiento]]" = {}
    for a in vivos:
        por_fecha.setdefault(a.fecha, []).append(a)

    for fecha in sorted(set(por_fecha) | set(corporativas)):
        if limite is not None and fecha > limite:
            return
        del_dia = por_fecha.get(fecha, ())
        splits, dividendos = corporativas.get(fecha, ({}, {}))

        for a in del_dia:
            if a.tipo == "split":
                yield ("split", fecha, a.ticker, float(a.factor))
        for ticker, factor in sorted(splits.items()):
            if not _silenciado_por_manual(ticker, fecha, manual_split):
                yield ("split", fecha, ticker, factor)
        for ticker, por_accion in sorted(dividendos.items()):
            if (ticker, fecha) not in manual_dividendo:
                yield ("dividendo", fecha, ticker, por_accion)
        for a in del_dia:
            if a.tipo != "split":
                yield ("asiento", fecha, a)


def estado(
    asientos: "list[Asiento]",
    hasta: str | date | None = None,
    historia: "Historia | None" = None,
) -> Estado:
    """Shares per ticker and cash, as of `hasta` (default: everything).

    **`historia` no es un adorno: sin ella el efectivo sale corto.** Los
    dividendos automáticos —acciones en cartera en la fecha ex por el dividendo
    por acción— sólo vivían dentro de `serie()`, así que la misma pantalla
    enseñaba 320,00 arriba, que sale de la serie, y 300,00 abajo, que salía de
    aquí. Dos saldos del mismo libro, en la misma pantalla, sin nada que
    explicara la diferencia.

    Se queda opcional a propósito: **`libro.anadir` la llama sin historia**, y
    tiene que poder. Decidir si una compra cabe en el efectivo no puede depender
    de una descarga de red que falla, y sin dividendos el saldo que sale es
    menor, o sea conservador: como mucho arrastra una aportación de financiación
    que no hacía falta, y esa se ve en Movimientos. Al revés —aceptar una compra
    contando un dividendo que la red inventó— no se vería.
    """
    acciones: dict[str, float] = {}
    efectivo = 0.0

    for evento in cronologia(asientos, historia, hasta=hasta):
        if evento[0] == "split":
            _, _, ticker, factor = evento
            if acciones.get(ticker):
                acciones[ticker] *= factor
        elif evento[0] == "dividendo":
            _, _, ticker, por_accion = evento
            efectivo += acciones.get(ticker, 0.0) * por_accion
        else:
            a = evento[2]
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


def primer_descubierto(
    asientos: "list[Asiento]",
    historia: "Historia | None" = None,
) -> str | None:
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

    **`Historia` es opcional, y esa asimetría es deliberada.** Decidir si un
    asiento se puede escribir no puede depender de una descarga que falla: los
    días en que yfinance se cae serían días en que no se puede registrar una
    venta perfectamente real. Por eso sin `Historia` este recorrido es puro y
    sólo cuenta lo que el usuario registró como asiento.

    Pero cuando la pantalla **ya tiene** los precios —los acaba de descargar
    para pintarse— pasárselos es gratis, y no hacerlo costaba caro: `estado()`
    empezó a cobrar los dividendos automáticos y esta función se quedó sin
    verlos, así que la cabecera enseñaba 20,00 de efectivo mientras aquí se
    rechazaba un retiro de 20,00. Peor: `libro.anadir` financiaba la compra con
    una **aportación que el usuario nunca hizo**, y el libro es append-only, así
    que ese hecho falso se quedaba para siempre inflando el aportado neto y
    envenenando la TIR.

    La regla, entonces: con datos se cuenta lo que de verdad hay; sin datos se
    es conservador. Rechazar de más es recuperable —se registra el dividendo a
    mano y se vuelve a intentar—; aceptar de más escribe un descubierto que no
    se puede deshacer.
    """
    acciones: dict[str, float] = {}
    efectivo = 0.0

    for evento in cronologia(asientos, historia):
        if evento[0] == "split":
            # Sin esto, quien vivió un 2:1 de una compra de diez e intentaba
            # vender veinte recibía «no tienes suficientes acciones»: o mentía
            # en el número, o no podía apuntar la venta.
            _, _, ticker, factor = evento
            if acciones.get(ticker):
                acciones[ticker] *= factor
            continue
        if evento[0] == "dividendo":
            _, _, ticker, por_accion = evento
            efectivo += acciones.get(ticker, 0.0) * por_accion
            continue

        a = evento[2]
        if a.tipo == "split":
            if acciones.get(a.ticker):
                acciones[a.ticker] *= a.factor
        elif a.tipo == "aportacion":
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
    # Los dividendos llevan **una columna por cada ticker del libro**, no solo
    # por cada uno con precios. El cobro entra en caja siempre, pero hasta que
    # esto fue asi solo se anotaba aqui si el ticker tenia columna, y
    # `precios.desde_panel` aparta los que vuelven vacios de la descarga --el
    # aviso de la pantalla documenta que eso le pasa a tickers perfectamente
    # validos--. Resultado: la cabecera decia «Dividendos 0,00» y la tabla del
    # mismo libro decia 50,00. Un dividendo apuntado a mano es un hecho que el
    # usuario registro; no depende de que la descarga de precios lo acompane.
    #
    # `acciones` no lleva esas columnas a proposito: sin precio no hay nada que
    # valorar, y eso ya se cuenta aparte en `Historia.sin_datos`.
    con_dividendo = sorted(
        {a.ticker for a in vivos if a.tipo == "dividendo" and a.ticker}
        | set(tickers)
    )
    dividendos = pd.DataFrame(0.0, index=calendario, columns=con_dividendo)

    # Los dividendos que el usuario apunto a mano, indexados para que el
    # calculado sepa cuando callarse.
    manuales = {
        (a.ticker, a.fecha) for a in vivos if a.tipo == "dividendo"
    }
    splits_manuales: "dict[str, list[date]]" = {}
    for a in vivos:
        if a.tipo == "split":
            splits_manuales.setdefault(a.ticker, []).append(date.fromisoformat(a.fecha))

    tenencia: dict[str, float] = {}
    caja = 0.0
    pendientes = list(vivos)

    def _aplicar(a, dia) -> None:
        """Un asiento que no es un split, sobre la tenencia y la caja."""
        nonlocal caja
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

    for dia in calendario:
        clave = dia.strftime("%Y-%m-%d")

        # 1. Lo fechado ANTES de hoy y todavia sin aplicar, que el primer dia
        #    del calendario es todo lo anterior a el. Va delante del split de
        #    hoy y no detras: una compra de diciembre que vive un split de enero
        #    se tiene que partir, y aplicandola despues se quedaba entera.
        while pendientes and pendientes[0].fecha < clave:
            a = pendientes.pop(0)
            if a.tipo == "split":
                if tenencia.get(a.ticker):
                    tenencia[a.ticker] *= a.factor
            else:
                _aplicar(a, dia)

        # 2. Los splits de HOY que el usuario registro. Van antes que los de la
        #    historia y **en lugar de ellos** para ese ticker: sumar los dos
        #    partiria la posicion dos veces, que es el peor error posible aqui
        #    porque duplica acciones en silencio. Es la misma precedencia que ya
        #    regia para los dividendos, y por lo mismo.
        #
        #    El silencio alcanza una ventana de dias y no solo la fecha exacta
        #    --ver `_silenciado_por_manual`--, porque el broker aplica el split
        #    un dia y lo notifica otro. Esta regla y la de `cronologia` tienen
        #    que decir lo mismo: si se separan, la cabecera y la tabla vuelven a
        #    contradecirse, que es el defecto que este modulo existe para haber
        #    cerrado.
        registrados = set()
        indice = 0
        while indice < len(pendientes) and pendientes[indice].fecha == clave:
            a = pendientes[indice]
            if a.tipo == "split":
                if tenencia.get(a.ticker):
                    tenencia[a.ticker] *= a.factor
                registrados.add(a.ticker)
                pendientes.pop(indice)
                continue
            indice += 1

        # 3. Los splits del dia que trae la historia parten lo que ya se tenia.
        for ticker in tickers:
            if ticker in registrados or _silenciado_por_manual(
                ticker, clave, splits_manuales
            ):
                continue
            factor = celda(historia.splits, dia, ticker)
            if factor > 0 and tenencia.get(ticker):
                tenencia[ticker] *= factor

        # 4. La foto de lo que se tenia al cierre de ayer, ya partida por el
        #    split de hoy si lo hubo. Es la que decide quien cobra el dividendo,
        #    y por eso se toma ANTES de los movimientos del dia.
        tenencia_ex = dict(tenencia)

        # 5. Los asientos de hoy.
        while pendientes and pendientes[0].fecha <= clave:
            _aplicar(pendientes.pop(0), dia)

        # 6. Los dividendos calculados, sobre la foto de la fecha ex.
        for ticker in tickers:
            por_accion = celda(historia.dividendos, dia, ticker)
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
