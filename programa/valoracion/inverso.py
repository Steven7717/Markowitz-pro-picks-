"""El DCF leído al revés: qué crecimiento hace falta para justificar el precio.

Es la lectura más sólida de las cuatro, porque no hay que suponer el
crecimiento: se calcula. Con margen de flujo libre positivo el valor crece con
`g`, así que una bisección converge.
"""

from dataclasses import dataclass

from valoracion.criterio import INVERSO_LIMITES
from valoracion.dcf import Datos, valor_por_accion

ARRIBA = "arriba"
ABAJO = "abajo"


@dataclass(frozen=True)
class Implicito:
    """El valor que iguala el precio, o por qué lado se sale de los límites."""

    valor: "float | None"
    fuera_de_limites: "str | None"


def biseccion(funcion, objetivo: float, limites, tolerancia: float = 1e-9) -> Implicito:
    """El `x` en `limites` con `funcion(x) == objetivo`, para una función creciente."""
    bajo, alto = limites
    en_bajo, en_alto = funcion(bajo), funcion(alto)
    if en_bajo is None or en_alto is None:
        return Implicito(None, None)
    if en_alto < objetivo:
        return Implicito(None, ARRIBA)
    if en_bajo > objetivo:
        return Implicito(None, ABAJO)
    for _ in range(200):
        medio = (bajo + alto) / 2
        if funcion(medio) < objetivo:
            bajo = medio
        else:
            alto = medio
        if alto - bajo < tolerancia:
            break
    return Implicito((bajo + alto) / 2, None)


def crecimiento_implicito(datos: Datos, precio: float) -> Implicito:
    return biseccion(lambda g: valor_por_accion(datos, g), precio, INVERSO_LIMITES)
