import math
from dataclasses import replace

import pytest

from valoracion.dcf import (
    ANOS,
    Datos,
    crecimientos,
    cumple_gordon,
    margen_fcff,
    proyeccion,
    proyeccion_de,
    terminal,
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


def test_un_poco_por_debajo_de_la_holgura_se_rechaza():
    # La tolerancia del flotante sólo absorbe el ruido, no regala holgura.
    assert valor_empresa(1000.0, 0.10, 0.03, 0.025, 0.0349) is None


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


def test_el_margen_es_el_agregado_de_los_anos():
    # Σ(flujo operativo − capex + intereses × (1 − t)) ÷ Σ ingresos, con
    # intereses 20 × 0,75 = 15 en cada año.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, ingresos=1200.0, flujo_operativo=400.0, capex=100.0),
            ejercicio(2025, ingresos=800.0, flujo_operativo=250.0, capex=90.0),
            ejercicio(2024, ingresos=500.0, flujo_operativo=100.0, capex=40.0),
        ]
    )
    esperado = ((400 - 100 + 15) + (250 - 90 + 15) + (100 - 40 + 15)) / (1200 + 800 + 500)
    assert margen_fcff(f, t=0.25) == pytest.approx(esperado)


def test_el_agregado_pesa_cada_ano_por_su_tamano_y_no_como_la_mediana():
    # Dos años pequeños de valle al 5 % y el actual, diez veces mayor, al 30 %:
    # la mediana diría 5 % y el agregado pesa el año grande.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, ingresos=1000.0, flujo_operativo=300.0, capex=0.0, gasto_financiero=0.0),
            ejercicio(2025, ingresos=100.0, flujo_operativo=5.0, capex=0.0, gasto_financiero=0.0),
            ejercicio(2024, ingresos=100.0, flujo_operativo=5.0, capex=0.0, gasto_financiero=0.0),
        ]
    )
    assert margen_fcff(f, t=0.25) == pytest.approx((5 + 5 + 300) / 1200)
    assert margen_fcff(f, t=0.25) > 0.25


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


def test_un_gasto_financiero_sin_declarar_no_tira_el_ano():
    # NaN suma cero de intereses pero el año sigue contando, con sus ingresos y
    # su flujo: descartarlo dejaría sin margen a una empresa sana.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, gasto_financiero=20.0),
            ejercicio(2025, gasto_financiero=math.nan),
        ]
    )
    esperado = ((300 - 100 + 20 * 0.75) + (300 - 100)) / 2000
    assert margen_fcff(f, t=0.25) == pytest.approx(esperado)


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


# --- La sensibilidad ---------------------------------------------------------

from valoracion.criterio import DELTA_WACC_ESCENARIOS, HOLGURA_GORDON  # noqa: E402
from valoracion.dcf import sensibilidad  # noqa: E402

DATOS_SENSIBILIDAD = Datos(
    ingresos=1000.0, margen=0.2, wacc=0.09, g_perpetuo=0.025,
    deuda=100.0, efectivo=50.0, acciones=10.0,
)


def test_la_casilla_central_es_el_valor_base():
    s = sensibilidad(DATOS_SENSIBILIDAD, 0.08)
    assert s.valores[2][2] == pytest.approx(valor_por_accion(DATOS_SENSIBILIDAD, 0.08))
    assert s.waccs == pytest.approx((0.07, 0.08, 0.09, 0.10, 0.11))
    assert s.gs == pytest.approx((0.015, 0.02, 0.025, 0.03, 0.035))


def test_cada_casilla_es_el_dcf_con_ese_coste_y_ese_crecimiento_perpetuo():
    s = sensibilidad(DATOS_SENSIBILIDAD, 0.08)
    otro = replace(DATOS_SENSIBILIDAD, wacc=0.11, g_perpetuo=0.015)
    assert s.valores[4][0] == pytest.approx(valor_por_accion(otro, 0.08))


def test_las_filas_vecinas_de_la_central_son_los_costes_de_los_escenarios():
    # Ata `PASOS_WACC` a `DELTA_WACC_ESCENARIOS`: la tabla y el rango pesimista
    # y optimista mueven el coste de capital con el mismo paso.
    s = sensibilidad(DATOS_SENSIBILIDAD, 0.08)
    mas = valor_por_accion(DATOS_SENSIBILIDAD, 0.08, DATOS_SENSIBILIDAD.wacc + DELTA_WACC_ESCENARIOS)
    menos = valor_por_accion(DATOS_SENSIBILIDAD, 0.08, DATOS_SENSIBILIDAD.wacc - DELTA_WACC_ESCENARIOS)
    assert s.valores[3][2] == pytest.approx(mas)
    assert s.valores[1][2] == pytest.approx(menos)


