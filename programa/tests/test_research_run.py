from research.run import END, HORIZONS, START, expected_test_count
from research.signals import SIGNALS


def test_the_grid_is_the_twenty_eight_pre_registered_tests():
    """Eight signals times four horizons. Any other number means the grid drifted."""
    assert len(SIGNALS) * len(HORIZONS) == 32
    assert expected_test_count() == 28


def test_the_four_pre_registered_horizons_are_used():
    assert HORIZONS == [1, 5, 21, 63]


def test_the_study_window_matches_the_pre_registered_criterion():
    assert START == "2010-01-01"
    assert END == "2026-06-30"
