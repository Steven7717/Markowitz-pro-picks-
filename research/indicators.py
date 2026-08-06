"""Technical indicators, implemented natively.

Written in-house rather than pulled from a library so the shift discipline is
visible in one place: none of these functions shifts anything. Aligning a value
to the date it may be acted on is signals.py's job, and splitting that
responsibility across a dependency is how look-ahead sneaks in.
"""

import numpy as np
import pandas as pd


def _wilder_smooth(values: pd.DataFrame, window: int) -> pd.DataFrame:
    """Wilder's smoothing, seeded with the simple mean of the first full window.

    The seed matters more than it looks. Running ewm(adjust=False) straight from
    the first observation instead starts the recursion from a single data point,
    which on real price series lands up to 16 RSI points away from Wilder's
    definition and takes ~244 observations to converge — roughly the first year
    of this study, and a large enough error to flip an oversold trigger.
    """
    if len(values) <= window:
        return values * np.nan
    seeded = values.copy()
    seeded.iloc[:window] = np.nan
    seeded.iloc[window] = values.iloc[1 : window + 1].mean()
    return seeded.ewm(alpha=1.0 / window, adjust=False).mean()


def rsi(close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Wilder's RSI. 100 when every period gained, 0 when every period lost."""
    delta = close.diff()
    avg_gain = _wilder_smooth(delta.clip(lower=0.0), window)
    avg_loss = _wilder_smooth((-delta).clip(lower=0.0), window)

    both_flat = (avg_gain == 0.0) & (avg_loss == 0.0)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    values = 100.0 - 100.0 / (1.0 + rs)
    values = values.where(~(avg_loss == 0.0), 100.0)
    return values.where(~both_flat, 50.0)


def macd_histogram(
    close: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD line minus its signal line. Positive means the fast trend leads."""
    macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    return macd - macd.ewm(span=signal, adjust=False).mean()


def sma(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close.rolling(window).mean()


def rolling_max(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close.rolling(window).max()


def bollinger_position(
    close: pd.DataFrame, window: int = 20, n_std: float = 2.0
) -> pd.DataFrame:
    """Where the price sits inside its band: -1 is the lower band, +1 the upper.

    Undefined while the price is perfectly flat, because a band of zero width
    has no inside.
    """
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    width = n_std * std
    return (close - mean) / width.replace(0.0, np.nan)
