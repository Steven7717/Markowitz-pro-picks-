"""El sector GICS de un ticker, para compararlo con sus pares del S&P 500.

A una empresa del S&P 500 se le saca de la tabla congelada de siempre
(`fundamentals/data/sectores_2026-08-10.csv`): es con la que está hecho el
panel de referencia. A cualquier otra, del `info["sector"]` de Yahoo, que no usa
los nombres GICS y se traduce con esta tabla, también congelada. Un sector que
no esté aquí se queda sin pares, y se dice, en vez de adivinarse.

La traducción no es sólo un cambio de nombre: Yahoo clasifica con Morningstar, y
en una muestra de 119 empresas del S&P 500, 5 (un 4 %) caen en otro sector --los
envases SW, AVY y AMCR salen Consumer Cyclical en Yahoo y son Materials en
GICS--. Por eso se mira primero la tabla del S&P 500, y ése es el error que cabe
esperar en las empresas de fuera.
"""

from fundamentals.sectors import load_sectors

YAHOO_A_GICS = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
}


def sector_gics(
    ticker: str, sector_yahoo: "str | None", tabla: "dict | None" = None
) -> "tuple[str | None, str]":
    """El sector GICS y de dónde salió: `"sp500"`, `"yahoo"` o `"sin_sector"`.

    `ticker` llega ya normalizado (`resolver.normalizar`) y se busca tal cual. A
    propósito no se le quita el sufijo de bolsa: `ALL.AX` es Aristocrat Leisure y
    `ALL` es Allstate.

    `tabla` se inyecta para las pruebas y para cargarla una sola vez cuando se
    analizan varios tickers; por defecto es la del S&P 500.
    """
    tabla = load_sectors() if tabla is None else tabla
    sector = tabla.get(ticker)
    # pandas lee la celda vacía como NaN, que es verdadero: sólo vale un texto no vacío.
    if isinstance(sector, str) and sector:
        return sector, "sp500"
    gics = YAHOO_A_GICS.get(sector_yahoo or "")
    return (gics, "yahoo") if gics else (None, "sin_sector")
