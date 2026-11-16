# VaR y Expected Shortfall en el optimizador — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el optimizador diga, para la cartera que acaba de proponer y para cada uno de sus activos, cuánto se puede perder en un mal día (VaR 99 % a 1 día) y cuánto se pierde de media cuando ese día llega (ES 97,5 % y 99 %), con el método que más tiempo pasa en la zona verde del semáforo de Basilea.

**Architecture:** un paquete nuevo `riesgo/` sin Streamlit dentro salvo la descarga: `metodos.py` (seis estimadores de VaR/ES con la misma firma), `backtest.py` (semáforo de Basilea, Kupiec, competencia y elección), `informe.py` (cartera, activos, aportaciones al ES) y `datos.py` (retornos diarios propios). La pantalla `vistas/optimizador.py` lo calcula una vez en `_ejecutar`, lo guarda en la corrida y lo pinta en una pestaña nueva, «Riesgo: VaR y ES».

**Tech Stack:** numpy, scipy (`stats`, `signal.lfilter`), pandas, yfinance, Streamlit, plotly, pytest. Ninguna dependencia nueva.

---

## Decisiones de diseño (léelas antes de escribir código)

1. **Datos diarios siempre, aparte del horizonte.** El semáforo de Basilea está
   definido para VaR al 99 % **a 1 día** sobre las **250 últimas sesiones**. Los
   horizontes de 3 meses en adelante descargan semanas o meses
   (`data.HORIZON_CONFIG`), así que el riesgo no puede reutilizar
   `market["returns"]`: tiene su propia descarga de 5 años diarios
   (≈1.255 retornos). Con una ventana de estimación de 500 sesiones quedan
   ≈755 días de backtest y ≈506 ventanas de 250 sobre las que medir el semáforo.

2. **Los seis métodos que compiten.** Todos con la firma
   `f(r: np.ndarray, alpha: float) -> tuple[float, float]` que devuelve
   `(VaR, ES)` como **pérdidas positivas** en fracción del valor:

   | Clave | Método | Por qué está |
   |---|---|---|
   | `historico` | Simulación histórica, 500 sesiones | La referencia de la industria |
   | `normal` | Varianza-covarianza normal | La referencia paramétrica; se espera que falle en las colas |
   | `t_student` | t de Student, ν por momentos (curtosis) | Colas gruesas sin pagar un ajuste por máxima verosimilitud en cada día |
   | `ewma` | Normal con volatilidad EWMA (RiskMetrics, λ = 0,94) | Reacciona a los clústeres de volatilidad |
   | `fhs` | Histórica filtrada por EWMA | Colas empíricas + volatilidad actual; suele ser el que gana |
   | `cornish_fisher` | Normal corregida por asimetría y curtosis | Paramétrico barato con colas no normales |

   Se descartan GARCH por máxima verosimilitud (un ajuste por día y serie: lento
   y frágil, y EWMA es su caso integrado) y Monte Carlo (con los mismos
   supuestos que el paramétrico no da otra respuesta, sólo ruido).

3. **Clave y etiqueta separadas**, como `optimizer.STRATEGY_LABELS` y
   `data.HORIZON_LABELS`: la clave es dato, la etiqueta es pantalla. Hoy nada
   de esto va a disco, pero si un día va, ya está hecho bien.

4. **Los límites del semáforo se calculan, no se copian.** Basilea define la
   zona verde como el número de excepciones cuya probabilidad acumulada
   binomial es menor del 95 %, y la roja desde el 99,99 %. Con n = 250 y
   p = 1 % sale verde 0–4, amarilla 5–9, roja 10+, que es la tabla publicada; un
   test lo fija.

5. **«Zona verde la mayor parte del tiempo», medido así:** se cuentan las
   excepciones de cada ventana móvil de 250 días del backtest, y la fracción de
   ventanas con ≤ 4 es la **fracción verde** del método. Gana la mayor.
   **Desempates, en este orden:** la tasa de excepciones más cercana al 1 %
   (un método absurdamente conservador también está siempre en verde, y no
   sirve), y después el VaR medio más bajo (el que menos capital inmoviliza a
   igual acierto).

