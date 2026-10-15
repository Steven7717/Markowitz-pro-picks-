"""Qué es cada ticker y de dónde salen sus números.

**La forma del ticker es una trampa en dos sitios.**
`research.universe.normalise_ticker` cambia todo punto por guion
(`BRK.B` → `BRK-B`), que es como Yahoo escribe las clases de acción, y con eso
`WALMEX.MX` acaba en `WALMEX-MX`, que Yahoo no conoce. `aprobacion.acta`
rechaza cualquier punto. Aquí el punto se distingue por lo que lleva detrás: si
es un sufijo de bolsa de Yahoo se conserva, y si no, es de clase de acción y
pasa a guion. Las dos funciones existentes no se tocan: sirven al universo del
S&P 500 y al acta, y ahí están bien.
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from noticias import cache
from ranking.criterio import TAMANO_TOP
from valoracion import mercado

# Privadas y aun así importadas: son la lectura de `info` que `mercado` ya
# hace para el perfil. Una segunda copia aquí es como empiezan a separarse.
from valoracion.mercado import _hora, _num, _texto

# Los sufijos de bolsa de Yahoo que se reconocen. Tabla cerrada a propósito: con
# un sufijo que no esté, el punto se lee como de clase de acción y el ticker
# sale con guion, que Yahoo no conocerá y la fila lo dirá. Lo contrario --tomar
# por bolsa cualquier cosa detrás de un punto-- convertiría `BF.B` en una bolsa
# llamada «B», y ese error no da ningún aviso.
# El precio de cerrarla: un sufijo puede coincidir con la letra de una clase.
# `V` es TSX Venture y también la clase con voto de McCormick, del S&P 500, así
# que `MKC.V` se lee como bolsa y Yahoo no lo encuentra. Escrito con guion,
# `MKC-V`, funciona siempre, porque el guion no se toca.
SUFIJOS_DE_BOLSA = frozenset(
    {
        "MX",  # Bolsa Mexicana de Valores
        "TO", "V", "NE", "CN",  # Toronto, TSX Venture, NEO, CSE
        "L", "IL",  # Londres
        "DE", "F", "BE", "DU", "HM", "HA", "MU", "SG",  # Xetra, Fráncfort y regionales
        "PA", "AS", "BR", "LS", "MI", "MC", "SW", "VI",
        "ST", "HE", "CO", "OL", "IR", "WA", "PR", "AT",
        "HK", "T", "SS", "SZ", "KS", "KQ", "TW", "TWO",
        "SI", "KL", "BK", "JK", "AX", "NZ",
        "SA", "BA", "SN", "JO", "TA", "IS", "NS", "BO",
    }
)

# Cada ticker cuesta varias consultas de red, y el tope es el tamaño del top de
# candidatos: lo que el usuario ya está acostumbrado a revisar de una vez.
MAX_TICKERS = TAMANO_TOP

_LARGO_MAXIMO = 20
# Letras y dígitos, separados por un punto, un guion, un igual o un `&` (así
# escribe Yahoo la Ñ de Peñoles, `PE&OLES.MX`, y también sale en `M&M.NS`), y un
# `^` delante para los índices. Sin separadores seguidos ni en los extremos:
# `A..B` o `WALMEX.` no son tickers mal escritos que se puedan arreglar, son
# otra cosa.
_FORMA = re.compile(r"^\^?[A-Z0-9]+(?:[.\-=&][A-Z0-9]+)*$")
_SEPARADORES = re.compile(r"[,\s]+")
# Lo que se pega de una web o de Excel trae caracteres de formato que en
# pantalla no se ven, y harían inválido un ticker que se lee bien. NFKC no los
# quita, así que se borran aparte. Se borra la categoría entera (`Cf`) y no una
# lista: además de los de anchura cero y la marca de orden de bytes, caen las
# marcas de dirección (U+200E, U+200F) que se cuelan al copiar de algunas webs,
# el unidor de palabras (U+2060) y el guion blando (U+00AD); una lista se
# queda corta con el siguiente. Ninguno puede formar parte de un ticker.
_FORMATO = "Cf"


def _limpiar(texto: str) -> str:
    """El texto como se ve: NFKC lleva el ancho completo (`ＭＵ，`) a `MU,`."""
    normal = unicodedata.normalize("NFKC", texto)
    return "".join(c for c in normal if unicodedata.category(c) != _FORMATO)


def tiene_sufijo(ticker: str) -> bool:
    """Si lo que va detrás del último punto es una bolsa de la tabla.

    Espera el ticker ya normalizado, en mayúsculas: la tabla no conoce `mx`.
    """
    _, punto, sufijo = ticker.rpartition(".")
    return bool(punto) and sufijo in SUFIJOS_DE_BOLSA


def normalizar(texto: object) -> "str | None":
    """El ticker como lo escribe Yahoo, o `None` si no tiene forma de ticker."""
    if not isinstance(texto, str):
        return None
    limpio = _limpiar(texto).strip().upper()
    if len(limpio) > _LARGO_MAXIMO or not _FORMA.match(limpio):
        return None
    if tiene_sufijo(limpio):
        base, _, sufijo = limpio.rpartition(".")
        return f"{base.replace('.', '-')}.{sufijo}"
    return limpio.replace(".", "-")


def separar(texto: "str | None") -> "tuple[list[str], list[str]]":
    """Los tickers de un campo de texto, separados por comas o espacios.

    Devuelve `(validos, invalidos)`: los válidos normalizados y sin repetir, en
    el orden en que se escribieron; los inválidos tal como se escribieron, ya
    limpios de lo que no se vería, y sin repetir, para poder decir cuáles. El
    tope de `MAX_TICKERS` lo aplica quien llama, que es quien sabe decirlo en
    pantalla.

    La limpieza va antes de partir, porque la coma de ancho completo sólo
    separa después de NFKC.
    """
    validos: list[str] = []
    invalidos: list[str] = []
    for trozo in _SEPARADORES.split(_limpiar(texto or "")):
        if not trozo:
            continue
        ticker = normalizar(trozo)
        if ticker is None:
            if trozo not in invalidos:
                invalidos.append(trozo)
        elif ticker not in validos:
            validos.append(ticker)
    return validos, invalidos


# --- La clase de cada ticker -----------------------------------------------------
#
# | Clase            | Presenta          | Números                     |
# |------------------|-------------------|-----------------------------|
# | `sec`            | 10-K              | EDGAR, como los candidatos  |
# | `extranjera_sec` | 20-F o 40-F       | yfinance                    |
# | `sin_sec`        | nada en EDGAR     | yfinance                    |
# | `etf`            | —                 | ninguno: no se valora       |
#
# Los motivos de un ticker sin clase son claves, no textos: `sin_red` (Yahoo no
# devolvió nada), `tipo_no_soportado` (un índice, un fondo, una divisa o una
# cripto), `sin_red_edgar` y `sin_identidad_edgar`. Las etiquetas las pone N2.

RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
# Qué informes anuales presenta una empresa no cambia en meses.
VALIDEZ_FORMULARIOS = timedelta(days=30)
# Para que `cache.leer` devuelva lo guardado tenga la edad que tenga: sin red,
# un formulario de hace meses sigue diciendo la verdad.
_CUALQUIER_EDAD = timedelta(days=36_500)
FORMULARIOS_ANUALES = ("10-K", "20-F", "40-F")
_EXTRANJEROS = ("20-F", "40-F")


@dataclass(frozen=True)
class Identidad:
    """Qué es un ticker según Yahoo. Precio y hora, para enseñarlos; nada de beta."""

    ticker: str
    tipo: "str | None"
    nombre: "str | None"
    bolsa: "str | None"
    moneda: "str | None"
    moneda_estados: "str | None"
    sector: "str | None"
    industria: "str | None"
    pais: "str | None"
    precio: "float | None"
    hora: "str | None"


@dataclass(frozen=True)
class Resuelto:
    """La clase de un ticker, o por qué no tiene. `motivo` es None si hay clase."""

    ticker: str
    clase: "str | None"
    identidad: "Identidad | None"
    motivo: "str | None"


def identidad_desde_info(ticker: str, info: dict) -> Identidad:
    precio = _num(info.get("currentPrice"))
    if not precio > 0:
        precio = _num(info.get("regularMarketPrice"))
    moneda = _texto(info.get("currency"))
    return Identidad(
        ticker=ticker,
        tipo=_texto(info.get("quoteType")),
        nombre=_texto(info.get("longName")) or _texto(info.get("shortName")),
        bolsa=_texto(info.get("exchange")),
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        sector=_texto(info.get("sector")),
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        precio=precio if precio > 0 else None,
        hora=_hora(info.get("regularMarketTime")),
    )


def clase_de(
    identidad: Identidad, formularios: "tuple[str, ...]"
) -> "tuple[str | None, str | None]":
    """`(clase, None)`, o `(None, motivo)` si el ticker no es una acción ni un ETF."""
    if identidad.tipo == "ETF":
        return "etf", None
    if identidad.tipo != "EQUITY":
        return None, "tipo_no_soportado"
    if "10-K" in formularios:
        return "sec", None
    if any(f in formularios for f in _EXTRANJEROS):
        return "extranjera_sec", None
    return "sin_sec", None


def _consultar_sec(ticker: str) -> "tuple[str, ...] | None":
    """Qué informes anuales presenta el ticker en EDGAR.

    `()` si EDGAR no conoce el ticker, que es un hecho y se guarda; `None` si no
    se pudo saber. Aislada para los tests. Sólo las llamadas a edgartools van
    dentro del `try`, para que un defecto propio no se disfrace de «sin red».
    """
    from edgar import Company
    from edgar.exceptions import NotFoundError

    try:
        empresa = Company(ticker)
        presentados = tuple(
            forma for forma in FORMULARIOS_ANUALES if len(empresa.get_filings(form=forma)) > 0
        )
    except NotFoundError:
        return ()
    except Exception:
        # edgartools lanza de todo según qué falle --transporte, identidad
        # rechazada, una respuesta a medias-- y aquí sólo importa que no se supo.
        return None
    return presentados


def formularios_sec(ticker: str) -> "tuple[tuple[str, ...] | None, str]":
    """Los informes anuales del ticker en EDGAR, de la caché si vale y si no de la red."""
    if not (os.environ.get("EDGAR_IDENTITY") or "").strip():
        # La SEC rechaza las peticiones sin contacto, y el rechazo llega como un
        # fallo de red: mejor decir qué falta.
        return None, "sin_identidad_edgar"
    guardado = cache.leer(RAIZ_CACHE, "formularios", ticker, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None and isinstance(guardado.datos, list):
        previo = tuple(guardado.datos)
        if guardado.cuando + VALIDEZ_FORMULARIOS > datetime.now(timezone.utc):
            return previo, "ok"
    encontrados = _consultar_sec(ticker)
    if encontrados is None:
        return (previo, "ok") if previo is not None else (None, "sin_red_edgar")
    try:
        cache.guardar(RAIZ_CACHE, "formularios", ticker, list(encontrados))
    except OSError:
        pass
    return encontrados, "ok"


def resolver(ticker: str) -> Resuelto:
    """Qué es un ticker ya normalizado: su identidad de Yahoo y su clase."""
    crudo, motivo = mercado.identidad(ticker)
    if crudo is None:
        return Resuelto(ticker, None, None, motivo)
    identidad = identidad_desde_info(ticker, crudo)
    if identidad.tipo == "EQUITY" and not tiene_sufijo(ticker):
        formularios, motivo = formularios_sec(ticker)
        if formularios is None:
            return Resuelto(ticker, None, identidad, motivo)
    else:
        # Un ETF, un tipo no soportado o una emisora con sufijo de bolsa: la
        # clase no depende de EDGAR, y preguntar costaría un segundo por ticker.
        formularios = ()
    clase, motivo = clase_de(identidad, formularios)
    return Resuelto(ticker, clase, identidad, motivo)
