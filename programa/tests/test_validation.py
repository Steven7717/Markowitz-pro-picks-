import numpy as np
import pandas as pd
import pytest

from validation import (
    default_window_sizes,
    frase_veredicto,
    medida_veredicto,
    retorno_stderr,
    sharpe_difference_standard_error,
    sharpe_standard_error,
    veredicto,
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
    """Y los dos lados de la resta se miden igual: media de ventanas contra media.

    Restar el Sharpe agrupado a la media de cocientes cruzaba dos estimadores
    distintos del mismo número; `out_of_sample_sharpe_medio` es el que hace juego
    con `in_sample_sharpe`.
    """
    r = walk_forward_validation(_noise(3000), 0.0, 252, (0.0, 1.0), False)
    assert np.isclose(
        r["degradation"], r["in_sample_sharpe"] - r["out_of_sample_sharpe_medio"]
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
    """Contra el error del HUECO, y con el margen de dos sigmas."""
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    hueco = abs(r["out_of_sample_sharpe"] - r["equal_weight_sharpe"])
    if r["beats_equal_weight"] is None:
        assert hueco <= r["umbral_veredicto"]
    else:
        assert hueco > r["umbral_veredicto"]


def test_the_gap_error_is_reported_alongside_the_sharpe_error():
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert r["gap_stderr"] > 0
    assert r["gap_stderr"] < r["sharpe_stderr"]


def _mercado_con_ventaja(n_obs: int, seed: int, alfa: float = 0.0020) -> pd.DataFrame:
    """El mercado de factor de arriba, con una ventaja REAL en el primer activo.

    Un activo con alfa sobre el factor común es la ventaja que la optimización
    puede encontrar de verdad, y deja la cartera óptima pegada a 1/N —todos los
    activos comparten el factor— que es el régimen medido en la aplicación
    (correlación de 0,90 a 0,995) y donde el error del hueco y el del nivel se
    separan de veras.
    """
    rng = np.random.default_rng(seed)
    betas = np.linspace(0.5, 1.8, 6)
    idio = np.linspace(0.006, 0.024, 6)
    factor = rng.normal(0.0004, 0.010, size=(n_obs, 1))
    datos = factor @ betas.reshape(1, -1) + rng.normal(0, 1, (n_obs, 6)) * idio
    datos[:, 0] += alfa
    return pd.DataFrame(datos, columns=[f"A{i}" for i in range(6)])


def test_a_genuine_edge_is_no_longer_hidden_by_the_wrong_error_bar():
    """Seis mundos con ventaja real, con el tope del 30% que trae la aplicación.

    Sobre un solo sorteo esta pregunta no se puede contestar: el hueco fuera de
    muestra tiene un error estándar de ~0,3 Sharpe, así que una semilla
    afortunada demuestra tan poco como una desafortunada. Medido sobre seis
    mundos, la barra que toca —la del hueco pareado— ve la ventaja en cinco; la
    del Sharpe suelto no la ve en **ninguno**, que es lo que el usuario contaba
    («casi ninguna optimización supera a repartir por igual»).

    Y las dos barras se juzgan aquí con el MISMO umbral de dos sigmas, para que
    la comparación sea sobre el estadístico y no sobre el listón.
    """
    con_el_hueco = con_el_nivel = 0
    for semilla in range(8, 14):
        r = walk_forward_validation(
            _mercado_con_ventaja(2000, semilla), 0.0, 252, (0.0, 0.30), False
        )
        hueco = r["out_of_sample_sharpe"] - r["equal_weight_sharpe"]
        con_el_hueco += veredicto(hueco, r["gap_stderr"]) is True
        con_el_nivel += veredicto(hueco, r["sharpe_stderr"]) is True
    assert con_el_hueco >= 4, "la barra que toca sigue sin ver una ventaja real"
    assert con_el_nivel == 0, "la barra del nivel ya no era la que escondía nada"


def test_el_precio_de_pedir_dos_sigmas_es_callar_en_los_casos_justos():
    """Lo que el umbral nuevo cuesta, escrito aquí para que no se olvide.

    Este mundo —un activo de Sharpe 1,6 entre cuatro de ruido— tiene ventaja de
    verdad y el hueco medido la ve, pero a 1,91 errores estándar: dentro del
    listón. Con un solo error estándar la pantalla habría dicho «gana»; con dos
    dice «estos datos no lo distinguen», que es exactamente lo que ocurre a 1,91
    sigmas y es la dirección en la que conviene equivocarse. La misma tirada con
    otras siete semillas da entre -0,74 y 2,73 sigmas: el sorteo no sostenía un
    veredicto, lo sorteaba.
    """
    rng = np.random.default_rng(1000)
    mu = np.array([0.0010, 0.0, 0.0, 0.0, 0.0])
    vol = np.array([0.010, 0.02, 0.02, 0.02, 0.02])
    datos = pd.DataFrame(
        rng.standard_normal((2000, 5)) * vol + mu,
        columns=[f"A{i}" for i in range(5)],
    )
    r = walk_forward_validation(datos, 0.0, 252, (0.0, 1.0), False)
    hueco = r["out_of_sample_sharpe"] - r["equal_weight_sharpe"]
    assert hueco > r["gap_stderr"], "con un error estándar habría sido un «gana»"
    assert r["beats_equal_weight"] is None


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


# ── Con covarianza por pares, los retornos llevan huecos ──────────────────────

def _con_recien_llegado(n_obs: int = 2000, desde: int = 1400) -> pd.DataFrame:
    datos = _factor_market(n_obs, n_assets=4)
    datos["JOVEN"] = datos["A0"] * 1.1 + np.random.default_rng(4).normal(0, 0.01, n_obs)
    datos.iloc[:desde, datos.columns.get_loc("JOVEN")] = np.nan
    return datos


def test_el_walk_forward_admite_series_con_arranque_tardio():
    r = walk_forward_validation(_con_recien_llegado(), 0.0, 252, (0.0, 1.0), False,
                                pairwise=True)
    assert r is not None
    assert np.isfinite(r["out_of_sample_sharpe"])


def test_medir_fuera_de_muestra_exige_que_coticen_todos():
    """Ajustar puede mirar fechas incompletas; medir, no.

    `test.values @ pesos` con un activo sin precio da NaN, y un solo NaN
    envenena la media, la desviacion y el Sharpe de la serie entera.
    """
    r = walk_forward_validation(_con_recien_llegado(), 0.0, 252, (0.0, 1.0), False,
                                pairwise=True)
    assert np.isfinite(r["oos_return"])
    assert np.isfinite(r["equal_weight_sharpe"])
    assert np.isfinite(r["gap_stderr"])


def test_la_comparacion_tambien_admite_huecos():
    c = walk_forward_comparison(_con_recien_llegado(), 0.0, 252, (0.0, 1.0), False,
                                pairwise=True)
    assert c is not None
    assert len({r["equal_weight_sharpe"] for r in c["por_estrategia"].values()}) == 1
    for r in c["por_estrategia"].values():
        assert np.isfinite(r["out_of_sample_sharpe"])


def test_sin_la_opcion_los_resultados_no_se_mueven():
    """La covarianza por pares es opcional y por defecto no esta."""
    datos = _factor_market(1500)
    con = walk_forward_validation(datos, 0.0, 252, (0.0, 1.0), False, pairwise=False)
    sin = walk_forward_validation(datos, 0.0, 252, (0.0, 1.0), False)
    assert con["out_of_sample_sharpe"] == sin["out_of_sample_sharpe"]


# ── El veredicto pide dos errores estándar, no uno ────────────────────────────

def test_una_diferencia_de_un_solo_error_estandar_no_basta_para_un_veredicto():
    """Un error estándar es ~1σ, y el convenio de toda la estadística es 2σ."""
    assert veredicto(0.50, 0.30) is None


def test_dos_errores_estandar_sostienen_el_veredicto():
    assert veredicto(0.70, 0.30) is True


def test_perder_contra_1_sobre_n_exige_la_misma_evidencia_que_ganar():
    assert veredicto(-0.50, 0.30) is None
    assert veredicto(-0.70, 0.30) is False


def test_sin_un_error_medible_no_se_dicta_nada():
    assert veredicto(1.0, float("inf")) is None


def test_el_umbral_recorta_los_falsos_positivos_en_mundos_sin_ninguna_ventaja():
    """200 mundos sintéticos donde la optimización NO aporta nada.

    El hueco medido es entonces puro ruido de media cero. Con un solo error
    estándar la pantalla escribía el recuadro verde de `st.success` —«La
    optimización supera a repartir por igual»— en el 12% de ellos; con dos, la
    cola normal deja ~2%.
    """
    rng = np.random.default_rng(20)
    error = 0.35
    huecos = rng.normal(0.0, error, 200)
    con_uno = sum(veredicto(h, error, sigmas=1.0) is True for h in huecos)
    con_dos = sum(veredicto(h, error) is True for h in huecos)
    assert con_uno / 200 > 0.10
    assert con_dos / 200 < 0.05


def test_el_recorrido_completo_usa_el_mismo_umbral_que_la_regla():
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    hueco = r["out_of_sample_sharpe"] - r["equal_weight_sharpe"]
    assert r["beats_equal_weight"] is veredicto(hueco, r["gap_stderr"])


def test_el_resultado_dice_contra_que_umbral_se_juzgo():
    """La pantalla tiene que poder escribir el número, no reconstruirlo."""
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert r["umbral_veredicto"] == pytest.approx(2.0 * r["gap_stderr"])


# ── La barra de error del retorno esperado ────────────────────────────────────

def test_el_error_del_retorno_esperado_es_la_volatilidad_repartida_entre_los_anios():
    """SE(μ anual) = σ anual / √años, que es el mismo Lo de siempre sin el cociente."""
    assert retorno_stderr(0.25, n_periods=252, periods_per_year=252) == pytest.approx(0.25)
    assert retorno_stderr(0.25, n_periods=1008, periods_per_year=252) == pytest.approx(0.125)


def test_el_error_del_retorno_reproduce_el_ruido_que_dice_medir():
    """Monte Carlo: 4.000 muestras de dos años de retornos diarios."""
    rng = np.random.default_rng(3)
    vol_anual, n, ppy = 0.25, 504, 252
    muestras = rng.standard_normal((4000, n)) * (vol_anual / np.sqrt(ppy))
    empirico = float((muestras.mean(axis=1) * ppy).std(ddof=1))
    assert retorno_stderr(vol_anual, n, ppy) == pytest.approx(empirico, rel=0.05)


def test_medio_ano_de_datos_deja_el_retorno_esperado_sin_significado():
    """El caso de la pantalla: 28,76% esperado con ±15,64 pp de error.

    El intervalo al 95% va de -1,9% a 59,4%, y la pantalla escribía el 28,76%
    solo, con dos decimales, mientras sí ponía barra de error al Sharpe.
    """
    se = retorno_stderr(0.2482, n_periods=500, periods_per_year=252)
    assert se == pytest.approx(0.1762, abs=0.01)
    assert 0.2876 - 2 * se < 0


# ── La frase del veredicto la escribe quien lo dicta ──────────────────────────

def test_la_frase_dice_contra_que_umbral_se_juzga():
    frase = frase_veredicto(0.80, 0.30)
    assert "0,60" in frase, "no dice el listón que había que superar"
    assert "supera" in frase.lower()


def test_la_frase_del_empate_no_promete_nada():
    frase = frase_veredicto(0.40, 0.30)
    assert "no" in frase.lower()
    assert "0,60" in frase


def test_la_frase_de_la_derrota_tambien_lleva_su_umbral():
    frase = frase_veredicto(-0.80, 0.30)
    assert "0,60" in frase
    assert "debajo" in frase.lower()


def test_sin_veredicto_medible_la_frase_lo_dice_en_vez_de_inventar_un_numero():
    assert "sin" in frase_veredicto(0.5, float("inf")).lower()


def test_la_frase_concuerda_siempre_con_el_veredicto():
    for hueco in (-1.0, -0.61, -0.59, 0.0, 0.59, 0.61, 1.0):
        frase = frase_veredicto(hueco, 0.30).lower()
        estado = veredicto(hueco, 0.30)
        assert ("supera" in frase) is (estado is True)
        assert ("debajo" in frase) is (estado is False)


# ── La medida, sin repetir el veredicto ──────────────────────────────────────

def test_la_medida_no_repite_el_veredicto():
    """La pantalla del optimizador ya pone su propio titular en negrita.

    Con la frase entera detras, el usuario leia dos veces el mismo juicio:
    «Con estos datos no se puede distinguir la optimizacion de repartir por
    igual. Estos datos no distinguen esta cartera de repartir por igual: las
    separan...». La medida es la mitad que aporta algo nuevo.
    """
    for hueco in (0.80, 0.40, -0.80):
        medida = medida_veredicto(hueco, 0.30).lower()
        assert "supera" not in medida
        assert "debajo" not in medida
        assert "no distinguen" not in medida


def test_la_medida_lleva_el_hueco_y_el_liston():
    medida = medida_veredicto(0.40, 0.30)
    assert "0,40" in medida, "no dice cuanto separa a las dos"
    assert "0,60" in medida, "no dice el liston que habia que superar"
    assert "0,30" in medida, "no dice el error estandar del que sale el liston"


def test_la_frase_entera_contiene_su_medida():
    """Las dos salen de las mismas piezas: no pueden separarse con el tiempo."""
    for hueco in (0.80, 0.40, -0.80):
        assert medida_veredicto(hueco, 0.30) in frase_veredicto(hueco, 0.30)


def test_sin_error_medible_la_medida_tampoco_inventa_un_numero():
    assert "sin" in medida_veredicto(0.5, float("inf")).lower()


# ── La degradación resta dos números del mismo tipo ───────────────────────────

def test_la_degradacion_resta_medias_de_ventana_contra_medias_de_ventana():
    """Restaba el Sharpe AGRUPADO menos la media de cocientes: dos estimadores.

    En la pantalla salía «-0,57» donde quien leía 1,13 en muestra y 0,80 fuera
    esperaba -0,33, y ninguno de los dos números de la resta era el que tenía
    delante.
    """
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert r["degradation"] == pytest.approx(
        r["in_sample_sharpe"] - r["out_of_sample_sharpe_medio"]
    )


def test_el_sharpe_medio_por_ventana_se_publica_junto_al_agrupado():
    """Son dos estimadores del mismo número y la pantalla los enseña los dos."""
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert np.isfinite(r["out_of_sample_sharpe_medio"])
    assert r["out_of_sample_sharpe_medio"] != r["out_of_sample_sharpe"]


def test_el_agrupado_sigue_siendo_el_titular_y_el_que_lleva_barra_de_error():
    """El agrupado usa todas las observaciones a la vez: es el mejor estimador.

    La media de cocientes la domina la ventana más afortunada —1,206, 0,941,
    0,993 y 2,343 en el caso medido— y por eso no es la que se anuncia.
    """
    r = walk_forward_validation(_factor_market(2000), 0.0, 252, (0.0, 1.0), False)
    assert r["sharpe_stderr"] == sharpe_standard_error(
        r["out_of_sample_sharpe"], r["n_oos_periods"], 252
    )


def test_una_sola_ventana_hace_coincidir_los_dos_estimadores():
    """Con una ventana no hay promedio de cocientes que pueda separarse."""
    r = walk_forward_validation(
        _factor_market(600), 0.0, 252, (0.0, 1.0), False, train_size=500, test_size=100
    )
    assert r["n_windows"] == 1
    assert r["out_of_sample_sharpe_medio"] == pytest.approx(r["out_of_sample_sharpe"])
