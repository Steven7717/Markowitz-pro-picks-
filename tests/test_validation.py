import numpy as np
import pandas as pd
import pytest

from validation import (
    default_window_sizes,
    sharpe_standard_error,
    walk_forward_validation,
)


def _noise(n_obs: int, n_assets: int = 6, seed: int = 4) -> pd.DataFrame:
    """Assets with zero true expected return — any positive Sharpe is fitted noise."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0.0, 0.012, size=(n_obs, n_assets)),
        columns=[f"A{i}" for i in range(n_assets)],
    )


def test_returns_none_when_history_is_shorter_than_a_year():
    assert walk_forward_validation(_noise(120), 0.0, 252, (0.0, 1.0), False) is None


def test_default_windows_scale_with_the_data_frequency():
    assert default_window_sizes(252) == (504, 63)
    assert default_window_sizes(12) == (24, 3)


def test_windows_shrink_to_fit_when_history_is_tight():
    """One year of daily data cannot host a two-year training window.

    The app's '1 Semana' horizon fetches exactly 252 rows, so without an adaptive
    fallback validation would silently never run on the daily horizons.
    """
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert r is not None
    assert r["n_windows"] >= 3
    assert r["train_size"] + r["test_size"] <= 252


def test_one_year_of_daily_data_still_reports_out_of_sample_results():
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert np.isfinite(r["out_of_sample_sharpe"])


def test_reports_how_many_windows_were_evaluated():
    r = walk_forward_validation(_noise(1200), 0.0, 252, (0.0, 1.0), False)
    assert r["n_windows"] > 0


def test_window_count_follows_the_requested_window_sizes():
    r = walk_forward_validation(
        _noise(1000), 0.0, 252, (0.0, 1.0), False, train_size=400, test_size=100,
    )
    # windows start at 0, 100, 200, ... while train+test still fits in 1000 rows
    assert r["n_windows"] == 6


def test_in_sample_sharpe_far_exceeds_out_of_sample_on_pure_noise():
    """The whole point of the audit: the reported Sharpe does not survive validation."""
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert r["in_sample_sharpe"] > r["out_of_sample_sharpe"] + 0.5


def test_out_of_sample_sharpe_on_pure_noise_is_unbiased():
    """Averaged over seeds, not a single draw.

    One walk-forward run has a standard error of roughly 0.3-0.4 Sharpe, so any
    single seed can land near 1.0 by luck. Averaging across seeds is what
    actually tests that the procedure is unbiased.
    """
    sharpes = [
        walk_forward_validation(_noise(2000, seed=s), 0.0, 252, (0.0, 1.0), False)[
            "out_of_sample_sharpe"
        ]
        for s in range(6)
    ]
    assert abs(np.mean(sharpes)) < 0.6


def test_reports_an_equal_weight_benchmark_over_the_same_windows():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert "equal_weight_sharpe" in r
    assert np.isfinite(r["equal_weight_sharpe"])


def test_degradation_is_the_gap_between_in_and_out_of_sample():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert np.isclose(
        r["degradation"], r["in_sample_sharpe"] - r["out_of_sample_sharpe"]
    )


def test_reports_out_of_sample_return_and_volatility():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert np.isfinite(r["oos_return"])
    assert r["oos_vol"] > 0


# ── Statistical power of the comparison ───────────────────────────────────────

def test_standard_error_shrinks_as_the_sample_lengthens():
    short = sharpe_standard_error(1.2, n_periods=252, periods_per_year=252)
    long = sharpe_standard_error(1.2, n_periods=2520, periods_per_year=252)
    assert long < short


def test_standard_error_of_one_year_of_daily_data_is_around_one():
    """sqrt((1 + S^2/2) / years) with S=1.2 over 1 year is ~1.27."""
    se = sharpe_standard_error(1.2, n_periods=252, periods_per_year=252)
    assert 1.2 < se < 1.35


def test_validation_reports_the_standard_error_of_its_own_estimate():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert r["sharpe_stderr"] > 0


def test_four_windows_cannot_distinguish_the_optimum_from_equal_weight():
    """The gap the app warns about must exceed the noise in measuring it."""
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    gap = abs(r["equal_weight_sharpe"] - r["out_of_sample_sharpe"])
    assert gap < r["sharpe_stderr"]
    assert r["beats_equal_weight"] is None


def test_verdict_is_none_while_the_difference_stays_inside_the_noise():
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert r["beats_equal_weight"] is None


# ── Validating the other strategies ───────────────────────────────────────────

def _factor_market(n_obs: int, n_assets: int = 6, seed: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    betas = np.linspace(0.5, 1.8, n_assets)
    idio = np.linspace(0.006, 0.024, n_assets)
    factor = rng.normal(0.0004, 0.010, size=(n_obs, 1))
    return pd.DataFrame(
        factor @ betas.reshape(1, -1) + rng.normal(0, 1, (n_obs, n_assets)) * idio,
        columns=[f"A{i}" for i in range(n_assets)],
    )


def test_validation_defaults_to_max_sharpe():
    data = _factor_market(1500)
    assert (
        walk_forward_validation(data, 0.0, 252, (0.0, 1.0), False)["out_of_sample_sharpe"]
        == walk_forward_validation(
            data, 0.0, 252, (0.0, 1.0), False, strategy="max_sharpe"
        )["out_of_sample_sharpe"]
    )


@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_can_be_validated_out_of_sample(strategy):
    r = walk_forward_validation(
        _factor_market(1500), 0.0, 252, (0.0, 1.0), False, strategy=strategy
    )
    assert r is not None
    assert np.isfinite(r["out_of_sample_sharpe"])


def test_min_variance_delivers_the_lowest_out_of_sample_volatility():
    """It optimises for low risk, so it should actually deliver low risk."""
    data = _factor_market(2000)
    vols = {
        s: walk_forward_validation(data, 0.0, 252, (0.0, 1.0), False, strategy=s)["oos_vol"]
        for s in ("max_sharpe", "min_variance", "risk_parity")
    }
    assert vols["min_variance"] == min(vols.values())


def test_shrinkage_setting_is_carried_into_the_validation():
    plain = walk_forward_validation(_noise(1500), 0.0, 252, (0.0, 1.0), False, shrinkage=False)
    shrunk = walk_forward_validation(_noise(1500), 0.0, 252, (0.0, 1.0), False, shrinkage=True)
    assert shrunk["in_sample_sharpe"] < plain["in_sample_sharpe"]
