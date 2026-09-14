"""Lo que se ha comunicado sobre lo que tienes, y lo que viene.

Dos bloques que no se funden nunca: **los hechos** y **la prensa**. Un 8-K es
un documento que la empresa está obligada a presentar ante la SEC, firmado, con
fecha y con consecuencias legales si miente. Un titular es lo que alguien
decidió escribir, y nadie responde de él. Ordenarlos juntos en una sola lista
cronológica —que es lo que hace cualquier agregador— borra esa diferencia justo
donde más cara sale: el aviso de que las cuentas anteriores no son fiables
quedaría entre dos artículos de opinión, indistinguible.

Tampoco se filtra la prensa. No hay criterio defendible para decidir qué
titular importa, y fingir uno sería peor que no tenerlo. Lo que sí se hace es
enseñar el medio y el formato, que es lo que permite descartar de un vistazo:
Yahoo mete vídeos entre las noticias y no lo dice en el titular.

**Aquí no se recomienda nada.** Ni comprar, ni vender, ni esperar. La pantalla
enseña lo que se publicó y quién lo publicó, y la decisión se queda entera del
lado del usuario.
"""

from datetime import date

import streamlit as st

import tema
from noticias import cache, macro, texto, traer
from seguimiento import libro as mod, posiciones
from vistas import libros

# El orden en que se pintan y se consultan. Es el orden de la pantalla —lo que
# viene, los hechos, la prensa— y no el alfabético, para que el pie de página
# se lea en el mismo orden en que se leyó lo de arriba.
ORDEN = ("agenda", "hechos", "prensa")

ETIQUETA = {
    "agenda": "Calendario",
    "hechos": "Hechos (8-K)",
    "prensa": "Prensa",
}

# Por encima de esto la lista deja de leerse y empieza a ser un muro. Se recorta
# **diciéndolo**: cuántas quedaron fuera y cómo verlas. Un recorte silencioso es
# indistinguible de que no hubiera más.
TOPE = 40

# El escapado de `$`, el enlace, «hace X» y la linea de un hecho viven en
# `noticias/texto.py`. Salieron de aqui en el sub-proyecto K, cuando el panel
# de seguimiento empezo a pintar los mismos hechos y los mismos titulares:
# desde un guion de Streamlit --que no se puede importar-- la unica
# alternativa era copiarlos, y lo que se copiaria es el escapado. Dos copias
# de una decision de seguridad se separan igual que dos de cualquier otra, y
# la que se quede atras no da un numero raro: sigue pintando titulares hasta
# el dia en que uno lleve un dolar.


