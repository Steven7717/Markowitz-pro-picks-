# programa/tests/test_migracion_metricas.py
"""La migración de los ficheros que guardaron texto de pantalla en `metricas`.

`vistas/optimizador.py` metía en `metricas` dos campos ya renderizados —la
ETIQUETA castellana de la estrategia y el «Sí»/«No» del shrinkage— y de ahí
salían a `portafolios/*.json` y, copiados enteros por
`seguimiento/libro.py:desde_portafolio`, a `libros/*.json`. La regla que eso
rompe la documenta `cartera.Portafolio.estrategia`: en disco va el dato, porque
el texto de pantalla puede reescribirse en cualquier momento.

**Lo que hace testable la migración es que el valor bueno ya está en el
fichero.** Los dos campos tienen al lado, en el mismo JSON, su hermano tipado:
`estrategia` y `shrinkage`. La migración copia de ahí y no traduce el texto, así
que no depende de ninguna redacción — ni de la de hoy ni de la de cuando se
guardó el fichero. Es la diferencia entre una migración que caduca y una que no:
`b8ec37b` le quitó el sufijo a «Paridad de riesgo (ERC)», y un fichero anterior
se migra igual de bien.

El texto viejo se lee para una sola cosa, y nunca para sacar el valor: para
detectar que el fichero **se contradice a sí mismo**. Ahí no se toca y se
informa, porque eso lo mira una persona.

Lo que este script no alcanza —una copia de seguridad, un fichero traído de otra
máquina— lo cubre la tolerancia de `exporter.py`, que trata un valor que no es
un dato como el texto ya escrito que es.
"""

import json

import pytest

import cartera
from optimizer import STRATEGY_LABELS
from scripts.migrar_metricas_guardadas import arreglos_de, migrar, migrar_fichero
from seguimiento import libro as libro_mod

ETIQUETA = STRATEGY_LABELS["max_sharpe"]


def _metricas(**campos) -> dict:
    base = {"sharpe": 1.42, "annual_return": 0.183, "horizon": "1_mes",
            "strategy": ETIQUETA, "shrinkage": "Sí"}
    base.update(campos)
    return base


def _portafolio_crudo(**campos) -> dict:
    """Un fichero como los de verdad: las `metricas` dicen lo mismo que el objeto.

    Coherentes por defecto y a propósito. La primera versión de este fichero las
    dejaba fijas en «Máximo Sharpe (Markowitz)» aunque el caso pidiese otra
    estrategia, y el guardarraíl de contradicción —que hace bien su trabajo— se
    negaba a migrarlas. Para probar un fichero que se contradice está el test
    que lo dice en el nombre, con las `metricas` puestas a mano.
    """
    metricas = campos.pop("metricas", None)
    base = {
        "nombre": "prueba",
        "fecha": "2026-09-01T19:01:54",
        "posiciones": [{"ticker": "AAPL", "peso": 0.6},
                       {"ticker": "MSFT", "peso": 0.4}],
        "horizonte": "1_mes",
        "estrategia": "max_sharpe",
        "peso_min": 0.0,
        "peso_max": 0.4,
        "permitir_cortos": False,
        "shrinkage": True,
        "nota": "por qué la guardé",
    }
    base.update(campos)
    base["metricas"] = metricas if metricas is not None else _metricas(
        strategy=STRATEGY_LABELS.get(base["estrategia"], ETIQUETA),
        shrinkage="Sí" if base["shrinkage"] else "No",
        horizon=base["horizonte"],
    )
    return base


def _libro_crudo(*portafolios) -> dict:
    return {
        "nombre": "prueba",
        "creado": "2026-09-08T19:48:56",
        "objetivos": [
            {"fecha": "2026-09-08", "base": "estrategia",
             "portafolio": p, "veredicto": {}}
            for p in portafolios
        ],
        "asientos": [],
    }


# ── El valor bueno sale del hermano, no del texto ────────────────────────────

def test_la_estrategia_se_toma_del_campo_tipado_de_al_lado():
    crudo = _portafolio_crudo(estrategia="risk_parity")
    assert migrar(crudo) == (2, [])
    assert crudo["metricas"]["strategy"] == "risk_parity"


def test_el_shrinkage_se_toma_del_campo_tipado_de_al_lado():
    crudo = _portafolio_crudo(shrinkage=False,
                              metricas=_metricas(strategy="max_sharpe", shrinkage="No"))
    assert migrar(crudo) == (1, [])
    assert crudo["metricas"]["shrinkage"] is False


def test_una_etiqueta_retirada_se_migra_igual_de_bien():
    """El caso que motivó todo: `b8ec37b` quitó el «(ERC)».

    Traduciendo el texto haría falta reconocer la redacción de cada época y este
    fichero se quedaría sin migrar. Leyendo el hermano, da igual qué ponga.
    """
    crudo = _portafolio_crudo(
        estrategia="risk_parity",
        metricas=_metricas(strategy="Paridad de riesgo (ERC)", shrinkage=True),
    )
    assert migrar(crudo) == (1, [])
    assert crudo["metricas"]["strategy"] == "risk_parity"


