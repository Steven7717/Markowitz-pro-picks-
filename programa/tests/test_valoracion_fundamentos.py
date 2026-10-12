from datetime import date
from unittest.mock import patch

import pandas as pd

from fundamentals.concepts import LINEAS
from fundamentals.fetch import CorridaAbortada, CoverageReport
from valoracion.fundamentos import TRIMESTRES, desde_lineas, desde_sec


def lineas(n: int = 20, **columnas) -> pd.DataFrame:
    """Un panel con la forma de `resolve_lines`: trimestres, una columna por línea."""
    fechas = (
        pd.period_range("2021Q4", periods=n, freq="Q")
        .to_timestamp(how="end")
        .normalize()
    )
    marco = pd.DataFrame(float("nan"), index=fechas, columns=list(LINEAS), dtype="float64")
    valores = {
        "ingresos": 250.0,
        "flujo_operativo": 75.0,
        "capex": 25.0,
        "gasto_por_intereses": 5.0,
        "beneficio_operativo": 50.0,
        "beneficio_neto": 30.0,
        "patrimonio_neto": 2000.0,
        "deuda_total": 500.0,
        "efectivo": 100.0,
    }
    valores.update(columnas)
    for columna, valor in valores.items():
        marco[columna] = valor
    return marco


def test_el_ttm_suma_cuatro_trimestres():
    f = desde_lineas(lineas(), "USD", "sec")
    assert f.ultimo.ingresos == 1000.0
    assert f.ultimo.flujo_operativo == 300.0
    assert f.ultimo.capex == 100.0
    assert f.ultimo.gasto_financiero == 20.0
    assert f.ultimo.beneficio_operativo == 200.0
    assert f.ultimo.beneficio_neto == 120.0


def test_un_ejercicio_cada_cuatro_trimestres_del_mas_reciente_al_mas_antiguo():
    f = desde_lineas(lineas(), "USD", "sec")
    assert [e.fin for e in f.ejercicios] == [
        date(2026, 9, 30),
        date(2025, 9, 30),
        date(2024, 9, 30),
        date(2023, 9, 30),
        date(2022, 9, 30),
    ]


def test_el_balance_es_el_del_ultimo_trimestre():
    marco = lineas()
    marco["deuda_total"] = range(len(marco))
    marco["efectivo"] = [10.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.deuda_total == len(marco) - 1
    assert f.efectivo == 10.0 * (len(marco) - 1)


def test_el_patrimonio_de_cada_ejercicio_es_el_de_su_cierre():
    marco = lineas()
    marco["patrimonio_neto"] = [100.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.ejercicios[0].patrimonio_neto == 1900.0
    assert f.ejercicios[1].patrimonio_neto == 1500.0


def test_el_ultimo_ejercicio_es_el_ultimo_con_ingresos_de_doce_meses():
    marco = lineas()
    marco.iloc[-1, marco.columns.get_loc("ingresos")] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == date(2026, 6, 30)
    assert len(f.ejercicios) == 4


def test_menos_de_cuatro_trimestres_no_dan_fundamentos():
    assert desde_lineas(lineas(3), "USD", "sec") is None


def test_un_panel_vacio_no_da_fundamentos():
    assert desde_lineas(lineas(0), "USD", "sec") is None


def test_sin_hechos_de_la_sec_lo_dice():
    vacio = ({}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=vacio):
        assert desde_sec("TST") == (None, "sin_estados")


def test_una_corrida_abortada_no_se_propaga():
    error = CorridaAbortada("sin_identidad", "x", CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", side_effect=error):
        assert desde_sec("TST") == (None, "sin_estados")


def test_desde_sec_pide_veinte_trimestres_y_construye():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ) as panel, patch(
        "valoracion.fundamentos.resolve_lines", return_value=(lineas(), [])
    ), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        fundamentos, motivo = desde_sec("TST")
    assert motivo == "ok"
    assert fundamentos.moneda == "USD" and fundamentos.fuente == "sec"
    assert panel.call_args.kwargs["n_periodos"] == TRIMESTRES == 20


def test_desde_sec_sin_historia_suficiente_lo_dice():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ), patch("valoracion.fundamentos.resolve_lines", return_value=(lineas(2), [])), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        assert desde_sec("TST") == (None, "sin_historia")
