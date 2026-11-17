# programa/tests/test_vistas_optimizador.py
"""Lo que la pantalla del optimizador tiene que llegar a decir.

`data.py` medía desde el principio la cobertura de cada serie --cuántas de las
fechas del horizonte trae cada ticker-- y la devolvía en `tickers_con_huecos`.
**Nadie la leía.** Ni una vista, ni un informe: el cálculo, la clave del
diccionario y sus tests existían, y un activo con el 11 % de sus sesiones
entraba en la optimización sin que el usuario se enterara.

La escalera de `historial.py` cubre el caso normal --nombra al activo que más
historia cuesta-- pero se calla en dos sitios: con dos activos no culpa a nadie,
porque quitar a uno dejaría uno solo, y con dos series rotas en las mismas
fechas quitar a cualquiera de las dos no gana ni una fecha. Dos activos es el
mínimo que el optimizador acepta.

La pantalla es un guion de Streamlit --se ejecuta al importarse-- así que no se
pueden llamar sus funciones. Se lee su fuente, que es lo que sí se puede; mismo
recurso que `test_vistas_perfil.py` y `test_noticias_texto.py`.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = (RAIZ / "vistas" / "optimizador.py").read_text(encoding="utf-8")
ARBOL = ast.parse(FUENTE)


def _cuerpo(nombre: str) -> str:
    funcion = next(n for n in ast.walk(ARBOL)
                   if isinstance(n, ast.FunctionDef) and n.name == nombre)
    return ast.get_source_segment(FUENTE, funcion)


def _llamadas(nombre: str) -> list[ast.Call]:
    return [n for n in ast.walk(ARBOL)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == nombre]


def test_la_pantalla_lee_la_cobertura_que_data_py_mide():
    """El defecto en una linea: la clave existia y no la leia nadie."""
    assert "tickers_con_huecos" in _cuerpo("_avisar_cobertura")


def test_quien_decide_si_la_cobertura_duele_es_el_modulo_probado():
    """La vista no filtra por su cuenta: llamar «rota» a una empresa joven es
    justo el aviso que se retiro de esta pantalla, y esa distincion vive en
    `historial.motivo_de`, que si tiene tests."""
    assert "historial.avisos_de_cobertura(" in _cuerpo("_avisar_cobertura")


def test_el_aviso_va_antes_que_los_errores_que_la_falta_de_datos_provoca():
    """La causa va antes que el sintoma, como con los tickers omitidos.

    Sin esto el usuario lee «datos insuficientes: 10 observaciones para 2
    activos» y no sabe cual de los dos las esta recortando; el aviso no llega
    nunca porque `_ejecutar` ya se ha ido por un `return None`.
    """
    cuerpo = _cuerpo("_ejecutar")
    assert cuerpo.index("_avisar_cobertura(") < cuerpo.index("Datos insuficientes")


def test_el_aviso_sobrevive_a_las_reejecuciones():
    """Dos veces, como `_avisar_omitidos`: en la corrida nueva y al repintar la
    guardada. Si solo se dijera en la corrida, cambiar de pestana o descargar el
    informe dejaria los resultados en pantalla y el aviso que los matiza fuera."""
    assert len(_llamadas("_avisar_cobertura")) == 2
    assert len(_llamadas("_avisar_cobertura")) == len(_llamadas("_avisar_omitidos"))


def test_el_aviso_no_se_repite_dentro_de_la_misma_reejecucion():
    """Las dos llamadas coinciden en la corrida recien lanzada."""
    assert "_cobertura_avisada" in _cuerpo("_avisar_cobertura")


def test_a_la_serie_con_huecos_se_le_ensena_la_cobertura_de_su_propio_tramo():
    """El 65% que le falta a una joven por no cotizar no son huecos.

    La cifra que trae `data.py` es sobre el horizonte. Detras de «le faltan
    fechas dentro de su propio historial» convierte un 12% real en un 65%
    aparente y manda a buscar una averia mucho mayor de la que hay --el mismo
    error por el que al activo joven y limpio no se le avisa en absoluto--.
    """
    cuerpo = _cuerpo("_linea_cobertura")
    assert 'a.motivo == "huecos"' in cuerpo
    assert "a.cobertura_interna" in cuerpo
    # Y la del horizonte no se pierde: es la que lo mete en la lista.
    assert "a.cobertura:" in cuerpo


def test_la_vista_no_arma_la_linea_dos_veces():
    """Una sola redaccion, para que las dos cifras no puedan divergir."""
    assert "_linea_cobertura(a)" in _cuerpo("_avisar_cobertura")


# ── Lo que la pantalla escribe en disco ───────────────────────────────────────
#
# El diccionario `metrics` no es solo del informe: se le pasa a
# `cartera.desde_corrida(metricas=...)`, que lo escribe en `portafolios/*.json`,
# y `seguimiento/libro.py:desde_portafolio` lo copia entero a `libros/*.json`.
# O sea que todo lo que entre aqui acaba en un fichero, y le aplica la regla que
# `cartera.Portafolio.estrategia` ya documenta: se guarda la CLAVE de la
# estrategia, no su etiqueta, porque la etiqueta es texto de pantalla y puede
# reescribirse en cualquier momento.
#
# `metrics["strategy"]` era `STRATEGY_LABELS[...]` y esquivaba la regla por el
# lado de al lado. La traduccion vive ahora en `exporter.py`, que es quien
# presenta.

from optimizer import STRATEGY_LABELS  # noqa: E402


def _diccionario_asignado(nombre: str) -> ast.Dict:
    """El diccionario literal que el guion asigna a `nombre` en el modulo."""
    return next(
        n.value for n in ARBOL.body
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
        and any(isinstance(d, ast.Name) and d.id == nombre for d in n.targets)
    )


def _valor_de(diccionario: ast.Dict, clave: str) -> str:
    return next(
        ast.get_source_segment(FUENTE, v)
        for k, v in zip(diccionario.keys, diccionario.values)
        if isinstance(k, ast.Constant) and k.value == clave
    )


def _cadenas_que_se_escriben(nodo):
    """Los literales de cadena que pueden acabar DENTRO del fichero.

    No los que indexan. En `optimal["sharpe"]` la cadena es la llave del
    diccionario del que se lee, no lo que se guarda, y contarla convertiria la
    regla en ruido: la primera version de este test se cayo justo ahi.
    """
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        yield nodo.value
        return
    for hijo in ast.iter_child_nodes(nodo):
        if isinstance(nodo, ast.Subscript) and hijo is nodo.slice:
            continue
        yield from _cadenas_que_se_escriben(hijo)


def test_lo_que_se_guarda_no_lleva_ni_una_cadena_escrita_a_mano():
    """La regla en su forma general: aqui se mide, no se redacta.

    Empezo mas estrecha --«ninguna etiqueta de `STRATEGY_LABELS`»-- y el campo
    de al lado enseño que no bastaba: `"shrinkage": "Si" if ... else "No"` no
    era una etiqueta de ese diccionario y era exactamente el mismo defecto, un
    dato renderizado a castellano y escrito en disco. Lo que los une no es de
    donde sale el texto, es que es TEXTO ESCRITO AQUI. Un literal de cadena
    entre los valores es, por definicion, algo que puso el codigo en vez de
    medirlo — y lo que se pone se puede reescribir mañana.
    """
    for valor in _diccionario_asignado("metrics").values:
        for nodo in ast.walk(valor):
            assert not (isinstance(nodo, ast.Name) and nodo.id == "STRATEGY_LABELS")
        for cadena in _cadenas_que_se_escriben(valor):
            raise AssertionError(f"«{cadena}» se escribiria tal cual en el fichero")


def test_la_regla_se_comprueba_sobre_los_valores_y_no_sobre_el_texto():
    """Por que el test de arriba anda por el AST en vez de buscar cadenas.

    Sobre el texto crudo sale mas corto y esta mal, y se vio: el diccionario
    lleva comentarios dentro, uno de ellos nombra «Paridad de riesgo (ERC)»
    para contar por que existe la regla, y eso contiene la etiqueta de hoy como
    subcadena. El test se caia solo al documentarse. Un comentario no se escribe
    en disco; lo que se escribe es lo que se evalua.
    """
    escrito = ast.get_source_segment(FUENTE, _diccionario_asignado("metrics"))
    assert "Paridad de riesgo" in escrito   # el comentario sigue ahi...
    assert not [                             # ...y no molesta.
        c for v in _diccionario_asignado("metrics").values
        for c in _cadenas_que_se_escriben(v)
    ]


def test_el_shrinkage_se_guarda_como_lo_que_es_y_no_como_se_lee():
    """El par de al lado, con la misma forma: el bool, no «Sí»/«No».

    `Portafolio.shrinkage` guarda el booleano en este mismo fichero, asi que
    `metricas` llevaba las dos formas del mismo hecho y una era de pantalla.
    """
    guardado = _diccionario_asignado("metrics")
    assert _valor_de(guardado, "shrinkage") == 'corrida["shrinkage"]'


def test_la_estrategia_se_guarda_por_su_clave():
    """La misma fuente que el campo `estrategia` del portafolio, sin traducir.

    Es lo que hace que los dos no puedan discrepar: el fichero guardaba
    `estrategia: "max_sharpe"` y, dos lineas mas abajo, `metricas.strategy`
    con la etiqueta de ese dia.
    """
    guardado = _diccionario_asignado("metrics")
    assert _valor_de(guardado, "strategy") == 'corrida["estrategia"]'


def test_la_pantalla_si_sigue_traduciendo_para_mirarla():
    """La etiqueta no desaparece: deja de escribirse, se sigue enseniando.

    Sin esto, «guardar la clave» se podria cumplir dejando `max_sharpe` en la
    cabecera de la pantalla y en la leyenda de la frontera eficiente.
    """
    assert "STRATEGY_LABELS[corrida[\"estrategia\"]]" in FUENTE


# ── Riesgo de cola: VaR y ES ──────────────────────────────────────────────────

def test_el_riesgo_se_calcula_una_vez_en_la_corrida():
    """Como la validación: repintar no puede volver a descargar ni backtestear."""
    cuerpo = _cuerpo("_ejecutar")
    assert "informe_riesgo(" in cuerpo
    assert '"riesgo":' in cuerpo
    assert FUENTE.count("informe_riesgo(") == 1


def test_la_falta_de_historia_se_explica_y_no_tumba_la_corrida():
    cuerpo = _cuerpo("_ejecutar")
    assert "except HistoriaInsuficiente" in cuerpo


def test_hay_pestana_de_riesgo():
    assert '"Riesgo: VaR y ES"' in FUENTE


def test_un_ticker_sin_datos_diarios_se_nombra_como_tal():
    """Con un ticker a 0 sesiones la historia común es 0, y «la que más recorta
    es X, con 0» manda a quitar historia que no existe: lo que pasa es que
    yfinance no devolvió ni un día de ese activo, y la pestaña tiene que
    decirlo así."""
    assert "sin_datos" in _cuerpo("_ejecutar")
    assert FUENTE.count("sin_datos") >= 2   # se guarda... y se lee en la pestaña


def _manejadores(cuerpo_de: str) -> list[ast.ExceptHandler]:
    funcion = next(n for n in ast.walk(ARBOL)
                   if isinstance(n, ast.FunctionDef) and n.name == cuerpo_de)
    return [n for n in ast.walk(funcion) if isinstance(n, ast.ExceptHandler)]


def test_cualquier_otro_fallo_del_riesgo_tampoco_tumba_la_corrida():
    """Un NaN que se cuele, pesos y columnas que no casen o la red caída en la
    descarga diaria: el reparto sigue valiendo, así que se guarda el motivo y
    la pestaña lo enseña. Sin `except:` desnudo, que se tragaría hasta Ctrl+C."""
    manejadores = _manejadores("_ejecutar")
    assert all(m.type is not None for m in manejadores)
    capturados = {ast.get_source_segment(FUENTE, m.type) for m in manejadores}
    assert "ValueError" in capturados
    assert "Exception" in capturados
    assert '"error":' in _cuerpo("_ejecutar")
    assert 'inf.get("error")' in FUENTE or "inf[\"error\"]" in FUENTE


def _try_que_llama(nombre: str) -> ast.Try:
    """El `try` cuyo cuerpo hace la llamada, no uno cualquiera de la función."""
    funcion = next(n for n in ast.walk(ARBOL)
                   if isinstance(n, ast.FunctionDef) and n.name == "_ejecutar")
    return next(
        t for t in ast.walk(funcion) if isinstance(t, ast.Try)
        and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == nombre for b in t.body for n in ast.walk(b)))


def test_el_informe_de_riesgo_no_tumba_la_corrida_por_nada():
    """`HistoriaInsuficiente` y `ValueError` son los fallos que se esperan;
    un `KeyError` o un `LinAlgError` de un caso que nadie previó también
    dejaría la página en rojo con un reparto perfectamente válido. El último
    manejador del `try` del informe es `Exception`, y guarda su tipo."""
    tipos = [ast.get_source_segment(FUENTE, h.type)
             for h in _try_que_llama("informe_riesgo").handlers]
    assert tipos == ["HistoriaInsuficiente", "ValueError", "Exception"]
    assert "type(error).__name__" in _cuerpo("_ejecutar")


def _seccion_riesgo() -> str:
    return FUENTE[FUENTE.index("with riesgo_tab:"):FUENTE.index("with exportar:")]


def _formateador_pct():
    """La función del módulo, sin ejecutar el guion: se compila sola."""
    nodo = next(n for n in ARBOL.body
                if isinstance(n, ast.FunctionDef) and n.name == "_pct")
    espacio: dict = {}
    exec(compile(ast.Module([nodo], []), "optimizador.py", "exec"), espacio)
    return espacio["_pct"]


def test_un_porcentaje_de_cero_no_lleva_signo():
    pct = _formateador_pct()
    assert pct(-1e-17) == "0.0%"
    assert pct(-0.0004) == "0.0%"
    assert pct(-0.0004, 2) == "-0.04%"
    assert pct(0.1234) == "12.3%"
    assert pct(-0.25, 0) == "-25%"


def test_la_tabla_por_activo_formatea_todos_sus_porcentajes_igual():
    """Una aportación al ES de −1e-17 salía «−0.0%»: toda columna en % de la
    tabla por activo pasa por `_pct`, ninguna por un f-string suelto."""
    tabla = _seccion_riesgo()
    tabla = tabla[tabla.index("##### Por activo"):]
    tabla = tabla[:tabla.index("for f in inf.activos")]
    assert "%}" not in tabla
    for columna in ("f.peso", "f.var99", "f.es975", "f.es99",
                    "f.fraccion_verde", "f.aportacion_es"):
        assert f"_pct({columna}" in tabla


def test_la_zona_no_lleva_flecha():
    """«3 excepciones» no es una subida: es un recuento, y la flecha ↑ lo
    pintaba como si lo fuera."""
    assert 'delta_arrow="off"' in _seccion_riesgo()


def test_una_diversificacion_nula_no_se_escribe_en_negativo():
    seccion = _seccion_riesgo()
    assert "inf.diversificacion > 0" in seccion
    assert "Diversificar no reduce el ES de esta cartera" in seccion


def test_la_tabla_de_metodos_ensena_el_var_medio():
    """Para que un ganador que gana por exceso de prudencia se vea: su tiempo
    en verde sale alto y su VaR medio, también."""
    assert '"VaR medio":' in _seccion_riesgo()
    assert "b.var99.mean()" in _seccion_riesgo()
