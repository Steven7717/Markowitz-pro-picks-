import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from fundamentals.fallos import (
    NO_FACTS,
    UNKNOWN,
    UNRESOLVED_CIK,
    Fallo,
    clasificar,
)

_DEFAULT_CACHE = Path(__file__).parent / ".cache"

PERIODOS = 12
MIN_TRIMESTRES = 5

# 2 % del universo. Un falso positivo exigiría diez empresas seguidas rotas
# mientras la SEC va bien, que no es un escenario real.
RACHA_MAXIMA = 10


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


class CorridaAbortada(RuntimeError):
    """La corrida entera está condenada; seguir sólo gasta tiempo.

    Vive aquí y no en `fallos.py` porque lleva dentro la `CoverageReport`, que
    también vive aquí: al revés sería un import circular.

    Llevar la cobertura dentro es lo que permite decir cuánto se llegó a bajar
    antes de rendirse. Sin ese número, «falló» y «falló habiendo bajado 480 de
    503» se leen igual, y no son lo mismo en absoluto.
    """

    def __init__(self, causa: str, explicacion: str, cobertura: CoverageReport):
        self.causa = causa
        self.explicacion = explicacion
        self.cobertura = cobertura
        # «reunir» y no «descargar»: con media caché poblada, la mayoría de esas
        # empresas salieron de disco sin una sola petición. Este módulo se apoya
        # en que un acierto de caché no prueba que la SEC responda; llamarlos
        # descargas en el mensaje de aborto lo contradiría.
        super().__init__(
            f"{explicacion} Se abortó tras reunir "
            f"{len(cobertura.included)} de {len(cobertura.requested)} empresas."
        )


