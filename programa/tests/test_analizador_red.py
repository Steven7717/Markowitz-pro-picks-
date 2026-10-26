"""Contra yfinance, EDGAR y Banxico de verdad. Excluidos de la suite normal.

Comprueban que las fuentes siguen teniendo la forma que el código espera: las
clases de cuatro tickers reales, los nombres de fila de yfinance y el id de la
serie del Bono M por el título de sus metadatos. Las empresas de la SEC
necesitan `EDGAR_IDENTITY`, y el Bono M `BANXICO_TOKEN`; sin ellos se omiten.
"""

import json
import os
import urllib.request

import pytest

from analizador import divisas, resolver
from analizador.analisis import analizar
from analizador.lineas_yf import FILAS, lineas_de
from valoracion import mercado

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def caches_aisladas(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path / "mercado")
    monkeypatch.setattr(resolver, "RAIZ_CACHE", tmp_path / "resolver")


def _con_edgar():
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("Falta EDGAR_IDENTITY")


@pytest.mark.parametrize(
    "ticker, clase",
    [
        ("MU", "sec"),
        ("TSM", "extranjera_sec"),
        # RY presenta 40-F y edgartools la marca `is_foreign = False`.
        ("RY", "extranjera_sec"),
        ("WALMEX.MX", "sin_sec"),
        ("SPY", "etf"),
    ],
)
def test_las_cuatro_clases_con_casos_reales(ticker, clase):
    if clase in ("sec", "extranjera_sec"):
        _con_edgar()
    r = resolver.resolver(ticker)
    assert (r.clase, r.motivo) == (clase, None)


def test_un_indice_no_es_una_accion():
    assert resolver.resolver("^GSPC").motivo == "tipo_no_soportado"


@pytest.mark.parametrize("ticker", ["MU", "WALMEX.MX", "TSM"])
def test_las_filas_de_yfinance_siguen_llamandose_asi(ticker):
    estados, motivo = mercado.estados(ticker)
    assert motivo == "ok"
    _, anuales = lineas_de(estados)
    vacias = [linea for linea in FILAS if anuales[linea].isna().all()]
    assert vacias == []


def test_el_bono_m_es_la_serie_buena(tmp_path):
    clave = os.environ.get("BANXICO_TOKEN")
    if not clave:
        pytest.skip("sin BANXICO_TOKEN")
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{divisas.SERIE_BONO_M_10}"
    peticion = urllib.request.Request(url, headers={"Bmx-Token": clave, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=20) as respuesta:
        titulo = json.loads(respuesta.read().decode("utf-8"))["bmx"]["series"][0]["titulo"]
    normalizado = " ".join(titulo.split()).lower()
    assert "tasa de rendimiento" in normalizado
    assert "bono tasa fija 10 años" in normalizado
    valor, motivo, _ = divisas.bono_m(clave, raiz=tmp_path)
    # En tanto por uno: un 9 % es 0,09. Fuera de esto es la serie equivocada.
    assert motivo == "ok" and 0.02 < valor < 0.20


def test_walmex_de_punta_a_punta():
    a = analizar("WALMEX.MX", panel=None)
    assert (a.clase, a.sector) == ("sin_sec", "Consumer Staples")
    assert a.entradas.divisa.moneda_valoracion == "MXN"
    assert a.entradas.divisa.indice_beta == "^MXX"
    json.dumps(a.valoracion, allow_nan=False)
    if os.environ.get("BANXICO_TOKEN"):
        assert a.valoracion["supuestos"]["r_f"]["procedencia"]["fuente"] == "bono_m_10"
    else:
        assert a.valoracion["motivo"] == "sin_bono_m"


def test_tsm_se_valora_en_dolares_sin_aviso_de_adr():
    _con_edgar()
    a = analizar("TSM", panel=None)
    assert a.clase == "extranjera_sec"
    assert a.entradas.divisa.convertida and a.entradas.divisa.moneda_estados == "TWD"
    assert not divisas.adr_dudosa(a.entradas.cociente_adr)
    json.dumps(a.valoracion, allow_nan=False)
