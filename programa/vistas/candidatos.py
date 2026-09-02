"""El gate: revisar los candidatos del ranking y decidir cuáles pasan.

Es la página que vivía en `pages/1_Revisar_candidatos.py`. Lo único que ha
salido de aquí son las credenciales, que ahora están en «Perfil y ajustes», y
con ellas se ha ido `_recargar_si_toca`: existía porque un `st.rerun()` lanzado
desde el desplegable de credenciales se disparaba antes de que se dibujaran las
casillas de aprobación, Streamlit descartaba el estado de los widgets que no
llegó a ver, y la revisión en curso desaparecía sin decir nada. Sin credenciales
en esta pantalla, no queda ninguna recarga que pueda hacer eso.
"""

import streamlit as st

import medidores
import tema
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
from ranking.criterio import TRIMESTRES_VENTANA

st.markdown(
    tema.cabecera(
        "Revisar candidatos",
        "El paso intermedio entre el ranking y el optimizador: nada llega a la "
        "cartera sin que alguien lo apruebe aquí, y de cada revisión queda un "
        "acta fechada.",
    ),
    unsafe_allow_html=True,
)

if "anadidos" not in st.session_state:
    st.session_state.anadidos = []


def _generar(con_ia: bool) -> None:
    """Run sub-project B and overwrite salidas/, then reload the page."""
    from fundamentals.fetch import CorridaAbortada
    from ranking.run import construir_ranking, guardar

    try:
        with st.spinner(
            "Generando candidatos"
            + (" y redactando fichas con IA" if con_ia else " sin IA")
            + "… puede tardar unos minutos. No cierres ni recargues."
        ):
            guardar(construir_ranking(con_llm=con_ia), "salidas")
    except CorridaAbortada as error:
        # Ni se limpia el estado ni se recarga: no se llegó a sobrescribir
        # salidas/, así que lo que el revisor tenga marcado sigue apuntando a la
        # lista que está viendo. Borrarlo aquí sería el defecto que arregló
        # cbe71a0, y encima castigaría al usuario por un fallo que no es suyo.
        st.error(str(error))
        return

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

with st.container(border=True):
    columna_modo, columna_boton = st.columns([4, 1], vertical_alignment="bottom")
    eleccion = columna_modo.radio(
        "Generar candidatos", opciones, horizontal=True, key="modo_generacion"
    )
    con_ia = eleccion.startswith("Con IA")
    pulsado = columna_boton.button(
        "Generar",
        key="generar",
        use_container_width=True,
        type="primary",
        icon=":material/autorenew:",
        disabled=not puede.puede_generar,
    )

    if not puede.puede_generar:
        # warning y no caption: sin EDGAR_IDENTITY no hay generación posible, ni
        # siquiera la mitad gratis, y eso no es una nota al pie.
        st.warning(puede.motivo_generacion)
    elif not puede.puede_usar_ia:
        st.caption(puede.motivo)

    if not puede.puede_generar or not puede.puede_usar_ia:
        if st.button("Configurar mis credenciales", icon=":material/key:"):
            st.switch_page("vistas/perfil.py")

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
    # Es el camino que recorre quien acaba de recibir el programa: todavia no ha
    # generado nada. Se le ofrece el boton en vez de dejarle el mensaje solo.
    if st.button("Configurar mis credenciales", key="credenciales_sin_fichas",
                 icon=":material/key:"):
        st.switch_page("vistas/perfil.py")
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

# La hoja de estilo de los medidores, una sola vez por pasada. Va aqui y no
# arriba del todo porque los dos caminos que terminan en st.stop() -- sin
# fichas, contrato roto -- no llegan a pintar ni un medidor.
st.markdown(medidores.CSS, unsafe_allow_html=True)

