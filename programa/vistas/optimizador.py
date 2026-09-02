"""La pantalla principal: de una lista de tickers a una cartera con pesos.

Es el cuerpo que antes vivía entero en `app.py`, reorganizado en un formulario
y cuatro pestañas. Dos cambios de fondo, y ninguno es cosmético:

1. **La corrida se guarda en `st.session_state`.** Antes el guion terminaba en
   `st.stop()` si no se acababa de pulsar "Optimizar", y cualquier interacción
   posterior —descargar el Excel, abrir una pestaña— reejecutaba el guion con
   el botón ya en falso y devolvía la pantalla al estado inicial. Los
   resultados desaparecían delante del usuario después de descargar su propio
   informe. Con la corrida en sesión, la descarga descarga y la pantalla se
   queda donde estaba.
2. **Los controles van dentro de un `st.form`.** Sin él, mover un deslizador
   relanzaba la descarga de datos y el walk-forward completo de las tres
   estrategias. Ahora se recalcula cuando se pide, no cuando se toca algo.
"""

import numpy as np
import pandas as pd
import streamlit as st

import cartera
import preferencias as preferencias_mod
import tema
from charts import (
    plot_comparison,
    plot_correlation_heatmap,
    plot_efficient_frontier,
    plot_weights_pie,
)
from data import (
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

TICKERS_POR_DEFECTO = "AAPL, MSFT, GOOGL, AMZN, NVDA"

st.markdown(
    tema.cabecera(
        "Optimizador de portafolio",
        "Reparte el capital entre los activos que elijas y contrasta el "
        "resultado fuera de muestra. Todo lo que sale de aquí es una "
        "asignación calculada sobre datos pasados, no una previsión.",
    ),
    unsafe_allow_html=True,
)

guardadas, avisos_preferencias = preferencias_mod.cargar()
for aviso in avisos_preferencias:
    st.warning(aviso)


def _valores_iniciales() -> dict:
    """What the form opens with, and where each value comes from.

    Tres fuentes, en este orden y no en otro: lo que el usuario acaba de cargar
    a propósito (un portafolio guardado, un acta), lo que le llega del gate de
    aprobación, y por último sus preferencias. Un portafolio recién cargado
    tiene que ganarle a las preferencias — es lo que el usuario pidió hace un
    segundo — y el traspaso del gate tiene que ganarle a la lista por defecto,
    porque si no, aprobar quince empresas no serviría de nada.
    """
    inicial = {
        "tickers": guardadas.tickers or TICKERS_POR_DEFECTO,
        "horizonte": guardadas.horizonte,
        "estrategia": guardadas.estrategia,
        "peso_min": guardadas.peso_min,
        "peso_max": guardadas.peso_max,
        "cortos": guardadas.permitir_cortos,
        "shrinkage": guardadas.shrinkage,
        "origen": "",
    }

    aprobados = st.session_state.get("tickers_aprobados")
    if aprobados:
        inicial["tickers"] = ", ".join(aprobados)
        inicial["origen"] = f"{len(aprobados)} empresas aprobadas en el gate"

    # pop y no get: cargar un portafolio es un gesto de una sola vez. Si se
    # quedase en sesión, cada reejecución volvería a pisar lo que el usuario
    # hubiera escrito después, y el campo de tickers sería imposible de editar.
    cargado = st.session_state.pop("portafolio_a_cargar", None)
    if cargado is not None:
        st.session_state.origen_cargado = cargado.nombre
        inicial.update(
            tickers=", ".join(cargado.tickers),
            horizonte=cargado.horizonte,
            estrategia=cargado.estrategia,
            peso_min=int(round(cargado.peso_min * 100)),
            peso_max=int(round(cargado.peso_max * 100)),
            cortos=cargado.permitir_cortos,
            shrinkage=cargado.shrinkage,
        )
    if st.session_state.get("origen_cargado"):
        inicial["origen"] = f"cargado de «{st.session_state['origen_cargado']}»"
    return inicial


inicial = _valores_iniciales()

with st.container(border=True):
    if inicial["origen"]:
        st.markdown(
            tema.etiqueta(inicial["origen"], "acento"), unsafe_allow_html=True
        )

    with st.form("configuracion", border=False):
        raw_tickers = st.text_input(
            "Activos",
            value=inicial["tickers"],
            placeholder="AAPL, MSFT, GOOGL",
            help="Separados por coma o espacio. Hacen falta al menos dos.",
        )

        col_horizonte, col_estrategia = st.columns([1, 2])
        horizon = col_horizonte.selectbox(
            "Horizonte de inversión",
            options=list(HORIZON_CONFIG),
            index=list(HORIZON_CONFIG).index(inicial["horizonte"]),
            help="Decide la frecuencia de los datos y cuánto historial se usa.",
        )
        strategy = col_estrategia.radio(
            "Estrategia",
            options=list(STRATEGY_LABELS),
            format_func=lambda k: STRATEGY_LABELS[k],
            index=list(STRATEGY_LABELS).index(inicial["estrategia"]),
            horizontal=True,
            help="Mínima varianza y paridad de riesgo NO usan retornos esperados, "
            "que es donde vive casi todo el error de estimación.",
        )

        col_min, col_max, col_cortos = st.columns([2, 2, 1])
        weight_min = col_min.slider(
            "Peso mínimo por activo (%)", 0, 20, inicial["peso_min"],
            help="No aplica con ventas en corto: el límite pasa a ser simétrico "
            "(±peso máximo).",
        ) / 100
        weight_max = col_max.slider(
            "Peso máximo por activo (%)", 20, 100, inicial["peso_max"],
            help="Con ventas en corto, limita el tamaño absoluto de cada posición (±).",
        ) / 100
        allow_short = col_cortos.toggle("Ventas en corto", value=inicial["cortos"])

        use_shrinkage = st.toggle(
            "Estimación robusta (shrinkage Ledoit-Wolf + Bayes-Stein)",
            value=inicial["shrinkage"],
            help=(
                "Corrige el sesgo optimista de Markowitz. Con medias y covarianzas "
                "muestrales crudas el optimizador maximiza el error de estimación, no "
                "el Sharpe: sobre activos de puro ruido (retorno esperado real = 0) "
                "llega a reportar Sharpe 3,4. Desactívalo sólo para comparar con el "
                "método clásico."
            ),
        )

        enviado = st.form_submit_button(
            "Optimizar cartera", type="primary", use_container_width=True,
            icon=":material/play_arrow:",
        )


def _ejecutar() -> dict | None:
    """Fetch, optimise and validate. Returns None once it has explained a stop.

    Devuelve None en vez de llamar a `st.stop()` para que quien llama decida qué
    hacer: parar aquí dejaría la corrida anterior a medio borrar en sesión, y el
    usuario vería un error nuevo junto a los resultados viejos como si fueran
    de la misma corrida.
    """
    tickers = parse_tickers(raw_tickers)
    if len(tickers) < 2:
        st.error("Hacen falta al menos dos activos para repartir algo entre ellos.")
        return None

    with st.spinner("Descargando datos de mercado…"):
        market = fetch_market_data(tuple(tickers), horizon)

    valid_tickers = market["valid_tickers"]
    if len(valid_tickers) < 2:
        st.error(
            "Se necesitan al menos dos activos válidos. No se encontraron: "
            + ", ".join(market["invalid_tickers"])
        )
        return None

    returns = market["returns"]
    periods_per_year = market["periods_per_year"]
    n_obs = market["n_obs"]

    # La covarianza muestral necesita del orden de 30-50 observaciones por
    # activo antes de ser estable al invertirla. Por debajo, el optimizador
    # ajusta ruido.
    obs_per_asset = n_obs / len(valid_tickers)
    if obs_per_asset < 10:
        st.error(
            f"Datos insuficientes: {n_obs} observaciones para {len(valid_tickers)} "
            f"activos ({obs_per_asset:.0f} por activo). La matriz de covarianza es "
            "prácticamente singular y el resultado no es interpretable. Usa menos "
            "activos o un horizonte con datos diarios."
        )
        return None

    feasible, msg = validate_constraints(len(valid_tickers), weight_min, weight_max)
    if not feasible:
        st.error(msg)
        return None

    rf_rate = market["rf_rate"]
    bounds = (weight_min, weight_max)
    with st.spinner("Optimizando…"):
        sim_df = simulate_portfolios(
            returns, rf_rate, periods_per_year, bounds, allow_short,
            shrinkage=use_shrinkage,
        )
        optimal = optimize_portfolio(
            returns, rf_rate, periods_per_year, bounds, allow_short,
            strategy=strategy, shrinkage=use_shrinkage,
        )
        ew = equal_weight_portfolio(
            returns, rf_rate, periods_per_year, shrinkage=use_shrinkage
        )

    if not optimal["converged"]:
        st.error(
            f"La optimización no convergió: {optimal['message']}. Revisa activos muy "
            "correlacionados o ajusta los límites de posición."
        )
        return None

    with st.spinner("Validando fuera de muestra (walk-forward)…"):
        wf = walk_forward_validation(
            returns, rf_rate, periods_per_year, bounds, allow_short,
            strategy=strategy, shrinkage=use_shrinkage,
        )
        todas = {
            nombre: walk_forward_validation(
                returns, rf_rate, periods_per_year, bounds, allow_short,
                strategy=nombre, shrinkage=use_shrinkage,
            )
            for nombre in STRATEGY_LABELS
        }

    benchmark = None
    if not market["benchmark_returns"].empty:
        bm = market["benchmark_returns"]
        bm_ret = float(bm.mean() * periods_per_year)
        bm_vol = float(bm.std() * np.sqrt(periods_per_year))
        benchmark = {
            "annual_return": bm_ret,
            "annual_vol": bm_vol,
            "sharpe": float((bm_ret - rf_rate * periods_per_year) / bm_vol)
            if bm_vol > 0 else 0.0,
        }

    return {
        "market": market,
        "optimal": optimal,
        "equal_weight": ew,
        "sim_df": sim_df,
        "wf": wf,
        "todas": todas,
        "benchmark": benchmark,
        "tickers": valid_tickers,
        "horizonte": horizon,
        "estrategia": strategy,
        "peso_min": weight_min,
        "peso_max": weight_max,
        "cortos": allow_short,
        "shrinkage": use_shrinkage,
    }


if enviado:
    # Se borra antes de calcular: si el cálculo falla, lo que queda en pantalla
    # es el error, no los resultados de la corrida anterior con los parámetros
    # nuevos escritos encima.
    st.session_state.pop("corrida", None)
    corrida = _ejecutar()
    if corrida is not None:
        st.session_state.corrida = corrida
        st.session_state.pop("origen_cargado", None)

corrida = st.session_state.get("corrida")

if corrida is None:
    st.markdown("#### Cómo funciona")
    paso1, paso2, paso3 = st.columns(3)
    paso1.markdown(
        "**1 · Elige los activos**\n\nEscríbelos arriba, cárgalos desde un "
        "portafolio guardado, o déjalos que lleguen del gate de candidatos."
    )
    paso2.markdown(
        "**2 · Optimiza**\n\nSe descargan los precios, se estiman los momentos "
        "y se reparte el capital según la estrategia elegida."
    )
    paso3.markdown(
        "**3 · Comprueba que sirve**\n\nLa validación fuera de muestra dice si "
        "la optimización le gana a repartir por igual, o si sólo ajustó ruido."
    )
    st.stop()

# ── Desempaquetado de la corrida guardada ────────────────────────────────────
market = corrida["market"]
optimal = corrida["optimal"]
ew = corrida["equal_weight"]
wf = corrida["wf"]
valid_tickers = corrida["tickers"]
returns = market["returns"]
periods_per_year = market["periods_per_year"]
rf_anual = market["rf_rate"] * periods_per_year
n_obs = market["n_obs"]

if market["invalid_tickers"]:
    st.warning(
        "Activos no encontrados y omitidos: " + ", ".join(market["invalid_tickers"])
    )
if not market.get("rf_available", True):
    st.warning(
        f"^IRX no disponible. Se usa una tasa libre de riesgo de referencia: "
        f"{RF_FALLBACK:.1%} anual."
    )
obs_per_asset = n_obs / len(valid_tickers)
if obs_per_asset < 30:
    st.warning(
        f"Muestra corta: {n_obs} observaciones para {len(valid_tickers)} activos "
        f"({obs_per_asset:.0f} por activo, recomendado >30). Los pesos serán "
        "inestables: cambios pequeños en los datos moverán mucho el portafolio."
    )

st.markdown(
    tema.etiqueta(STRATEGY_LABELS[corrida["estrategia"]], "acento")
    + tema.etiqueta(f"Horizonte {corrida['horizonte']}")
    + tema.etiqueta(f"{len(valid_tickers)} activos")
    + tema.etiqueta(f"{n_obs} observaciones")
    + tema.etiqueta(
        "Estimación robusta" if corrida["shrinkage"] else "Estimación clásica",
        "bueno" if corrida["shrinkage"] else "aviso",
    )
    + (tema.etiqueta("Ventas en corto", "aviso") if corrida["cortos"] else ""),
    unsafe_allow_html=True,
)

# ── Estructuras compartidas por varias pestañas ──────────────────────────────
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
    "rf_rate": rf_anual,
    "horizon": corrida["horizonte"],
    "strategy": STRATEGY_LABELS[corrida["estrategia"]],
    "shrinkage": "Sí" if corrida["shrinkage"] else "No",
    "cov_shrinkage": optimal["cov_shrinkage"],
    "mean_shrinkage": optimal["mean_shrinkage"],
    "n_obs": n_obs,
    "oos_sharpe": wf["out_of_sample_sharpe"] if wf else None,
    "oos_equal_weight_sharpe": wf["equal_weight_sharpe"] if wf else None,
    "oos_windows": wf["n_windows"] if wf else 0,
}

