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
from interprete import ajuste, archivo
from interprete import cliente as interprete_cliente
from noticias import texto
from rebalanceo import criterio, propuesta as prop
from seguimiento import libro as mod, posiciones, precios, rendimiento
from vistas import libros

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


def _titulo_del_dinero(efectivo: float, nuevo: float, moneda: str) -> str:
    """El encabezado nombra las dos mitades cuando hay dos.

    Un total solo escondería el único riesgo que esta pantalla añade:
    quien ya ingresó su aportación del mes la tiene registrada como
    efectivo, y si además la escribe arriba se la reparte dos veces.
    Con las dos cifras a la vista ese error se ve; con la suma sola, no.
    """
    if nuevo <= 0:
        return f"Con tu efectivo ({efectivo:,.2f} {moneda})"
    if efectivo <= 0:
        return f"Con tu aportación ({nuevo:,.2f} {moneda})"
    return (
        f"Con {efectivo + nuevo:,.2f} {moneda} — {efectivo:,.2f} "
        f"registrados y {nuevo:,.2f} que vas a aportar"
    )


st.markdown(
    tema.cabecera(
        "Rebalanceo",
        "Cuánto se ha separado tu cartera del objetivo, dónde poner el dinero "
        "nuevo, y qué costaría corregir el resto. Aquí no se registra nada: "
        "esto son propuestas, y lo que ejecutes lo anotas en Seguimiento.",
    ),
    unsafe_allow_html=True,
)

# Listar, nombrar los ilegibles y elegir uno es el mismo trabajo en las tres
# pantallas que tienen libro. Vive en `vistas/libros.py`, que es tambien donde
# esta escrito por que el desplegable lleva `key`: sin ella la eleccion no
# sobrevivia al salto de una pantalla a otra.
_en_disco, etiquetas = libros.disponibles()
if not etiquetas:
    st.info(
        "Todavía no llevas ningún libro. Empiézalo en **Empezar un libro**."
    )
    if st.button("Ir a seguimiento", icon=":material/monitoring:"):
        st.switch_page("vistas/seguimiento.py")
    st.stop()

elegida = libros.desplegable(etiquetas)
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
# Con la `Historia`, y no sin ella: **toda la deriva de esta pantalla sale de
# aqui**. Sin los splits, las acciones de un activo que hubiera partido salian
# a la mitad, su peso real tambien, y la propuesta mandaba comprar mas de algo
# que ya estaba donde tenia que estar. Y sin los dividendos, el efectivo a
# repartir salia corto.
lineas = rendimiento.por_activo(
    actual.asientos, {t: p for t, p in ultimos.items() if p}, historia
)
valores = {t: l.valor for t, l in lineas.items()}
efectivo = posiciones.estado(actual.asientos, historia=historia).efectivo

# --- Lo que hay y lo que vas a poner -----------------------------------------

# Dos cifras separadas a proposito. `efectivo` es un **hecho**: sale de los
# asientos del libro. `nuevo` es un **plan**: dinero que el usuario dice que va
# a aportar y que todavia no ha entrado en ninguna parte. Repartir la suma esta
# bien —esta pantalla propone y no escribe nunca— pero enseñarlas como un solo
# numero no lo estaria: quien ya ingreso su aportacion la tiene contada como
# efectivo, y la veria dos veces sin nada que se lo advierta.
#
# La `key` lleva el nombre del fichero porque Streamlit **ignora `value=` en
# cuanto esa key existe en `session_state`**. Con una key fija, cambiar de libro
# en el selector dejaria en pantalla la cifra del libro anterior: un numero
# plausible que pertenece a otra cartera.
previsto = mod.importe_previsto(actual.aportacion_prevista)
nuevo = st.number_input(
    "Dinero nuevo que vas a aportar",
    min_value=0.0,
    value=previsto,
    step=100.0,
    key=f"aportacion_nueva_{elegida.ruta.name}",
    help="Se reparte junto con el efectivo que ya tiene el libro. Aquí no se "
         "registra nada: cuando lo ingreses de verdad, anótalo en Seguimiento.",
)
if actual.aportacion_prevista is not None:
    st.caption(
        f"Precargado con tu plan: {previsto:,.2f} {actual.moneda} "
        f"{actual.aportacion_prevista.cadencia}. **Si ya lo ingresaste**, está "
        "contado abajo como efectivo — ponlo a cero para no repartirlo dos veces."
    )

