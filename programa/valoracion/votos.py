"""Los tres votos y el veredicto.

Cuatro lecturas y tres votos, no cuatro: el DCF y su inverso son la misma
ecuación leída en las dos direcciones, y si votaran por separado una sola
lectura contaría dos veces. El voto de flujos lo da el inverso; el rango del
DCF es su contexto.
"""

import math
from dataclasses import dataclass

from valoracion.criterio import MIN_VOTOS, UMBRAL_PARES
from valoracion.inverso import ABAJO, ARRIBA, Implicito

BARATA = "barata"
NEUTRA = "neutra"
CARA = "cara"
NO_APLICA = "no_aplica"

VEREDICTOS = ("infravalorada", "sobrevalorada", "mixtas", "en_rango", "sin_datos")

# Todas las claves de motivo que este paquete puede escribir. La pantalla tiene
# que tener una etiqueta para cada una, y un test lo comprueba.
MOTIVOS = frozenset(
    {
        "quema_caja",
        "ebit_negativo",
        "sin_historia",
        "sin_beneficio_operativo",
        "sin_flujo_libre",
        "wacc_bajo_crecimiento",
        "sin_pares",
        "sin_precio",
        "sin_red",
        "sin_tasa_libre",
        "sin_bono_m",
        "financiera",
        "patrimonio_negativo",
        "sin_estados",
        "error_interno",
    }
)


@dataclass(frozen=True)
class Voto:
    """Un voto y, si no aplica, por qué.

    `motivo` es una clave de `MOTIVOS`, nunca texto de pantalla: la etiqueta
    legible vive en la vista, y así una ficha guardada no se queda con una frase
    que luego se reescriba.
    """

    voto: str
    motivo: "str | None" = None


def margen_voto(referencia: float, minimo: float) -> float:
    """El mayor entre `minimo` y la mitad de la referencia.

    Con un crecimiento de referencia del 22 % son ±11 puntos; con un 5 %, ±5. El
    mismo margen abre los escenarios pesimista y optimista, así que el rango del
    DCF y el voto de flujos dicen lo mismo con dos dibujos.
    """
    return max(minimo, 0.5 * abs(referencia))


def voto_implicito(implicito: Implicito, referencia: float, margen: float) -> Voto:
    """Compara el valor implícito con la referencia, a un lado y otro del margen.

    Salirse de los límites de la bisección ya es una respuesta: por ARRIBA ni el
    crecimiento (o el ROE) más alto que se permite llega a justificar el precio,
    o sea «cara», y por ABAJO el precio se justifica hasta con el más bajo, o sea
    «barata».

    «ARRIBA → cara» (y «ABAJO → barata») es exacto mientras los límites de la
    bisección queden fuera de la banda neutra: se cumple con un `g_ref` dentro
    de sus topes y con un `roe_ref` entre un −13 % y un +40 % aproximadamente.

    `margen` tiene que salir de `margen_voto`: con un margen negativo las dos
    bandas se cruzan y un mismo valor sería a la vez cara y barata.

    `Implicito(None, None)` es una red de seguridad para un invariante roto, no
    un caso corriente: el motor comprueba `wacc_bajo_crecimiento`, `quema_caja`
    y `patrimonio_negativo` ANTES de invertir, así que una empresa real no llega
    aquí por ninguna de esas causas y el motivo genérico no las tapa.
    """
    if implicito.fuera_de_limites == ARRIBA:
        return Voto(CARA)
    if implicito.fuera_de_limites == ABAJO:
        return Voto(BARATA)
    if implicito.valor is None:
        return Voto(NO_APLICA, "sin_historia")
    if implicito.valor > referencia + margen:
        return Voto(CARA)
    if implicito.valor < referencia - margen:
        return Voto(BARATA)
    return Voto(NEUTRA)


def voto_epv(epv: float, precio: float) -> Voto:
    """Nunca «cara», a propósito: pagar por el crecimiento no es estar cara.

    La consecuencia es que «sobrevalorada» exige que coincidan flujos y pares:
    cara frente a sus propios números y frente a su sector.
    """
    # Con NaN toda comparación es falsa y el voto saldría «neutra»; con un EPV
    # infinito saldría «barata». Sería un voto que nadie calculó, y además puede
    # ser el que complete un «en_rango» o una «infravalorada» con datos rotos.
    if not (math.isfinite(epv) and math.isfinite(precio)):
        return Voto(NO_APLICA, "sin_precio")
    return Voto(BARATA) if precio < epv else Voto(NEUTRA)


def voto_pares(pilar: "float | None") -> Voto:
    """El pilar de valoración ya lleva el signo: positivo es barata frente al sector."""
    # OverflowError: un entero enorme (10**400) es legal pero `float()` no lo
    # convierte, y no es ni TypeError ni ValueError.
    try:
        valor = float(pilar)
    except (TypeError, ValueError, OverflowError):
        return Voto(NO_APLICA, "sin_pares")
    if not math.isfinite(valor):
        return Voto(NO_APLICA, "sin_pares")
    if valor >= UMBRAL_PARES:
        return Voto(BARATA)
    if valor <= -UMBRAL_PARES:
        return Voto(CARA)
    return Voto(NEUTRA)


def veredicto(votos) -> str:
    """El veredicto de los votos, que pueden venir de cualquier iterable.

    El motor pasa `dict.values()`, así que sólo se recorre una vez. Sólo
    «sin_datos» tiene que ir primero, porque con menos de `MIN_VOTOS` votos
    aplicables ni una unanimidad cuenta. Las otras tres condiciones (dos baratas
    sin cara, dos caras sin barata, y al menos una de cada) se excluyen entre
    sí, y «en_rango» es lo que queda: a lo sumo un voto en un sentido y el resto
    neutros.
    """
    aplicables = [v.voto for v in votos if v.voto != NO_APLICA]
    baratas, caras = aplicables.count(BARATA), aplicables.count(CARA)
    if len(aplicables) < MIN_VOTOS:
        return "sin_datos"
    if baratas >= 2 and caras == 0:
        return "infravalorada"
    if caras >= 2 and baratas == 0:
        return "sobrevalorada"
    if baratas >= 1 and caras >= 1:
        return "mixtas"
    return "en_rango"
