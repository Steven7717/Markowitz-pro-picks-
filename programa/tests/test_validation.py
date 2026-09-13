import numpy as np
import pandas as pd
import pytest

from validation import (
    default_window_sizes,
    sharpe_difference_standard_error,
    sharpe_standard_error,
    walk_forward_comparison,
    walk_forward_validation,
)


def _noise(n_obs: int, n_assets: int = 6, seed: int = 4) -> pd.DataFrame:
    """Assets with zero true expected return — any positive Sharpe is fitted noise."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0.0, 0.012, size=(n_obs, n_assets)),
        columns=[f"A{i}" for i in range(n_assets)],
    )


def test_returns_none_when_history_is_shorter_than_a_year():
    assert walk_forward_validation(_noise(120), 0.0, 252, (0.0, 1.0), False) is None


def test_default_windows_scale_with_the_data_frequency():
    assert default_window_sizes(252) == (504, 63)
    assert default_window_sizes(12) == (24, 3)


def test_windows_shrink_to_fit_when_history_is_tight():
    """One year of daily data cannot host a two-year training window.

    The app's '1 Semana' horizon fetches exactly 252 rows, so without an adaptive
    fallback validation would silently never run on the daily horizons.
    """
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert r is not None
    assert r["n_windows"] >= 3
    assert r["train_size"] + r["test_size"] <= 252


def test_one_year_of_daily_data_still_reports_out_of_sample_results():
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert np.isfinite(r["out_of_sample_sharpe"])


def test_reports_how_many_windows_were_evaluated():
    r = walk_forward_validation(_noise(1200), 0.0, 252, (0.0, 1.0), False)
    assert r["n_windows"] > 0


def test_window_count_follows_the_requested_window_sizes():
    r = walk_forward_validation(
        _noise(1000), 0.0, 252, (0.0, 1.0), False, train_size=400, test_size=100,
    )
    # windows start at 0, 100, 200, ... while train+test still fits in 1000 rows
    assert r["n_windows"] == 6


def test_in_sample_sharpe_far_exceeds_out_of_sample_on_pure_noise():
    """The whole point of the audit: the reported Sharpe does not survive validation."""
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert r["in_sample_sharpe"] > r["out_of_sample_sharpe"] + 0.5


def test_out_of_sample_sharpe_on_pure_noise_is_unbiased():
    """Averaged over seeds, not a single draw.

    One walk-forward run has a standard error of roughly 0.3-0.4 Sharpe, so any
    single seed can land near 1.0 by luck. Averaging across seeds is what
    actually tests that the procedure is unbiased.
    """
    sharpes = [
        walk_forward_validation(_noise(2000, seed=s), 0.0, 252, (0.0, 1.0), False)[
            "out_of_sample_sharpe"
        ]
        for s in range(6)
    ]
    assert abs(np.mean(sharpes)) < 0.6


def test_reports_an_equal_weight_benchmark_over_the_same_windows():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert "equal_weight_sharpe" in r
    assert np.isfinite(r["equal_weight_sharpe"])


def test_degradation_is_the_gap_between_in_and_out_of_sample():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert np.isclose(
        r["degradation"], r["in_sample_sharpe"] - r["out_of_sample_sharpe"]
    )


def test_reports_out_of_sample_return_and_volatility():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert np.isfinite(r["oos_return"])
    assert r["oos_vol"] > 0


# ── Statistical power of the comparison ───────────────────────────────────────

def test_standard_error_shrinks_as_the_sample_lengthens():
    short = sharpe_standard_error(1.2, n_periods=252, periods_per_year=252)
    long = sharpe_standard_error(1.2, n_periods=2520, periods_per_year=252)
    assert long < short


def test_validation_reports_the_standard_error_of_its_own_estimate():
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert r["sharpe_stderr"] > 0


def test_four_windows_cannot_distinguish_the_optimum_from_equal_weight():
    """The gap the app warns about must exceed the noise in measuring it."""
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    gap = abs(r["equal_weight_sharpe"] - r["out_of_sample_sharpe"])
    assert gap < r["sharpe_stderr"]
    assert r["beats_equal_weight"] is None


def test_verdict_is_none_while_the_difference_stays_inside_the_noise():
    r = walk_forward_validation(_noise(252), 0.0, 252, (0.0, 1.0), False)
    assert r["beats_equal_weight"] is None


# ── Validating the other strategies ───────────────────────────────────────────

def _factor_market(n_obs: int, n_assets: int = 6, seed: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    betas = np.linspace(0.5, 1.8, n_assets)
    idio = np.linspace(0.006, 0.024, n_assets)
    factor = rng.normal(0.0004, 0.010, size=(n_obs, 1))
    return pd.DataFrame(
        factor @ betas.reshape(1, -1) + rng.normal(0, 1, (n_obs, n_assets)) * idio,
        columns=[f"A{i}" for i in range(n_assets)],
    )


def test_validation_defaults_to_max_sharpe():
    data = _factor_market(1500)
    assert (
        walk_forward_validation(data, 0.0, 252, (0.0, 1.0), False)["out_of_sample_sharpe"]
        == walk_forward_validation(
            data, 0.0, 252, (0.0, 1.0), False, strategy="max_sharpe"
        )["out_of_sample_sharpe"]
    )


@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_can_be_validated_out_of_sample(strategy):
    r = walk_forward_validation(
        _factor_market(1500), 0.0, 252, (0.0, 1.0), False, strategy=strategy
    )
    assert r is not None
    assert np.isfinite(r["out_of_sample_sharpe"])


def test_min_variance_delivers_the_lowest_out_of_sample_volatility():
    """It optimises for low risk, so it should actually deliver low risk."""
    data = _factor_market(2000)
    vols = {
        s: walk_forward_validation(data, 0.0, 252, (0.0, 1.0), False, strategy=s)["oos_vol"]
        for s in ("max_sharpe", "min_variance", "risk_parity")
    }
    assert vols["min_variance"] == min(vols.values())


def test_shrinkage_setting_is_carried_into_the_validation():
    plain = walk_forward_validation(_noise(1500), 0.0, 252, (0.0, 1.0), False, shrinkage=False)
    shrunk = walk_forward_validation(_noise(1500), 0.0, 252, (0.0, 1.0), False, shrinkage=True)
    assert shrunk["in_sample_sharpe"] < plain["in_sample_sharpe"]


# ── El error estándar de un Sharpe suelto ─────────────────────────────────────

def _sharpe_muestral(x: np.ndarray, ppy: int) -> np.ndarray:
    return x.mean(axis=1) / x.std(axis=1, ddof=1) * np.sqrt(ppy)


@pytest.mark.parametrize(
    "sharpe, ppy, n_periods",
    [(0.5, 252, 504), (1.3, 252, 504), (3.0, 252, 504), (1.3, 12, 153), (3.0, 12, 153)],
)
def test_standard_error_reproduces_the_sampling_noise_it_claims_to_measure(
    sharpe, ppy, n_periods
):
    """Lo (2002) sobre el Sharpe ANUALIZADO lleva S²/(2q), no S²/2.

    Metiendo el Sharpe anualizado en la fórmula por período el error se
    ensanchaba un 30% con Sharpe 1,3 y se duplicaba con Sharpe 3 — siempre en la
    dirección de «no se distingue del ruido».
    """
    rng = np.random.default_rng(0)
    muestras = rng.standard_normal((4000, n_periods)) + sharpe / np.sqrt(ppy)
    empirico = float(_sharpe_muestral(muestras, ppy).std(ddof=1))
    formula = sharpe_standard_error(sharpe, n_periods, ppy)
    assert formula == pytest.approx(empirico, rel=0.05)


def test_standard_error_of_one_year_of_daily_data_is_around_one():
    """sqrt((1 + S²/(2·252)) / años) con S=1,2 sobre un año es ~1,00."""
    se = sharpe_standard_error(1.2, n_periods=252, periods_per_year=252)
    assert 0.95 < se < 1.05


# ── El error estándar de la DIFERENCIA entre dos Sharpe ───────────────────────

def _par_correlado(rho: float, n: int, sharpe: float, ppy: int, seed: int = 1):
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(np.array([[1.0, rho], [rho, 1.0]]))
    z = rng.standard_normal((n, 2)) @ chol.T + sharpe / np.sqrt(ppy)
    return z[:, 0], z[:, 1]


def test_the_gap_error_collapses_as_the_two_portfolios_converge():
    """Dos carteras casi iguales tienen un hueco casi perfectamente medido."""
    flojo = sharpe_difference_standard_error(
        *_par_correlado(0.30, 400, 1.0, 252), 0.0, 252
    )
    pegado = sharpe_difference_standard_error(
        *_par_correlado(0.99, 400, 1.0, 252), 0.0, 252
    )
    assert pegado < flojo / 3


@pytest.mark.parametrize("rho", [0.90, 0.95, 0.99])
def test_the_gap_error_reproduces_the_sampling_noise_of_the_gap(rho):
    """Monte Carlo sobre la diferencia, que es el estadístico del veredicto."""
    n, ppy, sharpe = 153, 12, 1.3
    rng = np.random.default_rng(5)
    chol = np.linalg.cholesky(np.array([[1.0, rho], [rho, 1.0]]))
    huecos = []
    for _ in range(3000):
        z = rng.standard_normal((n, 2)) @ chol.T + sharpe / np.sqrt(ppy)
        a, b = z[:, 0], z[:, 1]
        huecos.append(
            a.mean() / a.std(ddof=1) * np.sqrt(ppy)
            - b.mean() / b.std(ddof=1) * np.sqrt(ppy)
        )
    empirico = float(np.std(huecos, ddof=1))
    formula = sharpe_difference_standard_error(
        *_par_correlado(rho, n, sharpe, ppy), 0.0, ppy
    )
    assert formula == pytest.approx(empirico, rel=0.15)


def test_the_gap_error_is_far_tighter_than_the_error_of_either_sharpe():
    """La comparación es pareada: el movimiento común de mercado se cancela.

    Es el mismo argumento que `research/timing.py:block_bootstrap_stderr` ya
    escribió para la Puerta B, y que esta validación no aplicaba.
    """
    a, b = _par_correlado(0.95, 153, 1.3, 12)
    suelto = sharpe_standard_error(1.3, 153, 12)
    pareado = sharpe_difference_standard_error(a, b, 0.0, 12)
    assert pareado < suelto / 3


def test_two_identical_series_have_a_gap_error_of_zero():
    a = np.linspace(-0.02, 0.03, 200)
    assert sharpe_difference_standard_error(a, a, 0.0, 252) == pytest.approx(0.0, abs=1e-9)


def test_the_gap_error_needs_two_series_of_the_same_length():
    assert sharpe_difference_standard_error(
        np.zeros(10), np.zeros(11), 0.0, 252
    ) == float("inf")


# ── El veredicto se decide con el error del hueco ─────────────────────────────

def test_the_verdict_is_judged_against_the_error_of_the_gap():
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    hueco = abs(r["out_of_sample_sharpe"] - r["equal_weight_sharpe"])
    if r["beats_equal_weight"] is None:
        assert hueco <= r["gap_stderr"]
    else:
        assert hueco > r["gap_stderr"]


def test_the_gap_error_is_reported_alongside_the_sharpe_error():
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert r["gap_stderr"] > 0
    assert r["gap_stderr"] < r["sharpe_stderr"]


def test_a_genuine_edge_is_no_longer_hidden_by_the_wrong_error_bar():
    """Un activo con Sharpe verdadero 1,6 entre cuatro de puro ruido.

    La optimización le gana a 1/N de verdad; con el umbral viejo —el error de un
    Sharpe suelto— el veredicto salía «no se distingue» en el 100% de los casos.
    """
    rng = np.random.default_rng(1000)
    mu = np.array([0.0010, 0.0, 0.0, 0.0, 0.0])
    vol = np.array([0.010, 0.02, 0.02, 0.02, 0.02])
    datos = pd.DataFrame(
        rng.standard_normal((2000, 5)) * vol + mu,
        columns=[f"A{i}" for i in range(5)],
    )
    r = walk_forward_validation(datos, 0.0, 252, (0.0, 1.0), False)
    assert r["out_of_sample_sharpe"] > r["equal_weight_sharpe"]
    assert r["beats_equal_weight"] is True


# ── Un año bursátil de datos diarios ──────────────────────────────────────────

def test_one_trading_year_of_daily_data_is_enough_to_validate():
    """El horizonte «1 Semana» descarga un año y devuelve 250 retornos.

    La guarda comparaba ese conteo real contra el 252 nominal con el que se
    anualiza, así que ese horizonte no se validaba nunca: la pantalla decía
    «no hay suficiente historial» sobre un año entero de datos.
    """
    assert walk_forward_validation(_noise(250), 0.0, 252, (0.0, 1.0), False) is not None


def test_half_a_year_of_daily_data_is_still_rejected():
    assert walk_forward_validation(_noise(126), 0.0, 252, (0.0, 1.0), False) is None


# ── Las tres estrategias sobre exactamente las mismas ventanas ────────────────

def test_the_comparison_gives_every_strategy_the_same_windows():
    c = walk_forward_comparison(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert {r["n_windows"] for r in c["por_estrategia"].values()} == {c["n_windows"]}
    assert len({r["n_oos_periods"] for r in c["por_estrategia"].values()}) == 1


def test_the_comparison_shares_a_single_equal_weight_benchmark():
    """Con ventanas distintas cada estrategia se medía contra un 1/N distinto.

    Medido con datos reales: paridad de riesgo convergía en 30 de 31 ventanas y
    su referencia salía +1,06 donde las otras dos veían +1,13. La tabla imprimía
    una sola fila «Equal Weight» y la comparaba con las tres.
    """
    c = walk_forward_comparison(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    referencias = {r["equal_weight_sharpe"] for r in c["por_estrategia"].values()}
    assert len(referencias) == 1


def test_the_comparison_covers_the_three_strategies():
    c = walk_forward_comparison(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert set(c["por_estrategia"]) == {"max_sharpe", "min_variance", "risk_parity"}


def test_the_comparison_says_how_many_windows_it_had_to_discard():
    c = walk_forward_comparison(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert c["n_windows_descartadas"] >= 0
    assert c["n_windows"] + c["n_windows_descartadas"] > 0


def test_the_comparison_matches_the_single_run_when_nothing_is_discarded():
    datos = _factor_market(2000)
    c = walk_forward_comparison(datos, 0.0, 252, (0.0, 1.0), False)
    if c["n_windows_descartadas"] == 0:
        suelto = walk_forward_validation(datos, 0.0, 252, (0.0, 1.0), False)
        assert c["por_estrategia"]["max_sharpe"]["out_of_sample_sharpe"] == pytest.approx(
            suelto["out_of_sample_sharpe"]
        )


def test_the_comparison_returns_none_when_history_is_too_short():
    assert walk_forward_comparison(_noise(120), 0.0, 252, (0.0, 1.0), False) is None
