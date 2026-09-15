"""Estrenar un libro: el programa propone la compra y el usuario la confirma.

Un libro recién creado nacía vacío, y la primera compra se registraba en un
desplegable debajo de los gráficos. Esta pantalla es ese primer paso, y sólo
ese: cuando termina, el libro ya tiene dentro lo que se compró.

**El programa propone y el usuario confirma, y esa fricción es la
característica.** Repartir 15.000 entre unos pesos no produce una compra:
produce una división. La compra real fue de otro número de acciones, a otro
precio, con comisión, porque entre mirar la propuesta y ejecutarla en el bróker
el precio se mueve. Escribir la división en el libro metería una intención
donde sólo van hechos, y una vez dentro sería indistinguible de una medida:
contaminaría el coste de adquisición, la TIR y el rendimiento, y nadie lo
notaría porque el número es plausible. Por eso lo que entra al libro sale de
una tabla editable, y no de un «sí, correcto».

Aquí no se calcula nada: el reparto y los asientos viven en `seguimiento.alta`,
que no importa Streamlit, igual que en el resto del proyecto.
"""

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import cartera
import tema
from seguimiento import alta, libro as mod, precios
from validation import veredicto_guardado

# Cinco días naturales hacia atrás, y no uno: un fin de semana o un festivo
# dejan el último cierre fuera de una ventana de un día, y entonces la
# propuesta saldría entera «sin precio» un lunes por la mañana sin que nada
# explicara por qué.
VENTANA = 5

# La fecha más antigua que acepta el calendario. `st.date_input` sin
# `min_value` sólo deja retroceder diez años, y una cartera cargada a mano
# puede tener compras más viejas que eso.
PRIMER_DIA = date(1990, 1, 1)

PUERTAS = ("comprar", "ya_compre", "manual")
NOMBRE_PUERTA = {
    "comprar": "Voy a comprar — repárteme el capital entre los pesos",
    "ya_compre": "Ya compré — anoto lo que ejecuté de verdad",
    "manual": "Ya tenía una cartera — la cargo entera",
}

OBJETIVOS_MANUAL = ("mezcla", "equal_weight", "ninguno")
NOMBRE_OBJETIVO = {
    "mezcla": "Mantener la mezcla que tengo hoy",
    "equal_weight": "Repartir por igual (1/N)",
    "ninguno": "Ninguno por ahora",
}

# Lo que el estreno va guardando por el camino. Se borra entero al crear el
# libro para que el siguiente empiece limpio.
BORRADOR = (
    "estreno_puerta", "estreno_filas", "estreno_capital",
    "estreno_fracciones", "estreno_base",
)

AVISO_SIN_RED = (
    "No se pudieron traer los precios ({error}). Sin ellos no se puede "
    "calcular cuánto comprar de cada activo. Si ya compraste, usa **«Ya "
    "compré»**: ese camino no necesita precios porque los pones tú."
)


@st.cache_data(ttl=3600, show_spinner="Descargando precios...")
def _historia(tickers: tuple[str, ...], desde: str):
    return precios.descargar(list(tickers), desde=desde)


def _cierres(tickers: list[str], aviso: str) -> tuple[dict, str | None]:
    """Último cierre de cada activo, o el aviso en pantalla y parar.

    La red falla de mil formas y ninguna es nuestra, así que se atrapa todo: lo
    contrario es enseñar una tabla vacía, que parece un fallo del programa.
    """
    desde = (date.today() - timedelta(days=VENTANA)).isoformat()
    try:
        historia = _historia(tuple(tickers), desde)
    except Exception as error:  # noqa: BLE001 — ver el docstring
        st.warning(aviso.format(error=error))
        st.stop()

    ultimos, fechas = {}, []
    for ticker in tickers:
        # `ultimo` y no `cierre_en`: `cierre_en` exige una fecha exacta, y la
        # de hoy puede no haber cotizado. Esa es la razón de la ventana de
        # cinco días, y pedir el último cierre es lo que la aprovecha.
        precio, cuando = precios.ultimo(historia, ticker)
        ultimos[ticker] = precio
        if cuando:
            fechas.append(cuando)
    return ultimos, (max(fechas) if fechas else None)


def _limpiar() -> None:
    for clave in BORRADOR:
        st.session_state.pop(clave, None)


