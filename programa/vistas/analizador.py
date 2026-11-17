"""El Analizador: cualquier acción con la ficha de los candidatos, su gráfico y sus noticias.

Widgets sin lógica, como el resto de `vistas/`. Lo que se decide --qué es cada
ticker, cuánto vale, qué se dice de él-- vive en `analizador/`,
`medidores_analizador.py` y `medidores_valoracion.py`, con tests: este guion
pinta.

Absorbe «Noticias y calendario», que salió del menú: lo que aquella pantalla
hacía para un libro entero se hace aquí con «Cargar de un libro», y cada ticker
tiene sus hechos, su prensa y su calendario en su pestaña.

La pestaña IA vive en `vistas/analizador_ia.py`: tres lecturas de pago, cada una
con su confirmación, y lo ya leído guardado en `analisis/<TICKER>.json`.

**El precio no se refresca solo, a propósito.** Un veredicto que cambia cada
minuto con el precio es ruido: cada fila lleva la hora de su cotización, y
«Actualizar precios» la vuelve a pedir. El tiempo real está en el gráfico, que
no es del programa ni entra en ninguna cuenta.

**Aquí no se recomienda nada.** Ni comprar, ni vender, ni esperar.
"""

from datetime import date

import pandas as pd
import streamlit as st

import medidores
import medidores_analizador as ma
import medidores_valoracion
import tema
from analizador import archivo as archivo_analizador
from analizador import deslizadores, grafico, referencia, sesion
from analizador.analisis import analizar, con_precio_nuevo, pilar_valoracion
from analizador.resolver import MAX_TICKERS, separar
from analizador.valorar import proyeccion, sensibilidad, valorar
from aprobacion.acta import Anadido, problema_al_anadir
from aprobacion.carga import ContratoRoto, FaltanFichas, cargar_candidatos, kpis_con_dato
from aprobacion.generacion import disponibilidad
from fundamentals.fetch import CorridaAbortada
from fundamentals.sectors import load_sectors
from noticias import macro, resumen, texto, traer
from seguimiento import posiciones
from vistas import analizador_ia, libros, panel_ia

st.markdown(
    tema.cabecera(
        "Analizador",
        "Cualquier acción —de la SEC, extranjera o de la BMV— o un ETF, con la "
        "misma ficha frente a su sector y el mismo valor intrínseco que los "
        "candidatos, más su gráfico, sus noticias y su calendario. Aquí no se "
        "recomienda nada.",
    ),
    unsafe_allow_html=True,
)
st.markdown(medidores.CSS, unsafe_allow_html=True)
st.markdown(medidores_valoracion.CSS, unsafe_allow_html=True)


# --- Arriba: los tickers --------------------------------------------------------


def _cargar_de_un_libro() -> None:
    """«Cargar de un libro»: el desplegable de Seguimiento y Rebalanceo. Sólo viajan los tickers."""
    _en_disco, etiquetas = libros.disponibles()
    if not etiquetas:
        st.caption("Todavía no llevas ningún libro. Empiézalo en **Empezar un libro**.")
        return
    elegida = libros.desplegable(etiquetas)
    tickers = posiciones.tickers_a_mirar(elegida.libro.asientos, elegida.libro.objetivo)
    if not tickers:
        st.caption(
            "Este libro no tiene ningún activo: ni posiciones abiertas ni pesos "
            "objetivo. Registra una compra en **Seguimiento**, o dale un objetivo "
            "desde el optimizador."
        )
        return
    # Si pasan del tope se dice aquí, antes de cargar, y no después con el
    # campo ya lleno.
    st.caption(ma.pie_del_libro(len(tickers), MAX_TICKERS))
    st.button(
        "Cargar en el campo",
        key="analizador_cargar_libro",
        icon=":material/download:",
        # En un callback: el campo ya está dibujado arriba, y Streamlit no deja
        # escribir en su clave después de dibujarlo en la misma pasada.
        on_click=sesion.cargar_texto,
        args=(st.session_state, tickers),
    )


def _analizar_tickers(tickers, hechos, panel, tabla) -> None:
    """Analiza los que faltan, con barra: quince en frío tardan cerca de un minuto."""
    barra = st.progress(0.0, text="Analizando…")
    for numero, ticker in enumerate(tickers, start=1):
        barra.progress(
            (numero - 1) / len(tickers),
            text=(
                f"Analizando {ticker} ({numero} de {len(tickers)}). En frío, "
                "quince tickers tardan cerca de un minuto."
            ),
        )
        hechos[ticker] = analizar(ticker, panel, tabla)
        sesion.olvidar_deslizadores(st.session_state, ticker)
        if hechos[ticker].clase is not None:
            # El calendario entra en el resumen («Próximo evento» y «Lo que
            # viene»): se trae aquí, dentro de la barra, y luego sale de la
            # caché, que vale un día.
            traer.traer("agenda", ticker, traer.DESCARGA["agenda"], False)
    barra.empty()


