# Sub-proyecto B — Agentes de análisis y ranking · Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usa superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para ejecutar este plan tarea a tarea. Los pasos usan casillas (`- [ ]`) para el seguimiento.

**Objetivo:** convertir el panel de KPIs del sub-proyecto A en un top de hasta 15 empresas, ordenado por un score determinista y acompañado de fichas trazables.

**Arquitectura:** paquete nuevo `ranking/`, hermano de `fundamentals/` y `research/`. El criterio se congela en `ranking/criterio.py` como datos, antes de calcular ningún ranking. El score y la selección son aritmética pura sin red. El LLM vive aislado en `ranking/llm.py`, sólo redacta, y su ausencia degrada a fichas de plantilla sin romper nada.

**Stack:** Python 3.11+, pandas, numpy, pytest, edgartools (ya instalado), anthropic 0.100 + pydantic 2 (a añadir).

**Diseño de referencia:** [`docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md`](../specs/2026-08-12-agentes-analisis-ranking-design.md), incluida la enmienda 1.

**Convenciones del repo, para no romperlas:**
- Docstrings del código fuente **en inglés**, explicando *por qué*, no *qué*. Tests y documentación **en español**.
- Tests en `tests/test_ranking_<modulo>.py`.
- Nada de red en la suite normal. Los tests que la necesitan van marcados `red`.
- Suite completa: `pytest tests/ -q -m "not red"`. Debe seguir pasando en verde después de cada tarea.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `ranking/__init__.py` | Vacío |
| `ranking/criterio.py` | Datos congelados: pilares, pesos, signos, umbrales. Sin lógica |
| `ranking/score.py` | Ventana, pilares, guardas, compuesto re-estandarizado |
| `ranking/seleccion.py` | Orden global, tope sectorial, empates deterministas |
| `ranking/fichas.py` | Mitad numérica de la ficha; ensamblaje final |
| `ranking/filings.py` | Item 1A vía edgartools, con caché y tope duro |
| `ranking/llm.py` | Esquema, llamada a Sonnet 5, verificación de citas, caché |
| `ranking/informe.py` | Render del `informe.md` |
| `ranking/run.py` | Orquestación y escritura de las tres salidas |

---

### Task 1: Paquete y criterio congelado

Este commit es el **pre-registro**. Su fecha es la prueba de que los umbrales no se movieron al ver los números. No calcules ningún ranking antes de que esté hecho.

**Files:**
- Create: `ranking/__init__.py`
- Create: `ranking/criterio.py`
- Test: `tests/test_ranking_criterio.py`
- Modify: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_criterio.py`:

```python
from itertools import chain

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking import criterio


def test_los_pilares_cubren_los_17_kpis_sin_solaparse():
    asignados = list(chain.from_iterable(criterio.PILARES.values()))
    assert len(asignados) == len(set(asignados)), "algún KPI está en dos pilares"
    assert set(asignados) == set(TODOS_LOS_KPIS)


def test_los_17_kpis_tienen_signo_declarado():
    # Un KPI sin signo produciría un ranking plausible y al revés.
    assert set(criterio.SIGNOS) == set(TODOS_LOS_KPIS)
    assert set(criterio.SIGNOS.values()) <= {1, -1}


def test_los_multiplos_y_la_deuda_van_invertidos():
    # Un PER alto significa caro, no bueno.
    for kpi in criterio.PILARES["valoracion"]:
        assert criterio.SIGNOS[kpi] == -1, kpi
    assert criterio.SIGNOS["deuda_neta_ebitda"] == -1


def test_los_pesos_suman_uno_y_cubren_los_pilares():
    assert sum(criterio.PESOS.values()) == 1.0
    assert set(criterio.PESOS) == set(criterio.PILARES)
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_criterio.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking'`

- [ ] **Step 3: Crea el paquete y el criterio**

`ranking/__init__.py`: fichero vacío.

`ranking/criterio.py`:

```python
"""The selection criterion, frozen before any ranking is computed.

Data, not logic: the date of the commit that introduces this file is the proof
that the thresholds did not move once the numbers were visible. Changing it
requires a dated amendment in the design document, never a silent edit.
"""

PILARES: dict[str, tuple[str, ...]] = {
    "calidad": (
        "margen_bruto",
        "margen_operativo",
        "margen_neto",
        "roe",
        "roic",
        "margen_fcf",
        "fcf_sobre_beneficio",
    ),
    "crecimiento": (
        "crecimiento_ingresos",
        "crecimiento_bpa",
        "crecimiento_fcf",
    ),
    "valoracion": (
        "per",
        "ev_ebitda",
        "precio_fcf",
        "precio_valor_libro",
    ),
    "solidez": (
        "deuda_neta_ebitda",
        "cobertura_intereses",
        "razon_corriente",
    ),
}

PESOS: dict[str, float] = {
    "calidad": 0.25,
    "crecimiento": 0.25,
    "valoracion": 0.25,
    "solidez": 0.25,
}

# +1 means higher is better, -1 means higher is worse.
#
# Declared one by one rather than derived from a list of exceptions, so a test
# can assert that all 17 carry a sign. A KPI whose sign was forgotten would
# produce a plausible ranking that is exactly backwards, and nothing about the
# output would look wrong.
SIGNOS: dict[str, int] = {
    "margen_bruto": 1,
    "margen_operativo": 1,
    "margen_neto": 1,
    "roe": 1,
    "roic": 1,
    "margen_fcf": 1,
    "fcf_sobre_beneficio": 1,
    "crecimiento_ingresos": 1,
    "crecimiento_bpa": 1,
    "crecimiento_fcf": 1,
    "razon_corriente": 1,
    "cobertura_intereses": 1,
    "deuda_neta_ebitda": -1,
    "per": -1,
    "ev_ebitda": -1,
    "precio_fcf": -1,
    "precio_valor_libro": -1,
}

TRIMESTRES_VENTANA = 4
MIN_TRIMESTRES_HISTORIA = 4
MAX_ANTIGUEDAD_TRIMESTRES = 2
MIN_PILARES_CON_DATO = 4
MIN_KPIS_CON_DATO = 8
TOPE_POR_SECTOR = 3
TAMANO_TOP = 15
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_criterio.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Añade la caché al .gitignore y las dependencias**

Añade al final de `.gitignore`:

```
ranking/.cache/
```

Añade al final de `requirements.txt`:

```
# Fichas del sub-proyecto B (paquete ranking/). Necesita ANTHROPIC_API_KEY en el
# entorno; sin ella el ranking sale igual con fichas de plantilla.
anthropic>=0.100
pydantic>=2.0
```

- [ ] **Step 6: Commit**

```bash
git add ranking/__init__.py ranking/criterio.py tests/test_ranking_criterio.py .gitignore requirements.txt
git commit -m "feat: criterio de seleccion congelado antes de medir"
```

---

### Task 2: Media de la ventana de 4 trimestres

**Files:**
- Create: `ranking/score.py`
- Test: `tests/test_ranking_score.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_score.py`:

```python
import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.score import media_ventana


def panel_falso(filas: dict[str, list[tuple[str, dict]]]) -> pd.DataFrame:
    """Panel con la forma de fundamentals.run.build_panel(con_zscore=True).

    `filas` mapea ticker -> [(trimestre, {kpi: valor_z}), ...], en orden
    cronológico. Los KPIs no mencionados quedan en NaN, como en el panel real.
    """
    registros, indice = [], []
    for ticker, periodos in filas.items():
        for trimestre, valores in periodos:
            fin = pd.Period(trimestre, freq="Q").end_time.normalize()
            fila = {f"z_{kpi}": np.nan for kpi in TODOS_LOS_KPIS}
            fila.update({f"z_{kpi}": v for kpi, v in valores.items()})
            fila.update({kpi: np.nan for kpi in TODOS_LOS_KPIS})
            fila["trimestre"] = trimestre
            registros.append(fila)
            indice.append((ticker, fin))
    return pd.DataFrame(
        registros,
        index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"]),
    )


def test_usa_solo_los_cuatro_trimestres_mas_recientes():
    panel = panel_falso(
        {
            "AAA": [
                ("2024Q1", {"roe": 100.0}),  # fuera de la ventana
                ("2024Q2", {"roe": 100.0}),  # fuera de la ventana
                ("2024Q3", {"roe": 1.0}),
                ("2024Q4", {"roe": 1.0}),
                ("2025Q1", {"roe": 1.0}),
                ("2025Q2", {"roe": 1.0}),
            ]
        }
    )
    z, _, _ = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 1.0


def test_la_ventana_salta_los_huecos_de_presentacion():
    # 2024Q4 no existe: la ventana coge las 4 filas más recientes que hay,
    # no los 4 trimestres naturales más recientes.
    panel = panel_falso(
        {
            "AAA": [
                ("2024Q1", {"roe": 2.0}),
                ("2024Q2", {"roe": 2.0}),
                ("2024Q3", {"roe": 2.0}),
                ("2025Q1", {"roe": 2.0}),
            ]
        }
    )
    z, _, historial = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 2.0
    assert historial.loc["AAA", "trimestres"] == 4


def test_promedia_solo_los_trimestres_con_dato_de_ese_kpi():
    panel = panel_falso(
        {
            "AAA": [
                ("2024Q3", {"roe": 1.0}),
                ("2024Q4", {}),
                ("2025Q1", {}),
                ("2025Q2", {"roe": 3.0}),
            ]
        }
    )
    z, _, _ = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 2.0


def test_el_historial_registra_cuenta_y_ultimo_trimestre():
    panel = panel_falso(
        {
            "AAA": [("2024Q3", {"roe": 1.0}), ("2024Q4", {"roe": 1.0})],
            "BBB": [("2025Q1", {"roe": 1.0})],
        }
    )
    _, _, historial = media_ventana(panel)
    assert historial.loc["AAA", "trimestres"] == 2
    assert historial.loc["AAA", "ultimo_trimestre"] == "2024Q4"
    assert historial.loc["BBB", "ultimo_trimestre"] == "2025Q1"


def test_panel_vacio_no_revienta():
    z, valores, historial = media_ventana(panel_falso({}))
    assert z.empty and valores.empty and historial.empty
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_score.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.score'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/score.py`:

```python
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import TRIMESTRES_VENTANA

COLUMNAS_Z = tuple(f"z_{kpi}" for kpi in TODOS_LOS_KPIS)


def media_ventana(
    panel: pd.DataFrame, n: int = TRIMESTRES_VENTANA
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Average each company's n most recent rows.

    Returns (z, valores, historial), all indexed by ticker: sector z-scores,
    raw KPI values for the fichas, and the row count plus newest calendar
    quarter that the guards need.

    The n most recent *rows*, which need not be n consecutive quarters: a
    company that skipped a filing leaves a gap and the window jumps it. Each
    row's z-score is already relative to its own quarter's peers, so jumping a
    gap never mixes periods — which averaging raw KPIs across quarters would.

    Averaging a single KPI over fewer than n quarters is allowed on purpose: a
    line item missing in one quarter should not discard the other three. The
    guards decide separately whether the surviving coverage is enough.
    """
    columnas_vacias = list(TODOS_LOS_KPIS)
    if panel.empty:
        vacio = pd.DataFrame(columns=columnas_vacias, dtype="float64")
        historial = pd.DataFrame(columns=["trimestres", "ultimo_trimestre"])
        return vacio, vacio.copy(), historial

    ordenado = panel.sort_index(level=["ticker", "periodo"])
    recientes = ordenado.groupby(level="ticker", sort=False).tail(n)
    por_ticker = recientes.groupby(level="ticker", sort=True)

    z = por_ticker[list(COLUMNAS_Z)].mean()
    z.columns = columnas_vacias

    valores = por_ticker[columnas_vacias].mean()

    historial = pd.DataFrame(
        {
            "trimestres": por_ticker.size(),
            "ultimo_trimestre": por_ticker["trimestre"].max(),
        }
    )
    return z, valores, historial
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_score.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/score.py tests/test_ranking_score.py
git commit -m "feat: media de la ventana de cuatro trimestres por empresa"
```

