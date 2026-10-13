import dataclasses
import math

import pytest

from valoracion.epv import epv_por_accion, margen_operativo, parte_crecimiento
from valoracion.inverso import ARRIBA, Implicito
from valoracion.residual import (
    DatosResidual,
    roe_implicito,
    valor_por_accion,
    valor_residual,
)

from tests.dobles_valoracion import ejercicio, fundamentos


# --- EPV ----------------------------------------------------------------------


def test_el_epv_capitaliza_el_beneficio_operativo_sin_crecer():
    # Margen operativo 0,20 sobre ingresos de 1.000: 200 × 0,75 / 0,10 = 1.500,
    # menos 100 de deuda y más 50 de efectivo, entre 10 acciones.
    valor, motivo = epv_por_accion(fundamentos(), t=0.25, wacc=0.10, deuda=100.0, efectivo=50.0, acciones=10.0)
    assert valor == pytest.approx(145.0)
    assert motivo is None


def test_el_epv_parte_de_los_ingresos_del_ultimo_ejercicio():
    # Con ingresos distintos cada año, el margen (0,20) sale de los tres pero el
    # beneficio que se capitaliza es el del último: 0,20 × 2.000, no el de la media.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, ingresos=2000.0, beneficio_operativo=400.0),
            ejercicio(2025, ingresos=1000.0, beneficio_operativo=200.0),
            ejercicio(2024, ingresos=500.0, beneficio_operativo=100.0),
        ]
    )
    valor, motivo = epv_por_accion(f, 0.0, 0.10, 0.0, 0.0, 10.0)
    assert valor == pytest.approx(0.2 * 2000.0 / 0.10 / 10.0)
    assert motivo is None


def test_con_beneficio_operativo_negativo_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, beneficio_operativo=-10.0) for i in range(3)])
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "ebit_negativo")


def test_con_beneficio_operativo_cero_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, beneficio_operativo=0.0) for i in range(3)])
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "ebit_negativo")


def test_con_deuda_neta_mayor_que_el_negocio_el_epv_sale_negativo_sin_motivo():
    # 200 × 0,75 / 0,10 = 1.500 de empresa y 2.000 de deuda: el valor de la acción
    # es negativo, y es un resultado y no un fallo: el motivo queda vacío.
    valor, motivo = epv_por_accion(fundamentos(), 0.25, 0.10, 2000.0, 0.0, 10.0)
    assert valor == pytest.approx(-50.0)
    assert motivo is None


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


def test_con_dos_anos_ya_hay_margen():
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025)])
    assert margen_operativo(f) == pytest.approx(0.20)


def test_un_ejercicio_sin_beneficio_operativo_declarado_no_cuenta():
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025, beneficio_operativo=math.nan), ejercicio(2024)])
    assert margen_operativo(f) == pytest.approx(0.20)


def test_con_dos_ejercicios_validos_de_tres_hay_epv_y_con_uno_no():
    dos = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025, beneficio_operativo=math.nan), ejercicio(2024)])
    uno = fundamentos(
        ejercicios=[
            ejercicio(2026),
            ejercicio(2025, beneficio_operativo=math.nan),
            ejercicio(2024, beneficio_operativo=math.nan),
        ]
    )
    assert epv_por_accion(dos, 0.25, 0.10, 0.0, 0.0, 10.0)[1] is None
    assert margen_operativo(uno) is None


def test_un_ejercicio_sin_ingresos_no_cuenta():
    # El año sin ingresos (NaN o cero) se descarta entero: queda uno solo.
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025, ingresos=math.nan), ejercicio(2024, ingresos=0.0)])
    assert margen_operativo(f) is None
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_historia")


@pytest.mark.parametrize("anos", [2, 4])
def test_si_ninguna_empresa_declara_beneficio_operativo_el_motivo_no_es_la_historia(anos):
    # XOM, JNJ, LLY, MRK, PFE, IBM y GE no etiquetan OperatingIncomeLoss: tienen
    # años de sobra y lo que falta es el dato, y «sin historia» mentiría. Con dos
    # años, el mínimo de historia, ya cuenta.
    f = fundamentos(ejercicios=[ejercicio(2026 - i, beneficio_operativo=math.nan) for i in range(anos)])
    assert margen_operativo(f) is None
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_beneficio_operativo")


def test_con_un_solo_beneficio_operativo_declarado_tampoco_hay_margen():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026),
            ejercicio(2025, beneficio_operativo=math.nan),
            ejercicio(2024, beneficio_operativo=math.nan),
        ]
    )
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_beneficio_operativo")


