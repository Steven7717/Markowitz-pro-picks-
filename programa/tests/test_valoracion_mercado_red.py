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
    # Yahoo lo conoce (trae tipo y moneda) pero no cotiza: es un hecho, se guarda.
    info = {"quoteType": "EQUITY", "currency": "USD"}
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=info)):
        assert mercado.perfil("NADA") == (None, "sin_precio")
    with patch.object(mercado.yf, "Ticker") as fabrica:
        assert mercado.perfil("NADA") == (None, "sin_precio")
    fabrica.assert_not_called()


def test_un_info_sin_identidad_no_se_guarda(tmp_path):
    # Un 401, 404 o 5xx de quoteSummary no lanza: `info` queda en una sola clave
    # suelta, igual que para un símbolo inexistente. Sin saber nada, no se guarda.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={})):
        assert mercado.perfil("MU") == (None, "sin_red")
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={"trailingPegRatio": 1.2})):
        assert mercado.perfil("MU") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def test_un_info_sin_identidad_no_pisa_el_perfil_guardado(tmp_path, monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        mercado.perfil("MU")
    antes = {ruta: ruta.read_bytes() for ruta in _escritos(tmp_path)}
    monkeypatch.setitem(mercado.VALIDEZ, "perfil", timedelta(seconds=-1))
    roto = _ticker(info={"trailingPegRatio": 1.2})
    with patch.object(mercado.yf, "Ticker", return_value=roto) as fabrica:
        perfil, motivo = mercado.perfil("MU")
    fabrica.assert_called()
    assert motivo == "ok" and perfil.precio == 989.04
    assert {ruta: ruta.read_bytes() for ruta in _escritos(tmp_path)} == antes


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
        "identidad": lambda: mercado.identidad("MU"),
        "estados": lambda: mercado.estados("MU"),
        "tipo_de_cambio": lambda: mercado.tipo_de_cambio("TWD", "USD"),
    }[fuente]()


def _red_buena(fuente):
    """Los argumentos de `patch.object(yf, "Ticker", ...)` que dan un dato bueno."""
    if fuente == "beta":
        dobles = _dobles_de_beta()
        return {"side_effect": lambda simbolo: dobles[simbolo]}
    if fuente == "tasa_libre":
        return {"return_value": _con_historial([5.1, 5.24])}
    if fuente == "tipo_de_cambio":
        return {"return_value": _con_historial([0.0309, 0.0311])}
    if fuente == "estados":
        return {"return_value": _ticker(**_estados_dobles())}
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
    "identidad": "sin_red",
    "estados": "sin_red",
    "tipo_de_cambio": "sin_red",
}


def _igual(a, b):
    """`==` no sirve para DataFrames; los estados se comparan con su propia igualdad."""
    if isinstance(a[0], dict) and a[0] and isinstance(next(iter(a[0].values())), pd.DataFrame):
        return a[1] == b[1] and all(a[0][k].equals(b[0][k]) for k in a[0])
    return a == b


@pytest.mark.parametrize("fuente", list(FALLOS))
def test_lo_guardado_sirve_de_respaldo_dentro_de_su_edad_maxima(fuente, tmp_path):
    with patch.object(mercado.yf, "Ticker", **_red_buena(fuente)):
        bueno = _llamar(fuente)
    assert bueno[1] == "ok"
    _envejecer(tmp_path, mercado.ANTIGUEDAD_MAXIMA[fuente].days - 1)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")) as fabrica:
        assert _igual(_llamar(fuente), bueno)
    fabrica.assert_called()


@pytest.mark.parametrize("fuente", list(FALLOS))
def test_lo_guardado_mas_viejo_que_su_edad_maxima_no_sirve(fuente, tmp_path):
    with patch.object(mercado.yf, "Ticker", **_red_buena(fuente)):
        assert _llamar(fuente)[1] == "ok"
    _envejecer(tmp_path, mercado.ANTIGUEDAD_MAXIMA[fuente].days + 1)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        assert _llamar(fuente) == (None, FALLOS[fuente])


# --- La identidad, los estados y el tipo de cambio ----------------------------

INFO_ETF = {
    "quoteType": "ETF",
    "exchange": "PCX",
    "currency": "USD",
    "regularMarketPrice": 769.6,
    "regularMarketTime": 1_791_835_140,
    "longName": "State Street SPDR S&P 500 ETF Trust",
}


