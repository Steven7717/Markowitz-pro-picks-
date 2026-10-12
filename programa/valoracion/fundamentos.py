"""Lo que el motor necesita saber de una empresa, en una sola moneda.

El motor no sabe de fuentes ni de divisas: recibe `Fundamentos` y devuelve
cifras en la moneda de los estados. Este módulo construye `Fundamentos` desde
las líneas trimestrales que produce `fundamentals.concepts.resolve_lines`. Las
mismas columnas sirven hoy para EDGAR y en el sub-proyecto N para yfinance, que
las traduce antes de llegar aquí.

**El capex llega en positivo**, con la convención de la SEC:
`PaymentsToAcquirePropertyPlantAndEquipment` es un pago y se declara positivo.
yfinance lo da en negativo; el constructor de esa fuente le cambia el signo
antes de llamar a `desde_lineas`, que no lo comprueba.
"""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from fundamentals.concepts import (
    CONCEPTOS,
    completar_bpa_por_identidad,
    reconciliar_recuento_de_acciones,
    resolve_lines,
)
from fundamentals.fetch import CorridaAbortada, load_facts

# Privada y aun así importada: es la regla de los cuatro trimestres
# consecutivos, medida y documentada en `fundamentals/kpis.py`. Una segunda
# copia aquí es como empiezan a separarse.
from fundamentals.kpis import _ttm
from fundamentals.panel import quarterly_panel

# Veinte y no los doce del ranking: el CAGR de ingresos pide tres años y las
# medianas de márgenes cuantos haya. Los hechos en caché traen la historia
# entera desde 2007 (comprobado el 2026-10-12 sobre tres cachés reales), así que
# pedir más no sale a la red.
TRIMESTRES = 20
_TRIMESTRES_POR_ANO = 4
_FLUJOS = (
    "ingresos",
    "flujo_operativo",
    "capex",
    "gasto_por_intereses",
    "beneficio_operativo",
    "beneficio_neto",
)


@dataclass(frozen=True)
class Ejercicio:
    """Doce meses que terminan en `fin`: flujos sumados y el balance a esa fecha."""

    fin: date
    ingresos: float
    flujo_operativo: float
    capex: float
    gasto_financiero: float
    beneficio_operativo: float
    beneficio_neto: float
    patrimonio_neto: float


@dataclass(frozen=True)
class Fundamentos:
    """Una empresa, en la moneda de sus estados. `ejercicios[0]` es el más reciente."""

    moneda: str
    fuente: str
    ejercicios: tuple[Ejercicio, ...]
    deuda_total: float
    efectivo: float

    @property
    def ultimo(self) -> Ejercicio:
        return self.ejercicios[0]


def _num(valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return math.nan
    return numero if math.isfinite(numero) else math.nan


def desde_lineas(lineas: pd.DataFrame, moneda: str, fuente: str) -> "Fundamentos | None":
    """Las líneas trimestrales de una empresa, en ejercicios de doce meses.

    Un ejercicio cada cuatro filas hacia atrás desde la última fila con ingresos
    TTM. Asume, como `_ttm`, que las filas son trimestres consecutivos del más
    antiguo al más reciente, que es como los entrega `quarterly_panel`. Devuelve
    `None` si no hay ni un TTM de ingresos completo.
    """
    if lineas.empty:
        return None
    lineas = lineas.sort_index()
    ttm = {columna: _ttm(lineas[columna]) for columna in _FLUJOS}
    con_ingresos = [
        posicion
        for posicion in range(len(lineas))
        if pd.notna(ttm["ingresos"].iloc[posicion])
    ]
    if not con_ingresos:
        return None
    ultima = con_ingresos[-1]
    posiciones = [
        posicion
        for posicion in range(ultima, -1, -_TRIMESTRES_POR_ANO)
        if pd.notna(ttm["ingresos"].iloc[posicion])
    ]
    ejercicios = tuple(
        Ejercicio(
            fin=lineas.index[posicion].date(),
            ingresos=_num(ttm["ingresos"].iloc[posicion]),
            flujo_operativo=_num(ttm["flujo_operativo"].iloc[posicion]),
            capex=_num(ttm["capex"].iloc[posicion]),
            gasto_financiero=_num(ttm["gasto_por_intereses"].iloc[posicion]),
            beneficio_operativo=_num(ttm["beneficio_operativo"].iloc[posicion]),
            beneficio_neto=_num(ttm["beneficio_neto"].iloc[posicion]),
            patrimonio_neto=_num(lineas["patrimonio_neto"].iloc[posicion]),
        )
        for posicion in posiciones
    )
    return Fundamentos(
        moneda=moneda,
        fuente=fuente,
        ejercicios=ejercicios,
        deuda_total=_num(lineas["deuda_total"].iloc[ultima]),
        efectivo=_num(lineas["efectivo"].iloc[ultima]),
    )


def desde_sec(
    ticker: str, cache_dir: Path | None = None
) -> "tuple[Fundamentos | None, str]":
    """Los fundamentos de una empresa de la SEC, con el mismo motor que los candidatos.

    Las mismas reconciliaciones que `fundamentals.run.build_panel`, en el mismo
    orden: un recuento de acciones en otra base no se arregla aquí por segunda
    vez de otra manera.
    """
    try:
        hechos, _ = load_facts([ticker], cache_dir=cache_dir)
    except CorridaAbortada:
        # Con un solo ticker, abortar significa que la SEC no está: no es la
        # empresa la que falla, pero para esta valoración el efecto es el mismo.
        return None, "sin_estados"
    facts = hechos.get(ticker)
    if facts is None or facts.empty:
        return None, "sin_estados"
    panel = quarterly_panel(facts, CONCEPTOS, n_periodos=TRIMESTRES)
    lineas, _ = resolve_lines(panel)
    lineas = completar_bpa_por_identidad(reconciliar_recuento_de_acciones(lineas))
    fundamentos = desde_lineas(lineas, moneda="USD", fuente="sec")
    if fundamentos is None:
        return None, "sin_historia"
    return fundamentos, "ok"
