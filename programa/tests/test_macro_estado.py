# tests/test_macro_estado.py
from datetime import date, datetime, timezone

import pandas as pd

from macro.estado import leer_region
from macro.fuentes import Serie


def _serie(valores, desde="2026-07"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


def test_con_dato_bueno_se_puede_inclinar():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8]), "ok", datetime.now(timezone.utc))
    e = leer_region("usa", date(2026, 11, 16), traer=traer)
    assert e.fase.clave == "expansion"
    assert e.motivo_no_inclinar is None


def test_sin_red_no_hay_fase_y_dice_por_que():
    e = leer_region("usa", date(2026, 11, 16), traer=lambda r: Serie(None, "sin_red"))
    assert e.fase is None and e.serie is None
    assert e.motivo_no_inclinar == "sin_red"


def test_dato_rancio_tiene_fase_pero_no_inclina():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8], desde="2026-01"), "ok")
    e = leer_region("usa", date(2026, 11, 16), traer=traer)
    assert e.fase.clave == "expansion"
    assert e.motivo_no_inclinar == "dato_rancio"


def test_la_cache_vieja_se_avisa():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8]), "ok", vieja=True)
    assert leer_region("usa", date(2026, 11, 16), traer=traer).vieja is True