def _base_del_objetivo(pendiente) -> str | None:
    """El veredicto fuera de muestra y la pregunta de los pesos.

    Las dos cosas van juntas y en este orden a propósito: el veredicto es la
    única evidencia que el programa produjo sobre si la optimización aportaba
    algo, y la pregunta es lo que se hace con ella. Separarlas dejaría la
    pregunta sin su motivo delante.
    """
    metricas = pendiente.metricas or {}
    # **Se vuelve a dictar, no se lee.** Esta pantalla escribía «Fuera de
    # muestra, la optimización superó a repartir por igual: 2,24 frente a 2,07»
    # a partir del `beats_equal_weight` guardado, sin barra de error, sin umbral
    # y sin recálculo — y es la pantalla desde la que se decide contra qué pesos
    # se medirá la deriva de aquí en adelante. Un veredicto dictado con un
    # listón derogado no puede tomar esa decisión.
    dictamen = veredicto_guardado(metricas)
    if dictamen is None:
        st.info(
            "Este portafolio se guardó antes de que el programa midiera el error "
            "de la diferencia contra repartir por igual, así que no hay veredicto "
            "que enseñar: no se puede decir si la optimización aportó algo. "
            "Repartir por igual es la opción que menos supone."
        )
    else:
        _pintar = {True: st.success, False: st.warning}.get(dictamen["estado"], st.info)
        _cifras = (
            f"Fuera de muestra: {metricas['oos_sharpe']:.2f} frente a "
            f"{metricas['oos_equal_weight_sharpe']:.2f} de repartir por igual."
        )
        _aviso = (
            " El fichero guarda otro veredicto, dictado con el listón de entonces."
            if dictamen["discrepa"] else ""
        )
        _pintar(f"**{dictamen['titular']}.** {dictamen['medida']} {_cifras}{_aviso}")

    # Sin índice por defecto, como en el resto del proyecto: un valor
    # preseleccionado convertiría el veredicto de arriba en un clic que nadie
    # mira. Si el usuario ya contestó antes de «Ya la ejecuté», se respeta su
    # respuesta en vez de volver a preguntar en blanco.
    ya = st.session_state.get("estreno_base")
    opciones = ["estrategia", "equal_weight"]
    return st.radio(
        "¿Contra qué pesos quieres medir la deriva?",
        options=opciones,
        format_func=lambda b: (
            "Los pesos de la estrategia" if b == "estrategia"
            else "Repartir por igual (1/N)"
        ),
        index=opciones.index(ya) if ya in opciones else None,
    )


def _pesos_de(pendiente, base: str) -> dict[str, float]:
    """Los pesos que toca comprar, que dependen de la base elegida.

    Se pasa por `mod.pesos_objetivo` en vez de leer las posiciones a mano
    porque es la misma función con la que Rebalanceo medirá la deriva después.
    Calcularlo de otra forma aquí dejaría una cartera recién comprada ya fuera
    de banda el primer día.
    """
    return mod.pesos_objetivo(
        mod.Objetivo(
            fecha=date.today().isoformat(), base=base, portafolio=asdict(pendiente)
        )
    )


def _tabla_editable(filas: list[dict], clave: str) -> pd.DataFrame:
    """La tabla que confirma el usuario. Es lo único que escribe en el libro."""
    return st.data_editor(
        pd.DataFrame(filas, columns=["ticker", "acciones", "precio", "comision"]),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=clave,
        column_config={
            "ticker": st.column_config.TextColumn(
                "Activo", help="El símbolo tal como lo escribe tu bróker.",
            ),
            "acciones": st.column_config.NumberColumn(
                "Acciones", min_value=0.0, format="%.4f",
            ),
            "precio": st.column_config.NumberColumn(
                "Precio pagado", min_value=0.0, format="%.2f",
                help="Lo que pagaste por acción, no el cierre de ese día.",
            ),
            "comision": st.column_config.NumberColumn(
                "Comisión", min_value=0.0, format="%.2f",
            ),
        },
    )


def _filas_de(editado: pd.DataFrame) -> list[dict]:
    """Las filas de la tabla, con los huecos vacíos hechos ceros.

    Una celda que el usuario deja en blanco vuelve como NaN, y NaN atraviesa
    entero cualquier `<= 0`: toda comparación con él es falsa. Sin este relleno
    llegaría hasta el fichero y envenenaría el efectivo del libro.
    """
    limpio = editado.fillna(
        {"ticker": "", "acciones": 0.0, "precio": 0.0, "comision": 0.0}
    )
    return limpio.to_dict("records")


