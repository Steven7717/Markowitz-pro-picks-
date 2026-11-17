# tests/test_macro_red.py
"""Contra la OCDE y FRED de verdad. Excluidos de la suite normal.

Comprueba que la clave del flujo y las cinco áreas siguen dando dato, y que las
tres series de FRED existen. Si la OCDE cambia la versión del flujo o retira un
área, esto lo dice antes que la pantalla.
"""

import pytest

from macro import fuentes
from macro.contexto import SERIES
from macro.criterio import REGIONES

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(fuentes, "RAIZ_CACHE", tmp_path)


@pytest.mark.parametrize("region", sorted(REGIONES))
def test_cada_region_trae_al_menos_cinco_anos_de_cli(region):
    r = fuentes.traer_cli(region, raiz=fuentes.RAIZ_CACHE)
    assert r.motivo == "ok", r.motivo
    assert len(r.datos) >= 60
    assert 80 < r.datos.iloc[-1] < 120


@pytest.mark.parametrize("serie", sorted(SERIES.values()))
def test_las_series_de_fred_existen(serie):
    r = fuentes.traer_fred(serie, raiz=fuentes.RAIZ_CACHE)
    assert r.motivo == "ok", r.motivo
    assert len(r.datos) > 12
