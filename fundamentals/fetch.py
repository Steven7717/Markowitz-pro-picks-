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

# Diez fallos seguidos, pero «seguidos» no quiere decir seguidos en el universo:
# quiere decir seguidos entre los tickers que llegaron a tocar la red. Un acierto
# de caché no reinicia la racha —ver el invariante en `load_facts`— así que con
# la caché caliente el conjunto se encoge a los tickers que aún fallan, y unos
# fallos permanentes repartidos por el índice quedan adyacentes entre sí.
#
# Medido: 11 tickers con el payload roto, uno cada 50 posiciones, con la SEC
# sana. Primera corrida, 492 incluidas. Segunda, con los 492 en caché, aborta a
# la décima petición diciendo que no hay fuente. O sea que lo que de verdad topa
# esta constante no es el 2 % del universo: es el número de empresas
# permanentemente rotas que haya en él. Hoy es ~1 (`salidas/corrida.json` da
# n_panel 502 de 503), así que el margen es de uno contra diez — real, pero no
# el que sugería el comentario anterior, que hablaba de un escenario
# «no real».
RACHA_MAXIMA = 10

# Un conteo solo no acota el caso «SEC colgada»: con un read timeout de 30 s y
# los 5 intentos de stamina, cada ticker cuesta ~2,7 min, y RACHA_MAXIMA de esos
# son 27 minutos — que es el problema que este módulo existe para no tener.
SIN_RESPUESTA_MAXIMO = 180.0

# Sin este mínimo, el tope de tiempo dispararía con sólo dos muestras: con 500
# tickers cacheados entre dos fallos de red 200 s aparte, el reloj no se apaga
# —los aciertos de caché no lo tocan— y el segundo fallo condenaría una corrida
# sana que ya reunió casi todo el universo. RACHA_MAXIMA exige diez muestras
# para decir «no hay fuente»; este mínimo alinea al tope de tiempo con esa
# misma exigencia sin costarle nada al caso que sí importa: medido, a 162
# s/ticker el tope ya dispara en el tercer fallo, y a 25 s/ticker en el noveno.
#
# La alternativa obvia —que un acierto de caché también reinicie el reloj— se
# descarta porque rompe el caso para el que existe el tope de tiempo: con la
# caché medio poblada, fallo, fallo, acierto, fallo, fallo… nunca se acumulan
# 180 s seguidos, y la corrida cae al tope de racha: diez fallos × 2,7 min son
# los 27 minutos que este módulo existe para no tener.
SIN_RESPUESTA_RACHA_MINIMA = 3


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
        #
        # Y se dice que lo reunido se guarda. Varios de estos mensajes acaban
        # pidiéndole al usuario que reintente, y lo que le hace no reintentar no
        # es no saber la causa: es acordarse de que la última vez esto tardó 25
        # minutos. Decirle que las que ya están no se vuelven a bajar es la mitad
        # del arreglo, y sin ella sólo se entrega el mecanismo.
        reunidas = len(cobertura.included)
        super().__init__(
            f"{explicacion} Se abortó tras reunir "
            f"{reunidas} de {len(cobertura.requested)} empresas"
            + (
                f"; esas {reunidas} quedan en caché y no se vuelven a bajar."
                if reunidas
                else "."
            )
        )


def _diagnostico(racha: int, desconocidos: int, fallo: Fallo) -> str:
    """La atribución de causa, compartida por los dos topes.

    Vive aparte porque los dos mensajes difieren sólo en cómo llegaron —uno
    cuenta fallos, el otro cuenta segundos— y en nada en el diagnóstico. Cuando
    estaban duplicados, arreglar uno dejó al otro mintiendo: una racha 100%
    `unknown` que tarda más de `SIN_RESPUESTA_MAXIMO` en abortar por tiempo es
    alcanzable —un `to_dataframe()` que revienta después de descargar de
    verdad cuesta un ticker entero, no microsegundos— y hasta este cambio el
    texto de ese aborto decía «comprueba tu conexión» sobre un fallo que no
    tiene nada que ver con la conexión.

    Decidir por el último fallo manda al usuario al sitio equivocado en cuanto
    la racha mezcla causas, y mezclarlas es fácil: `unknown` sale por empresa de
    un `to_dataframe()` sobre un payload malformado, así que unos pocos tickers
    malos repartidos por el universo se entrelazan con los timeouts de una
    caída. Medido sobre la implementación anterior: nueve errores nuestros y un
    timeout final le decían al usuario que revisara una conexión que funciona, y
    nueve timeouts con un error nuestro al final le decían que el programa
    estaba roto en mitad de una caída de la SEC.

    Con tres textos, el mensaje no afirma más de lo que la evidencia sostiene.
    """
    # «el último fallo» y no el detalle a secas: un «(ConnectTimeout)» pelado se
    # lee como si caracterizara los diez fallos, y sólo caracteriza uno. Lleva
    # «fallo» explícito porque sin él el texto sólo funciona en la rama
    # all-unknown («errores... el último») -- en la pura SEC el sustantivo más
    # cercano es «datos» (leería «el último dato») y en la mixta es «la red»
    # (leería «el último de la red» en vez de el último de los diez).
    ultimo = f"el último fallo, {fallo.detalle}"
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
    # La rama mixta no puede decir «sin entregar datos» de las dos partes: la
    # mitad `unknown` es justo lo contrario, un to_dataframe() que falló sobre
    # un cuerpo que la SEC sí entregó. Y termina diciendo qué hacer, no que el
    # programa no puede decidir: comprobar la conexión es gratis e instantáneo,
    # así que va primero; culpar al programa sólo se justifica una vez que esa
    # comprobación sale limpia.
    sin_interpretar = (
        "un error que este programa no sabe interpretar"
        if desconocidos == 1
        else "errores que este programa no sabe interpretar"
    )
    return (
        f"{racha} empresas seguidas fallaron por causas mezcladas: "
        f"{desconocidos} con {sin_interpretar} y {racha - desconocidos} de la "
        f"SEC o de la red ({ultimo}). Comprueba primero tu conexión y si "
        "data.sec.gov responde; si van bien, es un fallo del propio programa."
    )


