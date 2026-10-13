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
        "wacc_bajo_crecimiento",
        "sin_pares",
        "sin_precio",
        "sin_tasa_libre",
        "financiera",
        "patrimonio_negativo",
        "sin_estados",
        "error_interno",
    }
)


@dataclass(frozen=True)
class Voto:
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
    return Voto(BARATA) if precio < epv else Voto(NEUTRA)


def voto_pares(pilar: "float | None") -> Voto:
    """El pilar de valoración ya lleva el signo: positivo es barata frente al sector."""
    try:
        valor = float(pilar)
    except (TypeError, ValueError):
        return Voto(NO_APLICA, "sin_pares")
    if not math.isfinite(valor):
        return Voto(NO_APLICA, "sin_pares")
    if valor >= UMBRAL_PARES:
        return Voto(BARATA)
    if valor <= -UMBRAL_PARES:
        return Voto(CARA)
    return Voto(NEUTRA)


def veredicto(votos) -> str:
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
