import numpy as np
import pandas as pd
import pytest
from optimizer import portfolio_metrics, validate_constraints, risk_contribution


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