---

### Task 3: Puntuaciones por pilar, con los signos aplicados

**Files:**
- Modify: `ranking/score.py`
- Test: `tests/test_ranking_score.py`

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_ranking_score.py`:

```python
from ranking.score import puntuaciones_por_pilar


def medias_falsas(por_ticker: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Tabla con la forma que devuelve media_ventana(): ticker x 17 KPIs."""
    marco = pd.DataFrame(
        np.nan, index=sorted(por_ticker), columns=list(TODOS_LOS_KPIS), dtype="float64"
    )
    for ticker, valores in por_ticker.items():
        for kpi, valor in valores.items():
            marco.loc[ticker, kpi] = valor
    return marco


def test_un_multiplo_alto_penaliza_en_vez_de_premiar():
    # PER con z = +2 significa caro. Sin invertir el signo, el pilar de
    # valoración saldría +2 y el ranking premiaría lo caro.
    medias = medias_falsas({"AAA": {"per": 2.0}})
    pilares, _ = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "valoracion"] == -2.0


def test_la_deuda_alta_penaliza_en_solidez():
    medias = medias_falsas({"AAA": {"deuda_neta_ebitda": 1.0, "razon_corriente": 1.0}})
    pilares, _ = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "solidez"] == 0.0


def test_promedia_solo_los_kpis_con_dato_del_pilar():
    medias = medias_falsas({"AAA": {"roe": 2.0, "roic": 4.0}})
    pilares, conteo = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "calidad"] == 3.0
    assert conteo.loc["AAA", "calidad"] == 2


def test_un_pilar_sin_ningun_dato_queda_en_nan_no_en_cero():
    # Un 0 se leería como "exactamente la media del sector", que es una
    # afirmación; NaN dice "no medido", que es la verdad.
    medias = medias_falsas({"AAA": {"roe": 1.0}})
    pilares, conteo = puntuaciones_por_pilar(medias)
    assert pd.isna(pilares.loc["AAA", "crecimiento"])
    assert conteo.loc["AAA", "crecimiento"] == 0


def test_medias_vacias_no_revientan():
    pilares, conteo = puntuaciones_por_pilar(medias_falsas({}))
    assert list(pilares.columns) == list(PILARES)
    assert pilares.empty and conteo.empty
```

Y añade `PILARES` al bloque de imports de la cabecera del fichero:

```python
from ranking.criterio import PILARES
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_score.py -q`
Expected: FAIL con `ImportError: cannot import name 'puntuaciones_por_pilar'`

- [ ] **Step 3: Escribe la implementación mínima**

Añade a `ranking/score.py` (y amplía el import de `criterio`):

```python
from ranking.criterio import PILARES, SIGNOS, TRIMESTRES_VENTANA


def puntuaciones_por_pilar(medias: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Average the available KPIs of each pillar, applying the declared signs.

    Returns (pilares, conteo): the four scores per company, and how many KPIs
    actually carried data in each — the guards need the count, and so does the
    ficha, because a pillar resting on two KPIs is a weaker claim than one
    resting on seven.

    Signs are applied here rather than upstream so `medias` stays readable as
    raw z-scores: a +2 in `per` means expensive, and only the pillar turns that
    into a penalty.
    """
    if medias.empty:
        vacio = pd.DataFrame(columns=list(PILARES), dtype="float64")
        return vacio, vacio.copy().astype("int64")

    con_signo = medias.mul(pd.Series(SIGNOS), axis=1)

    pilares = pd.DataFrame(index=medias.index, dtype="float64")
    conteo = pd.DataFrame(index=medias.index, dtype="int64")
    for pilar, kpis in PILARES.items():
        bloque = con_signo[list(kpis)]
        pilares[pilar] = bloque.mean(axis=1)
        conteo[pilar] = bloque.notna().sum(axis=1)
    return pilares, conteo
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_score.py -q`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/score.py tests/test_ranking_score.py
git commit -m "feat: puntuaciones por pilar con los signos declarados"
```

---

### Task 4: Las guardas de exclusión

**Files:**
- Modify: `ranking/score.py`
- Test: `tests/test_ranking_score.py`

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_ranking_score.py`:

```python
from ranking.score import aplicar_guardas

PILARES_CRECIMIENTO = PILARES["crecimiento"]


def historial_falso(por_ticker: dict[str, tuple[int, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trimestres": n, "ultimo_trimestre": trimestre}
            for n, trimestre in por_ticker.values()
        ],
        index=sorted(por_ticker),
    )


def _completa(**cambios) -> dict[str, float]:
    """Empresa que supera todas las guardas, para alterar una sola cosa."""
    base = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
    base.update(cambios)
    return base


def test_una_empresa_completa_no_se_excluye():
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert pd.isna(motivos["AAA"])


def test_historia_corta_excluye():
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (3, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "historia_corta"


def test_datos_rancios_excluye_a_partir_del_tercer_trimestre_de_rezago():
    medias = medias_falsas({"AAA": _completa(), "BBB": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares,
        conteo,
        historial_falso({"AAA": (4, "2024Q4"), "BBB": (4, "2024Q3")}),
        "2025Q2",
    )
    assert pd.isna(motivos["AAA"]), "2 trimestres de rezago están dentro del límite"
    assert motivos["BBB"] == "datos_rancios"


def test_un_pilar_sin_datos_excluye():
    sin_crecimiento = {
        kpi: 1.0 for kpi in TODOS_LOS_KPIS if kpi not in PILARES_CRECIMIENTO
    }
    medias = medias_falsas({"AAA": sin_crecimiento})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "pilar_sin_datos"


def test_menos_de_ocho_kpis_excluye_aunque_haya_cuatro_pilares():
    # Uno por pilar en calidad, dos en cada uno de los otros tres: 7 KPIs.
    escasa = {
        "roe": 1.0,
        "crecimiento_ingresos": 1.0,
        "crecimiento_bpa": 1.0,
        "per": 1.0,
        "ev_ebitda": 1.0,
        "razon_corriente": 1.0,
        "cobertura_intereses": 1.0,
    }
    medias = medias_falsas({"AAA": escasa})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "cobertura_insuficiente"


def test_una_empresa_ausente_del_historial_se_excluye():
    # NaN < 4 es False: una comparación ingenua dejaría pasar a una empresa de
    # la que no sabemos nada, que es el peor de los casos posibles.
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    vacio = pd.DataFrame(columns=["trimestres", "ultimo_trimestre"])
    motivos = aplicar_guardas(pilares, conteo, vacio, "2025Q2")
    assert motivos["AAA"] == "historia_corta"
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_score.py -q`
Expected: FAIL con `ImportError: cannot import name 'aplicar_guardas'`

- [ ] **Step 3: Escribe la implementación mínima**

Añade a `ranking/score.py` (amplía el import de `criterio` con las cuatro constantes nuevas):

```python
from ranking.criterio import (
    MAX_ANTIGUEDAD_TRIMESTRES,
    MIN_KPIS_CON_DATO,
    MIN_PILARES_CON_DATO,
    MIN_TRIMESTRES_HISTORIA,
    PILARES,
    SIGNOS,
    TRIMESTRES_VENTANA,
)


def _rezago_trimestres(ultimos: pd.Series, trimestre_max: str) -> pd.Series:
    """How many calendar quarters behind the panel's newest bucket each company is.

    Measured against the panel, not against today's date: the panel is what the
    ranking is computed from, and a run made three months later must not start
    excluding companies that were current when the data was fetched.
    """
    ordinales = pd.PeriodIndex(ultimos.astype(str), freq="Q").asi8
    tope = pd.Period(trimestre_max, freq="Q").ordinal
    return pd.Series(tope - ordinales, index=ultimos.index)


def aplicar_guardas(
    pilares: pd.DataFrame,
    conteo: pd.DataFrame,
    historial: pd.DataFrame,
    trimestre_max: str,
) -> pd.Series:
    """Name why each company is excluded, or NaN when it survives.

    Every exclusion is named and returned rather than dropped, because a company
    that silently vanishes from a ranking is indistinguishable from one that
    scored badly — and the difference matters when reading the result.

    The first failing guard wins, so the reported reason is the most fundamental
    one rather than whichever check happened to run last.
    """
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    if pilares.empty:
        return motivos

    historial = historial.reindex(pilares.index)

    # Negar >= en vez de usar <, porque NaN < 4 es False: una empresa ausente
    # del historial pasaría la guarda por no saber nada de ella.
    corta = ~(historial["trimestres"] >= MIN_TRIMESTRES_HISTORIA)
    motivos[corta & motivos.isna()] = "historia_corta"

    ultimos = historial["ultimo_trimestre"]
    conocidos = ultimos.notna()
    rezago = pd.Series(float("nan"), index=motivos.index)
    if conocidos.any():
        rezago[conocidos] = _rezago_trimestres(ultimos[conocidos], trimestre_max)
    motivos[(rezago > MAX_ANTIGUEDAD_TRIMESTRES) & motivos.isna()] = "datos_rancios"

    sin_pilar = (conteo > 0).sum(axis=1) < MIN_PILARES_CON_DATO
    motivos[sin_pilar & motivos.isna()] = "pilar_sin_datos"

    pocos = conteo.sum(axis=1) < MIN_KPIS_CON_DATO
    motivos[pocos & motivos.isna()] = "cobertura_insuficiente"

    return motivos
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_score.py -q`
Expected: PASS, 16 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/score.py tests/test_ranking_score.py
git commit -m "feat: guardas de historia, frescura y cobertura con motivo nombrado"
```

---

### Task 5: Compuesto re-estandarizado dentro del sector

**Files:**
- Modify: `ranking/score.py`
- Test: `tests/test_ranking_score.py`

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_ranking_score.py`:

```python
from ranking.score import compuesto, marcar_sin_pares


def test_el_compuesto_se_reestandariza_dentro_del_sector():
    # Tres empresas del mismo sector con compuestos brutos 1, 2 y 3: tras
    # re-estandarizar, la media del sector es 0 y la desviación 1.
    medias = medias_falsas(
        {
            "AAA": {kpi: 1.0 for kpi in TODOS_LOS_KPIS},
            "BBB": {kpi: 2.0 for kpi in TODOS_LOS_KPIS},
            "CCC": {kpi: 3.0 for kpi in TODOS_LOS_KPIS},
        }
    )
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert abs(puntos.mean()) < 1e-12
    assert abs(puntos.std(ddof=1) - 1.0) < 1e-12
    assert puntos["CCC"] > puntos["BBB"] > puntos["AAA"]


def test_una_empresa_excluida_no_puntua():
    medias = medias_falsas({t: {kpi: 1.0 for kpi in TODOS_LOS_KPIS} for t in "ABC"})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    motivos["A"] = "historia_corta"
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert pd.isna(puntos["A"])


def test_un_pilar_en_nan_deja_el_compuesto_en_nan():
    # Sin esto, una empresa con tres pilares medidos competiría contra otras
    # con cuatro y el compuesto significaría cosas distintas en cada fila.
    completa = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
    sin_crecimiento = {
        kpi: 1.0 for kpi in TODOS_LOS_KPIS if kpi not in PILARES_CRECIMIENTO
    }
    medias = medias_falsas({"AAA": completa, "BBB": completa, "CCC": sin_crecimiento})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert pd.isna(puntos["CCC"])


def test_un_sector_con_menos_de_tres_pares_se_nombra_como_exclusion():
    # zscore_within_sector devuelve NaN con menos de 3 pares. Sin nombrarlo,
    # esas empresas desaparecerían del ranking sin explicación.
    medias = medias_falsas({t: {kpi: 1.0 for kpi in TODOS_LOS_KPIS} for t in "AB"})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Utilities", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)
    motivos = marcar_sin_pares(motivos, puntos)

    assert motivos["A"] == "sector_sin_pares"
    assert motivos["B"] == "sector_sin_pares"
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_score.py -q`
Expected: FAIL con `ImportError: cannot import name 'compuesto'`

- [ ] **Step 3: Escribe la implementación mínima**

Añade a `ranking/score.py` (importa también `PESOS` desde `criterio` y `zscore_within_sector` desde `fundamentals.sectors`):

```python
from fundamentals.sectors import zscore_within_sector
from ranking.criterio import PESOS  # junto a los imports ya presentes


def compuesto(
    pilares: pd.DataFrame, motivos: pd.Series, sectores: pd.Series
) -> pd.Series:
    """Weighted composite, re-standardised within sector before the global sort.

    A pillar averaged over two KPIs is more variable than one averaged over
    seven, and the companies missing KPIs are concentrated in banks, insurers
    and REITs. Without this step their composites would be systematically more
    extreme and would crowd both ends of the global order — the ranking would be
    measuring how many KPIs a company publishes, and would look entirely normal
    while doing it.

    Re-standardising within sector alone, with no time axis: after averaging the
    window there is one row per company, and grouping by the company's own last
    quarter would produce groups of one, where a z-score is 0 by construction.
    See amendment 1 of the design document.
    """
    if pilares.empty:
        return pd.Series(dtype="float64")

    pesos = pd.Series(PESOS)
    # min_count exige los cuatro pilares: una empresa con tres medidos no
    # compite contra otras con cuatro.
    bruto = (pilares[list(pesos.index)] * pesos).sum(axis=1, min_count=len(pesos))
    bruto = bruto.mask(motivos.reindex(bruto.index).notna())

    normalizado = zscore_within_sector(
        bruto.to_frame("compuesto"), sectores.reindex(bruto.index)
    )
    return normalizado["compuesto"]


def marcar_sin_pares(motivos: pd.Series, compuestos: pd.Series) -> pd.Series:
    """Name the exclusion for companies the sector re-standardisation dropped.

    zscore_within_sector returns NaN — never 0 — when a sector has fewer than
    three peers or no dispersion. Those companies would otherwise fall out of
    the ranking with no reason attached, which is the one thing the guards exist
    to prevent.
    """
    motivos = motivos.copy()
    huerfanas = compuestos.reindex(motivos.index).isna() & motivos.isna()
    motivos[huerfanas] = "sector_sin_pares"
    return motivos
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_score.py -q`
Expected: PASS, 20 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/score.py tests/test_ranking_score.py
git commit -m "feat: compuesto ponderado reestandarizado dentro del sector"
```

---

### Task 6: Control negativo y referencia positiva

Los dos estándares metodológicos del proyecto, como tests ejecutables. El control negativo es el que detecta el defecto que ningún otro test ve: un score que premia la cobertura en vez de la calidad.

**Files:**
- Create: `tests/test_ranking_control.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_control.py`:

```python
"""Control negativo y referencia positiva del score.

Estándares #2 y #3 del proyecto: ruido con la misma forma que la señal, y algo
que el aparato debe detectar si funciona.
"""

import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    puntuaciones_por_pilar,
)

SECTORES = ["Tech", "Financials", "Health", "Energy"]
EMPRESAS_POR_SECTOR = 20


def universo_sintetico(semilla: int) -> tuple[pd.DataFrame, pd.Series]:
    """Medias z aleatorias, con cobertura desigual por sector.

    Financials pierde los 5 KPIs que dependen del beneficio operativo, igual que
    en el panel real: bancos y aseguradoras no lo publican.
    """
    generador = np.random.default_rng(semilla)
    sin_operativo = (
        "margen_bruto",
        "margen_operativo",
        "ev_ebitda",
        "cobertura_intereses",
        "deuda_neta_ebitda",
    )
    filas, indice, sectores = [], [], []
    for sector in SECTORES:
        for numero in range(EMPRESAS_POR_SECTOR):
            fila = dict(zip(TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))))
            if sector == "Financials":
                for kpi in sin_operativo:
                    fila[kpi] = np.nan
            filas.append(fila)
            indice.append(f"{sector[:2].upper()}{numero:02d}")
            sectores.append(sector)
    medias = pd.DataFrame(filas, index=indice, columns=list(TODOS_LOS_KPIS))
    return medias, pd.Series(sectores, index=indice)


def puntuar(medias: pd.DataFrame, sectores: pd.Series) -> pd.Series:
    pilares, conteo = puntuaciones_por_pilar(medias)
    historial = pd.DataFrame(
        {"trimestres": 4, "ultimo_trimestre": "2025Q2"}, index=medias.index
    )
    motivos = aplicar_guardas(pilares, conteo, historial, "2025Q2")
    puntos = compuesto(pilares, motivos, sectores)
    marcar_sin_pares(motivos, puntos)
    return puntos


def test_control_negativo_el_score_no_premia_la_cobertura():
    """Con KPIs puro ruido, el sector de menos cobertura no puede dominar.

    Si un compuesto calculado sobre menos KPIs sale sistemáticamente más
    extremo, las cabeceras del ranking serían empresas por publicar menos
    líneas, no por ser mejores. El resultado sería indistinguible a ojo de uno
    correcto: de ahí que haga falta medirlo.
    """
    apariciones = []
    for semilla in range(40):
        medias, sectores = universo_sintetico(semilla)
        puntos = puntuar(medias, sectores).dropna()
        cabeza = puntos.sort_values(ascending=False).head(15).index
        apariciones.append((sectores.reindex(cabeza) == "Financials").sum())

    proporcion = np.mean(apariciones) / 15
    esperado = 1 / len(SECTORES)
    assert abs(proporcion - esperado) < 0.10, (
        f"Financials ocupa {proporcion:.0%} del top con datos aleatorios, "
        f"cuando por tamaño le corresponde {esperado:.0%}"
    )


def test_referencia_positiva_la_empresa_dominante_sale_primera():
    """Si el aparato no detecta esto, no detecta nada."""
    medias, sectores = universo_sintetico(semilla=0)
    medias.loc["TE00"] = 5.0

    puntos = puntuar(medias, sectores)

    assert puntos.idxmax() == "TE00"


def test_el_score_es_reproducible():
    medias, sectores = universo_sintetico(semilla=7)
    assert puntuar(medias, sectores).equals(puntuar(medias, sectores))
```

- [ ] **Step 2: Ejecuta los tests**

Run: `pytest tests/test_ranking_control.py -q`
Expected: PASS, 3 passed

Si el control negativo falla, **no ajustes la tolerancia**: significa que el compuesto sí premia la cobertura y hay que revisar la re-estandarización de la Task 5. Anota el número que salió antes de tocar nada.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ranking_control.py
git commit -m "test: control negativo de cobertura y referencia positiva del score"
```

---

### Task 7: Selección con tope sectorial y empates deterministas

**Files:**
- Create: `ranking/seleccion.py`
- Test: `tests/test_ranking_seleccion.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_seleccion.py`:

```python
import pandas as pd

from ranking.seleccion import desplazamientos_por_ticker, seleccionar


def entradas(pares: list[tuple[str, float, str]]):
    tickers = [t for t, _, _ in pares]
    compuestos = pd.Series([c for _, c, _ in pares], index=tickers, dtype="float64")
    sectores = pd.Series([s for _, _, s in pares], index=tickers)
    return compuestos, sectores


def test_ordena_de_mayor_a_menor():
    compuestos, sectores = entradas(
        [("AAA", 1.0, "Tech"), ("BBB", 3.0, "Health"), ("CCC", 2.0, "Energy")]
    )
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=3)
    assert list(elegidas["ticker"]) == ["BBB", "CCC", "AAA"]
    assert list(elegidas["puesto"]) == [1, 2, 3]


def test_el_tope_sectorial_deja_fuera_a_la_cuarta_del_sector():
    compuestos, sectores = entradas(
        [
            ("T1", 5.0, "Tech"),
            ("T2", 4.0, "Tech"),
            ("T3", 3.0, "Tech"),
            ("T4", 2.5, "Tech"),
            ("H1", 1.0, "Health"),
        ]
    )
    elegidas, desplazadas = seleccionar(compuestos, sectores, tope=3, n=5)
    assert list(elegidas["ticker"]) == ["T1", "T2", "T3", "H1"]
    assert list(desplazadas["ticker"]) == ["T4"]
    assert desplazadas.loc[0, "puesto_global"] == 4
    assert desplazadas.loc[0, "bloqueada_por"] == ("T1", "T2", "T3")


def test_los_empates_se_rompen_por_ticker():
    # Sin desempate determinista, dos corridas sobre el mismo panel pueden
    # devolver listas distintas y el sistema deja de ser auditable.
    compuestos, sectores = entradas(
        [("ZZZ", 1.0, "Tech"), ("AAA", 1.0, "Health"), ("MMM", 1.0, "Energy")]
    )
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=3)
    assert list(elegidas["ticker"]) == ["AAA", "MMM", "ZZZ"]


def test_las_empresas_sin_compuesto_no_entran():
    compuestos, sectores = entradas([("AAA", float("nan"), "Tech"), ("BBB", 1.0, "Tech")])
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=5)
    assert list(elegidas["ticker"]) == ["BBB"]


def test_menos_candidatos_que_el_top_devuelve_los_que_haya():
    compuestos, sectores = entradas([("AAA", 1.0, "Tech")])
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=15)
    assert len(elegidas) == 1


