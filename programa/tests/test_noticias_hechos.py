from datetime import date

import pandas as pd

from noticias import hechos

# Copiado de la forma real de edgartools 5.52 (to_pandas()), 2026-09-08.
INDICE = pd.DataFrame(
    [
        {"form": "8-K/A", "filing_date": date(2026, 9, 1), "items": "5.02",
         "accession_number": "0001140361-26-035325",
         "primaryDocument": "ef20081427_8ka.htm"},
        {"form": "8-K", "filing_date": date(2026, 7, 30), "items": "2.02,9.01",
         "accession_number": "0000320193-26-000018",
         "primaryDocument": "aapl-20260730.htm"},
        {"form": "8-K", "filing_date": date(2026, 2, 24), "items": "5.07,9.01",
         "accession_number": "0001140361-26-006577",
         "primaryDocument": "brhc10.htm"},
    ]
)


def test_parte_los_items_por_comas():
    assert hechos.partir("2.02,9.01") == ("2.02", "9.01")


def test_parte_un_item_solo():
    assert hechos.partir("5.02") == ("5.02",)


def test_parte_con_espacios_y_vacios():
    """La SEC ha servido ' 2.02 , 9.01 ' y tambien cadenas vacias."""
    assert hechos.partir(" 2.02 , 9.01 ") == ("2.02", "9.01")
    assert hechos.partir("") == ()
    assert hechos.partir(None) == ()


def test_los_resultados_salen_materiales():
    """El caso que un modelo de un solo tipo clasificaria mal.

    "2.02,9.01" es como llega SIEMPRE un anuncio de resultados. Si esto sale
    False, cada trimestre de cada activo queda plegado entre la rutina.
    """
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert resultados.material is True
    assert resultados.tipos == ("2.02", "9.01")


def test_una_votacion_de_accionistas_no_es_material():
    """Contrapeso: que no pase por 'dos items = material'."""
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    votacion = [h for h in salida if "5.07" in h.tipos][0]
    assert votacion.material is False


def test_la_enmienda_se_marca_y_no_desaparece():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    enmiendas = [h for h in salida if h.enmienda]
    assert len(enmiendas) == 1
    assert enmiendas[0].tipos == ("5.02",)


def test_no_se_descarta_ningun_expediente():
    """Destacar no es excluir: lo que H tirase, I no lo veria nunca."""
    assert len(hechos.desde_indice("AAPL", 320193, INDICE)) == len(INDICE)


def test_la_url_apunta_al_documento_real():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert resultados.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000018/aapl-20260730.htm"
    )


def test_las_descripciones_acompanan_a_los_tipos():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert "Resultados" in resultados.descripciones


def test_un_tipo_desconocido_no_revienta():
    """La SEC anade items; uno nuevo debe salir con su codigo, no caerse."""
    indice = pd.DataFrame(
        [{"form": "8-K", "filing_date": date(2026, 1, 1), "items": "9.99",
          "accession_number": "0000000000-26-000001",
          "primaryDocument": "x.htm"}]
    )
    h = hechos.desde_indice("AAPL", 1, indice)[0]
    assert h.tipos == ("9.99",)
    assert h.material is False
    assert "9.99" in h.descripciones[0]


def test_un_indice_vacio_da_tupla_vacia():
    assert hechos.desde_indice("AAPL", 1, pd.DataFrame()) == ()


def test_salen_del_mas_nuevo_al_mas_viejo():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    assert [h.cuando for h in salida] == sorted(
        [h.cuando for h in salida], reverse=True
    )
