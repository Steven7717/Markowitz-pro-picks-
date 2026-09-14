import numpy as np
import pandas as pd
import pytest

from fundamentals.panel import cierres_de_ejercicio, quarterly_panel

COLUMNAS = [
    "concept", "numeric_value", "unit", "period_type",
    "period_start", "period_end", "fiscal_year", "fiscal_period",
]


def _hecho(concept, valor, inicio, fin, tipo="duration", fy=2025, fp="Q1", unit="USD"):
    return {
        "concept": concept,
        "numeric_value": valor,
        "unit": unit,
        "period_type": tipo,
        "period_start": inicio,
        "period_end": fin,
        "fiscal_year": fy,
        "fiscal_period": fp,
    }


def _facts(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=COLUMNAS)


def _trimestres(concept="us-gaap:Revenues", valores=(10.0, 20.0, 30.0, 40.0), ano=2025):
    """Cuatro trimestres naturales del mismo ano."""
    limites = [
        (f"{ano}-01-01", f"{ano}-03-31"),
        (f"{ano}-04-01", f"{ano}-06-30"),
        (f"{ano}-07-01", f"{ano}-09-30"),
        (f"{ano}-10-01", f"{ano}-12-31"),
    ]
    return [
        _hecho(concept, v, i, f, fy=ano, fp=f"Q{n + 1}")
        for n, (v, (i, f)) in enumerate(zip(valores, limites))
    ]


def test_the_us_gaap_prefix_is_stripped_from_concept_names():
    """El plan asumia nombres desnudos; SEC los entrega como 'us-gaap:Revenues'."""
    panel = quarterly_panel(_facts(_trimestres()[:1]), {"Revenues"})
    assert "Revenues" in panel.columns