def _sin_fuente(racha: int, desconocidos: int, fallo: Fallo) -> str:
    """Por qué se abortó, diagnosticando sobre la racha entera y no sobre su
    último fallo.

    Decidir por el último manda al usuario al sitio equivocado en cuanto la
    racha mezcla causas, y mezclarlas es fácil: `unknown` sale por empresa de un
    `to_dataframe()` sobre un payload malformado, así que unos pocos tickers
    malos repartidos por el universo se entrelazan con los timeouts de una
    caída. Medido sobre la implementación anterior: nueve errores nuestros y un
    timeout final le decían al usuario que revisara una conexión que funciona, y
    nueve timeouts con un error nuestro al final le decían que el programa
    estaba roto en mitad de una caída de la SEC.

    Con tres textos, el mensaje no afirma más de lo que la evidencia sostiene.
    """
    # «el último» y no el detalle a secas: un «(ConnectTimeout)» pelado se lee
    # como si caracterizara los diez fallos, y sólo caracteriza uno.
    ultimo = f"el último, {fallo.detalle}"
    if desconocidos == racha:
        return (
            f"{racha} empresas seguidas fallaron con errores que este programa "
            f"no sabe interpretar ({ultimo}). No apunta a la SEC ni a tu "
            "conexión: lo más probable es que sea un fallo del propio programa. "
            "La corrida se para aquí en vez de repetirlo 503 veces."
        )
    if desconocidos == 0:
        # «sin entregar datos» y no «sin contestar»: la racha también avanza con
        # un 5xx, que técnicamente es una respuesta. Decir «no contestó» delante
        # de un «(HTTP 503)» sería contradecirse en la misma frase.
        return (
            f"{racha} empresas seguidas fallaron sin que la SEC entregara datos "
            f"({ultimo}). No es que fallen esas empresas: es que no hay fuente. "
            "Comprueba tu conexión y si data.sec.gov responde."
        )
    return (
        f"{racha} empresas seguidas fallaron sin entregar datos, por causas "
        f"mezcladas: {desconocidos} con errores que este programa no sabe "
        f"interpretar y {racha - desconocidos} de la SEC o de la red ({ultimo}). "
        "Puede ser la fuente o puede ser el programa, así que la corrida se para "
        "aquí en vez de repetirlo 503 veces."
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


@dataclass(frozen=True)
class Intento:
    """Qué salió de pedir un ticker, y de dónde salió.

    `facts` y `fallo` son exactamente uno de los dos: si hay hechos no hay
    fallo, y al revés. Es lo que hace inalcanzable el `pd.DataFrame()` de
    respaldo en `load_facts`, que sólo existe para satisfacer la anotación.

    `desde_cache` no es instrumentación: es lo que impide que un fichero leído
    de disco cuente como prueba de que la SEC responde. Sin ese dato, una caché
    a medio poblar apagaría el cortacircuitos de `load_facts`.
    """

    facts: pd.DataFrame | None
    fallo: Fallo | None
    desde_cache: bool = False


def _load_one(ticker: str, cache_dir: Path, refresh: bool) -> Intento:
    """Un intento por ticker; el reintento de lo transitorio es de edgartools.

    Aquí había un bucle de `max_retries=3` con `time.sleep(2.0**intento)`. Se
    quitó porque no añadía intentos útiles y sí 3 s de espera por ticker: sobre
    503 tickers, esos 3 s eran los ~25 minutos que esta función tardaba en no
    devolver nada cuando la SEC rechazaba la identidad.

    edgartools ya reintenta 5 veces con backoff lo que mejora reintentando, y
    deja pasar al primer intento lo que no —429, SSL, identidad—, que es
    justamente lo que un bucle de fuera no puede distinguir.
    """
    path = _cache_path(cache_dir, ticker)
    if path.exists() and not refresh:
        try:
            return Intento(pd.read_parquet(path), None, desde_cache=True)
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a miss
            # rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    try:
        frame = _fetch_facts(ticker)
    except Exception as exc:
        return Intento(None, clasificar(exc))

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # SEC mixes types in the raw value column and parquet needs one per
    # column. astype's errors="ignore" does not cover a missing key — it
    # still raises KeyError — so the column is checked before casting.
    if "value" in frame.columns:
        frame = frame.astype({"value": "string"})
    frame.to_parquet(tmp)
    tmp.replace(path)  # atomic rename: a reader never sees a partial file
    return Intento(frame, None)


def _anotar(cobertura: CoverageReport, ticker: str, fallo: Fallo) -> None:
    """Cada exclusión, en la casilla que le toca.

    Las tres causas restantes —`transient`, `systemic` y `unknown`— caen a
    propósito en la misma casilla, no por descuido: desde el punto de vista de
    quien lee el informe, las tres son «esta empresa no se pudo descargar». La
    diferencia entre ellas gobierna si la corrida sigue o se para, que es cosa
    de `load_facts`, no del recuento.
    """
    if fallo.causa == UNRESOLVED_CIK:
        cobertura.unresolved_cik.append(ticker)
    elif fallo.causa == NO_FACTS:
        cobertura.no_facts.append(ticker)
    else:
        cobertura.failed_download.append(ticker)


def load_facts(
    tickers: list[str],
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], CoverageReport]:
    """Download SEC's long fact table per ticker, caching each to disk.

    `refresh` re-downloads even when a cache entry exists. It defaults to False
    on purpose: quarterly reports arrive staggered, and a cache that refreshed
    itself would change the numbers between two runs without anyone asking. Like
    the universe snapshot, refreshing is a deliberate act.

    Un ticker que falla se registra y se salta. Que fallen todos por la misma
    causa no es un ticker que falla: es que no hay fuente, y entonces levanta
    `CorridaAbortada` en vez de recorrer el universo entero para no devolver
    nada. La racha se reinicia cuando la SEC entrega datos —un acierto de red o
    un 404, que también exigió preguntar—, avanza cuando preguntamos y no los
    entregó, y no se toca cuando no llegamos a preguntar: un acierto de caché o
    un CIK que resuelve contra el parquet local.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    cobertura = CoverageReport(requested=list(tickers))
    hechos: dict[str, pd.DataFrame] = {}
    racha = desconocidos = 0

    for ticker in tickers:
        intento = _load_one(ticker, cache_dir, refresh)

        if intento.fallo is None:
            hechos[ticker] = (
                intento.facts if intento.facts is not None else pd.DataFrame()
            )
            cobertura.included.append(ticker)
            if not intento.desde_cache:
                racha = desconocidos = 0
            continue

        fallo = intento.fallo
        _anotar(cobertura, ticker, fallo)

        if fallo.aborta:
            raise CorridaAbortada(fallo.causa, fallo.explicacion, cobertura)
        if fallo.fuente_viva:
            racha = desconocidos = 0
            continue
        if not fallo.cuenta_racha:
            continue

        racha += 1
        if fallo.causa == UNKNOWN:
            desconocidos += 1
        if racha >= RACHA_MAXIMA:
            raise CorridaAbortada(
                fallo.causa, _sin_fuente(racha, desconocidos, fallo), cobertura
            )

    return hechos, cobertura