def test_sin_holgura_de_gordon_la_casilla_sale_vacia_y_no_recortada():
    s = sensibilidad(replace(DATOS_SENSIBILIDAD, wacc=0.045), 0.08)
    vacias = 0
    for wacc, fila in zip(s.waccs, s.valores):
        for g, valor in zip(s.gs, fila):
            sin_holgura = wacc - g < HOLGURA_GORDON - 1e-12
            assert (valor is None) == sin_holgura
            vacias += sin_holgura
    assert vacias > 0


@pytest.mark.parametrize("wacc", [0.02, 0.07 - 0.05])
def test_con_un_coste_de_capital_no_positivo_la_casilla_sale_vacia(wacc):
    # Gordon sólo mira la diferencia: con coste 0 % y crecimiento −1 % hay
    # holgura y la casilla daba un número. `0.07 - 0.05` deja el coste de la
    # primera fila en 3e-18, un cero que el redondeo vuelve positivo.
    s = sensibilidad(replace(DATOS_SENSIBILIDAD, wacc=wacc, g_perpetuo=0.0), 0.08)
    assert s.valores[0] == (None,) * 5
    assert s.valores[1][0] is not None


def test_un_valor_negativo_sale_como_numero_y_no_vacio():
    # Una deuda mayor que la empresa da un valor por acción negativo: es un
    # resultado, no una casilla sin Gordon.
    s = sensibilidad(replace(DATOS_SENSIBILIDAD, deuda=60000.0), 0.08)
    assert all(isinstance(v, float) and v < 0 for fila in s.valores for v in fila)


def test_mas_coste_de_capital_vale_menos():
    columna = [fila[2] for fila in sensibilidad(DATOS_SENSIBILIDAD, 0.08).valores]
    assert all(a > b for a, b in zip(columna, columna[1:]))


# --- La proyección, que el Analizador enseña plegada ---------------------------


def _en_orden(anos) -> float:
    """Los años descontados sumados uno a uno, como `valor_empresa`.

    No con `sum()`: desde Python 3.12 suma con compensación y difiere del bucle
    en el último bit en uno de cada cinco casos, y `valor_empresa` tiene que dar
    lo mismo que en M hasta el último bit.
    """
    total = 0.0
    for ano in anos:
        total += ano.descontado
    return total


# (0.20, 0.12) y (0.30, 0.10): ahí `sum()` daría otro valor de la empresa.
@pytest.mark.parametrize(
    "g, wacc", [(0.20, 0.09), (0.05, 0.12), (-0.03, 0.08), (0.40, 0.036), (0.20, 0.12), (0.30, 0.10)]
)
def test_el_valor_de_la_empresa_es_la_suma_exacta_de_su_proyeccion(g, wacc):
    anos = proyeccion(1000.0, 0.15, g, 0.025, wacc)
    esperado = _en_orden(anos) + terminal(anos[-1].flujo, 0.025, wacc) / (1 + wacc) ** ANOS
    # Igualdad exacta, no aproximada: la tabla y el valor base son la misma cuenta.
    assert valor_empresa(1000.0, 0.15, g, 0.025, wacc) == esperado


def test_la_proyeccion_son_diez_anos_con_los_crecimientos_del_dcf():
    anos = proyeccion(1000.0, 0.15, 0.20, 0.02, 0.09)
    assert [a.ano for a in anos] == list(range(1, ANOS + 1))
    assert [a.crecimiento for a in anos] == crecimientos(0.20, 0.02)
    assert anos[0].ingresos == pytest.approx(1200.0)
    assert anos[0].flujo == pytest.approx(180.0)
    assert anos[0].descontado == pytest.approx(180.0 / 1.09)


def test_la_holgura_de_gordon_es_la_misma_para_el_valor_y_para_la_tabla():
    assert not cumple_gordon(0.03, 0.025)
    assert valor_empresa(1000.0, 0.15, 0.10, 0.025, 0.03) is None
    assert proyeccion_de(replace(DATOS, wacc=0.03), 0.10) is None
    p = proyeccion_de(DATOS, 0.10)
    assert len(p.anos) == ANOS
    assert _en_orden(p.anos) + p.terminal_descontado == valor_empresa(
        DATOS.ingresos, DATOS.margen, 0.10, DATOS.g_perpetuo, DATOS.wacc
    )
