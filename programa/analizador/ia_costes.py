"""Lo más que puede costar cada botón de IA del Analizador, antes de pulsarlo.

Son **topes, no estimaciones**: cada uno cuenta los dos turnos, porque el
reintento lo dispara el propio documento. Salen de las constantes que producen
el gasto, como `vistas/panel_ia.coste_peor_caso`. Lo que costó de verdad se
dice al terminar, con los tokens que devuelve la API.
"""

from analizador import informe_anual
from aprobacion import generacion
from interprete import cliente as cliente_mod

# Caracteres por token del MD&A al calcular su tope. **Es una cota prudente, no
# una medida.** La medida de `ranking/filings.py` (3,30) es de prosa, y su
# comentario avisa de que un texto con tablas puede pasarse; el MD&A lleva
# tablas de cifras, más densas en tokens. Con 2,5 el tope anunciado deja margen
# sin pasar de `cliente.TOPE_USD_POR_PULSACION`.
CARACTERES_POR_TOKEN_CON_TABLAS = 2.5

# El sistema, el bloque en palabras y las instrucciones: unos cientos de tokens,
# redondeados hacia arriba.
_TOKENS_DE_CONTEXTO = 1_000


def tesis() -> float:
    """Una ficha de candidatos con su reintento: el mismo cálculo, para una."""
    return generacion.coste_peor_caso(1)


def mdna() -> float:
    """El MD&A al tope, mandado dos veces, más el eco de la primera respuesta."""
    por_turno = int(informe_anual.TOPE_MDNA / CARACTERES_POR_TOKEN_CON_TABLAS) + _TOKENS_DE_CONTEXTO
    return cliente_mod.coste(
        2 * por_turno + cliente_mod.MAX_TOKENS, 2 * cliente_mod.MAX_TOKENS
    )


def valoracion() -> float:
    """Dos turnos sin documento: lo que pesa es la salida."""
    return cliente_mod.coste(
        2 * _TOKENS_DE_CONTEXTO + cliente_mod.MAX_TOKENS, 2 * cliente_mod.MAX_TOKENS
    )
