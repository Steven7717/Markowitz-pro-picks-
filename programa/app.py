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
    STRATEGY_LABELS,
    equal_weight_portfolio,
    optimize_portfolio,
    simulate_portfolios,
    validate_constraints,
)
from validation import walk_forward_validation

st.set_page_config(
    page_title="Markowitz Pro Picks",
    # Ruta relativa: el lanzador entra en programa/ antes de arrancar, asi que
    # resuelve. Streamlit lo pasa por PIL, que lee .ico sin problema.
    page_icon="icono.ico",
    layout="wide",
)

st.title("📈 Markowitz Pro Picks")
st.caption("Optimización de portafolio con validación fuera de muestra")

with st.expander("📚 ¿Qué hace cada estrategia?"):
    st.markdown(
        """
**Máximo Sharpe (Markowitz)** — Busca la mejor relación entre retorno y riesgo.

Usa dos inputs: los **retornos esperados** y la **matriz de covarianzas**. Es la más
ambiciosa y también la más frágil, porque los retornos esperados son casi imposibles
de estimar: el error típico de una media muestral solo baja con la raíz del número de
observaciones. El optimizador no distingue entre "este activo rinde más" y "este activo
tuvo suerte en la muestra", así que amplifica ese error. Por eso concentra el portafolio
en pocos activos y reporta un Sharpe inflado.

---

**Mínima varianza** — Busca el portafolio menos volátil posible, sin más.

**No usa retornos esperados en absoluto**: solo la matriz de covarianzas. Ese es
justamente su punto fuerte, porque elimina de raíz la fuente principal de error de
estimación. Las covarianzas se estiman bastante mejor que las medias. A cambio, no
intenta ganar nada: solo evitar riesgo. Suele dar el portafolio más estable en el
tiempo (menos rotación), pero puede quedarse atrás en mercados alcistas.

---

**Paridad de riesgo (ERC)** — Que cada activo aporte la misma cantidad de riesgo.

Tampoco usa retornos esperados. Parte de una observación incómoda: repartir el **dinero**
por igual no reparte el **riesgo** por igual. Si tenés 5 activos al 20% cada uno y uno
es el doble de volátil que el resto, ese activo aporta mucho más que el 20% de la
volatilidad total — domina el portafolio sin que se note en la tabla de pesos. ERC
resuelve el peso de cada activo para que todos contribuyan lo mismo al riesgo, lo que
en la práctica significa **más peso a los activos calmos y menos a los volátiles**.

---

**Equal Weight (1/N)** — Repartir por igual, sin optimizar nada. No es una opción del
selector: aparece siempre como referencia. Si una estrategia no le gana a esto fuera de
muestra, la optimización no está aportando información.
        """
    )

# ── Configuration panel ───────────────────────────────────────────────────────
TICKERS_POR_DEFECTO = "AAPL, MSFT, GOOGL, AMZN, NVDA"

with st.container():
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        raw_tickers = st.text_input(
            "Tickers (separados por coma o espacio)",
            value=", ".join(
                st.session_state.get("tickers_aprobados", [])
            ) or TICKERS_POR_DEFECTO,
        )
    with col2:
        horizon = st.selectbox(
            "Horizonte de inversión",
            options=list(HORIZON_CONFIG.keys()),
            index=list(HORIZON_CONFIG.keys()).index(DEFAULT_HORIZON),
        )
    with col3:
        allow_short = st.toggle("Short selling", value=False)

    strategy = st.radio(
        "Estrategia",
        options=list(STRATEGY_LABELS.keys()),
        format_func=lambda k: STRATEGY_LABELS[k],
        horizontal=True,
        help="Mínima varianza y paridad de riesgo NO usan retornos esperados, "
             "que es donde vive casi todo el error de estimación.",
    )

    col4, col5, col6 = st.columns([1, 1, 1])
    with col4:
        weight_min = st.slider(
            "Peso mínimo por activo (%)", 0, 20, 0,
            disabled=allow_short,
            help="No aplica con short selling: el límite pasa a ser simétrico (±peso máximo).",
        ) / 100
    with col5:
        weight_max = st.slider(
            "Peso máximo por activo (%)", 20, 100, 100,
            help="Con short selling activo, limita el tamaño absoluto de cada posición (±).",
        ) / 100
    with col6:
        st.write("")
        st.write("")
        optimize_btn = st.button("▶ Optimizar", type="primary", use_container_width=True)

    use_shrinkage = st.toggle(
        "Estimación robusta (shrinkage Ledoit-Wolf + Bayes-Stein)",
        value=True,
        help=(
            "Corrige el sesgo optimista de Markowitz. Con medias y covarianzas muestrales "
            "crudas el optimizador maximiza el error de estimación, no el Sharpe: sobre "
            "activos de puro ruido (retorno esperado real = 0) llega a reportar Sharpe 3.4. "
            "Desactívalo solo para comparar con el método clásico."
        ),
    )

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
n_obs = market["n_obs"]

