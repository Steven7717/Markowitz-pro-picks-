# macro/fuentes.py
"""El CLI de la OCDE y tres series de FRED. Solo descarga y guarda.

Las dos son gratis y sin clave. La caché no es opcional: Streamlit vuelve a
ejecutar la página con cada clic, y la OCDE limita las consultas por minuto.

Un fallo es un resultado con nombre, no una excepción, como en
`seguimiento/banxico.py`. Si la red cae y hay algo guardado, se devuelve lo
guardado marcado `vieja=True`: un dato viejo con su fecha a la vista sirve, uno
que se lee como fresco sin serlo no.
"""

import http.client
import io
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from macro.criterio import REGIONES
from noticias import cache

URL_CLI = (
    "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/"
    "{area}.M.LI...AA...H?startPeriod={desde}"
    "&dimensionAtObservation=AllDimensions&format=csvfile"
)
URL_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}"
RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
VALIDEZ = timedelta(hours=24)
ANOS_HISTORIA = 6
_ESPERA_SEGUNDOS = 20
_CUALQUIER_EDAD = timedelta(days=36_500)


@dataclass(frozen=True)
class Serie:
    """`motivo`: ok | sin_red | serie_desconocida | respuesta_ilegible."""

    datos: "pd.Series | None"
    motivo: str
    descargada: "datetime | None" = None
    vieja: bool = False


class _Vacia(ValueError):
    pass


def parsear_cli(texto: str) -> pd.Series:
    marco = pd.read_csv(io.StringIO(texto))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(marco.columns):
        raise ValueError("el CSV de la OCDE no trae TIME_PERIOD/OBS_VALUE")
    marco = marco.dropna(subset=["OBS_VALUE"])
    if marco.empty:
        raise _Vacia()
    indice = pd.PeriodIndex(marco["TIME_PERIOD"].astype(str), freq="M").to_timestamp()
    serie = pd.Series(marco["OBS_VALUE"].astype(float).to_numpy(), index=indice)
    return serie.sort_index()


def parsear_fred(texto: str, serie_id: str) -> pd.Series:
    marco = pd.read_csv(io.StringIO(texto))
    if serie_id not in marco.columns or "observation_date" not in marco.columns:
        raise ValueError(f"el CSV de FRED no trae {serie_id}")
    valores = pd.to_numeric(marco[serie_id], errors="coerce")
    serie = pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(marco["observation_date"]))
    serie = serie.dropna().sort_index()
    if serie.empty:
        raise _Vacia()
    return serie


def _a_plano(serie: pd.Series) -> dict:
    return {d.date().isoformat(): float(v) for d, v in serie.items()}


def _de_plano(plano) -> pd.Series:
    if not isinstance(plano, dict):
        raise TypeError("caché sin forma de serie")
    indice = pd.DatetimeIndex([pd.Timestamp(k) for k in plano])
    return pd.Series([float(v) for v in plano.values()], index=indice, dtype=float).sort_index()


def _traer(url: str, llave: str, parsear, *, raiz: Path, abrir, ahora, agente=None) -> Serie:
    """`agente`: User-Agent propio o None para el de urllib. Las dos fuentes lo
    exigen opuesto: la OCDE (Cloudflare) rechaza con 403 el de urllib y FRED deja
    colgada, sin responder, la petición con uno que no reconoce."""
    abrir = abrir or urllib.request.urlopen
    ahora = ahora or datetime.now(timezone.utc)

    guardado = cache.leer(raiz, "macro", llave, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None:
        try:
            previo = _de_plano(guardado.datos)
        except (TypeError, ValueError):
            previo = None
    if previo is not None and ahora - guardado.cuando <= VALIDEZ:
        return Serie(previo, "ok", guardado.cuando)

    try:
        cabeceras = {"User-Agent": agente} if agente else {}
        peticion = urllib.request.Request(url, headers=cabeceras)
        with abrir(peticion, timeout=_ESPERA_SEGUNDOS) as respuesta:
            datos = parsear(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        motivo = "serie_desconocida" if error.code == 404 else "sin_red"
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        motivo = "sin_red"
    except _Vacia:
        motivo = "serie_desconocida"
    except (ValueError, KeyError, TypeError, pd.errors.ParserError):
        motivo = "respuesta_ilegible"
    else:
        try:
            cache.guardar(raiz, "macro", llave, _a_plano(datos))
        except OSError:
            pass
        return Serie(datos, "ok", ahora)

    if previo is not None:
        return Serie(previo, "ok", guardado.cuando, vieja=True)
    return Serie(None, motivo)


def traer_cli(region: str, *, raiz: Path = RAIZ_CACHE, abrir=None, ahora=None) -> Serie:
    """El CLI de una región. `KeyError` si la región no existe: es un defecto, no un fallo de red."""
    area = REGIONES[region]
    hoy = (ahora or datetime.now(timezone.utc)).date()
    desde = f"{hoy.year - ANOS_HISTORIA}-01"
    url = URL_CLI.format(area=area, desde=desde)
    return _traer(url, f"cli_{area}", parsear_cli, raiz=raiz, abrir=abrir, ahora=ahora,
                  agente="markowitz-pro-picks")


def traer_fred(serie_id: str, *, raiz: Path = RAIZ_CACHE, abrir=None, ahora=None) -> Serie:
    url = URL_FRED.format(serie=serie_id)
    return _traer(
        url, f"fred_{serie_id}", lambda t: parsear_fred(t, serie_id),
        raiz=raiz, abrir=abrir, ahora=ahora,
    )
