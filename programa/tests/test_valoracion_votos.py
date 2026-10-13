import pytest

from valoracion.inverso import ABAJO, ARRIBA, Implicito
from valoracion.votos import (
    BARATA,
    CARA,
    NEUTRA,
    NO_APLICA,
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


def test_un_implicito_sin_valor_ni_limite_no_aplica():
    assert voto_implicito(Implicito(None, None), 0.22, 0.11) == Voto(NO_APLICA, "sin_historia")


def test_el_epv_vota_barata_si_el_precio_esta_por_debajo():
    assert voto_epv(epv=1000.0, precio=989.0).voto == BARATA


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


@pytest.mark.parametrize("pilar", [None, float("nan")])
def test_sin_pilar_los_pares_no_aplican(pilar):
    assert voto_pares(pilar) == Voto(NO_APLICA, "sin_pares")


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
    assert len({combinacion for combinacion, _ in TABLA}) == 64


@pytest.mark.parametrize("combinacion, esperado", TABLA)
def test_el_veredicto(combinacion, esperado):
    votos = [Voto(_CLAVE[letra]) for letra in combinacion]
    assert veredicto(votos) == esperado
