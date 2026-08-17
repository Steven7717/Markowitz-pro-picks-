import json
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache" / "riesgos"

# Medido con count_tokens contra la API real el 2026-08-16, no estimado: este
# tope da **24.231 tokens** en el peor caso probado (el Item 1A de JPM, que
# llega recortado justo aquí). La proporción real es de 3,30 caracteres por
# token en texto legal denso —3,54 en Apple, 3,02 en el filing corto de
# Incyte—, no los 4,0 que asumió el diseño: la regla de tres se quedaba corta
# en un 21%.
#
# Importa porque el test `red` que lo comprueba afirma < 25.000 tokens, así que
# el margen real es del 3%. Un filing más denso en cifras y tablas podría
# pasarse con este mismo tope de caracteres. Si ese test falla algún día no
# será un fallo del código: será esta cota diciendo que hay que bajar
# MAX_CARACTERES.
MAX_CARACTERES = 80_000

SECCION = "Item 1A"


@dataclass(frozen=True)
class Riesgos:
    """The risk-factor section as it was sent to the model, with its provenance."""

    ticker: str
    formulario: str
    fecha: str
    accession: str
    seccion: str
    texto: str
    caracteres_totales: int
    recortado: bool


def _descargar(ticker: str) -> dict | None:
    """Fetch Item 1A of the latest 10-K.

    Isolated so tests can replace it without touching the network, the same way
    fundamentals.fetch isolates its own SEC call. Setting the SEC identity is the
    caller's job, not this function's — see fundamentals/fetch.py:set_sec_identity.
    """
    from edgar import Company

    presentacion = Company(ticker).get_filings(form="10-K").latest(1)
    if presentacion is None:
        return None
    texto = getattr(presentacion.obj(), "risk_factors", None)
    if not texto:
        return None
    return {
        "formulario": presentacion.form,
        "fecha": str(presentacion.filing_date),
        "accession": presentacion.accession_no,
        "texto": texto,
    }


_CAMPOS_ESPERADOS = {"formulario", "fecha", "accession", "texto"}


def _leer_cache(fichero: Path) -> dict | None:
    """Return the cached raw filing, treating a miss and a corrupt file alike.

    A run killed mid-write leaves a truncated JSON file — the same failure mode
    fundamentals/fetch.py:_load_one treats as a cache miss for its parquet
    files. A file that parses but has the wrong shape (an old schema missing
    "texto", or a JSON value that isn't even an object) gets the same
    treatment, otherwise it would pass this function only to raise KeyError or
    TypeError later in cargar_riesgos — the exact "wedge the pipeline
    permanently" failure this function exists to avoid.

    Returning None is what makes the caller re-download; the unlink is a
    separate cleanup so a bad file left on disk doesn't get parsed and
    rejected again on every call whose re-download also happens to fail.
    """
    if not fichero.exists():
        return None
    # fetch.py:_load_one catches bare Exception around its parquet read; here
    # the catch stays narrow (I/O and decode failures only) because the shape
    # check below is what now covers "parses but wrong shape" — widening the
    # catch on top of that would also swallow a real bug in this function
    # (e.g. a NameError) behind an innocent-looking cache miss.
    try:
        crudo = json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        fichero.unlink(missing_ok=True)
        return None
    if not isinstance(crudo, dict) or not _CAMPOS_ESPERADOS.issubset(crudo):
        fichero.unlink(missing_ok=True)
        return None
    return crudo


def _escribir_cache(fichero: Path, crudo: dict) -> None:
    """Write atomically so a reader never observes a half-written file.

    Same tmp-then-replace pattern as fundamentals/fetch.py:_load_one — replace()
    is atomic on both POSIX and Windows, unlike writing fichero directly.
    """
    fichero.parent.mkdir(parents=True, exist_ok=True)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(json.dumps(crudo, ensure_ascii=False), encoding="utf-8")
    tmp.replace(fichero)


def cargar_riesgos(
    ticker: str,
    cache_dir: Path | None = None,
    max_caracteres: int = MAX_CARACTERES,
    refresh: bool = False,
) -> Riesgos | None:
    """Item 1A of the company's latest 10-K, truncated to a hard budget.

    Returns None when the filing has no extractable section. That result is
    deliberately NOT cached: a miss today can stop being one tomorrow (the
    company finally files its 10-K, or edgartools' extraction improves), and
    fundamentals/fetch.py:_load_one already treats its own two failure modes
    (unresolved_cik, failed_download) the same way — only successful results
    are written to disk. The cost is a repeated request per run for whichever
    tickers keep missing; that trade favors freshness over saving requests.

    The cache stores the full section and truncation happens on read, so raising
    or lowering the token budget never costs a second download.

    If refresh=True and the re-download fails (returns None), any existing
    cache entry is left untouched on disk and this call returns None rather
    than falling back to it — the next call without refresh will serve that
    now-possibly-stale entry silently. That is deliberate: stale is still
    better than nothing for a narrative input, and refresh is the one lever an
    operator reaches for specifically when they suspect the cache, so a silent
    fallback there would hide the very thing they were checking.
    """
    directorio = Path(cache_dir or CACHE_DIR)
    # One file per ticker, named directly by the ticker rather than hashed the
    # way fundamentals/fetch.py:_cache_path hashes it (md5, content-addressed):
    # here a human is expected to open the file by hand to confirm a citation
    # really appears in the Item 1A it claims to. Safe as a filename because
    # tickers come from the curated S&P 500 CSV (503 tickers, only BF-B and
    # BRK-B non-alphabetic, no dots or slashes in any of them).
    fichero = directorio / f"{ticker}.json"

    crudo = None if refresh else _leer_cache(fichero)
    if crudo is None:
        crudo = _descargar(ticker)
        if crudo is not None:
            _escribir_cache(fichero, crudo)

    if crudo is None:
        return None

    completo = crudo["texto"]
    return Riesgos(
        ticker=ticker,
        formulario=crudo["formulario"],
        fecha=crudo["fecha"],
        accession=crudo["accession"],
        seccion=SECCION,
        texto=completo[:max_caracteres],
        caracteres_totales=len(completo),
        recortado=len(completo) > max_caracteres,
    )
