# tests/test_macro_informe.py
from datetime import date
from types import SimpleNamespace

import pandas as pd

from macro import informe, lectura
from macro.contexto import ContextoUSA
from macro.estado import Estado
from macro.fase import Fase
from noticias import cache


def _estado(region="usa", fase=None, motivo=None, vieja=False):
    serie = pd.Series(
        [100.5, 100.6, 100.7, 100.8],
        index=pd.period_range("2026-07", periods=4, freq="M").to_timestamp(),
    )
    fase = fase or Fase("expansion", None, date(2026, 10, 1), 100.8, 0.3, 4)
    return Estado(region, serie, fase, motivo, None, vieja)


def _todo(entorno):
    filas, parrafos = informe.declaraciones(entorno)
    return dict(filas), " ".join(parrafos)


def test_la_fase_los_sectores_y_el_dato_salen_con_las_palabras_de_la_pantalla():
    filas, texto = _todo(informe.EntornoPDF("mex", _estado("mex")))
    assert filas["Región"] == "México"
    assert filas["Fase del ciclo (CLI de la OCDE)"] == "Expansión"
    assert filas["Indicador adelantado (100 = tendencia)"] == "100,80 (+0,30 en 3 meses)"
    assert filas["Mes del dato"] == "oct 2026"
    assert "Tecnología" in filas["Suele favorecer"]
    assert "Servicios públicos" in filas["Suele desfavorecer"]
    assert "evidencia floja" in texto


def test_el_informe_dice_que_la_fase_no_movio_los_pesos():
    _, parrafos = informe.declaraciones(informe.EntornoPDF("mex", _estado("mex")))
    assert parrafos[-1] == informe.NO_INTERVIENE


def test_fase_indeterminada_dice_por_que_y_no_inventa_sectores():
    indeterminada = Fase(None, "indeterminada", date(2026, 10, 1), 99.9, 0.0, 0)
    filas, texto = _todo(informe.EntornoPDF("g7", _estado("g7", indeterminada)))
    assert filas["Fase del ciclo (CLI de la OCDE)"] == "Indeterminada"
    assert "Suele favorecer" not in filas
    assert "no marca dirección" in texto


def test_sin_serie_queda_el_motivo_y_el_aviso():
    vacio = Estado("china", None, None, "sin_red", None, False)
    filas, parrafos = informe.declaraciones(informe.EntornoPDF("china", vacio))
    assert filas == [("Región", "China")]
    assert "La OCDE no responde" in parrafos[0]


def test_el_contexto_de_eeuu_entra_con_sus_avisos():
    contexto = ContextoUSA(-0.4, True, 0.6, True, 0.031, date(2026, 9, 1))
    filas, texto = _todo(informe.EntornoPDF("usa", _estado(), contexto, {}))
    assert filas["Curva 10 años - 3 meses (EE. UU.)"] == "-0,40"
    assert filas["Regla de Sahm (EE. UU.)"] == "0,60"
    assert filas["Inflación interanual (EE. UU.)"] == "3,1% (sep 2026)"
    assert "invertida" in texto and "activada" in texto


def test_la_lectura_guardada_entra_y_la_no_pagada_no(tmp_path):
    sin = informe.recoger("mex", date(2026, 11, 21), leer=lambda r, h: _estado("mex"),
                          raiz=tmp_path)
    assert sin.lectura is None
    cache.guardar(tmp_path, "macro", "mex_2026-10-01",
                  {"explicacion": "Crece.", "vigilar": ["El empleo."]})
    con = informe.recoger("mex", date(2026, 11, 21), leer=lambda r, h: _estado("mex"),
                          raiz=tmp_path)
    _, texto = _todo(con)
    assert "Crece." in texto and "Qué vigilar: El empleo." in texto


def test_recoger_no_revienta_si_la_ocde_falla(tmp_path):
    def falla(region, hoy):
        raise RuntimeError("boom")

    entorno = informe.recoger("usa", date(2026, 11, 21), leer=falla, raiz=tmp_path)
    filas, parrafos = informe.declaraciones(entorno)
    assert "boom" in parrafos[0] and parrafos[-1] == informe.NO_INTERVIENE


def test_recoger_sigue_sin_el_contexto_si_fred_falla(tmp_path):
    def falla():
        raise RuntimeError("fred caído")

    entorno = informe.recoger("usa", date(2026, 11, 21), leer=lambda r, h: _estado(),
                              traer_contexto=falla, raiz=tmp_path)
    assert entorno.contexto is None and entorno.problema is None


def test_guardada_nunca_llama_a_la_ia(tmp_path):
    assert lectura.guardada(_estado(), raiz=tmp_path) is None
    sin_fase = Estado("usa", None, None, "sin_red", None, False)
    assert lectura.guardada(sin_fase, raiz=tmp_path) is None
