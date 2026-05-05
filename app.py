import numpy as np
import pandas as pd
import streamlit as st

from charts import (
    plot_comparison,
    plot_correlation_heatmap,
    plot_efficient_frontier,
    plot_weights_pie,
)
from data import (
    DEFAULT_HORIZON,
    HORIZON_CONFIG,
    RF_FALLBACK,
    fetch_market_data,
    parse_tickers,
)
from exporter import to_excel, to_pdf
from optimizer import (
    equal_weight_portfolio,
    optimize_max_sharpe,
    simulate_portfolios,
    validate_constraints,
)

st.set_page_config(
    page_title="Markowitz Pro Picks",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Markowitz Pro Picks")
st.caption("Optimización de portafolio — Máximo Sharpe Ratio (Markowitz)")

# ── Configuration panel ───────────────────────────────────────────────────────
with st.container():
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        raw_tickers = st.text_input(
            "Tickers (separados por coma o espacio)",
            value="AAPL, MSFT, GOOGL, AMZN, NVDA",
        )
    with col2:
        horizon = st.selectbox(
            "Horizonte de inversión",
            options=list(HORIZON_CONFIG.keys()),
            index=list(HORIZON_CONFIG.keys()).index(DEFAULT_HORIZON),
        )
    with col3:
        allow_short = st.toggle("Short selling", value=False)

    col4, col5, col6 = st.columns([1, 1, 1])
    with col4:
        weight_min = st.slider("Peso mínimo por activo (%)", 0, 20, 0) / 100
    with col5:
        weight_max = st.slider("Peso máximo por activo (%)", 20, 100, 100) / 100
    with col6:
        st.write("")
        st.write("")
        optimize_btn = st.button("▶ Optimizar", type="primary", use_container_width=True)

if not optimize_btn:
    st.info("Ingresa los tickers y presiona **▶ Optimizar** para calcular el portafolio óptimo.")
    st.stop()

# ── Parse and validate tickers ────────────────────────────────────────────────
tickers = parse_tickers(raw_tickers)
if not tickers:
    st.error("🔴 Ingresa al menos 2 tickers.")
    st.stop()

# ── Fetch market data ─────────────────────────────────────────────────────────
with st.spinner("Descargando datos de mercado..."):
    market = fetch_market_data(tuple(tickers), horizon)

if market["invalid_tickers"]:
    st.warning(f"⚠️ Tickers no encontrados y omitidos: {', '.join(market['invalid_tickers'])}")

valid_tickers = market["valid_tickers"]
if len(valid_tickers) < 2:
    st.error("🔴 Se necesitan al menos 2 tickers válidos para optimizar el portafolio.")
    st.stop()

if not market.get("rf_available", True):
    st.warning(
        f"⚠️ ^IRX no disponible. Usando tasa libre de riesgo de referencia: {RF_FALLBACK:.1%} anual."
    )

returns = market["returns"]
rf_rate = market["rf_rate"]
periods_per_year = market["periods_per_year"]

# ── Validate weight constraints ───────────────────────────────────────────────
feasible, msg = validate_constraints(len(valid_tickers), weight_min, weight_max)
if not feasible:
    st.error(f"🔴 {msg}")
    st.stop()

# ── Run optimization ──────────────────────────────────────────────────────────
weight_bounds = (weight_min, weight_max)
with st.spinner("Optimizando portafolio..."):
    sim_df = simulate_portfolios(returns, rf_rate, periods_per_year, weight_bounds, allow_short)
    optimal = optimize_max_sharpe(returns, rf_rate, periods_per_year, weight_bounds, allow_short)
    ew = equal_weight_portfolio(returns, rf_rate, periods_per_year)

if not optimal["converged"]:
    st.error(
        f"🔴 La optimización no convergió: {optimal['message']}. "
        "Revisa activos muy correlacionados o ajusta los límites de posición."
    )
    st.stop()

# ── Benchmark metrics ─────────────────────────────────────────────────────────
benchmark = None
if not market["benchmark_returns"].empty:
    bm = market["benchmark_returns"]
    bm_ret = float(bm.mean() * periods_per_year)
    bm_vol = float(bm.std() * np.sqrt(periods_per_year))
    bm_sharpe = float((bm_ret - rf_rate * periods_per_year) / bm_vol) if bm_vol > 0 else 0.0
    benchmark = {"annual_return": bm_ret, "annual_vol": bm_vol, "sharpe": bm_sharpe}

# ── KPI cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sharpe Ratio", f"{optimal['sharpe']:.4f}")
k2.metric("Retorno Anual Esperado", f"{optimal['annual_return']:.2%}")
k3.metric("Volatilidad Anual", f"{optimal['annual_vol']:.2%}")
k4.metric("Tasa Libre de Riesgo", f"{rf_rate * periods_per_year:.2%}")

# ── Concentration warning ─────────────────────────────────────────────────────
max_w = float(optimal["weights"].max())
if max_w > 0.50:
    top = valid_tickers[int(optimal["weights"].argmax())]
    st.warning(
        f"⚠️ Alta concentración: **{top}** recibe **{max_w:.1%}** del portafolio. "
        "Considera establecer un peso máximo menor."
    )

# ── Build shared data structures ──────────────────────────────────────────────
weights_df = pd.DataFrame({
    "Ticker": valid_tickers,
    "Peso Óptimo (%)": [f"{w:.2%}" for w in optimal["weights"]],
    "Retorno Esperado (%)": [
        f"{returns[t].mean() * periods_per_year:.2%}" for t in valid_tickers
    ],
    "Volatilidad (%)": [
        f"{returns[t].std() * np.sqrt(periods_per_year):.2%}" for t in valid_tickers
    ],
    "Contrib. Riesgo (%)": [f"{c:.2%}" for c in optimal["risk_contribution"]],
})

metrics = {
    "sharpe": optimal["sharpe"],
    "annual_return": optimal["annual_return"],
    "annual_vol": optimal["annual_vol"],
    "rf_rate": rf_rate * periods_per_year,
    "horizon": horizon,
}

fig_frontier = plot_efficient_frontier(sim_df, optimal, benchmark, ew, valid_tickers)
fig_pie = plot_weights_pie(optimal["weights"], valid_tickers)
fig_corr = plot_correlation_heatmap(returns)
fig_comp = plot_comparison(
    valid_tickers,
    optimal["weights"],
    ew["weights"],
    optimal["annual_return"],
    ew["annual_return"],
    optimal["annual_vol"],
    ew["annual_vol"],
)

# ── Export buttons ────────────────────────────────────────────────────────────
ex_col, pdf_col = st.columns(2)
with ex_col:
    st.download_button(
        label="⬇ Descargar Excel",
        data=to_excel(weights_df, metrics),
        file_name=f"markowitz_{horizon.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with pdf_col:
    st.download_button(
        label="⬇ Descargar PDF",
        data=to_pdf(weights_df, metrics, [fig_frontier, fig_pie, fig_corr, fig_comp]),
        file_name=f"markowitz_{horizon.replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

# ── Charts 2×2 ────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(fig_frontier, use_container_width=True)
with c2:
    st.plotly_chart(fig_pie, use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.plotly_chart(fig_corr, use_container_width=True)
with c4:
    st.plotly_chart(fig_comp, use_container_width=True)

# ── Weights table ─────────────────────────────────────────────────────────────
st.subheader("📋 Tabla de Pesos Óptimos")
st.dataframe(weights_df, use_container_width=True, hide_index=True)
