import numpy as np
import pandas as pd
import pytest

from optimizer import (
    STRATEGY_LABELS,
    equal_weight_portfolio,
    optimize_max_sharpe,
    optimize_min_variance,
    optimize_portfolio,
    optimize_risk_parity,
    risk_contribution,
)

PPY = 252
RF = 0.0


@pytest.fixture
def market() -> pd.DataFrame:
    """Correlated assets with clearly different volatilities."""
    rng = np.random.default_rng(31)
    n_obs, n_assets = 800, 5
    betas = np.linspace(0.5, 1.8, n_assets)
    idio = np.linspace(0.006, 0.024, n_assets)
    factor = rng.normal(0.0005, 0.010, size=(n_obs, 1))
    data = factor @ betas.reshape(1, -1) + rng.normal(0, 1, (n_obs, n_assets)) * idio
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


@pytest.fixture
def uncorrelated() -> pd.DataFrame:
    """Independent assets with volatilities in a 1:2:4:8 ratio."""
    rng = np.random.default_rng(5)
    vols = np.array([0.005, 0.010, 0.020, 0.040])
    return pd.DataFrame(
        rng.normal(0, 1, (4000, 4)) * vols, columns=list("PQRS")
    )


def _shift_means(returns: pd.DataFrame) -> pd.DataFrame:
    """Change every expected return while leaving the covariance untouched."""
    bumps = np.linspace(-0.004, 0.004, returns.shape[1])
    return returns + bumps


# ── Minimum variance ──────────────────────────────────────────────────────────

def test_min_variance_beats_equal_weight_on_volatility(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    ew = equal_weight_portfolio(market, RF, PPY)
    assert mv["annual_vol"] < ew["annual_vol"]


def test_min_variance_has_the_lowest_volatility_of_all_strategies(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    for other in (
        optimize_max_sharpe(market, RF, PPY, (0.0, 1.0), False),
        optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False),
        equal_weight_portfolio(market, RF, PPY),
    ):
        assert mv["annual_vol"] <= other["annual_vol"] + 1e-9


def test_min_variance_completely_ignores_expected_returns(market):
    """This is why it is robust: the noisiest input is never consulted."""
    base = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    bumped = optimize_min_variance(_shift_means(market), RF, PPY, (0.0, 1.0), False)
    assert np.allclose(base["weights"], bumped["weights"], atol=1e-4)


def test_min_variance_matches_the_closed_form_when_unconstrained(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), allow_short=True)
    inv = np.linalg.inv(market.cov().values)
    ones = np.ones(market.shape[1])
    closed_form = inv @ ones / (ones @ inv @ ones)
    assert np.allclose(mv["weights"], closed_form, atol=1e-3)


def test_min_variance_respects_weight_bounds(market):
    mv = optimize_min_variance(market, RF, PPY, (0.10, 0.30), False)
    assert mv["weights"].min() >= 0.10 - 1e-6
    assert mv["weights"].max() <= 0.30 + 1e-6


def test_min_variance_weights_sum_to_one(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    assert abs(mv["weights"].sum() - 1.0) < 1e-6


# ── Risk parity (equal risk contribution) ─────────────────────────────────────

def test_risk_parity_equalises_every_risk_contribution(market):
    """The defining property: each asset supplies the same share of portfolio risk."""
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    contributions = risk_contribution(rp["weights"], market.cov().values)
    assert np.allclose(contributions, 1.0 / market.shape[1], atol=1e-3)


def test_risk_parity_is_more_balanced_than_equal_weight(market):
    """Equal money is not equal risk when volatilities differ."""
    ew_contrib = risk_contribution(np.ones(5) / 5, market.cov().values)
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    rp_contrib = risk_contribution(rp["weights"], market.cov().values)
    assert rp_contrib.std() < ew_contrib.std()


def test_risk_parity_gives_more_weight_to_calmer_assets(uncorrelated):
    rp = optimize_risk_parity(uncorrelated, RF, PPY, (0.0, 1.0), False)
    w = rp["weights"]
    assert all(w[i] > w[i + 1] for i in range(len(w) - 1))


def test_risk_parity_is_inverse_volatility_when_assets_are_uncorrelated(uncorrelated):
    """With zero correlation the analytic answer is w proportional to 1/sigma."""
    rp = optimize_risk_parity(uncorrelated, RF, PPY, (0.0, 1.0), False)
    inv_vol = 1.0 / uncorrelated.std().values
    expected = inv_vol / inv_vol.sum()
    assert np.allclose(rp["weights"], expected, atol=0.02)


def test_risk_parity_completely_ignores_expected_returns(market):
    base = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    bumped = optimize_risk_parity(_shift_means(market), RF, PPY, (0.0, 1.0), False)
    assert np.allclose(base["weights"], bumped["weights"], atol=1e-4)


def test_risk_parity_never_takes_short_positions(market):
    """Equal risk contribution is undefined for negative weights."""
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), allow_short=True)
    assert rp["weights"].min() >= 0.0


def test_risk_parity_respects_weight_bounds(market):
    rp = optimize_risk_parity(market, RF, PPY, (0.15, 0.25), False)
    assert rp["weights"].min() >= 0.15 - 1e-6
    assert rp["weights"].max() <= 0.25 + 1e-6


# ── Common interface ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_returns_the_same_result_shape(market, strategy):
    result = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=strategy)
    for key in ("converged", "weights", "annual_return", "annual_vol", "sharpe",
                "risk_contribution", "cov_shrinkage", "mean_shrinkage"):
        assert key in result, f"{strategy} is missing '{key}'"


@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_produces_a_valid_portfolio(market, strategy):
    result = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=strategy)
    assert result["converged"]
    assert abs(result["weights"].sum() - 1.0) < 1e-6


def test_max_sharpe_still_has_the_highest_in_sample_sharpe(market):
    """Each strategy should win on the metric it actually optimises."""
    best = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy="max_sharpe")
    for other in ("min_variance", "risk_parity"):
        rival = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=other)
        assert best["sharpe"] >= rival["sharpe"] - 1e-6


def test_unknown_strategy_is_rejected(market):
    with pytest.raises(ValueError, match="desconocida"):
        optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy="martingala")


def test_every_strategy_has_a_label_for_the_interface():
    assert set(STRATEGY_LABELS) == {"max_sharpe", "min_variance", "risk_parity"}


def test_strategies_accept_shrinkage(market):
    for strategy in ("min_variance", "risk_parity"):
        result = optimize_portfolio(
            market, RF, PPY, (0.0, 1.0), False, strategy=strategy, shrinkage=True
        )
        assert result["cov_shrinkage"] > 0.0
