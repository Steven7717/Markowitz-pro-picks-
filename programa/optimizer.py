import numpy as np
import pandas as pd
from scipy.optimize import minimize

from estimators import estimate_moments

N_SIMULATIONS = 10_000
_N_RANDOM_STARTS = 12


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


def effective_bounds(
    weight_bounds: tuple[float, float],
    allow_short: bool,
) -> tuple[float, float]:
    """The single source of truth for the feasible set.

    Under short selling the minimum-weight slider has no meaning — a floor of
    "at least 5% of every asset" contradicts taking short positions. The maximum
    slider is reinterpreted as a cap on absolute position size in either
    direction, so the constraint the user set still binds.
    """
    weight_min, weight_max = weight_bounds
    if allow_short:
        return -weight_max, weight_max
    return weight_min, weight_max


def project_to_bounds(weights: np.ndarray, lb: float, ub: float) -> np.ndarray:
    """Project weights onto {w : sum(w) = 1, lb <= w <= ub}.

    Clipping and then renormalizing does NOT do this — dividing by the sum pushes
    weights straight back out of range. Here any shortfall or excess is absorbed
    only by the coordinates that still have room for it, so the sum constraint and
    the box constraint hold simultaneously.
    """
    w = np.clip(np.asarray(weights, dtype=float), lb, ub)
    for _ in range(64):
        gap = 1.0 - w.sum()
        if abs(gap) < 1e-12:
            break
        room = (ub - w) if gap > 0 else (w - lb)
        total_room = room.sum()
        if total_room <= 1e-15:
            break
        w = np.clip(w + gap * (room / total_room), lb, ub)
    return w


