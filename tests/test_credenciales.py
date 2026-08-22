import json
import os
import stat

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
    reemplazar,
    variables_del_shell,
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


def test_los_espacios_alrededor_de_la_clave_se_quitan(tmp_path):
    # Pegar desde el navegador arrastra espacios. Es el caso mas comun de todos.
    ruta = guardar(Credenciales(api_key="  sk-ant-abc123456789  "), tmp_path / "c.json")
    assert cargar(ruta).api_key == "sk-ant-abc123456789"


def test_guardar_dos_veces_deja_el_valor_nuevo(tmp_path):
    ruta = tmp_path / "c.json"
    guardar(Credenciales(api_key="sk-ant-primera"), ruta)
    guardar(Credenciales(api_key="sk-ant-segunda"), ruta)
    assert cargar(ruta).api_key == "sk-ant-segunda"


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


def test_un_campo_que_no_es_texto_es_ilegible(tmp_path):
    # Un fichero editado a mano puede traer un número donde va una cadena.
    # Sin esto sale un AttributeError, que la página no espera y no atrapa:
    # un fichero de configuración mal escrito tumbaría el optimizador entero.
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"api_key": 12345}), encoding="utf-8")
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


def test_una_variable_de_entorno_vacia_no_gana_al_fichero():
    # setx con una cadena vacia deja la variable definida y sin valor; el
    # fichero debe ganarle. Es la misma regla que ya prueba
    # tests/test_aprobacion_generacion.py para disponibilidad().
    entorno = {"ANTHROPIC_API_KEY": ""}
    aplicar(Credenciales(api_key="sk-ant-x"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-x"


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


def test_un_guardado_que_falla_a_medias_deja_intacto_lo_anterior(tmp_path,
                                                                 monkeypatch):
    ruta = guardar(Credenciales(api_key="sk-ant-la-buena-de-antes"),
                   tmp_path / "c.json")

    def replace_que_falla(self, destino):
        raise OSError("disco lleno")

    monkeypatch.setattr("pathlib.Path.replace", replace_que_falla)
    with pytest.raises(OSError):
        guardar(Credenciales(api_key="sk-ant-la-nueva-que-no-cuaja"), ruta)

    assert cargar(ruta).api_key == "sk-ant-la-buena-de-antes"


@pytest.mark.skipif(os.name == "nt", reason="Windows no usa permisos POSIX")
def test_el_fichero_no_lo_puede_leer_nadie_mas(tmp_path):
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="Windows no usa permisos POSIX")
def test_la_clave_nunca_llega_al_disco_con_permisos_abiertos(tmp_path, monkeypatch):
    # Mirar el modo del fichero final, o el del temporal al hacer replace, no
    # distingue un guardado seguro de uno que expuso la clave y la tapó
    # después: los dos acaban en 0o600. Lo que hay que comprobar es el modo
    # ANTES de que se escriba un solo byte del secreto.
    #
    # Se monta ademas el caso peor: un .tmp que dejo un guardado reventado. El
    # modo de os.open solo se aplica al crear, asi que ese fichero conserva sus
    # permisos viejos y es el camino por el que la clave se escapaba.
    modos = []
    fdopen_original = os.fdopen

    def fdopen_espia(descriptor, *args, **kwargs):
        modos.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
        return fdopen_original(descriptor, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", fdopen_espia)

    destino = tmp_path / "c.json"
    rancio = destino.with_suffix(".tmp")
    rancio.write_text("lo que dejó un guardado que reventó", encoding="utf-8")
    os.chmod(rancio, 0o644)

    guardar(Credenciales(api_key="sk-ant-abc123456789"), destino)

    assert modos == [0o600]


def test_reemplazar_pone_en_vigor_la_credencial_nueva():
    # Es el boton "Cambiar": te revocan la clave y pegas otra. Si el entorno
    # se queda con la vieja, la pagina ensena la nueva y la API recibe la
    # vieja, que es la peor combinacion posible.
    viejas = Credenciales(api_key="sk-ant-vieja")
    entorno = {}
    aplicar(viejas, entorno)
    reemplazar(viejas, Credenciales(api_key="sk-ant-nueva"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-nueva"


def test_reemplazar_no_pisa_una_variable_del_shell():
    viejas = Credenciales(api_key="la-del-fichero")
    entorno = {"ANTHROPIC_API_KEY": "la-del-shell"}
    reemplazar(viejas, Credenciales(api_key="la-nueva-del-fichero"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "la-del-shell"


def test_reemplazar_cambia_una_variable_que_el_shell_traia_igual():
    # Caso raro y deliberado: el shell trae el mismo valor que habia guardado.
    # La pagina no avisa de esa variable --variables_del_shell tampoco la
    # nombra, porque coinciden-- asi que el cambio tiene que surtir efecto.
    # Al reiniciar volvera a mandar el shell, y entonces la pagina SI lo dira.
    viejas = Credenciales(api_key="sk-ant-la-misma")
    entorno = {"ANTHROPIC_API_KEY": "sk-ant-la-misma"}
    reemplazar(viejas, Credenciales(api_key="sk-ant-la-nueva"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-la-nueva"


def test_reemplazar_retira_una_credencial_que_ya_no_esta():
    # Vaciar el campo del correo y guardar tiene que quitarlo tambien del
    # entorno, no solo del fichero: si no, edgartools seguiria usando el viejo.
    viejas = Credenciales(api_key="sk-ant-k", edgar_identity="yo@x.com")
    entorno = {}
    aplicar(viejas, entorno)
    reemplazar(viejas, Credenciales(api_key="sk-ant-k"), entorno)
    assert "EDGAR_IDENTITY" not in entorno
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-k"


def test_variables_del_shell_nombra_lo_que_el_shell_pisa():
    # Es lo que la pagina necesita para no mentir: si el shell trae una clave
    # distinta a la guardada, lo que el usuario guarde no entra en vigor.
    guardadas = Credenciales(api_key="sk-ant-del-fichero")
    entorno = {"ANTHROPIC_API_KEY": "sk-ant-del-shell"}
    assert variables_del_shell(guardadas, entorno) == ["ANTHROPIC_API_KEY"]


def test_variables_del_shell_no_nombra_lo_que_coincide():
    guardadas = Credenciales(api_key="sk-ant-igual")
    entorno = {"ANTHROPIC_API_KEY": "sk-ant-igual"}
    assert variables_del_shell(guardadas, entorno) == []


def test_variables_del_shell_no_nombra_lo_que_solo_esta_en_el_fichero():
    guardadas = Credenciales(api_key="sk-ant-solo-fichero")
    entorno = {}
    assert variables_del_shell(guardadas, entorno) == []


def test_un_temporal_rancio_y_largo_no_deja_cola_de_basura(tmp_path):
    # O_TRUNC y no O_EXCL deja escribir dentro de un .tmp que dejo un guardado
    # reventado. Si ademas no truncara, un guardado mas corto que el anterior
    # dejaria una cola del contenido viejo y el JSON resultante no se podria
    # leer: el usuario perderia las credenciales por un fallo anterior que ya
    # habia sobrevivido.
    destino = tmp_path / "c.json"
    rancio = destino.with_suffix(".tmp")
    rancio.write_text("x" * 5000, encoding="utf-8")

    guardar(Credenciales(api_key="sk-ant-corta"), destino)

    assert cargar(destino).api_key == "sk-ant-corta"


def test_guardar_sin_nada_relleno_no_escribe_un_fichero_de_nulls(tmp_path):
    # Pulsar "Guardar" con los dos campos en blanco es un despiste, no una
    # instrucción: escribir {"api_key": null, "edgar_identity": null} y
    # devolver la ruta tan contentos le diría al usuario que guardó algo.
    ruta = tmp_path / "c.json"
    with pytest.raises(CredencialInvalida):
        guardar(Credenciales(), ruta)
    assert not ruta.exists()
