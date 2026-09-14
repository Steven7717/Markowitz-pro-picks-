import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import (
    KPIS_CRECIMIENTO,
    KPIS_NIVEL,
    KPIS_VALORACION,
    TODOS_LOS_KPIS,
    compute_growth,
    compute_levels,
    compute_valuation,
)

# Empresa sintetica: cada cifra elegida para que los KPIs salgan redondos.
# Es el control negativo del motor — si un KPI no da su valor de aqui, el motor
# esta mal, y ningun error puede disimularse en un promedio.
# En millones de dolares, no en decenas. La guarda del gasto financiero es un
# minimo **economico** —por debajo de un millon al trimestre no hay coste que
# cubrir— asi que una empresa de juguete con 25 dolares de intereses la disparia
# y el control negativo dejaria de medir lo que dice medir. Los cocientes salen
# iguales a cualquier escala; el BPA no se escala, porque es por accion, y con
# 50 millones de acciones cuadra con el beneficio: 100e6 / 50e6 = 2,00.
M = 1e6

EMPRESA = {
    "ingresos": 1000.0 * M,
    "coste_de_ventas": 600.0 * M,           # margen bruto = 40%
    "beneficio_operativo": 200.0 * M,       # margen operativo = 20%
    "beneficio_neto": 100.0 * M,            # margen neto = 10%
    "depreciacion_amortizacion": 50.0 * M,  # EBITDA = 250; TTM = 1000
    "gasto_por_intereses": 25.0 * M,        # cobertura = 200/25 = 8
    "activos_totales": 2000.0 * M,
    "activos_corrientes": 500.0 * M,
    "pasivos_corrientes": 250.0 * M,        # razon corriente = 2
    "patrimonio_neto": 500.0 * M,           # ROE = 100/500 = 20%
    "deuda_total": 400.0 * M,
    "efectivo": 150.0 * M,                  # deuda neta = 250; /EBITDA TTM = 0.25
    "flujo_operativo": 180.0 * M,
    "capex": 60.0 * M,                      # FCF = 120; margen 12%; FCF/BN = 1.2
    "bpa_diluido": 2.0,
    "acciones_diluidas": 50.0 * M,
}

# Cuatro trimestres, no uno. Los multiplos de flujo se miden sobre doce meses
# moviles, asi que una fila suelta no tiene TTM y la cuenta a mano no existiria.
# Con cuatro trimestres identicos el TTM es cuatro veces la cifra trimestral, y
# cada KPI sigue saliendo redondo a mano -- que es el punto de esta empresa.
FECHAS = pd.date_range("2024-06-30", periods=4, freq="QE")
FECHA = FECHAS[-1]


def _lineas(**cambios) -> pd.DataFrame:
    datos = {**EMPRESA, **cambios}
    return pd.DataFrame({k: [v] * len(FECHAS) for k, v in datos.items()}, index=FECHAS)


def _serie(valores: list[float], columna: str) -> pd.DataFrame:
    """Trimestres consecutivos, del mas antiguo al mas reciente."""
    fechas = pd.date_range("2024-03-31", periods=len(valores), freq="QE")
    datos = {k: [v] * len(valores) for k, v in EMPRESA.items()}
    datos[columna] = valores
    return pd.DataFrame(datos, index=fechas)


# ---------------------------------------------------------------- niveles

@pytest.mark.parametrize(
    "kpi, esperado",
    [
        ("margen_bruto", 0.40),
        ("margen_operativo", 0.20),
        ("margen_neto", 0.10),
        ("roe", 0.20),
        ("roic", 100.0 / 750.0),      # BN / (patrimonio 500 + deuda 400 - efectivo 150)
        # Deuda neta 250 sobre el EBITDA de doce meses, 4 x 250 = 1000.
        ("deuda_neta_ebitda", 0.25),
        ("cobertura_intereses", 8.0),
        ("razon_corriente", 2.0),
        ("margen_fcf", 0.12),
        ("fcf_sobre_beneficio", 1.2),
    ],
)
def test_each_level_kpi_matches_its_hand_computed_value(kpi, esperado):
    assert compute_levels(_lineas()).loc[FECHA, kpi] == pytest.approx(esperado)


