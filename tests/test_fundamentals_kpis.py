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
EMPRESA = {
    "ingresos": 1000.0,
    "coste_de_ventas": 600.0,           # margen bruto = 40%
    "beneficio_operativo": 200.0,       # margen operativo = 20%
    "beneficio_neto": 100.0,            # margen neto = 10%
    "depreciacion_amortizacion": 50.0,  # EBITDA = 250
    "gasto_por_intereses": 25.0,        # cobertura = 200/25 = 8
    "activos_totales": 2000.0,
    "activos_corrientes": 500.0,
    "pasivos_corrientes": 250.0,        # razon corriente = 2
    "patrimonio_neto": 500.0,           # ROE = 100/500 = 20%
    "deuda_total": 400.0,
    "efectivo": 150.0,                  # deuda neta = 250; /EBITDA 250 = 1.0
    "flujo_operativo": 180.0,
    "capex": 60.0,                      # FCF = 120; margen 12%; FCF/BN = 1.2
    "bpa_diluido": 2.0,
    "acciones_diluidas": 50.0,
}

FECHA = pd.Timestamp("2025-03-31")


def _lineas(**cambios) -> pd.DataFrame:
    datos = {**EMPRESA, **cambios}
    return pd.DataFrame({k: [v] for k, v in datos.items()}, index=[FECHA])


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
        ("deuda_neta_ebitda", 1.0),
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


def test_negative_ebitda_still_produces_a_number():
    """Un EBITDA negativo es informacion real, no un error: no debe suprimirse."""
    assert compute_levels(_lineas(beneficio_operativo=-500.0)).loc[FECHA, "deuda_neta_ebitda"] < 0


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

def test_each_valuation_kpi_matches_its_hand_computed_value():
    """Precio 20, 50 acciones -> capitalizacion 1000. EV = 1000 + 400 - 150 = 1250."""
    resultado = compute_valuation(_lineas(), pd.Series([20.0], index=[FECHA]))
    assert resultado.loc[FECHA, "per"] == pytest.approx(10.0)                  # 20 / 2.0
    assert resultado.loc[FECHA, "precio_valor_libro"] == pytest.approx(2.0)    # 1000 / 500
    assert resultado.loc[FECHA, "ev_ebitda"] == pytest.approx(5.0)             # 1250 / 250
    assert resultado.loc[FECHA, "precio_fcf"] == pytest.approx(1000.0 / 120.0)


def test_every_declared_valuation_kpi_is_produced():
    resultado = compute_valuation(_lineas(), pd.Series([20.0], index=[FECHA]))
    assert sorted(resultado.columns) == sorted(KPIS_VALORACION)


def test_a_quarter_without_a_price_yields_missing_valuation():
    """El precio de hoy con fundamentales de hace tres anos da un multiplo inexistente."""
    resultado = compute_valuation(_lineas(), pd.Series(dtype="float64"))
    assert resultado["per"].isna().all()
    assert resultado["ev_ebitda"].isna().all()


def test_negative_earnings_yield_missing_pe():
    """Un PER negativo no ordena: -2 no es 'mas barato' que 10."""
    resultado = compute_valuation(_lineas(bpa_diluido=-2.0), pd.Series([20.0], index=[FECHA]))
    assert np.isnan(resultado.loc[FECHA, "per"])


def test_negative_free_cash_flow_yields_missing_price_to_fcf():
    resultado = compute_valuation(
        _lineas(flujo_operativo=10.0, capex=60.0), pd.Series([20.0], index=[FECHA])
    )
    assert np.isnan(resultado.loc[FECHA, "precio_fcf"])


def test_zero_shares_outstanding_yields_missing_not_a_huge_multiple():
    resultado = compute_valuation(_lineas(acciones_diluidas=0.0), pd.Series([20.0], index=[FECHA]))
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
