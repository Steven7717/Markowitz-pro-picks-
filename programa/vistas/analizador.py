"""El Analizador: cualquier acción con la ficha de los candidatos, su gráfico y sus noticias.

Widgets sin lógica, como el resto de `vistas/`. Lo que se decide --qué es cada
ticker, cuánto vale, qué se dice de él-- vive en `analizador/`,
`medidores_analizador.py` y `medidores_valoracion.py`, con tests: este guion
pinta.

Absorbe «Noticias y calendario», que salió del menú: lo que aquella pantalla
hacía para un libro entero se hace aquí con «Cargar de un libro», y cada ticker
tiene sus hechos, su prensa y su calendario en su pestaña.

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
from analizador import grafico, referencia, sesion
from aprobacion.carga import kpis_con_dato
from analizador.analisis import analizar, con_precio_nuevo
from analizador.resolver import MAX_TICKERS, separar
from aprobacion.generacion import disponibilidad
from fundamentals.fetch import CorridaAbortada
from fundamentals.sectors import load_sectors
from noticias import macro, texto, traer
from seguimiento import posiciones
from vistas import libros

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
    st.caption(
        f"{len(tickers)} activos: lo que tienes ahora más lo que el objetivo dice "
        "que deberías tener. Sólo viajan los tickers, ni pesos ni importes."
    )
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
            st.error(
                f"No se pudo escribir el panel: {texto.plano(str(error))}. El panel de "
                "antes sigue como estaba; puedes volver a intentarlo en un momento."
            )
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
    if not proximos:
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
    exclusion = ma.texto_exclusion(analisis, panel_dicho=panel_dicho)
    if exclusion:
        st.caption(exclusion)


def _resumen(analisis, contexto) -> None:
    """La pestaña Resumen: quién es, sus avisos, el veredicto con sus votos y la tarjeta."""
    st.markdown(f"#### {texto.plano(analisis.ticker)} · {texto.plano(ma.nombre(analisis))}")
    st.markdown(ma.ficha_de_identidad(analisis))
    fila = ma.fila(analisis, None, contexto["sp500"], contexto["trimestre"], date.today())
    st.caption(f"Precio: {fila['Precio']}, cotización del {fila['Hora del precio']}.")
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


# Qué función dibuja cada pestaña de `ma.pestanas_de`. Una pestaña sin función
# no se dibuja, en vez de salir vacía.
_PESTANAS = {
    "Resumen": _resumen,
    "Fundamentales": _fundamentales,
    "Gráfico": _grafico,
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
_detalle(hechos[elegido], contexto)
