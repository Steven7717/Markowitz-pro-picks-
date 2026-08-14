import os

from pydantic import BaseModel, ValidationError

from ranking.verificacion import sin_digitos, verificar_cita

MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000
# Reserved for Task 12's cache key (fichas cached by hash of the prompt
# content). Unused in this module on purpose — bump it whenever SISTEMA or
# _prompt's shape changes in a way that should invalidate that cache.
VERSION_PROMPT = "b1"
MAX_RIESGOS = 3

# _prompt() needs MAX_RIESGOS in words, not as a digit — see the comment on
# SISTEMA below for why. A lookup keeps that spelling next to the number it
# has to match; if MAX_RIESGOS ever grows past what's mapped here, this
# raises KeyError at import time — loud and immediate — rather than letting a
# bare digit slip back into the prompt.
_NUMEROS_EN_PALABRAS = {1: "un", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}
_MAX_RIESGOS_EN_PALABRAS = _NUMEROS_EN_PALABRAS[MAX_RIESGOS]

# The minimum is spelled out ("veinticinco") for the same reason the maximum
# is ("doscientos"): this text goes in front of a model whose one hard rule is
# "no digits", so the rule statement itself cannot contain one — a numeral
# right next to "don't write numerals" is exactly the kind of thing a model
# copies.
SISTEMA = """Eres un analista que redacta la ficha de una empresa candidata a \
una cartera. El orden del ranking ya está decidido por un score cuantitativo: \
tu trabajo es explicar y advertir, no valorar ni recomendar.

Reglas, todas obligatorias:
- No escribas ningún dígito. Las cifras las pone el código desde el panel.
- Las cifras que veas en el bloque "Empresa candidata" las puso el código \
para darte contexto; son suyas, no tuyas, y no se copian a la tesis ni a \
ningún riesgo.
- Cada riesgo lleva una cita literal y contigua del texto que se te entrega, \
copiada carácter a carácter, de al menos veinticinco caracteres y de menos de \
doscientos caracteres.
- Si el texto no respalda un riesgo, no lo menciones. Pocos riesgos bien \
citados valen más que muchos sin respaldo.
- Escribe en español, en prosa llana, sin viñetas."""


class Riesgo(BaseModel):
    afirmacion: str
    cita: str


class Narrativa(BaseModel):
    tesis: str
    riesgos: list[Riesgo]


# Characters that read as blank to a human (and to sin_digitos, which finds
# no numerals in them either) but that str.strip() does not remove, because
# Python's definition of whitespace does not include them. A tesis or
# afirmacion made only of these is exactly as empty as "" or "   " — the
# check has to see through them for the same reason verificar_cita's own
# docstring flags U+200B as a known gap on the citation side.
_CARACTERES_INVISIBLES = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")


def _vacio(texto: str) -> bool:
    return not texto.translate(_CARACTERES_INVISIBLES).strip()


def _prompt(contexto: str, fuente: str) -> str:
    return (
        f"Empresa candidata:\n<<<\n{contexto}\n>>>\n\n"
        f"Factores de riesgo declarados por la empresa:\n<<<\n{fuente}\n>>>\n\n"
        "Escribe la tesis y hasta "
        f"{_MAX_RIESGOS_EN_PALABRAS} riesgos, cada uno con su cita literal."
    )


def _reintento(
    fallidas: list[Riesgo],
    con_digitos: bool,
    tesis_vacia: bool,
    sin_afirmacion: list[Riesgo],
) -> str:
    """Each paragraph names a failure only if that failure actually happened —
    never a fixed template that complains about something that was fine."""
    partes = []
    if fallidas:
        listado = "\n".join(f"- {riesgo.cita}" for riesgo in fallidas)
        partes.append(
            "Estas citas no aparecen literalmente en el texto entregado:\n"
            f"{listado}\n"
            "Vuelve a escribir esos riesgos usando sólo citas que puedas copiar "
            "del texto. Si un riesgo no tiene respaldo literal, elimínalo."
        )
    if con_digitos:
        partes.append(
            "La tesis o alguna afirmación de riesgo lleva un dígito. Las cifras "
            "las pone el código desde el panel: vuelve a escribirlas sin ningún "
            "número."
        )
    if tesis_vacia:
        partes.append("La tesis llegó vacía. Escribe una tesis con contenido real.")
    if sin_afirmacion:
        partes.append(
            "Alguno de los riesgos lleva cita pero no lleva afirmación: no dice "
            "a qué advierte. Escribe la afirmación que esa cita respalda, o "
            "quita el riesgo si no tiene una advertencia real detrás."
        )
    return "\n\n".join(partes)


