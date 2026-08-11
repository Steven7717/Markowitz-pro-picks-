"""Turn SEC's long fact table into a quarterly panel.

`facts.to_dataframe()` returns one row per reported fact: tens of thousands per
company, mixing quarters with annual and cumulative periods, point-in-time
balance figures with flow figures, and several restatements of the same quarter.
This module reduces that to one row per quarter and one column per concept.
"""
import numpy as np
import pandas as pd

# A filing reports the same line over several windows: the quarter, the half,
# the nine months, and the year. Only true quarters and true years are useful —
# the cumulative ones would multiply a flow figure if mistaken for a quarter.
_DIAS_TRIMESTRE = (80, 100)
_DIAS_ANO = (350, 380)

_TRIMESTRES_POR_ANO = 4


def _sin_prefijo(concepto: pd.Series) -> pd.Series:
    """SEC namespaces every tag ('us-gaap:Revenues'); the chains match bare names."""
    return concepto.astype(str).str.split(":").str[-1]


def _preparar(facts: pd.DataFrame, conceptos: set[str]) -> pd.DataFrame:
    columnas = ["concept", "numeric_value", "period_type", "period_start", "period_end"]
    df = facts.loc[:, [c for c in columnas if c in facts.columns]].copy()
    df["concept"] = _sin_prefijo(df["concept"])
    df = df[df["concept"].isin(conceptos)]

    df["period_start"] = pd.to_datetime(df["period_start"], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df["numeric_value"] = pd.to_numeric(df["numeric_value"], errors="coerce")
    df = df.dropna(subset=["period_end", "numeric_value"])

    # Later filings restate earlier quarters, so the same concept and window can
    # appear several times. Keeping the last occurrence takes the most recently
    # filed value; keeping the first would freeze a figure the company corrected,
    # and summing them would double it.
    if "fiscal_year" in facts.columns:
        df["_orden"] = pd.to_numeric(facts.loc[df.index, "fiscal_year"], errors="coerce")
    else:
        df["_orden"] = 0
    df = df.sort_values("_orden", kind="stable")

    return df


def _por_duracion(df: pd.DataFrame, minimo: int, maximo: int) -> pd.DataFrame:
    dur = df[df["period_type"] == "duration"].copy()
    if dur.empty:
        return dur
    dias = (dur["period_end"] - dur["period_start"]).dt.days
    dur = dur[dias.between(minimo, maximo)]
    return dur.drop_duplicates(["concept", "period_start", "period_end"], keep="last")


def _cuartos_derivados(trimestres: pd.DataFrame, anuales: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the missing Q4 as the year minus the three reported quarters.

    Companies file no 10-Q for their fourth quarter — it is folded into the 10-K
    as an annual figure — so without this one quarter in four is empty for every
    flow KPI, and the year-on-year shift lands on a hole.

    Exact arithmetic for flows, and only when all three quarters are present: two
    quarters subtracted from a year produce an inflated figure that looks real.
    """
    if trimestres.empty or anuales.empty:
        return trimestres.iloc[:0]

    derivadas = []
    for _, ano in anuales.iterrows():
        dentro = trimestres[
            (trimestres["concept"] == ano["concept"])
            & (trimestres["period_start"] >= ano["period_start"])
            & (trimestres["period_end"] <= ano["period_end"])
        ]
        if len(dentro) != _TRIMESTRES_POR_ANO - 1:
            continue
        derivadas.append(
            {
                "concept": ano["concept"],
                "numeric_value": ano["numeric_value"] - dentro["numeric_value"].sum(),
                "period_type": "duration",
                "period_start": dentro["period_end"].max() + pd.Timedelta(days=1),
                "period_end": ano["period_end"],
            }
        )

    return pd.DataFrame(derivadas, columns=trimestres.columns.drop("_orden", errors="ignore"))


def quarterly_panel(
    facts: pd.DataFrame, conceptos: set[str], n_periodos: int = 12
) -> pd.DataFrame:
    """Long SEC facts -> panel indexed by period end, one column per concept.

    Every requested concept becomes a column even when the company never reports
    it: a panel whose columns depend on the filer cannot be concatenated across
    a universe.
    """
    conceptos = set(conceptos)
    vacio = pd.DataFrame(
        columns=sorted(conceptos), index=pd.DatetimeIndex([], name="period_end"), dtype="float64"
    )
    if facts.empty or "concept" not in facts.columns:
        return vacio

    df = _preparar(facts, conceptos)
    if df.empty:
        return vacio

    trimestres = _por_duracion(df, *_DIAS_TRIMESTRE)
    anuales = _por_duracion(df, *_DIAS_ANO)
    piezas = [trimestres.drop(columns="_orden", errors="ignore"), _cuartos_derivados(trimestres, anuales)]
    # Concatenating empty frames is deprecated in pandas and changes dtype
    # inference; dropping them keeps the result float64 either way.
    piezas = [p for p in piezas if not p.empty]
    flujos = pd.concat(piezas, ignore_index=True) if piezas else trimestres.iloc[:0]
    # A reported quarter always wins over a derived one: the derivation exists
    # only to fill the gap the 10-K leaves.
    flujos = flujos.drop_duplicates(["concept", "period_end"], keep="first")

    fechas = pd.DatetimeIndex(sorted(flujos["period_end"].unique()))
    if fechas.empty:
        return vacio

    instantes = df[df["period_type"] == "instant"]
    # Balance figures are snapshots, so they carry no duration to filter on.
    # Restricting them to the quarter grid keeps stray dates from the 10-K cover
    # page — share counts as of a filing day — from inventing extra quarters.
    instantes = instantes[instantes["period_end"].isin(fechas)]
    instantes = instantes.drop_duplicates(["concept", "period_end"], keep="last")

    largo = pd.concat(
        [flujos[["concept", "period_end", "numeric_value"]],
         instantes[["concept", "period_end", "numeric_value"]]],
        ignore_index=True,
    )
    panel = largo.pivot_table(
        index="period_end", columns="concept", values="numeric_value", aggfunc="last"
    )
    panel = panel.reindex(columns=sorted(conceptos)).sort_index()
    panel.index.name = "period_end"
    return panel.tail(n_periodos).astype("float64")
