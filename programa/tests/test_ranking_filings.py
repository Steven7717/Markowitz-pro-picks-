import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ranking.filings import Riesgos, cargar_riesgos

CRUDO = {
    "formulario": "10-K",
    "fecha": "2025-10-31",
    "accession": "0000320193-25-000079",
    # Guion largo, no ASCII: en cp1252 y en utf-8 no ocupa los mismos bytes.
    # Con "A" * 500 (puro ASCII) las dos codificaciones coinciden y la
    # restricción de encoding="utf-8" en ranking.filings queda sin defensor.
    "texto": "—" * 500,
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
    assert riesgos.texto == "—" * 500
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
    # Riesgos es un dataclass frozen: comparar por igualdad cubre los ocho
    # campos, no sólo accession.
    assert segunda == primera


def test_el_tope_se_aplica_sobre_la_cache_sin_redescargar(cache):
    """La caché guarda el texto COMPLETO; el recorte ocurre al leer.

    La primera llamada usa el tope MÁS BAJO a propósito: así, si el recorte se
    aplicara antes de escribir a disco, el resto del filing se perdería para
    siempre y una llamada posterior con un tope más alto no lo recuperaría sin
    una descarga nueva.
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
    """Una ausencia de hoy puede dejar de serlo mañana (la empresa presenta su
    10-K), así que no se cachea: se reintenta la descarga en cada corrida,
    igual que fundamentals/fetch.py:_load_one hace con unresolved_cik, no_facts
    y failed_download.
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


def test_cache_con_esquema_viejo_se_trata_como_fallo_y_se_vuelve_a_descargar(cache):
    # JSON válido pero sin la clave "texto" (p.ej. un esquema de una versión
    # anterior de este módulo). Sin validar la forma, esto pasaría _leer_cache
    # y reventaría más abajo con KeyError en vez de tratarse como caché rota.
    cache.mkdir(parents=True)
    fichero = cache / "AAPL.json"
    fichero.write_text(
        json.dumps({"formulario": "10-K", "fecha": "2025-10-31"}),
        encoding="utf-8",
    )

    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        riesgos = cargar_riesgos("AAPL", cache_dir=cache)
    assert descarga.call_count == 1
    assert riesgos.accession == "0000320193-25-000079"
