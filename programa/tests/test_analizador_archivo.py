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


# --- La forma de la explicación al leer ---------------------------------------------


def _con_explicacion(tmp_path, **cambios):
    ruta = tmp_path / "MU.json"
    archivo.anotar_explicacion(ruta, EXPLICACION)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["valoracion"][0].update(cambios)
    ruta.write_text(json.dumps(crudo), encoding="utf-8")
    return ruta


@pytest.mark.parametrize(
    "cambios",
    [
        {"movidos": "beta"},
        {"movidos": ["beta", 3]},
        {"veredicto": 5},
        {"votos": [["flujos", "neutra"], ["sin_crecimiento", "neutra"]]},
        {"votos": [["pares", "barata"], ["sin_crecimiento", "neutra"], ["flujos", "neutra"]]},
        {"votos": [["flujos", "neutra"], ["sin_crecimiento", "neutra"], ["otro", "barata"]]},
        {"votos": [["flujos", 3], ["sin_crecimiento", "neutra"], ["pares", "barata"]]},
        {"votos": "flujos"},
        {"votos": [["flujos"], ["sin_crecimiento", "neutra"], ["pares", "barata"]]},
    ],
)
def test_una_explicacion_con_otra_forma_es_un_fichero_corrupto(tmp_path, cambios):
    ruta = _con_explicacion(tmp_path, **cambios)
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.cargar(ruta)


def test_una_explicacion_con_veredicto_y_votos_vacios_se_lee(tmp_path):
    ruta = _con_explicacion(
        tmp_path, veredicto=None,
        votos=[["flujos", None], ["sin_crecimiento", None], ["pares", None]],
    )
    leida = archivo.cargar(ruta).valoracion[0]
    assert leida.veredicto is None and leida.votos[0] == ("flujos", None)


def test_el_error_de_un_booleano_nombra_su_campo(tmp_path):
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["tesis"][0]["fuente"]["recortado"] = "no"
    ruta.write_text(json.dumps(crudo), encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible, match="'recortado'"):
        archivo.cargar(ruta)
    archivo.anotar_explicacion(tmp_path / "otro.json", EXPLICACION)
    crudo = json.loads((tmp_path / "otro.json").read_text(encoding="utf-8"))
    crudo["valoracion"][0]["observaciones"][0]["marcada"] = "si"
    (tmp_path / "otro.json").write_text(json.dumps(crudo), encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible, match="'marcada'"):
        archivo.cargar(tmp_path / "otro.json")


# --- Lo que se escribe también se valida --------------------------------------------


def test_una_entrada_que_no_se_podria_leer_no_se_escribe(tmp_path):
    mala = archivo.Tesis(CUANDO, "m", "v", FUENTE, "t", (("a", "c", 1),))
    ruta = tmp_path / "MU.json"
    with pytest.raises(ValueError):
        archivo.anotar_tesis(ruta, mala)
    assert not ruta.exists()


def test_una_entrada_mala_deja_el_fichero_como_estaba(tmp_path):
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    antes = ruta.read_text(encoding="utf-8")
    mala = archivo.Tesis(CUANDO, "m", "v", FUENTE, "t", (("a", "c", 1),))
    with pytest.raises(ValueError):
        archivo.anotar_tesis(ruta, mala)
    assert ruta.read_text(encoding="utf-8") == antes
    assert archivo.cargar(ruta).tesis == (TESIS,)


def test_anotar_no_pisa_un_fichero_cuyas_otras_lecturas_no_se_entienden(tmp_path):
    # `leer_crudo` sólo exige un objeto JSON: lo que se ve en `tesis` lo comprueba
    # `cargar`, y sin esa lectura previa se escribiría encima de un historial roto.
    ruta = tmp_path / "MU.json"
    archivo.anotar_tesis(ruta, TESIS)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["tesis"][0]["riesgos"][0]["verificada"] = "false"
    roto = json.dumps(crudo)
    ruta.write_text(roto, encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.anotar_contraste(ruta, CONTRASTE)
    assert ruta.read_text(encoding="utf-8") == roto


@pytest.mark.parametrize("valor", [{}, "", 0, None, {"a": 1}])
def test_una_clave_que_no_es_una_lista_es_un_fichero_corrupto_sea_lo_que_sea(tmp_path, valor):
    # Un `{}` o un `""` se recorren sin error y darían «ninguna lectura»: parecería vacío.
    ruta = tmp_path / "MU.json"
    ruta.write_text(json.dumps({"hechos": [], "rebalanceo": [], "tesis": valor}), encoding="utf-8")
    with pytest.raises(interprete_archivo.ArchivoIlegible):
        archivo.cargar(ruta)
