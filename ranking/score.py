import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.sectors import MIN_PARES, zscore_within_sector
from ranking.criterio import (
    MAX_ANTIGUEDAD_TRIMESTRES,
    MIN_KPIS_CON_DATO,
    MIN_PILARES_CON_DATO,
    MIN_TRIMESTRES_HISTORIA,
    PESOS,
    PILARES,
    SIGNOS,
    TRIMESTRES_VENTANA,
)

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


def _rezago_trimestres(ultimos: pd.Series, trimestre_max: str) -> pd.Series:
    """How many calendar quarters behind the panel's newest bucket each company is.

    Measured against the panel, not against today's date: the panel is what the
    ranking is computed from, and a run made three months later must not start
    excluding companies that were current when the data was fetched.
    """
    ordinales = pd.PeriodIndex(ultimos.astype(str), freq="Q").astype("int64")
    tope = pd.Period(trimestre_max, freq="Q").ordinal
    return pd.Series(tope - ordinales, index=ultimos.index)


def aplicar_guardas(
    pilares: pd.DataFrame,
    conteo: pd.DataFrame,
    historial: pd.DataFrame,
    trimestre_max: str,
) -> pd.Series:
    """Name why each company is excluded, or NaN when it survives.

    Every exclusion is named and returned rather than dropped, because a company
    that silently vanishes from a ranking is indistinguishable from one that
    scored badly — and the difference matters when reading the result.

    The first failing guard wins, so the reported reason is the most fundamental
    one rather than whichever check happened to run last.
    """
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    if pilares.empty:
        return motivos

    historial = historial.reindex(pilares.index)

    # Negar >= en vez de usar <, porque NaN < 4 es False: una empresa ausente
    # del historial pasaría la guarda por no saber nada de ella.
    corta = ~(historial["trimestres"] >= MIN_TRIMESTRES_HISTORIA)
    motivos[corta & motivos.isna()] = "historia_corta"

    ultimos = historial["ultimo_trimestre"]
    conocidos = ultimos.notna()
    rezago = pd.Series(float("nan"), index=motivos.index)
    if conocidos.any():
        rezago[conocidos] = _rezago_trimestres(ultimos[conocidos], trimestre_max)
    motivos[(rezago > MAX_ANTIGUEDAD_TRIMESTRES) & motivos.isna()] = "datos_rancios"

    sin_pilar = (conteo > 0).sum(axis=1) < MIN_PILARES_CON_DATO
    motivos[sin_pilar & motivos.isna()] = "pilar_sin_datos"

    pocos = conteo.sum(axis=1) < MIN_KPIS_CON_DATO
    motivos[pocos & motivos.isna()] = "cobertura_insuficiente"

    return motivos


def compuesto(
    pilares: pd.DataFrame, motivos: pd.Series, sectores: pd.Series
) -> pd.Series:
    """Weighted composite, re-standardised within sector before the global sort.

    A pillar averaged over two KPIs is more variable than one averaged over
    seven, and the companies missing KPIs are concentrated in banks, insurers
    and REITs. Without this step their composites would be systematically more
    extreme and would crowd both ends of the global order — the ranking would be
    measuring how many KPIs a company publishes, and would look entirely normal
    while doing it.

    Re-standardising within sector alone, with no time axis: after averaging the
    window there is one row per company, and grouping by the company's own last
    quarter would produce groups of one, where a z-score is 0 by construction.
    See amendment 1 of the design document.
    """
    if pilares.empty:
        return pd.Series(dtype="float64", index=pilares.index, name="compuesto")

    pesos = pd.Series(PESOS)
    # min_count exige los cuatro pilares: una empresa con tres medidos no
    # compite contra otras con cuatro.
    bruto = (pilares[list(pesos.index)] * pesos).sum(axis=1, min_count=len(pesos))
    bruto = bruto.mask(motivos.reindex(bruto.index).notna())

    normalizado = zscore_within_sector(
        bruto.to_frame("compuesto"), sectores.reindex(bruto.index)
    )
    return normalizado["compuesto"]


def marcar_sin_pares(
    motivos: pd.Series, compuestos: pd.Series, sectores: pd.Series
) -> pd.Series:
    """Name the exclusion for companies the sector re-standardisation dropped.

    zscore_within_sector returns NaN — never 0 — for three different reasons:
    an unknown sector, a peer group too small to have a spread, and a sector
    where every company reports the same value. Collapsing all three into "too
    few peers" would put a false statement in the exclusions report, which is
    the one artefact of this pipeline that has to be trustworthy.

    The three are told apart from the sector column alone, without repeating
    the z-score arithmetic that produced the NaN.
    """
    motivos = motivos.copy()
    sectores = sectores.reindex(motivos.index)
    huerfanas = compuestos.reindex(motivos.index).isna() & motivos.isna()
    if not huerfanas.any():
        return motivos

    tamanos = sectores.map(sectores.value_counts())
    motivos[huerfanas & sectores.isna()] = "sector_desconocido"
    motivos[huerfanas & motivos.isna() & (tamanos < MIN_PARES)] = "sector_sin_pares"
    motivos[huerfanas & motivos.isna()] = "sin_dispersion_sectorial"
    return motivos
