"""Walk-forward validation of the optimised portfolio.

The Sharpe ratio the optimiser reports is measured on the very data it was fitted
to, so it is an upper bound rather than an expectation. This module re-runs the
whole procedure through time — fit on a training window, hold the resulting
weights through the following window without touching them, repeat — and measures
the Sharpe actually achieved on data the optimiser never saw.
"""

import numpy as np
import pandas as pd

from optimizer import optimize_portfolio


def default_window_sizes(periods_per_year: int) -> tuple[int, int]:
    """Train on roughly two years, hold for roughly one quarter."""
    train = max(2, 2 * periods_per_year)
    test = max(1, periods_per_year // 4)
    return train, test


def _resolve_windows(
    periods_per_year: int,
    n_obs: int,
    train_size: int | None,
    test_size: int | None,
) -> tuple[int, int]:
    """Pick window sizes that actually fit the history available.

    The daily horizons fetch as little as one year of data, which cannot host a
    two-year training window. Rather than silently skipping validation there, the
    windows shrink proportionally — fewer windows, but a real out-of-sample number.
    """
    if train_size is not None and test_size is not None:
        return train_size, test_size

    train, test = default_window_sizes(periods_per_year)
    if train + test <= n_obs:
        return train_size or train, test_size or test

    train = max(2, int(n_obs * 0.6))
    test = max(1, (n_obs - train) // 4)
    return train_size or train, test_size or test


def sharpe_standard_error(
    sharpe: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    """How precisely a Sharpe ratio can be measured from this much data.

    Standard error of an annualised Sharpe estimate, sqrt((1 + S^2/2) / years).
    Short walk-forward runs measure the Sharpe so imprecisely that comparing two
    strategies is meaningless — one year of data carries an error bar wider than
    the entire difference the comparison is looking for.

    Reference: Lo (2002), "The Statistics of Sharpe Ratios", Financial Analysts
    Journal 58(4).
    """
    years = n_periods / periods_per_year
    if years <= 0:
        return float("inf")
    return float(np.sqrt((1.0 + sharpe**2 / 2.0) / years))


def _annualised_sharpe(
    period_returns: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> float:
    vol = period_returns.std(ddof=1) * np.sqrt(periods_per_year)
    if vol <= 0:
        return 0.0
    excess = (period_returns.mean() - rf_rate) * periods_per_year
    return float(excess / vol)


def walk_forward_validation(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    strategy: str = "max_sharpe",
    train_size: int | None = None,
    test_size: int | None = None,
) -> dict | None:
    """Return out-of-sample performance, or None if history is too short.

    Weights are frozen for the whole holding window — no look-ahead, and no
    rebalancing that the in-sample figure would not have paid for.
    """
    n_obs, n_assets = returns.shape

    # Below a year of history there is not enough independent data for the
    # out-of-sample figure to mean anything, whatever the window sizes.
    if n_obs < periods_per_year:
        return None

    train_size, test_size = _resolve_windows(periods_per_year, n_obs, train_size, test_size)
    if n_obs < train_size + test_size:
        return None

    equal_weights = np.ones(n_assets) / n_assets
    in_sample_sharpes: list[float] = []
    oos_chunks: list[np.ndarray] = []
    benchmark_chunks: list[np.ndarray] = []

    start = 0
    while start + train_size + test_size <= n_obs:
        train = returns.iloc[start:start + train_size]
        test = returns.iloc[start + train_size:start + train_size + test_size]

        fitted = optimize_portfolio(
            train, rf_rate, periods_per_year, weight_bounds, allow_short,
            strategy=strategy, shrinkage=shrinkage,
        )
        if fitted["converged"]:
            in_sample_sharpes.append(fitted["sharpe"])
            oos_chunks.append(test.values @ fitted["weights"])
            benchmark_chunks.append(test.values @ equal_weights)

        start += test_size

    if not oos_chunks:
        return None

    oos = np.concatenate(oos_chunks)
    benchmark = np.concatenate(benchmark_chunks)

    in_sample = float(np.mean(in_sample_sharpes))
    out_of_sample = _annualised_sharpe(oos, rf_rate, periods_per_year)
    equal_weight = _annualised_sharpe(benchmark, rf_rate, periods_per_year)

    # Only call a winner when the gap is bigger than the error bar on measuring
    # it. Otherwise the honest answer is "this data cannot tell them apart".
    stderr = sharpe_standard_error(out_of_sample, int(oos.size), periods_per_year)
    gap = out_of_sample - equal_weight
    beats_equal_weight = bool(gap > 0) if abs(gap) > stderr else None

    return {
        "n_windows": len(oos_chunks),
        "n_oos_periods": int(oos.size),
        "in_sample_sharpe": in_sample,
        "out_of_sample_sharpe": out_of_sample,
        "equal_weight_sharpe": equal_weight,
        "sharpe_stderr": stderr,
        "beats_equal_weight": beats_equal_weight,
        "oos_return": float(oos.mean() * periods_per_year),
        "oos_vol": float(oos.std(ddof=1) * np.sqrt(periods_per_year)),
        "degradation": in_sample - out_of_sample,
        "train_size": train_size,
        "test_size": test_size,
    }
