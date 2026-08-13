import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import PILARES, SIGNOS, TRIMESTRES_VENTANA

COLUMNAS_Z = tuple(f"z_{kpi}" for kpi in TODOS_LOS_KPIS)


def media_ventana(
    panel: pd.DataFrame, n: int = TRIMESTRES_VENTANA
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Average each company's n most recent rows.

    Returns (z, valores, historial), all indexed by ticker: sector z-scores,
    raw KPI values for the fichas, and the row count plus newest calendar
    quarter that the guards need.

    The n most recent *rows*, which need not be n consecutive quarters: a
    company that skipped a filing leaves a gap and the window jumps it. Each
    row's z-score is already relative to its own quarter's peers, so jumping a
    gap never mixes periods.

    The ranking is built from z, not from raw KPIs, precisely so it can average
    across quarters at all: a margin from Q1 and a margin from Q3 are only
    comparable once both are expressed relative to their own quarter's peers.
    `valores` is a separate, display-only average of the raw figures over the
    same window, for the fichas — it makes no cross-company comparability claim.

    Averaging a single KPI over fewer than n quarters is allowed on purpose: a
    line item missing in one quarter should not discard the other three. The
    guards decide separately whether the surviving coverage is enough.
    """
    kpis = list(TODOS_LOS_KPIS)
    if panel.empty:
        indice_vacio = pd.Index([], name="ticker")
        vacio = pd.DataFrame(columns=kpis, index=indice_vacio, dtype="float64")
        historial = pd.DataFrame(
            columns=["trimestres", "ultimo_trimestre"], index=indice_vacio
        )
        return vacio, vacio.copy(), historial

    ordenado = panel.sort_index(level=["ticker", "periodo"])
    recientes = ordenado.groupby(level="ticker", sort=False).tail(n)
    por_ticker = recientes.groupby(level="ticker", sort=True)

    z = por_ticker[list(COLUMNAS_Z)].mean()
    z.columns = kpis

    valores = por_ticker[kpis].mean()

    historial = pd.DataFrame(
        {
            "trimestres": por_ticker.size(),
            "ultimo_trimestre": por_ticker["trimestre"].max(),
        }
    )
    return z, valores, historial


def puntuaciones_por_pilar(medias: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Average the available KPIs of each pillar, applying the declared signs.

    Returns (pilares, conteo): the four scores per company, and how many KPIs
    actually carried data in each — the guards need the count, and so does the
    ficha, because a pillar resting on two KPIs is a weaker claim than one
    resting on seven.

    Signs are applied here rather than upstream so `medias` stays readable as
    raw z-scores: a +2 in `per` means expensive, and only the pillar turns that
    into a penalty.
    """
    if medias.empty:
        vacio = pd.DataFrame(index=medias.index, columns=list(PILARES), dtype="float64")
        return vacio, vacio.copy().astype("int64")

    con_signo = medias.mul(pd.Series(SIGNOS), axis=1)
    bloques = {pilar: con_signo[list(kpis)] for pilar, kpis in PILARES.items()}

    pilares = pd.DataFrame(
        {pilar: bloque.mean(axis=1) for pilar, bloque in bloques.items()},
        index=medias.index,
    )
    conteo = pd.DataFrame(
        {pilar: bloque.notna().sum(axis=1) for pilar, bloque in bloques.items()},
        index=medias.index,
    )
    return pilares, conteo
