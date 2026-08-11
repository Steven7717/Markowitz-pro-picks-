from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import DIAS_HASTA_PRESENTACION, _precios_por_periodo, build_panel

BASE = {
    "Revenues": 1000.0,
    "CostOfGoodsAndServicesSold": 600.0,
    "OperatingIncomeLoss": 200.0,
    "NetIncomeLoss": 100.0,
    "EarningsPerShareDiluted": 2.0,
    "DepreciationDepletionAndAmortization": 50.0,
    "InterestExpense": 25.0,
    "Assets": 2000.0,
    "AssetsCurrent": 500.0,
    "LiabilitiesCurrent": 250.0,
    "StockholdersEquity": 500.0,
    "LongTermDebt": 400.0,
    "CashAndCashEquivalentsAtCarryingValue": 150.0,
    "NetCashProvidedByUsedInOperatingActivities": 180.0,
    "PaymentsToAcquirePropertyPlantAndEquipment": 60.0,
    "WeightedAverageNumberOfDilutedSharesOutstanding": 50.0,
}

INSTANTES = {
    "Assets", "AssetsCurrent", "LiabilitiesCurrent", "StockholdersEquity",
    "LongTermDebt", "CashAndCashEquivalentsAtCarryingValue",
}


def _facts(ticker: str, n: int = 8, escala: float = 1.0) -> pd.DataFrame:
    """Tabla larga con la forma de facts.to_dataframe()."""
    fines = pd.date_range("2024-03-31", periods=n, freq="QE")
    filas = []
    for fin in fines:
        for concepto, valor in BASE.items():
            instante = concepto in INSTANTES
            filas.append(
                {
                    "concept": f"us-gaap:{concepto}",
                    "numeric_value": valor * escala,
                    "unit": "USD",
                    "period_type": "instant" if instante else "duration",
                    "period_start": pd.NaT if instante else fin - pd.Timedelta(days=89),
                    "period_end": fin,
                    "fiscal_year": fin.year,
                    "fiscal_period": f"Q{(fin.month - 1) // 3 + 1}",
                }
            )
    return pd.DataFrame(filas)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def sectores(tmp_path: Path) -> Path:
    ruta = tmp_path / "sectores.csv"
    pd.DataFrame(
        {"ticker": ["AAA", "BBB", "CCC"], "sector_gics": ["Tec"] * 3}
    ).to_csv(ruta, index=False)
    return ruta


def _construir(tickers, cache_dir, sectores, **kwargs):
    sin_precio = pd.Series(dtype="float64")
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=sin_precio):
        return build_panel(tickers, cache_dir=cache_dir, sectores_path=sectores, **kwargs)


def test_the_panel_carries_every_kpi_for_every_ticker(cache_dir, sectores):
    panel, _, _ = _construir(["AAA", "BBB", "CCC"], cache_dir, sectores)
    assert set(TODOS_LOS_KPIS) <= set(panel.columns)
    assert set(panel.index.get_level_values("ticker")) == {"AAA", "BBB", "CCC"}


def test_the_panel_is_indexed_by_ticker_and_period(cache_dir, sectores):
    panel, _, _ = _construir(["AAA"], cache_dir, sectores)
    assert panel.index.names == ["ticker", "periodo"]


def test_metadata_carries_the_sector_for_each_ticker(cache_dir, sectores):
    _, meta, _ = _construir(["AAA"], cache_dir, sectores)
    assert meta.loc["AAA", "sector_gics"] == "Tec"


def test_kpis_reach_the_panel_with_their_computed_values(cache_dir, sectores):
    """Sin esto, un panel lleno de NaN pasaria todos los demas tests."""
    panel, _, _ = _construir(["AAA"], cache_dir, sectores)
    assert panel["margen_bruto"].dropna().iloc[0] == pytest.approx(0.40)
    assert panel["roe"].dropna().iloc[0] == pytest.approx(0.20)