def _asientos(filas: list[dict], capital: float | None, cuando: date):
    """Los asientos de apertura, o el error del usuario pintado tal cual."""
    try:
        asientos = alta.asientos_de(filas, capital, cuando.isoformat())
        for asiento in asientos:
            # `asientos_de` no valida la forma del asiento, y `cargar` sí la
            # revalida al abrir el fichero. Un ticker con forma rara pasaría de
            # largo aquí y dejaría un libro que se escribe y luego no se puede
            # leer, que es peor que uno que no se escribe.
            mod.validar(asiento)
    except (alta.AltaInvalida, mod.AsientoInvalido) as error:
        st.error(str(error))
        return None
    return asientos


def _comunes(nombre_por_defecto: str) -> tuple[str, bool, object, str | None]:
    """El nombre, las fracciones y el plan de aportar: iguales en las tres puertas.

    Devuelve también el motivo por el que todavía no se puede crear, o None.
    """
    st.subheader("Y para terminar")
    nombre = st.text_input(
        "Nombre del libro", value=nombre_por_defecto, max_chars=60
    )
    fracciones = st.checkbox(
        "Mi bróker admite fracciones de acción",
        value=bool(st.session_state.get("estreno_fracciones")),
        help="Decide si el reparto de futuras aportaciones redondea hacia "
             "abajo y deja sobrante, o si cuadra al céntimo.",
    )

    cadencia = st.radio(
        "¿Piensas aportar más dinero cada cierto tiempo?",
        options=("no", "mensual", "trimestral", "anual"),
        format_func=lambda c: "No, por ahora no" if c == "no" else c.capitalize(),
        horizontal=True,
    )
    importe = 0.0
    if cadencia != "no":
        importe = st.number_input(
            "Cuánto, cada vez", min_value=0.0, value=0.0, step=50.0
        )
    st.caption(
        "Es un **plan**, no un movimiento: el libro sólo registra la aportación "
        "cuando ocurra de verdad. Rebalanceo lo usa para no volver a preguntarlo."
    )

    plan = None
    bloqueo = None
    if cadencia != "no":
        if importe <= 0:
            bloqueo = (
                "Dinos cuánto vas a aportar cada vez, o elige «No, por ahora no»."
            )
        else:
            plan = mod.AportacionPrevista(importe=importe, cadencia=cadencia)
    return nombre, fracciones, plan, bloqueo


def _crear(nuevo: mod.Libro) -> None:
    """Guarda el libro, apaga el borrador y aterriza en Seguimiento.

    El `except OSError` está aquí por lo mismo que en el alta de
    `vistas/seguimiento.py`: **el disco es el único sitio donde este dato
    existe**, y sin esta rama un disco lleno o el antivirus llegaban como un
    traceback --`showErrorDetails` viene encendido por defecto-- que no le dice
    al usuario lo único que importa, que es si el libro se creó o no. Se puede
    afirmar que no: `mod.guardar` escribe en un temporal y hace `replace`, así
    que un fallo no deja un fichero a medias, deja que no haya fichero. Y como
    no se pone la marca de `estreno_creado`, volver a pulsar vuelve a intentarlo
    en vez de quedarse en una pantalla que dice que ya está hecho.
    """
    try:
        ruta = mod.guardar(nuevo)
    except OSError as fallo:
        st.error(
            f"No se pudo crear el libro: {fallo}. No se ha guardado nada — "
            "comprueba que hay espacio en el disco y que ningún antivirus esté "
            "bloqueando la carpeta, y vuelve a intentarlo."
        )
        return
    # La marca se pone en cuanto el fichero existe, y entre `guardar` y esta
    # línea no hay ninguna llamada a Streamlit donde un segundo clic pueda
    # interrumpir la pasada. Sin ella ese segundo clic escribiría un libro
    # idéntico con otro nombre, porque `guardar` **no sobrescribe nunca** — es
    # lo que en su día dejó tres ficheros donde había dos altas.
    st.session_state.estreno_creado = str(ruta)
    st.session_state.pop("portafolio_a_seguir", None)
    _limpiar()
    st.switch_page("vistas/seguimiento.py")