# ── Sample-size guard ─────────────────────────────────────────────────────────
# The sample covariance needs roughly 30-50 observations per asset before it is
# stable enough to invert. Below that the optimiser fits noise.
obs_per_asset = n_obs / len(valid_tickers) if valid_tickers else 0
if obs_per_asset < 10:
    st.error(
        f"🔴 Datos insuficientes: {n_obs} observaciones para {len(valid_tickers)} activos "
        f"({obs_per_asset:.0f} por activo). La matriz de covarianza es prácticamente singular "
        "y el resultado no es interpretable. Usa menos activos o un horizonte con datos diarios."
    )
    st.stop()
if obs_per_asset < 30:
    st.warning(
        f"⚠️ Muestra corta: {n_obs} observaciones para {len(valid_tickers)} activos "
        f"({obs_per_asset:.0f} por activo, recomendado >30). Los pesos serán inestables: "
        "pequeños cambios en los datos moverán mucho el portafolio."
    )

# ── Validate weight constraints ───────────────────────────────────────────────
feasible, msg = validate_constraints(len(valid_tickers), weight_min, weight_max)
if not feasible:
    st.error(f"🔴 {msg}")
    st.stop()

# ── Run optimization ──────────────────────────────────────────────────────────
weight_bounds = (weight_min, weight_max)
with st.spinner("Optimizando portafolio..."):
    sim_df = simulate_portfolios(
        returns, rf_rate, periods_per_year, weight_bounds, allow_short, shrinkage=use_shrinkage
    )
    optimal = optimize_portfolio(
        returns, rf_rate, periods_per_year, weight_bounds, allow_short,
        strategy=strategy, shrinkage=use_shrinkage,
    )
    ew = equal_weight_portfolio(returns, rf_rate, periods_per_year, shrinkage=use_shrinkage)

with st.spinner("Validando fuera de muestra (walk-forward)..."):
    wf = walk_forward_validation(
        returns, rf_rate, periods_per_year, weight_bounds, allow_short,
        strategy=strategy, shrinkage=use_shrinkage,
    )
    all_strategies = {
        name: walk_forward_validation(
            returns, rf_rate, periods_per_year, weight_bounds, allow_short,
            strategy=name, shrinkage=use_shrinkage,
        )
        for name in STRATEGY_LABELS
    }

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
k1.metric(
    "Sharpe Ratio (en muestra)", f"{optimal['sharpe']:.2f}",
    help="Medido sobre los mismos datos con los que se optimizó. Es una cota superior, "
         "no una expectativa. Compara con el Sharpe fuera de muestra más abajo.",
)
k2.metric(
    "Retorno Anual Esperado", f"{optimal['annual_return']:.2%}",
    help="Media aritmética anualizada (μ×períodos), la convención de Markowitz. "
         "No es un CAGR: no es la tasa que capitaliza una inversión.",
)
k3.metric("Volatilidad Anual", f"{optimal['annual_vol']:.2%}")
k4.metric(
    "Tasa Libre de Riesgo", f"{rf_rate * periods_per_year:.2%}",
    help="Promedio de ^IRX sobre el período de estimación, no el último dato.",
)

if use_shrinkage:
    st.caption(
        f"🛡️ Estimación robusta activa — shrinkage de covarianza: "
        f"**{optimal['cov_shrinkage']:.0%}** · shrinkage de medias: "
        f"**{optimal['mean_shrinkage']:.0%}**. Valores altos indican que la muestra "
        "aporta poca información y el estimador se apoya en el objetivo estructurado."
    )
else:
    st.caption(
        "⚠️ Estimación clásica (sin shrinkage): el Sharpe mostrado está inflado por "
        "error de estimación. Actívala en el panel superior."
    )

# ── Out-of-sample validation ──────────────────────────────────────────────────
st.subheader("🎯 Validación fuera de muestra (walk-forward)")
if wf is None:
    st.info(
        "No hay suficiente historial para validar fuera de muestra en este horizonte. "
        "Se necesita al menos 1 año de datos. Sin esta validación, el Sharpe mostrado "
        "arriba no está verificado."
    )
