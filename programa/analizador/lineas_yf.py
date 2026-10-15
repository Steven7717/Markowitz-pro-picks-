"""Los estados de yfinance en las mismas columnas que la SEC.

Las filas de yfinance se traducen a las columnas que produce
`fundamentals.concepts.resolve_lines`, y de ahí pasan por las mismas funciones
de `fundamentals/kpis.py`. Así el ROE de WALMEX y el de MU salen de la misma
fórmula y en la misma base trimestral.

Los nombres de fila se fijaron contra lo que yfinance 1.6 devuelve de verdad
para MU, WALMEX.MX, TSM, JPM y BRK-B (sondeo del 2026-10-14); el test `red`
comprueba que siguen ahí.

**El capex se cambia de signo**: yfinance lo da negativo, como una salida de
caja, y la SEC lo declara positivo, como un pago. `valoracion.fundamentos` y
`fundamentals.kpis` lo esperan positivo.

**yfinance da cinco o seis trimestres, y a veces se salta uno** (a WALMEX le
falta el 3T 2025). `fundamentals.kpis` compara con `shift(4)` y suma con
`rolling(4)`, que cuentan filas y no trimestres: con un hueco, el «mismo
trimestre del año pasado» caería en otro. `rejilla_trimestral` da una fila a
cada trimestre natural, y `rellenar_desde_anual` recupera el flujo del que falta
como el año menos los otros tres.
"""

import numpy as np
import pandas as pd

from fundamentals.concepts import LINEAS

# Privadas y aun así importadas: son la duración de un trimestre con que
# `fundamentals.panel` decide qué es un trimestre, y el límite con que descarta
# una media derivada que se aleja demasiado de la anual. Una segunda copia aquí
# es como se separan.
from fundamentals.panel import _DIAS_TRIMESTRE, _FACTOR_MAXIMO_MEDIA, _TRIMESTRES_POR_ANO

# Cada línea del motor, la hoja de la que sale y sus filas candidatas por orden.
# La primera con dato **en cada fecha** gana, como en `resolve_lines`.
FILAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ingresos": ("resultados", ("Total Revenue",)),
    "coste_de_ventas": ("resultados", ("Cost Of Revenue",)),
    # BRK-B no trae `Operating Income`, sólo `EBIT`.
    "beneficio_operativo": ("resultados", ("Operating Income", "EBIT")),
    # El de los accionistas comunes, que es el que divide el BPA: en JPM, el
    # `Net Income` total incluye los dividendos de las preferentes.
    "beneficio_neto": ("resultados", ("Net Income Common Stockholders",)),
    "bpa_diluido": ("resultados", ("Diluted EPS",)),
    "depreciacion_amortizacion": ("resultados", ("Reconciled Depreciation",)),
    "gasto_por_intereses": ("resultados", ("Interest Expense",)),
    "acciones_diluidas": ("resultados", ("Diluted Average Shares",)),
    "activos_totales": ("balance", ("Total Assets",)),
    "activos_corrientes": ("balance", ("Current Assets",)),
    "pasivos_corrientes": ("balance", ("Current Liabilities",)),
    "patrimonio_neto": ("balance", ("Stockholders Equity",)),
    "deuda_total": ("balance", ("Total Debt",)),
    "efectivo": ("balance", ("Cash And Cash Equivalents",)),
    "flujo_operativo": ("flujos", ("Operating Cash Flow",)),
    "capex": ("flujos", ("Capital Expenditure",)),
}

# Las líneas que son flujos del periodo: su año es la suma de sus trimestres.
# El recuento medio de acciones es una media ponderada: su año es el promedio.
_FLUJOS = (
    "ingresos",
    "coste_de_ventas",
    "beneficio_operativo",
    "beneficio_neto",
    "depreciacion_amortizacion",
    "gasto_por_intereses",
    "flujo_operativo",
    "capex",
    "acciones_diluidas",
)
_MEDIAS = ("acciones_diluidas",)

# Los trimestres de un ejercicio que cierra en `fin` caen entre unos 273 días
# antes y `fin`; el cuarto trimestre del ejercicio anterior, a unos 365. Tres
# trimestres largos (300 días) separan los dos casos con margen, también en los
# calendarios de 52/53 semanas.
_ANTES_DEL_CIERRE = pd.Timedelta(days=3 * _DIAS_TRIMESTRE[1])
_DESPUES_DEL_CIERRE = pd.Timedelta(days=7)


def _fila(estado: pd.DataFrame, candidatas: "tuple[str, ...]") -> pd.Series:
    """La primera candidata con dato, columna a columna."""
    serie = pd.Series(np.nan, index=estado.columns, dtype="float64")
    for nombre in candidatas:
        if nombre not in estado.index:
            continue
        valores = estado.loc[nombre]
        if isinstance(valores, pd.DataFrame):
            # Un nombre de fila repetido: se queda la primera, como la ordena yfinance.
            valores = valores.iloc[0]
        serie = serie.where(serie.notna(), pd.to_numeric(valores, errors="coerce"))
    return serie


