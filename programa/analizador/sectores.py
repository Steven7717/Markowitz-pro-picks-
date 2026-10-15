"""El sector GICS de un ticker, para compararlo con sus pares del S&P 500.

A una empresa del S&P 500 se le saca de la tabla congelada de siempre
(`fundamentals/data/sectores_2026-08-10.csv`): es con la que está hecho el
panel de referencia. A cualquier otra, del `info["sector"]` de Yahoo, que no usa
los nombres GICS y se traduce con esta tabla, también congelada. Un sector que
no esté aquí se queda sin pares, y se dice, en vez de adivinarse.
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

    `tabla` se inyecta para las pruebas; por defecto es la del S&P 500.
    """
    tabla = load_sectors() if tabla is None else tabla
    if tabla.get(ticker):
        return tabla[ticker], "sp500"
    gics = YAHOO_A_GICS.get(sector_yahoo or "")
    return (gics, "yahoo") if gics else (None, "sin_sector")