6. **ES: 97,5 % (el nivel de FRTB) y 99 % (el del VaR).** El semáforo sólo
   backtestea VaR; para el ES se enseña una comprobación sencilla: en los días
   en que la pérdida supera el VaR 97,5 %, la pérdida media realizada entre el
   ES previsto medio. Cerca de 1 está bien; por encima de 1 el ES se queda
   corto.

7. **La cartera es la que el optimizador acaba de proponer, con pesos
   constantes** (rebalanceo diario implícito, el backtest «hipotético» de
   siempre). Esos pesos se eligieron con datos del mismo periodo; para medir la
   cola de la pérdida eso no sesga el conteo de excepciones como sesgaría un
   Sharpe, y la pantalla lo dice en una línea.

8. **Por activo, tres cosas:** el VaR/ES del activo solo, con **su propia
   competencia** (cada serie elige su método: una utility y una
   semiconductora no tienen por qué ganar con el mismo); su zona y fracción
   verde; y su **aportación al ES de la cartera** (Euler por escenarios: la
   media de `w_i·r_i` en los días de cola de la cartera, en cuotas que suman
   100 %, escaladas al ES del método elegido). Más el **beneficio de
   diversificación**: `1 − ES_cartera / Σ|w_i|·ES_i`.

9. **Se calcula en `_ejecutar` y se guarda en la corrida**, como la
   validación: cambiar de pestaña o descargar no repite la descarga ni el
   backtest. Si la historia común no llega al mínimo, se guarda el motivo y la
   pestaña lo dice nombrando al activo con menos sesiones.

10. **Fuera de alcance:** el PDF/Excel y el JSON guardado. Primero pantalla; si
    convence, va al informe en un plan aparte. **No se tocan** `vistas/candidatos.py`,
    `vistas/analizador.py` ni `analizador/`: hay otra sesión trabajando ahí.

## Mapa de ficheros

- Create: `riesgo/__init__.py` — vacío.
- Create: `riesgo/metodos.py` — los seis estimadores, `METODOS`, `ETIQUETAS`.
- Create: `riesgo/backtest.py` — `limites_semaforo`, `zona`, `kupiec`, `pronosticos`, `Backtest`, `backtestear`, `competir`, `elegir`.
- Create: `riesgo/informe.py` — `HistoriaInsuficiente`, `FilaActivo`, `InformeRiesgo`, `informe_riesgo`.
- Create: `riesgo/datos.py` — `retornos_diarios` (cacheada).
- Create: `scripts/medir_var.py` — la competencia sobre carteras reales, para el documento de investigación.
- Create: `docs/research/2026-11-15-var-metodos.md` — resultados medidos.
- Modify: `charts.py` — `plot_backtest_var`.
- Modify: `vistas/optimizador.py` — cálculo en `_ejecutar`, pestaña nueva.
- Modify: `CONTEXTO.md` — sub-proyecto O.
- Test: `tests/test_riesgo_metodos.py`, `tests/test_riesgo_backtest.py`, `tests/test_riesgo_informe.py`, `tests/test_riesgo_datos.py`, `tests/test_charts.py` (añadir), `tests/test_vistas_optimizador.py` (añadir).

Todos los comandos desde `programa/`.

---

### Task 1: los estimadores

**Files:**
- Create: `riesgo/__init__.py`, `riesgo/metodos.py`
- Test: `tests/test_riesgo_metodos.py`

- [ ] **Step 1: Write the failing tests**

```python
# programa/tests/test_riesgo_metodos.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_riesgo_metodos.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'riesgo'`

- [ ] **Step 3: Write the implementation**

`riesgo/__init__.py` vacío. Y:

```python
# programa/riesgo/metodos.py
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
# ν por momentos: la curtosis de una t sólo existe por encima de 4.
_NU_MIN, _NU_MAX = 4.1, 30.0


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_riesgo_metodos.py -q`
Expected: PASS. Si `test_sobre_normales_todos_dan_el_valor_normal` falla sólo para `t_student` es que ν no está llegando a 30 con curtosis ≈ 0: revisar la rama `exceso <= 0`, no aflojar la tolerancia.

- [ ] **Step 5: Commit**

```bash
git add riesgo/__init__.py riesgo/metodos.py tests/test_riesgo_metodos.py
git commit -m "feat: seis estimadores de VaR y ES con la misma firma"
```

---

### Task 2: el semáforo de Basilea y Kupiec

