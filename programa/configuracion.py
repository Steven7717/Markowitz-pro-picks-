"""Qué valores muestra el formulario del optimizador, y de dónde sale cada uno.

**El formulario no puede leer sus valores de un diccionario que se recalcula en
cada reejecución.** Es lo que hacía, y de ahí salió el fallo que este módulo
existe para cerrar: un widget de Streamlit sin `key` deriva su identidad de sus
propios parámetros, `value` incluido. Si el `value` que se le pasa cambia entre
dos pasadas, Streamlit lo toma por un widget nuevo y lo devuelve a ese valor,
tirando lo que el usuario tuviera escrito.

Con eso, el traspaso de un portafolio guardado no podía funcionar de ninguna de
las dos maneras:

- **Consumido en la primera pasada** (lo que había): en la siguiente --y pulsar
  «Optimizar cartera» ya es una-- el `value` volvía a las preferencias, el
  widget se reiniciaba, y la corrida salía con los activos de muestra. Medido:
  se cargaba «prueba 1» con seis activos, la pantalla seguía diciendo «cargado
  de prueba 1» y la optimización corría sobre cinco.
- **Dejado en sesión**: el `value` quedaba fijo, sí, pero volver a pisarlo en
  cada pasada haría el campo imposible de editar.

Así que los valores viven en `session_state` bajo una clave propia --`CLAVES`--
y el formulario los declara con `key=` y sin `value=`. Streamlit deja de
adivinar la identidad del widget, lo escrito persiste porque es suyo, y un
traspaso es lo único que lo pisa: escribe en esas claves una vez y se vacía.
"""

from typing import MutableMapping

# Qué clave de `session_state` guarda cada campo del formulario. El prefijo
# `cfg_` las separa de los canales de traspaso, que viven en el mismo sitio.
CLAVES: dict[str, str] = {
    "tickers": "cfg_tickers",
    "horizonte": "cfg_horizonte",
    "estrategia": "cfg_estrategia",
    "peso_min": "cfg_peso_min",
    "peso_max": "cfg_peso_max",
    "cortos": "cfg_cortos",
    "shrinkage": "cfg_shrinkage",
    "pares": "cfg_pares",
}

# De dónde salió lo que se está viendo, para la etiqueta de la cabecera.
CLAVE_ORIGEN = "cfg_origen"

# Los dos canales por los que otra pantalla manda una configuración aquí.
# `vistas/portafolios.py` y `vistas/comparar.py` usan el primero;
# `vistas/candidatos.py` y `vistas/actas.py`, el segundo.
CANAL_PORTAFOLIO = "portafolio_a_cargar"
CANAL_GATE = "tickers_aprobados"


def sembrar(
    estado: MutableMapping,
    guardadas,
    tickers_por_defecto: str,
) -> str:
    """Deja en `estado` lo que el formulario debe mostrar. Devuelve el origen.

    Tres fuentes, en este orden y no en otro: lo que el usuario acaba de cargar
    a propósito (un portafolio guardado), lo que le llega del gate de
    aprobación, y por último sus preferencias. Un portafolio recién cargado
    tiene que ganarle a las preferencias --es lo que el usuario pidió hace un
    segundo-- y el traspaso del gate tiene que ganarle a la lista por defecto,
    porque si no, aprobar quince empresas no serviría de nada.

    Los dos traspasos se consumen al usarlos. Es lo que separa «esto lo acaba
    de pedir el usuario» de «esto lleva ahí desde hace tres pantallas»: si se
    quedasen, volverían a pisar lo que escriba después y el formulario sería
    imposible de editar.

    Args:
        estado: `st.session_state`, o cualquier diccionario en los tests.
        guardadas: las `Preferencias` del usuario.
        tickers_por_defecto: la lista de muestra, para quien no tiene ninguna.

    Returns:
        El origen de lo que se muestra, o "" si sale de las preferencias.
    """
    # `setdefault` y no asignación: esto es el suelo, no una orden. Lo que el
    # usuario escribió en una visita anterior de la misma sesión sigue siendo
    # suyo.
    base = {
        "tickers": guardadas.tickers or tickers_por_defecto,
        "horizonte": guardadas.horizonte,
        "estrategia": guardadas.estrategia,
        "peso_min": guardadas.peso_min,
        "peso_max": guardadas.peso_max,
        "cortos": guardadas.permitir_cortos,
        "shrinkage": guardadas.shrinkage,
        # La covarianza por pares no esta en las preferencias ni en el fichero
        # de un portafolio guardado: es una decision sobre como estimar, de esta
        # corrida, y arranca apagada siempre. Cargar un portafolio no la toca.
        "pares": False,
    }
    for campo, clave in CLAVES.items():
        estado.setdefault(clave, base[campo])
    estado.setdefault(CLAVE_ORIGEN, "")

    aprobados = estado.pop(CANAL_GATE, None)
    if aprobados:
        # Sólo los tickers: el gate decide qué empresas, no con qué horizonte
        # ni con qué límites de peso mirarlas.
        estado[CLAVES["tickers"]] = ", ".join(aprobados)
        estado[CLAVE_ORIGEN] = f"{len(aprobados)} empresas aprobadas en el gate"

    cargado = estado.pop(CANAL_PORTAFOLIO, None)
    if cargado is not None:
        estado[CLAVES["tickers"]] = ", ".join(cargado.tickers)
        estado[CLAVES["horizonte"]] = cargado.horizonte
        estado[CLAVES["estrategia"]] = cargado.estrategia
        # Los deslizadores van de 0 a 100 y el portafolio lo guarda en
        # fracción, que es como lo consume el optimizador.
        estado[CLAVES["peso_min"]] = int(round(cargado.peso_min * 100))
        estado[CLAVES["peso_max"]] = int(round(cargado.peso_max * 100))
        estado[CLAVES["cortos"]] = cargado.permitir_cortos
        estado[CLAVES["shrinkage"]] = cargado.shrinkage
        estado[CLAVE_ORIGEN] = f"cargado de «{cargado.nombre}»"

    return estado[CLAVE_ORIGEN]


def reiniciar(estado: MutableMapping) -> None:
    """Olvidar el formulario entero para que la próxima pasada vuelva a sembrarlo.

    Se llama al guardar preferencias nuevas, y al volver a las de fábrica.
    «Guardadas. El optimizador arrancará con estos valores» es lo que dice esa
    pantalla, y es una promesa: sin esto, los valores viejos seguirían en sesión
    y unas preferencias recién guardadas no se verían hasta la sesión siguiente.
    """
    for clave in CLAVES.values():
        estado.pop(clave, None)
    estado.pop(CLAVE_ORIGEN, None)


def olvidar_origen(estado: MutableMapping) -> None:
    """Dejar de decir de dónde vino esto, sin tocar lo que hay en el formulario.

    Se llama cuando el usuario vuelve a optimizar: a partir de ahí la corrida es
    suya, no la del portafolio que cargó, y seguir etiquetándola con el nombre
    de aquél afirmaría algo que ya no es cierto.
    """
    estado.pop(CLAVE_ORIGEN, None)
