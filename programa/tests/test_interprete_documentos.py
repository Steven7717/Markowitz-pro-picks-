"""El texto de un 8-K: de donde se saca y como se recorta."""

import pytest

from interprete import documentos
from noticias import hechos


class _Anexo:
    def __init__(self, tipo, cuerpo):
        self.document_type = tipo
        self._cuerpo = cuerpo

    def text(self):
        return self._cuerpo


class _Expediente:
    def __init__(self, cuerpo, anexos=()):
        self._cuerpo = cuerpo
        self.attachments = list(anexos)

    def text(self):
        return self._cuerpo


CUERPO = (
    "UNITED STATES\n\nSECURITIES AND EXCHANGE COMMISSION\n\n" + "caratula " * 300
    + "\n\nItem 5.02      Departure of Directors\n\n"
    "On June 2, 2026, Reid Hoffman informed the Board of his decision.\n\n"
    "SIGNATURE\n\nPursuant to the requirements of the Act, " + "firma " * 50
)


def test_recorta_entre_el_item_y_la_firma():
    trozo = documentos.recortar(CUERPO)
    assert trozo.startswith("Item 5.02")
    assert "Reid Hoffman" in trozo
    assert "caratula" not in trozo
    assert "Pursuant to the requirements" not in trozo


def test_el_espacio_fino_tambien_cuenta():
    """MSFT escribe «Item 5.02». Un literal " " se lo salta y devuelve el
    documento entero: no revienta, solo encarece y ensucia el prompt."""
    con_fino = CUERPO.replace("Item 5.02", "Item 5.02")
    trozo = documentos.recortar(con_fino)
    assert "caratula" not in trozo
    assert "Reid Hoffman" in trozo


def test_sin_marcas_se_devuelve_entero():
    """De las dos formas de equivocarse, mandar caratula de mas es cara y
    mandar el contenido de menos es mentir."""
    suelto = "Un documento sin Item ni firma, pero con contenido real."
    assert documentos.recortar(suelto) == suelto


def test_la_firma_antes_del_item_no_recorta():
    raro = "SIGNATURE al principio\n\nItem 2.02 y despues el contenido"
    assert documentos.recortar(raro) == raro


def test_el_anexo_gana_al_cuerpo():
    """Medido: el cuerpo del 2.02 de MSFT son 3.579 caracteres de caratula y
    una frase de reenvio; el EX-99.1 son 52.823 con la nota de prensa."""
    assert documentos.elegir("el cuerpo", ["la nota de prensa"]) == "la nota de prensa"


def test_sin_anexo_se_usa_el_cuerpo_recortado():
    assert documentos.elegir(CUERPO, []).startswith("Item 5.02")


def test_varios_anexos_se_juntan():
    assert documentos.elegir("cuerpo", ["uno", "dos"]) == "uno\n\ndos"


def test_el_tope_corta_por_el_final_y_lo_dice():
    """Por el final: una nota de prensa pone las cifras y el titular arriba."""
    texto, recortado = documentos.aplicar_tope("abcdef", tope=3)
    assert (texto, recortado) == ("abc", True)


def test_lo_que_cabe_no_se_marca_como_recortado():
    assert documentos.aplicar_tope("abc", tope=3) == ("abc", False)


def test_los_identificadores_salen_de_la_url_que_escribe_hechos():
    """**Este test es el que ata los dos modulos.** `documentos` reconstruye el
    numero de acceso parseando la url que `hechos._url` escribe. Si alguien
    cambia ese formato, esto deja de encontrar nada **y no revienta**: los
    hechos caerian en `sin_documento` como si fuera un fallo de red."""
    url = hechos._url(789019, "0001193125-26-323632", "msft-20260729.htm")
    assert documentos.identificadores(url) == (789019, "0001193125-26-323632")


def test_una_url_sin_forma_de_expediente_no_da_identificadores():
    assert documentos.identificadores("https://example.com/algo.htm") is None


def test_url_rota_no_llega_a_la_red():
    """`hechos._url` escribe `.../data/789019//doc.htm` cuando el indice viene
    sin numero de acceso. Eso no es un fallo de red y no debe gastarse una."""
    def _explota(_accession):
        raise AssertionError("no se debe tocar la red con una url rota")

    doc = documentos.texto_de("https://www.sec.gov/Archives/edgar/data/789019//d.htm",
                              buscar=_explota)
    assert doc.texto == ""
    assert "no tiene forma" in doc.problema


def test_texto_de_prefiere_el_anexo():
    expediente = _Expediente(CUERPO, [_Anexo("EX-99.1", "la nota de prensa entera")])
    url = hechos._url(789019, "0001193125-26-323632", "d.htm")
    doc = documentos.texto_de(url, buscar=lambda _a: expediente)
    assert doc.texto == "la nota de prensa entera"
    assert doc.problema == ""
    assert doc.recortado is False


def test_texto_de_ignora_los_anexos_que_no_son_ex99():
    """Un 8-K trae 35 adjuntos: esquemas XBRL, jpgs, css, js. Medido en MSFT."""
    expediente = _Expediente(
        CUERPO,
        [_Anexo("EX-101.SCH", "esquema xbrl"), _Anexo("GRAPHIC", "una foto")],
    )
    url = hechos._url(789019, "0001193125-26-323632", "d.htm")
    doc = documentos.texto_de(url, buscar=lambda _a: expediente)
    assert doc.texto.startswith("Item 5.02")


def test_un_fallo_de_red_vuelve_como_texto_y_no_lanza():
    """Misma regla que `noticias/fuentes.py`: que se caiga la pantalla entera
    por un expediente es peor que ensenar los otros cinco."""
    def _revienta(_accession):
        raise RuntimeError("la SEC no responde")

    url = hechos._url(789019, "0001193125-26-323632", "d.htm")
    doc = documentos.texto_de(url, buscar=_revienta)
    assert doc.texto == ""
    assert "la SEC no responde" in doc.problema


def test_sin_edgar_identity_no_se_toca_la_red(monkeypatch):
    """La guarda tiene que comprobarse interceptando la descarga y no por el
    texto del error: `edgartools` lanza `IdentityNotSetError` con la cadena
    EDGAR_IDENTITY dentro, asi que un test por subcadena pasa con guarda y sin
    ella. Eso ya paso en H y el test era decorativo."""
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)

    def _explota(_accession):
        raise AssertionError("no se debe tocar la red sin EDGAR_IDENTITY")

    url = hechos._url(789019, "0001193125-26-323632", "d.htm")
    doc = documentos.texto_de(url, buscar=_explota)
    assert "EDGAR_IDENTITY" in doc.problema


@pytest.mark.red
def test_red_un_expediente_real_trae_su_anexo():
    import os
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("sin EDGAR_IDENTITY")
    url = hechos._url(789019, "0001193125-26-323632", "msft-20260729.htm")
    doc = documentos.texto_de(url)
    assert doc.problema == ""
    # El EX-99.1 medido el 2026-09-10 tenia 52.823 caracteres; el cuerpo 3.579.
    # No se fija el numero, que cambiara: se fija que gano el anexo.
    assert len(doc.texto) > 20_000
    assert "�" not in doc.texto
