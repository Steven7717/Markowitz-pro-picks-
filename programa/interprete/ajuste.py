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


def _limpiar_conjunto(texto: str, tickers: "set[str]") -> str:
    """Vaciar entero si lleva un digito o nombra un activo que no es tuyo.

    Entero y no a trozos, por la misma razon que en `noticias.py`: un parrafo al
    que se le quita una frase queda diciendo algo que nadie escribio.
    """
    if _vacio(texto) or not sin_digitos(texto):
        return ""
    ajenos = {
        palabra.strip(".,;:()").upper()
        for palabra in texto.split()
        if palabra.strip(".,;:()").isupper() and len(palabra.strip(".,;:()")) >= 2
    }
    return "" if ajenos - tickers else texto


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

    for intento in range(2):
        salida = cliente_mod.preguntar(
            SISTEMA, mensajes, Salida, cliente=cliente, modelo=modelo
        )
        if salida is None:
            return Comentario(FALLO)

        descartadas = 0
        validas = []
        for cruda in salida.observaciones:
            if cruda.sobre not in mapa or _vacio(cruda.dice):
                descartadas += 1
                continue
            validas.append(cruda)

        con_digitos = any(not sin_digitos(o.dice) for o in validas)
        if not con_digitos:
            return Comentario(
                estado=HECHO,
                observaciones=tuple((mapa[o.sobre], o.dice) for o in validas),
                en_conjunto=_limpiar_conjunto(salida.en_conjunto, tickers),
                descartadas=descartadas,
            )
        if intento == 1:
            return Comentario(FALLO)

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
