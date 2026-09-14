"""Turn SEC's long fact table into a quarterly panel.

`facts.to_dataframe()` returns one row per reported fact: tens of thousands per
company, mixing quarters with annual and cumulative periods, point-in-time
balance figures with flow figures, and several restatements of the same quarter.
This module reduces that to one row per quarter and one column per concept.
"""
import numpy as np
import pandas as pd

from fundamentals.concepts import MEDIAS_PONDERADAS

# A filing reports the same line over several windows: the quarter, the half,
# the nine months, and the year. Only true quarters and true years are useful —
# the cumulative ones would multiply a flow figure if mistaken for a quarter.
_DIAS_TRIMESTRE = (80, 100)
_DIAS_ANO = (350, 380)

_TRIMESTRES_POR_ANO = 4

# Días de un trimestre medio (365,25 / 4). Sirve para contar cuántos trimestres
# abarca una ventana acumulada, que es lo que pondera la media de la que sale el
# trimestre que falta. Redondear el cociente tolera de sobra los calendarios de
# 52/53 semanas, donde un trimestre dura 91 días unas veces y 98 otras.
_DIAS_POR_TRIMESTRE = 91.31

# Una media ponderada derivada no puede alejarse de la del año del que sale: un
# recuento de acciones no se duplica ni se parte por la mitad en un trimestre.
# La fórmula multiplica por n, así que también multiplica por n cualquier
# irregularidad del calendario; fuera de este margen lo que sale no es una
# medición sino ruido amplificado, y un hueco declarado es preferible.
_FACTOR_MAXIMO_MEDIA = 2.0


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


def _trimestres_de_ventana(inicio: pd.Timestamp, fin: pd.Timestamp) -> int:
    """Cuántos trimestres abarca una ventana acumulada: 1, 2, 3 o 4."""
    return int(round(((fin - inicio).days + 1) / _DIAS_POR_TRIMESTRE))


def _descumulado(
    concepto: str, n_anterior: int, v_anterior: float, v_actual: float
) -> float:
    """El trimestre que encierran dos ventanas acumuladas consecutivas.

    Un flujo acumulado es la **suma** de sus trimestres, así que el último es la
    resta de las dos ventanas. Una media ponderada es el **promedio** de ellos,
    así que la media de n trimestres por n, menos la media de n-1 por n-1, deja
    el que falta: `n·YTDn − (n−1)·YTDn−1`.

    Restar sin más una media ponderada era el defecto: CPRT declara 977.485.000
    acciones hasta abril de 2025 y 977.563.000 hasta julio, y el panel guardaba
    la diferencia —78.000— como «las acciones del Q4», que es con lo que se
    calculaba la capitalización. Medido sobre las 6.004 celdas de recuento del
    panel: 974 no positivas —que al menos se enmascaraban— y 474 positivas pero
    absurdas —que sobrevivían— repartidas por 248 empresas. Los mínimos de la
    serie de cada una lo enseñan: AAPL −55.080.000, ADI −1.845.000, MCD −2,
    ES 109.161 contra una mediana de 356.618.658. Con esta fórmula quedan 0 no
    positivas y 37 absurdas en 16 empresas, y el mínimo de CPRT pasa de 78.000 a
    942.770.000 contra una mediana de 976.475.500.

    Contrastado sobre las 502 cachés contra el trimestre que la empresa sí llegó
    a declarar suelto, con 15.579 pares para el recuento de acciones: la resta
    simple se equivoca con un error mediano del 100% y esta fórmula acierta con
    un 0,03%, dentro del 1% en el 93,4% de los casos. Para los ingresos y el BPA
    es al revés — error mediano 0 restando—, que es lo que los confirma como
    acumulados de verdad.
    """
    if concepto in MEDIAS_PONDERADAS:
        return (n_anterior + 1) * v_actual - n_anterior * v_anterior
    return v_actual - v_anterior


def _media_creible(concepto: str, derivado: float, referencia: float) -> bool:
    """Si el trimestre derivado de una media puede ser una medición."""
    if concepto not in MEDIAS_PONDERADAS:
        return True
    if not np.isfinite(derivado) or not np.isfinite(referencia) or referencia <= 0:
        return False
    return referencia / _FACTOR_MAXIMO_MEDIA <= derivado <= referencia * _FACTOR_MAXIMO_MEDIA


