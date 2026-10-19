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


# --- Por qué faltó un dato de mercado ------------------------------------------
# Sin el motivo, una beta que no llegó por la red se guardaba igual que una sin
# regresión posible, y la pantalla daba una causa falsa: «historial corto».


@pytest.mark.parametrize("motivo", ["sin_red", "sin_regresion"])
def test_sin_beta_la_procedencia_dice_por_que(motivo):
    s = beta_ajustada(None, motivo=motivo)
    assert s.valor == 1.0
    assert s.procedencia == {"fuente": "por_defecto", "motivo": motivo}


@pytest.mark.parametrize("motivo", [None, "ok"])
def test_sin_motivo_de_mercado_la_beta_por_defecto_es_la_de_siempre(motivo):
    assert beta_ajustada(None, motivo=motivo).procedencia == {"fuente": "por_defecto"}


def test_una_regresion_corta_no_lleva_motivo_de_mercado():
    # La red sí contestó: lo que falta son semanas, no un dato de Yahoo.
    corta = Beta(bruta=1.5, r2=0.4, semanas=51, indice="^GSPC")
    assert beta_ajustada(corta, motivo="ok").procedencia == {"fuente": "por_defecto"}


@pytest.mark.parametrize("motivo", ["sin_red", "sin_tasa_efectiva"])
def test_sin_tasa_efectiva_la_legal_dice_por_que(motivo):
    s = tasa_impositiva(None, "United States", motivo=motivo)
    assert s.valor == pytest.approx(0.21)
    assert s.procedencia == {"fuente": "legal", "pais": "US", "motivo": motivo}


def test_con_tasa_efectiva_no_hay_motivo_que_guardar():
    assert tasa_impositiva(0.19, "United States", motivo="ok").procedencia == {
        "fuente": "efectiva",
        "bruta": 0.19,
    }
    assert tasa_impositiva(None, "United States").procedencia == {"fuente": "legal", "pais": "US"}


@pytest.mark.parametrize("motivo", ["sin_red", "sin_consenso"])
def test_sin_consenso_el_crecimiento_dice_por_que(motivo):
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    s = crecimiento_ref(f, consenso=None, motivo=motivo)
    assert s.valor == pytest.approx(0.10)
    assert s.procedencia["fuente"] == "historia"
    assert s.procedencia["motivo_consenso"] == motivo


def test_sin_historia_ni_consenso_tambien_dice_por_que_falto_el_consenso():
    s = crecimiento_ref(fundamentos(ejercicios=[ejercicio(2026)]), consenso=None, motivo="sin_red")
    assert s.procedencia == {"fuente": "sin_dato", "motivo_consenso": "sin_red"}


@pytest.mark.parametrize("motivo", [None, "ok"])
def test_con_consenso_o_sin_motivo_no_hay_motivo_del_consenso(motivo):
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    assert "motivo_consenso" not in crecimiento_ref(f, consenso=0.2, motivo="ok").procedencia
    assert "motivo_consenso" not in crecimiento_ref(f, consenso=None, motivo=motivo).procedencia


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


def test_deducir_sin_tasa_efectiva_usa_la_legal_del_pais_del_perfil():
    s = deducir(
        fundamentos(), perfil(pais="Mexico"), r_f=0.04, beta=None, tasa=None, consenso=None
    )
    assert s.t.valor == pytest.approx(0.30)
    assert s.t.procedencia == {"fuente": "legal", "pais": "MX"}


def test_deducir_guarda_por_que_faltaron_los_datos_de_mercado():
    motivos = {"beta": "sin_red", "tasa": "sin_red", "consenso": "sin_red"}
    s = deducir(
        _creciendo([1331.0, 1210.0, 1100.0, 1000.0]),
        perfil(),
        r_f=0.04,
        beta=None,
        tasa=None,
        consenso=None,
        motivos=motivos,
    )
    assert s.beta.procedencia == {"fuente": "por_defecto", "motivo": "sin_red"}
    assert s.t.procedencia == {"fuente": "legal", "pais": "US", "motivo": "sin_red"}
    assert s.g_ref.procedencia["motivo_consenso"] == "sin_red"


def test_deducir_con_los_datos_de_mercado_presentes_no_guarda_motivos():
    beta = Beta(bruta=1.5, r2=0.4, semanas=104, indice="^GSPC")
    motivos = {"beta": "ok", "tasa": "ok", "consenso": "ok"}
    con = deducir(fundamentos(), perfil(), 0.04, beta, 0.19, 0.20, motivos=motivos)
    sin = deducir(fundamentos(), perfil(), 0.04, beta, 0.19, 0.20)
    assert con == sin


