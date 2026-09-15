from pathlib import Path

import numpy as np
import pandas as pd

# Al regenerar la tabla, actualiza también OUTPUT en scripts/bootstrap_sectors.py
_TABLA = Path(__file__).parent / "data" / "sectores_2026-08-10.csv"

MIN_PARES = 3

# El tope del z-score, en desviaciones. Enmienda fechada del 2026-09-14; el
# porque, y por que tres y no dos y medio, en `zscore_within_sector`.
TOPE_Z = 3.0


def load_sectors(path: Path | None = None) -> dict[str, str]:
    """Read the frozen ticker -> GICS sector table. Never queries the network."""
    frame = pd.read_csv(path or _TABLA)
    return dict(zip(frame["ticker"], frame["sector_gics"]))


def zscore_within_sector(
    kpis: pd.DataFrame,
    sectores: pd.Series,
    min_pares: int = MIN_PARES,
    tope: "float | None" = TOPE_Z,
) -> pd.DataFrame:
    """Standardise each KPI against sector peers rather than the whole universe.

    A margin of 40% means something different for software than for a grocer, so
    comparing across sectors ranks the sector, not the company.

    Returns NaN — never 0 — where a score cannot be computed: unknown sector, a
    peer group too small to have a meaningful spread, or a sector where every
    company reports the same value. A 0 would read as "exactly average".

    **Enmienda fechada del 2026-09-14: el z se recorta a ±`TOPE_Z`.** Muchos de
    estos KPIs son cocientes acotados por abajo y sin techo --una razón corriente
    no puede bajar de cero y puede subir a diez-- así que estandarizar con media
    y desviación típica produce colas que un z-score no representa. Medido sobre
    el panel de esa fecha: ocho de las quince empresas elegidas tenían más de la
    mitad de su nota bruta en un solo z, y PLTR el 98,2 %.

    El recorte **no** arregla el sesgo del pilar apoyado en un solo KPI: se midió
    y lo empeoraba, porque un pilar de un único z recortado vale exactamente el
    tope mientras uno de tres recortados casi nunca. Eso lo corrige la imputación
    a 0 de `ranking.score.puntuaciones_por_pilar`, que es la otra mitad de la
    misma enmienda. Lo que el recorte aporta es acotar cuánto puede decidir un
    solo número: con las dos medidas juntas el máximo de concentración de la nota
    baja del 94,6 % al 61,5 %, y sólo un 2,15 % de las celdas llega a tocar el
    tope, así que se conserva la resolución que hace falta para ordenar 424
    nombres.

    Tres y no dos y medio: a ±2,5 el top 15 salía igual y el máximo de
    concentración sólo bajaba al 57,1 %, pero se saturaban más celdas. Y no se
    usa estandarización robusta (mediana/MAD) porque se midió y **fabrica** colas
    en vez de quitarlas: el p99 del z pasaba de 4,07 a 17,12 y el máximo a 963.

    `tope=None` desactiva el recorte, y `ranking.score.compuesto` lo usa así al
    re-estandarizar la nota final. El recorte es para los KPIs, que son cocientes
    sin techo; el compuesto ya es una suma de cuatro pilares hechos de z
    recortados, así que sus colas están acotadas por construcción. Recortarlo
    otra vez sólo destruye orden justo donde se decide el ranking: con el tope
    puesto, MU y NVDA empataban en exactamente 3,000 en los puestos 1 y 2.
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
        z = centrado / desviacion.where(desviacion > 0)
        # `clip` deja los NaN como están: «no medido» no es «en el tope».
        resultado.loc[grupo.index] = z if tope is None else z.clip(-tope, tope)

    return resultado
