# noticias/prensa.py
"""La prensa que Yahoo asocia a cada activo, normalizada y sin juzgar.

H no filtra la prensa: no hay criterio defendible para decidir que titular
importa, y fingir uno seria peor que no tenerlo. Lo que si hace es ensenar el
medio y si es texto o video, que es lo que permite descartar de un vistazo.
Hace falta: en el sondeo, la primera "noticia" de MSFT era un video sobre los
resultados de Oracle.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Noticia:
    ticker: str
    titular: str
    resumen: str
    medio: str
    url: str
    cuando: datetime
    clase: str


def desde_crudo(ticker: str, crudo: dict) -> "Noticia | None":
    """One yfinance news item, or None when there is nothing to show.

    `provider` y `canonicalUrl` son **diccionarios**, no cadenas: tratarlos como
    cadenas da un medio ilegible y una url rota, y ninguna de las dos cosas
    lanza excepcion.
    """
    contenido = crudo.get("content") or {}
    titular = (contenido.get("title") or "").strip()
    if not titular:
        return None

    publicado = contenido.get("pubDate")
    if not publicado:
        return None
    try:
        cuando = datetime.fromisoformat(publicado.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None

    proveedor = contenido.get("provider") or {}
    enlace = contenido.get("canonicalUrl") or {}

    return Noticia(
        ticker=ticker,
        titular=titular,
        # **Solo `summary`.** `description` trae el mismo texto en HTML crudo,
        # y volcarlo pintaria etiquetas en la pantalla. Sin resumen se ensena
        # el titular solo, que ya dice algo.
        resumen=(contenido.get("summary") or "").strip(),
        medio=(proveedor.get("displayName") or "").strip(),
        url=(enlace.get("url") or "").strip(),
        # De `pubDate` y no de `displayTime`, que en el sondeo venia vacia.
        cuando=cuando,
        clase=(contenido.get("contentType") or "ARTICLE").strip(),
    )


def normalizar(ticker: str, crudos: list) -> "tuple[Noticia, ...]":
    """De la mas nueva a la mas vieja, sin los elementos que no dicen nada."""
    salida = [n for n in (desde_crudo(ticker, c) for c in crudos) if n]
    salida.sort(key=lambda n: n.cuando, reverse=True)
    return tuple(salida)
