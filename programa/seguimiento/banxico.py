"""El tipo de cambio FIX y el INPC, del SIE de Banxico.

Solo descarga y guarda. Las cuentas estan en `seguimiento/fisher.py`, que no
sabe que existe una red.

El token viaja en la cabecera `Bmx-Token` y **nunca en la URL**. La API admite
las dos formas, pero una URL acaba en logs, en trazas de error y en el
historial de cualquier proxy.

La cache no es opcional: Banxico inhabilita por un tiempo el token que pasa de
su limite de consultas, y Streamlit vuelve a ejecutar la pagina con cada clic.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from noticias import cache

SERIE_FIX = "SF43718"
SERIE_INPC = "SP1"
URL = (
    "https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
    "{serie}/datos/{desde}/{hasta}"
)
RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
_FUENTE = "banxico"
_ESPERA_SEGUNDOS = 15
# Para que `cache.leer` devuelva lo guardado tenga la edad que tenga. Si esta
# vigente o no lo decide `caduca`, que para el INPC no es un plazo fijo.
_CUALQUIER_EDAD = timedelta(days=36_500)


@dataclass(frozen=True)
class Serie:
    """Lo que vino de Banxico, o por que no vino nada.

    `motivo` es `"ok"`, `"sin_token"`, `"token_invalido"`, `"sin_red"` o
    `"respuesta_rara"`. Con `vieja=True` los datos son de una descarga anterior
    que ya caduco, usada porque la de ahora fallo.
    """

    datos: "pd.Series | None"
    motivo: str
    descargada: "datetime | None" = None
    vieja: bool = False


def token() -> "str | None":
    """El token vigente, del entorno, que es donde lo deja `credenciales.aplicar`."""
    valor = (os.environ.get("BANXICO_TOKEN") or "").strip()
    return valor or None


def parsear(crudo: dict) -> pd.Series:
    """La serie de una respuesta del SIE, por fecha.

    Las fechas vienen como `dd/mm/aaaa` y los valores como texto con comas de
    miles. `"N/E"` es «sin dato» y se descarta: convertirlo en cero seria
    afirmar un tipo de cambio de cero pesos. Si Banxico repite una fecha se
    queda la ultima: es la misma regla que usaria una relectura del fichero.
    """
    puntos = crudo["bmx"]["series"][0].get("datos") or []
    fechas, valores = [], []
    for punto in puntos:
        try:
            numero = float(str(punto["dato"]).replace(",", "").strip())
        except ValueError:
            continue
        fechas.append(datetime.strptime(punto["fecha"], "%d/%m/%Y"))
        valores.append(numero)
    serie = pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float).sort_index()
    return serie[~serie.index.duplicated(keep="last")]


def caduca(serie: str, datos: pd.Series, cuando: datetime) -> datetime:
    """Hasta cuando vale lo descargado.

    El FIX cambia cada dia habil, asi que vale un dia. El INPC mensual sale
    hacia el dia 9 del mes siguiente, asi que el de agosto no tiene sucesor
    hasta el 9 de octubre: vale hasta el 10.
    """
    if serie == SERIE_INPC and len(datos):
        ultimo = datos.index[-1]
        # Meses contados desde el año 0, dos por delante del ultimo dato: agosto
        # da octubre, diciembre da febrero del año siguiente.
        meses = ultimo.year * 12 + (ultimo.month - 1) + 2
        return datetime(meses // 12, meses % 12 + 1, 10, tzinfo=timezone.utc)
    return cuando + timedelta(days=1)


def _a_plano(serie: pd.Series) -> dict:
    return {d.date().isoformat(): float(v) for d, v in serie.items()}


def _de_plano(plano) -> pd.Series:
    if not isinstance(plano, dict):
        raise TypeError("cache de Banxico sin forma de serie")
    serie = pd.Series(
        {pd.Timestamp(k): float(v) for k, v in plano.items()}, dtype=float
    )
    return serie.sort_index()


def _pedir(serie, desde: date, hasta: date, clave: str, abrir) -> dict:
    url = URL.format(serie=serie, desde=desde.isoformat(), hasta=hasta.isoformat())
    peticion = urllib.request.Request(
        url, headers={"Bmx-Token": clave, "Accept": "application/json"}
    )
    with abrir(peticion, timeout=_ESPERA_SEGUNDOS) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def traer(
    serie: str,
    desde: date,
    hasta: date,
    clave: "str | None",
    *,
    raiz: Path = RAIZ_CACHE,
    abrir=None,
    ahora: "datetime | None" = None,
) -> Serie:
    """Una serie de Banxico, de la cache si vale y de la red si no.

    La clave de la cache es la serie y `desde`. `hasta` es siempre hoy, y
    meterlo en la clave haria que ninguna cache sobreviviera a un cambio de dia.
    """
    if not clave:
        return Serie(None, "sin_token")
    abrir = abrir or urllib.request.urlopen
    ahora = ahora or datetime.now(timezone.utc)
    llave = f"{serie}_{desde.isoformat()}"

    guardado = cache.leer(raiz, _FUENTE, llave, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None:
        try:
            previo = _de_plano(guardado.datos)
        except (TypeError, ValueError):
            previo = None
    if previo is not None and ahora < caduca(serie, previo, guardado.cuando):
        return Serie(previo, "ok", guardado.cuando)

    try:
        datos = parsear(_pedir(serie, desde, hasta, clave, abrir))
    except urllib.error.HTTPError as error:
        # Antes que URLError, que es su clase madre.
        if error.code in (401, 403):
            motivo = "token_invalido"
        elif error.code == 429 or error.code >= 500:
            motivo = "sin_red"
        else:
            motivo = "respuesta_rara"
    except (urllib.error.URLError, TimeoutError, OSError):
        motivo = "sin_red"
    except (ValueError, KeyError, IndexError, TypeError):
        motivo = "respuesta_rara"
    else:
        cache.guardar(raiz, _FUENTE, llave, _a_plano(datos))
        return Serie(datos, "ok", ahora)

    if previo is not None:
        return Serie(previo, "ok", guardado.cuando, vieja=True)
    return Serie(None, motivo)
