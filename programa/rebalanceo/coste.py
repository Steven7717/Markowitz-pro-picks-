"""Qué cuesta operar, según lo que este usuario ha pagado de verdad.

La `comision` de cada compra y cada venta ya está en el libro, así que la mejor
estimación de lo que costará la siguiente es la mediana de las anteriores — no
el supuesto de nadie. `research/costs.py` tiene escenarios de 5, 10 y 25 puntos
básicos, pero son supuestos de backtest institucional sobre rotación de cartera:
muchos brókers minoristas ya cobran cero por acciones de EE.UU., así que ese
número podría equivocarse en un orden de magnitud, y en la dirección de
desaconsejar operaciones que son gratis.

Mediana y no media: una sola operación con una comisión rara —un mercado
extranjero, una corrección— no debe mover la estimación de todas las demás.
"""

import statistics

from seguimiento import posiciones
from seguimiento.libro import Asiento

OPERACIONES = frozenset({"compra", "venta"})


def por_operacion(
    asientos: list[Asiento], declarado: float
) -> tuple[float, bool]:
    """Estimated cost per trade, and whether it came from the book.

    **Las comisiones de cero cuentan.** Si el bróker no cobra y así se registró,
    la estimación correcta es cero. Filtrarlas «para quedarse con datos reales»
    convertiría un dato en la ausencia de un dato, y haría que un usuario sin
    comisiones viera operaciones bloqueadas por un coste que no paga.

    El segundo valor devuelto es lo que separa una estimación medida de un
    supuesto, y la pantalla lo dice: un número inventado que se lee como medido
    es peor que no tener número.
    """
    comisiones = [
        float(a.comision)
        for a in posiciones.vigentes(asientos)
        if a.tipo in OPERACIONES
    ]
    if not comisiones:
        return (float(declarado), False)
    return (float(statistics.median(comisiones)), True)
