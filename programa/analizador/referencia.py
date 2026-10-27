"""La ficha de un ticker frente a sus pares del S&P 500.

El panel de referencia es el que `ranking.run.guardar` deja en
`salidas/panel.parquet` cada vez que se generan candidatos: los KPIs crudos, el
trimestre natural y el sector de cada fila. La referencia es la de la última
vez que se generaron candidatos, y su fecha se enseña.

**Si el ticker está en el panel**, su ficha sale idéntica a la de Revisar
candidatos en sector, pilares, nota, destacados, flojos y cobertura; no en el
puesto, que es el global (abajo), ni en `desplazo_a`, que aquí siempre va
vacío porque sin la selección con tope no desplaza a nadie.

**Si no está**, sus filas se insertan en su sector, trimestre a
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

import io
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
# Las fichas de los candidatos, al lado del panel: `ranking.run.guardar` escribe
# los dos en la misma carpeta.
RUTA_FICHAS = RUTA_PANEL.parent / "fichas.json"
# Lo que separa el panel de las fichas cuando los escribe la misma corrida de
# `guardar`: unos segundos. Un panel más nuevo que eso se rehízo aparte, con
# `construir_panel`, que tarda al menos dos minutos.
HOLGURA_MISMA_CORRIDA = timedelta(minutes=1)
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
    # Cuántas filas propias se quedaron fuera por ser posteriores al último
    # trimestre del panel. Más de cero es que el panel se quedó atrás: con los
    # cinco trimestres de yfinance y el panel dos por detrás quedan tres, y la
    # guarda dice `historia_corta` cuando el problema es el panel (revisión de la
    # Task 11 de N1). Una del panel, siempre cero.
    filas_posteriores: int = 0


def cargar_panel(ruta: "Path | None" = None) -> "tuple[pd.DataFrame | None, date | None]":
    """El panel de referencia y la fecha en que se escribió, o `(None, None)`.

    Un fichero que no se puede leer, al que le falta una columna, vacío o con
    un `(ticker, periodo)` repetido se trata como ausente: la pantalla ofrece
    reconstruirlo, que es gratis. No es historial que se pierda, al revés que
    un archivo de la IA.
    """
    ruta = Path(ruta or RUTA_PANEL)
    if not ruta.exists():
        return None, None
    # `except Exception` a propósito: es un fichero que se regenera gratis, y
    # cualquier fallo al leerlo equivale a que no hay panel. Y no se puede
    # acotar: con bytes alterados pyarrow no se queda en `ArrowInvalid` (un
    # `ValueError`) ni en `ArrowIOError` (un `OSError`), sino que también lanza
    # su `ArrowException` base, `KeyError` o `TypeError`.
    try:
        crudo = pd.read_parquet(ruta)
        # Sólo las columnas que se usan: una de más, de texto, rompería los z,
        # y una que falta lanza `KeyError` aquí mismo.
        crudo = crudo[list(_COLUMNAS)].copy()
        crudo["periodo"] = pd.to_datetime(crudo["periodo"])
        panel = crudo.set_index(["ticker", "periodo"]).sort_index()
        fecha = date.fromtimestamp(ruta.stat().st_mtime)
    except Exception:
        return None, None
    # Sin filas no hay sector que comparar, y con un `(ticker, periodo)`
    # repetido los z no se pueden alinear con sus filas.
    if panel.empty or panel.index.has_duplicates:
        return None, None
    return panel, fecha


def construir_panel(ruta: "Path | None" = None) -> "tuple[pd.DataFrame | None, date | None]":
    """El panel de referencia, construido y escrito aparte de los candidatos.

    Es la corrida de «Generar gratis» sin la valoración
    --`construir_ranking(con_llm=False, con_valoracion=False)`, unos dos minutos
    con la caché llena--, pero **sólo escribe el panel**: ni las fichas, ni la
    corrida, ni el informe. `ranking.run.guardar` habría pisado las fichas con
    IA que el usuario pagó y, con ellas, sus casillas marcadas y sus añadidos a
    mano (revisión final de N1). Decisión del usuario del 2026-10-26.

    Escribe de forma atómica, un temporal en la misma carpeta y `os.replace`: un
    corte a mitad deja el panel de antes, que sigue siendo un panel válido de
    una corrida anterior. `guardar` hace otra cosa --borra el viejo antes de
    escribir-- porque allí el viejo es ajeno a las fichas nuevas.

    Devuelve lo que `cargar_panel` lee del fichero escrito. Una corrida sin panel
    (un universo vacío) no escribe nada y devuelve `(None, None)`.
    `CorridaAbortada` se deja salir: quien llama sabe decirlo. También puede
    salir `OSError`: el disco lleno, o el panel aún ocupado tras los reintentos.
    """
    # Aquí y no arriba: `ranking.run` arrastra la IA y la valoración, y este
    # módulo lo importan el análisis de un ticker y los tests, que no las necesitan.
    from ranking.run import construir_ranking

    ruta = Path(ruta or RUTA_PANEL)
    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    if resultado.panel is None or resultado.panel.empty:
        return None, None
    buffer = io.BytesIO()
    resultado.panel.reset_index().to_parquet(buffer, index=False)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # `mkstemp` y no un nombre fijo: dos pestañas pueden pulsar a la vez, y en
    # la misma carpeta porque `os.replace` sólo es atómico dentro de un volumen.
    descriptor, provisional = tempfile.mkstemp(dir=ruta.parent, prefix=".panel-", suffix=".tmp")
    temporal = Path(provisional)
    try:
        with os.fdopen(descriptor, "wb") as destino:
            destino.write(buffer.getvalue())
        _reemplazar(temporal, ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return cargar_panel(ruta)


# En Windows, `os.replace` da `PermissionError` mientras otra sesión tiene el
# panel abierto para leerlo, y suele soltarlo en un momento: pocas veces y poco
# rato, que quien pulsa está esperando.
_REINTENTOS = 4
_PAUSA = 0.25


def _reemplazar(temporal: Path, ruta: Path) -> None:
    for intento in range(_REINTENTOS):
        try:
            os.replace(temporal, ruta)
            return
        except PermissionError:
            if intento == _REINTENTOS - 1:
                raise
            time.sleep(_PAUSA)


def trimestre_final(panel: pd.DataFrame) -> str:
    """El último trimestre natural del panel (`"2026Q3"`): hasta dónde llega la referencia."""
    return str(panel["trimestre"].max())


def pares_en_panel(panel: pd.DataFrame, sector: str) -> int:
    """Cuántas empresas del panel son de `sector`."""
    return int(panel.index.get_level_values("ticker")[panel["sector_gics"] == sector].nunique())


@dataclass(frozen=True)
class Frescura:
    """De cuándo son el panel y los candidatos, por la hora de sus ficheros; None si no hay."""

    panel: "datetime | None"
    candidatos: "datetime | None"

    @property
    def panel_posterior(self) -> bool:
        """Si el panel se rehízo aparte después de generar los candidatos.

        Entonces la ficha de un candidato en el Analizador puede diferir un poco
        de la de Revisar candidatos, que se calculó con el panel de entonces.
        Sin candidatos no hay con qué compararlo.
        """
        if self.panel is None or self.candidatos is None:
            return False
        return self.panel - self.candidatos > HOLGURA_MISMA_CORRIDA


def _hora_del_fichero(ruta: Path) -> "datetime | None":
    try:
        return datetime.fromtimestamp(Path(ruta).stat().st_mtime)
    except OSError:
        return None


def frescura(ruta_panel: "Path | None" = None, ruta_fichas: "Path | None" = None) -> Frescura:
    """La hora del panel y la de los candidatos.

    Por la hora de los ficheros y no por `corrida.json`, que lleva el día pero
    no la hora: un panel rehecho la misma tarde no se distinguiría. Desde que el
    panel se construye aparte (`construir_panel`), panel y candidatos no tienen
    por qué ser de la misma corrida, y la pantalla enseña las dos fechas.
    """
    return Frescura(
        _hora_del_fichero(ruta_panel or RUTA_PANEL),
        _hora_del_fichero(ruta_fichas or RUTA_FICHAS),
    )


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
    trimestre_max = trimestre_final(panel)
    en_panel = ticker in panel.index.get_level_values("ticker")
    posteriores = 0
    if en_panel:
        # Ordenado como lo deja `build_panel` antes de los z: el orden de las
        # filas fija el de las sumas, y con otro los z diferirían en la última
        # cifra de los del ranking.
        completo = panel.sort_index()
    else:
        if sector is None or propias is None:
            return None
        dentro = propias[propias["trimestre"].astype(str) <= trimestre_max]
        posteriores = len(propias) - len(dentro)
        propias = dentro
        if propias.empty:
            return None
        filas = propias.reindex(columns=[*TODOS_LOS_KPIS, "trimestre"]).copy()
        # En texto, como el del panel: un `Period` formaría grupos aparte en
        # `anadir_zscores`, sin pares, y todos sus z saldrían vacíos.
        filas["trimestre"] = propias["trimestre"].astype(str)
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
        filas_posteriores=posteriores,
    )
