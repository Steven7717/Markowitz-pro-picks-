import numpy as np
import pandas as pd
import pytest

from research.costs import COST_SCENARIOS, apply_costs, turnover_from_weights


def test_zero_cost_leaves_returns_untouched():
    returns = pd.Series([0.01, -0.02, 0.03])
    turnover = pd.Series([1.0, 1.0, 1.0])
    pd.testing.assert_series_equal(apply_costs(returns, turnover, bps=0.0), returns)


def test_full_turnover_at_ten_bps_costs_ten_bps():
    returns = pd.Series([0.01])
    turnover = pd.Series([1.0])
    assert apply_costs(returns, turnover, bps=10.0).iloc[0] == pytest.approx(0.01 - 0.0010)


def test_half_turnover_costs_half_as_much():
    returns = pd.Series([0.01])
    assert apply_costs(returns, pd.Series([0.5]), bps=10.0).iloc[0] == pytest.approx(0.01 - 0.0005)


def test_costs_only_ever_reduce_returns():
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0, 0.02, 100))
    turnover = pd.Series(rng.uniform(0, 1, 100))
    assert (apply_costs(returns, turnover, bps=25.0) <= returns).all()


def test_turnover_of_an_unchanged_portfolio_is_zero():
    weights = pd.DataFrame([[0.5, 0.5], [0.5, 0.5]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[-1] == pytest.approx(0.0)


def test_turnover_of_a_completely_rebuilt_portfolio_is_one():
    """Selling everything and buying a disjoint set trades the whole portfolio once."""
    weights = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[-1] == pytest.approx(1.0)


def test_the_first_period_counts_as_building_the_position():
    weights = pd.DataFrame([[0.5, 0.5]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[0] == pytest.approx(1.0)


def test_the_three_pre_registered_cost_scenarios_are_available():
    assert COST_SCENARIOS == {"optimista": 5.0, "base": 10.0, "conservador": 25.0}