def test_deducir_sin_motivos_es_el_de_siempre():
    # Las llamadas que no pasan motivos (los tests, y N cuando llegue) no cambian.
    s = deducir(fundamentos(), perfil(), r_f=0.04, beta=None, tasa=None, consenso=None)
    assert s.beta.procedencia == {"fuente": "por_defecto"}
    assert s.t.procedencia == {"fuente": "legal", "pais": "US"}
    assert "motivo_consenso" not in s.g_ref.procedencia


def test_deducir_recorta_el_perpetuo_a_la_tasa_libre_que_recibe():
    s = deducir(fundamentos(), perfil(), r_f=0.02, beta=None, tasa=0.25, consenso=None)
    assert s.g_perpetuo.valor == 0.02
    assert s.g_perpetuo.procedencia["fuente"] == "recortado_a_r_f"


def test_deducir_toma_el_roe_de_los_ejercicios_que_recibe():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026 - i, beneficio_neto=200.0, patrimonio_neto=1000.0)
            for i in range(4)
        ]
    )
    s = deducir(f, perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=None)
    assert s.roe_ref.valor == pytest.approx(0.20)


def test_una_deuda_negativa_no_pesa_en_el_coste_de_capital():
    s = coste_capital(k_e=0.10, k_d=0.05, t=0.2, capitalizacion=800.0, deuda=-50.0)
    assert s.valor == pytest.approx(0.10)
    assert s.procedencia["peso_deuda"] == 0.0
    assert s.procedencia["deuda_declarada"] is True


# --- La procedencia de la tasa libre y `aplicar` ------------------------------

from tests.dobles_valoracion import ejercicio as _ejercicio  # noqa: E402
from tests.dobles_valoracion import fundamentos as _fundamentos  # noqa: E402
from tests.dobles_valoracion import perfil as _perfil  # noqa: E402
from valoracion.mercado import Beta as _Beta  # noqa: E402
from valoracion.supuestos import MOVIBLES, aplicar, movidos  # noqa: E402
from valoracion.supuestos import deducir as _deducir  # noqa: E402


def test_sin_procedencia_la_tasa_libre_es_el_tesoro():
    s = _deducir(_fundamentos(), _perfil(), 0.05, None, None, None)
    assert s.r_f.procedencia == {"fuente": "tesoro_10", "serie": "^TNX"}