def _actualizar_precios(tickers, hechos, panel, tabla) -> None:
    """Rehace la identidad y la valoración de cada ticker; la ficha frente al sector se queda."""
    barra = st.progress(0.0, text="Actualizando precios…")
    for numero, ticker in enumerate(tickers, start=1):
        barra.progress((numero - 1) / len(tickers), text=f"Actualizando {ticker} ({numero} de {len(tickers)})…")
        hechos[ticker] = con_precio_nuevo(hechos[ticker], panel, tabla)
        sesion.olvidar_deslizadores(st.session_state, ticker)
    barra.empty()


def _panel_de_referencia(panel, fecha_panel, frescura, analizados) -> None:
    """De cuándo es la referencia sectorial y, si falta o se quedó atrás, el botón para hacerla."""
    trimestre = None if panel is None else referencia.trimestre_final(panel)
    atrasado = trimestre is not None and any(
        ma.aviso_panel_atrasado(a, trimestre) for a in analizados
    )
    if panel is None:
        st.warning(ma.SIN_PANEL)
    else:
        st.caption(ma.fecha_del_panel(fecha_panel, trimestre, frescura))
        if frescura.panel_posterior:
            st.info(ma.PANEL_POSTERIOR)
        if atrasado:
            st.warning(ma.PANEL_ATRASADO)
    if panel is not None and not atrasado:
        return
    puede = disponibilidad()
    if not puede.puede_generar:
        st.warning(puede.motivo_generacion)
        if st.button("Configurar mis credenciales", key="analizador_credenciales_panel", icon=":material/key:"):
            st.switch_page("vistas/perfil.py")
        return
    if st.button(
        "Construir el panel" if panel is None else "Rehacer el panel",
        key="analizador_panel",
        icon=":material/construction:",
        help=ma.AYUDA_PANEL,
    ):
        try:
            with st.spinner(
                "Construyendo el panel del S&P 500… unos dos minutos con la caché "
                "llena, y bastantes más la primera vez. No cierres ni recargues."
            ):
                referencia.construir_panel()
        except CorridaAbortada as error:
            # Como en Revisar candidatos: la causa con nombre, y nada escrito.
            st.error(str(error))
            return
        except OSError as error:
            # Al escribirlo: el disco lleno, o el panel aún ocupado por otra
            # sesión tras los reintentos de `construir_panel`.
            st.error(ma.fallo_al_escribir_el_panel(str(error), habia_panel=panel is not None))
            return
        # Con el panel nuevo los análisis guardados ya no valen
        # (`sesion.preparar`): se rehacen los de la tabla, con el mismo elegido.
        if analizados:
            sesion.encargar(
                st.session_state,
                [a.ticker for a in analizados],
                st.session_state.get(sesion.CLAVE_ELEGIDO),
            )
        st.rerun()


# --- El resumen y lo que viene ------------------------------------------------


def _agenda(analizados) -> "tuple[dict, dict]":
    """El calendario de cada ticker, de la caché de un día, y los fallos agrupados por mensaje."""
    agenda, problemas = {}, {}
    for a in analizados:
        if a.clase is None:
            continue
        datos, problema, _cuando, _vigente = traer.traer("agenda", a.ticker, traer.DESCARGA["agenda"], False)
        agenda[a.ticker] = list(datos)
        if problema:
            problemas.setdefault(problema, []).append(a.ticker)
    return agenda, problemas


def _macro() -> None:
    """Los punteros macro, en su propio bloque y sin ninguna fecha."""
    st.markdown("##### Datos de mercado")
    st.caption(
        "Aquí no hay fechas, y es a propósito: el calendario macro no lo publica "
        "ninguna de las fuentes que usa el programa, y copiarlo al repositorio "
        "crearía algo que caduca en silencio —un calendario viejo se lee igual "
        "que uno vigente—. Lo que se guarda es quién publica cada dato y dónde, "
        "que no caduca."
    )
    for evento in macro.PUNTEROS:
        st.markdown(
            f"- {texto.plano(evento.detalle)} — "
            + texto.enlace("ver el calendario", evento.url or "")
        )


def _lo_que_viene(agenda, problemas) -> None:
    """«Lo que viene» de todos los tickers juntos, y los punteros macro."""
    st.subheader("Lo que viene")
    # Agrupados por mensaje y no por ticker, como hacía Noticias: el mismo
    # fallo para quince tickers son quince avisos que no dicen más que uno.
    for problema, afectados in problemas.items():
        st.warning(
            f"**Calendario** — no se pudo traer lo de {', '.join(afectados)}. "
            f"{texto.plano(problema)}"
        )
    proximos = ma.proximos([e for eventos in agenda.values() for e in eventos])
    for evento in proximos:
        st.markdown(
            f"**{texto.plano(evento.ticker)}** — {texto.plano(evento.detalle)}  \n"
            f"{evento.cuando:%d/%m/%Y} · {texto.cuanto_falta(evento.cuando)}"
        )
    fallidos = {t for afectados in problemas.values() for t in afectados}
    if not proximos and agenda and fallidos >= set(agenda):
        # Vacío porque no respondió no es «ninguna fecha»: el criterio de
        # `consultado` en los 8-K.
        st.caption(
            "No se pudo traer el calendario —el aviso está arriba—: no se sabe si "
            "hay fechas próximas."
        )
    elif not proximos and fallidos:
        st.caption(
            "Ninguna fecha próxima de los que sí respondieron; de los del aviso de "
            "arriba no se sabe."
        )
    elif not proximos:
        st.caption(
            "Ninguna fecha próxima para estos tickers. El calendario sólo trae "
            "resultados y dividendos, y no todas las empresas los tienen "
            "publicados: que esto esté vacío no significa que no vaya a pasar nada."
        )
    _macro()


