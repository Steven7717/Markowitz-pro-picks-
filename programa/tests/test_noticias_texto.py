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
    # El guion de "sec-alertas" tambien sale escapado desde que `ESPECIALES`
    # cubre los caracteres de bloque: `-` abre vineta y raya horizontal al
    # principio de una linea, y el escapado se pinta como el guion de siempre.
    assert salido == (
        r"Consulta \[el aviso oficial\](https://sec\-alertas.example/XYZ) y \$1000M."
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


# --- La url, lo unico de una noticia que no se escapaba ----------------------
#
# El `url` sale de yfinance (`noticias/prensa.py`: `canonicalUrl.url`, sin
# validar ni el esquema) y de EDGAR. El destino va entre `<>` desde que las
# urls con parentesis cortaban el enlace a la mitad, pero un `>` dentro de la
# url cierra ese destino antes de tiempo y lo que viene detras se pinta como un
# SEGUNDO enlace pulsable -- justo al lado de «Cita literal del documento de la
# empresa» y debajo de cada titular.


def test_un_cierre_dentro_de_la_url_no_planta_un_segundo_enlace():
    salido = texto.enlace("ver el expediente", "https://www.sec.gov/a.htm>")
    assert salido == "[ver el expediente](<https://www.sec.gov/a.htm%3E>)"
    # Un solo destino, y por tanto un solo enlace.
    assert salido.count("](<") == 1


def test_una_url_con_parentesis_sigue_entera():
    """Lo que motivo los `<>` en su dia: las urls de prensa traen parentesis y
    sin ellos el enlace se corta a la mitad. Eso no se pierde al arreglar el
    `>`."""
    salido = texto.enlace("titular", "https://medio.example/nota_(2026)")
    assert "nota_(2026)" in salido


def test_un_esquema_que_no_es_http_no_se_pinta_como_enlace():
    """`canonicalUrl.url` llega sin validar. Un `javascript:` o un `data:` con
    pinta de noticia es un enlace que el usuario pulsa porque el titular se lo
    pide."""
    assert texto.enlace("Pulsa aqui", "javascript:alert(1)") == "Pulsa aqui"
    assert texto.enlace("Pulsa aqui", "data:text/html,<h1>hola") == "Pulsa aqui"


def test_una_url_relativa_o_rota_tampoco_se_pinta_como_enlace():
    """Un enlace que no lleva a ninguna parte invita a pulsarlo igual. Es la
    misma razon por la que la url vacia ya devolvia el texto solo."""
    assert texto.enlace("titular", "/Archives/edgar/data/1/a.htm") == "titular"
    assert texto.enlace("titular", "   ") == "titular"


def test_una_url_con_un_salto_de_linea_no_parte_la_linea():
    salido = texto.enlace("titular", "https://medio.example/a\nb")
    assert "\n" not in salido


# --- Lo que markdown se seguia quedando en `plano` --------------------------


def test_un_encabezado_del_modelo_no_se_pinta_como_encabezado():
    """Un salto de linea seguido de `# TITULO` dentro de un `que_dice` salia
    como encabezado de seccion, con el tamano y el peso de los que pone el
    programa."""
    salido = texto.plano("Dice algo.\n# TITULO FALSO")
    assert salido == "Dice algo.\n" + r"\# TITULO FALSO"


def test_un_autoenlace_no_sale_pulsable():
    """`<https://…>` es un autoenlace en commonmark: se pinta pulsable sin
    necesidad de corchetes, y una imagen remota confirma que la ficha se
    abrio."""
    assert texto.plano("<https://evil.tld/pixel>") == r"\<https://evil.tld/pixel\>"


def test_una_vineta_del_modelo_no_se_convierte_en_lista():
    assert texto.plano("Uno.\n- dos\n+ tres") == "Uno.\n" + r"\- dos" + "\n" + r"\+ tres"


def test_una_tabla_y_una_entidad_tampoco_se_interpretan():
    assert texto.plano("a | b &amp; c") == r"a \| b \&amp; c"


def test_una_exclamacion_antes_de_un_corchete_no_es_una_imagen():
    assert texto.plano("![x](https://evil.tld/p.png)") == (
        r"\!\[x\](https://evil.tld/p.png)"
    )


def test_un_subrayado_setext_no_asciende_el_parrafo_a_titulo():
    """Un `===` en la linea siguiente convierte el parrafo entero en un
    encabezado de nivel uno, sin que el caracter este al principio de la linea
    del texto que se lleva."""
    assert texto.plano("Dice algo.\n===") == "Dice algo.\n" + r"\=\=\="


def test_lo_que_ya_se_escapaba_se_sigue_escapando():
    """El saboteador de la lista: reescribir ESPECIALES a mano y perder uno de
    los de siempre no lo notaria nadie."""
    salido = texto.plano(HOSTIL)
    assert r"\[el aviso oficial\]" in salido
    assert r"\$1000M" in salido
