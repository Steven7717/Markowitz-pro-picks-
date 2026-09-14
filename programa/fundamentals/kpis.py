import pandas as pd

from fundamentals.concepts import LINEAS

# Below this, a denominator is noise and the quotient is an artefact rather than
# a measurement. Study D shipped a guard that only caught exact zeros and
# returned t = 3.6e16 for a near-constant series; the defect was invisible on
# the page and only showed up when the code was run.
_MIN_DENOMINADOR = 1e-6

# Un mínimo **económico**, no numérico, y por eso va aparte de `_MIN_DENOMINADOR`.
# Las partidas de este motor van en dólares crudos, así que la guarda numérica
# la atraviesan mil dólares de gasto financiero: ODFL declaró unos 2.000 en un
# trimestre y salió con una cobertura de intereses de 169.027 veces, contra un
# p99 de 493 en todo el panel — y puntuó con ella. Por debajo de un millón de
# dólares al trimestre, una empresa no tiene una cobertura altísima: no tiene
# coste financiero que cubrir, y el cociente mide redondeo en vez de solvencia.
_MIN_GASTO_FINANCIERO = 1e6

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


def _ttm(serie: pd.Series) -> pd.Series:
    """Los últimos doce meses de un flujo: cuatro trimestres sumados.

    Ni `fundamentals/`, ni `ranking/`, ni `medidores.py` contenían «TTM», «doce
    meses» ni «anualizado», y los múltiplos se calculaban contra la magnitud de
    **un** trimestre. El resultado era una mediana del universo de 7,24x en
    deuda neta / EBITDA contra el 1,5-2,0x real del S&P 500, 58,0x en EV/EBITDA
    contra 13-15x y 81,3x en precio/FCF contra 25-30x. `medidores.py` rotulaba
    ese 7,24 como «Deuda neta / EBITDA» y escribía «7,2×»: el usuario leía una
    empresa mediana como siete veces apalancada cuando está por debajo de dos.

    Con doce meses, las mismas medianas quedan en 1,80x, 15,9x y 23,1x, que es
    el orden de magnitud que esos nombres significan fuera de este programa.

    `min_periods` exige los cuatro trimestres. Sumar los que haya subestimaría
    el denominador y dispararía el múltiplo justo en las empresas con menos
    historia, que es donde menos se puede permitir un número inventado; los tres
    primeros trimestres de un panel se quedan por tanto sin múltiplo de flujo.

    Asume, como `compute_growth`, que las filas son trimestres consecutivos del
    más antiguo al más reciente, que es como los entrega `quarterly_panel`.
    """
    return (
        pd.to_numeric(serie, errors="coerce")
        .rolling(_TRIMESTRES_POR_ANO, min_periods=_TRIMESTRES_POR_ANO)
        .sum()
    )


def _empty(columnas: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columnas), dtype="float64")


def _lineas(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.reindex(columns=list(LINEAS))


def compute_levels(lineas: pd.DataFrame) -> pd.DataFrame:
    """Level KPIs, ninguno de los cuales compara contra el mismo trimestre del año pasado.

    Casi todos son cocientes de dos magnitudes del mismo periodo —un margen, una
    razón corriente— y por eso siguen siendo trimestrales: el periodo se cancela
    y el número no promete un año que no cubre.

    La excepción es `deuda_neta_ebitda`, que divide un saldo de balance entre un
    flujo, así que el flujo tiene que ser de doce meses o el múltiplo sale
    multiplicado por cuatro. Ver `_ttm`.

    `roe` y `roic` son el mismo caso —flujo entre saldo— y siguen siendo
    trimestrales a propósito: pasarlos a doce meses movería los números del
    pilar de calidad, que es una decisión del dueño y no un arreglo de
    integridad. Mientras no la tome, `medidores.py` los rotula «ROE trimestral»
    y «ROIC trimestral», que es lo que impide que un 5% trimestral se lea como
    un 5% anual.
    """
    if lineas.empty:
        return _empty(KPIS_NIVEL)

    l = _lineas(lineas)
    ebitda_ttm = _ttm(l["beneficio_operativo"] + l["depreciacion_amortizacion"])
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
            # El EBITDA va por `_solo_positivo` y no por `_div` a secas: con un
            # EBITDA negativo el cociente sale negativo y el signo -1 del
            # criterio lo premia como si fuese caja neta. Eran 398 de 2.934
            # celdas negativas donde colapsaban las dos cosas opuestas. Lo que
            # sí es caja neta —deuda menor que el efectivo con EBITDA positivo—
            # sigue saliendo negativo, y ahí el signo acierta.
            "deuda_neta_ebitda": _div(deuda_neta, _solo_positivo(ebitda_ttm)),
            "cobertura_intereses": _div(
                l["beneficio_operativo"],
                l["gasto_por_intereses"].where(
                    l["gasto_por_intereses"] >= _MIN_GASTO_FINANCIERO
                ),
            ),
            "razon_corriente": _div(l["activos_corrientes"], l["pasivos_corrientes"]),
            "margen_fcf": _div(fcf, l["ingresos"]),
            # Con beneficio negativo el cociente cambia de signo y miente al
            # revés: quien quema caja perdiendo dinero sale con conversión
            # positiva. Es el mismo motivo por el que `_yoy` no crece desde una
            # base negativa. El rango iba de -624,50 a +652,83.
            "fcf_sobre_beneficio": _div(fcf, _solo_positivo(l["beneficio_neto"])),
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

    Los denominadores de flujo —BPA, EBITDA, flujo libre— van en doce meses
    móviles; los de balance —patrimonio, deuda, efectivo— son instantáneas y
    entran tal cual. Un múltiplo contra el flujo de un solo trimestre es cuatro
    veces el múltiplo que todo el mundo llama PER o EV/EBITDA: ver `_ttm`.

    Pasar a doce meses además arregla un sesgo que no se veía: `_solo_positivo`
    descarta el trimestre con BPA o FCF negativo, así que con el múltiplo
    trimestral quien perdía dinero un trimestre se puntuaba sólo por sus tres
    buenos. Sobre doce meses, el trimestre malo entra en la cuenta.
    """
    if lineas.empty:
        return _empty(KPIS_VALORACION)

    l = _lineas(lineas)
    precio = pd.to_numeric(precios, errors="coerce").reindex(lineas.index)

    acciones = _solo_positivo(l["acciones_diluidas"])
    capitalizacion = precio * acciones
    ebitda_ttm = _ttm(l["beneficio_operativo"] + l["depreciacion_amortizacion"])
    valor_empresa = capitalizacion + l["deuda_total"] - l["efectivo"]
    fcf_ttm = _ttm(l["flujo_operativo"] - l["capex"])

    return pd.DataFrame(
        {
            "per": _div(precio, _solo_positivo(_ttm(l["bpa_diluido"]))),
            # El numerador también: `_solo_positivo` protegía el denominador y
            # dejaba pasar un valor de empresa negativo. LUV salía con -116,18 y
            # CSGP con -46,00, y con el signo -1 del criterio un -116 es la
            # empresa más barata de su sector. El docstring de `_solo_positivo`
            # ya decía que un EV/EBITDA negativo no ordena contra uno positivo:
            # la guarda estaba en el lado equivocado del cociente.
            "ev_ebitda": _div(_solo_positivo(valor_empresa), _solo_positivo(ebitda_ttm)),
            "precio_fcf": _div(capitalizacion, _solo_positivo(fcf_ttm)),
            "precio_valor_libro": _div(capitalizacion, _solo_positivo(l["patrimonio_neto"])),
        },
        index=lineas.index,
    )
