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
_BASE_ESCALA = 1000.0
_TOLERANCIA_ESCALA = 0.1


def corregir_escala_de_acciones(lineas: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el recuento de acciones a su escala real cuando está en miles o millones.

    McDonald's etiqueta sus acciones **en millones**: `numeric_value` 717,6 con
    `unit` "shares" para el trimestre de septiembre de 2025, o sea 717,6
    acciones en vez de 717.600.000. La capitalización sale multiplicada por
    1e-6 y con ella los doce trimestres de precio/FCF (0,000076 · 0,000102 ·
    0,000089…) y de precio/valor en libros. La unidad del hecho no lo delata —
    pone "shares" igual que todo el mundo — pero la identidad contable sí: el
    BPA diluido es, por definición, el beneficio entre las acciones diluidas.

    Se decide **fila a fila**: McDonald's cambió de escala a mitad de la serie
    (731.600.000 un trimestre y 725,9 el siguiente), así que una corrección por
    empresa se comería la mitad buena. Contrastado sobre las 502 cachés, el
    cociente `beneficio / BPA / acciones` cae dentro de ±10% del 1 en 482 de las
    491 empresas donde se puede calcular; las nueve restantes son REITs y
    emisores con minoritarios, cuyo desvío es del 20-30% y por tanto no dispara
    nada. Sólo MCD sale con un factor de mil.

    Fuera de esas condiciones el número se deja como está: sin beneficio, sin
    BPA o con un cociente que no es potencia de mil, no hay con qué contrastar,
    y cambiar la cifra a ciegas sería peor que dejarla.
    """
    if lineas.empty:
        return lineas

    necesarias = ("acciones_diluidas", "beneficio_neto", "bpa_diluido")
    if not all(c in lineas.columns for c in necesarias):
        return lineas

    acciones = pd.to_numeric(lineas["acciones_diluidas"], errors="coerce")
    beneficio = pd.to_numeric(lineas["beneficio_neto"], errors="coerce")
    bpa = pd.to_numeric(lineas["bpa_diluido"], errors="coerce")

    implicitas = beneficio / bpa.where(bpa.abs() >= _MIN_BPA)
    cociente = implicitas.where(implicitas > 0) / acciones.where(acciones > 0)

    exponente = np.log(cociente) / np.log(_BASE_ESCALA)
    entero = exponente.round()
    factor = _BASE_ESCALA**entero
    aplicable = (entero != 0) & ((cociente / factor - 1).abs() <= _TOLERANCIA_ESCALA)

    corregidas = lineas.copy()
    corregidas["acciones_diluidas"] = acciones.where(~aplicable.fillna(False), acciones * factor)
    return corregidas
