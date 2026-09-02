"""Perfil y ajustes: las credenciales, los valores por defecto y dónde vive todo.

Las credenciales vivían dentro de la página de candidatos, y eso obligaba a esa
página a hacer un baile delicado: un `st.rerun()` lanzado desde el desplegable
de credenciales se disparaba antes de que se dibujaran las casillas de
aprobación, Streamlit descartaba el estado de los widgets que no llegó a ver, y
la revisión en curso desaparecía sin decir nada. Existía una función entera
(`_recargar_si_toca`) para posponer esas recargas hasta el final del guion.

Al mudarse aquí, ese peligro deja de existir: en esta pantalla no hay ningún
trabajo a medias que una recarga pueda tirar a la basura.
"""

import streamlit as st

import cartera
import preferencias as preferencias_mod
import tema
from credenciales import (
    RUTA as RUTA_CREDENCIALES,
    CredencialInvalida,
    Credenciales,
    avisos,
    borrar,
    cargar,
    enmascarar,
    reemplazar,
    variables_del_shell,
)
from credenciales import guardar as guardar_credenciales
from data import HORIZON_CONFIG
from optimizer import STRATEGY_LABELS
from preferencias import Preferencias

st.markdown(
    tema.cabecera(
        "Perfil y ajustes",
        "Tus credenciales y los valores con los que arranca el optimizador. "
        "Ambos se guardan en tu carpeta personal, fuera del proyecto.",
    ),
    unsafe_allow_html=True,
)

credenciales_tab, preferencias_tab, datos_tab = st.tabs(
    ["Credenciales", "Valores por defecto", "Dónde vive todo"]
)

# ── Credenciales ─────────────────────────────────────────────────────────────
with credenciales_tab:
    for texto in st.session_state.pop("avisos_credenciales", []):
        st.warning(texto)

    roto = st.session_state.get("credenciales_rotas")
    if roto:
        st.warning(
            f"{roto}\n\nGuarda las credenciales otra vez para reemplazarlo, o borra "
            "el fichero a mano."
        )

    guardadas = st.session_state.get("credenciales") or Credenciales()

    st.markdown(
        f"Se guardan en `{RUTA_CREDENCIALES}`, **fuera de este proyecto**: si "
        "comprimes la carpeta y se la pasas a alguien, tu clave no viaja dentro."
    )

    # La regla de precedencia vive en credenciales.py, no aqui: es la misma que
    # aplica aplicar(), y repetirla seria dejar dos versiones que se pueden
    # separar.
    desde_entorno = variables_del_shell(guardadas)
    if desde_entorno:
        st.info(
            "Ahora mismo manda el entorno para "
            + " y ".join(f"`{nombre}`" for nombre in desde_entorno)
            + ". Lo que guardes aquí no lo pisa."
        )

    editando = st.session_state.get("editando_credenciales")
    if guardadas.api_key and not editando:
        clave, cambiar, quitar = st.columns([4, 1, 1])
        clave.text_input(
            "Clave de Anthropic", value=enmascarar(guardadas.api_key), disabled=True
        )
        cambiar.write("")
        cambiar.write("")
        if cambiar.button("Cambiar", use_container_width=True):
            st.session_state.editando_credenciales = True
            st.rerun()
        quitar.write("")
        quitar.write("")
        if quitar.button("Borrar", use_container_width=True):
            try:
                borrar()
            except OSError as error:
                st.error(f"No se pudo borrar: {error}")
            else:
                st.session_state.pop("credenciales", None)
                st.rerun()
        st.text_input(
            "Correo para EDGAR", value=guardadas.edgar_identity or "", disabled=True
        )
    else:
        nueva_clave = st.text_input(
            "Clave de Anthropic",
            type="password",
            key="entrada_clave",
            help="Se saca de console.anthropic.com. Empieza por sk-ant-.",
        )
        nuevo_correo = st.text_input(
            "Correo para EDGAR",
            value=guardadas.edgar_identity or "",
            key="entrada_correo",
            help="No es un registro: la SEC exige un contacto en la cabecera de "
            "cada petición y sólo se envía ahí.",
        )
        guardar_col, cancelar_col = st.columns([1, 1])
        if guardar_col.button("Guardar credenciales", type="primary",
                              icon=":material/save:"):
            nuevas = Credenciales(
                api_key=nueva_clave or guardadas.api_key,
                edgar_identity=nuevo_correo,
            )
            try:
                guardar_credenciales(nuevas)
            except CredencialInvalida as error:
                st.error(str(error))
            except OSError as error:
                st.error(f"No se pudieron guardar: {error}")
            else:
                # reemplazar y no aplicar: aplicar() no pisa lo que ya hay en el
                # entorno, y despues de arrancar siempre hay algo -- lo puso el
                # propio aplicar(). Con aplicar() aqui, cambiar una clave
                # revocada la guardaria en disco y el proceso seguiria usando la
                # vieja toda la sesion, con esta pantalla mostrando la nueva
                # enmascarada.
                reemplazar(guardadas, nuevas)
                st.session_state.avisos_credenciales = avisos(nuevas)
                st.session_state.credenciales = nuevas
                st.session_state.editando_credenciales = False
                st.rerun()

        # Solo si hay algo guardado a lo que volver: sin esto, quien pulsa
        # "Cambiar" y se arrepiente se queda ante un campo vacio donde estaba su
        # clave, sin Borrar y sin vuelta atras que no sea reiniciar.
        if guardadas.api_key and cancelar_col.button("Cancelar"):
            st.session_state.editando_credenciales = False
            st.rerun()

    st.divider()
    st.markdown(
        "**Para qué sirve cada una**\n\n"
        "- **Correo para EDGAR** — obligatorio para generar candidatos, con IA o "
        "sin ella. La SEC exige un contacto en la cabecera de cada petición y "
        "rechaza las que no lo llevan, así que sin él no hay datos que descargar.\n"
        "- **Clave de Anthropic** — opcional. Sólo la necesita la mitad con IA, "
        "que redacta la tesis y verifica las citas del informe anual. Sin ella el "
        "ranking sale igual, con fichas de plantilla."
    )

