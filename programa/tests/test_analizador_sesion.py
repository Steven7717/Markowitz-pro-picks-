"""Lo que el Analizador guarda en la sesión, con un diccionario en lugar de `st.session_state`."""

from datetime import datetime
from types import SimpleNamespace

from analizador import sesion


def test_un_encargo_rellena_el_campo_y_elige_el_detalle():
    estado = {}
    sesion.encargar(estado, ["MU", "TSM"], "TSM")
    encargo = sesion.recoger(estado)
    assert encargo.tickers == ("MU", "TSM")
    assert estado[sesion.CLAVE_TEXTO] == "MU TSM"
    assert estado[sesion.CLAVE_ELEGIDO] == "TSM"


def test_un_encargo_se_consume_al_usarlo():
    # Si se quedase, volvería a pisar lo que el usuario escriba después.
    estado = {}
    sesion.encargar(estado, ["MU"])
    sesion.recoger(estado)
    estado[sesion.CLAVE_TEXTO] = "JPM"
    assert sesion.recoger(estado) is None
    assert estado[sesion.CLAVE_TEXTO] == "JPM"


def test_un_encargo_sin_elegido_no_toca_el_detalle():
    estado = {sesion.CLAVE_ELEGIDO: "MU"}
    sesion.encargar(estado, ["JPM"])
    sesion.recoger(estado)
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"


def test_lo_que_no_es_un_encargo_se_tira():
    estado = {sesion.CANAL: ["MU"]}
    assert sesion.recoger(estado) is None
    assert sesion.CANAL not in estado and sesion.CLAVE_TEXTO not in estado


def test_cargar_de_un_libro_solo_rellena_el_campo():
    estado = {}
    sesion.cargar_texto(estado, ["AAPL", "MSFT"])
    assert estado == {sesion.CLAVE_TEXTO: "AAPL MSFT"}


def test_los_analisis_valen_mientras_no_cambie_el_panel():
    hora = datetime(2026, 10, 16, 12, 0)
    estado = {}
    hechos = sesion.preparar(estado, hora)
    hechos["MU"] = "ANALISIS"
    assert sesion.preparar(estado, hora) == {"MU": "ANALISIS"}
    assert not sesion.panel_cambiado(estado, hora)
    assert sesion.panel_cambiado(estado, datetime(2026, 10, 26, 9, 0))
    assert sesion.preparar(estado, datetime(2026, 10, 26, 9, 0)) == {}


def test_una_cache_que_no_es_un_diccionario_se_rehace():
    # Un valor de otra versión no puede tumbar la pantalla.
    hora = datetime(2026, 10, 16, 12, 0)
    estado = {sesion.CLAVE_HORA_PANEL: hora, sesion.CLAVE_ANALISIS: ["MU"]}
    assert sesion.preparar(estado, hora) == {}


def test_sin_analisis_no_hay_panel_que_haya_cambiado():
    assert not sesion.panel_cambiado({}, datetime(2026, 10, 26))


def test_se_analiza_lo_que_falta_y_lo_que_fallo_en_su_orden():
    # Un ticker que salió sin clase (sin red, la SEC sin responder) se vuelve
    # a intentar al pulsar «Analizar»; uno con clase sale de la caché.
    hechos = {"TSM": SimpleNamespace(clase="extranjera_sec"), "JPM": SimpleNamespace(clase=None)}
    assert sesion.pendientes(["MU", "TSM", "JPM"], hechos) == ["MU", "JPM"]


def test_el_detalle_elegido_tiene_que_estar_entre_las_opciones():
    estado = {sesion.CLAVE_ELEGIDO: "ZZZZQ"}
    sesion.fijar_elegido(estado, ["MU", "TSM"])
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"
    sesion.fijar_elegido(estado, ["MU", "TSM"])
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"
    # Uno que sí está entre las opciones se respeta, aunque no sea el primero.
    estado[sesion.CLAVE_ELEGIDO] = "TSM"
    sesion.fijar_elegido(estado, ["MU", "TSM"])
    assert estado[sesion.CLAVE_ELEGIDO] == "TSM"
    vacio = {sesion.CLAVE_ELEGIDO: "MU"}
    sesion.fijar_elegido(vacio, [])
    assert vacio[sesion.CLAVE_ELEGIDO] == "MU"


def test_restaurar_borra_lo_movido_y_deja_la_tasa_puesta_a_mano():
    estado = {
        sesion.clave_deslizador("MU", "beta"): 1.5,
        sesion.clave_deslizador("MU", "g_ref"): 30.0,
        sesion.clave_a_mano("MU"): 9.0,
        sesion.clave_deslizador("MU.DE", "beta"): 1.2,
        sesion.clave_deslizador("BRK-B", "beta"): 0.4,
    }
    sesion.restaurar_deslizadores(estado, "MU")
    assert estado == {
        sesion.clave_a_mano("MU"): 9.0,
        sesion.clave_deslizador("MU.DE", "beta"): 1.2,
        sesion.clave_deslizador("BRK-B", "beta"): 0.4,
    }


def test_un_analisis_nuevo_olvida_todo_lo_movido_de_su_ticker():
    estado = {sesion.clave_deslizador("MU", "beta"): 1.5, sesion.clave_a_mano("MU"): 9.0, "otra": 1, 7: "no es texto"}
    sesion.olvidar_deslizadores(estado, "MU")
    assert estado == {"otra": 1, 7: "no es texto"}
