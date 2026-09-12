"""El libro de posiciones: lo que se compró de verdad y cómo va.

Esta pantalla **no calcula nada**. La aritmética vive en `seguimiento/panel.py`
y el HTML de las barras en `medidores.py`; aquí sólo se decide qué se enseña,
en qué orden y con cuánto sitio. El reparto es del sub-proyecto K y el motivo
está escrito en el encabezado de `panel.py`: lo que se calculaba dentro de un
guion de Streamlit no lo podía mirar ningún test.
"""

import contextlib
import html
from datetime import date

import pandas as pd
import streamlit as st

import cartera
import medidores
import tema
from exporter import to_excel
from interprete import archivo
from interprete import cliente as interprete_cliente
from interprete import noticias as interprete_noticias
from noticias import resumen, texto, traer
from seguimiento import comparacion, libro as mod, panel, posiciones, precios
from vistas import panel_ia

st.markdown(
    tema.cabecera(
        "Seguimiento",
        "Lo que compraste con tu dinero, medido contra el objetivo que te dio "
        "el optimizador. Los portafolios guardados son fotografías; esto es el "
        "libro de lo que pasó después.",
    ),
    unsafe_allow_html=True,
)

# `portafolios.py` y el optimizador fijan esto y saltan. El estreno ya no vive
# aqui, asi que se reenvia en vez de dejar la pantalla sin explicar por que no
# pasa nada.
if st.session_state.get("portafolio_a_seguir") is not None:
    st.switch_page("vistas/estrenar.py")

entradas = mod.listar()

if not entradas:
    st.info(
        "Todavía no llevas ningún libro. Empiézalo en **Empezar un libro**: "
        "desde un portafolio guardado, o cargando a mano una cartera que "
        "ya tenías."
    )
    if st.button("Ir a portafolios guardados", icon=":material/folder_open:"):
        st.switch_page("vistas/portafolios.py")
    st.stop()

# Los ilegibles se pintan con su motivo, como en vistas/portafolios.py. Aqui no
# hay boton de borrar: alli lo peor que se pierde es una fotografia repetible, y
# aqui es el historial entero de lo que alguien compro.
for entrada in entradas:
    if entrada.libro is None:
        st.error(f"`{entrada.ruta.name}` no se puede leer: {entrada.error}")

sanos = [e for e in entradas if e.libro is not None]
if not sanos:
    st.stop()

etiquetas = {f"{e.libro.nombre} · {e.ruta.name}": e for e in sanos}

# El nombre del libro grande, con el selector al lado. Hasta el sub-proyecto K
# el nombre solo aparecia DENTRO del desplegable: para saber que cartera se
# estaba mirando habia que abrirlo. En un panel que se abre a diario la
# identidad de lo que se mira va primero, no escondida en el control que la
# cambia.
#
# La columna de la izquierda se escribe DESPUES que la derecha porque el nombre
# depende de la seleccion. Streamlit coloca cada elemento en la columna a la que
# se lo pides, no en el orden en que se lo pides.
col_nombre, col_libro = st.columns([3, 2], vertical_alignment="center")
elegida = etiquetas[col_libro.selectbox("Libro", options=list(etiquetas))]
actual = elegida.libro
col_nombre.markdown(
    f'<div style="font-size:1.45rem;font-weight:700;line-height:1.2;'
    f'color:{tema.TEXTO}">{html.escape(actual.nombre)}</div>',
    unsafe_allow_html=True,
)

# La linea de contexto se reserva aqui y se rellena mas abajo: la fecha de
# valoracion no se sabe hasta despues de descargar precios, y la identidad del
# libro tiene que salir ANTES que los avisos de esa descarga. Leer «sin precios
# para AAPL» sin saber todavia de que cartera se habla obliga a leerlo dos veces.
contexto = st.empty()


