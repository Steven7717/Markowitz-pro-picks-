"""Dos o más portafolios guardados, enfrentados."""

import pandas as pd
import streamlit as st

import cartera
import tema
from optimizer import STRATEGY_LABELS

st.markdown(
    tema.cabecera(
        "Comparar portafolios",
        "Pon lado a lado lo que guardaste. Cada columna es la fotografía de una "
        "corrida distinta, no una simulación común.",
    ),
    unsafe_allow_html=True,
)

entradas = [e for e in cartera.listar() if e.portafolio is not None]

if len(entradas) < 2:
    st.info(
        "Hacen falta al menos dos portafolios guardados para comparar. Ahora "
        f"mismo hay {len(entradas)}."
    )
    if st.button("Ir al optimizador", icon=":material/insights:"):
        st.switch_page("vistas/optimizador.py")
    st.stop()

por_etiqueta = {
    f"{e.portafolio.nombre} · {e.portafolio.fecha_legible}": e.portafolio
    for e in entradas
}
elegidos = st.multiselect(
    "Portafolios a comparar",
    options=list(por_etiqueta),
    default=list(por_etiqueta)[:2],
    help="La fecha va en la etiqueta porque dos guardados pueden llamarse igual.",
)

if len(elegidos) < 2:
    st.info("Elige al menos dos.")
    st.stop()

seleccion = [por_etiqueta[etiqueta] for etiqueta in elegidos]

# La advertencia que hace honesta a esta pantalla. Dos carteras optimizadas
# sobre horizontes distintos no compiten: sus Sharpe salen de muestras
# diferentes, con distinta frecuencia de datos y distinto numero de
# observaciones. Ponerlas en la misma tabla sin decirlo invita justo a la
# comparacion que los numeros no sostienen.
horizontes = {p.horizonte for p in seleccion}
if len(horizontes) > 1:
    st.warning(
        "Estás comparando portafolios con horizontes distintos ("
        + ", ".join(sorted(horizontes))
        + "). Sus métricas salen de muestras diferentes, con otra frecuencia de "
        "datos y otro número de observaciones: las cifras se pueden leer una a "
        "una, pero la diferencia entre ellas no mide cuál es mejor."
    )

fechas = {p.fecha[:10] for p in seleccion}
if len(fechas) > 1:
    st.caption(
        "Guardados en fechas distintas ("
        + ", ".join(sorted(fechas))
        + "): cada uno vio los precios que había ese día."
    )

# ── Métricas enfrentadas ─────────────────────────────────────────────────────
st.markdown("#### Métricas")
filas = []
for p in seleccion:
    m = p.metricas or {}
    filas.append({
        "Portafolio": p.nombre,
        "Guardado": p.fecha_legible,
        "Estrategia": STRATEGY_LABELS.get(p.estrategia, p.estrategia),
        "Horizonte": p.horizonte,
        "Activos": len(p.posiciones),
        "Sharpe (en muestra)": cartera.formato_cifra(m.get("sharpe")),
        "Sharpe (fuera)": cartera.formato_cifra(m.get("oos_sharpe")),
        "Equal Weight (fuera)": cartera.formato_cifra(m.get("oos_equal_weight_sharpe")),
        "Retorno anual": cartera.formato_porcentaje(m.get("annual_return")),
        "Volatilidad anual": cartera.formato_porcentaje(m.get("annual_vol")),
    })
st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
st.caption(
    "Un guion significa que esa métrica no se guardó, no que valga cero: los "
    "portafolios guardados antes de que existiera un campo no lo tienen."
)

# ── Pesos enfrentados ────────────────────────────────────────────────────────
st.markdown("#### Pesos por activo")
matriz: dict[str, dict[str, float]] = {}
for p in seleccion:
    for ticker, peso in zip(p.tickers, p.pesos):
        matriz.setdefault(ticker, {})[p.nombre] = peso

# Un activo que no esta en una cartera sale vacio, no a cero: son cosas
# distintas. Un cero significaria "se considero y se le dio peso nulo", y en la
# mayoria de los casos ni siquiera estaba en la lista de entrada.
pesos = pd.DataFrame(
    [
        {"Ticker": ticker, **{
            p.nombre: (
                f"{columnas[p.nombre]:.2%}" if p.nombre in columnas else "—"
            )
            for p in seleccion
        }}
        for ticker, columnas in sorted(matriz.items())
    ]
)
st.dataframe(pesos, use_container_width=True, hide_index=True)

comunes = set.intersection(*(set(p.tickers) for p in seleccion))
todos = set.union(*(set(p.tickers) for p in seleccion))
st.caption(
    f"{len(comunes)} activos aparecen en todos los portafolios elegidos, de "
    f"{len(todos)} distintos en total. Un guion significa que ese activo no "
    "estaba en esa cartera, no que se le asignara un peso de cero."
)

st.divider()
cargar = st.selectbox(
    "Cargar uno en el optimizador", options=[p.nombre for p in seleccion]
)
if st.button("Cargar", type="primary", icon=":material/upload:"):
    st.session_state.portafolio_a_cargar = next(
        p for p in seleccion if p.nombre == cargar
    )
    st.switch_page("vistas/optimizador.py")