# --- El detalle -------------------------------------------------------------------


def _valor_y_sector(analisis, panel_dicho: bool) -> None:
    """El veredicto con sus tres votos, en la moneda del precio, y la tarjeta frente al sector.

    `panel_dicho`: el aviso del panel atrasado ya está encima, y el detalle de
    pares y la exclusión no lo repiten (con 7203.T se leía tres veces).
    """
    valoracion = ma.en_moneda_del_precio(analisis.valoracion)
    st.markdown("**Valor intrínseco**, con los supuestos del programa")
    st.markdown(medidores_valoracion.resumen(valoracion), unsafe_allow_html=True)
    if (analisis.valoracion or {}).get("motivo") == "sin_bono_m" and analisis.entradas is not None:
        st.caption(ma.falta_tasa(analisis.entradas) + " Se pone en la pestaña Valoración.")
    pares = ma.detalle_pares(analisis, panel_dicho=panel_dicho)
    # Si el detalle de pares ya nombró la guarda, debajo de la tarjeta sólo va
    # su causa: con AMX se leía la misma frase dos veces seguidas.
    guarda_dicha = ma.guarda_dicha_por_pares(analisis)
    if pares:
        st.caption(pares)
    for nota in medidores_valoracion.pie(valoracion):
        st.caption(nota)
    st.markdown("**Frente a su sector**")
    ref = analisis.referencia
    if ref is None:
        st.caption(ma.sin_ficha(analisis, panel_dicho=panel_dicho))
        return
    st.markdown(
        medidores.tarjeta_candidato(
            {**ref.ficha, "valoracion": valoracion}, puesto=ma.puesto_en_tarjeta(ref)
        ),
        unsafe_allow_html=True,
    )
    if ref.puesto is not None:
        st.caption(ma.nota_puesto(ref, analisis.ticker))
    exclusion = ma.texto_exclusion(analisis, panel_dicho=panel_dicho, guarda_dicha=guarda_dicha)
    if exclusion:
        st.caption(exclusion)


def _a_la_revision(analisis) -> None:
    """«Añadir a la revisión»: el ticker entra en los añadidos de Revisar candidatos.

    Hay un solo gate y una sola acta: el Analizador no aprueba nada, lo lleva a
    Revisar candidatos, donde siguen sus reglas (si ya está en el ranking se
    rechaza, el motivo es obligatorio, y regenerar vacía los añadidos y lo
    avisa).
    """
    st.markdown("**Añadir a la revisión**")
    razon = ma.puerta(analisis)
    if razon:
        st.caption(razon)
        return
    # Antes de pedir el motivo, y no al enviarlo: sin candidatos, Revisar
    # candidatos se detiene antes de enseñar los añadidos, y el ticker se
    # añadía igual y se saltaba a una pantalla que no lo enseñaba.
    try:
        del_ranking = {f["ticker"] for f in cargar_candidatos().fichas}
    except FaltanFichas:
        st.caption(
            "Aún no se puede añadir: todavía no hay candidatos, y sin ellos "
            "**Revisar candidatos** no llega a enseñar lo añadido. Genéralos allí "
            "y vuelve: este análisis sigue aquí mientras no cierres la aplicación."
        )
        return
    except ContratoRoto:
        st.caption(
            "Aún no se puede añadir: el fichero de candidatos no se puede leer, y "
            "sin él **Revisar candidatos** no llega a enseñar lo añadido. Allí "
            "está el porqué y el botón para volver a generarlos."
        )
        return
    clave = sesion.clave_motivo(analisis.ticker)
    # Por su clave y sin `value=`, como el campo de tickers: lo que el usuario
    # edite sobrevive a las pasadas. Sin editar, sigue a la valoración: tras
    # «Actualizar precios» el motivo no puede decir el veredicto de antes.
    redactado = ma.motivo_para_la_revision(analisis.valoracion, date.today())
    if sesion.preparar_motivo(st.session_state, analisis.ticker, redactado):
        st.warning(
            "La valoración cambió desde que escribiste el motivo, y al acta va la "
            "de ahora. El programa escribiría: "
            f"«{texto.plano(redactado)}» Revisa que el tuyo siga diciendo lo que "
            "quieres."
        )
    with st.form(f"analizador_revision_{analisis.ticker}"):
        st.text_area(
            "Motivo: es la única justificación que va a constar en el acta, y lo puedes editar",
            key=clave,
        )
        enviado = st.form_submit_button("Añadir a la revisión", type="primary", icon=":material/fact_check:")
    st.caption(
        "Al acta va la valoración con los supuestos del programa, aunque hayas "
        "movido alguno: así se puede comparar entre actas. Si los moviste, dilo en "
        "el motivo."
    )
    if not enviado:
        return
    # La misma lista que pinta Revisar candidatos (`st.session_state.anadidos`).
    anadidos = st.session_state.setdefault("anadidos", [])
    motivo = st.session_state[clave]
    problema = problema_al_anadir(analisis.ticker, motivo, del_ranking, anadidos)
    if problema:
        st.error(problema)
        return
    # La del programa, y no la de los deslizadores: lo movido no se guarda.
    anadidos.append(Anadido(ticker=analisis.ticker, motivo=motivo, valoracion=analisis.valoracion))
    st.switch_page("vistas/candidatos.py")