# Las figuras se construyen una vez, antes de las pestañas, y se pintan con una
# `key` explícita cada vez. Streamlit deriva el id de un gráfico de sus
# argumentos, así que la misma tarta en dos pestañas producía dos elementos con
# el mismo id y la página entera moría con StreamlitDuplicateElementId.
fig_frontier = plot_efficient_frontier(
    corrida["sim_df"], optimal, corrida["benchmark"], ew, valid_tickers,
    strategy_label=STRATEGY_LABELS[corrida["estrategia"]],
)
fig_pie = plot_weights_pie(optimal["weights"], valid_tickers)
fig_corr = plot_correlation_heatmap(returns)
fig_comp = plot_comparison(
    valid_tickers, optimal["weights"], ew["weights"],
    optimal["annual_return"], ew["annual_return"],
    optimal["annual_vol"], ew["annual_vol"],
)

resumen, validacion, graficos, exportar = st.tabs(
    ["Resumen", "Validación fuera de muestra", "Gráficos", "Guardar y exportar"]
)

# ── Resumen ──────────────────────────────────────────────────────────────────
with resumen:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Sharpe (en muestra)", f"{optimal['sharpe']:.2f}",
        help="Medido sobre los mismos datos con los que se optimizó. Es una cota "
        "superior, no una expectativa: el número que importa está en la pestaña "
        "de validación.",
    )
    k2.metric(
        "Retorno anual esperado", f"{optimal['annual_return']:.2%}",
        help="Media aritmética anualizada (μ×períodos), la convención de Markowitz. "
        "No es un CAGR: no es la tasa a la que capitaliza una inversión.",
    )
    k3.metric("Volatilidad anual", f"{optimal['annual_vol']:.2%}")
    k4.metric(
        "Tasa libre de riesgo", f"{rf_anual:.2%}",
        help="Promedio de ^IRX sobre el período de estimación, no el último dato.",
    )

    # El veredicto de fuera de muestra sube al resumen a proposito: es la
    # afirmacion con mas consecuencias de toda la aplicacion, y escondida en una
    # pestana la lee quien ya sospechaba, que es justo quien menos la necesita.
    if wf is None:
        st.info(
            "No hay suficiente historial para validar fuera de muestra en este "
            "horizonte. Sin esa validación, el Sharpe de arriba no está verificado."
        )
    else:
        hueco = wf["out_of_sample_sharpe"] - wf["equal_weight_sharpe"]
        if wf["beats_equal_weight"] is None:
            st.info(
                f"**Con estos datos no se puede distinguir la optimización de "
                f"repartir por igual.** La diferencia es {abs(hueco):.2f} de Sharpe "
                f"y el error de medición es ±{wf['sharpe_stderr']:.2f}: cabe dentro "
                f"del ruido. Hacen falta más ventanas (hay {wf['n_windows']}); "
                "elige un horizonte con más historial."
            )
        elif wf["beats_equal_weight"] is False:
            st.warning(
                f"**La optimización queda por debajo de repartir por igual.** "
                f"Fuera de muestra logra Sharpe {wf['out_of_sample_sharpe']:.2f} "
                f"frente a {wf['equal_weight_sharpe']:.2f} de Equal Weight, una "
                f"diferencia de {abs(hueco):.2f} que supera el error de medición "
                f"(±{wf['sharpe_stderr']:.2f}). Con esta selección y este horizonte, "
                "la optimización está ajustando ruido."
            )
        else:
            st.success(
                f"**La optimización supera a repartir por igual.** Sharpe "
                f"{wf['out_of_sample_sharpe']:.2f} frente a "
                f"{wf['equal_weight_sharpe']:.2f}, una diferencia de {hueco:.2f} por "
                f"encima del error de medición (±{wf['sharpe_stderr']:.2f})."
            )

    if corrida["shrinkage"]:
        st.caption(
            f"Estimación robusta activa — shrinkage de covarianza "
            f"**{optimal['cov_shrinkage']:.0%}**, shrinkage de medias "
            f"**{optimal['mean_shrinkage']:.0%}**. Valores altos indican que la "
            "muestra aporta poca información y el estimador se apoya en el objetivo "
            "estructurado."
        )
    else:
        st.caption(
            "Estimación clásica (sin shrinkage): el Sharpe mostrado está inflado por "
            "error de estimación. Actívala en el panel de arriba."
        )

    peso_max_real = float(optimal["weights"].max())
    if peso_max_real > 0.50:
        arriba = valid_tickers[int(optimal["weights"].argmax())]
        st.warning(
            f"Alta concentración: **{arriba}** recibe **{peso_max_real:.1%}** del "
            "portafolio. Considera bajar el peso máximo por activo."
        )

    tabla, tarta = st.columns([3, 2])
    with tabla:
        st.markdown("**Pesos óptimos**")
        st.dataframe(weights_df, use_container_width=True, hide_index=True)
    with tarta:
        st.plotly_chart(fig_pie, use_container_width=True, key="tarta_resumen")

