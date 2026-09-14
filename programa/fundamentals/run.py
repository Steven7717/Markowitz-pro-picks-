from pathlib import Path

import pandas as pd

from fundamentals.concepts import (
    CONCEPTOS,
    completar_bpa_por_identidad,
    reconciliar_recuento_de_acciones,
    resolve_lines,
)
from fundamentals.fetch import (
    MIN_TRIMESTRES,
    PERIODOS,
    CorridaAbortada,
    CoverageReport,
    load_facts,
)
from fundamentals.kpis import (
    TODOS_LOS_KPIS,
    compute_growth,
    compute_levels,
    compute_valuation,
)
from fundamentals.panel import cierres_de_ejercicio, quarterly_panel
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

# El cierre de ejercicio no se presenta en un 10-Q sino en un 10-K, y su plazo
# no es de 40 días sino de **60** para un large accelerated filer. Aplicarle los
# 45 del trimestre devolvía el look-ahead por la puerta de atrás: contrastado
# con las fechas de presentación que las propias fichas traen dentro, CPRT cerró
# el 2025-07-31 y presentó el 2025-09-26 —57 días—, así que el motor cotizaba el
# 2025-09-14, doce días ANTES de que las cuentas existieran. Diez de las quince
# candidatas de la última corrida usaban un precio anterior a la publicación de
# sus cuentas: MNST 13 días, CF 11, CEG 10, GRMN 8, CBOE 6, APP 5, CVNA 4,
# EXE 4, PLTR 3, VEEV 3.
#
# 65 y no 60 por el mismo margen de cinco días que lleva la constante de arriba
# sobre su propio plazo. Y no un desfase único de 65 para los cuatro trimestres,
# porque cotizaría tres de cada cuatro con veinte días de rancio sin motivo.
#
# Lo ideal sería la fecha real de presentación, que `edgartools` conoce; no se
# usa porque no viaja en la caché de hechos —sus diez columnas no incluyen
# ninguna fecha de registro— y leerla obligaría a salir a la red por cada
# empresa. El desfase por plazo legal es la aproximación que no la necesita.
DIAS_HASTA_PRESENTACION_ANUAL = 65