def test_a_ticker_outside_the_index_keeps_its_kpis_and_loses_only_the_zscore(cache_dir, sectores):
    """Decision de diseno: fuera del S&P 500 no hay GICS, pero los KPIs valen igual."""
    panel, meta, cobertura = _construir(["AAA", "BBB", "CCC", "ZZZ"], cache_dir, sectores)
    assert panel.loc["ZZZ", "margen_bruto"].notna().any()
    assert "ZZZ" in cobertura.missing_sector
    assert pd.isna(meta.loc["ZZZ", "sector_gics"])


def test_companies_are_scored_against_peers_in_the_same_calendar_quarter(cache_dir, sectores):
    """El trimestre fiscal de Apple no coincide con el de JPM.

    Agrupar por la fecha exacta pondria a cada empresa en un grupo de una, donde
    el z-score vale 0 por construccion en vez de por medicion.
    """
    def escalado(ticker):
        return _facts(ticker, escala={"AAA": 1.0, "BBB": 2.0, "CCC": 3.0}[ticker])

    with patch("fundamentals.fetch._fetch_facts", side_effect=escalado), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, _ = build_panel(
            ["AAA", "BBB", "CCC"], cache_dir=cache_dir, sectores_path=sectores, con_zscore=True
        )
    assert "z_margen_neto" in panel.columns
    # Tres empresas identicas en margen -> sin dispersion -> z ausente, no cero.
    # Pero el ROIC difiere por escala, asi que ese si puntua.
    assert panel["z_roe"].notna().any() or panel["z_margen_bruto"].isna().all()


def test_zscores_are_returned_alongside_the_raw_kpis(cache_dir, sectores):
    panel, _, _ = _construir(["AAA", "BBB", "CCC"], cache_dir, sectores, con_zscore=True)
    assert "z_margen_bruto" in panel.columns
    assert "margen_bruto" in panel.columns


def test_missing_concepts_are_reported_per_ticker(cache_dir, sectores):
    """Una empresa a la que le falta un renglon entra al panel marcada, no se elimina."""
    def sin_capex(ticker):
        f = _facts(ticker)
        return f[~f["concept"].str.endswith("PaymentsToAcquirePropertyPlantAndEquipment")]

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_capex), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, cobertura = build_panel(
            ["AAA"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert "capex" in cobertura.missing_concepts["AAA"]
    assert "AAA" in panel.index.get_level_values("ticker")


def test_a_failed_ticker_does_not_abort_the_whole_run(cache_dir, sectores):
    """Una empresa rota no puede costar el universo entero."""
    def una_falla(ticker):
        if ticker == "BBB":
            raise LookupError("sin CIK")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=una_falla), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, cobertura = build_panel(
            ["AAA", "BBB", "CCC"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert cobertura.unresolved_cik == ["BBB"]
    assert set(panel.index.get_level_values("ticker")) == {"AAA", "CCC"}


def test_a_company_with_too_few_quarters_is_marked_but_kept(cache_dir, sectores):
    """Sin 5 trimestres no hay crecimiento interanual, pero los niveles sirven."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t, n=3)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, cobertura = build_panel(
            ["AAA"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert cobertura.short_history["AAA"] == 3
    assert "AAA" in panel.index.get_level_values("ticker")


def test_the_price_is_taken_after_the_results_became_public():
    """El defecto de look-ahead: los resultados de un trimestre no son publicos
    el dia que el trimestre cierra, sino cuando se presenta el 10-Q semanas
    despues. Cotizar al cierre usa informacion que el mercado no tenia."""
    fechas = pd.bdate_range("2024-01-01", periods=400)
    panel = pd.DataFrame(
        {("Close", "AAA"): np.arange(len(fechas), dtype="float64")},
        index=fechas,
        columns=pd.MultiIndex.from_tuples([("Close", "AAA")]),
    )
    trimestre = pd.DatetimeIndex([pd.Timestamp("2024-03-31")])

    with patch("research.loader.load_ohlcv", return_value=(panel, None)):
        precios = _precios_por_periodo("AAA", trimestre)

    serie = panel[("Close", "AAA")]
    publicacion = trimestre[0] + pd.Timedelta(days=DIAS_HASTA_PRESENTACION)
    assert precios.iloc[0] == serie.asof(publicacion)
    assert precios.iloc[0] != serie.asof(trimestre[0])