def test_only_quarter_length_durations_are_kept():
    """Un hecho anual y uno trimestral comparten concepto: confundirlos cuadruplica los ingresos."""
    filas = _trimestres()[:1] + [
        _hecho("us-gaap:Revenues", 999.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert list(panel["Revenues"].dropna()) == [10.0]


def test_cumulative_windows_never_enter_the_panel_at_face_value():
    """Las presentaciones acumulan: 6 y 9 meses aparecen junto a los trimestres.

    Sus cifras en crudo son varios trimestres sumados. Colarlas tal cual
    multiplicaria los ingresos del trimestre; lo correcto es la diferencia
    consecutiva, que este mismo caso produce como 545 y 222.
    """
    filas = _trimestres()[:1] + [
        _hecho("us-gaap:Revenues", 555.0, "2025-01-01", "2025-06-30", fy=2025, fp="Q2"),
        _hecho("us-gaap:Revenues", 777.0, "2025-01-01", "2025-09-30", fy=2025, fp="Q3"),
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    valores = panel["Revenues"].dropna().tolist()
    assert 555.0 not in valores
    assert 777.0 not in valores
    assert valores == [10.0, 545.0, 222.0]


def test_a_restated_quarter_keeps_the_most_recent_version():
    """Apple reexpresa: 25 de sus 72 filas de ingresos repiten concepto y fecha.

    Quedarse con la primera daria el valor viejo; sumarlas daria el doble.
    """
    filas = [
        _hecho("us-gaap:Revenues", 10.0, "2025-01-01", "2025-03-31", fy=2025, fp="Q1"),
        _hecho("us-gaap:Revenues", 11.0, "2025-01-01", "2025-03-31", fy=2026, fp="Q1"),
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert panel["Revenues"].dropna().tolist() == [11.0]


def test_the_fourth_quarter_is_derived_from_the_annual_figure():
    """Nadie presenta un 10-Q del Q4: va dentro del 10-K como cifra anual.

    Sin derivarlo, uno de cada cuatro trimestres quedaria vacio.
    """
    filas = _trimestres(valores=(10.0, 20.0, 30.0))[:3] + [
        _hecho("us-gaap:Revenues", 100.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert panel.loc[pd.Timestamp("2025-12-31"), "Revenues"] == pytest.approx(40.0)


def test_the_fourth_quarter_is_not_derived_when_a_quarter_is_missing():
    """Restar el anual a dos trimestres da un Q4 inflado que parece un dato real."""
    filas = _trimestres(valores=(10.0, 20.0))[:2] + [
        _hecho("us-gaap:Revenues", 100.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert pd.Timestamp("2025-12-31") not in panel.index


def test_a_reported_fourth_quarter_is_not_overwritten_by_the_derived_one():
    filas = _trimestres() + [
        _hecho("us-gaap:Revenues", 999.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert panel.loc[pd.Timestamp("2025-12-31"), "Revenues"] == pytest.approx(40.0)


def _acumulados(concept="us-gaap:NetCashProvidedByUsedInOperatingActivities",
                valores=(10.0, 25.0, 45.0), ano=2025):
    """Como reportan de verdad el flujo de caja: tres meses, seis, nueve.

    Todos comparten la fecha de inicio del ano fiscal.
    """
    fines = [f"{ano}-03-31", f"{ano}-06-30", f"{ano}-09-30"]
    return [
        _hecho(concept, v, f"{ano}-01-01", f, fy=ano, fp=f"Q{n + 1}")
        for n, (v, f) in enumerate(zip(valores, fines))
    ]


def test_cumulative_year_to_date_figures_are_split_into_quarters():
    """El flujo de caja no viene por trimestre suelto sino acumulado.

    Sin descumular, solo el primer trimestre de cada ano pasa el filtro de
    duracion: es lo que tenia la cobertura del flujo de caja libre en el 12%.
    """
    panel = quarterly_panel(_facts(_acumulados()), {"NetCashProvidedByUsedInOperatingActivities"})
    serie = panel["NetCashProvidedByUsedInOperatingActivities"]
    assert serie.loc[pd.Timestamp("2025-03-31")] == pytest.approx(10.0)
    assert serie.loc[pd.Timestamp("2025-06-30")] == pytest.approx(15.0)  # 25 - 10
    assert serie.loc[pd.Timestamp("2025-09-30")] == pytest.approx(20.0)  # 45 - 25


def test_a_reported_quarter_beats_one_recovered_from_a_cumulative_series():
    """Si la empresa declara el trimestre, esa cifra manda sobre la resta."""
    filas = _acumulados() + [
        _hecho("us-gaap:NetCashProvidedByUsedInOperatingActivities", 99.0,
               "2025-04-01", "2025-06-30", fy=2025, fp="Q2")
    ]
    panel = quarterly_panel(_facts(filas), {"NetCashProvidedByUsedInOperatingActivities"})
    valor = panel.loc[pd.Timestamp("2025-06-30"), "NetCashProvidedByUsedInOperatingActivities"]
    assert valor == pytest.approx(99.0)


def test_a_gap_in_the_cumulative_series_does_not_produce_a_double_quarter():
    """De tres meses a nueve hay medio ano: esa resta no es un trimestre."""
    filas = _acumulados(valores=(10.0, 45.0))[:1] + [
        _hecho("us-gaap:NetCashProvidedByUsedInOperatingActivities", 45.0,
               "2025-01-01", "2025-09-30", fy=2025, fp="Q3")
    ]
    panel = quarterly_panel(_facts(filas), {"NetCashProvidedByUsedInOperatingActivities"})
    assert pd.Timestamp("2025-09-30") not in panel.index


def test_cumulative_splitting_does_not_touch_series_with_different_start_dates():
    """Dos trimestres sueltos no son una serie acumulada; restarlos inventaria un dato."""
    panel = quarterly_panel(_facts(_trimestres()[:2]), {"Revenues"})
    assert panel["Revenues"].tolist() == [10.0, 20.0]


def test_balance_sheet_instants_are_kept_at_their_own_date():
    """El balance es una foto a una fecha, no un periodo: no tiene duracion."""
    filas = _trimestres()[:1] + [
        _hecho("us-gaap:Assets", 500.0, None, "2025-03-31", tipo="instant")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues", "Assets"})
    assert panel.loc[pd.Timestamp("2025-03-31"), "Assets"] == pytest.approx(500.0)


def test_instants_off_the_quarter_grid_do_not_create_extra_rows():
    """Los 10-K traen instantes en fechas sueltas; cada uno seria un trimestre falso."""
    filas = _trimestres()[:1] + [
        _hecho("us-gaap:Assets", 500.0, None, "2025-03-31", tipo="instant"),
        _hecho("us-gaap:Assets", 600.0, None, "2025-05-14", tipo="instant"),
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues", "Assets"})
    assert list(panel.index) == [pd.Timestamp("2025-03-31")]


def test_only_the_requested_concepts_become_columns():
    """SEC entrega 25.000 filas por empresa; sin filtrar, el panel es inmanejable."""
    filas = _trimestres()[:1] + [
        _hecho("us-gaap:IrrelevantConcept", 1.0, "2025-01-01", "2025-03-31")
    ]
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert list(panel.columns) == ["Revenues"]


def test_periods_are_sorted_oldest_first():
    """El calculo interanual usa shift(4) y depende del orden cronologico."""
    filas = _trimestres()
    panel = quarterly_panel(_facts(list(reversed(filas))), {"Revenues"})
    assert list(panel.index) == sorted(panel.index)


def test_only_the_most_recent_n_quarters_are_returned():
    filas = _trimestres(ano=2024) + _trimestres(ano=2025)
    panel = quarterly_panel(_facts(filas), {"Revenues"}, n_periodos=3)
    assert len(panel) == 3
    assert panel.index.max() == pd.Timestamp("2025-12-31")


def test_non_monetary_units_are_not_mixed_into_a_concept():
    """Un mismo concepto puede venir en USD y en USD/accion; sumarlos no significa nada."""
    filas = [
        _hecho("us-gaap:EarningsPerShareDiluted", 2.0, "2025-01-01", "2025-03-31", unit="USD/shares"),
    ]
    panel = quarterly_panel(_facts(filas), {"EarningsPerShareDiluted"})
    assert panel.loc[pd.Timestamp("2025-03-31"), "EarningsPerShareDiluted"] == pytest.approx(2.0)


def test_an_empty_fact_table_yields_an_empty_panel_with_every_column():
    panel = quarterly_panel(_facts([]), {"Revenues", "Assets"})
    assert panel.empty
    assert sorted(panel.columns) == ["Assets", "Revenues"]


def test_a_concept_never_reported_still_appears_as_an_empty_column():
    """Un panel con columnas variables segun la empresa no se puede concatenar."""
    panel = quarterly_panel(_facts(_trimestres()[:1]), {"Revenues", "NuncaReportado"})
    assert "NuncaReportado" in panel.columns
    assert panel["NuncaReportado"].isna().all()


# ── Medias ponderadas frente a acumulados ─────────────────────────────────────

ACCIONES = "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"


def _ytd(concept, valores, ano=2025, unit="USD"):
    """El acumulado del ano hasta la fecha: 3 meses, 6, 9 y el ejercicio."""
    limites = [
        (f"{ano}-01-01", f"{ano}-03-31"),
        (f"{ano}-01-01", f"{ano}-06-30"),
        (f"{ano}-01-01", f"{ano}-09-30"),
        (f"{ano}-01-01", f"{ano}-12-31"),
    ]
    return [
        _hecho(concept, v, i, f, fy=ano, fp=("FY" if n == 3 else f"Q{n + 1}"), unit=unit)
        for n, (v, (i, f)) in enumerate(zip(valores, limites))
    ]


def test_a_weighted_average_share_count_is_never_descumulated_as_a_flow():
    """El recuento medio ponderado no es un acumulado: restarlo da basura.

    CPRT declara 977.485.000 acciones hasta abril de 2025 y 977.563.000 hasta
    julio; la resta, 78.000, es lo que el panel guardaba como «acciones del Q4»
    y con lo que se calculaba la capitalizacion. Medido sobre las 502 empresas:
    974 celdas nulas o negativas mas 473 positivas pero absurdas.

    La media de n trimestres es la media de las n-1 anteriores mas la del
    ultimo, asi que el trimestre sale de n*YTDn - (n-1)*YTDn-1, no de la resta.
    """
    filas = _ytd(ACCIONES, [1000.0, 1010.0, 1020.0, 1030.0], unit="shares")
    panel = quarterly_panel(_facts(filas), {"WeightedAverageNumberOfDilutedSharesOutstanding"})
    serie = panel["WeightedAverageNumberOfDilutedSharesOutstanding"]
    assert serie.iloc[0] == pytest.approx(1000.0)
    # 2*1010 - 1*1000 = 1020; 3*1020 - 2*1010 = 1040; 4*1030 - 3*1020 = 1060
    assert list(serie.iloc[1:]) == pytest.approx([1020.0, 1040.0, 1060.0])


def test_a_flow_is_still_descumulated_by_plain_subtraction():
    """Contrastado en las cachés: la resta simple reproduce el trimestre
    declarado con error mediano 0 en ingresos y en BPA, y 1,0 —o sea, del todo
    equivocada— en el recuento de acciones."""
    filas = _ytd("us-gaap:Revenues", [100.0, 250.0, 420.0, 600.0])
    panel = quarterly_panel(_facts(filas), {"Revenues"})
    assert list(panel["Revenues"]) == pytest.approx([100.0, 150.0, 170.0, 180.0])


def test_the_fourth_quarter_of_a_weighted_average_comes_from_the_annual_average():
    """El Q4 que el 10-K no publica: la media anual son las cuatro trimestrales,
    asi que la que falta es 4*anual menos las tres declaradas, no la resta."""
    filas = _trimestres(ACCIONES, (1000.0, 1010.0, 1020.0, 0.0))[:3] + [
        _hecho(ACCIONES, 1020.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY", unit="shares")
    ]
    panel = quarterly_panel(_facts(filas), {"WeightedAverageNumberOfDilutedSharesOutstanding"})
    serie = panel["WeightedAverageNumberOfDilutedSharesOutstanding"]
    # 4*1020 - (1000 + 1010 + 1020) = 1050
    assert serie.iloc[3] == pytest.approx(1050.0)


def test_a_derived_weighted_average_wildly_off_its_own_year_is_dropped():
    """Un emisor de 52/53 semanas tiene trimestres desiguales y la aritmetica
    se le va. Un recuento de acciones no se duplica ni se parte por la mitad en
    un trimestre: fuera de ese margen no es una medicion, es ruido amplificado,
    y un hueco declarado es preferible a una cifra inventada."""
    filas = _ytd(ACCIONES, [1000.0, 200.0, 210.0, 220.0], unit="shares")
    panel = quarterly_panel(_facts(filas), {"WeightedAverageNumberOfDilutedSharesOutstanding"})
    serie = panel["WeightedAverageNumberOfDilutedSharesOutstanding"]
    # 2*200 - 1000 = -600, que no es un recuento de acciones de nadie: el
    # trimestre se queda sin cifra en vez de entrar con esa.
    assert np.isnan(serie.reindex([pd.Timestamp("2025-06-30")]).iloc[0])
    assert (serie.dropna() > 0).all()


def test_the_fiscal_year_closes_are_the_ends_of_the_twelve_month_windows():
    """El desfase hasta la presentacion depende de si el cierre es de ejercicio.

    El mes de cierre no se puede leer del calendario: el de Apple es septiembre
    y el de CPRT julio. Lo que si lo dice son las ventanas de doce meses que la
    propia empresa declara.
    """
    filas = _trimestres()[:3] + [
        _hecho("us-gaap:Revenues", 600.0, "2025-01-01", "2025-12-31", fy=2025, fp="FY")
    ]
    cierres = cierres_de_ejercicio(_facts(filas), {"Revenues"})
    assert list(cierres) == [pd.Timestamp("2025-12-31")]


def test_a_company_with_no_annual_window_declares_no_fiscal_year_close():
    cierres = cierres_de_ejercicio(_facts(_trimestres()[:1]), {"Revenues"})
    assert len(cierres) == 0
