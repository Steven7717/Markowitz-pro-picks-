# programa/tests/test_panel_ia.py
"""Lo que el bloque de «Interpretar estos hechos» anuncia antes de pulsar, y lo
que puede costar de verdad. Nació en la pantalla de Noticias, que ya no existe:
hoy lo pintan Seguimiento y el Analizador (`vistas/panel_ia.py`).

La pantalla decia «cuesta unos **0,10 $** como mucho» y el README repetia la
cifra. Pero `interprete/noticias.py` **reenvia el turno de usuario entero** en
el reintento, y el reintento lo dispara el propio documento --una cita que no
verifique basta--, asi que el peor caso era dos turnos y medio de lo anunciado.
Es el mismo defecto que ya se cerro en la pantalla hermana con
`aprobacion/generacion.py:coste_peor_caso`, con el mismo disparador controlado
por el texto de un tercero.
"""

from interprete import cliente as cliente_mod
from interprete import documentos
from noticias import resumen
from ranking import filings
from vistas import panel_ia


def test_el_ratio_es_el_medido_contra_la_api_y_no_la_regla_de_tres():
    """`ranking/filings.py` midio 3,30 caracteres por token contra la API real
    y dejo escrito que «la regla de tres se quedaba corta en un 21%». Las dos
    pantallas que anuncian coste seguian con el 4,0 del diseño."""
    assert panel_ia.CARACTERES_POR_TOKEN == filings.CARACTERES_POR_TOKEN
    assert filings.CARACTERES_POR_TOKEN < 4


def test_el_peor_caso_cuenta_los_dos_turnos_que_el_documento_puede_forzar():
    assert panel_ia.coste_peor_caso(6) > 2 * panel_ia.coste_estimado(6)


def test_el_peor_caso_usa_el_tope_por_hecho_y_no_la_media():
    """La media sirve para estimar; para un tope no vale, porque los documentos
    van de tres mil a ciento doce mil caracteres y el tope duro es lo unico que
    ningun hecho puede pasarse."""
    entrada_por_turno = (
        6 * documentos.TOPE_CARACTERES / filings.CARACTERES_POR_TOKEN
    )
    esperado = cliente_mod.coste(
        int(entrada_por_turno) * 2 + cliente_mod.MAX_TOKENS,
        2 * cliente_mod.MAX_TOKENS,
    )
    assert panel_ia.coste_peor_caso(6) == esperado


def test_el_peor_caso_crece_con_los_hechos():
    assert panel_ia.coste_peor_caso(6) > panel_ia.coste_peor_caso(3)


def test_sin_hechos_no_se_anuncia_gasto():
    assert panel_ia.coste_peor_caso(0) == 0.0


def test_el_tope_de_la_pulsacion_cubre_el_peor_caso_sin_ahogarlo():
    """Mismo par de cotas que `ranking/llm.py:TOPE_USD_POR_CORRIDA` contra
    `coste_peor_caso`: si el tope quedara por debajo del peor caso previsto,
    saltaria en una pulsacion normal y la degradacion dejaria de ser una
    excepcion para ser la regla."""
    peor = panel_ia.coste_peor_caso(resumen.TOPE_HECHOS)
    assert cliente_mod.TOPE_USD_POR_PULSACION > peor
    assert cliente_mod.TOPE_USD_POR_PULSACION < peor * 4


def test_el_tope_se_mira_antes_de_llamar_no_despues():
    """`dentro_del_tope` recibe lo gastado hasta ahora. Con cero gastado deja
    pasar; con el tope alcanzado, no."""
    assert cliente_mod.dentro_del_tope(0, 0)
    de_golpe = int(
        cliente_mod.TOPE_USD_POR_PULSACION / cliente_mod.PRECIO_ENTRADA * 1_000_000
    )
    assert not cliente_mod.dentro_del_tope(de_golpe, 0)


# --- La pantalla, que es un guion de Streamlit y no se puede importar --------

from pathlib import Path  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def _interpretar_hechos():
    import ast

    fuente = (RAIZ / "vistas" / "panel_ia.py").read_text(encoding="utf-8")
    funcion = next(
        n for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.FunctionDef) and n.name == "interpretar_hechos"
    )
    return fuente, funcion


