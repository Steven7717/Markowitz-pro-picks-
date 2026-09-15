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
import configuracion
import estimators
import historial
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
from validation import (
    frase_identificabilidad,
    identificabilidad,
    medida_veredicto,
    metricas_de_identificabilidad,
    metricas_de_validacion,
    retorno_stderr,
    walk_forward_comparison,
)

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

# El acuse del acta que acaba de escribir el gate, que ahora salta aqui en vez
# de pedir que uses el menu.
#
# `pop` y no `get`: el acuse pertenece al salto que acaba de ocurrir. Con `get`
# reaparecería en cada re-ejecución de Streamlit, que son muchas.
destino_acta = st.session_state.pop("acta_recien_escrita", None)
if destino_acta:
    st.success(f"Acta escrita en {destino_acta}.")

guardadas, avisos_preferencias = preferencias_mod.cargar()
for aviso in avisos_preferencias:
    st.warning(aviso)


# Los valores del formulario viven en `session_state` bajo las claves de
# `configuracion`, no en un diccionario que se recalcule aqui. El porque --y el
# fallo que salio de hacerlo al reves-- esta escrito en ese modulo.
origen = configuracion.sembrar(st.session_state, guardadas, TICKERS_POR_DEFECTO)
CLAVES = configuracion.CLAVES

with st.container(border=True):
    if origen:
        st.markdown(tema.etiqueta(origen, "acento"), unsafe_allow_html=True)

    with st.form("configuracion", border=False):
        # `key=` y nada de `value=`: los dos juntos hacen que Streamlit avise de
        # que uno pisa al otro, y el que manda es la sesion.
        raw_tickers = st.text_input(
            "Activos",
            key=CLAVES["tickers"],
            placeholder="AAPL, MSFT, GOOGL",
            help="Separados por coma o espacio. Hacen falta al menos dos.",
        )

        col_horizonte, col_estrategia = st.columns([1, 2])
        horizon = col_horizonte.selectbox(
            "Horizonte de inversión",
            options=list(HORIZON_CONFIG),
            key=CLAVES["horizonte"],
            help="Decide la frecuencia de los datos y cuánto historial se usa.",
        )
        strategy = col_estrategia.radio(
            "Estrategia",
            options=list(STRATEGY_LABELS),
            format_func=lambda k: STRATEGY_LABELS[k],
            key=CLAVES["estrategia"],
            horizontal=True,
            help="Mínima varianza y paridad de riesgo NO usan retornos esperados, "
            "que es donde vive casi todo el error de estimación.",
        )

        col_min, col_max, col_cortos = st.columns([2, 2, 1])
        weight_min = col_min.slider(
            "Peso mínimo por activo (%)", 0, 20, key=CLAVES["peso_min"],
            help="No aplica con ventas en corto: el límite pasa a ser simétrico "
            "(±peso máximo).",
        ) / 100
        weight_max = col_max.slider(
            "Peso máximo por activo (%)", 20, 100, key=CLAVES["peso_max"],
            help="Con ventas en corto, limita el tamaño absoluto de cada posición (±).",
        ) / 100
        allow_short = col_cortos.toggle("Ventas en corto", key=CLAVES["cortos"])

        use_shrinkage = st.toggle(
            "Estimación robusta (shrinkage Ledoit-Wolf + Bayes-Stein)",
            key=CLAVES["shrinkage"],
            help=(
                "Corrige el sesgo optimista de Markowitz. Con medias y covarianzas "
                "muestrales crudas el optimizador maximiza el error de estimación, no "
                "el Sharpe: sobre activos de puro ruido (retorno esperado real = 0) "
                "llega a reportar Sharpe 3,4. Desactívalo sólo para comparar con el "
                "método clásico."
            ),
        )

        usar_pares = st.toggle(
            "Aprovechar la historia que no comparten todos (covarianza por pares)",
            key=CLAVES["pares"],
            help=(
                "Cada covarianza se estima con las fechas que comparte ESE par, "
                "no las que comparten todos. Con un activo recién salido a bolsa "
                "la pareja AAPL-MSFT deja de pagar su juventud. Las medias siguen "
                "saliendo de la ventana común a propósito, así que ayuda sobre "
                "todo a mínima varianza y paridad de riesgo."
            ),
        )

        enviado = st.form_submit_button(
            "Optimizar cartera", type="primary", use_container_width=True,
            icon=":material/play_arrow:",
        )


_MOTIVOS = {
    "arranque": "sólo hay precios desde {desde}",
    "interrumpida": "la fuente deja de dar precios suyos; los últimos son de {hasta}",
    "huecos": "le faltan fechas dentro de su propio historial",
    "sin datos": "no ha devuelto ningún precio",
}


