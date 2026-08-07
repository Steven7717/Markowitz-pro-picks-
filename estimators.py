"""Robust estimators for the inputs of the Markowitz problem.

Sample means and sample covariances are noisy. A mean-variance optimiser fed with
raw sample moments does not maximise the Sharpe ratio — it maximises estimation
error, systematically loading on whichever assets got lucky in the sample. These
shrinkage estimators trade a little bias for a large reduction in variance.

References:
    Ledoit & Wolf (2004), "A Well-Conditioned Estimator for Large-Dimensional
        Covariance Matrices", Journal of Multivariate Analysis 88(2).
    Jorion (1986), "Bayes-Stein Estimation for Portfolio Analysis",
        Journal of Financial and Quantitative Analysis 21(3).
"""

import numpy as np
import pandas as pd


def ledoit_wolf_cov(returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Shrink the sample covariance toward a scaled identity matrix.

    The optimal intensity is derived analytically, so there is nothing to tune.
    Total variance (the trace) is preserved; what changes is how variance is
    distributed, and the resulting matrix is always invertible and better
    conditioned than the sample estimate.

    Returns:
        (shrunk_covariance, shrinkage_intensity) with intensity in [0, 1].
    """
    x = returns.values.astype(float)
    x = x - x.mean(axis=0)
    n_obs, n_assets = x.shape

    if n_assets == 1:
        return returns.cov().values, 0.0

    # Intensity is derived on the maximum-likelihood (1/T) covariance, per the paper.
    sample = x.T @ x / n_obs
    mean_var = np.trace(sample) / n_assets

    # Dispersion of the sample covariance around the shrinkage target.
    dispersion = np.trace(sample @ sample) / n_assets - mean_var**2

    # Expected estimation error of the sample covariance itself.
    sq_norms = np.einsum("ij,ij->i", x, x)
    error = (np.sum(sq_norms**2) / n_obs - np.trace(sample @ sample)) / (n_obs * n_assets)

    if dispersion <= 0:
        intensity = 1.0
    else:
        intensity = float(np.clip(error / dispersion, 0.0, 1.0))

    # Apply that intensity to the unbiased (ddof=1) covariance the rest of the
    # app uses, so variance conventions stay consistent everywhere.
    unbiased = returns.cov().values
    target = np.trace(unbiased) / n_assets * np.eye(n_assets)
    shrunk = intensity * target + (1.0 - intensity) * unbiased
    return shrunk, intensity


def james_stein_mean(
    returns: pd.DataFrame,
    cov_matrix: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Shrink sample mean returns toward the cross-sectional grand mean.

    Mean returns are the least reliable input in mean-variance optimisation: the
    standard error of a sample mean shrinks only with sqrt(T). Bayes-Stein pulls
    the extreme estimates in, which is what stops the optimiser from betting the
    portfolio on the single asset that happened to run hardest.

    Returns:
        (shrunk_means, shrinkage_intensity) with intensity in [0, 1].
    """
    sample_mu = returns.mean().values.astype(float)
    n_obs, n_assets = returns.shape

    if n_assets == 1:
        return sample_mu, 0.0

    if cov_matrix is None:
        cov_matrix = returns.cov().values

    grand_mean = float(sample_mu.mean())
    deviation = sample_mu - grand_mean

    # Precision-weighted size of the cross-sectional spread. pinv keeps this
    # defined even when assets are perfectly collinear.
    precision = np.linalg.pinv(cov_matrix)
    spread = float(deviation @ precision @ deviation)

    intensity = (n_assets + 2) / ((n_assets + 2) + n_obs * max(spread, 0.0))
    intensity = float(np.clip(intensity, 0.0, 1.0))

    shrunk = (1.0 - intensity) * sample_mu + intensity * grand_mean
    return shrunk, intensity


def estimate_moments(returns: pd.DataFrame, shrinkage: bool = False) -> dict:
    """Produce the (mean, covariance) pair the optimiser consumes.

    With shrinkage disabled this returns plain sample moments, preserving the
    original behaviour of the app.
    """
    if not shrinkage:
        return {
            "mean": returns.mean().values.astype(float),
            "cov": returns.cov().values,
            "cov_shrinkage": 0.0,
            "mean_shrinkage": 0.0,
        }

    cov, cov_intensity = ledoit_wolf_cov(returns)
    mean, mean_intensity = james_stein_mean(returns, cov_matrix=cov)
    return {
        "mean": mean,
        "cov": cov,
        "cov_shrinkage": cov_intensity,
        "mean_shrinkage": mean_intensity,
    }