def test_el_mapa_de_desplazamientos_atribuye_a_las_bloqueadoras():
    compuestos, sectores = entradas(
        [
            ("T1", 5.0, "Tech"),
            ("T2", 4.0, "Tech"),
            ("T3", 3.0, "Tech"),
            ("T4", 2.5, "Tech"),
        ]
    )
    _, desplazadas = seleccionar(compuestos, sectores, tope=3, n=4)
    mapa = desplazamientos_por_ticker(desplazadas)
    assert mapa == {"T1": ["T4"], "T2": ["T4"], "T3": ["T4"]}
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_seleccion.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.seleccion'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/seleccion.py`:

```python
import pandas as pd

from ranking.criterio import TAMANO_TOP, TOPE_POR_SECTOR


def seleccionar(
    compuestos: pd.Series,
    sectores: pd.Series,
    tope: int = TOPE_POR_SECTOR,
    n: int = TAMANO_TOP,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk the global order, admitting a company unless its sector is full.

    Returns (elegidas, desplazadas). The second frame is not a debugging aid: a
    sector cap that silently reshapes the list would be invisible in the output,
    so every company passed over on the way to n is recorded with the tickers
    that blocked it.

    Ties break on ticker, so two runs over the same panel return the same list.
    Without it the system would stop being auditable for a silly reason.
    """
    tabla = pd.DataFrame(
        {
            "ticker": list(compuestos.index),
            "compuesto": compuestos.to_numpy(),
            "sector": sectores.reindex(compuestos.index).to_numpy(),
        }
    ).dropna(subset=["compuesto"])

    tabla = tabla.sort_values(
        ["compuesto", "ticker"], ascending=[False, True], kind="mergesort"
    )
    tabla["puesto_global"] = range(1, len(tabla) + 1)

    elegidas: list[dict] = []
    desplazadas: list[dict] = []
    ocupacion: dict[str, list[str]] = {}

    for fila in tabla.itertuples(index=False):
        if len(elegidas) >= n:
            break
        ocupadas = ocupacion.setdefault(fila.sector, [])
        if len(ocupadas) >= tope:
            desplazadas.append(
                {
                    "ticker": fila.ticker,
                    "sector": fila.sector,
                    "puesto_global": fila.puesto_global,
                    "bloqueada_por": tuple(ocupadas),
                }
            )
            continue
        ocupadas.append(fila.ticker)
        elegidas.append(
            {
                "ticker": fila.ticker,
                "sector": fila.sector,
                "compuesto": fila.compuesto,
                "puesto_global": fila.puesto_global,
                "puesto": len(elegidas) + 1,
            }
        )

    columnas_elegidas = ["ticker", "sector", "compuesto", "puesto_global", "puesto"]
    columnas_desplazadas = ["ticker", "sector", "puesto_global", "bloqueada_por"]
    return (
        pd.DataFrame(elegidas, columns=columnas_elegidas),
        pd.DataFrame(desplazadas, columns=columnas_desplazadas),
    )


def desplazamientos_por_ticker(desplazadas: pd.DataFrame) -> dict[str, list[str]]:
    """Map each admitted ticker to the tickers it kept out through the cap."""
    mapa: dict[str, list[str]] = {}
    for fila in desplazadas.itertuples(index=False):
        for bloqueadora in fila.bloqueada_por:
            mapa.setdefault(bloqueadora, []).append(fila.ticker)
    return mapa
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_seleccion.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/seleccion.py tests/test_ranking_seleccion.py
git commit -m "feat: seleccion con tope sectorial y desempate determinista"
```