def test_con_un_solo_ejercicio_con_ingresos_el_motivo_es_la_historia():
    # El otro año no tiene ingresos ni beneficio operativo: aquí sí falta historia.
    f = fundamentos(
        ejercicios=[ejercicio(2026), ejercicio(2025, ingresos=math.nan, beneficio_operativo=math.nan)]
    )
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_historia")


def test_con_ingresos_del_ultimo_ejercicio_sin_declarar_no_hay_epv():
    # Antes decía «ebit_negativo»: el producto con NaN no es mayor que cero, y la
    # causa es otra, que el beneficio que se capitaliza no se puede calcular.
    f = fundamentos(ejercicios=[ejercicio(2026, ingresos=math.nan), ejercicio(2025), ejercicio(2024)])
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_historia")


def test_la_parte_del_precio_que_es_crecimiento():
    assert parte_crecimiento(145.0, 200.0) == pytest.approx(0.275)
    assert parte_crecimiento(-5.0, 200.0) is None


def test_la_parte_de_crecimiento_exige_epv_y_precio_positivos():
    assert parte_crecimiento(0.0, 100.0) is None
    assert parte_crecimiento(10.0, 0.0) is None
    assert parte_crecimiento(10.0, -5.0) is None


# --- Beneficio residual -------------------------------------------------------

G = 0.025
DATOS = DatosResidual(patrimonio=1000.0, k_e=0.09, payout=0.4, g_perpetuo=G, acciones=10.0)


@pytest.mark.parametrize("payout", [0.0, 0.4, 1.0])
def test_con_roe_igual_al_coste_el_valor_es_el_contable(payout):
    # Referencia positiva: sin exceso de rentabilidad no hay nada que sumar, ni en
    # los diez años ni en el valor terminal, repartan lo que repartan.
    assert valor_residual(1000.0, 0.10, 0.10, payout, G) == pytest.approx(1000.0, rel=1e-12)


def test_si_lo_retenido_crece_como_el_perpetuo_el_valor_es_el_de_gordon():
    # Oráculo independiente: con el patrimonio creciendo siempre a g, el exceso
    # de cada año es (ROE − k_e) × BV_0 × (1 + g)^(t−1), y la suma entera vale
    # BV_0 × (ROE − g) / (k_e − g) = 1.000 × 0,125 / 0,065.
    roe, k_e = 0.15, 0.09
    payout = 1 - G / roe
    assert valor_residual(1000.0, roe, k_e, payout, G) == pytest.approx(1000.0 * 0.125 / 0.065, rel=1e-12)


def _por_dividendos(patrimonio, roe, k_e, payout, g):
    """El valor por la vía de los dividendos, sin pasar por el exceso de rentabilidad.

    Superávit limpio: el valor de los dividendos de diez años, más el patrimonio
    final y el valor terminal de su exceso, tiene que coincidir con el patrimonio
    de hoy más el exceso descontado. Es otro camino a la misma cifra.
    """
    libros, valor = patrimonio, 0.0
    for ano in range(1, 11):
        beneficio = roe * libros
        # Con pérdida no hay reparto y el patrimonio la absorbe entera.
        nuevo = libros + (beneficio * (1 - payout) if beneficio > 0 else beneficio)
        dividendo = beneficio - (nuevo - libros)
        valor += dividendo / (1 + k_e) ** ano
        libros = nuevo
    terminal = (roe - k_e) * libros / (k_e - g)
    return valor + (libros + terminal) / (1 + k_e) ** 10


@pytest.mark.parametrize(
    "roe, k_e, payout",
    [
        (0.12, 0.09, 0.0),
        (0.12, 0.09, 1.0),
        (-0.05, 0.09, 0.4),
        (0.30, 0.09, 0.4),
        (0.05, 0.10, 0.7),
    ],
)
def test_el_valor_residual_coincide_con_el_de_los_dividendos(roe, k_e, payout):
    assert valor_residual(1000.0, roe, k_e, payout, G) == pytest.approx(
        _por_dividendos(1000.0, roe, k_e, payout, G), rel=1e-12
    )


def test_mas_rentabilidad_mas_valor():
    def valor(roe):
        return valor_residual(1000.0, roe, 0.10, 0.4, G)

    assert valor(0.15) > valor(0.12) > 1000.0 > valor(0.08)


