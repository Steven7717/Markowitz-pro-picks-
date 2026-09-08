from datetime import datetime, timezone

from noticias import prensa

# Copiado de la forma real de yfinance 1.6.0, sondeada el 2026-09-08.
CRUDO = {
    "id": "abc-123",
    "content": {
        "title": "Apple sube tras presentar el iPhone",
        "summary": "La accion subio un 2% en la sesion.",
        "description": '<p>La accion <a href="http://x">subio</a> un 2%.</p>',
        "pubDate": "2026-09-08T15:29:15Z",
        "displayTime": "",
        "contentType": "ARTICLE",
        "provider": {"displayName": "Reuters", "url": "http://r.com"},
        "canonicalUrl": {"url": "https://finance.yahoo.com/n/1", "site": "finance"},
    },
}


def test_extrae_los_campos():
    n = prensa.desde_crudo("AAPL", CRUDO)
    assert n.ticker == "AAPL"
    assert n.titular == "Apple sube tras presentar el iPhone"
    assert n.resumen == "La accion subio un 2% en la sesion."
    assert n.medio == "Reuters"
    assert n.url == "https://finance.yahoo.com/n/1"
    assert n.clase == "ARTICLE"
    assert n.cuando == datetime(2026, 9, 8, 15, 29, 15, tzinfo=timezone.utc)


def test_el_resumen_nunca_sale_de_description():
    """`description` viene en HTML crudo y volcarlo pintaria etiquetas.

    Se fija con `summary` vacio, que es cuando la tentacion de caer a
    `description` existe: el resultado correcto es cadena vacia, no HTML.
    """
    crudo = {"content": dict(CRUDO["content"], summary="")}
    n = prensa.desde_crudo("AAPL", crudo)
    assert n.resumen == ""
    assert "<" not in n.resumen


def test_la_fecha_no_sale_de_displayTime():
    """`displayTime` puede venir vacia, y venia vacia en el sondeo real."""
    crudo = {"content": dict(CRUDO["content"], displayTime="")}
    n = prensa.desde_crudo("AAPL", crudo)
    assert n.cuando.year == 2026


def test_provider_y_canonicalUrl_son_diccionarios():
    """Tratarlos como cadenas es el error natural, y da un medio ilegible."""
    n = prensa.desde_crudo("AAPL", CRUDO)
    assert n.medio == "Reuters"
    assert n.url.startswith("https://")


def test_un_video_se_marca_como_video():
    """Yahoo mete videos entre las noticias; el sondeo vio uno el primero."""
    crudo = {"content": dict(CRUDO["content"], contentType="VIDEO")}
    assert prensa.desde_crudo("AAPL", crudo).clase == "VIDEO"


def test_un_elemento_sin_titulo_se_descarta_sin_reventar():
    """Sin titular no hay nada que ensenar, pero tampoco motivo para caerse."""
    assert prensa.desde_crudo("AAPL", {"content": {"title": ""}}) is None


def test_un_elemento_sin_content_se_descarta():
    assert prensa.desde_crudo("AAPL", {"id": "x"}) is None


def test_las_noticias_salen_de_la_mas_nueva_a_la_mas_vieja():
    viejo = {"content": dict(CRUDO["content"], pubDate="2026-09-01T10:00:00Z")}
    nuevo = {"content": dict(CRUDO["content"], pubDate="2026-09-08T10:00:00Z")}
    salida = prensa.normalizar("AAPL", [viejo, nuevo])
    assert [n.cuando.day for n in salida] == [8, 1]


def test_una_lista_vacia_da_una_tupla_vacia():
    assert prensa.normalizar("AAPL", []) == ()
