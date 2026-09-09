"""Lo que el panel enseña de las noticias, decidido fuera de la pantalla.

**Aqui no se descarga nada.** El panel de seguimiento lee lo que la cache ya
tenga y ofrece un boton para traer el resto: con doce activos, descargar al
abrir serian veinticuatro llamadas, y un fallo de red dejaria la cartera
arrancando con errores encima de las cifras. Abrir tu cartera no puede depender
de que la red responda. Por eso `resumir` recibe `traer.cacheado` --que lee el
disco y no toca la red-- y no `traer.traer`.

## Los tres estados no se dicen igual

| Estado | Que significa | Que se dice |
|---|---|---|
| `SIN_CACHE` | no hay **nada** guardado de ningun activo | «No hay noticias descargadas todavia» |
| `VIEJA` | hay, pero algo se salio de su ventana de frescura | se pinta **diciendo de cuando es** |
| `AL_DIA` | hay y esta dentro de su ventana | se pinta, y si no hay 8-K se dice |

Los tres son distintos y **decirlos igual seria mentir en dos de ellos**. El
caso que mas se confunde es el ultimo contra el primero: «este activo no ha
presentado ningun 8-K material» y «no hemos mirado si lo ha presentado» se
pintan igual de vacios y son cosas opuestas. El primero es una respuesta; el
segundo es la ausencia de una. Por eso el estado se devuelve como un dato y no
se deduce de que las listas vengan vacias --de esa deduccion salen los dos
iguales.
"""

from dataclasses import dataclass
from datetime import datetime

from noticias import traer

# Las dos fuentes que el panel lee. El calendario --«agenda»-- no entra: el
# panel enseña lo que **paso**, y lo que viene tiene su sitio en la pantalla
# completa. Meterlo aqui obligaria a mezclar fechas futuras con fechas pasadas
# en el mismo bloque corto, que es justo lo que la pantalla de Noticias separa.
FUENTES = ("hechos", "prensa")

SIN_CACHE = "sin_cache"
VIEJA = "vieja"
AL_DIA = "al_dia"

# Pocos, a proposito: esto es un panel y no la pantalla de Noticias. Lo que no
# cabe no se esconde, se cuenta y se manda alli.
TOPE_HECHOS = 6
TOPE_TITULARES = 5


@dataclass(frozen=True)
class Resumen:
    """Lo que hay para pintar, y de cuando es.

    `hechos` son **solo los materiales**, que es donde el programa tiene un
    criterio congelado y defendible (`noticias/criterio.py`). El tramite no
    sube al panel: en la pantalla completa se pliega, y aqui no hay sitio ni
    para plegarlo.
    """

    estado: str
    # Materiales, del mas reciente al mas viejo. Sin recortar: quien pinta
    # recorta con `TOPE_HECHOS` y dice cuantos dejo fuera, porque un recorte
    # silencioso es indistinguible de que no hubiera mas.
    hechos: tuple
    titulares: tuple
    # La marca MAS ANTIGUA de todo lo que se esta enseñando, no la mas nueva.
    # Es la antiguedad de lo peor que estas mirando, y lo que se enseña tiene
    # que poder defenderse entero. Es la misma regla que el pie de
    # `vistas/noticias.py`. `None` solo cuando el estado es `SIN_CACHE`.
    cuando: "datetime | None"
    # Los activos de los que no hay **nada** guardado. Se nombran en vez de
    # contarse: saber que faltan cuatro no dice cuales, y de los que faltan no
    # se esta enseñando nada aunque el panel parezca lleno.
    sin_cachear: "tuple[str, ...]"
    # Los que tienen algo guardado pero fuera de su ventana de validez.
    caducados: "tuple[str, ...]"


def resumir(tickers, cacheado=traer.cacheado) -> Resumen:
    """Lo que la cache tenga de estos activos, **sin tocar la red**.

    `cacheado` se inyecta para que los tests puedan fijar cada caso sin montar
    un directorio de cache: lo que hay que probar es que a cada situacion le
    corresponde un estado, y eso no depende de como se serializa un `Hecho`.
    Por defecto es `traer.cacheado`, que es el unico que se usa en la app.

    Un ticker cuenta como cacheado si **alguna** de las dos fuentes tiene algo.
    Exigir las dos dejaria en `sin_cachear` a un activo del que si se estan
    enseñando titulares, y entonces el aviso de arriba contradiria a la lista
    de abajo.
    """
    hechos: list = []
    titulares: list = []
    marcas: list = []          # (cuando, vigente, ticker)
    sin_cachear: list = []

    recogido = {"hechos": hechos, "prensa": titulares}

    for ticker in tickers:
        tiene_algo = False
        for fuente in FUENTES:
            guardado = cacheado(fuente, ticker)
            if guardado is None:
                continue
            datos, cuando, vigente = guardado
            tiene_algo = True
            recogido[fuente].extend(datos)
            marcas.append((cuando, vigente, ticker))
        if not tiene_algo:
            sin_cachear.append(ticker)

    if not marcas:
        # Ni una sola fuente de ni un solo activo. **Este es el caso que no se
        # puede confundir con «no hay 8-K»**: no se ha mirado. Se devuelve
        # explicito y no se deja que quien pinte lo deduzca de unas listas
        # vacias, porque de esa deduccion salen los dos casos iguales.
        return Resumen(
            estado=SIN_CACHE,
            hechos=(),
            titulares=(),
            cuando=None,
            sin_cachear=tuple(tickers),
            caducados=(),
        )

    # El criterio ya decidio al bajarlos (`noticias/criterio.py`): aqui solo se
    # filtra por la marca que trae puesta. Volver a mirar los tipos a mano
    # pondria un segundo criterio en el programa, y el dia que se moviera uno
    # el otro se quedaria atras sin que nadie lo notara.
    materiales = sorted(
        (h for h in hechos if h.material), key=lambda h: h.cuando, reverse=True
    )
    titulares.sort(key=lambda n: n.cuando, reverse=True)

    caducados = sorted({t for _, vigente, t in marcas if not vigente})
    return Resumen(
        estado=VIEJA if caducados else AL_DIA,
        hechos=tuple(materiales),
        titulares=tuple(titulares),
        cuando=min(cuando for cuando, _, _ in marcas),
        sin_cachear=tuple(sin_cachear),
        caducados=tuple(caducados),
    )
