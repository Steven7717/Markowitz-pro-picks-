"""El guardarraíl de la explicación de la valoración, con un cliente doble y sin red."""

import pytest

from analizador import ia_valoracion as iv

BLOQUE = "Empresa: MU, sector Tech.\n[A] Flujos descontados: no se inclina a ningún lado."
MAPA = {"A": "flujos", "B": "sin_crecimiento", "C": "pares"}


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


def _salida(observaciones, en_conjunto=""):
    return iv.Salida(
        observaciones=[iv.ObservacionCruda(sobre=s, dice=d) for s, d in observaciones],
        en_conjunto=en_conjunto,
    )


def test_una_observacion_sobre_una_lectura_que_existe_pasa():
    cliente = _falso([_salida([("A", "Depende de que el crecimiento se sostenga.")])])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert explicacion.estado == iv.HECHA
    assert explicacion.observaciones == (iv.Observacion("flujos", "Depende de que el crecimiento se sostenga.", False),)


def test_la_letra_puede_venir_entre_corchetes_o_en_minuscula():
    cliente = _falso([_salida([("[b]", "El negocio de hoy respalda poco.")])])
    assert iv.explicar(BLOQUE, MAPA, cliente=cliente).observaciones[0].sobre == "sin_crecimiento"


def test_una_letra_que_no_esta_en_el_conjunto_se_descarta():
    cliente = _falso([_salida([("D", "Una cuarta lectura."), ("A", "Ésta sí.")])])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert [o.sobre for o in explicacion.observaciones] == ["flujos"]
    assert explicacion.descartadas == 1


def test_un_digito_se_reintenta_y_el_reintento_puede_arreglarlo():
    vistos = []
    cliente = _falso(
        [_salida([("A", "Crece un 40 por ciento.")]), _salida([("A", "Crece mucho.")])], vistos
    )
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert explicacion.observaciones[0].dice == "Crece mucho."
    assert len(vistos) == 2 and "dígito" in vistos[1]["messages"][-1]["content"]


def test_un_digito_que_sobrevive_tira_esa_observacion_y_no_las_demas():
    mala = [("A", "Crece un 40 por ciento."), ("C", "Sus múltiplos son bajos.")]
    cliente = _falso([_salida(mala), _salida(mala)])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert [o.sobre for o in explicacion.observaciones] == ["pares"]
    assert explicacion.descartadas == 1


def test_una_recomendacion_sale_marcada_y_no_se_borra():
    cliente = _falso([_salida([("C", "Con estos múltiplos conviene comprar."), ("A", "Te recomiendo esperar.")])])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert [o.marcada for o in explicacion.observaciones] == [True, True]


def test_las_palabras_que_solo_se_parecen_no_marcan():
    for frase in (
        "El precio comprende mucho crecimiento.",
        "Hay un compromiso entre margen y volumen.",
        "Las ventas sostienen el valor.",
        "La recompra de acciones ayuda.",
    ):
        assert not iv.recomienda(frase), frase
    for frase in ("Yo vendería.", "Es momento de comprar.", "Se aconseja prudencia.", "Mi recomendación es clara."):
        assert iv.recomienda(frase), frase


def test_el_parrafo_de_conjunto_con_un_digito_se_vacia_entero_y_se_dice():
    cliente = _falso([_salida([("A", "Bien.")], "Las tres lecturas difieren en un 20 por ciento.")])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert explicacion.en_conjunto == "" and explicacion.conjunto_descartado


def test_el_parrafo_de_conjunto_que_recomienda_se_vacia_entero():
    cliente = _falso([_salida([("A", "Bien.")], "En conjunto, recomiendo vender.")])
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=cliente)
    assert explicacion.en_conjunto == "" and explicacion.conjunto_descartado