@pytest.mark.parametrize("texto", ["Activada", "SI", "sí", "true", ""])
def test_un_shrinkage_escrito_de_otra_forma_tambien(texto):
    """Misma idea: la palabra no se interpreta, se sustituye por el booleano."""
    crudo = _portafolio_crudo(
        shrinkage=True, metricas=_metricas(strategy="max_sharpe", shrinkage=texto))
    assert migrar(crudo) == (1, [])
    assert crudo["metricas"]["shrinkage"] is True


def test_el_horizonte_heredado_se_traduce_con_la_tabla_congelada():
    """El único sin hermano: antes no había clave, la etiqueta ERA la identidad.

    Aquí sí hay que leer el texto, y se puede porque `data._HEREDADOS` es una
    tabla escrita a mano y congelada —la redacción vigente hasta el 2026-09-20—,
    no una derivada de cómo se escriba hoy.
    """
    crudo = _portafolio_crudo(horizonte="3 Años",
                              metricas=_metricas(strategy="max_sharpe",
                                                 shrinkage=True, horizon="3 Años"))
    assert migrar(crudo) == (2, [])
    assert crudo["horizonte"] == "3_anos"
    assert crudo["metricas"]["horizon"] == "3_anos"


def test_el_horizonte_de_las_metricas_copia_del_campo_ya_arreglado():
    """Y no del que había al empezar, que todavía era «1 Mes».

    Es el orden lo que lo garantiza: el campo del portafolio se arregla primero
    y `metricas["horizon"]` copia del arreglado. Si copiase del otro, el fichero
    saldría con la clave arriba y la etiqueta dentro — el defecto de origen, otra
    vez y recién hecho.
    """
    crudo = _portafolio_crudo(horizonte="6 Meses",
                              metricas=_metricas(strategy="max_sharpe",
                                                 shrinkage=True, horizon="6 Meses"))
    migrar(crudo)
    assert crudo["metricas"]["horizon"] == crudo["horizonte"] == "6_meses"


def test_un_horizonte_que_no_es_de_hoy_ni_de_antes_no_se_adivina():
    crudo = _portafolio_crudo(horizonte="1 Quincena",
                              metricas=_metricas(strategy="max_sharpe",
                                                 shrinkage=True, horizon="1 Quincena"))
    cambiados, quejas = migrar(crudo)
    assert cambiados == 0
    assert crudo["horizonte"] == "1 Quincena"
    assert any("1 Quincena" in q for q in quejas)


# ── Lo que ya está bien no se toca ───────────────────────────────────────────

def test_un_fichero_ya_migrado_no_cambia():
    crudo = _portafolio_crudo(metricas=_metricas(strategy="max_sharpe", shrinkage=True))
    assert migrar(crudo) == (0, [])
    assert crudo == _portafolio_crudo(
        metricas=_metricas(strategy="max_sharpe", shrinkage=True))


def test_unas_metricas_sin_esos_campos_no_ganan_ninguno():
    crudo = _portafolio_crudo(metricas={"sharpe": 1.0})
    assert migrar(crudo) == (0, [])
    assert crudo["metricas"] == {"sharpe": 1.0}


def test_los_campos_tipados_no_se_tocan():
    """Esos ya cumplían la regla; son la fuente, no el destino."""
    crudo = _portafolio_crudo(estrategia="min_variance", shrinkage=False)
    migrar(crudo)
    assert crudo["estrategia"] == "min_variance"
    assert crudo["shrinkage"] is False


def test_no_se_toca_nada_mas_del_portafolio():
    crudo = _portafolio_crudo()
    esperado = _portafolio_crudo(
        metricas=_metricas(strategy="max_sharpe", shrinkage=True))
    migrar(crudo)
    assert crudo == esperado


# ── Cuando no se puede, se dice ──────────────────────────────────────────────

def test_sin_hermano_del_que_copiar_no_se_inventa_nada():
    crudo = _portafolio_crudo(estrategia="una_que_ya_no_existe")
    cambiados, quejas = migrar(crudo)
    assert cambiados == 1                       # el shrinkage sí se pudo
    assert crudo["metricas"]["strategy"] == ETIQUETA
    assert any("una_que_ya_no_existe" in q for q in quejas)


def test_un_fichero_que_se_contradice_a_si_mismo_no_se_pisa():
    """«Mínima varianza» en `metricas` y `max_sharpe` en el campo tipado.

    Copiar el hermano en silencio cambiaría lo que el fichero dice que pasó. Un
    fichero así lo ha editado alguien a mano, y eso lo mira una persona.
    """
    crudo = _portafolio_crudo(
        estrategia="max_sharpe",
        metricas=_metricas(strategy=STRATEGY_LABELS["min_variance"], shrinkage=True),
    )
    cambiados, quejas = migrar(crudo)
    assert cambiados == 0
    assert crudo["metricas"]["strategy"] == STRATEGY_LABELS["min_variance"]
    assert any("no dicen lo mismo" in q for q in quejas)


