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
