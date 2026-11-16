# programa/tests/test_riesgo_backtest.py
import numpy as np
import pytest

from riesgo import backtest


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
