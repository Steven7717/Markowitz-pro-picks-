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


@pytest.mark.parametrize("semanas, fuente", [(51, "por_defecto"), (52, "regresion")])
def test_la_regresion_corta_no_se_usa(semanas, fuente):
    s = beta_ajustada(Beta(bruta=1.5, r2=0.4, semanas=semanas, indice="^GSPC"))
    assert s.procedencia["fuente"] == fuente
    assert s.valor == pytest.approx(1.0 if fuente == "por_defecto" else 0.67 * 1.5 + 0.33)


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
        (float("nan"), "United States", 0.21, "legal"),
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


@pytest.mark.parametrize("intereses", [float("nan"), 0.0, -10.0])
def test_un_gasto_financiero_sin_dato_o_no_positivo_no_es_un_coste(intereses):
    # Negativo es ingreso neto por intereses (DIS, FTV), no un coste de la deuda.
    f = fundamentos(
        ejercicios=[ejercicio(2026, gasto_financiero=intereses)], deuda_total=200.0
    )
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


def test_el_crecimiento_dice_de_donde_sale():
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    ambos = crecimiento_ref(f, consenso=0.20)
    assert ambos.procedencia == {
        "fuente": "historia_y_consenso",
        "historico": 0.10,
        "consenso": 0.20,
        "bruto": 0.15,
    }
    solo_historia = crecimiento_ref(f, consenso=None)
    assert solo_historia.procedencia["fuente"] == "historia"
    assert solo_historia.procedencia["consenso"] is None
    solo_consenso = crecimiento_ref(fundamentos(ejercicios=[ejercicio(2026)]), consenso=0.03)
    assert solo_consenso.valor == pytest.approx(0.03)
    assert solo_consenso.procedencia["fuente"] == "consenso"
    assert solo_consenso.procedencia["historico"] is None


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


def test_un_consenso_que_no_es_numero_no_cuenta():
    f = _creciendo([1100.0, 1000.0])
    s = crecimiento_ref(f, consenso=float("nan"))
    assert s.valor == pytest.approx(0.10)
    assert s.procedencia["fuente"] == "historia"


@pytest.mark.parametrize(
    "ingresos",
    [
        [0.0, 1000.0, 1000.0, 1000.0],
        [1000.0, 1000.0, 1000.0, 0.0],
        [-5.0, 1000.0, 1000.0, 1000.0],
        [1000.0, 1000.0, 1000.0, -5.0],
        [float("nan"), 1000.0, 1000.0, 1000.0],
        [1000.0, 1000.0, 1000.0, float("nan")],
    ],
    ids=[
        "final_cero",
        "inicial_cero",
        "final_negativo",
        "inicial_negativo",
        "final_nan",
        "inicial_nan",
    ],
)
def test_unos_ingresos_que_no_dan_un_cagr_se_quedan_con_el_consenso(ingresos):
    f = _creciendo(ingresos)
    assert crecimiento_ref(f, consenso=None).valor is None
    con_consenso = crecimiento_ref(f, consenso=0.05)
    assert con_consenso.valor == pytest.approx(0.05)
    assert con_consenso.procedencia["fuente"] == "consenso"


def test_el_crecimiento_de_referencia_tambien_se_acota_por_abajo():
    f = _creciendo([343.0, 490.0, 700.0, 1000.0])
    s = crecimiento_ref(f, consenso=None)
    assert s.valor == pytest.approx(-0.10)
    assert s.procedencia["bruto"] == pytest.approx(-0.30)


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


def test_el_roe_se_salta_los_ejercicios_sin_patrimonio_ni_beneficio():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, beneficio_neto=100.0, patrimonio_neto=1000.0),
            ejercicio(2025, beneficio_neto=150.0, patrimonio_neto=0.0),
            ejercicio(2024, beneficio_neto=float("nan"), patrimonio_neto=1000.0),
            ejercicio(2023, beneficio_neto=140.0, patrimonio_neto=1000.0),
        ]
    )
    s = roe_referencia(f)
    assert s.valor == pytest.approx(0.12)
    assert s.procedencia["anos"] == 2


