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
