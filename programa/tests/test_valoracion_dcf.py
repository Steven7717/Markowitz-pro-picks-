import math
from dataclasses import replace

import pytest

from valoracion.dcf import (
    Datos,
    crecimientos,
    margen_fcff,
    valor_empresa,
    valor_por_accion,
)
from valoracion.inverso import ABAJO, ARRIBA, crecimiento_implicito

from tests.dobles_valoracion import ejercicio, fundamentos

DATOS = Datos(
    ingresos=1000.0,
    margen=0.15,
    wacc=0.09,
    g_perpetuo=0.025,
    deuda=0.0,
    efectivo=0.0,
    acciones=10.0,
)


def test_cinco_anos_altos_y_cinco_de_convergencia():
    g = crecimientos(0.20, 0.02)
    assert len(g) == 10
    assert g[:5] == [0.20] * 5
    assert g[5] == pytest.approx(0.164)
    assert g[9] == pytest.approx(0.02)


def test_con_crecimiento_constante_el_dcf_es_gordon():
    # Referencia positiva: una perpetuidad creciente es una suma geométrica, y
    # el DCF de diez años más valor terminal tiene que darla exacta.
    flujo_1 = 1000.0 * 1.03 * 0.10
    assert valor_empresa(1000.0, 0.10, 0.03, 0.03, 0.09) == pytest.approx(
        flujo_1 / (0.09 - 0.03), rel=1e-12
    )


def test_sin_holgura_gordon_no_hay_valor():
    assert valor_empresa(1000.0, 0.10, 0.05, 0.03, 0.035) is None


def test_con_la_holgura_justa_hay_valor_aunque_el_flotante_diga_lo_contrario():
    # 0,036 − 0,026 es exactamente un punto, pero en coma flotante da un
    # poco menos: sin tolerancia, el redondeo decidiría si hay valor.
    assert 0.036 - 0.026 < 0.01
    assert valor_empresa(1000.0, 0.10, 0.03, 0.026, 0.036) is not None


def test_dos_etapas_contra_un_valor_presente_escrito_a_mano():
    # Oráculo propio, sin dependencias ni `crecimientos`: el valor presente de
    # los diez flujos y del terminal, sumado término a término.
    g_alto, g_perpetuo, wacc, margen = 0.12, 0.025, 0.09, 0.15
    ritmos = [g_alto] * 5 + [g_alto + (g_perpetuo - g_alto) * k / 5 for k in range(1, 6)]
    ingresos, flujos = 1000.0, []
    for ritmo in ritmos:
        ingresos *= 1 + ritmo
        flujos.append(ingresos * margen)
    terminal = flujos[-1] * (1 + g_perpetuo) / (wacc - g_perpetuo)
    caja = [0.0, *flujos[:-1], flujos[-1] + terminal]
    esperado = sum(c / (1 + wacc) ** t for t, c in enumerate(caja))
    assert valor_empresa(1000.0, margen, g_alto, g_perpetuo, wacc) == pytest.approx(esperado)


def test_con_todo_plano_el_valor_es_una_perpetuidad_sin_crecimiento():
    # Sin crecimiento en ninguna etapa, flujo y terminal se suman a 100 / 0,09.
    assert valor_empresa(1000.0, 0.10, 0.0, 0.0, 0.09) == pytest.approx(100.0 / 0.09)


def test_el_valor_por_accion_resta_deuda_y_suma_efectivo():
    datos = replace(DATOS, deuda=300.0, efectivo=100.0)
    ve = valor_empresa(1000.0, 0.15, 0.10, 0.025, 0.09)
    assert valor_por_accion(datos, 0.10) == pytest.approx((ve - 300.0 + 100.0) / 10.0)


def test_otro_coste_de_capital_sustituye_al_de_los_datos():
    assert valor_por_accion(DATOS, 0.10, wacc=0.10) < valor_por_accion(DATOS, 0.10)


def test_sin_holgura_el_valor_por_accion_y_el_inverso_no_responden():
    datos = replace(DATOS, wacc=0.03)
    assert valor_por_accion(datos, 0.10) is None
    implicito = crecimiento_implicito(datos, 50.0)
    assert implicito.valor is None and implicito.fuera_de_limites is None


def test_contraste_contra_numpy_financial():
    # Contraste opcional: el oráculo de arriba ya no depende de esta librería.
    npf = pytest.importorskip("numpy_financial")
    ingresos, flujos = 1000.0, []
    for g in crecimientos(0.12, 0.025):
        ingresos *= 1 + g
        flujos.append(ingresos * 0.15)
    terminal = flujos[-1] * 1.025 / (0.09 - 0.025)
    esperado = npf.npv(0.09, [0.0, *flujos[:-1], flujos[-1] + terminal])
    assert valor_empresa(1000.0, 0.15, 0.12, 0.025, 0.09) == pytest.approx(esperado)