def test_un_parrafo_de_conjunto_limpio_se_conserva_y_uno_vacio_no_cuenta_como_descartado():
    cliente = _falso([_salida([("A", "Bien.")], "Las tres lecturas apuntan a sitios distintos.")])
    assert iv.explicar(BLOQUE, MAPA, cliente=cliente).en_conjunto == "Las tres lecturas apuntan a sitios distintos."
    cliente = _falso([_salida([("A", "Bien.")], "")])
    assert not iv.explicar(BLOQUE, MAPA, cliente=cliente).conjunto_descartado


def test_el_modelo_ve_el_bloque_y_nada_mas():
    vistos = []
    iv.explicar(BLOQUE, MAPA, cliente=_falso([_salida([("A", "Bien.")])], vistos))
    assert BLOQUE in vistos[0]["messages"][0]["content"]
    assert vistos[0]["system"] == iv.SISTEMA


def test_sin_votos_no_se_llama():
    vistos = []
    assert iv.explicar("", {}, cliente=_falso([], vistos)).estado == iv.SIN_VALORACION
    assert vistos == []


def test_sin_clave_se_dice(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert iv.explicar(BLOQUE, MAPA).estado == iv.SIN_CLAVE


def test_una_respuesta_vacia_es_un_fallo_con_su_problema():
    explicacion = iv.explicar(BLOQUE, MAPA, cliente=_falso([None]))
    assert explicacion.estado == iv.FALLO and explicacion.problema


def test_el_sistema_no_lleva_ni_un_digito():
    from ranking.verificacion import sin_digitos

    assert sin_digitos(iv.SISTEMA)


DEBE_MARCAR = [
    "Conviene adquirir acciones.", "Lo mejor es deshacerse de ellas.", "Conviene mantener la posición.",
    "Deberías comprarla ya.", "Cómprala.", "Compradla.", "¿Comprarías a este precio?", "Compraré más.",
    "Compremos.", "Es desaconsejable entrar.", "Yo esperaría.", "Te sugiero entrar ahora.",
    "Es buen momento para invertir.", "Hay que acumular.", "Mejor salir del valor.", "Yo vendería.",
    "Es momento de comprar.", "Se aconseja prudencia.", "Mi recomendación es clara.",
    "Con estos múltiplos conviene comprar.", "Te recomiendo esperar.", "En conjunto, recomiendo vender.",
    "Es una oportunidad de compra.", "COMPRARÍA sin dudar.", "Es recomendable.", "Es aconsejable.",
]
NO_DEBE_MARCAR = [
    "La empresa vende memoria.", "Depende de que venda más.", "El vendedor de chips.", "Las ventas vendrán.",
    "Vendrán tiempos mejores.", "Si los clientes compran menos, cae.", "La compra de un competidor ayudó.",
    "El precio comprende mucho crecimiento.", "Hay un compromiso entre margen y volumen.",
    "Las ventas sostienen el valor.", "La recompra de acciones ayuda.", "Tiene ventaja frente a sus compradores.",
    "El precio espera mucho crecimiento.", "Se mantiene el margen.", "Los inversores esperan más.",
    "La empresa invierte en capacidad.", "Conviene recordar que el crecimiento no está asegurado.",
]


@pytest.mark.parametrize("frase", DEBE_MARCAR)
def test_el_detector_marca_las_formas_de_recomendar(frase):
    assert iv.recomienda(frase), frase


@pytest.mark.parametrize("frase", NO_DEBE_MARCAR)
def test_el_detector_no_marca_frases_descriptivas(frase):
    assert not iv.recomienda(frase), frase


def test_el_reintento_pide_la_respuesta_entera_y_no_sólo_lo_corregido():
    vistos = []
    cliente = _falso([_salida([("A", "Crece un 40 por ciento.")]), _salida([("A", "Crece mucho.")])], vistos)
    iv.explicar(BLOQUE, MAPA, cliente=cliente)
    segundo = vistos[1]["messages"][-1]["content"]
    assert "respuesta completa" in segundo and "sin cambiar" in segundo
