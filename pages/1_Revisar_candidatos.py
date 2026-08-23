import streamlit as st

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
    guardar_acta,
    tickers_aprobados,
)
from aprobacion.carga import ContratoRoto, FaltanFichas, cargar_candidatos, resumen_corrida
from aprobacion.generacion import (
    COSTE_APROXIMADO_USD,
    disponibilidad,
    hay_revision_en_curso,
)
from credenciales import (
    RUTA as RUTA_CREDENCIALES,
    ConfigIlegible,
    CredencialInvalida,
    Credenciales,
    aplicar,
    avisos,
    borrar,
    cargar,
    enmascarar,
    variables_del_shell,
    reemplazar,
)
from credenciales import guardar as guardar_credenciales
from fundamentals.kpis import TODOS_LOS_KPIS

st.set_page_config(page_title="Revisar candidatos", page_icon="✅", layout="wide")
st.title("✅ Revisar candidatos")

if "anadidos" not in st.session_state:
    st.session_state.anadidos = []


def _generar(con_ia: bool) -> None:
    """Run sub-project B and overwrite salidas/, then reload the page."""
    from ranking.run import construir_ranking, guardar

    with st.spinner(
        "Generando candidatos"
        + (" y redactando fichas con IA" if con_ia else " sin IA")
        + "… puede tardar unos minutos. No cierres ni recargues."
    ):
        guardar(construir_ranking(con_llm=con_ia), "salidas")
    # Lo marcado antes se refiere a una lista que acaba de dejar de existir.
    for clave in [c for c in st.session_state if c.startswith("ok_")]:
        del st.session_state[clave]
    st.session_state.anadidos = []
    st.rerun()


def _recargar_si_toca() -> None:
    """Rerun only once every widget on the page has been instantiated.

    Un `st.rerun()` lanzado desde el desplegable de credenciales se dispara
    antes de que se dibujen las casillas y los motivos: Streamlit descarta el
    estado de los widgets que no llegó a ver en esa pasada, y la revisión en
    curso desaparece sin decir nada. Es justo lo que `hay_revision_en_curso`
    existe para evitar, y encima la deja muda, porque para cuando pregunta ya
    no queda nada marcado.
    """
    if st.session_state.pop("recargar_credenciales", False):
        st.rerun()


def _apartado_credenciales(guardadas: Credenciales) -> None:
    """Los dos datos que necesita la mitad con IA, y de dónde sale cada uno."""
    for texto in st.session_state.pop("avisos_credenciales", []):
        st.warning(texto)

    st.markdown(
        f"Se guardan en tu carpeta personal (`{RUTA_CREDENCIALES}`), **fuera de "
        "este proyecto**: si comprimes la carpeta y se la pasas a alguien, tu "
        "clave no viaja dentro."
    )

    # La regla de precedencia vive en credenciales.py, no aqui: es la misma
    # que aplica aplicar(), y una pagina de Streamlit no se puede probar.
    desde_entorno = variables_del_shell(guardadas)
    if desde_entorno:
        st.info(
            "Ahora mismo manda el entorno para "
            + " y ".join(f"`{nombre}`" for nombre in desde_entorno)
            + ". Lo que guardes aqui no lo pisa."
        )

    if guardadas.api_key and not st.session_state.get("editando_credenciales"):
        columna_clave, columna_cambiar, columna_borrar = st.columns([4, 1, 1])
        columna_clave.text_input(
            "Clave de Anthropic",
            value=enmascarar(guardadas.api_key),
            disabled=True,
        )
        if columna_cambiar.button("Cambiar", use_container_width=True):
            st.session_state.editando_credenciales = True
            st.session_state.recargar_credenciales = True
        if columna_borrar.button("Borrar", use_container_width=True):
            try:
                borrar()
            except OSError as error:
                st.error(f"No se pudo borrar: {error}")
            else:
                st.session_state.recargar_credenciales = True
        st.text_input(
            "Correo para EDGAR",
            value=guardadas.edgar_identity or "",
            disabled=True,
        )
        return

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
        help=(
            "No es un registro: la SEC exige un contacto en la cabecera de "
            "cada peticion y solo se envia ahi."
        ),
    )
    columna_guardar, columna_cancelar = st.columns([1, 1])
    if columna_guardar.button("Guardar credenciales", type="primary"):
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
            # propio aplicar(). Con aplicar() aqui, cambiar una clave revocada
            # la guardaria en disco y el proceso seguiria usando la vieja toda
            # la sesion, con esta pagina mostrando la nueva enmascarada.
            reemplazar(guardadas, nuevas)
            # Los avisos se guardan en sesion en vez de pintarse aqui: para
            # cuando se pintan el guion ya se reinicio (via
            # _recargar_si_toca) y esta pasada nunca vuelve a pasar por aqui.
            st.session_state.avisos_credenciales = avisos(nuevas)
            st.session_state.editando_credenciales = False
            st.session_state.recargar_credenciales = True

    # Sólo si hay algo guardado a lo que volver: sin esto, quien pulsa
    # "Cambiar" y se arrepiente se queda ante un campo vacío donde estaba su
    # clave, sin Borrar y sin vuelta atrás que no sea reiniciar.
    if guardadas.api_key and columna_cancelar.button("Cancelar"):
        st.session_state.editando_credenciales = False
        st.session_state.recargar_credenciales = True


