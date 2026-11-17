# tests/test_macro_textos.py
from macro import textos
from macro.criterio import REGIONES, SECTORES_POR_FASE


def test_cada_fase_y_region_tiene_nombre():
    assert set(textos.NOMBRE_FASE) == set(SECTORES_POR_FASE)
    assert set(textos.NOMBRE_REGION) == set(REGIONES)
    assert textos.NOMBRE_REGION["eurozona"] == "Eurozona (4 grandes)"


def test_cada_sector_del_mapa_tiene_su_porque():
    for fase, listas in SECTORES_POR_FASE.items():
        for sector in listas["favorecidos"] + listas["desfavorecidos"]:
            assert textos.POR_QUE[fase][sector].strip(), (fase, sector)
            assert sector in textos.NOMBRE_SECTOR


def test_cada_motivo_tiene_frase():
    for motivo in ("indeterminada", "serie_corta", "dato_rancio",
                   "sin_red", "serie_desconocida", "respuesta_ilegible",
                   "serie_con_huecos"):
        assert textos.MOTIVO[motivo].strip()


def test_resumen_sin_macro():
    assert textos.etiqueta_corrida(None) == "sin macro"


def test_resumen_con_macro():
    bloque = {"region": "usa", "fase": "recuperacion", "mes_dato": "2026-10-01",
              "inclinacion": 0.25, "entradas": ["JPM"], "salidas": ["NVDA"]}
    assert textos.etiqueta_corrida(bloque) == "con macro: Recuperación (Estados Unidos, oct 2026)"
    frase = textos.lo_que_movio(bloque)
    assert "JPM" in frase and "NVDA" in frase


def test_lo_que_movio_sin_cambios_lo_dice():
    bloque = {"region": "usa", "fase": "expansion", "mes_dato": "2026-10-01",
              "inclinacion": 0.25, "entradas": [], "salidas": []}
    assert "no cambió" in textos.lo_que_movio(bloque)


def test_ajuste_de_ficha():
    assert textos.ajuste_ficha(0.25) == "La macro la subió (+0,25)."
    assert textos.ajuste_ficha(-0.25) == "La macro la bajó (−0,25)."
    assert textos.ajuste_ficha(0.0) == "La macro no la tocó."
    assert textos.ajuste_ficha(None) is None
