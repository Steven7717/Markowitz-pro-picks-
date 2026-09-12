# programa/tests/test_interprete_noticias.py
"""Los guardarrailes de la mitad que si tiene texto que citar."""

from datetime import date

from interprete import noticias

FUENTE = (
    "Item 4.02 Non-Reliance on Previously Issued Financial Statements. "
    "On September 3, 2026, the Audit Committee concluded that the financial "
    "statements for fiscal 2025 should no longer be relied upon."
)
CITA = "the financial statements for fiscal 2025 should no longer be relied upon"

ENTRADA = ("MSFT", date(2026, 9, 3), ("4.02",), ("Cuentas anteriores no fiables",), FUENTE)


def _falso(salidas):
    """Un cliente que devuelve las salidas dadas, una por llamada."""
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


def _salida(juicios, en_conjunto=""):
    return noticias.Salida(
        juicios=[noticias.JuicioCrudo(**j) for j in juicios], en_conjunto=en_conjunto
    )


def test_un_juicio_bien_citado_pasa_entero():
    cliente = _falso([_salida([{
        "hecho": "A", "que_dice": "La empresa dice que sus cuentas no valen.",
        "por_que_te_toca": "Es una de tus posiciones grandes.", "cita": CITA,
    }])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.estado == noticias.HECHA
    assert len(lectura.juicios) == 1
    assert lectura.juicios[0].ticker == "MSFT"
    assert lectura.juicios[0].verificada is True


def test_una_cita_inventada_se_reintenta_y_luego_sale_marcada():
    """Como en B: una afirmacion sin respaldo **visiblemente marcada** todavia
    la puede juzgar un humano. Esconderla no."""
    malo = {"hecho": "A", "que_dice": "Dice algo.", "por_que_te_toca": "Te toca.",
            "cita": "esta frase no esta en el documento en absoluto, ninguna"}
    cliente = _falso([_salida([malo]), _salida([malo])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert len(lectura.juicios) == 1
    assert lectura.juicios[0].verificada is False


def test_el_reintento_puede_arreglarlo():
    malo = {"hecho": "A", "que_dice": "Dice algo.", "por_que_te_toca": "Te toca.",
            "cita": "inventada del todo, no aparece por ningun lado aqui"}
    bueno = {"hecho": "A", "que_dice": "Dice algo.", "por_que_te_toca": "Te toca.",
             "cita": CITA}
    cliente = _falso([_salida([malo]), _salida([bueno])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.juicios[0].verificada is True


def test_un_digito_es_fatal_tras_el_reintento():
    """Una cifra inventada se lee exactamente igual que una real. La asimetria
    con la cita es deliberada y viene de `ranking/llm.py`."""
    con_numero = {"hecho": "A", "que_dice": "Cayeron un 40 por ciento.",
                  "por_que_te_toca": "Te toca.", "cita": CITA}
    cliente = _falso([_salida([con_numero]), _salida([con_numero])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.estado == noticias.FALLO
    assert lectura.juicios == ()


def test_los_digitos_de_la_cita_no_cuentan():
    """La cita se copia del documento y puede traer las cifras de la empresa,
    que nadie invento."""
    cliente = _falso([_salida([{
        "hecho": "A", "que_dice": "Las cuentas no valen.",
        "por_que_te_toca": "Pesa mucho en tu cartera.", "cita": CITA,
    }])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.juicios[0].verificada is True


def test_una_etiqueta_inexistente_se_cae_y_se_cuenta():
    """Se cuenta y no se esconde: que el modelo nombre un hecho que no existe
    es senal de que algo va mal en el prompt."""
    cliente = _falso([_salida([{
        "hecho": "Z", "que_dice": "Algo.", "por_que_te_toca": "Te toca.", "cita": CITA,
    }])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.juicios == ()
    assert lectura.descartados == 1


def test_un_juicio_sin_texto_se_cae():
    cliente = _falso([_salida([{
        "hecho": "A", "que_dice": "   ", "por_que_te_toca": "Te toca.", "cita": CITA,
    }])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.juicios == ()
    assert lectura.descartados == 1


def test_en_conjunto_con_ticker_ajeno_se_vacia_entero():
    """Entero y no a trozos: un parrafo al que se le quita una frase queda
    diciendo algo que nadie escribio."""
    cliente = _falso([_salida(
        [{"hecho": "A", "que_dice": "Algo.", "por_que_te_toca": "Te toca.", "cita": CITA}],
        en_conjunto="Esto y lo de TSLA apuntan al mismo sitio.",
    )])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.en_conjunto == ""
    assert lectura.conjunto_descartado is True
    assert len(lectura.juicios) == 1


def test_en_conjunto_con_digito_se_vacia_entero():
    """`_limpiar_conjunto` tambien vacia por digito, no solo por ticker ajeno.
    Sabotaje de la tabla: quitar la comprobacion `sin_digitos` de
    `_limpiar_conjunto` no tumba ningun otro test hoy."""
    cliente = _falso([_salida(
        [{"hecho": "A", "que_dice": "Algo.", "por_que_te_toca": "Te toca.", "cita": CITA}],
        en_conjunto="Cayeron un 30%",
    )])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.en_conjunto == ""
    assert lectura.conjunto_descartado is True


def test_en_conjunto_limpio_sobrevive():
    cliente = _falso([_salida(
        [{"hecho": "A", "que_dice": "Algo.", "por_que_te_toca": "Te toca.", "cita": CITA}],
        en_conjunto="Los dos hechos apuntan al mismo sector.",
    )])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.en_conjunto == "Los dos hechos apuntan al mismo sector."


def test_sin_hechos_no_se_llama_al_modelo():
    def _explota(**_kwargs):
        raise AssertionError("no se debe llamar sin hechos que leer")

    class _Falso:
        class messages:
            parse = staticmethod(_explota)

    lectura = noticias.leer((), {"MSFT"}, cliente=_Falso())
    assert lectura.estado == noticias.SIN_HECHOS


def test_sin_clave_ni_cliente_no_se_llama(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lectura = noticias.leer((ENTRADA,), {"MSFT"})
    assert lectura.estado == noticias.SIN_CLAVE


def test_la_api_caida_es_fallo_y_no_excepcion():
    class _Mensajes:
        def parse(self, **_kwargs):
            return type("R", (), {"parsed_output": None})()

    class _Falso:
        messages = _Mensajes()

    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=_Falso())
    assert lectura.estado == noticias.FALLO


def test_un_en_conjunto_vacio_no_es_un_descarte():
    """Una cadena vacia de entrada significa «el modelo no vio ningun patron».
    Marcarla como descartada diria que se tiro algo, y no se tiro nada."""
    cliente = _falso([_salida([{
        "hecho": "A", "que_dice": "Algo.", "por_que_te_toca": "Te toca.", "cita": CITA,
    }], en_conjunto="")])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.en_conjunto == ""
    assert lectura.conjunto_descartado is False


def test_hecha_sin_juicios_no_es_ni_fallo_ni_sin_hechos():
    """El quinto caso: se miro, se pago la llamada, y no salio nada que decir.
    La pantalla tiene que poder decirlo con esas palabras."""
    cliente = _falso([_salida([])])
    lectura = noticias.leer((ENTRADA,), {"MSFT"}, cliente=cliente)
    assert lectura.estado == noticias.HECHA
    assert lectura.juicios == ()
