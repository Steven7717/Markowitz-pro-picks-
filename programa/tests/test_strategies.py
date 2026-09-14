import numpy as np
import pandas as pd
import pytest

from optimizer import (
    STRATEGY_LABELS,
    equal_weight_portfolio,
    optimize_max_sharpe,
    optimize_min_variance,
    optimize_portfolio,
    optimize_risk_parity,
    risk_contribution,
)

PPY = 252
RF = 0.0


@pytest.fixture
def market() -> pd.DataFrame:
    """Correlated assets with clearly different volatilities."""
    rng = np.random.default_rng(31)
    n_obs, n_assets = 800, 5
    betas = np.linspace(0.5, 1.8, n_assets)
    idio = np.linspace(0.006, 0.024, n_assets)
    factor = rng.normal(0.0005, 0.010, size=(n_obs, 1))
    data = factor @ betas.reshape(1, -1) + rng.normal(0, 1, (n_obs, n_assets)) * idio
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


@pytest.fixture
def uncorrelated() -> pd.DataFrame:
    """Independent assets with volatilities in a 1:2:4:8 ratio."""
    rng = np.random.default_rng(5)
    vols = np.array([0.005, 0.010, 0.020, 0.040])
    return pd.DataFrame(
        rng.normal(0, 1, (4000, 4)) * vols, columns=list("PQRS")
    )


def _shift_means(returns: pd.DataFrame) -> pd.DataFrame:
    """Change every expected return while leaving the covariance untouched."""
    bumps = np.linspace(-0.004, 0.004, returns.shape[1])
    return returns + bumps


# ── Minimum variance ──────────────────────────────────────────────────────────

def test_min_variance_beats_equal_weight_on_volatility(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    ew = equal_weight_portfolio(market, RF, PPY)
    assert mv["annual_vol"] < ew["annual_vol"]


def test_min_variance_has_the_lowest_volatility_of_all_strategies(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    for other in (
        optimize_max_sharpe(market, RF, PPY, (0.0, 1.0), False),
        optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False),
        equal_weight_portfolio(market, RF, PPY),
    ):
        assert mv["annual_vol"] <= other["annual_vol"] + 1e-9


def test_min_variance_completely_ignores_expected_returns(market):
    """This is why it is robust: the noisiest input is never consulted."""
    base = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    bumped = optimize_min_variance(_shift_means(market), RF, PPY, (0.0, 1.0), False)
    assert np.allclose(base["weights"], bumped["weights"], atol=1e-4)


def test_min_variance_matches_the_closed_form_when_unconstrained(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), allow_short=True)
    inv = np.linalg.inv(market.cov().values)
    ones = np.ones(market.shape[1])
    closed_form = inv @ ones / (ones @ inv @ ones)
    assert np.allclose(mv["weights"], closed_form, atol=1e-3)


def test_min_variance_respects_weight_bounds(market):
    mv = optimize_min_variance(market, RF, PPY, (0.10, 0.30), False)
    assert mv["weights"].min() >= 0.10 - 1e-6
    assert mv["weights"].max() <= 0.30 + 1e-6


def test_min_variance_weights_sum_to_one(market):
    mv = optimize_min_variance(market, RF, PPY, (0.0, 1.0), False)
    assert abs(mv["weights"].sum() - 1.0) < 1e-6


# ── Risk parity (equal risk contribution) ─────────────────────────────────────

def test_risk_parity_equalises_every_risk_contribution(market):
    """The defining property: each asset supplies the same share of portfolio risk."""
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    contributions = risk_contribution(rp["weights"], market.cov().values)
    assert np.allclose(contributions, 1.0 / market.shape[1], atol=1e-3)


def test_risk_parity_is_more_balanced_than_equal_weight(market):
    """Equal money is not equal risk when volatilities differ."""
    ew_contrib = risk_contribution(np.ones(5) / 5, market.cov().values)
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    rp_contrib = risk_contribution(rp["weights"], market.cov().values)
    assert rp_contrib.std() < ew_contrib.std()


def test_risk_parity_gives_more_weight_to_calmer_assets(uncorrelated):
    rp = optimize_risk_parity(uncorrelated, RF, PPY, (0.0, 1.0), False)
    w = rp["weights"]
    assert all(w[i] > w[i + 1] for i in range(len(w) - 1))


def test_risk_parity_is_inverse_volatility_when_assets_are_uncorrelated(uncorrelated):
    """With zero correlation the analytic answer is w proportional to 1/sigma."""
    rp = optimize_risk_parity(uncorrelated, RF, PPY, (0.0, 1.0), False)
    inv_vol = 1.0 / uncorrelated.std().values
    expected = inv_vol / inv_vol.sum()
    assert np.allclose(rp["weights"], expected, atol=0.02)


