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
import unicodedata

from ranking.criterio import TAMANO_TOP

# Los sufijos de bolsa de Yahoo que se reconocen. Tabla cerrada a propósito: con
# un sufijo que no esté, el punto se lee como de clase de acción y el ticker
# sale con guion, que Yahoo no conocerá y la fila lo dirá. Lo contrario --tomar
# por bolsa cualquier cosa detrás de un punto-- convertiría `BF.B` en una bolsa
# llamada «B», y ese error no da ningún aviso.
# El precio de cerrarla: un sufijo puede coincidir con la letra de una clase.
# `V` es TSX Venture y también la clase con voto de McCormick, del S&P 500, así
# que `MKC.V` se lee como bolsa y Yahoo no lo encuentra. Escrito con guion,
# `MKC-V`, funciona siempre, porque el guion no se toca.
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
# Letras y dígitos, separados por un punto, un guion, un igual o un `&` (así
# escribe Yahoo la Ñ de Peñoles, `PE&OLES.MX`, y también sale en `M&M.NS`), y un
# `^` delante para los índices. Sin separadores seguidos ni en los extremos:
# `A..B` o `WALMEX.` no son tickers mal escritos que se puedan arreglar, son
# otra cosa.
_FORMA = re.compile(r"^\^?[A-Z0-9]+(?:[.\-=&][A-Z0-9]+)*$")
_SEPARADORES = re.compile(r"[,\s]+")
# Lo que se pega de una web o de Excel trae caracteres sin anchura que en
# pantalla no se ven, y harían inválido un ticker que se lee bien. NFKC no los
# quita, así que se borran aparte.
_INVISIBLES = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"))


def _limpiar(texto: str) -> str:
    """El texto como se ve: NFKC lleva el ancho completo (`ＭＵ，`) a `MU,`."""
    return unicodedata.normalize("NFKC", texto).translate(_INVISIBLES)


def tiene_sufijo(ticker: str) -> bool:
    """Si lo que va detrás del último punto es una bolsa de la tabla.

    Espera el ticker ya normalizado, en mayúsculas: la tabla no conoce `mx`.
    """
    _, punto, sufijo = ticker.rpartition(".")
    return bool(punto) and sufijo in SUFIJOS_DE_BOLSA


def normalizar(texto: object) -> "str | None":
    """El ticker como lo escribe Yahoo, o `None` si no tiene forma de ticker."""
    if not isinstance(texto, str):
        return None
    limpio = _limpiar(texto).strip().upper()
    if len(limpio) > _LARGO_MAXIMO or not _FORMA.match(limpio):
        return None
    if tiene_sufijo(limpio):
        base, _, sufijo = limpio.rpartition(".")
        return f"{base.replace('.', '-')}.{sufijo}"
    return limpio.replace(".", "-")


def separar(texto: "str | None") -> "tuple[list[str], list[str]]":
    """Los tickers de un campo de texto, separados por comas o espacios.

    Devuelve `(validos, invalidos)`: los válidos normalizados y sin repetir, en
    el orden en que se escribieron; los inválidos tal como se escribieron, ya
    limpios de lo que no se vería, y sin repetir, para poder decir cuáles. El
    tope de `MAX_TICKERS` lo aplica quien llama, que es quien sabe decirlo en
    pantalla.

    La limpieza va antes de partir, porque la coma de ancho completo sólo
    separa después de NFKC.
    """
    validos: list[str] = []
    invalidos: list[str] = []
    for trozo in _SEPARADORES.split(_limpiar(texto or "")):
        if not trozo:
            continue
        ticker = normalizar(trozo)
        if ticker is None:
            if trozo not in invalidos:
                invalidos.append(trozo)
        elif ticker not in validos:
            validos.append(ticker)
    return validos, invalidos