def test_un_patrimonio_negativo_no_cuenta_para_el_roe():
    f = fundamentos(
        ejercicios=[ejercicio(2026, patrimonio_neto=-50.0), ejercicio(2025)]
    )
    assert roe_referencia(f).valor is None


def test_el_payout_se_acota_y_tiene_respaldo():
    assert payout(1.4).valor == 1.0
    assert payout(-0.3).valor == 0.0
    assert payout(None).valor == 0.5
    assert payout(None).procedencia["fuente"] == "por_defecto"
    sin_numero = payout(float("nan"))
    assert sin_numero.valor == 0.5
    assert sin_numero.procedencia["fuente"] == "por_defecto"


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


def test_deducir_con_una_regresion_y_un_consenso_dice_de_donde_sale_cada_cosa():
    beta = Beta(bruta=1.5, r2=0.4, semanas=104, indice="^GSPC")
    s = deducir(fundamentos(), perfil(), r_f=0.04, beta=beta, tasa=0.19, consenso=0.20)
    assert s.r_f.valor == 0.04
    assert s.r_f.procedencia == {"fuente": "tesoro_10", "serie": "^TNX"}
    assert s.beta.valor == pytest.approx(0.67 * 1.5 + 0.33)
    assert s.beta.procedencia == {
        "fuente": "regresion",
        "indice": "^GSPC",
        "semanas": 104,
        "r2": 0.4,
        "bruta": 1.5,
    }
    assert s.t.valor == pytest.approx(0.19)
    assert s.t.procedencia == {"fuente": "efectiva", "bruta": 0.19}
    assert s.k_e.valor == pytest.approx(0.04 + (0.67 * 1.5 + 0.33) * 0.042)
    assert s.k_e.procedencia == {"fuente": "capm"}
    assert s.g_ref.valor == pytest.approx((0.0 + 0.20) / 2)
    assert s.g_ref.procedencia["fuente"] == "historia_y_consenso"


def test_deducir_sin_ingresos_ni_deuda_declarados_no_inventa_nada():
    # Un JPM: no declara ingresos, deuda ni gasto financiero, pero sí tiene
    # consenso. La industria es de otro sector a propósito, para no entrar en el
    # caso de las financieras: aquí lo que se prueba es el NaN.
    nan = float("nan")
    jpm = fundamentos(
        ejercicios=[
            ejercicio(2026 - i, ingresos=nan, gasto_financiero=nan) for i in range(4)
        ],
        deuda_total=nan,
    )
    s = deducir(
        jpm,
        perfil(industria="Semiconductors"),
        r_f=0.04,
        beta=None,
        tasa=None,
        consenso=0.03,
    )
    assert s.k_d.valor == 0.04 and s.k_d.procedencia["fuente"] == "sin_dato"
    assert s.wacc.valor == pytest.approx(s.k_e.valor)
    assert s.wacc.procedencia["deuda_declarada"] is False
    assert s.g_ref.valor == pytest.approx(0.03)
    assert s.g_ref.procedencia["fuente"] == "consenso"


def test_una_financiera_no_tiene_coste_de_deuda_ni_de_capital_pero_si_k_e():
    s = deducir(
        fundamentos(),
        perfil(industria="Banks - Regional"),
        r_f=0.04,
        beta=None,
        tasa=0.25,
        consenso=None,
    )
    assert s.k_d.valor is None and s.k_d.procedencia == {"fuente": "financiera"}
    assert s.wacc.valor is None and s.wacc.procedencia == {"fuente": "financiera"}
    assert s.k_e.valor == pytest.approx(0.04 + 1.0 * 0.042)
    assert s.roe_ref.valor == pytest.approx(0.12)
