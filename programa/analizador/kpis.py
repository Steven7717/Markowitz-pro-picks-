"""Las filas de KPIs de un ticker que no está en el panel de referencia.

Una empresa de la SEC pasa por el mismo motor que el ranking: `build_panel` con
un universo de una. Las demás salen de yfinance (`analizador.lineas_yf`), con el
precio de cada trimestre en la moneda de sus estados.
"""

import pandas as pd

from analizador.lineas_yf import kpis_trimestrales
from fundamentals.fetch import CorridaAbortada
from valoracion.mercado import SUBUNIDADES

# Privada y aun así importada: es el precio del día en que se publicaron las
# cuentas de cada trimestre, con el plazo del 10-Q o del 10-K. Una segunda
# copia aquí sería el look-ahead que el estudio D encontró siete veces.
from fundamentals.run import _precios_por_periodo, build_panel


def kpis_sec(ticker: str) -> "tuple[pd.DataFrame | None, str]":
    """Las filas del panel de la SEC de un ticker, indexadas por fecha de cierre."""
    try:
        panel, _, _ = build_panel([ticker])
    except CorridaAbortada:
        # Con un solo ticker, abortar es que la fuente no responde o rechaza la
        # identidad: no es la empresa, pero para esta ficha el efecto es el mismo.
        return None, "sin_estados"
    if panel.empty or ticker not in panel.index.get_level_values("ticker"):
        return None, "sin_estados"
    return panel.xs(ticker, level="ticker"), "ok"


def kpis_yf(
    ticker: str,
    trimestrales: pd.DataFrame,
    anuales: pd.DataFrame,
    moneda_precio: str,
    moneda_estados: str,
    tipo_a_usd: float,
) -> pd.DataFrame:
    """Los KPIs trimestrales de un ticker de yfinance.

    El precio de cada trimestre es el del día en que sus cuentas se hicieron
    públicas, con los plazos de `fundamentals.run`. Si cotiza en otra moneda
    que la de sus estados (TSM: dólares y TWD), se convierte al tipo de cambio
    de ese mismo día, que se baja con el mismo cargador: un tipo de hoy para
    precios de hace un año movería los múltiplos con la divisa, no con la
    empresa. `min_obs=1` porque con cinco trimestres la ventana de precios es
    de poco más de un año, y el mínimo del cargador la descartaría.

    Después, las líneas y el precio se pasan a dólares con **un único** tipo,
    `tipo_a_usd` (dólares por unidad de la moneda de los estados, el último
    cierre). Los suelos económicos de `fundamentals.kpis` están pensados en
    dólares --1e8 de partida de balance y 1e6 de gasto financiero--, y en wones
    el del gasto financiero valdría 745 $: una pequeña de la BMV o de KOSDAQ
    sacaría márgenes y coberturas que el panel de referencia le taparía a una
    empresa de EE. UU. de su tamaño. Un tipo constante no cambia ningún cociente
    ni ningún crecimiento; con el de cada fecha, la divisa entraría en el
    crecimiento interanual.
    """
    cierres = pd.DatetimeIndex(anuales.index)
    precios, _ = _precios_por_periodo(ticker, trimestrales.index, cierres, min_obs=1)
    # Una cotización en subunidades (Londres, en peniques) se cambia con su
    # moneda principal y se divide por la escala: yfinance pasa el par a
    # mayúsculas, y «GBpUSD=X» sería el tipo de la libra, cien veces mayor.
    base, escala = SUBUNIDADES.get(moneda_precio, (moneda_precio, 1))
    if base != moneda_estados:
        par = f"{base}{moneda_estados}=X"
        tipos, _ = _precios_por_periodo(par, trimestrales.index, cierres, min_obs=1)
        precios = precios * tipos
    dinero = [linea for linea in trimestrales.columns if linea != "acciones_diluidas"]
    en_dolares = trimestrales.copy()
    en_dolares[dinero] = en_dolares[dinero] * tipo_a_usd
    return kpis_trimestrales(en_dolares, precios / escala * tipo_a_usd)
