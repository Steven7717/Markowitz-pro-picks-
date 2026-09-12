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
    r = cliente.preguntar("sistema", [{"role": "user", "content": "hola"}], dict)
    assert r.salida is None


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

    r = cliente.preguntar("s", [], dict, cliente=_Falso())
    assert r.salida == {"ok": True}


def test_una_respuesta_sin_parsear_es_none():
    class _Respuesta:
        parsed_output = None

    class _Mensajes:
        def parse(self, **_kwargs):
            return _Respuesta()

    class _Falso:
        messages = _Mensajes()

    r = cliente.preguntar("s", [], dict, cliente=_Falso())
    assert r.salida is None


def test_sin_clave_se_dice_por_que(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = cliente.preguntar("s", [], dict)
    assert r.salida is None
    assert "clave" in r.problema.lower()


def test_una_respuesta_buena_trae_sus_tokens():
    class _Uso:
        input_tokens, output_tokens = 1000, 200

    class _Respuesta:
        parsed_output = {"ok": True}
        usage = _Uso()

    class _Falso:
        class messages:
            parse = staticmethod(lambda **_k: _Respuesta())

    r = cliente.preguntar("s", [], dict, cliente=_Falso())
    assert r.salida == {"ok": True}
    assert (r.entrada_tokens, r.salida_tokens) == (1000, 200)
    assert r.problema == ""


def test_un_doble_sin_usage_no_revienta():
    """Los dobles de los otros ficheros de test no tienen `usage`."""
    class _Respuesta:
        parsed_output = {"ok": True}

    class _Falso:
        class messages:
            parse = staticmethod(lambda **_k: _Respuesta())

    r = cliente.preguntar("s", [], dict, cliente=_Falso())
    assert r.salida == {"ok": True}
    assert r.entrada_tokens == 0


def test_el_coste_sale_de_la_tarifa():
    """Un millon de entrada y cien mil de salida a la tarifa de Sonnet 5."""
    assert cliente.coste(1_000_000, 0) == cliente.PRECIO_ENTRADA
    assert round(cliente.coste(0, 100_000), 4) == round(cliente.PRECIO_SALIDA / 10, 4)