def test_la_identidad_de_un_etf_se_lee_aunque_no_tenga_capitalizacion():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO_ETF)):
        identidad, motivo = mercado.identidad("SPY")
    assert motivo == "ok"
    assert identidad["quoteType"] == "ETF"
    assert identidad["regularMarketPrice"] == 769.6
    # Y `perfil`, que exige capitalización, no lo valora: es lo que se quiere.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO_ETF)):
        assert mercado.perfil("SPY") == (None, "sin_precio")


def test_la_identidad_solo_guarda_las_claves_que_sirven():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        identidad, _ = mercado.identidad("MU")
    assert set(identidad) == set(mercado.CLAVES_IDENTIDAD_INFO)
    assert "beta" not in identidad


def test_una_identidad_sin_claves_no_se_guarda(tmp_path):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={"trailingPegRatio": None})):
        assert mercado.identidad("ZZZZQ") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def _estados_dobles():
    estado = pd.DataFrame({pd.Timestamp("2026-06-30"): [2.5e11]}, index=["Total Revenue"])
    vacio = empty_df()
    return {nombre: (estado if nombre == "income_stmt" else vacio) for nombre in mercado.ESTADOS}


def test_los_estados_se_descargan_y_vuelven_como_dataframes():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_estados_dobles())):
        estados, motivo = mercado.estados("WALMEX.MX")
    assert motivo == "ok"
    assert set(estados) == set(mercado.ESTADOS)
    assert estados["income_stmt"].loc["Total Revenue"].iloc[0] == 2.5e11
    assert estados["cashflow"].empty


def test_seis_estados_vacios_no_se_guardan(tmp_path):
    vacios = {nombre: empty_df() for nombre in mercado.ESTADOS}
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**vacios)):
        assert mercado.estados("WALMEX.MX") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def test_el_tipo_de_cambio_de_una_moneda_consigo_misma_no_sale_a_la_red():
    with patch.object(mercado.yf, "Ticker", side_effect=AssertionError("a la red no")):
        assert mercado.tipo_de_cambio("MXN", "MXN") == (1.0, "ok")


def test_el_tipo_de_cambio_es_el_ultimo_cierre_del_par():
    doble = _con_historial([0.0309, 0.0311])
    with patch.object(mercado.yf, "Ticker", return_value=doble) as fabrica:
        assert mercado.tipo_de_cambio("TWD", "USD") == (pytest.approx(0.0311), "ok")
    fabrica.assert_called_with("TWDUSD=X")


def test_un_tipo_de_cambio_vacio_no_se_guarda(tmp_path):
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([])):
        assert mercado.tipo_de_cambio("TWD", "USD") == (None, "sin_red")
    assert _escritos(tmp_path) == []


# --- Arreglos de la revisión --------------------------------------------------

ANUALES = ("income_stmt", "balance_sheet", "cashflow")


def _seis_estados(valor):
    return {
        nombre: pd.DataFrame({pd.Timestamp("2026-06-30"): [valor]}, index=["Total Revenue"])
        for nombre in mercado.ESTADOS
    }


def test_un_estado_que_llega_vacio_no_pisa_el_guardado(monkeypatch):
    # Cada estado es una petición aparte, y yfinance devuelve vacío el que
    # falla: un 429 en la cuarta da tres llenos y tres vacíos.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_seis_estados(1.0))):
        assert mercado.estados("MU")[1] == "ok"
    monkeypatch.setitem(mercado.VALIDEZ, "estados", timedelta(seconds=-1))
    a_medias = {**_seis_estados(2.0), **{nombre: empty_df() for nombre in ANUALES}}
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**a_medias)) as fabrica:
        estados, motivo = mercado.estados("MU")
    fabrica.assert_called()
    assert motivo == "ok"
    for nombre in ANUALES:
        assert estados[nombre].loc["Total Revenue"].iloc[0] == 1.0
    # Lo que sí llegó lleno es lo nuevo: no se ha servido lo guardado entero.
    assert estados["quarterly_income_stmt"].loc["Total Revenue"].iloc[0] == 2.0


def test_un_estado_vacio_de_verdad_sigue_vacio():
    # NESN.SW publica semestralmente: sus trimestrales de resultados y de
    # flujos llegan vacíos siempre, y no hay nada guardado que conservar.
    semestral = {
        **_seis_estados(1.0),
        "quarterly_income_stmt": empty_df(),
        "quarterly_cashflow": empty_df(),
    }
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**semestral)):
        estados, motivo = mercado.estados("NESN.SW")
    assert motivo == "ok"
    assert estados["quarterly_income_stmt"].empty and estados["quarterly_cashflow"].empty


