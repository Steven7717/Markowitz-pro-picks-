"""Which XBRL concepts stand for which financial line.

Filers do not agree on tags: Apple reports revenue as
RevenueFromContractWithCustomerExcludingAssessedTax, Coca-Cola as Revenues, and
a bank splits it into interest and non-interest income. Each line is therefore an
ordered chain of candidates rather than a single name.

The chains below were measured, not guessed: every concept here was observed in
a 20-company sample spanning technology, banks, insurers, REITs, energy,
healthcare, consumer and utilities.
"""
import numpy as np
import pandas as pd

# Ordered fallback chains. The first concept carrying data *in each quarter* wins.
#
# Deliberately absent: IncomeLossFromContinuingOperationsBeforeIncomeTaxes... as
# a fallback for operating income. It appears in 17 of 20 companies against 13
# for OperatingIncomeLoss, so it would raise coverage — but it is measured after
# interest, which would make interest coverage a ratio of the wrong quantity. A
# declared gap beats a plausible wrong number.
LINEAS: dict[str, tuple[str, ...]] = {
    "ingresos": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        # Banks report no single revenue line; this is the closest equivalent.
        "InterestAndDividendIncomeOperating",
    ),
    "coste_de_ventas": (
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfServices",
    ),
    "beneficio_operativo": ("OperatingIncomeLoss",),
    "beneficio_neto": (
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ),
    "bpa_diluido": (
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
    ),
    "depreciacion_amortizacion": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        # 76 filers tag depreciation and amortisation separately instead of
        # combined. Adding them is exact arithmetic; taking either alone would
        # understate the EBITDA add-back, so both must be present.
        ("Depreciation", "AmortizationOfIntangibleAssets"),
    ),
    "gasto_por_intereses": (
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "InterestExpenseOperating",
        "InterestAndDebtExpense",
    ),
    "activos_totales": ("Assets",),
    "activos_corrientes": ("AssetsCurrent",),
    "pasivos_corrientes": ("LiabilitiesCurrent",),
    "patrimonio_neto": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "deuda_total": (
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ),
    "efectivo": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "flujo_operativo": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireRealEstate",
    ),
    "acciones_diluidas": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
}

# Conceptos cuyo acumulado del año hasta la fecha NO es la suma de sus
# trimestres sino la media ponderada de ellos. La distinción gobierna cómo
# `fundamentals.panel` recupera el trimestre que la empresa no declara suelto:
# una media se descumula multiplicando, un flujo restando. Contrastado sobre las
# 502 cachés, comparando cada estimador con el trimestre que la empresa sí llegó
# a declarar: para el recuento de acciones la resta simple se equivoca con un
# error mediano del 100% y la fórmula de la media acierta con un 0,03%; para los
# ingresos y el BPA es al revés.
#
# Va aquí y no en `panel.py` porque es semántica de la etiqueta XBRL, que es de
# lo que trata este módulo, y porque quien añada un concepto nuevo a las cadenas
# de arriba tiene que decidirlo en el mismo sitio donde lo añade.
MEDIAS_PONDERADAS: frozenset[str] = frozenset(
    {
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    }
)


def _aplanar(entrada: str | tuple[str, ...]) -> tuple[str, ...]:
    return (entrada,) if isinstance(entrada, str) else entrada


CONCEPTOS = {
    concepto
    for cadena in LINEAS.values()
    for entrada in cadena
    for concepto in _aplanar(entrada)
}


