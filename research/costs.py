import pandas as pd

COST_SCENARIOS: dict[str, float] = {
    "optimista": 5.0,
    "base": 10.0,
    "conservador": 25.0,
}


def turnover_from_weights(weights: pd.DataFrame) -> pd.Series:
    """Fraction of the portfolio traded each period.

    Half the sum of absolute weight changes: selling 100% of one name to buy
    another moves 200% of weight but only trades the portfolio once. The first
    period counts as a full trade, because the position has to be built.
    """
    previous = weights.shift(1)
    first_period = previous.isna().all(axis=1)
    traded = (weights - previous.fillna(0.0)).abs().sum(axis=1) / 2.0
    return traded.where(~first_period, weights.abs().sum(axis=1))


def apply_costs(gross_returns: pd.Series, turnover: pd.Series, bps: float) -> pd.Series:
    """Charge `bps` per unit of turnover, round trip.

    High-turnover signals live or die here, so gross and net are always reported
    side by side rather than collapsed into one number.
    """
    return gross_returns - turnover.reindex(gross_returns.index).fillna(0.0) * (bps / 10_000.0)