def _mostrar_escalera(peldanos: list, n_obs: int) -> None:
    """El compromiso entre cuántos activos llevas y cuánta historia tienes.

    Se dice antes que cualquier otra cosa porque es la causa, no el síntoma. El
    aviso que había aquí llamaba «serie incompleta» a un activo recién salido a
    bolsa, y eso manda a buscar un fallo donde no lo hay: la serie de PLTR está
    completa, empieza en 2020 porque la empresa no cotizaba antes.
    """
    if len(peldanos) < 2:
        return
    cabeza = peldanos[0]
    if cabeza.corta is None:
        return

    motivo = _MOTIVOS.get(cabeza.motivo, "recorta la muestra").format(
        desde=cabeza.desde, hasta=cabeza.hasta)
    mejor = peldanos[-1]
    st.warning(
        f"**{cabeza.corta} decide el historial de toda la cartera**: {motivo}. "
        f"Como se descartan las fechas en las que falte algún precio, con estos "
        f"{cabeza.activos} activos quedan **{n_obs} observaciones**; sin "
        f"{cabeza.corta} habría **{peldanos[1].observaciones}**"
        + (f", y con {mejor.activos} activos hasta **{mejor.observaciones}**."
           if len(peldanos) > 2 else ".")
    )
    with st.expander(f"Qué ganas quitando activos ({len(peldanos) - 1} opciones)"):
        st.caption(
            "Ningún dato se está perdiendo por un fallo: el historial anterior a "
            "una salida a bolsa no existe. Lo que hay es un compromiso entre "
            "llevar ese activo y tener con qué estimar, y lo decides tú."
        )
        st.dataframe(
            pd.DataFrame([{
                "Dejando fuera": ", ".join(e.fuera) if e.fuera else "— nada —",
                "Activos": e.activos,
                "Observaciones": e.observaciones,
                "Por activo": f"{e.observaciones / e.activos:.0f}",
                "Lo corta": e.corta or "— ya nadie —",
            } for e in peldanos]),
            use_container_width=True, hide_index=True,
        )


# Si el aviso de tickers omitidos ya se ha pintado en ESTA re-ejecución. Es una
# variable de módulo y no de sesión a propósito: Streamlit reejecuta el guion
# entero en cada interacción, así que el módulo se recarga y la bandera se
# reinicia sola, que es justo el alcance que hace falta.
_omitidos_avisados = False

# Los nombres ya usados, leidos una vez por re-ejecución en vez de una vez por
# tecla: `cartera.nombres_usados()` abre y parsea todos los JSON guardados, y
# esto se consulta desde un `text_input`, o sea en cada pulsación. Se vacía al
# lanzar una corrida nueva y después de guardar, que son los dos momentos en que
# la lista puede haber cambiado.
_NOMBRES_USADOS: list[set[str]] = []


def _nombres_usados() -> set[str]:
    if not _NOMBRES_USADOS:
        _NOMBRES_USADOS.append(cartera.nombres_usados())
    return _NOMBRES_USADOS[0]


def _avisar_omitidos(market: dict) -> None:
    """Los tickers que se descartaron, dichos antes que nada.

    Vivía en el camino de éxito, **después** de los seis `return None` de
    `_ejecutar`. Reproducido con `AAPL, MSFT, ZZZZNOEXISTE`: el ticker malo se
    descarta en `data.py`, quedan dos activos, y lo único que el usuario leía era
    «Restricción infactible: peso máximo (30%) × 2 activos = 60% < 100%» — un
    error sobre una restricción que él no había tocado, sin una palabra sobre el
    ticker que la había provocado. Otra pantalla le promete además que «el fallo
    aparecerá en el optimizador».

    La causa va antes que el síntoma: quien ve primero «ZZZZNOEXISTE no existe»
    entiende el resto de la pantalla; quien ve primero la restricción, no.
    """
    global _omitidos_avisados
    if _omitidos_avisados or not market.get("invalid_tickers"):
        return
    _omitidos_avisados = True
    st.warning(
        "Activos no encontrados y omitidos: "
        + ", ".join(market["invalid_tickers"])
        + ". Todo lo que sigue se ha calculado sin ellos."
    )


# Si el aviso de cobertura ya se ha pintado en ESTA re-ejecución. Mismo alcance
# y mismo motivo que `_omitidos_avisados`, justo encima.
_cobertura_avisada = False


