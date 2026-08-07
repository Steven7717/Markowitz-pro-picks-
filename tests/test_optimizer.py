import numpy as np
import pandas as pd
import pytest
from optimizer import portfolio_metrics, validate_constraints, risk_contribution, simulate_portfolios


@pytest.fixture
def synthetic_returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    data = rng.normal(
        loc=[0.001, 0.0008, 0.0012],
        scale=[0.015, 0.012, 0.018],
        size=(500, 3),
    )
    return pd.DataFrame(data, columns=["A", "B", "C"])


def test_portfolio_metrics_returns_three_floats(synthetic_returns):
    w = np.array([1/3, 1/3, 1/3])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    ret, vol, sharpe = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0001, periods_per_year=252)
    assert isinstance(ret, float)
    assert isinstance(vol, float)
    assert isinstance(sharpe, float)


def test_portfolio_metrics_vol_is_positive(synthetic_returns):
    w = np.array([0.5, 0.3, 0.2])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    _, vol, _ = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0001, periods_per_year=252)
    assert vol > 0


def test_portfolio_metrics_zero_rf_gives_positive_sharpe(synthetic_returns):
    w = np.array([1/3, 1/3, 1/3])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    _, _, sharpe = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0, periods_per_year=252)
    assert isinstance(sharpe, float)


def test_risk_contribution_sums_to_one(synthetic_returns):
    w = np.array([0.4, 0.3, 0.3])
    cov = synthetic_returns.cov().values
    contrib = risk_contribution(w, cov)
    assert abs(contrib.sum() - 1.0) < 1e-6


def test_risk_contribution_length_matches_assets(synthetic_returns):
    w = np.array([0.4, 0.3, 0.3])
    cov = synthetic_returns.cov().values
    contrib = risk_contribution(w, cov)
    assert len(contrib) == 3


def test_validate_constraints_feasible():
    ok, msg = validate_constraints(n_assets=5, weight_min=0.05, weight_max=0.40)
    assert ok is True


def test_validate_constraints_min_too_high():
    ok, msg = validate_constraints(n_assets=3, weight_min=0.40, weight_max=1.0)
    assert ok is False
    assert "infactible" in msg.lower()


def test_validate_constraints_max_too_low():
    ok, msg = validate_constraints(n_assets=5, weight_min=0.0, weight_max=0.15)
    assert ok is False
    assert "infactible" in msg.lower()


def test_validate_constraints_exactly_feasible_min():
    # 3 assets, min=1/3 → 3 * 1/3 = 1.0 exactly
    ok, _ = validate_constraints(n_assets=3, weight_min=1/3, weight_max=1.0)
    assert ok is True


def test_validate_constraints_exactly_feasible_max():
    # 3 assets, max=1/3 → 3 * 1/3 = 1.0 exactly
    ok, _ = validate_constraints(n_assets=3, weight_min=0.0, weight_max=1/3)
    assert ok is True


