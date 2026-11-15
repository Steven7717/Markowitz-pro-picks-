"""Dónde se guardan las lecturas de la IA de un ticker del Analizador."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from analizador import archivo
from interprete import archivo as interprete_archivo
from interprete import noticias

RAIZ = Path(__file__).resolve().parent.parent


def test_cada_ticker_tiene_su_archivo_en_analisis():
    assert archivo.ruta_de("MU") == Path("analisis") / "MU.json"
    assert archivo.ruta_de("BRK-B").name == "BRK-B.json"


def test_el_archivo_de_un_ticker_es_el_de_interprete_tal_cual(tmp_path, monkeypatch):
    monkeypatch.setattr(archivo, "DIRECTORIO", tmp_path / "analisis")
    ruta = archivo.ruta_de("MU")
    # Que no exista es un ticker que nadie ha interpretado.
    assert interprete_archivo.cargar(ruta) == interprete_archivo.Archivo()
    juicio = noticias.Juicio("MU", "qué dice", "por qué", "una cita literal del documento", True)
    anotada = interprete_archivo.Anotada("https://www.sec.gov/x", "MU", date(2026, 10, 1), ("2.02",), juicio)
    interprete_archivo.anotar_hechos(ruta, "modelo", "i3", (anotada,), "")
    assert interprete_archivo.urls_leidas(interprete_archivo.cargar(ruta)) == {"https://www.sec.gov/x"}
    assert ruta.parent == tmp_path / "analisis"


def test_las_lecturas_quedan_fuera_de_git():
    assert "analisis/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()


FUENTE = archivo.Fuente("10-K", "2026-10-09", "0000723125-26-000023", "Item 1A", True)
CUANDO = datetime(2026, 11, 15, 10, 30)
TESIS = archivo.Tesis(CUANDO, "claude-sonnet-5", "b3", FUENTE, "Vende memoria.",
                      (("Depende de pocos clientes.", "a small number of customers", True),))
CONTRASTE = archivo.Contraste(CUANDO, "claude-sonnet-5", "n1", FUENTE, "Crece por debajo de su ritmo.",
                              (("La empresa espera más demanda.", "contradice", "we expect demand to grow", False),))
EXPLICACION = archivo.Explicacion(
    CUANDO, "claude-sonnet-5", "n1",
    (("flujos", "neutra"), ("sin_crecimiento", "neutra"), ("pares", "barata")),
    "en_rango", ("beta",), (("flujos", "Depende del crecimiento.", False),), "Las tres coinciden poco.",
)


def test_un_ticker_sin_fichero_no_tiene_lecturas(tmp_path):
    assert archivo.cargar(tmp_path / "MU.json") == archivo.Lecturas()


def test_un_fichero_de_n2_sin_las_claves_nuevas_se_lee_como_vacio(tmp_path):
    ruta = tmp_path / "MU.json"
    ruta.write_text(json.dumps({"hechos": [], "rebalanceo": []}), encoding="utf-8")
    assert archivo.cargar(ruta) == archivo.Lecturas()


def test_cada_lectura_vuelve_como_se_guardo(tmp_path):
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    archivo.anotar_contraste(ruta, CONTRASTE)
    archivo.anotar_explicacion(ruta, EXPLICACION)
    assert archivo.cargar(ruta) == archivo.Lecturas((TESIS,), (CONTRASTE,), (EXPLICACION,))


def test_volver_a_leer_anade_y_no_pisa(tmp_path):
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    archivo.anotar_tesis(ruta, TESIS)
    assert len(archivo.cargar(ruta).tesis) == 2


def test_el_fichero_nuevo_lo_sigue_leyendo_el_archivo_de_los_8k(tmp_path):
    # `interprete.archivo.cargar` exige `hechos` y `rebalanceo`: un fichero que
    # naciera sólo con `tesis` dejaría los 8-K de ese ticker «ilegibles».
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    assert interprete_archivo.cargar(ruta) == interprete_archivo.Archivo()


def test_una_lectura_de_8k_posterior_no_borra_la_tesis(tmp_path):
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    interprete_archivo.anotar_hechos(ruta, "modelo", "i4", (), "")
    assert archivo.cargar(ruta).tesis == (TESIS,)


def test_un_fichero_ilegible_ni_se_lee_como_vacio_ni_se_toca(tmp_path):
    ruta = tmp_path / "MU.json"
    ruta.write_text("{", encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.cargar(ruta)
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.anotar_tesis(ruta, TESIS)
    assert ruta.read_text(encoding="utf-8") == "{"


def test_una_verificada_que_no_es_booleana_es_un_fichero_corrupto(tmp_path):
    # `bool("false")` es True: daría por respaldada una cita que no lo está.
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["tesis"][0]["riesgos"][0]["verificada"] = "false"
    ruta.write_text(json.dumps(crudo), encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.cargar(ruta)


def test_una_clave_nueva_que_no_es_lista_es_un_fichero_corrupto(tmp_path):
    ruta = tmp_path / "MU.json"
    ruta.write_text(json.dumps({"hechos": [], "rebalanceo": [], "mdna": "x"}), encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.cargar(ruta)


def test_los_votos_de_una_valoracion_son_los_tres_en_orden():
    valoracion = {"votos": {"pares": {"voto": "barata"}, "flujos": {"voto": "neutra"}}}
    assert archivo.votos_de(valoracion) == (("flujos", "neutra"), ("sin_crecimiento", None), ("pares", "barata"))
    assert archivo.votos_de({"motivo": "sin_red"}) == (("flujos", None), ("sin_crecimiento", None), ("pares", None))
