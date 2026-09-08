from datetime import date

import pandas as pd
import pytest

from noticias import fuentes


def test_sin_edgar_identity_los_hechos_dicen_que_falta(monkeypatch):
    """Mismo patron que el ranking sin ANTHROPIC_API_KEY: se explica y sigue."""
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)
    resultado = fuentes.hechos_de("AAPL")
    assert resultado.datos == ()
    assert "EDGAR_IDENTITY" in resultado.problema


def test_un_fallo_de_red_se_nombra_y_no_se_propaga(monkeypatch):
    def revienta(*a, **k):
        raise ConnectionError("sin ruta al host")

    monkeypatch.setattr(fuentes, "_descargar_prensa", revienta)
    resultado = fuentes.prensa_de("AAPL")
    assert resultado.datos == ()
    assert "sin ruta al host" in resultado.problema


def test_una_lista_vacia_no_es_un_fallo(monkeypatch):
    """'Sin noticias recientes' y 'la fuente cayo' no son lo mismo.

    El campo `problema` vacio es lo que las separa, y la pantalla pinta un
    aviso solo cuando trae texto.
    """
    monkeypatch.setattr(fuentes, "_descargar_prensa", lambda t: [])
    resultado = fuentes.prensa_de("AAPL")
    assert resultado.datos == ()
    assert resultado.problema == ""


def test_un_ticker_sin_cik_se_nombra(monkeypatch):
    def sin_cik(ticker):
        raise LookupError(f"{ticker} no resuelve a CIK")

    monkeypatch.setenv("EDGAR_IDENTITY", "x@y.com")
    monkeypatch.setattr(fuentes, "_descargar_hechos", sin_cik)
    resultado = fuentes.hechos_de("ZZZZ")
    assert "ZZZZ" in resultado.problema


def test_el_cik_llega_hasta_la_url(monkeypatch):
    """El CIK no viene en el indice, y sin el las urls apuntan a /data/0/.

    Nada lo delata mirando la pantalla: el texto del enlace se ve bien y solo
    falla al pulsarlo.
    """
    indice = pd.DataFrame(
        [{"form": "8-K", "filing_date": date(2026, 7, 30), "items": "2.02",
          "accession_number": "0000320193-26-000018",
          "primaryDocument": "aapl.htm"}]
    )
    monkeypatch.setenv("EDGAR_IDENTITY", "x@y.com")
    monkeypatch.setattr(fuentes, "_descargar_hechos", lambda t: (indice, 320193))
    resultado = fuentes.hechos_de("AAPL")
    assert "/data/320193/" in resultado.datos[0].url


@pytest.mark.red
def test_la_prensa_viva_sigue_teniendo_la_forma_del_sondeo():
    """Un fixture protege de que cambies tu; solo esto, de que cambie Yahoo."""
    crudos = fuentes._descargar_prensa("AAPL")
    assert crudos, "yfinance no devolvio noticias"
    c = crudos[0]["content"]
    assert isinstance(c["provider"], dict)
    assert isinstance(c["canonicalUrl"], dict)
    assert "pubDate" in c


@pytest.mark.red
def test_el_indice_vivo_de_la_sec_sigue_trayendo_items():
    """Si la SEC dejase de servir `items`, todo el criterio se queda mudo.

    Y si dejara de servirlos **sin fallar** -- columna ausente en vez de error
    --, `partir(None)` daria `()` y todos los expedientes saldrian plegados y
    sin descripcion. Verde y vacio, que es la peor forma de romperse.
    """
    indice, cik = fuentes._descargar_hechos("AAPL")
    assert "items" in indice.columns
    assert cik == 320193, "el CIK de Apple no sale de la Company"
