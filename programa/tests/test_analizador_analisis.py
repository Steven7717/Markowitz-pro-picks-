"""Un ticker de punta a punta, con cada pieza sustituida en su frontera."""

import logging
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import analisis
from analizador.resolver import Identidad, Resuelto
from tests.test_analizador_referencia import panel_crudo


def _identidad(ticker="IN0", tipo="EQUITY", sector="Technology", moneda="USD"):
    return Identidad(ticker, tipo, "Una empresa", "NMS", moneda, moneda, sector,
                     "Semiconductors", "United States", 100.0, None)


def _resuelto(ticker="IN0", clase="sec", **sobre):
    return Resuelto(ticker, clase, _identidad(ticker, **sobre), None)


class _Valoracion:
    """Sustituye a `entradas` y `valorar`, y apunta con qué pilar se valoró."""

    def __init__(self):
        self.pilares = []

    def __enter__(self):
        self._a = patch.object(analisis, "entradas", return_value=("ENTRADAS", "ok"))
        self._b = patch.object(analisis, "valorar", side_effect=self._valorar)
        self._a.start(), self._b.start()
        return self

    def __exit__(self, *_):
        self._a.stop(), self._b.stop()

    def _valorar(self, entradas, pilar):
        self.pilares.append(pilar)
        return {"version": "m1", "veredicto": "en_rango"}


def test_un_ticker_del_panel_toma_su_ficha_del_panel_y_vota_con_su_pilar():
    panel = panel_crudo()
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.kpis, "kpis_sec", side_effect=AssertionError("no hace falta")), \
            _Valoracion() as valoracion:
        a = analisis.analizar("IN0", panel, {"IN0": "Information Technology"})
    assert (a.clase, a.motivo, a.sector, a.fuente_sector) == ("sec", None, "Information Technology", "sp500")
    assert a.referencia.en_panel and a.motivo_referencia is None
    assert valoracion.pilares == [a.referencia.ficha["pilares"]["valoracion"]]
    assert a.valoracion == {"version": "m1", "veredicto": "en_rango"}


def test_un_ticker_de_la_sec_fuera_del_panel_se_inserta_con_sus_filas():
    panel = panel_crudo()
    propias = panel.xs("IN1", level="ticker").drop(columns="sector_gics")
    sin_el = panel.drop(index="IN1", level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto("IN1")), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(propias, "ok")), \
            _Valoracion():
        a = analisis.analizar("IN1", sin_el, {})
    assert a.sector == "Information Technology" and a.fuente_sector == "yahoo"
    assert not a.referencia.en_panel and a.referencia.puesto is not None


def test_sin_panel_se_valora_igual_y_se_dice():
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            _Valoracion() as valoracion:
        a = analisis.analizar("IN0", None, {})
    assert a.referencia is None and a.motivo_referencia == "sin_panel"
    assert valoracion.pilares == [None]


def test_sin_sector_no_hay_pares_y_se_dice():
    panel = panel_crudo().drop(index="IN0", level="ticker")
    resuelto = _resuelto(sector="Conglomerates")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), _Valoracion():
        a = analisis.analizar("IN0", panel, {})
    assert a.sector is None and a.motivo_referencia == "sin_sector"


def test_un_sector_con_menos_pares_de_los_que_pide_el_z_no_tiene_referencia():
    # Con ella dentro, Utilities tendría dos empresas: menos de `MIN_PARES`, sin
    # z, y la ficha saldría «pilar sin datos», que culparía a la empresa.
    panel = panel_crudo().drop(index=["UT0", "UT1", "UT2", "UT3"], level="ticker")
    resuelto = _resuelto("UT0", sector="Utilities")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), \
            patch.object(analisis.kpis, "kpis_sec", side_effect=AssertionError("no hace falta")), \
            _Valoracion():
        a = analisis.analizar("UT0", panel, {})
    assert a.referencia is None and a.motivo_referencia == "sector_sin_pares"


def test_con_los_pares_justos_si_hay_referencia():
    crudo = panel_crudo()
    propias = crudo.xs("UT0", level="ticker").drop(columns="sector_gics")
    panel = crudo.drop(index=["UT0", "UT1", "UT2"], level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto("UT0", sector="Utilities")), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(propias, "ok")), \
            _Valoracion():
        a = analisis.analizar("UT0", panel, {})
    assert a.motivo_referencia is None and a.referencia is not None


def test_si_no_hay_filas_propias_el_motivo_es_el_suyo():
    panel = panel_crudo().drop(index="IN0", level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(None, "sin_estados")), \
            _Valoracion():
        a = analisis.analizar("IN0", panel, {})
    assert a.motivo_referencia == "sin_estados"


def test_un_etf_solo_tiene_su_identidad():
    resuelto = _resuelto("SPY", "etf", tipo="ETF")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), \
            patch.object(analisis, "entradas", side_effect=AssertionError("no se valora")):
        a = analisis.analizar("SPY", panel_crudo(), {})
    assert (a.clase, a.motivo, a.valoracion, a.referencia) == ("etf", None, None, None)
    assert a.identidad.tipo == "ETF"


def test_un_ticker_sin_clase_dice_por_que():
    with patch.object(analisis.resolver, "resolver", return_value=Resuelto("ZZZZQ", None, None, "sin_red")):
        a = analisis.analizar("ZZZZQ", None, {})
    assert (a.clase, a.motivo) == (None, "sin_red")


def test_sin_entradas_la_valoracion_es_una_fallida_con_su_motivo():
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis, "entradas", return_value=(None, "sin_precio")):
        a = analisis.analizar("IN0", None, {})
    assert a.valoracion["motivo"] == "sin_precio"
    assert isinstance(a.valoracion["version"], str)


def test_un_defecto_en_un_ticker_no_tumba_a_los_demas_y_deja_traza(caplog):
    def resolver(ticker):
        if ticker == "ROTO":
            raise KeyError("un defecto propio")
        return Resuelto(ticker, None, None, "sin_red")

    with patch.object(analisis.resolver, "resolver", side_effect=resolver), \
            patch.object(analisis.referencia, "cargar_panel", return_value=(None, None)), \
            caplog.at_level(logging.ERROR):
        resultados, fecha = analisis.analizar_varios(["ROTO", "MU"], tabla_sectores={})
    assert [a.motivo for a in resultados] == ["error_interno", "sin_red"]
    assert fecha is None
    assert "ROTO" in caplog.text
