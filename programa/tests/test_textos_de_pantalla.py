"""Ningún texto de pantalla lleva un `$` sin escapar.

En el markdown de Streamlit `$…$` es LaTeX: «cuesta como mucho **0.26 $**, y
normalmente alrededor de **0.12 $**» salía como «0.26 **, y normalmente
alrededor de **0.12 .», con lo de en medio en fórmula (recorrido de la app
real, Task 21 de N2). Un `$` suelto se pinta bien, pero basta con que la frase
gane una segunda cifra para que se rompa, así que se escapan todos: `\\$`.

Se mira sobre los literales del parser, ya unidos, y no sobre la fuente: los
comentarios no se pintan. Quedan fuera los docstrings y los patrones de `re`,
que tampoco son texto de pantalla. Lo que escribe el modelo o una web pasa por
`noticias.texto.plano`, que ya escapa el `$`.
"""

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHEROS = [*sorted((RAIZ / "vistas").glob("*.py")), *sorted(RAIZ.glob("medidores*.py"))]
SIN_ESCAPAR = re.compile(r"(?<!\\)\$")


def _excluidos(arbol: ast.AST) -> "set[int]":
    fuera = set()
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if (
            isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and cuerpo
            and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
        ):
            fuera.add(id(cuerpo[0].value))
        if isinstance(nodo, ast.Call) and ast.unparse(nodo.func).startswith("re."):
            fuera.update(id(a) for a in nodo.args)
    return fuera


def dolares_sin_escapar(fuente: str) -> "list[str]":
    arbol = ast.parse(fuente)
    fuera = _excluidos(arbol)
    return [
        n.value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in fuera
        and SIN_ESCAPAR.search(n.value)
    ]


def test_ningun_texto_de_pantalla_lleva_un_dolar_sin_escapar():
    for ruta in FICHEROS:
        assert dolares_sin_escapar(ruta.read_text(encoding="utf-8")) == [], ruta.name


def test_el_detector_ve_el_dolar_de_un_f_string_y_no_el_escapado():
    # Sin esto el test de arriba podría pasar por no mirar nada.
    assert dolares_sin_escapar('x = f"cuesta **{c:.2f} $**"') == [" $**"]
    assert dolares_sin_escapar('x = f"cuesta **{c:.2f} \\\\$**"') == []
    assert dolares_sin_escapar('import re\nP = re.compile(r"^A$")') == []
    assert dolares_sin_escapar('def f():\n    """Vale 5 $ y 6 $."""') == []