**Files:**
- Create: `riesgo/backtest.py`
- Test: `tests/test_riesgo_backtest.py`

- [ ] **Step 1: Write the failing tests**

```python
# programa/tests/test_riesgo_backtest.py
import numpy as np
import pytest

from riesgo import backtest


def test_los_limites_son_los_de_la_tabla_de_basilea():
    """0–4 verde, 5–9 amarilla, 10+ roja, con 250 días al 99 %."""
    assert backtest.limites_semaforo(250, 0.99) == (4, 9)


@pytest.mark.parametrize("x, esperada", [(0, "verde"), (4, "verde"), (5, "amarilla"),
                                         (9, "amarilla"), (10, "roja"), (40, "roja")])
def test_zona(x, esperada):
    assert backtest.zona(x) == esperada


def test_kupiec_no_rechaza_la_tasa_exacta_y_si_el_doble_largo():
    assert backtest.kupiec(10, 1000, 0.01) == pytest.approx(1.0)
    assert backtest.kupiec(30, 1000, 0.01) < 0.001
    assert 0 < backtest.kupiec(0, 1000, 0.01) < 0.001
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_riesgo_backtest.py -q`
Expected: FAIL, `ImportError: cannot import name 'backtest'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_riesgo_backtest.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add riesgo/backtest.py tests/test_riesgo_backtest.py
git commit -m "feat: semáforo de Basilea calculado del binomial y test de Kupiec"
```

---

### Task 3: el backtest de un método y la competencia

**Files:**
- Modify: `riesgo/backtest.py`
- Test: `tests/test_riesgo_backtest.py`

- [ ] **Step 1: Write the failing tests** (añadir al fichero)

```python
from riesgo import metodos


def _garch(n, semilla, omega=2e-6, a=0.10, b=0.88):
    """Retornos con clústeres de volatilidad, que es lo que tiene el mercado."""
    rng = np.random.default_rng(semilla)
    r, v = np.empty(n), omega / (1 - a - b)
    for i in range(n):
        r[i] = np.sqrt(v) * rng.standard_normal()
        v = omega + a * r[i] ** 2 + b * v
    return r


def test_pronosticos_solo_miran_el_pasado():
    r = np.random.default_rng(3).normal(0, 0.01, 800)
    p = backtest.pronosticos(r, "historico")
    assert len(p["var99"]) == 800 - backtest.VENTANA_ESTIMACION
    # Cambiar el último día no puede cambiar ninguna previsión: ninguna lo mira.
    r2 = r.copy()
    r2[-1] = -0.5
    np.testing.assert_array_equal(p["var99"], backtest.pronosticos(r2, "historico")["var99"])


def test_sobre_normales_iid_la_normal_acierta_la_tasa():
    r = np.random.default_rng(4).normal(0, 0.01, 3000)
    bt = backtest.backtestear(r, "normal")
    assert bt.tasa == pytest.approx(0.01, abs=0.005)
    assert bt.fraccion_verde > 0.8


def test_con_clusteres_ewma_pasa_mas_tiempo_en_verde_que_la_normal():
    r = _garch(3000, 5)
    assert backtest.backtestear(r, "ewma").fraccion_verde > \
        backtest.backtestear(r, "normal").fraccion_verde


def test_la_fraccion_verde_cuenta_ventanas_de_250():
    r = np.random.default_rng(6).normal(0, 0.01, 1000)
    bt = backtest.backtestear(r, "normal")
    conteos = np.convolve(bt.excepciones.astype(int), np.ones(250, int), "valid")
    assert bt.fraccion_verde == pytest.approx(np.mean(conteos <= 4))
    assert bt.excepciones_ultimas == conteos[-1]
    assert bt.zona_actual == backtest.zona(int(conteos[-1]))


def _bt(metodo, verde, tasa, var_medio):
    return backtest.Backtest(
        metodo=metodo, var99=np.array([var_medio]), es975=np.array([0.0]),
        es99=np.array([0.0]), var975=np.array([0.0]), realizados=np.array([0.0]),
        excepciones=np.array([False]), fraccion_verde=verde, zona_actual="verde",
        excepciones_ultimas=0, tasa=tasa, kupiec_p=1.0, razon_es=1.0,
    )


def test_elegir_gana_el_mas_verde():
    assert backtest.elegir({"a": _bt("a", 0.7, 0.01, 1), "b": _bt("b", 0.9, 0.02, 1)}) == "b"


def test_elegir_empata_por_la_tasa_mas_cercana_al_uno_por_ciento():
    """El conservador de más también está siempre en verde, y no sirve."""
    assert backtest.elegir({"a": _bt("a", 1.0, 0.001, 1), "b": _bt("b", 1.0, 0.009, 1)}) == "b"


def test_elegir_luego_por_el_var_mas_bajo():
    assert backtest.elegir({"a": _bt("a", 1.0, 0.01, 2), "b": _bt("b", 1.0, 0.01, 1)}) == "b"


def test_competir_corre_los_seis():
    r = _garch(1200, 7)
    assert set(backtest.competir(r)) == set(metodos.METODOS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_riesgo_backtest.py -q`