# Lo guardado ayer no sirve de nada si nadie lo carga hoy: guardar es lo que
# escribe, arrancar es lo que aplica, y hacen falta los dos.
credenciales_rotas = None
try:
    credenciales_guardadas = cargar()
    aplicar(credenciales_guardadas)
except ConfigIlegible as error:
    # Un fichero de configuracion corrupto no deja a nadie sin optimizador:
    # se avisa y se sigue con la mitad gratis.
    credenciales_guardadas = Credenciales()
    credenciales_rotas = str(error)

# A la vista y no dentro de un desplegable: el caso de uso que lo motivó es
# "una evaluación rápida sin IA", y esconder tras un clic extra algo que se
# quiere usar de pasada lo convierte en algo que no se usa.
puede = disponibilidad()

opciones = ["Sin IA — sólo números, gratis"]
if puede.puede_usar_ia:
    opciones.append(
        f"Con IA — narrativa y citas verificadas (~{COSTE_APROXIMADO_USD:.2f} $)"
    )

columna_modo, columna_boton = st.columns([4, 1])
eleccion = columna_modo.radio(
    "Generar candidatos", opciones, horizontal=True, key="modo_generacion"
)
con_ia = eleccion.startswith("Con IA")
pulsado = columna_boton.button(
    "Generar",
    key="generar",
    use_container_width=True,
    disabled=not puede.puede_generar,
)

if not puede.puede_generar:
    # warning y no caption: sin EDGAR_IDENTITY no hay generación posible, ni
    # siquiera la mitad gratis, y eso no es una nota al pie.
    st.warning(puede.motivo_generacion)
elif not puede.puede_usar_ia:
    st.caption(puede.motivo)

with st.expander(
    "🔑 Mis credenciales",
    # También abierto cuando hay algo que decir: el aviso de la clave y el del
    # fichero corrupto se pintan aquí dentro, y si nace plegado justo en la
    # pasada que los genera, nadie los lee nunca -- se consumen igual.
    # Las dos razones se nombran por separado -- no generar y no poder usar
    # IA -- en vez de dejar que la segunda cubra a la primera por coincidencia
    # (sin identidad tampoco hay IA, pero eso no es por lo que se abre aquí).
    expanded=(
        not puede.puede_generar
        or not puede.puede_usar_ia
        or bool(credenciales_rotas)
        or bool(st.session_state.get("avisos_credenciales"))
    ),
):
    if credenciales_rotas:
        st.warning(
            f"{credenciales_rotas}\n\nGuarda las credenciales otra vez para "
            "reemplazarlo, o borra el fichero a mano."
        )
    _apartado_credenciales(credenciales_guardadas)

