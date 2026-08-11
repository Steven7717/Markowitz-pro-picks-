from pathlib import Path

import numpy as np
import pandas as pd

# Al regenerar la tabla, actualiza también OUTPUT en scripts/bootstrap_sectors.py
_TABLA = Path(__file__).parent / "data" / "sectores_2026-08-10.csv"

MIN_PARES = 3


def load_sectors(path: Path | None = None) -> dict[str, str]:
    """Read the frozen ticker -> GICS sector table. Never queries the network."""
    frame = pd.read_csv(path or _TABLA)
    return dict(zip(frame["ticker"], frame["sector_gics"]))


def zscore_within_sector(
    kpis: pd.DataFrame, sectores: pd.Series, min_pares: int = MIN_PARES
) -> pd.DataFrame:
    """Standardise each KPI against sector peers rather than the whole universe.

    A margin of 40% means something different for software than for a grocer, so
    comparing across sectors ranks the sector, not the company.

    Returns NaN — never 0 — where a score cannot be computed: unknown sector, a
    peer group too small to have a meaningful spread, or a sector where every
    company reports the same value. A 0 would read as "exactly average".
    """
    sectores = sectores.reindex(kpis.index)
    resultado = pd.DataFrame(np.nan, index=kpis.index, columns=kpis.columns, dtype="float64")

    for _, grupo in kpis.groupby(sectores, dropna=True):
        if len(grupo) < min_pares:
            continue
        desviacion = grupo.std(ddof=1)
        # A zero spread divides to infinity, which downstream reads as a huge
        # score. Masking it keeps "no dispersion" distinguishable from "extreme".
        centrado = grupo - grupo.mean()
        resultado.loc[grupo.index] = centrado / desviacion.where(desviacion > 0)

    return resultado
