"""La línea de los datos de la SEC en «Revisar candidatos» (sub-proyecto Q),
ejecutada con `AppTest` y sin red. Monta la pantalla igual que
`test_pantalla_candidatos_macro.py`."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from aprobacion import carga

RAIZ = Path(__file__).resolve().parent.parent
GUION = str(Path(__file__).resolve().parent / "guion_vista.py")
DATOS_SEC = {
    "ultimo_trimestre": "2026Q3",
    "descarga_mas_antigua": "2026-08-30",
    "descarga_mas_reciente": "2026-11-22",
    "actualizadas": 41,
    "servidas_caducadas": 0,
}


def _pantalla(monkeypatch, tmp_path, datos_sec):
    destino = tmp_path / "salidas"
    shutil.copytree(RAIZ / "salidas_ejemplo", destino)
    corrida = json.loads((destino / "corrida.json").read_text(encoding="utf-8"))
    corrida["datos_sec"] = datos_sec
    (destino / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")

    real_cargar = carga.cargar_candidatos
    monkeypatch.setattr("aprobacion.carga.cargar_candidatos", lambda *a: real_cargar(destino))
    monkeypatch.setattr(
        "aprobacion.generacion.disponibilidad",
        lambda *a: SimpleNamespace(puede_generar=True, puede_usar_ia=False,
                                   motivo="Sin clave de Anthropic.", motivo_generacion=""),
    )
    monkeypatch.setattr("preferencias.RUTA", tmp_path / "preferencias.json")
    monkeypatch.setenv("GUION_VISTA", "candidatos.py")
    st.cache_data.clear()
    at = AppTest.from_file(GUION, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture(autouse=True)
def _limpiar_cache():
    yield
    st.cache_data.clear()


def test_la_linea_sale_como_info(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, DATOS_SEC)
    assert any("Datos de la SEC hasta el 3T 2026" in i.value for i in at.info)
    assert not any("Datos de la SEC" in w.value for w in at.warning)


def test_con_caducadas_sale_como_aviso(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, {**DATOS_SEC, "servidas_caducadas": 3})
    assert any("3 servidas sin actualizar" in w.value for w in at.warning)


def test_una_corrida_sin_el_bloque_no_pinta_nada(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, None)
    textos = [e.value for e in at.info] + [e.value for e in at.warning]
    assert not any("Datos de la SEC" in t for t in textos)
