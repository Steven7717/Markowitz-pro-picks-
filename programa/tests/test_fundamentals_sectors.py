import numpy as np
import pandas as pd
import pytest

from fundamentals import sectors
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


# --- Enmienda 2026-09-14: la cola se recorta a tres desviaciones -------------


def test_un_z_extremo_se_recorta_a_tres_desviaciones():
    """Una razon corriente no tiene techo y un z-score si deberia tenerlo.

    Medido sobre el panel del 2026-09-14: ocho de las quince empresas elegidas
    tenian mas de la mitad de su nota bruta en un solo z, y PLTR el 98,2%. El
    recorte no arregla el sesgo del pilar manco --eso lo hace la imputacion a 0
    de `ranking/score.py`, y de hecho recortar SOLO lo empeoraba-- pero acota lo
    que un unico numero puede decidir: con las dos medidas juntas, el maximo de
    concentracion baja del 94,6% al 61,5%.
    """
    # Veinte pares y no diez: con n observaciones el z maximo posible es
    # (n-1)/sqrt(n), o sea 2,85 con diez. Un test con diez nunca podria ver el
    # recorte aunque el recorte no existiera.
    valores = pd.DataFrame(
        {"razon_corriente": [1.0] * 19 + [500.0]},
        index=[f"E{i}" for i in range(20)],
    )
    sectores = pd.Series(["Industrials"] * 20, index=valores.index)

    z = sectors.zscore_within_sector(valores, sectores)

    assert z["razon_corriente"].max() == pytest.approx(3.0)
    assert z["razon_corriente"].min() >= -3.0


def test_un_z_dentro_de_la_banda_no_se_toca():
    valores = pd.DataFrame(
        {"roe": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=[f"E{i}" for i in range(5)]
    )
    sectores = pd.Series(["Industrials"] * 5, index=valores.index)

    z = sectors.zscore_within_sector(valores, sectores)

    assert abs(z["roe"]).max() < 3.0
    assert z["roe"].iloc[0] == pytest.approx(-1.2649110640673518)


def test_el_recorte_no_convierte_un_nan_en_un_numero():
    """NaN sigue diciendo «no medido», que no es lo mismo que «en el tope»."""
    valores = pd.DataFrame(
        {"roe": [1.0, 2.0, 3.0, 4.0, np.nan]}, index=[f"E{i}" for i in range(5)]
    )
    sectores = pd.Series(["Industrials"] * 5, index=valores.index)

    z = sectors.zscore_within_sector(valores, sectores)

    assert pd.isna(z.loc["E4", "roe"])


def test_el_recorte_se_puede_desactivar_para_el_compuesto():
    """El recorte es para los KPIs, que son cocientes sin techo.

    El compuesto ya es una suma de cuatro pilares hechos de z recortados, asi
    que sus colas estan acotadas por construccion. Recortarlo otra vez destruia
    orden justo donde se decide el ranking: MU y NVDA empataban en exactamente
    3,000 en los puestos 1 y 2.
    """
    valores = pd.DataFrame(
        {"compuesto": [1.0] * 19 + [500.0]}, index=[f"E{i}" for i in range(20)]
    )
    sectores = pd.Series(["Industrials"] * 20, index=valores.index)

    recortado = sectors.zscore_within_sector(valores, sectores)
    sin_recortar = sectors.zscore_within_sector(valores, sectores, tope=None)

    assert recortado["compuesto"].max() == pytest.approx(3.0)
    assert sin_recortar["compuesto"].max() > 4.0
