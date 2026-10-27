"""El gráfico de TradingView: el símbolo y el HTML del widget."""

import json
import re

import pytest

from analizador import grafico


@pytest.mark.parametrize(
    "ticker, bolsa, simbolo",
    [
        ("MU", "NMS", "NASDAQ:MU"),
        ("DUOL", "NGM", "NASDAQ:DUOL"),
        ("JPM", "NYQ", "NYSE:JPM"),
        ("BRK-B", "NYQ", "NYSE:BRK.B"),
        ("BF-B", "NYQ", "NYSE:BF.B"),
        ("SPY", "PCX", "AMEX:SPY"),
        ("WALMEX.MX", "MEX", "BMV:WALMEX"),
        ("PE&OLES.MX", "MEX", "BMV:PE&OLES"),
        ("RY.TO", "TOR", "TSX:RY"),
        ("7203.T", "JPX", "TSE:7203"),
        # Sin sufijo es de EE. UU.: si no se sabe la bolsa, va sin prefijo.
        ("MU", None, "MU"),
        # Con sufijo y sin prefijo conocido no hay símbolo: quitarle el sufijo
        # daría otra empresa (`BA.L`, BAE, sería `BA`, Boeing).
        ("BA.L", "LSE", None),
        ("SAP.DE", None, None),
    ],
)
def test_el_simbolo_de_tradingview(ticker, bolsa, simbolo):
    assert grafico.simbolo(ticker, bolsa) == simbolo


def _config(html: str) -> dict:
    return json.loads(re.search(r"<script[^>]*>\s*(\{.*?\})\s*</script>", html, re.S).group(1))


def test_el_widget_lleva_el_simbolo_el_tema_y_el_castellano():
    config = _config(grafico.html("NYSE:BRK.B", oscuro=True))
    assert config["symbol"] == "NYSE:BRK.B"
    assert config["theme"] == "dark" and config["locale"] == "es"
    assert config["allow_symbol_change"] is False
    assert _config(grafico.html("NASDAQ:MU", oscuro=False))["theme"] == "light"


def test_sin_conexion_el_widget_lo_dice():
    html = grafico.html("NASDAQ:MU", oscuro=True)
    assert 'onerror="' in html and "No se pudo cargar el gráfico" in html


def test_el_widget_ocupa_todo_el_marco():
    # Con `autosize`, TradingView reescribe el contenedor a `height:100%`: sin
    # altura en html y body, el gráfico salía de 150 píxeles en un marco de 520.
    assert "html,body{height:100%" in grafico.html("NASDAQ:MU", oscuro=True)


def test_la_bmv_no_se_incrusta_y_se_enlaza_a_tradingview():
    # Con BMV:WALMEX el widget dice «Símbolo solo disponible en TradingView»
    # (2026-10-26, al planear N2).
    assert not grafico.en_widget("WALMEX.MX", "MEX")
    assert grafico.en_widget("MU", "NMS") and grafico.en_widget("MU", None)
    assert grafico.enlace("WALMEX.MX", "MEX") == (
        "Ver BMV:WALMEX en TradingView",
        "https://es.tradingview.com/symbols/BMV-WALMEX/",
    )


@pytest.mark.parametrize(
    "ticker, bolsa",
    [("T.TO", "TOR"), ("BA.L", "LSE"), ("RY.TO", "TOR"), ("SHEL.L", "LSE"), ("7203.T", "JPX")],
)
def test_un_ticker_de_fuera_no_se_incrusta_si_su_bolsa_no_esta_comprobada(ticker, bolsa):
    # Sin prefijo, el widget toma el ticker por uno de EE. UU.: `T.TO` (TELUS)
    # enseñaba AT&T, y `BA.L` (BAE) enseñaba Boeing.
    assert not grafico.en_widget(ticker, bolsa)


def test_el_enlace_de_fuera_lleva_a_la_empresa_y_no_a_su_homonima():
    # Con prefijo, a su página en TradingView (TSX:T es TELUS, comprobado el
    # 2026-10-27); sin él, a Yahoo, que no confunde porque lleva el sufijo.
    assert grafico.enlace("T.TO", "TOR") == (
        "Ver TSX:T en TradingView",
        "https://es.tradingview.com/symbols/TSX-T/",
    )
    assert grafico.enlace("BA.L", "LSE") == (
        "Ver BA.L en Yahoo Finanzas",
        "https://finance.yahoo.com/quote/BA.L/",
    )


def test_nada_del_simbolo_puede_cerrar_la_etiqueta_del_script():
    html = grafico.html("</script><img src=x>", oscuro=True)
    assert "</script><img" not in html


def test_lo_que_se_dice_debajo():
    assert "ninguna mostró ventaja después de costes" in grafico.ESTUDIO_D
    avisos = grafico.avisos("MU", "NMS")
    assert len(avisos) == 1 and "TradingView sabe qué ticker" in avisos[0]
    bmv = grafico.avisos("WALMEX.MX", "MEX")
    assert "no se incrusta" in bmv[0] and "TradingView" in bmv[0]
    assert any("15–20 minutos" in aviso for aviso in bmv)
    londres = grafico.avisos("BA.L", "LSE")
    assert len(londres) == 1 and "Yahoo Finanzas" in londres[0]
