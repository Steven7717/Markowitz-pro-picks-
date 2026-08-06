from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

N_DATES = 500
BASKET_SIZE = 20
WAIT_DAYS = 10
HOLD_DAYS = 63
N_RESAMPLES = 1000
BOOTSTRAP_BLOCK = 8
SEED = 20260805


@dataclass(frozen=True)
class GateBResult:
    signal: str
    sharpe_immediate: float
    sharpe_signal: float
    delta: float
    stderr: float
    n_entries: int
    n_forced: int
    hold_days: int

    @property
    def passes(self) -> bool:
        return self.delta > self.stderr


def block_bootstrap_stderr(
    values: np.ndarray, block: int, n_resamples: int = N_RESAMPLES, seed: int = SEED
) -> float:
    """Standard error of the mean under a moving-block bootstrap.

    Resampling individual observations would assume independence the data does
    not have: baskets sampled days apart share most of their holding period.
    Resampling contiguous blocks preserves that dependence.

    Deliberately not validation.sharpe_standard_error: that implements Lo (2002)
    for an unpaired Sharpe level under an independence assumption this data does
    not satisfy. What Gate B needs is the uncertainty of the paired difference
    between two arms measured on the same dates, where the shared market move
    cancels — a different statistic, not a stricter version of the same one.
    """
    x = np.asarray(values, dtype=float)
    n = x.size
    if n < 2:
        return float("inf")
    block = max(1, min(block, n))
    n_blocks = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(n_resamples, n_blocks))
    means = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        sample = np.concatenate([x[s : s + block] for s in starts[i]])[:n]
        means[i] = sample.mean()
    return float(means.std(ddof=1))


def _annualised_sharpe(period_returns: np.ndarray, hold_days: int) -> float:
    """Sharpe with a zero risk-free rate.

    Both arms hold for the same number of days, so the risk-free rate cancels
    out of the comparison the criterion actually cares about.
    """
    std = period_returns.std(ddof=1)
    if std == 0.0:
        return 0.0
    return float(period_returns.mean() / std * np.sqrt(252.0 / hold_days))


def compare_entry_timing(
    name: str,
    trigger_fn: Callable[[pd.DataFrame], pd.DataFrame],
    panel: pd.DataFrame,
    n_dates: int = N_DATES,
    basket_size: int = BASKET_SIZE,
    wait_days: int = WAIT_DAYS,
    hold_days: int = HOLD_DAYS,
    seed: int = SEED,
) -> GateBResult:
    """Does waiting for the signal beat entering right away?

    For each sampled decision date a random basket is bought two ways: at once,
    or on the first day the trigger fires within the wait window. If it never
    fires, the position is opened anyway on the last day of the window —
    dropping those cases would keep only the entries that happened to work out
    and manufacture an edge from selection alone.
    """
    opens = panel["Open"]
    dates = opens.index
    rng = np.random.default_rng(seed)

    triggers = trigger_fn(panel)
    last_start = len(dates) - (wait_days + hold_days + 2)
    if last_start <= 0:
        raise ValueError("El panel es demasiado corto para el protocolo de la Puerta B.")

    candidates = rng.choice(last_start, size=min(n_dates, last_start), replace=False)

    immediate: list[float] = []
    delayed: list[float] = []
    n_entries = 0
    n_forced = 0

    for offset in sorted(candidates):
        decision = dates[offset]
        window = opens.iloc[offset + 1 : offset + 1 + wait_days + hold_days + 1]
        eligible = window.columns[window.notna().all()]
        if len(eligible) < basket_size:
            continue
        basket = rng.choice(eligible, size=basket_size, replace=False)

        immediate_returns: list[float] = []
        delayed_returns: list[float] = []
        for ticker in basket:
            entry_now = opens.iloc[offset + 1][ticker]
            exit_now = opens.iloc[offset + 1 + hold_days][ticker]
            immediate_returns.append(exit_now / entry_now - 1.0)

            fired = triggers.iloc[offset + 1 : offset + 1 + wait_days][ticker]
            hit = fired[fired].index
            if len(hit):
                entry_offset = dates.get_loc(hit[0])
            else:
                entry_offset = offset + wait_days
                n_forced += 1
            entry_price = opens.iloc[entry_offset][ticker]
            exit_price = opens.iloc[entry_offset + hold_days][ticker]
            delayed_returns.append(exit_price / entry_price - 1.0)
            n_entries += 1

        immediate.append(float(np.mean(immediate_returns)))
        delayed.append(float(np.mean(delayed_returns)))

    immediate_arr = np.asarray(immediate)
    delayed_arr = np.asarray(delayed)
    sharpe_immediate = _annualised_sharpe(immediate_arr, hold_days)
    sharpe_signal = _annualised_sharpe(delayed_arr, hold_days)

    # The difference is measured per decision date and then converted to Sharpe
    # units with the immediate arm's own volatility, so the bootstrap resamples
    # paired observations rather than two independent Sharpe estimates. Pairing
    # removes the market moves both arms shared, which is most of the variance.
    paired = delayed_arr - immediate_arr
    scale = np.sqrt(252.0 / hold_days) / (immediate_arr.std(ddof=1) or 1.0)
    stderr = block_bootstrap_stderr(paired * scale, block=BOOTSTRAP_BLOCK, seed=seed)

    return GateBResult(
        signal=name,
        sharpe_immediate=sharpe_immediate,
        sharpe_signal=sharpe_signal,
        delta=sharpe_signal - sharpe_immediate,
        stderr=stderr,
        n_entries=n_entries,
        n_forced=n_forced,
        hold_days=hold_days,
    )
