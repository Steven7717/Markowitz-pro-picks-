import math

import numpy as np
import pandas as pd
import pytest

from valoracion.mercado import (
    Perfil,
    consenso_desde_estimacion,
    perfil_desde_info,
    regresion_beta,
    tasa_efectiva_desde_estado,
    tasa_libre_desde_cierres,
)

INFO = {
    "currentPrice": 989.04,
    "marketCap": 1_119_022_743_552,
    "currency": "USD",
    "financialCurrency": "USD",
    "industry": "Semiconductors",
    "country": "United States",
    "payoutRatio": 0.02,
    "quoteType": "EQUITY",
    "regularMarketTime": 1_791_835_140,
    "beta": 2.226,
}


def test_el_perfil_lee_lo_que_hace_falta():
    p = perfil_desde_info("MU", INFO)
    assert p.precio == 989.04
    assert p.capitalizacion == 1_119_022_743_552
    assert p.moneda == p.moneda_estados == "USD"
    assert p.industria == "Semiconductors"
    assert p.pais == "United States"
    assert p.payout == 0.02
    assert p.tipo == "EQUITY"
    assert p.hora.startswith("2026-")


def test_el_perfil_no_tiene_donde_guardar_la_beta_de_yahoo():
    # La beta se calcula con `regresion_beta`, nunca se lee de Yahoo: para
    # WALMEX.MX daba 0,016. La garantía es la forma del tipo, no una promesa.
    assert "beta" not in Perfil.__dataclass_fields__


def test_sin_precio_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": None}) is None


def test_el_precio_cae_al_de_mercado_si_falta_el_actual():
    p = perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": 50.0})
    assert p.precio == 50.0


def test_sin_capitalizacion_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "marketCap": None}) is None


def test_sin_moneda_no_hay_perfil():
    # Un precio sin moneda no se puede comparar con nada.
    assert perfil_desde_info("X", {**INFO, "currency": None}) is None


def test_la_moneda_de_los_estados_cae_a_la_del_precio():
    p = perfil_desde_info("X", {**INFO, "financialCurrency": None})
    assert p.moneda_estados == "USD"


def _cierres(rendimientos: np.ndarray) -> pd.Series:
    fechas = pd.date_range("2024-10-07", periods=len(rendimientos) + 1, freq="W-MON")
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1 + rendimientos]), index=fechas)


def test_la_beta_es_la_pendiente_de_la_regresion():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0.002, 0.02, 104)
    activo = 1.5 * mercado + generador.normal(0, 0.002, 104)
    beta = regresion_beta(_cierres(activo), _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.5, abs=0.05)
    assert beta.r2 > 0.95
    assert beta.semanas == 104
    assert beta.indice == "^GSPC"


def test_con_menos_de_un_ano_no_hay_beta():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0, 0.02, 40)
    assert regresion_beta(_cierres(mercado), _cierres(mercado), "^GSPC") is None


def test_la_beta_tolera_zonas_horarias_distintas():
    generador = np.random.default_rng(3)
    mercado = generador.normal(0, 0.02, 80)
    activo = _cierres(mercado)
    activo.index = activo.index.tz_localize("America/New_York")
    beta = regresion_beta(activo, _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.0)


def test_la_tasa_libre_es_el_ultimo_cierre_en_tanto_por_uno():
    assert tasa_libre_desde_cierres(pd.Series([4.1, 4.2, 5.24])) == pytest.approx(0.0524)


def test_sin_cierres_no_hay_tasa_libre():
    assert tasa_libre_desde_cierres(pd.Series([], dtype="float64")) is None


def test_la_tasa_efectiva_es_la_mas_reciente_con_dato():
    estado = pd.DataFrame(
        {"2025": [float("nan"), 10.0], "2024": [0.19, 9.0]},
        index=["Tax Rate For Calcs", "Net Income"],
    )
    assert tasa_efectiva_desde_estado(estado) == 0.19


def test_sin_fila_de_impuestos_no_hay_tasa_efectiva():
    estado = pd.DataFrame({"2025": [1.0]}, index=["Net Income"])
    assert tasa_efectiva_desde_estado(estado) is None
    assert tasa_efectiva_desde_estado(None) is None


def _estimacion(moneda: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"avg": [1.0, 2.0], "growth": [1.0663, 0.1648], "currency": [moneda, moneda]},
        index=["0y", "+1y"],
    )


def test_el_consenso_es_el_crecimiento_del_proximo_ano():
    assert consenso_desde_estimacion(_estimacion("USD"), "USD") == pytest.approx(0.1648)


def test_un_consenso_en_otra_moneda_se_descarta():
    # TSM: revenue_estimate en TWD y earnings_estimate en USD, en la misma consulta.
    assert consenso_desde_estimacion(_estimacion("TWD"), "USD") is None


def test_sin_estimacion_no_hay_consenso():
    assert consenso_desde_estimacion(pd.DataFrame(), "USD") is None
    assert consenso_desde_estimacion(None, "USD") is None
