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


# --- El informe anual (N3) ---------------------------------------------------------

from analizador import informe_anual


@pytest.fixture
def sin_cache_de_informes(monkeypatch, tmp_path):
    monkeypatch.setattr(informe_anual, "RAIZ_CACHE", tmp_path)


def test_el_informe_de_mu_trae_los_riesgos_y_el_mdna(sin_cache_de_informes):
    _con_edgar()
    informe, motivo = informe_anual.cargar("MU", "10-K")
    assert motivo == "ok"
    assert informe.riesgos.nombre == "Item 1A" and informe.riesgos.caracteres_totales > 50_000
    assert informe.mdna.nombre == "Item 7"
    assert "discussion and analysis" in informe.mdna.texto[:300].lower()
    assert informe_anual.ultimo_presentado("MU", "10-K") == (informe.accession, informe.fecha)


def test_el_mdna_de_pgr_sale_de_su_anexo_13(sin_cache_de_informes):
    _con_edgar()
    informe, _ = informe_anual.cargar("PGR", "10-K")
    assert informe.mdna.nombre == "EX-13"
    assert informe.mdna.texto.lower().startswith("management")


def test_wfc_remite_el_mdna_y_los_riesgos_a_su_informe_y_no_se_cita_nada(sin_cache_de_informes):
    _con_edgar()
    # Su Item 1A son 289 caracteres («incorporated into this item by reference»,
    # a «Financial Review - Risk Factors» del anexo) y su Item 7 también remite,
    # a un anexo sin el encabezado «Management's Discussion and Analysis».
    informe, motivo = informe_anual.cargar("WFC", "10-K")
    assert motivo == "ok" and informe.mdna is None and informe.riesgos is None


def test_el_20f_de_tsm_corta_los_riesgos_desde_su_encabezado(sin_cache_de_informes):
    _con_edgar()
    informe, _ = informe_anual.cargar("TSM", "20-F")
    assert informe.riesgos.nombre == "Item 3.D"
    assert informe.riesgos.texto.lower().startswith("risk factors")
    assert informe.mdna.nombre == "Item 5"


def test_el_20f_de_nvo_remite_los_riesgos_al_informe_anual(sin_cache_de_informes):
    _con_edgar()
    informe, motivo = informe_anual.cargar("NVO", "20-F")
    assert motivo == "ok" and informe.riesgos is None


def test_los_riesgos_de_mu_son_los_que_lee_candidatos(sin_cache_de_informes, tmp_path):
    _con_edgar()
    # El mismo texto, para que la ficha ya pagada salga de la caché por contenido.
    from ranking.filings import cargar_riesgos

    informe, _ = informe_anual.cargar("MU", "10-K")
    de_candidatos = cargar_riesgos("MU", cache_dir=tmp_path / "riesgos", refresh=True)
    assert informe.riesgos.texto == de_candidatos.texto