def lineas_desde_estados(
    resultados: "pd.DataFrame | None",
    balance: "pd.DataFrame | None",
    flujos: "pd.DataFrame | None",
) -> pd.DataFrame:
    """Las tres hojas de un periodo (trimestral o anual) en las columnas del motor.

    Una fila por fecha de cierre, de la más antigua a la más reciente, y siempre
    todas las columnas de `LINEAS`: un panel cuyas columnas dependen de la
    empresa no se puede concatenar con otro. Una fecha sin ningún dato no es una
    fila: el balance de WALMEX trae vacía la columna del trimestre que falta.
    """
    hojas = {"resultados": resultados, "balance": balance, "flujos": flujos}
    fechas = sorted(
        {
            pd.Timestamp(columna)
            for hoja in hojas.values()
            if hoja is not None and not hoja.empty
            for columna in hoja.columns
        }
    )
    indice = pd.DatetimeIndex(fechas, name="period_end")
    lineas = pd.DataFrame(np.nan, index=indice, columns=list(LINEAS), dtype="float64")
    for linea, (nombre_hoja, candidatas) in FILAS.items():
        hoja = hojas[nombre_hoja]
        if hoja is None or hoja.empty:
            continue
        serie = _fila(hoja, candidatas)
        serie.index = pd.DatetimeIndex([pd.Timestamp(c) for c in serie.index])
        serie = serie[~serie.index.duplicated(keep="first")]
        lineas[linea] = serie.reindex(indice)
    lineas["capex"] = -lineas["capex"]
    return lineas.dropna(how="all")


def rejilla_trimestral(lineas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por trimestre natural, consecutivos, con el que falta en NaN.

    El que falta lleva la fecha de tres meses después del anterior: así las
    distancias entre fechas siguen siendo las de un trimestre, que es lo que
    miran `valoracion.fundamentos` y `fundamentals.panel`.
    """
    if lineas.empty:
        return lineas
    trimestres = pd.PeriodIndex(lineas.index, freq="Q")
    # El mismo trimestre natural dos veces sería un cambio de calendario fiscal:
    # se queda la fecha más reciente, que es la que la empresa publicó después.
    lineas = lineas[~trimestres.duplicated(keep="last")]
    trimestres = pd.PeriodIndex(lineas.index, freq="Q")
    por_trimestre = dict(zip(trimestres, lineas.index))
    todos = pd.period_range(trimestres.min(), trimestres.max(), freq="Q")
    fechas, anterior = [], None
    for trimestre in todos:
        fecha = por_trimestre.get(trimestre)
        if fecha is None:
            # `DateOffset(months=3)` conserva el día del mes: del 30 de
            # septiembre daría el 30 de diciembre, que no es el cierre de nadie.
            # Desde un fin de mes se salta de fin de mes en fin de mes.
            salto = pd.offsets.MonthEnd(3) if anterior.is_month_end else pd.DateOffset(months=3)
            fecha = anterior + salto
        fechas.append(fecha)
        anterior = fecha
    rejilla = lineas.set_axis(trimestres).reindex(todos)
    rejilla.index = pd.DatetimeIndex(fechas, name=lineas.index.name)
    return rejilla


def rellenar_desde_anual(trimestres: pd.DataFrame, anuales: pd.DataFrame) -> pd.DataFrame:
    """El flujo del trimestre que falta, como el año menos los otros tres.

    Es la aritmética de `fundamentals.panel._cuartos_derivados`, que reconstruye
    el cuarto trimestre que la SEC no declara suelto, llevada a cualquier
    trimestre: dentro de un ejercicio con exactamente un trimestre vacío y el
    anual declarado, el vacío es el año menos los tres. Con dos vacíos no hay
    aritmética que valga, y se quedan vacíos.

    Sólo para flujos: un saldo de balance es una foto, y la del cierre no dice
    nada de la de septiembre. El recuento medio de acciones es una media: cuatro
    veces el anual menos los tres, y sólo si lo que sale no se aleja más del
    doble o la mitad del anual, que es la guarda de `fundamentals.panel`.
    """
    if trimestres.empty or anuales.empty:
        return trimestres
    rellenas = trimestres.copy()
    fechas = rellenas.index
    for fin, ano in anuales.iterrows():
        dentro = (fechas > fin - _ANTES_DEL_CIERRE) & (fechas <= fin + _DESPUES_DEL_CIERRE)
        posiciones = np.flatnonzero(dentro)
        if len(posiciones) != _TRIMESTRES_POR_ANO:
            continue
        for linea in _FLUJOS:
            anual = ano[linea]
            if not np.isfinite(anual):
                continue
            valores = rellenas[linea].iloc[posiciones]
            vacios = valores.isna().to_numpy()
            if vacios.sum() != 1:
                continue
            media = linea in _MEDIAS
            valor = (_TRIMESTRES_POR_ANO if media else 1) * anual - valores[~vacios].sum()
            if media and not (
                anual / _FACTOR_MAXIMO_MEDIA <= valor <= anual * _FACTOR_MAXIMO_MEDIA
            ):
                continue
            rellenas.iloc[posiciones[vacios][0], rellenas.columns.get_loc(linea)] = valor
    return rellenas
