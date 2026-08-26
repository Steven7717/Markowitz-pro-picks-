import numpy as np
import pandas as pd
import pytest

from research.timing import GateBResult, block_bootstrap_stderr, compare_entry_timing

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


@pytest.fixture
def panel() -> pd.DataFrame:
    tickers = [f"T{i}" for i in range(40)]
    dates = pd.bdate_range("2015-01-01", periods=1200)
    rng = np.random.default_rng(53)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, size=(len(dates), len(tickers))), axis=0))
    frames = {
        "Open": closes * 0.999,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Close": closes,
        "Volume": np.full_like(closes, 1e6),
    }
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    return pd.DataFrame(np.hstack([frames[f] for f in FIELDS]), index=dates, columns=columns)


def _always(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(True, index=panel.index, columns=panel["Close"].columns)


def _never(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(False, index=panel.index, columns=panel["Close"].columns)


def test_returns_a_result_with_both_arms(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=1)
    assert isinstance(result, GateBResult)
    assert np.isfinite(result.sharpe_immediate)
    assert np.isfinite(result.sharpe_signal)


def test_a_trigger_that_never_fires_still_enters_at_the_end_of_the_window(panel):
    """Without the forced entry, non-firing cases would vanish and bias the comparison."""
    result = compare_entry_timing("never", _never, panel, n_dates=40, seed=1)
    assert result.n_forced == result.n_entries


def test_a_trigger_that_always_fires_forces_nothing(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=1)
    assert result.n_forced == 0


def test_the_same_seed_reproduces_the_same_numbers(panel):
    first = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    second = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    assert first.delta == pytest.approx(second.delta)
    assert first.stderr == pytest.approx(second.stderr)


def test_different_seeds_give_different_samples(panel):
    first = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    second = compare_entry_timing("always", _always, panel, n_dates=40, seed=99)
    assert first.sharpe_immediate != second.sharpe_immediate


def test_a_trigger_that_fires_at_once_is_indistinguishable_from_entering_immediately(panel):
    """Waiting for a signal that says 'now' is the same action as not waiting.

    Any non-zero delta here would be a lag the measurement invented rather than
    a property of the signal.
    """
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    assert result.delta == pytest.approx(0.0)


def test_delta_is_the_gap_between_the_two_arms(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=3)
    assert result.delta == pytest.approx(result.sharpe_signal - result.sharpe_immediate)


def test_both_arms_hold_for_the_same_number_of_days(panel):
    """A longer exposure would beat a shorter one on drift alone, not on timing."""
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=3, hold_days=63)
    assert result.hold_days == 63


def test_a_delta_smaller_than_its_own_noise_does_not_pass():
    """An improvement inside the error bars is not an improvement."""
    result = GateBResult("s", 0.50, 0.55, 0.05, 0.30, 100, 0, 63)
    assert result.passes is False


def test_a_delta_larger_than_its_own_noise_passes():
    result = GateBResult("s", 0.50, 1.00, 0.50, 0.20, 100, 0, 63)
    assert result.passes is True


def test_passing_is_decided_solely_by_delta_against_stderr(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=60, seed=5)
    assert result.passes == (result.delta > result.stderr)


# ── Bootstrap por bloques ─────────────────────────────────────────────────────

def test_block_bootstrap_returns_a_positive_standard_error():
    rng = np.random.default_rng(61)
    assert block_bootstrap_stderr(rng.normal(0, 1, 300), block=8, n_resamples=200, seed=1) > 0.0


def test_block_bootstrap_shrinks_as_the_sample_grows():
    rng = np.random.default_rng(67)
    small = block_bootstrap_stderr(rng.normal(0, 1, 100), block=8, n_resamples=300, seed=1)
    large = block_bootstrap_stderr(rng.normal(0, 1, 2000), block=8, n_resamples=300, seed=1)
    assert large < small


def test_block_bootstrap_reports_more_uncertainty_than_an_iid_estimate_when_data_overlap():
    """Overlapping observations carry less information than their count suggests."""
    rng = np.random.default_rng(71)
    overlapping = pd.Series(rng.normal(0, 1, 2000)).rolling(20).mean().dropna().to_numpy()
    iid_stderr = overlapping.std(ddof=1) / np.sqrt(len(overlapping))
    assert block_bootstrap_stderr(overlapping, block=20, n_resamples=400, seed=1) > iid_stderr
