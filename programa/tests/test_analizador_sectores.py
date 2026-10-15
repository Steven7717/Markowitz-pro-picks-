import pytest

from analizador.sectores import YAHOO_A_GICS, sector_gics
from fundamentals.sectors import load_sectors


def test_la_tabla_traduce_a_los_nombres_gics_que_usa_el_panel():
    gics = set(load_sectors().values())
    # Once sectores GICS, once entradas: ninguno se queda sin traducir.
    assert set(YAHOO_A_GICS.values()) == gics


def test_una_empresa_del_sp500_usa_la_tabla_de_siempre():
    # Yahoo dice Technology y GICS Industrials: el panel de referencia está
    # hecho con la tabla, y es la que manda.
    assert sector_gics("UBER", "Technology", {"UBER": "Industrials"}) == (
        "Industrials",
        "sp500",
    )


@pytest.mark.parametrize("celda", [float("nan"), ""])
def test_una_celda_de_sector_vacia_recurre_a_yahoo(celda):
    assert sector_gics("X", "Technology", {"X": celda}) == ("Information Technology", "yahoo")


def test_fuera_del_sp500_se_traduce_el_de_yahoo():
    assert sector_gics("WALMEX.MX", "Consumer Defensive", {}) == ("Consumer Staples", "yahoo")


def test_un_sector_que_no_esta_en_la_tabla_no_se_adivina():
    assert sector_gics("XYZ", "Conglomerates", {}) == (None, "sin_sector")
    assert sector_gics("XYZ", None, {}) == (None, "sin_sector")