# ── Valores por defecto ──────────────────────────────────────────────────────
with preferencias_tab:
    actuales, avisos_preferencias = preferencias_mod.cargar()
    for aviso in avisos_preferencias:
        st.warning(aviso)

    st.caption(
        "Con esto arranca el optimizador cada vez que lo abres. Cambiarlo aquí no "
        "toca ninguna corrida ya guardada."
    )

    with st.form("preferencias"):
        tickers = st.text_input(
            "Activos por defecto",
            value=actuales.tickers,
            placeholder="Déjalo vacío para usar la lista de ejemplo",
            help="Los tickers que aprueba el gate siempre ganan a esto.",
        )
        col_horizonte, col_estrategia = st.columns([1, 2])
        horizonte = col_horizonte.selectbox(
            "Horizonte", options=list(HORIZON_CONFIG),
            index=list(HORIZON_CONFIG).index(actuales.horizonte),
        )
        estrategia = col_estrategia.radio(
            "Estrategia", options=list(STRATEGY_LABELS),
            format_func=lambda k: STRATEGY_LABELS[k],
            index=list(STRATEGY_LABELS).index(actuales.estrategia),
            horizontal=True,
        )
        col_min, col_max = st.columns(2)
        peso_min = col_min.slider("Peso mínimo por activo (%)", 0, 20, actuales.peso_min)
        peso_max = col_max.slider("Peso máximo por activo (%)", 20, 100, actuales.peso_max)
        col_cortos, col_shrink = st.columns(2)
        cortos = col_cortos.toggle("Ventas en corto", value=actuales.permitir_cortos)
        shrink = col_shrink.toggle("Estimación robusta", value=actuales.shrinkage)

        if st.form_submit_button("Guardar preferencias", type="primary",
                                 icon=":material/save:"):
            try:
                preferencias_mod.guardar(
                    Preferencias(
                        tickers=tickers.strip(),
                        horizonte=horizonte,
                        estrategia=estrategia,
                        peso_min=peso_min,
                        peso_max=peso_max,
                        permitir_cortos=cortos,
                        shrinkage=shrink,
                        guia_vista=actuales.guia_vista,
                    )
                )
            except OSError as error:
                st.error(f"No se pudieron guardar: {error}")
            else:
                st.success("Guardadas. El optimizador arrancará con estos valores.")

    if st.button("Volver a los valores de fábrica", icon=":material/restart_alt:"):
        try:
            preferencias_mod.borrar()
        except OSError as error:
            st.error(f"No se pudieron borrar: {error}")
        else:
            st.rerun()

# ── Dónde vive todo ──────────────────────────────────────────────────────────
with datos_tab:
    st.markdown(
        "Nada de esto se envía a ningún sitio. Todo son ficheros en tu ordenador."
    )
    st.markdown(
        f"""
| Qué | Dónde | Se puede borrar |
|---|---|---|
| Credenciales | `{RUTA_CREDENCIALES}` | Sí, desde la pestaña Credenciales |
| Preferencias | `{preferencias_mod.RUTA}` | Sí, con el botón de arriba |
| Portafolios guardados | `{cartera.DIRECTORIO}/` | Sí, uno a uno |
| Actas de aprobación | `actas/` | Se dejan a propósito: son el registro |
| Candidatos generados | `salidas/` | Sí, se regeneran |
| Caché de descargas | `fundamentals/.cache/`, `ranking/.cache/` | Sí, se vuelven a bajar |
"""
    )
    st.caption(
        "Las credenciales y las preferencias viven en tu carpeta personal y no "
        "dentro del proyecto: comprimir la carpeta del programa y pasársela a "
        "alguien no manda tu clave dentro, porque nunca estuvo ahí."
    )
    st.info(
        "Las actas son lo único que no se ofrece borrar desde aquí. Son el "
        "registro de qué se aprobó y cuándo, y lo peor que le puede pasar a un "
        "registro es desaparecer con un clic de más."
    )

    guardados = cartera.listar()
    ilegibles = [e for e in guardados if e.portafolio is None]
    st.markdown(
        f"Ahora mismo: **{len(guardados) - len(ilegibles)}** portafolios guardados"
        + (f" y **{len(ilegibles)}** ficheros ilegibles." if ilegibles else ".")
    )