def _a_dict(tesis: str, riesgos: list["Riesgo"], fuente: str) -> dict:
    return {
        "tesis": tesis,
        "riesgos": [
            {
                "afirmacion": riesgo.afirmacion,
                "cita": riesgo.cita,
                "verificada": verificar_cita(riesgo.cita, fuente),
            }
            for riesgo in riesgos
        ],
    }


def redactar(
    contexto: str,
    fuente: str,
    cliente=None,
    modelo: str = MODELO,
) -> dict | None:
    """Ask the model for the qualitative half, verifying every quote by code.

    Returns None whenever the narrative cannot be trusted or produced — no
    key, an API failure, a response that fails schema validation, digits that
    survived the retry, or a thesis that came back blank. The caller ships the
    template ficha instead: the ranking never depends on this succeeding.

    A failed quote is retried once and then kept with `verificada: False`, but
    digits and a blank thesis are fatal even after the retry. The asymmetry is
    deliberate: an unbacked claim that is visibly marked can still be judged
    by a human, whereas an invented number reads exactly like a real one, and
    an empty thesis is not a narrative with a flaw — it is no narrative,
    nothing left for a human to judge. A risk with no afirmacion sits between
    the two: it invalidates only that risk, not the whole narrative — after
    the retry it is dropped rather than kept, because a citation with nothing
    said about it gives a human nothing to judge either.

    Digits are checked on the thesis and on each risk's `afirmacion`, never on
    its `cita` — the quote is copied verbatim from the filing and may carry
    the company's own figures, which were never invented by the model.

    At most MAX_RIESGOS risks are kept, in the order the model wrote them; a
    model that ignores "hasta tres" and writes ten does not get all ten
    shipped, nor does the tenth get to fail the whole narrative.
    """
    import anthropic

    if cliente is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        cliente = anthropic.Anthropic()

    mensajes: list[dict] = [{"role": "user", "content": _prompt(contexto, fuente)}]

    for intento in range(2):
        try:
            respuesta = cliente.messages.parse(
                model=modelo,
                max_tokens=MAX_TOKENS,
                system=SISTEMA,
                messages=mensajes,
                output_format=Narrativa,
                thinking={"type": "disabled"},
            )
        except (anthropic.APIError, ValidationError):
            return None

        narrativa = respuesta.parsed_output
        if narrativa is None:
            return None

        riesgos = narrativa.riesgos[:MAX_RIESGOS]
        tesis_vacia = _vacio(narrativa.tesis)
        con_digitos = not sin_digitos(narrativa.tesis) or any(
            not sin_digitos(riesgo.afirmacion) for riesgo in riesgos
        )
        sin_afirmacion = [riesgo for riesgo in riesgos if _vacio(riesgo.afirmacion)]
        fallidas = [
            riesgo for riesgo in riesgos if not verificar_cita(riesgo.cita, fuente)
        ]

        limpia = not tesis_vacia and not con_digitos and not sin_afirmacion
        if limpia and not fallidas:
            return _a_dict(narrativa.tesis, riesgos, fuente)
        if intento == 1:
            if tesis_vacia or con_digitos:
                return None
            conservados = [r for r in riesgos if not _vacio(r.afirmacion)]
            return _a_dict(narrativa.tesis, conservados, fuente)

        # The echo below necessarily contains whatever the model wrote,
        # digits included when digits were the reason for rejection — the
        # whole point of showing the model its own previous turn is so it
        # knows exactly what to change. Suppressing that content would break
        # the correction it's meant to enable, so — like the citas-fallidas
        # listing above, which quotes the filing's own text — this is an
        # accepted source of digits in the prompt, not an oversight.
        mensajes = mensajes + [
            {
                "role": "assistant",
                "content": Narrativa(
                    tesis=narrativa.tesis, riesgos=riesgos
                ).model_dump_json(),
            },
            {
                "role": "user",
                "content": _reintento(
                    fallidas, con_digitos, tesis_vacia, sin_afirmacion
                ),
            },
        ]
