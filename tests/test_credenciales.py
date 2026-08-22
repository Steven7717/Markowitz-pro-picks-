import json

import pytest

from credenciales import ConfigIlegible, Credenciales, cargar, guardar


def test_lo_guardado_se_lee_igual(tmp_path):
    ruta = tmp_path / "credenciales.json"
    guardar(
        Credenciales(api_key="sk-ant-abc123456789", edgar_identity="yo@x.com"),
        ruta,
    )
    leidas = cargar(ruta)
    assert leidas.api_key == "sk-ant-abc123456789"
    assert leidas.edgar_identity == "yo@x.com"


def test_guardar_crea_la_carpeta_si_no_existe(tmp_path):
    # El usuario nuevo no tiene ~/.markowitz-pro-picks: si guardar no la crea,
    # el primer guardado de todo el mundo falla.
    ruta = tmp_path / "sin" / "crear" / "credenciales.json"
    guardar(Credenciales(api_key="sk-ant-abc123456789"), ruta)
    assert ruta.exists()


def test_sin_fichero_las_credenciales_salen_vacias(tmp_path):
    leidas = cargar(tmp_path / "no-existe.json")
    assert leidas.api_key is None
    assert leidas.edgar_identity is None


def test_un_fichero_corrupto_no_se_confunde_con_uno_ausente(tmp_path):
    # Devolver credenciales vacías aquí escondería el fallo: la página diría
    # "falta la clave" cuando lo que pasa es que el fichero está roto, y el
    # usuario buscaría el problema donde no está.
    ruta = tmp_path / "credenciales.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ConfigIlegible):
        cargar(ruta)


def test_un_json_que_no_es_un_objeto_tambien_es_ilegible(tmp_path):
    ruta = tmp_path / "credenciales.json"
    ruta.write_text(json.dumps(["una", "lista"]), encoding="utf-8")
    with pytest.raises(ConfigIlegible):
        cargar(ruta)
