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
    assert inf.es975 == pytest.approx(inf.var99, rel=0.15)  # el ES97,5 ≈ VaR99
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
    r = _retornos()
    for f in inf.activos:
        esperado = backtest.elegir(backtest.competir(r[f.ticker].to_numpy()))
        assert f.metodo == esperado


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


def _asimetrica(n=900, semilla=3):
    rng = np.random.default_rng(semilla)
    base = rng.lognormal(0, 0.9, n) - np.exp(0.9 ** 2 / 2)  # cola derecha larga
    return pd.DataFrame({"AAA": base * 0.01, "BBB": rng.normal(0, 0.01, n)},
                        index=pd.bdate_range("2021-01-01", periods=n))


def test_un_corto_solo_no_diversifica_nada():
    inf = informe.informe_riesgo(_asimetrica(), np.array([-1.0, 0.0]))
    assert inf.diversificacion == pytest.approx(0.0, abs=1e-9)


def test_una_cobertura_largo_corto_entre_correlacionadas_diversifica():
    rng = np.random.default_rng(5)
    comun = rng.normal(0, 0.01, 900)
    r = pd.DataFrame({"AAA": comun + rng.normal(0, 0.004, 900),
                      "BBB": comun + rng.normal(0, 0.004, 900)},
                     index=pd.bdate_range("2021-01-01", periods=900))
    inf = informe.informe_riesgo(r, np.array([1.0, -0.8]))
    assert 0 < inf.diversificacion < 1


def test_dos_series_identicas_reparten_el_es_como_los_pesos():
    x = _retornos()["AAA"]
    r = pd.DataFrame({"X": x, "Y": x})
    inf = informe.informe_riesgo(r, np.array([0.6, 0.4]))
    assert [f.aportacion_es for f in inf.activos] == pytest.approx([0.6, 0.4])


def test_la_cuota_del_corto_cubierto_es_negativa():
    rng = np.random.default_rng(7)
    a = rng.normal(0, 0.01, 900)
    r = pd.DataFrame({"AAA": a, "BBB": a + rng.normal(0, 0.002, 900)},
                     index=pd.bdate_range("2021-01-01", periods=900))
    inf = informe.informe_riesgo(r, np.array([1.0, -0.5]))
    assert inf.activos[0].aportacion_es > 1
    assert inf.activos[1].aportacion_es < 0


def test_sin_cola_positiva_el_reparto_es_por_peso_absoluto():
    cuotas = informe._cuotas_es(np.full((10, 3), 0.01), np.array([0.5, 0.0, 0.5]))
    assert list(cuotas) == pytest.approx([0.5, 0.0, 0.5])
