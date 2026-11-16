# programa/riesgo/backtest.py
"""El semáforo de Basilea y la competencia entre métodos.

Una **excepción** es un día en que la pérdida real supera el VaR al 99 % que
se había previsto la víspera. En 250 días se esperan 2,5; Basilea tolera hasta
4 (verde), avisa de 5 a 9 (amarilla) y suspende desde 10 (roja).
"""

import numpy as np
from scipy.stats import binom, chi2

NIVEL_VAR = 0.99
NIVEL_ES = 0.975
VENTANA_BASILEA = 250
# Dos años de sesiones para estimar cada día. Con 250 la histórica al 99 %
# sería el segundo o tercer peor día del año, que no es un cuantil, es una
# anécdota; Basilea pide como mínimo un año, no como máximo.
VENTANA_ESTIMACION = 500
# Del acumulado binomial: verde por debajo del 95 %, roja desde el 99,99 %.
_CORTE_VERDE, _CORTE_ROJO = 0.95, 0.9999


def limites_semaforo(n: int = VENTANA_BASILEA, alpha: float = NIVEL_VAR) -> tuple[int, int]:
    """El máximo de excepciones de la zona verde y el de la amarilla."""
    k = np.arange(n + 1)
    acumulada = binom.cdf(k, n, 1 - alpha)
    return int(k[acumulada < _CORTE_VERDE].max()), int(k[acumulada < _CORTE_ROJO].max())


def zona(excepciones: int, n: int = VENTANA_BASILEA, alpha: float = NIVEL_VAR) -> str:
    verde, amarilla = limites_semaforo(n, alpha)
    if excepciones <= verde:
        return "verde"
    return "amarilla" if excepciones <= amarilla else "roja"


def kupiec(x: int, n: int, p: float) -> float:
    """p-valor del test de proporción de fallos: ¿la tasa observada es `p`?"""
    def _ll(q):
        # 0·log(0) = 0: con x = 0 o x = n un término desaparece.
        aciertos = (n - x) * np.log1p(-q) if x < n else 0.0
        fallos = x * np.log(q) if x > 0 else 0.0
        return aciertos + fallos
    lr = -2 * (_ll(p) - _ll(x / n))
    return float(1 - chi2.cdf(max(lr, 0.0), 1))