with st.expander("📏 Cómo se leen los medidores"):
    st.markdown(
        f"""
Cada medidor compara a la empresa **con las de su propio sector**, no con todo
el mercado: un margen del 40 % no significa lo mismo en software que en un
supermercado. La unidad es el z-score — cuántas desviaciones típicas se separa
de la media de sus pares — y la barra crece desde la línea central, que es esa
media.

{medidores.tabla_de_tramos()}

- **«Regular» no es un defecto**: significa que la empresa está donde está la
  media de su sector en esa área, ni mejor ni peor.
- **El rayado gris no es un cero ni un "regular"**: es que el dato no existe.
  Dos de cada tres bancos pierden el pilar de solidez entero así, porque no
  publican EBITDA ni clasifican su balance en corriente y no corriente. Quedan
  fuera por reportar distinto, no por ser peores.
- **El signo ya viene aplicado.** En `PER`, `EV / EBITDA` o `Deuda neta /
  EBITDA` menos es mejor, así que un múltiplo caro se pinta en rojo aunque su
  z sea positivo. Esos llevan escrito **«menos es mejor»** junto al nombre; los
  demás no lo llevan porque ahí el valor alto y la barra verde ya apuntan al
  mismo sitio.
- **La barra se corta en ±3.** Cuando el valor se sale, una marca blanca lo
  avisa y el número de la derecha, precedido de `›`, sigue siendo el real: en
  este panel hay z de hasta 8,6.
- **Los valores son la media de los últimos {TRIMESTRES_VENTANA} trimestres**
  publicados, así que el ROE y el ROIC son trimestrales, no anuales.
- Un pilar puede apoyarse en 1 KPI o en 7, y no vale lo mismo: el recuento va
  junto a su nombre.
"""
    )

# Cuantas van marcadas, antes de la lista y no solo en el boton del final:
# con quince tarjetas de por medio, el recuento que vive abajo del todo no
# esta a la vista cuando se decide.
marcadas_ahora = sum(
    1 for c in st.session_state if c.startswith("ok_") and st.session_state[c]
)
st.caption(
    f"**{len(candidatos.fichas)} candidatos** · {marcadas_ahora} marcados. "
    "Marca la casilla de la izquierda para aprobar un candidato. Nacen "
    "desmarcadas a propósito: aprobar es un acto, no el resultado de no hacer "
    "nada."
)

aprobados: set[str] = set()
motivos: dict[str, str] = {}

for ficha in candidatos.fichas:
    ticker = ficha["ticker"]
    columna_casilla, columna_tarjeta = st.columns([1, 14], vertical_alignment="center")
    with columna_casilla:
        # Nace desmarcada a proposito: si llegara marcada, aprobar los quince
        # seria un clic y el gate pasaria a ser decorado.
        #
        # La etiqueta se colapsa pero no desaparece: Streamlit la deja como
        # aria-label del input, asi que un lector de pantalla sigue anunciando
        # "Aprobar". Quince veces escrita al lado de quince tarjetas solo
        # anadia ruido, y en una ventana estrecha se partia en tres lineas.
        # Lo que faltaba era decirlo una vez, y eso lo hace el pie de arriba.
        marcada = st.checkbox(
            "Aprobar", key=f"ok_{ticker}", label_visibility="collapsed"
        )
    with columna_tarjeta:
        st.markdown(medidores.tarjeta_candidato(ficha), unsafe_allow_html=True)
    if marcada:
        aprobados.add(ticker)

    with st.expander(f"Ver la ficha completa de {ticker}"):
        st.markdown("**Los cuatro pilares**, frente a sus pares del sector")
        st.markdown(medidores.medidores_pilares(ficha), unsafe_allow_html=True)
        st.markdown(
            medidores.medidor_cobertura(ficha["cobertura"]["kpis_con_dato"]),
            unsafe_allow_html=True,
        )

        # "Sus tres mas fuertes" y no "Fuerte en": la lista es relativa a la
        # propia empresa, y una companyia solida puede tener sus tres peores
        # KPIs en "Regular". Decir "Flojo en" de un regular seria una
        # afirmacion que el dato no sostiene.
        st.markdown("**Sus tres puntos más fuertes**")
        st.markdown(
            "".join(medidores.medidor_kpi(i) for i in ficha["destacados"]),
            unsafe_allow_html=True,
        )
        st.markdown("**Sus tres puntos más flojos**")
        st.markdown(
            "".join(medidores.medidor_kpi(i) for i in ficha["flojos"]),
            unsafe_allow_html=True,
        )
        if ficha["desplazo_a"]:
            st.caption(
                "Dejó fuera por el tope sectorial: "
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
