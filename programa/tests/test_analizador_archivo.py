"""Dónde se guardan las lecturas de la IA de un ticker del Analizador."""

from datetime import date
from pathlib import Path

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
