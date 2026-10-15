"""La forma del ticker: el punto de una clase de acción frente al de una bolsa."""

import pytest

from analizador.resolver import MAX_TICKERS, normalizar, separar, tiene_sufijo


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("BRK.B", "BRK-B"),
        ("BF.B", "BF-B"),
        ("WALMEX.MX", "WALMEX.MX"),
        ("GFNORTEO.MX", "GFNORTEO.MX"),
        ("RY.TO", "RY.TO"),
        ("brk-b", "BRK-B"),
        ("walmex.mx", "WALMEX.MX"),
        ("  mu  ", "MU"),
        ("BRK.B.MX", "BRK-B.MX"),
        # Así escribe Yahoo las clases de acción canadienses.
        ("RCI.B.TO", "RCI-B.TO"),
        # MU es a la vez un ticker y el sufijo de Múnich.
        ("MU.MU", "MU.MU"),
        # El `&` es como Yahoo escribe la Ñ de Peñoles.
        ("pe&oles.mx", "PE&OLES.MX"),
        # El precio de la tabla cerrada: `V` es TSX Venture y también la clase
        # con voto de McCormick, así que `MKC.V` se lee como bolsa y Yahoo no
        # lo encuentra. Con guion funciona siempre, porque el guion no se toca.
        ("MKC.V", "MKC.V"),
        ("MKC-V", "MKC-V"),
        ("A" * 20, "A" * 20),
        # Lo que se pega de una web o de Excel: ancho completo e invisibles.
        ("ＭＵ", "MU"),
        ("\ufeffMU\u200b", "MU"),
        # Índices, divisas y cripto pasan la forma: es Yahoo quien dirá que no
        # son acciones, y la pantalla lo dirá con su motivo.
        ("^GSPC", "^GSPC"),
        ("EURUSD=X", "EURUSD=X"),
        ("BTC-USD", "BTC-USD"),
    ],
)
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", "BRK B", "MU;", "A..B", "WALMEX.", "-A", "&A", "A&", "A" * 21, None, 3],
)
def test_lo_que_no_tiene_forma_de_ticker_se_rechaza(entrada):
    assert normalizar(entrada) is None


def test_las_dos_funciones_de_siempre_rompen_la_bmv_y_por_eso_no_se_usan():
    # Documenta la trampa del spec: las dos funciones existentes sirven al
    # universo del S&P 500 y al acta, y ahí están bien; aquí romperían WALMEX.
    from aprobacion.acta import _FORMA_TICKER
    from research.universe import normalise_ticker

    assert normalise_ticker("WALMEX.MX") == "WALMEX-MX"
    assert _FORMA_TICKER.match("WALMEX.MX") is None


def test_separar_por_comas_y_espacios_sin_repetir():
    assert separar("mu, TSM  walmex.mx,MU\nbrk.b") == (
        ["MU", "TSM", "WALMEX.MX", "BRK-B"],
        [],
    )


def test_separar_por_tabuladores():
    assert separar("MU\tTSM JPM") == (["MU", "TSM", "JPM"], [])


def test_separar_devuelve_los_invalidos_tal_como_se_escribieron():
    assert separar("MU, A..B MU;") == (["MU"], ["A..B", "MU;"])


def test_separar_no_repite_los_invalidos():
    assert separar("A..B A..B") == ([], ["A..B"])


def test_separar_parte_por_el_espacio_aunque_parezca_una_clase_de_accion():
    # `BRK B` son dos tickers, y `B` es Barrick. No hay forma de saber qué
    # quiso decir quien lo escribió; N2 enseña el nombre largo de cada fila
    # para que se note.
    assert separar("BRK B") == (["BRK", "B"], [])


def test_separar_limpia_los_invisibles_de_lo_que_se_pega():
    assert separar("MU\u200b, \ufeffTSM") == (["MU", "TSM"], [])


def test_separar_limpia_las_marcas_de_direccion():
    # La marca de izquierda a derecha se cuela al copiar de algunas webs.
    assert separar("MU\u200e, TSM") == (["MU", "TSM"], [])


def test_separar_lleva_el_ancho_completo_a_su_forma_normal():
    # NFKC convierte también la coma de ancho completo, y con eso separa.
    assert separar("ＭＵ，ＴＳＭ") == (["MU", "TSM"], [])


@pytest.mark.parametrize("vacio", ["", "  ,  ", None])
def test_separar_nada(vacio):
    assert separar(vacio) == ([], [])


def test_el_tope_es_el_tamano_del_top_de_candidatos():
    from ranking.criterio import TAMANO_TOP

    assert MAX_TICKERS == TAMANO_TOP


@pytest.mark.parametrize(
    "ticker, esperado",
    [("WALMEX.MX", True), ("RY.TO", True), ("BRK-B", False), ("MU", False)],
)
def test_tiene_sufijo(ticker, esperado):
    assert tiene_sufijo(ticker) is esperado


from datetime import timedelta  # noqa: E402
from unittest.mock import patch  # noqa: E402

from analizador import resolver  # noqa: E402
from analizador.resolver import Identidad, clase_de, identidad_desde_info  # noqa: E402

INFO_MU = {
    "quoteType": "EQUITY",
    "exchange": "NMS",
    "currency": "USD",
    "financialCurrency": "USD",
    "sector": "Technology",
    "industry": "Semiconductors",
    "country": "United States",
    "longName": "Micron Technology, Inc.",
    "currentPrice": 914.13,
    "regularMarketPrice": 914.13,
    "regularMarketTime": 1_791_835_140,
}


