import hashlib
import re
from string import ascii_uppercase

# The line between "citing a claim" and "copying the section" (MAX), and
# between "a real quote" and "two words rubber-stamped as verified" (MIN).
# Both are judgment calls, not measurements or a token budget: MAX is roughly
# one to two sentences, MIN is roughly a short clause (four or five words) —
# below the shortest quote this task's own spec uses as a valid example.
# Nothing here derives 200 or 25 from anything, and the tests below fix the
# boundary *mechanism* (checked against the normalised text, with a strict
# inequality on each side) rather than pin these particular numbers: moving
# either constant does not, by itself, fail the suite.
MAX_CARACTERES_CITA = 200
MIN_CARACTERES_CITA = 25

# SEC filings are typeset with curly quotes and en/em dashes; a model that
# "reads" a quote often re-emits the plain-ASCII equivalent, and without this
# table that turns a real quote into a rejected one. The mapping is
# punctuation code point to punctuation code point, never letter to letter —
# that guarantee is about this table specifically, not about _normalizar() as
# a whole: casefold() below does fold some letters together (e.g. "straße"
# == "strasse"), a separate, accepted trade-off of case-insensitive matching
# that this table has nothing to do with.
#
# Left uncovered on purpose, cheap side of the asymmetry (a real quote gets
# rejected, nothing fabricated gets accepted): non-breaking space (U+00A0) is
# handled for free by str.split(), which already treats it as whitespace, but
# soft hyphen (U+00AD) and zero-width space (U+200B) are not — a filing
# extracted from a PDF can carry either, and a real quote spanning one would
# fail to match.
_EQUIVALENCIAS_TIPOGRAFICAS = str.maketrans(
    {
        "‘": "'",  # left single quotation mark
        "’": "'",  # right single quotation mark (also used as apostrophe)
        "“": '"',  # left double quotation mark
        "”": '"',  # right double quotation mark
        "–": "-",  # en dash
        "—": "-",  # em dash
    }
)


def _normalizar(texto: str) -> str:
    sin_tipografia = texto.translate(_EQUIVALENCIAS_TIPOGRAFICAS)
    return " ".join(sin_tipografia.split()).casefold()


def verificar_cita(cita: str, fuente: str) -> bool:
    """Whether the quote appears verbatim in the text the model was given.

    Checked against what was sent, not the full filing: a quote from a part
    the model never saw is a quote it could not have read, however real it
    looks.

    Both length bounds are checked against the *normalised* citation, not the
    raw one — it is what is actually compared, and what MAX/MIN above are
    judgment calls about. That also means "normalised is shorter" is not a
    safe assumption: casefold() can lengthen a string (e.g. "straße" ->
    "strasse"), so a raw citation right at a bound can land on either side of
    it once normalised.

    Passing both bounds says the citation is real and plausibly sized — not
    that it is relevant to whatever claim the ficha attaches it to. Length is
    not something that can check for relevance.
    """
    normalizada = _normalizar(cita)
    if len(normalizada) < MIN_CARACTERES_CITA:
        return False
    if len(normalizada) > MAX_CARACTERES_CITA:
        return False
    return normalizada in _normalizar(fuente)


def sin_digitos(texto: str) -> bool:
    """Whether the text is free of numerals.

    Numbers in a ficha come from the panel, never from the model. A hard rule
    rather than a regex that checks each number against the data: verifying a
    number is fiddly and fails on rounding, forbidding them outright is one
    line and cannot be wrong.

    Uses str.isnumeric() rather than str.isdigit() — a strict superset (it
    additionally catches vulgar fractions like "½"), so switching can only
    turn previously-accepted text into rejected text, never the reverse.

    Two known gaps, both left unsolved because neither has a cheap check: a
    number spelled out in words ("treinta por ciento") is exactly as
    fabricated as a digit, and Roman numerals ("MMXXV") are letters, not
    numeric-category code points, so isnumeric() misses those too.
    """
    return not any(caracter.isnumeric() for caracter in texto)