def test_every_declared_level_kpi_is_produced():
    """Un KPI declarado pero no calculado seria una columna vacia que nadie nota."""
    assert sorted(compute_levels(_lineas()).columns) == sorted(KPIS_NIVEL)


def test_zero_equity_yields_missing_not_an_astronomical_roe():
    """El defecto exacto del estudio D: una guarda que no disparaba dio t = 3.6e16.

    Un ROE de 1e16 se ve como un dato extraordinario, no como una division por cero.
    """
    assert np.isnan(compute_levels(_lineas(patrimonio_neto=0.0)).loc[FECHA, "roe"])


def test_tiny_but_nonzero_equity_also_yields_missing():
    """Una guarda de '== 0' pasa por alto un patrimonio de 1e-12 y explota igual."""
    assert np.isnan(compute_levels(_lineas(patrimonio_neto=1e-12)).loc[FECHA, "roe"])


def test_zero_revenue_yields_missing_margins():
    resultado = compute_levels(_lineas(ingresos=0.0))
    assert np.isnan(resultado.loc[FECHA, "margen_bruto"])
    assert np.isnan(resultado.loc[FECHA, "margen_neto"])


def test_negative_ebitda_yields_no_leverage_ratio():
    """La guarda estaba en el lado equivocado del cociente.

    Con EBITDA negativo, deuda/EBITDA sale negativa -- y el signo -1 del criterio
    la premia como si fuese caja neta. En el panel real colapsaban las dos cosas
    opuestas en 398 de 2.934 celdas: CSGP -670 y COIN -554 no tienen caja neta,
    tienen EBITDA negativo con deuda encima. Un apalancamiento no se puede medir
    contra un EBITDA que no existe; ausente es la unica lectura honesta.
    """
    assert np.isnan(
        compute_levels(_lineas(beneficio_operativo=-500.0 * M)).loc[FECHA, "deuda_neta_ebitda"]
    )


def test_net_cash_still_shows_up_as_a_negative_leverage_ratio():
    """Lo que si es caja neta se queda: una deuda menor que el efectivo es una
    fortaleza real, y el signo -1 del criterio la recompensa con razon."""
    resultado = compute_levels(_lineas(deuda_total=100.0 * M, efectivo=350.0 * M))
    assert resultado.loc[FECHA, "deuda_neta_ebitda"] == pytest.approx(-0.25)


def test_a_negligible_interest_expense_yields_no_coverage_ratio():
    """1e-6 es una guarda numerica y las partidas van en dolares crudos.

    ODFL declaro unos 2.000 dolares de gasto financiero en un trimestre y salio
    con una cobertura de 169.027 veces, contra un p99 de 493 en todo el panel.
    Eso no es una empresa solidisima: es una division por casi-cero con las
    unidades del mundo real. Por debajo de un minimo economico el cociente mide
    redondeo, no solvencia.
    """
    assert np.isnan(
        compute_levels(_lineas(gasto_por_intereses=2000.0)).loc[FECHA, "cobertura_intereses"]
    )


def test_a_loss_yields_no_cash_conversion_ratio():
    """Con beneficio negativo el cociente cambia de signo y miente al reves: una
    empresa que quema caja perdiendo dinero sale con conversion positiva. Es el
    mismo motivo por el que `_yoy` no crece desde una base negativa.
    """
    lineas = _lineas(beneficio_neto=-100.0 * M, flujo_operativo=10.0 * M, capex=60.0 * M)
    assert np.isnan(compute_levels(lineas).loc[FECHA, "fcf_sobre_beneficio"])


def test_the_leverage_ratio_is_measured_against_twelve_trailing_months():
    """Mediana del universo con EBITDA de un trimestre: 7,24x. Real del S&P 500:
    1,5-2,0x. `medidores.py` lo rotula «Deuda neta / EBITDA» y escribe «7,2x», o
    sea que el usuario lee una empresa mediana como siete veces apalancada
    cuando esta por debajo de dos.
    """
    trimestral = 250.0 / 250.0  # deuda neta 250 sobre el EBITDA de un trimestre
    assert compute_levels(_lineas()).loc[FECHA, "deuda_neta_ebitda"] == pytest.approx(
        trimestral / 4
    )