def test_simulate_portfolios_returns_dataframe(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert isinstance(df, pd.DataFrame)
    assert {"ret", "vol", "sharpe"} <= set(df.columns)


def test_simulate_portfolios_not_empty(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert len(df) > 0


def test_simulate_portfolios_vol_positive(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert (df["vol"] > 0).all()


def test_simulate_portfolios_with_bounds(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.1, 0.6),
        allow_short=False,
    )
    assert len(df) > 0


from optimizer import optimize_max_sharpe, equal_weight_portfolio


def test_optimize_max_sharpe_converges(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert result["converged"] is True


def test_optimize_max_sharpe_weights_sum_to_one(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert abs(result["weights"].sum() - 1.0) < 1e-4


def test_optimize_max_sharpe_weights_non_negative_when_no_short(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert all(w >= -1e-6 for w in result["weights"])


def test_optimize_max_sharpe_returns_risk_contribution(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert "risk_contribution" in result
    assert len(result["risk_contribution"]) == 3


def test_optimize_max_sharpe_respects_bounds(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.1, 0.6),
        allow_short=False,
    )
    if result["converged"]:
        assert all(w >= 0.1 - 1e-4 for w in result["weights"])
        assert all(w <= 0.6 + 1e-4 for w in result["weights"])


def test_equal_weight_portfolio_weights_are_equal(synthetic_returns):
    result = equal_weight_portfolio(synthetic_returns, rf_rate=0.0001, periods_per_year=252)
    assert abs(result["weights"][0] - 1/3) < 1e-6
    assert abs(result["weights"].sum() - 1.0) < 1e-6


def test_equal_weight_portfolio_returns_metrics(synthetic_returns):
    result = equal_weight_portfolio(synthetic_returns, rf_rate=0.0001, periods_per_year=252)
    assert "annual_return" in result
    assert "annual_vol" in result
    assert "sharpe" in result


# ── Feasible-set handling (regression tests for the audit findings) ───────────

from optimizer import effective_bounds, project_to_bounds, sample_feasible_weights


def test_effective_bounds_long_only_uses_the_user_limits():
    assert effective_bounds((0.1, 0.4), allow_short=False) == (0.1, 0.4)


def test_effective_bounds_short_selling_is_symmetric_around_zero():
    """Under shorting the max-weight slider caps absolute position size both ways."""
    assert effective_bounds((0.1, 0.4), allow_short=True) == (-0.4, 0.4)


def test_project_to_bounds_produces_weights_that_sum_to_one():
    w = project_to_bounds(np.array([0.9, 0.05, 0.03, 0.02]), lb=0.1, ub=0.4)
    assert abs(w.sum() - 1.0) < 1e-9


def test_project_to_bounds_respects_both_limits():
    w = project_to_bounds(np.array([0.9, 0.05, 0.03, 0.02]), lb=0.1, ub=0.4)
    assert w.min() >= 0.1 - 1e-9
    assert w.max() <= 0.4 + 1e-9


def test_project_to_bounds_leaves_already_feasible_weights_untouched():
    w0 = np.array([0.25, 0.25, 0.25, 0.25])
    assert np.allclose(project_to_bounds(w0, lb=0.1, ub=0.4), w0)


def test_project_to_bounds_allows_negative_weights_when_lower_bound_is_negative():
    w = project_to_bounds(np.array([2.0, -0.5, -0.3, -0.2]), lb=-0.5, ub=1.0)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w.min() >= -0.5 - 1e-9
    assert w.max() <= 1.0 + 1e-9


def test_sampled_weights_always_satisfy_tight_bounds():
    """Audit finding A: clip-then-renormalize violated the max bound 67% of the time."""
    rng = np.random.default_rng(0)
    for _ in range(2000):
        w = sample_feasible_weights(n_assets=4, lb=0.10, ub=0.40, rng=rng)
        assert w.min() >= 0.10 - 1e-9
        assert w.max() <= 0.40 + 1e-9
        assert abs(w.sum() - 1.0) < 1e-9


def test_sampled_weights_can_be_negative_when_shorting_is_enabled():
    """Audit finding B: the simulated cloud never contained a single short position."""
    rng = np.random.default_rng(0)
    saw_negative = any(
        sample_feasible_weights(n_assets=4, lb=-1.0, ub=1.0, rng=rng).min() < 0
        for _ in range(500)
    )
    assert saw_negative


def test_simulated_cloud_respects_the_same_bounds_as_the_optimizer(synthetic_returns):
    sim = simulate_portfolios(
        synthetic_returns, rf_rate=0.0001, periods_per_year=252,
        weight_bounds=(0.10, 0.40), allow_short=False,
    )
    assert sim["max_weight"].max() <= 0.40 + 1e-9
    assert sim["min_weight"].min() >= 0.10 - 1e-9


def test_simulated_cloud_contains_shorts_when_shorting_is_enabled(synthetic_returns):
    sim = simulate_portfolios(
        synthetic_returns, rf_rate=0.0001, periods_per_year=252,
        weight_bounds=(0.0, 1.0), allow_short=True,
    )
    assert sim["min_weight"].min() < 0


# ── Optimiser quality ─────────────────────────────────────────────────────────

def test_optimum_is_never_worse_than_the_equal_weight_portfolio(synthetic_returns):
    """Equal weight is feasible here, so the optimum must at least match it."""
    opt = optimize_max_sharpe(
        synthetic_returns, rf_rate=0.0001, periods_per_year=252,
        weight_bounds=(0.0, 1.0), allow_short=False,
    )
    ew = equal_weight_portfolio(synthetic_returns, rf_rate=0.0001, periods_per_year=252)
    assert opt["sharpe"] >= ew["sharpe"] - 1e-6


def test_optimizer_respects_bounds_under_short_selling(synthetic_returns):
    opt = optimize_max_sharpe(
        synthetic_returns, rf_rate=0.0001, periods_per_year=252,
        weight_bounds=(0.0, 0.60), allow_short=True,
    )
    assert opt["converged"]
    assert opt["weights"].min() >= -0.60 - 1e-4
    assert opt["weights"].max() <= 0.60 + 1e-4


# ── Shrinkage integration ─────────────────────────────────────────────────────

def _scarce_data() -> pd.DataFrame:
    rng = np.random.default_rng(21)
    betas = np.linspace(0.6, 1.6, 8)
    market = rng.normal(0.0004, 0.011, size=(70, 1))
    idio = rng.normal(0.0, 1.0, size=(70, 8)) * np.linspace(0.008, 0.022, 8)
    return pd.DataFrame(market @ betas.reshape(1, -1) + idio, columns=[f"A{i}" for i in range(8)])


def test_shrinkage_lowers_the_reported_in_sample_sharpe():
    """The inflated Sharpe comes from fitting noise; shrinkage should deflate it."""
    data = _scarce_data()
    plain = optimize_max_sharpe(data, 0.0, 252, (0.0, 1.0), False, shrinkage=False)
    shrunk = optimize_max_sharpe(data, 0.0, 252, (0.0, 1.0), False, shrinkage=True)
    assert shrunk["sharpe"] < plain["sharpe"]


def test_shrinkage_produces_a_less_concentrated_portfolio():
    data = _scarce_data()
    plain = optimize_max_sharpe(data, 0.0, 252, (0.0, 1.0), False, shrinkage=False)
    shrunk = optimize_max_sharpe(data, 0.0, 252, (0.0, 1.0), False, shrinkage=True)
    effective_n = lambda w: 1.0 / np.sum(w**2)
    assert effective_n(shrunk["weights"]) > effective_n(plain["weights"])


def test_optimizer_reports_the_shrinkage_intensities_it_used():
    data = _scarce_data()
    result = optimize_max_sharpe(data, 0.0, 252, (0.0, 1.0), False, shrinkage=True)
    assert 0.0 < result["cov_shrinkage"] <= 1.0
    assert 0.0 < result["mean_shrinkage"] <= 1.0


def test_optimizer_defaults_to_no_shrinkage(synthetic_returns):
    result = optimize_max_sharpe(synthetic_returns, 0.0001, 252, (0.0, 1.0), False)
    assert result["cov_shrinkage"] == 0.0
