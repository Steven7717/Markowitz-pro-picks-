"""Lo que el formulario del optimizador muestra, y que no se le cambie solo."""

import pytest

import configuracion
from cartera import Portafolio, Posicion
from preferencias import Preferencias

POR_DEFECTO = "AAPL, MSFT, GOOGL, AMZN, NVDA"


def _portafolio(nombre: str, tickers: list[str], **campos) -> Portafolio:
    base = dict(
        horizonte="3 Años", estrategia="risk_parity", peso_min=0.05,
        peso_max=0.40, permitir_cortos=True, shrinkage=False,
    )
    base.update(campos)
    return Portafolio(
        nombre=nombre, fecha="2026-09-10",
        posiciones=[Posicion(ticker=t, peso=1 / len(tickers)) for t in tickers],
        **base,
    )


def sembrar(estado: dict, guardadas: Preferencias | None = None) -> str:
    return configuracion.sembrar(estado, guardadas or Preferencias(), POR_DEFECTO)


def valores(estado: dict) -> dict:
    return {campo: estado[clave] for campo, clave in configuracion.CLAVES.items()}


# ── La primera visita ─────────────────────────────────────────────────────────

def test_sin_nada_en_sesion_se_siembra_de_las_preferencias():
    estado: dict = {}
    sembrar(estado, Preferencias(tickers="KO, PEP", horizonte="1 Año"))
    assert valores(estado)["tickers"] == "KO, PEP"
    assert valores(estado)["horizonte"] == "1 Año"


def test_sin_tickers_guardados_se_usan_los_de_muestra():
    estado: dict = {}
    sembrar(estado)
    assert valores(estado)["tickers"] == POR_DEFECTO


def test_la_primera_visita_no_declara_ningun_origen():
    estado: dict = {}
    assert sembrar(estado) == ""


# ── Cargar un portafolio guardado ─────────────────────────────────────────────

def test_un_portafolio_cargado_pisa_todos_los_campos():
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MU"])}
    origen = sembrar(estado)
    assert valores(estado) == {
        "tickers": "AAPL, MU",
        "horizonte": "3 Años",
        "estrategia": "risk_parity",
        "peso_min": 5,
        "peso_max": 40,
        "cortos": True,
        "shrinkage": False,
    }
    assert origen == "cargado de «prueba 1»"


def test_un_portafolio_cargado_sobrevive_a_las_reejecuciones():
    """El fallo que abrió esto: los activos volvían solos a los de muestra.

    El traspaso se consumía en la primera pasada y el formulario leía sus
    valores de un diccionario que se recalculaba entera cada vez, asi que en la
    siguiente reejecucion --pulsar «Optimizar cartera» ya es una-- los campos
    volvian a las preferencias. Medido en la aplicacion: se cargaba «prueba 1»
    con seis activos y la corrida salia con cinco, los de muestra, mientras la
    etiqueta seguia diciendo «cargado de prueba 1».
    """
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MSFT", "MU"])}
    sembrar(estado)

    for _ in range(3):  # tres reejecuciones mas, nadie toca nada
        origen = sembrar(estado)

    assert valores(estado)["tickers"] == "AAPL, MSFT, MU"
    assert valores(estado)["horizonte"] == "3 Años"
    assert origen == "cargado de «prueba 1»"


def test_lo_que_el_usuario_escribe_despues_no_se_pisa():
    """La otra cara de lo mismo, y la razon por la que el traspaso era de un solo uso."""
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MU"])}
    sembrar(estado)

    estado[configuracion.CLAVES["tickers"]] = "KO, PEP"
    estado[configuracion.CLAVES["horizonte"]] = "1 Año"
    sembrar(estado)

    assert valores(estado)["tickers"] == "KO, PEP"
    assert valores(estado)["horizonte"] == "1 Año"


def test_cargar_un_segundo_portafolio_pisa_al_primero():
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MU"])}
    sembrar(estado)
    estado["portafolio_a_cargar"] = _portafolio("otra", ["KO"], horizonte="1 Mes")
    origen = sembrar(estado)
    assert valores(estado)["tickers"] == "KO"
    assert valores(estado)["horizonte"] == "1 Mes"
    assert origen == "cargado de «otra»"


