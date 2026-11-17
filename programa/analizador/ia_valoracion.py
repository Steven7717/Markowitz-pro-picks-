"""Qué significa la valoración, explicado sin poder inventar una cifra ni un consejo.

Esta lectura **no tiene verdad contrastable**: no lee nada de la empresa, sólo
los votos y los supuestos que el código ya tradujo a palabras
(`analizador/palabras.py`). Así que el guardarraíl no es la cita sino el de
`interprete/ajuste.py`, más uno propio:

- **Pertenencia.** Cada observación va dirigida a una letra del mapa. Una letra
  que no está se cae sola.
- **Cero dígitos.** Una observación con un dígito se tira entera.
- **Sin recomendaciones.** El prompt lo prohíbe y el código lo comprueba: una
  observación que recomienda sale **marcada**, no borrada, igual que una cita
  sin verificar. Borrarla en silencio escondería que el modelo lo intentó.
- **El párrafo de conjunto se vacía entero** si lleva un dígito o recomienda.
  Entero y no a trozos: un párrafo al que se le quita una frase dice algo que
  nadie escribió.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel

from interprete import cliente as cliente_mod
from ranking.verificacion import sin_digitos

SIN_CLAVE = "sin_clave"
SIN_VALORACION = "sin_valoracion"
FALLO = "fallo"
HECHA = "hecha"

# No es una clave de caché: es la procedencia que se anota con cada explicación.
VERSION_PROMPT = "n1"

# El detector de recomendaciones. Una raíz suelta (`compr`, `vend`) marcaba
# frases que describen («la empresa vende memoria», «los clientes compran
# menos»), así que se cubren **formas**, no raíces. Prioridad: no dar falsos
# positivos en frases descriptivas; lo dudoso se deja pasar.
#
# 1. Palabras que sólo se usan para recomendar, en cualquier forma:
#    recomiendo/recomendación/recomendable, aconseja/aconsejable/desaconsejable,
#    sugiero.
# 2. Formas de primera o segunda persona de comprar y vender, que se dirigen a
#    alguien: condicional (comprarías, vendería), futuro (compraré, venderé),
#    subjuntivo (compremos, compres), presente en primera persona (compro, vendo)
#    e imperativo con pronombre (cómprala, compradla, véndelo). No las de tercera
#    persona (vende, compran, venderán), que describen.
# 3. «Esperaría» (yo esperaría), salvo que lleve complemento («esperaría más
#    crecimiento»): `espera`/`esperan` a secas describen lo que se espera.
# 4. Un disparador de consejo (conviene, deberías, hay que, mejor, momento de/para,
#    hora de) seguido de un verbo de operar (comprar, vender, adquirir, acumular,
#    invertir, deshacerse, esperar, mantener la posición, y entrar/salir si cierran
#    la frase o hablan del valor). «Conviene recordar que…» no basta.
# 5. Sustantivos de operación: oportunidad/señal/momento de compra o de venta.
_CL = r"(?:l[aeo]s?|me|te|se|nos)"
_OPERAR = (
    rf"(?:(?:comprar|vender|adquirir|acumular|invertir){_CL}?|deshacerse|esperar"
    r"|mantener\s+(?:la|su|tu|esa|esta)\s+posici[oó]n"
    r"|(?:entrar|salir)(?=\s*(?:[.,;:!?]|$|ya\b|ahora\b|del\s+valor|de\s+la\s+(?:acci|posici))))"
)
_RECOMIENDA = re.compile(
    r"(?<!\w)(?:"
    r"(?:des)?aconsej\w*|recomiend\w*|recomend\w*|sugiero"
    r"|comprar(?:ía|ías|íamos|é|ás|emos)|vender(?:ía|ías|íamos|é|ás|emos)"
    r"|compremos|compres|vendamos|compro|vendo"
    rf"|c[oó]mpr(?:a|e){_CL}|comprad{_CL}|v[eé]nd(?:e|a){_CL}|vended{_CL}"
    r"|esperar(?:ía|ías|íamos)(?!\s+(?:que|más|mucho|menos|poco|un|una|el|la|los|las|algo)\b)"
    rf"|(?:(?<!\ble )(?<!\bles )conviene|convendría|convenga|deberías|deberíamos|hay\s+que|habría\s+que)"
    rf"[\s,]+(?:\w+[\s,]+){{0,3}}?{_OPERAR}"
    rf"|(?:lo\s+mejor\s+es|es\s+mejor|mejor|momento\s+(?:de|para)|hora\s+de)\s+{_OPERAR}"
    r"|(?:oportunidad|señal|momento)\s+de\s+(?:compra|venta)"
    r")(?!\w)",
    re.IGNORECASE,
)

SISTEMA = """Eres un analista que explica una valoración ya calculada a alguien \
que no es financiero. Las lecturas, los votos y el veredicto los puso el código: \
no los discutes ni propones otros. Tu trabajo es decir qué significa cada \
lectura y de qué depende que siga siendo cierta.

