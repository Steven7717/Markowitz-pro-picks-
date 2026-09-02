"""Apagar el servidor cuando ya no queda nadie mirándolo.

Con la ventana de consola a la vista, cerrarla era la forma de parar el
programa. Ocultarla deja al usuario sin esa palanca: cierra la pestaña del
navegador, cree que ha terminado, y queda un proceso vivo ocupando el puerto
para siempre. El siguiente arranque se encuentra el puerto cogido y falla sin
que nada de lo que se ve en pantalla lo explique.

El botón «Salir» de la barra lateral resuelve el caso del usuario que busca
cómo cerrar. Este módulo resuelve el que no lo busca —cierra la pestaña y ya
está—, que es la mayoría.

**Cómo sabe que no queda nadie.** Streamlit mantiene una sesión por pestaña
conectada. Al cerrar la pestaña, el websocket se cae y la sesión deja de
contar como activa de inmediato. Cero sesiones activas significa, literalmente,
que nadie tiene el programa abierto.

**Por qué hay dos guardas y no una.** Cero sesiones ocurre también en dos
momentos en los que apagar sería un fallo:

- *Antes de que llegue el primer navegador.* Entre que arranca el servidor y
  que se abre la pestaña pasan segundos, y en un primer arranque —descargando
  Python y las librerías— pueden ser minutos. Por eso la cuenta atrás no
  empieza hasta que alguien se ha conectado al menos una vez.
- *Al recargar la página.* El websocket se cae y se vuelve a levantar, así que
  hay un instante a cero. Por eso hace falta que el cero se sostenga durante
  `ESPERA` segundos seguidos, y no basta con verlo una vez.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

# Un minuto y medio sin nadie conectado. Sobra para aguantar una recarga o el
# reinicio del navegador, y no deja un proceso olvidado toda la tarde. No se
# hace configurable a propósito: es un detalle de intendencia, y una opción más
# en la pantalla de ajustes cuesta más atención de la que ahorra.
ESPERA = 90.0
INTERVALO = 5.0

# El interruptor lo pone el lanzador, no el código. Quien arranca a mano con
# `streamlit run app.py` -- desarrollo, pruebas -- se queda con el comportamiento
# de siempre: nada se apaga solo mientras mira otra ventana.
VARIABLE = "MPP_AUTOAPAGADO"


@dataclass
class Vigilante:
    """Cuenta cuánto lleva el programa sin nadie delante, y apaga si toca.

    Toda la lógica vive en `tic()`, que no duerme, no crea hilos y no toca
    Streamlit: recibe de fuera cómo contar, cómo apagar y qué hora es. Así se
    puede probar el caso que importa —noventa segundos vacío— sin esperar
    noventa segundos.
    """

    contar: Callable[[], int]
    apagar: Callable[[], None]
    espera: float = ESPERA
    reloj: Callable[[], float] = time.monotonic
    _hubo_alguien: bool = field(default=False, init=False)
    _vacio_desde: float | None = field(default=None, init=False)
    averiado: bool = field(default=False, init=False)
    _parada: threading.Event = field(default_factory=threading.Event, init=False)

    def parar(self) -> None:
        """Detener el hilo de vigilancia sin apagar el programa.

        En produccion no se llama nunca --el vigilante vive lo que vive el
        proceso--, pero un bucle que no se puede parar no se puede probar sin
        dejar un hilo suelto para el resto de la sesion de pytest. Y uno suelto
        llamando a time.sleep tumbo un test de `fundamentals` que comprueba,
        con un mock global de time.sleep, que la descarga no se duerme entre
        tickers.
        """
        self._parada.set()

    def tic(self) -> bool:
        """Una comprobación. Devuelve True si ha ordenado el apagado."""
        if self.averiado:
            return False

        try:
            conectados = self.contar()
        except Exception:
            # Contar sesiones toca un atributo privado de Streamlit
            # (`_session_mgr`). Si una versión futura lo renombra, esto se
            # apaga a sí mismo y el programa sigue funcionando exactamente como
            # antes: con una ventana que no se cierra sola. Lo contrario
            # --dejar que la excepción suba desde un hilo de fondo, o apagar
            # ante la duda-- cerraría el programa por sorpresa mientras alguien
            # lo usa, que es el único desenlace inaceptable.
            self.averiado = True
            return False

        if conectados > 0:
            self._hubo_alguien = True
            self._vacio_desde = None
            return False

        if not self._hubo_alguien:
            return False

        ahora = self.reloj()
        if self._vacio_desde is None:
            self._vacio_desde = ahora
            return False

        if ahora - self._vacio_desde < self.espera:
            return False

        self.apagar()
        return True


def sesiones_activas() -> int:
    """Cuántas pestañas hay conectadas ahora mismo.

    `num_active_sessions` es API del SessionManager; llegar hasta él pasa por
    `_session_mgr`, que es privado. Está aislado en esta función para que el
    día que cambie haya un solo sitio que arreglar, y para que el `except` del
    vigilante lo cubra entero.
    """
    from streamlit.runtime import Runtime

    return Runtime.instance()._session_mgr.num_active_sessions()


def detener() -> None:
    """Pedirle a Streamlit que cierre. `stop()` es público y seguro entre hilos.

    Se pide el apagado ordenado en vez de matar el proceso: así se cierran las
    sesiones, se sueltan los ficheros abiertos y el puerto queda libre de
    verdad para el siguiente arranque.
    """
    from streamlit.runtime import Runtime

    Runtime.instance().stop()


def detener_en(segundos: float = 1.5, apagar: Callable[[], None] = detener) -> None:
    """Apagar dentro de un momento, no ahora mismo.

    Lo que se pinta durante una reejecución no llega al navegador hasta que el
    guion termina. Llamando a `detener()` en mitad del guion, el servidor se
    cae antes de entregar la despedida y lo que ve el usuario es el aviso de
    conexión perdida de Streamlit — que parece exactamente lo que pasa cuando
    un programa se rompe, justo en el momento en que acaba de cerrarlo bien.
    """
    threading.Timer(segundos, apagar).start()


def activo(entorno: dict | None = None) -> bool:
    """Si el lanzador pidió el apagado automático."""
    import os

    valores = os.environ if entorno is None else entorno
    return valores.get(VARIABLE, "").strip().lower() in {"1", "true", "si", "sí"}


def vigilar(
    espera: float = ESPERA,
    intervalo: float = INTERVALO,
    contar: Callable[[], int] = sesiones_activas,
    apagar: Callable[[], None] = detener,
) -> Vigilante | None:
    """Lanzar el vigilante en un hilo de fondo. None si no toca vigilar.

    El hilo es `daemon` para que no impida salir cuando el apagado llega por
    otro camino —el botón «Salir», o cerrar la ventana si está a la vista—.
    """
    if not activo():
        return None

    vigilante = Vigilante(contar=contar, apagar=apagar, espera=espera)

    def bucle() -> None:
        # wait() y no sleep(): despierta en cuanto alguien llama a parar(), y
        # ademas no toca time.sleep, que otras pruebas de este proyecto
        # sustituyen por un mock global.
        while not vigilante._parada.wait(intervalo):
            if vigilante.averiado or vigilante.tic():
                return

    threading.Thread(target=bucle, name="mpp-autoapagado", daemon=True).start()
    return vigilante
