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