def test_los_peniques_de_londres_se_cambian_como_libras_entre_cien():
    # yfinance pasa el símbolo a mayúsculas: `GBpUSD=X` daría el tipo de la
    # libra, cien veces mayor.
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([1.30, 1.32])) as fabrica:
        assert mercado.tipo_de_cambio("GBp", "USD") == (pytest.approx(0.0132), "ok")
    fabrica.assert_called_with("GBPUSD=X")


def test_a_peniques_el_tipo_de_cambio_se_multiplica_por_cien():
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([0.75, 0.76])) as fabrica:
        assert mercado.tipo_de_cambio("USD", "GBp") == (pytest.approx(76.0), "ok")
    fabrica.assert_called_with("USDGBP=X")


def test_una_moneda_frente_a_su_subunidad_no_sale_a_la_red():
    with patch.object(mercado.yf, "Ticker", side_effect=AssertionError("a la red no")):
        assert mercado.tipo_de_cambio("GBp", "GBP") == (pytest.approx(0.01), "ok")
        assert mercado.tipo_de_cambio("GBP", "GBp") == (pytest.approx(100.0), "ok")


def test_un_estado_guardado_con_una_fila_como_lista_no_se_sirve_y_se_va_a_la_red(tmp_path):
    # La fila rota va en un estado que llega vacío: tampoco puede conservarse.
    roto = {nombre: {} for nombre in mercado.ESTADOS}
    roto["balance_sheet"] = {"Total Assets": [1.0]}
    mercado.cache.guardar(tmp_path, "estados", "MU", {"estados": roto})
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_estados_dobles())) as fabrica:
        estados, motivo = mercado.estados("MU")
    fabrica.assert_called()
    assert motivo == "ok"
    assert estados["income_stmt"].loc["Total Revenue"].iloc[0] == 2.5e11
    assert estados["balance_sheet"].empty


def test_una_identidad_guardada_sin_forma_de_diccionario_no_se_sirve(tmp_path):
    mercado.cache.guardar(tmp_path, "identidad", "MU", {"identidad": ["quoteType"]})
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)) as fabrica:
        identidad, motivo = mercado.identidad("MU")
    fabrica.assert_called()
    assert motivo == "ok" and identidad["quoteType"] == "EQUITY"


# Si cae sólo quoteSummary, llegan el tipo, la moneda y el precio, sin más.
PARCIAL = {"quoteType": "EQUITY", "currency": "USD", "regularMarketPrice": 990.0}


def test_una_identidad_parcial_trae_el_precio_nuevo_y_la_clasificacion_guardada(monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={**INFO, "sector": "Technology"})):
        mercado.identidad("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "identidad", timedelta(seconds=-1))
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=PARCIAL)) as fabrica:
        identidad, motivo = mercado.identidad("MU")
    fabrica.assert_called()
    assert motivo == "ok"
    assert identidad["regularMarketPrice"] == 990.0
    assert identidad["currentPrice"] is None
    assert (identidad["sector"], identidad["industry"], identidad["country"]) == (
        "Technology",
        "Semiconductors",
        "United States",
    )


def _retrasar(raiz, dias):
    """Como `_envejecer`, pero corre `dias` hacia atrás la hora del fichero y la
    de cada `desde`: como si todo lo guardado hubiera pasado `dias` antes."""

    def atras(iso):
        return (datetime.fromisoformat(iso) - timedelta(days=dias)).isoformat()

    for ruta in _escritos(raiz):
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        crudo["cuando"] = atras(crudo["cuando"])
        desde = crudo["datos"].get("desde", {})
        for nombre in desde:
            desde[nombre] = atras(desde[nombre])
        ruta.write_text(json.dumps(crudo), encoding="utf-8")


def test_pasado_el_tope_la_identidad_parcial_pierde_la_clasificacion(tmp_path, monkeypatch):
    # Lo rellenado se guarda con la hora nueva; si su tope contase desde ella,
    # el sector de un ticker reasignado se arrastraría sin límite.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={**INFO, "sector": "Technology"})):
        mercado.identidad("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "identidad", timedelta(seconds=-1))
    for dias in (3, 6, 9):
        _retrasar(tmp_path, 3)
        with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=PARCIAL)):
            identidad, motivo = mercado.identidad("MU")
        assert motivo == "ok" and identidad["regularMarketPrice"] == 990.0
        assert (identidad["sector"] is None) == (dias > 7), dias