def _avisar_cobertura(market: dict) -> None:
    """Los activos cuya serie está rota, nombrados uno a uno y con su cifra.

    `data.tickers_con_huecos` medía esto desde el principio —qué parte del
    horizonte trae cada serie— y **no lo leía nadie**: ni una vista, ni un
    informe. El cálculo, la clave del diccionario y sus tests existían, y un
    activo con el 11% de sus sesiones entraba en el reparto en silencio.

    La escalera de aquí abajo cubre el caso corriente, pero se calla con dos
    activos y con dos series rotas a la vez (el porqué, en
    `historial.avisos_de_cobertura`) — que es justo cuando esto hace más falta:
    lo único que el usuario llega a leer entonces es «datos insuficientes», el
    síntoma, sin saber cuál de sus activos lo provoca.

    Lo que **no** se avisa es al activo joven. Su cobertura también es baja y su
    serie está entera; de ése habla la escalera, como el compromiso que es.
    """
    global _cobertura_avisada
    if _cobertura_avisada:
        return
    avisos = historial.avisos_de_cobertura(
        market.get("precios", pd.DataFrame()),
        market.get("tickers_con_huecos", {}),
    )
    if not avisos:
        return
    _cobertura_avisada = True
    st.warning(
        "**Series incompletas, y entran igual en el reparto:**\n\n"
        + "\n".join(
            f"- **{a.ticker}** sólo trae precio en el {a.cobertura:.0%} de las "
            f"fechas del horizonte: "
            + _MOTIVOS.get(a.motivo, "su serie recorta la muestra").format(
                desde=a.desde, hasta=a.hasta)
            + "."
            for a in avisos
        )
        + "\n\nSe descartan las fechas en las que falte algún precio, así que "
        "lo que les falta se lo quitan también a los demás."
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

    # Lo primero que se pinta, porque es la causa de casi todo lo que puede
    # fallar debajo. El que no existe, y luego el que existe pero llega roto:
    # los dos van antes que los errores que provocan.
    _avisar_omitidos(market)
    _avisar_cobertura(market)

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
    # Sobre qué se estima: en modo por pares, los retornos que conservan las
    # fechas que no comparten todos; si no, los de siempre. Se decide aquí
    # arriba porque las guardas de más abajo ya dependen de ello.
    base = market["returns_amplios"] if usar_pares else returns

    # Se dice antes de cualquier otra cosa porque es la causa, no el sintoma: un
    # ticker con la serie rota recorta el historial de TODOS —se descartan las
    # fechas donde falte algun precio— y sin esto el usuario solo veia el
    # resultado, "datos insuficientes", sin saber cual de sus activos lo
    # provocaba ni que quitandolo se arreglaba.
    peldanos = historial.escalera(market.get("precios", pd.DataFrame()))
    _mostrar_escalera(peldanos, n_obs)

    # Cada modo se bloquea por lo que de verdad le rompe, porque no es lo mismo.
    #
    # Sobre la ventana común manda el cociente observaciones/activos: la
    # covarianza muestral necesita del orden de 30-50 por activo antes de ser
    # estable al invertirla, y por debajo de 10 es prácticamente singular.
    #
    # Por pares esa premisa no se sostiene --la matriz sale reparada a definida
    # positiva y encogida hacia la identidad, así que singular no es-- y lo que
    # manda es otra cosa: que ningún activo baje del solape mínimo con el que se
    # estima una pareja. Por debajo de eso su fila entera saldría a cero, que es
    # decir que no se relaciona con nada.
    if usar_pares:
        por_activo = int(base.notna().sum().min()) if len(base) else 0
        if por_activo < estimators.SOLAPE_MINIMO:
            flaco = str(base.notna().sum().idxmin())
            st.error(
                f"Datos insuficientes incluso por pares: **{flaco}** sólo tiene "
                f"{por_activo} observaciones, y hacen falta "
                f"{estimators.SOLAPE_MINIMO} para estimar una sola de sus "
                "parejas. Quítalo, o elige un horizonte con datos diarios."
            )
            return None
    else:
        obs_per_asset = n_obs / len(valid_tickers)
        if obs_per_asset < 10:
            st.error(
                f"Datos insuficientes: {n_obs} observaciones para "
                f"{len(valid_tickers)} activos ({obs_per_asset:.0f} por activo). "
                "La matriz de covarianza es prácticamente singular y el "
                "resultado no es interpretable. "
                + (
                    f"La causa está arriba: quita {peldanos[0].corta} y pasas a "
                    f"{peldanos[1].observaciones} observaciones. O marca "
                    "«aprovechar la historia que no comparten todos»."
                    if len(peldanos) > 1 and peldanos[0].corta
                    else "Usa menos activos o un horizonte con datos diarios."
                )
            )
            return None

    feasible, msg = validate_constraints(len(valid_tickers), weight_min, weight_max)
    if not feasible:
        st.error(msg)
        return None

    rf_rate = market["rf_rate"]
    bounds = (weight_min, weight_max)
    with st.spinner("Optimizando…"):
        # Todo lo que se dibuja junto en la frontera se estima igual: mezclar
        # un optimo calculado por pares con una nube calculada sobre la ventana
        # comun pondria en el mismo grafico puntos que no son comparables.
        sim_df = simulate_portfolios(
            base, rf_rate, periods_per_year, bounds, allow_short,
            shrinkage=use_shrinkage, pairwise=usar_pares,
        )
        optimal = optimize_portfolio(
            base, rf_rate, periods_per_year, bounds, allow_short,
            strategy=strategy, shrinkage=use_shrinkage, pairwise=usar_pares,
        )
        ew = equal_weight_portfolio(
            base, rf_rate, periods_per_year, shrinkage=use_shrinkage,
            pairwise=usar_pares,
        )

    if not optimal["converged"]:
        st.error(
            f"La optimización no convergió: {optimal['message']}. Revisa activos muy "
            "correlacionados o ajusta los límites de posición."
        )
        return None

    with st.spinner("Validando fuera de muestra (walk-forward)…"):
        # Una sola pasada donde antes había cuatro. No es sólo velocidad —la
        # seleccionada se recorría dos veces—: corriendo cada estrategia por su
        # lado, cada una se quedaba con las ventanas donde ella convergió y con
        # su propia referencia 1/N, y la tabla de abajo las ponía en columnas
        # como si vinieran de la misma medición.
        comparacion = walk_forward_comparison(
            base, rf_rate, periods_per_year, bounds, allow_short,
            shrinkage=use_shrinkage, pairwise=usar_pares,
        )
        todas = comparacion["por_estrategia"] if comparacion else {}
        wf = todas.get(strategy)

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
        "comparacion": comparacion,
        "benchmark": benchmark,
        "tickers": valid_tickers,
        "horizonte": horizon,
        "estrategia": strategy,
        "peso_min": weight_min,
        "peso_max": weight_max,
        "cortos": allow_short,
        "shrinkage": use_shrinkage,
        "pares": usar_pares,
    }


