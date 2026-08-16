import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aprobacion.carga import Candidatos

ACTAS = Path("actas")

# Letras y guion, en mayusculas: la forma que usan los tickers del universo
# real (503 nombres, de los que solo BF-B y BRK-B no son alfabeticos puros).
_FORMA_TICKER = re.compile(r"^[A-Z]+(-[A-Z]+)*$")


class MotivoRequerido(ValueError):
    """Un anadido a mano sin razon escrita."""


class TickerDuplicado(ValueError):
    """Se anadio a mano algo que el ranking ya proponia."""


class TickerInvalido(ValueError):
    """El texto no tiene forma de ticker."""


class NadaQueAprobar(ValueError):
    """Un acta sin ningun aprobado no significa nada."""


@dataclass(frozen=True)
class Anadido:
    """A company the reviewer put in by hand, with the reason it went in."""

    ticker: str
    motivo: str


def _normalizar(ticker: str) -> str:
    limpio = ticker.strip().upper()
    if not _FORMA_TICKER.match(limpio):
        raise TickerInvalido(f"{ticker!r} no tiene forma de ticker")
    return limpio


def construir_acta(
    candidatos: Candidatos,
    aprobados: set[str],
    anadidos: list[Anadido] | None = None,
    motivos: dict[str, str] | None = None,
    ahora: datetime | None = None,
) -> dict:
    """Build the dated record of one approval.

    The fichas travel copied inside, not referenced: salidas/fichas.json is
    overwritten on every run of sub-project B, so a reference would rot. That
    copy is the entire point of the artifact.

    The second list is `no_aprobados`, not `rechazados`. Checkboxes start
    unticked, so leaving one unticked can mean two very different things — it
    was considered and dropped, or it was never looked at. Calling it a
    rejection would assert a judgment that may never have happened. `motivo`
    is what separates the two: written means deliberate, absent means only
    that it did not go in.
    """
    anadidos = anadidos or []
    motivos = motivos or {}
    ahora = ahora or datetime.now()

    por_ticker = {ficha["ticker"]: ficha for ficha in candidatos.fichas}

    manuales = []
    manuales_vistos: set[str] = set()
    for anadido in anadidos:
        if not anadido.motivo.strip():
            raise MotivoRequerido(
                f"{anadido.ticker}: un ticker que entra sin ranking necesita "
                "una razon escrita, porque es la unica justificacion que va a "
                "existir"
            )
        ticker = _normalizar(anadido.ticker)
        if ticker in por_ticker:
            raise TickerDuplicado(
                f"{ticker} ya esta en el ranking: aprobalo con su casilla en "
                "vez de anadirlo a mano"
            )
        # Sin esta comprobacion, dos Anadido con el mismo ticker producirian
        # dos entradas para el mismo ticker en "aprobados" -- exactamente lo
        # que tickers_aprobados() no deberia poder devolver, porque el
        # optimizador que lo consuma pesaria esa empresa dos veces.
        if ticker in manuales_vistos:
            raise TickerDuplicado(
                f"{ticker} aparece mas de una vez entre los anadidos a mano"
            )
        manuales_vistos.add(ticker)
        manuales.append(
            {
                "ticker": ticker,
                "origen": "manual",
                "puesto": None,
                "ficha": None,
                "motivo": anadido.motivo.strip(),
            }
        )

    if not aprobados and not manuales:
        raise NadaQueAprobar("no hay ningun candidato aprobado")

    del_ranking = [
        {
            "ticker": ficha["ticker"],
            "origen": "ranking",
            "puesto": ficha["puesto"],
            "ficha": ficha,
        }
        for ficha in candidatos.fichas
        if ficha["ticker"] in aprobados
    ]

    no_aprobados = [
        {
            "ticker": ficha["ticker"],
            "puesto": ficha["puesto"],
            "ficha": ficha,
            "motivo": motivos.get(ficha["ticker"]),
        }
        for ficha in candidatos.fichas
        if ficha["ticker"] not in aprobados
    ]

    return {
        "fecha": ahora.isoformat(timespec="seconds"),
        "corrida": candidatos.corrida,
        "aprobados": del_ranking + manuales,
        "no_aprobados": no_aprobados,
    }


def tickers_aprobados(acta: dict) -> list[str]:
    """The list the optimizer needs, in the order the act records it."""
    return [entrada["ticker"] for entrada in acta["aprobados"]]


def guardar_acta(acta: dict, directorio: Path | None = None) -> Path:
    """Write the act atomically and return where it landed.

    One file per approval, named by timestamp, rather than one growing file:
    same reason fundamentals caches one file per ticker — a run killed
    mid-write cannot corrupt the whole history.

    allow_nan=False for the same reason fichas.json uses it: json.dumps writes
    a NaN as the bare literal `NaN`, which no strict parser accepts. An act
    that cannot be read back is not a record.
    """
    directorio = Path(directorio or ACTAS)
    directorio.mkdir(parents=True, exist_ok=True)

    momento = datetime.fromisoformat(acta["fecha"]).strftime("%Y-%m-%d-%H%M")
    fichero = directorio / f"{momento}.json"

    texto = json.dumps(acta, ensure_ascii=False, indent=2, allow_nan=False)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(fichero)
    return fichero
