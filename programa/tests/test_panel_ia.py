# programa/tests/test_panel_ia.py
"""Lo que la pantalla de Noticias anuncia antes de pulsar, y lo que puede
costar de verdad.

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


def test_la_pantalla_pega_el_como_mucho_a_un_tope_de_verdad():
    """«Cuesta unos X $ **como mucho**» iba con la cifra de `coste_estimado`,
    que es la media y un solo turno. El saboteador: devolver la llamada a
    `coste_estimado` a la linea del «como mucho» tumba esto."""
    fuente = (RAIZ / "vistas" / "seguimiento.py").read_text(encoding="utf-8")
    anuncio = next(
        bloque for bloque in fuente.split("st.caption(") if "como mucho" in bloque
    ).split(")\n")[0]
    assert "panel_ia.coste_peor_caso(" in anuncio
    # Y la cifra que el «como mucho» califica es la del tope: la primera que
    # aparece detras de esas dos palabras.
    detras = anuncio.split("como mucho", 1)[1]
    assert detras.split("coste_", 1)[1].startswith("peor_caso")
