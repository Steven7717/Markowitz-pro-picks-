"""Los tres estados vacios del panel de noticias, que no son el mismo vacio.

El panel de seguimiento lee la cache y **no descarga al abrir**, asi que casi
siempre esta pintando algo incompleto: falta un activo, o lo que hay es de
ayer, o esta al dia y ese activo simplemente no ha presentado ningun 8-K. Los
tres se pintan igual de vacios y significan cosas opuestas:

- «no lo hemos mirado» no es una respuesta;
- «lo miramos ayer» es una respuesta con fecha;
- «lo miramos hace diez minutos y no hay nada» **si** es una respuesta.

Decirlos con la misma frase seria mentir en dos de los tres, y es un error que
no deja rastro: la pantalla se ve bien en los tres casos.

Sin red y sin disco: `resumir` recibe la funcion de cache, asi que cada caso se
fija a mano. Lo que se prueba es el reparto de estados, que no depende de como
se serializa un `Hecho`.
"""

from datetime import date, datetime, timedelta, timezone

from noticias import prensa, resumen
from noticias.hechos import Hecho

AHORA = datetime.now(timezone.utc)
AYER = AHORA - timedelta(days=1)

MATERIAL = Hecho(
    ticker="AAPL",
    tipos=("2.02",),
    descripciones=("Resultados",),
    url="https://www.sec.gov/Archives/edgar/data/320193/x.htm",
    cuando=date(2026, 9, 8),
    enmienda=False,
    material=True,
)

TITULAR = prensa.Noticia(
    ticker="AAPL",
    titular="Apple pasa de $4T",
    resumen="",
    medio="Reuters",
    url="https://example.invalid/x",
    cuando=AHORA - timedelta(hours=3),
    clase="STORY",
)


def cache_de(contenido: dict):
    """Una cache de mentira: `{(fuente, ticker): (datos, cuando, vigente)}`.

    Lo que no este en el diccionario devuelve `None`, que es exactamente lo que
    `traer.cacheado` devuelve cuando no hay fichero.
    """
    return lambda fuente, ticker: contenido.get((fuente, ticker))


def test_no_haber_mirado_no_es_lo_mismo_que_no_haber_nada():
    """El caso que se confunde: cache vacia contra activo al dia y sin 8-K.

    Los dos dejan `hechos` vacio. Si el estado tambien saliera igual, la
    pantalla no tendria con que distinguirlos y diria «sin hechos recientes»
    --que afirma que se miro-- de un activo que nadie ha consultado nunca.
    """
    vacia = resumen.resumir(["AAPL"], cacheado=cache_de({}))

    assert vacia.estado == resumen.SIN_CACHE
    assert vacia.hechos == ()
    # Y se dice de quien no se sabe nada, en vez de contar cuantos faltan.
    assert vacia.sin_cachear == ("AAPL",)
    # No hay ninguna fecha que enseñar: poner la de hoy afirmaria que se
    # consulto hoy, que es justo lo que no ha pasado.
    assert vacia.cuando is None

    mirado = resumen.resumir(["AAPL"], cacheado=cache_de({
        # Se pregunto hace un momento y la SEC no devolvio ningun 8-K. Es una
        # respuesta, y ademas es lo normal fuera de temporada de resultados.
        ("hechos", "AAPL"): ((), AHORA, True),
        ("prensa", "AAPL"): ((TITULAR,), AHORA, True),
    }))

    assert mirado.estado == resumen.AL_DIA
    assert mirado.hechos == ()
    assert mirado.sin_cachear == ()
    # Los dos casos dejan `hechos` vacio: es el estado, y solo el estado, lo
    # que los separa.
    assert mirado.hechos == vacia.hechos
    assert mirado.estado != vacia.estado


def test_lo_viejo_se_pinta_marcado_como_viejo_y_no_se_esconde():
    """Caducado no es vacio: se enseña, con la fecha de lo peor que se enseña.

    Filtrar lo caducado convertiria «esto es de ayer» en «no hay nada», que es
    el primer caso otra vez. Y la fecha que se devuelve es la MAS ANTIGUA de
    todas, no la mas nueva: es la antiguedad de lo peor que estas mirando.
    """
    viejo = resumen.resumir(["AAPL", "MSFT"], cacheado=cache_de({
        ("hechos", "AAPL"): ((MATERIAL,), AYER, False),
        ("prensa", "AAPL"): ((TITULAR,), AHORA, True),
        ("hechos", "MSFT"): ((), AHORA, True),
    }))

    assert viejo.estado == resumen.VIEJA
    assert viejo.caducados == ("AAPL",)
    # El hecho sigue ahi. Un 8-K de ayer marcado como de ayer es util; una
    # ausencia silenciosa no.
    assert viejo.hechos == (MATERIAL,)
    assert viejo.cuando == AYER
    # De MSFT hay algo guardado --su consulta de hechos-- aunque venga vacia,
    # asi que no esta «sin cachear»: se pregunto y no habia nada.
    assert viejo.sin_cachear == ()
