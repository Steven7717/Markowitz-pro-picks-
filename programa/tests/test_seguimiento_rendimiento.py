import numpy as np
import pandas as pd
import pytest

from seguimiento import rendimiento


def serie(valores, fechas=None) -> pd.Series:
    fechas = fechas or pd.bdate_range("2026-01-05", periods=len(valores))
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


def test_sin_flujos_el_twr_es_el_retorno_simple():
    valor = serie([100.0, 110.0, 121.0])
    flujos = serie([0.0, 0.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_una_aportacion_no_cuenta_como_ganancia():
    # Sin descontar el flujo, meter 100 en una cartera de 100 se leeria como un
    # 100% de rentabilidad en un dia. Es el error que hace falta que no ocurra.
    valor = serie([100.0, 200.0, 200.0])
    flujos = serie([0.0, 100.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.0)


def test_el_twr_calculado_a_mano_no_es_el_retorno_simple():
    # 100 -> 110 (+10%), se aportan 90, 200 -> 220 (+10%). El TWR es 1,1*1,1-1
    # = 21%. El retorno simple sobre lo aportado daria (220-190)/190 = 15,8%.
    # Este test existe para que el dia que alguien "simplifique" la formula,
    # falle.
    valor = serie([100.0, 200.0, 220.0])
    flujos = serie([0.0, 90.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_un_valor_inicial_de_cero_no_revienta_ni_devuelve_infinito():
    # Pasa el primer dia y cada vez que la cartera se vacia y vuelve a empezar.
    valor = serie([0.0, 100.0, 110.0])
    flujos = serie([0.0, 100.0, 0.0])
    resultado = rendimiento.twr(valor, flujos)
    assert np.isfinite(resultado)
    assert resultado == pytest.approx(0.1)


def test_anualizar_por_debajo_del_minimo_no_se_hace():
    # Un 2% en tres dias anualiza a +780%. Devolver eso seria una afirmacion
    # que los datos no sostienen.
    assert rendimiento.anualizar(0.02, dias=3) is None


def test_anualizar_por_encima_del_minimo_si_se_hace():
    assert rendimiento.anualizar(0.10, dias=365) == pytest.approx(0.10)


def test_anualizar_medio_ano_capitaliza():
    assert rendimiento.anualizar(0.10, dias=182.5) == pytest.approx(0.21, abs=1e-3)


def test_el_minimo_es_treinta_dias():
    assert rendimiento.MINIMO_DIAS_ANUALIZAR == 30
    assert rendimiento.anualizar(0.02, dias=29) is None
    assert rendimiento.anualizar(0.02, dias=30) is not None
