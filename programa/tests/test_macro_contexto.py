# tests/test_macro_contexto.py
from datetime import date

import pandas as pd
import pytest

from macro.contexto import UMBRAL_SAHM, calcular


def _mensual(valores, desde="2025-01"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


def test_curva_invertida():
    curva = pd.Series([0.2, -0.1], index=pd.DatetimeIndex(["2026-11-12", "2026-11-13"]))
    c = calcular(curva=curva, desempleo=None, ipc=None)
    assert c.curva == pytest.approx(-0.1) and c.curva_invertida is True


def test_sahm_activada():
    # 12 meses en 4,0 y después 4,5, 4,7 y 4,9: media de 3 = 4,7; mínimo previo = 4,0.
    desempleo = _mensual([4.0] * 12 + [4.5, 4.7, 4.9])
    c = calcular(curva=None, desempleo=desempleo, ipc=None)
    assert c.sahm == pytest.approx(0.7)
    assert c.sahm_activada is (0.7 >= UMBRAL_SAHM)


def test_sahm_sin_historia_suficiente_es_none():
    c = calcular(curva=None, desempleo=_mensual([4.0] * 10), ipc=None)
    assert c.sahm is None and c.sahm_activada is None


def test_inflacion_interanual():
    ipc = _mensual([100.0] + [101.0] * 11 + [103.0])
    c = calcular(curva=None, desempleo=None, ipc=ipc)
    assert c.inflacion == pytest.approx(0.03)


def test_sin_series_todo_es_none():
    c = calcular(curva=None, desempleo=None, ipc=None)
    assert (c.curva, c.sahm, c.inflacion) == (None, None, None)


def _sin(serie, mes):
    return serie.drop(pd.Timestamp(mes))


def test_inflacion_lee_t_menos_12_por_fecha_aunque_falte_un_mes_intermedio():
    # 2025-01..2026-09 con 2025-10 ausente; t-12 = 2025-09 existe.
    valores = [100.0 + i for i in range(21)]
    ipc = _sin(_mensual(valores, "2025-01"), "2025-10")
    esperado = 120.0 / 108.0 - 1  # 2026-09 frente a 2025-09
    assert calcular(curva=None, desempleo=None, ipc=ipc).inflacion == pytest.approx(esperado)


def test_inflacion_es_none_si_falta_t_menos_12_en_los_4_ultimos_meses():
    # Faltan 2025-07..2025-10: t-12 de 2026-07..2026-10 no existe.
    ipc = _mensual([100.0 + i for i in range(22)], "2025-01")
    for mes in ("2025-07", "2025-08", "2025-09", "2025-10"):
        ipc = _sin(ipc, mes)
    c = calcular(curva=None, desempleo=None, ipc=ipc)
    assert c.inflacion is None and c.mes_inflacion is None


def test_inflacion_salta_al_ultimo_mes_con_t_y_t_menos_12():
    # El caso real: sin 2025-10, el último dato (2026-10) no tiene t-12.
    ipc = _sin(_mensual([100.0 + i for i in range(22)], "2025-01"), "2025-10")
    c = calcular(curva=None, desempleo=None, ipc=ipc)
    assert c.mes_inflacion == date(2026, 9, 1)
    assert c.inflacion == pytest.approx(120.0 / 108.0 - 1)


def test_inflacion_real_con_hueco_de_octubre_2025():
    ipc = _sin(_mensual([100.0] * 21, "2024-10"), "2025-10")
    ipc.loc[pd.Timestamp("2025-09-01")] = 324.245
    ipc.loc[pd.Timestamp("2026-09-01")] = 336.298
    ipc.loc[pd.Timestamp("2026-10-01")] = 337.0
    c = calcular(curva=None, desempleo=None, ipc=ipc.sort_index())
    assert c.mes_inflacion == date(2026, 9, 1)
    assert c.inflacion == pytest.approx(0.03717, abs=1e-5)


def _unrate_real():
    cola = {"2025-08": 4.3, "2025-09": 4.4, "2025-11": 4.5, "2025-12": 4.4,
            "2026-01": 4.3, "2026-02": 4.4, "2026-03": 4.3, "2026-04": 4.3,
            "2026-05": 4.3, "2026-06": 4.2, "2026-07": 4.1, "2026-08": 4.1,
            "2026-09": 4.2, "2026-10": 4.1}
    previo = _mensual([4.2] * 10, "2024-10")  # 2024-10..2025-07
    cola = pd.Series(cola)
    cola.index = pd.to_datetime(cola.index + "-01")
    return pd.concat([previo, cola])


def test_sahm_real_con_el_hueco_de_octubre_2025_se_calcula():
    c = calcular(curva=None, desempleo=_unrate_real(), ipc=None)
    # Media de 2026-10 menos el mínimo de las medias existentes (2026-08).
    assert c.sahm == pytest.approx((4.1 + 4.2 + 4.1) / 3 - (4.2 + 4.1 + 4.1) / 3)
    assert c.sahm_activada is False


def test_sahm_es_none_con_mas_de_3_medias_previas_ausentes():
    # Cuatro huecos separados en los 12 meses previos anulan más de 3 medias.
    d = _mensual([4.0] * 24, "2024-01")
    for mes in ("2025-02", "2025-05", "2025-08", "2025-10"):
        d = _sin(d, mes)
    assert calcular(curva=None, desempleo=d, ipc=None).sahm is None


def test_sahm_con_un_hueco_dentro_de_los_12_meses_previos_se_calcula():
    # Un hueco anula 3 medias; quedan 9 de 12, que es el mínimo.
    desempleo = _sin(_mensual([4.0] * 20 + [4.8], "2025-01"), "2025-10")
    assert calcular(curva=None, desempleo=desempleo, ipc=None).sahm is not None


def test_sahm_con_un_hueco_en_los_ultimos_3_meses_es_none():
    desempleo = _sin(_mensual([4.0] * 24, "2024-01"), "2025-11")  # acaba en 2025-12
    assert calcular(curva=None, desempleo=desempleo, ipc=None).sahm is None


def test_sahm_con_un_hueco_antiguo_se_calcula():
    # 2024-01..2025-12; el hueco de 2024-03 queda fuera de los 12 previos de 2025-12.
    valores = [4.0] * 21 + [4.5, 4.7, 4.9]
    desempleo = _sin(_mensual(valores, "2024-01"), "2024-03")
    c = calcular(curva=None, desempleo=desempleo, ipc=None)
    assert c.sahm == pytest.approx(0.7)
