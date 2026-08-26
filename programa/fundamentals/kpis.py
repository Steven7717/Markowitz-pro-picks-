import pandas as pd

from fundamentals.concepts import LINEAS

# Below this, a denominator is noise and the quotient is an artefact rather than
# a measurement. Study D shipped a guard that only caught exact zeros and
# returned t = 3.6e16 for a near-constant series; the defect was invisible on
# the page and only showed up when the code was run.
_MIN_DENOMINADOR = 1e-6

_TRIMESTRES_POR_ANO = 4

KPIS_NIVEL = (
    "margen_bruto",
    "margen_operativo",
    "margen_neto",
    "roe",
    "roic",
    "deuda_neta_ebitda",
    "cobertura_intereses",
    "razon_corriente",
    "margen_fcf",
    "fcf_sobre_beneficio",
)

KPIS_CRECIMIENTO = (
    "crecimiento_ingresos",
    "crecimiento_bpa",
    "crecimiento_fcf",
)

KPIS_VALORACION = (
    "per",
    "ev_ebitda",
    "precio_fcf",
    "precio_valor_libro",
)

TODOS_LOS_KPIS = KPIS_NIVEL + KPIS_CRECIMIENTO + KPIS_VALORACION


def _div(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """Divide, yielding NaN where the denominator is too small to mean anything.

    NaN rather than 0 or inf on purpose: a 0 reads as a real measurement of zero
    and an inf reads as an extraordinary company. Both are lies about a division
    that could not be performed.
    """
    num = pd.to_numeric(numerador, errors="coerce")
    den = pd.to_numeric(denominador, errors="coerce")
    return num / den.where(den.abs() >= _MIN_DENOMINADOR)


def _solo_positivo(serie: pd.Series) -> pd.Series:
    """Mask non-positive denominators for multiples.

    A P/E of -2 does not mean cheaper than 10, and a negative EV/EBITDA does not
    rank against a positive one. Leaving them in would corrupt any sort.
    """
    valores = pd.to_numeric(serie, errors="coerce")
    return valores.where(valores > _MIN_DENOMINADOR)


def _empty(columnas: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columnas), dtype="float64")


def _lineas(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.reindex(columns=list(LINEAS))


def compute_levels(lineas: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time KPIs: no KPI here needs a previous quarter."""
    if lineas.empty:
        return _empty(KPIS_NIVEL)

    l = _lineas(lineas)
    ebitda = l["beneficio_operativo"] + l["depreciacion_amortizacion"]
    deuda_neta = l["deuda_total"] - l["efectivo"]
    fcf = l["flujo_operativo"] - l["capex"]
    capital_invertido = l["patrimonio_neto"] + l["deuda_total"] - l["efectivo"]

    return pd.DataFrame(
        {
            "margen_bruto": _div(l["ingresos"] - l["coste_de_ventas"], l["ingresos"]),
            "margen_operativo": _div(l["beneficio_operativo"], l["ingresos"]),
            "margen_neto": _div(l["beneficio_neto"], l["ingresos"]),
            "roe": _div(l["beneficio_neto"], l["patrimonio_neto"]),
            "roic": _div(l["beneficio_neto"], capital_invertido),
            "deuda_neta_ebitda": _div(deuda_neta, ebitda),
            "cobertura_intereses": _div(l["beneficio_operativo"], l["gasto_por_intereses"]),
            "razon_corriente": _div(l["activos_corrientes"], l["pasivos_corrientes"]),
            "margen_fcf": _div(fcf, l["ingresos"]),
            "fcf_sobre_beneficio": _div(fcf, l["beneficio_neto"]),
        },
        index=lineas.index,
    )


def _yoy(serie: pd.Series) -> pd.Series:
    """Year-on-year change against the same quarter last year.

    Compares four quarters back rather than one because a retailer's Q4 beats
    its Q3 every year: quarter-on-quarter measures seasonality, not growth.

    A base at or below zero yields NaN. Growth from zero is not infinite, and
    from a negative base the ratio flips sign and reports a collapse as a gain.
    """
    base = serie.shift(_TRIMESTRES_POR_ANO)
    return (serie - base) / base.where(base > _MIN_DENOMINADOR)


def compute_growth(lineas: pd.DataFrame) -> pd.DataFrame:
    """Growth KPIs. Assumes rows are consecutive quarters, oldest first.

    quarterly_panel() sorts by period end and derives the fourth quarter the
    10-K leaves out, so shift(4) lands on the same quarter of the previous year
    rather than sliding when a filing is missing.
    """
    if lineas.empty:
        return _empty(KPIS_CRECIMIENTO)

    l = _lineas(lineas)
    fcf = l["flujo_operativo"] - l["capex"]

    return pd.DataFrame(
        {
            "crecimiento_ingresos": _yoy(l["ingresos"]),
            "crecimiento_bpa": _yoy(l["bpa_diluido"]),
            "crecimiento_fcf": _yoy(fcf),
        },
        index=lineas.index,
    )


def compute_valuation(lineas: pd.DataFrame, precios: pd.Series) -> pd.DataFrame:
    """Market multiples, priced at the date each quarter's results became public.

    `precios` is indexed by the same periods as `lineas`. Quarters with no price
    yield missing multiples rather than borrowing today's price: pairing a
    current price with three-year-old fundamentals invents a multiple that never
    traded.
    """
    if lineas.empty:
        return _empty(KPIS_VALORACION)

    l = _lineas(lineas)
    precio = pd.to_numeric(precios, errors="coerce").reindex(lineas.index)

    acciones = _solo_positivo(l["acciones_diluidas"])
    capitalizacion = precio * acciones
    ebitda = l["beneficio_operativo"] + l["depreciacion_amortizacion"]
    valor_empresa = capitalizacion + l["deuda_total"] - l["efectivo"]
    fcf = l["flujo_operativo"] - l["capex"]

    return pd.DataFrame(
        {
            "per": _div(precio, _solo_positivo(l["bpa_diluido"])),
            "ev_ebitda": _div(valor_empresa, _solo_positivo(ebitda)),
            "precio_fcf": _div(capitalizacion, _solo_positivo(fcf)),
            "precio_valor_libro": _div(capitalizacion, _solo_positivo(l["patrimonio_neto"])),
        },
        index=lineas.index,
    )
