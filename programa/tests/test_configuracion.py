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
        # No viene del portafolio: el fichero no lleva ese campo.
        "pares": False,
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


def test_la_covarianza_por_pares_arranca_apagada_y_no_la_trae_un_portafolio():
    """Es una decision sobre como estimar, de esta corrida, no del portafolio.

    El fichero guardado no lleva ese campo --no existia cuando se guardo-- asi
    que cargarlo no puede encenderla ni apagarla sin inventarse lo que quiso su
    dueño.
    """
    estado = {"portafolio_a_cargar": _portafolio("prueba 1", ["AAPL", "MU"])}
    sembrar(estado)
    assert valores(estado)["pares"] is False


def test_lo_que_el_usuario_marque_en_pares_sobrevive():
    estado: dict = {}
    sembrar(estado)
    estado[configuracion.CLAVES["pares"]] = True
    sembrar(estado)
    assert valores(estado)["pares"] is True


def test_un_portafolio_con_pesos_fuera_del_rango_no_deja_la_pantalla_en_blanco():
    """Los deslizadores van de 0 a 20 y de 20 a 100; el fichero, de 0 a 1.

    `cargar` acepta cualquier float y `sembrar` lo escribia sin acotar, asi que
    un portafolio editado a mano, venido de otra version o compartido por
    alguien reventaba el widget al construirlo -- `StreamlitValueAboveMaxError`
    -- y la pagina entera se quedaba en blanco antes de pintar nada. Y el valor
    malo se quedaba en sesion: seguia rota hasta cargar otro o reiniciar.

    Es el mismo fallo que `preferencias.saneadas()` documenta y evita; el canal
    del portafolio no pasaba por ahi.
    """
    estado = {
        "portafolio_a_cargar": _portafolio(
            "de otra version", ["AAPL", "MU"], peso_min=0.30, peso_max=1.50
        )
    }

    sembrar(estado)

    assert 0 <= estado[configuracion.CLAVES["peso_min"]] <= 20
    assert 20 <= estado[configuracion.CLAVES["peso_max"]] <= 100


def test_un_portafolio_con_pesos_dentro_del_rango_se_siembra_tal_cual():
    estado = {
        "portafolio_a_cargar": _portafolio(
            "normal", ["AAPL", "MU"], peso_min=0.05, peso_max=0.40
        )
    }

    sembrar(estado)

    assert estado[configuracion.CLAVES["peso_min"]] == 5
    assert estado[configuracion.CLAVES["peso_max"]] == 40


# ── Lo que el portafolio trae y el formulario no puede mostrar ────────────────
#
# Los deslizadores ya estaban protegidos, y el comentario que lo hizo dice por
# qué: «Streamlit revienta al CONSTRUIR el widget, o sea que la página se queda
# en blanco antes de pintar nada, y el valor malo se queda en sesión: sigue rota
# hasta cargar otro portafolio o reiniciar».
#
# Esa misma frase vale palabra por palabra para los otros dos campos del mismo
# bloque. `st.selectbox(options=list(HORIZON_CONFIG), key=...)` y
# `st.radio(options=list(STRATEGY_LABELS), key=...)` revientan igual si la
# sesión trae un valor que no está entre las opciones, y `cartera.cargar` valida
# el contrato del fichero pero no que el horizonte siga existiendo.
#
# `preferencias.saneadas()` protege los dos desde el principio --con su aviso--,
# así que el canal de las preferencias no puede traer nada de esto. El del
# portafolio sí: un fichero de otra versión, uno editado a mano, o uno guardado
# antes de que se retirase un horizonte.

from data import HORIZON_CONFIG  # noqa: E402
from optimizer import STRATEGY_LABELS  # noqa: E402


def test_un_horizonte_que_ya_no_existe_no_deja_el_formulario_sin_pintar():
    estado = {"portafolio_a_cargar": _portafolio(
        "viejo", ["AAPL", "MU"], horizonte="8 Meses"
    )}

    sembrar(estado)

    assert valores(estado)["horizonte"] in HORIZON_CONFIG


def test_una_estrategia_que_ya_no_existe_tampoco():
    estado = {"portafolio_a_cargar": _portafolio(
        "viejo", ["AAPL", "MU"], estrategia="momentum_12_1"
    )}

    sembrar(estado)

    assert valores(estado)["estrategia"] in STRATEGY_LABELS


def test_lo_que_se_deja_en_su_sitio_es_lo_que_ya_habia_sembrado():
    """No un valor de fábrica: lo que el usuario tenía, que es suyo.

    `sembrar` ya ha puesto las preferencias en el formulario cuando llega el
    canal del portafolio, así que el repuesto está ahí mismo y es mejor que
    `DEFAULT_HORIZON`.
    """
    estado = {"portafolio_a_cargar": _portafolio(
        "viejo", ["AAPL", "MU"], horizonte="8 Meses", estrategia="momentum_12_1"
    )}

    sembrar(estado, Preferencias(horizonte="1 Año", estrategia="min_variance"))

    assert valores(estado)["horizonte"] == "1 Año"
    assert valores(estado)["estrategia"] == "min_variance"


def test_un_horizonte_y_una_estrategia_validos_se_siembran_tal_cual():
    """El guardarraíl no puede comerse el caso normal, que es todos los demás."""
    estado = {"portafolio_a_cargar": _portafolio(
        "normal", ["AAPL", "MU"], horizonte="3 Años", estrategia="risk_parity"
    )}

    sembrar(estado, Preferencias(horizonte="1 Mes", estrategia="max_sharpe"))

    assert valores(estado)["horizonte"] == "3 Años"
    assert valores(estado)["estrategia"] == "risk_parity"


def test_la_sustitucion_se_dice_en_vez_de_hacerse_en_silencio():
    """Cambiar en silencio lo que el usuario guardó sería peor que el defecto.

    Es la regla que `vistas/portafolios.py` ya aplica al veredicto: «el usuario
    recuerda lo que leyó el día que lo guardó, y tiene derecho a saber que el
    listón cambió». Aquí el formulario diría «cargado de X» mientras muestra un
    horizonte que X no pidió.
    """
    estado = {"portafolio_a_cargar": _portafolio(
        "viejo", ["AAPL", "MU"], horizonte="8 Meses"
    )}

    origen = sembrar(estado)

    assert "8 Meses" in origen
    assert "viejo" in origen


def test_sin_sustituciones_el_origen_no_se_ensucia():
    estado = {"portafolio_a_cargar": _portafolio("normal", ["AAPL", "MU"])}

    origen = sembrar(estado)

    assert origen == "cargado de «normal»"
