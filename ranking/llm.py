import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ranking.verificacion import (
    MAX_CARACTERES_CITA,
    MIN_CARACTERES_CITA,
    sin_digitos,
    verificar_cita,
)

MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000
# Task 12's cache key (ranking/llm.py:clave_cache) hashes exactly what gets
# sent to the model — the rendered prompt, via _prompt(), and SISTEMA — plus
# the bounds its answer will be judged by (MIN/MAX_CARACTERES_CITA). None of
# those needs a bump by hand: a wording change anywhere in the request, or a
# change to either bound, is already part of what changed. This stays as the
# manual escape hatch for what the hash cannot see by construction: a change
# to redactar()'s own logic — retry policy, what counts as an empty
# afirmacion, the shape written to the cached dict — that touches neither the
# rendered prompt nor these bounds. Bump it by hand whenever one of those
# changes in a way that should invalidate the cache.
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


CACHE_DIR = Path(__file__).parent / ".cache" / "fichas"

_CAMPOS_ESPERADOS = {"tesis", "riesgos"}
_CAMPOS_RIESGO_ESPERADOS = {"afirmacion", "cita", "verificada"}


def clave_cache(
    contexto: str, fuente: str, modelo: str, version: str, sistema: str = SISTEMA
) -> str:
    """Content hash of everything the model is sent, plus the bounds its
    answer will be judged by. No exceptions to that rule — anything that
    changes what redactar() sends, or how its answer gets marked verified,
    changes this key.

    hashlib rather than hash(): Python randomises string hashing between
    processes, so hash() would produce a different key on every run and the
    cache would never hit. That lesson cost a poisoned cache once already —
    see fundamentals/fetch.py:_cache_path, which uses md5 for the same reason.

    Hashes the *rendered* user turn, `_prompt(contexto, fuente)`, rather than
    contexto and fuente separately. contexto and fuente still each change the
    key on their own — both are interpolated into that render — but so does
    a wording change in _prompt() itself, with nothing to remember: the exact
    kind of change Task 11 made (delimiting contexto, spelling MAX_RIESGOS
    out in words) is automatically part of what changed. Hashing contexto and
    fuente as two separate fields, as an earlier version of this function
    did, left exactly that gap open — proven by patching _prompt() to a
    different template and watching a stale cached ficha get served with
    zero calls to the model, in silence.

    `sistema` defaults to the live SISTEMA prompt, so an ordinary call gets it
    for free and it can never drift from what redactar() actually sends to
    the model — the same guarantee _prompt() gets above, for the same reason
    (Task 11 changed SISTEMA's text twice).

    MIN/MAX_CARACTERES_CITA are folded in too: they decide each risk's
    `verificada`, which is baked into the dict this function's key ends up
    naming (see redactar_con_cache) — a cache entry written under one bound
    is not a valid answer under another.

    `version` stays regardless — not as a catch-all for the pieces above,
    which no longer need one, but as the one manual escape hatch left: for a
    change to redactar()'s own logic (retry policy, what counts as an empty
    afirmacion, the shape written to the cached dict) that touches neither
    the rendered prompt nor these bounds.
    """
    carga = json.dumps(
        {
            "prompt": _prompt(contexto, fuente),
            "modelo": modelo,
            "version": version,
            "sistema": sistema,
            "min_caracteres_cita": MIN_CARACTERES_CITA,
            "max_caracteres_cita": MAX_CARACTERES_CITA,
        },
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(carga.encode("utf-8")).hexdigest()


def _forma_valida(crudo: object) -> bool:
    """Shallow shape check, same rigor as ranking/filings.py's
    _CAMPOS_ESPERADOS: field presence, not a full schema — checking each
    value's type too would mean re-deriving Narrativa/Riesgo's validation
    here, for a file this module itself wrote.

    `riesgos` gets one extra level filings.py's flat cache never needed: it
    is a list of sub-dicts here, so an entry that is not a list — or a list
    item missing `afirmacion`, `cita`, or `verificada` — would otherwise pass
    this check only to raise TypeError or KeyError later, once something
    downstream iterates it expecting the real shape. That is the same "wedge
    the pipeline permanently on a stale file" failure filings.py's own check
    exists to avoid, one level deeper.
    """
    if not isinstance(crudo, dict) or not _CAMPOS_ESPERADOS.issubset(crudo):
        return False
    riesgos = crudo["riesgos"]
    if not isinstance(riesgos, list):
        return False
    return all(
        isinstance(riesgo, dict) and _CAMPOS_RIESGO_ESPERADOS.issubset(riesgo)
        for riesgo in riesgos
    )


def _leer_cache(fichero: Path) -> dict | None:
    """Return the cached ficha, treating a miss and a corrupt file alike.

    Same failure mode ranking/filings.py:_leer_cache exists for, handled the
    same way: a run killed mid-write leaves a truncated JSON file, and a file
    that parses but has the wrong shape (an old schema, or a JSON value that
    isn't even an object) gets the same treatment. Either is a cache miss,
    not a crash — the caller re-generates the ficha instead of failing the
    whole run over one stale or truncated file.

    The catch stays narrow (I/O and decode failures only), like filings.py's:
    the shape check below is what covers "parses but wrong shape", so
    widening the catch on top of that would also swallow a real bug in this
    function behind an innocent-looking cache miss.

    The unlink is cleanup so a bad file left on disk is not parsed and
    rejected again on every future call whose re-generation also happens to
    fail.
    """
    if not fichero.exists():
        return None
    try:
        crudo = json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        fichero.unlink(missing_ok=True)
        return None
    if not _forma_valida(crudo):
        fichero.unlink(missing_ok=True)
        return None
    return crudo


def _escribir_cache(fichero: Path, ficha: dict) -> None:
    """Write atomically so a reader never observes a half-written file.

    Same tmp-then-replace pattern as ranking/filings.py:_escribir_cache —
    replace() is atomic on both POSIX and Windows, unlike writing fichero
    directly.

    One difference from that precedent, not copied blindly: filings.py names
    its temp file by ticker alone ("{ticker}.tmp"), so two processes racing
    on the *same* ticker collide on that same temp path — a real hazard,
    flagged there for Task 14's parallel downloads, because "same ticker,
    concurrent calls" is the ordinary case a retry or a re-run produces.
    Here the temp file is named by the content hash (clave_cache), so it only
    collides if two calls hash to the exact same key — either an actual
    sha256 collision, astronomically unlikely, or two calls whose contexto,
    fuente, modelo, sistema and verification bounds are all byte-identical,
    in which case the two calls were always going to be interchangeable
    anyway. Content-addressing narrows the hazard; it does not reproduce it.
    """
    fichero.parent.mkdir(parents=True, exist_ok=True)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(ficha, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    tmp.replace(fichero)


def redactar_con_cache(
    contexto: str,
    fuente: str,
    cache_dir: Path | None = None,
    cliente=None,
    modelo: str = MODELO,
) -> dict | None:
    """redactar(), memoised on content.

    Sonnet 5 no longer accepts `temperature`, so two identical calls can
    return different narratives. The cache is what makes a rerun
    reproducible — and free: a second run over the same universe reads every
    ficha back from disk instead of paying for it again.

    Failures are never cached: a transient API error (rate limit, a dropped
    connection) would otherwise freeze into a permanent template ficha for
    that company, on every future run, for a problem that may not even
    repeat on retry.
    """
    directorio = Path(cache_dir or CACHE_DIR)
    fichero = directorio / f"{clave_cache(contexto, fuente, modelo, VERSION_PROMPT)}.json"

    cacheada = _leer_cache(fichero)
    if cacheada is not None:
        return cacheada

    resultado = redactar(contexto, fuente, cliente=cliente, modelo=modelo)
    if resultado is not None:
        _escribir_cache(fichero, resultado)
    return resultado