def _sin_portafolio() -> None:
    st.info(
        "Esta puerta reparte el capital entre los pesos de un portafolio, y no "
        "traes ninguno. Ábrelo desde **Portafolios guardados** con «Empezar a "
        "seguir», o usa **«Ya tenía una cartera»** para cargarla a mano."
    )
    if st.button("Ir a portafolios guardados", icon=":material/folder_open:"):
        st.switch_page("vistas/portafolios.py")
    st.stop()


st.markdown(
    tema.cabecera(
        "Empezar un libro",
        "El primer movimiento de la cartera. El programa calcula cuánto "
        "comprar de cada activo, pero lo que se guarda es lo que tú confirmes "
        "que ejecutaste: el libro es un registro de hechos, no de intenciones.",
    ),
    unsafe_allow_html=True,
)

pendiente = st.session_state.get("portafolio_a_seguir")

# Llegar con un portafolio pendiente es empezar OTRO estreno, así que la marca
# del anterior sobra. `_crear` vacía `portafolio_a_seguir` antes de saltar, de
# modo que un segundo clic que llegue tarde no puede pasar por aquí.
if pendiente is not None and st.session_state.get("estreno_creado"):
    st.session_state.pop("estreno_creado")

creado = st.session_state.get("estreno_creado")
if creado:
    st.success(f"Ya creaste este libro, en `{creado}`.")
    st.caption(
        "No se escribe otra vez. Un segundo libro con el mismo contenido no se "
        "distingue del primero, y borrar el sobrante sería borrar un historial."
    )
    ir, otro = st.columns(2)
    if ir.button("Ver el libro", type="primary", icon=":material/monitoring:"):
        st.switch_page("vistas/seguimiento.py")
    if otro.button("Empezar otro libro", icon=":material/note_add:"):
        st.session_state.pop("estreno_creado")
        _limpiar()
        st.rerun()
    st.stop()

if pendiente is not None:
    st.markdown(f"### Empezar a seguir «{pendiente.nombre}»")

previa = st.session_state.get("estreno_puerta")
puerta = st.radio(
    "¿En qué punto estás?",
    options=PUERTAS,
    index=PUERTAS.index(previa) if previa in PUERTAS else None,
    format_func=lambda p: NOMBRE_PUERTA[p],
)
# El valor vive en `session_state` y no en una `key` del propio radio: «Ya la
# ejecuté» tiene que poder mover al usuario de puerta, y a un widget no se le
# puede reescribir su estado después de haberlo dibujado.
if puerta != previa:
    st.session_state.estreno_puerta = puerta

if puerta is None:
    st.caption(
        "Los tres caminos acaban en la misma tabla, y esa tabla es lo único que "
        "escribe en el libro."
    )
    st.stop()

# --- Puerta 1: voy a comprar -------------------------------------------------

if puerta == "comprar":
    if pendiente is None:
        _sin_portafolio()

    base = _base_del_objetivo(pendiente)

    col_a, col_b = st.columns(2)
    capital = col_a.number_input(
        "Capital a invertir", min_value=0.0, value=0.0, step=100.0,
        help="El dinero que vas a poner en esta cartera.",
    )
    fracciones = col_b.checkbox(
        "Mi bróker admite fracciones de acción",
        value=bool(st.session_state.get("estreno_fracciones")),
        help="Con acciones enteras el reparto redondea hacia abajo y sobra "
             "dinero. Con fracciones cuadra al céntimo.",
    )
    st.session_state.estreno_fracciones = fracciones

    if base is None:
        st.info("Elige antes contra qué pesos vas a medir la deriva.")
        st.stop()
    if capital <= 0:
        st.info(
            "Dime cuánto vas a invertir y te digo cuántas acciones de cada "
            "activo salen. Con cero no hay nada que repartir."
        )
        st.stop()

    pesos = _pesos_de(pendiente, base)
    ultimos, cierre = _cierres(sorted(pesos), AVISO_SIN_RED)
    reparto = alta.repartir(capital, pesos, ultimos, fracciones)

    st.subheader("Lo que tocaría comprar")
    if cierre:
        st.caption(
            f"Precios del cierre del **{cierre}**. Cuando ejecutes serán otros: "
            "por eso lo que se guarda es lo que confirmes tú."
        )
    st.dataframe(
        pd.DataFrame([
            {
                "Activo": linea.ticker,
                "Peso": f"{linea.peso:.2%}",
                "Importe objetivo": f"{linea.objetivo:,.2f}",
                "Precio": cartera.formato_cifra(linea.precio),
                "Acciones": f"{linea.acciones:,.4f}".rstrip("0").rstrip("."),
                "Nota": linea.motivo,
            }
            for linea in reparto.lineas
        ]),
        use_container_width=True, hide_index=True,
    )

    gastado, sobra = st.columns(2)
    gastado.metric("Se gastaría", f"{reparto.gastado:,.2f}")
    sobra.metric("Sobrante", f"{reparto.sobrante:,.2f}")
    st.caption(
        "**El sobrante no se reparte entre los demás**: nadie ha decidido darle "
        "más peso a ninguno. Queda en el libro como efectivo sin asignar, que "
        "es lo que es, y Rebalanceo ya sabe proponer dónde ponerlo."
    )
    if reparto.sin_precio:
        st.warning(
            "Sin precio para: " + ", ".join(reparto.sin_precio) + ". No se les "
            "asignan acciones a ciegas, así que su parte del capital está "
            "dentro del sobrante. Puedes escribirlas a mano en el paso "
            "siguiente."
        )

    if st.button("Ya la ejecuté", type="primary", icon=":material/task_alt:"):
        st.session_state.estreno_filas = [
            {
                "ticker": linea.ticker,
                "acciones": float(linea.acciones),
                "precio": float(linea.precio or 0.0),
                "comision": 0.0,
            }
            for linea in reparto.lineas
        ]
        st.session_state.estreno_capital = capital
        st.session_state.estreno_base = base
        st.session_state.estreno_puerta = "ya_compre"
        st.rerun()

    st.stop()