def test_un_estado_conservado_caduca_a_los_30_dias_de_llegar_lleno_por_ultima_vez(
    tmp_path, monkeypatch
):
    # Lo conservado se guarda con la hora nueva; si su tope contase desde ella,
    # un estado que ya no se publica --o el de otra empresa, con un ticker
    # reasignado-- se serviría sin límite.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_seis_estados(1.0))):
        mercado.estados("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "estados", timedelta(seconds=-1))
    sin_flujos = {**_seis_estados(2.0), "cashflow": empty_df()}
    for dias in (7, 14, 21, 28, 35):
        _retrasar(tmp_path, 7)
        with patch.object(mercado.yf, "Ticker", return_value=_ticker(**sin_flujos)):
            estados, motivo = mercado.estados("MU")
        assert motivo == "ok"
        assert estados["cashflow"].empty == (dias > 30), dias


def test_unos_estados_guardados_sin_desde_cuentan_desde_su_hora(tmp_path, monkeypatch):
    # La forma de antes de `desde`: sólo los planos.
    planos = {nombre: mercado.estado_a_plano(df) for nombre, df in _seis_estados(1.0).items()}
    mercado.cache.guardar(tmp_path, "estados", "MU", {"estados": planos})
    monkeypatch.setitem(mercado.VALIDEZ, "estados", timedelta(seconds=-1))
    sin_flujos = {**_seis_estados(2.0), "cashflow": empty_df()}
    _retrasar(tmp_path, 25)
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**sin_flujos)):
        estados, _ = mercado.estados("MU")
    assert estados["cashflow"].loc["Total Revenue"].iloc[0] == 1.0
    # Ahora el `cashflow` conservado lleva la hora de la entrada vieja: 25 días.
    _retrasar(tmp_path, 7)
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**sin_flujos)):
        estados, motivo = mercado.estados("MU")
    assert motivo == "ok" and estados["cashflow"].empty


def test_los_fils_de_kuwait_son_milesimas_de_dinar():
    # NBK.KW cotiza en fils (KWF): mil fils, un dinar.
    with patch.object(mercado.yf, "Ticker", side_effect=AssertionError("a la red no")):
        assert mercado.tipo_de_cambio("KWF", "KWD") == (pytest.approx(0.001), "ok")


@pytest.mark.parametrize(
    "cierres", [[0.031, 0.0], [0.031, float("inf")]], ids=["ultimo_a_cero", "ultimo_infinito"]
)
def test_el_tipo_de_cambio_es_el_ultimo_cierre_finito_y_positivo(cierres):
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial(cierres)):
        assert mercado.tipo_de_cambio("TWD", "USD") == (pytest.approx(0.031), "ok")


@pytest.mark.parametrize("cierres", [[0.0], [float("inf")]], ids=["cero", "infinito"])
def test_sin_un_cierre_valido_no_se_sabe_el_tipo_de_cambio_ni_se_guarda(cierres, tmp_path):
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial(cierres)):
        assert mercado.tipo_de_cambio("TWD", "USD") == (None, "sin_red")
    assert _escritos(tmp_path) == []


@pytest.mark.parametrize("guardado", [None, "abc", 0, -1, "NaN"])
def test_un_tipo_de_cambio_guardado_sin_valor_valido_no_se_sirve(guardado, tmp_path):
    # `None` es la forma de antes, cuando un par sin cierres válidos se guardaba;
    # los demás, una caché que no escribió este código.
    mercado.cache.guardar(tmp_path, "tipo_de_cambio", "TWDUSD=X", {"valor": guardado})
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([0.0311])) as fabrica:
        assert mercado.tipo_de_cambio("TWD", "USD") == (pytest.approx(0.0311), "ok")
    fabrica.assert_called()


def test_sin_red_un_estado_conservado_no_sobrevive_a_su_tope(tmp_path, monkeypatch):
    # El respaldo de `_traer` mide la edad del fichero, que lo conservado
    # rejuvenece: sin mirar el `desde`, un estado conservado el día 29 se
    # serviría sin red hasta el 58.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_seis_estados(1.0))):
        mercado.estados("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "estados", timedelta(seconds=-1))
    _retrasar(tmp_path, 25)
    sin_flujos = {**_seis_estados(2.0), "cashflow": empty_df()}
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**sin_flujos)):
        assert not mercado.estados("MU")[0]["cashflow"].empty
    # Escritura de hace 6 días; el `cashflow` llegó lleno hace 31.
    _retrasar(tmp_path, 6)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")) as fabrica:
        estados, motivo = mercado.estados("MU")
    fabrica.assert_called()
    assert motivo == "ok"
    assert estados["cashflow"].empty
    assert estados["income_stmt"].loc["Total Revenue"].iloc[0] == 2.0


