"""El libro de posiciones: lo que se compró de verdad y cómo va."""

from datetime import date

import pandas as pd
import streamlit as st

import cartera
import tema
from exporter import to_excel
from seguimiento import comparacion, libro as mod, posiciones, precios, rendimiento

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
elegida = etiquetas[st.selectbox("Libro", options=list(etiquetas))]
actual = elegida.libro

st.caption(
    f"Moneda: **{actual.moneda}**. Coste calculado por **media ponderada**, no "
    "por lotes: cambia el reparto entre ganancia realizada y latente, nunca el "
    "total. Esto no es un cálculo fiscal."
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

def _registrar_operacion():
    """El formulario de alta. Es una funcion porque hacen falta dos llamadas.

    Un libro recien creado no tiene asientos, y la pantalla corta ahi para no
    descargar precios de nada ni calcular un rendimiento sobre cero. Pero si el
    corte se lleva por delante el formulario, ese libro es un callejon sin
    salida: dice «anade el primero» y no hay donde anadirlo. Asi que se llama
    antes de cortar, y otra vez en su sitio cuando si hay asientos.
    """
    with st.expander("Registrar una operación"):
        tipo = st.selectbox("Tipo", options=sorted(mod.TIPOS - {"anulacion"}))
        cuando = st.date_input("Fecha", value=date.today(), max_value=date.today())
        ticker = st.text_input("Ticker").strip().upper() if tipo in mod.CON_TICKER else None

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
                if len(escritos) > 1:
                    st.info(
                        f"No había efectivo suficiente, así que se registró también "
                        f"una aportación de {escritos[0].importe:,.2f} que financia "
                        "la compra."
                    )
                if estimado:
                    st.info(
                        f"Precio tomado del cierre del {cuando.isoformat()}: "
                        f"{precio:,.2f}. Queda marcado como estimado en el historial."
                    )
                st.success("Registrado.")
                st.rerun()


# --- Precios ----------------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
if not vivos:
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
    st.warning(
        "Sin precios para: " + ", ".join(historia.sin_datos) + ". No valen "
        "cero: es que no se pudieron descargar. **El valor y el gráfico de "
        "abajo no las incluyen**, así que la cifra que ves es un mínimo, no el "
        "total. Comprueba que el ticker es correcto y que la empresa sigue "
        "cotizando."
    )

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

# Sin nada valorado este pie diria que «todo lo de abajo» esta valorado a una
# fecha en la que la cartera todavia no existia, que es justo lo contrario de lo
# que pasa. El aviso de abajo da la misma fecha y la explica.
if ultimo_cierre and ultimo_cierre < date.today().isoformat() and not sin_valorar:
    st.caption(
        f"Último cierre disponible: **{ultimo_cierre}**. Todo lo de abajo está "
        "valorado a esa fecha, no a hoy."
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

# De `marcha.flujos`, no de los asientos. Los dos numeros de arriba se restan
# entre si, asi que tienen que salir del MISMO corte temporal: `valor` viene de
# la serie, que acaba en el ultimo cierre disponible, y sumar aqui los asientos
# de hoy --que la serie todavia no puede valorar-- producia una ganancia
# inventada. Medido en la app: una aportacion de 10.000 registrada hoy dejaba
# VALOR 10.299, APORTADO 20.000 y GANANCIA -9.700 sin que nadie hubiera perdido
# un dolar. `flujos` son ya las aportaciones menos los retiros dentro del
# calendario de la serie, asi que la coincidencia es por construccion.
aportado = float(marcha.flujos.sum())
if sin_valorar:
    # `flujos` vive en el calendario de la serie, y eso es DELIBERADO:
    # `aportado` y `valor` se restan para dar la ganancia, y si vinieran
    # de cortes temporales distintos daria una ganancia inventada -- en
    # el sub-proyecto F salio GANANCIA -9.700 sin que nadie hubiera
    # perdido un dolar.
    #
    # Cuando NO hay ningun dia valorado esa razon desaparece, porque
    # `ganancia` ya es «—» y no hay dos numeros que restar. Y decir
    # «Aportado neto 0,00» a quien acaba de meter su dinero no es una
    # medida que falte: es una **afirmacion falsa sobre un hecho
    # registrado**, que es peor que un «—». El dinero entro; lo que aun
    # no se puede es valorarlo.
    aportado = sum(
        a.importe if a.tipo == "aportacion" else -a.importe
        for a in vivos
        if a.tipo in mod.FLUJOS_EXTERNOS
    )
valor_hoy = float(marcha.valor.iloc[-1]) if len(marcha.valor) else 0.0
dias = (marcha.valor.index[-1] - marcha.valor.index[0]).days if len(marcha.valor) > 1 else 0

twr_periodo = rendimiento.twr(marcha.valor, marcha.flujos)
twr_anual = rendimiento.anualizar(twr_periodo, dias=dias)

# Otra vez desde `marcha.flujos`, y por lo mismo que `aportado`: el valor final
# de la serie se fecha en el ultimo cierre, asi que meter aqui un flujo
# POSTERIOR a esa fecha construye una ecuacion que mezcla dos momentos. El
# signo se invierte porque en `flujos` una aportacion es positiva y para la TIR
# el dinero que entra es una salida del bolsillo.
flujos_tir = [
    (dia.date(), -float(importe)) for dia, importe in marcha.flujos.items() if importe
]
if flujos_tir and len(marcha.valor) and not sin_valorar:
    flujos_tir.append((marcha.valor.index[-1].date(), valor_hoy))
tasa_interna = rendimiento.tir(flujos_tir)


def _cifra(valor) -> str:
    """El «—» de `cartera.formato_cifra`, con el separador de miles de aqui.

    No se llama a `formato_cifra` directamente porque escribe `10299.00` donde
    esta pantalla lleva `10,299.00` desde siempre, y cambiar el formato del caso
    normal para arreglar el caso vacio seria pagar el arreglo con una regresion.
    Lo que se copia es la regla, que es lo que importa: `None` no es cero.
    """
    return "—" if valor is None else f"{valor:,.2f}"


# Nada que valorar: las cifras que dependen del precio no existen todavia. Se
# ponen a None y salen «—»; inventarlas con el precio al que se compro daria un
# numero plausible, sin marca y sin unidades raras, que nadie distinguiria de
# uno medido de verdad.
valor_visible = None if sin_valorar else valor_hoy
ganancia_visible = None if sin_valorar else valor_hoy - aportado
twr_visible = None if sin_valorar else twr_anual
tir_visible = None if sin_valorar else tasa_interna

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Valor", _cifra(valor_visible))
k2.metric("Aportado neto", f"{aportado:,.2f}",
          help="Aportaciones menos retiros: el dinero tuyo que hay dentro ahora "
               "mismo, no la suma de todo lo que pasó por la cartera.")
k3.metric("Ganancia", _cifra(ganancia_visible))
k4.metric(
    "TWR anual", cartera.formato_porcentaje(twr_visible),
    help="Ponderado por tiempo: neutraliza cuándo metiste el dinero, así que "
         "mide la cartera y no tu timing. Es el único comparable con un índice."
         + ("" if sin_valorar else
            f" Sin anualizar, el periodo entero rindió {twr_periodo:.2%}."),
)
k5.metric(
    "TIR", cartera.formato_porcentaje(tir_visible),
    help="Ponderada por dinero: lo que ganaste tú, con tu timing dentro. "
         "Aparece «—» cuando no hay una respuesta defendible.",
)
k6.metric("Dividendos", f"{float(marcha.dividendos.sum().sum()):,.2f}")

if twr_visible is not None and tir_visible is not None:
    brecha = tir_visible - twr_visible
    if abs(brecha) > 0.02:
        st.info(
            f"**TWR y TIR se separan {abs(brecha):.1%}.** Esa diferencia es el "
            "efecto de *cuándo* aportaste, no de qué compraste: "
            + ("tus aportaciones cayeron en buenos momentos."
               if brecha > 0 else
               "tus aportaciones cayeron en momentos peores que la media.")
        )

# --- Valor en el tiempo, contra las tres referencias -------------------------

st.subheader("Valor en el tiempo")

objetivo = actual.objetivo
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

# --- Por activo --------------------------------------------------------------

st.subheader("Por activo")

pesos_obj = mod.pesos_objetivo(objetivo)
filas = []
for ticker, linea in rendimiento.por_activo(actual.asientos, precios_hoy).items():
    peso_real = (linea.valor / valor_hoy) if (linea.valor and valor_hoy) else None
    filas.append({
        "Ticker": ticker,
        "Acciones": f"{linea.acciones:,.4f}".rstrip("0").rstrip("."),
        "Coste medio": f"{linea.coste_medio:,.2f}",
        "Precio": cartera.formato_cifra(linea.precio),
        "Valor": cartera.formato_cifra(linea.valor),
        "Peso real": cartera.formato_porcentaje(peso_real),
        "Peso objetivo": cartera.formato_porcentaje(pesos_obj.get(ticker)),
        "Latente": cartera.formato_cifra(linea.latente),
        "Realizada": f"{linea.realizada:,.2f}",
        "Dividendos": f"{linea.dividendos:,.2f}",
        "Contribución": cartera.formato_cifra(linea.contribucion),
    })

st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
st.caption(
    "La contribución va en dólares y suma. Un porcentaje de contribución con "
    "aportaciones de por medio compararía cada activo contra un capital que no "
    "fue el suyo durante todo el periodo."
)

_registrar_operacion()

# --- Historial ---------------------------------------------------------------

st.subheader("Historial")

anulados = {a.anula for a in actual.asientos if a.tipo == "anulacion" and a.anula}
historial = []
for a in reversed(posiciones.ordenados(actual.asientos)):
    historial.append({
        "Fecha": a.fecha,
        "Tipo": a.tipo,
        "Ticker": a.ticker or "—",
        "Acciones": cartera.formato_cifra(a.acciones, 4),
        "Precio": cartera.formato_cifra(a.precio) + (" (est.)" if a.precio_estimado else ""),
        "Importe": f"{a.importe:,.2f}",
        "Comisión": f"{a.comision:,.2f}",
        "Estado": "Anulado" if a.id in anulados else "",
        "Nota": a.nota,
    })
st.dataframe(pd.DataFrame(historial), use_container_width=True, hide_index=True)

# --- Exportar ----------------------------------------------------------------
#
# Solo Excel. `exporter.to_pdf` pasa por `kpi_rows`, que indexa directamente
# `sharpe`, `annual_return`, `annual_vol` y `rf_rate` -- claves de una corrida
# del optimizador que un libro de seguimiento no tiene, y que reventarian con
# KeyError. `to_excel` si es generico: acepta cualquier DataFrame y cualquier
# dict. Hacer que kpi_rows tolere dos formas distintas de metricas es un cambio
# a un modulo compartido, y se hace cuando se decida, no de refilon.
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
            "Valor": valor_visible,
            "Aportado neto": aportado,
            "Ganancia": ganancia_visible,
            "TWR del periodo": None if sin_valorar else twr_periodo,
            "TWR anual": twr_visible,
            "TIR": tir_visible,
            "Dividendos": float(marcha.dividendos.sum().sum()),
            "Metodo de coste": "media ponderada",
        },
    ),
    file_name=f"seguimiento_{elegida.ruta.stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table_view:",
)
