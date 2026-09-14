# programa/tests/test_noticias_texto.py
"""El escapado, y la unica pantalla que se habia quedado atras.

`noticias/texto.py` existe porque el escapado es **una decision de seguridad con
una sola copia**: su propio docstring dice que dos copias se separan igual de
facil que cualquier otro par, con la diferencia de que la que se queda atras no
da un numero raro --sigue pintando texto, sin mas, hasta el dia en que uno lleve
un dolar--.

Eso es literalmente lo que habia pasado. Toda la app pinta el texto ajeno via
`plano` --`vistas/noticias.py`, `vistas/panel_ia.py`, `vistas/rebalanceo.py`--
menos la ficha del candidato, que pintaba la tesis, la afirmacion y la **cita
copiada del filing** en crudo. No es XSS, porque Streamlit sanea el HTML; es
inyeccion de markdown: enlaces al dominio de quien escribio el documento,
imagenes remotas que confirman que la ficha se abrio, y `$…$` como LaTeX, que se
come la linea entera hasta el siguiente dolar.
"""

import ast
from pathlib import Path

from noticias import texto

RAIZ = Path(__file__).resolve().parent.parent

# La prueba de concepto de la auditoria, tal cual: un filing que dice esto
# pintaba un enlace pulsable al dominio del emisor y se comia «y 1000M».
HOSTIL = "Consulta [el aviso oficial](https://sec-alertas.example/XYZ) y $1000M."


def test_el_texto_hostil_del_filing_sale_inerte():
    salido = texto.plano(HOSTIL)
    assert salido == (
        r"Consulta \[el aviso oficial\](https://sec-alertas.example/XYZ) y \$1000M."
    )


def test_una_cita_se_pinta_en_bloque_sin_markdown_dentro():
    """La cita va como bloque citado, que es lo que la distingue a simple vista
    de lo que escribio el modelo. El `>` lo pone el codigo; lo de dentro, no."""
    salido = texto.cita_en_bloque("  Our business   is subject\nto competition. ")
    assert salido.startswith("> ")
    # Los blancos se colapsan: un filing trae saltos de linea a mitad de frase,
    # y un salto dentro de un bloque citado lo parte en dos.
    assert salido == "> Our business is subject to competition."


def test_una_cita_hostil_no_se_lleva_el_bloque_por_delante():
    salido = texto.cita_en_bloque(HOSTIL)
    assert "](" not in salido.replace(r"\]", "")
    assert r"\$" in salido


def test_una_cita_vacia_no_pinta_un_bloque_vacio():
    """Un `>` solo se pinta como una raya gris sin texto, que se lee como que la
    cita existe y esta en blanco. No tener cita es otra cosa."""
    assert texto.cita_en_bloque("   ") == ""


# --- La copia que se habia quedado atras ------------------------------------


# Lo que Streamlit interpreta como markdown al pintarlo.
_PINTAN = {"markdown", "caption", "write", "info", "warning", "error", "success"}

# Las variables por las que entra texto que no escribio este programa: la
# narrativa la escribio el modelo y la cita la copio del filing, que lo escribio
# la empresa. Se busca por nombre porque es lo que hay -- la ficha es un
# diccionario leido de `fichas.json`, no un tipo que se pueda marcar.
_AJENAS = {"narrativa", "riesgo", "fuente"}


def _sin_escapar(arbol: ast.AST) -> list:
    """Los trozos de texto ajeno que llegan a una llamada que pinta markdown sin
    haber pasado por `noticias/texto.py`.

    Se mira solo dentro de las llamadas que pintan: `riesgo["verificada"]` en un
    `if` o `narrativa["riesgos"]` en un `for` no pintan nada, y marcarlos seria
    un test que obliga a escapar booleanos.
    """
    crudas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        if not isinstance(funcion, ast.Attribute) or funcion.attr not in _PINTAN:
            continue
        crudas.extend(_ajenas_fuera_de_texto(nodo))
    return crudas


def _ajenas_fuera_de_texto(nodo: ast.AST) -> list:
    """Recorre el arbol parando en cuanto entra en una llamada a `texto.algo`:
    lo que hay ahi dentro ya esta escapado y no hay que seguir mirando."""
    if isinstance(nodo, ast.Call):
        funcion = nodo.func
        if (
            isinstance(funcion, ast.Attribute)
            and isinstance(funcion.value, ast.Name)
            and funcion.value.id == "texto"
        ):
            return []
    crudas = []
    if (
        isinstance(nodo, ast.Subscript)
        and isinstance(nodo.value, ast.Name)
        and nodo.value.id in _AJENAS
    ):
        crudas.append(nodo)
    for hijo in ast.iter_child_nodes(nodo):
        crudas.extend(_ajenas_fuera_de_texto(hijo))
    return crudas


def test_la_ficha_del_candidato_no_pinta_nada_ajeno_sin_escapar():
    """El saboteador: quitar un `texto.plano` de `vistas/candidatos.py` tumba
    esto. La pantalla es un guion de Streamlit --se ejecuta al importarse-- asi
    que no se puede llamar a sus funciones; se lee su fuente, que es lo que si
    se puede.
    """
    fuente = (RAIZ / "vistas" / "candidatos.py").read_text(encoding="utf-8")
    crudas = _sin_escapar(ast.parse(fuente))
    assert crudas == [], (
        "vistas/candidatos.py pinta texto del modelo o del filing sin pasarlo "
        "por noticias/texto.py, en las lineas "
        + ", ".join(str(n.lineno) for n in crudas)
    )


def test_el_saboteador_de_ese_test_lo_tumba():
    """Un test que lee fuente y no falla nunca es decoracion. Este comprueba que
    el de arriba sabe ver el defecto que existia de verdad."""
    antes = "st.markdown(f\"> {' '.join(riesgo['cita'].split())}\")"
    assert len(_sin_escapar(ast.parse(antes))) == 1