def test_sin_red_una_clasificacion_rellenada_no_sobrevive_a_su_tope(tmp_path, monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={**INFO, "sector": "Technology"})):
        mercado.identidad("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "identidad", timedelta(seconds=-1))
    _retrasar(tmp_path, 5)
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=PARCIAL)):
        assert mercado.identidad("MU")[0]["sector"] == "Technology"
    # Escritura de hace 3 días; el sector llegó hace 8.
    _retrasar(tmp_path, 3)
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")) as fabrica:
        identidad, motivo = mercado.identidad("MU")
    fabrica.assert_called()
    assert motivo == "ok"
    assert identidad["regularMarketPrice"] == 990.0
    assert (identidad["sector"], identidad["industry"], identidad["country"]) == (None, None, None)


def test_la_beta_con_par_regresa_el_precio_convertido():
    g = np.random.default_rng(7)
    m = g.normal(0.002, 0.02, 104)
    a = 2 * m + g.normal(0, 0.002, 104)
    # Un tipo de cambio constante no cambia ningún rendimiento: la beta es la misma.
    dobles = {
        "AMX": _con_historial(_cierres(a)),
        "^MXX": _con_historial(_cierres(m)),
        "USDMXN=X": _con_historial(_cierres(np.zeros(104))),
    }
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]) as fabrica:
        beta, motivo = mercado.beta("AMX", "^MXX", "USDMXN=X")
    assert motivo == "ok" and beta.bruta == pytest.approx(2.0, abs=0.1)
    assert {c.args[0] for c in fabrica.call_args_list} == {"AMX", "^MXX", "USDMXN=X"}


def test_la_beta_con_par_se_mide_con_el_precio_ya_convertido():
    # Con un tipo constante, la prueba de arriba no distingue si se convirtió.
    # Aquí el precio en dólares sólo tiene ruido y el tipo de cambio sigue al
    # índice: en pesos el activo se mueve con el IPC (beta cerca de 1); sin
    # convertir no tendría nada que ver con él (beta cerca de 0).
    g = np.random.default_rng(7)
    m = g.normal(0.002, 0.02, 104)
    dobles = {
        "AMX": _con_historial(_cierres(g.normal(0, 0.002, 104))),
        "^MXX": _con_historial(_cierres(m)),
        "USDMXN=X": _con_historial(_cierres(m)),
    }
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        beta, motivo = mercado.beta("AMX", "^MXX", "USDMXN=X")
    assert motivo == "ok" and beta.bruta == pytest.approx(1.0, abs=0.1)


def _dia(indice) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(indice).tz_localize(None).normalize()


def _par(diario, semanal):
    """Un par cuyo `history` da el diario o el semanal según el intervalo pedido.

    Como Yahoo, el diario de `period="2y"` empieza una semana después que el
    semanal (USDMXN=X, el 2026-10-25: el 28/10/2024 frente al 21/10/2024); con
    `start=`, desde ese día.
    """
    diario = pd.Series(diario, dtype="float64")

    def history(**pedido):
        if pedido.get("interval") != "1d":
            return pd.DataFrame({"Close": semanal})
        if diario.empty:
            return pd.DataFrame({"Close": diario})
        if "start" in pedido:
            desde = pd.Timestamp(pedido["start"])
        else:
            desde = _dia(semanal.index).min() + pd.offsets.Week(1)
        return pd.DataFrame({"Close": diario[_dia(diario.index) >= desde]})

    doble = _ticker()
    doble.history.side_effect = history
    return doble


