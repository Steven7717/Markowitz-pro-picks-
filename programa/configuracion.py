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

from data import HORIZON_CONFIG
from optimizer import STRATEGY_LABELS
from preferencias import entero_en_rango

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

        # **Los mismos dos, con el mismo guardarraíl que los deslizadores de
        # abajo.** El razonamiento está escrito ahí y vale palabra por palabra:
        # Streamlit revienta al CONSTRUIR el widget si la sesión trae un valor
        # que no está entre sus opciones, y `st.selectbox` y `st.radio` toman
        # las suyas de `HORIZON_CONFIG` y `STRATEGY_LABELS`. `cartera.cargar`
        # valida el contrato del fichero, pero no que el horizonte que guardó
        # siga existiendo hoy.
        #
        # Que el aviso llegase a los pesos y no a estos dos, estando los cuatro
        # en el mismo bloque, es el patrón de la auditoría otra vez.
        #
        # **El repuesto es lo que ya hay sembrado**, y por eso aquí no se
        # asigna nada en el camino malo: cuando llega este canal, `setdefault`
        # ya ha puesto las preferencias del usuario en el formulario. Son suyas
        # y son válidas —`preferencias.saneadas()` las revisa al cargarlas, con
        # su aviso— así que son mejor repuesto que cualquier valor de fábrica.
        sustituidos: list[str] = []
        if cargado.horizonte in HORIZON_CONFIG:
            estado[CLAVES["horizonte"]] = cargado.horizonte
        else:
            sustituidos.append(f"su horizonte «{cargado.horizonte}» ya no existe")
        if cargado.estrategia in STRATEGY_LABELS:
            estado[CLAVES["estrategia"]] = cargado.estrategia
        else:
            sustituidos.append(f"su estrategia «{cargado.estrategia}» ya no existe")

        # Los deslizadores van de 0 a 100 y el portafolio lo guarda en
        # fracción, que es como lo consume el optimizador.
        #
        # Acotado con la misma función que `preferencias.saneadas()`, y por
        # el mismo motivo: `cartera.cargar` valida el contrato del fichero
        # pero no los rangos, así que un portafolio editado a mano, venido
        # de otra versión o compartido por alguien podía traer un 30 % de
        # peso mínimo cuando el deslizador llega a 20. Streamlit revienta al
        # CONSTRUIR el widget, o sea que la página se queda en blanco antes
        # de pintar nada, y el valor malo se queda en sesión: sigue rota
        # hasta cargar otro portafolio o reiniciar. El canal de las
        # preferencias ya estaba protegido; este no.
        estado[CLAVES["peso_min"]] = entero_en_rango(
            round(cargado.peso_min * 100), 0, 20, 0
        )
        estado[CLAVES["peso_max"]] = entero_en_rango(
            round(cargado.peso_max * 100), 20, 100, 100
        )
        estado[CLAVES["cortos"]] = cargado.permitir_cortos
        estado[CLAVES["shrinkage"]] = cargado.shrinkage
        # **Y se dice, en vez de hacerse en silencio.** Es la regla que
        # `vistas/portafolios.py` ya aplica al veredicto: el usuario recuerda lo
        # que guardó, y un formulario que anuncia «cargado de X» mientras enseña
        # un horizonte que X no pidió estaría afirmando algo falso. La etiqueta
        # de origen es donde ya mira para saber qué está viendo.
        estado[CLAVE_ORIGEN] = f"cargado de «{cargado.nombre}»"
        if sustituidos:
            estado[CLAVE_ORIGEN] += f" — {' y '.join(sustituidos)}"

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
