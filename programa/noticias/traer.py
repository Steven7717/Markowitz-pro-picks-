# noticias/traer.py
"""La orquestacion de cache-o-descarga, fuera de la pantalla que la estreno.

Hasta el sub-proyecto K esto vivia dentro de `vistas/noticias.py`, que es un
guion de Streamlit y **no se puede importar**. El panel de seguimiento necesita
lo mismo, y desde un guion la unica forma de tenerlo habria sido copiarlo: dos
copias de una decision --cuando vale la cache, que se guarda, que se devuelve
cuando la red falla-- que se irian separando sin que nada avisara, porque las
dos seguirian dando datos plausibles.

`VALIDEZ` **no vive aqui**. Esta en `noticias/cache.py` y se lee de alli. Cuanto
dura una cache se mira en un solo sitio.
"""

import pathlib
from datetime import datetime, timezone

from noticias import cache, fuentes, plano

RAIZ_CACHE = pathlib.Path(__file__).resolve().parent / ".cache"

DESCARGA = {
    "agenda": fuentes.agenda_de,
    "hechos": fuentes.hechos_de,
    "prensa": fuentes.prensa_de,
}


def traer(fuente: str, ticker: str, descargar, forzar: bool):
    """Lo cacheado si sirve; si no, se descarga y se guarda.

    Devuelve `(datos, problema, cuando, vigente)`. `cuando` es None sólo cuando
    no hubo NI caché NI descarga con éxito, y en ese caso hay `problema`.

    Los datos vuelven **siempre** como dataclases y **siempre** por el mismo
    camino: hasta lo recién descargado se guarda, se relee y se reconstruye. Es
    más trabajo del imprescindible y se hace a propósito. Si el camino fresco
    devolviera los objetos directos y el camino de caché diccionarios
    reconstruidos, cualquier diferencia entre los dos —una tupla que vuelve
    como lista, una fecha que vuelve como texto— se estrenaría en la segunda
    pasada, cuando el usuario ya se fue y volvió. Ver `noticias/plano.py`.
    """
    validez = cache.VALIDEZ[fuente]

    if not forzar:
        guardado = cache.leer(RAIZ_CACHE, fuente, ticker, validez)
        if guardado and guardado.vigente:
            return (
                plano.reconstruir(fuente, guardado.datos),
                "",
                guardado.cuando,
                True,
            )

    traida = descargar(ticker)
    if traida.problema:
        # La descarga falló: si hay algo viejo en caché es mejor que nada, pero
        # se devuelve MARCADO como viejo. Nunca en silencio.
        viejo = cache.leer(RAIZ_CACHE, fuente, ticker, validez)
        if viejo:
            return (
                plano.reconstruir(fuente, viejo.datos),
                traida.problema,
                viejo.cuando,
                False,
            )
        return (), traida.problema, None, False

    llano = plano.aplanar(traida.datos)
    try:
        cache.guardar(RAIZ_CACHE, fuente, ticker, llano)
        guardado = cache.leer(RAIZ_CACHE, fuente, ticker, validez)
    except OSError:
        guardado = None
    # Que la caché no se pueda escribir es un problema de la caché, no de los
    # datos: se enseña lo que se acaba de traer, por el mismo `reconstruir`
    # para que el tipo no dependa de si el disco dejó escribir.
    if guardado is None:
        return (
            plano.reconstruir(fuente, llano),
            "",
            datetime.now(timezone.utc),
            True,
        )
    return plano.reconstruir(fuente, guardado.datos), "", guardado.cuando, True


def cacheado(fuente: str, ticker: str):
    """Lo que haya en cache, sin tocar la red. `None` si no hay nada.

    Es lo que hace que abrir Seguimiento no dependa de que la red responda.
    Devuelve `(datos, cuando, vigente)`: `vigente` dice si esta dentro de su
    ventana de validez, y **se devuelve en vez de filtrarse** porque una noticia
    vieja marcada como vieja es util y una ausencia silenciosa no.
    """
    guardado = cache.leer(RAIZ_CACHE, fuente, ticker, cache.VALIDEZ[fuente])
    if guardado is None:
        return None
    return (
        plano.reconstruir(fuente, guardado.datos),
        guardado.cuando,
        guardado.vigente,
    )
