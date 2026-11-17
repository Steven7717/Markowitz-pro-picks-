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

from analizador import deslizadores
from analizador.analisis import pilar_valoracion
from analizador.valorar import valorar

CLAVE_TEXTO = "analizador_texto"
CLAVE_TICKERS = "analizador_tickers"
CLAVE_ANALISIS = "analizador_analisis"
CLAVE_HORA_PANEL = "analizador_hora_panel"
CLAVE_ELEGIDO = "analizador_elegido"
# Una copia del elegido fuera del widget: ver `fijar_elegido`.
_CLAVE_RECORDADO = "analizador_elegido_recordado"
# El canal por el que otras pantallas mandan tickers a analizar.
CANAL = "analizador_encargo"

_PREFIJO_DESLIZADOR = "analizador_desl"
_PREFIJO_MOTIVO = "analizador_motivo"
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

    Y tira la clave de un widget que no se dibujó en una pasada: «Actualizar
    precios» acaba en `st.rerun()` antes del desplegable, y el detalle volvía
    al primero (con SPY elegido, a MU; recorrido de la app real, Task 21 de
    N2). Sin clave, vuelve el último elegido (`recordar_elegido`) si sigue
    entre las opciones.
    """
    if not opciones:
        return
    if CLAVE_ELEGIDO not in estado and estado.get(_CLAVE_RECORDADO) in opciones:
        estado[CLAVE_ELEGIDO] = estado[_CLAVE_RECORDADO]
    if estado.get(CLAVE_ELEGIDO) not in opciones:
        estado[CLAVE_ELEGIDO] = opciones[0]


def recordar_elegido(estado, elegido: str) -> None:
    """Tras dibujar el desplegable: una copia que Streamlit no tira (`fijar_elegido`)."""
    estado[_CLAVE_RECORDADO] = elegido


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


def clave_motivo(ticker: str) -> str:
    """La clave del campo del motivo de «Añadir a la revisión» de `ticker`."""
    return f"{_PREFIJO_MOTIVO}_{ticker}"


def _clave_redactado(ticker: str) -> str:
    # Con otro prefijo: `analizador_motivo_redactado_X` sería el motivo de un
    # ticker que se llamase «redactado_X».
    return f"analizador_redactado_{ticker}"


def preparar_motivo(estado, ticker: str, redactado: str) -> bool:
    """Antes de dibujar el campo del motivo: lo deja al día, y dice si se quedó viejo.

    `redactado` es lo que el programa escribiría ahora, con la valoración y la
    fecha de esta pasada. Junto al campo se guarda lo último que el programa
    redactó, que hace de huella de la valoración: el texto sale entero de ella
    (veredicto y votos) y de la fecha. Con un `setdefault` a secas, tras
    «Actualizar precios» o rehacer el análisis llegaba al acta la valoración
    nueva con un motivo que decía el veredicto y la fecha de antes.

    - Sin tocar --el campo dice lo que redactó el programa, o Streamlit tiró su
      clave por no dibujarlo en una pasada--, se vuelve a redactar.
    - Editado, se conserva: es texto del usuario. Devuelve True si el programa
      redactaría ahora otra cosa que cuando se editó, para que la pantalla lo
      diga: el acta llevaría la valoración de ahora con un motivo escrito
      frente a la de antes.
    """
    clave, huella = clave_motivo(ticker), _clave_redactado(ticker)
    if clave not in estado or estado[clave] == estado.get(huella):
        estado[clave] = estado[huella] = redactado
        return False
    return estado.get(huella) != redactado


def valoracion_en_pantalla(estado, analisis) -> "tuple[dict | None, tuple[str, ...]]":
    """La valoración con lo que marcan los deslizadores ahora, y qué se movió.

    Los bloques de IA explican lo que el usuario tiene delante, y los
    deslizadores viven en un fragmento: lo movido sólo está en las claves de
    sus widgets. Sin entradas, sin nada movido o con supuestos que rompen las
    fórmulas, es la del programa y nada movido.
    """
    entradas = analisis.entradas
    if entradas is None:
        return analisis.valoracion, ()
    puesta = estado.get(clave_a_mano(analisis.ticker))
    r_f_a_mano = None if puesta is None else puesta / 100
    try:
        programa = deslizadores.del_programa(entradas, r_f_a_mano)
        if programa is None:
            return analisis.valoracion, ()
        en_pantalla = {
            nombre: estado.get(clave_deslizador(analisis.ticker, nombre))
            for nombre in programa
            if not (nombre == "r_f" and entradas.r_f is None)
        }
        cambios = deslizadores.cambios(en_pantalla, programa, r_f_a_mano)
        if not cambios:
            return analisis.valoracion, ()
        movida = valorar(entradas, pilar_valoracion(analisis.referencia), cambios)
        return movida, deslizadores.nombres_movidos(entradas, cambios)
    except ValueError:
        return analisis.valoracion, ()
