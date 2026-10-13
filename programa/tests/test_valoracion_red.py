"""Contra yfinance y EDGAR de verdad. Excluidos de la suite normal.

Lo que comprueban es que las fuentes siguen teniendo la forma que los
intérpretes puros esperan, y que la lista de industrias financieras casa con
las cadenas reales de Yahoo. Necesitan red, y `valorar` además `EDGAR_IDENTITY`
(sin ella se omite).
"""

import json
import os

import pytest

from valoracion import mercado
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.votos import VEREDICTOS

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)


def test_el_tnx_da_una_tasa_plausible():
    tasa, motivo = mercado.tasa_libre()
    assert motivo == "ok"
    assert 0.0 < tasa < 0.15


def test_la_beta_de_mu_sale_de_una_regresion_completa():
    beta, motivo = mercado.beta("MU")
    assert motivo == "ok"
    assert beta.semanas >= 100
    assert 0.3 < beta.bruta < 4.0


def test_el_consenso_de_mu_viene_en_dolares():
    valor, motivo = mercado.consenso("MU", "USD")
    assert motivo == "ok" and valor is not None


def test_el_consenso_de_tsm_contra_dolares_se_descarta():
    # Su revenue_estimate viene en TWD.
    valor, _ = mercado.consenso("TSM", "USD")
    assert valor is None


@pytest.mark.parametrize(
    "ticker, financiera",
    [
        ("JPM", True), ("USB", True), ("MET", True), ("PGR", True), ("GS", True),
        ("V", False), ("MA", False), ("COF", False), ("AJG", False), ("BLK", False),
        ("MU", False),
    ],
)
def test_la_lista_de_financieras_casa_con_yahoo(ticker, financiera):
    perfil, motivo = mercado.perfil(ticker)
    assert motivo == "ok"
    assert (perfil.industria in INDUSTRIAS_FINANCIERAS) is financiera


def test_valorar_mu_de_punta_a_punta():
    from fundamentals.fetch import set_sec_identity
    from valoracion.motor import valorar

    # Como los demás tests contra EDGAR: sin identidad se omite, no falla. Con
    # la caché de hechos llena pasaría igual, pero eso depende de la máquina.
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("Falta EDGAR_IDENTITY")
    set_sec_identity()
    plano = valorar("MU", 0.3)
    json.dumps(plano, allow_nan=False)
    assert plano["veredicto"] in VEREDICTOS
    assert plano["supuestos"]["beta"]["procedencia"]["fuente"] == "regresion"
