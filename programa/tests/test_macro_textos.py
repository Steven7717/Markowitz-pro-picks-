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


def test_cada_motivo_de_fred_tiene_frase_y_no_nombra_a_la_ocde():
    for motivo in ("sin_red", "serie_desconocida", "respuesta_ilegible"):
        assert textos.MOTIVO_FRED[motivo].strip()
        assert "OCDE" not in textos.MOTIVO_FRED[motivo]


def test_indeterminada_vale_para_los_dos_casos():
    frase = textos.MOTIVO["indeterminada"]
    assert "no se movió" in frase and "desmiente" in frase


def test_meses_en_fase_singular_y_plural():
    assert textos.lleva_meses(1) == "Lleva 1 mes en esta fase."
    assert textos.lleva_meses(5) == "Lleva 5 meses en esta fase."


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
    for basura in ("0.25", [], True, float("nan")):
        assert textos.ajuste_ficha(basura) is None


def test_un_bloque_raro_no_revienta_nada():
    raro = {"region": "marte", "fase": "caos", "mes_dato": "no es una fecha"}
    assert "marte" in textos.etiqueta_corrida(raro) and "caos" in textos.etiqueta_corrida(raro)
    assert "no es una fecha" in textos.etiqueta_corrida(raro)
    assert "no cambió" in textos.lo_que_movio(raro)
    assert textos.mes_legible("no es una fecha") == "no es una fecha"
    assert textos.mes_legible(None) == "None"


def test_un_bloque_que_no_es_un_dict_cuenta_como_sin_macro():
    for basura in ([], "texto", 3, {}):
        assert textos.etiqueta_corrida(basura) == "sin macro"
    assert textos.lo_que_movio(None)
    assert textos.lo_que_movio([1])


def test_un_dict_sin_fase_valida_cuenta_como_sin_macro():
    sin_macro = textos.lo_que_movio(None)
    for bloque in ({"foo": 1}, {"fase": None}, {"fase": ""}, {"fase": ["expansion"]},
                   {"region": "usa", "mes_dato": "2026-10-01"}):
        assert not textos.lleva_macro(bloque)
        assert textos.etiqueta_corrida(bloque) == "sin macro"
        assert textos.lo_que_movio(bloque) == sin_macro


def test_entradas_y_salidas_ausentes_son_listas_vacias():
    bloque = {"region": "usa", "fase": "expansion", "mes_dato": "2026-10-01"}
    assert "no cambió" in textos.lo_que_movio(bloque)


def test_cifra_usa_coma_decimal():
    assert textos.cifra(0.25) == "0,25"
