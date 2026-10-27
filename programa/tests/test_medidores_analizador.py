"""Las palabras del Analizador.

Cada clave que escribe `analizador/` tiene su etiqueta, y cada etiqueta culpa a
quien toca: un motivo es una afirmación (la lección de M y de N1). Las tablas se
contrastan contra las cadenas que aparecen de verdad en el código, para que una
etiqueta no hable de una clave que nadie escribe.
"""

import ast
from pathlib import Path

import pytest

import medidores_analizador as ma
from analizador.analisis import Analisis
from analizador.resolver import Identidad
from aprobacion.carga import MOTIVOS_EN_CASTELLANO

RAIZ = Path(__file__).resolve().parent.parent


def _literales(*rutas: str) -> set:
    """Las cadenas escritas en esos ficheros: las claves que el código puede devolver."""
    salida = set()
    for ruta in rutas:
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        salida |= {
            n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    return salida


def identidad(ticker="MU", moneda="USD", pais="United States",
              nombre="Micron Technology, Inc.", bolsa="NMS", precio=100.0):
    return Identidad(ticker, "EQUITY", nombre, bolsa, moneda, moneda, "Technology",
                     "Semiconductors", pais, precio, "2026-10-26T20:00:00+00:00")


# Las claves de `Analisis.motivo`: `resolver.resolver`, `resolver.clase_de`,
# `resolver.formularios_sec`, `mercado._traer` y `analisis.analizar`.
MOTIVOS_DEL_ANALISIS = {
    "sin_red", "tipo_no_soportado", "sin_red_edgar", "sin_identidad_edgar", "error_interno",
}
# Las de `Analisis.motivo_referencia`: las de su docstring, de `kpis` y de `mercado`.
MOTIVOS_DE_LA_REFERENCIA = {
    "sin_panel", "sin_sector", "sector_sin_pares", "sin_estados", "sin_historia",
    "sin_precio", "sin_trimestres_comparables", "sin_red", "error_interno",
}
# Las de `Entradas.motivo_r_f` que no son «ok»: Banxico, `divisas.bono_m` y el Tesoro.
MOTIVOS_DE_LA_TASA = {
    "sin_token", "token_invalido", "sin_red", "respuesta_rara", "sin_dato", "sin_tasa_libre",
}


def test_cada_clase_tiene_su_etiqueta_y_su_fuente_de_datos():
    assert set(ma.CLASE) == set(ma.FUENTE_DE_DATOS) == {"sec", "extranjera_sec", "sin_sec", "etf"}


def test_cada_motivo_del_analisis_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_ANALISIS) == MOTIVOS_DEL_ANALISIS
    escritos = _literales("analizador/resolver.py", "analizador/analisis.py", "valoracion/mercado.py")
    assert MOTIVOS_DEL_ANALISIS <= escritos


def test_cada_motivo_de_la_referencia_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_REFERENCIA) == MOTIVOS_DE_LA_REFERENCIA
    escritos = _literales("analizador/analisis.py", "analizador/kpis.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_REFERENCIA <= escritos


def test_cada_motivo_de_la_tasa_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_TASA) == MOTIVOS_DE_LA_TASA
    escritos = _literales("seguimiento/banxico.py", "analizador/divisas.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_TASA <= escritos


def test_sin_red_no_afirma_que_yahoo_no_conozca_el_ticker():
    # Enmienda del spec: desde fuera de `mercado` no se distingue un símbolo
    # desconocido de una conexión caída (ZZZZQ, en el recorrido de N1).
    texto = ma.MOTIVO_ANALISIS["sin_red"]
    assert "sin conexión" in texto and "no conoce" in texto


def test_sin_historia_en_la_ficha_habla_de_trimestres_y_no_de_anos():
    assert "trimestre" in ma.MOTIVO_REFERENCIA["sin_historia"]
    assert "año" not in ma.MOTIVO_REFERENCIA["sin_historia"]


def test_sin_trimestres_comparables_culpa_al_panel_y_no_a_la_empresa():
    assert "panel" in ma.MOTIVO_REFERENCIA["sin_trimestres_comparables"]


def test_el_error_interno_de_la_fila_no_dice_que_fallo_la_valoracion():
    assert "valorar" not in ma.MOTIVO_ANALISIS["error_interno"]


@pytest.mark.parametrize(
    "tabla, clave",
    [
        (ma.MOTIVO_ANALISIS, "sin_identidad_edgar"),
        (ma.MOTIVO_TASA, "sin_token"),
        (ma.MOTIVO_TASA, "token_invalido"),
    ],
)
def test_lo_que_arregla_el_usuario_dice_donde(tabla, clave):
    assert "Perfil y ajustes" in tabla[clave]


def test_una_clave_desconocida_se_ensena_tal_cual_y_una_que_no_es_texto_no():
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, "motivo_nuevo") == "motivo_nuevo"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, ["sin_red"]) == "n/d"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, None) == "n/d"


@pytest.mark.parametrize("codigo", sorted(MOTIVOS_EN_CASTELLANO))
def test_la_exclusion_usa_las_frases_de_revisar_candidatos(codigo):
    texto = ma.etiqueta_exclusion(codigo)
    assert texto.endswith(MOTIVOS_EN_CASTELLANO[codigo])
    assert "dejarían fuera" in texto


def test_una_exclusion_desconocida_se_dice_entre_comillas():
    assert "«guarda_nueva»" in ma.etiqueta_exclusion("guarda_nueva")


def test_el_nombre_largo_deja_ver_un_ticker_mal_partido():
    # `separar("BRK B")` da BRK y B, y B es Barrick, no la clase B de Berkshire.
    b = Analisis("B", "sec", identidad("B", nombre="Barrick Mining Corporation"), None)
    assert ma.nombre(b) == "Barrick Mining Corporation"
    assert ma.nombre(Analisis("ZZZZQ", None, None, "sin_red")) == "—"
    assert ma.nombre(Analisis("X", "sec", identidad("X", nombre=None), None)) == "—"


def test_una_ene_se_sugiere_con_el_ampersand_de_yahoo():
    aviso = ma.aviso_invalidos(["PEÑOLES.MX", "A..B"])
    assert "PE&OLES.MX" in aviso and "A..B" in aviso
    assert ma.aviso_invalidos(["A..B"]) == "Sin forma de ticker, y no se analizan: A..B."


@pytest.mark.parametrize(
    "ticker, pista",
    [("MKC.V", "MKC-V"), ("SHEL.L", "SHEL-L"), ("WALMEX.MX", None), ("MU", None), ("BRK-B", None)],
)
def test_un_sufijo_de_una_letra_puede_ser_una_clase_de_accion(ticker, pista):
    sugerencia = ma.sugerencia_sin_red(ticker)
    assert (sugerencia is None) == (pista is None)
    if pista:
        assert pista in sugerencia


def test_la_fila_de_un_ticker_sin_clase_dice_por_que_y_da_la_pista():
    assert "MKC-V" in ma.motivo_de_la_fila(Analisis("MKC.V", None, None, "sin_red"))
    assert ma.motivo_de_la_fila(Analisis("ZZZZQ", None, None, "sin_red")) == (
        ma.MOTIVO_ANALISIS["sin_red"]
    )
    assert ma.motivo_de_la_fila(Analisis("^GSPC", None, None, "tipo_no_soportado")) == (
        ma.MOTIVO_ANALISIS["tipo_no_soportado"]
    )