def _descumulados(df: pd.DataFrame) -> pd.DataFrame:
    """Split cumulative year-to-date figures into the quarters they contain.

    Cash flow and, for many filers, the income statement are not reported one
    quarter at a time. A 10-Q gives the year to date: three months, then six,
    then nine, all sharing the fiscal year's start date. Keeping only windows
    that are already 80-100 days long therefore captures the first quarter of
    each year and silently drops the other three — which is what held free cash
    flow coverage at 12% before this existed.

    Cómo se recupera el trimestre depende de si el concepto se acumula sumando o
    promediando; lo decide `_descumulado`, y la lista de los que promedian está
    en `fundamentals.concepts.MEDIAS_PONDERADAS`.
    """
    dur = df[df["period_type"] == "duration"]
    if dur.empty:
        return dur.iloc[:0]

    dur = dur.drop_duplicates(["concept", "period_start", "period_end"], keep="last")
    dur = dur.sort_values(["concept", "period_start", "period_end"], kind="stable")

    salida: list[dict] = []
    for (concepto, inicio), grupo in dur.groupby(["concept", "period_start"], sort=False):
        if len(grupo) < 2 or pd.isna(inicio):
            continue
        fines = grupo["period_end"].tolist()
        valores = grupo["numeric_value"].tolist()
        for anterior, actual, v_anterior, v_actual in zip(fines, fines[1:], valores, valores[1:]):
            dias = (actual - anterior).days
            if not _DIAS_TRIMESTRE[0] <= dias <= _DIAS_TRIMESTRE[1]:
                continue
            n_anterior = _trimestres_de_ventana(inicio, anterior)
            valor = _descumulado(concepto, n_anterior, v_anterior, v_actual)
            if not _media_creible(concepto, valor, v_actual):
                continue
            salida.append(
                {
                    "concept": concepto,
                    "numeric_value": valor,
                    "period_type": "duration",
                    "period_start": anterior + pd.Timedelta(days=1),
                    "period_end": actual,
                }
            )

    return pd.DataFrame(salida, columns=["concept", "numeric_value", "period_type",
                                         "period_start", "period_end"])


def _cuartos_derivados(trimestres: pd.DataFrame, anuales: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the missing Q4 as the year minus the three reported quarters.

    Companies file no 10-Q for their fourth quarter — it is folded into the 10-K
    as an annual figure — so without this one quarter in four is empty for every
    flow KPI, and the year-on-year shift lands on a hole.

    Exact arithmetic for flows, and only when all three quarters are present: two
    quarters subtracted from a year produce an inflated figure that looks real.

    La misma distinción que en `_descumulado`: la cifra anual de un flujo son
    sus cuatro trimestres sumados, y la de una media ponderada es su promedio,
    de modo que las cuatro juntas son cuatro veces la anual. En los dos casos se
    resta lo mismo —las tres trimestrales declaradas—, y lo único que cambia es
    el coeficiente que lleva la anual.
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
        veces = (
            _TRIMESTRES_POR_ANO if ano["concept"] in MEDIAS_PONDERADAS else 1
        )
        valor = veces * ano["numeric_value"] - dentro["numeric_value"].sum()
        if not _media_creible(ano["concept"], valor, ano["numeric_value"]):
            continue
        derivadas.append(
            {
                "concept": ano["concept"],
                "numeric_value": valor,
                "period_type": "duration",
                "period_start": dentro["period_end"].max() + pd.Timedelta(days=1),
                "period_end": ano["period_end"],
            }
        )

    return pd.DataFrame(derivadas, columns=trimestres.columns.drop("_orden", errors="ignore"))


def cierres_de_ejercicio(facts: pd.DataFrame, conceptos: set[str]) -> pd.DatetimeIndex:
    """Las fechas en que esta empresa cierra un ejercicio, no un trimestre.

    Existe porque el plazo legal de presentación no es el mismo: 40 días para el
    10-Q y 60 para el 10-K de un large accelerated filer. Quien fija el precio de
    cada trimestre necesita saber cuál de los dos le toca, y el mes de cierre no
    se puede leer del calendario — el de Apple es septiembre y el de CPRT julio.

    Se deduce de las ventanas de doce meses que la propia empresa declara, que
    es la definición que este módulo ya usa para todo lo demás y no depende de
    que la SEC rellene la columna `fiscal_period`.

    Función aparte y no un segundo valor de `quarterly_panel` para no cambiarle
    la firma a la docena de sitios que la llaman por una cosa que sólo necesita
    `fundamentals.run`.
    """
    vacio = pd.DatetimeIndex([], name="period_end")
    if facts.empty or "concept" not in facts.columns:
        return vacio

    df = _preparar(facts, set(conceptos))
    if df.empty:
        return vacio

    anuales = _por_duracion(df, *_DIAS_ANO)
    if anuales.empty:
        return vacio
    return pd.DatetimeIndex(sorted(anuales["period_end"].unique()), name="period_end")


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
    # Order matters: a quarter the company reported outright beats one recovered
    # from a cumulative series, which in turn beats one backed out of the annual
    # figure. drop_duplicates(keep="first") below enforces exactly that ranking.
    piezas = [
        trimestres.drop(columns="_orden", errors="ignore"),
        _descumulados(df),
        _cuartos_derivados(trimestres, anuales),
    ]
    # Concatenating empty frames is deprecated in pandas and changes dtype
    # inference; dropping them keeps the result float64 either way.
    piezas = [p for p in piezas if not p.empty]
    flujos = pd.concat(piezas, ignore_index=True) if piezas else trimestres.iloc[:0]
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
