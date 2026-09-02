"""El punto de entrada: tema, credenciales y navegación. Nada más.

Antes este fichero era el optimizador entero y las demás pantallas colgaban de
`pages/`, la navegación automática de Streamlit. Ahora es un enrutador y las
pantallas viven en `vistas/`, declaradas con `st.navigation`. El cambio compra
tres cosas que `pages/` no daba:

- **Secciones con nombre.** Ocho pantallas en una lista plana no dicen en qué
  orden se usan; agrupadas en Análisis, Cartera y Cuenta, sí.
- **Un solo `set_page_config`.** Con `pages/`, cada fichero repetía el título y
  el icono de la ventana, y bastaba con olvidarse en uno para que la pestaña del
  navegador cambiara de nombre al navegar.
- **Las credenciales se aplican una vez, al arrancar.** Antes eso lo hacía la
  página de candidatos, así que quien abría el optimizador primero corría sin
  ellas puestas.

El nombre del fichero no cambia a propósito: `Iniciar App.bat`, el acceso
directo del escritorio y `.claude/launch.json` apuntan aquí.
"""

import streamlit as st

import apagado
import tema
from credenciales import ConfigIlegible, Credenciales, aplicar, cargar
from preferencias import cargar as cargar_preferencias

st.set_page_config(
    page_title="Markowitz Pro Picks",
    # Ruta relativa: el lanzador entra en programa/ antes de arrancar, asi que
    # resuelve. Streamlit lo pasa por PIL, que lee .ico sin problema.
    page_icon="icono.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)

tema.aplicar(st)


# Una sola vez por proceso, no por sesion ni por reejecucion: cache_resource es
# lo que distingue "arrancar un hilo" de "arrancar un hilo en cada clic".
@st.cache_resource
def _vigilante():
    """El apagado automatico cuando ya no queda ninguna pestana abierta."""
    return apagado.vigilar()


_vigilante()

if st.session_state.get("cerrando"):
    # La despedida ocupa la pantalla entera y no hay navegacion debajo: lo que
    # queda no es una pagina de la que se pueda seguir tirando.
    st.markdown(
        tema.cabecera(
            "Programa cerrado",
            "Ya puedes cerrar esta pestaña. Para volver a abrirlo, usa el "
            "acceso directo del Escritorio o «Iniciar App».",
        ),
        unsafe_allow_html=True,
    )
    apagado.detener_en()
    st.stop()


# Lo guardado ayer no sirve de nada si nadie lo carga hoy: guardar es lo que
# escribe, arrancar es lo que aplica, y hacen falta los dos. Una sola vez por
# sesion: `aplicar` no pisa lo que ya hay en el entorno, asi que repetirlo en
# cada reejecucion no haria nada, pero volveria a leer el disco en cada clic.
if "credenciales" not in st.session_state:
    try:
        guardadas = cargar()
        aplicar(guardadas)
    except ConfigIlegible as error:
        # Un fichero de configuracion corrupto no deja a nadie sin optimizador:
        # se anota, lo cuenta la pantalla de perfil, y el resto sigue.
        st.session_state.credenciales = Credenciales()
        st.session_state.credenciales_rotas = str(error)
    else:
        st.session_state.credenciales = guardadas
        st.session_state.credenciales_rotas = None

preferencias, _ = cargar_preferencias()

# st.logo y no un markdown en la barra lateral: `st.navigation` monta su menu
# lo primero dentro de la barra, asi que cualquier cosa que se dibuje "antes"
# acaba debajo del menu de todas formas. Este es el unico sitio por encima.
st.logo("icono.ico", size="large")

# La guia manda hasta que alguien la despide. Quien abre esto por primera vez
# no sabe que hay un gate entre el ranking y el optimizador, y aterrizar
# directamente en el optimizador con cinco tickers de ejemplo no se lo cuenta.
inicio = st.Page(
    "vistas/inicio.py", title="Primeros pasos", icon=":material/waving_hand:",
    default=not preferencias.guia_vista,
)
optimizador = st.Page(
    "vistas/optimizador.py", title="Optimizador", icon=":material/insights:",
    default=preferencias.guia_vista,
)

navegacion = st.navigation(
    {
        "Análisis": [
            optimizador,
            st.Page(
                "vistas/candidatos.py", title="Revisar candidatos",
                icon=":material/fact_check:",
            ),
        ],
        "Cartera": [
            st.Page(
                "vistas/portafolios.py", title="Portafolios guardados",
                icon=":material/folder_open:",
            ),
            st.Page(
                "vistas/comparar.py", title="Comparar",
                icon=":material/compare_arrows:",
            ),
            st.Page(
                "vistas/actas.py", title="Actas de aprobación",
                icon=":material/history_edu:",
            ),
        ],
        "Cuenta": [
            st.Page(
                "vistas/perfil.py", title="Perfil y ajustes",
                icon=":material/settings:",
            ),
            inicio,
        ],
    }
)

with st.sidebar:
    st.divider()
    if st.session_state.get("credenciales_rotas"):
        st.warning("Hay un problema con tus credenciales. Míralo en Perfil y ajustes.")
    st.caption(
        "El orden de los candidatos es un criterio de selección transparente, "
        "**no** una previsión de rentabilidad."
    )
    # Con la ventana de consola oculta, cerrarla ya no es una opcion: este boton
    # es la forma visible de terminar. Para quien cierre la pestana sin usarlo
    # --la mayoria-- esta el apagado automatico de `apagado.py`.
    if st.button(
        "Salir del programa", use_container_width=True,
        icon=":material/power_settings_new:",
        help="Cierra el programa. Los portafolios y las actas guardadas se "
        "quedan donde están.",
    ):
        st.session_state.cerrando = True
        st.rerun()

navegacion.run()
