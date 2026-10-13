import pytest

from valoracion.epv import epv_por_accion, margen_operativo, parte_crecimiento
from valoracion.inverso import ARRIBA
from valoracion.residual import (
    DatosResidual,
    rentabilidades,
    roe_implicito,
    valor_por_accion,
    valor_residual,
)

from tests.dobles_valoracion import ejercicio, fundamentos


def test_el_epv_capitaliza_el_beneficio_operativo_sin_crecer():
    # Margen operativo 0,20 sobre ingresos de 1.000: 200 × 0,75 / 0,10 = 1.500,
    # menos 100 de deuda y más 50 de efectivo, entre 10 acciones.
    valor, motivo = epv_por_accion(fundamentos(), t=0.25, wacc=0.10, deuda=100.0, efectivo=50.0, acciones=10.0)
    assert valor == pytest.approx(145.0)
    assert motivo is None


def test_con_beneficio_operativo_negativo_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, beneficio_operativo=-10.0) for i in range(3)])
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "ebit_negativo")


def test_el_margen_operativo_es_agregado_y_no_la_mediana():
    # Ingresos 1.000, 100 y 100 con márgenes del 30 %, 5 % y 5 %: la mediana
    # sería 0,05 y el agregado (300 + 5 + 5) / 1.200.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, ingresos=1000.0, beneficio_operativo=300.0),
            ejercicio(2025, ingresos=100.0, beneficio_operativo=5.0),
            ejercicio(2024, ingresos=100.0, beneficio_operativo=5.0),
        ]
    )
    assert margen_operativo(f) == pytest.approx(310.0 / 1200.0)


def test_sin_anos_suficientes_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026)])
    assert margen_operativo(f) is None
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_historia")


def test_la_parte_del_precio_que_es_crecimiento():
    assert parte_crecimiento(145.0, 200.0) == pytest.approx(0.275)
    assert parte_crecimiento(-5.0, 200.0) is None


def test_el_roe_converge_al_coste_del_capital_en_diez_anos():
    roes = rentabilidades(0.20, 0.10)
    assert len(roes) == 10
    assert roes[0] == pytest.approx(0.20)
    assert roes[-1] == pytest.approx(0.10)


def test_con_roe_igual_al_coste_el_valor_es_el_contable():
    # Referencia positiva: sin exceso de rentabilidad no hay nada que sumar.
    assert valor_residual(1000.0, 0.10, 0.10, 0.4) == pytest.approx(1000.0, rel=1e-12)


def test_mas_rentabilidad_mas_valor():
    assert valor_residual(1000.0, 0.15, 0.10, 0.4) > valor_residual(1000.0, 0.12, 0.10, 0.4) > 1000.0


DATOS = DatosResidual(patrimonio=1000.0, k_e=0.09, payout=0.4, acciones=10.0)


def test_el_valor_por_accion_reparte_entre_las_acciones():
    assert valor_por_accion(DATOS, 0.09) == pytest.approx(100.0)


def test_un_coste_del_capital_no_positivo_no_da_valor():
    assert valor_por_accion(DATOS, 0.10, k_e=0.0) is None


def test_el_roe_implicito_devuelve_el_de_partida():
    precio = valor_por_accion(DATOS, 0.14)
    assert roe_implicito(DATOS, precio).valor == pytest.approx(0.14, abs=1e-6)


def test_un_precio_inalcanzable_exige_mas_roe_del_limite():
    assert roe_implicito(DATOS, 1e9).fuera_de_limites == ARRIBA
