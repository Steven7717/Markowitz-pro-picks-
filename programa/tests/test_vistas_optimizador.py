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