Expected: FAIL, `AttributeError: module 'riesgo.backtest' has no attribute 'pronosticos'`

- [ ] **Step 3: Write the implementation** (añadir a `riesgo/backtest.py`)

```python
from dataclasses import dataclass

from riesgo import metodos

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_riesgo_backtest.py -q`
Expected: PASS. Si `test_con_clusteres_ewma_pasa_mas_tiempo_en_verde_que_la_normal` falla, **no cambiar la semilla para que pase**: imprimir las dos fracciones; si están empatadas en 1.0, subir la persistencia (`b=0.90`) para que el caso tenga clústeres de verdad, y escribir en el docstring por qué.

- [ ] **Step 5: Commit**

```bash
git add riesgo/backtest.py tests/test_riesgo_backtest.py
git commit -m "feat: backtest por método y elección por tiempo en zona verde"
```

---

### Task 4: el informe de la cartera y de cada activo

**Files:**
- Create: `riesgo/informe.py`
- Test: `tests/test_riesgo_informe.py`

- [ ] **Step 1: Write the failing tests**

```python
# programa/tests/test_riesgo_informe.py
import numpy as np
import pandas as pd
import pytest

from riesgo import backtest, informe


def _retornos(n=900, semilla=0):
    rng = np.random.default_rng(semilla)
    comun = rng.normal(0, 0.008, n)
    datos = {
        "AAA": comun + rng.normal(0, 0.006, n),
        "BBB": comun + rng.normal(0, 0.012, n),
        "CCC": rng.standard_t(4, n) * 0.007,
    }
    return pd.DataFrame(datos, index=pd.bdate_range("2021-01-01", periods=n))


def test_el_informe_trae_la_cartera_y_cada_activo():
    r = _retornos()
    inf = informe.informe_riesgo(r, np.array([0.5, 0.3, 0.2]))
    assert inf.elegido in inf.competencia
    assert [f.ticker for f in inf.activos] == ["AAA", "BBB", "CCC"]
    assert inf.es975 >= inf.var99 * 0.9  # mismo orden de magnitud: el ES97,5 ≈ VaR99
    assert inf.es99 >= inf.var99 > 0


def test_el_var_de_hoy_es_el_del_metodo_elegido_sobre_la_ultima_ventana():
    r = _retornos()
    w = np.array([0.5, 0.3, 0.2])
    inf = informe.informe_riesgo(r, w)
    rp = r.to_numpy() @ w
    from riesgo import metodos
    var, _ = metodos.METODOS[inf.elegido](rp[-backtest.VENTANA_ESTIMACION:], 0.99)
    assert inf.var99 == pytest.approx(var)


def test_las_aportaciones_al_es_suman_el_cien_por_cien():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    assert sum(f.aportacion_es for f in inf.activos) == pytest.approx(1.0)


def test_diversificar_reduce_el_es():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    assert 0 < inf.diversificacion < 1


def test_cada_activo_elige_su_propio_metodo():
    inf = informe.informe_riesgo(_retornos(), np.array([0.5, 0.3, 0.2]))
    for f in inf.activos:
        assert f.metodo in inf.competencia  # misma lista de candidatos


def test_con_poca_historia_dice_cuanta_hay_y_cuanta_falta():
    with pytest.raises(informe.HistoriaInsuficiente) as e:
        informe.informe_riesgo(_retornos(n=600), np.array([0.5, 0.3, 0.2]))
    assert e.value.observaciones == 600
    assert e.value.necesarias == backtest.MINIMO_OBSERVACIONES


def test_los_pesos_tienen_que_cuadrar_con_las_columnas():
    with pytest.raises(ValueError):
        informe.informe_riesgo(_retornos(), np.array([0.5, 0.5]))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_riesgo_informe.py -q`
