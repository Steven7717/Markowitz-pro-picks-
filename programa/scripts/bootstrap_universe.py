"""Generate the frozen S&P 500 membership snapshot. Run once, commit the output.

The study must reproduce exactly across runs, so the universe is never queried
live. Refreshing it is a deliberate, reviewed change to a committed file.
"""
import os
import sys
from pathlib import Path

import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Al refrescar el snapshot, actualiza también _SNAPSHOT en research/universe.py
OUTPUT = Path(__file__).resolve().parent.parent / "research" / "data" / "sp500_members_2026-08-05.csv"

# Wikipedia rejects requests carrying urllib's default User-Agent (HTTP 403).
# This identifies the client per the Wikimedia User-Agent policy; it does not
# change what is fetched or from where.
#
# The contact is read from the environment rather than hard-coded, so nobody's
# personal address ends up in a committed file. Wikimedia asks for a real
# contact on high-volume use; this script fetches a single page, by hand, once.
# Set BOOTSTRAP_CONTACT before running if you want to identify yourself:
#     BOOTSTRAP_CONTACT="tu@correo.com" python scripts/bootstrap_universe.py
_CONTACT = os.environ.get("BOOTSTRAP_CONTACT", "sin contacto declarado")
_HEADERS = {"User-Agent": f"markowitz-pro-picks-research/1.0 ({_CONTACT})"}


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
