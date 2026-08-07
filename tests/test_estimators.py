import numpy as np
import pandas as pd
import pytest

from estimators import estimate_moments, james_stein_mean, ledoit_wolf_cov


def _structured_returns(n_obs: int, n_assets: int, seed: int) -> pd.DataFrame:
    """Returns with a market factor and heterogeneous idiosyncratic risk.

    Real equity returns are correlated and have unequal variances. Purely i.i.d.
    returns are exactly the shrinkage target, so they make shrinkage tests
    degenerate — every estimator correctly reports 100% shrinkage.
    """
    rng = np.random.default_rng(seed)
    betas = np.linspace(0.6, 1.6, n_assets)
    idio_vol = np.linspace(0.008, 0.022, n_assets)
    market = rng.normal(0.0004, 0.011, size=(n_obs, 1))
    idio = rng.normal(0.0, 1.0, size=(n_obs, n_assets)) * idio_vol
    data = market @ betas.reshape(1, -1) + idio
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


@pytest.fixture
def noisy_returns() -> pd.DataFrame:
    """8 assets, only 60 observations — the regime where sample cov is unreliable."""
    return _structured_returns(n_obs=60, n_assets=8, seed=7)


@pytest.fixture
def ample_returns() -> pd.DataFrame:
    """Same population as noisy_returns but 3000 observations, isolating sample size."""
    return _structured_returns(n_obs=3000, n_assets=8, seed=11)


# ── Ledoit-Wolf covariance shrinkage ──────────────────────────────────────────

def test_ledoit_wolf_returns_square_matrix_matching_asset_count(noisy_returns):
    cov, _ = ledoit_wolf_cov(noisy_returns)
    assert cov.shape == (8, 8)


def test_ledoit_wolf_intensity_is_a_valid_proportion(noisy_returns):
    _, delta = ledoit_wolf_cov(noisy_returns)
    assert 0.0 <= delta <= 1.0


def test_ledoit_wolf_preserves_total_variance(noisy_returns):
    """Shrinkage redistributes variance across assets but must not create or destroy it."""
    cov, _ = ledoit_wolf_cov(noisy_returns)
    assert np.isclose(np.trace(cov), np.trace(noisy_returns.cov().values))


def test_ledoit_wolf_result_is_symmetric(noisy_returns):
    cov, _ = ledoit_wolf_cov(noisy_returns)
    assert np.allclose(cov, cov.T)


def test_ledoit_wolf_is_positive_definite_when_sample_cov_is_singular():
    """10 assets from 5 observations: sample cov has rank 4, shrunk cov must be invertible."""
    rng = np.random.default_rng(3)
    r = pd.DataFrame(rng.normal(0, 0.01, size=(5, 10)))
    sample_eigs = np.linalg.eigvalsh(r.cov().values)
    shrunk, _ = ledoit_wolf_cov(r)
    shrunk_eigs = np.linalg.eigvalsh(shrunk)
    assert sample_eigs.min() < 1e-10
    assert shrunk_eigs.min() > 1e-10


def test_ledoit_wolf_improves_condition_number(noisy_returns):
    sample_cond = np.linalg.cond(noisy_returns.cov().values)
    shrunk, _ = ledoit_wolf_cov(noisy_returns)
    assert np.linalg.cond(shrunk) < sample_cond


def test_ledoit_wolf_shrinks_less_when_more_data_is_available(noisy_returns, ample_returns):
    _, delta_scarce = ledoit_wolf_cov(noisy_returns)
    _, delta_ample = ledoit_wolf_cov(ample_returns)
    assert delta_ample < delta_scarce


def test_ledoit_wolf_intensity_matches_sklearn_reference(noisy_returns):
    """Cross-check our native implementation against the reference implementation."""
    sk = pytest.importorskip("sklearn.covariance")
    expected = sk.ledoit_wolf_shrinkage(noisy_returns.values)
    _, delta = ledoit_wolf_cov(noisy_returns)
    assert np.isclose(delta, expected, atol=1e-10)


# ── James-Stein / Bayes-Stein mean shrinkage ──────────────────────────────────

def test_james_stein_intensity_is_a_valid_proportion(noisy_returns):
    _, delta = james_stein_mean(noisy_returns)
    assert 0.0 <= delta <= 1.0


def test_james_stein_preserves_the_grand_mean(noisy_returns):
    """Shrinking toward the grand mean must not move the grand mean itself."""
    shrunk, _ = james_stein_mean(noisy_returns)
    assert np.isclose(shrunk.mean(), noisy_returns.mean().values.mean())


def test_james_stein_reduces_cross_sectional_dispersion(noisy_returns):
    sample_mu = noisy_returns.mean().values
    shrunk, _ = james_stein_mean(noisy_returns)
    assert shrunk.std() < sample_mu.std()


def test_james_stein_pulls_every_asset_toward_the_grand_mean(noisy_returns):
    sample_mu = noisy_returns.mean().values
    grand = sample_mu.mean()
    shrunk, _ = james_stein_mean(noisy_returns)
    for original, moved in zip(sample_mu, shrunk):
        assert min(original, grand) - 1e-12 <= moved <= max(original, grand) + 1e-12


def test_james_stein_leaves_already_identical_means_unchanged():
    rng = np.random.default_rng(5)
    base = rng.normal(0, 0.01, size=(400, 1))
    r = pd.DataFrame(np.hstack([base, base, base]), columns=list("XYZ"))
    shrunk, _ = james_stein_mean(r)
    assert np.allclose(shrunk, r.mean().values, atol=1e-12)


# ── Combined moment estimation ────────────────────────────────────────────────

def test_estimate_moments_without_shrinkage_returns_plain_sample_moments(noisy_returns):
    m = estimate_moments(noisy_returns, shrinkage=False)
    assert np.allclose(m["mean"], noisy_returns.mean().values)
    assert np.allclose(m["cov"], noisy_returns.cov().values)


def test_estimate_moments_without_shrinkage_reports_zero_intensity(noisy_returns):
    m = estimate_moments(noisy_returns, shrinkage=False)
    assert m["cov_shrinkage"] == 0.0
    assert m["mean_shrinkage"] == 0.0


def test_estimate_moments_with_shrinkage_changes_both_moments(noisy_returns):
    m = estimate_moments(noisy_returns, shrinkage=True)
    assert not np.allclose(m["mean"], noisy_returns.mean().values)
    assert not np.allclose(m["cov"], noisy_returns.cov().values)


def test_estimate_moments_with_shrinkage_reports_positive_intensities(noisy_returns):
    m = estimate_moments(noisy_returns, shrinkage=True)
    assert m["cov_shrinkage"] > 0.0
    assert m["mean_shrinkage"] > 0.0