def _resumen(analisis, contexto) -> None:
    """La pestaña Resumen: quién es, sus avisos, el veredicto con sus votos y la tarjeta."""
    st.markdown(f"#### {texto.plano(analisis.ticker)} · {texto.plano(ma.nombre(analisis))}")
    st.markdown(ma.ficha_de_identidad(analisis))
    st.caption(ma.precio_y_hora(analisis))
    for _corto, largo in ma.avisos(analisis, contexto["sp500"], contexto["trimestre"], date.today()):
        st.warning(largo)
    if analisis.clase == "etf":
        st.caption(
            "Un ETF no se valora ni se compara con un sector: aquí están su precio, "
            "su gráfico y sus noticias."
        )
    else:
        # El aviso del panel atrasado va entre los de arriba (`ma.avisos`).
        panel_dicho = ma.aviso_panel_atrasado(analisis, contexto["trimestre"]) is not None
        _valor_y_sector(analisis, panel_dicho)
    st.divider()
    _a_la_revision(analisis)


def _fundamentales(analisis, contexto) -> None:
    """La pestaña Fundamentales: la ficha de candidatos, contra quién y con qué panel."""
    ref = analisis.referencia
    if ref is None:
        st.info(ma.sin_ficha(analisis))
        return
    aviso = ma.aviso_panel_atrasado(analisis, contexto["trimestre"])
    if aviso:
        st.warning(aviso)
    # Con el aviso a la vista, la exclusión no repite que el panel se quedó atrás.
    exclusion = ma.texto_exclusion(analisis, panel_dicho=aviso is not None)
    if exclusion:
        st.warning(exclusion)
    if contexto["panel"] is not None:
        st.caption(
            ma.contra_quien(
                analisis,
                referencia.pares_en_panel(contexto["panel"], analisis.sector),
                contexto["fecha_panel"],
            )
        )
    st.markdown(
        "**Los cuatro pilares** —calidad, crecimiento, valoración y solidez—, "
        "frente a sus pares del sector"
    )
    st.markdown(medidores.medidores_pilares(ref.ficha), unsafe_allow_html=True)
    con_dato = kpis_con_dato(ref.ficha)
    if con_dato is not None:
        st.markdown(medidores.medidor_cobertura(con_dato), unsafe_allow_html=True)
    # «Sus tres más fuertes» y no «Fuerte en»: la lista es relativa a la propia
    # empresa, y sus tres peores KPIs pueden estar en «Regular».
    st.markdown("**Sus tres puntos más fuertes**")
    st.markdown("".join(medidores.medidor_kpi(i) for i in ref.ficha["destacados"]), unsafe_allow_html=True)
    st.markdown("**Sus tres puntos más flojos**")
    st.markdown("".join(medidores.medidor_kpi(i) for i in ref.ficha["flojos"]), unsafe_allow_html=True)


def _grafico(analisis, contexto) -> None:
    """La pestaña Gráfico: TradingView, y lo que se sabe y se dice de él.

    Se decide con el ticker y la bolsa: un ticker de fuera sólo se incrusta si
    su bolsa está comprobada en el widget (`grafico.COMPROBADAS_EN_WIDGET`).
    Sin el prefijo de bolsa, `T.TO` (TELUS) salía como AT&T y `BA.L` (BAE)
    como Boeing; la BMV no se ve en el widget («Símbolo solo disponible en
    TradingView»).
    """
    ticker = analisis.ticker
    bolsa = analisis.identidad.bolsa
    avisos = grafico.avisos(ticker, bolsa)
    if grafico.en_widget(ticker, bolsa):
        # El tema de la app: la paleta de `tema.py` es oscura, pero el menú de
        # ajustes de Streamlit deja cambiarlo y el gráfico tiene que seguirlo.
        oscuro = (st.context.theme.type or "dark") == "dark"
        simbolo = grafico.simbolo(ticker, bolsa)
        st.iframe(grafico.html(simbolo, oscuro), height=grafico.ALTO)
        st.caption(f"Símbolo en TradingView: {texto.plano(simbolo)}")
        for aviso in avisos:
            st.caption(aviso)
    else:
        # Un enlace en vez de un recuadro vacío, o de la empresa equivocada. El
        # primer aviso dice por qué no se incrusta y adónde lleva el enlace.
        st.info(avisos[0])
        rotulo, url = grafico.enlace(ticker, bolsa)
        st.markdown(texto.enlace(texto.plano(rotulo), url))
        for aviso in avisos[1:]:
            st.caption(aviso)
    st.info(grafico.ESTUDIO_D)


