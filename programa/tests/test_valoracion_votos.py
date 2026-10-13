import itertools

import numpy as np
import pytest

from valoracion.inverso import ABAJO, ARRIBA, Implicito
from valoracion.votos import (
    BARATA,
    CARA,
    MOTIVOS,
    NEUTRA,
    NO_APLICA,
    VEREDICTOS,
    Voto,
    margen_voto,
    veredicto,
    voto_epv,
    voto_implicito,
    voto_pares,
)


def test_el_margen_es_la_mitad_de_la_referencia_con_un_suelo():
    assert margen_voto(0.22, 0.05) == pytest.approx(0.11)
    assert margen_voto(0.05, 0.05) == pytest.approx(0.05)
    assert margen_voto(-0.04, 0.05) == pytest.approx(0.05)


def test_el_margen_usa_el_valor_absoluto_de_la_referencia():
    # Con -0,04 el suelo gana de todos modos; con un ROE de referencia de -30 %
    # (que no lleva tope) sólo gana el valor absoluto, y sin él el margen sería
    # negativo y las bandas del voto se invertirían.
    assert margen_voto(-0.30, 0.03) == pytest.approx(0.15)


@pytest.mark.parametrize(
    "implicito, esperado",
    [
        (Implicito(0.38, None), CARA),
        (Implicito(0.30, None), NEUTRA),
        (Implicito(0.12, None), NEUTRA),
        (Implicito(0.10, None), BARATA),
        (Implicito(None, ARRIBA), CARA),
        (Implicito(None, ABAJO), BARATA),
    ],
)
def test_el_voto_de_flujos(implicito, esperado):
    assert voto_implicito(implicito, referencia=0.22, margen=0.11).voto == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [(0.75, NEUTRA), (0.7500001, CARA), (0.25, NEUTRA), (0.2499999, BARATA)],
)
def test_el_limite_del_margen_cae_en_neutra(valor, esperado):
    # 0,5 ± 0,25 son binarios exactos: ninguna suma de coma flotante decide el
    # límite, lo decide la comparación. Justo en el borde el voto es neutro.
    assert voto_implicito(Implicito(valor, None), referencia=0.5, margen=0.25).voto == esperado


def test_un_implicito_sin_valor_ni_limite_no_aplica():
    assert voto_implicito(Implicito(None, None), 0.22, 0.11) == Voto(NO_APLICA, "sin_historia")


def test_el_epv_vota_barata_si_el_precio_esta_por_debajo():
    assert voto_epv(epv=1000.0, precio=989.0).voto == BARATA


def test_con_el_precio_igual_al_epv_el_voto_es_neutro():
    assert voto_epv(epv=410.0, precio=410.0).voto == NEUTRA
    assert voto_epv(epv=410.0, precio=409.99).voto == BARATA


@pytest.mark.parametrize(
    "epv, precio",
    [
        (float("nan"), 100.0),
        (100.0, float("nan")),
        (float("inf"), 100.0),
        (100.0, float("inf")),
        (float("-inf"), 100.0),
    ],
)
def test_un_epv_o_un_precio_no_finitos_no_votan(epv, precio):
    # Un NaN haría falsa la comparación y saldría «neutra», y un EPV infinito
    # saldría «barata»: un voto que nadie calculó, que además puede completar
    # un «en_rango» o una «infravalorada» con datos rotos.
    assert voto_epv(epv, precio) == Voto(NO_APLICA, "sin_precio")


@pytest.mark.parametrize("precio", [411.0, 989.0, 1e9])
def test_el_epv_nunca_vota_cara(precio):
    # Pagar por el crecimiento no es estar cara: casi todo el S&P 500 cotiza
    # por encima de lo que valdría si dejara de crecer.
    assert voto_epv(epv=410.0, precio=precio).voto == NEUTRA


@pytest.mark.parametrize(
    "pilar, esperado",
    [(0.8, BARATA), (0.5, BARATA), (0.2, NEUTRA), (-0.49, NEUTRA), (-0.5, CARA), (-2.0, CARA)],
)
def test_el_voto_de_pares(pilar, esperado):
    assert voto_pares(pilar).voto == esperado


@pytest.mark.parametrize("pilar, esperado", [(0.49, NEUTRA), (0.51, BARATA), (-0.51, CARA)])
def test_el_voto_de_pares_junto_a_los_umbrales(pilar, esperado):
    assert voto_pares(pilar).voto == esperado


@pytest.mark.parametrize(
    "pilar",
    [
        None,
        float("nan"),
        float("inf"),
        float("-inf"),
        np.float64("nan"),
        pytest.param(10**400, id="entero_enorme"),
    ],
)
def test_sin_pilar_los_pares_no_aplican(pilar):
    # `10**400` es un entero legal que `float()` no sabe convertir: lanza
    # OverflowError, no ValueError, y tiene que acabar en «no aplica» igual.
    assert voto_pares(pilar) == Voto(NO_APLICA, "sin_pares")


