"""Generate the frozen ticker -> GICS sector table. Run once, commit the output.

Sector membership must not change between two runs of the engine, so this is a
committed file rather than a live lookup, exactly like the universe snapshot.

Deliberately does NOT touch research/data/sp500_members_2026-08-05.csv: study D
reproduces against that exact membership, and regenerating it today would change
which companies it contains.
"""
import os
import sys
from pathlib import Path

import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Al refrescar la tabla, actualiza también _TABLA en fundamentals/sectors.py
OUTPUT = Path(__file__).resolve().parent.parent / "fundamentals" / "data" / "sectores_2026-08-10.csv"

# Same User-Agent policy as scripts/bootstrap_universe.py: Wikipedia rejects
# urllib's default with HTTP 403, and the contact comes from the environment so
# nobody's personal address lands in a committed file.
_CONTACT = os.environ.get("BOOTSTRAP_CONTACT", "sin contacto declarado")
_HEADERS = {"User-Agent": f"markowitz-pro-picks-research/1.0 ({_CONTACT})"}

MIN_POR_SECTOR = 10


def normalise(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def main() -> int:
    constituents = pd.read_html(WIKIPEDIA_URL, storage_options=_HEADERS)[0]
    tabla = (
        pd.DataFrame(
            {
                "ticker": [normalise(s) for s in constituents["Symbol"]],
                "sector_gics": constituents["GICS Sector"].str.strip(),
            }
        )
        .sort_values("ticker")
        .drop_duplicates("ticker")
    )

    grupos = tabla["sector_gics"].value_counts()
    if grupos.min() < MIN_POR_SECTOR:
        print(
            f"AVISO: el sector mas pequeno tiene {grupos.min()} empresas. "
            "Un z-score sectorial contra un grupo pequeno no informa nada.",
            file=sys.stderr,
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(OUTPUT, index=False)
    print(f"Escritos {len(tabla)} tickers en {OUTPUT}")
    print(f"Sectores: {len(grupos)} | menor: {grupos.min()} | mayor: {grupos.max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
