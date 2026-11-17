"""Seis maneras de estimar el VaR y el ES de una serie de retornos diarios.

Todas reciben la ventana de retornos pasados `r` y el nivel de confianza
`alpha` (0,99 para el VaR de Basilea, 0,975 para el ES de FRTB) y devuelven
`(VaR, ES)` como **pérdidas positivas**, en fracción del valor: un VaR de 0,023
es «un 2,3 % en un mal día». Así cualquiera de ellas entra en el mismo backtest
y la competencia es justa.
"""

from functools import lru_cache

import numpy as np
from scipy import stats
from scipy.signal import lfilter
from scipy.special import gammaln, stdtrit

LAMBDA_EWMA = 0.94
# Con cuántas observaciones se siembra la recursión EWMA. Sembrar con la
# primera al cuadrado haría depender el arranque de un solo día.
_SEMILLA_EWMA = 30
# Puntos con los que se integra la cola de Cornish-Fisher para su ES.
_PUNTOS_COLA = 200
# Techo de |asimetría| con el que entra Cornish-Fisher. El dominio en que la
# expansión es un cuantil válido se estrecha deprisa con el sesgo (Maillard,
# 2012) y, pasado |S| ≈ 1, lo que queda de curtosis admisible ya no describe
# una serie de retornos diaria: se recorta el sesgo antes de proyectar.
_SESGO_MAX_CF = 1.0
# ν por momentos: la curtosis de una t sólo existe por encima de 4. El techo es
# 100 y no 30: una muestra normal de 200.000 puntos tiene exceso de curtosis
# ≈ 0,008 (ν ≈ 760), y recortarla a 30 inflaba el ES al 99 % un 4 % sobre la
# normal; con 100 la t ya es normal a efectos prácticos (≈ 1 %).
_NU_MIN, _NU_MAX = 4.1, 100.0
# Suelo de la varianza EWMA (σ = 1e-6, mil veces por debajo de un retorno
# diario normal): si la semilla es 0 (activo parado al principio de la
# ventana) r/σ sería 0/0.
_VARIANZA_MIN = 1e-12


@lru_cache(maxsize=None)
def _normal_cola(alpha: float) -> tuple[float, float]:
    """z = Φ⁻¹(1−α) y φ(z): sólo dependen de alpha, no de la ventana."""
    z = float(stats.norm.ppf(1 - alpha))
    return z, float(stats.norm.pdf(z))


@lru_cache(maxsize=None)
def _momentos_cola_cf(alpha: float) -> tuple[float, float, float, float]:
    """Medias, sobre la rejilla de la cola, de los cuatro polinomios de z del
    cuantil de Cornish-Fisher. El cuantil es lineal en (1, sesgo, exceso,
    sesgo²), así que su media sobre la cola se saca con estas cuatro."""
    niveles = (np.arange(_PUNTOS_COLA) + 0.5) / _PUNTOS_COLA * (1 - alpha)
    z = stats.norm.ppf(niveles)
    return (float(z.mean()), float((z * z - 1).mean()),
            float((z**3 - 3 * z).mean()), float((2 * z**3 - 5 * z).mean()))


def _sesgo_y_exceso(r: np.ndarray) -> tuple[float, float]:
    """Asimetría y exceso de curtosis poblacionales (los de scipy por defecto),
    con momentos de numpy. Una serie constante no tiene forma: (0, 0)."""
    d = r - r.mean()
    m2 = float(np.mean(d * d))
    if m2 <= 0.0:
        return 0.0, 0.0
    return float(np.mean(d**3) / m2**1.5), float(np.mean(d**4) / (m2 * m2) - 3.0)


def historico(r: np.ndarray, alpha: float) -> tuple[float, float]:
    q = np.quantile(r, 1 - alpha)
    return float(-q), float(-r[r <= q].mean())


def normal(r: np.ndarray, alpha: float) -> tuple[float, float]:
    mu, sigma = r.mean(), r.std(ddof=1)
    z, pdf = _normal_cola(alpha)
    return float(-(mu + sigma * z)), float(-mu + sigma * pdf / (1 - alpha))


