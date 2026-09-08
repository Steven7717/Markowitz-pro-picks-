from noticias import macro
from noticias.agenda import Evento


def test_son_cuatro():
    """Cuatro y no cuarenta: una lista larga de enlaces es una que nadie abre."""
    assert len(macro.PUNTEROS) == 4


def test_ninguno_lleva_fecha():
    """Es LA decision del sub-proyecto: punteros a la fuente, no fechas.

    Copiar fechas al repo crea algo que caduca en silencio; un enlace roto se
    ve roto y una fecha vieja no.
    """
    assert all(e.cuando is None for e in macro.PUNTEROS)


def test_todos_llevan_enlace_oficial():
    oficiales = ("federalreserve.gov", "bls.gov", "bea.gov")
    for e in macro.PUNTEROS:
        assert e.url and e.url.startswith("https://")
        assert any(d in e.url for d in oficiales), e.url


def test_ninguno_lleva_ticker():
    assert all(e.ticker is None for e in macro.PUNTEROS)


def test_todos_son_de_clase_macro():
    assert all(e.clase == "macro" for e in macro.PUNTEROS)


def test_el_detalle_dice_la_cadencia():
    """Sin cadencia el puntero no orienta: hay que saber si es mensual."""
    for e in macro.PUNTEROS:
        assert e.detalle.strip()


def test_son_Evento_como_los_del_activo():
    """Misma estructura, para que la pantalla no necesite dos caminos."""
    assert all(isinstance(e, Evento) for e in macro.PUNTEROS)
