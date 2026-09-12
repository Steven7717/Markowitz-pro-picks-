# programa/tests/test_interprete_archivo.py
"""El registro append-only de lo interpretado."""

from datetime import date, datetime

import pytest

from interprete import archivo, noticias
from seguimiento import libro

URL_A = "https://www.sec.gov/Archives/edgar/data/789019/000119312526323632/a.htm"
URL_B = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000013/b.htm"


def _juicio(ticker="MSFT"):
    return noticias.Juicio(ticker, "Dice algo.", "Te toca.", "una cita", True)


def _anotada(url=URL_A, ticker="MSFT"):
    return archivo.Anotada(url, ticker, date(2026, 9, 3), ("4.02",), _juicio(ticker))


def test_un_archivo_que_no_existe_esta_vacio(tmp_path):
    guardado = archivo.cargar(tmp_path / "x.json")
    assert guardado.hechos == () and guardado.rebalanceo == ()


def test_anotar_y_releer(tmp_path):
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "claude-sonnet-5", "i1", (_anotada(),), "en conjunto")
    guardado = archivo.cargar(ruta)
    assert len(guardado.hechos) == 1
    assert guardado.hechos[0].juicios[0].url == URL_A
    assert guardado.hechos[0].en_conjunto == "en conjunto"
    assert guardado.hechos[0].juicios[0].juicio.que_dice == "Dice algo."


def test_anotar_dos_veces_anade_y_no_pisa(tmp_path):
    """Un juicio es una opinion fechada. Reescribirla borraria que cambio.
    Misma forma que `Libro.objetivos`: se conserva todo, se ensena lo ultimo."""
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(),), "primera")
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(),), "segunda")
    guardado = archivo.cargar(ruta)
    assert len(guardado.hechos) == 2
    assert [s.en_conjunto for s in guardado.hechos] == ["primera", "segunda"]


def test_urls_leidas_atraviesa_las_sesiones(tmp_path):
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(URL_A),), "")
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(URL_B, "MU"),), "")
    assert archivo.urls_leidas(archivo.cargar(ruta)) == {URL_A, URL_B}


def test_la_sesion_lleva_su_fecha(tmp_path):
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(),), "")
    assert isinstance(archivo.cargar(ruta).hechos[0].cuando, datetime)


def test_el_comentario_de_rebalanceo_guarda_su_foto(tmp_path):
    """Sin el estado al que apuntaba es texto huerfano: habla de una deriva que
    manana ya es otra."""
    ruta = tmp_path / "x.json"
    foto = archivo.Foto(
        pesos_reales=(("MSFT", 0.18),),
        pesos_objetivo=(("MSFT", 0.15),),
        operaciones=(("MSFT", "vender", 0.03),),
    )
    archivo.anotar_rebalanceo(ruta, "m", "i1", foto, (("MSFT", "Pesa de mas."),), "")
    guardado = archivo.cargar(ruta)
    assert guardado.rebalanceo[0].foto.pesos_reales == (("MSFT", 0.18),)
    assert guardado.rebalanceo[0].observaciones[0] == ("MSFT", "Pesa de mas.")


def test_las_dos_mitades_conviven_en_el_mismo_fichero(tmp_path):
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(),), "")
    foto = archivo.Foto((), (), ())
    archivo.anotar_rebalanceo(ruta, "m", "i1", foto, (), "")
    guardado = archivo.cargar(ruta)
    assert len(guardado.hechos) == 1 and len(guardado.rebalanceo) == 1


def test_un_archivo_corrupto_NO_se_trata_como_vacio(tmp_path):
    """**Al reves que la cache.** Alli un fichero roto es un fallo de cache;
    aqui es historial perdido, y tragarselo significaria volver a pagar Y
    perder lo guardado sin que nadie se entere."""
    ruta = tmp_path / "x.json"
    ruta.write_text('{"hechos": [', encoding="utf-8")
    with pytest.raises(archivo.ArchivoIlegible):
        archivo.cargar(ruta)


def test_un_archivo_corrupto_no_se_borra(tmp_path):
    """Mientras este ahi se puede recuperar a mano."""
    ruta = tmp_path / "x.json"
    ruta.write_text("{roto", encoding="utf-8")
    with pytest.raises(archivo.ArchivoIlegible):
        archivo.cargar(ruta)
    assert ruta.exists()


def test_la_ruta_cuelga_del_libro_pero_en_su_subcarpeta(tmp_path):
    """`libro.listar()` hace glob('*.json') sobre `libros/` y valida lo que
    encuentra: un archivo ahi dentro apareceria como un libro ilegible."""
    ruta = archivo.ruta_de(tmp_path / "2026-09-01-mi-libro.json")
    assert ruta.parent.name == "interpretaciones"
    assert ruta.name == "2026-09-01-mi-libro.json"


def test_listar_libros_no_ve_el_archivo_de_interpretaciones(tmp_path):
    """El test que protege la decision de arriba. Si alguien mueve el archivo a
    `libros/` a secas, esto cae."""
    ruta_libro = tmp_path / "2026-09-01-mi-libro.json"
    # `creado` es obligatorio: sin el, `libro.cargar` lo rechaza y este test
    # pasaria igual pero con un libro ilegible dentro -- comprobado.
    ruta_libro.write_text(
        '{"nombre": "mi libro", "creado": "2026-09-01", "moneda": "USD", '
        '"asientos": [], "objetivos": []}',
        encoding="utf-8",
    )
    archivo.anotar_hechos(archivo.ruta_de(ruta_libro), "m", "i1", (_anotada(),), "")
    entradas = libro.listar(tmp_path)
    assert len(entradas) == 1
    assert entradas[0].ruta.name == "2026-09-01-mi-libro.json"
    # Las dos mitades: el archivo no aparece, Y el libro de verdad si se lee.
    assert entradas[0].libro is not None


def test_la_escritura_no_deja_temporales(tmp_path):
    ruta = tmp_path / "x.json"
    archivo.anotar_hechos(ruta, "m", "i1", (_anotada(),), "")
    assert list(tmp_path.glob("*.tmp")) == []
