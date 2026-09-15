import json
from datetime import datetime

import numpy as np
import pytest

import cartera
from cartera import ContratoRoto, NombreInvalido, Portafolio, Posicion

AHORA = datetime(2026, 9, 1, 14, 25, 30)

METRICAS = {
    "sharpe": 1.42,
    "annual_return": 0.183,
    "annual_vol": 0.129,
    "oos_sharpe": 0.91,
    "oos_equal_weight_sharpe": 0.77,
    "n_obs": 504,
}


def ejemplo(**cambios) -> Portafolio:
    argumentos = {
        "nombre": "Mi cartera",
        "tickers": ["AAPL", "MSFT", "BRK-B"],
        "pesos": [0.5, 0.3, 0.2],
        "horizonte": "1 Mes",
        "estrategia": "max_sharpe",
        "peso_min": 0.0,
        "peso_max": 1.0,
        "permitir_cortos": False,
        "shrinkage": True,
        "metricas": METRICAS,
        "ahora": AHORA,
    }
    argumentos.update(cambios)
    return cartera.desde_corrida(**argumentos)


# --- Guardar y volver --------------------------------------------------------


def test_lo_guardado_vuelve_igual(tmp_path):
    ruta = cartera.guardar(ejemplo(), tmp_path)
    vuelto = cartera.cargar(ruta)
    assert vuelto.nombre == "Mi cartera"
    assert vuelto.tickers == ["AAPL", "MSFT", "BRK-B"]
    assert vuelto.pesos == [0.5, 0.3, 0.2]
    assert vuelto.estrategia == "max_sharpe"
    assert vuelto.metricas["sharpe"] == 1.42


