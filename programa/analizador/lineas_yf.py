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

from fundamentals.concepts import (
    LINEAS,
    completar_bpa_por_identidad,
    reconciliar_recuento_de_acciones,
)
from fundamentals.kpis import (
    TODOS_LOS_KPIS,
    compute_growth,
    compute_levels,
    compute_valuation,
)

# Privadas y aun así importadas: son la duración de un trimestre y de un año con
# que `fundamentals.panel` decide qué es cada cosa, y el límite con que descarta
# una media derivada que se aleja demasiado de la anual. Una segunda copia aquí
# es como se separan.
from fundamentals.panel import (
    _DIAS_ANO,
    _DIAS_TRIMESTRE,
    _FACTOR_MAXIMO_MEDIA,
    _TRIMESTRES_POR_ANO,
)

# Privada y aun así importada: es el cubo de trimestre natural del panel de la
# SEC, y los dos paneles se juntan por él.
from fundamentals.run import _trimestre_natural
from valoracion.fundamentos import Ejercicio, Fundamentos, _num

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

# Las líneas que no se rellenan si salen negativas o descuadradas. Yahoo trae a
# veces trimestres que no cuadran con su año (WALMEX: 0,0 de intereses en cada
# trimestre y 9.115 M en el anual; HSBC: tres trimestres de amortización que
# suman más que el año; GFNORTEO: unos ingresos trimestrales negativos), y la
# resta los convierte en un trimestre absurdo con aspecto de medido. En estas
# líneas un negativo es casi siempre un descuadre. No es que no puedan serlo
# --los ingresos de una aseguradora como MFC pueden ser negativos de verdad--,
# pero dejar vacío el trimestre es la opción prudente. El beneficio operativo,
# el neto y el flujo operativo pueden ser negativos de verdad y a menudo lo son:
# no hay forma general de blindarlos, y se rellenan sin más guarda que la
# aritmética y la de que ningún trimestre conocido de su ejercicio esté roto.
_NO_NEGATIVAS = (
    "ingresos",
    "coste_de_ventas",
    "depreciacion_amortizacion",
    "gasto_por_intereses",
    "capex",
    "acciones_diluidas",
)

# Los trimestres de un ejercicio que cierra en `fin` caen entre unos 273 días
# antes y `fin`; el cuarto trimestre del ejercicio anterior, a unos 365. Tres
# trimestres largos (300 días) separan los dos casos con margen, también en los
# calendarios de 52/53 semanas.
_ANTES_DEL_CIERRE = pd.Timedelta(days=3 * _DIAS_TRIMESTRE[1])
# El cuarto trimestre cierra el mismo día que su ejercicio, pero las dos fechas
# pueden diferir unos días: una semana lo absorbe sin acercarse al primer
# trimestre del ejercicio siguiente, que cae unos 90 días después.
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


def _fecha(columna) -> pd.Timestamp:
    """La fecha de cierre de una columna, sin zona y sin hora.

    `mercado.estados` no las trae, pero una hoja con zona y otra sin ella no se
    pueden ni ordenar juntas, y la misma fecha a dos horas serían dos filas.
    """
    fecha = pd.Timestamp(columna)
    if fecha.tz is not None:
        fecha = fecha.tz_localize(None)
    return fecha.normalize()


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
            _fecha(columna)
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
        serie.index = pd.DatetimeIndex([_fecha(c) for c in serie.index])
        serie = serie[~serie.index.duplicated(keep="first")]
        lineas[linea] = serie.reindex(indice)
    lineas["capex"] = -lineas["capex"]
    return lineas.dropna(how="all")


