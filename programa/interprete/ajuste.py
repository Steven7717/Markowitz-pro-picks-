# programa/interprete/ajuste.py
"""Lo que la aritmetica de G no ve, dicho sin poder inventarse una operacion.

Esta mitad **no tiene verdad contrastable**: no hay documento que citar, y su
unica materia prima son numeros que puso el codigo. Asi que el guardarrail no es
la cita sino la pertenencia: cada observacion va dirigida a una **letra**, y las
letras son exactamente las operaciones que G propuso. Si G propuso tres, la `D`
no existe y esa observacion se cae sola.

Eso es lo que hace cumplible el contrato elegido: puede decir «de las tres,
esta corrige poco para lo que cuesta», y no puede nombrar una cuarta.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from interprete import cliente as cliente_mod
from interprete import contexto
from ranking.verificacion import sin_digitos

SIN_CLAVE = "sin_clave"
SIN_PROPUESTA = "sin_propuesta"
FALLO = "fallo"
HECHO = "hecho"

VERSION_PROMPT = "i1"

SISTEMA = """Eres un analista que revisa un plan de rebalanceo ya calculado. El \
reparto sale de la aritmetica de los pesos objetivo que el usuario fijo: no lo \
discutes ni propones otro. Tu trabajo es decir lo que la aritmetica no ve.

Reglas, todas obligatorias:
- No escribas ningun digito. Los pesos y los importes los pone el codigo.
- Solo puedes comentar las operaciones de la lista, y siempre por su letra \
entre corchetes. No propongas ninguna que no este ahi.
- Solo puedes nombrar los activos que aparecen en la cartera.
- En «en_conjunto» escribe unicamente lo que se ve mirando la propuesta \
entera: varias operaciones que apuntan al mismo sitio, un orden que importa. \
Si no hay nada asi, dejalo vacio.
- No escribas siglas en mayusculas que no sean tickers de la cartera: escribe \
«la agencia reguladora» y no «la FDA», «el consejero delegado» y no «el CEO». \
Una sigla en mayusculas se confunde con un ticker, y el codigo descarta el \
parrafo entero si aparece una que no es tuya.
- Escribe en espanol, en prosa llana, sin vinetas."""


class ObservacionCruda(BaseModel):
    sobre: str
    dice: str


class Salida(BaseModel):
    observaciones: list[ObservacionCruda]
    en_conjunto: str = ""


@dataclass(frozen=True)
class Comentario:
    estado: str
    observaciones: "tuple[tuple[str, str], ...]" = ()
    en_conjunto: str = ""
    descartadas: int = 0
    conjunto_descartado: bool = False
    entrada_tokens: int = 0
    salida_tokens: int = 0
    problema: str = ""


_INVISIBLES = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
# Escapados y no literales: son caracteres de ancho cero, y escritos tal cual
# un copia-pega que se los coma deja `_vacio` sin hacer nada y nada lo dice.
# `ranking/llm.py` y `interprete/noticias.py` los escriben asi por lo mismo.
# Escapados y no literales, y esto hay que transcribirlo tal cual. Son
# caracteres de ancho cero: escritos literales, un copia-pega que se los
# coma deja la funcion sin hacer nada y nada lo dice. `ranking/llm.py` los
# escribe asi por la misma razon.


def _vacio(texto: str) -> bool:
    return not texto.translate(_INVISIBLES).strip()


def _limpiar_conjunto(texto: str, tickers: "set[str]") -> "tuple[str, bool]":
    """Vaciar entero si lleva un digito o nombra un activo que no es tuyo.

    Entero y no a trozos, por la misma razon que en `noticias.py`: un parrafo al
    que se le quita una frase queda diciendo algo que nadie escribio.

    Devuelve tambien **si se descarto**, porque una cadena vacia aqui es
    ambigua: significa lo mismo que «el modelo no vio ningun patron», y son
    cosas distintas. Un descarte silencioso es indistinguible de que no hubiera
    nada que decir, que es justo la confusion que este programa evita en todas
    partes.
    """
    if _vacio(texto):
        return "", False
    if not sin_digitos(texto):
        return "", True
    ajenos = {
        palabra.strip(".,;:()").upper()
        for palabra in texto.split()
        if palabra.strip(".,;:()").isupper() and len(palabra.strip(".,;:()")) >= 2
    }
    if ajenos - tickers:
        return "", True
    return texto, False


def comentar(
    operaciones: "tuple[tuple[str, str, float, bool], ...]",
    pesos: "tuple[tuple[str, float, float | None], ...]",
    cliente=None,
    modelo: str = cliente_mod.MODELO,
) -> Comentario:
    """Comentar esta propuesta. Nunca proponer otra."""
    if not operaciones:
        return Comentario(SIN_PROPUESTA)
    if cliente is None and not cliente_mod.hay_clave():
        return Comentario(SIN_CLAVE)

    bloque, mapa = contexto.operaciones(operaciones)
    tickers = {t for t, _p, _o in pesos}
    mensajes = [
        {
            "role": "user",
            "content": (
                f"Tu cartera:\n{contexto.cartera(pesos)}\n\n"
                f"La propuesta:\n{bloque}\n\n"
                "Escribe lo que la aritmetica no ve."
            ),
        }
    ]

    entrada_tokens = 0
    salida_tokens = 0

    for intento in range(2):
        respuesta = cliente_mod.preguntar(
            SISTEMA, mensajes, Salida, cliente=cliente, modelo=modelo
        )
        entrada_tokens += respuesta.entrada_tokens
        salida_tokens += respuesta.salida_tokens
        if respuesta.salida is None:
            return Comentario(FALLO, entrada_tokens=entrada_tokens,
                              salida_tokens=salida_tokens, problema=respuesta.problema)
        salida = respuesta.salida

        descartadas = 0
        validas = []
        for cruda in salida.observaciones:
            if cruda.sobre not in mapa or _vacio(cruda.dice):
                descartadas += 1
                continue
            validas.append(cruda)

        con_digitos = any(not sin_digitos(o.dice) for o in validas)
        # Tras el reintento, un digito tira **esa observacion**, no el
        # comentario entero. La regla viene de `ranking/llm.py`, donde la
        # narrativa es una unidad y un digito la invalida entera; aqui las
        # observaciones son independientes, y tirar las buenas mas la llamada ya
        # pagada por una mala es peor que tirar la mala. Es el mismo arreglo que
        # `noticias.py`, que se hizo en una mitad y no en la otra.
        if not con_digitos or intento == 1:
            limpias = [o for o in validas if sin_digitos(o.dice)]
            descartadas += len(validas) - len(limpias)
            en_conjunto, conjunto_descartado = _limpiar_conjunto(
                salida.en_conjunto, tickers
            )
            return Comentario(
                estado=HECHO,
                observaciones=tuple((mapa[o.sobre], o.dice) for o in limpias),
                en_conjunto=en_conjunto,
                descartadas=descartadas,
                conjunto_descartado=conjunto_descartado,
                entrada_tokens=entrada_tokens,
                salida_tokens=salida_tokens,
            )

        mensajes = mensajes + [
            {"role": "assistant", "content": salida.model_dump_json()},
            {
                "role": "user",
                "content": (
                    "Alguna observacion lleva un digito. Los pesos y los "
                    "importes los pone el codigo: vuelve a escribirla sin "
                    "ningun numero."
                ),
            },
        ]