def test_the_first_quarters_have_no_trailing_twelve_month_ratio():
    """Sumar los trimestres que haya subestimaria el denominador y dispararia el
    multiplo. Un hueco declarado es preferible a un ano a medias."""
    assert compute_levels(_lineas())["deuda_neta_ebitda"].iloc[:3].isna().all()


def test_a_missing_quarter_breaks_the_trailing_year_rather_than_shrinking_it():
    lineas = _lineas()
    lineas.loc[FECHAS[1], "beneficio_operativo"] = np.nan
    assert np.isnan(compute_levels(lineas).loc[FECHA, "deuda_neta_ebitda"])


def test_zero_interest_expense_yields_missing_coverage():
    """Una empresa sin deuda no tiene cobertura infinita: no tiene cobertura."""
    assert np.isnan(compute_levels(_lineas(gasto_por_intereses=0.0)).loc[FECHA, "cobertura_intereses"])


def test_a_missing_input_line_yields_a_missing_kpi_not_a_zero():
    resultado = compute_levels(_lineas(coste_de_ventas=np.nan))
    assert np.isnan(resultado.loc[FECHA, "margen_bruto"])
    assert resultado.loc[FECHA, "margen_neto"] == pytest.approx(0.10)


def test_levels_on_an_empty_frame_yield_every_column():
    resultado = compute_levels(pd.DataFrame())
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_NIVEL)


# ------------------------------------------------------------ crecimiento

def test_year_on_year_growth_compares_against_four_quarters_back():
    """Comparar contra el trimestre anterior mide estacionalidad, no crecimiento."""
    lineas = _serie([100.0, 999.0, 999.0, 999.0, 110.0], "ingresos")
    assert compute_growth(lineas)["crecimiento_ingresos"].iloc[4] == pytest.approx(0.10)


def test_the_first_four_quarters_have_no_growth_value():
    """Sin homologo del ano anterior no hay dato. Extrapolar seria inventarlo."""
    resultado = compute_growth(_serie([100.0] * 5, "ingresos"))
    assert resultado["crecimiento_ingresos"].iloc[:4].isna().all()


def test_every_declared_growth_kpi_is_produced():
    assert sorted(compute_growth(_serie([100.0] * 8, "ingresos")).columns) == sorted(KPIS_CRECIMIENTO)


def test_a_zero_base_yields_missing_not_infinite_growth():
    """Crecer desde 0 no es crecimiento infinito: es una magnitud indefinida."""
    lineas = _serie([0.0, 1.0, 1.0, 1.0, 50.0], "ingresos")
    assert np.isnan(compute_growth(lineas)["crecimiento_ingresos"].iloc[4])


def test_a_negative_base_yields_missing():
    """Con base negativa el signo del cociente se invierte y el numero enganna."""
    lineas = _serie([-100.0, 1.0, 1.0, 1.0, -50.0], "ingresos")
    assert np.isnan(compute_growth(lineas)["crecimiento_ingresos"].iloc[4])


def test_a_missing_intermediate_quarter_does_not_shift_the_comparison():
    """Si una fila ausente corriera el shift, se compararia contra el trimestre equivocado."""
    lineas = _serie([100.0, np.nan, 999.0, 999.0, 120.0], "ingresos")
    assert compute_growth(lineas)["crecimiento_ingresos"].iloc[4] == pytest.approx(0.20)


def test_growth_on_an_empty_frame_yields_every_column():
    resultado = compute_growth(pd.DataFrame())
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_CRECIMIENTO)


# ------------------------------------------------------------- valoracion

def _precios(valor: float = 20.0) -> pd.Series:
    return pd.Series([valor] * len(FECHAS), index=FECHAS)


