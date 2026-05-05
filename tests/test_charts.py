import numpy as np
import pandas as pd
import plotly.graph_objects as go
from charts import (
    plot_efficient_frontier,
    plot_weights_pie,
    plot_correlation_heatmap,
    plot_comparison,
)


def _sim_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 200
    return pd.DataFrame({
        "ret": rng.uniform(0.05, 0.30, n),
        "vol": rng.uniform(0.05, 0.35, n),
        "sharpe": rng.uniform(0.5, 2.5, n),
    })


def _returns() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.normal(0.001, 0.015, (252, 3)),
        columns=["AAPL", "MSFT", "GOOGL"],
    )


def test_plot_efficient_frontier_returns_figure():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark={"annual_return": 0.12, "annual_vol": 0.16, "sharpe": 0.75},
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 3


def test_plot_efficient_frontier_no_benchmark():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark=None,
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)


def test_plot_weights_pie_returns_figure():
    fig = plot_weights_pie(np.array([0.5, 0.3, 0.2]), ["AAPL", "MSFT", "GOOGL"])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_correlation_heatmap_returns_figure():
    fig = plot_correlation_heatmap(_returns())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_comparison_returns_figure():
    fig = plot_comparison(
        tickers=["AAPL", "MSFT", "GOOGL"],
        opt_weights=np.array([0.5, 0.3, 0.2]),
        ew_weights=np.array([1/3, 1/3, 1/3]),
        opt_ret=0.18,
        ew_ret=0.13,
        opt_vol=0.14,
        ew_vol=0.15,
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
