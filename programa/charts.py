import numpy as np
import pandas as pd
import plotly.graph_objects as go

# La paleta vive en tema.py y no aqui: antes habia tres juegos de colores --
# este, el de .streamlit/config.toml y el de los medidores-- que coincidian por
# costumbre y no por construccion, asi que cualquiera se podia mover sin que los
# otros se enterasen y la aplicacion dejaba de verse como una sola cosa.
from tema import (
    ACENTO as _ACCENT,
    AZUL as _BLUE,
    FONDO as _DARK_BG,
    NARANJA as _ORANGE,
    TARJETA as _CARD_BG,
    TEXTO as _TEXTO,
    VERDE as _GREEN,
)


def _base_layout(**extra) -> dict:
    return dict(
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_CARD_BG,
        font=dict(color=_TEXTO, family="sans-serif"),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        **extra,
    )


def _etiqueta(nombre: str, punto: dict, sin_prima: bool) -> str:
    """El nombre de un punto en la leyenda, con la cifra que de verdad lo ordena.

    **Sin prima, la leyenda no puede prometer un Sharpe.** Cuando ningún activo
    supera a la tasa libre de riesgo, `optimize_max_sharpe` devuelve la cartera
    de mínima varianza, y escribir «Máximo Sharpe (Markowitz) (Sharpe: -1,16)»
    debajo de una estrella elegida por su volatilidad es prometer un criterio
    que no se usó. Y el número que promete es además el que la nube contradice:
    medido, el 98,1% de los 10.000 puntos simulados tenía un Sharpe mayor que
    esa estrella. Ahí se escribe la volatilidad, que es lo que sí decidió.
    """
    if sin_prima:
        return f"{nombre} (vol {punto['annual_vol']:.1%} · sin prima)"
    return f"{nombre} (Sharpe: {punto.get('sharpe', 0):.2f})"


def plot_efficient_frontier(
    sim_df: pd.DataFrame,
    optimal: dict,
    benchmark: dict | None,
    equal_weight: dict,
    tickers: list[str],
    strategy_label: str = "Óptimo",
) -> go.Figure:
    """La nube de carteras simuladas y los puntos que se quieren comparar.

    **El color de la nube es el criterio con el que se eligió la estrella, y no
    el cociente de Sharpe.** Los dos coinciden mientras haya prima de riesgo
    —que es el caso normal— pero se separan justo donde importa:

    * Con prima, se colorea por `criterio_sharpe`, que es Sharpe en el tramo de
      exceso positivo y `exceso × σ` en el negativo. Las carteras que pierden
      contra las letras dejan de premiarse por ser volátiles: con el cociente a
      secas, un -2% anual repartido en un 46% de volatilidad (Sharpe -0,043)
      salía por delante de un -1% en un 12% (Sharpe -0,083), porque agrandar el
      denominador de un número negativo lo acerca a cero.
    * Sin prima —`optimal["sin_prima"]`— la cartera se ha elegido por mínima
      varianza, así que el color pasa a ser la volatilidad con la escala
      invertida: menos es mejor. Así la estrella cae necesariamente en el punto
      más brillante de la nube, que es la coherencia que faltaba.

    La columna `criterio` la escribe `simulate_portfolios` y aquí se exige: un
    respaldo silencioso a `sharpe` devolvería el gráfico al fallo de origen sin
    que nadie se enterase.
    """
    sin_prima = bool(optimal.get("sin_prima", False))
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=sim_df["vol"],
        y=sim_df["ret"],
        mode="markers",
        marker=dict(
            color=sim_df["vol"] if sin_prima else sim_df["criterio"],
            colorscale="Viridis",
            # `reversescale` y no una columna en negativo: la barra de color
            # sigue enseñando volatilidades legibles en vez de «-0,46».
            reversescale=sin_prima,
            size=3,
            opacity=0.5,
            colorbar=dict(title="Volatilidad" if sin_prima else "Sharpe"),
        ),
        name="Portafolios simulados",
        hovertemplate="Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=[equal_weight["annual_vol"]],
        y=[equal_weight["annual_return"]],
        mode="markers",
        marker=dict(symbol="circle", size=13, color=_BLUE, line=dict(color="white", width=1)),
        name=_etiqueta("Equal Weight", equal_weight, sin_prima),
        hovertemplate="Equal Weight<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    if benchmark:
        fig.add_trace(go.Scatter(
            x=[benchmark["annual_vol"]],
            y=[benchmark["annual_return"]],
            mode="markers",
            marker=dict(symbol="triangle-up", size=15, color=_ORANGE, line=dict(color="white", width=1)),
            name=_etiqueta("S&P 500", benchmark, sin_prima),
            hovertemplate="S&P 500<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=[optimal["annual_vol"]],
        y=[optimal["annual_return"]],
        mode="markers",
        marker=dict(symbol="star", size=20, color=_GREEN, line=dict(color="white", width=1)),
        name=_etiqueta(strategy_label, optimal, sin_prima),
        hovertemplate=f"{strategy_label}<br>Vol: %{{x:.2%}}<br>Ret: %{{y:.2%}}<extra></extra>",
    ))

    fig.update_layout(
        # El porqué del cambio de escala va en el título y no en la leyenda:
        # una leyenda con la explicación dentro se corta por la mitad, y el
        # usuario tiene que entender el color antes de mirar ningún punto.
        title=(
            "Frontera Eficiente — sin prima de riesgo: el color es la "
            "volatilidad (menos es mejor), no el Sharpe"
            if sin_prima else "Frontera Eficiente"
        ),
        xaxis=dict(title="Volatilidad Anual", tickformat=".0%"),
        yaxis=dict(title="Retorno Anual Esperado", tickformat=".0%"),
        **_base_layout(),
    )
    return fig


def plot_weights_pie(weights: np.ndarray, tickers: list[str]) -> go.Figure:
    # `texttemplate` y no `textinfo="label+percent"`: el formato de por defecto
    # de Plotly para el porcentaje es de digitos significativos, y un activo que
    # el optimizador deja fuera no pesa 0 sino 7.7e-16 -- asi que al lado del
    # ticker aparecia "CSGP 7.67e-16%", que no se lee como "cero" sino como un
    # fallo del programa. Con decimales fijos sale "0.0%", que es lo que es.
    fig = go.Figure(go.Pie(
        labels=tickers,
        values=weights,
        hole=0.35,
        texttemplate="%{label}<br>%{percent:.1%}",
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
