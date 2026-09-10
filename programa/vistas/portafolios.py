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

# El renombrado termina en `st.rerun()`, que tira la pasada antes de
# dibujarla, asi que su confirmacion viaja por `session_state`. Mismo remedio
# que el alta y la anulacion en `vistas/seguimiento.py`.
if _aviso := st.session_state.pop("portafolios_aviso", ""):
    st.success(_aviso)

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

            # Renombrar. **Solo el nombre y la nota**: lo demas lo calculo el
            # optimizador para esta lista exacta de tickers, y cambiarlo aqui
            # dejaria numeros que pertenecen a otra cartera. Ver
            # `cartera.reetiquetar`.
            with st.expander("Cambiar nombre o nota"):
                nuevo_nombre = st.text_input(
                    "Nombre", value=p.nombre, key=f"nom_{entrada.ruta.name}"
                )
                nueva_nota = st.text_input(
                    "Nota", value=p.nota, key=f"nota_{entrada.ruta.name}"
                )
                st.caption(
                    "Los activos, los pesos y las métricas no se tocan aquí: los "
                    "calculó el optimizador para esta lista exacta. Para cambiarlos, "
                    "**Cargar en el optimizador** y volver a correr."
                )
                if st.button(
                    "Guardar cambios", key=f"reet_{entrada.ruta.name}",
                    icon=":material/save:",
                ):
                    try:
                        cartera.reetiquetar(
                            p, entrada.ruta, nuevo_nombre, nueva_nota
                        )
                    except cartera.NombreInvalido as error:
                        st.error(str(error))
                    else:
                        # Por `session_state` y no aqui: `st.rerun()` se lleva
                        # por delante la pasada que lo escribiria.
                        st.session_state["portafolios_aviso"] = (
                            f"Renombrado a «{nuevo_nombre.strip()}»."
                        )
                        st.rerun()

        with acciones:
            if st.button(
                "Cargar en el optimizador", key=f"cargar_{entrada.ruta.name}",
                use_container_width=True, type="primary", icon=":material/upload:",
            ):
                st.session_state.portafolio_a_cargar = p
                st.switch_page("vistas/optimizador.py")

            if st.button(
                "Empezar a seguir", key=f"seguir_{entrada.ruta.name}",
                use_container_width=True, icon=":material/monitoring:",
            ):
                st.session_state.portafolio_a_seguir = p
                st.switch_page("vistas/estrenar.py")

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
