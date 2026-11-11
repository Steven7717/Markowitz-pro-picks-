"""Ninguna pantalla manda a una que no existe.

`st.switch_page` a un fichero que ya no está en el menú de `app.py` no falla al
arrancar: falla al pulsar el botón, delante del usuario. Al borrar «Noticias y
calendario» había dos botones que apuntaban a ella, en Seguimiento y en
Primeros pasos.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _paginas_declaradas() -> "list[str]":
    arbol = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    return [
        n.args[0].value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and ast.unparse(n.func) == "st.Page"
        and n.args
        and isinstance(n.args[0], ast.Constant)
    ]


def _destinos() -> dict:
    salida = {}
    for ruta in [*sorted((RAIZ / "vistas").glob("*.py")), RAIZ / "app.py"]:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if (
                isinstance(n, ast.Call)
                and ast.unparse(n.func).endswith("switch_page")
                and n.args
                and isinstance(n.args[0], ast.Constant)
            ):
                salida.setdefault(n.args[0].value, []).append(ruta.name)
    return salida


def test_cada_switch_page_va_a_una_pantalla_del_menu_que_existe():
    declaradas = set(_paginas_declaradas())
    destinos = _destinos()
    assert destinos, "no se encontró ningún switch_page: el test no está mirando nada"
    for destino, desde in destinos.items():
        assert destino in declaradas, f"{desde} mandan a {destino}, que no está en el menú"
        assert (RAIZ / destino).exists()


def test_noticias_salio_del_menu_y_del_repositorio():
    assert "vistas/noticias.py" not in _paginas_declaradas()
    assert not (RAIZ / "vistas" / "noticias.py").exists()


def test_primeros_pasos_presenta_el_analizador_donde_lo_pone_el_menu():
    # Quedó como tarjeta 6 bajo «Seguir lo que compraste», y en el menú está en
    # «Análisis», con los candidatos y el optimizador.
    fuente = (RAIZ / "vistas" / "inicio.py").read_text(encoding="utf-8")
    elegir, seguir = fuente.split('st.markdown("### Seguir lo que compraste")', 1)
    assert "vistas/analizador.py" in elegir and "vistas/analizador.py" not in seguir
    assert elegir.index("vistas/optimizador.py") < elegir.index("vistas/analizador.py")
    assert "estas tres pantallas" not in fuente


def test_la_clave_de_anthropic_se_pone_en_perfil_y_no_en_aprobacion():
    for ruta in sorted((RAIZ / "vistas").glob("*.py")):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "Falta la clave de Anthropic" in linea:
                assert "Perfil y ajustes" in linea, f"{ruta.name}: {linea.strip()}"


def test_el_analizador_va_en_analisis_detras_de_revisar_candidatos():
    fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
    analisis = fuente.split('"Análisis":', 1)[1].split('"Cartera":', 1)[0]
    assert analisis.index("vistas/candidatos.py") < analisis.index("vistas/analizador.py")


def test_ningun_texto_de_pantalla_manda_a_noticias():
    # Sobre las cadenas ya unidas por el parser: «la pantalla " "de **Noticias**»
    # va partida en dos literales en la fuente, y buscarla en el texto no la vería.
    for ruta in (RAIZ / "vistas").glob("*.py"):
        textos = [
            n.value for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        assert not any("**Noticias**" in t for t in textos), ruta.name