def test_los_pesos_del_portafolio_llegan_en_porcentaje_entero():
    """Los deslizadores van de 0 a 100; el portafolio los guarda en fraccion.

    Los valores probados son los unicos que pueden existir: el portafolio se
    guarda desde deslizadores de porcentaje entero, asi que su fraccion siempre
    es k/100 y nunca cae en un empate a .5.
    """
    estado = {"portafolio_a_cargar": _portafolio(
        "p", ["AAPL"], peso_min=0.05, peso_max=0.35
    )}
    sembrar(estado)
    assert valores(estado)["peso_min"] == 5
    assert valores(estado)["peso_max"] == 35


# ── El traspaso del gate de aprobación ────────────────────────────────────────

def test_el_gate_trae_los_tickers_y_su_origen():
    estado = {"tickers_aprobados": ["KO", "PEP", "MO"]}
    origen = sembrar(estado)
    assert valores(estado)["tickers"] == "KO, PEP, MO"
    assert origen == "3 empresas aprobadas en el gate"


def test_el_gate_no_toca_nada_mas_que_los_tickers():
    estado = {"tickers_aprobados": ["KO"]}
    sembrar(estado, Preferencias(horizonte="1 Año", estrategia="min_variance"))
    assert valores(estado)["horizonte"] == "1 Año"
    assert valores(estado)["estrategia"] == "min_variance"


def test_el_gate_tambien_sobrevive_a_las_reejecuciones():
    estado = {"tickers_aprobados": ["KO", "PEP"]}
    sembrar(estado)
    origen = sembrar(estado)
    assert valores(estado)["tickers"] == "KO, PEP"
    assert origen == "2 empresas aprobadas en el gate"


def test_un_portafolio_cargado_le_gana_al_gate_en_la_misma_pasada():
    """El orden esta en el docstring de `sembrar` y aqui se ata.

    Un portafolio cargado es lo que el usuario acaba de pedir; la lista del
    gate puede llevar ahi desde hace tres pantallas.
    """
    estado = {
        "tickers_aprobados": ["KO", "PEP"],
        "portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MU"]),
    }
    origen = sembrar(estado)
    assert valores(estado)["tickers"] == "AAPL, MU"
    assert origen == "cargado de «prueba 1»"


# ── El traspaso se consume; el origen se queda ────────────────────────────────

@pytest.mark.parametrize("canal, valor", [
    ("portafolio_a_cargar", None),
    ("tickers_aprobados", ["KO"]),
])
def test_el_canal_de_traspaso_se_vacia_al_usarlo(canal, valor):
    """Si se quedase, volveria a pisar lo que el usuario escriba despues."""
    estado = {canal: valor or _portafolio("p", ["AAPL"])}
    sembrar(estado)
    assert canal not in estado


def test_el_origen_se_puede_olvidar_cuando_la_corrida_ya_es_del_usuario():
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL"])}
    assert sembrar(estado) == "cargado de «prueba 1»"
    configuracion.olvidar_origen(estado)
    assert sembrar(estado) == ""
    # Olvidar de donde vino no cambia lo que hay en el formulario.
    assert valores(estado)["tickers"] == "AAPL"


def test_una_lista_de_aprobados_vacia_no_cuenta_como_traspaso():
    estado = {"tickers_aprobados": []}
    assert sembrar(estado) == ""
    assert valores(estado)["tickers"] == POR_DEFECTO


# ── Guardar preferencias nuevas vuelve a sembrar ──────────────────────────────

def test_guardar_preferencias_nuevas_rehace_el_formulario():
    """«Guardadas. El optimizador arrancará con estos valores» es una promesa.

    El formulario guarda sus valores en sesión para que no se le cambien solos,
    y eso mismo haría que unas preferencias nuevas no se vieran hasta la
    siguiente sesión — con la pantalla de Perfil afirmando lo contrario.
    """
    estado: dict = {}
    sembrar(estado, Preferencias(tickers="KO, PEP"))
    assert valores(estado)["tickers"] == "KO, PEP"

    configuracion.reiniciar(estado)
    sembrar(estado, Preferencias(tickers="MO, PM", horizonte="1 Año"))
    assert valores(estado)["tickers"] == "MO, PM"
    assert valores(estado)["horizonte"] == "1 Año"


def test_reiniciar_tambien_borra_el_origen():
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL"])}
    sembrar(estado)
    configuracion.reiniciar(estado)
    assert sembrar(estado) == ""


def test_reiniciar_sobre_una_sesion_vacia_no_falla():
    estado: dict = {}
    configuracion.reiniciar(estado)
    assert sembrar(estado) == ""