if enviado:
    # Se borra antes de calcular: si el cálculo falla, lo que queda en pantalla
    # es el error, no los resultados de la corrida anterior con los parámetros
    # nuevos escritos encima.
    st.session_state.pop("corrida", None)
    # El informe pertenece a la corrida que lo generó.
    st.session_state.pop("pdf_informe", None)
    _NOMBRES_USADOS.clear()
    corrida = _ejecutar()
    if corrida is not None:
        st.session_state.corrida = corrida
        configuracion.olvidar_origen(st.session_state)

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

# En la corrida que acaba de lanzarse esto ya lo dijo `_ejecutar` antes de
# cualquier error; en las re-ejecuciones posteriores --cambiar de pestaña,
# descargar-- lo dice aquí, para que el aviso no desaparezca mientras los
# resultados que lo necesitan siguen en pantalla.
_avisar_omitidos(market)
_avisar_cobertura(market)
if not market.get("rf_available", True):
    st.warning(
        f"^IRX no disponible. Se usa una tasa libre de riesgo de referencia: "
        f"{RF_FALLBACK:.1%} anual."
    )
obs_per_asset = n_obs / len(valid_tickers)
if obs_per_asset < 30 and not corrida["pares"]:
    st.warning(
        f"Muestra corta: {n_obs} observaciones para {len(valid_tickers)} activos "
        f"({obs_per_asset:.0f} por activo, recomendado >30). Los pesos serán "
        "inestables: cambios pequeños en los datos moverán mucho el portafolio."
    )

st.markdown(
    tema.etiqueta(STRATEGY_LABELS[corrida["estrategia"]], "acento")
    + tema.etiqueta(f"Horizonte {corrida['horizonte']}")
    + tema.etiqueta(f"{len(valid_tickers)} activos")
    # En modo por pares, "55 observaciones" seria enganoso: son las comunes,
    # pero la covarianza ha mirado bastantes mas.
    + tema.etiqueta(
        f"{n_obs} comunes · hasta {int(market['returns_amplios'].notna().sum().max())} "
        "por pares" if corrida["pares"] else f"{n_obs} observaciones"
    )
    + tema.etiqueta(
        "Estimación robusta" if corrida["shrinkage"] else "Estimación clásica",
        "bueno" if corrida["shrinkage"] else "aviso",
    )
    + (tema.etiqueta("Covarianza por pares", "bueno") if corrida["pares"] else "")
    + (tema.etiqueta("Ventas en corto", "aviso") if corrida["cortos"] else ""),
    unsafe_allow_html=True,
)

# ── Estructuras compartidas por varias pestañas ──────────────────────────────
# Con la covarianza por pares, cada activo se describe con SU historia, que es
# la que el optimizador ha mirado; sin ella, con la ventana comun de siempre.
_serie_de = market["returns_amplios"] if corrida["pares"] else returns

