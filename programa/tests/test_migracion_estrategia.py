# programa/tests/test_migracion_estrategia.py
"""La migración de los ficheros que guardaron la etiqueta de la estrategia.

`vistas/optimizador.py` metía en `metricas["strategy"]` la ETIQUETA castellana
de la estrategia en vez de su clave, y de ahí salía a `portafolios/*.json` y,
copiada entera por `seguimiento/libro.py:desde_portafolio`, a `libros/*.json`.
La regla que eso rompe la documenta `cartera.Portafolio.estrategia`: en disco
va la clave, porque la etiqueta es texto de pantalla y puede reescribirse en
cualquier momento.

Hay dos maneras de vivir con los ficheros ya escritos, y este proyecto usa las
dos, cada una para lo suyo:

- **Tolerancia al leer**, en `exporter.py`: un valor que no está entre las
  claves se trata como una etiqueta ya escrita y se imprime tal cual. Es lo que
  cubre una copia de seguridad, un fichero traído de otra máquina o uno editado
  a mano — lo que esta migración no puede alcanzar.
- **Migración**, este script: los ficheros de esta instalación se dejan en
  clave, para que la tolerancia sea una red de seguridad y no lo que sostiene
  los datos del usuario.

Un valor que no corresponde a ninguna etiqueta de HOY se queda como está y se
informa. No es un caso imaginado: `b8ec37b`, el 2026-09-20, le quitó el sufijo
«(ERC)» a «Paridad de riesgo (ERC)» — el mismo día que se escribió este fichero
y mientras se escribía. Un portafolio guardado antes de ese commit lleva dentro
un texto que ya no figura en `STRATEGY_LABELS`, y adivinar a qué clave pertenece
sería reescribir el pasado a ojo.
"""

import json

import pytest

import cartera
from optimizer import STRATEGY_LABELS
from scripts.migrar_estrategia_guardada import clave_de, migrar, migrar_fichero
from seguimiento import libro as libro_mod

ETIQUETA = STRATEGY_LABELS["max_sharpe"]


def _metricas(strategy=ETIQUETA) -> dict:
    metricas = {"sharpe": 1.42, "annual_return": 0.183, "horizon": "1 Mes"}
    if strategy is not None:
        metricas["strategy"] = strategy
    return metricas


def _portafolio_crudo(strategy=ETIQUETA) -> dict:
    return {
        "nombre": "prueba",
        "fecha": "2026-09-01T19:01:54",
        "posiciones": [{"ticker": "AAPL", "peso": 0.6},
                       {"ticker": "MSFT", "peso": 0.4}],
        "horizonte": "1 Mes",
        "estrategia": "max_sharpe",
        "peso_min": 0.0,
        "peso_max": 0.4,
        "permitir_cortos": False,
        "shrinkage": True,
        "metricas": _metricas(strategy),
        "nota": "por qué la guardé",
    }


def _libro_crudo(*estrategias) -> dict:
    return {
        "nombre": "prueba",
        "creado": "2026-09-08T19:48:56",
        "objetivos": [
            {"fecha": "2026-09-08", "base": "estrategia",
             "portafolio": _portafolio_crudo(e), "veredicto": {}}
            for e in estrategias
        ],
        "asientos": [],
    }


# ── La traducción, una a una ─────────────────────────────────────────────────

def test_cada_etiqueta_de_hoy_encuentra_su_clave():
    for clave, etiqueta in STRATEGY_LABELS.items():
        assert clave_de(etiqueta) == clave


def test_una_clave_no_es_una_etiqueta():
    """Ya está migrado: no hay nada que traducir, y traducir dos veces no existe."""
    for clave in STRATEGY_LABELS:
        assert clave_de(clave) is None


@pytest.mark.parametrize("valor", [
    "Paridad de riesgo (ERC)",    # la redacción anterior a `b8ec37b`
    "Máximo Sharpe",
    "",
    None,
    3.0,
])
def test_lo_que_no_es_una_etiqueta_de_hoy_no_se_adivina(valor):
    assert clave_de(valor) is None


# ── Un portafolio ────────────────────────────────────────────────────────────

def test_un_portafolio_guardado_con_la_etiqueta_sale_con_la_clave():
    crudo = _portafolio_crudo()
    assert migrar(crudo) == 1
    assert crudo["metricas"]["strategy"] == "max_sharpe"


def test_el_campo_estrategia_del_portafolio_no_se_toca():
    """Ese ya cumplía la regla. La migración arregla el de al lado, no éste."""
    crudo = _portafolio_crudo()
    migrar(crudo)
    assert crudo["estrategia"] == "max_sharpe"


def test_no_se_toca_nada_mas_del_portafolio():
    crudo = _portafolio_crudo()
    esperado = _portafolio_crudo()
    esperado["metricas"]["strategy"] = "max_sharpe"
    migrar(crudo)
    assert crudo == esperado


def test_un_portafolio_ya_migrado_no_cambia():
    crudo = _portafolio_crudo("max_sharpe")
    assert migrar(crudo) == 0
    assert crudo == _portafolio_crudo("max_sharpe")


def test_un_portafolio_sin_estrategia_en_las_metricas_no_gana_una():
    crudo = _portafolio_crudo(None)
    assert migrar(crudo) == 0
    assert "strategy" not in crudo["metricas"]