def _par_de_yahoo(semanas, picos=()):
    """Un par como lo da Yahoo: `(diario, semanal)`, en la zona de Londres.

    El semanal, fechado el lunes, lleva el cierre del viernes. Cada vela diaria
    es una foto a medianoche: lleva el cierre del día hábil anterior, así que el
    diario va un día por detrás. El diario empieza una semana antes que el
    semanal, para que `start=` tenga qué devolver. En las semanas de `picos` el
    semanal sale un 30 % por encima, como el de CADUSD=X del 16/12/2024.
    """
    dias = pd.bdate_range(
        semanas[0] - pd.offsets.Week(1), periods=5 * (len(semanas) + 1), tz="Europe/London"
    )
    cierres = 0.70 * np.cumprod(1 + np.random.default_rng(3).normal(0, 0.005, len(dias)))
    diario = pd.Series(np.r_[0.70, cierres[:-1]], index=dias)
    # Los viernes de las semanas del semanal: el primero es el de la segunda del diario.
    semanal = pd.Series(cierres[9::5], index=semanas.tz_localize("Europe/London"))
    for semana in picos:
        semanal.iloc[semana] *= 1.30
    return diario, semanal


def _beta_con(par):
    """Activo y referencia de `_dobles_de_beta`, y la beta con `par` como CADUSD=X."""
    dobles = _dobles_de_beta()
    dobles["CADUSD=X"] = par
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        return mercado.beta("MU", "^GSPC", "CADUSD=X")


def _cierres_de(simbolo):
    return _dobles_de_beta()[simbolo].history.return_value["Close"]


def test_la_beta_con_par_descarta_la_semana_de_un_pico_del_semanal_de_yahoo():
    # El semanal de CADUSD=X marcó 0,911 la semana del 16/12/2024, entre dos de
    # 0,70 y 0,69, con el diario limpio: un +30 % y un −24 % que no existieron,
    # y RY.TO salía con una beta de 0,27 y un r² de 0,02.
    activo, indice = _cierres_de("MU"), _cierres_de("^GSPC")
    diario, semanal = _par_de_yahoo(activo.index, picos=(10,))
    beta, motivo = _beta_con(_par(diario, semanal))
    sin_el_pico = semanal.drop(semanal.index[10])
    esperada = mercado.regresion_beta(
        mercado.precio_convertido(activo, sin_el_pico), indice, "^GSPC"
    )
    assert motivo == "ok"
    assert beta.semanas == 103
    assert beta.bruta == pytest.approx(esperada.bruta)
    assert beta.r2 == pytest.approx(esperada.r2)


def test_la_beta_con_par_usa_el_cierre_de_la_semana_y_no_la_foto_del_diario():
    # Con el diario, que va un día por detrás, la beta de AMX salía 0,901 en
    # vez de 0,791. Sin picos no se descarta ninguna semana: la beta es la del
    # semanal de Yahoo.
    activo, indice = _cierres_de("MU"), _cierres_de("^GSPC")
    diario, semanal = _par_de_yahoo(activo.index)
    beta, motivo = _beta_con(_par(diario, semanal))
    esperada = mercado.regresion_beta(mercado.precio_convertido(activo, semanal), indice, "^GSPC")
    assert motivo == "ok"
    assert beta.semanas == 104
    assert beta.bruta == pytest.approx(esperada.bruta)
    assert beta.r2 == pytest.approx(esperada.r2)


def test_la_primera_semana_del_semanal_tiene_diario_con_que_compararse():
    # Con el diario de `period="2y"`, la primera semana no tenía con qué
    # compararse y se descartaba siempre: 103 semanas en vez de 104.
    diario, semanal = _par_de_yahoo(_cierres_de("MU").index)
    beta, motivo = _beta_con(_par(diario, semanal))
    assert motivo == "ok" and beta.semanas == 104


def test_sin_el_diario_del_par_no_hay_beta_ni_se_guarda(tmp_path):
    # Sin él no se pueden quitar los picos del semanal: es «no lo sé».
    _, semanal = _par_de_yahoo(_cierres_de("MU").index)
    assert _beta_con(_par([], semanal)) == (None, "sin_red")
    assert _escritos(tmp_path) == []


def test_la_beta_con_y_sin_par_no_comparten_cache(tmp_path):
    dobles = _dobles_de_beta()
    dobles["USDMXN=X"] = _con_historial(_cierres(np.zeros(104)))
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        mercado.beta("MU", "^GSPC")
        mercado.beta("MU", "^GSPC", "USDMXN=X")
    assert len(_escritos(tmp_path)) == 2


def test_sin_cierres_del_tipo_de_cambio_no_hay_beta_ni_se_guarda(tmp_path):
    dobles = _dobles_de_beta()
    dobles["USDMXN=X"] = _con_historial([])
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        assert mercado.beta("MU", "^GSPC", "USDMXN=X") == (None, "sin_red")
    assert _escritos(tmp_path) == []