def test_each_valuation_kpi_matches_its_hand_computed_value():
    """Precio 20, 50 acciones -> capitalizacion 1000. EV = 1000 + 400 - 150 = 1250.

    Los denominadores de flujo van en doce meses moviles: BPA 4 x 2 = 8, EBITDA
    4 x 250 = 1000, FCF 4 x 120 = 480. Los de balance -- patrimonio, deuda,
    efectivo -- son instantaneas y entran tal cual.
    """
    resultado = compute_valuation(_lineas(), _precios())
    assert resultado.loc[FECHA, "per"] == pytest.approx(2.5)                   # 20 / 8
    assert resultado.loc[FECHA, "precio_valor_libro"] == pytest.approx(2.0)    # 1000 / 500
    assert resultado.loc[FECHA, "ev_ebitda"] == pytest.approx(1.25)            # 1250 / 1000
    assert resultado.loc[FECHA, "precio_fcf"] == pytest.approx(1000.0 / 480.0)


def test_a_negative_enterprise_value_yields_no_ev_ebitda():
    """`_solo_positivo` protegia el denominador y dejaba pasar el numerador.

    LUV salio con -116,18 y CSGP con -46,00: con el signo -1 del criterio, un
    -116 es la empresa mas barata de su sector. El propio docstring de
    `_solo_positivo` dice que un EV/EBITDA negativo no ordena contra uno
    positivo -- la guarda estaba en el lado equivocado del cociente.
    """
    lineas = _lineas(efectivo=5000.0 * M)  # caja muy por encima de la capitalizacion
    assert np.isnan(compute_valuation(lineas, _precios()).loc[FECHA, "ev_ebitda"])


def test_one_loss_quarter_no_longer_hides_behind_three_good_ones():
    """`_solo_positivo` descarta el trimestre con BPA negativo, de modo que con el
    multiplo trimestral quien pierde dinero un trimestre se puntuaba solo por sus
    tres buenos. Sobre doce meses el trimestre malo entra en la cuenta.
    """
    lineas = _lineas()
    lineas["bpa_diluido"] = [3.0, 3.0, 3.0, -8.0]
    per = compute_valuation(lineas, _precios()).loc[FECHA, "per"]
    assert per == pytest.approx(20.0)  # 20 / (3 + 3 + 3 - 8) = 20 / 1


def test_every_declared_valuation_kpi_is_produced():
    resultado = compute_valuation(_lineas(), _precios())
    assert sorted(resultado.columns) == sorted(KPIS_VALORACION)


def test_a_quarter_without_a_price_yields_missing_valuation():
    """El precio de hoy con fundamentales de hace tres anos da un multiplo inexistente."""
    resultado = compute_valuation(_lineas(), pd.Series(dtype="float64"))
    assert resultado["per"].isna().all()
    assert resultado["ev_ebitda"].isna().all()


def test_negative_earnings_yield_missing_pe():
    """Un PER negativo no ordena: -2 no es 'mas barato' que 10."""
    resultado = compute_valuation(_lineas(bpa_diluido=-2.0), _precios())
    assert np.isnan(resultado.loc[FECHA, "per"])


def test_negative_free_cash_flow_yields_missing_price_to_fcf():
    resultado = compute_valuation(
        _lineas(flujo_operativo=10.0 * M, capex=60.0 * M), _precios()
    )
    assert np.isnan(resultado.loc[FECHA, "precio_fcf"])


def test_zero_shares_outstanding_yields_missing_not_a_huge_multiple():
    resultado = compute_valuation(_lineas(acciones_diluidas=0.0), _precios())
    assert np.isnan(resultado.loc[FECHA, "precio_valor_libro"])


def test_valuation_on_an_empty_frame_yields_every_column():
    resultado = compute_valuation(pd.DataFrame(), pd.Series(dtype="float64"))
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_VALORACION)


def test_the_three_families_together_make_seventeen_kpis_with_no_duplicates():
    """Son 17, no 16 como decia el diseno: 5 de rentabilidad, 3 de crecimiento,
    3 de solidez, 2 de calidad del beneficio y 4 de valoracion. El 16 era una
    suma mal hecha; el conjunto de KPIs no cambio.

    El segundo assert protege contra una colision de nombres entre familias, que
    perderia una columna silenciosamente al concatenarlas.
    """
    assert len(TODOS_LOS_KPIS) == 17
    assert len(set(TODOS_LOS_KPIS)) == 17
