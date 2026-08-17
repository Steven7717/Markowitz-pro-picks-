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
pulsado = columna_boton.button("Generar", key="generar", use_container_width=True)

if not puede.puede_usar_ia:
    st.caption(puede.motivo)

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
    st.stop()
except ContratoRoto as error:
    st.error(f"Las salidas de B no tienen la forma esperada: {error}")
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
