# Valor intrínseco (sub-proyecto M) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada candidato de Revisar candidatos lleve una valoración —infravalorada, en rango, sobrevalorada o señales mixtas— calculada con cuatro lecturas que dan tres votos, guardada en `fichas.json` y, por tanto, en el acta.

**Architecture:** Paquete nuevo `valoracion/`, sin Streamlit: `criterio` (congelado), `fundamentos` (EDGAR → ejercicios de doce meses), `mercado` (lo único que toca la red: yfinance), `supuestos`, `dcf`, `inverso`, `epv`, `residual`, `votos`, `motor` (`calcular` puro y `valorar` con red) y `plano` (a diccionario JSON estricto). `ranking/run.py` llama a `valorar` para cada ficha; `medidores_valoracion.py` pinta el distintivo y el resumen; `vistas/candidatos.py` los enseña. El score no se toca.

**Tech Stack:** Python 3, pandas, numpy, yfinance, edgartools (vía `fundamentals/`), pytest. Sin dependencias nuevas.

**Spec:** `programa/docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md`. Léelo antes de empezar: cada constante y cada regla de abajo sale de ahí.

---

## Antes de empezar

Todo se ejecuta **desde `programa/`**, no desde la raíz del repo. La rama ya existe: `feat/valor-intrinseco` (lleva los dos specs).

```bash
git switch feat/valor-intrinseco
uv run pytest tests/ -q -m "not red"
```

Esperado: todo verde (1.844 pasando a fecha del spec). Si algo falla **antes** de tocar nada, para y avisa: no es de este trabajo.

**Convenciones del repo que este plan sigue:**
- Comentarios y docstrings en castellano, explicando el **porqué**, no el qué.
- Lógica sin Streamlit en paquetes con tests; las vistas sólo pintan.
- Tests de red marcados `@pytest.mark.red`, excluidos de la suite normal.
- Nada de texto de pantalla en ficheros de datos: se guardan claves, las etiquetas viven en el módulo de presentación.
- Cada commit termina con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Mapa de ficheros

| Fichero | Qué hace | Tarea |
|---|---|---|
| `valoracion/__init__.py` | Marca el paquete | 1 |
| `valoracion/criterio.py` | Constantes congeladas | 1 |
| `valoracion/fundamentos.py` | `Ejercicio`, `Fundamentos`, `desde_lineas`, `desde_sec` | 2 |
| `valoracion/mercado.py` | `Perfil`, `Beta`, intérpretes puros y descargas con caché | 3, 4 |
| `valoracion/supuestos.py` | `Supuesto`, `Supuestos`, `deducir` | 5 |
| `valoracion/dcf.py` | DCF en dos etapas, `Escenarios` | 6 |
| `valoracion/inverso.py` | Bisección, `Implicito` | 6 |
| `valoracion/epv.py` | Valor sin crecimiento | 7 |
| `valoracion/residual.py` | Beneficio residual y ROE implícito | 7 |
| `valoracion/votos.py` | Los tres votos y el veredicto | 8 |
| `valoracion/motor.py` | `calcular` (puro) y `valorar` (con red) | 9 |
| `valoracion/plano.py` | La valoración como diccionario JSON estricto | 9 |
| `ranking/run.py` | Añade `ficha["valoracion"]` | 10 |
| `aprobacion/carga.py` | `valoracion_de(ficha)` | 11 |
| `medidores_valoracion.py` | Etiquetas, `distintivo`, `resumen`, CSS | 12 |
| `medidores.py` | El distintivo en `tarjeta_candidato` | 12 |
| `vistas/candidatos.py` | El bloque «Valoración» en cada ficha | 13 |
| `.gitignore` | `valoracion/.cache/` | 13 |
| `tests/dobles_valoracion.py` | Constructores de datos de prueba | 3 |
| `tests/test_valoracion_*.py` | Tests de cada módulo | 1–9, 14 |
| `scripts/medir_valoracion.py` | La medida sobre el S&P 500 | 17 |

---

### Task 1: Sondeo de industrias y criterio congelado

**Files:**
- Create: `valoracion/__init__.py`
- Create: `valoracion/criterio.py`
- Test: `tests/test_valoracion_criterio.py`

El criterio se congela **antes** de medir nada, en un commit propio. Las cadenas de industria no son un listón sino un hecho de la fuente, así que se sondean primero.

- [ ] **Step 1: Sondear las cadenas de industria reales de Yahoo**

```bash
uv run python -I -c "
import yfinance as yf
for t in ['JPM','USB','MET','PGR','AIG','RGA','GS','SCHW','RKT','V','MA','COF','SYF','AJG','BLK','MU']:
    print(t, '|', yf.Ticker(t).info.get('industry'))
"
```

Esperado (aproximado): `JPM | Banks - Diversified`, `USB | Banks - Regional`, `MET | Insurance - Life`, `PGR | Insurance - Property & Casualty`, `AIG | Insurance - Diversified`, `RGA | Insurance - Reinsurance`, `GS | Capital Markets`, `RKT | Mortgage Finance`, `V/MA/COF/SYF | Credit Services`, `AJG | Insurance Brokers`, `BLK | Asset Management`. **Si alguna cadena real difiere de la lista del Step 3, usa la real** y anótalo en el mensaje del commit. Ninguna de V, MA, COF, SYF, AJG, BLK ni MU puede acabar en la lista.

- [ ] **Step 2: Escribir el test del criterio**

`tests/test_valoracion_criterio.py`:

```python
"""El criterio no se prueba por sus valores --esos los fija el spec-- sino por
su coherencia: limites ordenados, monedas cubiertas, y la frontera de la lista
de financieras, que es donde un descuido cambia el metodo de valoracion."""

import pytest

from valoracion import criterio as c


def test_la_proyeccion_dura_diez_anos():
    assert c.ANOS_ALTO_CRECIMIENTO + c.ANOS_CONVERGENCIA == 10


def test_el_crecimiento_perpetuo_cubre_las_dos_monedas_que_se_valoran():
    assert set(c.CRECIMIENTO_PERPETUO) == {"USD", "MXN"}


def test_la_tasa_legal_tiene_respaldo_para_cualquier_pais():
    assert {"US", "MX", "otros"} <= set(c.TASA_LEGAL)


@pytest.mark.parametrize(
    "limites",
    [
        c.TASA_EFECTIVA_TOPES,
        c.CRECIMIENTO_REF_TOPES,
        c.INVERSO_LIMITES,
        c.INVERSO_ROE_LIMITES,
    ],
)
def test_los_limites_estan_ordenados(limites):
    bajo, alto = limites
    assert bajo < alto


def test_blume_deja_una_beta_de_uno_en_uno():
    a, b = c.BLUME
    assert a * 1.0 + b == pytest.approx(1.0)


def test_credit_services_y_los_corredores_no_son_financieras():
    # Visa, Mastercard y PayPal viven en Credit Services: su flujo de caja si
    # significa algo. Un corredor de seguros no tiene balance de riesgo.
    assert "Credit Services" not in c.INDUSTRIAS_FINANCIERAS
    assert "Insurance Brokers" not in c.INDUSTRIAS_FINANCIERAS
    assert "Asset Management" not in c.INDUSTRIAS_FINANCIERAS


def test_bancos_y_aseguradoras_de_riesgo_son_financieras():
    assert {
        "Banks - Diversified",
        "Banks - Regional",
        "Insurance - Life",
        "Insurance - Property & Casualty",
    } <= c.INDUSTRIAS_FINANCIERAS
```

- [ ] **Step 3: Escribir el criterio**

`valoracion/__init__.py`:

```python
"""Valor intrínseco: cuatro lecturas, tres votos, un veredicto. Sub-proyecto M."""
```

`valoracion/criterio.py`:

```python
"""El criterio del valor intrínseco, congelado antes de medir nada.

Datos, no lógica. La fecha del commit que introduce este fichero es la prueba de
que ningún listón se movió al ver los veredictos: cambiar cualquiera de estos
valores exige una enmienda fechada en
`docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md`, nunca una edición
silenciosa. El porqué de cada valor está en la tabla de esa sección y no se
repite aquí: dos copias de una justificación se separan igual que dos de un
número.
"""

# Viaja dentro de cada valoración guardada, para que una ficha vieja diga con
# qué criterio se calculó.
VERSION = "m1"

# --- Proyección ---------------------------------------------------------------
ANOS_ALTO_CRECIMIENTO = 5
ANOS_CONVERGENCIA = 5

# --- Coste del capital --------------------------------------------------------
PRIMA_RIESGO = 0.0420
PRIMA_RIESGO_FECHA = "2026-10-01"
BETA_SEMANAS = 104
BETA_SEMANAS_MIN = 52
BLUME = (0.67, 0.33)
COSTE_DEUDA_PRIMA_MAXIMA = 0.08
TASA_LEGAL = {"US": 0.21, "MX": 0.30, "otros": 0.24}
TASA_EFECTIVA_TOPES = (0.0, 0.35)

# --- Crecimiento --------------------------------------------------------------
CRECIMIENTO_PERPETUO = {"USD": 0.025, "MXN": 0.035}
CRECIMIENTO_REF_TOPES = (-0.10, 0.40)
CRECIMIENTO_REF_ANOS = 3
HOLGURA_GORDON = 0.01

# --- Votos --------------------------------------------------------------------
MARGEN_MINIMO = 0.05
MARGEN_ROE_MINIMO = 0.03
DELTA_WACC_ESCENARIOS = 0.01
INVERSO_LIMITES = (-0.30, 0.80)
INVERSO_ROE_LIMITES = (-0.20, 0.60)
UMBRAL_PARES = 0.5
MIN_ANOS_HISTORIA = 2
MIN_VOTOS = 2

# --- Beneficio residual -------------------------------------------------------
PAYOUT_SIN_DATO = 0.5

# Cadenas exactas de `info["industry"]` de Yahoo, sondeadas el día del commit.
# Fuera a propósito: Credit Services (Visa, Mastercard, PayPal), Insurance
# Brokers y Asset Management, cuyo flujo de caja sí significa algo.
INDUSTRIAS_FINANCIERAS = frozenset(
    {
        "Banks - Diversified",
        "Banks - Regional",
        "Insurance - Life",
        "Insurance - Property & Casualty",
        "Insurance - Diversified",
        "Insurance - Reinsurance",
        "Insurance - Specialty",
        "Capital Markets",
        "Mortgage Finance",
    }
)
```

- [ ] **Step 4: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_criterio.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit (el commit propio del criterio)**

```bash
git add valoracion/__init__.py valoracion/criterio.py tests/test_valoracion_criterio.py
git commit -m "feat: criterio congelado del valor intrinseco (M)

Antes de medir nada. Las industrias financieras son las cadenas reales
de Yahoo sondeadas hoy.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Fundamentos desde EDGAR

> **Ejecutada y superada.** El código de abajo es el de partida. Sus revisiones de calidad lo cambiaron (bancos sin ingresos, ejercicios que distan un año, tests de comportamiento): ver los commits de `valoracion/fundamentos.py` desde `2e655d4`. Si se re-ejecuta, manda el código vivo, no este bloque.

**Files:**
- Create: `valoracion/fundamentos.py`
- Test: `tests/test_valoracion_fundamentos.py`

- [ ] **Step 1: Escribir los tests de fundamentos**

`tests/test_valoracion_fundamentos.py`:

```python
from datetime import date
from unittest.mock import patch

import pandas as pd

from fundamentals.concepts import LINEAS
from fundamentals.fetch import CorridaAbortada, CoverageReport
from valoracion.fundamentos import TRIMESTRES, desde_lineas, desde_sec


def lineas(n: int = 20, **columnas) -> pd.DataFrame:
    """Un panel con la forma de `resolve_lines`: trimestres, una columna por línea."""
    fechas = (
        pd.period_range("2021Q4", periods=n, freq="Q")
        .to_timestamp(how="end")
        .normalize()
    )
    marco = pd.DataFrame(float("nan"), index=fechas, columns=list(LINEAS), dtype="float64")
    valores = {
        "ingresos": 250.0,
        "flujo_operativo": 75.0,
        "capex": 25.0,
        "gasto_por_intereses": 5.0,
        "beneficio_operativo": 50.0,
        "beneficio_neto": 30.0,
        "patrimonio_neto": 2000.0,
        "deuda_total": 500.0,
        "efectivo": 100.0,
    }
    valores.update(columnas)
    for columna, valor in valores.items():
        marco[columna] = valor
    return marco


def test_el_ttm_suma_cuatro_trimestres():
    f = desde_lineas(lineas(), "USD", "sec")
    assert f.ultimo.ingresos == 1000.0
    assert f.ultimo.flujo_operativo == 300.0
    assert f.ultimo.capex == 100.0
    assert f.ultimo.gasto_financiero == 20.0
    assert f.ultimo.beneficio_operativo == 200.0
    assert f.ultimo.beneficio_neto == 120.0


def test_un_ejercicio_cada_cuatro_trimestres_del_mas_reciente_al_mas_antiguo():
    f = desde_lineas(lineas(), "USD", "sec")
    assert [e.fin for e in f.ejercicios] == [
        date(2026, 9, 30),
        date(2025, 9, 30),
        date(2024, 9, 30),
        date(2023, 9, 30),
        date(2022, 9, 30),
    ]