def _sin_fuente(racha: int, desconocidos: int, fallo: Fallo) -> str:
    """Por qué se abortó por racha: la atribución de `_diagnostico`, tal cual.

    `_diagnostico` ya empieza nombrando la racha («N empresas seguidas
    fallaron…»), así que este tope no necesita una frase propia delante — a
    diferencia de `_sin_respuesta`, que sí la necesita para decir que llegó
    por tiempo y no por conteo.
    """
    return _diagnostico(racha, desconocidos, fallo)


def _sin_respuesta(racha: int, desconocidos: int, fallo: Fallo) -> str:
    """Por qué se abortó por tiempo: la misma atribución que `_sin_fuente`,
    con una frase propia delante que dice cómo se llegó — por segundos, no
    por conteo.
    """
    # No dice «en una sola petición», que sería falso por construcción: el
    # reloj arranca en el primer fallo contado con delta 0, así que el tope no
    # puede saltar antes del segundo. El tramo cubre siempre dos peticiones o
    # más, y puede cubrir cientos de lecturas de caché entre medias, porque los
    # aciertos de caché no tocan el reloj.
    return (
        f"Pasaron {SIN_RESPUESTA_MAXIMO:.0f} segundos sin que ningún intento "
        "tuviera éxito. " + _diagnostico(racha, desconocidos, fallo)
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
        # abortan una corrida sana, y «seguidos» se cuenta entre los que tocan la
        # red: con la caché caliente eso son sólo los que aún fallan, así que el
        # margen real es el número de empresas permanentemente rotas del universo,
        # no su tamaño. Ver el comentario de RACHA_MAXIMA, que lo trae medido.
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
    a medio poblar apagaría los dos cortacircuitos de `load_facts` -- el de
    racha y el de tiempo, que comparten el mismo reinicio.
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
    nada.

    Hay dos topes, no uno, porque «no hay fuente» tiene dos formas. Una racha
    de `RACHA_MAXIMA` fallos seguidos cubre la SEC que contesta rápido y mal
    -- rechazos, 5xx. Un tope de `SIN_RESPUESTA_MAXIMO` segundos sin ningún
    éxito cubre la SEC que no contesta y por tanto no falla rápido: con un
    read timeout de 30 s y los 5 intentos de stamina de edgartools, un solo
    ticker colgado cuesta minutos, y la racha sola tardaría demasiado en
    notarlo. Los dos comparten diagnóstico (`_diagnostico`) y el mismo
    reinicio: se reinician cuando la SEC entrega datos —un acierto de red o
    un 404, que también exigió preguntar—, avanzan cuando preguntamos y no los
    entregó, y no se tocan cuando no llegamos a preguntar: un acierto de caché
    o un CIK que resuelve contra el parquet local.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    cobertura = CoverageReport(requested=list(tickers))
    hechos: dict[str, pd.DataFrame] = {}
    racha = desconocidos = 0
    sin_respuesta_desde: float | None = None

    for ticker in tickers:
        intento = _load_one(ticker, cache_dir, refresh)

        if intento.fallo is None:
            hechos[ticker] = (
                intento.facts if intento.facts is not None else pd.DataFrame()
            )
            cobertura.included.append(ticker)
            if not intento.desde_cache:
                racha = desconocidos = 0
                sin_respuesta_desde = None
            continue

        fallo = intento.fallo
        _anotar(cobertura, ticker, fallo)

        if fallo.aborta:
            raise CorridaAbortada(fallo.causa, fallo.explicacion, cobertura)
        if fallo.fuente_viva:
            racha = desconocidos = 0
            sin_respuesta_desde = None
            continue
        if not fallo.cuenta_racha:
            continue

        racha += 1
        if fallo.causa == UNKNOWN:
            desconocidos += 1
        ahora = time.monotonic()
        if sin_respuesta_desde is None:
            sin_respuesta_desde = ahora
        if racha >= RACHA_MAXIMA:
            raise CorridaAbortada(
                fallo.causa, _sin_fuente(racha, desconocidos, fallo), cobertura
            )
        if (
            racha >= SIN_RESPUESTA_RACHA_MINIMA
            and ahora - sin_respuesta_desde >= SIN_RESPUESTA_MAXIMO
        ):
            raise CorridaAbortada(
                fallo.causa, _sin_respuesta(racha, desconocidos, fallo), cobertura
            )

    return hechos, cobertura