---

### Task 8: La mitad numérica de la ficha

**Files:**
- Create: `ranking/fichas.py`
- Test: `tests/test_ranking_fichas.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_fichas.py`:

```python
import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.fichas import descriptor, ficha_numerica


def serie(valores: dict[str, float]) -> pd.Series:
    base = pd.Series(np.nan, index=list(TODOS_LOS_KPIS), dtype="float64")
    for kpi, valor in valores.items():
        base[kpi] = valor
    return base


def ficha_ejemplo(**cambios):
    z = serie({kpi: 0.0 for kpi in TODOS_LOS_KPIS})
    z["roic"] = 2.5
    z["per"] = 2.0  # z alto en un múltiplo = caro = flojo
    valores = serie({kpi: 1.0 for kpi in TODOS_LOS_KPIS})
    valores["roic"] = 0.31
    valores["per"] = 34.2
    argumentos = {
        "ticker": "AAA",
        "sector": "Information Technology",
        "puesto": 3,
        "compuesto": 1.42,
        "pilares": pd.Series(
            {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1}
        ),
        "conteo": pd.Series(
            {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3}
        ),
        "z": z,
        "valores": valores,
        "desplazo_a": [],
    }
    argumentos.update(cambios)
    return ficha_numerica(**argumentos)


def test_recoge_identidad_puesto_y_pilares():
    ficha = ficha_ejemplo()
    assert ficha["ticker"] == "AAA"
    assert ficha["puesto"] == 3
    assert ficha["pilares"]["calidad"] == 1.9
    assert ficha["cobertura"] == {"kpis_con_dato": 17, "pilares_con_dato": 4}


def test_el_multiplo_caro_sale_entre_los_flojos_no_entre_los_destacados():
    # El z crudo de per es +2, el más alto después de roic. Sin aplicar el
    # signo, la ficha presumiría de estar cara.
    ficha = ficha_ejemplo()
    assert ficha["destacados"][0]["kpi"] == "roic"
    assert ficha["flojos"][0]["kpi"] == "per"
    assert ficha["flojos"][0]["valor"] == 34.2


def test_destacados_y_flojos_no_se_solapan():
    ficha = ficha_ejemplo()
    destacados = {item["kpi"] for item in ficha["destacados"]}
    flojos = {item["kpi"] for item in ficha["flojos"]}
    assert destacados.isdisjoint(flojos)


def test_ignora_los_kpis_sin_dato():
    z = serie({"roe": 1.0, "roic": 0.5})
    valores = serie({"roe": 0.2, "roic": 0.1})
    ficha = ficha_ejemplo(z=z, valores=valores)
    citados = {item["kpi"] for item in ficha["destacados"] + ficha["flojos"]}
    assert citados == {"roe", "roic"}


def test_la_ficha_nace_sin_narrativa():
    ficha = ficha_ejemplo()
    assert ficha["narrativa"] is None
    assert ficha["generada_por"] == "plantilla"


def test_el_descriptor_traduce_el_z_a_palabras_sin_digitos():
    assert descriptor(2.0) == "muy por encima de sus pares"
    assert descriptor(0.0) == "en línea con sus pares"
    assert descriptor(-2.0) == "muy por debajo de sus pares"
    assert not any(c.isdigit() for c in descriptor(1.0))
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_fichas.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.fichas'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/fichas.py`:

```python
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import SIGNOS

N_DESTACADOS = 3


def descriptor(z: float) -> str:
    """Turn a z-score into words.

    The prompt sent to the model carries these instead of numbers, so there is
    no digit in it for the model to echo back — which makes the "no digits in
    the narrative" rule something it can satisfy rather than resist.
    """
    if z >= 1.5:
        return "muy por encima de sus pares"
    if z >= 0.5:
        return "por encima de sus pares"
    if z > -0.5:
        return "en línea con sus pares"
    if z > -1.5:
        return "por debajo de sus pares"
    return "muy por debajo de sus pares"


def _item(kpi: str, z: pd.Series, valores: pd.Series) -> dict:
    return {
        "kpi": kpi,
        "valor": None if pd.isna(valores[kpi]) else float(valores[kpi]),
        "z": float(z[kpi]),
    }


def ficha_numerica(
    ticker: str,
    sector: str,
    puesto: int,
    compuesto: float,
    pilares: pd.Series,
    conteo: pd.Series,
    z: pd.Series,
    valores: pd.Series,
    desplazo_a: list[str],
) -> dict:
    """Build the half of the ficha the code owns. Never touches the network.

    Highlights are ranked by sign-adjusted z, so an expensive multiple lands
    among the weak points instead of being paraded as a strength.
    """
    con_signo = {
        kpi: z[kpi] * SIGNOS[kpi] for kpi in TODOS_LOS_KPIS if pd.notna(z[kpi])
    }
    orden = sorted(con_signo, key=lambda kpi: (-con_signo[kpi], kpi))

    destacados = orden[:N_DESTACADOS]
    flojos = [kpi for kpi in reversed(orden) if kpi not in destacados][:N_DESTACADOS]

    return {
        "ticker": ticker,
        "sector_gics": sector,
        "puesto": int(puesto),
        "compuesto": float(compuesto),
        "pilares": {pilar: _o_nulo(valor) for pilar, valor in pilares.items()},
        "destacados": [_item(kpi, z, valores) for kpi in destacados],
        "flojos": [_item(kpi, z, valores) for kpi in flojos],
        "cobertura": {
            "kpis_con_dato": int(conteo.sum()),
            "pilares_con_dato": int((conteo > 0).sum()),
        },
        "desplazo_a": list(desplazo_a),
        "generada_por": "plantilla",
        "narrativa": None,
    }


def _o_nulo(valor: float) -> float | None:
    return None if pd.isna(valor) else float(valor)
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_fichas.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/fichas.py tests/test_ranking_fichas.py
git commit -m "feat: mitad numerica de la ficha, sin red"
```

---

### Task 9: Extracción del Item 1A con caché y tope duro

**Files:**
- Create: `ranking/filings.py`
- Test: `tests/test_ranking_filings.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_filings.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from ranking.filings import Riesgos, cargar_riesgos

CRUDO = {
    "formulario": "10-K",
    "fecha": "2025-10-31",
    "accession": "0000320193-25-000079",
    "texto": "A" * 500,
}


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "riesgos"


def test_devuelve_la_seccion_con_su_procedencia(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO):
        riesgos = cargar_riesgos("AAPL", cache_dir=cache)
    assert isinstance(riesgos, Riesgos)
    assert riesgos.accession == "0000320193-25-000079"
    assert riesgos.seccion == "Item 1A"
    assert riesgos.recortado is False


def test_recorta_al_tope_y_lo_registra(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO):
        riesgos = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=100)
    assert len(riesgos.texto) == 100
    assert riesgos.caracteres_totales == 500
    assert riesgos.recortado is True


def test_la_segunda_llamada_no_vuelve_a_descargar(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        cargar_riesgos("AAPL", cache_dir=cache)
        cargar_riesgos("AAPL", cache_dir=cache)
    assert descarga.call_count == 1


def test_el_tope_se_aplica_sobre_la_cache_sin_redescargar(cache):
    # Cambiar el presupuesto de tokens no debe costar una descarga nueva.
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=500)
        recortada = cargar_riesgos("AAPL", cache_dir=cache, max_caracteres=50)
    assert descarga.call_count == 1
    assert len(recortada.texto) == 50


def test_sin_seccion_devuelve_none_en_vez_de_reventar(cache):
    with patch("ranking.filings._descargar", return_value=None):
        assert cargar_riesgos("XYZ", cache_dir=cache) is None


def test_refresh_fuerza_la_descarga(cache):
    with patch("ranking.filings._descargar", return_value=CRUDO) as descarga:
        cargar_riesgos("AAPL", cache_dir=cache)
        cargar_riesgos("AAPL", cache_dir=cache, refresh=True)
    assert descarga.call_count == 2
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_filings.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.filings'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/filings.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache" / "riesgos"

# ~20k tokens estimados a 4 caracteres por token. El presupuesto real se
# comprueba con client.messages.count_tokens en el test marcado `red`: contar
# tokens de Claude con una regla de tres es una aproximación, no una medida.
MAX_CARACTERES = 80_000

SECCION = "Item 1A"


@dataclass(frozen=True)
class Riesgos:
    """The risk-factor section as it was sent to the model, with its provenance."""

    ticker: str
    formulario: str
    fecha: str
    accession: str
    seccion: str
    texto: str
    caracteres_totales: int
    recortado: bool


def _descargar(ticker: str) -> dict | None:
    """Fetch Item 1A of the latest 10-K.

    Isolated so tests can replace it without touching the network, the same way
    fundamentals.run isolates its price lookup.
    """
    from edgar import Company

    presentacion = Company(ticker).get_filings(form="10-K").latest(1)
    if presentacion is None:
        return None
    texto = getattr(presentacion.obj(), "risk_factors", None)
    if not texto:
        return None
    return {
        "formulario": presentacion.form,
        "fecha": str(presentacion.filing_date),
        "accession": presentacion.accession_no,
        "texto": texto,
    }


def cargar_riesgos(
    ticker: str,
    cache_dir: Path | None = None,
    max_caracteres: int = MAX_CARACTERES,
    refresh: bool = False,
) -> Riesgos | None:
    """Item 1A of the company's latest 10-K, truncated to a hard budget.

    Returns None when the filing has no extractable section: the caller records
    it and ships a ficha without a risk narrative rather than aborting the run,
    the same policy fundamentals uses for a company that fails to download.

    The cache stores the full section and truncation happens on read, so raising
    or lowering the token budget never costs a second download.
    """
    directorio = Path(cache_dir or CACHE_DIR)
    fichero = directorio / f"{ticker}.json"

    crudo = None
    if fichero.exists() and not refresh:
        crudo = json.loads(fichero.read_text(encoding="utf-8"))
    else:
        crudo = _descargar(ticker)
        if crudo is not None:
            directorio.mkdir(parents=True, exist_ok=True)
            fichero.write_text(
                json.dumps(crudo, ensure_ascii=False), encoding="utf-8"
            )

    if crudo is None:
        return None

    completo = crudo["texto"]
    return Riesgos(
        ticker=ticker,
        formulario=crudo["formulario"],
        fecha=crudo["fecha"],
        accession=crudo["accession"],
        seccion=SECCION,
        texto=completo[:max_caracteres],
        caracteres_totales=len(completo),
        recortado=len(completo) > max_caracteres,
    )
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_filings.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/filings.py tests/test_ranking_filings.py
git commit -m "feat: extraccion del Item 1A con cache y tope duro"
```