def test_la_pantalla_pega_el_como_mucho_a_un_tope_de_verdad():
    """«Cuesta unos X $ **como mucho**» iba con la cifra de `coste_estimado`,
    que es la media y un solo turno. El saboteador: devolver la llamada a
    `coste_estimado` a la linea del «como mucho» tumba esto. Vive en
    `panel_ia.interpretar_hechos` desde que Seguimiento y el Analizador
    comparten el bloque."""
    import ast

    fuente, funcion = _interpretar_hechos()
    cuerpo = ast.get_source_segment(fuente, funcion)
    anuncio = next(
        bloque for bloque in cuerpo.split("st.caption(")[1:] if "como mucho" in bloque
    ).split(")\n")[0]
    assert "coste_peor_caso(" in anuncio
    detras = anuncio.split("como mucho", 1)[1]
    assert detras.split("coste_", 1)[1].startswith("peor_caso")


def test_tras_un_fallo_lo_guardado_se_sigue_pintando():
    """En el guion de Seguimiento, `_leidas` eran las urls leídas y, tras
    pulsar, lo que devolvía `preparar`: con una lectura fallida,
    `pintar_archivo` buscaba urls en una tupla de tuplas y no pintaba nada de
    lo guardado. El nombre que llega a `pintar_archivo` sólo se asigna una vez,
    con `urls_leidas`."""
    import ast

    _fuente, funcion = _interpretar_hechos()
    llamada = next(
        n for n in ast.walk(funcion)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "pintar_archivo"
    )
    nombre = llamada.args[3].id
    asignaciones = [
        n for n in ast.walk(funcion)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == nombre for o in n.targets for t in ast.walk(o))
    ]
    assert len(asignaciones) == 1
    assert "urls_leidas" in ast.unparse(asignaciones[0].value)


def test_seguimiento_usa_el_bloque_compartido():
    fuente = (RAIZ / "vistas" / "seguimiento.py").read_text(encoding="utf-8")
    assert "panel_ia.interpretar_hechos(" in fuente
    assert "interprete_noticias.leer(" not in fuente


# --- Sin hechos que interpretar: se miró y no había, o no se pudo mirar ---------


class _St:
    """Un `st` de mentira que apunta lo que se le pide pintar."""

    def __init__(self):
        self.session_state = {}
        self.pintado = []

    def __getattr__(self, nombre):
        return lambda *args, **kwargs: self.pintado.append((nombre, args[0] if args else None))


def _sin_hechos(tmp_path, consultado):
    st = _St()
    panel_ia.interpretar_hechos(
        st, (), tmp_path / "MU.json", {"MU"}, (), clave="prueba", consultado=consultado
    )
    (pie,) = [texto_ for nombre, texto_ in st.pintado if nombre == "caption"]
    return pie


def test_sin_hechos_y_con_la_fuente_consultada_se_dice_que_se_miro(tmp_path):
    assert "se miró y no había ninguno" in _sin_hechos(tmp_path, consultado=True)


def test_sin_hechos_porque_la_fuente_fallo_no_se_afirma_que_no_habia(tmp_path):
    # Con EDGAR caído, o sin el correo, la lista llega vacía igual: «se miró y
    # no había ninguno» afirmaba una consulta que no se hizo.
    pie = _sin_hechos(tmp_path, consultado=False)
    assert "se miró" not in pie and "no había ninguno" not in pie
    assert "no se sabe si hay alguno" in pie


def test_seguimiento_no_afirma_que_no_haya_titulares_si_la_prensa_no_respondio():
    fuente = (RAIZ / "vistas" / "seguimiento.py").read_text(encoding="utf-8")
    titulares = fuente.split('st.markdown("##### Titulares")', 1)[1].split("st.divider()", 1)[0]
    assert "prensa_sin_consultar" in titulares
    assert titulares.index("prensa_sin_consultar") < titulares.index("la fuente no devolvió ninguno")
    # Y de los que faltan se dice quiénes, como con los 8-K.
    assert "{', '.join(resumen_noticias.prensa_sin_consultar)}" in titulares


def test_seguimiento_dice_si_los_8k_de_todos_se_llegaron_a_consultar():
    import ast

    fuente = (RAIZ / "vistas" / "seguimiento.py").read_text(encoding="utf-8")
    llamada = next(
        n for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "interpretar_hechos"
    )
    claves = {k.arg: ast.unparse(k.value) for k in llamada.keywords}
    assert claves["consultado"] == "not resumen_noticias.hechos_sin_consultar"
