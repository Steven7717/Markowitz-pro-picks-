"""Las descargas, con `yf.Ticker` sustituido: sin red de verdad."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from valoracion import mercado

from tests.test_valoracion_mercado import INFO


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)


def _ticker(**atributos):
    doble = MagicMock()
    for nombre, valor in atributos.items():
        setattr(doble, nombre, valor)
    return doble


def test_el_perfil_se_descarga_y_se_reconstruye():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok"
    assert perfil.precio == 989.04


def test_un_ticker_sin_precio_dice_sin_precio():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={})):
        assert mercado.perfil("NADA") == (None, "sin_precio")


def test_sin_red_y_sin_cache_dice_sin_red():
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        assert mercado.perfil("MU") == (None, "sin_red")


def test_lo_guardado_vigente_no_vuelve_a_la_red():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        mercado.perfil("MU")
    # `assert_not_called` y no un `side_effect` que lance: `_traer` atrapa
    # cualquier excepción y caería a lo guardado, así que el test pasaría
    # también con la caché rota.
    with patch.object(mercado.yf, "Ticker") as fabrica:
        perfil, motivo = mercado.perfil("MU")
    fabrica.assert_not_called()
    assert motivo == "ok" and perfil.precio == 989.04


def test_si_la_red_falla_se_usa_lo_guardado_aunque_haya_caducado(monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        mercado.perfil("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "perfil", timedelta(seconds=-1))
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok" and perfil.precio == 989.04


def test_la_tasa_libre_sale_del_tnx():
    cierres = pd.DataFrame({"Close": [5.1, 5.24]})
    doble = _ticker()
    doble.history.return_value = cierres
    with patch.object(mercado.yf, "Ticker", return_value=doble) as fabrica:
        tasa, motivo = mercado.tasa_libre()
    assert (tasa, motivo) == (pytest.approx(0.0524), "ok")
    fabrica.assert_called_with("^TNX")


def test_sin_tasa_libre_lo_dice():
    with patch.object(mercado.yf, "Ticker", side_effect=OSError):
        assert mercado.tasa_libre() == (None, "sin_tasa_libre")


def test_sin_regresion_posible_no_hay_beta_y_lo_dice():
    corto = pd.DataFrame(
        {"Close": range(1, 11)}, index=pd.date_range("2026-01-05", periods=10, freq="W-MON")
    )
    doble = _ticker()
    doble.history.return_value = corto
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.beta("NUEVA") == (None, "sin_regresion")


def test_la_tasa_efectiva_y_el_consenso_se_descargan():
    estado = pd.DataFrame({"2025": [0.19]}, index=["Tax Rate For Calcs"])
    estimacion = pd.DataFrame(
        {"growth": [0.1648], "currency": ["USD"]}, index=["+1y"]
    )
    doble = _ticker(income_stmt=estado, revenue_estimate=estimacion)
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.tasa_efectiva("MU") == (0.19, "ok")
        assert mercado.consenso("MU", "USD") == (pytest.approx(0.1648), "ok")