titulo_dinero = _titulo_del_dinero(efectivo, nuevo, actual.moneda)
plan = prop.construir(
    valores, pesos, efectivo + nuevo, actual.asientos, COSTE_SUPUESTO
)

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
    _quien = "el dinero que vas a repartir" if nuevo else "tu efectivo"
    st.info(
        f"**{len(fuera)} activo(s) fuera de banda, y {_quien} basta para "
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
    st.subheader(titulo_dinero)
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
elif efectivo + nuevo > 0:
    st.subheader(titulo_dinero)
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

# --- Lo que la aritmética no ve ---------------------------------------------
#
# Va antes de la puerta a Seguimiento a propósito: es lo último que se lee sobre
# la propuesta, y después de leerlo es cuando tiene sentido ir a ejecutarla.
st.divider()
st.markdown("**Lo que la aritmética no ve**")

_todas = plan.con_efectivo + plan.y_ademas
_ops = tuple(
    # `abs`: el importe de una venta es negativo, y sin esto toda venta llegaba
    # al modelo como «vender MSFT, -30,0% de la cartera». Las tablas de arriba
    # ya usaban `abs(o.importe)` por lo mismo; esta linea no lo copio.
    (op.ticker, op.accion,
     (abs(op.importe) / plan.deriva.en_plan) if plan.deriva.en_plan > 0 else 0.0,
     op.viable)
    for op in _todas
)
_pesos_ia = tuple(
    (d.ticker, d.peso_real, d.peso_objetivo) for d in plan.deriva.lineas
)
_ruta_ia = archivo.ruta_de(elegida.ruta)
try:
    _guardado_ia = archivo.cargar(_ruta_ia)
    _roto_ia = ""
except archivo.ArchivoIlegible as _error_ia:
    _guardado_ia = archivo.Archivo()
    _roto_ia = str(_error_ia)

if _roto_ia:
    st.error(
        f"{_roto_ia}\n\nEl fichero **no se ha tocado**. Se puede comentar "
        "igual, pero lo que salga no se va a poder guardar."
    )

for _clase, _texto in st.session_state.pop("ajuste_avisos", []):
    getattr(st, _clase)(_texto)

if not _ops:
    st.caption("No hay ninguna operación que comentar: la propuesta está vacía.")
elif not interprete_cliente.hay_clave():
    st.info(
        "Falta la clave de Anthropic. Se pone en **Aprobación**, y la propuesta "
        "de arriba funciona igual sin ella."
    )
else:
    st.caption(
        "Comentar la propuesta cuesta menos de **0,01 $**: aquí no se manda "
        "ningún documento, sólo los pesos y las operaciones. Lo que costó de "
        "verdad se dice al terminar."
    )
    if st.button("¿Qué se le escapa a la aritmética?", icon=":material/auto_awesome:"):
        with st.spinner("Mirando la propuesta…"):
            _com = ajuste.comentar(_ops, _pesos_ia)
        if _com.estado == ajuste.HECHO and not _roto_ia:
            _guardado_aj = True
            try:
                archivo.anotar_rebalanceo(
                    _ruta_ia,
                    interprete_cliente.MODELO,
                    ajuste.VERSION_PROMPT,
                    archivo.Foto(
                        pesos_reales=tuple((d.ticker, d.peso_real) for d in plan.deriva.lineas),
                        pesos_objetivo=tuple((d.ticker, d.peso_objetivo) for d in plan.deriva.lineas),
                        operaciones=tuple((t, a, p) for t, a, p, _v in _ops),
                    ),
                    _com.observaciones,
                    _com.en_conjunto,
                )
            except OSError as _fallo_io:
                # Un disco lleno o el antivirus llegaban aqui como traceback, y
                # `showErrorDetails` viene encendido por defecto: lo que el
                # usuario leia era una pila de Python encima de un comentario
                # que ya habia pagado. El archivo anterior no se toca --se
                # escribe en un temporal y se hace `replace`-- asi que se puede
                # afirmar que sigue entero. Es el patron de
                # `vistas/optimizador.py`.
                st.error(
                    f"**No se pudo guardar el comentario: {_fallo_io}**\n\n"
                    "El archivo anterior sigue intacto, pero esto **no ha "
                    "quedado guardado** y volver a pedirlo se cobra otra vez. "
                    "Aquí abajo está entero."
                )
                for _sobre_io, _dice_io in _com.observaciones:
                    st.markdown(
                        f"- **{texto.plano(_sobre_io)}** — {texto.plano(_dice_io)}"
                    )
                if _com.en_conjunto:
                    st.markdown(texto.plano(_com.en_conjunto))
                # Y no `st.stop()`: lo que queda debajo es el historial de
                # comentarios y el boton «Anotar lo que ejecute», que es
                # justamente la puerta que esta pantalla existe para abrir.
                # Cortar aqui castigaria al usuario dos veces por un fallo
                # de disco. Misma forma que la rama de `FALLO` de abajo.
                _guardado_aj = False
            if _guardado_aj:
                _avisos_aj = [("success", "Comentado y guardado.")]
                if not _com.observaciones and not _com.en_conjunto:
                    _avisos_aj = [(
                        "warning",
                        "Se miró la propuesta y **no salió nada que decir**. No es un "
                        "fallo: la llamada fue bien y no había nada que añadir a la "
                        "aritmética.",
                    )]
                if _com.descartadas:
                    _avisos_aj.append((
                        "warning",
                        f"Se descartaron {_com.descartadas} observaciones que nombraban "
                        "una operación que no estaba en la propuesta.",
                    ))
                if _com.conjunto_descartado:
                    _avisos_aj.append((
                        "warning",
                        "Se descartó el párrafo de conjunto: nombraba algo en mayúsculas "
                        "que no está en tu cartera, o llevaba una cifra.",
                    ))
                if _com.entrada_tokens or _com.salida_tokens:
                    _coste_aj = interprete_cliente.coste(_com.entrada_tokens, _com.salida_tokens)
                    _avisos_aj.append((
                        "info",
                        f"Este comentario costó **{_coste_aj:.3f} $** "
                        f"({_com.entrada_tokens:,} tokens de entrada y "
                        f"{_com.salida_tokens:,} de salida, a la tarifa de "
                        f"{interprete_cliente.MODELO}).",
                    ))
                st.session_state["ajuste_avisos"] = _avisos_aj
                st.rerun()
        else:
            for _sobre, _dice in _com.observaciones:
                st.markdown(f"**{texto.plano(_sobre)}** — {texto.plano(_dice)}")
            if _com.estado == ajuste.FALLO:
                st.error(
                    "No se pudo comentar: "
                    + (_com.problema or "la llamada no devolvió nada utilizable")
                    + ". **No se ha guardado nada.**"
                )
            if _com.entrada_tokens or _com.salida_tokens:
                _coste_aj = interprete_cliente.coste(_com.entrada_tokens, _com.salida_tokens)
                st.info(
                    f"Este comentario costó **{_coste_aj:.3f} $** "
                    f"({_com.entrada_tokens:,} tokens de entrada y "
                    f"{_com.salida_tokens:,} de salida, a la tarifa de "
                    f"{interprete_cliente.MODELO})."
                )

# Los anteriores van plegados y fechados, con su foto. **Nunca junto a la
# propuesta de hoy**: hablan de una deriva que ya no es la que tienes delante, y
# pintarlos como si aplicaran sería mezclar dos cortes temporales — el defecto
# que en F dio una GANANCIA −9.700.
if _guardado_ia.rebalanceo:
    with st.expander(f"Comentarios anteriores ({len(_guardado_ia.rebalanceo)})"):
        st.caption(
            "Cada uno habla de la deriva que había **ese día**, no de la de "
            "ahora. Por eso viene con la foto de lo que comentaba."
        )
        for _com_v in reversed(_guardado_ia.rebalanceo):
            st.markdown(f"**{_com_v.cuando:%d/%m/%Y a las %H:%M}**")
            for _sobre, _dice in _com_v.observaciones:
                st.markdown(f"- **{texto.plano(_sobre)}** — {texto.plano(_dice)}")
            if _com_v.en_conjunto:
                st.markdown(texto.plano(_com_v.en_conjunto))
            st.caption(
                "Pesos de entonces: "
                + ", ".join(f"{t} {p:.1%}" for t, p in _com_v.foto.pesos_reales)
                + (" · objetivo: " + ", ".join(
                    f"{t} {p:.1%}" for t, p in _com_v.foto.pesos_objetivo)
                   if _com_v.foto.pesos_objetivo else "")
                + (" · operaciones: " + ", ".join(
                    f"{a} {t}" for t, a, _p in _com_v.foto.operaciones)
                   if _com_v.foto.operaciones else "")
            )
            st.divider()

# --- Y la puerta a donde esto se convierte en un hecho -----------------------
#
# La cabecera lleva desde siempre «lo que ejecutes lo anotas en Seguimiento», y
# hasta aqui esa frase era una instruccion sin puerta: habia que ir al menu,
# entrar en Seguimiento y encontrar el formulario. Es el mismo defecto que J
# arreglo en los otros dos saltos del recorrido --decir adonde ir en vez de
# llevar-- y este se habia quedado sin arreglar.
#
# `st.switch_page` y no un aviso: conserva `st.session_state`, y ahi es donde
# viaja el libro elegido.
#
# **Esa segunda frase fue falsa hasta que el desplegable tuvo `key`.** Los tres
# de esta app se pintaban sin ella, asi que en `session_state` no habia ninguna
# entrada con el libro: `switch_page` conservaba fielmente una sesion que no lo
# contenia, y Seguimiento aterrizaba en el primero de su lista con el
# formulario de registrar abierto debajo. Reproducido: elegir `CORE-SATELLIT`
# aqui y llegar alli con `prueba` puesto. Y el libro es append-only, asi que un
# asiento en la cartera equivocada solo se deshace con una anulacion que queda
# en el historial para siempre. La clave compartida y su preseleccion tolerante
# viven en `vistas/libros.py` y `seguimiento/libro.py`.
st.divider()
izq, der = st.columns([3, 2])
izq.markdown(
    "**¿Ya ejecutaste algo de esto?** Nada de lo de arriba está registrado: "
    "son propuestas hasta que las anotes."
)
if der.button("Anotar lo que ejecuté", icon=":material/edit_note:",
              use_container_width=True):
    # Y se deja dicho a que pestana, porque `switch_page` aterriza en la
    # primera y el formulario esta tres mas alla. Llevar a la pantalla y
    # dejar al usuario buscando es el mismo defecto a medias.
    st.session_state["seguimiento_pestana"] = "Registrar"
    st.switch_page("vistas/seguimiento.py")
