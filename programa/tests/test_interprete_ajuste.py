# programa/tests/test_interprete_ajuste.py
"""La mitad que no tiene texto que citar, y por eso lleva otro guardarrail."""

from interprete import ajuste

OPERACIONES = (("MSFT", "vender", 0.03, True), ("MU", "comprar", 0.03, False))
PESOS = (("MSFT", 0.18, 0.15), ("MU", 0.07, 0.10))


def _falso(salidas):
    restantes = list(salidas)

    class _Respuesta:
        def __init__(self, valor):
            self.parsed_output = valor

    class _Mensajes:
        def parse(self, **_kwargs):
            return _Respuesta(restantes.pop(0))

    class _Falso:
        messages = _Mensajes()

    return _Falso()


def _salida(observaciones, en_conjunto=""):
    return ajuste.Salida(
        observaciones=[ajuste.ObservacionCruda(**o) for o in observaciones],
        en_conjunto=en_conjunto,
    )


def test_una_observacion_sobre_una_operacion_propuesta_pasa():
    cliente = _falso([_salida([{"sobre": "B", "dice": "Ésta apenas corrige."}])])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.estado == ajuste.HECHO
    assert com.observaciones == (("MU", "Ésta apenas corrige."),)


def test_una_operacion_que_nadie_propuso_se_cae_y_se_cuenta():
    """**Éste es el guardarrail que hace cumplible el contrato.** G propuso dos,
    así que la letra C no existe: no hay forma de nombrar una tercera."""
    cliente = _falso([_salida([{"sobre": "C", "dice": "Vende NVDA también."}])])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.observaciones == ()
    assert com.descartadas == 1


def test_un_digito_tira_esa_observacion_y_no_el_comentario():
    """Antes tiraba el comentario entero, y con el las observaciones buenas y
    la llamada ya pagada. Son observaciones independientes, no una narrativa."""
    con_numero = {"sobre": "A", "dice": "Te sobran 3 puntos."}
    limpia = {"sobre": "B", "dice": "Esta apenas corrige."}
    cliente = _falso([_salida([con_numero, limpia]),
                      _salida([con_numero, limpia])])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.estado == ajuste.HECHO
    assert com.observaciones == (("MU", "Esta apenas corrige."),)
    assert com.descartadas == 1


def test_una_observacion_sin_texto_se_cae():
    cliente = _falso([_salida([{"sobre": "A", "dice": "   "}])])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.observaciones == ()
    assert com.descartadas == 1


def test_en_conjunto_con_ticker_ajeno_se_vacia_entero():
    cliente = _falso([_salida(
        [{"sobre": "A", "dice": "Pesa de más."}],
        en_conjunto="Las dos compras y TSLA van al mismo sector.",
    )])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.en_conjunto == ""
    assert com.conjunto_descartado is True
    assert len(com.observaciones) == 1


def test_sin_operaciones_no_se_llama_al_modelo():
    def _explota(**_kwargs):
        raise AssertionError("no se debe llamar sin propuesta que comentar")

    class _Falso:
        class messages:
            parse = staticmethod(_explota)

    com = ajuste.comentar((), PESOS, cliente=_Falso())
    assert com.estado == ajuste.SIN_PROPUESTA


def test_sin_clave_ni_cliente_no_se_llama(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ajuste.comentar(OPERACIONES, PESOS).estado == ajuste.SIN_CLAVE


def test_hecho_sin_observaciones_no_es_fallo():
    cliente = _falso([_salida([])])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.estado == ajuste.HECHO
    assert com.observaciones == ()


def test_en_conjunto_con_digito_se_vacia_entero():
    """La otra mitad de `_limpiar_conjunto`, que no tenia prueba.

    Su gemelo `noticias.py` si la tiene: el plan detecto el hueco para uno de
    los dos y se olvido del otro. Lo destapo un sabotaje que salio inerte
    porque apuntaba a la guarda de los digitos mientras el test que existia
    dependia de la de los tickers.
    """
    cliente = _falso([_salida(
        [{"sobre": "A", "dice": "Pesa de mas."}],
        en_conjunto="Las dos compras suman un 30 por ciento de la cartera.",
    )])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.en_conjunto == ""
    assert com.conjunto_descartado is True
    assert len(com.observaciones) == 1


def test_un_en_conjunto_vacio_no_es_un_descarte():
    """Una cadena vacia de entrada significa «el modelo no vio ningun patron».
    Marcarla como descartada diria que se tiro algo, y no se tiro nada."""
    cliente = _falso([_salida(
        [{"sobre": "A", "dice": "Pesa de mas."}], en_conjunto="",
    )])
    com = ajuste.comentar(OPERACIONES, PESOS, cliente=cliente)
    assert com.en_conjunto == ""
    assert com.conjunto_descartado is False
