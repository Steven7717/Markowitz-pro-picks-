from pathlib import Path
from unittest.mock import patch

import pytest

from ranking.filings import Riesgos, cargar_riesgos

CRUDO = {
    "formulario": "10-K",
    "fecha": "2025-10-31",
    "accession": "0000320193-25-000079",
    "texto": "A" * 500,
}


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "riesgos"


def test_devuelve_la_seccion_con_su_procedencia(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO):
        riesgos = cargar_riesgos("AAPL", cache_dir=cache)
    assert isinstance(riesgos, Riesgos)
    # La cita sólo es trazable si estos cuatro campos de procedencia viajan
    # completos: sin ellos no hay forma de localizar el texto en el filing
    # original. El test original sólo comprobaba accession y seccion.
    assert riesgos.ticker == "AAPL"
    assert riesgos.formulario == "10-K"
    assert riesgos.fecha == "2025-10-31"
    assert riesgos.accession == "0000320193-25-000079"
    assert riesgos.seccion == "Item 1A"
    assert riesgos.texto == "A" * 500
    assert riesgos.caracteres_totales == 500
    assert riesgos.recortado is False


def test_recorta_al_tope_y_lo_registra(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO):
        riesgos = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=100)
    assert len(riesgos.texto) == 100
    assert riesgos.caracteres_totales == 500
    assert riesgos.recortado is True


def test_la_segunda_llamada_no_vuelve_a_descargar(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        primera = cargar_riesgos("AAPL", cache_dir=cache)
        segunda = cargar_riesgos("AAPL", cache_dir=cache)
    assert descarga.call_count == 1
    assert segunda.accession == primera.accession


def test_el_tope_se_aplica_sobre_la_cache_sin_redescargar(cache):
    """La caché guarda el texto COMPLETO; el recorte ocurre al leer.

    La versión rota que este test tiene que descartar es tan plausible como la
    correcta: recortar ANTES de escribir a disco
    (``crudo["texto"] = crudo["texto"][:max_caracteres]``). Con esa versión,
    escrita con un max_caracteres bajo, el resto del filing se pierde para
    siempre y ninguna llamada posterior con un tope más alto lo recupera sin
    una descarga nueva.

    Por eso el orden importa: la primera llamada usa el tope MÁS BAJO. El test
    original de este archivo hacía lo contrario (primero max_caracteres=500,
    que no recorta nada porque el texto de prueba mide exactamente 500
    caracteres, y luego 50) y por eso no distinguía las dos implementaciones:
    con un texto que ya cabía entero, cachear "500 caracteres recortados" y
    cachear "500 caracteres completos" produce el mismo fichero.
    """
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        recortada = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=100)
        completa = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=500)
        mas_recortada = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=50)
    assert descarga.call_count == 1
    assert len(recortada.texto) == 100
    assert len(completa.texto) == 500
    assert completa.recortado is False
    assert len(mas_recortada.texto) == 50


def test_sin_seccion_devuelve_none_y_no_lo_cachea(cache):
    """Un filing sin Item 1A extraíble no se cachea.

    Decisión de diseño: se prefiere reintentar la descarga en cada corrida
    antes que cachear el None, por dos motivos. Primero, una ausencia de hoy
    puede dejar de serlo mañana (la empresa presenta su 10-K, o edgartools
    corrige cómo extrae risk_factors) y una caché negativa la escondería hasta
    que alguien la borrase a mano. Segundo, es el mismo trato que
    fundamentals/fetch.py:_load_one ya da a sus dos fallos (unresolved_cik y
    failed_download): ninguno de los dos se escribe en caché, sólo los
    resultados con datos se persisten.
    """
    with patch("ranking.filings._descargar", return_value=None) as descarga:
        primera = cargar_riesgos("XYZ", cache_dir=cache)
        segunda = cargar_riesgos("XYZ", cache_dir=cache)
    assert primera is None
    assert segunda is None
    assert descarga.call_count == 2


def test_refresh_fuerza_la_descarga(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        cargar_riesgos("AAPL", cache_dir=cache)
        cargar_riesgos("AAPL", cache_dir=cache, refresh=True)
    assert descarga.call_count == 2


def test_cache_corrupta_se_trata_como_fallo_y_se_vuelve_a_descargar(cache):
    # Mismo trato que fundamentals/fetch.py:_load_one da a un parquet
    # truncado por una corrida abortada a mitad de escritura: un JSON que no
    # parsea es un fallo de caché, no un error fatal, y se redescarga.
    with patch("ranking.filings._descargar", return_value=CRUDO):
        cargar_riesgos("AAPL", cache_dir=cache)
    fichero = cache / "AAPL.json"
    fichero.write_text("{esto no es json valido", encoding="utf-8")

    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        riesgos = cargar_riesgos("AAPL", cache_dir=cache)
    assert descarga.call_count == 1
    assert riesgos.accession == "0000320193-25-000079"
