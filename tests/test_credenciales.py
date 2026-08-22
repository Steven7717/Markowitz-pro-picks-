import json

import pytest

from credenciales import (
    ConfigIlegible,
    Credenciales,
    CredencialInvalida,
    aplicar,
    avisos,
    borrar,
    cargar,
    enmascarar,
    guardar,
)


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


def test_un_correo_sin_forma_de_correo_se_rechaza(tmp_path):
    # La SEC exige un contacto real en el User-Agent; si aceptamos "asdf" la
    # descarga falla mucho más tarde y con un error que no señala aquí.
    with pytest.raises(CredencialInvalida):
        guardar(Credenciales(edgar_identity="asdf"), tmp_path / "c.json")


def test_una_clave_con_espacios_dentro_se_rechaza(tmp_path):
    # Es lo que pasa al pegar desde un correo que partió la línea. Guardarla
    # daría un 401 desde la API, sin pista de que el problema fue el pegado.
    with pytest.raises(CredencialInvalida):
        guardar(Credenciales(api_key="sk-ant-abc 123"), tmp_path / "c.json")


def test_solo_el_correo_es_una_credencial_valida(tmp_path):
    # Guardar solo una de las dos es legítimo: se rellenan en dos momentos.
    ruta = guardar(Credenciales(edgar_identity="yo@x.com"), tmp_path / "c.json")
    assert cargar(ruta).api_key is None


def test_una_clave_con_prefijo_raro_se_guarda_pero_avisa(tmp_path):
    credenciales = Credenciales(api_key="clave-de-otro-formato")
    guardar(credenciales, tmp_path / "c.json")
    assert avisos(credenciales)


def test_una_clave_normal_no_genera_avisos():
    assert avisos(Credenciales(api_key="sk-ant-abc123456789")) == []


def test_aplicar_pone_las_credenciales_en_el_entorno():
    entorno = {}
    aplicar(Credenciales(api_key="sk-ant-x", edgar_identity="yo@x.com"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-x"
    assert entorno["EDGAR_IDENTITY"] == "yo@x.com"


def test_el_entorno_gana_sobre_el_fichero():
    # Quien tiene la variable puesta en su shell manda: si el fichero la
    # pisara, el entorno de desarrollo y los tests dejarían de ser los que
    # gobiernan, y sería la convención al revés de como está en todas partes.
    entorno = {"ANTHROPIC_API_KEY": "la-del-shell"}
    aplicar(Credenciales(api_key="la-del-fichero"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "la-del-shell"


def test_una_credencial_ausente_no_escribe_nada_en_el_entorno():
    entorno = {}
    aplicar(Credenciales(edgar_identity="yo@x.com"), entorno)
    assert "ANTHROPIC_API_KEY" not in entorno


def test_borrar_quita_el_fichero(tmp_path):
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    borrar(ruta, {})
    assert not ruta.exists()


def test_borrar_retira_del_entorno_lo_que_el_fichero_habia_puesto(tmp_path):
    # Sin esto, "Borrar" no hace nada visible hasta reiniciar: la clave sigue
    # en os.environ y la página sigue ofreciendo la IA como si nada.
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    entorno = {}
    aplicar(cargar(ruta), entorno)
    borrar(ruta, entorno)
    assert "ANTHROPIC_API_KEY" not in entorno


def test_borrar_no_toca_una_variable_que_venia_del_shell(tmp_path):
    # El usuario borra lo que guardó en la app, no lo que puso en su shell.
    ruta = guardar(Credenciales(api_key="la-del-fichero"), tmp_path / "c.json")
    entorno = {"ANTHROPIC_API_KEY": "la-del-shell"}
    borrar(ruta, entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "la-del-shell"


def test_borrar_un_fichero_corrupto_igualmente_lo_quita(tmp_path):
    # Es justo el caso en que el usuario más necesita poder borrar.
    ruta = tmp_path / "c.json"
    ruta.write_text("{roto", encoding="utf-8")
    borrar(ruta, {})
    assert not ruta.exists()


def test_la_clave_enmascarada_no_contiene_la_clave():
    clave = "sk-ant-api03-secretosecretosecreto1234"
    mascara = enmascarar(clave)
    assert clave not in mascara
    assert "secretosecreto" not in mascara
    assert mascara.endswith("1234")


def test_una_clave_corta_no_ensena_nada():
    # Con pocos caracteres, mostrar principio y final es mostrarla entera.
    assert "abc" not in enmascarar("sk-abc")


def test_sin_clave_la_mascara_esta_vacia():
    assert enmascarar(None) == ""