def test_risk_parity_completely_ignores_expected_returns(market):
    base = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    bumped = optimize_risk_parity(_shift_means(market), RF, PPY, (0.0, 1.0), False)
    assert np.allclose(base["weights"], bumped["weights"], atol=1e-4)


def test_risk_parity_never_takes_short_positions(market):
    """Equal risk contribution is undefined for negative weights."""
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), allow_short=True)
    assert rp["weights"].min() >= 0.0


def test_risk_parity_respects_weight_bounds(market):
    rp = optimize_risk_parity(market, RF, PPY, (0.15, 0.25), False)
    assert rp["weights"].min() >= 0.15 - 1e-6
    assert rp["weights"].max() <= 0.25 + 1e-6


# ── Common interface ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_returns_the_same_result_shape(market, strategy):
    result = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=strategy)
    for key in ("converged", "weights", "annual_return", "annual_vol", "sharpe",
                "risk_contribution", "cov_shrinkage", "mean_shrinkage"):
        assert key in result, f"{strategy} is missing '{key}'"


@pytest.mark.parametrize("strategy", ["max_sharpe", "min_variance", "risk_parity"])
def test_every_strategy_produces_a_valid_portfolio(market, strategy):
    result = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=strategy)
    assert result["converged"]
    assert abs(result["weights"].sum() - 1.0) < 1e-6


def test_max_sharpe_still_has_the_highest_in_sample_sharpe(market):
    """Each strategy should win on the metric it actually optimises."""
    best = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy="max_sharpe")
    for other in ("min_variance", "risk_parity"):
        rival = optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy=other)
        assert best["sharpe"] >= rival["sharpe"] - 1e-6


def test_unknown_strategy_is_rejected(market):
    with pytest.raises(ValueError, match="desconocida"):
        optimize_portfolio(market, RF, PPY, (0.0, 1.0), False, strategy="martingala")


def test_every_strategy_has_a_label_for_the_interface():
    assert set(STRATEGY_LABELS) == {"max_sharpe", "min_variance", "risk_parity"}


def test_strategies_accept_shrinkage(market):
    for strategy in ("min_variance", "risk_parity"):
        result = optimize_portfolio(
            market, RF, PPY, (0.0, 1.0), False, strategy=strategy, shrinkage=True
        )
        assert result["cov_shrinkage"] > 0.0


# ── Mercado bajista: nadie supera la tasa libre de riesgo ─────────────────────
#
# El hueco que dejó pasar el defecto: TODOS los tests de arriba usan `RF = 0` y
# fixtures con deriva positiva, así que el numerador del Sharpe nunca llegaba a
# ser negativo y la patología no podía aparecer. Aquí la tasa libre de riesgo es
# real y la deriva es la de 2022.

RF_REAL = 0.04 / PPY


def _bajista(
    medias: tuple[float, ...] = (-0.10, -0.12, -0.08),
    vols: tuple[float, ...] = (0.15, 0.24, 0.46),
    nombres: tuple[str, ...] = ("defensivo", "medio", "volatil"),
    n_obs: int = 500,
    seed: int = 7,
) -> pd.DataFrame:
    """Un mercado donde ningún activo renta lo que rentan las letras del Tesoro.

    Las medias y las volatilidades **muestrales** se fijan exactamente a lo
    pedido: lo que se está probando es cómo decide el optimizador dados unos
    momentos, no si un generador aleatorio los reproduce.
    """
    rng = np.random.default_rng(seed)
    mu = np.array(medias) / PPY
    sigma = np.array(vols) / np.sqrt(PPY)
    datos = rng.standard_normal((n_obs, len(medias)))
    datos = datos - datos.mean(axis=0)
    datos = datos / datos.std(axis=0, ddof=1) * sigma + mu
    return pd.DataFrame(datos, columns=list(nombres))


def test_max_sharpe_no_se_lleva_el_activo_mas_volatil_en_mercado_bajista():
    """El defecto crítico: con el exceso negativo, maximizar S maximiza la vol.

    Con todos los excesos esperados por debajo de cero, agrandar el denominador
    acerca un número negativo a cero, así que el cociente premia exactamente lo
    que debería penalizar. La aplicación entregaba el activo más volátil al
    100%, convergido y sin un aviso.
    """
    resultado = optimize_max_sharpe(_bajista(), RF_REAL, PPY, (0.0, 1.0), False)
    assert resultado["converged"]
    assert resultado["weights"][2] < 0.5, "se va entero al activo más volátil"
    assert resultado["annual_vol"] < 0.25, "la cartera hereda la volatilidad del peor"