def test_una_etiqueta_que_ya_no_se_usa_se_queda_como_esta():
    """El caso de «(ERC)», que es real y del mismo día: se informa, no se adivina.

    `exporter.py` la sigue imprimiendo tal cual, que es lo que es: la etiqueta
    que se escribió aquel día. Reescribirla a la de hoy diría que el fichero
    guardó algo que no guardó.
    """
    crudo = _portafolio_crudo("Paridad de riesgo (ERC)")
    assert migrar(crudo) == 0
    assert crudo["metricas"]["strategy"] == "Paridad de riesgo (ERC)"


# ── Un libro ─────────────────────────────────────────────────────────────────

def test_un_libro_migra_el_portafolio_que_lleva_copiado_dentro():
    crudo = _libro_crudo(ETIQUETA)
    assert migrar(crudo) == 1
    assert crudo["objetivos"][0]["portafolio"]["metricas"]["strategy"] == "max_sharpe"


def test_un_libro_con_varios_objetivos_los_migra_todos():
    """Un libro apila objetivos: re-optimizar añade uno y no borra el anterior."""
    crudo = _libro_crudo(ETIQUETA, STRATEGY_LABELS["min_variance"])
    assert migrar(crudo) == 2
    claves = [o["portafolio"]["metricas"]["strategy"] for o in crudo["objetivos"]]
    assert claves == ["max_sharpe", "min_variance"]


def test_un_libro_cuenta_solo_los_objetivos_que_hacia_falta_tocar():
    crudo = _libro_crudo("max_sharpe", ETIQUETA)
    assert migrar(crudo) == 1


def test_un_libro_sin_objetivos_no_revienta():
    crudo = _libro_crudo()
    assert migrar(crudo) == 0


# ── Sobre el fichero ─────────────────────────────────────────────────────────

def test_el_fichero_migrado_se_vuelve_a_poder_cargar(tmp_path):
    """La prueba de que el JSON sigue cumpliendo el contrato de `cartera`."""
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(_portafolio_crudo(), ensure_ascii=False),
                    encoding="utf-8")
    assert migrar_fichero(ruta) == 1
    assert cartera.cargar(ruta).metricas["strategy"] == "max_sharpe"


def test_el_libro_migrado_se_vuelve_a_poder_cargar(tmp_path):
    ruta = tmp_path / "l.json"
    ruta.write_text(json.dumps(_libro_crudo(ETIQUETA), ensure_ascii=False),
                    encoding="utf-8")
    assert migrar_fichero(ruta) == 1
    leido = libro_mod.cargar(ruta)
    assert leido.objetivos[0].portafolio["metricas"]["strategy"] == "max_sharpe"


def test_un_fichero_sin_nada_que_migrar_conserva_sus_bytes(tmp_path):
    """Ni se reescribe ni se reformatea.

    Los ficheros de `portafolios/` se escribieron con `indent=2` y
    `ensure_ascii=False`; una reescritura con otros ajustes los movería enteros
    sin arreglar nada, y el usuario vería seis ficheros cambiados de fecha por
    una migración que no tocó ni un campo.
    """
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(_portafolio_crudo("max_sharpe"), indent=2,
                               ensure_ascii=False), encoding="utf-8")
    antes = ruta.read_bytes()
    assert migrar_fichero(ruta) == 0
    assert ruta.read_bytes() == antes


def test_el_fichero_migrado_conserva_las_tildes_sin_escapar(tmp_path):
    """`cartera.guardar` escribe con `ensure_ascii=False`, y esto no lo cambia.

    Un fichero que vuelve con `\\u00e1` se lee igual desde Python y distinto
    desde cualquier otra cosa, el usuario incluido.
    """
    ruta = tmp_path / "p.json"
    crudo = _portafolio_crudo()
    crudo["nota"] = "optimización de septiembre"
    ruta.write_text(json.dumps(crudo, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    migrar_fichero(ruta)
    assert "optimización" in ruta.read_text(encoding="utf-8")


def test_un_fichero_ilegible_se_deja_en_paz(tmp_path):
    """Un JSON roto no se borra ni se sobrescribe: se informa y se sigue."""
    ruta = tmp_path / "roto.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(cartera.ContratoRoto):
        migrar_fichero(ruta)
    assert ruta.read_text(encoding="utf-8") == "{esto no es json"


def test_el_fichero_guardado_por_el_programa_es_el_caso_real(tmp_path):
    """De punta a punta con el código de verdad, no con un JSON a mano.

    `cartera.guardar` escribe, la migración reescribe y `cartera.cargar`
    devuelve un portafolio entero: es exactamente lo que pasa con los ficheros
    de `portafolios/` de esta instalación.
    """
    guardado = cartera.desde_corrida(
        nombre="prueba", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=0.4,
        permitir_cortos=False, shrinkage=True, metricas=_metricas(),
    )
    ruta = cartera.guardar(guardado, directorio=tmp_path)
    assert migrar_fichero(ruta) == 1
    vuelto = cartera.cargar(ruta)
    assert vuelto.metricas["strategy"] == "max_sharpe"
    assert vuelto.estrategia == "max_sharpe"
    assert vuelto.pesos == [0.6, 0.4]