@st.fragment
def _deslizadores(ticker: str) -> None:
    """Los supuestos con sus deslizadores, y lo que sale de ellos.

    En un fragmento: moverlos sólo rehace esto, y sin red, porque `valorar`,
    `sensibilidad` y `proyeccion` son aritmética pura sobre las `Entradas` que
    se guardaron al analizar. Cada cuenta va en un `try`: `aplicar` rechaza con
    `ValueError` lo que rompe las fórmulas, y el mensaje se enseña. **Lo movido
    no se guarda en ningún sitio**: vive en las claves de los widgets.
    """
    analisis = st.session_state[sesion.CLAVE_ANALISIS][ticker]
    entradas = analisis.entradas
    pilar = pilar_valoracion(analisis.referencia)
    r_f_a_mano = None
    if entradas.r_f is None:
        # Sin Bono M (sin token de Banxico, por ejemplo) no hay valoración hasta
        # que el usuario ponga la tasa: el deslizador «pide el dato».
        st.warning(ma.falta_tasa(entradas))
        puesta = st.number_input(
            "Tasa libre de riesgo (%)",
            value=None,
            step=0.1,
            format="%.2f",
            key=sesion.clave_a_mano(ticker),
        )
        r_f_a_mano = None if puesta is None else puesta / 100
    try:
        programa = deslizadores.del_programa(entradas, r_f_a_mano)
    except ValueError as error:
        st.error(f"Esa tasa no se puede usar: {ma.supuesto_imposible(error)}.")
        return
    if programa is None:
        st.markdown(
            medidores_valoracion.resumen(ma.en_moneda_del_precio(analisis.valoracion)),
            unsafe_allow_html=True,
        )
        return

    st.button(
        "Restaurar los del programa",
        key=f"analizador_restaurar_{ticker}",
        icon=":material/restart_alt:",
        on_click=sesion.restaurar_deslizadores,
        args=(st.session_state, ticker),
    )
    en_pantalla = {}
    columnas = st.columns(2)
    for indice, (nombre_, valor) in enumerate(programa.items()):
        if nombre_ == "r_f" and entradas.r_f is None:
            continue  # La pidió la casilla de arriba.
        clave = sesion.clave_deslizador(ticker, nombre_)
        with columnas[indice % 2]:
            if valor is None:
                # El programa no tiene la cifra (sin historia, sin años de ROE):
                # se pide en vez de dibujar un deslizador sin punto de partida.
                en_pantalla[nombre_] = st.number_input(
                    f"{ma.etiqueta_deslizador(nombre_)}, sin cifra del programa",
                    value=None,
                    key=clave,
                )
            else:
                rango = deslizadores.rango(nombre_, valor)
                # Nace en la cifra del programa por su clave y sin `value=`: un
                # `value` que cambia entre pasadas reinicia el widget («El
                # formulario que se quedaba en blanco»).
                st.session_state.setdefault(clave, deslizadores.a_pantalla(nombre_, valor))
                en_pantalla[nombre_] = st.slider(
                    ma.etiqueta_deslizador(nombre_),
                    min_value=rango.minimo,
                    max_value=rango.maximo,
                    step=rango.paso,
                    format=rango.formato,
                    key=clave,
                )

    cambios = deslizadores.cambios(en_pantalla, programa, r_f_a_mano)
    try:
        movida = valorar(entradas, pilar, cambios)
        tabla_sensibilidad = sensibilidad(entradas, cambios)
        tabla_proyeccion = proyeccion(entradas, cambios)
        movidos = deslizadores.nombres_movidos(entradas, cambios)
    except ValueError as error:
        st.error(
            f"Con esos supuestos no hay valoración posible: {ma.supuesto_imposible(error)}. Muévelos, o "
            "restaura los del programa."
        )
        return

    divisa = entradas.divisa
    if movidos:
        st.caption(
            f"Moviste: {ma.lista_de_supuestos(movidos)}. Lo movido no se guarda en "
            "ningún sitio: lo que va al acta es siempre la valoración con los "
            "supuestos del programa."
        )
    en_precio = ma.en_moneda_del_precio(movida)
    st.markdown(
        medidores_valoracion.resumen(en_precio, con_tus_supuestos=bool(movidos)),
        unsafe_allow_html=True,
    )
    for nota in medidores_valoracion.pie(en_precio):
        st.caption(nota)
    if tabla_sensibilidad is not None:
        st.markdown(
            "**Sensibilidad del valor base** al coste de capital y al crecimiento "
            f"a perpetuidad, en {divisa.moneda_precio} por acción"
        )
        columnas_s, filas_s = ma.tabla_sensibilidad(tabla_sensibilidad, divisa.tipo_precio, divisa.moneda_precio)
        st.dataframe(pd.DataFrame(filas_s, columns=columnas_s), hide_index=True, width="stretch")
    if tabla_proyeccion is not None:
        with st.expander("La proyección a 10 años del escenario base"):
            columnas_p, filas_p = ma.tabla_proyeccion(tabla_proyeccion, divisa.moneda_valoracion)
            st.dataframe(pd.DataFrame(filas_p, columns=columnas_p), hide_index=True, width="stretch")