def test_un_shrinkage_que_contradice_a_su_hermano_tampoco():
    crudo = _portafolio_crudo(
        shrinkage=False, metricas=_metricas(strategy="max_sharpe", shrinkage="Sí"))
    cambiados, quejas = migrar(crudo)
    assert cambiados == 0
    assert crudo["metricas"]["shrinkage"] == "Sí"
    assert any("no dicen lo mismo" in q for q in quejas)


def test_arreglos_de_no_toca_nada():
    """Pura: quien llama decide si escribe, y eso es lo que permite `--simular`."""
    crudo = _portafolio_crudo()
    antes = json.dumps(crudo, ensure_ascii=False)
    _, cambios, _ = arreglos_de(crudo)
    assert cambios == {"strategy": "max_sharpe", "shrinkage": True}
    assert json.dumps(crudo, ensure_ascii=False) == antes


# ── Un libro ─────────────────────────────────────────────────────────────────

def test_un_libro_migra_el_portafolio_que_lleva_copiado_dentro():
    crudo = _libro_crudo(_portafolio_crudo())
    assert migrar(crudo) == (2, [])
    dentro = crudo["objetivos"][0]["portafolio"]["metricas"]
    assert dentro["strategy"] == "max_sharpe" and dentro["shrinkage"] is True


def test_un_libro_con_varios_objetivos_los_migra_todos():
    """Un libro apila objetivos: re-optimizar añade uno y no borra el anterior."""
    crudo = _libro_crudo(
        _portafolio_crudo(estrategia="max_sharpe"),
        _portafolio_crudo(estrategia="min_variance"),
    )
    assert migrar(crudo) == (4, [])
    claves = [o["portafolio"]["metricas"]["strategy"] for o in crudo["objetivos"]]
    assert claves == ["max_sharpe", "min_variance"]


def test_un_libro_sin_objetivos_no_revienta():
    assert migrar(_libro_crudo()) == (0, [])


# ── Sobre el fichero ─────────────────────────────────────────────────────────

def test_el_fichero_migrado_se_vuelve_a_poder_cargar(tmp_path):
    """La prueba de que el JSON sigue cumpliendo el contrato de `cartera`."""
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(_portafolio_crudo(), ensure_ascii=False),
                    encoding="utf-8")
    assert migrar_fichero(ruta) == (2, [])
    vuelto = cartera.cargar(ruta)
    assert vuelto.metricas["strategy"] == "max_sharpe"
    assert vuelto.metricas["shrinkage"] is True


def test_el_libro_migrado_se_vuelve_a_poder_cargar(tmp_path):
    ruta = tmp_path / "l.json"
    ruta.write_text(json.dumps(_libro_crudo(_portafolio_crudo()), ensure_ascii=False),
                    encoding="utf-8")
    assert migrar_fichero(ruta) == (2, [])
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
    ruta.write_text(
        json.dumps(_portafolio_crudo(
            metricas=_metricas(strategy="max_sharpe", shrinkage=True)),
            indent=2, ensure_ascii=False),
        encoding="utf-8")
    antes = ruta.read_bytes()
    assert migrar_fichero(ruta) == (0, [])
    assert ruta.read_bytes() == antes


def test_simular_no_escribe(tmp_path):
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(_portafolio_crudo(), indent=2, ensure_ascii=False),
                    encoding="utf-8")
    antes = ruta.read_bytes()
    cambiados, _ = migrar_fichero(ruta, simular=True)
    assert cambiados == 2
    assert ruta.read_bytes() == antes


def test_el_fichero_migrado_conserva_las_tildes_sin_escapar(tmp_path):
    """`cartera.guardar` escribe con `ensure_ascii=False`, y esto no lo cambia.

    Un fichero que vuelve con `\\u00e1` se lee igual desde Python y distinto
    desde cualquier otra cosa, el usuario incluido.
    """
    ruta = tmp_path / "p.json"
    ruta.write_text(
        json.dumps(_portafolio_crudo(nota="optimización de septiembre"),
                   indent=2, ensure_ascii=False),
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

    Y con los tres campos a la vez, como estaban de verdad: el horizonte en la
    redacción de entonces, la estrategia con un sufijo ya retirado y el
    shrinkage escrito en castellano.
    """
    guardado = cartera.desde_corrida(
        nombre="prueba", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="risk_parity", peso_min=0.0, peso_max=0.4,
        permitir_cortos=False, shrinkage=True,
        metricas={"sharpe": 1.2, "strategy": "Paridad de riesgo (ERC)",
                  "shrinkage": "Sí", "horizon": "1 Mes"},
    )
    ruta = cartera.guardar(guardado, directorio=tmp_path)
    assert migrar_fichero(ruta) == (4, [])
    vuelto = cartera.cargar(ruta)
    assert vuelto.horizonte == "1_mes"
    assert vuelto.metricas["horizon"] == "1_mes"
    assert vuelto.metricas["strategy"] == "risk_parity"
    assert vuelto.metricas["shrinkage"] is True
    assert vuelto.estrategia == "risk_parity"
    assert vuelto.pesos == [0.6, 0.4]
