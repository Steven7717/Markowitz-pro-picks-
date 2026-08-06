import numpy as np
import pandas as pd
import pytest

from research.indicators import (
    bollinger_position,
    macd_histogram,
    rolling_max,
    rsi,
    sma,
)


def _frame(values: list[float], name: str = "AAA") -> pd.DataFrame:
    return pd.DataFrame({name: values}, index=pd.bdate_range("2020-01-01", periods=len(values)))


@pytest.fixture
def ramp() -> pd.DataFrame:
    """A strictly increasing series: every period is a gain, none is a loss."""
    return _frame(list(np.linspace(10.0, 110.0, 300)))


@pytest.fixture
def flat() -> pd.DataFrame:
    return _frame([50.0] * 300)


# ── RSI ───────────────────────────────────────────────────────────────────────

def test_rsi_of_a_strictly_rising_series_is_one_hundred(ramp):
    """With no down periods the average loss is zero, which pins RSI at its ceiling."""
    assert rsi(ramp, window=14).iloc[-1].item() == pytest.approx(100.0)


def test_rsi_of_a_strictly_falling_series_is_zero(ramp):
    falling = ramp.iloc[::-1].reset_index(drop=True)
    falling.index = pd.bdate_range("2020-01-01", periods=len(falling))
    assert rsi(falling, window=14).iloc[-1].item() == pytest.approx(0.0)


def test_rsi_of_a_flat_series_is_neutral(flat):
    """No gains and no losses is not a signal in either direction."""
    assert rsi(flat, window=14).iloc[-1].item() == pytest.approx(50.0)


def test_rsi_stays_inside_its_bounds():
    rng = np.random.default_rng(5)
    noisy = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 300))))
    values = rsi(noisy, window=14).dropna()
    assert values.min().item() >= 0.0
    assert values.max().item() <= 100.0


def test_rsi_needs_a_full_window_before_reporting(ramp):
    assert rsi(ramp, window=14).iloc[:14].isna().all().item()


def test_the_first_rsi_value_uses_wilders_simple_average_seed():
    """Seeding the recursion off a single delta instead of the first full window
    lands tens of RSI points away from Wilder's definition — 43 in the worst
    case measured — and stays wrong for ~240 observations, enough to flip an
    oversold trigger through the study's opening year. This pins the seed
    without depending on the optional reference library below.
    """
    rng = np.random.default_rng(23)
    frame = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 60))))
    window = 14

    delta = frame["AAA"].diff()
    seed_gain = delta.clip(lower=0.0).iloc[1 : window + 1].mean()
    seed_loss = (-delta).clip(lower=0.0).iloc[1 : window + 1].mean()
    expected = 100.0 - 100.0 / (1.0 + seed_gain / seed_loss)

    assert rsi(frame, window=window).iloc[window].item() == pytest.approx(expected)


# ── MACD ──────────────────────────────────────────────────────────────────────

def test_macd_histogram_of_a_rising_series_is_positive(ramp):
    assert macd_histogram(ramp).iloc[-1].item() > 0.0


def test_macd_histogram_of_a_flat_series_is_zero(flat):
    assert macd_histogram(flat).iloc[-1].item() == pytest.approx(0.0, abs=1e-9)


# ── SMA y máximo móvil ────────────────────────────────────────────────────────

def test_sma_of_a_flat_series_equals_the_level(flat):
    assert sma(flat, window=200).iloc[-1].item() == pytest.approx(50.0)


def test_sma_of_a_linear_ramp_equals_the_window_midpoint(ramp):
    window = 20
    expected = ramp.iloc[-window:].mean().item()
    assert sma(ramp, window=window).iloc[-1].item() == pytest.approx(expected)


def test_rolling_max_of_a_rising_series_is_the_latest_value(ramp):
    assert rolling_max(ramp, window=252).iloc[-1].item() == pytest.approx(ramp.iloc[-1].item())


def test_rolling_max_never_falls_below_the_current_price():
    rng = np.random.default_rng(9)
    noisy = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 400))))
    highs = rolling_max(noisy, window=252).dropna()
    assert (highs >= noisy.loc[highs.index]).all().item()


# ── Bollinger ─────────────────────────────────────────────────────────────────

def test_bollinger_position_is_zero_at_the_moving_average():
    values = [50.0] * 40 + [50.0]
    frame = _frame(values)
    assert bollinger_position(frame, window=20, n_std=2.0).iloc[-1].isna().item()


def test_bollinger_position_is_positive_above_the_average():
    rng = np.random.default_rng(11)
    values = list(100.0 + rng.normal(0, 1, 60)) + [130.0]
    assert bollinger_position(_frame(values), window=20, n_std=2.0).iloc[-1].item() > 0.0


def test_bollinger_position_is_negative_below_the_average():
    rng = np.random.default_rng(11)
    values = list(100.0 + rng.normal(0, 1, 60)) + [70.0]
    assert bollinger_position(_frame(values), window=20, n_std=2.0).iloc[-1].item() < 0.0


def test_bollinger_position_of_one_means_the_upper_band():
    rng = np.random.default_rng(13)
    frame = _frame(list(100.0 + rng.normal(0, 2, 100)))
    window, n_std = 20, 2.0
    mean = frame.rolling(window).mean()
    std = frame.rolling(window).std(ddof=0)
    at_upper = mean + n_std * std
    position = (at_upper - mean) / (n_std * std)
    assert position.dropna().iloc[-1].item() == pytest.approx(1.0)


# ── Referencia cruzada opcional ───────────────────────────────────────────────

def test_rsi_matches_a_reference_implementation():
    """Same pattern the repo already uses to check Ledoit-Wolf against scikit-learn."""
    ta = pytest.importorskip("pandas_ta_classic")
    rng = np.random.default_rng(17)
    series = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, 500)))
    ours = rsi(series.to_frame("AAA"), window=14)["AAA"].dropna()
    theirs = ta.rsi(series, length=14).dropna()
    common = ours.index.intersection(theirs.index)
    assert np.allclose(ours.loc[common], theirs.loc[common], atol=1e-6)
