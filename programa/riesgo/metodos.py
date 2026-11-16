"""Seis maneras de estimar el VaR y el ES de una serie de retornos diarios.

Todas reciben la ventana de retornos pasados `r` y el nivel de confianza
`alpha` (0,99 para el VaR de Basilea, 0,975 para el ES de FRTB) y devuelven
`(VaR, ES)` como **pérdidas positivas**, en fracción del valor: un VaR de 0,023
es «un 2,3 % en un mal día». Así cualquiera de ellas entra en el mismo backtest
y la competencia es justa.
"""

import numpy as np
from scipy import stats
from scipy.signal import lfilter

LAMBDA_EWMA = 0.94
# Con cuántas observaciones se siembra la recursión EWMA. Sembrar con la
# primera al cuadrado haría depender el arranque de un solo día.
_SEMILLA_EWMA = 30
# Puntos con los que se integra la cola de Cornish-Fisher para su ES.
_PUNTOS_COLA = 200
# ν por momentos: la curtosis de una t sólo existe por encima de 4. El techo es
# 100 y no 30: una muestra normal de 200.000 puntos tiene exceso de curtosis
# ≈ 0,008 (ν ≈ 760), y recortarla a 30 inflaba el ES al 99 % un 4 % sobre la
# normal; con 100 la t ya es normal a efectos prácticos (≈ 1 %).
_NU_MIN, _NU_MAX = 4.1, 100.0


def historico(r: np.ndarray, alpha: float) -> tuple[float, float]:
    q = np.quantile(r, 1 - alpha)
    return float(-q), float(-r[r <= q].mean())


def normal(r: np.ndarray, alpha: float) -> tuple[float, float]:
    mu, sigma = r.mean(), r.std(ddof=1)
    z = stats.norm.ppf(1 - alpha)
    return float(-(mu + sigma * z)), float(-mu + sigma * stats.norm.pdf(z) / (1 - alpha))


def t_student(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """t con ν por momentos: exceso de curtosis = 6/(ν−4).

    Por máxima verosimilitud serían cientos de ajustes por backtest; por
    momentos es una cuenta, y la diferencia en el cuantil al 99 % es menor que
    el error de muestreo de una ventana de 500 días.
    """
    mu, s = r.mean(), r.std(ddof=1)
    exceso = stats.kurtosis(r)
    nu = _NU_MAX if exceso <= 0 else float(np.clip(4 + 6 / exceso, _NU_MIN, _NU_MAX))
    escala = s * np.sqrt((nu - 2) / nu)
    q = stats.t.ppf(1 - alpha, nu)
    var = -(mu + escala * q)
    es = -mu + escala * stats.t.pdf(q, nu) / (1 - alpha) * (nu + q * q) / (nu - 1)
    return float(var), float(es)


def _varianzas_ewma(r: np.ndarray, lam: float = LAMBDA_EWMA) -> tuple[np.ndarray, float]:
    """La varianza prevista para cada `r[i]` y la de mañana.

    σ²ₜ = λ·σ²ₜ₋₁ + (1−λ)·r²ₜ₋₁, con `lfilter` en vez de un bucle: el backtest
    la llama cientos de veces.
    """
    semilla = float(np.mean(r[:_SEMILLA_EWMA] ** 2))
    despues, _ = lfilter([1 - lam], [1, -lam], r**2, zi=[lam * semilla])
    previas = np.concatenate([[semilla], despues[:-1]])
    return previas, float(despues[-1])


def ewma(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Normal de media cero con la volatilidad de mañana según RiskMetrics."""
    _, varianza = _varianzas_ewma(r)
    sigma = np.sqrt(varianza)
    z = stats.norm.ppf(1 - alpha)
    return float(-sigma * z), float(sigma * stats.norm.pdf(z) / (1 - alpha))


def fhs(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Histórica filtrada: la forma de la cola de los datos, la escala de hoy."""
    previas, varianza = _varianzas_ewma(r)
    z = r / np.sqrt(previas)
    q = np.quantile(z, 1 - alpha)
    sigma = np.sqrt(varianza)
    return float(-sigma * q), float(-sigma * z[z <= q].mean())


def cornish_fisher(r: np.ndarray, alpha: float) -> tuple[float, float]:
    mu, s = r.mean(), r.std(ddof=1)
    sesgo, exceso = stats.skew(r), stats.kurtosis(r)

    def cuantil(p):
        z = stats.norm.ppf(p)
        return (z + (z * z - 1) * sesgo / 6 + (z**3 - 3 * z) * exceso / 24
                - (2 * z**3 - 5 * z) * sesgo * sesgo / 36)

    var = -(mu + s * cuantil(1 - alpha))
    niveles = (np.arange(_PUNTOS_COLA) + 0.5) / _PUNTOS_COLA * (1 - alpha)
    es = -(mu + s * cuantil(niveles).mean())
    # Con curtosis muy alta la expansión deja de ser monótona y el ES integrado
    # puede quedar por debajo del VaR, que es imposible. Se acota.
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
