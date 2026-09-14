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
    normalizar,
    tickers_aprobados,
)
from aprobacion.carga import (
    ContratoRoto,
    FaltanFichas,
    cargar_candidatos,
    kpis_con_dato,
    resumen_corrida,
)
from aprobacion.generacion import (
    COSTE_APROXIMADO_USD,
    disponibilidad,
    hay_revision_en_curso,
)
from noticias import texto
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
    from ranking.llm import gasto_acumulado, reiniciar_gasto
    from ranking.run import construir_ranking, guardar

    # El contador de gasto vive en el módulo `ranking.llm` y el proceso de
    # Streamlit sobrevive a las corridas: sin ponerlo a cero, la segunda
    # heredaría el gasto de la primera y podría chocar contra el tope duro sin
    # haber gastado ella nada.
    reiniciar_gasto()
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
        #
        # El gasto sí se guarda: una corrida que aborta a mitad ya ha pagado las
        # llamadas que hizo, y no decirlo es justo el caso en que más falta hace
        # saberlo.
        st.session_state.gasto_ultima_corrida = gasto_acumulado()
        st.error(str(error))
        return

    st.session_state.gasto_ultima_corrida = gasto_acumulado()

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
        f"Con IA — narrativa y citas verificadas (hasta {COSTE_APROXIMADO_USD:.2f} $)"
    )

