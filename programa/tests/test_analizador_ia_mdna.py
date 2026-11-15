"""El contraste con el MD&A: la cita se verifica, y lo que no encaja se dice."""

from analizador import ia_mdna as im

DOCUMENTO = (
    "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS\n\n"
    "We expect demand for memory products to remain strong through the fiscal year. "
    "Capital expenditures will increase to support new fabrication capacity. " * 3
)
CITA = "We expect demand for memory products to remain strong"
SUPUESTO = "El escenario base supone que los ingresos crecen por debajo de su ritmo de los últimos años."


def _falso(salidas, vistos=None):
    restantes = list(salidas)

    class _Respuesta:
        def __init__(self, valor):
            self.parsed_output = valor

    class _Mensajes:
        def parse(self, **kwargs):
            if vistos is not None:
                vistos.append(kwargs)
            return _Respuesta(restantes.pop(0))

    class _Falso:
        messages = _Mensajes()

    return _Falso()


def _salida(*juicios):
    return im.Salida(juicios=[im.JuicioCrudo(afirmacion=a, postura=p, cita=c) for a, p, c in juicios])


BUENO = ("La empresa espera que la demanda siga fuerte.", "contradice", CITA)
INVENTADO = ("La empresa espera recortes.", "respalda", "we plan to cut production sharply next year")


def test_un_juicio_con_cita_literal_sale_verificado():
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(BUENO)]))
    assert contraste.estado == im.HECHA
    assert contraste.juicios == (im.Juicio(BUENO[0], "contradice", CITA, True),)


def test_una_cita_que_no_esta_se_reintenta_y_si_sigue_sin_estar_sale_marcada():
    vistos = []
    cliente = _falso([_salida(INVENTADO), _salida(INVENTADO)], vistos)
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=cliente)
    assert len(vistos) == 2
    assert contraste.juicios[0].verificada is False


def test_el_reintento_puede_arreglar_la_cita():
    cliente = _falso([_salida(INVENTADO), _salida(BUENO)])
    assert im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=cliente).juicios[0].verificada is True


def test_la_cita_del_reintento_va_vallada():
    # La cita que falla la escribió el modelo copiando del documento: es texto
    # de un tercero y no se le devuelve a pelo.
    vistos = []
    im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(INVENTADO), _salida(BUENO)], vistos))
    eco = vistos[1]["messages"][-1]["content"]
    assert "<<<" in eco and INVENTADO[2] in eco


def test_una_postura_que_no_es_de_las_tres_se_descarta():
    raro = ("Algo.", "confirma", CITA)
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(raro, BUENO)]))
    assert len(contraste.juicios) == 1 and contraste.descartados == 1


def test_la_postura_se_acepta_con_mayusculas():
    mayus = (BUENO[0], "Matiza", CITA)
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(mayus)]))
    assert contraste.juicios[0].postura == "matiza"


def test_un_digito_en_la_afirmacion_tira_ese_juicio_y_no_los_demas():
    con_numero = ("La demanda crecerá un 20 por ciento.", "respalda", CITA)
    cliente = _falso([_salida(con_numero, BUENO), _salida(con_numero, BUENO)])
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=cliente)
    assert [j.afirmacion for j in contraste.juicios] == [BUENO[0]]
    assert contraste.descartados == 1


def test_los_digitos_de_la_cita_no_cuentan():
    documento = DOCUMENTO + " Revenue increased 49% compared to fiscal 2025 on strong pricing."
    con_cifra = ("Los ingresos subieron con fuerza.", "matiza", "Revenue increased 49% compared to fiscal 2025")
    contraste = im.contrastar("MU", SUPUESTO, documento, cliente=_falso([_salida(con_cifra)]))
    assert contraste.juicios[0].verificada is True


def test_no_salen_mas_juicios_que_el_maximo():
    muchos = [BUENO] * (im.MAX_JUICIOS + 2)
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(*muchos)]))
    assert len(contraste.juicios) == im.MAX_JUICIOS and contraste.descartados == 2


def test_el_documento_va_vallado_y_el_supuesto_fuera():
    vistos = []
    im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida(BUENO)], vistos))
    turno = vistos[0]["messages"][0]["content"]
    assert turno.index(SUPUESTO) < turno.index("<<<") < turno.index("We expect demand")


def test_sin_documento_no_se_llama():
    vistos = []
    assert im.contrastar("MU", SUPUESTO, "", cliente=_falso([], vistos)).estado == im.SIN_DOCUMENTO
    assert vistos == []


def test_sin_clave_se_dice(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert im.contrastar("MU", SUPUESTO, DOCUMENTO).estado == im.SIN_CLAVE


def test_una_respuesta_vacia_es_un_fallo_con_su_problema():
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([None]))
    assert contraste.estado == im.FALLO and contraste.problema


def test_hecho_sin_juicios_es_un_estado_valido():
    contraste = im.contrastar("MU", SUPUESTO, DOCUMENTO, cliente=_falso([_salida()]))
    assert contraste.estado == im.HECHA and contraste.juicios == ()


def test_el_sistema_no_lleva_ni_un_digito():
    from ranking.verificacion import sin_digitos

    assert sin_digitos(im.SISTEMA)