# ── Validación ───────────────────────────────────────────────────────────────
with validacion:
    if wf is None:
        st.info(
            "No hay suficiente historial para validar fuera de muestra en este "
            "horizonte. Se necesita al menos un año de datos."
        )
    else:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric(
            "Sharpe fuera de muestra", f"{wf['out_of_sample_sharpe']:.2f}",
            delta=f"{-wf['degradation']:.2f} vs en muestra", delta_color="inverse",
            help="Optimiza en una ventana, mantiene los pesos fijos en la siguiente "
            "y repite. Este es el número que refleja lo que el método habría logrado.",
        )
        v2.metric(
            "Equal Weight (1/N)", f"{wf['equal_weight_sharpe']:.2f}",
            help="Repartir por igual, sin optimizar. Si el óptimo no le gana aquí, "
            "la optimización no está aportando valor.",
        )
        v3.metric("Retorno fuera de muestra", f"{wf['oos_return']:.2%}")
        v4.metric("Ventanas evaluadas", f"{wf['n_windows']}")

        st.caption(
            f"Entrena con {wf['train_size']} períodos y mantiene {wf['test_size']} · "
            f"{wf['n_oos_periods']} períodos fuera de muestra en total · error "
            f"estándar del Sharpe ±{wf['sharpe_stderr']:.2f}."
        )

        if wf["degradation"] > 1.0:
            st.warning(
                f"**Degradación alta:** el Sharpe cae {wf['degradation']:.2f} puntos "
                "al salir de la muestra. Señal clásica de sobreajuste — considera "
                "menos activos, más historial, o límites de peso más estrictos."
            )

        st.markdown("**Comparación de estrategias sobre las mismas ventanas**")
        filas = []
        for nombre, etiqueta in STRATEGY_LABELS.items():
            res = corrida["todas"].get(nombre)
            if res is None:
                continue
            filas.append({
                "Estrategia": etiqueta
                + ("  ◄ seleccionada" if nombre == corrida["estrategia"] else ""),
                "Sharpe en muestra": f"{res['in_sample_sharpe']:.2f}",
                "Sharpe fuera de muestra": f"{res['out_of_sample_sharpe']:.2f}",
                "Retorno anual (fuera)": f"{res['oos_return']:.1%}",
                "Volatilidad (fuera)": f"{res['oos_vol']:.1%}",
            })
        filas.append({
            "Estrategia": "Equal Weight 1/N (referencia)",
            "Sharpe en muestra": "—",
            "Sharpe fuera de muestra": f"{wf['equal_weight_sharpe']:.2f}",
            "Retorno anual (fuera)": "—",
            "Volatilidad (fuera)": "—",
        })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
        st.caption(
            f"Todas las cifras de fuera de muestra vienen del mismo walk-forward "
            f"({wf['n_windows']} ventanas, error estándar ±{wf['sharpe_stderr']:.2f}). "
            "Diferencias menores que el error estándar no se distinguen del ruido."
        )