def test_el_margen_de_flujo_libre_suma_los_intereses_despues_de_impuestos():
    f = fundamentos()
    assert margen_fcff(f, t=0.25) == pytest.approx((300 - 100 + 20 * 0.75) / 1000)


def test_el_margen_es_la_mediana_de_los_anos():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, flujo_operativo=300.0),
            ejercicio(2025, flujo_operativo=900.0),
            ejercicio(2024, flujo_operativo=200.0),
        ]
    )
    assert margen_fcff(f, t=0.25) == pytest.approx((300 - 100 + 15) / 1000)


def test_con_anos_pares_la_mediana_promedia_los_dos_centrales():
    # Márgenes 0,215, 0,315, 0,415 y 0,815: la mediana es la media de los dos
    # centrales, no uno de ellos.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, flujo_operativo=300.0),
            ejercicio(2025, flujo_operativo=400.0),
            ejercicio(2024, flujo_operativo=500.0),
            ejercicio(2023, flujo_operativo=900.0),
        ]
    )
    assert margen_fcff(f, t=0.25) == pytest.approx((315 + 415) / 2 / 1000)


@pytest.mark.parametrize("campo", ["capex", "flujo_operativo", "ingresos"])
def test_un_ano_con_un_dato_sin_declarar_no_cuenta(campo):
    # NaN es «no declarado», no cero: tratarlo como cero inflaría el margen.
    f = fundamentos(
        ejercicios=[ejercicio(2026), ejercicio(2025), ejercicio(2024, **{campo: math.nan})]
    )
    assert margen_fcff(f, t=0.25) == pytest.approx((300 - 100 + 15) / 1000)


def test_con_un_solo_ano_no_hay_margen():
    assert margen_fcff(fundamentos(ejercicios=[ejercicio(2026)]), t=0.25) is None


def test_un_ano_sin_ingresos_no_cuenta():
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025, ingresos=0.0)])
    assert margen_fcff(f, t=0.25) is None


def test_un_gasto_financiero_negativo_no_suma_intereses():
    # DIS y FTV declaran un gasto financiero negativo (ingreso financiero neto):
    # sumarlo con `abs` lo trataría como una deuda que no tienen.
    negativo = fundamentos(
        ejercicios=[ejercicio(2026, gasto_financiero=-20.0), ejercicio(2025, gasto_financiero=-20.0)]
    )
    cero = fundamentos(
        ejercicios=[ejercicio(2026, gasto_financiero=0.0), ejercicio(2025, gasto_financiero=0.0)]
    )
    assert margen_fcff(negativo, t=0.25) == pytest.approx(margen_fcff(cero, t=0.25))
    assert margen_fcff(negativo, t=0.25) == pytest.approx((300 - 100) / 1000)


def test_el_inverso_devuelve_el_crecimiento_de_partida():
    precio = valor_por_accion(DATOS, 0.12)
    implicito = crecimiento_implicito(DATOS, precio)
    assert implicito.valor == pytest.approx(0.12, abs=1e-8)
    assert implicito.fuera_de_limites is None


def test_un_precio_inalcanzable_queda_por_arriba():
    implicito = crecimiento_implicito(DATOS, 1e12)
    assert implicito.valor is None and implicito.fuera_de_limites == ARRIBA


def test_un_precio_minimo_queda_por_abajo():
    implicito = crecimiento_implicito(DATOS, 1e-9)
    assert implicito.valor is None and implicito.fuera_de_limites == ABAJO


@pytest.mark.parametrize("campo", ["deuda", "efectivo", "margen", "ingresos"])
def test_un_dato_sin_declarar_no_se_convierte_en_un_crecimiento_implicito(campo):
    # Con un NaN el valor por acción es NaN en los dos extremos: sin guardia,
    # la bisección se pega al límite de abajo y devuelve −30 % sin avisar.
    implicito = crecimiento_implicito(replace(DATOS, **{campo: math.nan}), 50.0)
    assert implicito.valor is None and implicito.fuera_de_limites is None


def test_un_precio_sin_declarar_no_se_convierte_en_un_crecimiento_implicito():
    implicito = crecimiento_implicito(DATOS, math.nan)
    assert implicito.valor is None and implicito.fuera_de_limites is None


@pytest.mark.parametrize("margen", [0.0, -0.05])
def test_sin_margen_positivo_el_inverso_no_responde(margen):
    # Con margen cero el valor es el mismo para todo `g`, y con margen negativo
    # decrece: la bisección sólo vale para una función creciente.
    implicito = crecimiento_implicito(replace(DATOS, margen=margen), 50.0)
    assert implicito.valor is None and implicito.fuera_de_limites is None
