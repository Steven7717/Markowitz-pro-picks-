"""Lo que el Analizador guarda en la sesión, y cómo le llegan tickers de otras pantallas.

Sin Streamlit: recibe `st.session_state`, o un diccionario en los tests. Es el
reparto de `configuracion.py` con el formulario del optimizador, y por las
mismas dos razones:

- **El campo de tickers se declara con `key=` y sin `value=`.** Un widget sin
  clave deriva su identidad de sus parámetros, y un `value` que cambia entre
  pasadas lo reinicia: es «El formulario que se quedaba en blanco». Lo que
  viene de fuera --«Analizar a fondo», «Abrir en el Analizador», «Cargar de un
  libro»-- escribe en esa clave antes de que se dibuje el campo, o desde un
  callback.
- **Un encargo se consume al usarlo.** Si se quedase, volvería a pisar lo que
  el usuario escriba después.

Los análisis se guardan porque cuestan: quince tickers en frío, cerca de un
minuto. Valen mientras no cambie el panel de referencia con que se hicieron;
si cambia, se tiran enteros, porque una ficha contra el panel de ayer y otra
contra el de hoy no van en la misma tabla.
"""

from dataclasses import dataclass

CLAVE_TEXTO = "analizador_texto"
CLAVE_TICKERS = "analizador_tickers"
CLAVE_ANALISIS = "analizador_analisis"
CLAVE_HORA_PANEL = "analizador_hora_panel"
CLAVE_ELEGIDO = "analizador_elegido"
# El canal por el que otras pantallas mandan tickers a analizar.
CANAL = "analizador_encargo"

_PREFIJO_DESLIZADOR = "analizador_desl"
_A_MANO = "r_f_a_mano"


@dataclass(frozen=True)
class Encargo:
    """Tickers que otra pantalla manda analizar, y cuál dejar elegido en el detalle."""

    tickers: "tuple[str, ...]"
    elegido: "str | None" = None


def encargar(estado, tickers, elegido: "str | None" = None) -> None:
    """Lo que llama «Analizar a fondo» o «Abrir en el Analizador» antes de saltar aquí."""
    estado[CANAL] = Encargo(tuple(tickers), elegido)


def recoger(estado) -> "Encargo | None":
    """El encargo pendiente, ya consumido: deja los tickers en el campo y, si lo hay, el elegido.

    Se llama antes de dibujar el campo. Lo que no es un `Encargo` se tira: un
    valor de otra versión no puede tumbar la pantalla.
    """
    encargo = estado.pop(CANAL, None)
    if not isinstance(encargo, Encargo):
        return None
    estado[CLAVE_TEXTO] = " ".join(encargo.tickers)
    if encargo.elegido is not None:
        estado[CLAVE_ELEGIDO] = encargo.elegido
    return encargo


def cargar_texto(estado, tickers) -> None:
    """Para el callback de «Cargar de un libro»: rellena el campo y no analiza (D13)."""
    estado[CLAVE_TEXTO] = " ".join(tickers)


def preparar(estado, hora_panel) -> dict:
    """La caché de análisis de esta sesión, vaciada si el panel cambió desde que se llenó."""
    if estado.get(CLAVE_HORA_PANEL) != hora_panel or not isinstance(estado.get(CLAVE_ANALISIS), dict):
        estado[CLAVE_ANALISIS] = {}
        estado[CLAVE_HORA_PANEL] = hora_panel
    return estado[CLAVE_ANALISIS]


def panel_cambiado(estado, hora_panel) -> bool:
    """Si hay análisis guardados hechos con otro panel que el de ahora."""
    return bool(estado.get(CLAVE_ANALISIS)) and estado.get(CLAVE_HORA_PANEL) != hora_panel


def pendientes(tickers, hechos: dict) -> "list[str]":
    """Los tickers por analizar, en el orden en que se escribieron.

    Los que no tienen análisis y los que lo tienen sin clase: un `sin_red` o un
    `sin_red_edgar` es un fallo de la red, no un hecho de la empresa, y pulsar
    «Analizar» otra vez tiene que volver a intentarlo. Los demás salen de la
    caché de la sesión.
    """
    return [t for t in tickers if t not in hechos or getattr(hechos[t], "clase", None) is None]


def fijar_elegido(estado, opciones) -> None:
    """Antes de dibujar el desplegable del detalle.

    Streamlit tumba la pasada entera si la clave guarda una opción que no está
    entre las de ahora (`seguimiento.libro.fijar_eleccion`): un ticker que ya no
    se analiza, o uno que llegó por un encargo y salió sin clase. Sin opciones
    no se toca.
    """
    if opciones and estado.get(CLAVE_ELEGIDO) not in opciones:
        estado[CLAVE_ELEGIDO] = opciones[0]


def clave_deslizador(ticker: str, nombre: str) -> str:
    """La clave del widget del supuesto `nombre` de `ticker`."""
    return f"{_PREFIJO_DESLIZADOR}_{ticker}_{nombre}"


def clave_a_mano(ticker: str) -> str:
    """La clave de la casilla donde se pone la tasa libre que falta."""
    return clave_deslizador(ticker, _A_MANO)


def _de_su_ticker(estado, ticker: str) -> "list[str]":
    prefijo = clave_deslizador(ticker, "")
    return [clave for clave in estado if isinstance(clave, str) and clave.startswith(prefijo)]


def restaurar_deslizadores(estado, ticker: str) -> None:
    """«Restaurar los del programa»: borra lo movido y deja la tasa puesta a mano.

    Sin claves, cada deslizador vuelve a nacer en la cifra del programa. La
    tasa puesta a mano se queda porque no hay programa al que volver: sin ella,
    no hay valoración.
    """
    for clave in _de_su_ticker(estado, ticker):
        if clave != clave_a_mano(ticker):
            del estado[clave]


def olvidar_deslizadores(estado, ticker: str) -> None:
    """Al rehacer el análisis de un ticker: las cifras del programa pueden haber cambiado."""
    for clave in _de_su_ticker(estado, ticker):
        del estado[clave]