def test_el_balance_es_el_del_ultimo_trimestre():
    marco = lineas()
    marco["deuda_total"] = range(len(marco))
    marco["efectivo"] = [10.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.deuda_total == len(marco) - 1
    assert f.efectivo == 10.0 * (len(marco) - 1)


def test_el_patrimonio_de_cada_ejercicio_es_el_de_su_cierre():
    marco = lineas()
    marco["patrimonio_neto"] = [100.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.ejercicios[0].patrimonio_neto == 1900.0
    assert f.ejercicios[1].patrimonio_neto == 1500.0


def test_el_ultimo_ejercicio_es_el_ultimo_con_ingresos_de_doce_meses():
    marco = lineas()
    marco.iloc[-1, marco.columns.get_loc("ingresos")] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == date(2026, 6, 30)
    assert len(f.ejercicios) == 4


def test_menos_de_cuatro_trimestres_no_dan_fundamentos():
    assert desde_lineas(lineas(3), "USD", "sec") is None


def test_un_panel_vacio_no_da_fundamentos():
    assert desde_lineas(lineas(0), "USD", "sec") is None


def test_sin_hechos_de_la_sec_lo_dice():
    vacio = ({}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=vacio):
        assert desde_sec("TST") == (None, "sin_estados")


def test_una_corrida_abortada_no_se_propaga():
    error = CorridaAbortada("sin_identidad", "x", CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", side_effect=error):
        assert desde_sec("TST") == (None, "sin_estados")


def test_desde_sec_pide_veinte_trimestres_y_construye():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ) as panel, patch(
        "valoracion.fundamentos.resolve_lines", return_value=(lineas(), [])
    ), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        fundamentos, motivo = desde_sec("TST")
    assert motivo == "ok"
    assert fundamentos.moneda == "USD" and fundamentos.fuente == "sec"
    assert panel.call_args.kwargs["n_periodos"] == TRIMESTRES == 20


def test_desde_sec_sin_historia_suficiente_lo_dice():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ), patch("valoracion.fundamentos.resolve_lines", return_value=(lineas(2), [])), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        assert desde_sec("TST") == (None, "sin_historia")
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_fundamentos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.fundamentos'`.

- [ ] **Step 3: Implementar**

`valoracion/fundamentos.py`:

```python
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
```

- [ ] **Step 4: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_fundamentos.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add valoracion/fundamentos.py tests/test_valoracion_fundamentos.py
git commit -m "feat: fundamentos del valor intrinseco desde EDGAR, en ejercicios de doce meses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Mercado — tipos e intérpretes puros

> **Ejecutada y superada.** Sus revisiones endurecieron la beta, la hora y el perfil (ver `960eaba`). Manda el código vivo.

**Files:**
- Create: `valoracion/mercado.py`
- Create: `tests/dobles_valoracion.py`
- Test: `tests/test_valoracion_mercado.py`

- [ ] **Step 1: Escribir los dobles compartidos**

`tests/dobles_valoracion.py` (lo usan los tests de las tareas 5 a 12). Importa `valoracion.mercado.Perfil`, que se crea en esta misma tarea; ningún test lo importa hasta la Task 5.

```python
"""Constructores de datos de prueba para `valoracion/`, sin red.

Las cifras por defecto están elegidas para que las cuentas salgan a mano:
ingresos 1.000, flujo operativo 300, capex 100, intereses 20 (margen de flujo
libre para la empresa 0,215 con t = 0,25), beneficio operativo 200, beneficio
neto 120 sobre un patrimonio de 1.000 (ROE 0,12). El perfil cotiza a 100 con
una capitalización de 1.000: diez acciones.
"""

from datetime import date

from valoracion.fundamentos import Ejercicio, Fundamentos
from valoracion.mercado import Perfil


def ejercicio(ano: int = 2026, **sobre) -> Ejercicio:
    valores = dict(
        fin=date(ano, 9, 30),
        ingresos=1000.0,
        flujo_operativo=300.0,
        capex=100.0,
        gasto_financiero=20.0,
        beneficio_operativo=200.0,
        beneficio_neto=120.0,
        patrimonio_neto=1000.0,
    )
    valores.update(sobre)
    return Ejercicio(**valores)


def fundamentos(ejercicios=None, deuda_total=200.0, efectivo=50.0) -> Fundamentos:
    if ejercicios is None:
        ejercicios = [ejercicio(2026 - i) for i in range(4)]
    return Fundamentos(
        moneda="USD",
        fuente="sec",
        ejercicios=tuple(ejercicios),
        deuda_total=deuda_total,
        efectivo=efectivo,
    )


def perfil(**sobre) -> Perfil:
    valores = dict(
        ticker="TST",
        precio=100.0,
        capitalizacion=1000.0,
        moneda="USD",
        moneda_estados="USD",
        industria="Semiconductors",
        pais="United States",
        payout=0.3,
        tipo="EQUITY",
        hora="2026-10-12T19:59:00+00:00",
    )
    valores.update(sobre)
    return Perfil(**valores)
```

- [ ] **Step 2: Escribir los tests de los intérpretes**

`tests/test_valoracion_mercado.py`:

```python
import math

import numpy as np
import pandas as pd
import pytest

from valoracion.mercado import (
    Perfil,
    consenso_desde_estimacion,
    perfil_desde_info,
    regresion_beta,
    tasa_efectiva_desde_estado,
    tasa_libre_desde_cierres,
)

INFO = {
    "currentPrice": 989.04,
    "marketCap": 1_119_022_743_552,
    "currency": "USD",
    "financialCurrency": "USD",
    "industry": "Semiconductors",
    "country": "United States",
    "payoutRatio": 0.02,
    "quoteType": "EQUITY",
    "regularMarketTime": 1_791_835_140,
    "beta": 2.226,
}


def test_el_perfil_lee_lo_que_hace_falta():
    p = perfil_desde_info("MU", INFO)
    assert p.precio == 989.04
    assert p.capitalizacion == 1_119_022_743_552
    assert p.moneda == p.moneda_estados == "USD"
    assert p.industria == "Semiconductors"
    assert p.pais == "United States"
    assert p.payout == 0.02
    assert p.tipo == "EQUITY"
    assert p.hora.startswith("2026-")


def test_el_perfil_no_tiene_donde_guardar_la_beta_de_yahoo():
    # La beta se calcula con `regresion_beta`, nunca se lee de Yahoo: para
    # WALMEX.MX daba 0,016. La garantía es la forma del tipo, no una promesa.
    assert "beta" not in Perfil.__dataclass_fields__


def test_sin_precio_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": None}) is None


def test_el_precio_cae_al_de_mercado_si_falta_el_actual():
    p = perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": 50.0})
    assert p.precio == 50.0


def test_sin_capitalizacion_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "marketCap": None}) is None


def test_sin_moneda_no_hay_perfil():
    # Un precio sin moneda no se puede comparar con nada.
    assert perfil_desde_info("X", {**INFO, "currency": None}) is None


def test_la_moneda_de_los_estados_cae_a_la_del_precio():
    p = perfil_desde_info("X", {**INFO, "financialCurrency": None})
    assert p.moneda_estados == "USD"


def _cierres(rendimientos: np.ndarray) -> pd.Series:
    fechas = pd.date_range("2024-10-07", periods=len(rendimientos) + 1, freq="W-MON")
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1 + rendimientos]), index=fechas)


def test_la_beta_es_la_pendiente_de_la_regresion():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0.002, 0.02, 104)
    activo = 1.5 * mercado + generador.normal(0, 0.002, 104)
    beta = regresion_beta(_cierres(activo), _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.5, abs=0.05)
    assert beta.r2 > 0.95
    assert beta.semanas == 104
    assert beta.indice == "^GSPC"


def test_con_menos_de_un_ano_no_hay_beta():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0, 0.02, 40)
    assert regresion_beta(_cierres(mercado), _cierres(mercado), "^GSPC") is None


def test_la_beta_tolera_zonas_horarias_distintas():
    generador = np.random.default_rng(3)
    mercado = generador.normal(0, 0.02, 80)
    activo = _cierres(mercado)
    activo.index = activo.index.tz_localize("America/New_York")
    beta = regresion_beta(activo, _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.0)


def test_la_tasa_libre_es_el_ultimo_cierre_en_tanto_por_uno():
    assert tasa_libre_desde_cierres(pd.Series([4.1, 4.2, 5.24])) == pytest.approx(0.0524)


def test_sin_cierres_no_hay_tasa_libre():
    assert tasa_libre_desde_cierres(pd.Series([], dtype="float64")) is None


def test_la_tasa_efectiva_es_la_mas_reciente_con_dato():
    estado = pd.DataFrame(
        {"2025": [float("nan"), 10.0], "2024": [0.19, 9.0]},
        index=["Tax Rate For Calcs", "Net Income"],
    )
    assert tasa_efectiva_desde_estado(estado) == 0.19


def test_sin_fila_de_impuestos_no_hay_tasa_efectiva():
    estado = pd.DataFrame({"2025": [1.0]}, index=["Net Income"])
    assert tasa_efectiva_desde_estado(estado) is None
    assert tasa_efectiva_desde_estado(None) is None


def _estimacion(moneda: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"avg": [1.0, 2.0], "growth": [1.0663, 0.1648], "currency": [moneda, moneda]},
        index=["0y", "+1y"],
    )


def test_el_consenso_es_el_crecimiento_del_proximo_ano():
    assert consenso_desde_estimacion(_estimacion("USD"), "USD") == pytest.approx(0.1648)


def test_un_consenso_en_otra_moneda_se_descarta():
    # TSM: revenue_estimate en TWD y earnings_estimate en USD, en la misma consulta.
    assert consenso_desde_estimacion(_estimacion("TWD"), "USD") is None


def test_sin_estimacion_no_hay_consenso():
    assert consenso_desde_estimacion(pd.DataFrame(), "USD") is None
    assert consenso_desde_estimacion(None, "USD") is None
```

- [ ] **Step 3: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_mercado.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.mercado'`.

- [ ] **Step 4: Implementar tipos e intérpretes**

`valoracion/mercado.py`:

```python
"""Lo único de `valoracion/` que toca la red, y lo que interpreta lo que trae.

Las funciones `*_desde_*` son puras: reciben lo que yfinance devolvió y deciden
qué significa. Las de red (más abajo) sólo descargan, guardan en caché y llaman
a las puras. Así los tests de lo que importa no necesitan red, y los `red`
comprueban que la fuente sigue teniendo la forma que las puras esperan.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from valoracion.criterio import BETA_SEMANAS, BETA_SEMANAS_MIN


@dataclass(frozen=True)
class Perfil:
    """Lo que se sabe de un ticker hoy. **No lleva beta, a propósito.**

    La beta de Yahoo no se lee: para WALMEX.MX dio 0,016, porque Yahoo la mide
    contra el S&P 500 con el precio en pesos. Para una empresa de EE. UU. sería
    razonable, pero dos caminos para el mismo dato se separan, y el que se queda
    atrás no da error: da un número plausible. Sin campo, no hay camino.
    """

    ticker: str
    precio: float
    capitalizacion: float
    moneda: str
    moneda_estados: str
    industria: "str | None"
    pais: "str | None"
    payout: "float | None"
    tipo: str
    hora: "str | None"


@dataclass(frozen=True)
class Beta:
    bruta: float
    r2: float
    semanas: int
    indice: str


def _num(valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return math.nan
    return numero if math.isfinite(numero) else math.nan


def _opcional(valor: object) -> "float | None":
    numero = _num(valor)
    return None if math.isnan(numero) else numero


def _texto(valor: object) -> "str | None":
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def perfil_desde_info(ticker: str, info: dict) -> "Perfil | None":
    """El perfil desde `yf.Ticker(t).info`, o `None` si falta precio, capitalización o moneda."""
    precio = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    capitalizacion = _num(info.get("marketCap"))
    moneda = _texto(info.get("currency"))
    if not (precio > 0 and capitalizacion > 0) or moneda is None:
        return None
    momento = _opcional(info.get("regularMarketTime"))
    return Perfil(
        ticker=ticker,
        precio=precio,
        capitalizacion=capitalizacion,
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        payout=_opcional(info.get("payoutRatio")),
        tipo=_texto(info.get("quoteType")) or "EQUITY",
        hora=(
            None
            if momento is None
            else datetime.fromtimestamp(momento, tz=timezone.utc).isoformat()
        ),
    )


def _semanal(cierres: pd.Series) -> pd.Series:
    """Sin zona horaria y al día: Yahoo fecha las velas del activo y del índice
    en zonas que no siempre coinciden, y sin esto el cruce sale vacío."""
    serie = pd.to_numeric(cierres, errors="coerce").dropna()
    indice = pd.DatetimeIndex(serie.index)
    if indice.tz is not None:
        indice = indice.tz_localize(None)
    serie.index = indice.normalize()
    return serie[~serie.index.duplicated(keep="last")]


def regresion_beta(
    activo: pd.Series, indice: pd.Series, nombre_indice: str
) -> "Beta | None":
    """La pendiente de los rendimientos semanales del activo contra los del índice.

    Las últimas `BETA_SEMANAS`; con menos de `BETA_SEMANAS_MIN`, `None`: un año
    de datos semanales ya da una beta ruidosa, y menos no da ninguna.
    """
    juntos = pd.concat([_semanal(activo), _semanal(indice)], axis=1, join="inner").dropna()
    rendimientos = juntos.pct_change(fill_method=None).dropna().tail(BETA_SEMANAS)
    if len(rendimientos) < BETA_SEMANAS_MIN:
        return None
    y, x = rendimientos.iloc[:, 0], rendimientos.iloc[:, 1]
    varianza = x.var()
    if not varianza > 0:
        return None
    return Beta(
        bruta=float(y.cov(x) / varianza),
        r2=float(y.corr(x) ** 2),
        semanas=int(len(rendimientos)),
        indice=nombre_indice,
    )


def tasa_libre_desde_cierres(cierres: pd.Series) -> "float | None":
    """`^TNX` cotiza el rendimiento en puntos: 5,24 es un 5,24 %."""
    validos = pd.to_numeric(cierres, errors="coerce").dropna()
    if validos.empty:
        return None
    return float(validos.iloc[-1]) / 100


def tasa_efectiva_desde_estado(estado: "pd.DataFrame | None") -> "float | None":
    """La tasa efectiva más reciente con dato. yfinance ordena las columnas de
    la más reciente a la más antigua."""
    if estado is None or estado.empty or "Tax Rate For Calcs" not in estado.index:
        return None
    for valor in estado.loc["Tax Rate For Calcs"]:
        numero = _opcional(valor)
        if numero is not None:
            return numero
    return None


def consenso_desde_estimacion(
    estimacion: "pd.DataFrame | None", moneda_estados: str
) -> "float | None":
    """El crecimiento de ingresos que el consenso espera el próximo ejercicio.

    `+1y` y no `0y`, que suele estar ya medio publicado. Y sólo si viene en la
    moneda de los estados: en TSM, `revenue_estimate` viene en TWD y
    `earnings_estimate` en USD **en la misma consulta**, así que la moneda se
    comprueba fila a fila y no se supone.
    """
    if estimacion is None or estimacion.empty or "+1y" not in estimacion.index:
        return None
    fila = estimacion.loc["+1y"]
    if str(fila.get("currency", "")) != moneda_estados:
        return None
    return _opcional(fila.get("growth"))
```

- [ ] **Step 5: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_mercado.py -v`
Expected: 17 passed.

- [ ] **Step 6: Commit**

```bash
git add valoracion/mercado.py tests/test_valoracion_mercado.py tests/dobles_valoracion.py
git commit -m "feat: perfil, beta, tasa libre y consenso del valor intrinseco, sin red

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Mercado — descargas con caché y motivos con nombre

> **Ejecutada y superada.** Su revisión encontró que yfinance no lanza al fallar y una descarga vacía se guardaba como dato (ver `5cceb96` y `3728757`). Manda el código vivo.

**Files:**
- Modify: `valoracion/mercado.py` (añadir al final; y dos imports arriba)
- Test: `tests/test_valoracion_mercado_red.py` (sin marca `red`: la red se sustituye por dobles)

- [ ] **Step 1: Escribir los tests**

`tests/test_valoracion_mercado_red.py`:

```python
"""Las descargas, con `yf.Ticker` sustituido: sin red de verdad."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from valoracion import mercado

from tests.test_valoracion_mercado import INFO


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)


def _ticker(**atributos):
    doble = MagicMock()
    for nombre, valor in atributos.items():
        setattr(doble, nombre, valor)
    return doble


def test_el_perfil_se_descarga_y_se_reconstruye():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok"
    assert perfil.precio == 989.04


def test_un_ticker_sin_precio_dice_sin_precio():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={})):
        assert mercado.perfil("NADA") == (None, "sin_precio")


def test_sin_red_y_sin_cache_dice_sin_red():
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        assert mercado.perfil("MU") == (None, "sin_red")


def test_lo_guardado_vigente_no_vuelve_a_la_red():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        mercado.perfil("MU")
    # `assert_not_called` y no un `side_effect` que lance: `_traer` atrapa
    # cualquier excepción y caería a lo guardado, así que el test pasaría
    # también con la caché rota.
    with patch.object(mercado.yf, "Ticker") as fabrica:
        perfil, motivo = mercado.perfil("MU")
    fabrica.assert_not_called()
    assert motivo == "ok" and perfil.precio == 989.04


def test_si_la_red_falla_se_usa_lo_guardado_aunque_haya_caducado(monkeypatch):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        mercado.perfil("MU")
    monkeypatch.setitem(mercado.VALIDEZ, "perfil", timedelta(seconds=-1))
    with patch.object(mercado.yf, "Ticker", side_effect=OSError("sin red")):
        perfil, motivo = mercado.perfil("MU")
    assert motivo == "ok" and perfil.precio == 989.04


def test_la_tasa_libre_sale_del_tnx():
    cierres = pd.DataFrame({"Close": [5.1, 5.24]})
    doble = _ticker()
    doble.history.return_value = cierres
    with patch.object(mercado.yf, "Ticker", return_value=doble) as fabrica:
        tasa, motivo = mercado.tasa_libre()
    assert (tasa, motivo) == (pytest.approx(0.0524), "ok")
    fabrica.assert_called_with("^TNX")


def test_sin_tasa_libre_lo_dice():
    with patch.object(mercado.yf, "Ticker", side_effect=OSError):
        assert mercado.tasa_libre() == (None, "sin_tasa_libre")


def test_sin_regresion_posible_no_hay_beta_y_lo_dice():
    corto = pd.DataFrame(
        {"Close": range(1, 11)}, index=pd.date_range("2026-01-05", periods=10, freq="W-MON")
    )
    doble = _ticker()
    doble.history.return_value = corto
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.beta("NUEVA") == (None, "sin_regresion")


def test_la_tasa_efectiva_y_el_consenso_se_descargan():
    estado = pd.DataFrame({"2025": [0.19]}, index=["Tax Rate For Calcs"])
    estimacion = pd.DataFrame(
        {"growth": [0.1648], "currency": ["USD"]}, index=["+1y"]
    )
    doble = _ticker(income_stmt=estado, revenue_estimate=estimacion)
    with patch.object(mercado.yf, "Ticker", return_value=doble):
        assert mercado.tasa_efectiva("MU") == (0.19, "ok")
        assert mercado.consenso("MU", "USD") == (pytest.approx(0.1648), "ok")
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_mercado_red.py -v`
Expected: FAIL con `AttributeError: module 'valoracion.mercado' has no attribute 'RAIZ_CACHE'`.

- [ ] **Step 3: Implementar las descargas**

En `valoracion/mercado.py`, cambia el bloque de imports por:

```python
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from noticias import cache
from valoracion.criterio import BETA_SEMANAS, BETA_SEMANAS_MIN
```

Y añade al final del fichero:

```python
# --- Red ------------------------------------------------------------------------
#
# Cada función devuelve el dato y un motivo con nombre, como
# `seguimiento/banxico.py`: `"ok"`, `"sin_red"`, o por qué el dato no existe.

RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
INDICE = "^GSPC"
BONO_10 = "^TNX"

# El precio cambia en minutos; la tasa libre, la beta de dos años, la tasa
# efectiva anual y el consenso, en días. Generar quince candidatos dos veces en
# una tarde no tiene por qué repetir sesenta descargas.
VALIDEZ = {
    "perfil": timedelta(minutes=15),
    "tasa_libre": timedelta(days=1),
    "beta": timedelta(days=1),
    "tasa_efectiva": timedelta(days=1),
    "consenso": timedelta(days=1),
}


def _traer(fuente: str, clave: str, descargar) -> "tuple[dict | None, str]":
    """Lo guardado si está vigente; si no, la red; si la red falla, lo guardado.

    Lo guardado caducado se usa antes que nada porque estos datos envejecen
    despacio --una beta de dos años no cambia de un día a otro-- y el precio
    lleva su propia hora dentro (`Perfil.hora`), que es la que se enseña.
    """
    guardado = cache.leer(RAIZ_CACHE, fuente, clave, VALIDEZ[fuente])
    if guardado is not None and guardado.vigente and isinstance(guardado.datos, dict):
        return guardado.datos, "ok"
    try:
        datos = descargar()
    except Exception:
        # yfinance lanza de todo según qué falle --HTTPError, KeyError,
        # JSONDecodeError, ValueError, TypeError en una respuesta a medias-- y
        # ninguna de esas clases distingue algo que aquí importe: o hay dato o no.
        datos = None
    if isinstance(datos, dict):
        cache.guardar(RAIZ_CACHE, fuente, clave, datos)
        return datos, "ok"
    if guardado is not None and isinstance(guardado.datos, dict):
        return guardado.datos, "ok"
    return None, "sin_red"


def _reconstruir(tipo, datos: "dict | None"):
    """Un `TypeError` aquí es una caché de una versión anterior del tipo: se
    trata como si no hubiera dato, no se revienta."""
    if not isinstance(datos, dict):
        return None
    try:
        return tipo(**datos)
    except TypeError:
        return None


def perfil(ticker: str) -> "tuple[Perfil | None, str]":
    def descargar():
        encontrado = perfil_desde_info(ticker, yf.Ticker(ticker).info)
        return {"perfil": None if encontrado is None else asdict(encontrado)}

    datos, motivo = _traer("perfil", ticker, descargar)
    if datos is None:
        return None, motivo
    encontrado = _reconstruir(Perfil, datos.get("perfil"))
    return (encontrado, "ok") if encontrado is not None else (None, "sin_precio")


def tasa_libre() -> "tuple[float | None, str]":
    def descargar():
        cierres = yf.Ticker(BONO_10).history(period="5d")["Close"]
        return {"valor": tasa_libre_desde_cierres(cierres)}

    datos, _ = _traer("tasa_libre", BONO_10, descargar)
    if datos is None or datos.get("valor") is None:
        return None, "sin_tasa_libre"
    return float(datos["valor"]), "ok"


def beta(ticker: str, indice: str = INDICE) -> "tuple[Beta | None, str]":
    def descargar():
        activo = yf.Ticker(ticker).history(period="2y", interval="1wk")["Close"]
        referencia = yf.Ticker(indice).history(period="2y", interval="1wk")["Close"]
        encontrada = regresion_beta(activo, referencia, indice)
        return {"beta": None if encontrada is None else asdict(encontrada)}

    datos, motivo = _traer("beta", f"{ticker}|{indice}", descargar)
    if datos is None:
        return None, motivo
    encontrada = _reconstruir(Beta, datos.get("beta"))
    # `regresion_beta` devuelve None por historial corto, pero también por un
    # precio no positivo en la ventana o una varianza nula: no siempre es la
    # historia lo que falta.
    return (encontrada, "ok") if encontrada is not None else (None, "sin_regresion")


def tasa_efectiva(ticker: str) -> "tuple[float | None, str]":
    def descargar():
        return {"valor": tasa_efectiva_desde_estado(yf.Ticker(ticker).income_stmt)}

    datos, motivo = _traer("tasa_efectiva", ticker, descargar)
    if datos is None:
        return None, motivo
    return datos.get("valor"), "ok"


def consenso(ticker: str, moneda_estados: str) -> "tuple[float | None, str]":
    def descargar():
        estimacion = yf.Ticker(ticker).revenue_estimate
        return {"valor": consenso_desde_estimacion(estimacion, moneda_estados)}

    datos, motivo = _traer("consenso", f"{ticker}|{moneda_estados}", descargar)
    if datos is None:
        return None, motivo
    return datos.get("valor"), "ok"
```

- [ ] **Step 4: Pasar los tests de las dos tareas**

Run: `uv run pytest tests/test_valoracion_mercado.py tests/test_valoracion_mercado_red.py -v`
Expected: 26 passed.

- [ ] **Step 5: Commit**

```bash
git add valoracion/mercado.py tests/test_valoracion_mercado_red.py
git commit -m "feat: descargas del valor intrinseco con cache y motivos con nombre

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Supuestos

> **Ejecutada y superada.** Sus revisiones quitaron el `abs()` del gasto financiero, vaciaron `k_d` y `wacc` en financieras y separaron la fuente de `g_ref` (ver `b412eab`). Manda el código vivo.

**Files:**
- Create: `valoracion/supuestos.py`
- Test: `tests/test_valoracion_supuestos.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_valoracion_supuestos.py`:

```python
import math

import pytest

from valoracion.mercado import Beta
from valoracion.supuestos import (
    beta_ajustada,
    coste_capital,
    coste_deuda,
    crecimiento_perpetuo,
    crecimiento_ref,
    deducir,
    payout,
    roe_referencia,
    tasa_impositiva,
)

from tests.dobles_valoracion import ejercicio, fundamentos, perfil


def test_blume_ajusta_la_beta_de_la_regresion():
    s = beta_ajustada(Beta(bruta=1.5, r2=0.4, semanas=104, indice="^GSPC"))
    assert s.valor == pytest.approx(0.67 * 1.5 + 0.33)
    assert s.procedencia["fuente"] == "regresion"
    assert s.procedencia["semanas"] == 104


def test_sin_regresion_la_beta_es_uno_y_se_dice():
    s = beta_ajustada(None)
    assert s.valor == 1.0
    assert s.procedencia["fuente"] == "por_defecto"


@pytest.mark.parametrize(
    "tasa, pais, esperado, fuente",
    [
        (0.19, "United States", 0.19, "efectiva"),
        (0.50, "United States", 0.35, "efectiva"),
        (-0.10, "United States", 0.0, "efectiva"),
        (None, "United States", 0.21, "legal"),
        (None, "Mexico", 0.30, "legal"),
        (None, "Taiwan", 0.24, "legal"),
        (None, None, 0.24, "legal"),
    ],
)
def test_la_tasa_impositiva(tasa, pais, esperado, fuente):
    s = tasa_impositiva(tasa, pais)
    assert s.valor == pytest.approx(esperado)
    assert s.procedencia["fuente"] == fuente


@pytest.mark.parametrize(
    "intereses, esperado",
    [(10.0, 0.05), (2.0, 0.04), (40.0, 0.12)],
)
def test_el_coste_de_la_deuda_se_acota(intereses, esperado):
    f = fundamentos(
        ejercicios=[ejercicio(2026, gasto_financiero=intereses)], deuda_total=200.0
    )
    assert coste_deuda(f, r_f=0.04).valor == pytest.approx(esperado)


def test_sin_deuda_el_coste_de_la_deuda_es_la_tasa_libre():
    f = fundamentos(deuda_total=float("nan"))
    s = coste_deuda(f, r_f=0.04)
    assert s.valor == 0.04 and s.procedencia["fuente"] == "sin_dato"


def test_el_coste_de_capital_pondera_capital_y_deuda():
    s = coste_capital(k_e=0.10, k_d=0.05, t=0.20, capitalizacion=800.0, deuda=200.0)
    assert s.valor == pytest.approx(0.8 * 0.10 + 0.2 * 0.05 * 0.8)


def test_sin_deuda_declarada_el_coste_de_capital_es_el_del_capital():
    s = coste_capital(k_e=0.10, k_d=0.05, t=0.20, capitalizacion=800.0, deuda=float("nan"))
    assert s.valor == pytest.approx(0.10)
    assert s.procedencia["deuda_declarada"] is False


def _creciendo(ingresos):
    return fundamentos(
        ejercicios=[ejercicio(2026 - i, ingresos=v) for i, v in enumerate(ingresos)]
    )


def test_el_crecimiento_de_referencia_mezcla_historia_y_consenso():
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=0.20).valor == pytest.approx((0.10 + 0.20) / 2)