# **Los momentos que el optimizador miró, no los que se pueden recalcular.** La
# tabla imprimía la media MUESTRAL de cada activo mientras el reparto se había
# decidido con las encogidas al 77%, y los dos números no se parecían:
#
#     AAPL  tabla 24,75% / optimizador 27,88%    MSFT   tabla 12,40% / 25,01%
#     GOOGL tabla 44,84% / optimizador 32,54%    NVDA   tabla 40,45% / 31,52%
#
# MSFT «esperaba» un 12,4% y recibía el 27,8% del dinero: la tabla que describe
# la cartera hacía imposible entenderla. Ahora `optimize_portfolio` devuelve
# `mean` y `cov`, y aquí se leen de ahí — con shrinkage y sin él, porque sin él
# son exactamente los muestrales y la tabla no cambia.
_mu_usada = np.asarray(optimal["mean"], dtype=float) * periods_per_year
_vol_usada = np.sqrt(np.diag(np.asarray(optimal["cov"], dtype=float))) * np.sqrt(
    periods_per_year
)
# **¿Estos datos identifican este reparto?** La tabla de abajo escribe los pesos
# con dos decimales, la tarta los dibuja y el PDF los imprime, y sobre el caso
# por defecto un bootstrap de 300 remuestreos con reoptimización completa da
# intervalos al 90% de 67 puntos de ancho: en el 54% de ellos manda un activo
# distinto del que la pantalla pone primero. El guardarraíl de muestra corta no
# se dispara ahí —100 observaciones por activo contra un umbral de 30— así que
# nada avisaba. Esto es la versión barata de esa comprobación; el porqué de
# preferirla a pagar el bootstrap en cada corrida está en
# `validation.identificabilidad`.
_identificabilidad = identificabilidad(_serie_de, periods_per_year)

