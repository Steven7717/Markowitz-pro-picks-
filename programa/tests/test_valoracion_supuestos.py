import math

import pytest

from valoracion.mercado import Beta
from valoracion.supuestos import (
    beta_ajustada,
    coste_capital,
    coste_deuda,
    crecimiento_perpetuo,
    crecimiento_ref,
    deducir,
    payout,
    roe_referencia,
    tasa_impositiva,
)

from tests.dobles_valoracion import ejercicio, fundamentos, perfil


def test_blume_ajusta_la_beta_de_la_regresion():
    s = beta_ajustada(Beta(bruta=1.5, r2=0.4, semanas=104, indice="^GSPC"))
    assert s.valor == pytest.approx(0.67 * 1.5 + 0.33)
    assert s.procedencia["fuente"] == "regresion"
    assert s.procedencia["semanas"] == 104


def test_sin_regresion_la_beta_es_uno_y_se_dice():
    s = beta_ajustada(None)
    assert s.valor == 1.0
    assert s.procedencia["fuente"] == "por_defecto"


@pytest.mark.parametrize(
    "tasa, pais, esperado, fuente",
    [
        (0.19, "United States", 0.19, "efectiva"),
        (0.50, "United States", 0.35, "efectiva"),
        (-0.10, "United States", 0.0, "efectiva"),
        (None, "United States", 0.21, "legal"),
        (None, "Mexico", 0.30, "legal"),
        (None, "Taiwan", 0.24, "legal"),
        (None, None, 0.24, "legal"),
    ],
)
def test_la_tasa_impositiva(tasa, pais, esperado, fuente):
    s = tasa_impositiva(tasa, pais)
    assert s.valor == pytest.approx(esperado)
    assert s.procedencia["fuente"] == fuente


@pytest.mark.parametrize(
    "intereses, esperado",
    [(10.0, 0.05), (2.0, 0.04), (40.0, 0.12)],
)
def test_el_coste_de_la_deuda_se_acota(intereses, esperado):
    f = fundamentos(
        ejercicios=[ejercicio(2026, gasto_financiero=intereses)], deuda_total=200.0
    )
    assert coste_deuda(f, r_f=0.04).valor == pytest.approx(esperado)


def test_sin_deuda_el_coste_de_la_deuda_es_la_tasa_libre():
    f = fundamentos(deuda_total=float("nan"))
    s = coste_deuda(f, r_f=0.04)
    assert s.valor == 0.04 and s.procedencia["fuente"] == "sin_dato"


def test_el_coste_de_capital_pondera_capital_y_deuda():
    s = coste_capital(k_e=0.10, k_d=0.05, t=0.20, capitalizacion=800.0, deuda=200.0)
    assert s.valor == pytest.approx(0.8 * 0.10 + 0.2 * 0.05 * 0.8)


def test_sin_deuda_declarada_el_coste_de_capital_es_el_del_capital():
    s = coste_capital(k_e=0.10, k_d=0.05, t=0.20, capitalizacion=800.0, deuda=float("nan"))
    assert s.valor == pytest.approx(0.10)
    assert s.procedencia["deuda_declarada"] is False


def _creciendo(ingresos):
    return fundamentos(
        ejercicios=[ejercicio(2026 - i, ingresos=v) for i, v in enumerate(ingresos)]
    )


def test_el_crecimiento_de_referencia_mezcla_historia_y_consenso():
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=0.20).valor == pytest.approx((0.10 + 0.20) / 2)


def test_sin_consenso_el_crecimiento_es_el_historico():
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.10)


def test_con_menos_anos_el_cagr_usa_los_que_hay():
    f = _creciendo([1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.10)


def test_el_crecimiento_de_referencia_se_acota():
    f = _creciendo([8000.0, 4000.0, 2000.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.40)


def test_sin_historia_ni_consenso_no_hay_crecimiento():
    f = fundamentos(ejercicios=[ejercicio(2026)])
    assert crecimiento_ref(f, consenso=None).valor is None


def test_el_perpetuo_nunca_supera_la_tasa_libre():
    assert crecimiento_perpetuo("USD", r_f=0.05).valor == 0.025
    s = crecimiento_perpetuo("USD", r_f=0.02)
    assert s.valor == 0.02 and s.procedencia["fuente"] == "recortado_a_r_f"


def test_el_roe_de_referencia_es_la_mediana_anual():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, beneficio_neto=100.0, patrimonio_neto=1000.0),
            ejercicio(2025, beneficio_neto=150.0, patrimonio_neto=1000.0),
            ejercicio(2024, beneficio_neto=120.0, patrimonio_neto=1000.0),
        ]
    )
    assert roe_referencia(f).valor == pytest.approx(0.12)


def test_un_patrimonio_negativo_no_cuenta_para_el_roe():
    f = fundamentos(
        ejercicios=[ejercicio(2026, patrimonio_neto=-50.0), ejercicio(2025)]
    )
    assert roe_referencia(f).valor is None


def test_el_payout_se_acota_y_tiene_respaldo():
    assert payout(1.4).valor == 1.0
    assert payout(None).valor == 0.5
    assert payout(None).procedencia["fuente"] == "por_defecto"


def test_deducir_compone_el_capm_y_el_coste_de_capital():
    s = deducir(fundamentos(), perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=None)
    assert s.k_e.valor == pytest.approx(0.04 + 1.0 * 0.042)
    assert s.k_d.valor == pytest.approx(0.10)
    peso_capital = 1000.0 / 1200.0
    assert s.wacc.valor == pytest.approx(
        peso_capital * s.k_e.valor + (1 - peso_capital) * 0.10 * 0.75
    )
    assert s.g_ref.valor == pytest.approx(0.0)
    assert s.g_perpetuo.valor == 0.025
    assert s.roe_ref.valor == pytest.approx(0.12)
    assert s.payout.valor == 0.3
    assert s.prima.procedencia == {"fuente": "damodaran", "fecha": "2026-10-01"}
