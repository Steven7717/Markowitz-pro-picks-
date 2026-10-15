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
    "entrada", ["", "   ", "BRK B", "MU;", "A..B", "WALMEX.", "-A", "A" * 21, None, 3]
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


def test_separar_devuelve_los_invalidos_tal_como_se_escribieron():
    assert separar("MU, A..B MU;") == (["MU"], ["A..B", "MU;"])


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
