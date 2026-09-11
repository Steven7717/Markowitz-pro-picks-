"""La cache por hash de contenido, y la degradacion del cliente."""

import json

from interprete import cache, cliente


def test_la_clave_es_estable_entre_procesos():
    """hashlib y no hash(): Python aleatoriza el hash de las cadenas entre
    procesos, asi que hash() daria una clave distinta en cada arranque y la
    cache no acertaria nunca. Esa leccion ya costo una cache envenenada --
    ver `fundamentals/fetch.py:_cache_path`."""
    assert cache.clave({"a": 1}) == cache.clave({"a": 1})
    assert len(cache.clave({"a": 1})) == 64


def test_el_orden_de_las_claves_no_cambia_el_hash():
    assert cache.clave({"a": 1, "b": 2}) == cache.clave({"b": 2, "a": 1})


def test_un_contenido_distinto_da_otra_clave():
    assert cache.clave({"a": 1}) != cache.clave({"a": 2})


def test_ida_y_vuelta(tmp_path):
    cache.escribir("hechos", "abc", {"juicios": []}, tmp_path)
    assert cache.leer("hechos", "abc", tmp_path) == {"juicios": []}


def test_lo_que_no_esta_es_un_fallo_de_cache(tmp_path):
    assert cache.leer("hechos", "nada", tmp_path) is None


def test_un_fichero_truncado_es_un_fallo_de_cache_y_se_borra(tmp_path):
    """Una corrida muerta a mitad de escritura deja un JSON truncado. Aqui si
    vale borrarlo y seguir: una cache rota es un fallo de cache. **En
    `archivo.py` sera lo contrario** -- alli es historial perdido."""
    fichero = tmp_path / "hechos" / "abc.json"
    fichero.parent.mkdir(parents=True)
    fichero.write_text('{"juicios": [', encoding="utf-8")
    assert cache.leer("hechos", "abc", tmp_path) is None
    assert not fichero.exists()


def test_un_json_que_no_es_objeto_tambien(tmp_path):
    fichero = tmp_path / "hechos" / "abc.json"
    fichero.parent.mkdir(parents=True)
    fichero.write_text("[1, 2, 3]", encoding="utf-8")
    assert cache.leer("hechos", "abc", tmp_path) is None


def test_la_escritura_no_deja_temporales(tmp_path):
    cache.escribir("hechos", "abc", {"x": 1}, tmp_path)
    assert list((tmp_path / "hechos").glob("*.tmp")) == []


def test_sin_clave_el_cliente_devuelve_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cliente.hay_clave() is False
    assert cliente.preguntar("sistema", [{"role": "user", "content": "hola"}], dict) is None


def test_con_clave_falsa_se_usa_el_cliente_inyectado(monkeypatch):
    """El cliente se inyecta para probar sin red y sin clave. Si `preguntar`
    construyera el suyo pese a recibir uno, esto tocaria la API de verdad."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class _Respuesta:
        parsed_output = {"ok": True}

    class _Mensajes:
        def parse(self, **_kwargs):
            return _Respuesta()

    class _Falso:
        messages = _Mensajes()

    assert cliente.preguntar("s", [], dict, cliente=_Falso()) == {"ok": True}


def test_una_respuesta_sin_parsear_es_none():
    class _Respuesta:
        parsed_output = None

    class _Mensajes:
        def parse(self, **_kwargs):
            return _Respuesta()

    class _Falso:
        messages = _Mensajes()

    assert cliente.preguntar("s", [], dict, cliente=_Falso()) is None