@pytest.mark.parametrize("pilar, esperado", [(np.float64(0.8), BARATA), (np.float32(-0.5), CARA)])
def test_el_pilar_puede_venir_de_numpy(pilar, esperado):
    assert voto_pares(pilar).voto == esperado


_CLAVE = {"B": BARATA, "N": NEUTRA, "C": CARA, "X": NO_APLICA}

# La regla del spec, escrita a mano para las 64 combinaciones. Algunas no se
# dan en la práctica --el voto del medio es el EPV, que nunca dice «cara»--
# pero la regla se prueba como tal, no sólo en los casos que hoy ocurren.
TABLA = [
    ("BBB", "infravalorada"), ("BBN", "infravalorada"), ("BBC", "mixtas"), ("BBX", "infravalorada"),
    ("BNB", "infravalorada"), ("BNN", "en_rango"), ("BNC", "mixtas"), ("BNX", "en_rango"),
    ("BCB", "mixtas"), ("BCN", "mixtas"), ("BCC", "mixtas"), ("BCX", "mixtas"),
    ("BXB", "infravalorada"), ("BXN", "en_rango"), ("BXC", "mixtas"), ("BXX", "sin_datos"),
    ("NBB", "infravalorada"), ("NBN", "en_rango"), ("NBC", "mixtas"), ("NBX", "en_rango"),
    ("NNB", "en_rango"), ("NNN", "en_rango"), ("NNC", "en_rango"), ("NNX", "en_rango"),
    ("NCB", "mixtas"), ("NCN", "en_rango"), ("NCC", "sobrevalorada"), ("NCX", "en_rango"),
    ("NXB", "en_rango"), ("NXN", "en_rango"), ("NXC", "en_rango"), ("NXX", "sin_datos"),
    ("CBB", "mixtas"), ("CBN", "mixtas"), ("CBC", "mixtas"), ("CBX", "mixtas"),
    ("CNB", "mixtas"), ("CNN", "en_rango"), ("CNC", "sobrevalorada"), ("CNX", "en_rango"),
    ("CCB", "mixtas"), ("CCN", "sobrevalorada"), ("CCC", "sobrevalorada"), ("CCX", "sobrevalorada"),
    ("CXB", "mixtas"), ("CXN", "en_rango"), ("CXC", "sobrevalorada"), ("CXX", "sin_datos"),
    ("XBB", "infravalorada"), ("XBN", "en_rango"), ("XBC", "mixtas"), ("XBX", "sin_datos"),
    ("XNB", "en_rango"), ("XNN", "en_rango"), ("XNC", "en_rango"), ("XNX", "sin_datos"),
    ("XCB", "mixtas"), ("XCN", "en_rango"), ("XCC", "sobrevalorada"), ("XCX", "sin_datos"),
    ("XXB", "sin_datos"), ("XXN", "sin_datos"), ("XXC", "sin_datos"), ("XXX", "sin_datos"),
]


def test_la_tabla_cubre_las_64_combinaciones():
    esperadas = {"".join(letras) for letras in itertools.product("BNCX", repeat=3)}
    assert len(TABLA) == 64
    assert {combinacion for combinacion, _ in TABLA} == esperadas


def test_los_veredictos_de_la_tabla_son_los_declarados():
    assert {veredicto_esperado for _, veredicto_esperado in TABLA} == set(VEREDICTOS)


def test_los_motivos_que_escribe_el_modulo_estan_declarados():
    # Se provocan las salidas sin voto de cada función en vez de copiar las
    # claves a mano: si alguien añade un motivo nuevo y no lo declara, falla.
    escritos = {
        voto_implicito(Implicito(None, None), 0.22, 0.11).motivo,
        voto_epv(float("nan"), 1.0).motivo,
        voto_pares(None).motivo,
    }
    assert escritos <= MOTIVOS


@pytest.mark.parametrize("combinacion, esperado", TABLA)
def test_el_veredicto(combinacion, esperado):
    votos = [Voto(_CLAVE[letra]) for letra in combinacion]
    assert veredicto(votos) == esperado


def test_el_veredicto_acepta_cualquier_iterable_de_votos():
    # El motor le pasa `dict.values()`, que no es una lista ni se puede indexar.
    votos = {"flujos": Voto(BARATA), "epv": Voto(BARATA), "pares": Voto(NO_APLICA, "sin_pares")}
    assert veredicto(votos.values()) == "infravalorada"
    assert veredicto(voto for voto in votos.values()) == "infravalorada"
