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


# ── The chart must name the strategy actually plotted ─────────────────────────

def _frontier(**kw):
    return plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3,
                 "weights": np.array([0.5, 0.3, 0.2])},
        benchmark=None,
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
        **kw,
    )


def test_frontier_marker_defaults_to_a_generic_optimum_label():
    names = [t.name for t in _frontier().data]
    assert any("Óptimo" in n for n in names)


def test_frontier_marker_uses_the_supplied_strategy_label():
    names = [t.name for t in _frontier(strategy_label="Mínima varianza").data]
    assert any("Mínima varianza" in n for n in names)


def test_frontier_marker_still_shows_the_sharpe_ratio():
    names = [t.name for t in _frontier(strategy_label="Paridad de riesgo").data]
    assert any("Sharpe" in n for n in names)


def test_la_tarta_no_escribe_los_pesos_nulos_en_notacion_cientifica():
    """Un activo que se queda fuera pesa 7.7e-16, no 0, y se veía como tal.

    `textinfo="label+percent"` deja el formato al de por defecto de Plotly, que
    es de dígitos significativos (`~%`): al lado del ticker salía
    «CSGP 7.67e-16%», que no se lee como «cero» sino como un fallo. Con
    decimales fijos sale «0.0%», que es lo que ese peso es.
    """
    fig = plot_weights_pie(np.array([0.6, 0.4, 7.67e-16]), ["AAA", "BBB", "CCC"])
    trazo = fig.data[0]
    assert trazo.texttemplate is not None, "sin plantilla el formato lo elige Plotly"
    assert "%{percent:." in trazo.texttemplate


def test_la_tarta_sigue_etiquetando_cada_porcion_con_su_ticker():
    trazo = plot_weights_pie(np.array([0.5, 0.5]), ["AAA", "BBB"]).data[0]
    assert "%{label}" in trazo.texttemplate


def test_la_tarta_no_deja_dos_formatos_compitiendo():
    """`textinfo` y `texttemplate` se pisan; que quede sólo el que manda."""
    trazo = plot_weights_pie(np.array([0.5, 0.5]), ["AAA", "BBB"]).data[0]
    assert trazo.textinfo is None
