from datetime import datetime, timedelta

import pytest

from noticias import cache


@pytest.fixture
def dir_cache(tmp_path):
    return tmp_path / ".cache"


def test_guarda_y_recupera(dir_cache):
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    assert guardado.datos == {"a": 1}
    assert guardado.vigente is True


def test_lo_caducado_vuelve_marcado_pero_vuelve(dir_cache):
    """Sin conexion, un dato viejo es mejor que nada. Mentir sobre su edad, no."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(seconds=-1))
    assert guardado.datos == {"a": 1}
    assert guardado.vigente is False


def test_lo_que_no_existe_da_None(dir_cache):
    assert cache.leer(dir_cache, "prensa", "ZZZZ", validez=timedelta(hours=1)) is None


def test_siempre_trae_la_hora_de_descarga(dir_cache):
    """La pantalla la ensena SIEMPRE, no solo cuando esta vieja."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    assert isinstance(guardado.cuando, datetime)
    assert guardado.cuando.tzinfo is not None


def test_cada_fuente_tiene_su_propio_hueco(dir_cache):
    """Prensa y hechos del mismo ticker no deben pisarse."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"quien": "prensa"})
    cache.guardar(dir_cache, "hechos", "AAPL", {"quien": "hechos"})
    p = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    h = cache.leer(dir_cache, "hechos", "AAPL", validez=timedelta(hours=1))
    assert p.datos["quien"] == "prensa"
    assert h.datos["quien"] == "hechos"


def test_un_fichero_corrupto_no_revienta(dir_cache):
    """Una cache se regenera; caerse por ella no tiene sentido."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    ruta = next(dir_cache.rglob("*.json"))
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1)) is None


def test_un_ticker_con_barras_no_escapa_del_directorio(dir_cache):
    """El ticker llega del libro; nunca debe componer una ruta a pelo."""
    cache.guardar(dir_cache, "prensa", "../../evil", {"a": 1})
    assert not (dir_cache.parent.parent / "evil.json").exists()
    escritos = list(dir_cache.rglob("*.json"))
    assert len(escritos) == 1
    assert dir_cache in escritos[0].parents


def test_dos_claves_distintas_no_se_pisan_al_sanear(dir_cache):
    """'A/B' y 'A_B' se sanean igual; sin digest acabarian en el mismo fichero."""
    cache.guardar(dir_cache, "prensa", "A/B", {"quien": "barra"})
    cache.guardar(dir_cache, "prensa", "A_B", {"quien": "guion"})
    a = cache.leer(dir_cache, "prensa", "A/B", validez=timedelta(hours=1))
    b = cache.leer(dir_cache, "prensa", "A_B", validez=timedelta(hours=1))
    assert a.datos["quien"] == "barra"
    assert b.datos["quien"] == "guion"


def test_las_validez_declaradas():
    assert cache.VALIDEZ["prensa"] == timedelta(hours=1)
    assert cache.VALIDEZ["hechos"] == timedelta(hours=1)
    assert cache.VALIDEZ["agenda"] == timedelta(days=1)