# --- Puerta 2: ya compré -----------------------------------------------------

if puerta == "ya_compre":
    if pendiente is None:
        _sin_portafolio()

    base = _base_del_objetivo(pendiente)

    st.subheader("Lo que ejecutaste")
    st.caption(
        "Corrige lo que haga falta: el precio al que entró la orden, las "
        "acciones que cupieron, la comisión. **Se guarda esto, no la "
        "propuesta.** Puedes añadir y quitar filas."
    )
    propuesta = st.session_state.get("estreno_filas")
    if propuesta:
        st.info("Precargado con la propuesta. Es un borrador, no un dato.")
    filas_iniciales = propuesta or [
        {"ticker": p.ticker, "acciones": 0.0, "precio": 0.0, "comision": 0.0}
        for p in pendiente.posiciones
    ]
    editado = _tabla_editable(filas_iniciales, "estreno_tabla_compra")

    cuando = st.date_input(
        "Fecha de las compras", value=date.today(),
        min_value=PRIMER_DIA, max_value=date.today(),
    )
    st.caption(
        "Una sola fecha para todas las filas. Si compraste en días distintos, "
        "registra el resto después desde Seguimiento."
    )

    capital = st.number_input(
        "Dinero que pusiste en la cuenta", min_value=0.0, step=100.0,
        value=float(st.session_state.get("estreno_capital") or 0.0),
        help="Lo que ingresaste para hacer estas compras. Lo que no gastaste "
             "queda en el libro como efectivo.",
    )
    st.caption(
        "Déjalo en cero y se deduce de las compras: el libro nacerá sin "
        "efectivo parado, que es lo honesto si no pusiste de más."
    )

    nombre, fracciones, plan, bloqueo = _comunes(pendiente.nombre)
    if bloqueo:
        st.info(bloqueo)

    if st.button(
        "Crear libro", type="primary", icon=":material/library_add:",
        disabled=base is None or bloqueo is not None,
    ):
        asientos = _asientos(_filas_de(editado), capital or None, cuando)
        if asientos is not None:
            try:
                cimiento = mod.desde_portafolio(nombre, pendiente, base=base)
            except cartera.NombreInvalido as error:
                st.error(str(error))
            else:
                _crear(replace(
                    cimiento, fracciones=fracciones,
                    aportacion_prevista=plan, asientos=asientos,
                ))
    if base is None:
        st.caption("Falta elegir contra qué pesos se mide la deriva.")

    st.stop()

# --- Puerta 3: ya tenía una cartera ------------------------------------------

st.subheader("Lo que ya tienes")
st.caption(
    "Un activo por fila, con lo que te costó cada acción cuando la compraste "
    "—no lo que vale hoy—. El coste es lo que decide después si ganas o pierdes."
)
editado = _tabla_editable(
    [{"ticker": "", "acciones": 0.0, "precio": 0.0, "comision": 0.0}],
    "estreno_tabla_manual",
)