Expected: FAIL, `ImportError: cannot import name 'informe'`

- [ ] **Step 3: Write the implementation**

```python
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

    matriz = retornos.to_numpy()
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_riesgo_informe.py -q`
Expected: PASS. Medir el tiempo: `uv run pytest tests/test_riesgo_informe.py -q --durations=3`. Si `informe_riesgo` sobre 900×3 pasa de ~3 s, el cuello es `pronosticos` (bucle Python); antes de optimizar, confirmar con un perfil.

- [ ] **Step 5: Commit**

```bash
git add riesgo/informe.py tests/test_riesgo_informe.py
git commit -m "feat: VaR y ES de la cartera y de cada activo, con aportaciones al ES"
```

---

### Task 5: los retornos diarios

**Files:**
- Create: `riesgo/datos.py`
- Test: `tests/test_riesgo_datos.py`

- [ ] **Step 1: Write the failing tests**

```python
# programa/tests/test_riesgo_datos.py
import numpy as np
import pandas as pd

from riesgo import datos


def _descarga_falsa(precios):
    def fake(tickers, **kw):
        assert kw["interval"] == "1d" and kw["period"] == datos.PERIODO_DIARIO
        return pd.concat({"Close": precios[tickers]}, axis=1)
    return fake


def test_descarga_diaria_y_devuelve_retornos_comunes(monkeypatch):
    idx = pd.bdate_range("2022-01-03", periods=6)
    precios = pd.DataFrame({"AAA": [10, 11, 12, 11, 12, 13.0],
                            "BBB": [np.nan, np.nan, 20, 21, 22, 23.0]}, index=idx)
    monkeypatch.setattr(datos.yf, "download", _descarga_falsa(precios))
    salida = datos.retornos_diarios.__wrapped__(("AAA", "BBB"))
    assert list(salida["retornos"].columns) == ["AAA", "BBB"]
    assert len(salida["retornos"]) == 3          # sólo donde cotizan los dos
    assert salida["sesiones"] == {"AAA": 6, "BBB": 4}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_riesgo_datos.py -q`
Expected: FAIL, `ImportError: cannot import name 'datos'`

- [ ] **Step 3: Write the implementation**

```python
# programa/riesgo/datos.py
"""Retornos diarios para el VaR, aparte de los del horizonte elegido.

El semáforo de Basilea está definido a un día; con el horizonte de un año el
optimizador trabaja con meses, y de ahí no sale un VaR diario.
"""

import pandas as pd
import streamlit as st
import yfinance as yf

from data import compute_returns

# 5 años ≈ 1.255 sesiones: 500 para estimar y ≈ 750 de backtest.
PERIODO_DIARIO = "5y"


@st.cache_data(ttl=3600)
def retornos_diarios(tickers: tuple[str, ...]) -> dict:
    raw = yf.download(list(tickers), period=PERIODO_DIARIO, interval="1d",
                      auto_adjust=True, progress=False)
    precios = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        precios = precios.rename(columns={"Close": tickers[0]})
    precios = precios.reindex(columns=list(tickers)).dropna(how="all")
    return {
        "retornos": compute_returns(precios),
        "sesiones": {t: int(precios[t].notna().sum()) for t in tickers},
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_riesgo_datos.py -q`
Expected: PASS. (`__wrapped__` es la función sin caché que expone `st.cache_data`; si la versión de Streamlit instalada no lo expone, mirar cómo lo resuelve `tests/test_data.py` y hacer lo mismo.)

- [ ] **Step 5: Commit**

```bash
git add riesgo/datos.py tests/test_riesgo_datos.py
git commit -m "feat: descarga diaria propia para el VaR"
```

---

### Task 6: el gráfico del backtest