def _valoracion(analisis, contexto) -> None:
    """La pestaña Valoración: los deslizadores, o la valoración del programa si no se puede mover nada."""
    valoracion = analisis.valoracion if isinstance(analisis.valoracion, dict) else {}
    if analisis.entradas is None or valoracion.get("motivo") == "error_interno":
        # Sin entradas no hay nada que mover; con `error_interno` la cuenta falló
        # por un defecto y volvería a fallar con cada movimiento.
        st.markdown(
            medidores_valoracion.resumen(ma.en_moneda_del_precio(analisis.valoracion)),
            unsafe_allow_html=True,
        )
        if analisis.entradas is not None:
            st.caption(
                "Los deslizadores no se dibujan: la cuenta falló por un defecto del "
                "programa, y volvería a fallar con cada movimiento."
            )
        return
    aviso = ma.aviso_bono_m(analisis.entradas.procedencia_r_f, date.today())
    if aviso:
        st.warning(aviso)
    _deslizadores(analisis.ticker)


def _hechos(ticker: str, hechos: list, consultado: bool) -> None:
    """Los 8-K de un ticker de la SEC, y su interpretación con IA.

    `consultado`: si la SEC respondió. Si no, la lista llega vacía igual --o
    con lo último guardado--, y no se afirma que no haya ninguno: el aviso de
    la fuente está arriba.
    """
    st.caption(
        "Formularios 8-K: lo que la empresa está **obligada** a comunicar a la SEC, "
        "con fecha y firma. No es prensa y no se mezcla con ella. Van desplegados "
        "los tipos que pueden mover los números sobre los que se construyó la "
        "tesis; el resto se pliega, pero no se descarta."
    )
    destacados, plegados = ma.repartir_hechos(hechos)
    visibles, fuera = ma.recorte(destacados)
    for hecho in visibles:
        st.markdown(texto.linea_de_hecho(hecho))
    if fuera:
        st.caption(f"Quedan {fuera} hechos destacados sin mostrar, más antiguos que los de arriba.")
    if plegados:
        with st.expander(f"Otros {len(plegados)} expedientes de trámite"):
            st.caption(
                "Ninguno de estos toca los números de la tesis: votaciones, anexos, "
                "cambios de estatutos. Se enseñan igual, porque plegar no es descartar."
            )
            visibles_p, fuera_p = ma.recorte(plegados)
            for hecho in visibles_p:
                st.markdown(texto.linea_de_hecho(hecho))
            if fuera_p:
                st.caption(f"Y {fuera_p} más, más antiguos.")
    if not destacados and plegados:
        # Que no haya nada destacado habiendo trámite es una respuesta: hubo
        # movimiento y nada de lo que importa. Un hueco vacío parece que no se miró.
        st.caption("Sin hechos materiales en el periodo; sólo trámite.")
    elif not hechos and consultado:
        st.caption("Ningún 8-K en la ventana consultada.")
    elif not hechos:
        st.caption(
            "No se pudo preguntar a la SEC —el aviso está arriba—, así que no se "
            "sabe si hay algún 8-K: no es lo mismo que no haya ninguno."
        )
    st.markdown("**Qué dicen estos 8-K**")
    st.caption(
        f"Se leen los {resumen.TOPE_HECHOS} hechos destacados más recientes, como en "
        "Seguimiento. El modelo no ve nada de tu cartera: ni pesos ni importes."
    )
    panel_ia.interpretar_hechos(
        st,
        tuple(destacados[: resumen.TOPE_HECHOS]),
        archivo_analizador.ruta_de(ticker),
        {ticker},
        pesos=(),
        clave=f"analizador_ia_{ticker}",
        consultado=consultado,
        con_enlace_a_perfil=True,
        con_confirmacion=True,
    )


