import pytest

from noticias import criterio


def test_un_tipo_material_es_material():
    assert criterio.material(("4.02",)) is True


def test_un_tipo_de_rutina_no_es_material():
    assert criterio.material(("8.01",)) is False


def test_varios_items_y_uno_material_basta():
    """El caso mas frecuente que existe, y el que rompe todo si se modela mal.

    Un anuncio de resultados llega SIEMPRE como "2.02,9.01": el 2.02 son los
    resultados y el 9.01 los estados y anexos que los acompanan. Si la
    materialidad exigiera que TODOS los tipos estuvieran en la lista, o si se
    comparase la cadena entera contra la lista, cada anuncio de resultados
    quedaria plegado entre la rutina.
    """
    assert criterio.material(("2.02", "9.01")) is True


def test_varios_items_y_ninguno_material():
    """Contrapeso del anterior: que no pase por 'dos items = material'."""
    assert criterio.material(("7.01", "9.01")) is False


def test_sin_items_no_es_material():
    assert criterio.material(()) is False


def test_hay_descripcion_para_cada_tipo_material():
    """Un tipo material sin texto saldria destacado y mudo en la pantalla."""
    faltan = criterio.MATERIALES - set(criterio.DESCRIPCIONES)
    assert faltan == set(), f"sin descripcion: {sorted(faltan)}"


def test_el_402_esta_en_la_lista():
    """El peor hecho posible para una cartera fundamental.

    Se fija aparte porque es el que justifica el criterio entero: la empresa
    declarando que sus propias cuentas anteriores no son fiables.
    """
    assert "4.02" in criterio.MATERIALES


@pytest.mark.parametrize("tipo", ["7.01", "8.01", "9.01"])
def test_la_rutina_queda_fuera(tipo):
    assert tipo not in criterio.MATERIALES
