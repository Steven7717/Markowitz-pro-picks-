"""El historial de aprobaciones del gate, leído desde `actas/`."""

from datetime import datetime

import pandas as pd
import streamlit as st

import tema
from aprobacion.acta import listar_actas, tickers_aprobados

st.markdown(
    tema.cabecera(
        "Actas de aprobación",
        "Cada acta es el registro de una revisión: qué se aprobó, qué no, y con "
        "qué motivo. Se escriben antes del traspaso al optimizador y no se "
        "modifican después.",
    ),
    unsafe_allow_html=True,
)

guardadas = listar_actas()

if not guardadas:
    st.info(
        "Todavía no hay ninguna. Se crean al aprobar candidatos desde "
        "**Revisar candidatos**."
    )
    if st.button("Ir a revisar candidatos", icon=":material/fact_check:"):
        st.switch_page("vistas/candidatos.py")
    st.stop()

st.caption(f"{len(guardadas)} actas, de la más reciente a la más antigua.")


def _fecha_legible(crudo: str) -> str:
    try:
        return datetime.fromisoformat(crudo).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        # Una fecha ilegible no puede dejar la lista entera sin pintar: el resto
        # del acta sigue siendo un registro válido.
        return str(crudo)


for guardada in guardadas:
    if guardada.acta is None:
        with st.container(border=True):
            st.error(f"`{guardada.ruta.name}`: {guardada.error}")
        continue

    acta = guardada.acta
    aprobados = acta["aprobados"]
    no_aprobados = acta["no_aprobados"]
    # Los descartados con motivo escrito y los que simplemente no se marcaron
    # son cosas distintas, y el acta las guarda juntas a proposito: sin el
    # motivo no se puede afirmar que alguien mirase esa empresa y la rechazara.
    con_motivo = [n for n in no_aprobados if n.get("motivo")]

    with st.container(border=True):
        cabecera, accion = st.columns([3, 1])
        with cabecera:
            st.markdown(f"#### {_fecha_legible(acta['fecha'])}")
            st.markdown(
                tema.etiqueta(f"{len(aprobados)} aprobadas", "bueno")
                + tema.etiqueta(f"{len(no_aprobados)} no aprobadas")
                + tema.etiqueta(f"{len(con_motivo)} con motivo escrito", "info"),
                unsafe_allow_html=True,
            )
            corrida = acta.get("corrida") or {}
            if corrida:
                st.caption(
                    f"Universo {corrida.get('universo', '?')} · "
                    f"{corrida.get('n_supervivientes', '?')} supervivientes de "
                    f"{corrida.get('n_panel', '?')} empresas con datos · "
                    + ("con IA" if corrida.get("con_llm") else "sin IA")
                )
            else:
                st.caption(
                    "Sin metadatos de corrida: este acta se escribió antes de que "
                    "se registraran."
                )

        with accion:
            tickers = tickers_aprobados(acta)
            if st.button(
                "Cargar en el optimizador", key=f"cargar_{guardada.ruta.name}",
                use_container_width=True, type="primary", icon=":material/upload:",
                disabled=not tickers,
            ):
                # Se reutiliza el mismo canal que usa el gate para el traspaso,
                # asi el optimizador no tiene que saber de donde vino la lista.
                st.session_state.tickers_aprobados = tickers
                st.session_state.pop("origen_cargado", None)
                st.switch_page("vistas/optimizador.py")

        with st.expander("Ver el detalle"):
            st.markdown("**Aprobadas**")
            st.dataframe(
                pd.DataFrame([
                    {
                        "Ticker": entrada["ticker"],
                        "Puesto": entrada.get("puesto") or "añadida a mano",
                        "Motivo": entrada.get("motivo") or "",
                    }
                    for entrada in aprobados
                ]),
                use_container_width=True, hide_index=True,
            )
            if con_motivo:
                st.markdown("**Descartadas con motivo escrito**")
                st.dataframe(
                    pd.DataFrame([
                        {"Ticker": n["ticker"], "Motivo": n["motivo"]}
                        for n in con_motivo
                    ]),
                    use_container_width=True, hide_index=True,
                )
            sin_motivo = len(no_aprobados) - len(con_motivo)
            if sin_motivo:
                st.caption(
                    f"Otras {sin_motivo} quedaron sin marcar y sin motivo. El acta "
                    "no las llama rechazadas: no marcar una casilla puede significar "
                    "que se miró y se descartó, o que no se llegó a mirar, y sin el "
                    "motivo escrito no hay forma de saber cuál de las dos fue."
                )
            st.caption(f"Fichero: `{guardada.ruta}`")
