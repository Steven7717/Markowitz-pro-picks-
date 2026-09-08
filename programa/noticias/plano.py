# noticias/plano.py
"""Las dataclases de H, de ida y vuelta por el JSON de la cache.

`cache.guardar` serializa con `json.dumps(..., default=str)`. Una dataclase
pasada tal cual no revienta: se guarda como su `repr`, una cadena, y vuelve del
disco convertida en texto sin que nada lo delate. La pantalla funcionaria la
primera vez --con los objetos recien descargados-- y se rompería en la segunda
pasada, cuando los mismos datos llegasen del fichero. Ese es exactamente el
fallo que se ve tarde: el que aparece cuando alguien vuelve a abrir la pantalla.

De ahi la regla de este modulo: **la cache guarda diccionarios y la pantalla
recibe siempre dataclases**, vengan de la red o del disco. `aplanar` es lo unico
que escribe en la cache, `reconstruir` lo unico que la lee, y el camino recien
descargado pasa tambien por los dos. Asi no hay ningun tipo que solo exista en
la primera pasada.

El JSON no distingue tupla de lista ni fecha de cadena, asi que la vuelta no es
automatica: `Hecho.tipos` volveria como lista y `Hecho.cuando` como texto. Aqui
se reponen los dos. De paso se normaliza lo que llega de pandas: `filing_date`
puede venir como `Timestamp`, y como el camino fresco tambien da la vuelta
completa, los dos caminos entregan `datetime.date` y no uno cada cosa.
"""

from dataclasses import asdict, is_dataclass
from datetime import date, datetime

from noticias import criterio
from noticias.agenda import Evento
from noticias.hechos import Hecho
from noticias.prensa import Noticia


def _llano(valor):
    """Lo mismo, en algo que `json.dumps` sepa escribir sin `default=str`.

    `datetime` antes que `date` porque el primero hereda del segundo: al reves,
    una hora se guardaria como su dia y la hora se perderia en silencio.
    """
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return [_llano(v) for v in valor]
    return valor


def _fecha(valor) -> "date | None":
    """Un dia, venga como venga, o None si no hay ninguno legible.

    Corta a diez caracteres a proposito: un `Timestamp` aplanado trae
    "2026-09-01T00:00:00" y `date.fromisoformat` no lo acepta entero.
    """
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _momento(valor) -> "datetime | None":
    if isinstance(valor, datetime):
        return valor
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def _texto(valor, defecto: str = "") -> str:
    return defecto if valor is None else str(valor)


def _noticia(crudo: dict) -> "Noticia | None":
    cuando = _momento(crudo.get("cuando"))
    if cuando is None:
        return None
    return Noticia(
        ticker=_texto(crudo.get("ticker")),
        titular=_texto(crudo.get("titular")),
        resumen=_texto(crudo.get("resumen")),
        medio=_texto(crudo.get("medio")),
        url=_texto(crudo.get("url")),
        cuando=cuando,
        clase=_texto(crudo.get("clase"), "ARTICLE"),
    )


def _hecho(crudo: dict) -> "Hecho | None":
    cuando = _fecha(crudo.get("cuando"))
    if cuando is None:
        return None
    tipos = tuple(_texto(t) for t in (crudo.get("tipos") or ()))
    return Hecho(
        ticker=_texto(crudo.get("ticker")),
        tipos=tipos,
        descripciones=tuple(
            _texto(d) for d in (crudo.get("descripciones") or ())
        ),
        url=_texto(crudo.get("url")),
        cuando=cuando,
        enmienda=bool(crudo.get("enmienda")),
        # Se **recalcula** desde los tipos en vez de releer la bandera guardada,
        # y no es lo mismo. Un fichero escrito por una version anterior podria
        # no traer la clave, `bool(None)` seria False, y un anuncio de
        # resultados quedaria plegado entre la rutina sin que nada avisara --
        # justo el defecto que este sub-proyecto existe para evitar. Llamar a
        # `criterio.material` no anade un segundo criterio: es el mismo y el
        # unico, el que ya uso `hechos.desde_indice` al bajarlo.
        material=criterio.material(tipos),
    )


def _evento(crudo: dict) -> "Evento | None":
    ticker = crudo.get("ticker")
    url = crudo.get("url")
    return Evento(
        ticker=None if ticker is None else _texto(ticker),
        clase=_texto(crudo.get("clase")),
        # Se admite None: `Evento` lo admite para lo macro. Los de la agenda
        # siempre traen fecha, y la pantalla filtra por si acaso.
        cuando=_fecha(crudo.get("cuando")),
        detalle=_texto(crudo.get("detalle")),
        url=None if url is None else _texto(url),
    )


CONSTRUCTORES = {
    "prensa": _noticia,
    "hechos": _hecho,
    "agenda": _evento,
}


def aplanar(objetos) -> list:
    """Las dataclases como diccionarios de tipos que el JSON sabe escribir."""
    return [
        {k: _llano(v) for k, v in asdict(o).items()}
        for o in (objetos or ())
        if is_dataclass(o)
    ]


def reconstruir(fuente: str, crudos) -> tuple:
    """Lo que devolvio la cache, otra vez como dataclases.

    Lo que no se puede reconstruir se cae, no lanza. Una cache se regenera --y
    la de aqui caduca en una hora-- asi que tumbar la pantalla por un fichero
    a medio escribir seria cambiar un hueco de un dia por una pagina en blanco.
    Es la misma decision que ya toma `cache.leer` con el JSON corrupto.
    """
    construir = CONSTRUCTORES[fuente]
    salida = []
    for crudo in crudos or ():
        if not isinstance(crudo, dict):
            continue
        objeto = construir(crudo)
        if objeto is not None:
            salida.append(objeto)
    return tuple(salida)