st.caption(
    "Regenerar **sobrescribe** los candidatos de abajo. El ranking es "
    "determinista: con los mismos datos sale el mismo orden, así que sin IA "
    "sólo cambia si el panel trae un trimestre nuevo."
)

if hay_revision_en_curso(
    {
        c.removeprefix("ok_")
        for c in st.session_state
        if c.startswith("ok_") and st.session_state[c]
    },
    st.session_state.anadidos,
):
    st.warning(
        "Tienes una revisión empezada. Regenerar la descarta: las casillas "
        "marcadas y los añadidos a mano se pierden, porque apuntan a una lista "
        "que dejará de existir."
    )

if pulsado:
    _generar(con_ia)

st.divider()

try:
    candidatos = cargar_candidatos()
except FaltanFichas as error:
    st.warning(str(error))
    # No hay casillas ni motivos todavia en este camino -- es justo el que
    # recorre quien acaba de recibir el programa y esta metiendo sus
    # credenciales por primera vez -- asi que recargar aqui es seguro.
    _recargar_si_toca()
    st.stop()
except ContratoRoto as error:
    st.error(f"Las salidas de B no tienen la forma esperada: {error}")
    _recargar_si_toca()
    st.stop()

st.info(resumen_corrida(candidatos.corrida))
st.caption(
    "El orden lo decide un score determinista que **no esta validado "
    "empiricamente**: es un criterio de seleccion transparente, no una "
    "prevision de rentabilidad."
)

aprobados: set[str] = set()
motivos: dict[str, str] = {}

for ficha in candidatos.fichas:
    ticker = ficha["ticker"]
    columna_casilla, columna_titulo = st.columns([1, 11])
    with columna_casilla:
        # Nace desmarcada a proposito: si llegara marcada, aprobar los quince
        # seria un clic y el gate pasaria a ser decorado.
        marcada = st.checkbox("Aprobar", key=f"ok_{ticker}", label_visibility="collapsed")
    with columna_titulo:
        st.markdown(
            f"**{ficha['puesto']}. {ticker}** — {ficha['sector_gics']} · "
            f"compuesto {ficha['compuesto']:+.2f} (z dentro del sector)"
        )
    if marcada:
        aprobados.add(ticker)

    with st.expander(f"Ficha de {ticker}"):
        pilares = " · ".join(
            f"{pilar} {valor:+.2f}" if valor is not None else f"{pilar} n/d"
            for pilar, valor in ficha["pilares"].items()
        )
        st.markdown(f"Pilares (z frente a todo el universo): {pilares}")
        st.markdown(
            "- Fuerte en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["destacados"])
        )
        st.markdown(
            "- Flojo en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["flojos"])
        )
        st.markdown(
            f"- Cobertura: {ficha['cobertura']['kpis_con_dato']} de "
            f"{len(TODOS_LOS_KPIS)} KPIs"
        )
        if ficha["desplazo_a"]:
            st.markdown(
                "- Dejo fuera por el tope sectorial: "
                + ", ".join(ficha["desplazo_a"])
            )

        narrativa = ficha["narrativa"]
        if narrativa is None:
            st.markdown("_Ficha de plantilla: sin narrativa generada._")
        else:
            st.markdown(narrativa["tesis"])
            for riesgo in narrativa["riesgos"]:
                st.markdown(f"- {riesgo['afirmacion']}")
                if not riesgo["verificada"]:
                    # Si el revisor puede leer la ficha entera sin enterarse de
                    # que una cita es inventada, este sub-proyecto ha fallado.
                    st.error("Cita SIN VERIFICAR: no aparece en el documento original")
                st.markdown(f"> {' '.join(riesgo['cita'].split())}")
            fuente = narrativa.get("fuente")
            if fuente:
                recorte = " (recortado)" if fuente["recortado"] else ""
                st.caption(
                    f"Fuente: {fuente['formulario']} de {fuente['fecha']}, "
                    f"{fuente['seccion']}, accession {fuente['accession']}{recorte}"
                )
            else:
                st.warning("Procedencia no disponible: la cita no se puede localizar")

        motivo = st.text_input(
            "Motivo si lo descartas (opcional)", key=f"motivo_{ticker}"
        )
        if motivo.strip() and not marcada:
            motivos[ticker] = motivo.strip()