def test_la_identidad_lee_lo_que_hace_falta():
    i = identidad_desde_info("MU", INFO_MU)
    assert (i.tipo, i.bolsa, i.moneda, i.moneda_estados) == ("EQUITY", "NMS", "USD", "USD")
    assert (i.sector, i.industria, i.pais) == ("Technology", "Semiconductors", "United States")
    assert i.nombre == "Micron Technology, Inc."
    assert i.precio == 914.13
    assert i.hora == "2026-10-12T19:59:00+00:00"


def test_sin_precio_actual_la_identidad_toma_el_de_mercado():
    info = {**INFO_MU, "currentPrice": None, "regularMarketPrice": 769.6}
    assert identidad_desde_info("SPY", info).precio == 769.6


def test_la_moneda_de_los_estados_cae_a_la_del_precio():
    info = {k: v for k, v in INFO_MU.items() if k != "financialCurrency"}
    assert identidad_desde_info("MU", info).moneda_estados == "USD"


def _identidad(tipo="EQUITY"):
    return identidad_desde_info("X", {**INFO_MU, "quoteType": tipo})


@pytest.mark.parametrize(
    "tipo, formularios, esperado",
    [
        ("ETF", ("10-K",), ("etf", None)),
        ("EQUITY", ("10-K",), ("sec", None)),
        ("EQUITY", ("20-F",), ("extranjera_sec", None)),
        # RY presenta 40-F y edgartools la marca `is_foreign = False`: la clase
        # sale de los formularios, no de esa marca.
        ("EQUITY", ("40-F",), ("extranjera_sec", None)),
        ("EQUITY", (), ("sin_sec", None)),
        ("INDEX", (), (None, "tipo_no_soportado")),
        ("MUTUALFUND", (), (None, "tipo_no_soportado")),
        ("CRYPTOCURRENCY", (), (None, "tipo_no_soportado")),
        (None, (), (None, "tipo_no_soportado")),
    ],
)
def test_la_clase(tipo, formularios, esperado):
    assert clase_de(_identidad(tipo), formularios) == esperado


@pytest.fixture
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "RAIZ_CACHE", tmp_path)
    monkeypatch.setenv("EDGAR_IDENTITY", "pruebas@example.com")
    return tmp_path


def test_los_formularios_se_preguntan_una_vez_y_se_guardan(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=("10-K",)) as consulta:
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")
    consulta.assert_called_once_with("MU")


def test_un_ticker_que_edgar_no_conoce_no_presenta_nada_y_se_guarda(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=()):
        assert resolver.formularios_sec("ZZZZ") == ((), "ok")
    assert list(cache_aislada.rglob("*.json"))


def test_sin_red_y_sin_nada_guardado_lo_dice(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=None):
        assert resolver.formularios_sec("MU") == (None, "sin_red_edgar")
    assert list(cache_aislada.rglob("*.json")) == []


def test_sin_red_vale_lo_guardado_aunque_haya_caducado(cache_aislada, monkeypatch):
    with patch.object(resolver, "_consultar_sec", return_value=("10-K",)):
        resolver.formularios_sec("MU")
    monkeypatch.setattr(resolver, "VALIDEZ_FORMULARIOS", timedelta(seconds=-1))
    with patch.object(resolver, "_consultar_sec", return_value=None):
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")


def test_sin_identidad_de_edgar_no_se_pregunta(cache_aislada, monkeypatch):
    monkeypatch.delenv("EDGAR_IDENTITY")
    with patch.object(resolver, "_consultar_sec", side_effect=AssertionError("no")):
        assert resolver.formularios_sec("MU") == (None, "sin_identidad_edgar")


def _resolver(ticker, info, formularios=("10-K",)):
    with patch.object(resolver.mercado, "identidad", return_value=(info, "ok")), patch.object(
        resolver, "formularios_sec", return_value=(formularios, "ok")
    ) as sec:
        return resolver.resolver(ticker), sec


def test_resolver_una_empresa_de_la_sec():
    resuelto, _ = _resolver("MU", INFO_MU)
    assert (resuelto.ticker, resuelto.clase, resuelto.motivo) == ("MU", "sec", None)
    assert resuelto.identidad.nombre == "Micron Technology, Inc."


def test_un_ticker_con_sufijo_de_bolsa_no_se_pregunta_a_edgar():
    resuelto, sec = _resolver("WALMEX.MX", {**INFO_MU, "currency": "MXN"})
    assert resuelto.clase == "sin_sec"
    sec.assert_not_called()


def test_un_etf_no_se_pregunta_a_edgar():
    resuelto, sec = _resolver("SPY", {**INFO_MU, "quoteType": "ETF"})
    assert resuelto.clase == "etf"
    sec.assert_not_called()


def test_si_yahoo_no_devuelve_nada_el_motivo_es_el_suyo():
    with patch.object(resolver.mercado, "identidad", return_value=(None, "sin_red")):
        resuelto = resolver.resolver("ZZZZQ")
    assert (resuelto.clase, resuelto.identidad, resuelto.motivo) == (None, None, "sin_red")


def test_un_indice_tiene_identidad_pero_no_clase():
    resuelto, _ = _resolver("^GSPC", {**INFO_MU, "quoteType": "INDEX"})
    assert resuelto.clase is None and resuelto.motivo == "tipo_no_soportado"
    assert resuelto.identidad.tipo == "INDEX"


def test_si_edgar_no_responde_no_se_adivina_la_clase():
    with patch.object(resolver.mercado, "identidad", return_value=(INFO_MU, "ok")), patch.object(
        resolver, "formularios_sec", return_value=(None, "sin_red_edgar")
    ):
        resuelto = resolver.resolver("MU")
    # Tratar a MU como `sin_sec` la valoraría con yfinance en vez de con EDGAR
    # sin decirlo: es mejor no tener clase que tener la equivocada.
    assert resuelto.clase is None and resuelto.motivo == "sin_red_edgar"
