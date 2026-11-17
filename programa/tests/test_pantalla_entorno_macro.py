"""La pantalla «Entorno macro», ejecutada de verdad con `AppTest` y sin red.

La OCDE y FRED se sustituyen por series inventadas, pero la fase sale de la
lógica de verdad (`leer_region` con un `traer` doble): lo que se prueba es que
ningún motivo —sin red, serie corta, con huecos, indeterminada, dato rancio,
caché vieja— revienta la pantalla, y que cada uno dice lo suyo.
"""

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import preferencias
from macro import estado as estado_mod
from macro import textos
from macro.fuentes import Serie
from macro.lectura import Lectura

GUION = str(Path(__file__).resolve().parent / "guion_vista.py")
HOY = date.today()


def _serie(valores, meses_atras: int = 1) -> pd.Series:
    """Termina `meses_atras` meses antes del mes en curso."""
    fin = pd.Period(HOY, freq="M") - meses_atras
    indice = pd.period_range(end=fin, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


SUBE = list(np.linspace(99.0, 101.0, 72))  # por encima de 100 y subiendo: expansión
BAJA = list(np.linspace(101.0, 99.0, 72))  # por debajo y bajando: contracción


def _con_hueco() -> pd.Series:
    s = _serie(SUBE)
    return s.drop(s.index[-2])  # falta el penúltimo mes


def _fred(serie_id: str) -> Serie:
    indice = pd.period_range(end=pd.Period(HOY, freq="M") - 1, periods=30, freq="M").to_timestamp()
    if serie_id == "CPIAUCSL":
        return Serie(pd.Series(np.linspace(290, 300, 30), index=indice), "ok")
    valor = {"T10Y3M": -0.4, "UNRATE": 4.1}[serie_id]
    return Serie(pd.Series(np.full(30, valor), index=indice), "ok")


@pytest.fixture
def pantalla(monkeypatch, tmp_path):
    mundo = {"traer": lambda region: Serie(_serie(SUBE), "ok", datetime.now(timezone.utc))}
    real = estado_mod.leer_region
    monkeypatch.setattr(
        "macro.estado.leer_region",
        lambda region, hoy: real(region, hoy, traer=lambda r: mundo["traer"](r)),
    )
    monkeypatch.setattr("macro.fuentes.traer_fred", _fred)
    monkeypatch.setattr(
        "macro.lectura.leer",
        lambda estado, contexto: Lectura("La economía crece.", ("El paro",), 0.0),
    )
    monkeypatch.setattr("interprete.cliente.hay_clave", lambda: True)
    monkeypatch.setattr("preferencias.RUTA", tmp_path / "preferencias.json")
    monkeypatch.setenv("GUION_VISTA", "entorno_macro.py")
    st.cache_data.clear()  # la caché de `_estado` es del proceso: no puede cruzar tests
    at = AppTest.from_file(GUION, default_timeout=30)
    at.mundo = mundo
    yield at
    st.cache_data.clear()


def _textos(at) -> str:
    partes = []
    for clase in ("markdown", "caption", "warning", "error", "info", "success"):
        partes += [e.value for e in getattr(at, clase)]
    partes += [f"{m.label} {m.value}" for m in at.metric]
    return "\n".join(partes)


def _correr(at) -> str:
    at.run()
    assert not at.exception, at.exception
    return _textos(at)


def _boton_ia(at):
    return [b for b in at.button if b.label.startswith("Leer con IA")]


def test_una_fase_normal_de_eeuu_lo_pinta_todo(pantalla):
    texto = _correr(pantalla)
    assert "### Expansión" in texto
    assert "Suele favorecer" in texto and "Tecnología" in texto
    assert textos.AVISO_EVIDENCIA in texto
    assert "Contexto de EE. UU." in texto
    assert "Invertida" in texto
    assert not pantalla.warning
    assert len(pantalla.get("plotly_chart")) == 1


def test_la_lectura_con_ia_se_pinta_al_pulsar(pantalla):
    _correr(pantalla)
    _boton_ia(pantalla)[0].click().run()
    assert not pantalla.exception
    texto = _textos(pantalla)
    assert "La economía crece." in texto and "El paro" in texto
    assert "no costó nada" in texto


def test_otra_region_no_trae_el_contexto_de_eeuu(pantalla):
    pantalla.mundo["traer"] = lambda region: Serie(_serie(BAJA), "ok")
    _correr(pantalla)
    pantalla.selectbox(key="region_macro_pantalla").set_value("eurozona").run()
    assert not pantalla.exception
    texto = _textos(pantalla)
    assert "### Contracción" in texto
    assert "Contexto de EE. UU." not in texto
    assert "solo está para EE. UU." in texto


def test_la_region_elegida_se_recuerda(pantalla, tmp_path):
    _correr(pantalla)
    pantalla.selectbox(key="region_macro_pantalla").set_value("china").run()
    assert not pantalla.exception
    assert preferencias.cargar(tmp_path / "preferencias.json")[0].region_macro == "china"


def test_una_serie_con_huecos_no_revienta_y_lo_dice(pantalla):
    pantalla.mundo["traer"] = lambda region: Serie(_con_hueco(), "ok")
    texto = _correr(pantalla)
    assert "Fase indeterminada" in texto
    assert textos.MOTIVO["serie_con_huecos"] in texto
    assert "Suele favorecer" not in texto
    assert "Sin una fase determinada" in texto
    assert not _boton_ia(pantalla)
    assert len(pantalla.get("plotly_chart")) == 1


def test_indeterminada_no_revienta(pantalla):
    valores = SUBE[:-1] + [SUBE[-2] - 0.01]  # el último mes desmiente la subida
    pantalla.mundo["traer"] = lambda region: Serie(_serie(valores), "ok")
    texto = _correr(pantalla)
    assert "Fase indeterminada" in texto
    assert textos.MOTIVO["indeterminada"] in texto


@pytest.mark.parametrize("motivo", ["sin_red", "serie_desconocida", "respuesta_ilegible"])
def test_sin_serie_dice_por_que_y_para(pantalla, motivo):
    pantalla.mundo["traer"] = lambda region: Serie(None, motivo)
    texto = _correr(pantalla)
    assert textos.MOTIVO[motivo] in texto
    assert not pantalla.get("plotly_chart")


def test_una_serie_corta_dice_por_que_y_para(pantalla):
    pantalla.mundo["traer"] = lambda region: Serie(_serie([100.5, 100.6]), "ok")
    texto = _correr(pantalla)
    assert textos.MOTIVO["serie_corta"] in texto
    assert not pantalla.get("plotly_chart")


def test_un_dato_rancio_se_avisa(pantalla):
    pantalla.mundo["traer"] = lambda region: Serie(_serie(SUBE, meses_atras=6), "ok")
    texto = _correr(pantalla)
    assert "### Expansión" in texto
    assert textos.MOTIVO["dato_rancio"] in [w.value for w in pantalla.warning]


def test_la_cache_vieja_se_avisa(pantalla):
    pantalla.mundo["traer"] = lambda region: Serie(_serie(SUBE), "ok", vieja=True)
    _correr(pantalla)
    assert any("lo último que se guardó" in w.value for w in pantalla.warning)


def test_fred_sin_red_deja_rayas(pantalla, monkeypatch):
    monkeypatch.setattr("macro.fuentes.traer_fred", lambda serie_id: Serie(None, "sin_red"))
    _correr(pantalla)
    assert [m.value for m in pantalla.metric][-3:] == ["—", "—", "—"]


def test_sin_clave_no_hay_boton(pantalla, monkeypatch):
    monkeypatch.setattr("interprete.cliente.hay_clave", lambda: False)
    texto = _correr(pantalla)
    assert "Hace falta la clave de Anthropic" in texto
    assert not _boton_ia(pantalla)