def sample_feasible_weights(
    n_assets: int,
    lb: float,
    ub: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw one random portfolio that actually satisfies the constraints."""
    if lb < 0:
        # Spread around equal weight without dividing by a sum that may be near zero.
        raw = rng.standard_normal(n_assets)
        raw = raw - raw.mean() + 1.0 / n_assets
    else:
        raw = rng.dirichlet(np.ones(n_assets))
    return project_to_bounds(raw, lb, ub)


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
    shrinkage: bool = False,
) -> pd.DataFrame:
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage)
    mean_returns, cov_matrix = moments["mean"], moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)
    rng = np.random.default_rng(42)
    rows = []

    for _ in range(N_SIMULATIONS):
        w = sample_feasible_weights(n, lb, ub, rng)
        ret, vol, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        rows.append({
            "ret": ret,
            "vol": vol,
            "sharpe": sharpe,
            "min_weight": float(w.min()),
            "max_weight": float(w.max()),
        })

    return pd.DataFrame(rows)


def _start_points(n: int, lb: float, ub: float) -> list[np.ndarray]:
    """Equal weight, each single-asset corner, and some random feasible points.

    The Sharpe ratio is a non-convex objective, so a single starting point can
    leave SLSQP parked on a local optimum.
    """
    starts = [project_to_bounds(np.ones(n) / n, lb, ub)]
    for i in range(n):
        corner = np.full(n, max(lb, 0.0))
        corner[i] = ub
        starts.append(project_to_bounds(corner, lb, ub))
    rng = np.random.default_rng(1234)
    starts.extend(sample_feasible_weights(n, lb, ub, rng) for _ in range(_N_RANDOM_STARTS))
    return starts


def optimize_max_sharpe(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
) -> dict:
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage)
    mean_returns, cov_matrix = moments["mean"], moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)

    def neg_sharpe(w: np.ndarray) -> float:
        _, _, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        return -sharpe

    bounds = [(lb, ub)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    best_w, best_sharpe = None, -np.inf
    for x0 in _start_points(n, lb, ub):
        # The start point is itself a feasible candidate, which guarantees the
        # result can never be worse than equal weight.
        _, _, s0 = portfolio_metrics(x0, mean_returns, cov_matrix, rf_rate, periods_per_year)
        if s0 > best_sharpe:
            best_w, best_sharpe = x0, s0

        result = minimize(
            neg_sharpe,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-9},
        )
        if not result.success:
            continue
        w = project_to_bounds(result.x, lb, ub)
        _, _, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        if sharpe > best_sharpe:
            best_w, best_sharpe = w, sharpe

    if best_w is None:
        return {"converged": False, "message": "SLSQP no encontró una solución factible"}

    ret, vol, sharpe = portfolio_metrics(best_w, mean_returns, cov_matrix, rf_rate, periods_per_year)
    return {
        "converged": True,
        "weights": best_w,
        "annual_return": ret,
        "annual_vol": vol,
        "sharpe": sharpe,
        "risk_contribution": risk_contribution(best_w, cov_matrix),
        "cov_shrinkage": moments["cov_shrinkage"],
        "mean_shrinkage": moments["mean_shrinkage"],
        "message": "OK",
    }


def _result(
    weights: np.ndarray,
    moments: dict,
    rf_rate: float,
    periods_per_year: int,
) -> dict:
    ret, vol, sharpe = portfolio_metrics(
        weights, moments["mean"], moments["cov"], rf_rate, periods_per_year
    )
    return {
        "converged": True,
        "weights": weights,
        "annual_return": ret,
        "annual_vol": vol,
        "sharpe": sharpe,
        "risk_contribution": risk_contribution(weights, moments["cov"]),
        "cov_shrinkage": moments["cov_shrinkage"],
        "mean_shrinkage": moments["mean_shrinkage"],
        "message": "OK",
    }


def optimize_min_variance(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
) -> dict:
    """The portfolio with the smallest possible variance.

    Expected returns are never consulted. That is the point: mean returns carry
    almost all of the estimation error in mean-variance optimisation, so a
    portfolio that ignores them is far more stable out of sample. The trade-off
    is that it makes no attempt to earn a return — it only avoids risk.
    """
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage)
    cov = moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)

    result = minimize(
        lambda w: float(w @ cov @ w),
        project_to_bounds(np.ones(n) / n, lb, ub),
        method="SLSQP",
        bounds=[(lb, ub)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}],
        options={"maxiter": 1000, "ftol": 1e-14},
    )
    if not result.success:
        return {"converged": False, "message": result.message}

    return _result(project_to_bounds(result.x, lb, ub), moments, rf_rate, periods_per_year)


def optimize_risk_parity(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool = False,
    shrinkage: bool = False,
) -> dict:
    """Equal Risk Contribution: every asset supplies the same share of the risk.

    Equal *money* is not equal *risk* — in an equally weighted portfolio a volatile
    asset quietly dominates the total variance. This balances the contributions
    instead of the amounts, using only the covariance matrix, so expected returns
    never enter. Short positions are excluded because a negative weight makes the
    notion of a risk contribution meaningless.
    """
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage)
    cov = moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short=False)
    lb = max(lb, 0.0)
    target = 1.0 / n

    def dispersion(w: np.ndarray) -> float:
        variance = float(w @ cov @ w)
        if variance <= 0:
            return 1e6
        contributions = w * (cov @ w) / variance
        return float(np.sum((contributions - target) ** 2))

    result = minimize(
        dispersion,
        project_to_bounds(np.ones(n) / n, lb, ub),
        method="SLSQP",
        bounds=[(lb, ub)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}],
        options={"maxiter": 2000, "ftol": 1e-16},
    )
    if not result.success:
        return {"converged": False, "message": result.message}

    return _result(project_to_bounds(result.x, lb, ub), moments, rf_rate, periods_per_year)


STRATEGY_LABELS: dict[str, str] = {
    "max_sharpe": "Máximo Sharpe (Markowitz)",
    "min_variance": "Mínima varianza",
    "risk_parity": "Paridad de riesgo (ERC)",
}

_STRATEGIES = {
    "max_sharpe": optimize_max_sharpe,
    "min_variance": optimize_min_variance,
    "risk_parity": optimize_risk_parity,
}


def optimize_portfolio(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    strategy: str = "max_sharpe",
    shrinkage: bool = False,
) -> dict:
    """Run one of the available allocation strategies behind a common interface."""
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"Estrategia desconocida: {strategy!r}. "
            f"Opciones válidas: {', '.join(_STRATEGIES)}"
        )
    return _STRATEGIES[strategy](
        returns, rf_rate, periods_per_year, weight_bounds, allow_short, shrinkage=shrinkage
    )


def equal_weight_portfolio(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    shrinkage: bool = False,
) -> dict:
    n = len(returns.columns)
    weights = np.ones(n) / n
    moments = estimate_moments(returns, shrinkage=shrinkage)
    ret, vol, sharpe = portfolio_metrics(
        weights, moments["mean"], moments["cov"], rf_rate, periods_per_year
    )
    return {"weights": weights, "annual_return": ret, "annual_vol": vol, "sharpe": sharpe}