def test_max_sharpe_descarta_al_mas_volatil_aunque_sea_el_que_menos_pierde():
    """El caso que ningún criterio sensato podría defender.

    Aquí el activo más volátil es además el que peor renta: pierde más y tiembla
    más. El cociente de Sharpe seguía prefiriéndolo —-0,16/0,46 = -0,35 contra
    -0,12/0,15 = -0,80— porque sólo mira el cociente.
    """
    mercado = _bajista(medias=(-0.08, -0.10, -0.12), vols=(0.15, 0.24, 0.46))
    resultado = optimize_max_sharpe(mercado, RF_REAL, PPY, (0.0, 1.0), False)
    assert resultado["weights"][2] < 0.10
    assert resultado["weights"][0] > 0.50


def test_max_sharpe_avisa_de_que_en_este_regimen_no_hay_prima_que_maximizar():
    """No basta con elegir mejor: hay que decir que el criterio cambió."""
    resultado = optimize_max_sharpe(_bajista(), RF_REAL, PPY, (0.0, 1.0), False)
    assert resultado["sin_prima"] is True
    assert "libre de riesgo" in resultado["message"].lower()


def test_a_igualdad_de_perdida_esperada_se_queda_con_la_cartera_mas_tranquila():
    mercado = _bajista(
        medias=(-0.10, -0.10), vols=(0.14, 0.40), nombres=("tranquilo", "nervioso")
    )
    resultado = optimize_max_sharpe(mercado, RF_REAL, PPY, (0.0, 1.0), False)
    assert resultado["weights"][0] > resultado["weights"][1]


def test_una_tasa_libre_de_riesgo_positiva_basta_para_entrar_en_el_regimen():
    """Con rf = 0 la deriva del 2% parece prima; con rf = 4% no lo es.

    Es literalmente el hueco de la suite: el mismo mercado, la misma
    optimización, y sólo cambia la tasa contra la que se compara.
    """
    mercado = _bajista(medias=(0.02, 0.01, 0.03), vols=(0.15, 0.24, 0.46))
    assert optimize_max_sharpe(mercado, 0.0, PPY, (0.0, 1.0), False)["sin_prima"] is False
    caro = optimize_max_sharpe(mercado, RF_REAL, PPY, (0.0, 1.0), False)
    assert caro["sin_prima"] is True
    assert caro["weights"][2] < 0.5


def test_en_un_mercado_normal_el_criterio_no_cambia(market):
    """La corrección no puede tocar el caso de siempre.

    Mientras exista una cartera factible con exceso positivo, el criterio de
    Israelsen coincide con el cociente de Sharpe —cualquier cartera con exceso
    negativo puntúa por debajo de cero y ninguna positiva lo hace— así que el
    óptimo es el mismo de antes.
    """
    resultado = optimize_max_sharpe(market, RF, PPY, (0.0, 1.0), False)
    assert resultado["sin_prima"] is False
    ew = equal_weight_portfolio(market, RF, PPY)
    assert resultado["sharpe"] >= ew["sharpe"] - 1e-9


def test_el_aviso_de_regimen_viaja_por_la_interfaz_comun():
    resultado = optimize_portfolio(
        _bajista(), RF_REAL, PPY, (0.0, 1.0), False, strategy="max_sharpe"
    )
    assert resultado["sin_prima"] is True


# ── Paridad de riesgo: «convergido» tiene que significar que iguala ───────────
#
# `optimize_risk_parity` arrancaba de un único punto sobre un objetivo que no es
# convexo, aceptaba cualquier `success` de SLSQP y no miraba nunca el resultado.
# `optimize_max_sharpe` usa 17 arranques justo por ese motivo. Con el tope del
# 30% por defecto, 11 de 40 carteras de cinco activos salían desiguales y la
# pantalla las llamaba «paridad de riesgo» igual.


def _dispares(
    vols: tuple[float, ...] = (0.08, 0.10, 0.55),
    n_obs: int = 500,
    rho: float = 0.2,
    seed: int = 3,
) -> pd.DataFrame:
    """Activos con volatilidades muy distintas y una correlación suave."""
    k = len(vols)
    rng = np.random.default_rng(seed)
    corr = np.full((k, k), rho)
    np.fill_diagonal(corr, 1.0)
    z = rng.standard_normal((n_obs, k)) @ np.linalg.cholesky(corr).T
    z = (z - z.mean(0)) / z.std(0, ddof=1) * (np.array(vols) / np.sqrt(PPY))
    return pd.DataFrame(z, columns=[f"A{i}" for i in range(k)])