**Files:**
- Modify: `charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write the failing test** (añadir)

```python
def test_plot_backtest_var_pinta_retornos_var_y_excepciones():
    import numpy as np
    import pandas as pd
    from charts import plot_backtest_var

    fechas = pd.bdate_range("2024-01-01", periods=5)
    fig = plot_backtest_var(fechas, np.array([0.01, -0.03, 0.0, -0.01, 0.02]),
                            np.array([0.02] * 5), np.array([False, True, False, False, False]))
    nombres = [t.name for t in fig.data]
    assert nombres == ["Retorno diario", "−VaR 99 %", "Excepción"]
    assert list(fig.data[2].y) == [-0.03]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_charts.py -q -k backtest`
Expected: FAIL, `ImportError: cannot import name 'plot_backtest_var'`

- [ ] **Step 3: Write the implementation** (añadir a `charts.py`, usando el `_base_layout` que ya existe)

```python
def plot_backtest_var(fechas, realizados, var99, excepciones) -> go.Figure:
    """Cada día, lo que pasó contra lo que el VaR de la víspera dijo que podía pasar."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=fechas, y=realizados, name="Retorno diario",
                         marker_color="rgba(120,120,140,0.45)"))
    fig.add_trace(go.Scatter(x=fechas, y=-np.asarray(var99), name="−VaR 99 %",
                             mode="lines", line=dict(width=1.5)))
    fig.add_trace(go.Scatter(x=fechas[excepciones], y=np.asarray(realizados)[excepciones],
                             name="Excepción", mode="markers",
                             marker=dict(color="crimson", size=7, symbol="x")))
    fig.update_layout(**_base_layout(yaxis_tickformat=".1%", bargap=0))
    return fig
```

Comprobar antes que `_base_layout(**extra)` acepta esas claves (`charts.py:20`); si no, pasarlas a `update_layout` aparte.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_charts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add charts.py tests/test_charts.py
git commit -m "feat: gráfico del backtest del VaR con sus excepciones"
```

---

### Task 7: la pestaña en el optimizador

**Files:**
- Modify: `vistas/optimizador.py` (imports, `_ejecutar` ~línea 350–520, `st.tabs` ~línea 692, nueva sección tras `with graficos:`)
- Test: `tests/test_vistas_optimizador.py`

- [ ] **Step 1: Write the failing tests** (añadir, con el mismo recurso de leer la fuente)

```python
def test_el_riesgo_se_calcula_una_vez_en_la_corrida():
    """Como la validación: repintar no puede volver a descargar ni backtestear."""
    cuerpo = _cuerpo("_ejecutar")
    assert "informe_riesgo(" in cuerpo
    assert '"riesgo":' in cuerpo
    assert FUENTE.count("informe_riesgo(") == 1


def test_la_falta_de_historia_se_explica_y_no_tumba_la_corrida():
    cuerpo = _cuerpo("_ejecutar")
    assert "except HistoriaInsuficiente" in cuerpo


def test_hay_pestana_de_riesgo():
    assert '"Riesgo: VaR y ES"' in FUENTE
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_vistas_optimizador.py -q`
Expected: los tres nuevos FAIL.

- [ ] **Step 3: Write the implementation**

Imports, junto a los demás:

```python
from charts import plot_backtest_var  # añadir al import de charts existente
from riesgo.backtest import limites_semaforo
from riesgo.datos import retornos_diarios
from riesgo.informe import HistoriaInsuficiente, informe_riesgo
from riesgo.metodos import ETIQUETAS as ETIQUETAS_RIESGO
```

En `_ejecutar`, después del bloque del walk-forward y antes del `benchmark`:

```python
    with st.spinner("Midiendo el riesgo de cola (VaR y ES)…"):
        # Diario siempre, sea cual sea el horizonte: el semáforo de Basilea
        # está definido a un día. Si falta historia no se para la corrida —el
        # reparto sigue valiendo—; se guarda el motivo y la pestaña lo dice.
        diarios = retornos_diarios(tuple(valid_tickers))
        try:
            riesgo = informe_riesgo(
                diarios["retornos"].reindex(columns=valid_tickers).dropna(),
                optimal["weights"],
            )
        except HistoriaInsuficiente as falta:
            sesiones = diarios["sesiones"]
            corto = min(sesiones, key=sesiones.get)
            riesgo = {"falta": falta, "corto": corto, "sesiones": sesiones[corto]}
```

y en el `return` de `_ejecutar`, `"riesgo": riesgo,`.

Pestañas:

```python
resumen, validacion, graficos, riesgo_tab, exportar = st.tabs(
    ["Resumen", "Validación fuera de muestra", "Gráficos", "Riesgo: VaR y ES",
     "Guardar y exportar"]
)
```

Y la sección, antes de `with exportar:`:

```python
# ── Riesgo: VaR y ES ─────────────────────────────────────────────────────────
with riesgo_tab:
    inf = corrida.get("riesgo")
    if inf is None:
        st.info("Esta corrida es de antes de medir el riesgo. Vuelve a optimizar.")
    elif isinstance(inf, dict):
        falta = inf["falta"]
        st.warning(
            f"Para backtestear el VaR hacen falta {falta.necesarias} sesiones "
            f"diarias comunes y hay {falta.observaciones}. La que más recorta es "
            f"**{inf['corto']}**, con {inf['sesiones']}: sin ella, o con activos "
            "con más historia, la pestaña se llena."
        )
    else:
        verde, amarilla = limites_semaforo()
        ganador = inf.competencia[inf.elegido]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("VaR 99 % · 1 día", f"{inf.var99:.2%}")
        k2.metric("ES 97,5 % · 1 día", f"{inf.es975:.2%}")
        k3.metric("ES 99 % · 1 día", f"{inf.es99:.2%}")
        k4.metric("Zona hoy", ganador.zona_actual.capitalize(),
                  f"{ganador.excepciones_ultimas} excepciones en 250 días",
                  delta_color="off")
        st.caption(
            f"Método: **{ETIQUETAS_RIESGO[inf.elegido]}**, el que más tiempo pasó "
            f"en zona verde ({ganador.fraccion_verde:.0%} de las ventanas de 250 "
            f"días). Verde es 0–{verde} excepciones; amarilla, {verde + 1}–{amarilla}. "
            f"A 10 días, escalando por √10 como Basilea: VaR {inf.var99 * 10 ** 0.5:.2%}. "
            "Los pesos se mantienen fijos en todo el historial y son los de esta "
            "corrida."
        )
        st.markdown("##### Los seis métodos, medidos sobre esta cartera")
        st.dataframe(pd.DataFrame([{
            "Método": ETIQUETAS_RIESGO[m] + (" ✓" if m == inf.elegido else ""),
            "Tiempo en verde": f"{b.fraccion_verde:.0%}",
            "Zona hoy": b.zona_actual,
            "Excepciones (250 d)": b.excepciones_ultimas,
            "Tasa total": f"{b.tasa:.2%}",
            "Kupiec p": f"{b.kupiec_p:.2f}",
            "Pérdida en cola / ES": f"{b.razon_es:.2f}",
        } for m, b in inf.competencia.items()]), hide_index=True, use_container_width=True)
        st.caption("«Pérdida en cola / ES»: en los días peores que el VaR 97,5 %, "
                   "lo que se perdió entre lo que el ES decía. Por encima de 1, el "
                   "ES se queda corto.")
        st.markdown("##### Por activo")
        st.dataframe(pd.DataFrame([{
            "Ticker": f.ticker, "Peso": f"{f.peso:.1%}",
            "VaR 99 %": f"{f.var99:.2%}", "ES 97,5 %": f"{f.es975:.2%}",
            "ES 99 %": f"{f.es99:.2%}", "Método": ETIQUETAS_RIESGO[f.metodo],
            "Zona hoy": f.zona_actual, "Tiempo en verde": f"{f.fraccion_verde:.0%}",
            "Aporta al ES": f"{f.aportacion_es:.1%}",
        } for f in inf.activos]), hide_index=True, use_container_width=True)
        st.caption(f"Diversificar quita un {inf.diversificacion:.0%} del ES que "
                   "sumarían los activos por separado.")
        st.plotly_chart(
            plot_backtest_var(inf.fechas, ganador.realizados, ganador.var99,
                              ganador.excepciones),
            use_container_width=True, key="grafico_backtest_var",
        )
```

Si el resto del fichero ya no usa `use_container_width` (Streamlit lo ha ido
sustituyendo por `width="stretch"`), usar lo que use el fichero.

- [ ] **Step 4: Run the suite and the app**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: todo en verde (3.494 + los nuevos).

Luego arrancar la app con `preview_start` (configuración de `.claude/launch.json`; si no existe, `uv run streamlit run app.py` desde `programa/`), optimizar los cinco tickers por defecto con horizonte «1 Año» (el caso mensual, el que obliga a la descarga diaria aparte) y comprobar: la pestaña sale llena, la tabla tiene seis filas con una marcada, el gráfico pinta las equis en los días de excepción, y cambiar a la pestaña «Gráficos» y volver no relanza el spinner. Probar también con un ticker joven (p. ej. uno con menos de tres años) para ver el aviso de historia.

- [ ] **Step 5: Commit**

```bash
git add vistas/optimizador.py tests/test_vistas_optimizador.py
git commit -m "feat: pestaña de VaR y ES en el optimizador"
```

---

### Task 8: medir qué método gana de verdad

La competencia ya se hace en cada corrida, pero hace falta saber qué gana en
carteras reales, para escribirlo y para detectar si algún método no gana
nunca (y sobra).

**Files:**
- Create: `scripts/medir_var.py`
- Create: `docs/research/2026-11-15-var-metodos.md`

- [ ] **Step 1: Write the script**

```python
# programa/scripts/medir_var.py
"""Corre la competencia de VaR sobre carteras reales a pesos iguales.

    uv run python scripts/medir_var.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riesgo import backtest  # noqa: E402
