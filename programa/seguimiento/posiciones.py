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
