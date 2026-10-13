"""Las descargas, con `yf.Ticker` sustituido: sin red de verdad."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from yfinance.utils import empty_df

from valoracion import mercado

from tests.test_valoracion_mercado import INFO, _cierres


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)


def _ticker(**atributos):
    doble = MagicMock()
    for nombre, valor in atributos.items():
        setattr(doble, nombre, valor)
    return doble


def _con_historial(cierres):
    doble = _ticker()
    doble.history.return_value = pd.DataFrame({"Close": cierres})
    return doble


def _dobles_de_beta():
    """Un activo de pendiente 2 contra el índice, por símbolo."""
    g = np.random.default_rng(7)
    m = g.normal(0.002, 0.02, 104)
    a = 2 * m + g.normal(0, 0.002, 104)
    return {"MU": _con_historial(_cierres(a)), "^GSPC": _con_historial(_cierres(m))}


def _escritos(raiz):
    return list(raiz.rglob("*.json"))


def _envejecer(raiz, dias):
    for ruta in _escritos(raiz):
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        crudo["cuando"] = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        ruta.write_text(json.dumps(crudo), encoding="utf-8")


def test_el_perfil_se_descarga_y_se_reconstruye():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok"
    assert perfil.precio == 989.04


def test_el_perfil_guardado_es_el_mismo_que_el_descargado():
    # Ida y vuelta por el disco: si `asdict` y el constructor no casaran, lo
    # guardado sería otra cosa que lo descargado.
    esperado = mercado.perfil_desde_info("MU", INFO)
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        descargado = mercado.perfil("MU")
    with patch.object(mercado.yf, "Ticker") as fabrica:
        guardado = mercado.perfil("MU")
    fabrica.assert_not_called()
    assert descargado == guardado == (esperado, "ok")


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
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")) as fabrica:
        perfil, motivo = mercado.perfil("MU")
    # Sin esto el test pasaría también si lo caducado se sirviera sin mirar la
    # validez: hay que probar que se fue a la red y que ésta falló.
    fabrica.assert_called()
    assert motivo == "ok" and perfil.precio == 989.04


def test_si_guardar_falla_se_devuelve_igual_lo_descargado(monkeypatch):
    def sin_disco(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(mercado.cache, "guardar", sin_disco)
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok" and perfil.precio == 989.04


def test_una_cache_de_otra_forma_vigente_no_se_sirve_y_se_va_a_la_red(tmp_path):
    # Un campo que el tipo de ahora no conoce: sin esto, el perfil diría
    # "sin_precio" durante lo que dure la validez.
    mercado.cache.guardar(tmp_path, "perfil", "MU", {"perfil": {"ticker": "MU", "viejo": 1}})
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)) as fabrica:
        perfil, motivo = mercado.perfil("MU")
    fabrica.assert_called()
    assert motivo == "ok" and perfil.precio == 989.04
    with patch.object(mercado.yf, "Ticker") as fabrica:
        assert mercado.perfil("MU")[0].precio == 989.04
    fabrica.assert_not_called()


def test_una_cache_de_otra_forma_no_sirve_de_respaldo(tmp_path):
    mercado.cache.guardar(tmp_path, "perfil", "MU", {"perfil": {"ticker": "MU", "viejo": 1}})
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        assert mercado.perfil("MU") == (None, "sin_red")


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


def test_una_descarga_vacia_de_la_tasa_libre_no_se_guarda(tmp_path):
    # `history()` no lanza cuando falla la red: devuelve un marco vacío con la
    # columna `Close`. Guardarlo habría fijado "sin tasa libre" durante un día.
    vacio = _ticker()
    vacio.history.return_value = empty_df()
    with patch.object(mercado.yf, "Ticker", return_value=vacio):
        assert mercado.tasa_libre() == (None, "sin_tasa_libre")
    assert _escritos(tmp_path) == []
    bueno = _con_historial([5.1, 5.24])
    with patch.object(mercado.yf, "Ticker", return_value=bueno) as fabrica:
        assert mercado.tasa_libre() == (pytest.approx(0.0524), "ok")
    fabrica.assert_called()


def test_una_descarga_vacia_no_pisa_lo_bueno_guardado(tmp_path, monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([5.1, 5.24])):
        mercado.tasa_libre()
    antes = {ruta: ruta.read_bytes() for ruta in _escritos(tmp_path)}
    monkeypatch.setitem(mercado.VALIDEZ, "tasa_libre", timedelta(seconds=-1))
    vacio = _ticker()
    vacio.history.return_value = empty_df()
    with patch.object(mercado.yf, "Ticker", return_value=vacio) as fabrica:
        assert mercado.tasa_libre() == (pytest.approx(0.0524), "ok")
    fabrica.assert_called()
    assert {ruta: ruta.read_bytes() for ruta in _escritos(tmp_path)} == antes


def test_sin_regresion_posible_no_hay_beta_y_lo_dice():
    corto = pd.DataFrame(
        {"Close": range(1, 11)}, index=pd.date_range("2026-01-05", periods=10, freq="W-MON")
    )
    doble = _ticker()
    doble.history.return_value = corto
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.beta("NUEVA") == (None, "sin_regresion")
    # Un historial corto es un hecho estable, no un fallo: se guarda.
    with patch.object(mercado.yf, "Ticker") as fabrica:
        assert mercado.beta("NUEVA") == (None, "sin_regresion")
    fabrica.assert_not_called()


def test_la_beta_de_la_red_es_la_del_activo_contra_el_indice():
    # Con el activo y el índice cambiados saldría 0,5 en lugar de 2.
    dobles = _dobles_de_beta()
    with patch.object(mercado.yf, "Ticker", side_effect=lambda simbolo: dobles[simbolo]):
        encontrada, motivo = mercado.beta("MU")
    assert motivo == "ok"
    assert encontrada.bruta == pytest.approx(2.0, abs=0.05)
    assert encontrada.indice == "^GSPC"
    assert encontrada.semanas == 104


def test_una_beta_guardada_vuelve_igual_que_se_descargo():
    dobles = _dobles_de_beta()
    with patch.object(mercado.yf, "Ticker", side_effect=lambda simbolo: dobles[simbolo]):
        descargada = mercado.beta("MU")
    with patch.object(mercado.yf, "Ticker") as fabrica:
        guardada = mercado.beta("MU")
    fabrica.assert_not_called()
    assert descargada == guardada


def test_sin_cierres_ni_del_activo_ni_del_indice_no_hay_beta_ni_se_guarda(tmp_path):
    # El mismo fallo silencioso que la tasa libre, pero aquí el motivo es de red,
    # no de regresión: nada se sabe todavía del historial del activo.
    dobles = _dobles_de_beta()
    vacio = _ticker()
    vacio.history.return_value = empty_df()
    for roto in ("MU", "^GSPC"):
        con_uno_roto = {**dobles, roto: vacio}
        with patch.object(mercado.yf, "Ticker", side_effect=lambda s: con_uno_roto[s]):
            assert mercado.beta("MU") == (None, "sin_red")
        assert _escritos(tmp_path) == []


def test_un_defecto_propio_al_interpretar_no_se_disfraza_de_sin_red(monkeypatch):
    def defectuosa(*args, **kwargs):
        raise AttributeError("un defecto nuestro")

    monkeypatch.setattr(mercado, "regresion_beta", defectuosa)
    dobles = _dobles_de_beta()
    with patch.object(mercado.yf, "Ticker", side_effect=lambda simbolo: dobles[simbolo]):
        with pytest.raises(AttributeError):
            mercado.beta("MU")


def test_la_tasa_efectiva_y_el_consenso_se_descargan():
    estado = pd.DataFrame({"2025": [0.19]}, index=["Tax Rate For Calcs"])
    estimacion = pd.DataFrame(
        {"growth": [0.1648], "currency": ["USD"]}, index=["+1y"]
    )
    doble = _ticker(income_stmt=estado, revenue_estimate=estimacion)
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.tasa_efectiva("MU") == (0.19, "ok")
        assert mercado.consenso("MU", "USD") == (pytest.approx(0.1648), "ok")


def test_la_tasa_efectiva_y_el_consenso_vacios_no_se_guardan(tmp_path):
    vacio = _ticker(income_stmt=pd.DataFrame(), revenue_estimate=pd.DataFrame())
    with patch.object(mercado.yf, "Ticker", return_value=vacio):
        assert mercado.tasa_efectiva("MU") == (None, "sin_red")
        assert mercado.consenso("MU", "USD") == (None, "sin_red")
    sin_nada = _ticker(income_stmt=None, revenue_estimate=None)
    with patch.object(mercado.yf, "Ticker", return_value=sin_nada):
        assert mercado.tasa_efectiva("MU") == (None, "sin_red")
        assert mercado.consenso("MU", "USD") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def test_sin_fila_de_impuestos_la_tasa_efectiva_lo_dice_y_se_guarda():
    estado = pd.DataFrame({"2025": [1.0]}, index=["Net Income"])
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(income_stmt=estado)):
        assert mercado.tasa_efectiva("MU") == (None, "sin_tasa_efectiva")
    with patch.object(mercado.yf, "Ticker") as fabrica:
        assert mercado.tasa_efectiva("MU") == (None, "sin_tasa_efectiva")
    fabrica.assert_not_called()


def test_un_consenso_en_otra_moneda_dice_sin_consenso():
    estimacion = pd.DataFrame({"growth": [0.1648], "currency": ["TWD"]}, index=["+1y"])
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(revenue_estimate=estimacion)):
        assert mercado.consenso("TSM", "USD") == (None, "sin_consenso")


def test_la_clave_del_consenso_lleva_la_moneda():
    estimacion = pd.DataFrame({"growth": [0.1648], "currency": ["USD"]}, index=["+1y"])
    doble = _ticker(revenue_estimate=estimacion)
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.consenso("MU", "USD") == (pytest.approx(0.1648), "ok")
        # Si la clave no llevase la moneda, esto devolvería el 0,1648 guardado.
        assert mercado.consenso("MU", "MXN") == (None, "sin_consenso")


def test_las_edades_maximas_cubren_las_mismas_fuentes_que_las_validez():
    assert mercado.ANTIGUEDAD_MAXIMA.keys() == mercado.VALIDEZ.keys()


def _llamar(fuente):
    return {
        "perfil": lambda: mercado.perfil("MU"),
        "tasa_libre": mercado.tasa_libre,
        "beta": lambda: mercado.beta("MU"),
        "tasa_efectiva": lambda: mercado.tasa_efectiva("MU"),
        "consenso": lambda: mercado.consenso("MU", "USD"),
    }[fuente]()


def _red_buena(fuente):
    """Los argumentos de `patch.object(yf, "Ticker", ...)` que dan un dato bueno."""
    if fuente == "beta":
        dobles = _dobles_de_beta()
        return {"side_effect": lambda simbolo: dobles[simbolo]}
    if fuente == "tasa_libre":
        return {"return_value": _con_historial([5.1, 5.24])}
    estado = pd.DataFrame({"2025": [0.19]}, index=["Tax Rate For Calcs"])
    estimacion = pd.DataFrame({"growth": [0.1648], "currency": ["USD"]}, index=["+1y"])
    return {
        "return_value": _ticker(info=INFO, income_stmt=estado, revenue_estimate=estimacion)
    }


FALLOS = {
    "perfil": "sin_red",
    "tasa_libre": "sin_tasa_libre",
    "beta": "sin_red",
    "tasa_efectiva": "sin_red",
    "consenso": "sin_red",
}


@pytest.mark.parametrize("fuente", list(FALLOS))
def test_lo_guardado_sirve_de_respaldo_dentro_de_su_edad_maxima(fuente, tmp_path):
    with patch.object(mercado.yf, "Ticker", **_red_buena(fuente)):
        bueno = _llamar(fuente)
    assert bueno[1] == "ok"
    _envejecer(tmp_path, mercado.ANTIGUEDAD_MAXIMA[fuente].days - 1)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")) as fabrica:
        assert _llamar(fuente) == bueno
    fabrica.assert_called()


@pytest.mark.parametrize("fuente", list(FALLOS))
def test_lo_guardado_mas_viejo_que_su_edad_maxima_no_sirve(fuente, tmp_path):
    with patch.object(mercado.yf, "Ticker", **_red_buena(fuente)):
        assert _llamar(fuente)[1] == "ok"
    _envejecer(tmp_path, mercado.ANTIGUEDAD_MAXIMA[fuente].days + 1)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        assert _llamar(fuente) == (None, FALLOS[fuente])
