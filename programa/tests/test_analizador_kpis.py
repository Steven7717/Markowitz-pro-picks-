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
    # Como lo devuelve `build_panel` cuando no queda ninguna empresa: sin
    # MultiIndex, así que no tiene nivel `ticker` por el que preguntar.
    vacio = pd.DataFrame(columns=[*TODOS_LOS_KPIS, "trimestre"], dtype="float64")
    with patch.object(kpis, "build_panel", return_value=(vacio, None, None)):
        assert kpis.kpis_sec("VEEV") == (None, "sin_estados")


def _trimestrales():
    fechas = pd.date_range("2025-03-31", periods=5, freq="QE")
    lineas = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    lineas["bpa_diluido"] = 1.0
    lineas["acciones_diluidas"] = 10.0
    return lineas


def _precios(por_simbolo, cierres=()):
    """Un `_precios_por_periodo` sin red que exige los cierres de ejercicio esperados."""

    def precios_por_periodo(simbolo, periodos, cierres_anuales, min_obs):
        assert min_obs == 1
        assert list(cierres_anuales) == list(cierres), simbolo
        return pd.Series(por_simbolo[simbolo], index=periodos), False

    return precios_por_periodo


def test_el_precio_va_en_la_moneda_de_los_estados_al_tipo_de_cada_fecha():
    # TSM cotiza en dólares y presenta en TWD: 10 dólares a 32 TWD por dólar.
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"TSM": 10.0, "USDTWD=X": 32.0})):
        filas, motivo = kpis.kpis_yf("TSM", trimestrales, pd.DataFrame(), "USD", "TWD", 0.031)
    assert motivo == "ok"
    # PER = precio en TWD / BPA de doce meses en TWD = 320 / 4.
    assert filas["per"].iloc[-1] == pytest.approx(320.0 / 4.0)


def test_un_precio_en_peniques_se_cambia_con_la_libra_y_se_divide_por_cien():
    # SHEL.L cotiza en peniques y presenta en dólares: el par es GBPUSD=X, y el
    # precio en dólares es el de peniques por el tipo y entre cien.
    trimestrales = _trimestrales()
    dobles = _precios({"SHEL.L": 3900.0, "GBPUSD=X": 1.3})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        filas, _ = kpis.kpis_yf("SHEL.L", trimestrales, pd.DataFrame(), "GBp", "USD", 1.0)
    assert filas["per"].iloc[-1] == pytest.approx(3900.0 * 1.3 / 100 / 4.0)


def test_peniques_frente_a_libras_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    dobles = _precios({"X.L": 400.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles) as precios:
        filas, _ = kpis.kpis_yf("X.L", trimestrales, pd.DataFrame(), "GBp", "GBP", 1.32)
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
        en_dolares, _ = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        sin_convertir, _ = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert en_dolares["margen_operativo"].isna().all()
    assert sin_convertir["margen_operativo"].iloc[-1] == pytest.approx(0.2)


def test_el_tipo_a_dolares_no_cambia_ningun_cociente():
    trimestrales = _trimestrales()
    dobles = _precios({"X.MX": 48.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        a, _ = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        b, _ = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert a["per"].iloc[-1] == pytest.approx(b["per"].iloc[-1])


def test_el_recuento_de_acciones_no_se_pasa_a_dolares():
    # Las acciones no son dinero: pasadas por el tipo, la capitalización lo
    # llevaría dos veces, en el precio y en el recuento, y el precio/FCF saldría
    # 0,054 veces el de verdad; el EV/EBITDA y el P/VL también saldrían mal, y
    # ningún suelo lo taparía. Se mira el precio/FCF porque sale con sólo dos
    # líneas y sin suelo que obligue a usar cifras grandes.
    trimestrales = _trimestrales()
    trimestrales["flujo_operativo"] = 2.0
    trimestrales["capex"] = 1.0
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"X.MX": 48.0})):
        filas, _ = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
    # Capitalización 48 × 10 entre un FCF de doce meses de 4 × (2 − 1).
    assert filas["precio_fcf"].iloc[-1] == pytest.approx(48.0 * 10.0 / 4.0)


def test_en_la_misma_moneda_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"WALMEX.MX": 48.0})) as precios:
        filas, _ = kpis.kpis_yf("WALMEX.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
    assert precios.call_count == 1
    assert filas["per"].iloc[-1] == pytest.approx(48.0 / 4.0)


def _anuales(ancla):
    # Dos ejercicios de verdad y, detrás, una columna de doce meses móviles con
    # sólo el BPA y el recuento, como las del anual de RY o de TM. Cae en un
    # cierre de trimestre: tomada por cierre de ejercicio, ese trimestre
    # cotizaría con el plazo del 10-K en vez del del 10-Q.
    fechas = pd.DatetimeIndex(["2024-12-31", "2025-12-31", "2026-03-31"])
    anuales = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    anuales.loc[fechas[:2], ancla] = 4.0e9
    anuales["bpa_diluido"] = 4.0
    anuales["acciones_diluidas"] = 10.0
    return anuales


@pytest.mark.parametrize("ancla", ["ingresos", "beneficio_neto"])
def test_solo_los_ejercicios_de_verdad_son_cierres(ancla):
    # Un banco no declara ingresos: su ancla es el beneficio.
    anuales = _anuales(ancla)
    dobles = _precios({"TSM": 10.0, "USDTWD=X": 32.0}, cierres=anuales.index[:2])
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles) as precios:
        _, motivo = kpis.kpis_yf("TSM", _trimestrales(), anuales, "USD", "TWD", 0.031)
    # El ticker y el par, los dos con los mismos cierres.
    assert precios.call_count == 2
    assert motivo == "ok"


@pytest.mark.parametrize(
    "por_simbolo",
    [{"TSM": NAN, "USDTWD=X": 32.0}, {"TSM": 10.0, "USDTWD=X": NAN}],
    ids=["sin_precio", "sin_tipo_de_cambio"],
)
def test_sin_precio_no_hay_filas_que_culpen_a_la_empresa(por_simbolo):
    # Con la valoración vacía, la ficha saldría excluida por «pilar sin datos»,
    # y culparía a la empresa de que Yahoo no diera el precio o el tipo.
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios(por_simbolo)):
        filas, motivo = kpis.kpis_yf("TSM", _trimestrales(), pd.DataFrame(), "USD", "TWD", 0.031)
    assert motivo == "sin_precio"
    assert filas is None


def test_sin_trimestres_no_es_un_fallo_de_precio():
    # Sin trimestres, la serie de precios sale vacía y pasaría por «sin precio».
    vacias = _trimestrales().iloc[:0]
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"X.MX": NAN})):
        filas, motivo = kpis.kpis_yf("X.MX", vacias, pd.DataFrame(), "MXN", "MXN", 0.054)
    assert motivo == "sin_estados"
    assert filas is None
