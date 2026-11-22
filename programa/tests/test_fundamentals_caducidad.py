"""La caducidad de la caché de la SEC: sub-proyecto Q.

`hoy` se pasa siempre a mano y el `mtime` de los ficheros se fija con
`os.utime`: ningún test depende del reloj real.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
import pytest

from fundamentals.fetch import (
    DIAS_ENTRE_COMPROBACIONES,
    DIAS_HASTA_INFORME_NUEVO,
    RACHA_MAXIMA,
    CorridaAbortada,
    _cache_path,
    caducado,
    load_facts,
    ultimo_cierre,
)

CIERRE = date(2025, 12, 31)


def _facts(ticker: str = "AAA", n: int = 12, ultimo: date = CIERRE) -> pd.DataFrame:
    """Tabla larga con la forma de facts.to_dataframe(); el último trimestre cierra en `ultimo`."""
    fechas = pd.date_range(end=pd.Timestamp(ultimo), periods=n, freq="QE")
    return pd.DataFrame(
        {
            "concept": ["us-gaap:Revenues"] * n,
            "value": [str(100.0 + i) for i in range(n)],
            "numeric_value": [100.0 + i for i in range(n)],
            "unit": ["USD"] * n,
            "period_type": ["duration"] * n,
            "period_start": fechas - pd.Timedelta(days=89),
            "period_end": fechas,
            "fiscal_year": [f.year for f in fechas],
            "fiscal_period": [f"Q{(f.month - 1) // 3 + 1}" for f in fechas],
        }
    )


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _envejecer(cache_dir: Path, ticker: str, dias: int, hoy: date) -> None:
    """Pone el mtime del fichero de `ticker` a `dias` días antes de `hoy`."""
    momento = datetime.combine(hoy - timedelta(days=dias), datetime.min.time()).timestamp()
    os.utime(_cache_path(cache_dir, ticker), (momento, momento))


# --- La regla ---------------------------------------------------------------


def test_las_constantes_son_las_del_spec():
    assert DIAS_HASTA_INFORME_NUEVO == 75
    assert DIAS_ENTRE_COMPROBACIONES == 7


def test_el_ultimo_cierre_es_el_period_end_mas_reciente():
    assert ultimo_cierre(_facts()) == CIERRE


def test_el_ultimo_cierre_ignora_filas_sin_periodo_trimestral_ni_anual():
    facts = _facts()
    rara = facts.iloc[[0]].copy()
    rara["period_end"] = pd.Timestamp("2030-01-01")
    rara["fiscal_period"] = None
    assert ultimo_cierre(pd.concat([facts, rara])) == CIERRE


def test_el_ultimo_cierre_cuenta_el_anual():
    facts = _facts()
    anual = facts.iloc[[0]].copy()
    anual["period_end"] = pd.Timestamp("2026-03-31")
    anual["fiscal_period"] = "FY"
    assert ultimo_cierre(pd.concat([facts, anual])) == date(2026, 3, 31)


def test_sin_cierre_medible_el_ultimo_cierre_es_none():
    assert ultimo_cierre(pd.DataFrame()) is None
    assert ultimo_cierre(_facts().assign(fiscal_period=None)) is None


@pytest.mark.parametrize(
    "dias_desde_cierre, dias_desde_descarga, esperado",
    [
        (74, 8, False),  # aún no toca informe nuevo
        (76, 6, False),  # se preguntó hace poco
        (76, 8, True),   # las dos condiciones
        (75, 8, False),  # el borde no cuenta: «más de 75»
        (76, 7, False),  # el borde no cuenta: «más de 7»
    ],
)
def test_caduca_solo_con_las_dos_condiciones(dias_desde_cierre, dias_desde_descarga, esperado):
    hoy = CIERRE + timedelta(days=dias_desde_cierre)
    descargado_el = hoy - timedelta(days=dias_desde_descarga)
    assert caducado(_facts(), descargado_el, hoy) is esperado


def test_un_fichero_sin_cierre_medible_no_caduca():
    hoy = CIERRE + timedelta(days=400)
    assert caducado(pd.DataFrame(), hoy - timedelta(days=30), hoy) is False
