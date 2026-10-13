"""El DCF leído al revés: qué crecimiento hace falta para justificar el precio.

Es la lectura más sólida de las cuatro, porque no hay que suponer el
crecimiento: se calcula. Con margen de flujo libre positivo el valor crece con
`g`, así que una bisección converge.
"""

import math
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
    """El `x` en `limites` con `funcion(x) == objetivo`.

    `limites` es `(bajo, alto)` y `funcion` tiene que ser creciente en ellos: con
    otra forma la bisección converge a un punto cualquiera, sin avisar. Quien
    llama es quien lo garantiza.

    `Implicito(None, None)` quiere decir «no hay respuesta»: sin holgura de
    Gordon la función devuelve `None`, y con un dato sin declarar devuelve NaN
    (como un `objetivo` NaN). Sin esta salida, un NaN hace que ninguna
    comparación sea cierta y la bisección se pega al límite de abajo,
    devolviendo un valor que nadie calculó.

    El tope de 200 vueltas es un cinturón: cada una divide el intervalo por dos,
    y con un ancho de 1,1 bastan unas 31 para bajar de 1e-9.
    """
    bajo, alto = limites
    en_bajo, en_alto = funcion(bajo), funcion(alto)
    if not all(
        valor is not None and math.isfinite(valor)
        for valor in (en_bajo, en_alto, objetivo)
    ):
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
    """El crecimiento de los cinco primeros años que iguala el valor al precio.

    Sin margen positivo el valor no crece con `g` --con margen cero es plano y
    con uno negativo decrece--, y la bisección no tiene sentido. Quien filtra la
    quema de caja es el motor; la guardia vive aquí porque la función depende de
    ello, no de que alguien la llame bien.
    """
    if not datos.margen > 0:
        return Implicito(None, None)
    return biseccion(lambda g: valor_por_accion(datos, g), precio, INVERSO_LIMITES)
