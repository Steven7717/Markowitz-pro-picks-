import pytest

from data import parse_tickers, HORIZON_CONFIG, DEFAULT_HORIZON


def test_parse_tickers_comma_separated():
    assert parse_tickers("AAPL, MSFT, GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_space_separated():
    assert parse_tickers("AAPL MSFT GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_mixed_delimiters():
    assert parse_tickers("AAPL, MSFT GOOGL,AMZN") == ["AAPL", "MSFT", "GOOGL", "AMZN"]


def test_parse_tickers_converts_to_uppercase():
    assert parse_tickers("aapl msft") == ["AAPL", "MSFT"]


def test_parse_tickers_empty_string():
    assert parse_tickers("") == []


def test_parse_tickers_only_whitespace():
    assert parse_tickers("   ") == []


def test_horizon_config_has_all_six_horizons():
    expected = {"1_semana", "1_mes", "3_meses", "6_meses", "1_ano", "3_anos"}
    assert set(HORIZON_CONFIG.keys()) == expected


# ── El horizonte tiene clave, y la etiqueta es texto de pantalla ─────────────
#
# Antes no la tenía: la etiqueta ERA la identidad, y se escribía en
# `portafolios/*.json`, en `libros/*.json` y en las preferencias. Reescribir «1
# Año» no habría roto una exportación —eso fue lo de la estrategia— sino la
# RECARGA de todo portafolio guardado con él.

import data  # noqa: E402
from data import HORIZON_LABELS, clave_de_horizonte  # noqa: E402


def test_las_claves_del_horizonte_no_son_texto_de_pantalla():
    """Una clave se escribe en un fichero: ni espacios, ni tildes, ni mayúsculas."""
    for clave in HORIZON_CONFIG:
        assert clave == clave.lower()
        assert " " not in clave
        assert clave.isascii()


def test_cada_horizonte_tiene_etiqueta_y_ninguna_sobra():
    assert set(HORIZON_LABELS) == set(HORIZON_CONFIG)


def test_una_clave_se_reconoce_a_si_misma():
    for clave in HORIZON_CONFIG:
        assert clave_de_horizonte(clave) == clave


def test_la_etiqueta_con_la_que_se_guardo_antes_sigue_valiendo():
    """Un portafolio de antes de esto guarda «1 Mes», no `1_mes`, y tiene que abrir."""
    assert clave_de_horizonte("1 Mes") == "1_mes"
    assert clave_de_horizonte("3 Años") == "3_anos"


@pytest.mark.parametrize("valor", ["8 Meses", "1 Quincena", "", None, 3, ["1 Mes"]])
def test_lo_que_no_es_ni_una_cosa_ni_otra_no_se_adivina(valor):
    assert clave_de_horizonte(valor) is None


def test_las_heredadas_no_dependen_de_como_se_escriba_hoy(monkeypatch):
    """La tabla de heredados es historia, y la historia no se recalcula.

    Si se derivase de `HORIZON_LABELS`, quedaría inservible justo el día que
    sirve: al reescribir una etiqueta, los ficheros que llevan la vieja dentro
    dejarían de reconocerse — el defecto entero otra vez, por la puerta de atrás.
    """
    monkeypatch.setitem(data.HORIZON_LABELS, "1_mes", "Un mes")
    assert clave_de_horizonte("1 Mes") == "1_mes"


def test_horizon_config_entries_have_required_fields():
    for key, cfg in HORIZON_CONFIG.items():
        assert "period" in cfg, f"{key} missing 'period'"
        assert "interval" in cfg, f"{key} missing 'interval'"
        assert "periods_per_year" in cfg, f"{key} missing 'periods_per_year'"
        assert cfg["periods_per_year"] in (12, 52, 252), f"{key} has unexpected periods_per_year"


def test_default_horizon_exists_in_config():
    assert DEFAULT_HORIZON in HORIZON_CONFIG


from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from data import fetch_market_data, RF_FALLBACK


def _make_mock_download(tickers: list[str], n_rows: int = 100) -> pd.DataFrame:
    """Build a fake yfinance MultiIndex DataFrame."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=n_rows)
    all_tickers = tickers + ["^IRX", "^GSPC"]
    arrays = [["Close"] * len(all_tickers), all_tickers]
    cols = pd.MultiIndex.from_arrays(arrays, names=["Price", "Ticker"])
    data = rng.uniform(100, 200, size=(n_rows, len(all_tickers)))
    # Make ^IRX look like a realistic annualized rate (e.g. 5.25)
    irx_idx = all_tickers.index("^IRX")
    data[:, irx_idx] = 5.25
    return pd.DataFrame(data, index=dates, columns=cols)


@patch("data.yf.download")
def test_fetch_market_data_returns_expected_keys(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"])
    result = fetch_market_data(("AAPL", "MSFT"), "1_mes")
    assert "returns" in result
    assert "rf_rate" in result
    assert "benchmark_returns" in result
    assert "invalid_tickers" in result
    assert "periods_per_year" in result
    assert "valid_tickers" in result


@patch("data.yf.download")
def test_fetch_market_data_rf_rate_converted_to_period(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"])
    result = fetch_market_data(("AAPL", "MSFT"), "1_mes")
    # ^IRX = 5.25% annual → per-day ≈ 5.25/100/252
    expected_rf = 5.25 / 100 / 252
    assert abs(result["rf_rate"] - expected_rf) < 1e-6


@patch("data.yf.download")
def test_fetch_market_data_uses_fallback_when_irx_missing(mock_dl):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=100)
    cols = pd.MultiIndex.from_arrays(
        [["Close", "Close", "Close"], ["AAPL", "^IRX", "^GSPC"]],
        names=["Price", "Ticker"],
    )
    data = rng.uniform(100, 200, size=(100, 3))
    data[:, 1] = np.nan  # ^IRX all NaN
    df = pd.DataFrame(data, index=dates, columns=cols)
    mock_dl.return_value = df
    result = fetch_market_data(("AAPL",), "1_mes")
    assert result["rf_rate"] == RF_FALLBACK / 252
    assert result.get("rf_available") is False


# ── Risk-free rate: audit finding D ───────────────────────────────────────────

import warnings

from data import compute_returns, compute_rf_rate


def test_risk_free_rate_averages_over_the_whole_sample_period():
    """A single spot yield does not describe the decade the returns came from."""
    irx = pd.Series([1.0, 3.0, 5.0])  # percent quotes averaging 3%
    rf, available = compute_rf_rate(irx, periods_per_year=12)
    assert available
    assert np.isclose(rf, 0.03 / 12)


def test_risk_free_rate_ignores_the_last_observation_alone():
    irx = pd.Series([1.0, 1.0, 9.0])
    rf, _ = compute_rf_rate(irx, periods_per_year=1)
    assert not np.isclose(rf, 0.09)


def test_risk_free_rate_falls_back_when_the_series_is_empty():
    rf, available = compute_rf_rate(pd.Series(dtype=float), periods_per_year=12)
    assert available is False
    assert np.isclose(rf, RF_FALLBACK / 12)


def test_risk_free_rate_falls_back_when_every_value_is_missing():
    rf, available = compute_rf_rate(pd.Series([np.nan, np.nan]), periods_per_year=12)
    assert available is False


# ── Return construction: gap handling ─────────────────────────────────────────

def test_returns_do_not_invent_flat_periods_across_price_gaps():
    """Forward-filling missing prices manufactures fake zero-return days."""
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, np.nan, 106.0, 107.0]})
    r = compute_returns(prices)
    assert not (r["A"] == 0.0).any()


def test_returns_drop_the_span_covering_a_gap_instead_of_mislabelling_it():
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, np.nan, 106.0, 107.0]})
    r = compute_returns(prices)
    assert len(r) == 2
    assert np.isclose(r["A"].iloc[0], 0.01)
    assert np.isclose(r["A"].iloc[1], 107.0 / 106.0 - 1.0)


def test_returns_keep_only_dates_where_every_asset_traded():
    prices = pd.DataFrame({
        "A": [100.0, 101.0, 102.0, 103.0],
        "B": [50.0, np.nan, 52.0, 53.0],
    })
    r = compute_returns(prices)
    assert not r.isna().any().any()


def test_return_construction_raises_no_pandas_deprecation_warning():
    """pandas 3.0 removes the implicit pad; this must not rely on it."""
    prices = pd.DataFrame({"A": [100.0, 101.0, np.nan, 106.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        compute_returns(prices)


@patch("data.yf.download")
def test_fetch_market_data_reports_the_observation_count(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"], n_rows=100)
    result = fetch_market_data(("AAPL", "MSFT"), "1_mes")
    assert result["n_obs"] == len(result["returns"])


# ── Un ticker incompleto se lleva por delante la muestra de los demás ──────────

import pytest

from data import COBERTURA_MINIMA, tickers_con_huecos


def _precios(n: int = 250, **columnas) -> pd.DataFrame:
    fechas = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame(columnas, index=fechas)


def test_una_serie_casi_vacia_se_senala():
    """El caso que lo motivó: AVB con 27 precios de 252.

    `compute_returns` tira las fechas donde falta algún precio —lo correcto con
    un hueco suelto— pero eso deja una cartera de cinco valores en 26
    observaciones y sin validación posible, sin decir cuál de los cinco lo causó.
    """
    completa = np.linspace(100, 130, 250)
    rota = np.full(250, np.nan)
    rota[:27] = np.linspace(200, 210, 27)
    p = _precios(AAA=completa, BBB=completa * 1.1, CCC=rota)
    huecos = tickers_con_huecos(p)
    assert set(huecos) == {"CCC"}
    assert huecos["CCC"] == pytest.approx(27 / 250, abs=0.01)


def test_las_series_completas_no_se_senalan():
    completa = np.linspace(100, 130, 250)
    assert tickers_con_huecos(_precios(AAA=completa, BBB=completa * 2)) == {}


def test_un_hueco_suelto_no_se_senala():
    """Un festivo local o una sesión sin cierre no es una serie rota."""
    casi = np.linspace(100, 130, 250)
    casi[50] = np.nan
    casi[120] = np.nan
    assert tickers_con_huecos(_precios(AAA=np.linspace(1, 2, 250), BBB=casi)) == {}


def test_el_umbral_es_configurable():
    casi = np.linspace(100, 130, 250)
    casi[:60] = np.nan  # 76% de cobertura
    p = _precios(AAA=np.linspace(1, 2, 250), BBB=casi)
    assert tickers_con_huecos(p, minimo=0.90) == {"BBB": pytest.approx(0.76, abs=0.01)}
    assert tickers_con_huecos(p, minimo=0.50) == {}


def test_el_umbral_por_defecto_deja_pasar_una_cobertura_alta():
    assert 0.5 < COBERTURA_MINIMA < 1.0


def test_un_marco_vacio_no_senala_nada():
    assert tickers_con_huecos(pd.DataFrame()) == {}


# ── Retornos sin exigir fecha común, para la covarianza por pares ─────────────

from data import compute_returns_amplios


def test_los_retornos_amplios_conservan_la_fecha_que_solo_le_falta_a_uno():
    """Donde `compute_returns` tira la fila entera, aqui el hueco es de su columna."""
    fechas = pd.bdate_range("2025-01-01", periods=6)
    p = pd.DataFrame({"AAA": [10, 11, 12, 13, 14, 15.0],
                      "BBB": [np.nan, np.nan, 20, 21, 22, 23.0]}, index=fechas)
    estrecho = compute_returns(p)
    amplio = compute_returns_amplios(p)
    assert len(estrecho) == 3          # solo donde cotizan los dos
    assert len(amplio) == 5            # toda la vida de AAA
    assert amplio["AAA"].notna().sum() == 5
    assert amplio["BBB"].notna().sum() == 3


def test_un_retorno_que_cruza_un_hueco_no_es_de_un_periodo_y_se_descarta():
    """Tres dias sin precio hacen que el cuarto valga por cuatro.

    Metido en una varianza la infla, y la covarianza por pares se come justo
    esas fechas que `compute_returns` habria tirado.
    """
    fechas = pd.bdate_range("2025-01-01", periods=7)
    p = pd.DataFrame({"AAA": [10, 11, np.nan, np.nan, 14, 15, 16.0],
                      "BBB": [20, 21, 22, 23, 24, 25, 26.0]}, index=fechas)
    amplio = compute_returns_amplios(p)
    # El de la reaparicion de AAA se descarta; los suyos limpios se quedan.
    assert np.isnan(amplio.loc[fechas[4], "AAA"])
    assert amplio["AAA"].notna().sum() == 3
    # Y a BBB no le quita ninguna fecha: el hueco no era suyo.
    assert amplio["BBB"].notna().sum() == 6


def test_los_retornos_amplios_no_inventan_ningun_precio():
    fechas = pd.bdate_range("2025-01-01", periods=5)
    p = pd.DataFrame({"AAA": [10, np.nan, 12, 13, 14.0]}, index=fechas)
    amplio = compute_returns_amplios(p)
    assert amplio["AAA"].dropna().tolist() == pytest.approx([13 / 12 - 1, 14 / 13 - 1])


def test_sin_huecos_amplio_y_estrecho_coinciden():
    fechas = pd.bdate_range("2025-01-01", periods=8)
    p = pd.DataFrame({"AAA": np.linspace(10, 20, 8), "BBB": np.linspace(30, 20, 8)},
                     index=fechas)
    assert np.allclose(compute_returns_amplios(p).values, compute_returns(p).values)