def test_sin_consenso_el_crecimiento_es_el_historico():
    f = _creciendo([1331.0, 1210.0, 1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.10)


def test_con_menos_anos_el_cagr_usa_los_que_hay():
    f = _creciendo([1100.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.10)


def test_el_crecimiento_de_referencia_se_acota():
    f = _creciendo([8000.0, 4000.0, 2000.0, 1000.0])
    assert crecimiento_ref(f, consenso=None).valor == pytest.approx(0.40)


def test_sin_historia_ni_consenso_no_hay_crecimiento():
    f = fundamentos(ejercicios=[ejercicio(2026)])
    assert crecimiento_ref(f, consenso=None).valor is None


def test_el_perpetuo_nunca_supera_la_tasa_libre():
    assert crecimiento_perpetuo("USD", r_f=0.05).valor == 0.025
    s = crecimiento_perpetuo("USD", r_f=0.02)
    assert s.valor == 0.02 and s.procedencia["fuente"] == "recortado_a_r_f"


def test_el_roe_de_referencia_es_la_mediana_anual():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, beneficio_neto=100.0, patrimonio_neto=1000.0),
            ejercicio(2025, beneficio_neto=150.0, patrimonio_neto=1000.0),
            ejercicio(2024, beneficio_neto=120.0, patrimonio_neto=1000.0),
        ]
    )
    assert roe_referencia(f).valor == pytest.approx(0.12)


def test_un_patrimonio_negativo_no_cuenta_para_el_roe():
    f = fundamentos(
        ejercicios=[ejercicio(2026, patrimonio_neto=-50.0), ejercicio(2025)]
    )
    assert roe_referencia(f).valor is None


def test_el_payout_se_acota_y_tiene_respaldo():
    assert payout(1.4).valor == 1.0
    assert payout(None).valor == 0.5
    assert payout(None).procedencia["fuente"] == "por_defecto"


def test_deducir_compone_el_capm_y_el_coste_de_capital():
    s = deducir(fundamentos(), perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=None)
    assert s.k_e.valor == pytest.approx(0.04 + 1.0 * 0.042)
    assert s.k_d.valor == pytest.approx(0.10)
    peso_capital = 1000.0 / 1200.0
    assert s.wacc.valor == pytest.approx(
        peso_capital * s.k_e.valor + (1 - peso_capital) * 0.10 * 0.75
    )
    assert s.g_ref.valor == pytest.approx(0.0)
    assert s.g_perpetuo.valor == 0.025
    assert s.roe_ref.valor == pytest.approx(0.12)
    assert s.payout.valor == 0.3
    assert s.prima.procedencia == {"fuente": "damodaran", "fecha": "2026-10-01"}
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_supuestos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.supuestos'`.

- [ ] **Step 3: Implementar**

`valoracion/supuestos.py`:

```python
"""Los supuestos de la valoración, cada uno con su procedencia.

La procedencia es **dato estructurado, no texto**
(`{"fuente": "regresion", "semanas": 104, ...}`), y la pantalla la traduce al
pintarla. Es la regla que dejó «La etiqueta de pantalla que se guardaba en
disco»: a un fichero de datos no se escribe nada cuyo valor sea una decisión de
redacción.

M no tiene forma de cambiar supuestos: en Revisar candidatos no hay
deslizadores. La función que aplica los cambios del usuario la añade N, que es
quien la usa.
"""

import math
from dataclasses import dataclass

import numpy as np

from valoracion.criterio import (
    BETA_SEMANAS_MIN,
    BLUME,
    COSTE_DEUDA_PRIMA_MAXIMA,
    CRECIMIENTO_PERPETUO,
    CRECIMIENTO_REF_ANOS,
    CRECIMIENTO_REF_TOPES,
    MIN_ANOS_HISTORIA,
    PAYOUT_SIN_DATO,
    PRIMA_RIESGO,
    PRIMA_RIESGO_FECHA,
    TASA_EFECTIVA_TOPES,
    TASA_LEGAL,
)
from valoracion.fundamentos import Fundamentos
from valoracion.mercado import Beta, Perfil

_PAISES = {"United States": "US", "Mexico": "MX"}


@dataclass(frozen=True)
class Supuesto:
    valor: "float | None"
    procedencia: dict


@dataclass(frozen=True)
class Supuestos:
    r_f: Supuesto
    beta: Supuesto
    prima: Supuesto
    k_e: Supuesto
    k_d: Supuesto
    t: Supuesto
    wacc: Supuesto
    g_ref: Supuesto
    g_perpetuo: Supuesto
    roe_ref: Supuesto
    payout: Supuesto


def _acotar(valor: float, limites: "tuple[float, float]") -> float:
    bajo, alto = limites
    return min(max(valor, bajo), alto)


def _redondeo(valor: "float | None") -> "float | None":
    return None if valor is None or not math.isfinite(valor) else round(float(valor), 4)


def beta_ajustada(beta: "Beta | None") -> Supuesto:
    """Blume sobre la regresión: la beta medida tiende a 1 con el tiempo."""
    if beta is None or beta.semanas < BETA_SEMANAS_MIN:
        return Supuesto(1.0, {"fuente": "por_defecto"})
    a, b = BLUME
    return Supuesto(
        a * beta.bruta + b,
        {
            "fuente": "regresion",
            "indice": beta.indice,
            "semanas": beta.semanas,
            "r2": _redondeo(beta.r2),
            "bruta": _redondeo(beta.bruta),
        },
    )


def tasa_impositiva(tasa: "float | None", pais: "str | None") -> Supuesto:
    if tasa is not None and math.isfinite(tasa):
        return Supuesto(
            _acotar(tasa, TASA_EFECTIVA_TOPES),
            {"fuente": "efectiva", "bruta": _redondeo(tasa)},
        )
    clave = _PAISES.get(pais or "", "otros")
    return Supuesto(TASA_LEGAL[clave], {"fuente": "legal", "pais": clave})


def coste_deuda(fundamentos: Fundamentos, r_f: float) -> Supuesto:
    """Gasto financiero entre deuda, sin bajar de la tasa libre ni subir como un bono basura."""
    deuda = fundamentos.deuda_total
    intereses = fundamentos.ultimo.gasto_financiero
    if not deuda > 0 or not math.isfinite(intereses):
        return Supuesto(r_f, {"fuente": "sin_dato"})
    bruto = abs(intereses) / deuda
    return Supuesto(
        _acotar(bruto, (r_f, r_f + COSTE_DEUDA_PRIMA_MAXIMA)),
        {"fuente": "gasto_entre_deuda", "bruto": _redondeo(bruto)},
    )


def coste_capital(
    k_e: float, k_d: float, t: float, capitalizacion: float, deuda: float
) -> Supuesto:
    """Capital a valor de mercado y deuda a valor contable.

    `capitalizacion` va en la moneda del precio y `deuda` en la de los estados.
    En M coinciden; N convierte antes de llamar.
    """
    declarada = math.isfinite(deuda)
    d = deuda if declarada and deuda > 0 else 0.0
    peso_deuda = d / (capitalizacion + d)
    return Supuesto(
        (1 - peso_deuda) * k_e + peso_deuda * k_d * (1 - t),
        {
            "fuente": "wacc",
            "peso_deuda": _redondeo(peso_deuda),
            "deuda_declarada": declarada,
        },
    )


def _cagr(fundamentos: Fundamentos) -> "float | None":
    anos = min(CRECIMIENTO_REF_ANOS, len(fundamentos.ejercicios) - 1)
    if anos < 1:
        return None
    final = fundamentos.ejercicios[0].ingresos
    inicial = fundamentos.ejercicios[anos].ingresos
    if not (final > 0 and inicial > 0):
        return None
    return (final / inicial) ** (1 / anos) - 1


def crecimiento_ref(fundamentos: Fundamentos, consenso: "float | None") -> Supuesto:
    historico = _cagr(fundamentos)
    partes = [v for v in (historico, consenso) if v is not None and math.isfinite(v)]
    if not partes:
        return Supuesto(None, {"fuente": "sin_dato"})
    bruto = sum(partes) / len(partes)
    return Supuesto(
        _acotar(bruto, CRECIMIENTO_REF_TOPES),
        {
            "fuente": "historia_y_consenso",
            "historico": _redondeo(historico),
            "consenso": _redondeo(consenso),
            "bruto": _redondeo(bruto),
        },
    )


def crecimiento_perpetuo(moneda: str, r_f: float) -> Supuesto:
    """Nunca por encima de la tasa libre: una empresa que crece para siempre más
    que la economía acaba siendo la economía."""
    base = CRECIMIENTO_PERPETUO[moneda]
    if base > r_f:
        return Supuesto(r_f, {"fuente": "recortado_a_r_f", "base": base})
    return Supuesto(base, {"fuente": "criterio", "moneda": moneda})


def roe_referencia(fundamentos: Fundamentos) -> Supuesto:
    """La mediana del ROE anual. No es el KPI `roe` del panel, que es trimestral."""
    roes = [
        e.beneficio_neto / e.patrimonio_neto
        for e in fundamentos.ejercicios
        if math.isfinite(e.beneficio_neto) and e.patrimonio_neto > 0
    ]
    if len(roes) < MIN_ANOS_HISTORIA:
        return Supuesto(None, {"fuente": "sin_dato"})
    return Supuesto(float(np.median(roes)), {"fuente": "mediana_historica", "anos": len(roes)})


def payout(valor: "float | None") -> Supuesto:
    if valor is not None and math.isfinite(valor):
        return Supuesto(_acotar(valor, (0.0, 1.0)), {"fuente": "yfinance"})
    return Supuesto(PAYOUT_SIN_DATO, {"fuente": "por_defecto"})


def deducir(
    fundamentos: Fundamentos,
    perfil: Perfil,
    r_f: float,
    beta: "Beta | None",
    tasa: "float | None",
    consenso: "float | None",
) -> Supuestos:
    """Los supuestos del programa. Siempre los mismos para los mismos datos."""
    b = beta_ajustada(beta)
    k_e = r_f + b.valor * PRIMA_RIESGO
    k_d = coste_deuda(fundamentos, r_f)
    t = tasa_impositiva(tasa, perfil.pais)
    return Supuestos(
        r_f=Supuesto(r_f, {"fuente": "tesoro_10", "serie": "^TNX"}),
        beta=b,
        prima=Supuesto(PRIMA_RIESGO, {"fuente": "damodaran", "fecha": PRIMA_RIESGO_FECHA}),
        k_e=Supuesto(k_e, {"fuente": "capm"}),
        k_d=k_d,
        t=t,
        wacc=coste_capital(
            k_e, k_d.valor, t.valor, perfil.capitalizacion, fundamentos.deuda_total
        ),
        g_ref=crecimiento_ref(fundamentos, consenso),
        g_perpetuo=crecimiento_perpetuo(fundamentos.moneda, r_f),
        roe_ref=roe_referencia(fundamentos),
        payout=payout(perfil.payout),
    )
```

- [ ] **Step 4: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_supuestos.py -v`
Expected: 25 passed.

- [ ] **Step 5: Commit**

```bash
git add valoracion/supuestos.py tests/test_valoracion_supuestos.py
git commit -m "feat: supuestos del valor intrinseco con su procedencia como dato

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: DCF e inverso

**Files:**
- Create: `valoracion/dcf.py`
- Create: `valoracion/inverso.py`
- Test: `tests/test_valoracion_dcf.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_valoracion_dcf.py`:

```python
import pytest

from valoracion.dcf import (
    Datos,
    crecimientos,
    margen_fcff,
    valor_empresa,
    valor_por_accion,
)
from valoracion.inverso import ABAJO, ARRIBA, crecimiento_implicito

from tests.dobles_valoracion import ejercicio, fundamentos

DATOS = Datos(
    ingresos=1000.0,
    margen=0.15,
    wacc=0.09,
    g_perpetuo=0.025,
    deuda=0.0,
    efectivo=0.0,
    acciones=10.0,
)


def test_cinco_anos_altos_y_cinco_de_convergencia():
    g = crecimientos(0.20, 0.02)
    assert len(g) == 10
    assert g[:5] == [0.20] * 5
    assert g[5] == pytest.approx(0.164)
    assert g[9] == pytest.approx(0.02)


def test_con_crecimiento_constante_el_dcf_es_gordon():
    # Referencia positiva: una perpetuidad creciente es una suma geométrica, y
    # el DCF de diez años más valor terminal tiene que darla exacta.
    flujo_1 = 1000.0 * 1.03 * 0.10
    assert valor_empresa(1000.0, 0.10, 0.03, 0.03, 0.09) == pytest.approx(
        flujo_1 / (0.09 - 0.03), rel=1e-12
    )


def test_sin_holgura_gordon_no_hay_valor():
    assert valor_empresa(1000.0, 0.10, 0.05, 0.03, 0.035) is None


def test_el_valor_por_accion_resta_deuda_y_suma_efectivo():
    datos = Datos(**{**DATOS.__dict__, "deuda": 300.0, "efectivo": 100.0})
    ve = valor_empresa(1000.0, 0.15, 0.10, 0.025, 0.09)
    assert valor_por_accion(datos, 0.10) == pytest.approx((ve - 300.0 + 100.0) / 10.0)


def test_otro_coste_de_capital_sustituye_al_de_los_datos():
    assert valor_por_accion(DATOS, 0.10, wacc=0.10) < valor_por_accion(DATOS, 0.10)


def test_contraste_contra_numpy_financial():
    npf = pytest.importorskip("numpy_financial")
    ingresos, flujos = 1000.0, []
    for g in crecimientos(0.12, 0.025):
        ingresos *= 1 + g
        flujos.append(ingresos * 0.15)
    terminal = flujos[-1] * 1.025 / (0.09 - 0.025)
    esperado = npf.npv(0.09, [0.0, *flujos[:-1], flujos[-1] + terminal])
    assert valor_empresa(1000.0, 0.15, 0.12, 0.025, 0.09) == pytest.approx(esperado)


def test_el_margen_de_flujo_libre_suma_los_intereses_despues_de_impuestos():
    f = fundamentos()
    assert margen_fcff(f, t=0.25) == pytest.approx((300 - 100 + 20 * 0.75) / 1000)


def test_el_margen_es_la_mediana_de_los_anos():
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, flujo_operativo=300.0),
            ejercicio(2025, flujo_operativo=900.0),
            ejercicio(2024, flujo_operativo=200.0),
        ]
    )
    assert margen_fcff(f, t=0.25) == pytest.approx((300 - 100 + 15) / 1000)


def test_con_un_solo_ano_no_hay_margen():
    assert margen_fcff(fundamentos(ejercicios=[ejercicio(2026)]), t=0.25) is None


def test_un_ano_sin_ingresos_no_cuenta():
    f = fundamentos(ejercicios=[ejercicio(2026), ejercicio(2025, ingresos=0.0)])
    assert margen_fcff(f, t=0.25) is None


def test_el_inverso_devuelve_el_crecimiento_de_partida():
    precio = valor_por_accion(DATOS, 0.12)
    implicito = crecimiento_implicito(DATOS, precio)
    assert implicito.valor == pytest.approx(0.12, abs=1e-6)
    assert implicito.fuera_de_limites is None


def test_un_precio_inalcanzable_queda_por_arriba():
    implicito = crecimiento_implicito(DATOS, 1e12)
    assert implicito.valor is None and implicito.fuera_de_limites == ARRIBA


def test_un_precio_minimo_queda_por_abajo():
    implicito = crecimiento_implicito(DATOS, 1e-9)
    assert implicito.valor is None and implicito.fuera_de_limites == ABAJO
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_dcf.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.dcf'`.

- [ ] **Step 3: Implementar el DCF**

`valoracion/dcf.py`:

```python
"""El DCF de flujo de caja libre en dos etapas. Aritmética pura, sin red.

Se proyectan los ingresos y no el flujo libre: el flujo libre baila con cada
ciclo de inversión --en MU, un año de capex fuerte lo hunde y el siguiente se
dispara--, y proyectar desde uno u otro daría valores distintos para el mismo
negocio. El margen normalizado es la mediana de los años disponibles.
"""

import math
from dataclasses import dataclass

import numpy as np

from valoracion.criterio import (
    ANOS_ALTO_CRECIMIENTO,
    ANOS_CONVERGENCIA,
    HOLGURA_GORDON,
    MIN_ANOS_HISTORIA,
)
from valoracion.fundamentos import Fundamentos

ANOS = ANOS_ALTO_CRECIMIENTO + ANOS_CONVERGENCIA


@dataclass(frozen=True)
class Datos:
    """Todo lo que el DCF necesita, en la moneda de los estados."""

    ingresos: float
    margen: float
    wacc: float
    g_perpetuo: float
    deuda: float
    efectivo: float
    acciones: float


@dataclass(frozen=True)
class Escenarios:
    """Valor por acción en tres escenarios. `None` donde no se cumple Gordon."""

    pesimista: "float | None"
    base: "float | None"
    optimista: "float | None"


def crecimientos(g: float, g_perpetuo: float) -> list[float]:
    """`g` cinco años y luego en línea recta hasta `g_perpetuo`, al que llega en el año diez."""
    convergencia = [
        g + (g_perpetuo - g) * k / ANOS_CONVERGENCIA
        for k in range(1, ANOS_CONVERGENCIA + 1)
    ]
    return [g] * ANOS_ALTO_CRECIMIENTO + convergencia


def valor_empresa(
    ingresos: float, margen: float, g: float, g_perpetuo: float, wacc: float
) -> "float | None":
    """Flujos de los años 1 a 10 más el valor terminal de Gordon, a fin de año.

    `None` si el coste de capital no supera al crecimiento perpetuo en al menos
    `HOLGURA_GORDON`: el valor terminal explota y cualquier número sería un
    artefacto. No se recorta el coste de capital para que cuadre: eso sería
    cambiar el escenario sin decirlo.
    """
    if wacc - g_perpetuo < HOLGURA_GORDON:
        return None
    total = 0.0
    flujo = 0.0
    for ano, crecimiento in enumerate(crecimientos(g, g_perpetuo), start=1):
        ingresos *= 1 + crecimiento
        flujo = ingresos * margen
        total += flujo / (1 + wacc) ** ano
    terminal = flujo * (1 + g_perpetuo) / (wacc - g_perpetuo)
    return total + terminal / (1 + wacc) ** ANOS


def valor_por_accion(datos: Datos, g: float, wacc: "float | None" = None) -> "float | None":
    """Del valor de la empresa al de cada acción: menos deuda, más efectivo.

    `datos.acciones` es capitalización ÷ precio, el recuento en la base del
    precio. Con el de los estados, una ADR saldría con el valor multiplicado o
    dividido por su ratio.
    """
    coste = datos.wacc if wacc is None else wacc
    empresa = valor_empresa(datos.ingresos, datos.margen, g, datos.g_perpetuo, coste)
    if empresa is None:
        return None
    return (empresa - datos.deuda + datos.efectivo) / datos.acciones


def margen_fcff(fundamentos: Fundamentos, t: float) -> "float | None":
    """La mediana del margen de flujo libre para la empresa de los años con dato.

    Flujo libre para la empresa = flujo operativo − capex + intereses × (1 − t):
    el flujo operativo ya descontó los intereses, y el DCF descuenta al coste de
    capital de toda la empresa, deuda incluida.
    """
    margenes = []
    for e in fundamentos.ejercicios:
        if not e.ingresos > 0:
            continue
        if not (math.isfinite(e.flujo_operativo) and math.isfinite(e.capex)):
            continue
        # Un gasto financiero negativo es ingreso financiero neto (DIS, FTV en la
        # revisión de la Task 5): sumarlo con `abs` lo trataría como un coste.
        intereses = (
            e.gasto_financiero
            if math.isfinite(e.gasto_financiero) and e.gasto_financiero > 0
            else 0.0
        )
        margenes.append((e.flujo_operativo - e.capex + intereses * (1 - t)) / e.ingresos)
    if len(margenes) < MIN_ANOS_HISTORIA:
        return None
    return float(np.median(margenes))
```

- [ ] **Step 4: Implementar el inverso**

`valoracion/inverso.py`:

```python
"""El DCF leído al revés: qué crecimiento hace falta para justificar el precio.

Es la lectura más sólida de las cuatro, porque no hay que suponer el
crecimiento: se calcula. Con margen de flujo libre positivo el valor crece con
`g`, así que una bisección converge.
"""

from dataclasses import dataclass

from valoracion.criterio import INVERSO_LIMITES
from valoracion.dcf import Datos, valor_por_accion

ARRIBA = "arriba"
ABAJO = "abajo"


@dataclass(frozen=True)
class Implicito:
    """El valor que iguala el precio, o por qué lado se sale de los límites."""

    valor: "float | None"
    fuera_de_limites: "str | None"


def biseccion(funcion, objetivo: float, limites, tolerancia: float = 1e-9) -> Implicito:
    """El `x` en `limites` con `funcion(x) == objetivo`, para una función creciente."""
    bajo, alto = limites
    en_bajo, en_alto = funcion(bajo), funcion(alto)
    if en_bajo is None or en_alto is None:
        return Implicito(None, None)
    if en_alto < objetivo:
        return Implicito(None, ARRIBA)
    if en_bajo > objetivo:
        return Implicito(None, ABAJO)
    for _ in range(200):
        medio = (bajo + alto) / 2
        if funcion(medio) < objetivo:
            bajo = medio
        else:
            alto = medio
        if alto - bajo < tolerancia:
            break
    return Implicito((bajo + alto) / 2, None)


def crecimiento_implicito(datos: Datos, precio: float) -> Implicito:
    return biseccion(lambda g: valor_por_accion(datos, g), precio, INVERSO_LIMITES)
```

- [ ] **Step 5: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_dcf.py -v`
Expected: 12 passed, 1 skipped (`numpy_financial` no está instalado; es el mismo caso que `test_contraste_contra_numpy_financial` de Seguimiento).

- [ ] **Step 6: Commit**

```bash
git add valoracion/dcf.py valoracion/inverso.py tests/test_valoracion_dcf.py
git commit -m "feat: DCF en dos etapas y su inverso, con la identidad de Gordon como referencia

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Valor sin crecimiento y beneficio residual

**Files:**
- Create: `valoracion/epv.py`
- Create: `valoracion/residual.py`
- Test: `tests/test_valoracion_epv_residual.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_valoracion_epv_residual.py`:

```python
import pytest

from valoracion.epv import epv_por_accion, margen_operativo, parte_crecimiento
from valoracion.inverso import ARRIBA
from valoracion.residual import (
    DatosResidual,
    rentabilidades,
    roe_implicito,
    valor_por_accion,
    valor_residual,
)

from tests.dobles_valoracion import ejercicio, fundamentos


def test_el_epv_capitaliza_el_beneficio_operativo_sin_crecer():
    # Margen operativo 0,20 sobre ingresos de 1.000: 200 × 0,75 / 0,10 = 1.500,
    # menos 100 de deuda y más 50 de efectivo, entre 10 acciones.
    valor, motivo = epv_por_accion(fundamentos(), t=0.25, wacc=0.10, deuda=100.0, efectivo=50.0, acciones=10.0)
    assert valor == pytest.approx(145.0)
    assert motivo is None


def test_con_beneficio_operativo_negativo_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, beneficio_operativo=-10.0) for i in range(3)])
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "ebit_negativo")


def test_el_margen_operativo_es_agregado_y_no_la_mediana():
    # Ingresos 1.000, 100 y 100 con márgenes del 30 %, 5 % y 5 %: la mediana
    # sería 0,05 y el agregado (300 + 5 + 5) / 1.200.
    f = fundamentos(
        ejercicios=[
            ejercicio(2026, ingresos=1000.0, beneficio_operativo=300.0),
            ejercicio(2025, ingresos=100.0, beneficio_operativo=5.0),
            ejercicio(2024, ingresos=100.0, beneficio_operativo=5.0),
        ]
    )
    assert margen_operativo(f) == pytest.approx(310.0 / 1200.0)


def test_sin_anos_suficientes_no_hay_epv():
    f = fundamentos(ejercicios=[ejercicio(2026)])
    assert margen_operativo(f) is None
    assert epv_por_accion(f, 0.25, 0.10, 0.0, 0.0, 10.0) == (None, "sin_historia")


def test_la_parte_del_precio_que_es_crecimiento():
    assert parte_crecimiento(145.0, 200.0) == pytest.approx(0.275)
    assert parte_crecimiento(-5.0, 200.0) is None


def test_el_roe_converge_al_coste_del_capital_en_diez_anos():
    roes = rentabilidades(0.20, 0.10)
    assert len(roes) == 10
    assert roes[0] == pytest.approx(0.20)
    assert roes[-1] == pytest.approx(0.10)


def test_con_roe_igual_al_coste_el_valor_es_el_contable():
    # Referencia positiva: sin exceso de rentabilidad no hay nada que sumar.
    assert valor_residual(1000.0, 0.10, 0.10, 0.4) == pytest.approx(1000.0, rel=1e-12)


def test_mas_rentabilidad_mas_valor():
    assert valor_residual(1000.0, 0.15, 0.10, 0.4) > valor_residual(1000.0, 0.12, 0.10, 0.4) > 1000.0


DATOS = DatosResidual(patrimonio=1000.0, k_e=0.09, payout=0.4, acciones=10.0)


def test_el_valor_por_accion_reparte_entre_las_acciones():
    assert valor_por_accion(DATOS, 0.09) == pytest.approx(100.0)


def test_un_coste_del_capital_no_positivo_no_da_valor():
    assert valor_por_accion(DATOS, 0.10, k_e=0.0) is None


def test_el_roe_implicito_devuelve_el_de_partida():
    precio = valor_por_accion(DATOS, 0.14)
    assert roe_implicito(DATOS, precio).valor == pytest.approx(0.14, abs=1e-6)


def test_un_precio_inalcanzable_exige_mas_roe_del_limite():
    assert roe_implicito(DATOS, 1e9).fuera_de_limites == ARRIBA
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_epv_residual.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.epv'`.

- [ ] **Step 3: Implementar el EPV**

`valoracion/epv.py`:

```python
"""Valor sin crecimiento (EPV de Greenwald): lo que vale el negocio si deja de crecer mañana.

Greenwald ajusta además la diferencia entre la amortización y el capex de
mantenimiento. Aquí no se hace, porque ninguna fuente separa el capex de
mantenimiento del de expansión, y la pantalla lo dice.
"""

import math

from valoracion.criterio import MIN_ANOS_HISTORIA
from valoracion.fundamentos import Fundamentos


def margen_operativo(fundamentos: Fundamentos) -> "float | None":
    """El margen operativo agregado: suma de beneficios operativos entre suma de ingresos.

    Agregado y no mediana, igual que `dcf.margen_fcff` y por la misma razón
    (decisión del 2026-10-12): la mediana pesaba un año pequeño del pasado lo
    mismo que el actual en una empresa que ha crecido mucho.
    """
    validos = [
        e for e in fundamentos.ejercicios
        if e.ingresos > 0 and math.isfinite(e.beneficio_operativo)
    ]
    if len(validos) < MIN_ANOS_HISTORIA:
        return None
    return sum(e.beneficio_operativo for e in validos) / sum(e.ingresos for e in validos)


def epv_por_accion(
    fundamentos: Fundamentos,
    t: float,
    wacc: float,
    deuda: float,
    efectivo: float,
    acciones: float,
) -> "tuple[float | None, str | None]":
    margen = margen_operativo(fundamentos)
    if margen is None:
        return None, "sin_historia"
    operativo = margen * fundamentos.ultimo.ingresos
    if not operativo > 0:
        return None, "ebit_negativo"
    empresa = operativo * (1 - t) / wacc
    return (empresa - deuda + efectivo) / acciones, None


def parte_crecimiento(epv: float, precio: float) -> "float | None":
    """Qué fracción del precio es apuesta por el crecimiento: 1 − EPV / precio."""
    if not (epv > 0 and precio > 0):
        return None
    return 1 - epv / precio
```

- [ ] **Step 4: Implementar el beneficio residual**

`valoracion/residual.py`:

```python
"""Beneficio residual, para bancos y aseguradoras.

El flujo de caja libre de un banco no significa nada: prestar es su operación,
no una inversión. Lo que se valora es cuánto rinde su patrimonio por encima de
lo que cuesta. El ROE va desde el de partida hasta el coste del capital en diez
años, en línea recta, y después el exceso es cero: no hay valor terminal aparte.
"""

from dataclasses import dataclass

from valoracion.criterio import INVERSO_ROE_LIMITES

# El mismo horizonte que el DCF, importado y no recalculado: dos copias de una
# suma se separan igual que dos de un número.
from valoracion.dcf import ANOS
from valoracion.inverso import Implicito, biseccion


@dataclass(frozen=True)
class DatosResidual:
    patrimonio: float
    k_e: float
    payout: float
    acciones: float


def rentabilidades(roe_ini: float, k_e: float) -> list[float]:
    return [roe_ini + (k_e - roe_ini) * (ano - 1) / (ANOS - 1) for ano in range(1, ANOS + 1)]


def valor_residual(patrimonio: float, roe_ini: float, k_e: float, payout: float) -> float:
    """Patrimonio más el valor presente del exceso de rentabilidad de cada año.

    El patrimonio crece con lo que se retiene: `(1 + ROE × (1 − payout))`.
    """
    valor = patrimonio
    libros = patrimonio
    for ano, roe in enumerate(rentabilidades(roe_ini, k_e), start=1):
        valor += (roe - k_e) * libros / (1 + k_e) ** ano
        libros *= 1 + roe * (1 - payout)
    return valor


def valor_por_accion(
    datos: DatosResidual, roe_ini: float, k_e: "float | None" = None
) -> "float | None":
    coste = datos.k_e if k_e is None else k_e
    if not coste > 0:
        return None
    return valor_residual(datos.patrimonio, roe_ini, coste, datos.payout) / datos.acciones


def roe_implicito(datos: DatosResidual, precio: float) -> Implicito:
    """El ROE de partida que el precio exige."""
    return biseccion(lambda roe: valor_por_accion(datos, roe), precio, INVERSO_ROE_LIMITES)
```

- [ ] **Step 5: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_epv_residual.py -v`
Expected: 12 passed.

- [ ] **Step 6: Commit**

```bash
git add valoracion/epv.py valoracion/residual.py tests/test_valoracion_epv_residual.py
git commit -m "feat: valor sin crecimiento y beneficio residual con sus identidades

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Los tres votos y el veredicto

