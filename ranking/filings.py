import json
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache" / "riesgos"

# ~20k tokens estimados a 4 caracteres por token. El presupuesto real se
# comprueba con client.messages.count_tokens en el test marcado `red`: contar
# tokens de Claude con una regla de tres es una aproximación, no una medida.
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


def _leer_cache(fichero: Path) -> dict | None:
    """Return the cached raw filing, or None on a miss or a corrupt file.

    A run killed mid-write leaves a truncated JSON file that would otherwise
    make json.loads raise on every future run until someone deletes it by
    hand — the same failure mode fundamentals/fetch.py:_load_one treats as a
    cache miss for its parquet files. The unlink lets the next call
    self-heal by re-downloading instead of wedging the pipeline permanently.
    """
    if not fichero.exists():
        return None
    try:
        return json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        fichero.unlink(missing_ok=True)
        return None


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
    """
    directorio = Path(cache_dir or CACHE_DIR)
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
