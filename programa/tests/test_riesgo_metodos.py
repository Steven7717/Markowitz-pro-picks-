"""Los seis estimadores de VaR y ES contra su valor teórico.

Con una muestra grande de una distribución conocida, cada método que la
supone (o no supone nada) tiene que reproducir el cuantil y la media de cola
teóricos. Es la única forma de saber que la fórmula está bien escrita antes de
ponerla a competir: un ES mal derivado también puede caer en verde.
"""

import numpy as np
import pytest
from scipy import stats

from riesgo import metodos

SIGMA = 0.01
N = 200_000


@pytest.fixture(scope="module")
def normales():
    return np.random.default_rng(0).normal(0.0, SIGMA, N)


@pytest.fixture(scope="module")
def t5():
    # t de 5 grados escalada a desviación SIGMA.
    nu = 5
    return np.random.default_rng(1).standard_t(nu, N) * SIGMA * np.sqrt((nu - 2) / nu)


def _normal_teorico(alpha):
    z = stats.norm.ppf(1 - alpha)
    return -SIGMA * z, SIGMA * stats.norm.pdf(z) / (1 - alpha)


@pytest.mark.parametrize("clave", ["historico", "normal", "cornish_fisher", "t_student"])
@pytest.mark.parametrize("alpha", [0.99, 0.975])
def test_sobre_normales_todos_dan_el_valor_normal(normales, clave, alpha):
    var, es = metodos.METODOS[clave](normales, alpha)
    var_t, es_t = _normal_teorico(alpha)
    assert var == pytest.approx(var_t, rel=0.03)
    assert es == pytest.approx(es_t, rel=0.03)


def test_la_t_reproduce_el_cuantil_de_una_t(t5):
    nu = 5
    escala = SIGMA * np.sqrt((nu - 2) / nu)
    var, es = metodos.t_student(t5, 0.99)
    assert var == pytest.approx(-escala * stats.t.ppf(0.01, nu), rel=0.05)


def test_la_normal_se_queda_corta_en_una_t_y_la_historica_no(t5):
    nu = 5
    verdadero = -SIGMA * np.sqrt((nu - 2) / nu) * stats.t.ppf(0.01, nu)
    assert metodos.normal(t5, 0.99)[0] < verdadero * 0.97
    assert metodos.historico(t5, 0.99)[0] == pytest.approx(verdadero, rel=0.03)


@pytest.mark.parametrize("clave", list(metodos.METODOS))
@pytest.mark.parametrize("alpha", [0.99, 0.975])
def test_el_es_nunca_es_menor_que_el_var(t5, clave, alpha):
    var, es = metodos.METODOS[clave](t5[:500], alpha)
    assert es >= var > 0


def test_ewma_sube_despues_de_un_golpe():
    rng = np.random.default_rng(2)
    calma = rng.normal(0, 0.005, 500)
    golpe = calma.copy()
    golpe[-5:] = -0.05
    assert metodos.ewma(golpe, 0.99)[0] > 3 * metodos.ewma(calma, 0.99)[0]
    assert metodos.fhs(golpe, 0.99)[0] > 3 * metodos.fhs(calma, 0.99)[0]


def test_las_varianzas_ewma_siguen_la_recursion():
    r = np.array([0.01, -0.02, 0.03, 0.0] * 10)
    previas, siguiente = metodos._varianzas_ewma(r, 0.94)
    v = np.mean(r[:metodos._SEMILLA_EWMA] ** 2)
    esperadas = []
    for x in r:
        esperadas.append(v)
        v = 0.94 * v + 0.06 * x * x
    np.testing.assert_allclose(previas, esperadas)
    assert siguiente == pytest.approx(v)


def test_cada_clave_tiene_etiqueta():
    assert set(metodos.METODOS) == set(metodos.ETIQUETAS)


@pytest.mark.parametrize("clave", list(metodos.METODOS))
@pytest.mark.parametrize("alpha", [0.99, 0.975])
def test_ceros_al_principio_y_series_constantes_dan_numeros(clave, alpha):
    """Un activo que no cotiza en las primeras sesiones de la ventana no puede
    dar NaN (0/0 en la semilla EWMA, curtosis de una serie constante)."""
    ruido = np.random.default_rng(11).normal(0, 0.01, 460)
    for r in (np.concatenate([np.zeros(40), ruido]), np.zeros(500)):
        var, es = metodos.METODOS[clave](r, alpha)
        assert np.isfinite(var) and np.isfinite(es)


