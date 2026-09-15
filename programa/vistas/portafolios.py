"""Los portafolios guardados: verlos, volver a cargarlos y borrarlos."""

import pandas as pd
import streamlit as st

import cartera
import tema
from optimizer import STRATEGY_LABELS
from validation import (
    frase_identificabilidad,
    identificabilidad_guardada,
    veredicto_guardado,
)

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
            # **Abierto mientras haya cambios sin guardar.** Un `st.text_input`
            # relanza el guion al pulsar Enter o al salir del campo, y en esa
            # pasada el desplegable vuelve a nacer cerrado: escribias el nombre,
            # pulsabas Enter --que es lo natural-- y el formulario se cerraba con
            # el cambio sin guardar y el boton fuera de alcance. Visto en la app;
            # no se ve de otra forma.
            #
            # Se compara el estado del widget contra lo que hay en el fichero, asi
            # que despues de guardar los dos coinciden y se cierra solo.
            clave_nom = f"nom_{entrada.ruta.name}"
            clave_nota = f"nota_{entrada.ruta.name}"
            editando = (
                st.session_state.get(clave_nom, p.nombre) != p.nombre
                or st.session_state.get(clave_nota, p.nota) != p.nota
            )
            with st.expander("Cambiar nombre o nota", expanded=editando):
                nuevo_nombre = st.text_input("Nombre", value=p.nombre, key=clave_nom)
                nueva_nota = st.text_input("Nota", value=p.nota, key=clave_nota)
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
        m1.metric(
            "Sharpe del ajuste único",
            cartera.formato_cifra(metricas.get("sharpe")),
            help="Medido sobre los mismos datos con los que se optimizó ese día. "
            "Es una cota superior, no una expectativa.",
        )
        m2.metric(
            "Sharpe fuera de muestra",
            cartera.formato_cifra(metricas.get("oos_sharpe")),
            help="El único de los cuatro que se midió sobre datos que el "
            "optimizador no había visto.",
        )
        # «Retorno anual» a secas, y sin la ayuda que sí tiene el optimizador: un
        # guardado lucía **144,91%** como si fuera lo que la cartera renta. Es la
        # media aritmética anualizada de la ventana con la que se optimizó —la
        # convención de Markowitz— y ni capitaliza ni se espera que se repita.
        m3.metric(
            "Retorno anual esperado",
            cartera.formato_porcentaje(metricas.get("annual_return")),
            help="Media aritmética anualizada (μ×períodos) sobre la muestra con la "
            "que se optimizó, la convención de Markowitz. No es un CAGR ni una "
            "previsión: sobre unos pocos meses de datos esta cifra se dispara con "
            "facilidad, y su error estándar es de varios puntos porcentuales.",
        )
        m4.metric("Volatilidad anual", cartera.formato_porcentaje(metricas.get("annual_vol")))

        # **El color y el texto salen del MISMO dictamen.** El color se
        # pintaba con el `beats_equal_weight` GUARDADO —dictado cuando bastaba
        # un error estándar— y la frase de al lado se recalculaba con el listón
        # de hoy, que son dos: un hueco de +0,350 con un error de ±0,20 salía en
        # VERDE con «estos datos no distinguen esta cartera de repartir por
        # igual» escrito dentro. Un recuadro no puede decir dos cosas, así que
        # `veredicto_guardado` dicta una sola vez y devuelve las dos.
        _oos = metricas.get("oos_sharpe")
        _ew = metricas.get("oos_equal_weight_sharpe")
        _dictamen = veredicto_guardado(metricas)
        if _dictamen is not None:
            _pintar = {True: st.success, False: st.warning}.get(
                _dictamen["estado"], st.info
            )
            _texto = f"{_dictamen['frase']} (Equal Weight: {cartera.formato_cifra(_ew)}.)"
            if _dictamen["discrepa"]:
                # Cambiar el veredicto en silencio sería peor que el defecto que
                # se está arreglando: el usuario recuerda lo que leyó el día que
                # lo guardó, y tiene derecho a saber que el listón cambió.
                _texto += (
                    " Este fichero guarda otro veredicto, dictado con el listón "
                    "de entonces —un error estándar en vez de dos—; arriba está "
                    "el de hoy."
                )
            _pintar(_texto)
        elif _oos is not None:
            st.info(
                "Este fichero es anterior al error de la diferencia contra 1/N, "
                "así que su Sharpe fuera de muestra no viene con barra de error y "
                "no se puede decir si le ganaba a repartir por igual."
            )

        with st.expander(f"Pesos de {p.nombre}"):
            # El mismo aviso que vio quien optimizó, re-dictado a partir de la
            # medición que el fichero guarda. Los portafolios anteriores a esto
            # no la llevan y ahí no se afirma nada: `identificabilidad_guardada`
            # devuelve None y no se escribe línea alguna.
            _identificabilidad = identificabilidad_guardada(metricas)
            if _identificabilidad is not None:
                _frase = frase_identificabilidad(_identificabilidad)
                if _identificabilidad["identificada"]:
                    st.caption(_frase)
                else:
                    st.warning(_frase)
            st.dataframe(
                pd.DataFrame({
                    "Ticker": p.tickers,
                    "Peso": [f"{peso:.2%}" for peso in p.pesos],
                }),
                use_container_width=True, hide_index=True,
            )
            st.caption(f"Fichero: `{entrada.ruta}`")
