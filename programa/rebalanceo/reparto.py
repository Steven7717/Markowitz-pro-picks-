"""Dónde poner el dinero nuevo, que es la forma barata de rebalancear.

Comprar lo infraponderado con una aportación corrige deriva **sin vender nada**:
no paga coste de venta y no realiza ninguna plusvalía. Por eso va primero, antes
de proponer ninguna venta.
"""

from dataclasses import dataclass

from rebalanceo import criterio


@dataclass(frozen=True)
class Reparto:
    """Cuánto va a cada activo, y qué se quedó fuera por no compensar."""

    asignaciones: dict[str, float]
    descartadas: dict[str, float]


def repartir(
    valores: dict[str, float],
    objetivo: dict[str, float],
    efectivo: float,
    coste: float,
) -> Reparto:
    """Split the idle cash across the underweight assets.

    Al activo `i` le tocaría `(V+C)·wᵢ` una vez invertido todo, así que su
    déficit es `max(0, (V+C)·wᵢ − vᵢ)` y la asignación es `C · dᵢ / Σd`.

    **La fórmula no necesita ramas, y merece la pena ver por qué.** Las
    diferencias con signo suman exactamente el efectivo::

        Σ [(V+C)·wᵢ − vᵢ] = (V+C)·1 − V = C

    Los déficits son sólo las positivas, así que suman siempre `C` o más, con
    igualdad únicamente cuando ningún activo está sobreponderado. Nunca sobra
    dinero por colocar, y no hay caso especial que escribir.

    Una asignación que no supera el mínimo económico se retira **y su importe se
    reparte entre las que sí lo pasan**, repitiendo hasta que ninguna quede por
    debajo. Descartar sin redistribuir dejaría dinero sin colocar: aquí no basta
    con decir que no compensa, porque el dinero tiene que ir a alguna parte.
    """
    if efectivo <= 0:
        return Reparto({}, {})

    total = sum(valores.values()) + efectivo
    candidatos = {}
    for ticker, peso in objetivo.items():
        deficit = total * peso - valores.get(ticker, 0.0)
        if deficit > 0:
            candidatos[ticker] = deficit

    descartadas: dict[str, float] = {}
    while candidatos:
        suma = sum(candidatos.values())
        asignaciones = {
            t: efectivo * d / suma for t, d in candidatos.items()
        }
        pequenas = [
            t for t, importe in asignaciones.items()
            if not criterio.merece_la_pena(importe, coste)
        ]
        if not pequenas:
            return Reparto(asignaciones, descartadas)
        for ticker in pequenas:
            descartadas[ticker] = asignaciones[ticker]
            del candidatos[ticker]

    # Ninguna compensa: la aportacion es demasiado pequena para invertirla
    # ahora, que es una respuesta util y bastante mejor que proponer cuatro
    # compras de tres dolares.
    return Reparto({}, descartadas)