st.divider()
st.subheader("Anadir una empresa a mano")
st.caption(
    "Para recuperar a una empresa que las guardas excluyeron por como reporta "
    "y no por su calidad. El motivo es obligatorio: sin ranking detras, es la "
    "unica justificacion que va a existir."
)

columna_ticker, columna_motivo, columna_boton = st.columns([1, 3, 1])
nuevo_ticker = columna_ticker.text_input("Ticker", key="nuevo_ticker")
nuevo_motivo = columna_motivo.text_input("Motivo", key="nuevo_motivo")
if columna_boton.button("Anadir", disabled=not (nuevo_ticker and nuevo_motivo.strip())):
    st.session_state.anadidos.append(
        Anadido(ticker=nuevo_ticker, motivo=nuevo_motivo)
    )
    st.rerun()

if st.session_state.anadidos:
    for indice, anadido in enumerate(st.session_state.anadidos):
        columna_texto, columna_quitar = st.columns([11, 1])
        with columna_texto:
            st.markdown(f"- **{anadido.ticker.strip().upper()}** — {anadido.motivo}")
        with columna_quitar:
            # El indice como key es seguro aqui porque cada clic reconstruye la
            # lista entera antes del siguiente rerun: no queda un hueco a medio
            # borrar con el que las keys de los botones restantes puedan
            # desalinearse.
            if st.button("Quitar", key=f"quitar_anadido_{indice}"):
                st.session_state.anadidos.pop(indice)
                st.rerun()
    # No se comprueba aqui si el ticker existe o tiene precio: llamar a yfinance
    # desde el gate lo ataria a la red y a un servicio externo, y es justo lo
    # que permite probar todo este paquete sin nada montado. El optimizador ya
    # falla de forma visible si un ticker no tiene datos.
    st.caption(
        "Solo se comprueba la forma del ticker. Si no existe o no tiene precio, "
        "el fallo aparecera en el optimizador, no aqui."
    )

st.divider()
total = len(aprobados) + len(st.session_state.anadidos)
if st.button(f"Aprobar {total} empresas y pasar al optimizador", disabled=total == 0,
             type="primary"):
    try:
        acta = construir_acta(
            candidatos,
            aprobados=aprobados,
            anadidos=st.session_state.anadidos,
            motivos=motivos,
        )
        # El acta se escribe ANTES del traspaso: el peor resultado posible seria
        # aprobar, perder el registro y seguir adelante creyendo que quedo
        # constancia.
        destino = guardar_acta(acta)
    except (MotivoRequerido, TickerDuplicado, TickerInvalido, NadaQueAprobar) as error:
        st.error(str(error))
    except OSError as error:
        st.error(f"No se pudo escribir el acta, no se aprueba nada: {error}")
    else:
        st.session_state.tickers_aprobados = tickers_aprobados(acta)
        # Se vacia solo lo anadido a mano: si el revisor vuelve a pulsar
        # "Aprobar" sin haber cambiado nada, esos tickers no vuelven a
        # mandarse y a duplicarse en una segunda acta. Las casillas se dejan
        # como estan a proposito -- el revisor puede querer seguir viendo que
        # aprobo -- aunque eso significa que un segundo clic con casillas
        # marcadas si vuelve a escribir esos tickers en una acta nueva.
        st.session_state.anadidos = []
        st.success(
            f"Acta escrita en {destino}. Para pasar al optimizador usa el "
            "enlace **Markowitz Pro Picks** de la barra lateral: recargar "
            "esta pagina abre una sesion nueva de Streamlit y pierde la "
            "seleccion aprobada."
        )

# Al final del todo y no dentro del desplegable: para cuando se llega aqui ya
# se dibujaron las casillas, los motivos y lo anadido a mano, asi que un
# rerun pedido desde las credenciales no le borra el trabajo a nadie.
_recargar_si_toca()
