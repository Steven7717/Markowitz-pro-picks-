"""Un ticker de punta a punta, con cada pieza sustituida en su frontera."""

import logging
from dataclasses import replace
from unittest.mock import MagicMock, patch

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


def test_si_ningun_trimestre_cae_en_la_ventana_del_panel_se_dice():
    panel = panel_crudo().drop(index="IN0", level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.kpis, "kpis_sec", return_value=("FILAS", "ok")), \
            patch.object(analisis.referencia, "frente_al_sector", return_value=None), \
            _Valoracion() as valoracion:
        a = analisis.analizar("IN0", panel, {})
    assert a.referencia is None and a.motivo_referencia == "sin_trimestres_comparables"
    assert valoracion.pilares == [None]


_TRIMESTRALES = pd.DataFrame({"ingresos": [1.0]})
_ANUALES = pd.DataFrame({"ingresos": [4.0]})


def _extranjera(moneda="USD", moneda_estados="TWD", clase="extranjera_sec"):
    """IN0 como una emisora de yfinance que cotiza en `moneda` y presenta en `moneda_estados`."""
    identidad = replace(_identidad(), moneda=moneda, moneda_estados=moneda_estados)
    return Resuelto("IN0", clase, identidad, None)


def _por_yfinance(
    resuelto, estados=("CRUDOS", "ok"), trimestrales=_TRIMESTRALES, cambio=(0.031, "ok"), filas=None
):
    """IN0 fuera del panel por la rama de yfinance, sustituida en sus cuatro fronteras.

    Devuelve el análisis y los dobles, para ver con qué monedas se llamaron.
    """
    crudo = panel_crudo()
    propias = crudo.xs("IN0", level="ticker").drop(columns="sector_gics")
    dobles = {
        "estados": MagicMock(return_value=estados),
        "lineas_de": MagicMock(return_value=(trimestrales, _ANUALES)),
        "tipo_de_cambio": MagicMock(return_value=cambio),
        "kpis_yf": MagicMock(return_value=filas or (propias, "ok")),
    }
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), \
            patch.object(analisis.mercado, "estados", dobles["estados"]), \
            patch.object(analisis, "lineas_de", dobles["lineas_de"]), \
            patch.object(analisis.mercado, "tipo_de_cambio", dobles["tipo_de_cambio"]), \
            patch.object(analisis.kpis, "kpis_yf", dobles["kpis_yf"]), \
            _Valoracion():
        a = analisis.analizar("IN0", crudo.drop(index="IN0", level="ticker"), {})
    return a, dobles


@pytest.mark.parametrize("clase", ["extranjera_sec", "sin_sec"])
def test_fuera_de_la_sec_se_pasa_a_dolares_desde_la_moneda_de_sus_estados(clase):
    # Como TSM: cotiza en dólares y presenta en TWD. El tipo a dólares es el de
    # los estados, y `kpis_yf` recibe primero la moneda del precio.
    a, dobles = _por_yfinance(_extranjera("USD", "TWD", clase))
    dobles["estados"].assert_called_once_with("IN0")
    dobles["lineas_de"].assert_called_once_with("CRUDOS")
    dobles["tipo_de_cambio"].assert_called_once_with("TWD", "USD")
    argumentos = dobles["kpis_yf"].call_args.args
    assert argumentos[0] == "IN0"
    assert argumentos[1] is _TRIMESTRALES and argumentos[2] is _ANUALES
    assert argumentos[3:] == ("USD", "TWD", 0.031)
    assert a.motivo_referencia is None and not a.referencia.en_panel


@pytest.mark.parametrize(
    "moneda, moneda_estados, esperada", [(None, "TWD", "TWD"), ("USD", None, "USD")]
)
def test_si_falta_una_de_las_dos_monedas_se_usa_la_otra(moneda, moneda_estados, esperada):
    _, dobles = _por_yfinance(_extranjera(moneda, moneda_estados))
    dobles["tipo_de_cambio"].assert_called_once_with(esperada, "USD")
    assert dobles["kpis_yf"].call_args.args[3:5] == (esperada, esperada)


def test_sin_ninguna_moneda_no_se_pide_un_par_inventado():
    a, dobles = _por_yfinance(_extranjera(None, None))
    dobles["tipo_de_cambio"].assert_not_called()
    dobles["kpis_yf"].assert_not_called()
    assert a.motivo_referencia == "sin_precio"


def test_sin_trimestres_de_yfinance_se_dice_sin_historia():
    a, dobles = _por_yfinance(_extranjera(), trimestrales=pd.DataFrame())
    dobles["tipo_de_cambio"].assert_not_called()
    dobles["kpis_yf"].assert_not_called()
    assert a.motivo_referencia == "sin_historia"


@pytest.mark.parametrize(
    "sustituto, motivo",
    [
        ({"estados": (None, "sin_red")}, "sin_red"),
        ({"cambio": (None, "sin_red")}, "sin_red"),
        ({"filas": (None, "sin_precio")}, "sin_precio"),
    ],
)
def test_el_motivo_de_yfinance_llega_tal_cual(sustituto, motivo):
    a, _ = _por_yfinance(_extranjera(), **sustituto)
    assert a.referencia is None and a.motivo_referencia == motivo


@pytest.mark.parametrize("pieza", ["entradas", "valorar"])
def test_un_defecto_al_valorar_no_se_lleva_la_ficha_y_deja_traza(pieza, caplog):
    sustitutos = {
        "entradas": MagicMock(return_value=("ENTRADAS", "ok")),
        "valorar": MagicMock(return_value={"version": "m1"}),
    }
    sustitutos[pieza].side_effect = ZeroDivisionError("un defecto del motor")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.multiple(analisis, **sustitutos), \
            caplog.at_level(logging.ERROR):
        a = analisis.analizar("IN0", panel_crudo(), {"IN0": "Information Technology"})
    assert (a.clase, a.motivo, a.identidad.nombre) == ("sec", None, "Una empresa")
    assert a.referencia.en_panel and a.motivo_referencia is None
    assert a.valoracion["motivo"] == "error_interno"
    # Las entradas que sí llegaron se quedan: el defecto es de la aritmética.
    assert a.entradas == (None if pieza == "entradas" else "ENTRADAS")
    assert "IN0" in caplog.text and "ZeroDivisionError" in caplog.text


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


def test_varios_sin_tabla_cargan_la_del_sp500_una_sola_vez():
    # Si la tabla no llegara a `sector_gics`, éste cargaría la real, que no
    # tiene IN0 ni IN1, y su sector saldría de Yahoo.
    tabla = {"IN0": "Information Technology", "IN1": "Information Technology"}
    with patch.object(analisis.resolver, "resolver", side_effect=_resuelto), \
            patch.object(analisis.referencia, "cargar_panel", return_value=(None, None)), \
            patch.object(analisis, "load_sectors", return_value=tabla) as cargar, \
            _Valoracion():
        resultados, _ = analisis.analizar_varios(["IN0", "IN1"])
    assert cargar.call_count == 1
    assert [a.fuente_sector for a in resultados] == ["sp500", "sp500"]
