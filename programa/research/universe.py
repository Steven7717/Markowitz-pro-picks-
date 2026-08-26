from pathlib import Path

import pandas as pd

# Al refrescar el snapshot, actualiza también OUTPUT en scripts/bootstrap_universe.py
_SNAPSHOT = Path(__file__).parent / "data" / "sp500_members_2026-08-05.csv"


def normalise_ticker(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def sp500_members(snapshot: Path | None = None) -> list[str]:
    """Read the frozen membership snapshot from disk.

    Never queries the network. Two runs of the study must evaluate the same
    universe, so membership is a committed file, not a live lookup.
    """
    frame = pd.read_csv(snapshot or _SNAPSHOT)
    return [normalise_ticker(s) for s in frame["ticker"]]