# ── Gráficos ─────────────────────────────────────────────────────────────────
with graficos:
    g1, g2 = st.columns(2)
    g1.plotly_chart(fig_frontier, use_container_width=True, key="frontera")
    g2.plotly_chart(fig_comp, use_container_width=True, key="comparacion")
    g3, g4 = st.columns(2)
    g3.plotly_chart(fig_corr, use_container_width=True, key="correlacion")
    g4.plotly_chart(fig_pie, use_container_width=True, key="tarta_graficos")

# ── Guardar y exportar ───────────────────────────────────────────────────────
with exportar:
    st.markdown("**Guardar este portafolio**")
    st.caption(
        "Se guarda una fotografía: los pesos y las métricas de esta corrida, con "
        "su fecha. No se recalcula al abrirlo — los precios de mañana ya no son "
        "los de hoy, y un portafolio que cambiara solo no sería el que guardaste."
    )
    col_nombre, col_nota, col_guardar = st.columns([2, 3, 1])
    nombre = col_nombre.text_input("Nombre", key="nombre_portafolio", max_chars=60)
    nota = col_nota.text_input(
        "Nota (opcional)", key="nota_portafolio",
        placeholder="Por qué guardas esta corrida",
    )
    col_guardar.write("")
    col_guardar.write("")
    if col_guardar.button(
        "Guardar", use_container_width=True, icon=":material/save:",
        disabled=not nombre.strip(),
    ):
        try:
            destino = cartera.guardar(
                cartera.desde_corrida(
                    nombre=nombre,
                    tickers=valid_tickers,
                    pesos=optimal["weights"],
                    horizonte=corrida["horizonte"],
                    estrategia=corrida["estrategia"],
                    peso_min=corrida["peso_min"],
                    peso_max=corrida["peso_max"],
                    permitir_cortos=corrida["cortos"],
                    shrinkage=corrida["shrinkage"],
                    metricas=metrics,
                    nota=nota,
                )
            )
        except cartera.NombreInvalido as error:
            st.error(str(error))
        except OSError as error:
            st.error(f"No se pudo guardar: {error}")
        else:
            st.success(f"Guardado en {destino}. Está en «Portafolios guardados».")

    st.divider()
    st.markdown("**Descargar el informe**")
    col_excel, col_pdf = st.columns(2)
    col_excel.download_button(
        "Descargar Excel",
        data=to_excel(weights_df, metrics),
        file_name=f"markowitz_{corrida['horizonte'].replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        icon=":material/table_view:",
    )
    col_pdf.download_button(
        "Descargar PDF",
        data=to_pdf(weights_df, metrics, [fig_frontier, fig_pie, fig_corr, fig_comp]),
        file_name=f"markowitz_{corrida['horizonte'].replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
        icon=":material/picture_as_pdf:",
    )
