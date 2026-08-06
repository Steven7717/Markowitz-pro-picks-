"""Generate the frozen S&P 500 membership snapshot. Run once, commit the output.

The study must reproduce exactly across runs, so the universe is never queried
live. Refreshing it is a deliberate, reviewed change to a committed file.
"""
import sys
from pathlib import Path

import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT = Path(__file__).resolve().parent.parent / "research" / "data" / "sp500_members_2026-08-05.csv"

# Wikipedia rejects requests carrying urllib's default User-Agent (HTTP 403).
# This identifies the client per the Wikimedia User-Agent policy; it does not
# change what is fetched or from where.
_HEADERS = {"User-Agent": "markowitz-pro-picks-research/1.0 (esteban.110203@gmail.com)"}


def normalise(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def main() -> int:
    tables = pd.read_html(WIKIPEDIA_URL, storage_options=_HEADERS)
    constituents = tables[0]
    tickers = sorted({normalise(s) for s in constituents["Symbol"]})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": tickers}).to_csv(OUTPUT, index=False)
    print(f"Escritos {len(tickers)} tickers en {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
