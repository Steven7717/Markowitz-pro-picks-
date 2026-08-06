import numpy as np
import pandas as pd
import pytest

from research.evaluation import (
    SUBPERIODS,
    GateAResult,
    benjamini_hochberg,
    equal_weight_sharpe,
    evaluate,
    forward_returns,
    information_coefficient,
    newey_west_tstat,
    quintile_spread,
)


@pytest.fixture
def close() -> pd.DataFrame:
    tickers = [f"T{i}" for i in range(20)]
    dates = pd.bdate_range("2015-01-01", periods=1500)
    rng = np.random.default_rng(31)
    steps = rng.normal(0.0004, 0.014, size=(len(dates), len(tickers)))
    return pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=dates, columns=tickers)


# ── Retornos futuros ──────────────────────────────────────────────────────────

def test_forward_returns_look_ahead_by_exactly_the_horizon(close):
    forward = forward_returns(close, horizon=5)
    expected = close.iloc[5, 0] / close.iloc[0, 0] - 1.0
    assert forward.iloc[0, 0] == pytest.approx(expected)


def test_the_last_rows_have_no_forward_return(close):
    assert forward_returns(close, horizon=5).iloc[-5:].isna().all().all()


# ── Information coefficient ───────────────────────────────────────────────────

def test_an_oracle_signal_scores_a_near_perfect_ic(close):
    """Proves the measurement works. If this fails, no other result means anything."""
    forward = forward_returns(close, horizon=21)
    ic = information_coefficient(forward, forward)
    assert ic.mean() == pytest.approx(1.0, abs=1e-9)


def test_a_random_signal_scores_essentially_zero_ic(close):
    """Proves nothing leaks. If this is far from zero, the pipeline peeks."""
    rng = np.random.default_rng(37)
    noise = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)
    ic = information_coefficient(noise, forward_returns(close, horizon=21))
    assert abs(ic.mean()) < 0.02


def test_a_sign_flipped_signal_scores_the_opposite_ic(close):
    forward = forward_returns(close, horizon=21)
    assert information_coefficient(-forward, forward).mean() == pytest.approx(-1.0, abs=1e-9)


def test_dates_without_enough_names_are_skipped(close):
    """Ranking three stocks says nothing about a cross-section; those dates are dropped."""
    forward = forward_returns(close, horizon=21)
    sparse = forward.copy()
    sparse.iloc[:100, 3:] = np.nan
    ic = information_coefficient(sparse, forward, min_names=10)
    assert ic.iloc[:100].isna().all()


# ── t-stat Newey-West ─────────────────────────────────────────────────────────

def test_newey_west_with_zero_lag_matches_the_plain_t_stat():
    rng = np.random.default_rng(41)
    series = pd.Series(rng.normal(0.05, 1.0, 500))
    plain = series.mean() / (series.std(ddof=0) / np.sqrt(len(series)))
    assert newey_west_tstat(series, lag=0) == pytest.approx(plain, rel=1e-6)


def test_newey_west_shrinks_the_t_stat_of_an_autocorrelated_series():
    """Overlapping horizons autocorrelate the IC series and inflate the naive t-stat."""
    rng = np.random.default_rng(43)
    noise = rng.normal(0, 1, 2000)
    smoothed = pd.Series(noise).rolling(20).mean().dropna() + 0.05
    assert abs(newey_west_tstat(smoothed, lag=19)) < abs(newey_west_tstat(smoothed, lag=0))


def test_a_series_with_no_variation_reports_no_evidence_rather_than_certainty():
    """Infinity would read as unlimited confidence and clear every gate downstream.

    Subtracting a float64 mean from identical values leaves residuals around
    1e-17, so a variance-based guard silently fails to fire and the function
    returns ~3.6e16 — which passes the t >= 2 threshold and Benjamini-Hochberg
    on a completely degenerate input.
    """
    assert newey_west_tstat(pd.Series([0.05] * 100), lag=0) == 0.0


# ── Benjamini-Hochberg ────────────────────────────────────────────────────────

def test_benjamini_hochberg_rejects_nothing_when_every_p_value_is_large():
    assert not benjamini_hochberg([0.5, 0.6, 0.7, 0.9], fdr=0.10).any()


def test_benjamini_hochberg_rejects_a_clearly_significant_p_value():
    passed = benjamini_hochberg([0.0001, 0.5, 0.6, 0.9], fdr=0.10)
    assert passed.tolist() == [True, False, False, False]


def test_a_lone_marginal_p_value_among_many_tests_does_not_survive():
    """0.04 looks significant on its own; among twenty tests it is what noise produces."""
    pvalues = [0.04] + [0.6] * 19
    assert benjamini_hochberg(pvalues, fdr=0.10).sum() == 0