def _cuanto_falta(cuando: date) -> str:
    dias = (cuando - date.today()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    return f"en {dias} días"


def _recorte(items: list) -> tuple:
    """Los que caben y cuántos se quedaron fuera."""
    return items[:TOPE], max(0, len(items) - TOPE)


def _sobrantes(cuantos: int, que: str) -> None:
    if cuantos:
        st.caption(
            f"Quedan {cuantos} {que} sin mostrar, más antiguos que los de "
            "arriba. Quita activos del selector para que quepan."
        )


def _macro() -> None:
    """Los punteros macro, en su propio bloque y sin ninguna fecha."""
    st.markdown("##### Datos de mercado")
    st.caption(
        "Aquí no hay fechas, y es a propósito: el calendario macro no lo "
        "publica ninguna de las fuentes que usa el programa, y copiarlo al "
        "repositorio crearía algo que caduca en silencio —un calendario viejo "
        "se lee igual que uno vigente—. Lo que se guarda es quién publica cada "
        "dato y dónde, que no caduca."
    )
    for evento in macro.PUNTEROS:
        st.markdown(
            f"- {texto.plano(evento.detalle)} — "
            + texto.enlace("ver el calendario", evento.url or "")
        )


st.markdown(
    tema.cabecera(
        "Noticias y calendario",
        "Lo que se ha comunicado sobre los activos de tu libro, y las fechas "
        "que vienen. Los hechos que la empresa está obligada a presentar van "
        "separados de la prensa, que no lo está. Aquí no se recomienda nada.",
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

# --- Sin activos no hay a quién consultar ------------------------------------

# Lo que se tiene ahora más lo que el objetivo dice que se debería tener. Lo
# segundo entra porque una noticia sobre un activo que aún no has comprado
# sigue siendo sobre tu plan; lo que ya vendiste del todo, no.
tenidos = posiciones.estado(actual.asientos).acciones
pesos = mod.pesos_objetivo(actual.objetivo)
tickers = sorted(set(tenidos) | set(pesos))

if not tickers:
    st.info(
        "Este libro no tiene ningún activo: ni posiciones abiertas ni pesos "
        "objetivo. Sin activos no hay a quién consultar noticias, así que no "
        "se ha pedido nada. Registra una compra en **Seguimiento**, o dale un "
        "objetivo desde el optimizador."
    )
    if st.button("Ir a seguimiento", icon=":material/monitoring:"):
        st.switch_page("vistas/seguimiento.py")
    st.stop()

izquierda, derecha = st.columns([5, 1], vertical_alignment="bottom")
elegidos = sorted(
    izquierda.multiselect("Activos", options=tickers, default=tickers)
)
forzar = derecha.button(
    "Actualizar", icon=":material/refresh:", use_container_width=True,
    help="Vuelve a pedir las tres fuentes ahora mismo, sin esperar a que "
    "caduque lo guardado.",
)

if not elegidos:
    st.info(
        "No has elegido ningún activo, así que no hay nada que consultar. "
        "Marca alguno arriba."
    )
    _macro()
    st.stop()

# --- Las tres fuentes --------------------------------------------------------

eventos: list = []
hechos: list = []
prensa: list = []
recogido = {"agenda": eventos, "hechos": hechos, "prensa": prensa}

# Agrupados por (fuente, mensaje) y no por ticker: la falta de EDGAR_IDENTITY
# da el mismo texto para los quince activos, y quince avisos idénticos tapan la
# pantalla y no dicen nada que uno no dijera ya.
problemas: dict = {}
horas: dict = {f: {} for f in ORDEN}

with st.spinner("Consultando las fuentes..."):
    for fuente in ORDEN:
        for ticker in elegidos:
            datos, problema, cuando, vigente = traer.traer(
                fuente, ticker, traer.DESCARGA[fuente], forzar
            )
            recogido[fuente].extend(datos)
            if problema:
                problemas.setdefault((fuente, problema), []).append(ticker)
            if cuando is not None:
                horas[fuente][ticker] = (cuando, vigente)

for (fuente, problema), afectados in problemas.items():
    st.warning(
        f"**{ETIQUETA[fuente]}** — no se pudo traer lo de "
        f"{', '.join(afectados)}. {problema}"
    )

# --- Lo que viene ------------------------------------------------------------

st.subheader("Lo que viene")

# Sólo los que traen fecha. Los punteros macro van aparte y con `cuando=None`:
# meterlos en este `sorted` sería un TypeError, y ponerles una fecha para que
# ordenaran sería inventarse el dato que precisamente no tenemos.
proximos = sorted(
    (e for e in eventos if e.cuando is not None), key=lambda e: e.cuando
)
if proximos:
    for evento in proximos:
        st.markdown(
            f"**{texto.plano(evento.ticker)}** — {texto.plano(evento.detalle)}  \n"
            f"{evento.cuando:%d/%m/%Y} · {_cuanto_falta(evento.cuando)}"
        )
else:
    st.caption(
        "Ninguna fecha próxima para los activos elegidos. El calendario sólo "
        "trae resultados y dividendos, y no todas las empresas los tienen "
        "publicados: que esto esté vacío no significa que no vaya a pasar nada."
    )

_macro()

# --- Lo que pasó: hechos -----------------------------------------------------

st.divider()
st.subheader("Lo que pasó — hechos")
st.caption(
    "Formularios 8-K: lo que la empresa está **obligada** a comunicar a la SEC, "
    "con fecha y firma. No es prensa y no se mezcla con ella. Van desplegados "
    "los tipos que pueden mover los números sobre los que se construyó la "
    "tesis; el resto se pliega, pero no se descarta."
)

# El criterio ya decidió al bajarlos: aquí sólo se reparte. Volver a mirar los
# tipos a mano pondría un segundo criterio en el programa, y el día que se
# moviera uno el otro se quedaría atrás sin que nadie lo notara.
destacados = [h for h in hechos if h.material]
plegados = [h for h in hechos if not h.material]
destacados.sort(key=lambda h: h.cuando, reverse=True)
plegados.sort(key=lambda h: h.cuando, reverse=True)

visibles, fuera = _recorte(destacados)
for hecho in visibles:
    st.markdown(texto.linea_de_hecho(hecho))
_sobrantes(fuera, "hechos destacados")

if plegados:
    with st.expander(f"Otros {len(plegados)} expedientes de trámite"):
        st.caption(
            "Ninguno de estos toca los números de la tesis: votaciones, "
            "anexos, cambios de estatutos. Se enseñan igual, porque plegar no "
            "es descartar."
        )
        for hecho in plegados[:TOPE]:
            st.markdown(texto.linea_de_hecho(hecho))
        if len(plegados) > TOPE:
            st.caption(
                f"Y {len(plegados) - TOPE} más. Quita activos del selector de "
                "arriba para verlos."
            )

if not destacados and plegados:
    # Hueco vacío y hueco vacío no son lo mismo. Que no haya nada destacado
    # habiendo trámite significa que hubo movimiento y nada de lo que importa,
    # que es una respuesta; dejar el sitio en blanco parece que no se miró.
    st.caption("Sin hechos materiales en el periodo; sólo trámite.")
elif not hechos:
    st.caption(
        "Ningún 8-K de los activos elegidos en la ventana consultada. Si "
        "arriba hay un aviso de esta fuente, es que no se pudo preguntar: no "
        "es lo mismo que no haya nada."
    )

# --- Lo que pasó: prensa -----------------------------------------------------

st.divider()
st.subheader("Lo que pasó — prensa")
st.caption(
    "Titulares que otros escribieron. Nadie responde de ellos y el programa no "
    "los filtra: no hay forma defendible de decidir cuál importa. Se enseña el "
    "medio y el formato para que puedas descartarlos tú."
)

prensa.sort(key=lambda n: n.cuando, reverse=True)
visibles, fuera = _recorte(prensa)

if not visibles:
    st.caption("Sin noticias recientes para los activos elegidos.")
for noticia in visibles:
    # Yahoo mete vídeos entre las noticias: en el sondeo, la primera "noticia"
    # de MSFT era un vídeo sobre los resultados de otra empresa. El formato va
    # a la vista para que se descarte sin abrirlo.
    # `clase` no es sólo ARTICLE o VIDEO: en la pasada real de este sub-proyecto
    # Yahoo devolvió STORY para casi todo. Por eso se pinta lo que venga en vez
    # de traducir contra una lista cerrada, que habría dejado la mayoría en
    # blanco. Sólo el vídeo lleva nombre propio, que es el que hay que ver.
    formato = (
        "Vídeo" if noticia.clase.upper() == "VIDEO"
        else noticia.clase.capitalize()
    )
    firma = " · ".join(
        p for p in (texto.plano(noticia.medio), formato) if p
    )
    st.markdown(
        f"**{texto.plano(noticia.ticker)}** — "
        + texto.enlace(texto.plano(noticia.titular), noticia.url)
        + f"  \n{firma} · {noticia.cuando.astimezone():%d/%m/%Y %H:%M}"
    )
    if noticia.resumen:
        st.caption(texto.plano(noticia.resumen[:240]))
_sobrantes(fuera, "noticias")

# --- Cuándo se trajo cada cosa -----------------------------------------------

st.divider()
for fuente in ORDEN:
    marcas = horas[fuente]
    if not marcas:
        st.caption(f"**{ETIQUETA[fuente]}**: no se pudo traer nada.")
        continue
    # La más vieja y no la más nueva: es la antigüedad de lo peor que estás
    # mirando, y lo que se enseña tiene que poder defenderse entero.
    vieja = min(cuando for cuando, _ in marcas.values())
    caducados = sorted(t for t, (_, vigente) in marcas.items() if not vigente)
    linea = (
        f"**{ETIQUETA[fuente]}**: lo más antiguo que estás viendo se descargó "
        f"el {vieja.astimezone():%d/%m/%Y a las %H:%M} ({texto.hace(vieja)}). "
        f"Se vuelve a pedir cada {texto.cada(cache.VALIDEZ[fuente])}."
    )
    if caducados:
        linea += (
            f" Lo de {', '.join(caducados)} es más viejo que eso: la descarga "
            "falló y se enseña lo último que había guardado."
        )
    st.caption(linea)

st.caption(
    "La hora se enseña siempre, esté el dato fresco o no. Un dato que se lee "
    "como recién traído sin serlo es peor que no tener dato."
)
