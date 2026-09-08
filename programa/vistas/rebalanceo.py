"""Qué hacer con la cartera: la deriva, el reparto y lo que costaría.

Pantalla aparte de «Seguimiento» a propósito. Aquella muestra **hechos** —lo que
se compró y cuánto vale— y esta muestra **propuestas**. Mezclarlas haría más
fácil leer una sugerencia como si fuera un dato registrado, que es la confusión
que este proyecto evita en todas partes.
"""

from datetime import date

import pandas as pd
import streamlit as st

import medidores
import tema
from rebalanceo import criterio, propuesta as prop
from seguimiento import libro as mod, posiciones, precios, rendimiento

# Lo que se supone que cuesta una operación cuando el libro todavía no tiene
# ninguna registrada. Sale del escenario "base" de `research/costs.py` aplicado
# a una operación típica de mil dólares, y se muestra siempre como supuesto.
COSTE_SUPUESTO = 1.0


def _medidores(deriva) -> str:
    """Una fila por activo, con su barra y su veredicto escrito.

    El veredicto va en palabras además de en color, como en `medidores.py`,
    porque un medidor que sólo cambia de tono no le dice nada a quien no
    distingue el verde del rojo ni a quien mira la página en blanco y negro.

    La escala es propia: va de −10 a +10 puntos de desviación. No lleva marcada
    la banda en el eje porque el criterio real combina un tramo absoluto con
    uno relativo al objetivo de cada activo (`rebalanceo.criterio.fuera_de_banda`):
    una sola marca fija en el eje describiría bien el activo con más peso y mal
    el que tiene menos. El veredicto de `fuera_de_banda` ya calculó las dos
    bandas, y por eso va en el color y en la palabra, no en el eje.
    """
    tope = 0.10
    filas = []
    for linea in deriva.lineas:
        pct = max(-tope, min(tope, linea.desviacion))
        posicion = (pct + tope) / (2 * tope) * 100
        if not linea.fuera_de_banda:
            color, veredicto = tema.VERDE, "En banda"
        elif linea.desviacion > 0:
            color, veredicto = tema.AMBAR, "Sobreponderado"
        else:
            color, veredicto = tema.AMBAR, "Infraponderado"
        filas.append(
            f'<div class="mpp-fila">'
            f'<span class="mpp-nombre">{linea.ticker}</span>'
            f'<span class="mpp-valor">{linea.peso_real:.1%} '
            f'<span class="mpp-nota">de {linea.peso_objetivo:.1%}</span></span>'
            f'<span class="mpp-pista"><i class="mpp-tope" '
            f'style="left:{posicion:.1f}%;background:{color}"></i></span>'
            f'<span class="mpp-vered" style="color:{color}">{veredicto}</span>'
            f'<span class="mpp-z">{linea.desviacion:+.1%}</span>'
            "</div>"
        )
    return "".join(filas)


st.markdown(
    tema.cabecera(
        "Rebalanceo",
        "Cuánto se ha separado tu cartera del objetivo, dónde poner el dinero "
        "nuevo, y qué costaría corregir el resto. Aquí no se registra nada: "
        "esto son propuestas, y lo que ejecutes lo anotas en Seguimiento.",
    ),
    unsafe_allow_html=True,
)

todas = mod.listar()
# **Un fichero ilegible se nombra.** Filtrarlo en silencio y decir despues que
# no llevas ningun libro convierte «no puedo leer el tuyo» en «no tienes
# ninguno»: son cosas opuestas, y la segunda deja al usuario sin nada que
# buscar. Es la misma regla que `vistas/seguimiento.py` ya aplicaba, y que
# `seguimiento/libro.py` explica: una cache se regenera, un libro no.
for _entrada in todas:
    if _entrada.libro is None:
        st.error(f"`{_entrada.ruta.name}` no se puede leer: {_entrada.error}")

entradas = [e for e in todas if e.libro is not None]
if not entradas:
    st.info("Todavía no llevas ningún libro. Empieza uno desde **Seguimiento**.")
    if st.button("Ir a seguimiento", icon=":material/monitoring:"):
        st.switch_page("vistas/seguimiento.py")
    st.stop()

etiquetas = {f"{e.libro.nombre} · {e.ruta.name}": e for e in entradas}
elegida = etiquetas[st.selectbox("Libro", options=list(etiquetas))]
actual = elegida.libro

# --- Sin objetivo no hay deriva que medir -----------------------------------

pesos = mod.pesos_objetivo(actual.objetivo)
if not pesos:
    st.info(
        "Este libro no tiene pesos objetivo, así que no hay contra qué medir la "
        "deriva. Puedes asignarle **repartir por igual** sobre los activos que "
        "ya tiene, o pasar por el optimizador y guardar un portafolio nuevo."
    )
    if st.button("Ir al optimizador", icon=":material/insights:"):
        st.switch_page("vistas/optimizador.py")
    st.stop()

st.caption(
    f"Objetivo vigente del **{actual.objetivo.fecha}** "
    f"({(date.today() - date.fromisoformat(actual.objetivo.fecha)).days} días). "
    f"Banda: {criterio.BANDA_ABSOLUTA:.0%} absoluto o "
    f"{criterio.BANDA_RELATIVA:.0%} relativo, lo que ocurra primero."
)

# --- Precios y estado --------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
tickers = sorted(set(pesos) | {a.ticker for a in vivos if a.ticker})
desde = min((a.fecha for a in vivos), default=date.today().isoformat())