Reglas, todas obligatorias:
- No escribas ningún dígito. Las cifras las pone el código.
- Sólo puedes comentar las lecturas de la lista. En el campo «sobre» va la \
letra de la lectura, sola. No comentes ninguna que no esté ahí.
- No recomiendes comprar, vender ni esperar, ni aconsejes nada: explicas, y \
decide quien lee.
- En «en_conjunto» escribe únicamente lo que se ve mirando las lecturas a la \
vez: si se contradicen, si dependen del mismo supuesto. Si no hay nada así, \
déjalo vacío. Vacío es una respuesta.
- Escribe en español, en prosa llana, sin viñetas y sin siglas."""


class ObservacionCruda(BaseModel):
    sobre: str
    dice: str


class Salida(BaseModel):
    observaciones: list[ObservacionCruda]
    en_conjunto: str = ""


@dataclass(frozen=True)
class Observacion:
    """`sobre` es la lectura (`flujos`, `sin_crecimiento`, `pares`), no la letra."""

    sobre: str
    dice: str
    marcada: bool


@dataclass(frozen=True)
class Explicacion:
    estado: str
    observaciones: "tuple[Observacion, ...]" = ()
    en_conjunto: str = ""
    descartadas: int = 0
    conjunto_descartado: bool = False
    entrada_tokens: int = 0
    salida_tokens: int = 0
    problema: str = ""


_INVISIBLES = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")


def _vacio(texto: str) -> bool:
    return not texto.translate(_INVISIBLES).strip()


def recomienda(texto: str) -> bool:
    """Si el texto recomienda comprar o vender, o aconseja algo."""
    return _RECOMIENDA.search(texto) is not None


def _limpiar_conjunto(texto: str) -> "tuple[str, bool]":
    """El párrafo, o vacío si falla; y **si se descartó**, que no es lo mismo que venir vacío."""
    if _vacio(texto):
        return "", False
    if not sin_digitos(texto) or recomienda(texto):
        return "", True
    return texto, False


def _letra(sobre: str) -> str:
    return sobre.strip().strip("[]").strip().upper()


def explicar(
    bloque: str,
    mapa: "dict[str, str]",
    cliente=None,
    modelo: str = cliente_mod.MODELO,
) -> Explicacion:
    """Explicar esta valoración. `bloque` y `mapa` salen de `palabras.contexto_valoracion`."""
    if not mapa:
        return Explicacion(SIN_VALORACION)
    if cliente is None and not cliente_mod.hay_clave():
        return Explicacion(SIN_CLAVE)

    mensajes = [
        {
            "role": "user",
            "content": (
                f"La valoración, en palabras:\n{bloque}\n\n"
                "Explica qué significa cada lectura y de qué depende."
            ),
        }
    ]
    entrada_tokens = 0
    salida_tokens = 0

    for intento in range(2):
        respuesta = cliente_mod.preguntar(SISTEMA, mensajes, Salida, cliente=cliente, modelo=modelo)
        entrada_tokens += respuesta.entrada_tokens
        salida_tokens += respuesta.salida_tokens
        if respuesta.salida is None:
            return Explicacion(
                FALLO, entrada_tokens=entrada_tokens, salida_tokens=salida_tokens,
                problema=respuesta.problema,
            )
        salida = respuesta.salida

        descartadas = 0
        validas = []
        for cruda in salida.observaciones:
            if _letra(cruda.sobre) not in mapa or _vacio(cruda.dice):
                descartadas += 1
                continue
            validas.append(cruda)

        con_digitos = any(not sin_digitos(o.dice) for o in validas)
        # El tope se mira antes de pedir el segundo turno: después ya se gastó.
        if not con_digitos or intento == 1 or not cliente_mod.dentro_del_tope(
            entrada_tokens, salida_tokens
        ):
            limpias = [o for o in validas if sin_digitos(o.dice)]
            descartadas += len(validas) - len(limpias)
            en_conjunto, conjunto_descartado = _limpiar_conjunto(salida.en_conjunto)
            return Explicacion(
                estado=HECHA,
                observaciones=tuple(
                    Observacion(mapa[_letra(o.sobre)], o.dice, recomienda(o.dice)) for o in limpias
                ),
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
                    "Alguna observación lleva un dígito. Las cifras las pone el "
                    "código: vuelve a escribirla sin ningún número."
                ),
            },
        ]
