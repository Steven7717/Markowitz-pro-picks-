from pathlib import Path

import pandas as pd
import pytest

from research.universe import normalise_ticker, sp500_members


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    path = tmp_path / "members.csv"
    pd.DataFrame({"ticker": ["aapl", "brk-b", "msft"]}).to_csv(path, index=False)
    return path


def test_reads_the_tickers_from_the_snapshot_file(snapshot):
    assert sp500_members(snapshot) == ["AAPL", "BRK-B", "MSFT"]


def test_uppercases_whatever_the_file_contains(snapshot):
    assert all(t == t.upper() for t in sp500_members(snapshot))


def test_the_committed_snapshot_has_a_plausible_number_of_members():
    members = sp500_members()
    assert 480 <= len(members) <= 520


def test_the_committed_snapshot_has_no_duplicates():
    members = sp500_members()
    assert len(members) == len(set(members))


def test_the_committed_snapshot_uses_yahoo_share_class_syntax():
    """Yahoo writes BRK.B as BRK-B; a dot silently returns an empty price series."""
    assert not any("." in ticker for ticker in sp500_members())


def test_share_classes_are_normalised_to_hyphens():
    assert normalise_ticker("brk.b") == "BRK-B"
