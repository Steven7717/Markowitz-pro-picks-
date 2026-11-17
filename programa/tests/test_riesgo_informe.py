# programa/tests/test_riesgo_informe.py
import numpy as np
import pandas as pd
import pytest

from riesgo import backtest, informe


def _retornos(n=900, semilla=0):
    rng = np.random.default_rng(semilla)
    comun = rng.normal(0, 0.008, n)
    datos = {
        "AAA": comun + rng.normal(0, 0.006, n),
        "BBB": comun + rng.normal(0, 0.012, n),
        "CCC": rng.standard_t(4, n) * 0.007,
    }
    return pd.DataFrame(datos, index=pd.bdate_range("2021-01-01", periods=n))


def test_el_informe_trae_la_cartera_y_cada_activo():
    r = _retornos()
    inf = informe.informe_riesgo(r, np.array([0.5, 0.3, 0.2]))
    assert inf.elegido in inf.competencia
    assert [f.ticker for f in inf.activos] == ["AAA", "BBB", "CCC"]
    assert inf.es975 >= inf.var99 * 0.9  # mismo orden de magnitud: el ES97,5 ≈ VaR99
    assert inf.es99 >= inf.var99 > 0


def test_el_var_de_hoy_es_el_del_metodo_elegido_sobre_la_ultima_ventana():
    r = _retornos()
    w = np.array([0.5, 0.3, 0.2])
    inf = informe.informe_riesgo(r, w)
    rp = r.to_numpy() @ w
    from riesgo import metodos
    var, _ = metodos.METODOS[inf.elegido](rp[-backtest.VENTANA_ESTIMACION:], 0.99)
    assert inf.var99 == pytest.approx(var)


def test_las_aportaciones_al_es_suman_el_cien_por_cien():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    assert sum(f.aportacion_es for f in inf.activos) == pytest.approx(1.0)


def test_diversificar_reduce_el_es():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    assert 0 < inf.diversificacion < 1


def test_cada_activo_elige_su_propio_metodo():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    for f in inf.activos:
        assert f.metodo in inf.competencia  # misma lista de candidatos


def test_con_poca_historia_dice_cuanta_hay_y_cuanta_falta():
    with pytest.raises(informe.HistoriaInsuficiente) as e:
        informe.informe_riesgo(_retornos(n=600), np.array([0.5, 0.3, 0.2]))
    assert e.value.observaciones == 600
    assert e.value.necesarias == backtest.MINIMO_OBSERVACIONES


def test_los_pesos_tienen_que_cuadrar_con_las_columnas():
    with pytest.raises(ValueError):
        informe.informe_riesgo(_retornos(), np.array([0.5, 0.5]))


def test_retornos_no_finitos_dan_un_error_claro():
    r = _retornos()
    r.iloc[10, 1] = np.nan
    with pytest.raises(ValueError, match="no finitos"):
        informe.informe_riesgo(r, np.array([0.5, 0.3, 0.2]))