weights_df = pd.DataFrame({
    "Ticker": valid_tickers,
    "Peso Óptimo (%)": [f"{w:.2%}" for w in optimal["weights"]],
    "Retorno Esperado (%)": [f"{m:.2%}" for m in _mu_usada],
    "Volatilidad (%)": [f"{v:.2%}" for v in _vol_usada],
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
    # **El recorrido entero, escrito por quien lo produjo.** Este diccionario
    # copiaba a mano seis campos de `wf` y se dejaba fuera los dos que dicen
    # contra qué listón se dictó el veredicto —`umbral_veredicto` y
    # `sigmas_veredicto`— así que el fichero guardaba una conclusión que nadie
    # podía recomprobar. De ahí los dos defectos de las otras pantallas: una
    # pintaba el color con el `beats_equal_weight` viejo junto a un texto
    # recalculado con el listón nuevo, y otra leía ese veredicto sin barra de
    # error ni umbral. Ahora la ida y la vuelta viven juntas en `validation`.
    **metricas_de_validacion(wf),
    # Y la medición que sostiene —o no— el reparto de la tabla, para que el
    # informe y la pantalla de portafolios puedan repetir el aviso sin tener
    # delante los retornos con los que se calculó.
    **metricas_de_identificabilidad(_identificabilidad),
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
# `_serie_de` y no `returns`: con «covarianza por pares» marcado, la tabla de
# arriba describe cada activo con SU historia y el mapa seguía dibujando la
# ventana común, que es otra matriz.
fig_corr = plot_correlation_heatmap(_serie_de)
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
    # «Sharpe (en muestra)» se llamaba igual que la columna de la tabla de
    # validación, y eran dos números distintos: éste es UN ajuste sobre toda la
    # muestra (salía 1,13), y aquél la media de los cocientes de
    # cada ventana (salía 1,37, dominada por una de las cuatro: 1,206 · 0,941 ·
    # 0,993 · 2,343). Dos etiquetas iguales sobre dos estimadores distintos
    # invitan a restarlos, que es de donde salía la degradación imposible.
    k1.metric(
        "Sharpe del ajuste único", f"{optimal['sharpe']:.2f}",
        help=f"Un solo ajuste sobre las {n_obs} observaciones, medido sobre los "
        "mismos datos con los que se optimizó. Es una cota superior, no una "
        "expectativa: el número que importa está en la pestaña de validación, y "
        "el «Sharpe medio en muestra» de allí es otro estimador —la media de las "
        "ventanas— que no se puede comparar con éste.",
    )
    # **Con su barra de error, como el Sharpe.** «28,76%» a dos decimales sobre
    # 500 observaciones lleva un error estándar de 15,6 puntos porcentuales: el
    # intervalo al 95% iba de -1,9% a 59,4%, y la pantalla ponía barra de error al
    # Sharpe fuera de muestra y no a esto. La media es el estadístico peor medido
    # de toda la optimización media-varianza —por eso `estimators` la encoge más
    # que la covarianza— y enseñarla desnuda con dos decimales promete una
    # precisión que no existe.
    _se_retorno = retorno_stderr(optimal["annual_vol"], n_obs, periods_per_year)
    k2.metric(
        "Retorno anual esperado",
        f"{optimal['annual_return']:.1%} ± {_se_retorno:.1%}",
        help="Media aritmética anualizada (μ×períodos), la convención de Markowitz. "
        "No es un CAGR: no es la tasa a la que capitaliza una inversión. El ± es un "
        f"error estándar sobre {n_obs} observaciones; el intervalo al 95% son dos, "
        f"o sea de {optimal['annual_return'] - 2 * _se_retorno:.1%} a "
        f"{optimal['annual_return'] + 2 * _se_retorno:.1%}.",
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
        # El listón va escrito en la frase, no reconstruido aquí: son dos
        # errores estándar, no uno, y con uno solo este recuadro verde salía en
        # el 12% de 200 mundos sintéticos SIN ninguna ventaja real. El porqué del
        # número está en `validation.veredicto`.
        hueco = wf["out_of_sample_sharpe"] - wf["equal_weight_sharpe"]
        _marco = f"{wf['n_windows']} ventanas · {wf['n_oos_periods']} períodos"
        # La medida y no la frase entera: el titular en negrita de cada rama
        # ya dice cuál de los tres casos es, y `frase_veredicto` lo repetía
        # palabra por palabra justo detrás.
        _frase = medida_veredicto(hueco, wf["gap_stderr"])
        _cifras = (
            f"Fuera de muestra: Sharpe {wf['out_of_sample_sharpe']:.2f} frente a "
            f"{wf['equal_weight_sharpe']:.2f} de Equal Weight ({_marco})."
        )
        if wf["beats_equal_weight"] is None:
            st.info(
                f"**Con estos datos no se puede distinguir la optimización de "
                f"repartir por igual.** {_frase} {_cifras} Elige un horizonte con "
                "más historial si quieres un veredicto."
            )
        elif wf["beats_equal_weight"] is False:
            st.warning(
                f"**La optimización queda por debajo de repartir por igual.** "
                f"{_frase} {_cifras} Con esta selección y este horizonte, la "
                "optimización está ajustando ruido."
            )
        else:
            st.success(
                f"**La optimización supera a repartir por igual.** {_frase} {_cifras}"
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

    # **Mercado bajista: el aviso que faltaba.** `optimize_max_sharpe` ya no
    # entrega el activo más volátil al 100% cuando el exceso esperado es
    # negativo, pero callarse el cambio de régimen sería la otra mitad del mismo
    # fallo: un Sharpe negativo en pantalla no dice por sí solo que NINGUNA
    # cartera factible supere a las letras del Tesoro, y esa es la afirmación.
    if optimal.get("sin_prima"):
        if corrida["estrategia"] == "max_sharpe":
            st.warning(
                "**Ningún reparto de estos activos supera a la tasa libre de "
                f"riesgo ({rf_anual:.2%} anual) en este período.** "
                + optimal["message"]
                + " El Sharpe de arriba es negativo y ordenar carteras por él deja "
                "de tener sentido: comparar dos números negativos divididos por su "
                "volatilidad premia a la más volátil."
            )
        else:
            st.warning(
                "**Esta cartera rinde por debajo de la tasa libre de riesgo "
                f"({rf_anual:.2%} anual) sobre el período estimado.** El Sharpe de "
                "arriba es negativo, y un Sharpe negativo no ordena: entre dos "
                "carteras que pierden, la más volátil sale con el cociente más "
                "alto. Léelo como «pierde», no como «pierde menos»."
            )

    # Paridad de riesgo que no ha podido igualar. `converged` sigue en True a
    # propósito —es una cartera factible y útil— pero llamarla «paridad de
    # riesgo» sin más sería falso: con el tope del 30% por defecto, 11 de 40
    # carteras de cinco activos salían desiguales y ninguna lo decía.
    if optimal.get("erc_exacto") is False:
        st.warning(
            f"**Esta cartera no llega a igualar el riesgo.** {optimal['message']}"
        )

    peso_max_real = float(optimal["weights"].max())
    if peso_max_real > 0.50:
        arriba = valid_tickers[int(optimal["weights"].argmax())]
        st.warning(
            f"Alta concentración: **{arriba}** recibe **{peso_max_real:.1%}** del "
            "portafolio. Considera bajar el peso máximo por activo."
        )

    # **El aviso va ANTES de la tabla y de la tarta, no debajo.** Puesto
    # detrás lo lee quien ya se ha quedado con «MSFT 45,8%», y el decimal es
    # justo lo que hay que desmentir.
    if _identificabilidad is not None:
        _frase = frase_identificabilidad(_identificabilidad)
        if _identificabilidad["identificada"]:
            st.caption(_frase)
        else:
            st.warning(_frase)

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
        # **Doble negación, flecha verde.** Estaba escrito `-degradation` (o sea
        # ya negativo cuando el método empeora) con `delta_color="inverse"` (que
        # pinta de verde lo negativo): «-0,57 vs en muestra» salía en VERDE, el
        # color de «va bien», justo cuando significa que fuera de muestra rinde
        # mucho peor. Con el signo ya invertido en el número, el color que toca
        # es el normal.
        #
        # Y la referencia se nombra: la degradación resta la media por ventana,
        # no el ajuste único del Resumen ni el agrupado de este mismo recuadro.
        v1.metric(
            "Sharpe fuera de muestra (agrupado)",
            f"{wf['out_of_sample_sharpe']:.2f}",
            delta=f"{-wf['degradation']:+.2f} vs. media en muestra",
            delta_color="normal",
            help="Optimiza en una ventana, mantiene los pesos fijos en la siguiente "
            "y repite. Este es el número que refleja lo que el método habría logrado, "
            "medido sobre todos los períodos fuera de muestra a la vez. La variación "
            "de debajo compara dos medias por ventana entre sí —"
            f"{wf['in_sample_sharpe']:.2f} dentro contra "
            f"{wf['out_of_sample_sharpe_medio']:.2f} fuera— que son los dos números "
            "que sí se pueden restar.",
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
            f"{wf['n_oos_periods']} períodos fuera de muestra en total · error del "
            f"Sharpe ±{wf['sharpe_stderr']:.2f} · error de la diferencia contra 1/N "
            f"±{wf['gap_stderr']:.2f}, y el veredicto pide superar "
            f"{wf['umbral_veredicto']:.2f} (dos de ellos)."
        )

        # El guardarraíl de muestra corta mira la muestra COMPLETA y nunca las
        # ventanas de entrenamiento, que son mucho más cortas: en «1 Año» y «3
        # Años» se entrena con 24 observaciones y la pantalla no decía nada.
        _por_activo_entreno = wf["train_size"] / len(valid_tickers)
        if _por_activo_entreno < 30:
            st.warning(
                f"**Cada ventana se entrena con {wf['train_size']} observaciones "
                f"para {len(valid_tickers)} activos** "
                f"({_por_activo_entreno:.0f} por activo, recomendado >30). El aviso "
                "de muestra corta de arriba mira el historial entero; la validación "
                "reoptimiza sobre trozos mucho más cortos, y ahí los pesos de cada "
                "ventana son ruido aunque la muestra completa parezca suficiente."
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
                "Sharpe medio en muestra": f"{res['in_sample_sharpe']:.2f}",
                "Sharpe medio fuera": f"{res['out_of_sample_sharpe_medio']:.2f}",
                "Sharpe fuera agrupado": f"{res['out_of_sample_sharpe']:.2f}",
                "Retorno anual (fuera)": f"{res['oos_return']:.1%}",
                "Volatilidad (fuera)": f"{res['oos_vol']:.1%}",
                # El listón ya multiplicado, no el error suelto: poner «±0,28»
                # al lado de un hueco que se juzga contra 0,56 es pedirle al
                # lector que compare contra el número equivocado.
                "Diferencia vs 1/N": (
                    f"{res['out_of_sample_sharpe'] - res['equal_weight_sharpe']:+.2f}"
                    f"  (hace falta {res['umbral_veredicto']:.2f})"
                ),
            })
        filas.append({
            "Estrategia": "Equal Weight 1/N (referencia)",
            "Sharpe medio en muestra": "—",
            "Sharpe medio fuera": "—",
            "Sharpe fuera agrupado": f"{wf['equal_weight_sharpe']:.2f}",
            "Retorno anual (fuera)": "—",
            "Volatilidad (fuera)": "—",
            "Diferencia vs 1/N": "—",
        })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
        _descartadas = corrida["comparacion"]["n_windows_descartadas"]
        st.caption(
            f"Las tres estrategias recorren exactamente las mismas "
            f"{wf['n_windows']} ventanas y se miden contra el mismo 1/N"
            + (f", descartando {_descartadas} donde alguna no convergió" if _descartadas
               else "")
            + ". Una diferencia contra 1/N que no llegue a lo que pide la columna "
            "de la derecha —dos errores estándar— no se distingue del ruido. "
            "«Medio» es la media de los cocientes de cada ventana y «agrupado» el "
            "cociente de todos los períodos juntos: son dos estimadores del mismo "
            "número, y sólo los medios se pueden restar entre sí."
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
    # Cuatro columnas donde antes habia tres, y la del boton largo es la mas
    # ancha: "Guardar y empezar a seguirlo" son 28 caracteres, y con menos de
    # 4/12 del ancho la etiqueta se parte en dos lineas en cuanto la ventana
    # baja de 1100 px.
    col_nombre, col_nota, col_seguir, col_guardar = st.columns([3, 3, 4, 2])
    nombre = col_nombre.text_input("Nombre", key="nombre_portafolio", max_chars=60)

    # **Guardar no sobrescribe, y eso es deliberado** --una fotografia que
    # quiza ya estas siguiendo en un libro no se pisa-- pero hasta ahora
    # tampoco lo decia: guardar dos veces con el mismo nombre dejaba dos
    # entradas indistinguibles en la lista y nadie avisaba. Se dice ANTES, que
    # es cuando el usuario todavia puede elegir otro.
    # La misma normalizacion que `cartera.normalizar_nombre` --recortar y juntar
    # espacios-- pero sin su excepcion: aqui solo se compara, y un nombre
    # todavia vacio o demasiado largo no es un error que toque gritar mientras
    # se escribe. `guardar` ya lo rechazara si llega asi.
    _comparable = " ".join(nombre.split())
    if _comparable and _comparable in _nombres_usados():
        st.warning(
            f"Ya tienes un portafolio llamado **{nombre.strip()}**. Guardar no "
            "lo sobrescribe: se quedan los dos, y en la lista se verán con el "
            "mismo nombre. Cambia el nombre aquí, o renombra el viejo desde "
            "**Portafolios guardados**."
        )
    nota = col_nota.text_input(
        "Nota (opcional)", key="nota_portafolio",
        placeholder="Por qué guardas esta corrida",
    )
    for _columna in (col_seguir, col_guardar):
        _columna.write("")
        _columna.write("")

    def _guardar(nombre: str, nota: str):
        """El portafolio guardado, o None si no se pudo, ya avisando en pantalla.

        Devuelve el objeto y no solo la ruta porque el boton de seguir necesita
        metersela a `portafolio_a_seguir`, que es lo que la pantalla de estreno
        lee. Volver a cargarlo del disco seria leer lo que acabamos de escribir.
        """
        # `desde_corrida` va DENTRO del try: es quien llama a
        # `normalizar_nombre`, o sea quien lanza `NombreInvalido`. `guardar` no
        # lo lanza nunca. Dejarlo fuera cambiaria el error en pantalla por un
        # traceback de Streamlit.
        try:
            portafolio = cartera.desde_corrida(
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
            destino = cartera.guardar(portafolio)
        except cartera.NombreInvalido as error:
            st.error(str(error))
            return None
        except OSError as error:
            st.error(f"No se pudo guardar: {error}")
            return None
        # El «esta en Portafolios guardados» no es adorno: en el camino que NO
        # salta, es la unica senal de adonde fue a parar, y la queja que abrio
        # este sub-proyecto era precisamente que la ruta no se veia. (Desde el
        # boton principal este mensaje no llega a leerse, porque `switch_page`
        # se lleva la pantalla en la misma re-ejecucion; alli el acuse es
        # aterrizar en el estreno con el nombre en el encabezado.)
        _NOMBRES_USADOS.clear()
        st.success(f"Guardado en {destino}. Está en **Portafolios guardados**.")
        return portafolio

    # Guardar y seguir son actos distintos: se pueden archivar tres corridas y
    # seguir una sola. Por eso hay dos botones y no un salto automatico.
    if col_seguir.button("Guardar y empezar a seguirlo", type="primary",
                         use_container_width=True,
                         disabled=not nombre.strip()):
        guardado = _guardar(nombre, nota)
        # Solo se salta si de verdad se guardo: saltar tras un fallo dejaria al
        # usuario en la pantalla de estreno de un portafolio que no existe.
        if guardado is not None:
            st.session_state.portafolio_a_seguir = guardado
            st.switch_page("vistas/estrenar.py")

    if col_guardar.button("Guardar", use_container_width=True,
                          icon=":material/save:", disabled=not nombre.strip()):
        _guardar(nombre, nota)

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
    # **El PDF se genera cuando se pide, no en cada re-ejecución.** `data=` de
    # `st.download_button` es un argumento normal: se evalúa SIEMPRE, y dentro
    # hay cuatro `write_image` que arrancan Chromium por kaleido. Medido: 8,8
    # segundos, sin caché, en cada cambio de pestaña, cada tecla del nombre del
    # portafolio y cada pulsación de cualquier botón de la pantalla. El PDF
    # estaba bien (33,8 KB); el problema era cuándo.
    #
    # El botón previo lo genera una vez y lo deja en sesión atado a la firma de
    # esta corrida, para que una corrida nueva no ofrezca el informe de la
    # anterior.
    _firma_pdf = (
        tuple(valid_tickers), corrida["horizonte"], corrida["estrategia"],
        tuple(np.round(optimal["weights"], 8).tolist()),
    )
    _pdf = st.session_state.get("pdf_informe")
    if _pdf is not None and _pdf["firma"] != _firma_pdf:
        _pdf = None
        st.session_state.pop("pdf_informe", None)

    if _pdf is None:
        if col_pdf.button("Preparar PDF", use_container_width=True,
                          icon=":material/picture_as_pdf:"):
            with st.spinner("Generando el PDF (tarda unos segundos)…"):
                st.session_state.pdf_informe = {
                    "firma": _firma_pdf,
                    "datos": to_pdf(
                        weights_df, metrics,
                        [fig_frontier, fig_pie, fig_corr, fig_comp],
                    ),
                }
            st.rerun()
    else:
        col_pdf.download_button(
            "Descargar PDF",
            data=_pdf["datos"],
            file_name=f"markowitz_{corrida['horizonte'].replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            icon=":material/picture_as_pdf:",
        )