def test_la_tasa_libre_lleva_la_procedencia_que_se_le_da():
    bono = {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    s = _deducir(_fundamentos(), _perfil(), 0.0925, None, None, None, procedencia_r_f=bono)
    assert s.r_f.procedencia == bono


from dataclasses import fields as _campos  # noqa: E402

from valoracion.criterio import BLUME as _BLUME  # noqa: E402

_BETA = _Beta(1.2, 0.4, 104, "^GSPC")


def _base(tasa=0.21):
    return _deducir(_fundamentos(), _perfil(), 0.05, _BETA, tasa, 0.10)


def _exacta(r_f=0.05, gasto=20.0, beta=_BETA):
    """Como `_base`, pero con una deuda de 250 sobre una capitalización de 1.000.

    El peso de la deuda es 0,2 justo, así que el redondeo de su procedencia no
    mete error y la comparación con `deducir` puede ser estricta. El coste de la
    deuda medido es `gasto / 250`.
    """
    ejercicios = [_ejercicio(2026 - i, gasto_financiero=gasto) for i in range(4)]
    f = _fundamentos(ejercicios=ejercicios, deuda_total=250.0)
    return _deducir(f, _perfil(), r_f, beta, 0.21, 0.10)


def _costes(s):
    return (s.k_e.valor, s.wacc.valor)


def test_sin_cambios_los_supuestos_son_los_mismos():
    s = _base()
    assert aplicar(s, {}) is s


def test_mover_un_supuesto_a_su_propio_valor_no_cuenta():
    # La pantalla diría «movido por ti; el programa decía 1.13» junto a 1.13.
    s = _base()
    assert aplicar(s, {"beta": s.beta.valor}) is s
    assert movidos(aplicar(s, {"beta": s.beta.valor, "g_ref": 0.3})) == ("g_ref",)


def test_mover_el_crecimiento_no_toca_el_coste_de_capital():
    s = _base()
    n = aplicar(s, {"g_ref": 0.30})
    assert n.g_ref.valor == 0.30
    assert n.g_ref.procedencia == {"fuente": "usuario", "programa": s.g_ref.valor}
    assert (n.k_e, n.wacc) == (s.k_e, s.wacc)


def test_mover_la_beta_recalcula_el_capital_propio_y_el_de_capital():
    s = _exacta()
    n = aplicar(s, {"beta": 2.0})
    a, b = _BLUME
    esperado = _exacta(beta=_Beta((2.0 - b) / a, 0.4, 104, "^GSPC"))
    assert _costes(n) == pytest.approx(_costes(esperado))
    assert n.k_e.procedencia == {**s.k_e.procedencia, "recalculado": True}
    assert n.wacc.procedencia == {**s.wacc.procedencia, "recalculado": True}


def test_mover_la_prima_da_los_costes_de_deducir(monkeypatch):
    n = aplicar(_exacta(), {"prima": 0.06})
    monkeypatch.setattr("valoracion.supuestos.PRIMA_RIESGO", 0.06)
    assert _costes(n) == pytest.approx(_costes(_exacta()))


def test_mover_el_coste_de_la_deuda_da_el_coste_de_capital_de_deducir():
    s = _exacta()
    n = aplicar(s, {"k_d": 0.12})
    assert n.k_e == s.k_e
    assert n.wacc.valor == pytest.approx(_exacta(gasto=0.12 * 250).wacc.valor)


def test_mover_los_impuestos_da_el_coste_de_capital_de_deducir():
    # Con el peso de la deuda redondeado (1/6 en `_base`): el error del redondeo
    # es de segundo orden y queda por debajo de la millonésima.
    s = _base()
    n = aplicar(s, {"t": s.t.valor + 0.01})
    assert n.k_e == s.k_e
    assert n.wacc.valor == pytest.approx(_base(tasa=s.t.valor + 0.01).wacc.valor, rel=1e-6)


def test_mover_la_tasa_libre_arrastra_al_coste_de_la_deuda_sin_dato():
    # Sin gasto financiero declarado, el coste de la deuda ES la tasa libre.
    ejercicios = [_ejercicio(2026 - i, gasto_financiero=float("nan")) for i in range(4)]
    s = _deducir(_fundamentos(ejercicios=ejercicios), _perfil(), 0.05, None, 0.21, 0.10)
    assert s.k_d.procedencia["fuente"] == "sin_dato"
    n = aplicar(s, {"r_f": 0.07})
    assert n.k_d.valor == 0.07
    assert n.k_d.procedencia["recalculado"] is True


def test_mover_la_tasa_libre_y_el_coste_de_la_deuda_a_la_vez():
    # El coste de la deuda sin dato sigue a la tasa libre, salvo que el usuario
    # lo mueva también.
    s = _exacta(gasto=float("nan"))
    assert s.k_d.procedencia["fuente"] == "sin_dato"
    n = aplicar(s, {"r_f": 0.07, "k_d": 0.09})
    assert n.k_d.valor == 0.09
    assert n.k_d.procedencia["fuente"] == "usuario"
    assert _costes(n) == pytest.approx(_costes(_exacta(r_f=0.07, gasto=0.09 * 250)))


@pytest.mark.parametrize(
    "antes, despues, gasto",
    [
        (0.02, 0.05, 20.0),
        (0.05, 0.02, 20.0),
        (0.05, 0.07, 5.0),
        (0.05, 0.01, 5.0),
        (0.05, 0.10, 50.0),
        (0.05, 0.11, 25.0),
        (0.05, 0.07, 23.33),
    ],
    ids=[
        "g_perpetuo_recortado_deja_de_estarlo",
        "g_perpetuo_pasa_a_recortado",
        "k_d_acotado_por_abajo_sube_con_la_tasa",
        "k_d_acotado_por_abajo_deja_de_estarlo",
        "k_d_acotado_por_arriba",
        "k_d_sin_acotar_pasa_a_acotado",
        "k_d_sin_acotar_conserva_su_valor_exacto",
    ],
)
def test_mover_la_tasa_libre_da_lo_mismo_que_deducir_con_ella(antes, despues, gasto):
    # Lo que en `deducir` depende de la tasa libre (el crecimiento a perpetuidad
    # recortado a ella, la banda del coste de la deuda) se rehace con la nueva.
    n = aplicar(_exacta(r_f=antes, gasto=gasto), {"r_f": despues})
    esperado = _exacta(r_f=despues, gasto=gasto)
    for campo in _campos(esperado):
        if campo.name == "r_f":
            continue
        nuevo, deducido = getattr(n, campo.name), getattr(esperado, campo.name)
        assert nuevo.valor == pytest.approx(deducido.valor), campo.name
        sin_marca = {k: v for k, v in nuevo.procedencia.items() if k != "recalculado"}
        assert sin_marca == deducido.procedencia, campo.name


def test_un_crecimiento_perpetuo_que_cambia_con_la_tasa_libre_lo_dice():
    s = _base()
    assert aplicar(s, {"r_f": 0.02}).g_perpetuo.procedencia == {
        "fuente": "recortado_a_r_f",
        "base": 0.025,
        "recalculado": True,
    }
    assert aplicar(s, {"r_f": 0.07}).g_perpetuo == s.g_perpetuo


def test_un_crecimiento_perpetuo_movido_no_lo_rehace_la_tasa_libre():
    assert aplicar(_base(), {"r_f": 0.02, "g_perpetuo": 0.03}).g_perpetuo.valor == 0.03


def test_un_coste_de_la_deuda_medido_dentro_de_la_banda_no_sigue_a_la_tasa_libre():
    s = _base()
    assert s.k_d.procedencia["fuente"] == "gasto_entre_deuda"
    assert aplicar(s, {"r_f": 0.07}).k_d == s.k_d


def test_en_una_financiera_el_coste_de_capital_sigue_vacio():
    s = _deducir(_fundamentos(), _perfil(industria="Banks - Regional"), 0.05, None, 0.21, 0.10)
    n = aplicar(s, {"beta": 1.5})
    assert n.wacc.valor is None
    assert n.k_e.procedencia["recalculado"] is True


@pytest.mark.parametrize("nombre", ["k_d", "t"])
def test_en_una_financiera_no_se_mueve_lo_que_no_se_usa(nombre):
    # El distintivo diría «con tus supuestos» sin ningún cambio visible.
    s = _deducir(_fundamentos(), _perfil(industria="Banks - Regional"), 0.05, None, 0.21, 0.10)
    with pytest.raises(ValueError, match=rf"\b{nombre}\b"):
        aplicar(s, {nombre: 0.08})


def test_lo_derivado_no_se_mueve_a_mano():
    with pytest.raises(ValueError, match="k_e"):
        aplicar(_base(), {"k_e": 0.1})
    assert "k_e" not in MOVIBLES and "wacc" not in MOVIBLES


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), "x", None, True, False])
def test_un_valor_que_no_es_un_numero_finito_se_rechaza(valor):
    with pytest.raises(ValueError):
        aplicar(_base(), {"g_ref": valor})


