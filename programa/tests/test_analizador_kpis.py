from unittest.mock import patch

import pandas as pd
import pytest

from analizador import kpis
from fundamentals.concepts import LINEAS
from fundamentals.fetch import CorridaAbortada, CoverageReport
from fundamentals.kpis import TODOS_LOS_KPIS

NAN = float("nan")


def _panel_de(ticker):
    indice = pd.MultiIndex.from_tuples(
        [(ticker, pd.Timestamp("2026-03-31")), (ticker, pd.Timestamp("2026-06-30"))],
        names=["ticker", "periodo"],
    )
    panel = pd.DataFrame(1.0, index=indice, columns=list(TODOS_LOS_KPIS))
    panel["trimestre"] = ["2026Q1", "2026Q2"]
    return panel


def test_una_empresa_de_la_sec_pasa_por_el_mismo_motor_que_el_ranking():
    with patch.object(kpis, "build_panel", return_value=(_panel_de("VEEV"), None, None)) as motor:
        filas, motivo = kpis.kpis_sec("VEEV")
    motor.assert_called_once_with(["VEEV"])
    assert motivo == "ok"
    assert list(filas.index) == [pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")]
    assert "trimestre" in filas.columns


def test_si_la_sec_no_responde_no_hay_filas():
    abortada = CorridaAbortada("sin_fuente", "x", CoverageReport(requested=["VEEV"]))
    with patch.object(kpis, "build_panel", side_effect=abortada):
        assert kpis.kpis_sec("VEEV") == (None, "sin_estados")


def test_si_falta_el_precio_no_se_culpa_a_la_sec():
    abortada = CorridaAbortada("sin_precios", "x", CoverageReport(requested=["VEEV"]))
    with patch.object(kpis, "build_panel", side_effect=abortada):
        assert kpis.kpis_sec("VEEV") == (None, "sin_precio")


def test_un_panel_vacio_no_son_filas():
    vacio = pd.DataFrame(columns=[*TODOS_LOS_KPIS, "trimestre"])
    vacio.index = pd.MultiIndex.from_arrays([[], []], names=["ticker", "periodo"])
    with patch.object(kpis, "build_panel", return_value=(vacio, None, None)):
        assert kpis.kpis_sec("VEEV") == (None, "sin_estados")


def _trimestrales():
    fechas = pd.date_range("2025-03-31", periods=5, freq="QE")
    lineas = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    lineas["bpa_diluido"] = 1.0
    lineas["acciones_diluidas"] = 10.0
    return lineas


def _precios(por_simbolo):
    def precios_por_periodo(simbolo, periodos, cierres, min_obs):
        assert min_obs == 1
        return pd.Series(por_simbolo[simbolo], index=periodos), False

    return precios_por_periodo


def test_el_precio_va_en_la_moneda_de_los_estados_al_tipo_de_cada_fecha():
    # TSM cotiza en dólares y presenta en TWD: 10 dólares a 32 TWD por dólar.
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"TSM": 10.0, "USDTWD=X": 32.0})):
        filas = kpis.kpis_yf("TSM", trimestrales, pd.DataFrame(), "USD", "TWD", 0.031)
    # PER = precio en TWD / BPA de doce meses en TWD = 320 / 4.
    assert filas["per"].iloc[-1] == pytest.approx(320.0 / 4.0)


def test_un_precio_en_peniques_se_cambia_con_la_libra_y_se_divide_por_cien():
    # SHEL.L cotiza en peniques y presenta en dólares: el par es GBPUSD=X, y el
    # precio en dólares es el de peniques por el tipo y entre cien.
    trimestrales = _trimestrales()
    dobles = _precios({"SHEL.L": 3900.0, "GBPUSD=X": 1.3})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        filas = kpis.kpis_yf("SHEL.L", trimestrales, pd.DataFrame(), "GBp", "USD", 1.0)
    assert filas["per"].iloc[-1] == pytest.approx(3900.0 * 1.3 / 100 / 4.0)


def test_peniques_frente_a_libras_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    dobles = _precios({"X.L": 400.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles) as precios:
        filas = kpis.kpis_yf("X.L", trimestrales, pd.DataFrame(), "GBp", "GBP", 1.32)
    assert precios.call_count == 1
    assert filas["per"].iloc[-1] == pytest.approx(4.0 / 4.0)


def test_los_suelos_de_los_kpis_se_aplican_en_dolares():
    # Unos ingresos de 1.500 millones de pesos son 81 millones de dólares: por
    # debajo del suelo de 100 millones de `fundamentals.kpis`, como lo estaría
    # una empresa de EE. UU. de ese tamaño en el panel de referencia. En pesos
    # el suelo no actuaría, y la comparación con los pares no sería la misma.
    trimestrales = _trimestrales()
    trimestrales["ingresos"] = 1.5e9
    trimestrales["beneficio_operativo"] = 3.0e8
    dobles = _precios({"PEQ.MX": 10.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        en_dolares = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        sin_convertir = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert en_dolares["margen_operativo"].isna().all()
    assert sin_convertir["margen_operativo"].iloc[-1] == pytest.approx(0.2)


def test_el_tipo_a_dolares_no_cambia_ningun_cociente():
    trimestrales = _trimestrales()
    dobles = _precios({"X.MX": 48.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        a = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        b = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert a["per"].iloc[-1] == pytest.approx(b["per"].iloc[-1])


def test_el_recuento_de_acciones_no_se_pasa_a_dolares():
    # Las acciones no son dinero: pasadas por el tipo, la capitalización lo
    # llevaría dos veces, en el precio y en el recuento, y el precio/FCF saldría
    # 0,054 veces el de verdad. Es el único múltiplo sin suelo que lo tape.
    trimestrales = _trimestrales()
    trimestrales["flujo_operativo"] = 2.0
    trimestrales["capex"] = 1.0
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"X.MX": 48.0})):
        filas = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
    # Capitalización 48 × 10 entre un FCF de doce meses de 4 × (2 − 1).
    assert filas["precio_fcf"].iloc[-1] == pytest.approx(48.0 * 10.0 / 4.0)


def test_en_la_misma_moneda_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"WALMEX.MX": 48.0})) as precios:
        filas = kpis.kpis_yf("WALMEX.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
    assert precios.call_count == 1
    assert filas["per"].iloc[-1] == pytest.approx(48.0 / 4.0)