cuando = st.date_input(
    "Fecha de compra", value=date.today(),
    min_value=PRIMER_DIA, max_value=date.today(),
)
st.caption(
    "Una sola fecha para todas las filas. Si las compraste en días distintos, "
    "pon la más antigua y corrige el resto desde Seguimiento: el rendimiento se "
    "mide desde el día que digas."
)

st.subheader("Contra qué medir la deriva")
eleccion = st.radio(
    "¿Qué quieres que sea el objetivo de esta cartera?",
    options=OBJETIVOS_MANUAL,
    format_func=lambda o: NOMBRE_OBJETIVO[o],
    index=None,
)
st.caption(
    "Sin opción marcada a propósito: el objetivo es lo que Rebalanceo usará "
    "después para decirte que operes, y elegirlo por ti sería decidir eso en tu "
    "nombre. **Ninguno por ahora** es una respuesta válida — esa pantalla dirá "
    "que no hay contra qué medir, y podrás asignarlo más tarde."
)

nombre, fracciones, plan, bloqueo = _comunes("Mi cartera")
if bloqueo:
    st.info(bloqueo)

if st.button(
    "Crear libro", type="primary", icon=":material/library_add:",
    disabled=eleccion is None or bloqueo is not None,
):
    filas = _filas_de(editado)
    # Sin capital declarado: aquí nadie ha dicho que tenga dinero parado, y
    # suponer un capital redondo dejaría la diferencia como efectivo fantasma
    # que falsearía la TIR desde el primer día. `asientos_de` lo deriva de lo
    # comprado, y el libro nace con cero efectivo sin asignar.
    asientos = _asientos(filas, None, cuando)
    if asientos is not None:
        acciones: dict[str, float] = {}
        for asiento in asientos:
            if asiento.tipo == "compra" and asiento.ticker and asiento.acciones:
                acciones[asiento.ticker] = (
                    acciones.get(asiento.ticker, 0.0) + asiento.acciones
                )

        momento = datetime.now().isoformat(timespec="seconds")
        objetivos: tuple[mod.Objetivo, ...] = ()

        if eleccion == "equal_weight":
            reparto_igual = 1.0 / len(acciones)
            objetivos = (mod.Objetivo(
                fecha=momento[:10], base="equal_weight",
                portafolio={"nombre": nombre, "fecha": momento[:10], "posiciones": [
                    {"ticker": t, "peso": reparto_igual} for t in sorted(acciones)
                ]},
            ),)
        elif eleccion == "mezcla":
            hoy, _ = _cierres(
                sorted(acciones),
                "No se pudieron traer los precios ({error}), y sin ellos no se "
                "sabe qué mezcla tienes hoy. Puedes crear el libro con "
                "**repartir por igual** o con **ninguno por ahora**, y "
                "asignarle el objetivo más tarde.",
            )
            faltan = [t for t in acciones if not hoy.get(t)]
            if faltan:
                st.warning(
                    "Sin precio de hoy para: " + ", ".join(sorted(faltan)) +
                    ". La mezcla de hoy saldría incompleta, y unos pesos "
                    "objetivo a los que les falta un activo no son los tuyos. "
                    "Elige otro objetivo, o revisa esos símbolos."
                )
                st.stop()
            valor = {t: acciones[t] * hoy[t] for t in acciones}
            total = sum(valor.values())
            # Los pesos de hoy pasan a ser el objetivo. Se fabrica un
            # portafolio con esos pesos y se usa base="estrategia", que
            # significa «los pesos que trae el portafolio»: añadir una base
            # nueva obligaría a tocar un frozenset que otros módulos ya validan
            # contra él.
            objetivos = (mod.Objetivo(
                fecha=momento[:10], base="estrategia",
                portafolio={"nombre": nombre, "fecha": momento[:10], "posiciones": [
                    {"ticker": t, "peso": v / total}
                    for t, v in sorted(valor.items())
                ]},
            ),)

        try:
            nuevo = mod.Libro(
                nombre=cartera.normalizar_nombre(nombre),
                creado=momento,
                fracciones=fracciones,
                aportacion_prevista=plan,
                objetivos=objetivos,
                asientos=asientos,
            )
        except cartera.NombreInvalido as error:
            st.error(str(error))
        else:
            _crear(nuevo)

if eleccion is None:
    st.caption("Falta elegir el objetivo de la cartera.")
