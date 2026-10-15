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
