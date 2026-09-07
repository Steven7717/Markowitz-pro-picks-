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

entradas = mod.listar()

pendiente = st.session_state.get("portafolio_a_seguir")
if pendiente is not None:
    st.markdown(f"### Empezar a seguir «{pendiente.nombre}»")
    v = mod.veredicto_de(pendiente.metricas or {})
    if v["beats_equal_weight"] is True:
        st.success(
            f"Fuera de muestra, la optimización superó a repartir por igual: "
            f"{v['oos_sharpe']:.2f} frente a {v['oos_equal_weight_sharpe']:.2f}."
        )
    elif v["beats_equal_weight"] is False:
        st.warning(
            f"Fuera de muestra, la optimización quedó **por debajo** de repartir "
            f"por igual: {v['oos_sharpe']:.2f} frente a "
            f"{v['oos_equal_weight_sharpe']:.2f}."
        )
    else:
        st.info(
            "Con estos datos no se pudo distinguir la optimización de repartir "
            "por igual. La diferencia cabía dentro del error de medición."
        )

    # Sin indice por defecto: el veredicto de arriba es la unica evidencia que
    # el programa produjo sobre si la optimizacion aportaba algo, y un valor
    # preseleccionado la convertiria en un clic que nadie mira.
    base = st.radio(
        "¿Contra qué pesos quieres medir la deriva?",
        options=["estrategia", "equal_weight"],
        format_func=lambda b: (
            "Los pesos de la estrategia" if b == "estrategia"
            else "Repartir por igual (1/N)"
        ),
        index=None,
    )
    nombre = st.text_input("Nombre del libro", value=pendiente.nombre, max_chars=60)
    if st.button("Crear libro", type="primary", disabled=base is None):
        ruta = mod.guardar(mod.desde_portafolio(nombre, pendiente, base=base))
        st.session_state.pop("portafolio_a_seguir")
        st.success(f"Creado en {ruta}.")
        st.rerun()
    st.stop()

if not entradas:
    st.info(
        "Todavía no llevas ningún libro. Empieza uno desde **Portafolios "
        "guardados**, o crea uno a mano si ya tenías acciones compradas."
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

# --- Precios ----------------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
if not vivos:
    st.info("Este libro todavía no tiene ningún asiento. Añade el primero abajo.")
    st.stop()

tickers = sorted({a.ticker for a in vivos if a.ticker})
desde = min(a.fecha for a in vivos)


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

fechas = [f for _, f in ultimos.values() if f]
if fechas and max(fechas) < date.today().isoformat():
    st.caption(
        f"Último cierre disponible: **{max(fechas)}**. Todo lo de abajo está "
        "valorado a esa fecha, no a hoy."
    )

if marcha.posteriores:
    # La tabla por activo si los ve, porque sale de los asientos; el valor de
    # cabecera no, porque sale de la serie y la serie no tiene precio con que
    # valorarlos. Sin decirlo, las dos cifras se contradicen sin explicacion.
    st.warning(
        f"{marcha.posteriores} asiento(s) con fecha posterior al último cierre "
        "disponible. Aparecen en la tabla por activo, pero todavía no en el "
        "valor ni en el gráfico: no hay precio con el que valorarlos."
    )

# --- Los numeros de cabecera -------------------------------------------------

aportado = sum(
    a.importe if a.tipo == "aportacion" else -a.importe
    for a in vivos
    if a.tipo in mod.FLUJOS_EXTERNOS
)
valor_hoy = float(marcha.valor.iloc[-1]) if len(marcha.valor) else 0.0
dias = (marcha.valor.index[-1] - marcha.valor.index[0]).days if len(marcha.valor) > 1 else 0

twr_periodo = rendimiento.twr(marcha.valor, marcha.flujos)
twr_anual = rendimiento.anualizar(twr_periodo, dias=dias)

flujos_tir = [
    (date.fromisoformat(a.fecha), a.importe if a.tipo == "retiro" else -a.importe)
    for a in vivos
    if a.tipo in mod.FLUJOS_EXTERNOS
]
if flujos_tir and len(marcha.valor):
    flujos_tir.append((marcha.valor.index[-1].date(), valor_hoy))
tasa_interna = rendimiento.tir(flujos_tir)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Valor", f"{valor_hoy:,.2f}")
k2.metric("Aportado neto", f"{aportado:,.2f}",
          help="Aportaciones menos retiros: el dinero tuyo que hay dentro ahora "
               "mismo, no la suma de todo lo que pasó por la cartera.")
k3.metric("Ganancia", f"{valor_hoy - aportado:,.2f}")
k4.metric(
    "TWR anual", cartera.formato_porcentaje(twr_anual),
    help="Ponderado por tiempo: neutraliza cuándo metiste el dinero, así que "
         "mide la cartera y no tu timing. Es el único comparable con un índice. "
         f"Sin anualizar, el periodo entero rindió {twr_periodo:.2%}.",
)
k5.metric(
    "TIR", cartera.formato_porcentaje(tasa_interna),
    help="Ponderada por dinero: lo que ganaste tú, con tu timing dentro. "
         "Aparece «—» cuando no hay una respuesta defendible.",
)
k6.metric("Dividendos", f"{float(marcha.dividendos.sum().sum()):,.2f}")

if twr_anual is not None and tasa_interna is not None:
    brecha = tasa_interna - twr_anual
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
st.download_button(
    "Descargar Excel",
    data=to_excel(
        pd.DataFrame(filas),
        {
            "Libro": actual.nombre,
            "Moneda": actual.moneda,
            "Valorado a": max(fechas) if fechas else "—",
            "Valor": valor_hoy,
            "Aportado neto": aportado,
            "Ganancia": valor_hoy - aportado,
            "TWR del periodo": twr_periodo,
            "TWR anual": twr_anual,
            "TIR": tasa_interna,
            "Dividendos": float(marcha.dividendos.sum().sum()),
            "Metodo de coste": "media ponderada",
        },
    ),
    file_name=f"seguimiento_{elegida.ruta.stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table_view:",
)
