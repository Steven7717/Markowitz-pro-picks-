import os

from pydantic import BaseModel, ValidationError

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


MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000
VERSION_PROMPT = "b1"
MAX_RIESGOS = 3

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


def _prompt(contexto: str, fuente: str) -> str:
    return (
        f"Empresa candidata:\n{contexto}\n\n"
        f"Factores de riesgo declarados por la empresa:\n<<<\n{fuente}\n>>>\n\n"
        "Escribe la tesis y hasta "
        f"{MAX_RIESGOS} riesgos, cada uno con su cita literal."
    )


def _reintento(fallidas: list[Riesgo], con_digitos: bool, tesis_vacia: bool) -> str:
    """Explain the failure that actually happened, not a fixed template.

    The first version of this function always talked about failed quotes,
    built from `fallidas` alone. That breaks the moment a narrative fails for
    a different reason with every quote intact: `fallidas` is empty, and the
    model receives a paragraph insisting quotes are missing under a heading
    that is technically true (a list of zero problems) but says nothing about
    the digit that is the actual reason the narrative was rejected. Each
    paragraph below is included only when the failure it names actually
    happened, so the model is never sent a complaint about something that was
    already fine.
    """
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
    nothing left for a human to judge.

    Digits are checked on the thesis and on each risk's `afirmacion`, never on
    its `cita` — the quote is copied verbatim from the filing and may carry
    the company's own figures, which were never invented by the model.

    At most MAX_RIESGOS risks are kept, in the order the model wrote them.
    Nothing enforced that cap before this function existed to slice the list;
    a model that ignores "hasta tres" and writes ten does not get all ten
    shipped, nor does the tenth get to fail the whole narrative — it is simply
    not part of the output.

    Only anthropic.APIError and pydantic.ValidationError degrade to None.
    Those are the two ways a call can fail that this function knows how to
    name: the API rejected or dropped the request, or the response came back
    shaped in a way the schema does not allow. Any other exception is left to
    propagate — a bug in this function, or a failure mode nobody has seen yet,
    should stop the run loudly rather than be mistaken for one company's
    narrative simply not working out.
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
        tesis_vacia = not narrativa.tesis.strip()
        con_digitos = not sin_digitos(narrativa.tesis) or any(
            not sin_digitos(riesgo.afirmacion) for riesgo in riesgos
        )
        fallidas = [
            riesgo for riesgo in riesgos if not verificar_cita(riesgo.cita, fuente)
        ]

        if not tesis_vacia and not con_digitos and not fallidas:
            return _a_dict(narrativa.tesis, riesgos, fuente)
        if intento == 1:
            if tesis_vacia or con_digitos:
                return None
            return _a_dict(narrativa.tesis, riesgos, fuente)

        mensajes = mensajes + [
            {"role": "assistant", "content": narrativa.model_dump_json()},
            {
                "role": "user",
                "content": _reintento(fallidas, con_digitos, tesis_vacia),
            },
        ]

    return None