---

### Task 10: Verificadores de cita y de dígitos

Se implementan **antes** que la llamada a la API, porque son lo que decide si la ficha es trazable. Sin ellos, el resto del módulo no tiene sentido.

**Files:**
- Create: `ranking/llm.py`
- Test: `tests/test_ranking_llm.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_llm.py`:

```python
from ranking.llm import sin_digitos, verificar_cita

FUENTE = (
    "Our business is subject to  intense competition.\n"
    "We depend on a limited number of suppliers for key components."
)


def test_acepta_una_cita_literal():
    assert verificar_cita("depend on a limited number of suppliers", FUENTE)


def test_tolera_diferencias_de_espacios_y_mayusculas():
    # Los saltos de línea del informe no deben invalidar una cita real.
    assert verificar_cita("SUBJECT TO INTENSE   competition", FUENTE)


def test_rechaza_una_cita_fabricada():
    # El test que decide si "trazable" significa algo.
    assert not verificar_cita("We expect margins to collapse next year", FUENTE)


def test_rechaza_una_cita_vacia():
    assert not verificar_cita("", FUENTE)


def test_rechaza_una_cita_demasiado_larga():
    # Sin tope, "citar" podría ser copiar la sección entera.
    assert not verificar_cita(FUENTE * 10, FUENTE * 10)


def test_detecta_digitos_en_la_narrativa():
    assert sin_digitos("Los márgenes están muy por encima de sus pares")
    assert not sin_digitos("Los márgenes superan el 30% del sector")
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.llm'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/llm.py`:

```python
MAX_CARACTERES_CITA = 200


def _normalizar(texto: str) -> str:
    return " ".join(texto.split()).casefold()


def verificar_cita(cita: str, fuente: str) -> bool:
    """Whether the quote appears verbatim in the text the model was given.

    Checked against what was sent, not against the full filing: a quote from a
    part the model never saw is a quote it could not have read, however real it
    looks.

    Whitespace and case are normalised because a line break in the filing is not
    a fabrication. The length cap exists so that "quoting" cannot degenerate
    into copying the whole section back.
    """
    if not cita or len(cita) > MAX_CARACTERES_CITA:
        return False
    return _normalizar(cita) in _normalizar(fuente)


def sin_digitos(texto: str) -> bool:
    """Whether the text is free of numerals.

    Numbers in a ficha come from the panel, never from the model. A hard rule
    rather than a regex that tries to check each number against the data:
    verifying a number is fiddly and fails on rounding, whereas forbidding them
    outright is one line and cannot be wrong.
    """
    return not any(caracter.isdigit() for caracter in texto)
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/llm.py tests/test_ranking_llm.py
git commit -m "feat: verificacion por codigo de citas literales y ausencia de cifras"
```

---

### Task 11: Llamada a Sonnet 5, reintento y degradación

**Files:**
- Modify: `ranking/llm.py`
- Test: `tests/test_ranking_llm.py`

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_ranking_llm.py`:

```python
from unittest.mock import MagicMock

import anthropic
import pytest

from ranking.llm import Narrativa, Riesgo, redactar


class ClienteFalso:
    """Devuelve las narrativas que se le den, una por llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.messages = MagicMock()
        self.messages.parse = self._parse

    def _parse(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return MagicMock(parsed_output=siguiente)


def narrativa(cita: str, tesis: str = "Negocio sólido y bien valorado") -> Narrativa:
    return Narrativa(
        tesis=tesis,
        riesgos=[Riesgo(afirmacion="Depende de pocos proveedores", cita=cita)],
    )


def test_devuelve_la_narrativa_con_la_cita_verificada():
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is True
    assert len(cliente.llamadas) == 1


def test_reintenta_una_vez_cuando_la_cita_no_aparece():
    cliente = ClienteFalso(
        narrativa("cita inventada que no está"),
        narrativa("limited number of suppliers"),
    )
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert len(cliente.llamadas) == 2
    assert resultado["riesgos"][0]["verificada"] is True


def test_tras_el_reintento_entrega_el_riesgo_marcado_no_lo_descarta():
    # Una afirmación sin respaldo que se ve es mejor que una que desaparece.
    cliente = ClienteFalso(narrativa("inventada"), narrativa("tambien inventada"))
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is False
    assert resultado["riesgos"][0]["afirmacion"] == "Depende de pocos proveedores"


def test_una_narrativa_con_cifras_se_rechaza_entera():
    # No podemos verificar un número; la regla era que los pone el código.
    cliente = ClienteFalso(
        narrativa("limited number of suppliers", tesis="Márgenes del 30%"),
        narrativa("limited number of suppliers", tesis="Márgenes del 30%"),
    )
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_un_error_de_api_degrada_a_none():
    cliente = ClienteFalso(anthropic.APIConnectionError(request=MagicMock()))
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_sin_clave_no_intenta_llamar(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert redactar("contexto", FUENTE) is None


def test_no_manda_temperature_ni_prefill():
    # Sonnet 5 rechaza temperature y el prefill de turno final.
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    redactar("contexto", FUENTE, cliente=cliente)
    envio = cliente.llamadas[0]
    assert "temperature" not in envio
    assert envio["messages"][-1]["role"] == "user"
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: FAIL con `ImportError: cannot import name 'Narrativa'`

- [ ] **Step 3: Escribe la implementación mínima**

Añade a `ranking/llm.py`, encima de los verificadores:

```python
import os

from pydantic import BaseModel

MODELO = "claude-sonnet-5"
MAX_TOKENS = 2000
VERSION_PROMPT = "b1"
MAX_RIESGOS = 3

SISTEMA = """Eres un analista que redacta la ficha de una empresa candidata a \
una cartera. El orden del ranking ya está decidido por un score cuantitativo: \
tu trabajo es explicar y advertir, no valorar ni recomendar.

