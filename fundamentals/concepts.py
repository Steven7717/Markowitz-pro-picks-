"""Which XBRL concepts stand for which financial line.

Filers do not agree on tags: Apple reports revenue as
RevenueFromContractWithCustomerExcludingAssessedTax, Coca-Cola as Revenues, and
a bank splits it into interest and non-interest income. Each line is therefore an
ordered chain of candidates rather than a single name.

The chains below were measured, not guessed: every concept here was observed in
a 20-company sample spanning technology, banks, insurers, REITs, energy,
healthcare, consumer and utilities.
"""
import pandas as pd

# Ordered fallback chains. The first concept carrying any data in the panel wins.
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

    A concept wins only if it carries data *within this panel*, not merely if the
    company ever reported it: JPMorgan stopped tagging quarterly Revenues in
    2014, so for a recent window that column exists and is entirely empty.

    A chain entry may be a tuple of concepts, which is used only when every one
    of them carries data and is then summed. That covers filers who split a line
    the standard tag combines; a partial sum would understate the total, so a
    tuple with any member missing is skipped rather than added up.

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
        for entrada in cadena:
            partes = _aplanar(entrada)
            if not all(
                c in panel.columns and panel[c].notna().any() for c in partes
            ):
                continue
            valores = sum(pd.to_numeric(panel[c], errors="coerce") for c in partes)
            lineas[linea] = valores
            break
        else:
            ausentes.append(linea)

    return lineas, ausentes