def _noticias(analisis, contexto) -> None:
    """La pestaña Noticias y calendario: lo que hacía la pantalla de Noticias, para un ticker."""
    ticker = analisis.ticker
    fuentes = ma.fuentes_de(analisis.clase)
    izquierda, derecha = st.columns([3, 1], vertical_alignment="center")
    izquierda.caption(
        "Los hechos que la empresa está obligada a presentar van separados de la "
        "prensa, que no lo está. Aquí no se recomienda nada."
    )
    forzar = derecha.button(
        "Actualizar noticias",
        key=f"analizador_noticias_{ticker}",
        icon=":material/refresh:",
        width="stretch",
        help="Vuelve a pedir las fuentes ahora mismo, sin esperar a que caduque lo guardado.",
    )
    # Lo que falló al pulsar «Actualizar noticias» en la pasada anterior, que
    # terminó en `st.rerun()` sin llegar a enseñarlo. Con `pop`: se dice una vez.
    clave_avisos = f"analizador_avisos_noticias_{ticker}"
    de_antes = st.session_state.pop(clave_avisos, {})
    recogido, horas, fallidas, problemas = {}, {}, set(), {}
    with st.spinner(f"Consultando las fuentes de {ticker}…"):
        for fuente in fuentes:
            datos, problema, cuando, vigente = traer.traer(fuente, ticker, traer.DESCARGA[fuente], forzar)
            recogido[fuente] = list(datos)
            horas[fuente] = (cuando, vigente)
            if problema:
                fallidas.add(fuente)
                problemas[fuente] = problema
            aviso = problema or de_antes.get(fuente)
            if aviso:
                st.warning(f"**{ma.ETIQUETA_FUENTE[fuente]}** — no se pudo traer. {texto.plano(aviso)}")
    if forzar:
        # «Lo que viene» y la columna «Próximo evento» ya se pintaron, más
        # arriba, con el calendario de antes: otra pasada los repinta con lo
        # recién traído, que sale de la caché. Los fallos viajan a esa pasada
        # por la sesión: si lo guardado sigue vigente, `traer` no vuelve a
        # pedir nada y el aviso se perdería.
        st.session_state[clave_avisos] = problemas
        st.rerun()

    st.markdown("##### Lo que viene")
    proximos = ma.proximos(recogido["agenda"])
    for evento in proximos:
        st.markdown(
            f"**{texto.plano(evento.detalle)}** — {evento.cuando:%d/%m/%Y} · "
            f"{texto.cuanto_falta(evento.cuando)}"
        )
    if not proximos and "agenda" in fallidas:
        # Como con la prensa y los 8-K: vacío porque falló no es «ninguna».
        st.caption(
            "No se pudo traer el calendario —el aviso está arriba—: no se sabe si "
            "hay fechas próximas."
        )
    elif not proximos:
        st.caption(
            "Ninguna fecha próxima. El calendario sólo trae resultados y dividendos, "
            "y no todas las empresas los tienen publicados: que esto esté vacío no "
            "significa que no vaya a pasar nada."
        )

    st.markdown("##### Lo que pasó — hechos")
    if "hechos" in fuentes:
        _hechos(ticker, recogido["hechos"], consultado="hechos" not in fallidas)
    else:
        st.caption(ma.sin_hechos(analisis.clase))

    st.markdown("##### Lo que pasó — prensa")
    st.caption(
        "Titulares que otros escribieron. Nadie responde de ellos y el programa no "
        "los filtra: no hay forma defendible de decidir cuál importa. Se enseña el "
        "medio y el formato para que puedas descartarlos tú."
    )
    prensa = sorted(recogido["prensa"], key=lambda n: n.cuando, reverse=True)
    visibles, fuera = ma.recorte(prensa)
    if not visibles:
        st.caption(ma.sin_prensa("prensa" in fallidas, horas["prensa"][0]))
    for noticia in visibles:
        firma = " · ".join(
            p for p in (texto.plano(noticia.medio), texto.plano(ma.formato_noticia(noticia.clase))) if p
        )
        st.markdown(
            texto.enlace(texto.plano(noticia.titular), noticia.url)
            + f"  \n{firma} · {noticia.cuando.astimezone():%d/%m/%Y %H:%M}"
        )
        if noticia.resumen:
            st.caption(texto.plano(noticia.resumen[:240]))
    if fuera:
        st.caption(f"Quedan {fuera} noticias sin mostrar, más antiguas que las de arriba.")

    st.divider()
    for fuente in fuentes:
        cuando, vigente = horas[fuente]
        st.caption(ma.linea_de_hora(fuente, cuando, vigente))
    st.caption(
        "La hora se enseña siempre, esté el dato fresco o no. Un dato que se lee "
        "como recién traído sin serlo es peor que no tener dato."
    )


def _ia(analisis, contexto) -> None:
    """La pestaña IA: la tesis, el contraste con la empresa y la explicación de la valoración."""
    analizador_ia.pintar(analisis)


# Qué función dibuja cada pestaña de `ma.pestanas_de`. Una pestaña sin función
# no se dibuja, en vez de salir vacía.
_PESTANAS = {
    "Resumen": _resumen,
    "Valoración": _valoracion,
    "Fundamentales": _fundamentales,
    "Gráfico": _grafico,
    "Noticias y calendario": _noticias,
    "IA": _ia,
}


def _detalle(analisis, contexto) -> None:
    """El detalle del ticker elegido, en pestañas.

    Un ETF sólo tiene las suyas: las demás no se dibujan, en vez de salir
    vacías. Streamlit ejecuta el contenido de todas las pestañas en cada
    pasada, estén a la vista o no.
    """
    if analisis.clase != "etf":
        # Una vez por pantalla, encima de las pestañas: la regla del registro es
        # glosar la primera vez que algo sale en una pantalla.
        with st.expander("📏 Cómo se leen los medidores"):
            st.markdown(medidores.como_se_leen())
        with st.expander(medidores_valoracion.TITULO_GLOSARIO):
            st.markdown(medidores_valoracion.glosario())
    nombres = [n for n in ma.pestanas_de(analisis.clase) if n in _PESTANAS]
    for nombre_, pestana in zip(nombres, st.tabs(nombres, key=f"analizador_pestanas_{analisis.ticker}")):
        with pestana:
            _PESTANAS[nombre_](analisis, contexto)


# --- La pasada --------------------------------------------------------------------

# Antes de dibujar el campo: un encargo de otra pantalla escribe en su clave.
encargo = sesion.recoger(st.session_state)

