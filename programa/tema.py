"""El aspecto de la aplicación, decidido en un solo sitio.

Antes había tres paletas: la de `.streamlit/config.toml`, la de `charts.py` y la
de `medidores.py`. Coincidían por costumbre, no por construcción, y cada una se
podía mover sin que las otras se enterasen. Aquí viven los colores y de aquí
los leen los demás módulos.

**Sobre el CSS.** Streamlit no tiene una API de estilos, así que las reglas de
abajo se cuelgan de los atributos `data-testid` de sus componentes. Son mucho
más estables que los nombres de clase generados (`st-emotion-cache-1ibys3g`),
pero siguen siendo interiores de la librería. La regla que hace que eso sea
aceptable: **ninguna regla de esta hoja cambia lo que la aplicación hace.** Si
una actualización de Streamlit renombra un `data-testid`, ese trozo deja de
pintarse bonito y todo lo demás sigue funcionando igual — nada de layout
crítico, ni de posicionamiento que esconda un botón, depende de estos
selectores.
"""

# ── Paleta ───────────────────────────────────────────────────────────────────
# Superficies, de más al fondo a más al frente.
FONDO = "#0f1117"
SUPERFICIE = "#151824"
TARJETA = "#1a1d2b"
ELEVADA = "#1f2331"
BORDE = "#2b3040"
BORDE_SUAVE = "#242938"

# Texto. Los tres pasan de 4,5:1 sobre FONDO; TENUE se queda en 4,6:1 y por eso
# no lleva nunca información que no esté también en otro sitio.
TEXTO = "#e6e8ef"
TEXTO_SUAVE = "#9aa2b8"
TEXTO_TENUE = "#79809a"

# Marca y semántica. La familia es la misma de charts.py (Tailwind 400), que ya
# estaba elegida y contrasta de sobra sobre el fondo oscuro.
ACENTO = "#7c83fd"
ACENTO_TENUE = "#4a4f8a"
VERDE = "#4ade80"
AMBAR = "#fbbf24"
ROJO = "#f87171"
AZUL = "#60a5fa"
NARANJA = "#fb923c"

# Una fuente del sistema en vez de una de Google: el programa se arranca con un
# .bat en el escritorio de alguien y tiene que verse igual sin conexión. Lo que
# de verdad hace que una tabla financiera parezca profesional no es la familia,
# son las cifras de ancho fijo, y eso lo da `font-variant-numeric` más abajo.
FUENTE = (
    '"Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, '
    '"Inter", system-ui, sans-serif'
)
FUENTE_MONO = '"Cascadia Mono", "SF Mono", "JetBrains Mono", Consolas, monospace'

_TONOS = {
    "neutro": TEXTO_SUAVE,
    "acento": ACENTO,
    "bueno": VERDE,
    "aviso": AMBAR,
    "malo": ROJO,
    "info": AZUL,
}


