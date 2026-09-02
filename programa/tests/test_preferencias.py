import json

import preferencias
from data import DEFAULT_HORIZON, HORIZON_CONFIG
from optimizer import STRATEGY_LABELS
from preferencias import Preferencias


def test_un_usuario_nuevo_no_es_un_error(tmp_path):
    guardadas, avisos = preferencias.cargar(tmp_path / "todavia-no.json")
    assert guardadas == Preferencias()
    assert avisos == []


def test_lo_guardado_vuelve_igual(tmp_path):
    ruta = tmp_path / "preferencias.json"
    mias = Preferencias(
        tickers="AAPL, MSFT",
        horizonte="1 Año",
        estrategia="min_variance",
        peso_min=5,
        peso_max=40,
        permitir_cortos=True,
        shrinkage=False,
        guia_vista=True,
    )
    preferencias.guardar(mias, ruta)
    vueltas, avisos = preferencias.cargar(ruta)
    assert vueltas == mias
    assert avisos == []


def test_los_valores_de_fabrica_son_opciones_que_existen():
    # Un defecto que no este en el desplegable deja al usuario ante un selector
    # sin nada seleccionado, o revienta al construirlo.
    de_fabrica = Preferencias()
    assert de_fabrica.horizonte in HORIZON_CONFIG
    assert de_fabrica.estrategia in STRATEGY_LABELS
    assert de_fabrica.horizonte == DEFAULT_HORIZON


# --- Nada de esto puede dejar a nadie fuera de su propia aplicacion ----------


def test_un_horizonte_que_ya_no_existe_avisa_y_cae_al_de_fabrica(tmp_path):
    # El caso real: una version futura renombra un horizonte, y quien tenia el
    # viejo guardado abre la app y se encuentra con que no arranca.
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"horizonte": "1 Quincena"}), encoding="utf-8")

    guardadas, avisos = preferencias.cargar(ruta)
    assert guardadas.horizonte == DEFAULT_HORIZON
    assert any("1 Quincena" in aviso for aviso in avisos)


def test_una_estrategia_desconocida_avisa_y_cae_a_maximo_sharpe(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"estrategia": "kelly"}), encoding="utf-8")

    guardadas, avisos = preferencias.cargar(ruta)
    assert guardadas.estrategia == preferencias.ESTRATEGIA_POR_DEFECTO
    assert any("kelly" in aviso for aviso in avisos)


def test_un_peso_fuera_del_rango_del_deslizador_se_recorta(tmp_path):
    # Streamlit revienta al construir el slider si `value` cae fuera de
    # [min, max], y lo hace antes de pintar nada: la pagina entera se queda en
    # blanco sin un sitio evidente donde mirar.
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"peso_min": 90, "peso_max": 500}), encoding="utf-8")

    guardadas, _ = preferencias.cargar(ruta)
    assert 0 <= guardadas.peso_min <= 20
    assert 20 <= guardadas.peso_max <= 100


def test_un_minimo_por_encima_del_maximo_restablece_los_dos(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(json.dumps({"peso_min": 20, "peso_max": 20}), encoding="utf-8")
    guardadas, _ = preferencias.cargar(ruta)
    assert guardadas.peso_min <= guardadas.peso_max

    ruta.write_text(json.dumps({"peso_min": 15, "peso_max": 100}), encoding="utf-8")
    guardadas, avisos = preferencias.cargar(ruta)
    assert (guardadas.peso_min, guardadas.peso_max) == (15, 100)
    assert avisos == []


def test_un_fichero_corrupto_no_impide_arrancar(tmp_path):
    ruta = tmp_path / "preferencias.json"
    ruta.write_text("esto no es json", encoding="utf-8")

    guardadas, avisos = preferencias.cargar(ruta)
    assert guardadas == Preferencias()
    assert avisos and "fábrica" in avisos[0]


def test_un_campo_desconocido_se_ignora_sin_ruido(tmp_path):
    # Es lo que permite que una version futura anada una preferencia y que el
    # fichero siga abriendose en la version instalada.
    ruta = tmp_path / "preferencias.json"
    ruta.write_text(
        json.dumps({"horizonte": "1 Año", "modo_experto": True}), encoding="utf-8"
    )

    guardadas, avisos = preferencias.cargar(ruta)
    assert guardadas.horizonte == "1 Año"
    assert avisos == []


def test_guardar_sanea_antes_de_escribir(tmp_path):
    # Sin esto, un valor imposible se quedaria en disco esperando a romper el
    # arranque siguiente.
    ruta = tmp_path / "preferencias.json"
    preferencias.guardar(Preferencias(horizonte="inventado", peso_max=999), ruta)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    assert crudo["horizonte"] == DEFAULT_HORIZON
    assert crudo["peso_max"] == 100


def test_borrar_vuelve_a_los_valores_de_fabrica(tmp_path):
    ruta = tmp_path / "preferencias.json"
    preferencias.guardar(Preferencias(horizonte="1 Año"), ruta)
    preferencias.borrar(ruta)
    guardadas, _ = preferencias.cargar(ruta)
    assert guardadas == Preferencias()
    preferencias.borrar(ruta)  # borrar lo que ya no esta tampoco falla
