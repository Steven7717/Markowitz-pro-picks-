"""Las cifras en pesos, que pueden faltar sin que falte nada de lo demas."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import panel, posiciones, rendimiento


def _serie(fechas, valores):
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


FECHAS = ["2026-01-30", "2026-03-02", "2026-03-31"]


def _marcha(valor, flujos):
    return posiciones.Marcha(
        acciones=pd.DataFrame(), efectivo=pd.Series(dtype=float),
        valor=_serie(FECHAS, valor), flujos=_serie(FECHAS, flujos),
        dividendos=pd.DataFrame(),
    )


MARCHA = _marcha([1000.0, 1050.0, 1100.0], [1000.0, 0.0, 0.0])
INPC = _serie(["2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01"],
              [100.0, 100.5, 101.0, 101.5])


def test_con_fix_constante_la_twr_en_pesos_es_la_de_dolares():
    fix = _serie(FECHAS, [17.0, 17.0, 17.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.motivo == "ok"
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial == cp.fix_final == 17.0
    assert cp.movimiento_tc == pytest.approx(0.0)


def test_las_reales_son_fisher_sobre_las_nominales_en_pesos():
    fix = _serie(FECHAS, [17.0, 17.5, 18.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    assert cp.inflacion is not None
    assert cp.twr_real == pytest.approx(
        (1 + cp.twr_anual) / (1 + cp.inflacion.anual) - 1)
    assert cp.tir_real == pytest.approx((1 + cp.tir) / (1 + cp.inflacion.anual) - 1)
    assert cp.movimiento_tc == pytest.approx(18.0 / 17.0 - 1)


def test_un_libro_en_pesos_no_se_convierte():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="MXN",
                              fix=None, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial is None


def test_sin_valorar_todo_es_none():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=True, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=INPC)
    assert cp.motivo == "sin_valorar"
    assert cp.twr_anual is cp.tir is cp.twr_real is cp.tir_real is None


def test_sin_fix_dice_por_que():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=None, inpc=None, motivo_datos="sin_token")
    assert cp.motivo == "sin_token"
    assert cp.twr_anual is None


def test_sin_inpc_las_nominales_salen_y_las_reales_no():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=None,
                              motivo_datos="sin_red")
    assert cp.twr_anual is not None
    assert cp.twr_real is None
    assert cp.motivo == "sin_red"


def test_otra_moneda_no_se_soporta():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="EUR",
                              fix=None, inpc=None)
    assert cp.motivo == "moneda_no_soportada"


def test_un_inpc_que_no_llega_al_inicio_lo_nombra():
    tarde = _serie(["2026-03-01"], [101.5])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=tarde)
    assert cp.inflacion is None
    assert cp.motivo == "inpc_incompleto"