**Files:**
- Create: `valoracion/votos.py`
- Test: `tests/test_valoracion_votos.py`

- [ ] **Step 1: Escribir los tests, con la tabla entera del veredicto**

`tests/test_valoracion_votos.py`:

```python
import pytest

from valoracion.inverso import ABAJO, ARRIBA, Implicito
from valoracion.votos import (
    BARATA,
    CARA,
    NEUTRA,
    NO_APLICA,
    Voto,
    margen_voto,
    veredicto,
    voto_epv,
    voto_implicito,
    voto_pares,
)


def test_el_margen_es_la_mitad_de_la_referencia_con_un_suelo():
    assert margen_voto(0.22, 0.05) == pytest.approx(0.11)
    assert margen_voto(0.05, 0.05) == pytest.approx(0.05)
    assert margen_voto(-0.04, 0.05) == pytest.approx(0.05)


@pytest.mark.parametrize(
    "implicito, esperado",
    [
        (Implicito(0.38, None), CARA),
        (Implicito(0.30, None), NEUTRA),
        (Implicito(0.12, None), NEUTRA),
        (Implicito(0.10, None), BARATA),
        (Implicito(None, ARRIBA), CARA),
        (Implicito(None, ABAJO), BARATA),
    ],
)
def test_el_voto_de_flujos(implicito, esperado):
    assert voto_implicito(implicito, referencia=0.22, margen=0.11).voto == esperado


def test_un_implicito_sin_valor_ni_limite_no_aplica():
    assert voto_implicito(Implicito(None, None), 0.22, 0.11) == Voto(NO_APLICA, "sin_historia")


def test_el_epv_vota_barata_si_el_precio_esta_por_debajo():
    assert voto_epv(epv=1000.0, precio=989.0).voto == BARATA


@pytest.mark.parametrize("precio", [411.0, 989.0, 1e9])
def test_el_epv_nunca_vota_cara(precio):
    # Pagar por el crecimiento no es estar cara: casi todo el S&P 500 cotiza
    # por encima de lo que valdría si dejara de crecer.
    assert voto_epv(epv=410.0, precio=precio).voto == NEUTRA


@pytest.mark.parametrize(
    "pilar, esperado",
    [(0.8, BARATA), (0.5, BARATA), (0.2, NEUTRA), (-0.49, NEUTRA), (-0.5, CARA), (-2.0, CARA)],
)
def test_el_voto_de_pares(pilar, esperado):
    assert voto_pares(pilar).voto == esperado


@pytest.mark.parametrize("pilar", [None, float("nan")])
def test_sin_pilar_los_pares_no_aplican(pilar):
    assert voto_pares(pilar) == Voto(NO_APLICA, "sin_pares")


_CLAVE = {"B": BARATA, "N": NEUTRA, "C": CARA, "X": NO_APLICA}

# La regla del spec, escrita a mano para las 64 combinaciones. Algunas no se
# dan en la práctica --el voto del medio es el EPV, que nunca dice «cara»--
# pero la regla se prueba como tal, no sólo en los casos que hoy ocurren.
TABLA = [
    ("BBB", "infravalorada"), ("BBN", "infravalorada"), ("BBC", "mixtas"), ("BBX", "infravalorada"),
    ("BNB", "infravalorada"), ("BNN", "en_rango"), ("BNC", "mixtas"), ("BNX", "en_rango"),
    ("BCB", "mixtas"), ("BCN", "mixtas"), ("BCC", "mixtas"), ("BCX", "mixtas"),
    ("BXB", "infravalorada"), ("BXN", "en_rango"), ("BXC", "mixtas"), ("BXX", "sin_datos"),
    ("NBB", "infravalorada"), ("NBN", "en_rango"), ("NBC", "mixtas"), ("NBX", "en_rango"),
    ("NNB", "en_rango"), ("NNN", "en_rango"), ("NNC", "en_rango"), ("NNX", "en_rango"),
    ("NCB", "mixtas"), ("NCN", "en_rango"), ("NCC", "sobrevalorada"), ("NCX", "en_rango"),
    ("NXB", "en_rango"), ("NXN", "en_rango"), ("NXC", "en_rango"), ("NXX", "sin_datos"),
    ("CBB", "mixtas"), ("CBN", "mixtas"), ("CBC", "mixtas"), ("CBX", "mixtas"),
    ("CNB", "mixtas"), ("CNN", "en_rango"), ("CNC", "sobrevalorada"), ("CNX", "en_rango"),
    ("CCB", "mixtas"), ("CCN", "sobrevalorada"), ("CCC", "sobrevalorada"), ("CCX", "sobrevalorada"),
    ("CXB", "mixtas"), ("CXN", "en_rango"), ("CXC", "sobrevalorada"), ("CXX", "sin_datos"),
    ("XBB", "infravalorada"), ("XBN", "en_rango"), ("XBC", "mixtas"), ("XBX", "sin_datos"),
    ("XNB", "en_rango"), ("XNN", "en_rango"), ("XNC", "en_rango"), ("XNX", "sin_datos"),
    ("XCB", "mixtas"), ("XCN", "en_rango"), ("XCC", "sobrevalorada"), ("XCX", "sin_datos"),
    ("XXB", "sin_datos"), ("XXN", "sin_datos"), ("XXC", "sin_datos"), ("XXX", "sin_datos"),
]


def test_la_tabla_cubre_las_64_combinaciones():
    assert len({combinacion for combinacion, _ in TABLA}) == 64


@pytest.mark.parametrize("combinacion, esperado", TABLA)
def test_el_veredicto(combinacion, esperado):
    votos = [Voto(_CLAVE[letra]) for letra in combinacion]
    assert veredicto(votos) == esperado
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_votos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.votos'`.

- [ ] **Step 3: Implementar**

`valoracion/votos.py`:

```python
"""Los tres votos y el veredicto.

Cuatro lecturas y tres votos, no cuatro: el DCF y su inverso son la misma
ecuación leída en las dos direcciones, y si votaran por separado una sola
lectura contaría dos veces. El voto de flujos lo da el inverso; el rango del
DCF es su contexto.
"""

import math
from dataclasses import dataclass

from valoracion.criterio import MIN_VOTOS, UMBRAL_PARES
from valoracion.inverso import ABAJO, ARRIBA, Implicito

BARATA = "barata"
NEUTRA = "neutra"
CARA = "cara"
NO_APLICA = "no_aplica"

VEREDICTOS = ("infravalorada", "sobrevalorada", "mixtas", "en_rango", "sin_datos")

# Todas las claves de motivo que este paquete puede escribir. La pantalla tiene
# que tener una etiqueta para cada una, y un test lo comprueba.
MOTIVOS = frozenset(
    {
        "quema_caja",
        "ebit_negativo",
        "sin_historia",
        "wacc_bajo_crecimiento",
        "sin_pares",
        "sin_precio",
        "sin_tasa_libre",
        "financiera",
        "patrimonio_negativo",
        "sin_estados",
        "error_interno",
    }
)


@dataclass(frozen=True)
class Voto:
    voto: str
    motivo: "str | None" = None


def margen_voto(referencia: float, minimo: float) -> float:
    """El mayor entre `minimo` y la mitad de la referencia.

    Con un crecimiento de referencia del 22 % son ±11 puntos; con un 5 %, ±5. El
    mismo margen abre los escenarios pesimista y optimista, así que el rango del
    DCF y el voto de flujos dicen lo mismo con dos dibujos.
    """
    return max(minimo, 0.5 * abs(referencia))


def voto_implicito(implicito: Implicito, referencia: float, margen: float) -> Voto:
    if implicito.fuera_de_limites == ARRIBA:
        return Voto(CARA)
    if implicito.fuera_de_limites == ABAJO:
        return Voto(BARATA)
    if implicito.valor is None:
        return Voto(NO_APLICA, "sin_historia")
    if implicito.valor > referencia + margen:
        return Voto(CARA)
    if implicito.valor < referencia - margen:
        return Voto(BARATA)
    return Voto(NEUTRA)


def voto_epv(epv: float, precio: float) -> Voto:
    """Nunca «cara», a propósito: pagar por el crecimiento no es estar cara.

    La consecuencia es que «sobrevalorada» exige que coincidan flujos y pares:
    cara frente a sus propios números y frente a su sector.
    """
    return Voto(BARATA) if precio < epv else Voto(NEUTRA)


def voto_pares(pilar: "float | None") -> Voto:
    """El pilar de valoración ya lleva el signo: positivo es barata frente al sector."""
    try:
        valor = float(pilar)
    except (TypeError, ValueError):
        return Voto(NO_APLICA, "sin_pares")
    if not math.isfinite(valor):
        return Voto(NO_APLICA, "sin_pares")
    if valor >= UMBRAL_PARES:
        return Voto(BARATA)
    if valor <= -UMBRAL_PARES:
        return Voto(CARA)
    return Voto(NEUTRA)


def veredicto(votos) -> str:
    aplicables = [v.voto for v in votos if v.voto != NO_APLICA]
    baratas, caras = aplicables.count(BARATA), aplicables.count(CARA)
    if len(aplicables) < MIN_VOTOS:
        return "sin_datos"
    if baratas >= 2 and caras == 0:
        return "infravalorada"
    if caras >= 2 and baratas == 0:
        return "sobrevalorada"
    if baratas >= 1 and caras >= 1:
        return "mixtas"
    return "en_rango"
```

- [ ] **Step 4: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_votos.py -v`
Expected: 85 passed.

- [ ] **Step 5: Commit**

```bash
git add valoracion/votos.py tests/test_valoracion_votos.py
git commit -m "feat: los tres votos y el veredicto, con las 64 combinaciones escritas a mano

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: El motor y su forma en disco

**Files:**
- Create: `valoracion/motor.py`
- Create: `valoracion/plano.py`
- Test: `tests/test_valoracion_motor.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_valoracion_motor.py`:

```python
import json
import math
from dataclasses import replace
from datetime import date
from unittest.mock import patch

import pytest

from valoracion import mercado
from valoracion.motor import calcular, valorar
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import NEUTRA, NO_APLICA, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil

HOY = date(2026, 10, 12)


def _supuestos(f=None, p=None, consenso=None):
    return deducir(f or fundamentos(), p or perfil(), r_f=0.04, beta=None, tasa=0.25, consenso=consenso)


def test_una_empresa_corriente_se_valora_por_flujos():
    v = calcular(fundamentos(), perfil(), _supuestos(), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "flujos"
    assert set(v.votos) == {"flujos", "sin_crecimiento", "pares"}
    assert v.valor.pesimista < v.valor.base < v.valor.optimista
    assert v.veredicto in VEREDICTOS


def test_un_banco_se_valora_por_beneficio_residual():
    p = perfil(industria="Banks - Regional")
    v = calcular(fundamentos(), p, _supuestos(p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.metodo == "residual"
    assert v.votos["sin_crecimiento"].voto == NO_APLICA
    assert v.votos["sin_crecimiento"].motivo == "financiera"
    assert v.implicito.magnitud == "roe"


def test_una_empresa_que_quema_caja_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    v = calcular(f, perfil(), _supuestos(f=f), pilar_valoracion=0.0, hoy=HOY)
    assert (v.votos["flujos"].voto, v.votos["flujos"].motivo) == (NO_APLICA, "quema_caja")
    assert v.valor is None


def test_un_banco_con_patrimonio_negativo_no_vota_flujos():
    f = fundamentos(ejercicios=[ejercicio(2026, patrimonio_neto=-10.0), ejercicio(2025), ejercicio(2024)])
    p = perfil(industria="Banks - Regional")
    v = calcular(f, p, _supuestos(f=f, p=p), pilar_valoracion=0.0, hoy=HOY)
    assert v.votos["flujos"].motivo == "patrimonio_negativo"


@pytest.mark.parametrize(
    "ingresos, consenso",
    [
        ([1000.0] * 4, None),
        ([1331.0, 1210.0, 1100.0, 1000.0], 0.20),
        ([900.0, 1000.0, 1100.0, 1200.0], None),
    ],
)
def test_con_el_precio_igual_al_valor_base_flujos_vota_neutra(ingresos, consenso):
    # Referencia positiva del voto: si el precio es el valor base, el
    # crecimiento implícito es el de referencia, y eso tiene que ser neutra.
    f = fundamentos(ejercicios=[ejercicio(2026 - i, ingresos=v) for i, v in enumerate(ingresos)])
    s = _supuestos(f=f, consenso=consenso)
    base = calcular(f, perfil(), s, 0.0, HOY).valor.base
    acciones = perfil().capitalizacion / perfil().precio
    en_su_valor = perfil(precio=base, capitalizacion=base * acciones)
    assert calcular(f, en_su_valor, s, 0.0, HOY).votos["flujos"].voto == NEUTRA


def test_el_margen_de_seguridad_es_relativo_al_precio():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    assert v.margen_seguridad == pytest.approx((v.valor.base - 100.0) / 100.0)


def test_la_valoracion_es_json_estricto_y_lleva_las_claves_del_spec():
    v = calcular(fundamentos(), perfil(), _supuestos(), float("nan"), HOY)
    plano = a_dict(v)
    json.dumps(plano, allow_nan=False)
    assert set(plano) == {
        "version", "fecha", "estados_hasta", "moneda", "precio", "precio_hora",
        "metodo", "valor", "margen_seguridad", "implicito", "epv", "votos",
        "veredicto", "supuestos",
    }
    assert plano["version"] == "m1" and plano["fecha"] == "2026-10-12"
    # La fecha de los estados con los que se valoró: en el Analizador (N) puede
    # ser vieja, y el número tiene que decir de cuándo son sus cifras.
    assert plano["estados_hasta"] == "2026-09-30"
    assert plano["votos"]["pares"] == {"voto": "no_aplica", "motivo": "sin_pares"}
    assert set(plano["supuestos"]["beta"]) == {"valor", "procedencia"}


def test_un_nan_en_una_procedencia_se_escribe_como_null():
    v = calcular(fundamentos(), perfil(), _supuestos(), 0.0, HOY)
    sup = replace(v.supuestos, g_ref=replace(v.supuestos.g_ref, procedencia={"consenso": float("nan")}))
    plano = a_dict(replace(v, supuestos=sup))
    assert plano["supuestos"]["g_ref"]["procedencia"]["consenso"] is None
    json.dumps(plano, allow_nan=False)


def test_una_fallida_dice_su_motivo_y_nada_mas():
    assert fallida("sin_precio", HOY) == {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"}


@pytest.fixture
def red_doble():
    with patch.object(mercado, "perfil", return_value=(perfil(), "ok")), patch.object(
        mercado, "tasa_libre", return_value=(0.04, "ok")
    ), patch.object(mercado, "beta", return_value=(None, "sin_regresion")), patch.object(
        mercado, "tasa_efectiva", return_value=(0.25, "ok")
    ), patch.object(mercado, "consenso", return_value=(None, "sin_consenso")), patch(
        "valoracion.motor.desde_sec", return_value=(fundamentos(), "ok")
    ):
        yield


def test_valorar_compone_todo_sin_red(red_doble):
    plano = valorar("TST", 0.3, hoy=HOY)
    json.dumps(plano, allow_nan=False)
    assert plano["veredicto"] in VEREDICTOS
    assert plano["votos"]["pares"]["voto"] == "neutra"


def test_sin_precio_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "perfil", return_value=(None, "sin_red")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_precio"


def test_sin_tasa_libre_valorar_dice_por_que(red_doble):
    with patch.object(mercado, "tasa_libre", return_value=(None, "sin_tasa_libre")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_tasa_libre"


def test_sin_estados_valorar_dice_por_que(red_doble):
    with patch("valoracion.motor.desde_sec", return_value=(None, "sin_estados")):
        assert valorar("TST", 0.3, hoy=HOY)["motivo"] == "sin_estados"
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_valoracion_motor.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'valoracion.motor'`.

- [ ] **Step 3: Implementar el plano**

`valoracion/plano.py`:

```python
"""La valoración como diccionario, para `fichas.json` y el acta.

Se guardan **claves, nunca textos de pantalla**: las etiquetas viven en
`medidores_valoracion.py`. Todo NaN se escribe como `null`, porque
`fichas.json` se escribe con `allow_nan=False` y ese es su contrato.
"""

import math
from dataclasses import fields
from datetime import date
from typing import TYPE_CHECKING

from valoracion.criterio import VERSION

if TYPE_CHECKING:
    from valoracion.motor import Valoracion


def _limpio(objeto):
    """Recorre lo que se va a escribir y cambia cada NaN o infinito por `None`."""
    if isinstance(objeto, dict):
        return {clave: _limpio(valor) for clave, valor in objeto.items()}
    if isinstance(objeto, (list, tuple)):
        return [_limpio(valor) for valor in objeto]
    if isinstance(objeto, float) and not math.isfinite(objeto):
        return None
    return objeto


def a_dict(v: "Valoracion") -> dict:
    return _limpio(
        {
            "version": VERSION,
            "fecha": v.fecha.isoformat(),
            "estados_hasta": v.estados_hasta.isoformat(),
            "moneda": v.moneda,
            "precio": v.precio,
            "precio_hora": v.precio_hora,
            "metodo": v.metodo,
            "valor": None
            if v.valor is None
            else {
                "pesimista": v.valor.pesimista,
                "base": v.valor.base,
                "optimista": v.valor.optimista,
            },
            "margen_seguridad": v.margen_seguridad,
            "implicito": None
            if v.implicito is None
            else {
                "magnitud": v.implicito.magnitud,
                "valor": v.implicito.valor,
                "referencia": v.implicito.referencia,
                "margen": v.implicito.margen,
                "fuera_de_limites": v.implicito.fuera_de_limites,
            },
            "epv": None
            if v.epv is None
            else {
                "por_accion": v.epv.por_accion,
                "parte_crecimiento": v.epv.parte_crecimiento,
            },
            "votos": {
                nombre: {"voto": voto.voto, "motivo": voto.motivo}
                for nombre, voto in v.votos.items()
            },
            "veredicto": v.veredicto,
            "supuestos": {
                campo.name: {
                    "valor": getattr(v.supuestos, campo.name).valor,
                    "procedencia": getattr(v.supuestos, campo.name).procedencia,
                }
                for campo in fields(v.supuestos)
            },
        }
    )


def fallida(motivo: str, hoy: "date | None" = None) -> dict:
    """Una valoración que no llegó a calcularse: su motivo y nada más."""
    return {"version": VERSION, "fecha": (hoy or date.today()).isoformat(), "motivo": motivo}
```