Reglas, todas obligatorias:
- No escribas ningún dígito. Las cifras las pone el código desde el panel.
- Cada riesgo lleva una cita literal y contigua del texto que se te entrega, \
copiada carácter a carácter, de menos de doscientos caracteres.
- Si el texto no respalda un riesgo, no lo menciones. Pocos riesgos bien \
citados valen más que muchos sin respaldo.
- Escribe en español, en prosa llana, sin viñetas."""


class Riesgo(BaseModel):
    afirmacion: str
    cita: str


class Narrativa(BaseModel):
    tesis: str
    riesgos: list[Riesgo]


def _prompt(contexto: str, fuente: str) -> str:
    return (
        f"Empresa candidata:\n{contexto}\n\n"
        f"Factores de riesgo declarados por la empresa:\n<<<\n{fuente}\n>>>\n\n"
        "Escribe la tesis y hasta "
        f"{MAX_RIESGOS} riesgos, cada uno con su cita literal."
    )


def _reintento(fallidas: list[Riesgo]) -> str:
    listado = "\n".join(f"- {riesgo.cita}" for riesgo in fallidas)
    return (
        "Estas citas no aparecen literalmente en el texto entregado:\n"
        f"{listado}\n\n"
        "Vuelve a escribir la respuesta usando sólo citas que puedas copiar "
        "del texto. Si un riesgo no tiene respaldo literal, elimínalo."
    )


def _a_dict(narrativa: Narrativa, fuente: str) -> dict:
    return {
        "tesis": narrativa.tesis,
        "riesgos": [
            {
                "afirmacion": riesgo.afirmacion,
                "cita": riesgo.cita,
                "verificada": verificar_cita(riesgo.cita, fuente),
            }
            for riesgo in narrativa.riesgos
        ],
    }


def redactar(
    contexto: str,
    fuente: str,
    cliente=None,
    modelo: str = MODELO,
) -> dict | None:
    """Ask the model for the qualitative half, verifying every quote by code.

    Returns None whenever the narrative cannot be trusted or produced — no key,
    an API failure, or digits that survived the retry. The caller ships the
    template ficha instead: the ranking never depends on this succeeding.

    A failed quote is retried once and then kept with `verificada: False`, but
    digits are fatal. The difference is deliberate: an unbacked claim that is
    visibly marked can still be judged by a human, whereas an invented number
    reads exactly like a real one.
    """
    import anthropic

    if cliente is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        cliente = anthropic.Anthropic()

    mensajes: list[dict] = [{"role": "user", "content": _prompt(contexto, fuente)}]

    for intento in range(2):
        try:
            respuesta = cliente.messages.parse(
                model=modelo,
                max_tokens=MAX_TOKENS,
                system=SISTEMA,
                messages=mensajes,
                output_format=Narrativa,
                thinking={"type": "disabled"},
            )
        except anthropic.APIError:
            return None

        narrativa = respuesta.parsed_output
        if narrativa is None:
            return None

        con_digitos = not sin_digitos(narrativa.tesis) or any(
            not sin_digitos(riesgo.afirmacion) for riesgo in narrativa.riesgos
        )
        fallidas = [
            riesgo
            for riesgo in narrativa.riesgos
            if not verificar_cita(riesgo.cita, fuente)
        ]

        if not con_digitos and not fallidas:
            return _a_dict(narrativa, fuente)
        if intento == 1:
            return None if con_digitos else _a_dict(narrativa, fuente)

        mensajes = mensajes + [
            {"role": "assistant", "content": narrativa.model_dump_json()},
            {"role": "user", "content": _reintento(fallidas)},
        ]

    return None
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: PASS, 13 passed

> **Si `thinking={"type": "disabled"}` no conviviera con `output_format=` al llegar al test `red` de la Task 15**, quita ese parámetro: Sonnet 5 corre pensamiento adaptativo por defecto, cuesta algo más y funciona igual. No inventes otra combinación sin comprobarla contra la API.

- [ ] **Step 5: Commit**

```bash
git add ranking/llm.py tests/test_ranking_llm.py
git commit -m "feat: llamada a Sonnet 5 con reintento y degradacion a plantilla"
```

---

### Task 12: Caché de fichas por hash de contenido

**Files:**
- Modify: `ranking/llm.py`
- Test: `tests/test_ranking_llm.py`

- [ ] **Step 1: Escribe el test que falla**

Añade a `tests/test_ranking_llm.py`:

```python
from pathlib import Path

from ranking.llm import clave_cache, redactar_con_cache


def test_la_clave_es_estable_entre_procesos():
    # hashlib, no hash(): Python aleatoriza el hash de strings entre procesos.
    primera = clave_cache("ctx", "fuente", "modelo", "b1")
    assert primera == clave_cache("ctx", "fuente", "modelo", "b1")
    assert len(primera) == 64


def test_la_clave_cambia_si_cambia_cualquier_pieza():
    base = clave_cache("ctx", "fuente", "modelo", "b1")
    assert clave_cache("otro", "fuente", "modelo", "b1") != base
    assert clave_cache("ctx", "otra", "modelo", "b1") != base
    assert clave_cache("ctx", "fuente", "otro", "b1") != base
    assert clave_cache("ctx", "fuente", "modelo", "b2") != base


def test_la_segunda_corrida_no_vuelve_a_llamar(tmp_path: Path):
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    primera = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    segunda = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert primera == segunda
    assert len(cliente.llamadas) == 1


def test_no_cachea_los_fallos(tmp_path: Path):
    # Cachear un None congelaría un fallo transitorio para siempre.
    fallo = ClienteFalso(anthropic.APIConnectionError(request=MagicMock()))
    assert redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=fallo) is None

    bueno = ClienteFalso(narrativa("limited number of suppliers"))
    assert redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=bueno) is not None
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: FAIL con `ImportError: cannot import name 'clave_cache'`

- [ ] **Step 3: Escribe la implementación mínima**

Añade a `ranking/llm.py` (y `import hashlib`, `import json`, `from pathlib import Path` arriba):

```python
CACHE_DIR = Path(__file__).parent / ".cache" / "fichas"


def clave_cache(contexto: str, fuente: str, modelo: str, version: str) -> str:
    """Content hash of everything that could change the narrative.

    hashlib rather than hash(): Python randomises string hashing between
    processes, so hash() would produce a different key on every run and the
    cache would never hit. That lesson cost a poisoned cache once already.
    """
    carga = json.dumps(
        {"contexto": contexto, "fuente": fuente, "modelo": modelo, "version": version},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(carga.encode("utf-8")).hexdigest()


def redactar_con_cache(
    contexto: str,
    fuente: str,
    cache_dir: Path | None = None,
    cliente=None,
    modelo: str = MODELO,
) -> dict | None:
    """redactar(), memoised on content.

    Sonnet 5 no longer accepts `temperature`, so two identical calls can differ.
    The cache is what makes a rerun reproducible — and free.

    Failures are never cached: a transient API error would otherwise freeze into
    a permanent template ficha for that company.
    """
    directorio = Path(cache_dir or CACHE_DIR)
    fichero = directorio / f"{clave_cache(contexto, fuente, modelo, VERSION_PROMPT)}.json"

    if fichero.exists():
        return json.loads(fichero.read_text(encoding="utf-8"))

    resultado = redactar(contexto, fuente, cliente=cliente, modelo=modelo)
    if resultado is not None:
        directorio.mkdir(parents=True, exist_ok=True)
        fichero.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_llm.py -q`
Expected: PASS, 17 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/llm.py tests/test_ranking_llm.py
git commit -m "feat: cache de fichas por hash de contenido, reproducible entre corridas"
```

---

### Task 13: El informe legible

**Files:**
- Create: `ranking/informe.py`
- Test: `tests/test_ranking_informe.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_informe.py`:

```python
from ranking.informe import render

FICHA = {
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "puesto": 1,
    "compuesto": 1.42,
    "pilares": {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1},
    "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
    "flojos": [{"kpi": "per", "valor": 34.2, "z": 2.0}],
    "cobertura": {"kpis_con_dato": 14, "pilares_con_dato": 4},
    "desplazo_a": ["BBB"],
    "generada_por": "sonnet-5",
    "narrativa": {
        "tesis": "Rentabilidad muy por encima de sus pares.",
        "riesgos": [
            {"afirmacion": "Depende de pocos proveedores", "cita": "limited number", "verificada": True},
            {"afirmacion": "Riesgo regulatorio", "cita": "no comprobable", "verificada": False},
        ],
        "fuente": {
            "formulario": "10-K",
            "fecha": "2025-10-31",
            "accession": "0000320193-25-000079",
            "seccion": "Item 1A",
            "caracteres_enviados": 68163,
            "recortado": False,
        },
    },
}

EXCLUSIONES = {"cobertura_insuficiente": 41, "datos_rancios": 3}


def test_incluye_ticker_puesto_y_tesis():
    texto = render([FICHA], EXCLUSIONES)
    assert "AAA" in texto
    assert "Rentabilidad muy por encima" in texto


def test_marca_visiblemente_los_riesgos_no_verificados():
    # Si esto no se ve, la verificación no sirve de nada.
    texto = render([FICHA], EXCLUSIONES)
    assert "sin verificar" in texto.lower()


def test_reporta_las_exclusiones_al_pie():
    texto = render([FICHA], EXCLUSIONES)
    assert "cobertura_insuficiente" in texto
    assert "41" in texto


def test_una_ficha_de_plantilla_no_revienta_el_render():
    plantilla = {**FICHA, "narrativa": None, "generada_por": "plantilla"}
    texto = render([plantilla], EXCLUSIONES)
    assert "AAA" in texto
    assert "plantilla" in texto
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_informe.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.informe'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/informe.py`:

```python
from datetime import date


def _pilares(ficha: dict) -> str:
    partes = [
        f"{pilar} {valor:+.2f}" if valor is not None else f"{pilar} n/d"
        for pilar, valor in ficha["pilares"].items()
    ]
    return " · ".join(partes)


def _kpis(items: list[dict]) -> str:
    return ", ".join(
        f"{item['kpi']} ({item['z']:+.2f})" for item in items
    ) or "—"


def _narrativa(ficha: dict) -> list[str]:
    narrativa = ficha["narrativa"]
    if narrativa is None:
        return ["", "_Ficha de plantilla: sin narrativa generada._"]

    lineas = ["", narrativa["tesis"], "", "**Riesgos declarados por la empresa**", ""]
    for riesgo in narrativa["riesgos"]:
        marca = "" if riesgo["verificada"] else " **[cita sin verificar]**"
        lineas.append(f"- {riesgo['afirmacion']}{marca}")
        lineas.append(f'  > "{riesgo["cita"]}"')

    fuente = narrativa["fuente"]
    recorte = " (recortado)" if fuente["recortado"] else ""
    lineas += [
        "",
        f"_Fuente: {fuente['formulario']} de {fuente['fecha']}, "
        f"{fuente['seccion']}, accession {fuente['accession']}{recorte}._",
    ]
    return lineas


def render(fichas: list[dict], exclusiones: dict[str, int]) -> str:
    """Human-readable report.

    Unverified quotes are marked in the body rather than footnoted: a warning
    nobody sees is the same as no warning, and the whole point of verifying was
    that the human gate can trust what it reads.
    """
    lineas = [
        "# Candidatos del sub-proyecto B",
        "",
        f"**Fecha:** {date.today().isoformat()} · **Candidatos:** {len(fichas)}",
        "",
        "> El orden lo decide un score determinista sobre z-scores sectoriales.",
        "> El score **no está validado empíricamente**: es un criterio de",
        "> selección transparente, no una previsión de rentabilidad.",
        "",
    ]

    for ficha in fichas:
        lineas += [
            f"## {ficha['puesto']}. {ficha['ticker']} — {ficha['sector_gics']}",
            "",
            f"Compuesto {ficha['compuesto']:+.2f} · {_pilares(ficha)}",
            "",
            f"- Fuerte en: {_kpis(ficha['destacados'])}",
            f"- Flojo en: {_kpis(ficha['flojos'])}",
            f"- Cobertura: {ficha['cobertura']['kpis_con_dato']} de 17 KPIs",
        ]
        if ficha["desplazo_a"]:
            lineas.append(
                f"- Dejó fuera por el tope sectorial: {', '.join(ficha['desplazo_a'])}"
            )
        lineas += _narrativa(ficha)
        lineas.append("")

    lineas += ["---", "", "## Empresas excluidas por las guardas", ""]
    for motivo, cuantas in sorted(exclusiones.items(), key=lambda par: -par[1]):
        lineas.append(f"- `{motivo}`: {cuantas}")

    return "\n".join(lineas) + "\n"
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_informe.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add ranking/informe.py tests/test_ranking_informe.py
git commit -m "feat: informe legible con las citas sin verificar marcadas"
```

---

### Task 14: Orquestación y salidas

**Files:**
- Create: `ranking/run.py`
- Test: `tests/test_ranking_run.py`

- [ ] **Step 1: Escribe el test que falla**

`tests/test_ranking_run.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.filings import Riesgos
from ranking.run import construir_ranking, guardar

SECTORES = {"Tech": 6, "Financials": 6, "Health": 6}


def panel_y_metadatos():
    """Panel con la forma de build_panel(con_zscore=True): 18 empresas, 4 trimestres."""
    generador = np.random.default_rng(11)
    trimestres = ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    filas, indice, meta = [], [], []
    for sector, cuantas in SECTORES.items():
        for numero in range(cuantas):
            ticker = f"{sector[:2].upper()}{numero}"
            meta.append({"ticker": ticker, "sector_gics": sector})
            for trimestre in trimestres:
                fila = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
                fila.update(
                    {
                        f"z_{kpi}": v
                        for kpi, v in zip(
                            TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))
                        )
                    }
                )
                fila["trimestre"] = trimestre
                filas.append(fila)
                indice.append(
                    (ticker, pd.Period(trimestre, freq="Q").end_time.normalize())
                )
    panel = pd.DataFrame(
        filas, index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"])
    )
    return panel, pd.DataFrame(meta).set_index("ticker")


RIESGOS = Riesgos(
    ticker="TE0",
    formulario="10-K",
    fecha="2025-10-31",
    accession="0000-25-000001",
    seccion="Item 1A",
    texto="We depend on a limited number of suppliers.",
    caracteres_totales=42,
    recortado=False,
)


@pytest.fixture
def sin_red():
    panel, metadatos = panel_y_metadatos()
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)), patch(
        "ranking.run.cargar_riesgos", return_value=RIESGOS
    ):
        yield


def test_devuelve_como_mucho_el_tamano_del_top(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert len(resultado.fichas) == 5
    assert [f["puesto"] for f in resultado.fichas] == [1, 2, 3, 4, 5]


def test_respeta_el_tope_sectorial(sin_red):
    resultado = construir_ranking(con_llm=False, n=15, tope=3)
    por_sector = pd.Series([f["sector_gics"] for f in resultado.fichas]).value_counts()
    assert por_sector.max() <= 3


def test_sin_llm_todas_las_fichas_son_de_plantilla(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert {f["generada_por"] for f in resultado.fichas} == {"plantilla"}
    assert all(f["narrativa"] is None for f in resultado.fichas)


def test_el_ranking_es_reproducible(sin_red):
    primera = construir_ranking(con_llm=False, n=5)
    segunda = construir_ranking(con_llm=False, n=5)
    assert [f["ticker"] for f in primera.fichas] == [f["ticker"] for f in segunda.fichas]


def test_cuenta_las_exclusiones_por_motivo(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    assert isinstance(resultado.exclusiones, dict)
    assert sum(resultado.exclusiones.values()) + len(resultado.tabla) == 18


def test_guardar_escribe_las_tres_salidas(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)

    assert (tmp_path / "ranking.csv").exists()
    assert (tmp_path / "informe.md").exists()

    fichas = json.loads((tmp_path / "fichas.json").read_text(encoding="utf-8"))
    assert len(fichas) == 5
    assert fichas[0]["narrativa"] is None
```

- [ ] **Step 2: Ejecuta el test para verificar que falla**

Run: `pytest tests/test_ranking_run.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ranking.run'`

- [ ] **Step 3: Escribe la implementación mínima**

`ranking/run.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fundamentals.run import build_panel
from ranking.criterio import TAMANO_TOP, TOPE_POR_SECTOR, TRIMESTRES_VENTANA
from ranking.fichas import descriptor, ficha_numerica
from ranking.filings import cargar_riesgos
from ranking.informe import render
from ranking.llm import redactar_con_cache
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    media_ventana,
    puntuaciones_por_pilar,
)
from ranking.seleccion import desplazamientos_por_ticker, seleccionar


@dataclass
class Resultado:
    """Everything a run produced, including what it left out and why."""

    tabla: pd.DataFrame
    fichas: list[dict]
    exclusiones: dict[str, int]
    cobertura_panel: object


def _contexto(ficha: dict) -> str:
    """Describe the candidate to the model in words, with no digits to echo."""
    lineas = [
        f"Empresa: {ficha['ticker']}, sector {ficha['sector_gics']}.",
        "Frente a sus pares del mismo sector:",
    ]
    for pilar, valor in ficha["pilares"].items():
        if valor is not None:
            lineas.append(f"- {pilar}: {descriptor(valor)}")
    lineas.append("Puntos más fuertes: " + ", ".join(i["kpi"] for i in ficha["destacados"]))
    lineas.append("Puntos más flojos: " + ", ".join(i["kpi"] for i in ficha["flojos"]))
    return "\n".join(lineas)


def _con_narrativa(ficha: dict, cache_dir: Path | None) -> dict:
    """Attach the qualitative half when it can be produced and verified."""
    riesgos = cargar_riesgos(ficha["ticker"])
    if riesgos is None:
        return ficha

    narrativa = redactar_con_cache(_contexto(ficha), riesgos.texto, cache_dir=cache_dir)
    if narrativa is None:
        return ficha

    narrativa["fuente"] = {
        "formulario": riesgos.formulario,
        "fecha": riesgos.fecha,
        "accession": riesgos.accession,
        "seccion": riesgos.seccion,
        "caracteres_enviados": len(riesgos.texto),
        "recortado": riesgos.recortado,
    }
    return {**ficha, "narrativa": narrativa, "generada_por": "sonnet-5"}


def construir_ranking(
    source: str | list[str] = "sp500",
    con_llm: bool = True,
    n: int = TAMANO_TOP,
    tope: int = TOPE_POR_SECTOR,
    cache_dir: Path | None = None,
) -> Resultado:
    """Panel in, ranked candidates out.

    A company that fails at any stage is recorded and skipped, never aborting
    the run — the same policy fundamentals already applies to downloads.
    """
    panel, metadatos, cobertura = build_panel(source, con_zscore=True)
    sectores = metadatos["sector_gics"]

    z, valores, historial = media_ventana(panel, n=TRIMESTRES_VENTANA)
    pilares, conteo = puntuaciones_por_pilar(z)

    trimestre_max = str(panel["trimestre"].max())
    motivos = aplicar_guardas(pilares, conteo, historial, trimestre_max)
    puntos = compuesto(pilares, motivos, sectores)
    motivos = marcar_sin_pares(motivos, puntos)

    elegidas, desplazadas = seleccionar(puntos, sectores, tope=tope, n=n)
    mapa = desplazamientos_por_ticker(desplazadas)

    fichas = []
    for fila in elegidas.itertuples(index=False):
        ficha = ficha_numerica(
            ticker=fila.ticker,
            sector=fila.sector,
            puesto=fila.puesto,
            compuesto=fila.compuesto,
            pilares=pilares.loc[fila.ticker],
            conteo=conteo.loc[fila.ticker],
            z=z.loc[fila.ticker],
            valores=valores.loc[fila.ticker],
            desplazo_a=mapa.get(fila.ticker, []),
        )
        if con_llm:
            ficha = _con_narrativa(ficha, cache_dir)
        fichas.append(ficha)

    tabla = pilares.join(puntos.rename("compuesto")).join(motivos.rename("exclusion"))
    tabla["sector_gics"] = sectores.reindex(tabla.index)
    tabla["kpis_con_dato"] = conteo.sum(axis=1)

    return Resultado(
        tabla=tabla.loc[motivos.isna()],
        fichas=fichas,
        exclusiones=motivos.dropna().value_counts().to_dict(),
        cobertura_panel=cobertura,
    )


def guardar(resultado: Resultado, destino: Path) -> None:
    """Write the three outputs. fichas.json is the contract with sub-project C."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    resultado.tabla.to_csv(destino / "ranking.csv")
    (destino / "fichas.json").write_text(
        json.dumps(resultado.fichas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destino / "informe.md").write_text(
        render(resultado.fichas, resultado.exclusiones), encoding="utf-8"
    )
```

- [ ] **Step 4: Ejecuta el test para verificar que pasa**

Run: `pytest tests/test_ranking_run.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Ejecuta la suite completa**

Run: `pytest tests/ -q -m "not red"`
Expected: PASS. El total debe ser 391 más los tests nuevos de las tareas 1-14.

- [ ] **Step 6: Commit**

```bash
git add ranking/run.py tests/test_ranking_run.py
git commit -m "feat: orquestacion del ranking y las tres salidas"
```

---

### Task 15: Test de red, medición real y documentación

**Files:**
- Create: `tests/test_ranking_contraste.py`
- Modify: `CONTEXTO.md`
- Modify: `docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md`

- [ ] **Step 1: Escribe el test marcado `red`**

`tests/test_ranking_contraste.py`:

```python
"""Contrastes contra las APIs reales. Necesitan red y credenciales.

    EDGAR_IDENTITY="tu@correo.com" ANTHROPIC_API_KEY=... pytest tests/ -q -m red
"""

import os

import pytest

from ranking.filings import MAX_CARACTERES, cargar_riesgos
from ranking.llm import MODELO, redactar, verificar_cita

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def identidad():
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("EDGAR_IDENTITY no está en el entorno")
    from fundamentals.fetch import set_sec_identity

    set_sec_identity()


def test_el_tope_en_caracteres_no_se_pasa_del_presupuesto_de_tokens():
    """El tope está en caracteres; el presupuesto real está en tokens.

    Se comprueba con count_tokens, que es lo único que cuenta tokens de Claude.
    Una regla de tres a 4 caracteres por token es una estimación, no una medida.
    """
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY no está en el entorno")

    riesgos = cargar_riesgos("JPM", max_caracteres=MAX_CARACTERES)
    assert riesgos is not None

    cuenta = anthropic.Anthropic().messages.count_tokens(
        model=MODELO,
        messages=[{"role": "user", "content": riesgos.texto}],
    )
    assert cuenta.input_tokens < 25_000, (
        f"{cuenta.input_tokens} tokens con un tope de {MAX_CARACTERES} caracteres: "
        "ajusta MAX_CARACTERES en ranking/filings.py"
    )


def test_el_modelo_devuelve_el_esquema_y_cita_de_verdad():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY no está en el entorno")

    riesgos = cargar_riesgos("AAPL", max_caracteres=20_000)
    assert riesgos is not None

    resultado = redactar(
        "Empresa: AAPL, sector Information Technology.\n"
        "Frente a sus pares: calidad muy por encima de sus pares.",
        riesgos.texto,
    )
    assert resultado is not None, "la API o el esquema fallaron"
    assert resultado["riesgos"], "el modelo no devolvió ningún riesgo"
    for riesgo in resultado["riesgos"]:
        assert verificar_cita(riesgo["cita"], riesgos.texto) == riesgo["verificada"]
```

- [ ] **Step 2: Ejecuta el test de red**

Run: `EDGAR_IDENTITY="esteban.110203@gmail.com" pytest tests/test_ranking_contraste.py -q -m red`
Expected: PASS, o SKIP si falta `ANTHROPIC_API_KEY`.

Si `thinking={"type": "disabled"}` fuera rechazado junto a `output_format=`, quita ese parámetro de `ranking/llm.py` y vuelve a ejecutar.

- [ ] **Step 3: Corre el ranking de verdad y mide las exclusiones**

Este es el número que el diseño dejó explícitamente pendiente de medir.

```bash
EDGAR_IDENTITY="esteban.110203@gmail.com" python -c "
from ranking.run import construir_ranking, guardar
r = construir_ranking(con_llm=False)
print('excluidas:', r.exclusiones)
print('supervivientes:', len(r.tabla))
print(r.tabla.groupby('sector_gics').size())
guardar(r, 'salidas')
"
```

Anota los números. **No ajustes ningún umbral** de `ranking/criterio.py` para mejorarlos.

- [ ] **Step 4: Escribe la enmienda con lo medido**

Añade al final de `docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md` una sección `## Enmienda 3 — <fecha>: cobertura real de las guardas` con: cuántas de las 502 sobreviven, el reparto por sector, y qué motivo de exclusión domina. Si un sector entero desaparece, dilo y explica en qué dirección afecta a la conclusión. Es un hallazgo, no un fallo que tapar.

- [ ] **Step 5: Actualiza CONTEXTO.md**

En la tabla de sub-proyectos, marca B como terminado. Añade una sección `## Resultado del sub-proyecto B` con los números del paso 3, y actualiza el bloque de comandos con:

```bash
EDGAR_IDENTITY="tu@correo.com" python -c "from ranking.run import construir_ranking, guardar; guardar(construir_ranking(), 'salidas')"
```

Actualiza también la cuenta de tests y la sección "Lo siguiente", que pasa a ser el sub-proyecto C.

- [ ] **Step 6: Commit**

```bash
git add tests/test_ranking_contraste.py CONTEXTO.md docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md
git commit -m "docs: sub-proyecto B terminado, con la cobertura de las guardas medida"
```

---

## Estado de ejecución — actualizado 2026-08-13

**Las quince tareas completas.** Fusionado en `master` (`79c052f`), **537 tests pasando** más 6 marcados `red`. La medición real de las guardas está en la **enmienda 3** del diseño.

De los tres tests `red`, el de EDGAR pasa; los dos que llaman al modelo saltan sin `ANTHROPIC_API_KEY`. El plan importaba `verificar_cita` de `ranking.llm`, que dejó de ser su sitio cuando la Task 11 separó los verificadores a `ranking/verificacion.py`.

| Task | Commits | Suite |
|---|---|---:|
| 1 · Criterio congelado | `4d45e9b` · `b95fcc1` | 396 |
| 2 · Ventana de 4 trimestres | `b39465e` · `9647863` | 402 |
| 3 · Pilares con signos | `9e63517` · `4b46940` · `7732310` | 408 |
| 4 · Guardas de exclusión | `3d0b91f` | 414 |
| 5 · Compuesto por sector | `2757398` · `5b91678` · `66939e3` | 422 |
| 6 · Control negativo | `f826d2a` · `a448af8` | 425 |
| 7 · Selección | `8f18bdc` · `fa7f6c0` · `a2f27c4` | 434 |
| 8 · Fichas numéricas | `b5b585d` · `2caf6bf` | 445 |
| 9 · Item 1A con caché | `9e30f85` · `5fe9179` | 453 |
| 10 · Verificadores | `01964c5` · `f23e2a0` | 467 |
| 11 · Llamada a Sonnet 5 | `4a8853f` · `301b0cc` · `7665f1f` | 493 |
| 12 · Caché de fichas | `5e5a429` · `7383ece` · `98b7b00` | 509 |
| 13 · Informe legible | `b63c17d` | 521 |
| 14 · Orquestación | `d326b8a` · `2e2cfce` | 537 |

**Siguiente: Task 15** (test de red, medición real y documentación). Sigue tal como está escrita arriba, con estas correcciones que la ejecución ya introdujo y que hay que respetar:

- `marcar_sin_pares` tiene la firma `(motivos, compuestos, sectores)` — sin `min_pares`. El código de la Task 14 en este plan la llama con dos argumentos; corregir al integrarla.
- Las etiquetas de exclusión son seis, no cuatro: `historia_corta`, `datos_rancios`, `pilar_sin_datos`, `cobertura_insuficiente`, `sector_desconocido`, `sin_dispersion_sectorial`.
- `ranking/filings.py` tiene ocho tests, no seis, y `cargar_riesgos` sanea la caché corrupta o con esquema viejo por su cuenta. La Task 14 no necesita envolverla en un `try`.
- `verificar_cita` exige ahora **dos** cotas, no una: `MIN_CARACTERES_CITA = 25` además del máximo, ambas sobre el texto normalizado. Es la **enmienda 2** del diseño, así que la que escribe la Task 15 pasa a ser la **enmienda 3**. `_normalizar` unifica además comillas tipográficas y guiones largos con sus equivalentes ASCII, y `sin_digitos` usa `isnumeric()`, no `isdigit()`.
- **Los verificadores ya no viven en `llm.py`**: están en `ranking/verificacion.py`, con sus constantes y sus tests en `tests/test_ranking_verificacion.py`. Se movieron antes de la Task 12 porque era el último momento en que el movimiento era mecánico: la caché mete I/O de disco en `llm.py`.
- **`redactar` hace más de lo que dice el plan.** Además de citas y cifras rechaza la tesis vacía (incluidos caracteres invisibles como U+200B, que `str.strip()` no ve), descarta el riesgo cuya `afirmacion` viene vacía —lleva cita real y sello de verificada sobre nada— y trunca a `MAX_RIESGOS` **antes** de verificar. El mensaje de reintento nombra el fallo que ocurrió de verdad; el del plan hablaba siempre de citas, aunque el fallo fueran cifras.
- **La clave de caché hashea el turno de usuario ya renderizado**, no `contexto` y `fuente` por separado, más `SISTEMA` y las dos cotas de verificación. La regla es "todo lo que se le manda al modelo, más las cotas con las que se juzgará su respuesta". `VERSION_PROMPT` deja de ser la única defensa y queda como escape manual para cambios en la lógica de `redactar` que el hash no ve.

- **`render` acepta una narrativa sin `fuente`** y lo dice en el cuerpo del informe en vez de reventar. Colapsa además los espacios de la cita, porque el texto crudo del Item 1A trae saltos de línea y sin eso la cita se sale de su bloque. La cobertura se imprime con `len(TODOS_LOS_KPIS)`, no con un 17 a mano.

- **La Task 14 ya está integrada y las dos correcciones anteriores aplicadas**: `marcar_sin_pares` con tres argumentos, y `guardar` escribiendo `fichas.json` con `allow_nan=False`. `construir_ranking(con_llm=False)` corre entero sin red.
- **El informe distingue la escala del compuesto de la de los pilares.** El compuesto es la media ponderada de los pilares **re-estandarizada dentro del sector** (enmienda 1), así que no está en su misma escala: en una corrida real conviven un compuesto de +1,53 y unos pilares que promedian +0,12. Se descubrió leyendo la salida de verdad, no con un test.

**Ya resuelto — `redactar()` no produce la procedencia, y el informe la necesita.** La Task 14 la inyecta en `_con_narrativa` desde el `Riesgos` de `filings.py`, y hay test que lo fija. Se deja anotado porque la dependencia sigue siendo invisible al leer `redactar` por su cuenta: Devuelve `{tesis, riesgos}` y nada más; `narrativa["fuente"]` —formulario, fecha, accession, sección, si se recortó— la tiene que inyectar la orquestación desde el `Riesgos` que devuelve `cargar_riesgos`. Sin eso, cada cita del informe queda sin forma de localizarse en el filing original, que es la promesa entera del sub-proyecto. El informe ya no aborta la corrida si falta, pero imprime "procedencia no disponible" en el cuerpo: **si eso aparece en la salida real, es un fallo de la Task 14, no del informe.**

**Resuelto — la clave de caché depende de que `contexto` sea único por empresa.** `_contexto` en `run.py` empieza por `f"Empresa: {ficha['ticker']}, sector ..."`, así que dos empresas no pueden compartir ficha por colisión de clave. Queda por escrito porque es una invariante que un refactor de `_contexto` podría romper sin que ningún test de `llm.py` se entere.

**Aviso para la Task 14 — un hazard dormido.** `_escribir_cache` deriva el nombre del temporal sólo del ticker (`fichero.with_suffix(".tmp")`), así que dos procesos cargando el mismo ticker comparten un único `.tmp` y uno puede hacer `replace()` de un fichero que el otro aún escribe, anulando justo la atomicidad que el temporal existe para dar. En un programa de un solo hilo no puede pasar, y por eso se dejó como está. **Despierta en cuanto se paralelicen las 502 descargas** — que es lo natural de querer, siendo ésta la etapa limitada por red. El seguro es barato: `tempfile.mkstemp(dir=...)` o el pid en el nombre. `fundamentals/fetch.py:124` tiene la forma idéntica, así que arreglar uno solo sería peor que arreglar los dos o ninguno.

### La disciplina que hay que mantener

Siete de las ocho revisiones encontraron un defecto real, y **los siete eran tests que no podían fallar**: verificaban el caso feliz sin comprobar nunca que distinguían el caso roto. No eran fallos de implementación — el código salía bien casi siempre.

El remedio es barato y hay que exigirlo en cada tarea: **romper a propósito la cosa que el test dice verificar, comprobar que el test falla, restaurar, y reportar la salida literal.** Desde que se pidió en cada despacho, los implementadores empezaron a encontrar los huecos ellos mismos antes de la revisión.

Casos concretos que se colaron y lo que los cazó:

| Hueco | Lo habría pasado por alto |
|---|---|
| Signos fijados sólo en 5 de 17 KPIs | `roe: -1` invertía el ranking en silencio |
| `valores` sin cobertura real | Promediar las columnas `z_` en vez de las crudas |
| Fixtures de un solo ticker | Un escalar repartido a todas las filas |
| Tolerancia ±0,10 en el control negativo | El artefacto que buscaba mide 0,087 |
| El límite `n` sin test | El "15" de "top 15" |
| `puesto` compactado sin aserción | Filtrar el rango global en su lugar |
| `json.dumps` sin `allow_nan=False` | Escribir el literal `NaN`, que no es JSON |
| Fixture de caché en ASCII puro | Escribir el filing en cp1252 y no volver a leerlo nunca |

**La Task 9 cambió de dónde salieron los huecos.** Por primera vez los siete tests del plan mordían para lo que cada uno decía verificar —el implementador cazó él solo el único que no, y la revisión lo reprodujo—. Los dos hallazgos importantes estaban en otro sitio: en las **dos features de robustez que el implementador añadió sin que se le pidieran** (escritura atómica y auto-sanado de caché corrupta). Añadió el código y no lo cubrió bien:

- La fixture heredada era `"A" * 500`, ASCII puro, donde cp1252 y utf-8 dan los mismos bytes: quitar el `encoding="utf-8"` dejaba los siete tests en verde. Y el auto-sanado recién añadido **convertía ese fallo en invisible** — `UnicodeDecodeError` → borrar el fichero → tratarlo como fallo de caché → redescargar en cada corrida, para siempre, sin error. Un Item 1A real va lleno de comillas tipográficas. Arreglo: `"—" * 500`.
- El auto-sanado sólo cubría JSON no parseable. Un JSON válido con otra forma lo atravesaba y reventaba después con `KeyError: 'texto'`, que es justo el atasco permanente que la función existía para evitar.

La lección que generaliza: **cuando un implementador añade robustez que no se le pidió, hay que revisar esa parte con más escrutinio que el resto, no con menos.** No hay test escrito de antemano que la cubra, y el propio mecanismo defensivo tiende a enmascarar el fallo que debería denunciar.

**La Task 10 volvió a moverlo de sitio, y en la dirección que peor se ve.** Toda la discusión de la tarea giró alrededor de la normalización tipográfica: si unificar comillas curvas abría una vía de cita fabricada. Se le dedicó un despacho, una decisión razonada y un intento adversarial de romperla en la revisión — que no lo consiguió, así que la respuesta fue "no, no la abre". Mientras tanto, el agujero grande estaba en lo que nadie miraba:

```
verificar_cita("we", item1a)    -> True
verificar_cita("risks", item1a) -> True
```

No había cota inferior. Una cita de dos letras se llevaba el sello de "verificada", que es la promesa central del sub-proyecto. Se cerró con `MIN_CARACTERES_CITA = 25` y quedó como **enmienda 2** del diseño.

Lo que hay que llevarse: **el escrutinio se concentra donde hubo debate, y el debate lo elige quien escribe el despacho.** Los tres agujeros que se le señalaron al implementador estaban medidos y eran reales, y aun así fijar la agenda en ellos dejó fuera el que más importaba. Contra eso no sirve mutar tests —los tests no cubrían el caso porque a nadie se le había ocurrido—, sino preguntar aparte, y en frío: *¿cuál es la entrada más tonta que esta función acepta y no debería?*

**Las tareas 11 y 12 volvieron a confirmarlo, con la misma forma.** En la 11 el implementador cerró la tesis vacía —el caso que se le señaló— y dejó abierto el campo de al lado: una `afirmacion` vacía con cita válida salía con `verificada: true`, el sello puesto sobre nada. Y borrar el chequeo de cifras en `afirmacion` dejaba los 26 tests en verde, siendo que el spec lo nombraba explícitamente. En la 12, el test que protegía la lección más cara del proyecto —`hashlib` y no `hash()`, que ya envenenó una caché— llamaba a la función dos veces **en el mismo proceso**, donde `hash()` también es estable: no podía fallar.

**La Task 14 aportó la variante más difícil de todas**, encontrada por el implementador al hacerse la pregunta en frío: forzó `if True:` en lugar de `if con_llm:`, de modo que `con_llm=False` **sí llamaba al modelo** — y `test_sin_llm_todas_las_fichas_son_de_plantilla` **siguió en verde**. El motivo es que en un entorno sin `ANTHROPIC_API_KEY`, `redactar_con_cache` degrada a `None` igualmente, así que el resultado observable del código roto y del correcto es idéntico. **El test no medía la bandera: medía la ausencia de credenciales.** Se cerró inyectando un cliente falso y comprobando que no recibe ninguna llamada.

Es un caso que generaliza mal y conviene tener presente: **un test puede pasar por una razón que no tiene nada que ver con lo que dice comprobar, y el entorno de pruebas es una de esas razones.** Cuando el sistema degrada con elegancia ante una dependencia ausente, todo test que sólo mire la salida final es sospechoso.

Y una tercera variante que conviene reconocer, porque no la caza mutar tests: **un docstring que promete una garantía que el código no da.** `clave_cache` afirmaba que su parámetro `sistema` no podía desincronizarse de lo que manda `redactar`. Los argumentos por defecto en Python se evalúan una sola vez, al definirse la función, así que reasignar la global desincronizaba las dos cosas en silencio — exactamente lo que el parámetro existía para impedir. El test que decía cubrirlo comparaba dos llamadas que usaban el mismo valor congelado. **Cuando un comentario afirme que algo es imposible, ejecútalo antes de creerlo.**

### Desviaciones conscientes de la skill de ejecución

- A partir de la Task 4 las dos revisiones (spec y calidad) van en **un solo subagente**, primero una y luego la otra, por presupuesto de sesión. Pierde el contexto fresco e independiente entre ambas.
- La Task 7 se aceptó sin tercera ronda de revisión: las cinco correcciones eran aplicación mecánica de código especificado literalmente, con bite-check verbatim.
- **La Task 12 se cerró sin subagente revisor.** Se agotó el límite de sesión y el subagente murió a mitad del último arreglo. La verificación la hizo el controlador: lectura del módulo entero, el hallazgo del default congelado (encontrado comprobando por ejecución una afirmación del docstring), y el bite-check de esa corrección con la salida literal. **Es la desviación más grande de todas las anotadas aquí**: la revisión independiente ha encontrado un defecto real en diez de las once tareas en que se hizo, así que su ausencia aquí no es prueba de que no haya nada. Si alguien retoma con presupuesto, revisar `redactar_con_cache`, `_forma_valida` y `_leer_cache` con ojos frescos es la deuda pendiente.

---

## Comprobación final

- [ ] `pytest tests/ -q -m "not red"` en verde
- [ ] El control negativo de `tests/test_ranking_control.py` pasa **sin** haber tocado su tolerancia
- [ ] `ranking/criterio.py` no se ha modificado desde su commit de la Task 1
- [ ] `salidas/fichas.json` existe y valida contra la forma del diseño
- [ ] La enmienda 3 recoge números medidos, no estimados
