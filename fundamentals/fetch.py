import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_DEFAULT_CACHE = Path(__file__).parent / ".cache"

PERIODOS = 12
MIN_TRIMESTRES = 5


@dataclass
class CoverageReport:
    """Which tickers made it into the panel, and why the rest did not.

    Silently dropping tickers is how an engine ends up describing a universe
    nobody chose. Every exclusion is counted and attributed to a cause.

    `unresolved_cik`, `no_facts` y `failed_download` son tres cosas distintas a
    propósito: el ticker que no existe, la empresa que existe y no publica
    facts, y la petición que no llegó a completarse. Meterlas en la misma
    casilla haría que una caída de la SEC se leyera como un universo lleno de
    empresas raras.
    """

    requested: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    unresolved_cik: list[str] = field(default_factory=list)
    no_facts: list[str] = field(default_factory=list)
    failed_download: list[str] = field(default_factory=list)
    short_history: dict[str, int] = field(default_factory=dict)
    missing_concepts: dict[str, list[str]] = field(default_factory=dict)
    missing_sector: list[str] = field(default_factory=list)
    missing_price: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Tickers solicitados: {len(self.requested)} | "
            f"incluidos: {len(self.included)} | "
            f"sin CIK: {len(self.unresolved_cik)} | "
            f"sin hechos: {len(self.no_facts)} | "
            f"fallos de descarga: {len(self.failed_download)} | "
            f"historia corta: {len(self.short_history)} | "
            f"sin sector: {len(self.missing_sector)} | "
            f"sin precio: {len(self.missing_price)}"
        )


def set_sec_identity() -> None:
    """SEC rejects requests without a contact in the User-Agent.

    Read from the environment rather than hard-coded, so nobody's personal
    address ends up in a committed file — same choice as bootstrap_universe.py.
    """
    from edgar import set_identity

    contacto = os.environ.get("EDGAR_IDENTITY")
    if not contacto:
        raise RuntimeError(
            "Falta la variable de entorno EDGAR_IDENTITY. SEC exige un contacto "
            "en el User-Agent: EDGAR_IDENTITY='tu@correo.com'"
        )
    set_identity(contacto)


def _fetch_facts(ticker: str) -> pd.DataFrame:
    """Raw edgartools call, isolated so tests can replace it without the network.

    Returns SEC's long fact table: one row per reported fact, carrying the real
    period_start/period_end dates. The per-statement helpers are not used — they
    label columns by fiscal quarter ('Q3 2026'), and a fiscal quarter is a
    different calendar window for Apple than for JPMorgan, so those labels cannot
    align companies against each other.

    No atrapa nada: las excepciones de edgartools ya distinguen lo que hay que
    distinguir y `fallos.clasificar` las sabe leer. Aquí hubo un
    `except Exception` que las convertía todas en «sin CIK», con lo que un corte
    de red acababa contado como un universo de tickers inexistentes.

    Va por `get_company_facts` y no por `Entity.get_facts()` a propósito. El
    método atrapa `CompanyFactsNotFoundError` y devuelve `None`, que queda
    indistinguible del `None` que la función devuelve por una descarga fallida
    en blando o por un parseo que no cuaja. Confundirlos mandaría un fallo de
    red a la casilla `no_facts`, cuya `fuente_viva` reinicia la racha: con la
    SEC sirviendo cuerpos vacíos, el cortacircuitos no saltaría jamás.
    """
    from edgar import Company, get_company_facts
    from edgar.exceptions import TransportError

    company = Company(ticker)  # levanta CompanyNotFoundError si no hay CIK
    facts = get_company_facts(company.cik)  # levanta CompanyFactsNotFoundError si es un 404
    if facts is None:
        # Aquí sólo se llega por fallo de descarga o de parseo, nunca por un 404.
        # TransportError es de la propia librería y clasificar() ya la lee como
        # transitoria, que es lo que hace avanzar la racha.
        #
        # Los dos casos no son iguales y se tratan igual a sabiendas: si falló la
        # descarga, la fuente está muerta y avanzar la racha es correcto; si falló
        # el parseo, la SEC contestó 200 con un cuerpo que no cuajó, o sea que la
        # fuente está viva y la racha avanza igualmente. Se acepta porque no se
        # pueden distinguir desde fuera y porque el error cae del lado seguro:
        # abortar de más, nunca seguir con datos malos. Diez tickers seguidos así
        # abortarían una corrida sana, que es improbable en un universo de 503 y
        # visible cuando pase.
        raise TransportError(f"la SEC no devolvió hechos usables para {ticker}")
    return facts.to_dataframe()


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    """Content-addressed cache name, one file per ticker.

    Uses md5 rather than the builtin hash(): Python randomises string hashing per
    process, so a builtin hash would miss on every fresh run and silently
    re-download the whole universe.

    One file per ticker because quarterly reports arrive staggered — a cache
    keyed on the whole universe would invalidate everything when one company files.
    """
    digest = hashlib.md5(ticker.encode()).hexdigest()[:12]
    return cache_dir / f"facts_{digest}.parquet"


def _load_one(
    ticker: str, cache_dir: Path, max_retries: int, refresh: bool
) -> tuple[pd.DataFrame | None, str | None]:
    """Return (facts, causa_del_fallo). Exactly one of the two is None."""
    path = _cache_path(cache_dir, ticker)
    if path.exists() and not refresh:
        try:
            return pd.read_parquet(path), None
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a miss
            # rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    for intento in range(max_retries):
        try:
            frame = _fetch_facts(ticker)
        except LookupError:
            return None, "unresolved_cik"
        except Exception:
            if intento == max_retries - 1:
                return None, "failed_download"
            time.sleep(2.0**intento)
            continue

        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        # SEC mixes types in the raw value column and parquet needs one per
        # column. astype's errors="ignore" does not cover a missing key — it
        # still raises KeyError — so the column is checked before casting.
        if "value" in frame.columns:
            frame = frame.astype({"value": "string"})
        frame.to_parquet(tmp)
        tmp.replace(path)  # atomic rename: a reader never sees a partial file
        return frame, None

    return None, "failed_download"


def load_facts(
    tickers: list[str],
    cache_dir: Path | None = None,
    max_retries: int = 3,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], CoverageReport]:
    """Download SEC's long fact table per ticker, caching each to disk.

    `refresh` re-downloads even when a cache entry exists. It defaults to False
    on purpose: quarterly reports arrive staggered, and a cache that refreshed
    itself would change the numbers between two runs without anyone asking. Like
    the universe snapshot, refreshing is a deliberate act.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    cobertura = CoverageReport(requested=list(tickers))
    hechos: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        frame, causa = _load_one(ticker, cache_dir, max_retries, refresh)
        if causa == "unresolved_cik":
            cobertura.unresolved_cik.append(ticker)
            continue
        if causa == "failed_download":
            cobertura.failed_download.append(ticker)
            continue

        hechos[ticker] = frame if frame is not None else pd.DataFrame()
        cobertura.included.append(ticker)

    return hechos, cobertura
