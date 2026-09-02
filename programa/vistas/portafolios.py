"""Los portafolios guardados: verlos, volver a cargarlos y borrarlos."""

import pandas as pd
import streamlit as st

import cartera
import tema
from optimizer import STRATEGY_LABELS

st.markdown(
    tema.cabecera(
        "Portafolios guardados",
        "Cada uno es una fotografía de una optimización: los pesos y las "
        "métricas que salieron ese día, con su fecha. Cargarlo rellena el "
        "optimizador con sus parámetros; volver a optimizar es un acto aparte.",
    ),
    unsafe_allow_html=True,
)

entradas = cartera.listar()

if not entradas:
    st.info(
        "Todavía no has guardado ninguno. Optimiza una cartera y guárdala desde "
        "la pestaña **Guardar y exportar** del optimizador."
    )
    if st.button("Ir al optimizador", icon=":material/insights:"):
        st.switch_page("vistas/optimizador.py")
    st.stop()

st.caption(
    f"{len(entradas)} guardados en `{cartera.DIRECTORIO}/`, del más reciente al "
    "más antiguo."
)

for entrada in entradas:
    # Los ilegibles se pintan igual, con su motivo y su boton de borrar: esta es
    # la unica pantalla desde la que se puede quitar de en medio un fichero
    # roto, y esconderlo dejaria al usuario buscandolo en la carpeta.
    if entrada.portafolio is None:
        with st.container(border=True):
            st.error(f"`{entrada.ruta.name}` no se puede leer: {entrada.error}")
            if st.button(
                "Borrar este fichero", key=f"borrar_roto_{entrada.ruta.name}",
                icon=":material/delete:",
            ):
                cartera.borrar(entrada.ruta)
                st.rerun()
        continue

    p = entrada.portafolio
    with st.container(border=True):
        cabecera, acciones = st.columns([3, 1])
        with cabecera:
            st.markdown(f"#### {p.nombre}")
            st.markdown(
                tema.etiqueta(p.fecha_legible)
                + tema.etiqueta(STRATEGY_LABELS.get(p.estrategia, p.estrategia), "acento")
                + tema.etiqueta(f"Horizonte {p.horizonte}")
                + tema.etiqueta(f"{len(p.posiciones)} activos")
                + (tema.etiqueta("Ventas en corto", "aviso") if p.permitir_cortos else "")
                + tema.etiqueta(
                    "Estimación robusta" if p.shrinkage else "Estimación clásica",
                    "bueno" if p.shrinkage else "aviso",
                ),
                unsafe_allow_html=True,
            )
            if p.nota:
                st.caption(p.nota)

        with acciones:
            if st.button(
                "Cargar en el optimizador", key=f"cargar_{entrada.ruta.name}",
                use_container_width=True, type="primary", icon=":material/upload:",
            ):
                st.session_state.portafolio_a_cargar = p
                st.switch_page("vistas/optimizador.py")

            confirmando = st.session_state.get("borrando") == str(entrada.ruta)
            if not confirmando:
                if st.button(
                    "Borrar", key=f"borrar_{entrada.ruta.name}",
                    use_container_width=True, icon=":material/delete:",
                ):
                    # Borrar es irreversible y el fichero es lo unico que queda
                    # de esa corrida: se pregunta antes, siempre.
                    st.session_state.borrando = str(entrada.ruta)
                    st.rerun()
            else:
                st.warning("¿Seguro? No se puede deshacer.")
                si, no = st.columns(2)
                if si.button("Sí, borrar", key=f"si_{entrada.ruta.name}",
                             use_container_width=True):
                    cartera.borrar(entrada.ruta)
                    st.session_state.pop("borrando", None)
                    st.rerun()
                if no.button("Cancelar", key=f"no_{entrada.ruta.name}",
                             use_container_width=True):
                    st.session_state.pop("borrando", None)
                    st.rerun()

        metricas = p.metricas or {}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sharpe (en muestra)", cartera.formato_cifra(metricas.get("sharpe")))
        m2.metric("Sharpe fuera de muestra", cartera.formato_cifra(metricas.get("oos_sharpe")))
        m3.metric("Retorno anual", cartera.formato_porcentaje(metricas.get("annual_return")))
        m4.metric("Volatilidad anual", cartera.formato_porcentaje(metricas.get("annual_vol")))

        with st.expander(f"Pesos de {p.nombre}"):
            st.dataframe(
                pd.DataFrame({
                    "Ticker": p.tickers,
                    "Peso": [f"{peso:.2%}" for peso in p.pesos],
                }),
                use_container_width=True, hide_index=True,
            )
            st.caption(f"Fichero: `{entrada.ruta}`")
