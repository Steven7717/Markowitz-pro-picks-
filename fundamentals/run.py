from pathlib import Path

import pandas as pd

from fundamentals.concepts import CONCEPTOS, resolve_lines
from fundamentals.fetch import MIN_TRIMESTRES, PERIODOS, CoverageReport, load_facts
from fundamentals.kpis import (
    TODOS_LOS_KPIS,
    compute_growth,
    compute_levels,
    compute_valuation,
)
from fundamentals.panel import quarterly_panel
from fundamentals.sectors import load_sectors, zscore_within_sector
from fundamentals.universe import resolve

# A quarter's results are not public on the day the quarter ends: the 10-Q lands
# weeks later. Pricing a multiple at period end would use figures the market did
# not have, which is look-ahead — the family of defect study D found seven times.
#
# 45 days is just past the SEC deadline for large accelerated filers (40 days),
# so it lands at or after the real filing for almost every company in the index.
# Erring late is the safe direction: a price taken after publication is merely
# stale, whereas one taken before is information nobody had.
DIAS_HASTA_PRESENTACION = 45


def _precios_por_periodo(ticker: str, periodos: pd.DatetimeIndex) -> pd.Series:
    """Closing price at the date each quarter's results became public.

    Isolated so tests can replace it without touching the network, and so the
    price source stays swappable — it reuses research.loader today.
    """
    from research.loader import load_ohlcv

    if len(periodos) == 0:
        return pd.Series(dtype="float64")

    publicacion = pd.DatetimeIndex(periodos) + pd.Timedelta(days=DIAS_HASTA_PRESENTACION)
    vacio = pd.Series(float("nan"), index=periodos, dtype="float64")

    panel, _ = load_ohlcv(
        [ticker],
        start=(publicacion.min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(publicacion.max() + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    if panel.empty or ("Close", ticker) not in panel.columns:
        return vacio

    cierres = panel[("Close", ticker)].dropna()
    if cierres.empty:
        return vacio

    # asof: the last close at or before publication, so a date falling on a
    # weekend or holiday takes the previous session rather than nothing.
    return pd.Series([cierres.asof(f) for f in publicacion], index=periodos, dtype="float64")


def _trimestre_natural(fechas: pd.DatetimeIndex) -> pd.Series:
    """Bucket fiscal quarter ends into the calendar quarter they belong to.

    Apple's fiscal year ends in September and JPMorgan's in December, so their
    quarter-end dates never coincide. Scoring companies against peers requires a
    common bucket; the fiscal label cannot provide one, but the calendar can.
    """
    return pd.PeriodIndex(fechas, freq="Q").astype(str)


def build_panel(
    source: str | list[str] = "sp500",
    periods: int = PERIODOS,
    cache_dir: Path | None = None,
    sectores_path: Path | None = None,
    con_zscore: bool = False,
    refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, CoverageReport]:
    """Build the KPI panel for a universe.

    Returns (panel, metadatos, cobertura):
      - panel: indexed by (ticker, periodo), one column per KPI, where periodo is
        the quarter end date; a `trimestre` column carries the calendar bucket
      - metadatos: indexed by ticker, carrying sector_gics
      - cobertura: every exclusion, counted and attributed

    A company that fails is recorded and skipped. All of them failing for the
    same cause is not a company failing: it means there is no source, and
    `load_facts` raises `CorridaAbortada` rather than walking the whole universe
    to return nothing.
    """
    tickers = resolve(source)
    hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, refresh=refresh)
    sectores = load_sectors(sectores_path)

    trozos: list[pd.DataFrame] = []
    filas_meta: list[dict] = []

    for ticker, facts in hechos.items():
        panel_conceptos = quarterly_panel(facts, CONCEPTOS, n_periodos=periods)
        lineas, ausentes = resolve_lines(panel_conceptos)
        if ausentes:
            cobertura.missing_concepts[ticker] = ausentes
        if lineas.empty:
            cobertura.short_history[ticker] = 0
            continue
        if len(lineas) < MIN_TRIMESTRES:
            cobertura.short_history[ticker] = len(lineas)

        precios = _precios_por_periodo(ticker, lineas.index)
        if precios.isna().all():
            cobertura.missing_price.append(ticker)

        kpis = pd.concat(
            [
                compute_levels(lineas),
                compute_growth(lineas),
                compute_valuation(lineas, precios),
            ],
            axis=1,
        ).reindex(columns=list(TODOS_LOS_KPIS))
        kpis["trimestre"] = _trimestre_natural(lineas.index)
        kpis.index = pd.MultiIndex.from_arrays(
            [[ticker] * len(lineas), lineas.index], names=["ticker", "periodo"]
        )
        trozos.append(kpis)

        sector = sectores.get(ticker)
        if sector is None:
            cobertura.missing_sector.append(ticker)
        filas_meta.append({"ticker": ticker, "sector_gics": sector})

    if not trozos:
        vacio = pd.DataFrame(columns=[*TODOS_LOS_KPIS, "trimestre"], dtype="float64")
        return vacio, pd.DataFrame(columns=["sector_gics"]), cobertura

    panel = pd.concat(trozos).sort_index()
    metadatos = pd.DataFrame(filas_meta).set_index("ticker")

    if con_zscore:
        panel = _anadir_zscores(panel, metadatos)

    return panel, metadatos, cobertura


def _anadir_zscores(panel: pd.DataFrame, metadatos: pd.DataFrame) -> pd.DataFrame:
    """Score each company against sector peers within the same calendar quarter.

    Grouping by calendar quarter rather than by row date is what makes the
    comparison fair: Apple's quarter ends in late June and JPMorgan's on the
    30th, and matching on the exact date would put each company in a group of
    one, where a z-score is 0 by construction.

    Scoring across quarters instead would rank a company against its own past,
    which measures the business cycle rather than its standing among peers.
    """
    kpis = [c for c in panel.columns if c != "trimestre"]
    piezas = []

    for _, grupo in panel.groupby("trimestre", sort=False):
        tickers = grupo.index.get_level_values("ticker")
        sectores = pd.Series(
            metadatos["sector_gics"].reindex(tickers).to_numpy(), index=grupo.index
        )
        piezas.append(zscore_within_sector(grupo[kpis], sectores).add_prefix("z_"))

    return pd.concat([panel, pd.concat(piezas)], axis=1)