CSS = f"""<style>
/* --- Base ---------------------------------------------------------------- */
/* Solo en la raiz, y que herede. Un selector de brocha gorda como
   `[class*="st-"]` alcanza TODOS los elementos de Streamlit, incluidos los
   <span> de los iconos, que llevan su propia familia ("Material Symbols
   Rounded") con la misma especificidad: al llegar esta hoja despues, ganaba, la
   ligadura no se aplicaba y cada icono se pintaba como su nombre en letras
   -- "insights", "settings" -- encima de la etiqueta del boton. */
html, body {{ font-family: {FUENTE}; }}

/* Cifras de ancho fijo en todo lo que sea un numero. Sin esto, una columna de
   pesos baila horizontalmente al cambiar de digito y la tabla se lee peor. */
[data-testid="stMetricValue"], [data-testid="stDataFrame"],
[data-testid="stTable"], code, .mpp-num {{ font-variant-numeric: tabular-nums; }}

[data-testid="stMainBlockContainer"] {{ padding-top: 2.4rem; max-width: 1500px; }}

/* --- Cabecera de pagina --------------------------------------------------- */
.mpp-cabecera {{ margin: 0 0 1.1rem; }}
.mpp-cabecera h1 {{
  font-size: 1.7rem; font-weight: 700; letter-spacing: -.02em;
  color: {TEXTO}; margin: 0 0 .2rem; line-height: 1.2;
}}
.mpp-cabecera p {{ color: {TEXTO_SUAVE}; font-size: .9rem; margin: 0; max-width: 78ch; }}
.mpp-regla {{
  height: 1px; border: 0; margin: .9rem 0 1.2rem;
  background: linear-gradient(90deg, {ACENTO}66, {BORDE} 45%, transparent);
}}

/* --- Etiqueta pequena ----------------------------------------------------- */
.mpp-etiqueta {{
  display: inline-block; border: 1px solid {BORDE}; border-radius: 999px;
  padding: .08rem .55rem; font-size: .72rem; color: {TEXTO_SUAVE};
  background: {SUPERFICIE}; margin-right: .3rem;
}}

/* --- Metricas como tarjetas ---------------------------------------------- */
[data-testid="stMetric"] {{
  background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 10px;
  padding: .7rem .85rem .55rem;
}}
[data-testid="stMetricLabel"] p {{
  font-size: .74rem !important; color: {TEXTO_SUAVE} !important;
  text-transform: uppercase; letter-spacing: .04em;
}}
[data-testid="stMetricValue"] {{ font-size: 1.5rem; color: {TEXTO}; }}

/* --- Pestanas ------------------------------------------------------------- */
/* role="tablist" y data-testid="stTab", no data-baseweb: Streamlit dejo de
   apoyarse en BaseWeb para las pestanas y esos selectores ya no casaban con
   nada. Un rol ARIA es lo mas estable que hay aqui, porque no es un detalle de
   implementacion sino lo que hace que un lector de pantalla las anuncie. */
[data-testid="stTabs"] [role="tablist"] {{
  gap: .15rem; border-bottom: 1px solid {BORDE};
}}
[data-testid="stTab"] {{
  padding: .5rem .95rem; border-radius: 8px 8px 0 0; color: {TEXTO_SUAVE};
  transition: background 160ms ease, color 160ms ease;
}}
[data-testid="stTab"]:hover {{ background: {SUPERFICIE}; color: {TEXTO}; }}
[data-testid="stTab"][aria-selected="true"] {{ color: {TEXTO}; background: {TARJETA}; }}

/* --- Botones -------------------------------------------------------------- */
/* Por prefijo: Streamlit tiene un testid por variante de boton --secondary,
   primary, primaryFormSubmit, download, tertiary-- y nombrarlos uno a uno
   dejaba sin estilo justo el de "Optimizar cartera", que es un submit de
   formulario. Se excluyen los iconos de las barras de herramientas de graficos
   y de la cabecera, donde un salto al pasar el raton queda ridiculo. */
[data-testid^="stBaseButton-"]:not([data-testid*="elementToolbar"]):not([data-testid*="header"]) {{
  border-radius: 8px; font-weight: 600;
  transition: transform 140ms ease, filter 140ms ease, border-color 140ms ease;
}}
[data-testid^="stBaseButton-"]:not([data-testid*="elementToolbar"]):not([data-testid*="header"]):hover {{
  transform: translateY(-1px); filter: brightness(1.08);
}}

/* --- Contenedores y desplegables ------------------------------------------ */
[data-testid="stExpander"] details {{
  border: 1px solid {BORDE}; border-radius: 10px; background: {SUPERFICIE};
}}
[data-testid="stExpander"] summary:hover {{ color: {ACENTO}; }}

/* --- Barra lateral -------------------------------------------------------- */
[data-testid="stSidebar"] {{ background: {SUPERFICIE}; border-right: 1px solid {BORDE}; }}
[data-testid="stSidebarNav"] a {{ border-radius: 8px; }}

/* --- Tablas --------------------------------------------------------------- */
[data-testid="stDataFrame"] {{ border: 1px solid {BORDE}; border-radius: 10px; }}

/* --- Foco visible --------------------------------------------------------- */
/* Nunca se quita el anillo de foco: es la unica pista de donde esta quien
   navega con el teclado. Solo se le da el color de la marca. */
:focus-visible {{ outline: 2px solid {ACENTO} !important; outline-offset: 2px !important; }}

/* --- Movimiento reducido -------------------------------------------------- */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: .001ms !important; transition-duration: .001ms !important;
  }}
  [data-testid^="stBaseButton-"]:hover {{ transform: none; }}
}}
</style>"""


def rgba(color: str, alpha: float) -> str:
    """The same palette colour, translucent.

    Existe para que las zonas de fondo de los medidores se deriven del color
    semántico en vez de llevar su propio `rgba(248,113,113,.13)` escrito a mano:
    con el literal, cambiar el rojo de la paleta dejaba la zona de "malo" del
    rojo anterior, y nadie lo vería hasta compararlos uno al lado del otro.
    """
    limpio = color.lstrip("#")
    r, g, b = (int(limpio[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def aplicar(st) -> None:
    """Inject the stylesheet once per script run.

    Recibe `st` por parámetro en vez de importar Streamlit arriba para que este
    módulo se pueda importar —y probar— sin arrancar nada: todo lo demás que
    hay aquí son cadenas.
    """
    st.markdown(CSS, unsafe_allow_html=True)


def _esc(texto: object) -> str:
    import html

    return html.escape(str(texto))


def cabecera(titulo: str, subtitulo: str = "") -> str:
    """The block that opens every page: what this is, and what it is for.

    El subtítulo no es decoración. Cada pantalla de esta aplicación hace algo
    que se puede malinterpretar —un score que no es una previsión, un acta que
    es un registro, una fotografía que no se recalcula— y la línea de debajo
    del título es donde se dice, antes de que nadie toque nada.
    """
    linea = f"<p>{_esc(subtitulo)}</p>" if subtitulo else ""
    return (
        f'<div class="mpp-cabecera"><h1>{_esc(titulo)}</h1>{linea}</div>'
        '<hr class="mpp-regla">'
    )


def etiqueta(texto: str, tono: str = "neutro") -> str:
    """A small inline chip. Unknown tones fall back to neutral rather than break."""
    color = _TONOS.get(tono, _TONOS["neutro"])
    return (
        f'<span class="mpp-etiqueta" style="color:{color};border-color:{color}55">'
        f"{_esc(texto)}</span>"
    )
