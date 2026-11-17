"""La casilla de la macro en «Revisar candidatos», ejecutada con `AppTest` y sin red.

Los candidatos son los de `salidas_ejemplo/` copiados a un directorio temporal
(con el bloque de la macro añadido cuando hace falta), la fase sale de
`leer_region` con un `traer` doble, y la corrida es un doble que solo apunta
con qué se la llamó.
"""

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from aprobacion import carga
from macro import estado as estado_mod
from macro import textos
from macro.fuentes import Serie

RAIZ = Path(__file__).resolve().parent.parent
GUION = str(Path(__file__).resolve().parent / "guion_vista.py")
BLOQUE = {"region": "usa", "fase": "expansion", "mes_dato": "2026-10-01",
          "inclinacion": 0.25, "entradas": ["JPM"], "salidas": ["NVDA"]}


def _serie(meses_atras: int = 1) -> pd.Series:
    fin = pd.Period(date.today(), freq="M") - meses_atras
    indice = pd.period_range(end=fin, periods=24, freq="M").to_timestamp()
    return pd.Series(np.linspace(99.0, 101.0, 24), index=indice)  # expansión


def _salidas(tmp_path, bloque=None, ajuste=None) -> Path:
    destino = tmp_path / "salidas"
    shutil.copytree(RAIZ / "salidas_ejemplo", destino)
    if bloque is not None:
        corrida = json.loads((destino / "corrida.json").read_text(encoding="utf-8"))
        corrida["macro"] = bloque
        (destino / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")
    if ajuste is not None:
        fichas = json.loads((destino / "fichas.json").read_text(encoding="utf-8"))
        for ficha in fichas:
            ficha["ajuste_macro"] = ajuste
        (destino / "fichas.json").write_text(json.dumps(fichas), encoding="utf-8")
    return destino


@pytest.fixture
def pantalla(monkeypatch, tmp_path):
    mundo = {
        "traer": lambda region: Serie(_serie(), "ok"),
        "salidas": _salidas(tmp_path),
        "llamadas": [],
    }
    real_leer, real_cargar = estado_mod.leer_region, carga.cargar_candidatos
    monkeypatch.setattr(
        "macro.estado.leer_region",
        lambda region, hoy: real_leer(region, hoy, traer=lambda r: mundo["traer"](r)),
    )
    monkeypatch.setattr("aprobacion.carga.cargar_candidatos", lambda *a: real_cargar(mundo["salidas"]))
    monkeypatch.setattr(
        "aprobacion.generacion.disponibilidad",
        lambda *a: SimpleNamespace(puede_generar=True, puede_usar_ia=False,
                                   motivo="Sin clave de Anthropic.", motivo_generacion=""),
    )
    monkeypatch.setattr(
        "ranking.run.construir_ranking", lambda **kw: mundo["llamadas"].append(kw) or "resultado"
    )
    monkeypatch.setattr("ranking.run.guardar", lambda *a: None)
    monkeypatch.setattr("preferencias.RUTA", tmp_path / "preferencias.json")
    monkeypatch.setenv("GUION_VISTA", "candidatos.py")
    st.cache_data.clear()
    at = AppTest.from_file(GUION, default_timeout=30)
    at.mundo = mundo
    yield at
    st.cache_data.clear()


def _textos(at) -> str:
    partes = []
    for clase in ("markdown", "caption", "warning", "error", "info", "success"):
        partes += [e.value for e in getattr(at, clase)]
    return "\n".join(partes)


def _correr(at):
    at.run()
    assert not at.exception, at.exception


def _generar_gratis(at):
    next(b for b in at.button if b.label == "Generar gratis").click().run()
    assert not at.exception, at.exception


def test_la_casilla_sale_apagada_y_sin_selector(pantalla):
    _correr(pantalla)
    assert pantalla.checkbox(key="inclinar_macro").value is False
    assert not [s for s in pantalla.selectbox if s.key == "region_macro_candidatos"]
    _generar_gratis(pantalla)
    assert pantalla.mundo["llamadas"][-1]["macro"] is None
    assert pantalla.mundo["llamadas"][-1]["region"] is None


def test_marcada_dice_la_fase_y_la_pasa_a_la_corrida(pantalla):
    _correr(pantalla)
    pantalla.checkbox(key="inclinar_macro").check().run()
    assert not pantalla.exception
    assert pantalla.selectbox(key="region_macro_candidatos").value == "usa"
    assert "Se usará la fase **Expansión**" in _textos(pantalla)
    _generar_gratis(pantalla)
    llamada = pantalla.mundo["llamadas"][-1]
    assert llamada["macro"].clave == "expansion"
    assert llamada["region"] == "usa"


@pytest.mark.parametrize(
    "serie, motivo",
    [(Serie(None, "sin_red"), "sin_red"), (Serie(_serie(meses_atras=6), "ok"), "dato_rancio")],
)
def test_si_la_fase_no_puede_inclinar_la_corrida_sale_sin_macro(pantalla, serie, motivo):
    pantalla.mundo["traer"] = lambda region: serie
    _correr(pantalla)
    pantalla.checkbox(key="inclinar_macro").check().run()
    assert not pantalla.exception
    assert any(textos.MOTIVO[motivo] in w.value and "sin macro" in w.value for w in pantalla.warning)
    _generar_gratis(pantalla)
    assert pantalla.mundo["llamadas"][-1]["macro"] is None


def test_una_corrida_con_macro_dice_lo_que_movio_y_el_ajuste(pantalla, tmp_path):
    pantalla.mundo["salidas"] = _salidas(tmp_path / "otra", BLOQUE, ajuste=0.25)
    _correr(pantalla)
    texto = _textos(pantalla)
    assert "El Top está inclinado" in texto and "JPM" in texto
    assert "La macro la subió (+0,25)." in texto


def test_una_corrida_sin_macro_no_dice_nada_de_macro(pantalla):
    _correr(pantalla)
    texto = _textos(pantalla)
    assert "El Top está inclinado" not in texto
    assert "La macro" not in texto


def test_un_bloque_sin_fase_cuenta_como_sin_macro(pantalla, tmp_path):
    pantalla.mundo["salidas"] = _salidas(tmp_path / "otra", {"foo": 1}, ajuste="raro")
    _correr(pantalla)
    texto = _textos(pantalla)
    assert "El Top está inclinado" not in texto and "no lleva entorno macro" not in texto


def test_el_pago_con_ia_lleva_la_macro_y_el_aviso_lo_dice(pantalla, monkeypatch):
    monkeypatch.setattr(
        "aprobacion.generacion.disponibilidad",
        lambda *a: SimpleNamespace(puede_generar=True, puede_usar_ia=True,
                                   motivo="", motivo_generacion=""),
    )
    _correr(pantalla)
    pantalla.checkbox(key="inclinar_macro").check().run()
    pantalla.radio(key="modo_generacion").set_value(
        next(o for o in pantalla.radio(key="modo_generacion").options if o.startswith("Con IA"))
    ).run()
    next(b for b in pantalla.button if b.label == "Generar con IA").click().run()
    assert not pantalla.exception, pantalla.exception
    assert pantalla.mundo["llamadas"] == []  # pulsar no gasta: falta confirmar
    assert "Irá inclinada por la fase Expansión de Estados Unidos." in _textos(pantalla)
    pantalla.button(key="confirmar_ia").click().run()
    assert not pantalla.exception, pantalla.exception
    llamada = pantalla.mundo["llamadas"][-1]
    assert llamada["macro"].clave == "expansion"
    assert llamada["region"] == "usa"