@pytest.mark.parametrize(
    "nombre, valor",
    [("payout", -0.1), ("payout", 1.1), ("t", -0.01), ("t", 1.0)],
)
def test_un_reparto_o_unos_impuestos_imposibles_se_rechazan(nombre, valor):
    # No se acotan en silencio: la pantalla diría «movido por ti» con un valor
    # que el usuario no eligió.
    with pytest.raises(ValueError, match=rf"\b{nombre}\b"):
        aplicar(_base(), {nombre: valor})


@pytest.mark.parametrize("nombre, valor", [("payout", 0.0), ("payout", 1.0), ("t", 0.0)])
def test_los_extremos_posibles_se_aceptan(nombre, valor):
    assert getattr(aplicar(_base(), {nombre: valor}), nombre).valor == valor


def test_un_coste_del_capital_propio_nulo_se_rechaza():
    # Los mínimos naturales de dos deslizadores: con ellos, `epv` dividía entre cero.
    with pytest.raises(ValueError, match="k_e"):
        aplicar(_base(), {"r_f": 0.0, "beta": 0.0})


def test_un_coste_de_capital_negativo_se_rechaza():
    with pytest.raises(ValueError, match="wacc"):
        aplicar(_base(), {"k_d": -1.0})


def test_una_beta_negativa_sola_es_valida():
    # Las mineras de oro la tienen: lo que importa es el coste que resulta.
    n = aplicar(_base(), {"beta": -0.5})
    assert n.k_e.valor == pytest.approx(0.05 - 0.5 * n.prima.valor)


def test_movidos_dice_cuales_movio_el_usuario_en_el_orden_de_siempre():
    assert movidos(aplicar(_base(), {"g_ref": 0.3, "beta": 2.0})) == ("beta", "g_ref")
    assert movidos(_base()) == ()
