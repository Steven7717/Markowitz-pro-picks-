"""Qué es cada ticker y de dónde salen sus números.

**La forma del ticker es una trampa en dos sitios.**
`research.universe.normalise_ticker` cambia todo punto por guion
(`BRK.B` → `BRK-B`), que es como Yahoo escribe las clases de acción, y con eso
`WALMEX.MX` acaba en `WALMEX-MX`, que Yahoo no conoce. `aprobacion.acta`
rechaza cualquier punto. Aquí el punto se distingue por lo que lleva detrás: si
es un sufijo de bolsa de Yahoo se conserva, y si no, es de clase de acción y
pasa a guion. Las dos funciones existentes no se tocan: sirven al universo del
S&P 500 y al acta, y ahí están bien.
"""

import re

from ranking.criterio import TAMANO_TOP

# Los sufijos de bolsa de Yahoo que se reconocen. Tabla cerrada a propósito: con
# un sufijo que no esté, el punto se lee como de clase de acción y el ticker
# sale con guion, que Yahoo no conocerá y la fila lo dirá. Lo contrario --tomar
# por bolsa cualquier cosa detrás de un punto-- convertiría `BF.B` en una bolsa
# llamada «B», y ese error no da ningún aviso.
SUFIJOS_DE_BOLSA = frozenset(
    {
        "MX",  # Bolsa Mexicana de Valores
        "TO", "V", "NE", "CN",  # Toronto, TSX Venture, NEO, CSE
        "L", "IL",  # Londres
        "DE", "F", "BE", "DU", "HM", "HA", "MU", "SG",  # Xetra, Fráncfort y regionales
        "PA", "AS", "BR", "LS", "MI", "MC", "SW", "VI",
        "ST", "HE", "CO", "OL", "IR", "WA", "PR", "AT",
        "HK", "T", "SS", "SZ", "KS", "KQ", "TW", "TWO",
        "SI", "KL", "BK", "JK", "AX", "NZ",
        "SA", "BA", "SN", "JO", "TA", "IS", "NS", "BO",
    }
)

# Cada ticker cuesta varias consultas de red, y el tope es el tamaño del top de
# candidatos: lo que el usuario ya está acostumbrado a revisar de una vez.
MAX_TICKERS = TAMANO_TOP

_LARGO_MAXIMO = 20
# Letras y dígitos, separados por un punto, un guion o un igual, y un `^`
# delante para los índices. Sin separadores seguidos ni al final: `A..B` o
# `WALMEX.` no son tickers mal escritos que se puedan arreglar, son otra cosa.
_FORMA = re.compile(r"^\^?[A-Z0-9]+(?:[.\-=][A-Z0-9]+)*$")
_SEPARADORES = re.compile(r"[,\s]+")


def tiene_sufijo(ticker: str) -> bool:
    """Si lo que va detrás del último punto es una bolsa de la tabla."""
    _, punto, sufijo = ticker.rpartition(".")
    return bool(punto) and sufijo in SUFIJOS_DE_BOLSA


def normalizar(texto: object) -> "str | None":
    """El ticker como lo escribe Yahoo, o `None` si no tiene forma de ticker."""
    if not isinstance(texto, str):
        return None
    limpio = texto.strip().upper()
    if len(limpio) > _LARGO_MAXIMO or not _FORMA.match(limpio):
        return None
    base, punto, sufijo = limpio.rpartition(".")
    if punto and sufijo in SUFIJOS_DE_BOLSA:
        return f"{base.replace('.', '-')}.{sufijo}"
    return limpio.replace(".", "-")


def separar(texto: "str | None") -> "tuple[list[str], list[str]]":
    """Los tickers de un campo de texto, separados por comas o espacios.

    Devuelve `(validos, invalidos)`: los válidos normalizados y sin repetir, en
    el orden en que se escribieron; los inválidos tal como se escribieron, para
    poder decir cuáles. El tope de `MAX_TICKERS` lo aplica quien llama, que es
    quien sabe decirlo en pantalla.
    """
    validos: list[str] = []
    invalidos: list[str] = []
    for trozo in _SEPARADORES.split(texto or ""):
        if not trozo:
            continue
        ticker = normalizar(trozo)
        if ticker is None:
            invalidos.append(trozo)
        elif ticker not in validos:
            validos.append(ticker)
    return validos, invalidos
