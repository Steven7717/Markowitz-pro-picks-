from datetime import date

import pytest

import medidores
import medidores_valoracion as mv
from valoracion.mercado import Beta
from valoracion.motor import calcular
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import MOTIVOS, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil


def _valoracion(f=None, p=None, pilar=0.8) -> dict:
    f, p = f or fundamentos(), p or perfil()
    s = deducir(f, p, r_f=0.04, beta=None, tasa=0.25, consenso=None)
    return a_dict(calcular(f, p, s, pilar, date(2026, 10, 12)))


def test_cada_veredicto_tiene_etiqueta():
    assert set(mv.VEREDICTO) == set(VEREDICTOS)


def test_cada_motivo_tiene_etiqueta():
    assert MOTIVOS <= set(mv.MOTIVO)


@pytest.mark.parametrize("clave", VEREDICTOS)
def test_el_distintivo_dice_el_veredicto(clave):
    assert mv.VEREDICTO[clave][0] in mv.distintivo({"version": "m1", "veredicto": clave})


@pytest.mark.parametrize("valor", [None, fallida("sin_precio"), {"version": "m1", "veredicto": "otra"}])
def test_sin_valoracion_reconocible_no_hay_distintivo(valor):
    assert mv.distintivo(valor) == ""


def test_el_resumen_nombra_los_tres_votos():
    html = mv.resumen(_valoracion())
    for nombre in mv.NOMBRE_VOTO.values():
        assert nombre in html
    assert "estados hasta 2026-09-30" in html


def test_el_resumen_de_un_banco_llama_beneficio_residual_a_los_flujos():
    p = perfil(industria="Banks - Regional")
    html = mv.resumen(_valoracion(p=p))
    assert "Beneficio residual" in html
    assert mv.MOTIVO["financiera"] in html


def test_quemar_caja_se_explica_y_no_se_pone_a_cero():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    html = mv.resumen(_valoracion(f=f))
    assert mv.MOTIVO["quema_caja"] in html


def test_una_fallida_dice_por_que():
    assert mv.MOTIVO["sin_precio"] in mv.resumen(fallida("sin_precio"))


def test_el_resumen_escapa_lo_que_no_es_suyo():
    valor = {**_valoracion(), "moneda": "<b>USD</b>"}
    html = mv.resumen(valor)
    assert "<b>USD</b>" not in html
    assert "&lt;b&gt;USD&lt;/b&gt;" in html


def test_una_procedencia_desconocida_no_revienta():
    assert mv.procedencia("beta", {"valor": 1.0, "procedencia": {"fuente": "otra"}}) == ""


def test_la_beta_dice_de_donde_sale():
    texto = mv.procedencia(
        "beta",
        {"valor": 1.33, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.41}},
    )
    assert "104 semanas" in texto and "^GSPC" in texto and "Blume" in texto


def _sin_historia():
    """Un solo ejercicio: no hay CAGR, así que el crecimiento sólo puede venir del consenso."""
    return fundamentos(ejercicios=[ejercicio(2026)])


# Cada caso fabrica supuestos reales con `deducir`, no a mano: si el paquete
# empieza a escribir una fuente nueva, este test falla en vez de dejar que la
# pantalla muestre un supuesto sin explicar. Cada caso lleva su propio perfil
# porque un banco valorado con un perfil de industrial no es una valoración real.
_CASOS_DE_SUPUESTOS = {
    "empresa normal": (fundamentos(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sin tasa efectiva ni payout": (
        fundamentos(), perfil(payout=None, pais="Mexico"), dict(tasa=None, consenso=None)
    ),
    "sin deuda": (fundamentos(deuda_total=0.0), perfil(), dict(tasa=0.25, consenso=0.08)),
    "banco": (fundamentos(), perfil(industria="Banks - Regional"), dict(tasa=0.25, consenso=0.08)),
    "sólo consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=0.08)),
    "sólo historia": (fundamentos(), perfil(), dict(tasa=0.25, consenso=None)),
    "con regresión de beta": (
        fundamentos(),
        perfil(),
        dict(beta=Beta(bruta=1.4, r2=0.41, semanas=104, indice="^GSPC"), tasa=0.25, consenso=0.08),
    ),
    "ni historia ni consenso": (_sin_historia(), perfil(), dict(tasa=0.25, consenso=None)),
}


@pytest.mark.parametrize("caso", _CASOS_DE_SUPUESTOS)
@pytest.mark.parametrize("r_f", [0.04, 0.02])
def test_todo_supuesto_que_se_puede_producir_tiene_procedencia_en_pantalla(caso, r_f):
    # Con r_f = 0,02 el crecimiento perpetuo (2,5 %) se recorta a la tasa libre.
    f, p, kwargs = _CASOS_DE_SUPUESTOS[caso]
    s = deducir(f, p, r_f=r_f, **{"beta": None, **kwargs})
    supuestos = a_dict(calcular(f, p, s, 0.8, date(2026, 10, 12)))["supuestos"]
    for nombre, supuesto in supuestos.items():
        assert mv.procedencia(nombre, supuesto) != "", (nombre, supuesto["procedencia"])


def test_un_banco_no_revienta_con_wacc_y_k_d_nulos():
    p = perfil(industria="Banks - Regional")
    html = mv.resumen(_valoracion(p=p))
    assert "coste de capital n/d" in html
    assert "coste de la deuda n/d" in html


FICHA = {
    "puesto": 1,
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "compuesto": 1.2,
    "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": -0.2, "solidez": 0.3},
    "cobertura": {
        "kpis_con_dato": 15,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
    },
}


def test_la_tarjeta_lleva_el_distintivo():
    ficha = {**FICHA, "valoracion": {"version": "m1", "veredicto": "infravalorada"}}
    assert "Infravalorada" in medidores.tarjeta_candidato(ficha)


def test_una_tarjeta_vieja_no_lleva_distintivo():
    assert "mpp-veredicto" not in medidores.tarjeta_candidato(FICHA)