def test_el_valor_crece_con_el_roe_donde_el_inverso_lo_necesita():
    # La bisección exige una función creciente. Lo es de 0 al límite de arriba...
    valores = [valor_por_accion(DATOS, roe / 100) for roe in range(0, 61)]
    assert all(a < b for a, b in zip(valores, valores[1:]))


def test_donde_el_valor_deja_de_crecer_con_el_roe_ya_es_negativo():
    # ...y por debajo de cero no lo es: una pérdida se come el patrimonio, y con
    # un patrimonio menor las pérdidas de los años siguientes pesan menos. Esa
    # zona vale menos que cero, así que ningún precio positivo la alcanza y la
    # bisección no puede equivocarse en ella.
    assert all(valor_por_accion(DATOS, -0.20 + roe / 100) < 0 for roe in range(0, 21))


def test_sin_holgura_de_gordon_no_hay_valor():
    # k_e − g = 0,005, por debajo de la holgura: el valor terminal explotaría.
    assert valor_residual(1000.0, 0.12, 0.03, 0.4, G) is None
    sin_holgura = dataclasses.replace(DATOS, k_e=0.03)
    assert valor_por_accion(sin_holgura, 0.12) is None


def test_una_holgura_exactamente_en_el_liston_cuenta():
    # 0,036 − 0,026 sale en coma flotante una pizca por debajo de 0,01: sin la
    # tolerancia del DCF decidiría el redondeo y no el criterio.
    assert valor_residual(1000.0, 0.12, 0.036, 0.4, 0.026) is not None


@pytest.mark.parametrize("k_e", [math.nan, math.inf, 0.0, -0.01])
def test_un_coste_del_capital_no_valido_no_da_valor(k_e):
    # Con g negativo la holgura de Gordon se cumple incluso con k_e cero o
    # negativo: es la guarda del propio coste la que tiene que parar.
    datos = dataclasses.replace(DATOS, g_perpetuo=-0.05)
    assert valor_por_accion(datos, 0.12, k_e=k_e) is None


def test_el_valor_por_accion_reparte_entre_las_acciones():
    datos = dataclasses.replace(DATOS, acciones=4.0)
    assert valor_por_accion(datos, 0.14) == pytest.approx(valor_residual(1000.0, 0.14, 0.09, 0.4, G) / 4.0)
    assert valor_por_accion(DATOS, 0.09) == pytest.approx(100.0)


def test_el_coste_alternativo_solo_mueve_el_descuento():
    # Sin ROE que converja al coste, `k_e` ya no es destino de nada: sólo descuenta.
    alto = valor_por_accion(DATOS, 0.14, k_e=0.11)
    assert alto == pytest.approx(valor_residual(1000.0, 0.14, 0.11, 0.4, G) / 10.0)
    assert alto < valor_por_accion(DATOS, 0.14)


@pytest.mark.parametrize("roe", [0.03, 0.14, 0.55])
def test_el_roe_implicito_devuelve_el_de_partida(roe):
    precio = valor_por_accion(DATOS, roe)
    implicito = roe_implicito(DATOS, precio)
    assert implicito.valor == pytest.approx(roe, abs=1e-6)
    assert implicito.fuera_de_limites is None


def test_un_precio_positivo_nunca_sale_por_abajo():
    # El valor con el ROE del límite de abajo es negativo, así que un precio
    # positivo, por bajo que sea, siempre se alcanza: sale el ROE donde el valor
    # se anula (algo menos del 2 % con estos datos).
    implicito = roe_implicito(DATOS, 0.01)
    assert implicito.fuera_de_limites is None
    assert 0.0 < implicito.valor < 0.03


def test_un_precio_inalcanzable_exige_mas_roe_del_limite():
    assert roe_implicito(DATOS, 1e9).fuera_de_limites == ARRIBA


@pytest.mark.parametrize(
    "sobre",
    [
        dict(patrimonio=-1000.0),
        dict(patrimonio=0.0),
        dict(patrimonio=math.nan),
        dict(acciones=0.0),
        dict(acciones=-10.0),
    ],
)
def test_sin_patrimonio_ni_acciones_positivos_no_hay_valor_ni_inverso(sobre):
    # Con patrimonio negativo el signo del exceso se invierte y la función deja
    # de ser creciente en el ROE: no hay respuesta, no una equivocada.
    datos = dataclasses.replace(DATOS, **sobre)
    assert valor_por_accion(datos, 0.14) is None
    assert roe_implicito(datos, 100.0) == Implicito(None, None)
