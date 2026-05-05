import numpy as np
import pandas as pd
from scipy.optimize import minimize

N_SIMULATIONS = 10_000


def portfolio_metrics(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> tuple[float, float, float]:
    port_return = float(np.dot(weights, mean_returns) * periods_per_year)
    port_vol = float(np.sqrt(weights @ cov_matrix @ weights) * np.sqrt(periods_per_year))
    rf_annual = rf_rate * periods_per_year
    sharpe = float((port_return - rf_annual) / port_vol) if port_vol > 0 else 0.0
    return port_return, port_vol, sharpe


def risk_contribution(weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
    port_variance = float(weights @ cov_matrix @ weights)
    if port_variance <= 0:
        return np.zeros_like(weights)
    marginal = cov_matrix @ weights
    contrib = weights * marginal
    return contrib / port_variance


def validate_constraints(
    n_assets: int,
    weight_min: float,
    weight_max: float,
) -> tuple[bool, str]:
    if weight_min * n_assets > 1.0 + 1e-6:
        return False, (
            f"Restricción infactible: peso mínimo ({weight_min:.0%}) × "
            f"{n_assets} activos = {weight_min * n_assets:.0%} > 100%"
        )
    if weight_max * n_assets < 1.0 - 1e-6:
        return False, (
            f"Restricción infactible: peso máximo ({weight_max:.0%}) × "
            f"{n_assets} activos = {weight_max * n_assets:.0%} < 100%"
        )
    return True, "OK"


def simulate_portfolios(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
) -> pd.DataFrame:
    n = len(returns.columns)
    mean_returns = returns.mean().values
    cov_matrix = returns.cov().values
    lb, ub = weight_bounds
    rng = np.random.default_rng(42)
    rows = []

    for _ in range(N_SIMULATIONS):
        if allow_short:
            w = rng.standard_normal(n)
        else:
            w = rng.dirichlet(np.ones(n))

        w = np.clip(w, lb, ub)
        total = w.sum()
        if total == 0:
            continue
        w = w / total

        ret, vol, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        rows.append({"ret": ret, "vol": vol, "sharpe": sharpe})

    return pd.DataFrame(rows)
