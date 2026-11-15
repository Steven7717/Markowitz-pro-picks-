"""Lo más que puede costar cada botón de IA del Analizador, antes de pulsarlo.

Son **topes, no estimaciones**: cada uno cuenta los dos turnos, porque el
reintento lo dispara el propio documento. Salen de las constantes que producen
el gasto, como `vistas/panel_ia.coste_peor_caso`. Lo que costó de verdad se
dice al terminar, con los tokens que devuelve la API.
"""

from analizador import informe_anual
from aprobacion import generacion
from interprete import cliente as cliente_mod
from ranking.filings import CARACTERES_POR_TOKEN

# El sistema, el bloque en palabras y las instrucciones: unos cientos de tokens,
# redondeados hacia arriba.
_TOKENS_DE_CONTEXTO = 1_000


def tesis() -> float:
    """Una ficha de candidatos con su reintento: el mismo cálculo, para una."""
    return generacion.coste_peor_caso(1)


def mdna() -> float:
    """El MD&A al tope, mandado dos veces, más el eco de la primera respuesta."""
    por_turno = int(informe_anual.TOPE_MDNA / CARACTERES_POR_TOKEN) + _TOKENS_DE_CONTEXTO
    return cliente_mod.coste(
        2 * por_turno + cliente_mod.MAX_TOKENS, 2 * cliente_mod.MAX_TOKENS
    )


def valoracion() -> float:
    """Dos turnos sin documento: lo que pesa es la salida."""
    return cliente_mod.coste(
        2 * _TOKENS_DE_CONTEXTO + cliente_mod.MAX_TOKENS, 2 * cliente_mod.MAX_TOKENS
    )
