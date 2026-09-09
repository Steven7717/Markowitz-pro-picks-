"""Traer noticias: lo cacheado, lo descargado, y la puerta que no toca la red.

`cacheado` existe para que abrir Seguimiento no dependa de que la red responda.
Con doce activos en el libro serian doce llamadas al abrir la pantalla, y un
fallo dejaria la cartera arrancando con errores encima de las cifras.
"""

import json

import pytest

from noticias import cache, traer

_CRUDOS = [{
    "ticker": "AAPL", "titular": "algo", "fuente": "X",
    "url": "https://x/y", "cuando": "2020-01-01T00:00:00+00:00",
}]


class _Explota:
    """Cualquier intento de descargar revienta el test en el acto.

    Es la unica forma de comprobar que `cacheado` NO toca la red: si se limita
    a mirar el resultado, un `cacheado` que descargase en silencio devolveria
    exactamente lo mismo y el test pasaria.
    """

    def __call__(self, ticker):
        raise AssertionError(f"cacheado descargo {ticker}, y no debia tocar la red")


@pytest.fixture
def cache_vacia(tmp_path, monkeypatch):
    monkeypatch.setattr(traer, "RAIZ_CACHE", tmp_path)
    for fuente in ("prensa", "hechos", "agenda"):
        monkeypatch.setitem(traer.DESCARGA, fuente, _Explota())
    return tmp_path


def test_cacheado_sobre_una_cache_vacia_no_descarga_nada(cache_vacia):
    """Devuelve `None` y se calla. No hay red de por medio."""
    assert traer.cacheado("prensa", "AAPL") is None


def _envejecer(raiz, fuente):
    """Retrasa el sello de la entrada cacheada, que es lo que decide `vigente`.

    `cache.guardar` sella con la hora de escritura, asi que la fecha que lleve
    la noticia por dentro no envejece nada: lo que caduca es **cuando se
    descargo**, no cuando ocurrio.
    """
    fichero = next((raiz / fuente).glob("*.json"))
    crudo = json.loads(fichero.read_text(encoding="utf-8"))
    crudo["cuando"] = "2020-01-01T00:00:00+00:00"
    fichero.write_text(json.dumps(crudo), encoding="utf-8")


def test_lo_viejo_vuelve_marcado_como_viejo_en_vez_de_esconderse(cache_vacia):
    """Una noticia vieja etiquetada de vieja es util; una ausencia no.

    Es la misma regla que H aplica en toda la pantalla de noticias: lo que se
    pinta lleva de cuando es.
    """
    cache.guardar(cache_vacia, "prensa", "AAPL", _CRUDOS)
    _envejecer(cache_vacia, "prensa")

    resultado = traer.cacheado("prensa", "AAPL")
    assert resultado is not None
    _datos, cuando, vigente = resultado
    assert vigente is False, "una descarga de 2020 no puede seguir vigente"
    assert cuando is not None, "y aun asi se dice de cuando es"


def test_lo_reciente_vuelve_vigente(cache_vacia):
    """La otra mitad: si esta dentro de su ventana, se dice que lo esta."""
    cache.guardar(cache_vacia, "prensa", "AAPL", _CRUDOS)

    _datos, _cuando, vigente = traer.cacheado("prensa", "AAPL")
    assert vigente is True