def rejilla_trimestral(lineas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por trimestre natural, consecutivos, con el que falta en NaN.

    El que falta lleva la fecha de tres meses después del anterior: así las
    distancias entre fechas siguen siendo las de un trimestre, que es lo que
    miran `valoracion.fundamentos` y `fundamentals.panel`.

    Da por hecho que Yahoo pone cada cierre el último día de su mes. En los 37
    tickers revisados siempre es así, también en los calendarios de 52/53
    semanas: el 27 de septiembre de AAPL sale como 30 de septiembre, y el 3 de
    enero de SNA como 31 de diciembre. Con las fechas sin redondear, un cierre
    a primeros de mes caería en el trimestre natural siguiente, y la rejilla
    podría inventar una fila o descartar una real.
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
            # septiembre daría el 30 de diciembre, y del 28 de febrero el 28 de
            # mayo, que no son el cierre de nadie. Desde un fin de mes se salta
            # de fin de mes en fin de mes; desde otro día, `MonthEnd(3)` caería
            # en el mismo trimestre (del 28 de enero, al 31 de marzo).
            salto = pd.offsets.MonthEnd(3) if anterior.is_month_end else pd.DateOffset(months=3)
            fecha = anterior + salto
        fechas.append(fecha)
        anterior = fecha
    rejilla = lineas.set_axis(trimestres).reindex(todos)
    rejilla.index = pd.DatetimeIndex(fechas, name=lineas.index.name)
    return rejilla


def _de_doce_meses(anuales: pd.DataFrame) -> pd.DataFrame:
    """Los anuales que cierran un año después del anterior con dato.

    Un ejercicio de transición de seis meses no es un año, y restarle tres
    trimestres no da el que falta. «Con dato» es con ingresos o beneficio neto:
    el anual de RY trae además columnas a fechas trimestrales con sólo el BPA y
    el recuento de doce meses móviles, y si contasen como el anterior ningún
    año suyo sería un año. El primero, sin anterior, vale.
    """
    anuales = anuales.sort_index()
    con_dato = anuales[["ingresos", "beneficio_neto"]].notna().any(axis=1).to_numpy()
    validos, anterior = [], None
    for fin, tiene_dato in zip(anuales.index, con_dato):
        validos.append(anterior is None or _DIAS_ANO[0] <= (fin - anterior).days <= _DIAS_ANO[1])
        if tiene_dato:
            anterior = fin
    return anuales[validos]


def rellenar_desde_anual(trimestres: pd.DataFrame, anuales: pd.DataFrame) -> pd.DataFrame:
    """El flujo del trimestre que falta, como el año menos los otros tres.

    Es la aritmética de `fundamentals.panel._cuartos_derivados`, que reconstruye
    el cuarto trimestre que la SEC no declara suelto, llevada a cualquier
    trimestre: dentro de un ejercicio de doce meses con exactamente un trimestre
    vacío y el anual declarado, el vacío es el año menos los tres. Con dos
    vacíos no hay aritmética que valga, y se quedan vacíos.

    Sólo para flujos: un saldo de balance es una foto, y la del cierre no dice
    nada de la de septiembre. El recuento medio de acciones es una media: cuatro
    veces el anual menos los tres, y sólo si lo que sale no se aleja más del
    doble o la mitad del anual, que es la guarda de `fundamentals.panel`.

    En las líneas de `_NO_NEGATIVAS`, la resta sólo vale si los tres conocidos
    no son todos 0,0, que es lo que pone Yahoo cuando no tiene el desglose, y si
    lo que sale queda entre 0 y el total del año (el anual, o cuatro veces el
    anual en la media). Un trimestre conocido con alguna de esas líneas en
    negativo está roto, y entonces no se rellena nada de su ejercicio.
    """
    if trimestres.empty or anuales.empty:
        return trimestres
    rellenas = trimestres.copy()
    fechas = rellenas.index
    for fin, ano in _de_doce_meses(anuales).iterrows():
        dentro = (fechas > fin - _ANTES_DEL_CIERRE) & (fechas <= fin + _DESPUES_DEL_CIERRE)
        posiciones = np.flatnonzero(dentro)
        if len(posiciones) != _TRIMESTRES_POR_ANO:
            continue
        # El signo no delata sólo su línea, sino el trimestre entero: el 2T 2025
        # de GFNORTEO trae ingresos de -13.555 M y beneficio de -670 M, y el
        # beneficio del 3T, rellenado como el año menos los otros tres, salía en
        # 28.296 M, 1,8 veces el resto. De un ejercicio con un trimestre así no
        # se rellena nada, tampoco las líneas que pueden ser negativas.
        if (rellenas[list(_NO_NEGATIVAS)].iloc[posiciones] < 0).to_numpy().any():
            continue
        for linea in _FLUJOS:
            anual = ano[linea]
            if not np.isfinite(anual):
                continue
            valores = rellenas[linea].iloc[posiciones]
            vacios = valores.isna().to_numpy()
            if vacios.sum() != 1:
                continue
            conocidos = valores[~vacios]
            media = linea in _MEDIAS
            total = (_TRIMESTRES_POR_ANO if media else 1) * anual
            valor = total - conocidos.sum()
            if linea in _NO_NEGATIVAS and ((conocidos == 0).all() or not 0 < valor < total):
                continue
            if media and not (
                anual / _FACTOR_MAXIMO_MEDIA <= valor <= anual * _FACTOR_MAXIMO_MEDIA
            ):
                continue
            rellenas.iloc[posiciones[vacios][0], rellenas.columns.get_loc(linea)] = valor
    return rellenas


def lineas_de(estados: dict) -> "tuple[pd.DataFrame, pd.DataFrame]":
    """Las líneas trimestrales, en rejilla y con el hueco rellenado, y las anuales.

    `estados` es lo que devuelve `valoracion.mercado.estados`. Las trimestrales
    pasan por las mismas reconciliaciones que el panel de la SEC, en el mismo
    orden; con yfinance casi nunca tocan nada, pero dos caminos para el mismo
    dato se separan, y el que se queda atrás no da error.
    """
    anuales = lineas_desde_estados(
        estados.get("income_stmt"), estados.get("balance_sheet"), estados.get("cashflow")
    )
    trimestrales = lineas_desde_estados(
        estados.get("quarterly_income_stmt"),
        estados.get("quarterly_balance_sheet"),
        estados.get("quarterly_cashflow"),
    )
    trimestrales = rellenar_desde_anual(rejilla_trimestral(trimestrales), anuales)
    trimestrales = completar_bpa_por_identidad(reconciliar_recuento_de_acciones(trimestrales))
    return trimestrales, anuales


def kpis_trimestrales(lineas: pd.DataFrame, precios: pd.Series) -> pd.DataFrame:
    """Los diecisiete KPIs, con las funciones del panel de la SEC, y el trimestre natural.

    `lineas` viene en rejilla: los KPIs se calculan con la fila vacía en su sitio
    --es lo que mantiene el `shift(4)` en el mismo trimestre del año anterior--,
    y esa fila sale después, porque no es un trimestre medido. `precios` va
    indexado por las mismas fechas y en la moneda de los estados.
    """
    columnas = [*TODOS_LOS_KPIS, "trimestre"]
    if lineas.empty:
        return pd.DataFrame(columns=columnas)
    kpis = pd.concat(
        [compute_levels(lineas), compute_growth(lineas), compute_valuation(lineas, precios)],
        axis=1,
    ).reindex(columns=list(TODOS_LOS_KPIS))
    kpis["trimestre"] = _trimestre_natural(lineas.index)
    kpis.index.name = "periodo"
    return kpis[lineas.notna().any(axis=1).to_numpy()]


def fundamentos_anuales(anuales: pd.DataFrame, moneda: str) -> "Fundamentos | None":
    """Los ejercicios fiscales de yfinance, del más reciente al más antiguo y seguidos.

    Ejercicios completos y no un TTM trimestral: con cinco trimestres sólo cabe
    un TTM, y ponerlo delante de los anuales rompería que `ejercicios[i]` sea
    «hace i años». `estados_hasta` dice en pantalla de cuándo son.

    El ancla es la de `valoracion.fundamentos.desde_lineas`: los ingresos si
    algún año los tiene, y si no el beneficio, que es lo que declara un banco.
    El más reciente es el último año con ancla; los demás van hacia atrás, y la
    serie se corta en el primer año que no dista un año del anterior. Una fila
    sin ancla se salta en vez de cortar: el anual de RY trae columnas a fechas
    trimestrales con sólo el BPA de doce meses móviles, y cortar en ellas le
    dejaría un solo ejercicio. Un año que de verdad falta lo detecta la
    distancia al siguiente con ancla. El balance es el del cierre del más
    reciente.
    """
    if anuales.empty:
        return None
    ancla = "ingresos" if anuales["ingresos"].notna().any() else "beneficio_neto"
    elegidos: list = []
    for fecha, fila in anuales.sort_index(ascending=False).iterrows():
        if pd.isna(fila[ancla]):
            continue
        if elegidos:
            dias = (elegidos[-1][0] - fecha).days
            if not _DIAS_ANO[0] <= dias <= _DIAS_ANO[1]:
                break
        elegidos.append((fecha, fila))
    if not elegidos:
        return None
    ejercicios = tuple(
        Ejercicio(
            fin=fecha.date(),
            ingresos=_num(fila["ingresos"]),
            flujo_operativo=_num(fila["flujo_operativo"]),
            capex=_num(fila["capex"]),
            gasto_financiero=_num(fila["gasto_por_intereses"]),
            beneficio_operativo=_num(fila["beneficio_operativo"]),
            beneficio_neto=_num(fila["beneficio_neto"]),
            patrimonio_neto=_num(fila["patrimonio_neto"]),
        )
        for fecha, fila in elegidos
    )
    _, ultima = elegidos[0]
    return Fundamentos(
        moneda=moneda,
        fuente="yfinance",
        ejercicios=ejercicios,
        deuda_total=_num(ultima["deuda_total"]),
        efectivo=_num(ultima["efectivo"]),
    )
