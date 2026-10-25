"""La ficha de un ticker frente a sus pares del S&P 500.

El panel de referencia es el que `ranking.run.guardar` deja en
`salidas/panel.parquet` cada vez que se generan candidatos: los KPIs crudos, el
trimestre natural y el sector de cada fila. La referencia es la de la última
vez que se generaron candidatos, y su fecha se enseña.

**Si el ticker está en el panel**, su ficha sale idéntica a la de Revisar
candidatos. **Si no está**, sus filas se insertan en su sector, trimestre a
trimestre, y se le aplican las mismas funciones que al ranking: el z por sector
con el mismo tope, la media de la ventana, los pilares, las guardas y la nota
compuesta. Insertarla mueve un poco la media y la dispersión de su sector, y
con ellas los z de sus pares: es lo que habría pasado si hubiera estado en el
panel desde el principio, que es justo la comparación que se busca.

El puesto es el **global**: el orden por nota compuesta entre las que pasan las
guardas, sin el tope por sector. Es el único que existe para un ticker que no
compite por las quince plazas, y para el primero de los candidatos coincide con
su puesto.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import anadir_zscores
from ranking.criterio import TRIMESTRES_VENTANA
from ranking.fichas import ficha_numerica
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    media_ventana,
    puntuaciones_por_pilar,
)

RUTA_PANEL = Path(__file__).resolve().parent.parent / "salidas" / "panel.parquet"
_COLUMNAS = ("ticker", "periodo", "trimestre", "sector_gics", *TODOS_LOS_KPIS)


@dataclass(frozen=True)
class Referencia:
    """La ficha frente al sector, con la forma de `ranking.fichas.ficha_numerica`.

    `puesto` y `compuesto` son None si una guarda lo deja fuera, y `exclusion`
    dice cuál. `supervivientes` es cuántas pasan las guardas, ésta incluida si
    pasa: el «de cuántas» del puesto.
    """

    ficha: dict
    compuesto: "float | None"
    puesto: "int | None"
    supervivientes: int
    exclusion: "str | None"
    en_panel: bool


def cargar_panel(ruta: "Path | None" = None) -> "tuple[pd.DataFrame | None, date | None]":
    """El panel de referencia y la fecha en que se escribió, o `(None, None)`.

    Un fichero que no se puede leer, o al que le falta una columna, se trata
    como ausente: la pantalla ofrece reconstruirlo, que es gratis. No es
    historial que se pierda, al revés que un archivo de la IA.
    """
    ruta = Path(ruta or RUTA_PANEL)
    if not ruta.exists():
        return None, None
    try:
        crudo = pd.read_parquet(ruta)
    except (OSError, ValueError, ImportError):
        # pyarrow lanza `ArrowInvalid`, que es un `ValueError`, con un fichero
        # que no es parquet, y `ArrowIOError`, que es un `OSError`, al leerlo.
        return None, None
    if not set(_COLUMNAS) <= set(crudo.columns):
        return None, None
    crudo["periodo"] = pd.to_datetime(crudo["periodo"])
    panel = crudo.set_index(["ticker", "periodo"]).sort_index()
    return panel, date.fromtimestamp(ruta.stat().st_mtime)


def frente_al_sector(
    ticker: str,
    panel: pd.DataFrame,
    sector: "str | None" = None,
    propias: "pd.DataFrame | None" = None,
) -> "Referencia | None":
    """La ficha de `ticker` frente a su sector, o `None` si no hay con qué hacerla.

    Si el ticker no está en el panel hacen falta su `sector` GICS y `propias`:
    sus filas de KPIs, indexadas por fecha de cierre y con la columna
    `trimestre`, como las da `analizador.kpis`. Las posteriores al último
    trimestre del panel no entran: en ese trimestre no tiene pares, y su z
    saldría vacía y le quitaría un trimestre de la ventana.
    """
    trimestre_max = str(panel["trimestre"].max())
    en_panel = ticker in panel.index.get_level_values("ticker")
    if en_panel:
        # Ordenado como lo deja `build_panel` antes de los z: el orden de las
        # filas fija el de las sumas, y con otro los z diferirían en la última
        # cifra de los del ranking.
        completo = panel.sort_index()
    else:
        if sector is None or propias is None:
            return None
        propias = propias[propias["trimestre"].astype(str) <= trimestre_max]
        if propias.empty:
            return None
        filas = propias.reindex(columns=[*TODOS_LOS_KPIS, "trimestre"]).copy()
        filas["sector_gics"] = sector
        filas.index = pd.MultiIndex.from_arrays(
            [[ticker] * len(filas), pd.DatetimeIndex(propias.index)],
            names=["ticker", "periodo"],
        )
        completo = pd.concat([panel, filas]).sort_index()

    # Las mismas funciones y en el mismo orden que `ranking.run.construir_ranking`.
    sectores = completo["sector_gics"].groupby(level="ticker").last()
    con_z = anadir_zscores(completo.drop(columns="sector_gics"), sectores.to_frame("sector_gics"))
    z, valores, historial = media_ventana(con_z, n=TRIMESTRES_VENTANA)
    pilares, conteo = puntuaciones_por_pilar(z)
    motivos = aplicar_guardas(pilares, conteo, historial, trimestre_max)
    puntos = compuesto(pilares, motivos, sectores)
    motivos = marcar_sin_pares(motivos, puntos, sectores)

    validos = puntos.dropna()
    orden = sorted(validos.index, key=lambda t: (-validos[t], t))
    puesto = orden.index(ticker) + 1 if ticker in validos.index else None
    nota = float(validos[ticker]) if ticker in validos.index else None
    ficha = ficha_numerica(
        ticker=ticker,
        sector=sectores[ticker],
        puesto=puesto or 0,
        compuesto=float("nan") if nota is None else nota,
        pilares=pilares.loc[ticker],
        conteo=conteo.loc[ticker],
        z=z.loc[ticker],
        valores=valores.loc[ticker],
        desplazo_a=[],
    )
    # `ficha_numerica` exige un puesto y una nota; fuera por una guarda no hay
    # ninguno de los dos, y un 0 o un NaN se leerían como una cifra.
    ficha = {**ficha, "puesto": puesto, "compuesto": nota}
    exclusion = motivos.get(ticker)
    return Referencia(
        ficha=ficha,
        compuesto=nota,
        puesto=puesto,
        supervivientes=len(validos),
        exclusion=None if pd.isna(exclusion) else str(exclusion),
        en_panel=en_panel,
    )