def test_paridad_de_riesgo_dice_cuando_ha_igualado_de_verdad(market):
    rp = optimize_risk_parity(market, RF, PPY, (0.0, 1.0), False)
    assert rp["erc_exacto"] is True
    assert rp["erc_desviacion"] < 0.01


def test_el_tope_puede_hacer_imposible_la_paridad_y_hay_que_decirlo():
    """Tres activos dispares con tope del 34%: no hay cartera que iguale.

    El tope encierra los pesos en [0.32, 0.34] —casi reparto por igual— y ahí el
    activo volátil aporta el 88% del riesgo. Es infactible, no un fallo del
    ajuste, y la diferencia importa: al usuario hay que decirle que afloje el
    tope, no que vuelva a intentarlo.
    """
    rp = optimize_risk_parity(_dispares(), RF, PPY, (0.0, 0.34), False)
    assert rp["converged"] is True
    assert rp["erc_exacto"] is False
    assert rp["erc_desviacion"] > 0.10
    # Y el mensaje manda a mover el deslizador que de verdad estorba.
    assert "peso máximo" in rp["message"].lower()
    assert "sube el peso máximo" in rp["message"].lower()


def test_el_tope_imposible_no_se_disfraza_de_fallo_de_convergencia():
    """`converged=False` haría que el walk-forward tirase la ventana entera.

    Y con el tope del 30% por defecto la tiraría casi siempre, que es peor que
    enseñar una cartera imperfecta explicando en qué lo es.
    """
    rp = optimize_risk_parity(_dispares(), RF, PPY, (0.0, 0.34), False)
    assert rp["converged"] is True
    assert "weights" in rp and abs(rp["weights"].sum() - 1.0) < 1e-6


def test_la_desviacion_es_la_peor_contribucion_contra_su_objetivo():
    rp = optimize_risk_parity(_dispares(), RF, PPY, (0.0, 0.34), False)
    contribuciones = rp["risk_contribution"]
    peor = float(np.max(np.abs(contribuciones - 1.0 / len(contribuciones))))
    assert rp["erc_desviacion"] == pytest.approx(peor, abs=1e-9)


def test_un_solo_arranque_deja_a_un_activo_sin_riesgo_y_hay_que_reintentar():
    """Ocho activos sin ningún tope: el óptimo existe y SLSQP no lo encontraba.

    Desde el reparto por igual el ajuste se quedaba parado con un activo en el
    0% de la varianza —una desviación de 0,125, que es el objetivo entero— y
    devolvía «convergido». Aquí no hay tope que culpar: es el arranque.
    """
    rng = np.random.default_rng(0)
    k = 8
    vols = rng.uniform(0.05, 0.70, k)
    betas = rng.uniform(-0.2, 2.0, k)
    factor = rng.normal(0, 0.012, (700, 1))
    datos = pd.DataFrame(
        factor @ betas.reshape(1, -1) + rng.standard_normal((700, k)) * (vols / np.sqrt(250)),
        columns=[f"A{i}" for i in range(k)],
    )
    rp = optimize_risk_parity(datos, RF, 250, (0.0, 1.0), False)
    assert rp["converged"] is True
    assert rp["erc_exacto"] is True, "sigue parado en un óptimo local"
    assert rp["erc_desviacion"] < 0.01


def test_con_tope_del_30_por_ciento_ninguna_cartera_miente_sobre_su_paridad():
    """Las 40 carteras de cinco activos del informe, ahora etiquetadas.

    No se exige que todas igualen —con el tope del 30% muchas no pueden— sino
    que ninguna diga que iguala sin igualar.
    """
    for semilla in range(40):
        rng = np.random.default_rng(semilla)
        k = 5
        vols = rng.uniform(0.08, 0.55, k)
        betas = rng.uniform(0.3, 1.8, k)
        factor = rng.normal(0, 0.010, (600, 1))
        datos = pd.DataFrame(
            factor @ betas.reshape(1, -1) + rng.standard_normal((600, k)) * (vols / np.sqrt(PPY)),
            columns=[f"A{i}" for i in range(k)],
        )
        rp = optimize_risk_parity(datos, RF, PPY, (0.0, 0.30), False)
        if not rp["converged"]:
            continue
        desigual = float(np.max(np.abs(rp["risk_contribution"] - 1.0 / k))) > 0.01
        assert rp["erc_exacto"] is not desigual, f"semilla {semilla} se etiqueta mal"


def test_el_aviso_de_paridad_viaja_por_la_interfaz_comun():
    rp = optimize_portfolio(
        _dispares(), RF, PPY, (0.0, 0.34), False, strategy="risk_parity"
    )
    assert rp["erc_exacto"] is False
