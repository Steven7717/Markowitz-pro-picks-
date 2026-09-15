# programa/tests/test_vistas_perfil.py
"""«Dónde vive todo», que prometia listarlo todo y se dejaba lo que mas importa.

La tabla enumeraba credenciales, preferencias, portafolios, actas, candidatos y
cachés — y omitia `libros/`, que es lo que el README describe como «cuánto
dinero tienes y en qué», y `libros/interpretaciones/`, que es lo unico que se
pagó con la clave del usuario. Una pantalla que dice «todo son ficheros en tu
ordenador» y se deja dos fuera no informa de menos: dice que no existen.

La pantalla es un guion de Streamlit --se ejecuta al importarse-- asi que no se
puede llamar a sus funciones. Se lee su fuente, que es lo que si se puede;
mismo recurso que `test_noticias_texto.py` con `vistas/candidatos.py`.
"""

from pathlib import Path

from interprete import archivo
from seguimiento import libro

RAIZ = Path(__file__).resolve().parent.parent


def _tabla() -> str:
    fuente = (RAIZ / "vistas" / "perfil.py").read_text(encoding="utf-8")
    return fuente.split("Dónde vive todo", 1)[1]


def test_la_tabla_nombra_los_libros():
    assert "libro_mod.DIRECTORIO" in _tabla()


def test_la_tabla_nombra_las_interpretaciones_que_se_pagaron():
    tabla = _tabla()
    assert "archivo_mod.SUBCARPETA" in tabla
    # Y colgando de `libros/`, que es donde viven de verdad: escritas como una
    # carpeta suelta dirian que estan en otro sitio.
    assert f"{{libro_mod.DIRECTORIO}}/{{archivo_mod.SUBCARPETA}}/" in tabla


def test_las_rutas_salen_de_las_constantes_y_no_escritas_a_mano():
    """El saboteador de verdad: mover `libros/` de sitio y que esta pantalla
    siguiera enseñando la ruta vieja. Ninguna fila lleva su carpeta escrita a
    mano, asi que mover una constante mueve lo que la pantalla promete."""
    tabla = _tabla()
    for literal in ("`actas/`", "`salidas/`", "`libros/`", "`portafolios/`"):
        assert literal not in tabla


def test_las_constantes_que_la_tabla_usa_son_las_que_el_programa_escribe():
    """Y que esos nombres sigan existiendo: un rename en `seguimiento/libro.py`
    dejaria la pantalla en blanco al abrirla, no un test en rojo."""
    assert libro.DIRECTORIO.name == "libros"
    assert archivo.SUBCARPETA == "interpretaciones"
