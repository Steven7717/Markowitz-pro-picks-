"""La coherencia entre lo que se descarga y lo que vuelve de la cache.

El fallo que estos tests existen para impedir no se ve en la primera pasada.
`cache.guardar` serializa a JSON, asi que si la pantalla guardara dataclases y
las releyera sin reconstruirlas, el camino "recien descargado" entregaria
`Noticia` y el camino "desde cache" entregaria diccionarios --o peor, la cadena
del `repr`, porque `json.dumps(..., default=str)` no lanza--. La pantalla
funcionaria al abrirla y se rompería al volver a ella. De ahi que casi todos
los de abajo comparen los dos caminos entre si, y no cada uno con lo que
esperaba.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from noticias import cache, hechos as hechos_mod, macro, plano
from noticias.agenda import Evento
from noticias.hechos import Hecho
from noticias.prensa import Noticia

AHORA = datetime(2026, 9, 8, 19, 56, tzinfo=timezone.utc)

NOTICIAS = (
    Noticia(
        ticker="AAPL",
        titular="Apple pasa de $4T y el $SPX no se entera",
        resumen="Un resumen con *asteriscos* y [corchetes].",
        medio="Barrons.com",
        url="https://ejemplo.test/a?x=1&y=2",
        cuando=AHORA,
        clase="STORY",
    ),
    Noticia(
        ticker="AAPL",
        titular="Sin enlace",
        resumen="",
        medio="",
        url="",
        cuando=AHORA - timedelta(hours=3),
        clase="VIDEO",
    ),
)

HECHOS = (
    Hecho(
        ticker="AAPL",
        tipos=("2.02", "9.01"),
        descripciones=("Resultados", "Estados financieros y anexos"),
        url="https://www.sec.gov/Archives/edgar/data/320193/000/a.htm",
        cuando=date(2026, 7, 30),
        enmienda=False,
        material=True,
    ),
    Hecho(
        ticker="AAPL",
        tipos=("5.07",),
        descripciones=("Votacion de accionistas",),
        url="https://www.sec.gov/Archives/edgar/data/320193/001/b.htm",
        cuando=date(2026, 2, 24),
        enmienda=True,
        material=False,
    ),
)

EVENTOS = (
    Evento("AAPL", "resultados", date(2026, 10, 29), "Resultados", None),
    Evento("AAPL", "ex-dividendo", date(2026, 11, 7), "Ultimo dia", None),
)

CASOS = (("prensa", NOTICIAS), ("hechos", HECHOS), ("agenda", EVENTOS))


@pytest.fixture
def dir_cache(tmp_path):
    return tmp_path / ".cache"


# --- La ida y la vuelta ------------------------------------------------------


@pytest.mark.parametrize("fuente,originales", CASOS)
def test_lo_aplanado_es_json_de_verdad(fuente, originales):
    """Sin `default=str`, que es la red que tapa el fallo.

    `cache.guardar` lo lleva puesto, asi que una dataclase colada ahi no
    reventaria: se guardaria como su `repr`. Aqui se exige que lo que sale de
    `aplanar` sea serializable por si mismo.
    """
    json.dumps(plano.aplanar(originales))


@pytest.mark.parametrize("fuente,originales", CASOS)
def test_la_vuelta_devuelve_lo_mismo(fuente, originales):
    vueltos = plano.reconstruir(fuente, plano.aplanar(originales))
    assert vueltos == tuple(originales)


@pytest.mark.parametrize("fuente,originales", CASOS)
def test_los_dos_caminos_dan_el_mismo_tipo(fuente, originales, dir_cache):
    """El test central: recien descargado y desde cache, indistinguibles.

    Pasa por `cache.guardar` y `cache.leer` de verdad --no por un JSON de
    laboratorio-- porque el fichero real es el que convierte las tuplas en
    listas y las fechas en cadenas.
    """
    cache.guardar(dir_cache, fuente, "AAPL", plano.aplanar(originales))
    guardado = cache.leer(dir_cache, fuente, "AAPL", timedelta(hours=1))

    fresco = plano.reconstruir(fuente, plano.aplanar(originales))
    desde_cache = plano.reconstruir(fuente, guardado.datos)

    assert desde_cache == fresco
    assert [type(o) for o in desde_cache] == [type(o) for o in fresco]
    assert desde_cache == tuple(originales)


def test_las_tuplas_no_vuelven_como_listas(dir_cache):
    """JSON no distingue tupla de lista, y `Hecho.tipos` es tupla.

    Sin reponerlas, `h.tipos == ("2.02", "9.01")` seria False en la segunda
    pasada y True en la primera.
    """
    cache.guardar(dir_cache, "hechos", "AAPL", plano.aplanar(HECHOS))
    guardado = cache.leer(dir_cache, "hechos", "AAPL", timedelta(hours=1))
    hecho = plano.reconstruir("hechos", guardado.datos)[0]
    assert isinstance(hecho.tipos, tuple)
    assert isinstance(hecho.descripciones, tuple)
    assert hecho.tipos == ("2.02", "9.01")


def test_las_fechas_no_vuelven_como_texto(dir_cache):
    """`{h.cuando:%d/%m/%Y}` sobre una cadena lanza, y lo hace en pantalla."""
    cache.guardar(dir_cache, "hechos", "AAPL", plano.aplanar(HECHOS))
    guardado = cache.leer(dir_cache, "hechos", "AAPL", timedelta(hours=1))
    hecho = plano.reconstruir("hechos", guardado.datos)[0]
    assert isinstance(hecho.cuando, date)
    assert f"{hecho.cuando:%d/%m/%Y}" == "30/07/2026"

    cache.guardar(dir_cache, "prensa", "AAPL", plano.aplanar(NOTICIAS))
    leido = cache.leer(dir_cache, "prensa", "AAPL", timedelta(hours=1))
    noticia = plano.reconstruir("prensa", leido.datos)[0]
    assert isinstance(noticia.cuando, datetime)
    assert noticia.cuando.tzinfo is not None


# --- Lo que llega de pandas --------------------------------------------------


def test_un_timestamp_de_pandas_acaba_siendo_un_date():
    """`filing_date` puede llegar como Timestamp segun la version de pandas.

    Si sólo el camino de cache lo normalizara, un `Timestamp` y un `date` para
    el mismo expediente convivirian en la pantalla. Por eso el camino fresco da
    la vuelta completa tambien: los dos terminan en `date`.
    """
    indice = pd.DataFrame(
        [{"form": "8-K", "filing_date": pd.Timestamp("2026-07-30"),
          "items": "2.02,9.01", "accession_number": "0000320193-26-000018",
          "primaryDocument": "aapl.htm"}]
    )
    crudos = hechos_mod.desde_indice("AAPL", 320193, indice)
    vueltos = plano.reconstruir("hechos", plano.aplanar(crudos))
    assert type(vueltos[0].cuando) is date
    assert vueltos[0].cuando == date(2026, 7, 30)


# --- El criterio, que no se guarda: se vuelve a aplicar ----------------------


def test_los_resultados_siguen_siendo_materiales_al_volver(dir_cache):
    """El defecto que mas teme el sub-proyecto, en su version diferida.

    Un anuncio de resultados es "2.02,9.01". Si `material` se releyera de la
    bandera guardada y un fichero viejo no la trajera, saldria plegado --y sólo
    a partir de la segunda visita.
    """
    cache.guardar(dir_cache, "hechos", "AAPL", plano.aplanar(HECHOS))
    guardado = cache.leer(dir_cache, "hechos", "AAPL", timedelta(hours=1))
    vueltos = plano.reconstruir("hechos", guardado.datos)
    assert [h.material for h in vueltos] == [True, False]


def test_sin_la_bandera_guardada_se_recalcula():
    """Un fichero de una version anterior no puede plegar unos resultados."""
    sin_bandera = [
        {"ticker": "AAPL", "tipos": ["2.02", "9.01"],
         "descripciones": ["Resultados", "Anexos"], "url": "u",
         "cuando": "2026-07-30", "enmienda": False},
        {"ticker": "AAPL", "tipos": ["5.07"], "descripciones": ["Votacion"],
         "url": "u", "cuando": "2026-02-24", "enmienda": False},
    ]
    vueltos = plano.reconstruir("hechos", sin_bandera)
    assert [h.material for h in vueltos] == [True, False]


def test_una_bandera_guardada_que_miente_no_manda():
    """La cache guarda datos, no veredictos: el criterio vive en un solo sitio."""
    mentira = [{"ticker": "AAPL", "tipos": ["5.07"], "descripciones": ["V"],
                "url": "u", "cuando": "2026-02-24", "enmienda": False,
                "material": True}]
    assert plano.reconstruir("hechos", mentira)[0].material is False


# --- Lo macro, que no pasa por la cache pero tiene la misma forma ------------


def test_un_evento_sin_fecha_sobrevive_la_vuelta():
    """`Evento.cuando` es None para lo macro, y None no es un error."""
    vueltos = plano.reconstruir("agenda", plano.aplanar(macro.PUNTEROS))
    assert vueltos == macro.PUNTEROS
    assert all(e.cuando is None for e in vueltos)


# --- Que no se caiga por la cache -------------------------------------------


def test_la_basura_no_revienta_la_pantalla():
    """Una cache se regenera; caerse por ella cambia un hueco por una pagina en
    blanco."""
    assert plano.reconstruir("prensa", None) == ()
    assert plano.reconstruir("prensa", ["no soy un dict", 7, None]) == ()
    assert plano.reconstruir("hechos", [{"ticker": "AAPL"}]) == ()
    assert plano.reconstruir("prensa", [{"cuando": "no es una fecha"}]) == ()


def test_lo_bueno_sobrevive_a_lo_malo():
    """Una fila ilegible no se lleva por delante a las que si lo son."""
    mezcla = plano.aplanar(NOTICIAS) + [{"titular": "sin fecha"}]
    assert len(plano.reconstruir("prensa", mezcla)) == len(NOTICIAS)


# --- Que las dos tablas no se separen ---------------------------------------


def test_hay_un_constructor_por_fuente_cacheada():
    """`VALIDEZ` y `CONSTRUCTORES` se recorren con la misma clave.

    Anadir una cuarta fuente a una sola de las dos daria un KeyError en la
    pantalla, y no aqui.
    """
    assert set(plano.CONSTRUCTORES) == set(cache.VALIDEZ)