def _pintar_contexto(activos: int, valorado: "str | None") -> None:
    """Moneda, fecha de valoracion y numero de activos, en un renglon.

    `valorado` es `None` cuando no hay ni un dia valorado, y entonces se dice
    eso y no una fecha: poner la de hoy afirmaria que la cartera esta medida a
    hoy, que es justo lo que no ocurre.

    El «no a hoy» era hasta el sub-proyecto K un `st.caption` aparte. Se pliega
    aqui porque decia lo mismo que esta linea dos renglones mas abajo, y dos
    frases seguidas con el mismo dato es una de las cosas que este panel existe
    para quitar. La aclaracion se conserva entera: sin ella, una fecha suelta se
    lee como «actualizado» y lo que dice es otra cosa.
    """
    cuando = "todavía sin valorar"
    if valorado:
        cuando = f"valorado al **{valorado}**"
        if valorado < date.today().isoformat():
            cuando += ", no a hoy"
    contexto.caption(
        f"**{actual.moneda}** · {cuando} · "
        f"**{activos}** activo{'' if activos == 1 else 's'}"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _cierre_del_dia(ticker: str, fecha: str):
    """El cierre de un ticker en una fecha, aunque no esté ya en el libro.
    Se descarga aparte y no se busca en `historia` porque el ticker puede ser
    nuevo — la primera compra de una empresa que el libro todavía no conoce — y
    entonces no hay ninguna columna donde mirar. La ventana pide dos días
    porque `yf.download` trata `end` como exclusivo.
    """
    from datetime import timedelta
    hasta = (date.fromisoformat(fecha) + timedelta(days=1)).isoformat()
    return precios.cierre_en(precios.descargar([ticker], desde=fecha, hasta=hasta),
                             ticker, fecha)

# --- Alta de asiento ---------------------------------------------------------

def _resumen(asiento) -> str:
    """Lo que se acaba de registrar, en una linea.

    Un «Registrado.» a secas no se puede comprobar: si pulsaste dos veces, dos
    «Registrado.» se leen igual que uno. Con el importe y el ticker dentro, el
    segundo mensaje se distingue del primero y el usuario ve QUE entro.
    """
    partes = [asiento.tipo]
    if asiento.ticker:
        partes.append(asiento.ticker)
    if asiento.acciones:
        partes.append(f"{asiento.acciones:g} acc.")
    if asiento.importe:
        partes.append(f"{asiento.importe:,.2f}")
    partes.append(f"el {asiento.fecha}")
    return " · ".join(partes)


def _registrar_operacion(plegado: bool = True):
    """El formulario de alta. Es una funcion porque hacen falta dos llamadas.

    Un libro recien creado no tiene asientos, y la pantalla corta ahi para no
    descargar precios de nada ni calcular un rendimiento sobre cero. Pero si el
    corte se lleva por delante el formulario, ese libro es un callejon sin
    salida: dice «anade el primero» y no hay donde anadirlo. Asi que se llama
    antes de cortar, y otra vez en su sitio cuando si hay asientos.

    `plegado` decide si se envuelve en un desplegable. **Dentro de su propia
    pestaña no se envuelve**: la pestaña ya es la puerta, y un desplegable
    detras de otra puerta es la razon por la que este formulario no se
    encontraba. En los caminos del libro vacio si va plegado, porque alli
    comparte sitio con el aviso que explica por que no hay nada mas.
    """
    # **Lo que se registro en la pasada anterior se cuenta AQUI.** El boton
    # termina en `st.rerun()`, y un `st.rerun()` tira la pasada entera antes de
    # dibujarla: un `st.success` escrito justo antes no llega nunca a la
    # pantalla. Asi se perdian los dos avisos que mas importan --que hizo falta
    # crear una aportacion para financiar la compra, y que el precio es del
    # cierre y queda marcado como estimado--, y registrar parecia no hacer nada.
    # Que parezca no hacer nada es lo que lleva a pulsar otra vez.
    #
    # Es el mismo remedio que el bloque de noticias de mas abajo, y por la misma
    # razon. `pop` y no `get`: se enseña una vez y no se queda pegado afirmando
    # algo que ya paso.
    for _clase, _texto in st.session_state.pop("registro_avisos", []):
        getattr(st, _clase)(_texto)

    marco = st.expander("Registrar una operación") if plegado else contextlib.nullcontext()
    with marco:
        tipo = st.selectbox("Tipo", options=sorted(mod.TIPOS - {"anulacion"}))
        cuando = st.date_input("Fecha", value=date.today(), max_value=date.today())
        # Los del libro primero, y `accept_new_options` para el que compras hoy
        # por primera vez. Escribirlo a pelo era la puerta por la que entraba un
        # ticker mal tecleado, que despues sale en «Sin precios para: ...» y ya
        # no hay forma de corregirlo.
        #
        # La lista junta lo comprado y lo que el objetivo contempla: se puede
        # comprar algo que esta en el plan y todavia no se tiene, y ese es
        # justamente el caso que Rebalanceo propone.
        conocidos = sorted(
            {a.ticker for a in actual.asientos if a.ticker}
            | set(mod.pesos_objetivo(actual.objetivo))
        )
        ticker = None
        if tipo in mod.CON_TICKER:
            elegido = st.selectbox(
                "Ticker", options=conocidos, index=None,
                accept_new_options=True,
                placeholder="Elige uno del libro o escribe otro",
                help="Los de tu cartera salen en la lista. Si compras algo "
                     "nuevo, escríbelo y pulsa Enter.",
            )
            ticker = (elegido or "").strip().upper() or None

        importe = acciones = precio = None
        del_cierre = False
        if tipo in {"compra", "venta"}:
            col_a, col_b, col_c = st.columns(3)
            importe = col_a.number_input("Importe", min_value=0.0, value=0.0) or None
            acciones = col_b.number_input("Acciones", min_value=0.0, value=0.0) or None
            precio = col_c.number_input("Precio", min_value=0.0, value=0.0) or None
            del_cierre = st.checkbox(
                "No recuerdo el precio: usa el cierre de ese día",
                help="La operación queda marcada como precio estimado y se ve así en "
                     "el historial. Una compra intradía en un día volátil se desvía "
                     "un 3-4% del cierre.",
            )
            st.caption(
                "Rellena el importe **o** las acciones, más el precio. El tercero se "
                "calcula solo. Si escribes los tres, mandan los tres: el bróker "
                "aplica redondeos que ninguna división reproduce."
            )
        else:
            importe = st.number_input("Importe", min_value=0.0, value=0.0) or None

        comision = st.number_input("Comisión", min_value=0.0, value=0.0)
        nota = st.text_input("Nota (opcional)")

        if st.button("Registrar", type="primary", icon=":material/add:"):
            try:
                estimado = False
                if tipo in {"compra", "venta"}:
                    # El cierre solo hace falta cuando hay que RELLENAR el precio.
                    # Exigirlo siempre impedia registrar una compra el mismo dia de
                    # hacerla --que es justo cuando la gente la registra-- porque la
                    # sesion todavia no ha cerrado. Y no hace falta: `serie()` ya
                    # cuenta esos asientos en `posteriores`, y la pantalla avisa de
                    # que todavia no entran en el valor.
                    if del_cierre or precio is None:
                        cierre = _cierre_del_dia(ticker, cuando.isoformat())
                        if cierre is None:
                            # Dos causas muy distintas, y decir la equivocada manda
                            # al usuario a revisar una fecha que esta bien.
                            if cuando >= date.today():
                                raise mod.AsientoInvalido(
                                    f"Todavía no hay cierre de {ticker} del "
                                    f"{cuando.isoformat()}: la sesión no ha terminado. "
                                    "Escribe el precio que pagaste, o espera al cierre "
                                    "para que lo rellene por ti."
                                )
                            raise mod.AsientoInvalido(
                                f"{ticker} no cotizó el {cuando.isoformat()}: revisa "
                                "la fecha, o el ticker si la empresa aún no había "
                                "salido a bolsa."
                            )
                        precio, estimado = cierre, True
                    importe, acciones, precio = mod.derivar(importe, acciones, precio)
                nuevo = mod.Asiento(
                    id=f"{cuando.isoformat()}-{len(actual.asientos) + 1}",
                    fecha=cuando.isoformat(), tipo=tipo, ticker=ticker or None,
                    acciones=acciones, precio=precio, importe=importe or 0.0,
                    comision=comision, precio_estimado=estimado, nota=nota,
                )
                actualizado, escritos = mod.anadir(actual, nuevo, financiar=True)
            except mod.AsientoInvalido as error:
                st.error(str(error))
            else:
                mod.actualizar(actualizado, elegida.ruta)

                # Se guardan para la pasada siguiente en vez de escribirse aqui:
                # `st.rerun()` esta a dos lineas y se los llevaria por delante.
                avisos = [("success", f"Registrado: {_resumen(nuevo)}.")]
                if len(escritos) > 1:
                    avisos.append((
                        "warning",
                        f"**Se registró además una aportación de "
                        f"{escritos[0].importe:,.2f}**, porque no había efectivo "
                        "suficiente para pagar la compra. Son dos asientos, y los "
                        "dos salen en **Movimientos**.",
                    ))
                if estimado:
                    avisos.append((
                        "info",
                        f"Precio tomado del cierre del {cuando.isoformat()}: "
                        f"{precio:,.2f}. Queda marcado como estimado en el historial.",
                    ))
                st.session_state["registro_avisos"] = avisos
                st.rerun()


# --- Precios ----------------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
if not vivos:
    _pintar_contexto(activos=0, valorado=None)
    st.info(
        "Este libro todavía no tiene ningún asiento. Registra el primero aquí "
        "debajo: puede ser una aportación de dinero, o directamente la compra "
        "que ya hiciste."
    )
    _registrar_operacion()
    st.stop()

tickers = sorted({a.ticker for a in vivos if a.ticker})
desde = min(a.fecha for a in vivos)

if not tickers:
    # Solo movimientos de efectivo, ninguna compra. No hay nada que descargar
    # --y `precios.descargar([])` revienta en pandas con "No objects to
    # concatenate"-- ni nada que valorar, pero si hay un saldo que enseñar y un
    # formulario con el que seguir.
    _pintar_contexto(activos=0, valorado=None)
    st.info(
        "Todavía no hay ninguna compra: el libro sólo tiene movimientos de "
        f"efectivo. Saldo disponible: "
        f"**{posiciones.estado(actual.asientos).efectivo:,.2f} {actual.moneda}**."
    )
    _registrar_operacion()
    st.stop()


@st.cache_data(ttl=3600, show_spinner="Descargando precios...")
def _historia(tickers: tuple[str, ...], desde: str):
    return precios.descargar(list(tickers), desde=desde)


historia = _historia(tuple(tickers), desde)


if historia.sin_datos:
    # No basta con decir que faltan precios. El dinero de esas compras SÍ salió
    # del efectivo, así que el valor de abajo está rebajado por su importe
    # entero y el gráfico enseña una caída que no ocurrió. Inventarles un valor
    # sería peor; nombrarlo es lo único honesto.
    #
    # **El orden de las causas importa.** Antes esto terminaba en «comprueba que
    # el ticker es correcto y que la empresa sigue cotizando», que son las dos
    # causas PERMANENTES, y se callaba la mas comun con diferencia: que la
    # descarga fallara sin mas. Mandaba a buscar un error de tecleo que
    # normalmente no existe -- comprobado con un libro real donde faltaban MSFT y
    # MU, dos tickers perfectamente validos que bajaban bien al reintentar.
    #
    # Y sin boton no habia forma de reintentar: `_historia` esta cacheada una
    # hora, asi que el fallo se quedaba congelado con la pantalla. Esperar o
    # reiniciar la app eran las dos unicas salidas, y ninguna estaba escrita.
    st.warning(
        "Sin precios para: " + ", ".join(historia.sin_datos) + ". No valen "
        "cero: es que no se pudieron descargar. **El valor y el gráfico de "
        "abajo no las incluyen**, así que la cifra que ves es un mínimo, no el "
        "total.\n\n"
        "Lo más probable es que la descarga fallara sin más: pasa, y se arregla "
        "reintentando. **Los precios se guardan una hora**, así que sin pulsar "
        "el botón esto seguiría igual hasta que caduquen. Si al reintentar "
        "siguen faltando, entonces sí: comprueba que el ticker sea correcto y "
        "que la empresa siga cotizando."
    )
    if st.button("Reintentar la descarga", icon=":material/refresh:"):
        # `.clear()` tira la cache de esta funcion entera. Es mas de lo que hace
        # falta --se rebajan tambien los tickers que si vinieron-- pero
        # `st.cache_data` no sabe invalidar una parte de un resultado, y bajar de
        # mas es preferible a dejar dentro el fallo que se venia a quitar.
        _historia.clear()
        st.rerun()

marcha = posiciones.serie(actual.asientos, historia)
ultimos = {t: precios.ultimo(historia, t) for t in historia.cierres.columns}
precios_hoy = {t: p for t, (p, _) in ultimos.items() if p is not None}

# Un libro estrenado hoy tiene todos sus asientos fechados hoy, y el ultimo
# cierre publicado es el de ayer: la serie no puede valorar ni uno solo, y el
# valor sale 0,00. Pero la cartera no vale cero --nadie ha medido eso-- es que
# todavia no se puede valorar, y en un 0,00 las dos cosas se leen igual. Es la
# regla de `cartera.formato_cifra`: un cero es una afirmacion, y aqui no la ha
# hecho nadie.
#
# La condicion es TODOS posteriores, no algunos. Con una compra de hoy encima de
# una cartera vieja si hay valor que ensenar, y para eso ya esta el aviso de
# abajo; taparlo con un «—» borraria cifras que si estan medidas.
sin_valorar = bool(marcha.posteriores) and marcha.posteriores == len(vivos)

cierres_vistos = [f for _, f in ultimos.values() if f]
ultimo_cierre = max(cierres_vistos) if cierres_vistos else None

# Sin nada valorado la linea diria que la cartera esta valorada a una fecha en
# la que todavia no existia, que es justo lo contrario de lo que pasa. El aviso
# de abajo da la misma fecha y la explica.
_pintar_contexto(
    activos=len(tickers), valorado=None if sin_valorar else ultimo_cierre
)

if sin_valorar:
    # Antes de las metricas, no despues: quien acaba de estrenar mira las cifras
    # primero, y un aviso debajo llega cuando ya ha leido el cero. Y en tono de
    # normalidad, porque lo es: no hay nada roto ni nada que el usuario tenga
    # que hacer.
    st.info(
        "**Todavía no hay nada que valorar, y es lo normal.** Este libro es de "
        "hoy y el último cierre publicado es el del "
        f"**{ultimo_cierre or 'día anterior'}**, así que ninguno de sus "
        "asientos entra aún en la serie de precios. Por eso el valor, la "
        "ganancia y los rendimientos salen como «—» en vez de como 0,00 —la "
        "cartera no vale cero, es que todavía no se puede medir— y el gráfico "
        "sale plano. La tabla por activo sí los enseña, valorados a ese último "
        "cierre, porque sale de los asientos y no de la serie. Arriba cuadrará "
        "solo cuando cierre la sesión, sin que tengas que hacer nada."
    )
elif marcha.posteriores:
    # La tabla por activo si los ve, porque sale de los asientos; el valor de
    # cabecera no, porque sale de la serie y la serie no tiene precio con que
    # valorarlos. Sin decirlo, las dos cifras se contradicen sin explicacion.
    st.warning(
        f"{marcha.posteriores} asiento(s) con fecha posterior al último cierre "
        "disponible. Aparecen en la tabla por activo y en el historial, pero "
        "**no en el valor, la ganancia ni el gráfico**: no hay precio con el "
        "que valorarlos todavía. Entrarán solos cuando cierre la sesión."
    )

# --- Los numeros de cabecera -------------------------------------------------
#
# La aritmetica vive en `seguimiento/panel.py`, fuera de este guion. Un guion de
# Streamlit no se puede importar desde un test, y lo que hay dentro de esas
# cuentas --el corte temporal comun de `aportado` y `valor`, el «—» que no es un
# cero-- estaba protegido solo por un comentario. Ahora esta protegido por
# `tests/test_panel_cabecera.py`.
cab = panel.cabecera(marcha, vivos, sin_valorar)

# CUATRO columnas, no seis. Medido en la app a 1024px con las seis: la columna
# de contenido son 724px, cada cifra recibe 79px y su caja de texto 50px, y
# Streamlit las recorta con puntos suspensivos --«51,…» «40,…» «11,…»--. No es
# que se aprieten: es que la pantalla que existe para decirte cuanto vale tu
# cartera no ensenaba ni un numero entero. A cuatro columnas cada cifra recibe
# 126px y caben nueve caracteres.
#
# Nueve, y conviene dejarlo escrito: una cartera de siete cifras --1,234,567.89,
# doce caracteres-- volveria a recortarse aun con cuatro columnas, y entonces el
# arreglo no es quitar otra cifra sino el tamano de letra de
# `[data-testid="stMetricValue"]` (`tema.py`). Hoy no es el caso.
#
# TIR y Dividendos bajan a «Por activo», donde estan sus detalles.
k1, k2, k3, k4 = st.columns(4)
k1.metric("Valor", panel._cifra(cab.valor))
k2.metric("Aportado neto", f"{cab.aportado:,.2f}",
          help="Aportaciones menos retiros: el dinero tuyo que hay dentro ahora "
               "mismo, no la suma de todo lo que pasó por la cartera.")
k3.metric("Ganancia", panel._cifra(cab.ganancia))
k4.metric(
    "TWR anual", cartera.formato_porcentaje(cab.twr_anual),
    help="Ponderado por tiempo: neutraliza cuándo metiste el dinero, así que "
         "mide la cartera y no tu timing. Es el único comparable con un índice."
         + ("" if sin_valorar else
            f" Sin anualizar, el periodo entero rindió {cab.twr_periodo:.2%}."),
)

# El texto lo escribe `panel.aviso_de_brecha`, no esta pantalla, y no es un
# capricho de reparto: hasta el sub-proyecto K el aviso afirmaba SIEMPRE que la
# separacion era «el efecto de cuando aportaste», tambien en un libro con una
# unica aportacion, donde no hay ningun «cuando» posible. Vivia aqui dentro, asi
# que ningun test podia leerlo. Ahora lo lee `tests/test_panel_brecha.py`.
aviso = panel.aviso_de_brecha(cab)
if aviso:
    st.info(aviso)

# --- Composicion -------------------------------------------------------------

st.subheader("Composición")

objetivo = actual.objetivo
comp = panel.composicion(actual.asientos, precios_hoy, objetivo)

if not comp.lineas:
    st.caption("Ningún activo con precio, así que no hay reparto que enseñar.")
else:
    # `escala` es el maximo sobre los pesos Y los objetivos, no solo sobre los
    # pesos. `.mpp-pista` lleva `overflow:hidden` (`medidores.py`), asi que un
    # objetivo por encima del peso real mayor cae fuera de la pista y **la marca
    # desaparece**: con peso 0,10, objetivo 0,35 y una escala de 0,20 la marca
    # sale en `left:175%`. Y una marca invisible se lee igual que «este activo no
    # tiene objetivo», que es justo la confusion que la guarda de `None` de
    # `barra_de_peso` existe para evitar.
    #
    # No se recorta la marca al 100%: aparcarla en el borde derecho afirmaria que
    # el objetivo es el peso mayor de la cartera, que es otra mentira distinta.
    # Lo que se arregla es el denominador.
    #
    # `_HOLGURA` esta por una razon medida, no por gusto: `.mpp-tope` son 3px
    # anclados por su borde izquierdo, asi que una marca en `left:100%` empieza
    # donde la pista acaba y `overflow:hidden` se la come entera. Sin holgura, el
    # unico caso que este denominador existe para arreglar --que el objetivo
    # mayor supere al peso mayor-- volveria a perder esa marca. Es la misma
    # solucion que `medidores._pista` ya aplica cuando aparca su tope en 99%.
    _HOLGURA = 1.02
    escala = _HOLGURA * max(
        [linea.peso for linea in comp.lineas]
        + [linea.objetivo for linea in comp.lineas if linea.objetivo is not None]
    )
    barras = sorted(comp.lineas, key=lambda linea: linea.peso, reverse=True)
    st.markdown(medidores.CSS, unsafe_allow_html=True)
    st.markdown(
        "".join(
            medidores.barra_de_peso(l.ticker, l.peso, l.objetivo, escala)
            for l in barras
        ),
        unsafe_allow_html=True,
    )

if not comp.hay_objetivo:
    st.caption(
        "Este libro no tiene un objetivo declarado, así que las barras van sin "
        "marca. No se pinta una encima del peso real: diría que ya estás donde "
        "querías estar, y eso es una afirmación sobre un plan que no existe."
    )

if comp.sin_precio:
    st.caption(
        "Fuera del reparto por no tener precio: **"
        + "**, **".join(comp.sin_precio)
        + "**. No entran porque su peso sería falso, no porque valgan cero."
    )

# El efectivo sin invertir, nombrado. Sin esta linea una cartera con el 28% en
# caja ensena doce barras que suman el 100% **de lo invertido** sin decir en
# ninguna parte que hay una cuarta parte del dinero fuera.
#
# `invertido` y `efectivo` se suman aqui y `cab.valor` NO entra en la cuenta:
# los dos primeros salen del mismo corte --los asientos, valorados al ultimo
# precio-- y aquel sale de la serie, que no ve los asientos posteriores al
# ultimo cierre. Restar o sumar dos cortes distintos es el defecto que en el
# sub-proyecto F dio GANANCIA -9.700.
if abs(comp.efectivo) >= 0.005:
    del_libro = comp.invertido + comp.efectivo
    cuota = f" (**{comp.efectivo / del_libro:.1%}** del libro)" if del_libro else ""
    st.caption(
        (f"Y **{comp.efectivo:,.2f} {actual.moneda}** sin invertir{cuota}, que no "
         "sale en ninguna barra: los pesos de arriba son sobre lo invertido."
         if comp.efectivo > 0 else
         f"El efectivo del libro está en **{comp.efectivo:,.2f} {actual.moneda}**: "
         "un descubierto. Los pesos de arriba son sobre lo invertido y no lo "
         "recogen.")
    )

# --- El detalle, en pestanas -------------------------------------------------
#
# Arriba se queda el resumen --la identidad del libro, las cuatro cifras, la
# composicion-- porque es lo que se mira a diario y **tiene que seguir a la
# vista al cambiar de pestana**: esa permanencia es la razon de ser del reparto,
# no un efecto secundario. Lo que entra aqui es el detalle, que hasta ahora
# obligaba a bajar cuatro pantallas para llegar al historial.
#
# **Streamlit ejecuta el contenido de las cuatro pestanas en cada pasada**,
# esten visibles o no: las filas del historial se construyen igual mientras
# miras el grafico. Asi que esto **no ahorra ni un calculo**, y conviene dejarlo
# escrito porque lo contrario es facil de suponer y muy facil de creer. Lo que
# ahorra es scroll, que es todo lo que promete.
#
# No hay que estilarlas: `tema.py` ya lo hace para toda la aplicacion, con el
# gancho `data-testid="stTab"` y la explicacion de por que no es `data-baseweb`.
#
# Los subtitulos de dentro se van, salvo uno. «Por activo» e «Historial» decian
# lo mismo que la pestana que ahora los contiene, y las otras dos pantallas con
# pestanas --`vistas/optimizador.py` y `vistas/perfil.py`-- no ponen ninguno:
# la etiqueta es el titulo. «Valor en el tiempo» se queda porque dice algo que
# «Evolución» no dice, que lo que evoluciona es dinero.
# «Registrar» va pegada a «Movimientos» a proposito: alli esta la lista de lo
# que ya se registro, y esto añade a esa lista. Y va en la barra, y no dentro
# de otra pestaña, porque el defecto que arregla era justo ese -- Rebalanceo
# manda a anotar aqui lo que ejecutaste, y el formulario estaba debajo de una
# tabla de once columnas dentro de un desplegable, en una pestaña que no se
# llama como lo que ibas a hacer.
#
# `key` explicita y no la automatica: sin ella Streamlit genera la clave a
# partir de los demas parametros, asi que cambiar `default` de una pasada a
# la siguiente crearia un widget distinto y la seleccion se reiniciaria --el
# usuario volveria a Evolucion en cuanto tocara cualquier cosa--. Con clave
# estable, `default` es solo el valor inicial y lo que el usuario elija
# despues manda.
#
# `pop` y no `get`: quien llega desde Rebalanceo aterriza una vez en
# «Registrar»; volver por el menu no tiene por que traerte aqui.
evolucion, por_activo, movimientos, registrar, noticias = st.tabs(
    ["Evolución", "Por activo", "Movimientos", "Registrar", "Noticias"],
    default=st.session_state.pop("seguimiento_pestana", None),
    key="pestanas_seguimiento",
)

# ── Evolución ────────────────────────────────────────────────────────────────
with evolucion:
    st.subheader("Valor en el tiempo")

    lineas = {"Tu cartera": marcha.valor}
    if objetivo is not None:
        pesos = mod.pesos_objetivo(objetivo)
        if pesos:
            lineas["Si hubieras seguido el plan"] = comparacion.referencia(
                marcha.flujos, pesos, historia.cierres
            )
    lineas["Repartir por igual (1/N)"] = comparacion.referencia(
        marcha.flujos,
        comparacion.equal_weight(list(historia.cierres.columns)),
        historia.cierres,
    )

    st.line_chart(pd.DataFrame(lineas))
    st.caption(
        "Las tres referencias reciben **el mismo dinero en las mismas fechas** que "
        "metiste tú. Así la comparación aísla qué compraste de cuándo lo compraste. "
        "Ninguna rebalancea: rebalancear es una decisión con coste."
    )

# ── Por activo ───────────────────────────────────────────────────────────────
with por_activo:
    # TIR y Dividendos viven aqui y no arriba: a seis columnas no se leia entera
    # ninguna de las seis cifras de cabecera. Y este es ademas su sitio, porque
    # el detalle que las explica --lo que aporto cada activo, lo que pago cada
    # uno-- es la tabla de debajo.
    d1, d2, _ = st.columns(3)
    d1.metric(
        "TIR", cartera.formato_porcentaje(cab.tir),
        help="Ponderada por dinero: lo que ganaste tú, con tu timing dentro. "
             "Aparece «—» cuando no hay una respuesta defendible.",
    )
    d2.metric("Dividendos", f"{cab.dividendos:,.2f}")

    # El denominador de los pesos sale de `composicion`, no de `cab.valor`: aquel
    # es la suma de los activos y este incluye el efectivo sin invertir. Con el
    # segundo la columna sumaba 71,9% al lado de un objetivo que suma 100%.
    filas = panel.filas_por_activo(
        actual.asientos, precios_hoy, comp.invertido, objetivo
    )

    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    # El metodo de coste se decia arriba, en la linea de identidad del libro. Baja
    # aqui porque es de aqui: «Coste medio», «Realizada» y «Latente» son las tres
    # columnas a las que afecta, y arriba competia por el sitio con el nombre de la
    # cartera sin explicar ninguna de las cuatro cifras de cabecera.
    st.caption(
        "Coste calculado por **media ponderada**, no por lotes: cambia el reparto "
        "entre ganancia realizada y latente, nunca el total. Esto no es un cálculo "
        "fiscal."
    )
    st.caption(
        "La contribución va en dólares y suma. Un porcentaje de contribución con "
        "aportaciones de por medio compararía cada activo contra un capital que no "
        "fue el suyo durante todo el periodo."
    )

    # Exportar. Solo Excel: `exporter.to_pdf` pasa por `kpi_rows`, que indexa
    # directamente `sharpe`, `annual_return`, `annual_vol` y `rf_rate` --claves de
    # una corrida del optimizador que un libro de seguimiento no tiene, y que
    # reventarian con KeyError--. `to_excel` si es generico: acepta cualquier
    # DataFrame y cualquier dict. Hacer que `kpi_rows` tolere dos formas distintas
    # de metricas es un cambio a un modulo compartido, y se hace cuando se decida,
    # no de refilon.
    #
    # Esta aqui, y no al final de la pagina, porque lo que descarga es esta tabla:
    # `filas` es el mismo DataFrame que se acaba de pintar. El boton se movio de
    # sitio y nada mas; `exporter.py` no se toco.
    #
    # Las mismas cifras que la pantalla, `_visible` incluido: un None sale como
    # celda vacia y un 0,00 saldria como un numero. Fuera del programa la
    # diferencia importa mas todavia, porque en una hoja de calculo ya no queda
    # ningun aviso al lado que explique de donde vino el cero.
    st.download_button(
        "Descargar Excel",
        data=to_excel(
            pd.DataFrame(filas),
            {
                "Libro": actual.nombre,
                "Moneda": actual.moneda,
                "Valorado a": "—" if sin_valorar else (ultimo_cierre or "—"),
                "Valor": cab.valor,
                "Aportado neto": cab.aportado,
                "Ganancia": cab.ganancia,
                "TWR del periodo": cab.twr_periodo,
                "TWR anual": cab.twr_anual,
                "TIR": cab.tir,
                "Dividendos": cab.dividendos,
                "Metodo de coste": "media ponderada",
            },
        ),
        file_name=f"seguimiento_{elegida.ruta.stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/table_view:",
    )

# ── Movimientos ──────────────────────────────────────────────────────────────
with movimientos:
    # El aviso de la anulacion se lee AQUI y no donde el alta lee el suyo: se
    # anula desde esta pestaña, y una confirmacion que aparece en otra es una
    # confirmacion que nadie ve.
    for _clase, _texto in st.session_state.pop("anulacion_avisos", []):
        getattr(st, _clase)(_texto)

    historial = panel.filas_de_historial(actual.asientos)
    st.dataframe(pd.DataFrame(historial), use_container_width=True, hide_index=True)

    # --- Anular ---------------------------------------------------------------
    #
    # **No se edita: se anula y se vuelve a registrar.** El libro guarda hechos,
    # y reescribir uno cambiaria el coste de adquisicion, la ganancia realizada
    # y la TIR sin dejar rastro de que cambio. Anulando, las dos lineas siguen
    # ahi y la tabla de arriba enseña cual quedo tachada.
    #
    # Va aqui y no en «Registrar» porque para elegir cual anular hay que verlos,
    # y la lista esta justo encima.
    _anulados = {a.anula for a in actual.asientos if a.tipo == "anulacion" and a.anula}
    _anulables = [
        a for a in actual.asientos
        if a.tipo != "anulacion" and a.id not in _anulados
    ]
    if _anulables:
        with st.expander("Anular un asiento"):
            st.caption(
                "Para corregir algo mal registrado: se anula y se vuelve a "
                "registrar bien. **Las dos líneas se quedan en esta tabla** — una "
                "tachada — porque el libro guarda lo que pasó, incluido el error."
            )
            _cual = st.selectbox(
                "Cuál", options=list(reversed(_anulables)),
                format_func=lambda a: f"{a.fecha} · {_resumen(a)}",
                index=None, placeholder="Elige el asiento a anular",
            )
            _motivo = st.text_input("Motivo (opcional)", key="motivo_anulacion")
            if _cual is not None:
                _confirmar, _ = st.columns([2, 3])
                if _confirmar.button(
                    "Anular este asiento", type="primary",
                    icon=":material/backspace:",
                ):
                    _anulacion = mod.Asiento(
                        id=f"{date.today().isoformat()}-{len(actual.asientos) + 1}",
                        fecha=date.today().isoformat(),
                        tipo="anulacion",
                        anula=_cual.id,
                        nota=_motivo,
                    )
                    try:
                        _nuevo_libro, _ = mod.anadir(actual, _anulacion)
                    except mod.AsientoInvalido as _error:
                        st.error(str(_error))
                    else:
                        mod.actualizar(_nuevo_libro, elegida.ruta)
                        # Como en el alta: `st.rerun()` se llevaria el mensaje por
                        # delante, asi que viaja por `session_state`.
                        st.session_state["anulacion_avisos"] = [(
                            "success",
                            f"Anulado: {_resumen(_cual)} del {_cual.fecha}. "
                            "Sigue en la tabla, marcado como anulado, y ya no "
                            "cuenta para el valor ni para el coste.",
                        )]
                        st.rerun()

# ── Registrar ────────────────────────────────────────────────────────────────
with registrar:
    st.caption(
        "Lo que de verdad ejecutaste en el bróker. **Aquí entra sólo lo que ya ocurrió**: "
        "las propuestas de Rebalanceo son papel hasta que las anotes."
    )
    _registrar_operacion(plegado=False)

# ── Noticias ─────────────────────────────────────────────────────────────────
#
# **No se descarga nada al abrir.** `resumen.resumir` lee la cache por defecto
# con `traer.cacheado`, que no toca la red: con doce activos, descargar al abrir
# serian veinticuatro llamadas y un fallo de red dejaria esta cartera arrancando
# con errores encima de las cifras. Lo que trae la red lo pide el boton, cuando
# el usuario lo pide.
#
# El escapado y la forma de pintar un hecho salen de `noticias/texto.py`, los
# mismos que usa `vistas/noticias.py`. No se reescriben aqui: un titular
# financiero va lleno de dolares y Streamlit lee `$...$` como LaTeX.
with noticias:
    # Un problema de descarga se guarda en la sesion porque el boton termina en
    # `st.rerun()` y la pasada que lo vio no llega a pintar nada. Se saca con
    # `pop` para que se enseñe una vez y no se quede pegado a la pantalla
    # afirmando un fallo que ya no esta pasando.
    for _fuente, _problema in st.session_state.pop("noticias_problemas", {}).items():
        st.warning(f"**{_fuente}** — {_problema}")

    resumen_noticias = resumen.resumir(tickers)

    # [2, 1] y no [3, 1]: a un cuarto de ancho la etiqueta del boton se partia
    # a mitad de palabra --«Actualiza / r noticias»-- en cuanto la ventana
    # bajaba de 1024px con la barra lateral abierta. Un corte a mitad de palabra
    # se lee como un fallo de la pantalla, no como un boton.
    izq_n, der_n = st.columns([2, 1], vertical_alignment="center")
    izq_n.caption(
        "Los 8-K que la SEC obliga a presentar, y detrás unos titulares. Aquí "
        "no se recomienda nada."
    )
    if der_n.button(
        "Actualizar noticias",
        icon=":material/refresh:",
        use_container_width=True,
        help="Pide a la SEC y a Yahoo lo que falte o haya caducado. Lo que ya "
             "esté fresco no se vuelve a pedir.",
    ):
        # `forzar=False`: `traer.traer` devuelve la cache sin tocar la red
        # cuando esta vigente, asi que este bucle baja **solo lo que falta**.
        # Forzar aqui volveria a pedir veinticuatro veces algo que ya se tiene.
        problemas: dict = {}
        for numero, ticker_n in enumerate(tickers, start=1):
            with st.spinner(
                f"Trayendo {ticker_n} ({numero} de {len(tickers)})..."
            ):
                for fuente_n in resumen.FUENTES:
                    _, problema, _, _ = traer.traer(
                        fuente_n, ticker_n, traer.DESCARGA[fuente_n], False
                    )
                    if problema:
                        # Agrupado por mensaje y no por ticker: la falta de
                        # EDGAR_IDENTITY da el mismo texto para los doce, y doce
                        # avisos identicos tapan la pantalla sin decir nada que
                        # uno no dijera ya. Es la regla de `vistas/noticias.py`.
                        problemas[fuente_n] = problema
        st.session_state["noticias_problemas"] = problemas
        st.rerun()

    if resumen_noticias.estado == resumen.SIN_CACHE:
        # **Este mensaje no es el de «sin hechos recientes»**, y la diferencia
        # es todo lo que hay aqui: aquel afirma que se miro y no habia nada;
        # este dice que no se ha mirado. Se pintan igual de vacios y significan
        # cosas opuestas. Ver `noticias/resumen.py`.
        st.info(
            "**No hay noticias descargadas todavía.** Este panel no descarga "
            "al abrirse —con "
            f"{len(tickers)} activos serían {len(tickers) * len(resumen.FUENTES)} "
            "llamadas, y abrir tu cartera no puede depender de que la red "
            "responda—. Pulsa **Actualizar noticias** para pedirlas."
        )
    else:
        procedencia = (
            "Lo más antiguo que estás viendo se descargó el "
            f"{resumen_noticias.cuando.astimezone():%d/%m/%Y a las %H:%M} "
            f"({texto.hace(resumen_noticias.cuando)})."
        )
        # Cuando han caducado TODOS se dice «todo» y no la lista de los doce.
        # Nombrarlos uno a uno sirve para saber cuáles de los que ves son
        # viejos; si lo son todos, la lista no separa nada y sólo tapa la fecha
        # que va justo delante, que es el dato.
        if resumen_noticias.caducados:
            procedencia += (
                " **Todo esto ya pasó su ventana de frescura**"
                if len(resumen_noticias.caducados) == len(tickers)
                else f" Lo de {', '.join(resumen_noticias.caducados)} ya pasó "
                     "su ventana de frescura"
            ) + ": es lo que había guardado, no lo de ahora mismo."
        # Aqui NO se contempla el caso de que falten todos: si a ninguno le
        # queda nada en cache, `resumir` devuelve `SIN_CACHE` y esta rama no se
        # ejecuta. Escribirlo igualmente seria codigo que afirma algo que no
        # puede pasar, y el dia que alguien lo leyera se creeria que si.
        #
        # Y la frase no lleva plural: con un solo activo, «de esos» chirria.
        if resumen_noticias.sin_cachear:
            procedencia += (
                f" De {', '.join(resumen_noticias.sin_cachear)} no hay nada "
                "descargado: nada de lo de abajo viene de ahí."
            )
        st.caption(procedencia)

        # --- Los hechos, primero -------------------------------------------
        #
        # Van arriba porque son la unica parte donde el programa tiene un
        # criterio congelado y defendible (`noticias/criterio.py`): un 8-K es un
        # documento firmado ante la SEC con consecuencias legales si miente. Un
        # titular es lo que alguien decidio escribir. Ordenarlos juntos borraria
        # esa diferencia justo donde mas cara sale.
        st.markdown("##### Hechos (8-K)")
        if resumen_noticias.hechos:
            for hecho in resumen_noticias.hechos[:resumen.TOPE_HECHOS]:
                st.markdown(texto.linea_de_hecho(hecho))
            sobran = len(resumen_noticias.hechos) - resumen.TOPE_HECHOS
            if sobran > 0:
                # No dice «están enteros en Noticias», porque no es verdad:
                # aquella pantalla tambien recorta a cuarenta (`TOPE`) y con
                # los doce activos marcados deja fuera casi noventa. Mandar
                # alli prometiendo la lista completa seria mandar a un sitio
                # donde tampoco esta, y encima sin decir que hay que filtrar.
                st.caption(
                    f"Y {sobran} más, más antiguos. En **Noticias** caben "
                    "cuarenta: filtra por activo allí para llegar al resto."
                )
        else:
            st.caption(
                "**Sin hechos recientes.** Se preguntó a la SEC y ninguno de "
                "estos activos ha presentado un 8-K material en la ventana "
                "consultada, que fuera de la temporada de resultados es lo "
                "normal. No es lo mismo que no haberlo mirado: arriba está "
                "cuándo se miró."
            )

        # --- Y detras la prensa, corta --------------------------------------
        st.markdown("##### Titulares")
        if resumen_noticias.titulares:
            for noticia in resumen_noticias.titulares[:resumen.TOPE_TITULARES]:
                st.markdown(
                    f"**{texto.plano(noticia.ticker)}** — "
                    + texto.enlace(texto.plano(noticia.titular), noticia.url)
                    + f"  \n{texto.plano(noticia.medio)} · "
                    f"{noticia.cuando.astimezone():%d/%m/%Y %H:%M}"
                )
            sobran = len(resumen_noticias.titulares) - resumen.TOPE_TITULARES
            if sobran > 0:
                st.caption(
                    f"Y {sobran} titulares más. En **Noticias** van con su "
                    "medio y su formato, también de cuarenta en cuarenta."
                )
        else:
            st.caption(
                "Ningún titular guardado de estos activos. Aquí no se filtra "
                "nada: si no hay, es que la fuente no devolvió ninguno."
            )

    st.divider()

    # --- La interpretación -------------------------------------------------
    #
    # **Se pinta desde el archivo, nunca desde la `Lectura` recién hecha.** Un
    # solo camino, y así la fecha de cada juicio vive donde pertenece --en la
    # sesión-- en vez de tener que viajar dentro de cada `Juicio` y que dos
    # sitios distintos sepan componerla.
    #
    # La excepción es el archivo ilegible: ahí no se puede ni leer ni guardar,
    # así que se pinta la lectura directamente con el aviso. Existe para que un
    # fichero roto no se lleve por delante la llamada que se acaba de pagar.
    #
    # Sin `st.divider()` propio: el de mas arriba ya cerraba Titulares, y dos
    # seguidos se ven como una raya doble sin nada en medio.
    st.markdown("**Qué significan estos hechos para tu cartera**")

    _ruta_archivo = archivo.ruta_de(elegida.ruta)
    try:
        _guardado = archivo.cargar(_ruta_archivo)
        _roto = ""
    except archivo.ArchivoIlegible as _error:
        _guardado = archivo.Archivo()
        _roto = str(_error)

    if _roto:
        st.error(
            f"{_roto}\n\nEl fichero **no se ha tocado**: sigue ahí por si "
            "quieres recuperarlo a mano. Se puede interpretar igual, pero lo "
            "que salga no se va a poder guardar."
        )

    _a_leer = resumen_noticias.hechos[:resumen.TOPE_HECHOS]
    _leidas = archivo.urls_leidas(_guardado)
    _nuevos = [h for h in _a_leer if h.url not in _leidas]

    if not _a_leer:
        st.caption(
            "No hay hechos materiales que interpretar. No es que no se haya "
            "mirado: se miró y no había ninguno."
        )
    elif not interprete_cliente.hay_clave():
        st.info(
            "Falta la clave de Anthropic. Se pone en **Aprobación**, y hasta "
            "entonces todo lo demás del panel funciona igual."
        )
    else:
        _etiqueta = (
            f"Interpretar estos hechos ({len(_nuevos)} nuevos)"
            if _nuevos else "Volver a interpretar (ninguno nuevo)"
        )
        st.caption(
            f"Leer {len(_nuevos) or len(_a_leer)} documentos cuesta unos "
            f"**{panel_ia.coste_estimado(len(_nuevos) or len(_a_leer)):.2f} $** "
            "como mucho. Es una estimación: lo que costó de verdad se dice al "
            "terminar."
        )
        if st.button(_etiqueta, icon=":material/auto_awesome:"):
            with st.spinner("Bajando los documentos y leyéndolos…"):
                if _nuevos:
                    _entradas, _leidas, _sin_doc, _recortados = panel_ia.preparar(
                        _a_leer, _guardado
                    )
                else:
                    # «Volver a interpretar» con todo ya leido tiene que ser una
                    # segunda lectura de verdad, no una relectura de resumenes:
                    # con un Archivo() vacio no hay nada leido, y `preparar`
                    # baja los seis documentos de nuevo en vez de reenviar lo
                    # que el propio modelo escribio la vez anterior.
                    _entradas, _leidas, _sin_doc, _recortados = panel_ia.preparar(
                        _a_leer, archivo.Archivo()
                    )
                _pesos = tuple(
                    (l.ticker, l.peso, l.objetivo) for l in comp.lineas
                )
                _lectura = interprete_noticias.leer(
                    _entradas,
                    {l.ticker for l in comp.lineas},
                    sin_documento=_sin_doc,
                    recortados=_recortados,
                    pesos=_pesos,
                    leidos=_leidas,
                )
            if _lectura.estado == interprete_noticias.HECHA and not _roto:
                archivo.anotar_hechos(
                    _ruta_archivo,
                    interprete_cliente.MODELO,
                    interprete_noticias.VERSION_PROMPT,
                    panel_ia.anotadas(_lectura, _a_leer),
                    _lectura.en_conjunto,
                )
                st.session_state["ia_avisos"] = panel_ia.avisos(_lectura)
                st.rerun()
            else:
                # No se guarda y no se rerun: si se fue por `FALLO` o el archivo
                # está roto, el `st.rerun()` se llevaría por delante el único
                # sitio donde se puede decir qué pasó.
                for _clase, _texto in panel_ia.avisos(_lectura):
                    getattr(st, _clase)(_texto)
                panel_ia.pintar_lectura(st, _lectura)

    for _clase, _texto in st.session_state.pop("ia_avisos", []):
        getattr(st, _clase)(_texto)

    panel_ia.pintar_archivo(st, _guardado, _a_leer, _leidas)

    st.caption(
        "Esto es un resumen. El calendario de resultados y dividendos, los "
        "expedientes de trámite y el resto de la prensa están en la pantalla "
        "de **Noticias**."
    )
    if st.button("Ver todas las noticias", icon=":material/newspaper:"):
        st.switch_page("vistas/noticias.py")