with st.container(border=True):
    columna_modo, columna_boton = st.columns([4, 1], vertical_alignment="bottom")
    eleccion = columna_modo.radio(
        "Generar candidatos", opciones, horizontal=True, key="modo_generacion"
    )
    con_ia = eleccion.startswith("Con IA")
    # El botón dice lo que va a pasar, no sólo «Generar». El precio vivía sólo
    # en la etiqueta del radio, en letra pequeña, así que el último clic antes
    # de gastar no mencionaba el dinero por ninguna parte.
    pulsado = columna_boton.button(
        "Generar con IA" if con_ia else "Generar gratis",
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

# --- El paso que separa un clic de un dólar y medio --------------------------
#
# La corrida con IA costaba 1,25 $ a un solo clic, y la elección se quedaba
# pegada: `key="modo_generacion"` sobrevive al `st.rerun()`, así que una corrida
# que falla a mitad devuelve la página con «Con IA» ya seleccionado y volver a
# pulsar eran otros 1,25 $ sin que nada lo dijera.
#
# La confirmación se arma con una bandera **que no es de un widget** y se
# desarma justo antes de llamar, así que no sobrevive a nada: después de un
# fallo hay que volver a confirmar. Eso deja el radio pegado --y da igual que lo
# esté--, porque pulsar «Generar» ya no gasta nada por sí solo.
#
# Lo que no cambia, porque ya estaba bien: la opción gratis es la de por
# defecto, y sin clave la de pago ni se dibuja.
_CONFIRMAR = "confirmar_generacion_ia"

if pulsado:
    if con_ia:
        st.session_state[_CONFIRMAR] = True
    else:
        _generar(False)

if st.session_state.get(_CONFIRMAR) and puede.puede_usar_ia:
    with st.container(border=True):
        st.warning(
            f"**Esto cuesta dinero: hasta {COSTE_APROXIMADO_USD:.2f} $** en tu "
            "cuenta de Anthropic, cargados al generar. Es el peor caso —todas "
            "las fichas reintentadas—; lo que cueste de verdad se dice aquí "
            "mismo al terminar. Sin IA la lista sale igual de ordenada, sólo "
            "que sin narrativa ni citas."
        )
        columna_si, columna_no, _ = st.columns([2, 1, 3])
        if columna_si.button(
            f"Sí, generar con IA (hasta {COSTE_APROXIMADO_USD:.2f} $)",
            key="confirmar_ia",
            type="primary",
        ):
            # Se desarma ANTES de llamar: si la corrida aborta a mitad,
            # `_generar` vuelve sin recargar y la página no puede quedarse con
            # la confirmación puesta de la vez anterior.
            st.session_state[_CONFIRMAR] = False
            _generar(True)
        if columna_no.button("Cancelar", key="cancelar_ia"):
            st.session_state[_CONFIRMAR] = False
            st.rerun()

_gasto = st.session_state.get("gasto_ultima_corrida")
if _gasto is not None and _gasto.llamadas:
    # El README promete que las pantallas que cuestan dinero «avisan antes y
    # dicen lo que costó después». Esta no decía nada: `ranking/llm.py` recibía
    # `respuesta.usage` de la API y la tiraba entera, al contrario que
    # `interprete/cliente.py`, que la conserva y la enseña.
    st.success(
        f"La última corrida con IA costó **{_gasto.usd:.2f} $**: "
        f"{_gasto.llamadas} llamadas, {_gasto.entrada_tokens:,} tokens de "
        f"entrada y {_gasto.salida_tokens:,} de salida."
    )
    if _gasto.tope_alcanzado:
        st.warning(
            "La corrida alcanzó el tope de gasto y paró de llamar al modelo: "
            "las fichas que faltaban salieron de plantilla, sin narrativa. "
            "No es lo normal, así que merece una mirada antes de repetirla."
        )

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
    # «B» es el nombre interno de un sub-proyecto: el revisor no sabe qué es y
    # el mensaje no le dice ni qué fichero mirar ni qué hacer.
    st.error(
        f"El fichero de candidatos (salidas/fichas.json) no tiene la forma "
        f"esperada: {error}. Vuelve a generarlos para reescribirlo."
    )
    st.stop()

st.info(resumen_corrida(candidatos.corrida))
st.caption(
    "El orden lo decide un score determinista que **no está validado "
    "empíricamente**: es un criterio de selección transparente, no una "
    "previsión de rentabilidad."
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
        # `.get` y no indexación directa, como hacen `medidores.tarjeta_candidato`
        # y `medidores._nota_pilar` con estos mismos campos: `_CAMPOS_FICHA`
        # valida que `cobertura` exista pero no su contenido, así que una
        # fichas.json vieja reventaba con KeyError **a mitad de la lista**, con
        # tarjetas ya pintadas encima. El escenario está en el repo:
        # salidas_ejemplo trae `kpis_con_dato` pero no `kpis_por_pilar`.
        _con_dato = kpis_con_dato(ficha)
        if _con_dato is None:
            st.caption("Sin cobertura registrada: esta ficha es de una versión anterior")
        else:
            st.markdown(
                medidores.medidor_cobertura(_con_dato), unsafe_allow_html=True
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
            # Todo lo de aquí abajo lo escribió el modelo, y la cita es texto
            # copiado literalmente del filing: lo escribe la empresa. Pintarlo
            # en crudo no es XSS --Streamlit sanea el HTML-- pero sí inyección
            # de markdown: un `[texto](url)` sale como enlace pulsable al
            # dominio del emisor, una imagen remota confirma que la ficha se
            # abrió, y `$…$` se lee como LaTeX y se come la línea. Esta pantalla
            # era la única de la app que no pasaba por `noticias/texto.py`.
            st.markdown(texto.plano(narrativa["tesis"]))
            for riesgo in narrativa["riesgos"]:
                st.markdown(f"- {texto.plano(riesgo['afirmacion'])}")
                if not riesgo["verificada"]:
                    # Si el revisor puede leer la ficha entera sin enterarse de
                    # que una cita es inventada, este sub-proyecto ha fallado.
                    st.error("Cita SIN VERIFICAR: no aparece en el documento original")
                bloque = texto.cita_en_bloque(riesgo["cita"])
                if bloque:
                    st.markdown(bloque)
                else:
                    # Una cita en blanco con el `>` puesto se pinta como una
                    # raya gris vacía, que se lee como que la cita existe.
                    st.caption("Sin cita: el modelo no escribió ninguna")
            fuente = narrativa.get("fuente")
            if fuente:
                recorte = " (recortado)" if fuente["recortado"] else ""
                # La procedencia sale de EDGAR y no del modelo, pero llega por
                # la misma tubería y se pinta en el mismo sitio: escaparla
                # cuesta lo mismo que razonar cada año si sigue siendo de fiar.
                st.caption(
                    f"Fuente: {texto.plano(fuente['formulario'])} de "
                    f"{texto.plano(fuente['fecha'])}, "
                    f"{texto.plano(fuente['seccion'])}, accession "
                    f"{texto.plano(fuente['accession'])}{recorte}"
                )
            else:
                st.warning("Procedencia no disponible: la cita no se puede localizar")

        motivo = st.text_input(
            "Motivo si lo descartas (opcional)", key=f"motivo_{ticker}"
        )
        if motivo.strip() and not marcada:
            motivos[ticker] = motivo.strip()

st.divider()
st.subheader("Añadir una empresa a mano")
st.caption(
    "Para recuperar a una empresa que las guardas excluyeron por cómo reporta "
    "y no por su calidad. El motivo es obligatorio: sin ranking detrás, es la "
    "única justificación que va a existir."
)

# Un formulario, y no dos `text_input` sueltos: `nuevo_ticker` y `nuevo_motivo`
# sobrevivían al `st.rerun()` que sigue a añadir, así que los campos se quedaban
# llenos y un clic de más añadía el mismo ticker dos veces. Nada avisaba hasta
# «Aprobar N empresas», al final de todo, donde `construir_acta` lanza
# `TickerDuplicado` y el revisor descubre el problema en el peor momento.
# `clear_on_submit` los vacía al enviar.
with st.form("anadir_a_mano", clear_on_submit=True):
    columna_ticker, columna_motivo, columna_boton = st.columns(
        [1, 3, 1], vertical_alignment="bottom"
    )
    nuevo_ticker = columna_ticker.text_input("Ticker", key="nuevo_ticker")
    nuevo_motivo = columna_motivo.text_input("Motivo", key="nuevo_motivo")
    # Dentro de un formulario no hay recarga al teclear, así que el botón no
    # puede deshabilitarse según lo escrito: la validación se hace al enviar, y
    # además así el usuario lee por qué en vez de encontrarse un botón apagado.
    enviado = columna_boton.form_submit_button("Añadir", use_container_width=True)

if enviado:
    _ya_anadidos = {a.ticker.strip().upper() for a in st.session_state.anadidos}
    _del_ranking = {f["ticker"] for f in candidatos.fichas}
    try:
        _candidato = normalizar(nuevo_ticker)
    except TickerInvalido as error:
        st.error(str(error))
    else:
        # Estas tres comprobaciones no sustituyen a las de `construir_acta`, que
        # sigue siendo la autoridad y las repite al escribir el acta: lo que
        # hacen es decirlo **ahora**, cuando el revisor todavía recuerda lo que
        # tecleó, en vez de al final de la revisión entera.
        if not nuevo_motivo.strip():
            st.error(
                f"{_candidato} necesita un motivo escrito: sin ranking detrás, "
                "es la única justificación que va a existir."
            )
        elif _candidato in _del_ranking:
            st.error(
                f"{_candidato} ya está en el ranking: apruébalo con su casilla "
                "en vez de añadirlo a mano."
            )
        elif _candidato in _ya_anadidos:
            st.error(f"{_candidato} ya está en la lista de añadidos a mano.")
        else:
            st.session_state.anadidos.append(
                Anadido(ticker=nuevo_ticker, motivo=nuevo_motivo)
            )
            st.rerun()

if st.session_state.anadidos:
    for indice, anadido in enumerate(st.session_state.anadidos):
        columna_texto, columna_quitar = st.columns([11, 1])
        with columna_texto:
            # El motivo lo escribió el propio revisor, pero se escapa igual: un
            # «PER < $20» se comería la línea hasta el siguiente dólar y le
            # borraría de la vista la razón que él mismo tecleó.
            st.markdown(
                f"- **{texto.plano(anadido.ticker.strip().upper())}** — "
                f"{texto.plano(anadido.motivo)}"
            )
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
        "Sólo se comprueba la forma del ticker. Si no existe o no tiene precio, "
        "el fallo aparecerá en el optimizador, no aquí."
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
        # `switch_page` navega DENTRO de la sesion: `tickers_aprobados` sigue
        # en `session_state` al llegar. El aviso que habia aqui --usa el menu,
        # recargar pierde la seleccion-- describia el problema de recargar la
        # pagina, que es otra cosa, y este fichero ya usa `switch_page` en las
        # lineas 110 y 145.
        st.session_state.acta_recien_escrita = str(destino)
        st.switch_page("vistas/optimizador.py")