# --- La valla: el texto ajeno, marcado como dato y no como instruccion -------
#
# Lo que se manda dentro de una valla lo escribio un tercero: el Item 1A de un
# 10-K, el EX-99 de un 8-K. **Es material que se lee y se cita, nunca
# instrucciones que obedecer**, y esa frase tiene que estar tambien en el
# prompt, no solo aqui.
#
# La valla anterior era `<<<` y `>>>` a secas, y no valia: bastaba con que el
# documento llevara la marca de cierre en una linea suya a mitad de pagina para
# cerrar el bloque antes de
# tiempo y que todo lo que viniera detras se leyera como instrucciones del
# programa. Y la unica defensa que quedaba no ve nada: `verificar_cita` compara
# la cita contra la misma fuente que controla quien escribio el documento, asi
# que una frase plantada verifica siempre y la pantalla la rotula «Cita literal
# del documento» justo al lado de la casilla de aprobar.
#
# La valla de ahora se cierra por dos lados a la vez, y hacen falta los dos:
#
# 1. **La marca lleva un sufijo que el texto no puede predecir.** Sale de un
#    hash del propio texto, de modo que escribir la marca de cierre dentro del
#    documento exigiria un texto cuyo hash fuese el sufijo que ese mismo texto
#    contiene: un punto fijo de SHA-256. Eso no es una barrera de coste, es una
#    preimagen.
# 2. **Las marcas a secas se neutralizan dentro del texto.** Aunque sin el
#    sufijo no cierren nada, un `>>>` suelto a mitad del documento invita al
#    modelo a creer que el bloque acabo ahi.
#
# El sufijo sale del texto y **no de `random`** porque `ranking/llm.py:
# clave_cache` hashea el prompt renderizado: una marca aleatoria daria una
# clave distinta en cada corrida y la cache no acertaria nunca. Y es de letras
# y no de digitos hexadecimales porque el turno de usuario de `ranking/llm.py`
# no puede llevar ni una cifra --hay un test que lo afirma--: la regla que el
# modelo tiene que cumplir es no escribir ninguna, y un digito pegado a esa
# regla es justo lo que un modelo copia.
_ABRE = "<<<"
_CIERRA = ">>>"
_LETRAS_DEL_SUFIJO = 12

# Runs de tres o mas, y no el literal exacto: `">>>>>"` con un solo `replace`
# quedaba en `"> > >>>"`, que vuelve a llevar la marca al final. Una expresion
# regular sobre la tirada entera no tiene ese borde.
_MARCAS_SUELTAS = re.compile(r"<{3,}|>{3,}")


def _sufijo(texto: str) -> str:
    digest = hashlib.sha256(texto.encode("utf-8")).digest()
    return "".join(
        ascii_uppercase[octeto % len(ascii_uppercase)]
        for octeto in digest[:_LETRAS_DEL_SUFIJO]
    )


def neutralizar_marcas(texto: str) -> str:
    """Las marcas de valla, separadas para que dejen de serlo.

    Se separan con espacios en vez de borrarse: lo que hay dentro de una valla
    es lo que despues se verifica caracter a caracter, asi que borrar seria
    perder texto de verdad. Separar deja el documento legible y la secuencia
    rota.

    Lo que si cuesta: una cita legitima que cruce una tirada de tres `>` se
    rechazara, porque `verificar_cita` compara contra la fuente sin tocar. Es
    el lado barato de la asimetria de siempre --una cita real rechazada, nunca
    una inventada aceptada-- y en prosa legal una tirada asi no aparece.
    """
    return _MARCAS_SUELTAS.sub(lambda hallado: " ".join(hallado.group()), texto)


def vallar(texto: str) -> str:
    """`texto` encerrado en una valla que no se puede abrir desde dentro.

    Devuelve el bloque entero, marcas incluidas, listo para pegar en un prompt.
    """
    sufijo = _sufijo(texto)
    return "\n".join(
        (f"{_ABRE}{sufijo}", neutralizar_marcas(texto), f"{_CIERRA}{sufijo}")
    )