def test_los_pesos_de_numpy_se_guardan_como_numeros_de_python(tmp_path):
    # El optimizador devuelve un numpy.ndarray. json.dumps no sabe serializar un
    # numpy.float64 y revienta con un TypeError, en el momento exacto en que el
    # usuario acaba de pulsar "Guardar" y cree que ya lo tiene a salvo.
    portafolio = ejemplo(pesos=np.array([0.5, 0.3, 0.2]), metricas={"sharpe": np.float64(1.42)})
    ruta = cartera.guardar(portafolio, tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    assert crudo["posiciones"][0]["peso"] == 0.5
    assert crudo["metricas"]["sharpe"] == 1.42


def test_un_ticker_sin_su_peso_no_llega_a_guardarse():
    # Dos listas paralelas de distinta longitud producirian una cartera con los
    # pesos corridos un puesto: se lee perfectamente bien y es otra cartera.
    with pytest.raises(ContratoRoto, match="no son la misma cartera"):
        ejemplo(tickers=["AAPL", "MSFT"], pesos=[0.5])


def test_guardar_dos_veces_el_mismo_nombre_deja_dos_fotografias(tmp_path):
    # Sobrescribir en silencio borraria una corrida que el usuario pidio
    # guardar. Pidio guardar las dos veces.
    primera = cartera.guardar(ejemplo(), tmp_path)
    segunda = cartera.guardar(ejemplo(), tmp_path)
    assert primera != segunda
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_un_portafolio_sin_nombre_no_se_guarda():
    with pytest.raises(NombreInvalido):
        ejemplo(nombre="   ")


def test_el_nombre_conserva_tildes_y_parentesis_aunque_el_fichero_no(tmp_path):
    # El nombre de verdad viaja dentro del JSON; el del fichero es solo una
    # etiqueta que el sistema de ficheros acepte.
    ruta = cartera.guardar(ejemplo(nombre="Cartera Año 2026 (v2)"), tmp_path)
    assert cartera.cargar(ruta).nombre == "Cartera Año 2026 (v2)"
    assert ruta.name == "2026-09-01-142530-cartera-ano-2026-v2.json"


# --- Listar ------------------------------------------------------------------


def test_la_lista_llega_de_lo_mas_nuevo_a_lo_mas_viejo(tmp_path):
    cartera.guardar(ejemplo(nombre="vieja", ahora=datetime(2026, 1, 1, 9, 0, 0)), tmp_path)
    cartera.guardar(ejemplo(nombre="nueva", ahora=datetime(2026, 8, 1, 9, 0, 0)), tmp_path)
    nombres = [e.portafolio.nombre for e in cartera.listar(tmp_path)]
    assert nombres == ["nueva", "vieja"]


def test_una_carpeta_que_no_existe_es_una_lista_vacia_no_un_fallo(tmp_path):
    assert cartera.listar(tmp_path / "todavia-no") == []


def test_un_fichero_roto_aparece_en_la_lista_con_su_motivo(tmp_path):
    # Saltarselo lo haria indistinguible de uno que nunca se guardo, y el
    # usuario se quedaria buscando en la carpeta equivocada.
    cartera.guardar(ejemplo(nombre="buena"), tmp_path)
    (tmp_path / "2020-01-01-000000-rota.json").write_text("{ no es json", encoding="utf-8")

    entradas = cartera.listar(tmp_path)
    assert len(entradas) == 2
    rotas = [e for e in entradas if e.portafolio is None]
    assert len(rotas) == 1
    assert "no se puede leer" in rotas[0].error


# --- El contrato de lectura --------------------------------------------------


def test_un_peso_que_no_es_numero_falla_aqui_y_no_tres_pantallas_despues(tmp_path):
    ruta = cartera.guardar(ejemplo(), tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["posiciones"][1]["peso"] = "mucho"
    ruta.write_text(json.dumps(crudo), encoding="utf-8")

    with pytest.raises(ContratoRoto, match="no es un número"):
        cartera.cargar(ruta)


def test_un_campo_que_falta_se_nombra(tmp_path):
    ruta = cartera.guardar(ejemplo(), tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    del crudo["estrategia"]
    ruta.write_text(json.dumps(crudo), encoding="utf-8")

    with pytest.raises(ContratoRoto, match="estrategia"):
        cartera.cargar(ruta)


def test_un_portafolio_sin_posiciones_no_es_un_portafolio(tmp_path):
    ruta = cartera.guardar(ejemplo(), tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["posiciones"] = []
    ruta.write_text(json.dumps(crudo), encoding="utf-8")

    with pytest.raises(ContratoRoto, match="ninguna posición"):
        cartera.cargar(ruta)


def test_lo_que_no_tiene_forma_de_ticker_se_rechaza(tmp_path):
    # El destino de estos tickers es yfinance y el panel del optimizador.
    ruta = cartera.guardar(ejemplo(), tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo["posiciones"][0]["ticker"] = "../../etc/passwd"
    ruta.write_text(json.dumps(crudo), encoding="utf-8")

    with pytest.raises(ContratoRoto, match="forma de ticker"):
        cartera.cargar(ruta)


def test_borrar_algo_que_ya_no_esta_no_es_un_error(tmp_path):
    cartera.borrar(tmp_path / "no-existe.json")


def test_la_fecha_ilegible_se_muestra_cruda_en_vez_de_reventar():
    # Un JSON editado a mano no puede dejar la lista entera sin pintar: es la
    # unica pantalla desde la que se puede llegar a borrar el fichero malo.
    portafolio = Portafolio(
        nombre="rara",
        fecha="ayer por la tarde",
        posiciones=[Posicion("AAPL", 1.0)],
        horizonte="1 Mes",
        estrategia="max_sharpe",
        peso_min=0.0,
        peso_max=1.0,
        permitir_cortos=False,
        shrinkage=True,
    )
    assert portafolio.fecha_legible == "ayer por la tarde"


# ── R4 y R6 · Lo que el fichero se lleva tiene que volver entero ──────────────
#
# Un portafolio guardado es una fotografía, y hasta ahora la fotografía no
# incluía contra qué listón se había dictado su propio veredicto ni si sus
# pesos estaban identificados. Las dos cosas se escriben planas —campos
# sueltos, no diccionarios anidados— porque `_serializable` convierte a
# `str(...)` todo lo que no sabe serializar, y un dict volvería del JSON como
# la cadena "{'mejor': 'MSFT', ...}".

from validation import (  # noqa: E402
    identificabilidad_guardada,
    metricas_de_identificabilidad,
    metricas_de_validacion,
    veredicto_guardado,
)

RECORRIDO = {
    "out_of_sample_sharpe": 0.91,
    "equal_weight_sharpe": 0.77,
    "sharpe_stderr": 0.42,
    "gap_stderr": 0.05,
    "umbral_veredicto": 0.10,
    "sigmas_veredicto": 2.0,
    "beats_equal_weight": True,
    "n_windows": 9,
}

MEDICION_PESOS = {
    "mejor": "MSFT", "peor": "AMZN", "brecha": 0.21, "stderr": 0.31, "anos": 2.0,
}


def test_el_umbral_y_las_sigmas_sobreviven_al_viaje_por_el_disco(tmp_path):
    """Sin ellos, `beats_equal_weight` es un dogma que nadie puede recomprobar."""
    metricas = {**METRICAS, **metricas_de_validacion(RECORRIDO)}
    vuelto = cartera.cargar(cartera.guardar(ejemplo(metricas=metricas), tmp_path))
    assert vuelto.metricas["oos_umbral_veredicto"] == pytest.approx(0.10)
    assert vuelto.metricas["oos_sigmas_veredicto"] == pytest.approx(2.0)


def test_el_veredicto_se_vuelve_a_dictar_igual_despues_de_ir_al_disco(tmp_path):
    metricas = {**METRICAS, **metricas_de_validacion(RECORRIDO)}
    vuelto = cartera.cargar(cartera.guardar(ejemplo(metricas=metricas), tmp_path))
    assert veredicto_guardado(vuelto.metricas)["estado"] is True
    assert veredicto_guardado(vuelto.metricas)["discrepa"] is False


def test_la_medicion_de_los_pesos_vuelve_como_numeros_y_no_como_texto(tmp_path):
    metricas = {**METRICAS, **metricas_de_identificabilidad(MEDICION_PESOS)}
    vuelto = cartera.cargar(cartera.guardar(ejemplo(metricas=metricas), tmp_path))
    assert vuelto.metricas["ident_mejor"] == "MSFT"
    assert vuelto.metricas["ident_brecha"] == pytest.approx(0.21)
    assert identificabilidad_guardada(vuelto.metricas)["identificada"] is False


def test_un_portafolio_viejo_sin_los_campos_nuevos_se_sigue_leyendo(tmp_path):
    """Los ficheros de `portafolios/` son de antes: no pueden dejar de abrirse."""
    viejo = {
        "nombre": "prueba 1",
        "fecha": "2026-09-10T10:52:38",
        "posiciones": [{"ticker": "AAPL", "peso": 0.6}, {"ticker": "MSFT", "peso": 0.4}],
        "horizonte": "1 Mes",
        "estrategia": "max_sharpe",
        "peso_min": 0.0,
        "peso_max": 1.0,
        "permitir_cortos": False,
        "shrinkage": True,
        "metricas": {"sharpe": 1.86, "oos_sharpe": 2.2389, "oos_windows": 4.0},
        "nota": "",
    }
    ruta = tmp_path / "viejo.json"
    ruta.write_text(json.dumps(viejo), encoding="utf-8")

    cargado = cartera.cargar(ruta)
    assert cargado.metricas["oos_sharpe"] == pytest.approx(2.2389)
    # Y ni se inventa un veredicto ni se inventa un aviso sobre los pesos.
    assert veredicto_guardado(cargado.metricas) is None
    assert identificabilidad_guardada(cargado.metricas) is None
