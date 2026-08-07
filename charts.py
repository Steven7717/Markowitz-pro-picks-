import numpy as np
import pandas as pd
import plotly.graph_objects as go

_DARK_BG = "#0f1117"
_CARD_BG = "#1e2130"
_ACCENT = "#7c83fd"
_GREEN = "#4ade80"
_ORANGE = "#fb923c"
_BLUE = "#60a5fa"


def _base_layout(**extra) -> dict:
    return dict(
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_CARD_BG,
        font=dict(color="#cccccc", family="sans-serif"),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        **extra,
    )


def plot_efficient_frontier(
    sim_df: pd.DataFrame,
    optimal: dict,
    benchmark: dict | None,
    equal_weight: dict,
    tickers: list[str],
    strategy_label: str = "Óptimo",
) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=sim_df["vol"],
        y=sim_df["ret"],
        mode="markers",
        marker=dict(
            color=sim_df["sharpe"],
            colorscale="Viridis",
            size=3,
            opacity=0.5,
            colorbar=dict(title="Sharpe"),
        ),
        name="Portafolios simulados",
        hovertemplate="Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=[equal_weight["annual_vol"]],
        y=[equal_weight["annual_return"]],
        mode="markers",
        marker=dict(symbol="circle", size=13, color=_BLUE, line=dict(color="white", width=1)),
        name=f"Equal Weight (Sharpe: {equal_weight['sharpe']:.2f})",
        hovertemplate="Equal Weight<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    if benchmark:
        fig.add_trace(go.Scatter(
            x=[benchmark["annual_vol"]],
            y=[benchmark["annual_return"]],
            mode="markers",
            marker=dict(symbol="triangle-up", size=15, color=_ORANGE, line=dict(color="white", width=1)),
            name=f"S&P 500 (Sharpe: {benchmark.get('sharpe', 0):.2f})",
            hovertemplate="S&P 500<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=[optimal["annual_vol"]],
        y=[optimal["annual_return"]],
        mode="markers",
        marker=dict(symbol="star", size=20, color=_GREEN, line=dict(color="white", width=1)),
        name=f"{strategy_label} (Sharpe: {optimal['sharpe']:.2f})",
        hovertemplate=f"{strategy_label}<br>Vol: %{{x:.2%}}<br>Ret: %{{y:.2%}}<extra></extra>",
    ))

    fig.update_layout(
        title="Frontera Eficiente",
        xaxis=dict(title="Volatilidad Anual", tickformat=".0%"),
        yaxis=dict(title="Retorno Anual Esperado", tickformat=".0%"),
        **_base_layout(),
    )
    return fig


def plot_weights_pie(weights: np.ndarray, tickers: list[str]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=tickers,
        values=weights,
        hole=0.35,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.2%}<extra></extra>",
    ))
    fig.update_layout(title="Distribución de Pesos Óptimos", **_base_layout())
    return fig


def plot_correlation_heatmap(returns: pd.DataFrame) -> go.Figure:
    corr = returns.corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns.tolist(),
        y=corr.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        hovertemplate="%{x} / %{y}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(title="Matriz de Correlación", **_base_layout())
    return fig


def plot_comparison(
    tickers: list[str],
    opt_weights: np.ndarray,
    ew_weights: np.ndarray,
    opt_ret: float,
    ew_ret: float,
    opt_vol: float,
    ew_vol: float,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Equal Weight",
        x=ew_weights,
        y=tickers,
        orientation="h",
        marker_color=_BLUE,
        hovertemplate="%{y}: %{x:.2%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Max Sharpe",
        x=opt_weights,
        y=tickers,
        orientation="h",
        marker_color=_GREEN,
        hovertemplate="%{y}: %{x:.2%}<extra></extra>",
    ))
    fig.update_layout(
        title=(
            f"Óptimo vs Equal Weight — "
            f"Ret: {opt_ret:.1%} vs {ew_ret:.1%} | "
            f"Vol: {opt_vol:.1%} vs {ew_vol:.1%}"
        ),
        barmode="group",
        xaxis=dict(title="Peso", tickformat=".0%"),
        **_base_layout(),
    )
    return fig