- [ ] **Step 4: Implementar el motor**

`valoracion/motor.py`:

```python
"""El motor: de fundamentos, perfil y supuestos al veredicto.

`calcular` es puro y es lo que prueban los tests. `valorar` sale a la red,
recoge lo que `calcular` necesita y devuelve ya el diccionario que se guarda.
"""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from valoracion import dcf, mercado, plano, residual
from valoracion.criterio import (
    DELTA_WACC_ESCENARIOS,
    INDUSTRIAS_FINANCIERAS,
    MARGEN_MINIMO,
    MARGEN_ROE_MINIMO,
)
from valoracion.dcf import Escenarios
from valoracion.epv import epv_por_accion, parte_crecimiento
from valoracion.fundamentos import Fundamentos, desde_sec
from valoracion.inverso import crecimiento_implicito
from valoracion.mercado import Perfil
from valoracion.supuestos import Supuestos, deducir
from valoracion.votos import (
    NO_APLICA,
    Voto,
    margen_voto,
    veredicto,
    voto_epv,
    voto_implicito,
    voto_pares,
)


@dataclass(frozen=True)
class Lectura:
    """Lo que el precio exige (crecimiento o ROE) frente a su referencia."""

    magnitud: str
    valor: "float | None"
    referencia: float
    margen: float
    fuera_de_limites: "str | None"


@dataclass(frozen=True)
class SinCrecimiento:
    por_accion: float
    parte_crecimiento: "float | None"


@dataclass(frozen=True)
class Valoracion:
    fecha: date
    # El cierre del último ejercicio. Una valoración con estados de hace un año
    # no se puede leer como una de hoy, y en N cualquiera puede traer un ticker
    # cuyas cuentas se quedaron atrás. En candidatos no pasa: la guarda
    # `MAX_ANTIGUEDAD_TRIMESTRES` del ranking ya excluye a los rezagados.
    estados_hasta: date
    moneda: str
    precio: float
    precio_hora: "str | None"
    metodo: str
    valor: "Escenarios | None"
    margen_seguridad: "float | None"
    implicito: "Lectura | None"
    epv: "SinCrecimiento | None"
    votos: dict
    veredicto: str
    supuestos: Supuestos


def _o_cero(valor: float) -> float:
    """Deuda o efectivo sin declarar cuentan como cero; la procedencia del
    coste de capital ya dice si la deuda estaba declarada."""
    return valor if math.isfinite(valor) else 0.0


def _lectura_flujos(fundamentos, supuestos, deuda, efectivo, acciones, precio):
    g_ref = supuestos.g_ref.valor
    if g_ref is None or not fundamentos.ultimo.ingresos > 0:
        return Voto(NO_APLICA, "sin_historia"), None, None
    margen = dcf.margen_fcff(fundamentos, supuestos.t.valor)
    if margen is None:
        return Voto(NO_APLICA, "sin_historia"), None, None
    if margen <= 0:
        # Quema caja: valorarla exigiría inventar cuándo deja de hacerlo.
        return Voto(NO_APLICA, "quema_caja"), None, None
    datos = dcf.Datos(
        ingresos=fundamentos.ultimo.ingresos,
        margen=margen,
        wacc=supuestos.wacc.valor,
        g_perpetuo=supuestos.g_perpetuo.valor,
        deuda=deuda,
        efectivo=efectivo,
        acciones=acciones,
    )
    base = dcf.valor_por_accion(datos, g_ref)
    if base is None:
        return Voto(NO_APLICA, "wacc_bajo_crecimiento"), None, None
    holgura = margen_voto(g_ref, MARGEN_MINIMO)
    valor = Escenarios(
        pesimista=dcf.valor_por_accion(datos, g_ref - holgura, datos.wacc + DELTA_WACC_ESCENARIOS),
        base=base,
        optimista=dcf.valor_por_accion(datos, g_ref + holgura, datos.wacc - DELTA_WACC_ESCENARIOS),
    )
    implicito = crecimiento_implicito(datos, precio)
    lectura = Lectura("crecimiento", implicito.valor, g_ref, holgura, implicito.fuera_de_limites)
    return voto_implicito(implicito, g_ref, holgura), valor, lectura


def _lectura_residual(fundamentos, supuestos, acciones, precio):
    roe_ref = supuestos.roe_ref.valor
    if roe_ref is None:
        return Voto(NO_APLICA, "sin_historia"), None, None
    if not fundamentos.ultimo.patrimonio_neto > 0:
        return Voto(NO_APLICA, "patrimonio_negativo"), None, None
    datos = residual.DatosResidual(
        patrimonio=fundamentos.ultimo.patrimonio_neto,
        k_e=supuestos.k_e.valor,
        payout=supuestos.payout.valor,
        acciones=acciones,
    )
    holgura = margen_voto(roe_ref, MARGEN_ROE_MINIMO)
    valor = Escenarios(
        pesimista=residual.valor_por_accion(datos, roe_ref - holgura, datos.k_e + DELTA_WACC_ESCENARIOS),
        base=residual.valor_por_accion(datos, roe_ref),
        optimista=residual.valor_por_accion(datos, roe_ref + holgura, datos.k_e - DELTA_WACC_ESCENARIOS),
    )
    implicito = residual.roe_implicito(datos, precio)
    lectura = Lectura("roe", implicito.valor, roe_ref, holgura, implicito.fuera_de_limites)
    return voto_implicito(implicito, roe_ref, holgura), valor, lectura


def _lectura_epv(fundamentos, supuestos, deuda, efectivo, acciones, precio):
    valor, motivo = epv_por_accion(
        fundamentos, supuestos.t.valor, supuestos.wacc.valor, deuda, efectivo, acciones
    )
    if valor is None:
        return Voto(NO_APLICA, motivo), None
    return voto_epv(valor, precio), SinCrecimiento(valor, parte_crecimiento(valor, precio))


def calcular(
    fundamentos: Fundamentos,
    perfil: Perfil,
    supuestos: Supuestos,
    pilar_valoracion: "float | None",
    hoy: "date | None" = None,
) -> Valoracion:
    """Las cuatro lecturas, los tres votos y el veredicto. Sin red.

    Las acciones son capitalización ÷ precio: el recuento en la base en la que
    está el precio. Es lo que desactiva la trampa de las ADR en N.
    """
    precio = perfil.precio
    acciones = perfil.capitalizacion / perfil.precio
    deuda, efectivo = _o_cero(fundamentos.deuda_total), _o_cero(fundamentos.efectivo)
    if perfil.industria in INDUSTRIAS_FINANCIERAS:
        metodo = "residual"
        flujos, valor, lectura = _lectura_residual(fundamentos, supuestos, acciones, precio)
        sin_crecimiento, epv = Voto(NO_APLICA, "financiera"), None
    else:
        metodo = "flujos"
        flujos, valor, lectura = _lectura_flujos(
            fundamentos, supuestos, deuda, efectivo, acciones, precio
        )
        sin_crecimiento, epv = _lectura_epv(
            fundamentos, supuestos, deuda, efectivo, acciones, precio
        )
    votos = {
        "flujos": flujos,
        "sin_crecimiento": sin_crecimiento,
        "pares": voto_pares(pilar_valoracion),
    }
    base = None if valor is None else valor.base
    return Valoracion(
        fecha=hoy or date.today(),
        estados_hasta=fundamentos.ultimo.fin,
        moneda=perfil.moneda,
        precio=precio,
        precio_hora=perfil.hora,
        metodo=metodo,
        valor=valor,
        margen_seguridad=None if base is None else (base - precio) / precio,
        implicito=lectura,
        epv=epv,
        votos=votos,
        veredicto=veredicto(votos.values()),
        supuestos=supuestos,
    )


def valorar(
    ticker: str,
    pilar_valoracion: "float | None",
    cache_dir: "Path | None" = None,
    hoy: "date | None" = None,
) -> dict:
    """La valoración de un ticker de la SEC, ya como diccionario para guardar.

    Lo que falta se dice con su motivo en vez de calcularse a medias: sin precio
    no hay acciones, sin tasa libre no hay coste de capital, y sin estados no
    hay nada que proyectar.
    """
    perfil, _ = mercado.perfil(ticker)
    if perfil is None:
        return plano.fallida("sin_precio", hoy)
    r_f, _ = mercado.tasa_libre()
    if r_f is None:
        return plano.fallida("sin_tasa_libre", hoy)
    fundamentos, motivo = desde_sec(ticker, cache_dir=cache_dir)
    if fundamentos is None:
        return plano.fallida(motivo, hoy)
    beta, _ = mercado.beta(ticker)
    tasa, _ = mercado.tasa_efectiva(ticker)
    consenso, _ = mercado.consenso(ticker, fundamentos.moneda)
    supuestos = deducir(fundamentos, perfil, r_f, beta, tasa, consenso)
    return plano.a_dict(calcular(fundamentos, perfil, supuestos, pilar_valoracion, hoy))
```

- [ ] **Step 5: Pasar los tests**

Run: `uv run pytest tests/test_valoracion_motor.py -v`
Expected: 15 passed.

- [ ] **Step 6: Pasar todo `valoracion`**

Run: `uv run pytest tests/ -q -k valoracion`
Expected: todo verde, 1 skipped (`numpy_financial`).

- [ ] **Step 7: Commit**

```bash
git add valoracion/motor.py valoracion/plano.py tests/test_valoracion_motor.py
git commit -m "feat: el motor del valor intrinseco y su forma en disco, JSON estricto

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: La valoración en cada ficha del ranking

**Files:**
- Modify: `ranking/run.py` (imports; firma de `construir_ranking`; bucle de fichas)
- Modify: `tests/test_ranking_run.py` (fixture autouse y tests nuevos)

- [ ] **Step 1: Escribir los tests y aislar los existentes de la red**

En `tests/test_ranking_run.py`, justo después de los imports, añade:

```python
@pytest.fixture(autouse=True)
def valoracion_doble():
    """La valoración sale a yfinance; aquí no se prueba ella, sino dónde cae.

    Autouse porque `construir_ranking` valora por defecto: sin esto, cada test
    de este fichero saldría a la red quince veces.
    """
    with patch(
        "ranking.run.valorar",
        return_value={"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"},
    ) as doble:
        yield doble
```

Y al final del fichero:

```python
def test_cada_ficha_lleva_su_valoracion(sin_red, valoracion_doble):
    resultado = construir_ranking(con_llm=False, n=5)
    assert all("valoracion" in ficha for ficha in resultado.fichas)
    llamadas = {c.args[0]: c.args[1] for c in valoracion_doble.call_args_list}
    for ficha in resultado.fichas:
        assert llamadas[ficha["ticker"]] == ficha["pilares"]["valoracion"]


def test_sin_valoracion_no_se_sale_a_valorar(sin_red, valoracion_doble):
    resultado = construir_ranking(con_llm=False, n=5, con_valoracion=False)
    assert all("valoracion" not in ficha for ficha in resultado.fichas)
    valoracion_doble.assert_not_called()


def test_una_valoracion_que_revienta_no_tumba_la_corrida(sin_red, valoracion_doble):
    valoracion_doble.side_effect = RuntimeError("un defecto del motor")
    resultado = construir_ranking(con_llm=False, n=5)
    assert {f["valoracion"]["motivo"] for f in resultado.fichas} == {"error_interno"}


def test_guardar_con_valoracion_sigue_siendo_json_estricto(sin_red, tmp_path):
    guardar(construir_ranking(con_llm=False, n=5), tmp_path)
    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert all(f["valoracion"]["version"] == "m1" for f in fichas)
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_ranking_run.py -v`
Expected: FAIL. Los tests existentes fallan con `AttributeError: <module 'ranking.run'> does not have the attribute 'valorar'`, y los nuevos igual.

- [ ] **Step 3: Implementar**

En `ranking/run.py`, añade a los imports (orden alfabético con el resto de `from …`):

```python
from valoracion.motor import valorar
from valoracion.plano import fallida
```

Añade esta función justo después de `_con_narrativa`:

```python
def _valoracion(ticker: str, pilar_valoracion: "float | None") -> dict:
    """La valoración de una ficha, o por qué no la tiene.

    Una empresa que falla al valorarse se anota y la corrida sigue: es la
    política de la descarga de fundamentales. Y un defecto del propio motor
    tampoco tumba el ranking, pero no se calla: queda escrito como
    `error_interno` en la ficha, a la vista en la pantalla.
    """
    try:
        return valorar(ticker, pilar_valoracion)
    except Exception:
        return fallida("error_interno")
```

Cambia la firma de `construir_ranking` añadiendo el parámetro al final:

```python
def construir_ranking(
    source: str | list[str] = "sp500",
    con_llm: bool = True,
    n: int = TAMANO_TOP,
    tope: int = TOPE_POR_SECTOR,
    cache_dir: Path | None = None,
    con_valoracion: bool = True,
) -> Resultado:
```

Y en el bucle de fichas, sustituye:

```python
        if con_llm:
            ficha = _con_narrativa(ficha, cache_dir)
        fichas.append(ficha)
```

por:

```python
        if con_llm:
            ficha = _con_narrativa(ficha, cache_dir)
        if con_valoracion:
            # La valoración no toca el score: se calcula sobre las ya elegidas
            # y sólo se enseña. Ver el spec de M, «Integración».
            ficha = {
                **ficha,
                "valoracion": _valoracion(fila.ticker, ficha["pilares"].get("valoracion")),
            }
        fichas.append(ficha)
```

- [ ] **Step 4: Pasar los tests del ranking**

Run: `uv run pytest tests/test_ranking_run.py -v`
Expected: todo verde (los existentes más 4 nuevos).

- [ ] **Step 5: Commit**

```bash
git add ranking/run.py tests/test_ranking_run.py
git commit -m "feat: cada ficha del ranking lleva su valoracion, sin tocar el score

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Leer la valoración de una ficha sin romperse con las viejas

**Files:**
- Modify: `aprobacion/carga.py` (función nueva al final)
- Modify: `tests/test_aprobacion_carga.py` (tests al final)

- [ ] **Step 1: Escribir los tests**

Añade `valoracion_de` a la importación de `aprobacion.carga` que ya hay arriba de `tests/test_aprobacion_carga.py`, y al final del fichero:

```python
def test_una_ficha_sin_valoracion_no_tiene_valoracion():
    assert valoracion_de({"ticker": "AAA"}) is None


@pytest.mark.parametrize("valor", ["mixtas", 3, [], {"veredicto": "mixtas"}])
def test_una_valoracion_sin_version_no_se_lee(valor):
    assert valoracion_de({"valoracion": valor}) is None


def test_una_valoracion_con_version_se_lee_tal_cual():
    valor = {"version": "m1", "veredicto": "mixtas"}
    assert valoracion_de({"valoracion": valor}) is valor


def test_una_fallida_tambien_se_lee():
    valor = {"version": "m1", "fecha": "2026-10-12", "motivo": "sin_precio"}
    assert valoracion_de({"valoracion": valor}) == valor
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_aprobacion_carga.py -v`
Expected: FAIL con `ImportError: cannot import name 'valoracion_de'`.

- [ ] **Step 3: Implementar**

Al final de `aprobacion/carga.py`:

```python
def valoracion_de(ficha: dict) -> "dict | None":
    """La valoración de la ficha, o `None` si no tiene o no se reconoce.

    `valoracion` no está en `_CAMPOS_FICHA` a propósito: es opcional, y un
    `fichas.json` anterior al sub-proyecto M --o el de `salidas_ejemplo`-- tiene
    que seguir cargando. Es el mismo defecto que ya pagó `kpis_por_pilar`:
    validar la existencia de un campo y no su contenido dejaba reventar la lista
    a la mitad, con tarjetas ya pintadas encima.

    Se exige `version` como cadena porque es lo único que tienen en común una
    valoración calculada y una fallida, y lo único que un formato futuro no va a
    quitar.
    """
    valor = ficha.get("valoracion")
    if not isinstance(valor, dict) or not isinstance(valor.get("version"), str):
        return None
    return valor
```

- [ ] **Step 4: Pasar los tests**

Run: `uv run pytest tests/test_aprobacion_carga.py -v`
Expected: todo verde.

- [ ] **Step 5: Commit**

```bash
git add aprobacion/carga.py tests/test_aprobacion_carga.py
git commit -m "feat: valoracion_de lee la valoracion de una ficha y tolera las viejas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Etiquetas, distintivo y resumen

**Files:**
- Create: `medidores_valoracion.py`
- Modify: `medidores.py` (import y `tarjeta_candidato`)
- Test: `tests/test_medidores_valoracion.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_medidores_valoracion.py`:

```python
from datetime import date

import pytest

import medidores
import medidores_valoracion as mv
from valoracion.motor import calcular
from valoracion.plano import a_dict, fallida
from valoracion.supuestos import deducir
from valoracion.votos import MOTIVOS, VEREDICTOS

from tests.dobles_valoracion import ejercicio, fundamentos, perfil


def _valoracion(f=None, p=None, pilar=0.8) -> dict:
    f, p = f or fundamentos(), p or perfil()
    s = deducir(f, p, r_f=0.04, beta=None, tasa=0.25, consenso=None)
    return a_dict(calcular(f, p, s, pilar, date(2026, 10, 12)))


def test_cada_veredicto_tiene_etiqueta():
    assert set(mv.VEREDICTO) == set(VEREDICTOS)


def test_cada_motivo_tiene_etiqueta():
    assert MOTIVOS <= set(mv.MOTIVO)


@pytest.mark.parametrize("clave", VEREDICTOS)
def test_el_distintivo_dice_el_veredicto(clave):
    assert mv.VEREDICTO[clave][0] in mv.distintivo({"version": "m1", "veredicto": clave})


@pytest.mark.parametrize("valor", [None, fallida("sin_precio"), {"version": "m1", "veredicto": "otra"}])
def test_sin_valoracion_reconocible_no_hay_distintivo(valor):
    assert mv.distintivo(valor) == ""


