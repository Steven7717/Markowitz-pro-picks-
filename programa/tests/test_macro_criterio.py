# tests/test_macro_criterio.py
from fundamentals.sectors import load_sectors
from macro import criterio

FASES = {"recuperacion", "expansion", "desaceleracion", "contraccion"}


def test_las_cuatro_fases_y_ninguna_mas():
    assert set(criterio.SECTORES_POR_FASE) == FASES


def test_cada_sector_del_mapa_existe_en_la_tabla_gics():
    """Un nombre mal escrito no inclinaría nada y no daría ningún error."""
    conocidos = set(load_sectors().values())
    for fase, listas in criterio.SECTORES_POR_FASE.items():
        for sector in listas["favorecidos"] + listas["desfavorecidos"]:
            assert sector in conocidos, (fase, sector)


def test_ningun_sector_es_a_la_vez_favorecido_y_desfavorecido():
    for fase, listas in criterio.SECTORES_POR_FASE.items():
        assert not set(listas["favorecidos"]) & set(listas["desfavorecidos"]), fase


def test_cada_fase_tiene_las_dos_listas_no_vacias():
    for listas in criterio.SECTORES_POR_FASE.values():
        assert set(listas) == {"favorecidos", "desfavorecidos"}
        assert listas["favorecidos"] and listas["desfavorecidos"]


def test_regiones_y_su_defecto():
    assert set(criterio.REGIONES) == {"usa", "mex", "eurozona", "china", "g7"}
    assert criterio.REGION_POR_DEFECTO == "usa"
    assert criterio.REGIONES["eurozona"] == "G4E"


def test_la_inclinacion_es_pequena():
    """El compuesto es un z dentro del sector: 0,25 es un cuarto de desviación."""
    assert 0 < criterio.INCLINACION <= 0.5
