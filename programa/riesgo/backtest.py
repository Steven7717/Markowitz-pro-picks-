# programa/riesgo/backtest.py
"""El semáforo de Basilea y la competencia entre métodos.

Una **excepción** es un día en que la pérdida real supera el VaR al 99 % que
se había previsto la víspera. En 250 días se esperan 2,5; Basilea tolera hasta
4 (verde), avisa de 5 a 9 (amarilla) y suspende desde 10 (roja).
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import binom, chi2

from riesgo import metodos

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


# Lo mínimo para que haya al menos una ventana de Basilea que contar.
MINIMO_OBSERVACIONES = VENTANA_ESTIMACION + VENTANA_BASILEA


def pronosticos(r: np.ndarray, metodo: str, ventana: int = VENTANA_ESTIMACION) -> dict:
    """La previsión de cada día t hecha con `r[t-ventana:t]`, sin mirar `r[t]`."""
    f = metodos.METODOS[metodo]
    salida = {k: [] for k in ("var99", "es99", "var975", "es975")}
    for t in range(ventana, len(r)):
        pasado = r[t - ventana:t]
        v99, e99 = f(pasado, NIVEL_VAR)
        v975, e975 = f(pasado, NIVEL_ES)
        salida["var99"].append(v99)
        salida["es99"].append(e99)
        salida["var975"].append(v975)
        salida["es975"].append(e975)
    return {k: np.asarray(v) for k, v in salida.items()}


@dataclass(frozen=True)
class Backtest:
    metodo: str
    var99: np.ndarray
    es99: np.ndarray
    var975: np.ndarray
    es975: np.ndarray
    realizados: np.ndarray       # el retorno de cada día pronosticado
    excepciones: np.ndarray      # pérdida > VaR99 previsto
    fraccion_verde: float        # de las ventanas de 250, cuántas en verde
    zona_actual: str             # la de las 250 últimas sesiones
    excepciones_ultimas: int
    tasa: float                  # excepciones / días, sobre todo el backtest
    kupiec_p: float
    razon_es: float              # pérdida media / ES previsto, días > VaR97,5


def backtestear(r: np.ndarray, metodo: str) -> Backtest:
    p = pronosticos(r, metodo)
    realizados = r[VENTANA_ESTIMACION:]
    perdida = -realizados
    excepciones = perdida > p["var99"]
    conteos = np.convolve(excepciones.astype(int), np.ones(VENTANA_BASILEA, int), "valid")
    verde, _ = limites_semaforo()
    cola = perdida > p["var975"]
    razon = float(perdida[cola].mean() / p["es975"][cola].mean()) if cola.any() else float("nan")
    x, n = int(excepciones.sum()), len(excepciones)
    return Backtest(
        metodo=metodo, realizados=realizados, excepciones=excepciones,
        fraccion_verde=float(np.mean(conteos <= verde)),
        zona_actual=zona(int(conteos[-1])), excepciones_ultimas=int(conteos[-1]),
        tasa=x / n, kupiec_p=kupiec(x, n, 1 - NIVEL_VAR), razon_es=razon, **p,
    )


def competir(r: np.ndarray) -> dict[str, Backtest]:
    return {m: backtestear(r, m) for m in metodos.METODOS}


def elegir(resultados: dict[str, Backtest]) -> str:
    """Más tiempo en verde; luego la tasa más cercana al 1 %; luego el VaR más bajo."""
    return min(resultados, key=lambda m: (
        -resultados[m].fraccion_verde,
        abs(resultados[m].tasa - (1 - NIVEL_VAR)),
        float(np.mean(resultados[m].var99)),
    ))
