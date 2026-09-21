"""Dos o más portafolios guardados, enfrentados."""

import pandas as pd
import streamlit as st

import cartera
import comparativa
import tema
from data import HORIZON_LABELS
from optimizer import STRATEGY_LABELS

st.markdown(
    tema.cabecera(
        "Comparar portafolios",
        "Pon lado a lado lo que guardaste. Cada columna es la fotografía de una "
        "corrida distinta, no una simulación común.",
    ),
    unsafe_allow_html=True,
)

# Las etiquetas las construye `comparativa` y no esta pantalla: dos
# guardados con el mismo nombre en el mismo minuto producian la misma
# clave, y el que llegaba segundo desaparecia sin decir nada.
por_etiqueta = comparativa.etiquetar(cartera.listar())

if len(por_etiqueta) < 2:
    st.info(
        "Hacen falta al menos dos portafolios guardados para comparar. Ahora "
        f"mismo hay {len(por_etiqueta)}."
    )
    if st.button("Ir al optimizador", icon=":material/insights:"):
        st.switch_page("vistas/optimizador.py")
    st.stop()

elegidos = st.multiselect(
    "Portafolios a comparar",
    options=list(por_etiqueta),
    default=list(por_etiqueta)[:2],
    help="La fecha va en la etiqueta porque dos guardados pueden llamarse igual.",
)

if len(elegidos) < 2:
    st.info("Elige al menos dos.")
    st.stop()

elegidas = {etiqueta: por_etiqueta[etiqueta] for etiqueta in elegidos}
seleccion = list(elegidas.values())

# La advertencia que hace honesta a esta pantalla. Dos carteras optimizadas
# sobre horizontes distintos no compiten: sus Sharpe salen de muestras
# diferentes, con distinta frecuencia de datos y distinto numero de
# observaciones. Ponerlas en la misma tabla sin decirlo invita justo a la
# comparacion que los numeros no sostienen.
horizontes = {HORIZON_LABELS.get(p.horizonte, p.horizonte) for p in seleccion}
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
        "Horizonte": HORIZON_LABELS.get(p.horizonte, p.horizonte),
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
st.dataframe(
    pd.DataFrame(comparativa.matriz_de_pesos(elegidas)),
    use_container_width=True, hide_index=True,
)
st.caption(comparativa.frase_de_cobertura(elegidas))

st.divider()
# Por etiqueta y no por nombre: con dos guardados que se llaman igual,
# `next(p for p in seleccion if p.nombre == cargar)` devolvia siempre el
# primero, que podia no ser el que el usuario acababa de elegir.
cargar = st.selectbox("Cargar uno en el optimizador", options=list(elegidas))
if st.button("Cargar", type="primary", icon=":material/upload:"):
    st.session_state.portafolio_a_cargar = elegidas[cargar]
    st.switch_page("vistas/optimizador.py")