def test_el_resumen_nombra_los_tres_votos():
    html = mv.resumen(_valoracion())
    for nombre in mv.NOMBRE_VOTO.values():
        assert nombre in html
    assert "estados hasta 2026-09-30" in html


def test_el_resumen_de_un_banco_llama_beneficio_residual_a_los_flujos():
    p = perfil(industria="Banks - Regional")
    html = mv.resumen(_valoracion(p=p))
    assert "Beneficio residual" in html
    assert mv.MOTIVO["financiera"] in html


def test_quemar_caja_se_explica_y_no_se_pone_a_cero():
    f = fundamentos(ejercicios=[ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    html = mv.resumen(_valoracion(f=f))
    assert mv.MOTIVO["quema_caja"] in html


def test_una_fallida_dice_por_que():
    assert mv.MOTIVO["sin_precio"] in mv.resumen(fallida("sin_precio"))


def test_el_resumen_escapa_lo_que_no_es_suyo():
    valor = {**_valoracion(), "moneda": "<b>USD</b>"}
    html = mv.resumen(valor)
    assert "<b>USD</b>" not in html
    assert "&lt;b&gt;USD&lt;/b&gt;" in html


def test_una_procedencia_desconocida_no_revienta():
    assert mv.procedencia("beta", {"valor": 1.0, "procedencia": {"fuente": "otra"}}) == ""


def test_la_beta_dice_de_donde_sale():
    texto = mv.procedencia(
        "beta",
        {"valor": 1.33, "procedencia": {"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.41}},
    )
    assert "104 semanas" in texto and "^GSPC" in texto and "Blume" in texto


FICHA = {
    "puesto": 1,
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "compuesto": 1.2,
    "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": -0.2, "solidez": 0.3},
    "cobertura": {
        "kpis_con_dato": 15,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
    },
}


def test_la_tarjeta_lleva_el_distintivo():
    ficha = {**FICHA, "valoracion": {"version": "m1", "veredicto": "infravalorada"}}
    assert "Infravalorada" in medidores.tarjeta_candidato(ficha)


def test_una_tarjeta_vieja_no_lleva_distintivo():
    assert "mpp-veredicto" not in medidores.tarjeta_candidato(FICHA)
```

- [ ] **Step 2: Ver que fallan**

Run: `uv run pytest tests/test_medidores_valoracion.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'medidores_valoracion'`.

- [ ] **Step 3: Implementar el módulo de presentación**

`medidores_valoracion.py`:

```python
"""Cómo se enseña una valoración: etiquetas y HTML, sin Streamlit.

`fichas.json` guarda claves (`"mixtas"`, `"quema_caja"`), nunca textos de
pantalla: es la regla de «La etiqueta de pantalla que se guardaba en disco».
Las palabras viven aquí y sólo aquí. Va aparte de `medidores.py`, que ya pasa
de las 450 líneas, y lo usarán las dos pantallas: Revisar candidatos y, en N, el
Analizador.

Todo lo que sale de la ficha se escapa antes de pintarlo, aunque lo haya
escrito este mismo programa: la moneda, por ejemplo, viene de Yahoo.
"""

import html

import tema
from valoracion.criterio import INVERSO_LIMITES, INVERSO_ROE_LIMITES

VEREDICTO = {
    "infravalorada": ("Infravalorada", tema.VERDE),
    "sobrevalorada": ("Sobrevalorada", tema.ROJO),
    "mixtas": ("Señales mixtas", tema.AMBAR),
    "en_rango": ("En rango", tema.TEXTO_SUAVE),
    "sin_datos": ("Sin datos suficientes", tema.TEXTO_TENUE),
}

VOTO = {
    "barata": ("Barata", tema.VERDE),
    "neutra": ("Neutra", tema.TEXTO_SUAVE),
    "cara": ("Cara", tema.ROJO),
    "no_aplica": ("No aplica", tema.TEXTO_TENUE),
}

NOMBRE_VOTO = {
    "flujos": "Flujos (DCF e inverso)",
    "sin_crecimiento": "Sin crecimiento (EPV)",
    "pares": "Frente a sus pares",
}
_NOMBRE_VOTO_RESIDUAL = {**NOMBRE_VOTO, "flujos": "Beneficio residual"}

MOTIVO = {
    "quema_caja": "quema caja: valorarla exigiría inventar cuándo deja de hacerlo",
    "ebit_negativo": "beneficio operativo negativo: sin crecer no queda nada que capitalizar",
    "sin_historia": "faltan años de historia para normalizar sus márgenes",
    "wacc_bajo_crecimiento": (
        "el coste de capital no supera al crecimiento perpetuo en al menos un "
        "punto, y el valor terminal explotaría"
    ),
    "sin_pares": "sin pares del sector con los que comparar",
    "sin_precio": "no se pudo descargar el precio",
    "sin_tasa_libre": "no se pudo descargar la tasa libre de riesgo",
    "financiera": "no aplica a bancos ni aseguradoras",
    "patrimonio_negativo": "patrimonio negativo: no hay base sobre la que medir la rentabilidad",
    "sin_estados": "no se pudieron leer sus estados financieros de la SEC",
    "error_interno": "error interno al valorar: merece avisar de ello",
}

NOTA = (
    "Un criterio transparente, no una previsión: no hay forma honesta de probar "
    "hacia atrás si acierta, porque las cifras de yfinance no dicen cuándo se "
    "publicaron y el universo arrastra sesgo de supervivencia."
)

CSS = f"""<style>
.mpp-veredicto {{
  border:1px solid currentColor; border-radius:999px; padding:.03rem .55rem;
  font-size:.72rem; font-weight:600;
}}
.mpp-val {{ font-size:.8rem; line-height:1.45; color:{tema.TEXTO}; margin:.2rem 0 .4rem; }}
.mpp-val-cab {{ display:flex; flex-wrap:wrap; gap:.55rem; align-items:baseline; margin-bottom:.35rem; }}
.mpp-val-voto {{ display:flex; gap:.55rem; align-items:baseline; margin:.15rem 0; }}
.mpp-val-nombre {{ flex:0 0 11.5rem; }}
.mpp-val-etiqueta {{ flex:0 0 5.5rem; font-weight:600; }}
.mpp-val-detalle {{ color:{tema.TEXTO_SUAVE}; }}
.mpp-val-sup {{ color:{tema.TEXTO_TENUE}; font-size:.72rem; margin-top:.45rem; }}
</style>"""


def _esc(texto: object) -> str:
    return html.escape(str(texto))


def _pct(valor) -> str:
    return "n/d" if valor is None else f"{valor * 100:.1f}%"


def _dinero(valor, moneda: str) -> str:
    return "n/d" if valor is None else f"{valor:,.2f} {moneda}"


def _motivo(clave) -> str:
    return MOTIVO.get(clave, str(clave))


def distintivo(valoracion: "dict | None") -> str:
    """El veredicto en una píldora de color, o nada si no hay veredicto que enseñar."""
    if not isinstance(valoracion, dict) or valoracion.get("veredicto") not in VEREDICTO:
        return ""
    etiqueta, color = VEREDICTO[valoracion["veredicto"]]
    return f'<span class="mpp-veredicto" style="color:{color}">{_esc(etiqueta)}</span>'


def _detalle_flujos(valoracion: dict) -> str:
    lectura = valoracion.get("implicito") or {}
    roe = lectura.get("magnitud") == "roe"
    bajo, alto = INVERSO_ROE_LIMITES if roe else INVERSO_LIMITES
    if lectura.get("fuera_de_limites") == "arriba":
        return (
            f"el precio exige un ROE de más del {_pct(alto)}" if roe
            else f"el precio exige crecer más de un {_pct(alto)} anual"
        )
    if lectura.get("fuera_de_limites") == "abajo":
        return (
            f"el precio queda por debajo incluso de un ROE del {_pct(bajo)}" if roe
            else f"el precio queda por debajo incluso de decrecer un {_pct(-bajo)} anual"
        )
    exige = (
        f"el precio exige un ROE del {_pct(lectura.get('valor'))}" if roe
        else f"el precio exige crecer un {_pct(lectura.get('valor'))} anual cinco años"
    )
    return (
        f"{exige}; su referencia es {_pct(lectura.get('referencia'))} "
        f"(±{_pct(lectura.get('margen'))})"
    )


def _detalle_epv(valoracion: dict) -> str:
    epv = valoracion.get("epv") or {}
    texto = f"sin crecer valdría {_dinero(epv.get('por_accion'), valoracion.get('moneda', ''))}"
    parte = epv.get("parte_crecimiento")
    if parte is not None and parte > 0:
        texto += f"; el {_pct(parte)} del precio es apuesta por el crecimiento"
    return texto


_DETALLE_PARES = {
    "barata": "múltiplos por debajo de los de su sector",
    "cara": "múltiplos por encima de los de su sector",
    "neutra": "múltiplos en línea con los de su sector",
}


def _detalle(clave: str, voto: dict, valoracion: dict) -> str:
    if voto.get("voto") == "no_aplica":
        return _motivo(voto.get("motivo"))
    if clave == "flujos":
        return _detalle_flujos(valoracion)
    if clave == "sin_crecimiento":
        return _detalle_epv(valoracion)
    return _DETALLE_PARES.get(voto.get("voto"), "")


def _rango(valoracion: dict) -> str:
    moneda = valoracion.get("moneda", "")
    valor = valoracion.get("valor")
    if not valor:
        return "Sin rango de valor."
    return (
        f"Valor por acción: pesimista {_dinero(valor.get('pesimista'), moneda)} · "
        f"base {_dinero(valor.get('base'), moneda)} · "
        f"optimista {_dinero(valor.get('optimista'), moneda)} · "
        f"margen de seguridad {_pct(valoracion.get('margen_seguridad'))}"
    )


_NOMBRE_SUPUESTO = {
    "r_f": "tasa libre",
    "beta": "beta",
    "prima": "prima de riesgo",
    "k_e": "coste del capital propio",
    "k_d": "coste de la deuda",
    "t": "impuestos",
    "wacc": "coste de capital",
    "g_ref": "crecimiento de referencia",
    "g_perpetuo": "crecimiento perpetuo",
    "roe_ref": "ROE de referencia",
    "payout": "reparto",
}


def procedencia(nombre: str, supuesto: dict) -> str:
    """De dónde sale un supuesto, en palabras. Vacío si la fuente no se reconoce."""
    p = (supuesto or {}).get("procedencia") or {}
    fuente = p.get("fuente")
    textos = {
        ("r_f", "tesoro_10"): "Tesoro de EE. UU. a 10 años (^TNX)",
        ("beta", "regresion"): (
            f"regresión semanal de {p.get('semanas')} semanas contra {p.get('indice')} "
            f"(R² {p.get('r2')}), con el ajuste de Blume"
        ),
        ("beta", "por_defecto"): "1,0 por defecto: no hubo regresión posible (historial corto o precios inválidos)",
        ("prima", "damodaran"): f"Damodaran, prima implícita a {p.get('fecha')}",
        ("k_e", "capm"): "tasa libre más beta por prima",
        ("k_d", "gasto_entre_deuda"): "gasto financiero entre deuda, acotado",
        ("k_d", "sin_dato"): "sin deuda o sin gasto financiero declarado: la tasa libre",
        ("k_d", "financiera"): "no aplica: en un banco o una aseguradora los intereses incluyen los depósitos",
        ("t", "efectiva"): "tasa efectiva de yfinance, acotada entre 0% y 35%",
        ("t", "legal"): f"tasa legal ({p.get('pais')})",
        ("wacc", "financiera"): "no aplica: se valora con el coste del capital propio",
        ("wacc", "wacc"): (
            f"deuda {_pct(p.get('peso_deuda'))} del capital"
            + ("" if p.get("deuda_declarada", True) else "; sin deuda declarada")
        ),
        ("g_ref", "historia_y_consenso"): (
            f"media del histórico de ingresos ({_pct(p.get('historico'))}) y del "
            f"consenso del próximo año ({_pct(p.get('consenso'))}), acotada"
        ),
        ("g_ref", "historia"): f"histórico de ingresos ({_pct(p.get('historico'))}), sin consenso, acotado",
        ("g_ref", "consenso"): f"consenso del próximo año ({_pct(p.get('consenso'))}), sin historia, acotado",
        ("g_ref", "sin_dato"): "sin historia ni consenso",
        ("g_perpetuo", "criterio"): f"crecimiento de largo plazo en {p.get('moneda')}",
        ("g_perpetuo", "recortado_a_r_f"): "recortado a la tasa libre de riesgo",
        ("roe_ref", "mediana_historica"): f"mediana de {p.get('anos')} años",
        ("roe_ref", "sin_dato"): "sin años suficientes",
        ("payout", "yfinance"): "reparto de beneficios de yfinance",
        ("payout", "por_defecto"): "sin dato: se supone la mitad",
    }
    return textos.get((nombre, fuente), "")


def _supuestos(valoracion: dict) -> str:
    partes = []
    for nombre, supuesto in (valoracion.get("supuestos") or {}).items():
        valor = (supuesto or {}).get("valor")
        cifra = f"{valor:.2f}" if nombre == "beta" and valor is not None else _pct(valor)
        origen = procedencia(nombre, supuesto)
        etiqueta = _NOMBRE_SUPUESTO.get(nombre, nombre)
        partes.append(f"{etiqueta} {cifra}" + (f" ({origen})" if origen else ""))
    if not partes:
        return ""
    return f'<div class="mpp-val-sup">Supuestos del programa: {_esc("; ".join(partes))}.</div>'


def resumen(valoracion: dict) -> str:
    """Los tres votos en una línea cada uno, el rango y la procedencia de los supuestos."""
    if "veredicto" not in valoracion:
        return (
            f'<div class="mpp-val">No se pudo valorar: '
            f'{_esc(_motivo(valoracion.get("motivo")))}.</div>'
        )
    nombres = _NOMBRE_VOTO_RESIDUAL if valoracion.get("metodo") == "residual" else NOMBRE_VOTO
    filas = []
    for clave in ("flujos", "sin_crecimiento", "pares"):
        voto = (valoracion.get("votos") or {}).get(clave) or {}
        etiqueta, color = VOTO.get(voto.get("voto"), ("n/d", tema.TEXTO_TENUE))
        filas.append(
            '<div class="mpp-val-voto">'
            f'<span class="mpp-val-nombre">{_esc(nombres[clave])}</span>'
            f'<span class="mpp-val-etiqueta" style="color:{color}">{_esc(etiqueta)}</span>'
            f'<span class="mpp-val-detalle">{_esc(_detalle(clave, voto, valoracion))}</span>'
            "</div>"
        )
    cabecera = (
        f'<div class="mpp-val-cab">{distintivo(valoracion)}'
        f'<span class="mpp-val-detalle">{_esc(_rango(valoracion))}</span>'
        f'<span class="mpp-val-detalle">Calculada el {_esc(valoracion.get("fecha"))} '
        f'con el precio de {_esc(_dinero(valoracion.get("precio"), valoracion.get("moneda", "")))} '
        f'y estados hasta {_esc(valoracion.get("estados_hasta", "n/d"))}'
        "</span></div>"
    )
    return f'<div class="mpp-val">{cabecera}{"".join(filas)}{_supuestos(valoracion)}</div>'
```

- [ ] **Step 4: El distintivo en la tarjeta**

En `medidores.py`, añade el import junto a los demás:

```python
import medidores_valoracion
```

Y en `tarjeta_candidato`, sustituye la línea del chip de sector:

```python
        f'<span class="mpp-chip">{_esc(ficha["sector_gics"])}</span>'
```

por:

```python
        f'<span class="mpp-chip">{_esc(ficha["sector_gics"])}</span>'
        f'{medidores_valoracion.distintivo(ficha.get("valoracion"))}'
```

- [ ] **Step 5: Pasar los tests nuevos y los de medidores**

Run: `uv run pytest tests/test_medidores_valoracion.py tests/test_medidores.py tests/test_medidores_peso.py -v`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add medidores_valoracion.py medidores.py tests/test_medidores_valoracion.py
git commit -m "feat: distintivo y resumen de la valoracion; las etiquetas viven fuera del dato

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: La valoración en Revisar candidatos

**Files:**
- Modify: `vistas/candidatos.py`

Las vistas no tienen tests unitarios en este repo; se comprueban con la app arrancada en la Task 16.

- [ ] **Step 1: Imports**

En `vistas/candidatos.py`, añade `import medidores_valoracion` debajo de `import medidores`, y añade `valoracion_de` a la importación de `aprobacion.carga`:

```python
from aprobacion.carga import (
    ContratoRoto,
    FaltanFichas,
    cargar_candidatos,
    kpis_con_dato,
    resumen_corrida,
    valoracion_de,
)
```

- [ ] **Step 2: El texto del indicador de progreso**

En `_generar`, sustituye:

```python
        with st.spinner(
            "Generando candidatos"
            + (" y redactando fichas con IA" if con_ia else " sin IA")
            + "… puede tardar unos minutos. No cierres ni recargues."
        ):
```

por:

```python
        with st.spinner(
            "Generando candidatos"
            + (" y redactando fichas con IA" if con_ia else " sin IA")
            + ", y calculando su valor intrínseco… puede tardar unos minutos. "
            "No cierres ni recargues."
        ):
```

- [ ] **Step 3: La hoja de estilo**

Sustituye:

```python
st.markdown(medidores.CSS, unsafe_allow_html=True)
```

por:

```python
st.markdown(medidores.CSS, unsafe_allow_html=True)
st.markdown(medidores_valoracion.CSS, unsafe_allow_html=True)
```

- [ ] **Step 4: Un solo aviso cuando todas fallan por lo mismo**

Justo después de la línea que pinta `resumen_corrida` (`st.info(resumen_corrida(candidatos.corrida))`), añade:

```python
# Si falla la tasa libre o la red, las quince fichas llevan el mismo motivo.
# Un aviso arriba lo dice una vez; repetirlo dentro de cada ficha es lo de
# siempre, pero sin este aviso hay que abrir quince desplegables para saberlo.
_motivos_valoracion = {
    (valoracion_de(f) or {}).get("motivo") for f in candidatos.fichas
}
if len(_motivos_valoracion) == 1 and None not in _motivos_valoracion:
    (_motivo_comun,) = _motivos_valoracion
    st.warning(
        "No se pudo valorar ningún candidato: "
        f"{medidores_valoracion.MOTIVO.get(_motivo_comun, _motivo_comun)}. "
        "El orden y las fichas no dependen de la valoración; vuelve a generar "
        "cuando se resuelva."
    )
```

- [ ] **Step 5: El bloque «Valoración» en cada ficha**

Dentro del `with st.expander(f"Ver la ficha completa de {ticker}"):`, justo después del bloque que pinta `desplazo_a`:

```python
        if ficha["desplazo_a"]:
            st.caption(
                "Dejó fuera por el tope sectorial: "
                + ", ".join(ficha["desplazo_a"])
            )
```

añade:

```python
        # Después de los pilares y antes de la narrativa: los números primero,
        # la lectura de la IA después. `valoracion_de` y no `ficha["valoracion"]`:
        # una ficha anterior a M no la trae, y reventar aquí sería hacerlo a
        # mitad de la lista, con tarjetas ya pintadas encima.
        st.markdown("**Valoración**: cuatro lecturas que dan tres votos")
        _valoracion = valoracion_de(ficha)
        if _valoracion is None:
            st.caption("Sin valoración: ficha de una versión anterior")
        else:
            st.markdown(medidores_valoracion.resumen(_valoracion), unsafe_allow_html=True)
            st.caption(medidores_valoracion.NOTA)
```

- [ ] **Step 6: `.gitignore`**

Ya lo hizo la Task 4, tras su revisión de calidad. Comprueba que la línea está:

Run: `grep -n "valoracion/.cache/" .gitignore`
Expected: una línea.

- [ ] **Step 7: Comprobar que la vista se importa sin errores de sintaxis**

Run: `uv run python -I -c "import ast, pathlib; ast.parse(pathlib.Path('vistas/candidatos.py').read_text(encoding='utf-8')); print('ok')"`
Expected: `ok`

- [ ] **Step 8: Commit**

```bash
git add vistas/candidatos.py
git commit -m "feat: la valoracion en Revisar candidatos, en la tarjeta y en la ficha

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Tests contra las fuentes vivas

**Files:**
- Create: `tests/test_valoracion_red.py`

- [ ] **Step 1: Escribir los tests `red`**

`tests/test_valoracion_red.py`:

```python
"""Contra yfinance y EDGAR de verdad. Excluidos de la suite normal.

Lo que comprueban es que las fuentes siguen teniendo la forma que los
intérpretes puros esperan, y que la lista de industrias financieras casa con
las cadenas reales de Yahoo. Necesitan red, y `valorar` además `EDGAR_IDENTITY`
si los hechos de MU no están en caché.
"""

import json

import pytest

from valoracion import mercado
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.votos import VEREDICTOS

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path)


def test_el_tnx_da_una_tasa_plausible():
    tasa, motivo = mercado.tasa_libre()
    assert motivo == "ok"
    assert 0.0 < tasa < 0.15


def test_la_beta_de_mu_sale_de_una_regresion_completa():
    beta, motivo = mercado.beta("MU")
    assert motivo == "ok"
    assert beta.semanas >= 100
    assert 0.3 < beta.bruta < 4.0


def test_el_consenso_de_mu_viene_en_dolares():
    valor, motivo = mercado.consenso("MU", "USD")
    assert motivo == "ok" and valor is not None


def test_el_consenso_de_tsm_contra_dolares_se_descarta():
    # Su revenue_estimate viene en TWD.
    valor, _ = mercado.consenso("TSM", "USD")
    assert valor is None


@pytest.mark.parametrize(
    "ticker, financiera",
    [
        ("JPM", True), ("USB", True), ("MET", True), ("PGR", True), ("GS", True),
        ("V", False), ("MA", False), ("COF", False), ("AJG", False), ("BLK", False),
        ("MU", False),
    ],
)
def test_la_lista_de_financieras_casa_con_yahoo(ticker, financiera):
    perfil, motivo = mercado.perfil(ticker)
    assert motivo == "ok"
    assert (perfil.industria in INDUSTRIAS_FINANCIERAS) is financiera


def test_valorar_mu_de_punta_a_punta():
    from valoracion.motor import valorar

    plano = valorar("MU", 0.3)
    json.dumps(plano, allow_nan=False)
    assert plano["veredicto"] in VEREDICTOS
    assert plano["supuestos"]["beta"]["procedencia"]["fuente"] == "regresion"
```

- [ ] **Step 2: Correrlos**

Run: `uv run pytest tests/test_valoracion_red.py -v -m red`
Expected: todos pasan. Si `test_la_lista_de_financieras_casa_con_yahoo` falla, **no toques el criterio en silencio**: la lista se congeló en la Task 1 con el sondeo; si Yahoo ha cambiado una cadena desde entonces, es una enmienda fechada en el spec.

- [ ] **Step 3: Comprobar que la suite normal los excluye**

Run: `uv run pytest tests/test_valoracion_red.py -q -m "not red"`
Expected: `16 deselected`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_valoracion_red.py
git commit -m "test: el valor intrinseco contra yfinance y EDGAR vivos (red)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Sabotaje de las guardas

Cada sabotaje se aplica, se corre el test indicado, se comprueba que **falla**, y se deshace con `git checkout -- <fichero>`. No se commitea nada. Si un sabotaje no tumba ningún test, el trabajo no es repetirlo: es averiguar qué otra cosa está devolviendo la respuesta correcta, y escribir el test que falta.

- [ ] **Step 1: La frontera de las financieras**

Añade `"Credit Services",` a `INDUSTRIAS_FINANCIERAS` en `valoracion/criterio.py`.
Run: `uv run pytest tests/test_valoracion_criterio.py -q`
Expected: FAIL en `test_credit_services_y_los_corredores_no_son_financieras`. Deshaz.

- [ ] **Step 2: La holgura de Gordon**

En `valoracion/dcf.py`, borra las dos líneas `if wacc - g_perpetuo < HOLGURA_GORDON: return None`.
Run: `uv run pytest tests/test_valoracion_dcf.py -q`
Expected: FAIL en `test_sin_holgura_gordon_no_hay_valor`. Deshaz.

- [ ] **Step 3: El EPV nunca vota cara**

En `valoracion/votos.py`, cambia `voto_epv` para que devuelva `Voto(CARA)` cuando `precio > 2 * epv`.
Run: `uv run pytest tests/test_valoracion_votos.py -q`
Expected: FAIL en `test_el_epv_nunca_vota_cara[989.0]` y `[1000000000.0]`. Deshaz.

- [ ] **Step 4: Quemar caja**

En `valoracion/motor.py`, borra el bloque `if margen <= 0: return Voto(NO_APLICA, "quema_caja"), None, None`.
Run: `uv run pytest tests/test_valoracion_motor.py -q`
Expected: FAIL en `test_una_empresa_que_quema_caja_no_vota_flujos`. Deshaz.

- [ ] **Step 5: El JSON estricto**

En `valoracion/plano.py`, haz que `_limpio` devuelva `objeto` tal cual para los `float`.
Run: `uv run pytest tests/test_valoracion_motor.py -q`
Expected: FAIL en `test_un_nan_en_una_procedencia_se_escribe_como_null` y `test_la_valoracion_es_json_estricto_y_lleva_las_claves_del_spec`. Deshaz.

- [ ] **Step 6: La moneda del consenso**

En `valoracion/mercado.py`, borra la comprobación `if str(fila.get("currency", "")) != moneda_estados: return None`.
Run: `uv run pytest tests/test_valoracion_mercado.py -q`
Expected: FAIL en `test_un_consenso_en_otra_moneda_se_descarta`. Deshaz.

- [ ] **Step 7: El perpetuo y la tasa libre**

En `valoracion/supuestos.py`, borra el `if base > r_f:` de `crecimiento_perpetuo` y su `return`.
Run: `uv run pytest tests/test_valoracion_supuestos.py -q`
Expected: FAIL en `test_el_perpetuo_nunca_supera_la_tasa_libre`. Deshaz.

- [ ] **Step 8: Una valoración que revienta**

En `ranking/run.py`, cambia `_valoracion` para que devuelva `valorar(ticker, pilar_valoracion)` sin `try`.
Run: `uv run pytest tests/test_ranking_run.py -q`
Expected: FAIL en `test_una_valoracion_que_revienta_no_tumba_la_corrida`. Deshaz.

- [ ] **Step 9: La lectura tolerante**

En `aprobacion/carga.py`, cambia `valoracion_de` por `return ficha.get("valoracion")`.
Run: `uv run pytest tests/test_aprobacion_carga.py -q`
Expected: FAIL en `test_una_valoracion_sin_version_no_se_lee`. Deshaz.

- [ ] **Step 10: El escapado**

En `medidores_valoracion.py`, cambia `_esc` para que devuelva `str(texto)`.
Run: `uv run pytest tests/test_medidores_valoracion.py -q`
Expected: FAIL en `test_el_resumen_escapa_lo_que_no_es_suyo`. Deshaz.

- [ ] **Step 11: Comprobar que todo quedó como estaba**

Run: `git status --short`
Expected: vacío (ningún fichero modificado).

---

### Task 16: Suite completa y recorrido con la app arrancada

- [ ] **Step 1: La suite normal entera**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: todo verde. El total debe ser el de antes de empezar más los tests nuevos de este plan. Si algo que no es de `valoracion` falla, es una regresión de este trabajo: arréglala antes de seguir.

- [ ] **Step 2: Arrancar la app**

Con las herramientas de vista previa: `preview_start` con `name: "markowitz-app"` (está en `.claude/launch.json` de la raíz del repo). No la arranques con Bash.

- [ ] **Step 3: Generar candidatos sin IA**

En «Revisar candidatos», elige «Sin IA» y pulsa «Generar gratis». Tarda unos minutos: el panel sale de caché y la valoración hace unas sesenta descargas. Comprueba:
- el indicador de progreso menciona el valor intrínseco;
- cada tarjeta lleva un distintivo de veredicto junto al sector;
- al desplegar una ficha aparece «Valoración», con los tres votos, el rango, la fecha, los supuestos y la nota;
- `read_console_messages` y `preview_logs` sin errores.

Haz una captura de la tarjeta y de una ficha desplegada.

- [ ] **Step 4: Una ficha vieja**

Copia `salidas/fichas.json` a `salidas/fichas.json.bak`. Con un script, quita la clave `valoracion` de la primera ficha y guarda. Recarga la página: esa ficha no tiene distintivo y su bloque dice «Sin valoración: ficha de una versión anterior», y las demás se pintan enteras. Restaura el fichero desde `salidas/fichas.json.bak` y borra la copia.

```bash
uv run python -I -c "import json, pathlib; p = pathlib.Path('salidas/fichas.json'); f = json.loads(p.read_text(encoding='utf-8')); f[0].pop('valoracion', None); p.write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding='utf-8')"
```

- [ ] **Step 5: El acta registra la valoración**

Marca un candidato y pulsa «Aprobar 1 empresas y pasar al optimizador». Abre el acta recién escrita en `actas/` y comprueba que su ficha lleva `valoracion`. **Esta acta es de prueba y la escribiste tú**: dile al usuario su nombre y pregúntale si la borra o la conserva; no la borres sin preguntar.

- [ ] **Step 6: Los tests `red`**

Run: `uv run pytest tests/test_valoracion_red.py -v -m red`
Expected: todo verde.

---

### Task 17: La medida sobre el S&P 500

Con el criterio ya congelado. **Una medida, no un ajuste**: si el reparto sale raro, los listones no se mueven desde aquí.

**Files:**
- Create: `scripts/medir_valoracion.py`
- Modify: `docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md` (anexo al final)

- [ ] **Step 1: Escribir el script**

`scripts/medir_valoracion.py`:

```python
"""Reparto de veredictos sobre el S&P 500, con el criterio ya congelado.

Una medida, no un ajuste: si el reparto sale raro, los listones no se mueven
desde aquí, se escribe una enmienda fechada en el spec del sub-proyecto M.

Uso, desde programa/:
    EDGAR_IDENTITY="tu@correo.com" uv run python scripts/medir_valoracion.py

Escribe salidas/medida_valoracion.csv e imprime las tablas que van al anexo.
Tarda: unas cuatro descargas de yfinance por empresa, con caché de un día.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from fundamentals.fetch import set_sec_identity  # noqa: E402
from ranking.run import construir_ranking  # noqa: E402
from valoracion.motor import valorar  # noqa: E402


def main() -> None:
    set_sec_identity()
    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    filas = []
    for ticker, fila in resultado.tabla.iterrows():
        plano = valorar(ticker, fila["valoracion"])
        votos = plano.get("votos", {})
        filas.append(
            {
                "ticker": ticker,
                "sector": fila["sector_gics"],
                "veredicto": plano.get("veredicto", "no_calculada"),
                "motivo": plano.get("motivo"),
                "metodo": plano.get("metodo"),
                **{f"voto_{k}": v["voto"] for k, v in votos.items()},
                **{f"motivo_{k}": v["motivo"] for k, v in votos.items()},
            }
        )
        print(f"{len(filas):>3} {ticker:<6} {filas[-1]['veredicto']}", file=sys.stderr)
    tabla = pd.DataFrame(filas)
    Path("salidas").mkdir(exist_ok=True)
    tabla.to_csv("salidas/medida_valoracion.csv", index=False)

    print("\n## Veredictos\n")
    print(tabla["veredicto"].value_counts().to_markdown())
    print("\n## Veredictos por sector\n")
    print(pd.crosstab(tabla["sector"], tabla["veredicto"]).to_markdown())
    for voto in ("flujos", "sin_crecimiento", "pares"):
        print(f"\n## Voto {voto}\n")
        print(tabla[f"voto_{voto}"].value_counts(dropna=False).to_markdown())
    print("\n## Motivos de no aplica\n")
    print(tabla.filter(like="motivo_").stack().value_counts().to_markdown())
    print("\n## Valoraciones que no se calcularon\n")
    print(tabla["motivo"].value_counts().to_markdown())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Correrlo en segundo plano**

Run (en segundo plano, puede tardar más de diez minutos): `uv run python scripts/medir_valoracion.py > salidas/medida_valoracion.md`
Expected: el fichero con seis tablas en markdown; `salidas/medida_valoracion.csv` con unas 425 filas.

- [ ] **Step 3: Anexar el resultado al spec**

Al final de `docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md`, añade una sección `## Resultado de la medida (AAAA-MM-DD)` con la fecha de la corrida, las seis tablas tal como salieron y tres párrafos:
1. qué proporción del índice sale en cada veredicto;
2. qué sectores concentran los `no_aplica` y por qué motivo;
3. si algún reparto sugiere que un listón está mal calibrado. **No se cambia ninguno aquí**: si hace falta, se propone una enmienda fechada y se le pregunta al usuario.

- [ ] **Step 4: Commit**

```bash
git add scripts/medir_valoracion.py docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md
git commit -m "docs: la medida del valor intrinseco sobre el S&P 500, anexa al spec

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: CONTEXTO.md

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: La tabla de sub-proyectos**

Añade dos filas a «Descomposición en sub-proyectos»:

```markdown
| M | Valor intrínseco | Veredicto por cuatro lecturas y tres votos en cada candidato | ✅ **terminado** |
| N | Analizador individual | La mecánica de candidatos para cualquier ticker, con gráfico, noticias e IA | ⏳ **diseñado** |
```

- [ ] **Step 2: La sección de resultado**

Añade, antes de «La auditoría», una sección `## Resultado del sub-proyecto M` con estos apartados:
- **Qué entrega**: el paquete `valoracion/`, el distintivo y el bloque en Revisar candidatos, y la valoración en el acta.
- **Decisiones que no hay que relitigar**: tres votos y no cuatro (DCF e inverso son la misma ecuación); el EPV nunca vota «cara»; no toca el score; la beta se calcula y nunca se lee de Yahoo; claves y no textos en disco; lo guardado es siempre con supuestos del programa.
- **Defectos encontrados**: los que hayan aparecido al ejecutar este plan, en una tabla «Defecto | Cómo se detectó», como en las secciones de F a L.
- **El resultado de la medida**: el reparto de veredictos de la Task 17, en una frase, con enlace al anexo del spec.
- **Lo que M no resuelve**: copia la lista del spec.

- [ ] **Step 3: La cabecera**

Actualiza «Última actualización», el número de tests y el bloque «Al retomar» para decir que M está en la rama `feat/valor-intrinseco` pendiente de fusionar, y que N tiene spec y espera a M.

- [ ] **Step 4: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: CONTEXTO al dia con el sub-proyecto M

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cobertura del spec

| Sección del spec | Tarea |
|---|---|
| `criterio.py` congelado en commit propio | 1 |
| `fundamentos.py`, 20 trimestres, capex en positivo | 2 |
| `mercado.py`: beta propia, consenso por moneda, caché, motivos | 3, 4 |
| `supuestos.py` con procedencia como dato | 5 |
| DCF, escenarios con el margen del voto, Gordon | 6, 9 |
| Inverso por bisección | 6 |
| EPV y parte del precio que es crecimiento | 7 |
| Beneficio residual y ROE implícito | 7 |
| Votos y veredicto (64 combinaciones) | 8 |
| `plano.py`, claves y no textos, JSON estricto | 9 |
| `ranking/run.py`: valoración por ficha, fallo que no tumba | 10 |
| `aprobacion/carga.valoracion_de` | 11 |
| `medidores_valoracion.py` y distintivo en la tarjeta | 12 |
| `vistas/candidatos.py` y la nota | 13 |
| Tests `red` (TNX, beta, consenso, industrias) | 14 |
| Sabotaje de cada guarda | 15 |
| Un aviso, no quince, cuando todas fallan igual | 13 |
| Recorrido con la app | 16 |
| La medida sobre el S&P 500 | 17 |
| La sensibilidad y `aplicar` | No es de M: el spec los mueve a N |