with st.container(border=True):
    st.text_input(
        f"Tickers, separados por comas o espacios (hasta {MAX_TICKERS})",
        key=sesion.CLAVE_TEXTO,
        placeholder="MU, WALMEX.MX, TSM, JPM, SPY",
        help=(
            "Una empresa de la SEC (MU), una extranjera (TSM), una de la BMV con "
            "su sufijo (WALMEX.MX) o un ETF (SPY). Las clases de acción, con punto "
            "o con guion: BRK.B o BRK-B."
        ),
    )
    izquierda, derecha = st.columns([4, 1], vertical_alignment="top")
    with izquierda.expander("Cargar de un libro"):
        _cargar_de_un_libro()
    pulsado = derecha.button("Analizar", type="primary", width="stretch", icon=":material/search:")

validos, invalidos = separar(st.session_state.get(sesion.CLAVE_TEXTO, ""))
if invalidos:
    st.warning(ma.aviso_invalidos(invalidos))
if len(validos) > MAX_TICKERS:
    st.warning(
        f"Hay {len(validos)} tickers y el tope es {MAX_TICKERS}: cada uno cuesta "
        f"varias consultas a Yahoo y a la SEC. Quita {len(validos) - MAX_TICKERS} "
        "para poder analizar."
    )

panel, fecha_panel = referencia.cargar_panel()
frescura = referencia.frescura()
tabla = load_sectors()
contexto = {
    "panel": panel,
    "fecha_panel": fecha_panel,
    # La tabla congelada del S&P 500: es con la que se hace el panel, y vale
    # también sin él (D2 del plan de N2).
    "sp500": set(tabla),
    "trimestre": None if panel is None else referencia.trimestre_final(panel),
}

if (pulsado or encargo is not None) and validos and len(validos) <= MAX_TICKERS:
    hechos = sesion.preparar(st.session_state, frescura.panel)
    st.session_state[sesion.CLAVE_TICKERS] = validos
    faltan = sesion.pendientes(validos, hechos)
    if faltan:
        _analizar_tickers(faltan, hechos, panel, tabla)

tickers = st.session_state.get(sesion.CLAVE_TICKERS, [])
hechos = st.session_state.get(sesion.CLAVE_ANALISIS, {})
analizados = [hechos[t] for t in tickers if t in hechos]

_panel_de_referencia(panel, fecha_panel, frescura, analizados)

if not analizados:
    st.info(
        "Escribe uno o varios tickers y pulsa **Analizar**. De cada uno salen su "
        "ficha frente a las empresas del S&P 500 de su sector, su valor "
        "intrínseco con los supuestos del programa —que puedes mover—, su gráfico "
        "y sus noticias."
    )
    st.stop()

if sesion.panel_cambiado(st.session_state, frescura.panel):
    st.warning(
        "El panel de referencia cambió desde que se analizaron estos tickers: "
        "pulsa **Analizar** para rehacer sus fichas con el nuevo."
    )

if any(a.motivo == "sin_identidad_edgar" for a in analizados):
    # D14 del plan de N2: el resolver no cambia; se dice una vez y se manda a Perfil.
    st.warning(
        "Falta el correo para EDGAR: sin él la SEC no responde, y las empresas que "
        "presentan en ella se quedan sin clase y sin ficha."
    )
    if st.button("Configurar mis credenciales", key="analizador_credenciales_edgar", icon=":material/key:"):
        st.switch_page("vistas/perfil.py")

agenda, problemas_agenda = _agenda(analizados)

st.subheader("Resumen")
st.dataframe(
    pd.DataFrame(
        [
            ma.fila(a, ma.proximo(agenda.get(a.ticker, [])), contexto["sp500"], contexto["trimestre"], date.today())
            for a in analizados
        ],
        columns=list(ma.COLUMNAS),
    ),
    hide_index=True,
    width="stretch",
)
st.caption(ma.leyenda_resumen())
if st.button(
    "Actualizar precios",
    icon=":material/refresh:",
    help=(
        "Vuelve a pedir la cotización y rehace la valoración con ella; la ficha "
        "frente al sector no depende del precio de hoy y no se rehace. Yahoo se "
        "consulta como mucho cada quince minutos: antes sale el precio guardado, "
        "con su hora. Un ticker que falló se analiza otra vez entero."
    ),
):
    _actualizar_precios([a.ticker for a in analizados], hechos, panel, tabla)
    st.rerun()

_lo_que_viene(agenda, problemas_agenda)

st.divider()
st.subheader("Detalle")
con_detalle = [a.ticker for a in analizados if a.clase is not None]
if not con_detalle:
    st.info("Ninguno de estos tickers tiene detalle: el motivo de cada uno está en su fila.")
    st.stop()
sesion.fijar_elegido(st.session_state, con_detalle)
elegido = st.selectbox(
    "Ticker",
    con_detalle,
    key=sesion.CLAVE_ELEGIDO,
    format_func=lambda t: f"{t} — {ma.nombre(hechos[t])}",
)
sesion.recordar_elegido(st.session_state, elegido)
_detalle(hechos[elegido], contexto)
