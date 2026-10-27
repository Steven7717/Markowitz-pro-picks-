"""Lo que la pantalla del Analizador tiene que hacer, leído de su fuente.

La pantalla es un guion de Streamlit --se ejecuta al importarse-- así que no se
pueden llamar sus funciones: se lee su fuente con `ast`, como
`test_vistas_optimizador.py`. La lógica tiene sus tests en
`test_medidores_analizador.py` y en los de `analizador/`; aquí se comprueba que
la pantalla la usa y no la rehace.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = (RAIZ / "vistas" / "analizador.py").read_text(encoding="utf-8")
ARBOL = ast.parse(FUENTE)


def _funcion(nombre: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(ARBOL) if isinstance(n, ast.FunctionDef) and n.name == nombre)


def _cuerpo(nombre: str) -> str:
    return ast.get_source_segment(FUENTE, _funcion(nombre))


def _llamadas_a(atributo: str) -> list:
    return [
        n for n in ast.walk(ARBOL)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == atributo
    ]


def test_el_tope_de_tickers_es_el_del_resolver():
    assert "MAX_TICKERS" in FUENTE
    assert not any(isinstance(n, ast.Constant) and n.value == 15 for n in ast.walk(ARBOL))


def test_el_campo_de_tickers_se_declara_con_clave_y_sin_valor():
    # «El formulario que se quedaba en blanco»: un `value` que cambia entre
    # pasadas reinicia el widget y tira lo escrito.
    (campo,) = _llamadas_a("text_input")
    claves = {k.arg: ast.unparse(k.value) for k in campo.keywords}
    assert claves.get("key") == "sesion.CLAVE_TEXTO"
    assert "value" not in claves


def test_el_encargo_se_recoge_antes_de_dibujar_el_campo():
    assert FUENTE.index("sesion.recoger(") < FUENTE.index("st.text_input(")


def test_analizar_lleva_barra_de_progreso_y_guarda_en_la_sesion():
    cuerpo = _cuerpo("_analizar_tickers")
    assert "st.progress(" in cuerpo and "analizar(" in cuerpo
    assert "sesion.preparar(" in FUENTE and "sesion.pendientes(" in FUENTE


def test_actualizar_precios_no_rehace_la_ficha():
    cuerpo = _cuerpo("_actualizar_precios").replace("con_precio_nuevo(", "")
    assert "con_precio_nuevo" in _cuerpo("_actualizar_precios")
    assert "analizar(" not in cuerpo


def test_cargar_de_un_libro_solo_lleva_tickers():
    cuerpo = _cuerpo("_cargar_de_un_libro")
    assert "posiciones.tickers_a_mirar(" in cuerpo
    assert "on_click=sesion.cargar_texto" in cuerpo
    # Ni pesos ni importes: la pantalla no calcula nada del libro.
    assert "pesos_objetivo(" not in cuerpo and "posiciones.estado(" not in cuerpo


def test_construir_el_panel_no_pasa_por_generar_candidatos():
    assert "referencia.construir_panel(" in _cuerpo("_panel_de_referencia")
    assert "guardar(" not in FUENTE and "construir_ranking(" not in FUENTE


def test_el_resumen_sale_de_las_filas_con_tests():
    assert "ma.fila(" in FUENTE and "ma.COLUMNAS" in FUENTE


def test_el_detalle_elegido_se_fija_antes_del_desplegable():
    assert FUENTE.index("sesion.fijar_elegido(") < FUENTE.index("key=sesion.CLAVE_ELEGIDO")


def test_las_pestanas_salen_de_la_clase():
    assert "ma.pestanas_de(" in _cuerpo("_detalle")


def test_el_codigo_nuevo_no_usa_lo_que_streamlit_da_por_obsoleto():
    # Streamlit 1.62 avisa en la consola de que `use_container_width` y
    # `st.components.v1.html` se retiran (visto al arrancar la pantalla en un
    # worktree, al planear N2): lo nuevo usa `width` y `st.iframe`.
    assert "use_container_width" not in FUENTE and "components.v1" not in FUENTE


# --- Lo que no escribió el programa se escapa -----------------------------------

_PINTAN = {"markdown", "caption", "write", "info", "warning", "error", "success"}
# Lo que llega de Yahoo, de la SEC o de la prensa. `cuando` es una fecha que se
# formatea, no texto.
_AJENOS = {"noticia", "evento", "hecho", "identidad", "juicio"}
_INOCUOS = {"cuando"}


def _ajenos_fuera_de_texto(nodo) -> list:
    """Recorre el árbol y para en cuanto entra en una llamada a `texto.algo`."""
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and isinstance(nodo.func.value, ast.Name)
        and nodo.func.value.id == "texto"
    ):
        return []
    crudos = []
    if (
        isinstance(nodo, ast.Attribute)
        and isinstance(nodo.value, ast.Name)
        and nodo.value.id in _AJENOS
        and nodo.attr not in _INOCUOS
    ):
        crudos.append(nodo)
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "nombre"
        and getattr(nodo.func.value, "id", None) == "ma"
    ):
        crudos.append(nodo)
    for hijo in ast.iter_child_nodes(nodo):
        crudos.extend(_ajenos_fuera_de_texto(hijo))
    return crudos


def _sin_escapar(arbol) -> list:
    crudos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in _PINTAN:
            crudos.extend(_ajenos_fuera_de_texto(nodo))
    return crudos


def test_lo_que_no_escribio_el_programa_se_escapa_antes_de_pintarlo():
    crudos = _sin_escapar(ARBOL)
    assert crudos == [], "sin escapar en las líneas " + ", ".join(str(n.lineno) for n in crudos)


def test_el_saboteador_de_ese_test_lo_tumba():
    assert len(_sin_escapar(ast.parse('st.markdown(f"{noticia.titular}")'))) == 1
    assert len(_sin_escapar(ast.parse("st.caption(ma.nombre(a))"))) == 1
    assert _sin_escapar(ast.parse("st.markdown(texto.plano(noticia.titular))")) == []


# --- Lo que cambió sobre el plan (revisión de las Tasks 1-10 y 12) -------------


def test_construir_el_panel_dice_tambien_un_fallo_al_escribirlo():
    # `construir_panel` reintenta si otra sesión lee el panel, y si sigue
    # ocupado --o el disco está lleno-- sale `OSError`: sin capturarlo, la
    # pantalla enseñaría una traza.
    capturas = [
        ast.unparse(n.type)
        for n in ast.walk(_funcion("_panel_de_referencia"))
        if isinstance(n, ast.ExceptHandler) and n.type is not None
    ]
    assert any("CorridaAbortada" in c for c in capturas)
    assert any("OSError" in c for c in capturas)


def test_el_panel_atrasado_se_dice_una_vez_en_el_resumen():
    # Con 7203.T, el aviso, el detalle de pares y la exclusión decían los tres
    # «el panel se quedó atrás». Donde el aviso está a la vista, los otros no.
    cuerpo = _cuerpo("_valor_y_sector")
    for llamada in ("ma.detalle_pares(", "ma.texto_exclusion(", "ma.sin_ficha("):
        assert llamada in cuerpo
        segmento = cuerpo.split(llamada, 1)[1].split(")", 1)[0]
        assert "panel_dicho" in segmento, llamada
    assert "ma.aviso_panel_atrasado(" in _cuerpo("_resumen")


def test_actualizar_precios_no_dice_que_el_precio_este_al_dia():
    # `con_precio_nuevo` devuelve la fila de antes si algo falla: lo que se
    # enseña es la hora de la cotización que tiene la fila, nunca «actualizado».
    assert "actualizad" not in FUENTE.lower().replace("actualizando", "")


def test_el_grafico_sigue_el_tema_de_la_app_y_dice_lo_que_se_sabe():
    cuerpo = _cuerpo("_grafico")
    assert "st.context.theme" in cuerpo
    assert "grafico.html(" in cuerpo and "st.iframe(" in cuerpo
    # La BMV no se ve en el widget: se enlaza a TradingView.
    assert "grafico.en_widget(" in cuerpo and "grafico.enlace(" in cuerpo
    assert "grafico.ESTUDIO_D" in cuerpo and "grafico.avisos(" in cuerpo


def test_el_grafico_decide_con_el_ticker_y_no_solo_con_la_bolsa():
    # Sin el ticker, `T.TO` (TELUS) se incrustaba como AT&T y `BA.L` (BAE)
    # como Boeing: `en_widget`, `enlace` y `avisos` reciben ticker y bolsa.
    llamadas = [
        n for n in ast.walk(_funcion("_grafico"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and getattr(n.func.value, "id", None) == "grafico"
        and n.func.attr in ("en_widget", "enlace", "avisos")
    ]
    assert {n.func.attr for n in llamadas} == {"en_widget", "enlace", "avisos"}
    assert all(len(n.args) == 2 for n in llamadas)


def test_la_tarjeta_lleva_el_puesto_global():
    cuerpo = _cuerpo("_valor_y_sector")
    assert "puesto=ma.puesto_en_tarjeta(" in cuerpo and "ma.nota_puesto(" in cuerpo


def test_los_fundamentales_son_los_medidores_de_candidatos():
    cuerpo = _cuerpo("_fundamentales")
    for llamada in (
        "medidores.medidores_pilares(",
        "medidores.medidor_cobertura(",
        "medidores.medidor_kpi(",
        "ma.contra_quien(",
        "ma.texto_exclusion(",
    ):
        assert llamada in cuerpo


def test_en_los_fundamentales_el_panel_atrasado_se_dice_una_vez():
    cuerpo = _cuerpo("_fundamentales")
    assert "ma.aviso_panel_atrasado(" in cuerpo
    assert "panel_dicho" in cuerpo.split("ma.texto_exclusion(", 1)[1].split(")", 1)[0]


def test_como_se_leen_los_medidores_va_una_vez_encima_de_las_pestanas():
    cuerpo = _cuerpo("_detalle")
    assert cuerpo.index("medidores.como_se_leen()") < cuerpo.index("st.tabs(")
