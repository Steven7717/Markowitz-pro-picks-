# noticias/hechos.py
"""Los 8-K del libro, desde el indice de la SEC y sin abrir ni uno.

**Los items vienen en el indice.** `EntityFilings.to_pandas()` trae una columna
`items` con los codigos, asi que basta una llamada por activo. Existe
`filing.obj().items`, pero descarga el documento entero de cada expediente, y
con quince activos eso convierte una pantalla en una espera.
"""

from dataclasses import dataclass
from datetime import date

from noticias import criterio


@dataclass(frozen=True)
class Hecho:
    ticker: str
    tipos: "tuple[str, ...]"
    descripciones: "tuple[str, ...]"
    url: str
    cuando: date
    enmienda: bool
    material: bool


def partir(items: "str | None") -> "tuple[str, ...]":
    """The SEC returns every item of a filing in one comma-separated string.

    **Aqui es donde se pierde todo si se hace mal.** "2.02,9.01" comparado
    entero contra la lista de materiales no coincide con nada, y cada anuncio
    de resultados -- el hecho mas frecuente que existe -- quedaria plegado
    entre la rutina, sin que nada lo delate.
    """
    if not items:
        return ()
    return tuple(t.strip() for t in str(items).split(",") if t.strip())


def _url(cik: int, accession: str, documento: str) -> str:
    """EDGAR guarda el documento bajo el numero de acceso sin guiones."""
    limpio = str(accession).replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{limpio}/{documento}"
    )


def desde_indice(ticker: str, cik: int, indice) -> "tuple[Hecho, ...]":
    """The filing index as it comes from edgartools, turned into Hechos.

    No se descarta ningun expediente: los materiales saldran destacados y el
    resto plegado, pero todos vuelven. Lo que H tirase, el sub-proyecto I no lo
    veria nunca.
    """
    if indice is None or len(indice) == 0:
        return ()

    salida = []
    for fila in indice.to_dict("records"):
        tipos = partir(fila.get("items"))
        salida.append(
            Hecho(
                ticker=ticker,
                tipos=tipos,
                descripciones=tuple(
                    criterio.DESCRIPCIONES.get(t, f"Tipo {t}") for t in tipos
                ),
                url=_url(
                    cik,
                    fila.get("accession_number", ""),
                    fila.get("primaryDocument", ""),
                ),
                cuando=fila.get("filing_date"),
                # get_filings(form="8-K") devuelve tambien los "8-K/A".
                enmienda=str(fila.get("form", "")).endswith("/A"),
                material=criterio.material(tipos),
            )
        )
    salida.sort(key=lambda h: h.cuando, reverse=True)
    return tuple(salida)