def test_benjamini_hochberg_preserves_input_order():
    passed = benjamini_hochberg([0.9, 0.0001, 0.8], fdr=0.10)
    assert passed.tolist() == [False, True, False]


# ── Quintiles ─────────────────────────────────────────────────────────────────

def test_an_oracle_signal_produces_a_positive_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, _, _ = quintile_spread(forward, forward, horizon=21)
    assert gross > 0.0


def test_a_sign_flipped_oracle_produces_a_negative_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, _, _ = quintile_spread(-forward, forward, horizon=21)
    assert gross < 0.0


def test_quintile_spread_also_reports_turnover(close):
    forward = forward_returns(close, horizon=21)
    _, _, turnover = quintile_spread(forward, forward, horizon=21)
    assert 0.0 <= turnover <= 1.0


def test_costs_never_improve_the_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, net, _ = quintile_spread(forward, forward, horizon=21, bps=25.0)
    assert net <= gross


# ── Línea base pasiva ─────────────────────────────────────────────────────────

def test_the_passive_benchmark_reports_a_finite_sharpe(close):
    assert np.isfinite(equal_weight_sharpe(close))


def test_the_passive_benchmark_is_positive_for_a_rising_market():
    dates = pd.bdate_range("2015-01-01", periods=600)
    rising = pd.DataFrame(
        {"A": np.linspace(100, 200, 600), "B": np.linspace(100, 180, 600)}, index=dates
    )
    assert equal_weight_sharpe(rising) > 0.0


# ── Sub-periodos ──────────────────────────────────────────────────────────────

def test_the_four_subperiods_do_not_overlap():
    bounds = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in SUBPERIODS.values()]
    ordered = sorted(bounds)
    assert all(ordered[i][1] < ordered[i + 1][0] for i in range(len(ordered) - 1))


def test_there_are_exactly_four_subperiods():
    assert len(SUBPERIODS) == 4


def test_the_subperiods_cover_the_whole_study_window():
    starts = [pd.Timestamp(a) for a, _ in SUBPERIODS.values()]
    ends = [pd.Timestamp(b) for _, b in SUBPERIODS.values()]
    assert min(starts) == pd.Timestamp("2010-01-01")
    assert max(ends) == pd.Timestamp("2026-06-30")


# ── evaluate ──────────────────────────────────────────────────────────────────

def test_evaluate_reports_every_field_the_criterion_needs(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert isinstance(result, GateAResult)
    assert result.signal == "oracle"
    assert result.horizon == 21
    assert result.n_dates > 0
    assert set(result.subperiod_pass) <= set(SUBPERIODS)


def test_evaluate_gives_the_oracle_a_huge_ic(close):
    forward = forward_returns(close, horizon=21)
    assert evaluate("oracle", forward, close, horizon=21, bps=10.0).mean_ic > 0.9


def test_evaluate_gives_random_noise_an_ic_near_zero(close):
    rng = np.random.default_rng(47)
    noise = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)
    assert abs(evaluate("noise", noise, close, horizon=21, bps=10.0).mean_ic) < 0.02


def test_evaluate_reports_the_three_pre_registered_cost_scenarios(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert set(result.spread_net_by_scenario) == {"optimista", "base", "conservador"}


def test_higher_costs_never_produce_a_better_net_spread(close):
    forward = forward_returns(close, horizon=21)
    scenarios = evaluate("oracle", forward, close, horizon=21, bps=10.0).spread_net_by_scenario
    assert scenarios["conservador"] <= scenarios["base"] <= scenarios["optimista"]


def test_the_base_scenario_is_the_one_the_criterion_uses(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert result.spread_net == pytest.approx(result.spread_net_by_scenario["base"])


# ── Referencia cruzada ────────────────────────────────────────────────────────

def test_our_information_coefficient_matches_an_independent_implementation(close):
    """The vectorised rank correlation must agree with scipy, date by date.

    Same pattern the repo already uses to check Ledoit-Wolf against scikit-learn.
    The loop version is the obvious implementation but far too slow for the full
    grid, so the fast one has to be pinned to a reference.
    """
    from scipy import stats as scipy_stats

    forward = forward_returns(close, horizon=21)
    rng = np.random.default_rng(51)
    signal = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)

    ours = information_coefficient(signal, forward).dropna()
    sample = ours.index[::97]
    for date in sample:
        valid = signal.loc[date].notna() & forward.loc[date].notna()
        reference = scipy_stats.spearmanr(
            signal.loc[date][valid], forward.loc[date][valid]
        ).statistic
        assert ours.loc[date] == pytest.approx(reference, abs=1e-9)
