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
    assert set(df.columns) == {"ret", "vol", "sharpe"}


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