def _precios_por_periodo(
    ticker: str,
    periodos: pd.DatetimeIndex,
    cierres_anuales: pd.DatetimeIndex | None = None,
) -> tuple[pd.Series, bool]:
    """Closing price at the date each quarter's results became public.

    Devuelve la serie y **si la descarga falló**, que no es lo mismo que una
    serie vacía: la empresa que no cotizó en esa ventana y la petición que no
    llegó a completarse dejan las dos el pilar de valoración vacío, y hasta este
    cambio eran indistinguibles. Ver `CoverageReport.failed_price_download`.

    `cierres_anuales` son las fechas en que esta empresa cierra ejercicio, que
    `fundamentals.panel.cierres_de_ejercicio` deduce de sus ventanas de doce
    meses. Las que estén ahí se cotizan con el plazo del 10-K y el resto con el
    del 10-Q. Vacío por defecto para que un test que sólo mira el caso
    trimestral no tenga que declararlo.

    Isolated so tests can replace it without touching the network, and so the
    price source stays swappable — it reuses research.loader today.

    **Defecto conocido, sin arreglar aquí: el precio viene doblemente ajustado.**
    `research.loader._download` descarga con `auto_adjust=True`, y hace bien para
    lo que ese módulo existe —el optimizador sólo usa retornos, donde el ajuste
    es consistente dentro de una descarga—. Pero un precio ajustado **cambia
    hacia atrás** cada vez que la empresa reparte un dividendo, así que el precio
    de un trimestre pasado no es el que se cotizó: para un pagador, el PER
    histórico sale un 3-4% más barato de lo que fue. `seguimiento/precios.py`
    existe precisamente para no hacer esto, y documenta por qué; aquí se hace.

    No se arregla desde este módulo porque la palanca está en `research/loader.py`
    —que es de otro subproyecto y cuyo `auto_adjust=True` el optimizador
    necesita— y porque deshacer el ajuste requeriría el histórico de dividendos
    y splits, que la caché de precios no guarda. Lo que corresponde es una
    función de descarga sin ajustar, como la que ya tiene `seguimiento`, y esa
    decisión no es de este fichero.

    **Y el mismo `auto_adjust` ajusta también por los splits, que no son un 3-4%:
    son factores de 2, 5, 10 o 24.** Es el mismo mecanismo y un defecto de otro
    orden de magnitud, así que va dicho aparte. El precio de un trimestre
    anterior a un split viene dividido por el factor del split —está en la base
    de hoy—, mientras que el recuento de acciones que declara el XBRL de ese
    trimestre está en la base de entonces. Multiplicar uno por otro no da la
    capitalización de nadie:

        NFLX, capitalización por trimestre (miles de millones $)
          2025-09-30  48,3    2025-12-31  814,2    2026-03-31  374,1
        BKNG  6,5 / 5,9 / 122,1 / 164,0, con PER 1,70 · 1,40 · 1,17 · 1,61
              — el único PER por debajo de 3 de todo el panel, en la empresa
              que cotiza a ~25x — y EV/EBITDA de 0,77 y 0,78.

    Y no sólo la capitalización: el TTM del BPA suma cuatro trimestres que pueden
    estar en dos bases distintas, así que el PER se corrompe aunque no use el
    recuento. Dieciséis empresas saltan más de 1,3x de recuento dentro de la
    ventana que puntúa; tres estaban en el top 50 —TPL (#24), BG (#37) y BKNG
    (#42)—, y el pilar de valoración es un cuarto de la nota.

    **Cómo se cierra, y por qué así.** No desde aquí sino desde el otro lado de
    la multiplicación, en `fundamentals.concepts.reconciliar_recuento_de_acciones`:
    el recuento de cada trimestre se contrasta contra la base más reciente de la
    propia empresa —que es la base en la que está el precio ajustado— y el que no
    encaja se declara ausente, junto con su BPA. La alternativa, que era usar
    precios sin ajustar para la capitalización, está descartada por dos motivos:
    la palanca vive en `research/loader.py`, que es de otro subproyecto, y la
    caché de precios sólo guarda series ya ajustadas, así que ni siquiera se
    puede medir el cambio sin salir a la red. La alternativa de restaurar la base
    multiplicando por el factor del split está descartada por un tercero: sin
    calendario de splits no se distingue un split de 2x de una fusión que emite
    el doble de acciones, y equivocarse pondría una capitalización inventada
    donde ahora hay un hueco visible en la cobertura del pilar.
    """
    from research.loader import load_ohlcv

    if len(periodos) == 0:
        return pd.Series(dtype="float64"), False

    periodos = pd.DatetimeIndex(periodos)
    if cierres_anuales is None:
        cierres_anuales = pd.DatetimeIndex([])
    anuales = periodos.isin(pd.DatetimeIndex(cierres_anuales))
    desfase = pd.to_timedelta(
        [
            DIAS_HASTA_PRESENTACION_ANUAL if es_anual else DIAS_HASTA_PRESENTACION
            for es_anual in anuales
        ],
        unit="D",
    )
    publicacion = periodos + desfase
    vacio = pd.Series(float("nan"), index=periodos, dtype="float64")

    # La ventana se calcula sobre las fechas que de verdad se van a buscar. Si
    # se quedara corta, `asof` devolvería el último cierre disponible en vez de
    # nada y el precio saldría rancio sin que nada lo dijera.
    panel, cobertura_precios = load_ohlcv(
        [ticker],
        start=(publicacion.min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(publicacion.max() + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    # `load_ohlcv` ya sabe si la descarga falló y su informe se estaba tirando a
    # la basura en este mismo renglón. Un doble de test puede devolver `None` en
    # su lugar, y eso se lee como «no consta», nunca como «falló»: convertir la
    # ausencia de informe en un fallo haría abortar corridas sanas.
    fallo = bool(
        cobertura_precios is not None and ticker in cobertura_precios.failed_download
    )
    if panel.empty or ("Close", ticker) not in panel.columns:
        return vacio, fallo

    cierres = panel[("Close", ticker)].dropna()
    if cierres.empty:
        return vacio, fallo

    # asof: the last close at or before publication, so a date falling on a
    # weekend or holiday takes the previous session rather than nothing.
    precios = pd.Series(
        [cierres.asof(f) for f in publicacion], index=periodos, dtype="float64"
    )
    return precios, fallo


def _abortar_si_no_hay_precios(cobertura: CoverageReport, con_precio: int) -> None:
    """Que fallen todas las descargas de precio no es que fallen las empresas.

    Es la misma política que `load_facts` aplica a los hechos, y por el mismo
    motivo: sin un solo precio, el pilar de valoración se queda vacío para todo
    el universo, `ranking.score.compuesto` exige los cuatro pilares y la corrida
    entrega un ranking vacío tras veinte minutos de trabajo. Decir por qué es
    estrictamente mejor que entregar esa página en blanco.

    Salta sólo cuando hubo fallos de descarga y **ninguna** empresa llegó a tener
    un precio. Una caché de precios a medias —70 de 502 claves fallando tras
    mover el desfase de 45 a 65 días— no condena la corrida: se anota empresa a
    empresa en `failed_price_download`, que es donde el informe la puede leer.
    Y un universo sin precios pero sin fallos de descarga tampoco: eso no es que
    falte la fuente, es que la fuente no cubre esas fechas.
    """
    if not cobertura.failed_price_download or con_precio:
        return
    raise CorridaAbortada(
        "sin_precios",
        "No se pudo descargar el precio de ninguna de las empresas, así que "
        "ninguna tiene múltiplos de valoración y el ranking saldría vacío. "
        "Comprueba tu conexión: los hechos de la SEC ya están en caché y no se "
        "vuelven a bajar, pero la caché de precios no cubre estas fechas.",
        cobertura,
    )


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
    con_precio = 0

    for ticker, facts in hechos.items():
        panel_conceptos = quarterly_panel(facts, CONCEPTOS, n_periodos=periods)
        lineas, ausentes = resolve_lines(panel_conceptos)
        # Después de resolver las cadenas y no dentro de ellas: la
        # reconciliación contrasta tres líneas ya resueltas entre sí, y
        # `resolve_lines` habla de qué etiqueta vale, no de en qué escala viene.
        #
        # Y completar el BPA va después de reconciliar, nunca antes: rellenar el
        # hueco con un recuento en la escala equivocada o en una base que no es
        # la del precio sembraría el hueco con el defecto que la reconciliación
        # acaba de quitar.
        lineas = reconciliar_recuento_de_acciones(lineas)
        lineas = completar_bpa_por_identidad(lineas)
        if ausentes:
            cobertura.missing_concepts[ticker] = ausentes
        if lineas.empty:
            cobertura.short_history[ticker] = 0
            continue
        if len(lineas) < MIN_TRIMESTRES:
            cobertura.short_history[ticker] = len(lineas)

        precios, fallo_de_precio = _precios_por_periodo(
            ticker, lineas.index, cierres_de_ejercicio(facts, CONCEPTOS)
        )
        # El orden importa: una descarga que falló deja la serie vacía, así que
        # preguntar primero por el `isna().all()` mandaría todos los fallos a la
        # casilla equivocada, que es justo la confusión que esto viene a quitar.
        if fallo_de_precio:
            cobertura.failed_price_download.append(ticker)
        elif precios.isna().all():
            cobertura.missing_price.append(ticker)
        if precios.notna().any():
            con_precio += 1

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

    _abortar_si_no_hay_precios(cobertura, con_precio)

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
