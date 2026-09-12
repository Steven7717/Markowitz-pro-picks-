"""La llamada a Anthropic y su degradacion.

Estos tres vivian en `test_interprete_cache.py`, junto a los de una cache que
no llego a usar nadie. Al borrar aquella se quedan aqui, que es donde debian
haber estado: `cliente.py` y `cache.py` eran dos modulos distintos compartiendo
un fichero de pruebas.
"""

from interprete import cliente


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
