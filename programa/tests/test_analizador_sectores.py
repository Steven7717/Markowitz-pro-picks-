from analizador.sectores import YAHOO_A_GICS, sector_gics
from fundamentals.sectors import load_sectors


def test_la_tabla_traduce_a_los_nombres_gics_que_usa_el_panel():
    gics = set(load_sectors().values())
    assert set(YAHOO_A_GICS.values()) <= gics
    # Once sectores GICS, once entradas: ninguno se queda sin traducir.
    assert set(YAHOO_A_GICS.values()) == gics


def test_una_empresa_del_sp500_usa_la_tabla_de_siempre():
    # Aunque Yahoo diga otra cosa: el panel de referencia está hecho con ésta.
    assert sector_gics("MU", "Healthcare", {"MU": "Information Technology"}) == (
        "Information Technology",
        "sp500",
    )


def test_fuera_del_sp500_se_traduce_el_de_yahoo():
    assert sector_gics("WALMEX.MX", "Consumer Defensive", {}) == ("Consumer Staples", "yahoo")


def test_un_sector_que_no_esta_en_la_tabla_no_se_adivina():
    assert sector_gics("XYZ", "Conglomerates", {}) == (None, "sin_sector")
    assert sector_gics("XYZ", None, {}) == (None, "sin_sector")