def resolve_lines(panel: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Map a concept panel onto the fixed set of line items the KPIs need.

    `panel` is indexed by period end with one column per XBRL concept, as
    fundamentals.panel.quarterly_panel returns it.

    La cadena se resuelve **trimestre a trimestre**, no una vez para todo el
    panel. Un concepto gana en las filas donde trae dato, y las que deja vacías
    las intenta el siguiente de la cadena. Fijarla una sola vez era el defecto:
    bastaba con que el concepto preferido tuviese dato en cualquier parte de los
    doce trimestres para que ganara entero, así que una empresa que cambió de
    etiqueta a mitad de la ventana quedaba sin línea justo en los cuatro
    trimestres que puntúan. CPRT dejó de etiquetar StockholdersEquity tras su
    ejercicio 2023 y pasó a la variante que incluye a los minoritarios; el motor
    no la veía y perdía ROE, ROIC y precio/valor en libros. Medido sobre las 502
    empresas de la caché: 233 tenían alguna línea vacía en la ventana de cuatro
    trimestres teniendo dato un concepto posterior de su cadena.

    El orden de la cadena sigue mandando: fila a fila no significa «el que más
    datos tenga», significa «el primero que tenga dato en esta fila».

    A chain entry may be a tuple of concepts, which is used only when every one
    of them carries data and is then summed. That covers filers who split a line
    the standard tag combines; a partial sum would understate the total, so a
    tuple with any member missing is skipped rather than added up — ahora
    también por filas, porque un trimestre al que le falta la mitad de
    amortización no puede invalidar los otros tres.

    The result always has one column per line in LINEAS, even for lines this
    filer never reports — a panel whose columns depend on the company cannot be
    concatenated across a universe. Returns the frame and the names of the lines
    no concept satisfied.
    """
    lineas = pd.DataFrame(
        float("nan"), index=panel.index, columns=list(LINEAS), dtype="float64"
    )
    ausentes: list[str] = []

    for linea, cadena in LINEAS.items():
        columna = pd.Series(float("nan"), index=panel.index, dtype="float64")
        for entrada in cadena:
            partes = _aplanar(entrada)
            if not all(c in panel.columns for c in partes):
                continue
            # La suma propaga el NaN: si a un trimestre le falta una de las
            # partes, esa fila queda vacía y la intenta el siguiente de la
            # cadena, que es exactamente la regla de la tupla llevada a la fila.
            valores = sum(pd.to_numeric(panel[c], errors="coerce") for c in partes)
            columna = columna.where(columna.notna(), valores)
        lineas[linea] = columna
        if not columna.notna().any():
            ausentes.append(linea)

    return lineas, ausentes


# El BPA se declara al céntimo. Por debajo de eso el cociente de la identidad es
# ruido dividido por redondeo, y podría fabricar un factor de mil de la nada.
_MIN_BPA = 0.01

# La escala de un hecho mal declarado siempre es una potencia de mil: miles,
# millones o miles de millones. Un cociente que no cae cerca de una de ellas no
# es un problema de escala, es otra cosa — y reescalar por 1,2 sería inventarse
# un dato en vez de corregir uno.
#
# La tolerancia es del 30% y no del 10% que tuvo antes. Con el ±10% la banda era
# el único juez, y se equivocaba en las dos direcciones a la vez: ECHO declaró
# 271.245 acciones en 2023-09-30 —el mismo error de mil que en sus otros cuatro
# trimestres— con un cociente implícito de 858,3, un 14,2% por debajo del 1000, y
# se quedó sin corregir; el trimestre siguiente, con 988,7, sí se corrigió. El
# cociente arrastra el ruido de la propia identidad (beneficio del grupo contra
# BPA del común, minoritarios, preferentes), que en las 502 cachés llega al
# 20-30% sin que nada esté mal. Lo que decide ahora no es la banda sino la serie
# de la empresa: ver `reconciliar_recuento_de_acciones`.
_BASE_ESCALA = 1000.0
_TOLERANCIA_ESCALA = 0.3

# Cuánto puede alejarse el recuento de un trimestre de la base de la empresa sin
# dejar de ser la misma base. Un recuento diluido se mueve unos puntos por
# trimestre —recompras, emisión de opciones—, así que tres años de deriva sana
# caben de sobra dentro de 1,5x; un split, un contrasplit o una fusión lo mueven
# por factores de 2, 5, 10 o 24, que es lo que esta guarda está para separar.
#
# El 1,5 está medido por los dos lados. Por arriba: es lo que hace falta para
# dejar fuera los dos casos que más ensucian —el Q4 derivado de NFLX, con 8,2e9
# acciones a 1,93x de su base, y el de NOW a 1,82x—. Por abajo: BG saltó de
# 135,6 a 198,5 millones de acciones al absorber a Viterra, o sea 1,46x, y ése es
# un aumento **real** de capital, no un cambio de base — el precio no se reajusta
# por una fusión, así que sus trimestres anteriores casan perfectamente con su
# precio y sus múltiplos salen bien (PER 7,7-10,6, precio/valor en libros
# 0,99-1,48). Un corte más fino se habría comido nueve trimestres correctos de
# BG. Tras reconciliar las 502 cachés, el cociente de cada celda contra la base
# de su empresa tiene un p99,9 de 1,36 y un máximo de 1,51: el umbral queda justo
# por encima de la cola real.
#
# Es el precio de no tener calendario de splits: una fusión que multiplique el
# capital por más de 1,5 se tratará como un cambio de base y sus trimestres
# viejos perderán la capitalización aunque fuera correcta. El error cae del lado
# seguro —un hueco visible en vez de un múltiplo falso— y afecta a trimestres
# anteriores a la operación, que casi nunca están en la ventana que puntúa.
_FACTOR_BASE = 1.5

# Cuándo la identidad está rota más allá de cualquier duda. No sirve el ±30% de
# la escala: ahí caben los REITs y los emisores con minoritarios, cuya identidad
# se desvía por motivos contables legítimos. Un factor de diez no cabe por nada
# legítimo, y es donde aparecen los hechos mal escalados como el BPA de HAL
# —790000,0 en un hecho cuya unidad dice "USD per share"—.
_FACTOR_IDENTIDAD_ROTA = 10.0

# Cuánto puede desviarse la identidad en los trimestres que la empresa SÍ declara
# para que se le permita rellenar los que no. Ver `completar_bpa_por_identidad`.
_MAX_ERROR_IDENTIDAD = 0.10


def _implicitas(lineas: pd.DataFrame) -> pd.Series:
    """Las acciones que la identidad contable pide: beneficio entre BPA diluido.

    Es la única medida del recuento que no depende de en qué escala venga
    declarado el recuento, y por eso es con la que se le contrasta.
    """
    beneficio = pd.to_numeric(lineas["beneficio_neto"], errors="coerce")
    bpa = pd.to_numeric(lineas["bpa_diluido"], errors="coerce")
    implicitas = beneficio / bpa.where(bpa.abs() >= _MIN_BPA)
    return implicitas.where(implicitas > 0)


def _escala_corregida(acciones: pd.Series, implicitas: pd.Series) -> pd.Series:
    """El recuento devuelto a su escala real cuando venía en miles o millones.

    **Sólo multiplica.** El exponente se recorta en cero a propósito, y es el
    arreglo de la regresión que motivó esta ronda: la identidad
    `beneficio ÷ BPA = acciones` tiene dos incógnitas y el código anterior le
    echaba la culpa siempre a las acciones. HAL declaró 902.000.000 acciones
    —correctas— junto a un BPA diluido de 790000,0, que es el hecho de la SEC mal
    escalado; el cociente salía 1,0e-6, el factor 1e-6, y el recuento acababa en
    902 acciones, con lo que el precio/valor en libros de HAL pasaba de 1,70 a
    0,00. Una escala mal declarada escribe el número **más pequeño** de lo que es
    —717,6 por 717.600.000, 271.245 por 271.245.000—, nunca más grande, así que
    una corrección que divide no está corrigiendo nada: está destruyendo el único
    de los dos datos que estaba bien.

    Un recuento absurdamente grande existe —WAT declaró 5,971e10 acciones contra
    una base de 5,97e7— y esta función deliberadamente no lo toca. De él se
    encarga la guarda de base de `reconciliar_recuento_de_acciones`, que lo
    declara ausente en vez de repararlo: sin poder dividir no hay reparación
    posible, y un hueco declarado es preferible a un número plausible y falso.
    """
    cociente = implicitas / acciones.where(acciones > 0)
    exponente = (np.log(cociente) / np.log(_BASE_ESCALA)).round()
    # `clip(lower=0)` es la guarda: el exponente negativo se convierte en 0, o
    # sea en "no tocar", en vez de en una división.
    exponente = exponente.clip(lower=0)
    factor = _BASE_ESCALA**exponente
    aplicable = (exponente > 0) & ((cociente / factor - 1).abs() <= _TOLERANCIA_ESCALA)
    return acciones.where(~aplicable.fillna(False), acciones * factor)


def _base_de_la_empresa(escaladas: pd.Series, identidad_ok: pd.Series) -> float:
    """El recuento que sirve de referencia para toda la serie de esta empresa.

    Se ancla en el trimestre **más reciente** cuya identidad cuadra, no en la
    mediana de la serie, y el motivo es el precio. `research.loader` descarga con
    `auto_adjust=True`, o sea que ajusta los precios hacia atrás por cada split
    hasta dejarlos todos en la base **de hoy**. Los recuentos XBRL, en cambio,
    vienen tal como se declararon, y una empresa que hizo un split a mitad de la
    ventana tiene sus trimestres viejos en la base vieja: BKNG tiene ocho
    trimestres a 33 millones de acciones y cuatro a 800, y los que casan con el
    precio ajustado son los cuatro nuevos, no los ocho viejos. Una mediana
    elegiría la mayoría, que aquí es precisamente la base equivocada.

    El ancla no es una fila suelta sino la mediana de las que coinciden con ella
    dentro de `_FACTOR_BASE`: una sola fila sería un punto único de fallo, y la
    identidad ya ha descartado como ancla las filas que no cuadran —el Q4
    derivado de NFLX, con 8,2e9 acciones y un BPA de -17,14, no cuadra—.

    Sin ninguna fila con la identidad cuadrada no hay a qué anclarse y se recurre
    a la mediana: es peor referencia, pero sigue siendo mejor que ninguna, y las
    empresas que llegan aquí son las que no declaran BPA, donde el recuento
    tampoco se ha podido corregir de escala.
    """
    candidatas = escaladas.where(escaladas > 0).dropna()
    if candidatas.empty:
        return float("nan")

    ancladas = candidatas[identidad_ok.reindex(candidatas.index).fillna(False)]
    if ancladas.empty:
        return float(candidatas.median())

    ultima = float(ancladas.iloc[-1])
    acordes = candidatas[candidatas.between(ultima / _FACTOR_BASE, ultima * _FACTOR_BASE)]
    return float(acordes.median())


def reconciliar_recuento_de_acciones(lineas: pd.DataFrame) -> pd.DataFrame:
    """Deja el recuento de acciones y el BPA en una base que se pueda multiplicar por el precio.

    Hace tres cosas, en este orden, y cada una tiene su propio defecto detrás:

    **1. Devuelve el recuento a su escala.** McDonald's etiqueta sus acciones
    **en millones**: `numeric_value` 717,6 con `unit` "shares", o sea 717,6
    acciones en vez de 717.600.000. La capitalización sale multiplicada por 1e-6
    y con ella los doce trimestres de precio/FCF (0,000076 · 0,000102 ·
    0,000089…) y de precio/valor en libros. La unidad del hecho no lo delata
    —pone "shares" igual que todo el mundo— pero la identidad contable sí: el BPA
    diluido es, por definición, el beneficio entre las acciones diluidas. Se
    decide fila a fila porque MCD cambió de escala a mitad de la serie
    (731.600.000 un trimestre y 725,9 el siguiente). La corrección **sólo
    multiplica**: ver `_escala_corregida`.

    **2. Declara ausente el recuento que no está en la base de la empresa.** La
    guarda anterior comparaba el trimestre derivado contra el acumulado del
    propio informe, que es la cifra de la que sale, así que medía la aritmética
    contra sí misma y lo peor que podía pasar era un factor de dos en la
    capitalización. Sobrevivían 44 celdas absurdas en 17 empresas, doce de ellas
    dentro de la ventana que puntúa: BKNG con 794.000.000 acciones contra una
    base de 33 millones —22,7x—, NFLX con 8.222.965.000 —3,5x—, NOW con 3,0x,
    TPL con 2,5x. Contrastar contra la serie de la propia empresa es más barato
    y más certero. Lo que no está en la base no se repara —no es una potencia de
    mil, así que no hay reparación posible— sino que se declara ausente.

    **3. Declara ausente el BPA que no se puede casar con el precio.** Son dos
    casos distintos y los dos acaban en el mismo sitio:

    - El trimestre cuya base es desconocida arrastra su BPA con él. Un BPA
      anterior a un split está en la misma base que su recuento y el precio no:
      el TTM suma dos bases y sale un PER que no es de nadie. Es lo que le daba a
      Booking Holdings un PER de 1,17 —el único por debajo de 3 de todo el
      panel— siendo una empresa que cotiza a ~25x.
    - El trimestre cuya base está bien y cuya identidad no cuadra por un factor
      de diez o más: ahí el que miente es el BPA, y se sabe porque la serie le da
      la razón al recuento. HAL declaró un BPA diluido de 790000,0 para
      2023-09-30 —el real fue 0,79 $— en un hecho cuya unidad dice "USD per
      share"; su caché trae además el mismo trimestre de 2024 declarado dos
      veces, una con 680000,0 y otra con 0,68.

    Lo que **no** hace: inventarse el factor de un split. Sin calendario de
    splits —que no viaja ni en la caché de hechos ni en la de precios— no se
    puede distinguir un split de 2x de una fusión que emite el doble de acciones,
    y restaurar la base a ojo pondría una capitalización inventada donde ahora
    hay un hueco. El hueco se ve en la cobertura del pilar de valoración; la
    capitalización inventada no se vería en ninguna parte.

    Lo que tampoco hace: tocar a quien no declara recuento. Dieciséis empresas
    —Visa, Berkshire, Hershey, KKR…— no etiquetan `WeightedAverageNumberOf...`,
    y sin recuento no hay base que contrastar ni motivo para quitarles el BPA.
    """
    if lineas.empty:
        return lineas

    necesarias = ("acciones_diluidas", "beneficio_neto", "bpa_diluido")
    if not all(c in lineas.columns for c in necesarias):
        return lineas

    acciones = pd.to_numeric(lineas["acciones_diluidas"], errors="coerce")
    bpa = pd.to_numeric(lineas["bpa_diluido"], errors="coerce")
    implicitas = _implicitas(lineas)

    escaladas = _escala_corregida(acciones, implicitas)

    # Tras la corrección de escala, la identidad o cuadra o no cuadra. Cuadrar
    # es lo que convierte a una fila en ancla creíble de la base.
    razon = implicitas / escaladas.where(escaladas > 0)
    identidad_ok = razon.between(1 / _FACTOR_BASE, _FACTOR_BASE).fillna(False)

    base = _base_de_la_empresa(escaladas, identidad_ok)
    if np.isnan(base) or base <= 0:
        coherente = escaladas.notna()
    else:
        coherente = escaladas.between(base / _FACTOR_BASE, base * _FACTOR_BASE)
    coherente = coherente.fillna(False)

    # "Tiene recuento y no está en la base": el `notna` es lo que impide que las
    # empresas sin recuento declarado caigan en esta rama y pierdan el BPA.
    base_desconocida = escaladas.notna() & ~coherente
    identidad_rota = razon.notna() & (
        (razon > _FACTOR_IDENTIDAD_ROTA) | (razon < 1 / _FACTOR_IDENTIDAD_ROTA)
    )

    reconciliadas = lineas.copy()
    reconciliadas["acciones_diluidas"] = escaladas.where(coherente)
    reconciliadas["bpa_diluido"] = bpa.where(~(base_desconocida | identidad_rota))
    return reconciliadas


def completar_bpa_por_identidad(lineas: pd.DataFrame) -> pd.DataFrame:
    """Rellena el BPA que la empresa no declaró, desde beneficio entre acciones.

    Existe por lo que el TTM le hace a un hueco. `fundamentals.kpis._ttm` exige
    los cuatro trimestres, y con razón —sumar los que haya subestimaría el
    denominador y dispararía el múltiplo—, pero eso convierte un hueco en cuatro:
    ninguna ventana de cuatro que lo contenga tiene múltiplo. A una empresa cuyo
    hueco cae un trimestre por año no le queda **ninguna** ventana limpia. El BPA
    de HAL está vacío en 2023-12-31, 2024-12-31 y 2025-12-31 —un Q4 cada año,
    porque su 10-K no trae una ventana de doce meses de BPA y `_cuartos_derivados`
    no tiene de dónde restar— y su PER pasó de 8 trimestres con dato a 0. Son 31
    empresas con al menos un hueco y 23 con tres o más.

    Se rellena desde la identidad y no reescalando el TTM de tres trimestres a
    cuatro. Medido sobre las 502 cachés, dropeando un trimestre de cada ventana
    completa y comparando: reescalar tres cuartos a un año se equivoca con un
    error mediano del 6,3% y un p90 del 43,9% en el BPA, y del 12,8% y el 63,4%
    en el flujo libre — o sea que el p90 de esa vía es un PER inventado de arriba
    abajo. La identidad, contrastada contra los 5.720 trimestres donde la empresa
    declara las tres cifras, se equivoca con un error mediano del **0,30%** y un
    p90 del 4,9%. Es veinte veces mejor porque no extrapola: mide el mismo
    trimestre con dos cifras del mismo informe.

    El p99 de la identidad sí es malo —un 58%— y son los emisores con
    minoritarios o preferentes, donde el beneficio neto no es el del común. Por
    eso no se rellena a ciegas: sólo a la empresa que ya ha enseñado, en los
    trimestres que sí declara, que la identidad la describe dentro del 10%. Eso
    deja fuera a las dieciséis que no declaran BPA en ningún trimestre —Monster,
    Visa, General Dynamics…—, que es lo correcto: fabricarles un PER sería
    publicar un múltiplo que la empresa no publica y que nada ha contrastado.

    Va después de `reconciliar_recuento_de_acciones` y no antes: rellenar con un
    recuento en la escala equivocada o en una base que no es la del precio sería
    sembrar el hueco con el mismo defecto que la reconciliación acaba de quitar.
    """
    if lineas.empty:
        return lineas

    necesarias = ("acciones_diluidas", "beneficio_neto", "bpa_diluido")
    if not all(c in lineas.columns for c in necesarias):
        return lineas

    acciones = pd.to_numeric(lineas["acciones_diluidas"], errors="coerce")
    beneficio = pd.to_numeric(lineas["beneficio_neto"], errors="coerce")
    bpa = pd.to_numeric(lineas["bpa_diluido"], errors="coerce")

    estimado = beneficio / acciones.where(acciones > 0)

    declarados = bpa.abs() >= _MIN_BPA
    contrastables = declarados & estimado.notna()
    if not contrastables.any():
        return lineas

    error = (estimado[contrastables] / bpa[contrastables] - 1).abs()
    # La mediana y no el máximo: un solo trimestre con un cargo a minoritarios no
    # descalifica a una empresa cuya identidad cuadra el resto del tiempo.
    if not np.isfinite(error.median()) or error.median() > _MAX_ERROR_IDENTIDAD:
        return lineas

    completadas = lineas.copy()
    completadas["bpa_diluido"] = bpa.where(bpa.notna(), estimado)
    return completadas
