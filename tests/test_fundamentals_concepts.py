import numpy as np
import pandas as pd

from fundamentals.concepts import CONCEPTOS, LINEAS, resolve_lines


def _panel(columnas: dict[str, list[float]], n: int = 1) -> pd.DataFrame:
    fechas = pd.date_range("2025-03-31", periods=n, freq="QE")
    return pd.DataFrame(columnas, index=fechas)


def test_the_first_concept_in_the_chain_wins():
    panel = _panel({"Revenues": [100.0], "SalesRevenueNet": [999.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 100.0


def test_a_later_concept_is_used_when_the_first_is_absent():
    """Apple no declara 'Revenues'; usa la etiqueta larga de ingresos por contrato."""
    panel = _panel({"RevenueFromContractWithCustomerExcludingAssessedTax": [250.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 250.0


def test_a_concept_present_but_entirely_empty_loses_to_the_next_in_the_chain():
    """JPMorgan dejo de etiquetar Revenues trimestral en 2014.

    En una ventana reciente la columna existe y esta vacia. Quedarse con ella
    dejaria al banco sin ingresos teniendolos bajo otra etiqueta.
    """
    panel = _panel({"Revenues": [np.nan], "SalesRevenueNet": [77.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 77.0


def test_a_line_with_no_matching_concept_is_missing_not_zero():
    """Un 0 en ingresos se lee como 'no vendio nada'. Ausente, como 'no lo declara'."""
    panel = _panel({"Revenues": [100.0]})
    lineas, ausentes = resolve_lines(panel)
    assert np.isnan(lineas["beneficio_neto"].iloc[0])
    assert "beneficio_neto" in ausentes


def test_present_lines_are_not_reported_as_missing():
    panel = _panel({"Revenues": [100.0]})
    _, ausentes = resolve_lines(panel)
    assert "ingresos" not in ausentes


def test_every_line_appears_as_a_column_even_when_absent():
    """Un panel con columnas variables segun la empresa no se puede concatenar."""
    panel = _panel({"Revenues": [100.0]})
    lineas, _ = resolve_lines(panel)
    assert sorted(lineas.columns) == sorted(LINEAS)


def test_the_period_index_is_preserved():
    """El calculo interanual usa shift(4) sobre este indice."""
    panel = _panel({"Revenues": [1.0, 2.0, 3.0]}, n=3)
    lineas, _ = resolve_lines(panel)
    assert list(lineas.index) == list(panel.index)


def test_an_empty_panel_yields_an_empty_frame_with_every_column():
    lineas, ausentes = resolve_lines(pd.DataFrame())
    assert lineas.empty
    assert sorted(ausentes) == sorted(LINEAS)


def test_no_line_declares_an_empty_chain():
    """Una cadena vacia haria que la linea nunca se resuelva, en silencio."""
    assert all(len(cadena) > 0 for cadena in LINEAS.values())


def test_the_concept_set_covers_every_chain():
    """panel.py filtra por este conjunto; una omision vaciaria la linea entera."""
    for cadena in LINEAS.values():
        assert set(cadena) <= CONCEPTOS


def test_operating_income_does_not_fall_back_to_pretax_income():
    """El beneficio antes de impuestos ya tiene los intereses restados.

    Usarlo como alternativa subiria la cobertura de 13 a 17 de 20 empresas, pero
    haria que la cobertura de intereses fuese el cociente de otra magnitud.
    """
    assert LINEAS["beneficio_operativo"] == ("OperatingIncomeLoss",)
