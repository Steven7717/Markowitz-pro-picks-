from collections.abc import Callable

import numpy as np
import pandas as pd

from research.indicators import bollinger_position, macd_histogram, rolling_max, rsi, sma

RANDOM_CONTROL_SEED = 20260805
TOP_QUINTILE = 0.8


def _as_of(frame: pd.DataFrame) -> pd.DataFrame:
    """Align a computed value to the first date it could have been acted on.

    Everything in this module funnels through here. A value computed from data
    through the close of t-1 is dated t, which is the date an order could first
    be placed. Every signal shifts exactly once, and only here.
    """
    return frame.shift(1)


# ── F1: momentum de medio plazo ───────────────────────────────────────────────

def mom_12_1(panel: pd.DataFrame) -> pd.DataFrame:
    """Return from t-252 to t-21. The most documented price-based signal there is.

    Skipping the most recent month is the convention: it is contaminated by the
    short-term reversal effect that rev_1m isolates.
    """
    close = panel["Close"]
    return _as_of(close.shift(21) / close.shift(252) - 1.0)


# ── F2: reversión de corto plazo ──────────────────────────────────────────────

def rev_1m(panel: pd.DataFrame) -> pd.DataFrame:
    """Last month's return, negated: recent losers score high."""
    close = panel["Close"]
    return _as_of(-(close.pct_change(21, fill_method=None)))


# ── F3: timing de entrada ─────────────────────────────────────────────────────

def rsi_14(panel: pd.DataFrame) -> pd.DataFrame:
    """RSI negated, so oversold reads as a high score like every other signal."""
    return _as_of(-rsi(panel["Close"], window=14))


def macd_cross(panel: pd.DataFrame) -> pd.DataFrame:
    return _as_of(macd_histogram(panel["Close"]))


def dist_sma200(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["Close"]
    average = sma(close, window=200)
    return _as_of((close - average) / average)


def breakout_52w(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["Close"]
    return _as_of(close / rolling_max(close, window=252))


def bollinger_pos(panel: pd.DataFrame) -> pd.DataFrame:
    """Band position negated, so touching the lower band reads as a high score."""
    return _as_of(-bollinger_position(panel["Close"], window=20, n_std=2.0))


# ── Control negativo ──────────────────────────────────────────────────────────

def random_control(panel: pd.DataFrame) -> pd.DataFrame:
    """Noise with the shape of a signal. Must fail the criterion.

    Drawn row by row from a fixed seed, so truncating the history leaves every
    surviving value untouched — which is what lets the control sit inside the
    same truncation test as the real signals.
    """
    close = panel["Close"]
    rng = np.random.default_rng(RANDOM_CONTROL_SEED)
    values = rng.uniform(size=(len(close.index), len(close.columns)))
    return _as_of(pd.DataFrame(values, index=close.index, columns=close.columns))


# ── Fixture de test, nunca usado por el estudio ───────────────────────────────

def oracle_signal(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """The forward return itself. Peeks on purpose.

    Not part of SIGNALS: its only job is to prove the evaluation machinery can
    detect future information when it is genuinely there. An IC near zero for
    this signal means the measurement is broken, not that markets are efficient.
    """
    close = panel["Close"]
    return close.shift(-horizon) / close - 1.0


# ── Registros ─────────────────────────────────────────────────────────────────

SIGNALS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "mom_12_1": mom_12_1,
    "rev_1m": rev_1m,
    "rsi_14": rsi_14,
    "macd_cross": macd_cross,
    "dist_sma200": dist_sma200,
    "breakout_52w": breakout_52w,
    "bollinger_pos": bollinger_pos,
    "random_control": random_control,
}

FAMILIES: dict[str, str] = {
    "mom_12_1": "F1 Momentum medio plazo",
    "rev_1m": "F2 Reversión corto plazo",
    "rsi_14": "F3 Timing de entrada",
    "macd_cross": "F3 Timing de entrada",
    "dist_sma200": "F3 Timing de entrada",
    "breakout_52w": "F3 Timing de entrada",
    "bollinger_pos": "F3 Timing de entrada",
    "random_control": "Control negativo",
}


def _top_quintile_trigger(name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Continuous signals have no natural threshold, so the cross-section supplies one."""

    def trigger(panel: pd.DataFrame) -> pd.DataFrame:
        values = SIGNALS[name](panel)
        return (values.rank(axis=1, pct=True) >= TOP_QUINTILE).astype(bool)

    return trigger


def _rsi_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    return (_as_of(rsi(panel["Close"], window=14)) < 30.0).astype(bool)


def _macd_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    """The crossing itself, not the level: negative yesterday, positive today."""
    histogram = _as_of(macd_histogram(panel["Close"]))
    return ((histogram > 0.0) & (histogram.shift(1) <= 0.0)).astype(bool)


def _sma200_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    close = _as_of(panel["Close"])
    average = _as_of(sma(panel["Close"], window=200))
    above = close > average
    return (above & ~above.shift(1, fill_value=False)).astype(bool)


def _breakout_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    """Today's close exceeds the highest close of the previous 252 days."""
    close = _as_of(panel["Close"])
    prior_high = _as_of(rolling_max(panel["Close"].shift(1), window=252))
    return (close > prior_high).astype(bool)


def _bollinger_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    position = _as_of(bollinger_position(panel["Close"], window=20, n_std=2.0))
    return (position <= -1.0).astype(bool)


TRIGGERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "mom_12_1": _top_quintile_trigger("mom_12_1"),
    "rev_1m": _top_quintile_trigger("rev_1m"),
    "rsi_14": _rsi_trigger,
    "macd_cross": _macd_trigger,
    "dist_sma200": _sma200_trigger,
    "breakout_52w": _breakout_trigger,
    "bollinger_pos": _bollinger_trigger,
    "random_control": _top_quintile_trigger("random_control"),
}
