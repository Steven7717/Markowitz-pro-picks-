# tests/test_macro_contexto.py
import pandas as pd
import pytest

from macro.contexto import UMBRAL_SAHM, calcular


def _mensual(valores, desde="2025-01"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


def test_curva_invertida():
    curva = pd.Series([0.2, -0.1], index=pd.DatetimeIndex(["2026-11-12", "2026-11-13"]))
    c = calcular(curva=curva, desempleo=None, ipc=None)
    assert c.curva == pytest.approx(-0.1) and c.curva_invertida is True


def test_sahm_activada():
    # 12 meses en 4,0 y después 4,5, 4,7 y 4,9: media de 3 = 4,7; mínimo previo = 4,0.
    desempleo = _mensual([4.0] * 12 + [4.5, 4.7, 4.9])
    c = calcular(curva=None, desempleo=desempleo, ipc=None)
    assert c.sahm == pytest.approx(0.7)
    assert c.sahm_activada is (0.7 >= UMBRAL_SAHM)


def test_sahm_sin_historia_suficiente_es_none():
    c = calcular(curva=None, desempleo=_mensual([4.0] * 10), ipc=None)
    assert c.sahm is None and c.sahm_activada is None


def test_inflacion_interanual():
    ipc = _mensual([100.0] + [101.0] * 11 + [103.0])
    c = calcular(curva=None, desempleo=None, ipc=ipc)
    assert c.inflacion == pytest.approx(0.03)


def test_sin_series_todo_es_none():
    c = calcular(curva=None, desempleo=None, ipc=None)
    assert (c.curva, c.sahm, c.inflacion) == (None, None, None)
