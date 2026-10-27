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
        # Una bolsa que no está en la tabla va sin prefijo, y TradingView lo resuelve.
        ("RY.TO", "TOR", "RY"),
        ("7203.T", "JPX", "7203"),
        ("MU", None, "MU"),
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
    assert not grafico.en_widget("MEX")
    assert grafico.en_widget("NMS") and grafico.en_widget(None)
    assert grafico.enlace("BMV:WALMEX") == "https://es.tradingview.com/symbols/BMV-WALMEX/"


def test_nada_del_simbolo_puede_cerrar_la_etiqueta_del_script():
    html = grafico.html("</script><img src=x>", oscuro=True)
    assert "</script><img" not in html


def test_lo_que_se_dice_debajo():
    assert "ninguna mostró ventaja después de costes" in grafico.ESTUDIO_D
    avisos = grafico.avisos("NMS")
    assert len(avisos) == 1 and "TradingView sabe qué ticker" in avisos[0]
    bmv = grafico.avisos("MEX")
    assert "sólo en su web" in bmv[0] and any("15–20 minutos" in aviso for aviso in bmv)
