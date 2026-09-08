# noticias/fuentes.py
"""Lo unico que toca la red, aislado para que el resto no la necesite.

Cada descarga devuelve `Traida`, con los datos y **el problema como texto**. No
lanza: si una fuente cae, la pantalla pinta las otras y dice cual fallo. Que se
caiga la pantalla entera por una de tres es peor que ensenar dos.
"""

import os
from dataclasses import dataclass
from datetime import date, timedelta

from noticias import agenda as agenda_mod
from noticias import hechos as hechos_mod
from noticias import prensa as prensa_mod

# Un ano y medio de expedientes: suficiente para ver el patron de una empresa
# sin traerse una decada que nadie va a leer.
VENTANA = timedelta(days=550)


@dataclass(frozen=True)
class Traida:
    datos: tuple
    problema: str


def _descargar_prensa(ticker: str) -> list:
    import yfinance as yf

    return yf.Ticker(ticker).news or []


def _descargar_hechos(ticker: str) -> tuple:
    """The filing index AND the cik, because the index does not carry it.

    Las columnas de `to_pandas()` se comprobaron una a una: accession_number,
    filing_date, reportDate, acceptanceDateTime, act, form, fileNumber, items,
    size, isXBRL, isInlineXBRL, primaryDocument, primaryDocDescription. **No hay
    cik.** Sacarlo de ahi daria 0, y las urls de los expedientes apuntarian a
    `/data/0/` sin que nada lo delate: el texto del enlace se ve bien.
    """
    import edgar

    hasta = date.today()
    empresa = edgar.Company(ticker)
    indice = empresa.get_filings(
        form="8-K",
        filing_date=(str(hasta - VENTANA), str(hasta)),
    ).to_pandas()
    return indice, int(empresa.cik)


def _descargar_agenda(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).calendar or {}


def prensa_de(ticker: str) -> Traida:
    try:
        crudos = _descargar_prensa(ticker)
    except Exception as e:  # la red falla de mil formas y ninguna es del programa
        return Traida((), f"{ticker}: {e}")
    # Una lista vacia NO es un fallo: "sin noticias recientes" y "la fuente
    # cayo" le dicen al usuario cosas distintas.
    return Traida(prensa_mod.normalizar(ticker, crudos), "")


def hechos_de(ticker: str) -> Traida:
    if not os.environ.get("EDGAR_IDENTITY"):
        return Traida(
            (),
            "Falta EDGAR_IDENTITY. La SEC exige un contacto en el User-Agent: "
            "EDGAR_IDENTITY='tu@correo.com'. La prensa y el calendario "
            "funcionan igual sin ella.",
        )
    try:
        indice, cik = _descargar_hechos(ticker)
    except Exception as e:
        return Traida((), f"{ticker}: {e}")
    return Traida(hechos_mod.desde_indice(ticker, cik, indice), "")


def agenda_de(ticker: str) -> Traida:
    try:
        crudo = _descargar_agenda(ticker)
    except Exception as e:
        return Traida((), f"{ticker}: {e}")
    return Traida(agenda_mod.desde_calendario(ticker, crudo, date.today()), "")