@pytest.mark.parametrize("alpha", [0.99, 0.975])
def test_los_momentos_a_mano_dan_lo_mismo_que_scipy(alpha):
    r = np.random.default_rng(12).standard_t(5, 500) * 0.01
    sesgo, exceso = metodos._sesgo_y_exceso(r)
    assert sesgo == pytest.approx(stats.skew(r))
    assert exceso == pytest.approx(stats.kurtosis(r))


# ── Cornish-Fisher dentro de su dominio (Maillard, 2012) ──────────────────────

def _cf_sin_proyectar(r, alpha):
    """La fórmula tal cual, con los momentos de la muestra: la de antes."""
    mu, s = r.mean(), r.std(ddof=1)
    sesgo, exceso = metodos._sesgo_y_exceso(r)
    z, _ = metodos._normal_cola(alpha)
    q = (z + (z * z - 1) * sesgo / 6 + (z**3 - 3 * z) * exceso / 24
         - (2 * z**3 - 5 * z) * sesgo * sesgo / 36)
    m1, m2, m3, m4 = metodos._momentos_cola_cf(alpha)
    q_cola = m1 + m2 * sesgo / 6 + m3 * exceso / 24 - m4 * sesgo * sesgo / 36
    var = -(mu + s * q)
    return float(var), float(max(-(mu + s * q_cola), var))


def _fuera_del_dominio(s, k):
    return s * s / 9 - 4 * (k / 8 - s * s / 6) * (1 - k / 8 - 5 * s * s / 36)


def _como_la_cartera_real():
    """El perfil de la max-Sharpe real (AAPL+NVDA): una t de colas gruesas y
    tres subidas enormes. Sesgo ≈ +1 y exceso ≈ 17, puestos por la cola de la
    derecha; la izquierda, la que mide el VaR, es moderada."""
    g = np.random.default_rng(3)
    r = g.standard_t(5, 500) * 0.015 * np.sqrt(3 / 5)
    r[g.choice(500, 3, replace=False)] = [0.10, 0.12, 0.14]
    return r


def test_con_colas_gruesas_cornish_fisher_no_se_dispara():
    r = _como_la_cartera_real()
    sesgo, exceso = metodos._sesgo_y_exceso(r)
    assert 0.9 < sesgo < 1.2 and exceso > 14          # el caso que se pretende
    historica = metodos.historico(r, 0.99)[0]
    assert _cf_sin_proyectar(r, 0.99)[0] > 1.3 * historica   # el test muerde...
    assert metodos.cornish_fisher(r, 0.99)[0] <= 1.3 * historica  # ...y pasa


@pytest.mark.parametrize("muestra", ["normal", "t8"])
@pytest.mark.parametrize("alpha", [0.99, 0.975])
def test_dentro_del_dominio_no_cambia_nada(muestra, alpha):
    g = np.random.default_rng(22)
    r = (g.normal(0, 0.01, 5000) if muestra == "normal"
         else g.standard_t(8, 5000) * 0.01)
    momentos = metodos._sesgo_y_exceso(r)
    assert _fuera_del_dominio(*momentos) <= 0          # la premisa del test
    assert metodos._proyectar_cf(*momentos) == momentos
    assert metodos.cornish_fisher(r, alpha) == _cf_sin_proyectar(r, alpha)


@pytest.mark.parametrize("semilla", range(6))
def test_a_una_normal_el_borde_de_abajo_casi_no_la_toca(semilla):
    """Media muestra normal cae con K un pelo por debajo de 0, fuera del
    dominio por el borde de abajo, y subirla al suelo (≈ 0) la mueve. Poco con
    5.000 datos (máximo 4,2 % en 400 muestras). Con las 500 sesiones del
    backtest se mueven seis de cada diez ventanas, hasta un 12,5 % en el VaR
    99 %, y el error medio contra el normal teórico apenas cambia (3,9 % con
    proyección, 4,1 % sin ella). Es ruido de curtosis, no información."""
    r = np.random.default_rng(semilla).normal(0, 0.01, 5000)
    for alpha in (0.99, 0.975):
        nuevo, viejo = metodos.cornish_fisher(r, alpha), _cf_sin_proyectar(r, alpha)
        assert nuevo == pytest.approx(viejo, rel=0.05)


@pytest.mark.parametrize("sesgo", [-3.0, -1.0, -0.4, 0.0, 0.5, 0.98, 2.5])
@pytest.mark.parametrize("exceso", [0.0, 3.0, 6.0, 14.8, 40.0])
def test_lo_proyectado_cumple_la_condicion_de_monotonia(sesgo, exceso):
    s, k = metodos._proyectar_cf(sesgo, exceso)
    assert abs(s) <= metodos._SESGO_MAX_CF
    assert _fuera_del_dominio(s, k) <= 1e-12