def t_student(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """t con ν por momentos: exceso de curtosis = 6/(ν−4).

    Por máxima verosimilitud serían cientos de ajustes por backtest; por
    momentos es una cuenta, y la diferencia en el cuantil al 99 % es menor que
    el error de muestreo de una ventana de 500 días.
    """
    mu, s = r.mean(), r.std(ddof=1)
    _, exceso = _sesgo_y_exceso(r)
    nu = _NU_MAX if exceso <= 0 else float(np.clip(4 + 6 / exceso, _NU_MIN, _NU_MAX))
    escala = s * np.sqrt((nu - 2) / nu)
    # stdtrit y la densidad a mano: lo mismo que stats.t.ppf/pdf sin el
    # envoltorio de rv_continuous, que domina el coste del backtest.
    q = float(stdtrit(nu, 1 - alpha))
    pdf = np.exp(gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log(nu * np.pi)
                 - (nu + 1) / 2 * np.log1p(q * q / nu))
    var = -(mu + escala * q)
    es = -mu + escala * pdf / (1 - alpha) * (nu + q * q) / (nu - 1)
    return float(var), float(es)


def _varianzas_ewma(r: np.ndarray, lam: float = LAMBDA_EWMA) -> tuple[np.ndarray, float]:
    """La varianza prevista para cada `r[i]` y la de mañana.

    σ²ₜ = λ·σ²ₜ₋₁ + (1−λ)·r²ₜ₋₁, con `lfilter` en vez de un bucle: el backtest
    la llama cientos de veces.
    """
    # La semilla usa r[:30] de la propia ventana: es información pasada para
    # el pronóstico de mañana, sólo «mira hacia delante» dentro de la ventana
    # (en la muestra) y no se filtra al día pronosticado.
    semilla = max(float(np.mean(r[:_SEMILLA_EWMA] ** 2)), _VARIANZA_MIN)
    despues, _ = lfilter([1 - lam], [1, -lam], r**2, zi=[lam * semilla])
    previas = np.maximum(np.concatenate([[semilla], despues[:-1]]), _VARIANZA_MIN)
    return previas, max(float(despues[-1]), _VARIANZA_MIN)


def ewma(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Normal de media cero con la volatilidad de mañana según RiskMetrics."""
    _, varianza = _varianzas_ewma(r)
    sigma = np.sqrt(varianza)
    z, pdf = _normal_cola(alpha)
    return float(-sigma * z), float(sigma * pdf / (1 - alpha))


def fhs(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Histórica filtrada: la forma de la cola de los datos, la escala de hoy."""
    previas, varianza = _varianzas_ewma(r)
    z = r / np.sqrt(previas)
    q = np.quantile(z, 1 - alpha)
    sigma = np.sqrt(varianza)
    return float(-sigma * q), float(-sigma * z[z <= q].mean())


def _proyectar_cf(sesgo: float, exceso: float) -> tuple[float, float]:
    """Lleva (S, K) al dominio en que la expansión de Cornish-Fisher es monótona.

    Fuera de él la «cuantil» de Cornish-Fisher no es un cuantil: deja de crecer
    con z y la cola se dispara. Sobre la cartera real (S ≈ +1, K ≈ 15) daba un
    VaR 99 % de 8,6 % donde la histórica, la t y la FHS daban ≈ 5 %, y ganaba
    el backtest sólo por pasarse de conservadora. Maillard (2012, «A User's
    Guide to the Cornish Fisher Expansion») da la condición de monotonía:

        S²/9 − 4·(K/8 − S²/6)·(1 − K/8 − 5S²/36) ≤ 0

    Con a = K/8 la condición es una cuadrática en a: para cada S, K válido es
    un intervalo [K_min, K_max] con forma cerrada. Se conserva el sesgo
    (recortado a ±_SESGO_MAX_CF) y se lleva K al intervalo: casi siempre es
    bajarla hasta K_max, que es lo que hace la cola real. El borde de abajo
    también cuenta: con S ≈ 1 y K pequeña la expansión ya no es monótona en
    z = −2,33, justo el 99 %. Con S ≈ 0 ese borde es K ≈ 0, así que a una
    muestra normal sólo le mueve una curtosis de ruido.
    """
    s = float(np.clip(sesgo, -_SESGO_MAX_CF, _SESGO_MAX_CF))
    s2 = s * s
    p, q = s2 / 6, 1 - 5 * s2 / 36
    # (a − p)(q − a) ≥ s²/36  ⇔  a entre las dos raíces. Con |S| ≤ 1 el
    # discriminante es ≥ 0,37: las raíces existen siempre.
    raiz = np.sqrt((q - p) ** 2 - s2 / 9)
    suelo, techo = 4 * (p + q - raiz), 4 * (p + q + raiz)
    return s, float(min(max(exceso, suelo), techo))


def cornish_fisher(r: np.ndarray, alpha: float) -> tuple[float, float]:
    mu, s = r.mean(), r.std(ddof=1)
    sesgo, exceso = _proyectar_cf(*_sesgo_y_exceso(r))
    z, _ = _normal_cola(alpha)
    q = (z + (z * z - 1) * sesgo / 6 + (z**3 - 3 * z) * exceso / 24
         - (2 * z**3 - 5 * z) * sesgo * sesgo / 36)
    var = -(mu + s * q)
    m1, m2, m3, m4 = _momentos_cola_cf(alpha)
    q_cola = m1 + m2 * sesgo / 6 + m3 * exceso / 24 - m4 * sesgo * sesgo / 36
    es = -(mu + s * q_cola)
    # Ya dentro del dominio de monotonía no debería pasar, pero el ES integrado
    # por la rejilla nunca puede quedar por debajo del VaR. Se acota.
    return float(var), float(max(es, var))


METODOS = {
    "historico": historico,
    "normal": normal,
    "t_student": t_student,
    "ewma": ewma,
    "fhs": fhs,
    "cornish_fisher": cornish_fisher,
}

ETIQUETAS = {
    "historico": "Simulación histórica",
    "normal": "Paramétrico normal",
    "t_student": "t de Student",
    "ewma": "EWMA (RiskMetrics)",
    "fhs": "Histórica filtrada (EWMA)",
    "cornish_fisher": "Cornish-Fisher",
}
