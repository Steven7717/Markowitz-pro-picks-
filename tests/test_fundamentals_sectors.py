import numpy as np
import pandas as pd
import pytest

from fundamentals.sectors import load_sectors, zscore_within_sector


def test_the_frozen_table_covers_the_whole_sp500():
    from fundamentals.universe import resolve

    sectores = load_sectors()
    faltan = [t for t in resolve("sp500") if t not in sectores]
    assert faltan == [], f"Sin sector: {faltan}"


def test_no_sector_group_is_too_small_to_zscore():
    """Un z-score contra un grupo de una empresa vale 0 por construccion.

    Medido durante el diseno: SIC de 4 digitos dejaba 87 empresas solas. GICS
    Sector no deja ninguna, y este test lo mantiene asi si la tabla se regenera.
    """
    conteo = pd.Series(load_sectors()).value_counts()
    assert conteo.min() >= 10


def test_a_value_at_the_sector_mean_scores_zero():
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec", "tec", "tec"], index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert z.loc["B", "margen"] == pytest.approx(0.0)


def test_sectors_are_scored_independently_of_each_other():
    """Comparar una petrolera con una tecnologica es el defecto que esto evita."""
    kpis = pd.DataFrame({"margen": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0]}, index=list("ABCDEF"))
    sectores = pd.Series(["tec"] * 3 + ["energia"] * 3, index=list("ABCDEF"))
    z = zscore_within_sector(kpis, sectores)
    assert z.loc["B", "margen"] == pytest.approx(z.loc["E", "margen"])


def test_a_company_without_a_known_sector_gets_a_missing_score_not_a_zero():
    """Un 0 se lee como 'promedio de su sector'. Ausente se lee como 'no se sabe'."""
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "X"])
    sectores = pd.Series(["tec", "tec", None], index=["A", "B", "X"])
    z = zscore_within_sector(kpis, sectores)
    assert np.isnan(z.loc["X", "margen"])


def test_a_sector_with_no_dispersion_yields_missing_not_infinity():
    """Dividir por una desviacion de cero da inf y parece un dato extraordinario."""
    kpis = pd.DataFrame({"margen": [7.0, 7.0, 7.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec"] * 3, index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert z["margen"].isna().all()


def test_a_missing_kpi_stays_missing_after_scoring():
    kpis = pd.DataFrame({"margen": [10.0, np.nan, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec"] * 3, index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert np.isnan(z.loc["B", "margen"])


def test_a_group_below_the_minimum_size_is_not_scored():
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec", "tec", "solo"], index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores, min_pares=3)
    assert np.isnan(z.loc["C", "margen"])