else:
    v1, v2, v3, v4 = st.columns(4)
    v1.metric(
        "Sharpe fuera de muestra", f"{wf['out_of_sample_sharpe']:.2f}",
        delta=f"{-wf['degradation']:.2f} vs en muestra",
        delta_color="inverse",
        help="Optimiza en una ventana, mantiene los pesos fijos en la siguiente, y repite. "
             "Este es el número que refleja lo que el método habría logrado.",
    )
    v2.metric(
        "Equal Weight (1/N)", f"{wf['equal_weight_sharpe']:.2f}",
        help="Repartir por igual, sin optimizar. Si el óptimo no le gana aquí, "
             "la optimización no está aportando valor.",
    )
    v3.metric("Retorno fuera de muestra", f"{wf['oos_return']:.2%}")
    v4.metric("Ventanas evaluadas", f"{wf['n_windows']}")

    st.caption(
        f"Entrena con {wf['train_size']} períodos, mantiene {wf['test_size']} · "
        f"{wf['n_oos_periods']} períodos fuera de muestra en total · "
        f"error estándar del Sharpe ±{wf['sharpe_stderr']:.2f}."
    )

    gap = wf["out_of_sample_sharpe"] - wf["equal_weight_sharpe"]
    if wf["beats_equal_weight"] is None:
        st.info(
            f"ℹ️ **Con estos datos no se puede distinguir la optimización de repartir por "
            f"igual.** La diferencia es {abs(gap):.2f} de Sharpe y el error de medición es "
            f"±{wf['sharpe_stderr']:.2f} — la diferencia cabe dentro del ruido. "
            f"Se necesitan más ventanas (hay {wf['n_windows']}) para concluir algo: "
            "elige un horizonte con más historial."
        )
    elif wf["beats_equal_weight"] is False:
        st.warning(
            f"⚠️ **La optimización queda por debajo de repartir por igual.** Fuera de muestra "
            f"logra Sharpe {wf['out_of_sample_sharpe']:.2f} frente a "
            f"{wf['equal_weight_sharpe']:.2f} de Equal Weight, una diferencia de {abs(gap):.2f} "
            f"que supera el error de medición (±{wf['sharpe_stderr']:.2f}). Con esta selección "
            "de activos y este horizonte, la optimización está ajustando ruido."
        )
    else:
        st.success(
            f"✅ La optimización supera a repartir por igual: Sharpe "
            f"{wf['out_of_sample_sharpe']:.2f} vs {wf['equal_weight_sharpe']:.2f}, "
            f"diferencia de {gap:.2f} por encima del error de medición "
            f"(±{wf['sharpe_stderr']:.2f})."
        )

    if wf["degradation"] > 1.0:
        st.warning(
            f"⚠️ **Degradación alta:** el Sharpe cae {wf['degradation']:.2f} puntos al salir "
            "de la muestra. Señal clásica de sobreajuste — considera menos activos, "
            "más historial, o límites de peso más estrictos."
        )

    # ── Head-to-head comparison of every strategy ─────────────────────────────
    st.markdown("**Comparación de estrategias sobre las mismas ventanas**")
    rows = []
    for name, label in STRATEGY_LABELS.items():
        res = all_strategies.get(name)
        if res is None:
            continue
        rows.append({
            "Estrategia": label + (" ◄ seleccionada" if name == strategy else ""),
            "Sharpe en muestra": f"{res['in_sample_sharpe']:.2f}",
            "Sharpe fuera de muestra": f"{res['out_of_sample_sharpe']:.2f}",
            "Retorno anual (fuera)": f"{res['oos_return']:.1%}",
            "Volatilidad (fuera)": f"{res['oos_vol']:.1%}",
        })
    rows.append({
        "Estrategia": "Equal Weight 1/N (referencia)",
        "Sharpe en muestra": "—",
        "Sharpe fuera de muestra": f"{wf['equal_weight_sharpe']:.2f}",
        "Retorno anual (fuera)": "—",
        "Volatilidad (fuera)": "—",
    })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        f"Todas las cifras 'fuera de muestra' vienen del mismo walk-forward "
        f"({wf['n_windows']} ventanas, error estándar ±{wf['sharpe_stderr']:.2f}). "
        "Diferencias menores al error estándar no son distinguibles del ruido."
    )

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
    "strategy": STRATEGY_LABELS[strategy],
    "shrinkage": "Sí" if use_shrinkage else "No",
    "cov_shrinkage": optimal["cov_shrinkage"],
    "mean_shrinkage": optimal["mean_shrinkage"],
    "n_obs": n_obs,
    "oos_sharpe": wf["out_of_sample_sharpe"] if wf else None,
    "oos_equal_weight_sharpe": wf["equal_weight_sharpe"] if wf else None,
    "oos_windows": wf["n_windows"] if wf else 0,
}

fig_frontier = plot_efficient_frontier(
    sim_df, optimal, benchmark, ew, valid_tickers, strategy_label=STRATEGY_LABELS[strategy]
)
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
