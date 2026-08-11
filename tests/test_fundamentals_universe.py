import pytest

from fundamentals.universe import resolve


def test_sp500_delegates_to_the_frozen_snapshot():
    from research.universe import sp500_members

    assert resolve("sp500") == sp500_members()


def test_an_explicit_list_is_returned_normalised():
    assert resolve(["aapl", " msft ", "brk.b"]) == ["AAPL", "MSFT", "BRK-B"]


def test_duplicates_are_removed_keeping_first_appearance():
    """Un ticker repetido se descargaria dos veces y contaria doble en la cobertura."""
    assert resolve(["AAPL", "MSFT", "AAPL"]) == ["AAPL", "MSFT"]


def test_an_empty_list_is_rejected():
    with pytest.raises(ValueError, match="vacío"):
        resolve([])


def test_an_unknown_source_name_is_rejected():
    with pytest.raises(ValueError, match="desconocido"):
        resolve("russell2000")
