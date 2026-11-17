# programa/riesgo/informe.py
"""El VaR y el ES de la cartera propuesta y de cada activo, ya decidido el método."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from riesgo import backtest, metodos


class HistoriaInsuficiente(ValueError):
    def __init__(self, observaciones: int, necesarias: int):
        self.observaciones, self.necesarias = observaciones, necesarias
        super().__init__(f"{observaciones} sesiones comunes; hacen falta {necesarias}")


@dataclass(frozen=True)
class FilaActivo:
    ticker: str
    peso: float
    metodo: str            # el que ganó su propia competencia
    var99: float
    es975: float
    es99: float
    zona_actual: str
    fraccion_verde: float
    aportacion_es: float   # cuota del ES97,5 de la cartera; suman 1


@dataclass(frozen=True)
class InformeRiesgo:
    elegido: str
    competencia: dict[str, backtest.Backtest]
    fechas: pd.DatetimeIndex   # las de los días pronosticados
    var99: float
    es975: float
    es99: float
    diversificacion: float     # 1 − ES_cartera / Σ|w|·ES_activo
    activos: list[FilaActivo]
    observaciones: int


def _hoy(r: np.ndarray, metodo: str) -> tuple[float, float, float]:
    ventana = r[-backtest.VENTANA_ESTIMACION:]
    f = metodos.METODOS[metodo]
    var99, es99 = f(ventana, backtest.NIVEL_VAR)
    _, es975 = f(ventana, backtest.NIVEL_ES)
    return var99, es975, es99


def _cuotas_es(ventana: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    """Euler por escenarios: lo que cada activo pierde en los días de cola.

    Suman exactamente el ES histórico; se usan como **cuotas** y se aplican al
    ES del método elegido, que es el que se enseña.
    """
    rp = ventana @ pesos
    cola = rp <= np.quantile(rp, 1 - backtest.NIVEL_ES)
    aporte = -(ventana[cola] * pesos).mean(axis=0)
    total = aporte.sum()
    return aporte / total if total > 0 else np.full(len(pesos), 1 / len(pesos))


def informe_riesgo(retornos: pd.DataFrame, pesos: np.ndarray) -> InformeRiesgo:
    pesos = np.asarray(pesos, dtype=float)
    if len(pesos) != retornos.shape[1]:
        raise ValueError(f"{len(pesos)} pesos para {retornos.shape[1]} activos")
    if len(retornos) < backtest.MINIMO_OBSERVACIONES:
        raise HistoriaInsuficiente(len(retornos), backtest.MINIMO_OBSERVACIONES)

    matriz = retornos.to_numpy(dtype=float)
    if not np.isfinite(matriz).all():
        raise ValueError("Los retornos tienen valores no finitos (NaN o infinito); "
                         "pásalos por dropna() antes.")
    rp = matriz @ pesos
    competencia = backtest.competir(rp)
    elegido = backtest.elegir(competencia)
    var99, es975, es99 = _hoy(rp, elegido)

    cuotas = _cuotas_es(matriz[-backtest.VENTANA_ESTIMACION:], pesos)
    activos = []
    for i, ticker in enumerate(retornos.columns):
        suya = backtest.competir(matriz[:, i])
        m = backtest.elegir(suya)
        v, e975, e99 = _hoy(matriz[:, i], m)
        activos.append(FilaActivo(
            ticker=str(ticker), peso=float(pesos[i]), metodo=m, var99=v,
            es975=e975, es99=e99, zona_actual=suya[m].zona_actual,
            fraccion_verde=suya[m].fraccion_verde, aportacion_es=float(cuotas[i]),
        ))

    suma_aislados = sum(abs(f.peso) * f.es975 for f in activos)
    return InformeRiesgo(
        elegido=elegido, competencia=competencia,
        fechas=retornos.index[backtest.VENTANA_ESTIMACION:],
        var99=var99, es975=es975, es99=es99,
        diversificacion=1 - es975 / suma_aislados if suma_aislados > 0 else 0.0,
        activos=activos, observaciones=len(retornos),
    )