from riesgo.datos import retornos_diarios  # noqa: E402
from riesgo.metodos import ETIQUETAS  # noqa: E402

CARTERAS = {
    "Tecnológicas": ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"),
    "Defensivas": ("KO", "PG", "JNJ", "XOM", "WMT"),
    "Mixta con bonos": ("SPY", "TLT", "GLD", "VNQ"),
    "Volátiles": ("TSLA", "AMD", "COIN", "PLTR"),
}

for nombre, tickers in CARTERAS.items():
    r = retornos_diarios.__wrapped__(tickers)["retornos"].dropna()
    rp = r.to_numpy() @ np.full(len(tickers), 1 / len(tickers))
    res = backtest.competir(rp)
    ganador = backtest.elegir(res)
    print(f"\n## {nombre} ({len(rp)} sesiones) — gana {ETIQUETAS[ganador]}\n")
    print("| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES |")
    print("|---|---|---|---|---|---|")
    for m, b in res.items():
        print(f"| {ETIQUETAS[m]} | {b.fraccion_verde:.0%} | {b.zona_actual} | "
              f"{b.tasa:.2%} | {b.kupiec_p:.2f} | {b.razon_es:.2f} |")
```

- [ ] **Step 2: Run it**

Run: `uv run python scripts/medir_var.py`
Expected: cuatro tablas. Lo esperado por la literatura es que `fhs` o `ewma` ganen y que `normal` pase menos tiempo en verde; **si no sale así, se escribe lo que sale**, no lo esperado.

- [ ] **Step 3: Write the research note**

`docs/research/2026-11-15-var-metodos.md`: fecha de la descarga, las cuatro
tablas tal cual, qué ganó en cada cartera, y una conclusión de dos o tres
frases. Si un método no gana en ninguna y tampoco queda segundo, decirlo —
es candidato a quitarse, pero eso se decide con el usuario, no en este plan.

- [ ] **Step 4: Commit**

```bash
git add scripts/medir_var.py docs/research/2026-11-15-var-metodos.md
git commit -m "docs: qué método de VaR pasa más tiempo en verde en carteras reales"
```

---

### Task 9: CONTEXTO

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1:** Añadir la fila `| O | VaR y ES en el optimizador | VaR 99 % y ES 97,5/99 % de la cartera y por activo, método elegido por el semáforo de Basilea | ✅ terminado |` a la tabla de sub-proyectos, una sección «Resultado del sub-proyecto O» con las decisiones 1, 5, 8 y 10 de este plan y el resultado de la Task 8, actualizar la cuenta de tests y la fecha de cabecera.

- [ ] **Step 2: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: CONTEXTO con el sub-proyecto O"
```

---

## Lo que este plan deja fuera, a propósito

- VaR/ES en el PDF, el Excel y el JSON del portafolio guardado.
- Backtest del ES con un test formal (Acerbi-Székely); aquí sólo la razón cola/ES.
- Christoffersen (independencia de excepciones): la fracción verde por ventanas
  móviles ya castiga los clústeres, que es lo que ese test mide.
- VaR en pesos del capital invertido: el optimizador no conoce el capital; el
  Seguimiento sí, y ahí tendría sentido en un plan aparte.
