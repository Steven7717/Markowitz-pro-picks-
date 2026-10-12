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

**NaN quiere decir «no declarada», no cero.** Una empresa que no informa de
capex, de gasto por intereses o de deuda no los tiene a cero: no se sabe. Un
banco, además, no declara ingresos con la etiqueta que usa el resto. Quien
necesite un cero (el capex de una empresa sin inmovilizado, la deuda de una sin
pasivo financiero) lo decide explícitamente al usarlo, sabiendo que lo decide.
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

# Privadas y aun así importadas: son la regla de los cuatro trimestres
# consecutivos, medida y documentada en `fundamentals/kpis.py`, y las ventanas de
# días con que `fundamentals/panel.py` decide qué es un trimestre y qué es un
# año. Una segunda copia aquí es como empiezan a separarse.
from fundamentals.kpis import _TRIMESTRES_POR_ANO, _ttm
from fundamentals.panel import _DIAS_ANO, _DIAS_TRIMESTRE, quarterly_panel

# Veinte y no los doce del ranking: el CAGR de ingresos pide tres años y las
# medianas de márgenes cuantos haya. Los hechos en caché traen la historia
# entera desde 2007 (comprobado el 2026-10-12 sobre tres cachés reales), así que
# pedir más no sale a la red.
TRIMESTRES = 20
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
    """Doce meses que terminan en `fin`: flujos sumados y el balance a esa fecha.

    Cualquier cifra puede ser NaN, y NaN es «no declarada», no cero: un banco no
    declara `ingresos`, y casi nadie declara `gasto_financiero` si no tiene deuda.
    """

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
    """Una empresa, en la moneda de sus estados. `ejercicios[0]` es el más reciente.

    `deuda_total` y `efectivo` son el balance del último trimestre. NaN es «no
    declarada», no cero: sin `deuda_total` no se sabe si la empresa no debe nada
    o no lo dice, y quien la use como cero lo decide él.
    """

    moneda: str
    fuente: str
    ejercicios: tuple[Ejercicio, ...]
    deuda_total: float
    efectivo: float

    def __post_init__(self) -> None:
        # `ultimo` indexa la posición 0: con la tupla vacía fallaría con un
        # IndexError lejos de donde se construyó el objeto.
        if not self.ejercicios:
            raise ValueError("Fundamentos necesita al menos un ejercicio")

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

    Una posición vale como cierre de ejercicio si sus cuatro trimestres son
    consecutivos de verdad (las fechas de la ventana distan lo que distan tres
    trimestres) y la serie ancla tiene TTM ahí. La serie ancla son los
    `ingresos` si la empresa tiene algún TTM de ingresos en todo el panel, y el
    `beneficio_neto` sólo si no lo tiene nunca: es el caso de los bancos, que no
    declaran ingresos con una etiqueta que el motor reconozca y a los que la
    valoración por resultado residual sólo pide beneficio y patrimonio.

    El ancla es una sola serie, no «cualquiera de las dos», a propósito. Con la
    segunda como alternativa, a una empresa normal a la que el último informe le
    falta sólo la etiqueta de ingresos le quedaría un ejercicio más reciente con
    `ingresos` vacío, y su DCF, que parte de ellos, se perdería por una etiqueta;
    anclada en los ingresos, retrocede al último trimestre que sí los tiene. La
    cifra que no es el ancla puede quedarse en NaN en el `Ejercicio`.

    El ejercicio más reciente es la **última** posición válida; los demás se
    buscan hacia atrás de cuatro en cuatro filas, y la búsqueda **se detiene**
    en la primera posición inválida o cuya distancia al ejercicio anterior no es
    de un año. Saltarse el hueco y seguir devolvería ejercicios que ya no son
    años consecutivos, y `ejercicios[i]` dejaría de ser «hace i años».

    Por eso lo que sale está garantizado: los ejercicios son años consecutivos,
    del más reciente al más antiguo, y el código posterior puede indexarlos por
    posición (`supuestos._cagr` toma `ejercicios[anos]` con exponente `1/anos`).
    Lo que no está garantizado es que cada cifra de cada ejercicio exista.

    La ventana de fechas es la de `fundamentals.panel` y no un múltiplo exacto:
    las empresas de 52/53 semanas cierran sus trimestres a 84 o 112 días unos de
    otros, y siguen teniendo un ejercicio al año.

    Devuelve `None` si no hay ni una posición válida.
    """
    if lineas.empty:
        return None
    lineas = lineas.sort_index()
    ttm = {columna: _ttm(lineas[columna]) for columna in _FLUJOS}
    fechas = lineas.index
    ancla = ttm["ingresos"] if ttm["ingresos"].notna().any() else ttm["beneficio_neto"]
    minimo_ventana = (_TRIMESTRES_POR_ANO - 1) * _DIAS_TRIMESTRE[0]
    maximo_ventana = (_TRIMESTRES_POR_ANO - 1) * _DIAS_TRIMESTRE[1]

    def valida(posicion: int) -> bool:
        if posicion < _TRIMESTRES_POR_ANO - 1:
            return False
        ventana = (fechas[posicion] - fechas[posicion - (_TRIMESTRES_POR_ANO - 1)]).days
        if not minimo_ventana <= ventana <= maximo_ventana:
            return False
        return bool(pd.notna(ancla.iloc[posicion]))

    validas = [posicion for posicion in range(len(lineas)) if valida(posicion)]
    if not validas:
        return None
    ultima = validas[-1]

    posiciones = [ultima]
    while True:
        candidata = posiciones[-1] - _TRIMESTRES_POR_ANO
        if candidata < 0 or not valida(candidata):
            break
        dias = (fechas[posiciones[-1]] - fechas[candidata]).days
        if not _DIAS_ANO[0] <= dias <= _DIAS_ANO[1]:
            break
        posiciones.append(candidata)

    ejercicios = tuple(
        Ejercicio(
            fin=fechas[posicion].date(),
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

    Devuelve `(fundamentos, motivo)`. Sólo se traducen a motivo los dos casos que
    son «esta empresa no se puede valorar» (`sin_estados`, `sin_historia`). Las
    demás excepciones (un `OSError` al leer la caché, un `KeyError` por una
    columna que falta) se dejan propagar a propósito: son defectos o fallos del
    entorno, no una propiedad de la empresa, y quien llama (`ranking/run.py`, que
    llega en una tarea posterior) las atrapa ficha a ficha y no las confunde con
    una empresa sin datos.
    """
    try:
        hechos, _ = load_facts([ticker], cache_dir=cache_dir)
    except CorridaAbortada:
        # Con un solo ticker, abortar significa que la fuente no responde o que
        # rechaza la identidad con que se le pregunta (EDGAR_IDENTITY): no es la
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
