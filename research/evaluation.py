from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from research.costs import COST_SCENARIOS, apply_costs, turnover_from_weights

SUBPERIODS: dict[str, tuple[str, str]] = {
    "P1 2010-2013": ("2010-01-01", "2013-12-31"),
    "P2 2014-2017": ("2014-01-01", "2017-12-31"),
    "P3 2018-2021": ("2018-01-01", "2021-12-31"),
    "P4 2022-2026": ("2022-01-01", "2026-06-30"),
}

MIN_IC = 0.03
MIN_TSTAT = 2.0
MIN_SUBPERIODS = 3
FDR = 0.10
N_QUANTILES = 5


@dataclass(frozen=True)
class GateAResult:
    signal: str
    horizon: int
    mean_ic: float
    t_stat: float
    p_value: float
    spread_gross: float
    spread_net: float
    turnover: float
    n_dates: int
    subperiod_pass: dict[str, bool] = field(default_factory=dict)
    spread_net_by_scenario: dict[str, float] = field(default_factory=dict)

    @property
    def subperiods_passed(self) -> int:
        return sum(self.subperiod_pass.values())


def forward_returns(close: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return from the close of t to the close of t+horizon."""
    return close.shift(-horizon) / close - 1.0


def information_coefficient(
    signal: pd.DataFrame, forward: pd.DataFrame, min_names: int = 10
) -> pd.Series:
    """Cross-sectional Spearman correlation, one value per date.

    Rank correlation rather than Pearson because the question is whether the
    signal orders the cross-section, not whether it predicts magnitudes. Dates
    with too few names are dropped: ranking a handful of stocks is noise.

    Computed as Pearson correlation of the ranks rather than by calling out to
    scipy per date. The full grid is roughly 160 evaluations over 4,000 dates;
    a per-date loop turns minutes into hours. A cross-check against scipy pins
    the two to the same answer.
    """
    aligned_signal, aligned_forward = signal.align(forward, join="inner")
    valid = aligned_signal.notna() & aligned_forward.notna()

    ranked_signal = aligned_signal.where(valid).rank(axis=1)
    ranked_forward = aligned_forward.where(valid).rank(axis=1)

    centred_signal = ranked_signal.sub(ranked_signal.mean(axis=1), axis=0)
    centred_forward = ranked_forward.sub(ranked_forward.mean(axis=1), axis=0)

    covariance = (centred_signal * centred_forward).sum(axis=1)
    scale = np.sqrt((centred_signal**2).sum(axis=1) * (centred_forward**2).sum(axis=1))

    ic = covariance / scale.replace(0.0, np.nan)
    return ic.where(valid.sum(axis=1) >= min_names)


def equal_weight_sharpe(close: pd.DataFrame) -> float:
    """Annualised Sharpe of buying the whole universe equal-weighted and holding.

    The passive baseline the criterion compares against economically. Risk-free
    rate is zero, matching the convention used in Gate B.
    """
    daily = close.pct_change(fill_method=None).mean(axis=1).dropna()
    if daily.empty or daily.std(ddof=1) == 0.0:
        return 0.0
    return float(daily.mean() / daily.std(ddof=1) * np.sqrt(252.0))


def newey_west_tstat(series: pd.Series, lag: int) -> float:
    """t-stat of the mean, robust to the autocorrelation overlapping horizons create.

    With a horizon of h days, consecutive IC observations share h-1 days of
    return, so the naive standard error understates the true uncertainty and
    manufactures significance. Bartlett weights, lag = h-1.

    A series with no variation returns 0 rather than infinity. Infinity would
    read as unlimited confidence and clear every gate downstream; 0 reads as no
    evidence, which is the honest answer for a degenerate input. The check uses
    the raw range rather than the computed variance because subtracting a
    float64 mean from identical values leaves residuals around 1e-17 instead of
    exactly zero, so a variance-based guard silently fails to fire.
    """
    x = series.dropna().to_numpy(dtype=float)
    n = x.size
    if n < 2 or float(np.ptp(x)) == 0.0:
        return 0.0
    mu = float(x.mean())
    e = x - mu
    variance = float(e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - l / (lag + 1.0)
        variance += 2.0 * weight * float(e[l:] @ e[:-l]) / n
    if variance <= 0.0:
        return 0.0
    return mu / float(np.sqrt(variance / n))


def benjamini_hochberg(pvalues, fdr: float = FDR) -> np.ndarray:
    """Which p-values survive a false-discovery-rate correction, in input order.

    Twenty-eight tests produce roughly 1.4 spurious winners at a 5% threshold.
    Without this step the study would report noise as a finding.
    """
    p = np.asarray(list(pvalues), dtype=float)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    thresholds = fdr * np.arange(1, n + 1) / n
    below = p[order] <= thresholds
    result = np.zeros(n, dtype=bool)
    if below.any():
        cutoff = int(np.flatnonzero(below).max()) + 1
        result[order[:cutoff]] = True
    return result


def quintile_spread(
    signal: pd.DataFrame, forward: pd.DataFrame, horizon: int, bps: float = 0.0
) -> tuple[float, float, float]:
    """Annualised (top quintile - bottom quintile), gross and net, plus turnover.

    Portfolios are rebalanced at the horizon frequency, so the holding period
    matches the return being predicted. Gross and net come back together rather
    than from two passes: high-turnover signals are decided by the gap between
    them, and computing it twice doubles the cost of the whole study.
    """
    aligned_signal, aligned_forward = signal.align(forward, join="inner")
    dates = aligned_signal.index[::horizon]

    top_weights: list[pd.Series] = []
    period_returns: list[float] = []
    for date in dates:
        row_s = aligned_signal.loc[date]
        row_f = aligned_forward.loc[date]
        valid = row_s.notna() & row_f.notna()
        if valid.sum() < N_QUANTILES * 2:
            continue
        ranks = row_s[valid].rank(pct=True)
        top = row_f[valid][ranks > 0.8]
        bottom = row_f[valid][ranks <= 0.2]
        if top.empty or bottom.empty:
            continue
        period_returns.append(float(top.mean() - bottom.mean()))
        membership = pd.Series(0.0, index=aligned_signal.columns)
        membership[top.index] = 1.0 / len(top)
        top_weights.append(membership)

    if not period_returns:
        return 0.0, 0.0, 0.0

    weights = pd.DataFrame(top_weights).reset_index(drop=True)
    turnover = turnover_from_weights(weights)

    gross = pd.Series(period_returns)
    net = apply_costs(gross, turnover, bps=bps)
    periods_per_year = 252.0 / horizon
    return (
        float(gross.mean() * periods_per_year),
        float(net.mean() * periods_per_year),
        float(turnover.mean()),
    )


def evaluate(
    name: str,
    signal: pd.DataFrame,
    close: pd.DataFrame,
    horizon: int,
    bps: float,
) -> GateAResult:
    """Everything Gate A needs about one signal at one horizon."""
    forward = forward_returns(close, horizon)
    ic = information_coefficient(signal, forward).dropna()

    t_stat = newey_west_tstat(ic, lag=max(horizon - 1, 0))
    p_value = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat))))

    spread_gross, spread_net, turnover = quintile_spread(signal, forward, horizon, bps=bps)

    by_scenario = {
        label: quintile_spread(signal, forward, horizon, bps=scenario_bps)[1]
        for label, scenario_bps in COST_SCENARIOS.items()
    }

    subperiod_pass: dict[str, bool] = {}
    for label, (start, end) in SUBPERIODS.items():
        window_signal = signal.loc[start:end]
        window_close = close.loc[start:end]
        if len(window_signal) < horizon * 4:
            subperiod_pass[label] = False
            continue
        window_forward = forward_returns(window_close, horizon)
        window_ic = information_coefficient(window_signal, window_forward).dropna()
        _, window_net, _ = quintile_spread(window_signal, window_forward, horizon, bps=bps)
        subperiod_pass[label] = bool(
            len(window_ic) > 0 and window_ic.mean() >= MIN_IC and window_net > 0.0
        )

    return GateAResult(
        signal=name,
        horizon=horizon,
        mean_ic=float(ic.mean()) if len(ic) else 0.0,
        t_stat=t_stat,
        p_value=p_value,
        spread_gross=spread_gross,
        spread_net=spread_net,
        turnover=turnover,
        n_dates=int(len(ic)),
        subperiod_pass=subperiod_pass,
        spread_net_by_scenario=by_scenario,
    )
