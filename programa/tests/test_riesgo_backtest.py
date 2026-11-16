# programa/tests/test_riesgo_backtest.py
import numpy as np
import pytest

from riesgo import backtest, metodos


def test_los_limites_son_los_de_la_tabla_de_basilea():
    """0–4 verde, 5–9 amarilla, 10+ roja, con 250 días al 99 %."""
    assert backtest.limites_semaforo(250, 0.99) == (4, 9)


@pytest.mark.parametrize("x, esperada", [(0, "verde"), (4, "verde"), (5, "amarilla"),
                                         (9, "amarilla"), (10, "roja"), (40, "roja")])
def test_zona(x, esperada):
    assert backtest.zona(x) == esperada


def test_kupiec_no_rechaza_la_tasa_exacta_y_si_el_doble_largo():
    assert backtest.kupiec(10, 1000, 0.01) == pytest.approx(1.0)
    assert backtest.kupiec(30, 1000, 0.01) < 0.001
    assert 0 < backtest.kupiec(0, 1000, 0.01) < 0.001
    # Todo fallos: el LR es enorme y el p-valor es 0 (no NaN ni error).
    assert backtest.kupiec(1000, 1000, 0.01) == 0.0


def _garch(n, semilla, omega=2e-6, a=0.10, b=0.88):
    """Retornos con clústeres de volatilidad, que es lo que tiene el mercado."""
    rng = np.random.default_rng(semilla)
    r, v = np.empty(n), omega / (1 - a - b)
    for i in range(n):
        r[i] = np.sqrt(v) * rng.standard_normal()
        v = omega + a * r[i] ** 2 + b * v
    return r


@pytest.mark.parametrize("metodo", ["historico", "ewma", "fhs"])
def test_pronosticos_solo_miran_el_pasado(metodo):
    r = np.random.default_rng(3).normal(0, 0.01, 800)
    p = backtest.pronosticos(r, metodo)
    assert len(p["var99"]) == 800 - backtest.VENTANA_ESTIMACION
    # Cambiar el último día no puede cambiar ninguna previsión: ninguna lo mira.
    r2 = r.copy()
    r2[-1] = -0.5
    np.testing.assert_array_equal(p["var99"], backtest.pronosticos(r2, metodo)["var99"])


@pytest.mark.parametrize("n", [0, 300, 500, 600, backtest.MINIMO_OBSERVACIONES - 1])
def test_backtestear_rechaza_series_cortas(n):
    r = np.random.default_rng(8).normal(0, 0.01, n)
    with pytest.raises(ValueError, match=str(n)):
        backtest.backtestear(r, "normal")


def test_backtestear_acepta_el_minimo():
    r = np.random.default_rng(9).normal(0, 0.01, backtest.MINIMO_OBSERVACIONES)
    assert backtest.backtestear(r, "normal").excepciones.size == backtest.VENTANA_BASILEA


def test_backtestear_rechaza_nan_e_infinitos():
    for malo in (np.nan, np.inf):
        r = np.random.default_rng(10).normal(0, 0.01, 900)
        r[700] = malo
        with pytest.raises(ValueError, match="finit"):
            backtest.backtestear(r, "normal")


def test_sobre_normales_iid_la_normal_acierta_la_tasa():
    """Promedio de 8 series: las ventanas de 250 se solapan y la fracción verde
    de una sola serie es muy ruidosa (de 0,73 a 0,95 según la semilla; esperada
    ≈ 0,87, pues P(≤4 | binomial 250, 1 %) = 0,89 menos el error de estimación)."""
    bts = [backtest.backtestear(np.random.default_rng(s).normal(0, 0.01, 3000), "normal")
           for s in range(8)]
    assert np.mean([b.tasa for b in bts]) == pytest.approx(0.01, abs=0.003)
    assert np.mean([b.fraccion_verde for b in bts]) > 0.8


def test_con_clusteres_ewma_pasa_mas_tiempo_en_verde_que_la_normal():
    r = _garch(3000, 5)
    assert backtest.backtestear(r, "ewma").fraccion_verde >         backtest.backtestear(r, "normal").fraccion_verde


def test_la_fraccion_verde_cuenta_ventanas_de_250():
    r = np.random.default_rng(6).normal(0, 0.01, 1000)
    bt = backtest.backtestear(r, "normal")
    conteos = np.convolve(bt.excepciones.astype(int), np.ones(250, int), "valid")
    assert bt.fraccion_verde == pytest.approx(np.mean(conteos <= 4))
    assert bt.excepciones_ultimas == conteos[-1]
    assert bt.zona_actual == backtest.zona(int(conteos[-1]))


def _bt(metodo, verde, tasa, var_medio):
    return backtest.Backtest(
        metodo=metodo, var99=np.array([var_medio]), es975=np.array([0.0]),
        es99=np.array([0.0]), var975=np.array([0.0]), realizados=np.array([0.0]),
        excepciones=np.array([False]), fraccion_verde=verde, zona_actual="verde",
        excepciones_ultimas=0, tasa=tasa, kupiec_p=1.0, razon_es=1.0,
    )


def test_elegir_gana_el_mas_verde():
    assert backtest.elegir({"a": _bt("a", 0.7, 0.01, 1), "b": _bt("b", 0.9, 0.02, 1)}) == "b"


def test_elegir_empata_por_la_tasa_mas_cercana_al_uno_por_ciento():
    """El conservador de más también está siempre en verde, y no sirve."""
    assert backtest.elegir({"a": _bt("a", 1.0, 0.001, 1), "b": _bt("b", 1.0, 0.009, 1)}) == "b"


def test_elegir_luego_por_el_var_mas_bajo():
    assert backtest.elegir({"a": _bt("a", 1.0, 0.01, 2), "b": _bt("b", 1.0, 0.01, 1)}) == "b"


def test_competir_corre_los_seis():
    r = _garch(1200, 7)
    assert set(backtest.competir(r)) == set(metodos.METODOS)