@st.cache_data(ttl=3600, show_spinner="Descargando precios...")
def _historia(tickers: tuple[str, ...], desde: str):
    return precios.descargar(list(tickers), desde=desde)


historia = _historia(tuple(tickers), desde)
ultimos = {t: precios.ultimo(historia, t)[0] for t in historia.cierres.columns}
lineas = rendimiento.por_activo(actual.asientos, {t: p for t, p in ultimos.items() if p})
valores = {t: l.valor for t, l in lineas.items()}
efectivo = posiciones.estado(actual.asientos).efectivo

plan = prop.construir(valores, pesos, efectivo, actual.asientos, COSTE_SUPUESTO)

if plan.deriva.sin_precio:
    st.warning(
        "Sin precio para: " + ", ".join(plan.deriva.sin_precio) + ". **El "
        "reparto y la deriva se calculan sin esas posiciones**, así que los "
        "pesos de abajo son sobre un total incompleto."
    )
if plan.deriva.pesos_normalizados:
    st.caption(
        "Los pesos objetivo no sumaban 100% y se han normalizado. Pasa cuando "
        "el objetivo se fijó sobre activos que hoy no traen precios."
    )

# --- El veredicto ------------------------------------------------------------

fuera = [l for l in plan.deriva.lineas if l.fuera_de_banda]
if not fuera:
    st.success(
        "**Dentro de banda.** Ningún activo se ha separado lo suficiente de su "
        "objetivo como para que operar compense."
    )
elif plan.basta_con_la_aportacion:
    st.info(
        f"**{len(fuera)} activo(s) fuera de banda, y tu efectivo basta para "
        "corregirlo.** No hace falta vender nada."
    )
else:
    st.warning(
        f"**{len(fuera)} activo(s) fuera de banda.** El efectivo disponible no "
        "llega para corregirlo sólo con compras."
    )

# --- Los medidores -----------------------------------------------------------

# La hoja de estilo de los medidores, una sola vez por pasada y aqui y no
# arriba del todo: los caminos que terminan en `st.stop()` mas arriba (sin
# libro, sin objetivo) no llegan a pintar ninguno.
st.markdown(medidores.CSS, unsafe_allow_html=True)
st.subheader("Deriva por activo")
st.markdown(_medidores(plan.deriva), unsafe_allow_html=True)

# --- Qué hacer ---------------------------------------------------------------

if plan.con_efectivo:
    st.subheader(f"Con tu efectivo ({efectivo:,.2f} {actual.moneda})")
    st.caption(
        "Comprar con dinero nuevo corrige deriva **sin vender nada**: no paga "
        "coste de venta y no realiza ninguna plusvalía. Por eso va primero."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Comprar": f"{o.importe:,.2f}"}
            for o in plan.con_efectivo
        ]),
        use_container_width=True, hide_index=True,
    )
elif efectivo > 0:
    st.subheader(f"Con tu efectivo ({efectivo:,.2f} {actual.moneda})")
    st.info(
        "La aportación es demasiado pequeña para que compense invertirla ahora: "
        f"con un coste de {plan.coste_por_operacion:,.2f} por operación, "
        "cualquier reparto se comería más del "
        f"{criterio.COSTE_MAXIMO:.0%} de lo comprado."
    )

if plan.y_ademas:
    st.subheader("Y además haría falta")
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Acción": o.accion.capitalize(),
             "Importe": f"{abs(o.importe):,.2f}", "Coste": f"{o.coste:,.2f}"}
            for o in plan.y_ademas
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        "Se mueve el plan entero, no sólo lo que rompió la banda: así lo que "
        "sale de unas entra en otras y el conjunto suma cero. Si alguna quedó "
        "descartada por coste, la diferencia se queda como efectivo."
    )

if plan.descartadas_por_coste:
    st.subheader("Descartadas porque el coste se las come")
    st.caption(
        "Están fuera de banda, pero mover ese importe cuesta más del "
        f"{criterio.COSTE_MAXIMO:.0%}. Se enseñan igualmente: una propuesta "
        "omitida en silencio es indistinguible de una que nadie calculó."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Acción": o.accion.capitalize(),
             "Importe": f"{abs(o.importe):,.2f}", "Coste": f"{o.coste:,.2f}"}
            for o in plan.descartadas_por_coste
        ]),
        use_container_width=True, hide_index=True,
    )

if plan.deriva.fuera_del_objetivo:
    st.subheader("Fuera del objetivo")
    st.caption(
        "Los tienes pero no están en el plan. **No se propone nada** con ellos: "
        "puede ser que el objetivo esté desactualizado o que la posición sobre, "
        "y el programa no puede distinguir las dos cosas."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": l.ticker, "Valor": f"{l.valor:,.2f}",
             "Peso": f"{l.peso_real:.2%}"}
            for l in plan.deriva.fuera_del_objetivo
        ]),
        use_container_width=True, hide_index=True,
    )

# --- El coste ----------------------------------------------------------------

st.caption(
    f"Coste estimado: **{plan.coste_por_operacion:,.2f} por operación**, "
    + ("mediana de las comisiones que registraste en este libro."
       if plan.coste_del_libro else
       "un supuesto — este libro todavía no tiene ninguna operación registrada.")
    + f" Total de la propuesta: **{plan.coste_total:,.2f}**. No incluye la "
    "horquilla de compraventa, que no está registrada en ninguna parte."
)
