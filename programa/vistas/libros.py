"""El desplegable de «Libro», que es el mismo en tres pantallas.

Seguimiento, Rebalanceo y Noticias empiezan igual: listan los libros, nombran
los que no se pueden leer y dejan elegir uno. Estaba escrito tres veces, y las
tres copias **no le ponían `key` al desplegable**. Sin `key` no hay nada en
`st.session_state`, y sin nada en `session_state` no hay nada que pueda viajar
entre páginas: «Anotar lo que ejecuté» saltaba de Rebalanceo a Seguimiento
—conservando la sesión entera, que no servía de nada porque la elección no
estaba dentro— y aterrizaba en el primer libro de la lista, con el formulario
de registrar abierto debajo.

Eso no es una molestia de navegación. El libro es **append-only**: un asiento
escrito en la cartera equivocada no se borra, se anula, y las dos líneas se
quedan en el historial para siempre.

Este módulo es la vista —tres llamadas a Streamlit— y no decide nada. Qué se
puede elegir, cuál se preselecciona y cómo se tolera que el libro recordado ya
no esté vive en `seguimiento/libro.py`, que se puede importar desde un test;
un guion de Streamlit, no. Es el mismo reparto que `seguimiento/panel.py` con
la aritmética y `comparativa.py` con la comparación.

Vive en `vistas/` y no es una pantalla: la navegación de la app se declara a
mano en `app.py` con `st.navigation`, así que un fichero de más aquí no se
convierte en una página. `vistas/panel_ia.py` es el precedente.
"""

import streamlit as st

from seguimiento import libro as mod


def disponibles() -> "tuple[list[mod.Entrada], dict[str, mod.Entrada]]":
    """Lo que hay en disco y lo que de eso se puede elegir.

    **Un fichero ilegible se nombra con su motivo.** Filtrarlo en silencio y
    decir después que no llevas ningún libro convierte «no puedo leer el tuyo»
    en «no tienes ninguno»: son cosas opuestas, y la segunda deja al usuario sin
    nada que buscar.

    Y no se ofrece borrarlo, al revés que en `vistas/portafolios.py`: allí lo
    peor que se pierde es una fotografía que se puede volver a sacar, y aquí es
    el historial entero de lo que alguien compró.

    Devuelve las dos listas porque no dicen lo mismo, y cada pantalla corta
    distinto: «no hay ningún libro» se responde invitando a empezar uno, y «los
    que hay no se leen» ya está dicho arriba con el error de cada fichero.
    """
    entradas = mod.listar()
    for entrada in entradas:
        if entrada.libro is None:
            st.error(f"`{entrada.ruta.name}` no se puede leer: {entrada.error}")
    return entradas, mod.etiquetas_de(entradas)


def desplegable(etiquetas: "dict[str, mod.Entrada]", contenedor=None) -> mod.Entrada:
    """El desplegable, con la clave compartida puesta. Devuelve lo elegido.

    `contenedor` es la columna donde va, o la página si no se dice: en
    Seguimiento comparte renglón con el nombre del libro y en las otras dos va
    a lo ancho.

    `fijar_eleccion` **tiene que correr antes** de pintar el widget, y no es un
    detalle de orden: Streamlit lee `session_state` por la `key` y tumba la
    pasada entera si encuentra ahí una opción que no está en `options`. Como la
    clave la comparten tres pantallas y las tres listan el disco por su cuenta,
    ese valor huérfano es un caso normal —un fichero borrado desde fuera, uno
    que se volvió ilegible— y no una rareza.
    """
    mod.fijar_eleccion(etiquetas, st.session_state)
    caja = st if contenedor is None else contenedor
    elegida = caja.selectbox(
        "Libro", options=list(etiquetas), key=mod.CLAVE_SELECCION
    )
    return etiquetas[elegida]
