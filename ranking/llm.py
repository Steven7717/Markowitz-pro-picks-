MAX_CARACTERES_CITA = 200

# SEC filings are typeset with curly quotes, en/em dashes, and other
# typographic punctuation; a model that "reads" a quote often re-emits the
# plain-ASCII equivalent. This table maps only punctuation to its ASCII
# counterpart, one code point to one code point, never a letter to another
# letter — so it cannot turn one word into a different word. A fabricated
# quote that merely swaps an ASCII dash for an em dash is still the same
# words as some real quote and was never the threat; a fabricated quote with
# different wording still fails the substring check afterwards, translation
# table or not. Non-breaking spaces need no entry here: str.split() already
# treats them as whitespace (verified against U+00A0), so they fall into the
# same bucket as ordinary spaces below.
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

    Checked against what was sent, not against the full filing: a quote from a
    part the model never saw is a quote it could not have read, however real it
    looks.

    Whitespace, case and typographic punctuation are normalised because a line
    break or a curly quote in the filing is not a fabrication — see the comment
    above _EQUIVALENCIAS_TIPOGRAFICAS for why that specific substitution cannot
    hide a fabricated quote.

    A citation that is empty, or that collapses to nothing once normalised
    (e.g. a string of only whitespace), is rejected rather than treated as
    trivially "found" — an empty needle is a substring of everything, which
    would let a blank citation pass as verified.

    The length cap is checked against the *normalised* citation, not the raw
    one, because the cap is a limit on how much content is being quoted, and
    content is what survives normalisation. Capping the raw string instead
    would reject a real, short quote just because the model inserted a few
    extra line breaks or spaces while copying it — punishing formatting noise
    that normalisation exists to ignore in the first place.
    """
    if not cita:
        return False
    normalizada = _normalizar(cita)
    if not normalizada or len(normalizada) > MAX_CARACTERES_CITA:
        return False
    return normalizada in _normalizar(fuente)


def sin_digitos(texto: str) -> bool:
    """Whether the text is free of numerals.

    Numbers in a ficha come from the panel, never from the model. A hard rule
    rather than a regex that tries to check each number against the data:
    verifying a number is fiddly and fails on rounding, whereas forbidding them
    outright is one line and cannot be wrong.

    Checked with str.isnumeric() rather than str.isdigit(): both catch plain
    digits, superscripts ("x²") and Arabic-indic digits ("٣"), but isnumeric()
    additionally catches vulgar fractions ("½"), which isdigit() misses. Since
    isnumeric() is a strict superset, switching to it can only turn some
    previously-accepted text into rejected text, never the other way around —
    consistent with this being a deliberately hard rule where a false
    rejection just falls back to the template ficha, and a false acceptance
    lets a fabricated number through.

    Known gap, left unsolved on purpose: a number spelled out in words
    ("supera el treinta por ciento del sector") is exactly as fabricated as a
    digit and neither isdigit() nor isnumeric() catches it. There is no cheap
    check for that — it would need language-aware parsing — so it is not
    attempted here.
    """
    return not any(caracter.isnumeric() for caracter in texto)
