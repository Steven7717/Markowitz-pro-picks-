# Motor de fundamentales — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingesta determinista de 16 KPIs fundamentales por trimestre, para 12 trimestres, sobre un universo configurable, con z-score sectorial y reporte de cobertura completo.

**Architecture:** Paquete nuevo `fundamentals/`, hermano de `research/`, que no toca la app ni el estudio. Seis módulos con una responsabilidad cada uno: resolución de universo, cadenas de conceptos XBRL, descarga con caché, cálculo de KPIs, sectores, orquestación. La red vive detrás de costuras parcheables (`_fetch_facts`, `_download`) siguiendo el patrón ya probado en `research/loader.py`.

**Tech Stack:** Python 3, pandas, edgartools (XBRL de SEC), pyarrow, pytest. `research.loader` se reutiliza para precios.

**Diseño de referencia:** [`docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md`](../specs/2026-08-10-motor-fundamentales-design.md)

---

## Convenciones del repo — leer antes de empezar

Los tests existentes en `tests/` establecen un estilo que este plan sigue:

- Nombre de test descriptivo y en inglés, que dice el comportamiento, no la función.
- Docstring cuando el test existe por una razón que no es obvia: explica **qué defecto real atrapa**.
- La red se aísla en una función privada de una sola línea que los tests parchean con `unittest.mock.patch`. Nunca se llama a la red en un test.
- Comentarios de código en inglés; texto que ve el usuario, en español.
- `hashlib.md5` para claves de caché, nunca `hash()`.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `fundamentals/__init__.py` | Paquete vacío |
| `fundamentals/universe.py` | `resolve(source)` → lista de tickers |
| `fundamentals/concepts.py` | Tabla de cadenas de conceptos XBRL y su resolución |
| `fundamentals/fetch.py` | Identidad SEC, descarga por ticker, caché parquet, `CoverageReport` |
| `fundamentals/kpis.py` | Los 16 KPIs, con guardas de división |
| `fundamentals/sectors.py` | Carga de GICS y z-score dentro del sector |
| `fundamentals/run.py` | Orquestación: universo → panel + metadatos + cobertura |
| `scripts/bootstrap_sectors.py` | Genera el fichero de sectores, una sola vez |
| `fundamentals/data/sectores_2026-08-10.csv` | ticker → sector GICS, congelado |

Tests espejo en `tests/test_fundamentals_<módulo>.py`.

---

### Task 1: Dependencia y verificación de la API real

Antes de escribir código contra edgartools hay que confirmar qué devuelve de verdad. El diseño asume `periods=12, annual=False` y conceptos XBRL en el índice; esto lo comprueba con empresas reales en vez de darlo por bueno.

**Files:**
- Modify: `requirements.txt`
- Create: `scripts/verificar_edgartools.py` (descartable, no se commitea)

- [ ] **Step 1: Instalar la dependencia**

```bash
pip install "edgartools>=4.0.0"
```

- [ ] **Step 2: Escribir el script de verificación**

Crear `scripts/verificar_edgartools.py`:

```python
"""Confirma la forma real de los datos que devuelve edgartools.

Descartable: existe para validar supuestos del diseno, no se commitea.
Ejecutar con EDGAR_IDENTITY puesto.
"""
import os

from edgar import Company, set_identity

set_identity(os.environ["EDGAR_IDENTITY"])

for ticker in ["AAPL", "JPM", "PLD", "NFLX"]:
    company = Company(ticker)
    facts = company.get_facts()
    df = facts.income_statement(periods=12, annual=False, as_dataframe=True)
    print(f"\n===== {ticker} | sic={company.sic} | {company.industry} =====")
    print(f"forma: {df.shape}")
    print(f"columnas: {list(df.columns)[:14]}")
    print(f"indice (primeros 12): {list(df.index)[:12]}")
```

- [ ] **Step 3: Ejecutar y anotar la forma real**

```bash
EDGAR_IDENTITY="tu@correo.com" python scripts/verificar_edgartools.py
```

Anotar cuatro cosas, porque las tareas siguientes dependen de ellas:
1. ¿Devuelve 12 columnas de periodo, o menos?
2. ¿El índice son conceptos XBRL crudos (`Revenues`) o etiquetas legibles (`Revenue`)?
3. ¿Cómo se llama exactamente el renglón de ingresos en AAPL frente a JPM?
4. ¿Las columnas de periodo son fechas de **cierre de trimestre** (`2025-09-27`) o de **presentación**? Son distintas y la diferencia importa: los resultados de un trimestre no son públicos el día que el trimestre cierra.

**Si el índice resulta ser etiquetas legibles y no conceptos XBRL crudos**, la tabla de la Task 5 debe usar esas etiquetas. El resto del plan no cambia.

**Si edgartools expone la fecha de presentación real** de cada trimestre, úsala en la Task 9 en lugar del desfase fijo que allí se documenta, y borra la constante `DIAS_HASTA_PRESENTACION`. La fecha real es estrictamente mejor que la aproximación.

- [ ] **Step 4: Fijar la dependencia**

Añadir al final de `requirements.txt`:

```
# Motor de fundamentales (paquete fundamentals/): XBRL de SEC, gratis y sin API key.
edgartools>=4.0.0
```

- [ ] **Step 5: Borrar el script y commitear**

```bash
rm scripts/verificar_edgartools.py
git add requirements.txt
git commit -m "chore: dependencia edgartools para el motor de fundamentales"
```

---

### Task 2: Resolución de universo

**Files:**
- Create: `fundamentals/__init__.py`, `fundamentals/universe.py`
- Test: `tests/test_fundamentals_universe.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_universe.py`:

```python
import pytest

from fundamentals.universe import resolve


def test_sp500_delegates_to_the_frozen_snapshot():
    from research.universe import sp500_members

    assert resolve("sp500") == sp500_members()


def test_an_explicit_list_is_returned_normalised():
    assert resolve(["aapl", " msft ", "brk.b"]) == ["AAPL", "MSFT", "BRK-B"]


def test_duplicates_are_removed_keeping_first_appearance():
    """Un ticker repetido se descargaria dos veces y contaria doble en la cobertura."""
    assert resolve(["AAPL", "MSFT", "AAPL"]) == ["AAPL", "MSFT"]


def test_an_empty_list_is_rejected():
    with pytest.raises(ValueError, match="vacío"):
        resolve([])


def test_an_unknown_source_name_is_rejected():
    with pytest.raises(ValueError, match="desconocido"):
        resolve("russell2000")
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_universe.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/__init__.py` vacío. Crear `fundamentals/universe.py`:

```python
from research.universe import normalise_ticker, sp500_members

_FUENTES = {"sp500": sp500_members}


def resolve(source: str | list[str]) -> list[str]:
    """Convierte un nombre de universo o una lista suelta en tickers normalizados.

    Accepting an arbitrary list is what lets sub-project B feed candidates that
    are not index members without this module needing to know where they came from.
    """
    if isinstance(source, str):
        if source not in _FUENTES:
            raise ValueError(
                f"Universo desconocido: {source!r}. Disponibles: {sorted(_FUENTES)}"
            )
        tickers = _FUENTES[source]()
    else:
        tickers = list(source)

    if not tickers:
        raise ValueError("El universo está vacío")

    vistos: dict[str, None] = {}
    for t in tickers:
        vistos.setdefault(normalise_ticker(t), None)
    return list(vistos)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_universe.py -v
```

Esperado: 5 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/__init__.py fundamentals/universe.py tests/test_fundamentals_universe.py
git commit -m "feat: resolucion de universo para el motor de fundamentales"
```

---

### Task 3: Fichero congelado de sectores GICS

El snapshot `research/data/sp500_members_2026-08-05.csv` **no se toca**: la reproducibilidad del estudio D depende de esa membresía exacta. Los sectores van en un fichero nuevo.

**Files:**
- Create: `scripts/bootstrap_sectors.py`, `fundamentals/data/sectores_2026-08-10.csv`

- [ ] **Step 1: Escribir el script de bootstrap**

Crear `scripts/bootstrap_sectors.py`:

```python
"""Generate the frozen ticker -> GICS sector table. Run once, commit the output.

Sector membership must not change between two runs of the engine, so this is a
committed file rather than a live lookup, exactly like the universe snapshot.

Deliberately does NOT touch research/data/sp500_members_2026-08-05.csv: study D
reproduces against that exact membership, and regenerating it today would change
which companies it contains.
"""
import os
import sys
from pathlib import Path

import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT = Path(__file__).resolve().parent.parent / "fundamentals" / "data" / "sectores_2026-08-10.csv"

# Same User-Agent policy as scripts/bootstrap_universe.py: Wikipedia rejects
# urllib's default with HTTP 403, and the contact comes from the environment so
# nobody's personal address lands in a committed file.
_CONTACT = os.environ.get("BOOTSTRAP_CONTACT", "sin contacto declarado")
_HEADERS = {"User-Agent": f"markowitz-pro-picks-research/1.0 ({_CONTACT})"}


def normalise(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def main() -> int:
    constituents = pd.read_html(WIKIPEDIA_URL, storage_options=_HEADERS)[0]
    tabla = pd.DataFrame(
        {
            "ticker": [normalise(s) for s in constituents["Symbol"]],
            "sector_gics": constituents["GICS Sector"].str.strip(),
        }
    ).sort_values("ticker").drop_duplicates("ticker")

    grupos = tabla["sector_gics"].value_counts()
    if grupos.min() < 10:
        print(
            f"AVISO: el sector mas pequeno tiene {grupos.min()} empresas. "
            "Un z-score sectorial contra un grupo pequeno no informa nada.",
            file=sys.stderr,
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(OUTPUT, index=False)
    print(f"Escritos {len(tabla)} tickers en {OUTPUT}")
    print(f"Sectores: {len(grupos)} | menor: {grupos.min()} | mayor: {grupos.max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Ejecutar el bootstrap**

```bash
python scripts/bootstrap_sectors.py
```

Esperado: `Escritos 503 tickers` y `Sectores: 11 | menor: 21 | mayor: 83`.

Si sale algún sector con menos de 10 empresas, parar: significa que la tabla de Wikipedia cambió de forma y hay que revisar antes de seguir.

- [ ] **Step 3: Verificar que el snapshot de D sigue intacto**

```bash
git status --porcelain research/data/
```

Esperado: sin salida. Si aparece `sp500_members_2026-08-05.csv` modificado, revertirlo — rompería la reproducibilidad de D.

- [ ] **Step 4: Commitear**

```bash
git add scripts/bootstrap_sectors.py fundamentals/data/sectores_2026-08-10.csv
git commit -m "feat: tabla congelada de sectores GICS"
```

---

### Task 4: Sectores y z-score

**Files:**
- Create: `fundamentals/sectors.py`
- Test: `tests/test_fundamentals_sectors.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_sectors.py`:

```python
import numpy as np
import pandas as pd
import pytest

from fundamentals.sectors import load_sectors, zscore_within_sector


def test_the_frozen_table_covers_the_whole_sp500():
    from fundamentals.universe import resolve

    sectores = load_sectors()
    faltan = [t for t in resolve("sp500") if t not in sectores]
    assert faltan == [], f"Sin sector: {faltan}"


def test_no_sector_group_is_too_small_to_zscore():
    """Un z-score contra un grupo de una empresa vale 0 por construccion.

    Medido durante el diseno: SIC de 4 digitos dejaba 87 empresas solas. GICS
    Sector no deja ninguna, y este test lo mantiene asi si la tabla se regenera.
    """
    conteo = pd.Series(load_sectors()).value_counts()
    assert conteo.min() >= 10


def test_a_value_at_the_sector_mean_scores_zero():
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec", "tec", "tec"], index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert z.loc["B", "margen"] == pytest.approx(0.0)


def test_sectors_are_scored_independently_of_each_other():
    """Comparar una petrolera con una tecnologica es el defecto que esto evita."""
    kpis = pd.DataFrame({"margen": [1.0, 2.0, 3.0, 100.0, 200.0, 300.0]}, index=list("ABCDEF"))
    sectores = pd.Series(["tec"] * 3 + ["energia"] * 3, index=list("ABCDEF"))
    z = zscore_within_sector(kpis, sectores)
    assert z.loc["B", "margen"] == pytest.approx(z.loc["E", "margen"])


def test_a_company_without_a_known_sector_gets_a_missing_score_not_a_zero():
    """Un 0 se lee como 'promedio de su sector'. Ausente se lee como 'no se sabe'."""
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "X"])
    sectores = pd.Series(["tec", "tec", None], index=["A", "B", "X"])
    z = zscore_within_sector(kpis, sectores)
    assert np.isnan(z.loc["X", "margen"])


def test_a_sector_with_no_dispersion_yields_missing_not_infinity():
    """Dividir por una desviacion de cero da inf y parece un dato extraordinario."""
    kpis = pd.DataFrame({"margen": [7.0, 7.0, 7.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec"] * 3, index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert z["margen"].isna().all()


def test_a_missing_kpi_stays_missing_after_scoring():
    kpis = pd.DataFrame({"margen": [10.0, np.nan, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec"] * 3, index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores)
    assert np.isnan(z.loc["B", "margen"])


def test_a_group_below_the_minimum_size_is_not_scored():
    kpis = pd.DataFrame({"margen": [10.0, 20.0, 30.0]}, index=["A", "B", "C"])
    sectores = pd.Series(["tec", "tec", "solo"], index=["A", "B", "C"])
    z = zscore_within_sector(kpis, sectores, min_pares=3)
    assert np.isnan(z.loc["C", "margen"])
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_sectors.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.sectors'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/sectors.py`:

```python
from pathlib import Path

import numpy as np
import pandas as pd

# Al regenerar la tabla, actualiza también OUTPUT en scripts/bootstrap_sectors.py
_TABLA = Path(__file__).parent / "data" / "sectores_2026-08-10.csv"

MIN_PARES = 3


def load_sectors(path: Path | None = None) -> dict[str, str]:
    """Read the frozen ticker -> GICS sector table. Never queries the network."""
    frame = pd.read_csv(path or _TABLA)
    return dict(zip(frame["ticker"], frame["sector_gics"]))


def zscore_within_sector(
    kpis: pd.DataFrame, sectores: pd.Series, min_pares: int = MIN_PARES
) -> pd.DataFrame:
    """Standardise each KPI against sector peers rather than the whole universe.

    A margin of 40% means something different for software than for a grocer, so
    comparing across sectors ranks the sector, not the company.

    Returns NaN — never 0 — where a score cannot be computed: unknown sector, a
    peer group too small to have a meaningful spread, or a sector where every
    company reports the same value. A 0 would read as "exactly average".
    """
    sectores = sectores.reindex(kpis.index)
    resultado = pd.DataFrame(np.nan, index=kpis.index, columns=kpis.columns, dtype="float64")

    for sector, grupo in kpis.groupby(sectores, dropna=True):
        if len(grupo) < min_pares:
            continue
        desviacion = grupo.std(ddof=1)
        # A zero spread divides to infinity, which downstream reads as a huge
        # score. Masking it keeps "no dispersion" distinguishable from "extreme".
        centrado = grupo - grupo.mean()
        resultado.loc[grupo.index] = centrado / desviacion.where(desviacion > 0)

    return resultado
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_sectors.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/sectors.py tests/test_fundamentals_sectors.py
git commit -m "feat: z-score sectorial que nunca imputa un cero"
```

---

### Task 5: Cadenas de conceptos XBRL

Los emisores no usan las mismas etiquetas para el mismo renglón. Esta tabla es el trabajo real del módulo.

**Files:**
- Create: `fundamentals/concepts.py`
- Test: `tests/test_fundamentals_concepts.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_concepts.py`:

```python
import numpy as np
import pandas as pd

from fundamentals.concepts import LINEAS, resolve_lines


def _facts(filas: dict[str, list[float]], periodos: list[str]) -> pd.DataFrame:
    """Hechos crudos tal como los devuelve edgartools: conceptos en el indice."""
    return pd.DataFrame(filas, index=periodos).T


def test_the_first_concept_in_the_chain_wins():
    facts = _facts({"Revenues": [100.0], "SalesRevenueNet": [999.0]}, ["2025Q1"])
    lineas, _ = resolve_lines(facts)
    assert lineas.loc["2025Q1", "ingresos"] == 100.0


def test_a_later_concept_is_used_when_the_first_is_absent():
    """Apple declara ingresos con una etiqueta que la mayoria no usa."""
    facts = _facts({"SalesRevenueNet": [250.0]}, ["2025Q1"])
    lineas, _ = resolve_lines(facts)
    assert lineas.loc["2025Q1", "ingresos"] == 250.0


def test_a_line_with_no_matching_concept_is_missing_not_zero():
    """Un 0 en ingresos se lee como 'no vendio nada'. Ausente se lee como 'no lo declara'."""
    facts = _facts({"Revenues": [100.0]}, ["2025Q1"])
    lineas, ausentes = resolve_lines(facts)
    assert np.isnan(lineas.loc["2025Q1", "beneficio_neto"])
    assert "beneficio_neto" in ausentes


def test_present_lines_are_not_reported_as_missing():
    facts = _facts({"Revenues": [100.0]}, ["2025Q1"])
    _, ausentes = resolve_lines(facts)
    assert "ingresos" not in ausentes


def test_every_line_appears_as_a_column_even_when_absent():
    """Un panel con columnas variables segun la empresa no se puede concatenar."""
    facts = _facts({"Revenues": [100.0]}, ["2025Q1"])
    lineas, _ = resolve_lines(facts)
    assert sorted(lineas.columns) == sorted(LINEAS)


def test_periods_are_sorted_oldest_first():
    """El calculo interanual usa shift(4) y depende del orden."""
    facts = _facts({"Revenues": [3.0, 1.0, 2.0]}, ["2025Q3", "2025Q1", "2025Q2"])
    lineas, _ = resolve_lines(facts)
    assert list(lineas.index) == ["2025Q1", "2025Q2", "2025Q3"]


def test_empty_facts_yield_an_empty_frame_with_every_column():
    lineas, ausentes = resolve_lines(pd.DataFrame())
    assert lineas.empty
    assert sorted(ausentes) == sorted(LINEAS)


def test_no_line_declares_an_empty_chain():
    """Una cadena vacia haria que la linea nunca se resuelva, en silencio."""
    assert all(len(cadena) > 0 for cadena in LINEAS.values())
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_concepts.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.concepts'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/concepts.py`:

```python
import numpy as np
import pandas as pd

# Ordered fallback chains: try the first tag, then the next. Filers do not agree
# on labels for the same line — Apple reports revenue as
# RevenueFromContractWithCustomerExcludingAssessedTax while most use Revenues.
#
# This is a data table on purpose: it can be tested row by row, and adding a
# filer's dialect is an edit here rather than a change to any logic.
LINEAS: dict[str, tuple[str, ...]] = {
    "ingresos": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ),
    "coste_de_ventas": (
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ),
    "beneficio_operativo": (
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ),
    "beneficio_neto": (
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ),
    "bpa_diluido": (
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
    ),
    "depreciacion_amortizacion": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ),
    "gasto_por_intereses": (
        "InterestExpense",
        "InterestIncomeExpenseNet",
        "InterestExpenseDebt",
    ),
    "activos_totales": ("Assets",),
    "activos_corrientes": ("AssetsCurrent",),
    "pasivos_corrientes": ("LiabilitiesCurrent",),
    "patrimonio_neto": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "deuda_total": (
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ),
    "efectivo": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "flujo_operativo": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "acciones_diluidas": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
}


def resolve_lines(facts: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Map raw XBRL facts onto the fixed set of line items the KPIs need.

    `facts` carries XBRL concepts on the index and periods on the columns, as
    edgartools returns it. The result always has one column per line in LINEAS,
    even for lines this filer never reports: a panel whose columns depend on the
    company cannot be concatenated across the universe.

    Returns the frame and the names of the lines no concept satisfied.
    """
    periodos = sorted(facts.columns.astype(str)) if not facts.empty else []
    lineas = pd.DataFrame(np.nan, index=periodos, columns=list(LINEAS), dtype="float64")
    ausentes: list[str] = []

    disponibles = {str(c): c for c in facts.index} if not facts.empty else {}

    for linea, cadena in LINEAS.items():
        for concepto in cadena:
            if concepto in disponibles:
                serie = facts.loc[disponibles[concepto]]
                serie.index = serie.index.astype(str)
                lineas[linea] = pd.to_numeric(serie, errors="coerce").reindex(periodos)
                break
        else:
            ausentes.append(linea)

    return lineas, ausentes
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_concepts.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/concepts.py tests/test_fundamentals_concepts.py
git commit -m "feat: cadenas de conceptos XBRL con alternativas por emisor"
```

---

### Task 6: Descarga con caché y reporte de cobertura

**Files:**
- Create: `fundamentals/fetch.py`
- Test: `tests/test_fundamentals_fetch.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_fetch.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from fundamentals.fetch import CoverageReport, _cache_path, load_facts


def _facts(ticker: str, n_periodos: int = 12) -> pd.DataFrame:
    periodos = [f"2023Q{i % 4 + 1}-{i}" for i in range(n_periodos)]
    return pd.DataFrame(
        {p: [100.0 + i, 40.0 + i] for i, p in enumerate(periodos)},
        index=["Revenues", "NetIncomeLoss"],
    )


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_returns_facts_per_ticker_and_a_coverage_report(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        hechos, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert sorted(hechos) == ["AAA", "BBB"]
    assert isinstance(cobertura, CoverageReport)
    assert cobertura.included == ["AAA", "BBB"]


def test_a_ticker_with_too_few_quarters_is_marked_but_still_included(cache_dir):
    """Sin 5 trimestres no hay ningun KPI de crecimiento, pero los niveles sirven."""
    def pocos(ticker, periods):
        return _facts(ticker, 3 if ticker == "BBB" else 12)

    with patch("fundamentals.fetch._fetch_facts", side_effect=pocos):
        hechos, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert "BBB" in hechos
    assert cobertura.short_history["BBB"] == 3
    assert "BBB" in cobertura.included


def test_an_unresolvable_ticker_is_reported_separately_from_a_network_failure(cache_dir):
    """Un ticker que no existe y una caida de SEC son problemas distintos.

    Medido durante el diseno: AEP no aparece en el mapa oficial ticker->CIK de
    SEC. Confundirlo con un fallo de red esconderia una caida real.
    """
    def falla(ticker, periods):
        if ticker == "BBB":
            raise LookupError("sin CIK")
        raise RuntimeError("boom")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla), \
         patch("fundamentals.fetch.time.sleep"):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir, max_retries=1)
    assert cobertura.unresolved_cik == ["BBB"]
    assert cobertura.failed_download == ["AAA"]


def test_a_transient_failure_is_retried(cache_dir):
    intentos = {"n": 0}

    def flaky(ticker, periods):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("transient")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=flaky), \
         patch("fundamentals.fetch.time.sleep"):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir, max_retries=3)
    assert intentos["n"] == 2
    assert cobertura.included == ["AAA"]


def test_the_second_call_reads_from_cache_without_downloading(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)) as primera:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert primera.call_count == 1

    with patch("fundamentals.fetch._fetch_facts") as segunda:
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert segunda.call_count == 0
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_a_corrupted_cache_file_is_recovered_by_re_downloading(cache_dir):
    """Una corrida matada a media escritura deja un parquet truncado.

    Es el defecto que envenenaba todas las corridas siguientes en el estudio D.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        load_facts(["AAA"], cache_dir=cache_dir)

    fichero = next(cache_dir.glob("*.parquet"))
    fichero.write_bytes(b"not a valid parquet file")

    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_the_cache_key_does_not_depend_on_process_local_hashing(cache_dir):
    """Python aleatoriza el hash de strings entre procesos; una clave asi nunca acierta."""
    import hashlib

    esperado = hashlib.md5(b"AAA_12").hexdigest()[:12]
    assert _cache_path(cache_dir, "AAA", 12).name == f"facts_{esperado}.parquet"


def test_each_ticker_is_cached_separately(cache_dir):
    """Los trimestrales llegan escalonados; una cache por universo se invalidaria entera."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert len(list(cache_dir.glob("*.parquet"))) == 2


def test_refresh_bypasses_the_cache_and_downloads_again(cache_dir):
    """Refrescar tiene que ser posible sin borrar ficheros a mano."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)) as otra:
        load_facts(["AAA"], cache_dir=cache_dir, refresh=True)
    assert otra.call_count == 1


def test_refresh_is_off_by_default(cache_dir):
    """Un refresco automatico cambiaria los numeros entre dos corridas sin avisar."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts") as ninguna:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert ninguna.call_count == 0


def test_coverage_summary_names_every_category(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    resumen = cobertura.summary()
    assert "solicitados" in resumen
    assert "incluidos" in resumen
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_fetch.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.fetch'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/fetch.py`:

```python
import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_DEFAULT_CACHE = Path(__file__).parent / ".cache"
PERIODOS = 12
MIN_TRIMESTRES = 5


@dataclass
class CoverageReport:
    """Which tickers made it into the panel, and why the rest did not.

    Silently dropping tickers is how an engine ends up describing a universe
    nobody chose. Every exclusion is counted and attributed to a cause.
    """

    requested: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    unresolved_cik: list[str] = field(default_factory=list)
    failed_download: list[str] = field(default_factory=list)
    short_history: dict[str, int] = field(default_factory=dict)
    missing_concepts: dict[str, list[str]] = field(default_factory=dict)
    missing_sector: list[str] = field(default_factory=list)
    missing_price: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Tickers solicitados: {len(self.requested)} | "
            f"incluidos: {len(self.included)} | "
            f"sin CIK: {len(self.unresolved_cik)} | "
            f"fallos de descarga: {len(self.failed_download)} | "
            f"historia corta: {len(self.short_history)} | "
            f"sin sector: {len(self.missing_sector)} | "
            f"sin precio: {len(self.missing_price)}"
        )


def set_sec_identity() -> None:
    """SEC rejects requests without a contact in the User-Agent.

    Read from the environment rather than hard-coded, so nobody's personal
    address ends up in a committed file — same choice as bootstrap_universe.py.
    """
    from edgar import set_identity

    contacto = os.environ.get("EDGAR_IDENTITY")
    if not contacto:
        raise RuntimeError(
            "Falta la variable de entorno EDGAR_IDENTITY. SEC exige un contacto "
            "en el User-Agent: EDGAR_IDENTITY='tu@correo.com'"
        )
    set_identity(contacto)


def _fetch_facts(ticker: str, periods: int) -> pd.DataFrame:
    """Raw edgartools call, isolated so tests can replace it without the network.

    Raises LookupError when the ticker has no CIK, which is a different problem
    from the network being down and is reported separately.
    """
    from edgar import Company

    try:
        company = Company(ticker)
    except Exception as exc:
        raise LookupError(f"sin CIK para {ticker}") from exc
    if company is None:
        raise LookupError(f"sin CIK para {ticker}")

    facts = company.get_facts()
    return facts.income_statement(periods=periods, annual=False, as_dataframe=True)


def _cache_path(cache_dir: Path, ticker: str, periods: int) -> Path:
    """Content-addressed cache name, one file per ticker.

    Uses md5 rather than the builtin hash(): Python randomises string hashing per
    process, so a builtin hash would miss on every fresh run and silently
    re-download the whole universe.

    One file per ticker because quarterly reports arrive staggered — a cache
    keyed on the whole universe would invalidate everything when one company files.
    """
    digest = hashlib.md5(f"{ticker}_{periods}".encode()).hexdigest()[:12]
    return cache_dir / f"facts_{digest}.parquet"


def _load_one(
    ticker: str, periods: int, cache_dir: Path, max_retries: int, refresh: bool
) -> tuple[pd.DataFrame | None, str | None]:
    """Return (facts, causa_del_fallo). Exactly one of the two is None."""
    path = _cache_path(cache_dir, ticker, periods)
    if path.exists() and not refresh:
        try:
            return pd.read_parquet(path), None
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a miss
            # rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    for intento in range(max_retries):
        try:
            frame = _fetch_facts(ticker, periods)
        except LookupError:
            return None, "unresolved_cik"
        except Exception:
            if intento == max_retries - 1:
                return None, "failed_download"
            time.sleep(2.0**intento)
            continue

        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        frame.to_parquet(tmp)
        tmp.replace(path)  # atomic rename: a reader never sees a partial file
        return frame, None

    return None, "failed_download"


def load_facts(
    tickers: list[str],
    periods: int = PERIODOS,
    cache_dir: Path | None = None,
    max_retries: int = 3,
    min_trimestres: int = MIN_TRIMESTRES,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], CoverageReport]:
    """Download raw XBRL facts per ticker, caching each to disk.

    A company with too few quarters is kept and marked, not dropped: its level
    KPIs are still valid even though no growth KPI can be computed.

    `refresh` re-downloads even when a cache entry exists. It defaults to False
    on purpose: quarterly reports arrive staggered, and a cache that refreshed
    itself would change the numbers between two runs without anyone asking. Like
    the universe snapshot, refreshing is a deliberate act.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    cobertura = CoverageReport(requested=list(tickers))
    hechos: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        frame, causa = _load_one(ticker, periods, cache_dir, max_retries, refresh)
        if causa == "unresolved_cik":
            cobertura.unresolved_cik.append(ticker)
            continue
        if causa == "failed_download":
            cobertura.failed_download.append(ticker)
            continue

        n = 0 if frame is None or frame.empty else len(frame.columns)
        if n < min_trimestres:
            cobertura.short_history[ticker] = n
        hechos[ticker] = frame
        cobertura.included.append(ticker)

    return hechos, cobertura
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_fetch.py -v
```

Esperado: 11 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py
git commit -m "feat: descarga de hechos XBRL con cache por ticker y cobertura"
```

---

### Task 7: KPIs de nivel — rentabilidad, solidez y calidad

Doce de los dieciséis. Los tres de crecimiento van en la Task 8 y los cuatro de valoración en la Task 9.

**Files:**
- Create: `fundamentals/kpis.py`
- Test: `tests/test_fundamentals_kpis.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_kpis.py`:

```python
import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import KPIS_NIVEL, compute_levels

# Empresa sintetica: cada cifra elegida para que los KPIs salgan redondos.
# Es el control negativo del motor — si un KPI no da su valor de aqui, el
# motor esta mal, y no hay forma de que un error se disimule en el promedio.
EMPRESA = {
    "ingresos": 1000.0,
    "coste_de_ventas": 600.0,          # margen bruto = 40%
    "beneficio_operativo": 200.0,      # margen operativo = 20%
    "beneficio_neto": 100.0,           # margen neto = 10%
    "depreciacion_amortizacion": 50.0,  # EBITDA = 250
    "gasto_por_intereses": 25.0,       # cobertura = 200/25 = 8
    "activos_totales": 2000.0,
    "activos_corrientes": 500.0,
    "pasivos_corrientes": 250.0,       # razon corriente = 2
    "patrimonio_neto": 500.0,          # ROE = 100/500 = 20%
    "deuda_total": 400.0,
    "efectivo": 150.0,                 # deuda neta = 250; /EBITDA 250 = 1.0
    "flujo_operativo": 180.0,
    "capex": 60.0,                     # FCF = 120; margen FCF = 12%; FCF/BN = 1.2
    "bpa_diluido": 2.0,
    "acciones_diluidas": 50.0,
}


def _lineas(**cambios) -> pd.DataFrame:
    datos = {**EMPRESA, **cambios}
    return pd.DataFrame({k: [v] for k, v in datos.items()}, index=["2025Q1"])


@pytest.mark.parametrize(
    "kpi, esperado",
    [
        ("margen_bruto", 0.40),
        ("margen_operativo", 0.20),
        ("margen_neto", 0.10),
        ("roe", 0.20),
        ("roic", 100.0 / 900.0),        # BN / (patrimonio + deuda - efectivo)
        ("deuda_neta_ebitda", 1.0),
        ("cobertura_intereses", 8.0),
        ("razon_corriente", 2.0),
        ("margen_fcf", 0.12),
        ("fcf_sobre_beneficio", 1.2),
    ],
)
def test_each_level_kpi_matches_its_hand_computed_value(kpi, esperado):
    resultado = compute_levels(_lineas())
    assert resultado.loc["2025Q1", kpi] == pytest.approx(esperado)


def test_every_declared_level_kpi_is_produced():
    """Un KPI declarado pero no calculado seria una columna vacia que nadie nota."""
    resultado = compute_levels(_lineas())
    assert sorted(resultado.columns) == sorted(KPIS_NIVEL)


def test_zero_equity_yields_missing_not_an_astronomical_roe():
    """El defecto exacto del estudio D: una guarda que no disparaba dio t = 3.6e16.

    Un ROE de 1e16 se ve como un dato extraordinario, no como una division por cero.
    """
    resultado = compute_levels(_lineas(patrimonio_neto=0.0))
    assert np.isnan(resultado.loc["2025Q1", "roe"])


def test_tiny_but_nonzero_equity_also_yields_missing():
    """Una guarda de '== 0' pasa por alto un patrimonio de 1e-12 y explota igual."""
    resultado = compute_levels(_lineas(patrimonio_neto=1e-12))
    assert np.isnan(resultado.loc["2025Q1", "roe"])


def test_zero_revenue_yields_missing_margins():
    resultado = compute_levels(_lineas(ingresos=0.0))
    assert np.isnan(resultado.loc["2025Q1", "margen_bruto"])
    assert np.isnan(resultado.loc["2025Q1", "margen_neto"])


def test_negative_ebitda_still_produces_a_number():
    """Un EBITDA negativo es informacion real, no un error: no debe suprimirse."""
    resultado = compute_levels(_lineas(beneficio_operativo=-500.0))
    assert resultado.loc["2025Q1", "deuda_neta_ebitda"] < 0


def test_zero_interest_expense_yields_missing_coverage():
    """Una empresa sin deuda no tiene cobertura infinita: no tiene cobertura."""
    resultado = compute_levels(_lineas(gasto_por_intereses=0.0))
    assert np.isnan(resultado.loc["2025Q1", "cobertura_intereses"])


def test_a_missing_input_line_yields_a_missing_kpi_not_a_zero():
    resultado = compute_levels(_lineas(coste_de_ventas=np.nan))
    assert np.isnan(resultado.loc["2025Q1", "margen_bruto"])
    assert resultado.loc["2025Q1", "margen_neto"] == pytest.approx(0.10)


def test_an_empty_frame_yields_an_empty_result_with_every_column():
    resultado = compute_levels(pd.DataFrame())
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_NIVEL)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.kpis'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/kpis.py`:

```python
import numpy as np
import pandas as pd

from fundamentals.concepts import LINEAS

# Below this, a denominator is noise and the quotient is an artefact rather than
# a measurement. Study D shipped a guard that only caught exact zeros and
# returned t = 3.6e16 for a near-constant series; the defect was invisible on
# the page and only showed up when the code was run.
_MIN_DENOMINADOR = 1e-6

KPIS_NIVEL = (
    "margen_bruto",
    "margen_operativo",
    "margen_neto",
    "roe",
    "roic",
    "deuda_neta_ebitda",
    "cobertura_intereses",
    "razon_corriente",
    "margen_fcf",
    "fcf_sobre_beneficio",
)


def _div(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """Divide, yielding NaN where the denominator is too small to mean anything.

    NaN rather than 0 or inf on purpose: a 0 reads as a real measurement of zero
    and an inf reads as an extraordinary company. Both are lies about a division
    that could not be performed.
    """
    num = pd.to_numeric(numerador, errors="coerce")
    den = pd.to_numeric(denominador, errors="coerce")
    return num / den.where(den.abs() >= _MIN_DENOMINADOR)


def _empty(columnas: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columnas), dtype="float64")


def compute_levels(lineas: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time KPIs: no KPI here needs a previous quarter."""
    if lineas.empty:
        return _empty(KPIS_NIVEL)

    l = lineas.reindex(columns=list(LINEAS))
    ebitda = l["beneficio_operativo"] + l["depreciacion_amortizacion"]
    deuda_neta = l["deuda_total"] - l["efectivo"]
    fcf = l["flujo_operativo"] - l["capex"]
    capital_invertido = l["patrimonio_neto"] + l["deuda_total"] - l["efectivo"]

    return pd.DataFrame(
        {
            "margen_bruto": _div(l["ingresos"] - l["coste_de_ventas"], l["ingresos"]),
            "margen_operativo": _div(l["beneficio_operativo"], l["ingresos"]),
            "margen_neto": _div(l["beneficio_neto"], l["ingresos"]),
            "roe": _div(l["beneficio_neto"], l["patrimonio_neto"]),
            "roic": _div(l["beneficio_neto"], capital_invertido),
            "deuda_neta_ebitda": _div(deuda_neta, ebitda),
            "cobertura_intereses": _div(l["beneficio_operativo"], l["gasto_por_intereses"]),
            "razon_corriente": _div(l["activos_corrientes"], l["pasivos_corrientes"]),
            "margen_fcf": _div(fcf, l["ingresos"]),
            "fcf_sobre_beneficio": _div(fcf, l["beneficio_neto"]),
        },
        index=lineas.index,
    )
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -v
```

Esperado: 18 passed (10 del parametrize + 8 sueltos)

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/kpis.py tests/test_fundamentals_kpis.py
git commit -m "feat: KPIs de nivel con guardas de division verificadas"
```

---

### Task 8: KPIs de crecimiento interanual

**Files:**
- Modify: `fundamentals/kpis.py`
- Modify: `tests/test_fundamentals_kpis.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_fundamentals_kpis.py`:

```python
from fundamentals.kpis import KPIS_CRECIMIENTO, compute_growth


def _serie(valores: list[float], columna: str) -> pd.DataFrame:
    """Trimestres consecutivos, del mas antiguo al mas reciente."""
    periodos = [f"T{i:02d}" for i in range(len(valores))]
    datos = {k: [v] * len(valores) for k, v in EMPRESA.items()}
    datos[columna] = valores
    return pd.DataFrame(datos, index=periodos)


def test_year_on_year_growth_compares_against_four_quarters_back():
    """Comparar contra el trimestre anterior mide estacionalidad, no crecimiento."""
    lineas = _serie([100.0, 999.0, 999.0, 999.0, 110.0], "ingresos")
    resultado = compute_growth(lineas)
    assert resultado.loc["T04", "crecimiento_ingresos"] == pytest.approx(0.10)


def test_the_first_four_quarters_have_no_growth_value():
    """Sin homologo del ano anterior no hay dato. Extrapolar seria inventarlo."""
    lineas = _serie([100.0] * 5, "ingresos")
    assert resultado_nan(compute_growth(lineas), ["T00", "T01", "T02", "T03"])


def resultado_nan(frame: pd.DataFrame, periodos: list[str]) -> bool:
    return all(np.isnan(frame.loc[p, "crecimiento_ingresos"]) for p in periodos)


def test_every_declared_growth_kpi_is_produced():
    lineas = _serie([100.0] * 8, "ingresos")
    assert sorted(compute_growth(lineas).columns) == sorted(KPIS_CRECIMIENTO)


def test_a_zero_base_yields_missing_not_infinite_growth():
    """Crecer desde 0 no es crecimiento infinito: es una magnitud indefinida."""
    lineas = _serie([0.0, 1.0, 1.0, 1.0, 50.0], "ingresos")
    resultado = compute_growth(lineas)
    assert np.isnan(resultado.loc["T04", "crecimiento_ingresos"])


def test_a_negative_base_yields_missing():
    """Con base negativa el signo del cociente se invierte y el numero enganna."""
    lineas = _serie([-100.0, 1.0, 1.0, 1.0, -50.0], "ingresos")
    resultado = compute_growth(lineas)
    assert np.isnan(resultado.loc["T04", "crecimiento_ingresos"])


def test_a_missing_intermediate_quarter_does_not_shift_the_comparison():
    """Si una fila ausente corriera el shift, se compararia contra el trimestre equivocado."""
    lineas = _serie([100.0, np.nan, 999.0, 999.0, 120.0], "ingresos")
    resultado = compute_growth(lineas)
    assert resultado.loc["T04", "crecimiento_ingresos"] == pytest.approx(0.20)


def test_growth_on_an_empty_frame_yields_every_column():
    resultado = compute_growth(pd.DataFrame())
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_CRECIMIENTO)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -k growth -v
```

Esperado: FAIL con `ImportError: cannot import name 'KPIS_CRECIMIENTO'`

- [ ] **Step 3: Implementar**

Añadir a `fundamentals/kpis.py`, después de `KPIS_NIVEL`:

```python
KPIS_CRECIMIENTO = (
    "crecimiento_ingresos",
    "crecimiento_bpa",
    "crecimiento_fcf",
)

_TRIMESTRES_POR_ANO = 4
```

Y al final del fichero:

```python
def _yoy(serie: pd.Series) -> pd.Series:
    """Year-on-year change against the same quarter last year.

    Compares four quarters back rather than one because a retailer's Q4 beats
    its Q3 every year: quarter-on-quarter measures seasonality, not growth.

    A base at or below zero yields NaN. Growth from zero is not infinite, and
    from a negative base the ratio flips sign and reports a collapse as a gain.
    """
    base = serie.shift(_TRIMESTRES_POR_ANO)
    return (serie - base) / base.where(base > _MIN_DENOMINADOR)


def compute_growth(lineas: pd.DataFrame) -> pd.DataFrame:
    """Growth KPIs. Assumes rows are consecutive quarters, oldest first.

    resolve_lines() sorts the periods, and every period is present as a row even
    when its values are missing, so shift(4) always lands on the same quarter of
    the previous year rather than sliding when a filing is incomplete.
    """
    if lineas.empty:
        return _empty(KPIS_CRECIMIENTO)

    l = lineas.reindex(columns=list(LINEAS))
    fcf = l["flujo_operativo"] - l["capex"]

    return pd.DataFrame(
        {
            "crecimiento_ingresos": _yoy(l["ingresos"]),
            "crecimiento_bpa": _yoy(l["bpa_diluido"]),
            "crecimiento_fcf": _yoy(fcf),
        },
        index=lineas.index,
    )
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -v
```

Esperado: 25 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/kpis.py tests/test_fundamentals_kpis.py
git commit -m "feat: crecimiento interanual sin extrapolar trimestres ausentes"
```

---

### Task 9: KPIs de valoración

Los cuatro que necesitan precio. El precio se toma en la fecha de presentación de cada trimestre, no hoy: mezclar el precio de hoy con fundamentales de hace tres años produce un múltiplo que nunca existió.

**Files:**
- Modify: `fundamentals/kpis.py`
- Modify: `tests/test_fundamentals_kpis.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_fundamentals_kpis.py`:

```python
from fundamentals.kpis import KPIS_VALORACION, compute_valuation


def test_each_valuation_kpi_matches_its_hand_computed_value():
    """Precio 20, 50 acciones -> capitalizacion 1000. EV = 1000 + 400 - 150 = 1250."""
    lineas = _lineas()
    precios = pd.Series([20.0], index=["2025Q1"])
    resultado = compute_valuation(lineas, precios)
    assert resultado.loc["2025Q1", "per"] == pytest.approx(10.0)        # 20 / 2.0
    assert resultado.loc["2025Q1", "precio_valor_libro"] == pytest.approx(2.0)   # 1000 / 500
    assert resultado.loc["2025Q1", "ev_ebitda"] == pytest.approx(5.0)   # 1250 / 250
    assert resultado.loc["2025Q1", "precio_fcf"] == pytest.approx(1000.0 / 120.0)


def test_every_declared_valuation_kpi_is_produced():
    resultado = compute_valuation(_lineas(), pd.Series([20.0], index=["2025Q1"]))
    assert sorted(resultado.columns) == sorted(KPIS_VALORACION)


def test_a_quarter_without_a_price_yields_missing_valuation():
    """El precio de hoy con fundamentales de hace tres anos da un multiplo inexistente."""
    resultado = compute_valuation(_lineas(), pd.Series(dtype="float64"))
    assert resultado["per"].isna().all()
    assert resultado["ev_ebitda"].isna().all()


def test_negative_earnings_yield_missing_pe():
    """Un PER negativo no ordena: -2 no es 'mas barato' que 10."""
    lineas = _lineas(bpa_diluido=-2.0)
    resultado = compute_valuation(lineas, pd.Series([20.0], index=["2025Q1"]))
    assert np.isnan(resultado.loc["2025Q1", "per"])


def test_negative_free_cash_flow_yields_missing_price_to_fcf():
    lineas = _lineas(flujo_operativo=10.0, capex=60.0)
    resultado = compute_valuation(lineas, pd.Series([20.0], index=["2025Q1"]))
    assert np.isnan(resultado.loc["2025Q1", "precio_fcf"])


def test_zero_shares_outstanding_yields_missing_not_a_huge_multiple():
    lineas = _lineas(acciones_diluidas=0.0)
    resultado = compute_valuation(lineas, pd.Series([20.0], index=["2025Q1"]))
    assert np.isnan(resultado.loc["2025Q1", "precio_valor_libro"])


def test_valuation_on_an_empty_frame_yields_every_column():
    resultado = compute_valuation(pd.DataFrame(), pd.Series(dtype="float64"))
    assert resultado.empty
    assert sorted(resultado.columns) == sorted(KPIS_VALORACION)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -k valuation -v
```

Esperado: FAIL con `ImportError: cannot import name 'KPIS_VALORACION'`

- [ ] **Step 3: Implementar**

Añadir a `fundamentals/kpis.py`, después de `KPIS_CRECIMIENTO`:

```python
KPIS_VALORACION = (
    "per",
    "ev_ebitda",
    "precio_fcf",
    "precio_valor_libro",
)

TODOS_LOS_KPIS = KPIS_NIVEL + KPIS_CRECIMIENTO + KPIS_VALORACION
```

Y al final del fichero:

```python
def _solo_positivo(serie: pd.Series) -> pd.Series:
    """Mask non-positive denominators for multiples.

    A P/E of -2 does not mean cheaper than 10, and a negative EV/EBITDA does not
    rank against a positive one. Leaving them in would corrupt any sort.
    """
    valores = pd.to_numeric(serie, errors="coerce")
    return valores.where(valores > _MIN_DENOMINADOR)


def compute_valuation(lineas: pd.DataFrame, precios: pd.Series) -> pd.DataFrame:
    """Market multiples, priced at each quarter's own filing date.

    `precios` is indexed by the same periods as `lineas`. Quarters with no price
    yield missing multiples rather than borrowing today's price: pairing a
    current price with three-year-old fundamentals invents a multiple that never
    traded.
    """
    if lineas.empty:
        return _empty(KPIS_VALORACION)

    l = lineas.reindex(columns=list(LINEAS))
    precio = pd.to_numeric(precios, errors="coerce").reindex(lineas.index)

    acciones = _solo_positivo(l["acciones_diluidas"])
    capitalizacion = precio * acciones
    ebitda = l["beneficio_operativo"] + l["depreciacion_amortizacion"]
    valor_empresa = capitalizacion + l["deuda_total"] - l["efectivo"]
    fcf = l["flujo_operativo"] - l["capex"]

    return pd.DataFrame(
        {
            "per": _div(precio, _solo_positivo(l["bpa_diluido"])),
            "ev_ebitda": _div(valor_empresa, _solo_positivo(ebitda)),
            "precio_fcf": _div(capitalizacion, _solo_positivo(fcf)),
            "precio_valor_libro": _div(capitalizacion, _solo_positivo(l["patrimonio_neto"])),
        },
        index=lineas.index,
    )
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_kpis.py -v
```

Esperado: 32 passed

- [ ] **Step 5: Commitear**

```bash
git add fundamentals/kpis.py tests/test_fundamentals_kpis.py
git commit -m "feat: multiples de valoracion al precio de su propio trimestre"
```

---

### Task 10: Orquestación

**Files:**
- Create: `fundamentals/run.py`
- Test: `tests/test_fundamentals_run.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_run.py`:

```python
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import build_panel


def _facts(ticker: str, n: int = 12) -> pd.DataFrame:
    periodos = [f"2023Q{i}" for i in range(n)]
    base = {
        "Revenues": 1000.0,
        "CostOfRevenue": 600.0,
        "OperatingIncomeLoss": 200.0,
        "NetIncomeLoss": 100.0,
        "EarningsPerShareDiluted": 2.0,
        "DepreciationDepletionAndAmortization": 50.0,
        "InterestExpense": 25.0,
        "Assets": 2000.0,
        "AssetsCurrent": 500.0,
        "LiabilitiesCurrent": 250.0,
        "StockholdersEquity": 500.0,
        "LongTermDebt": 400.0,
        "CashAndCashEquivalentsAtCarryingValue": 150.0,
        "NetCashProvidedByUsedInOperatingActivities": 180.0,
        "PaymentsToAcquirePropertyPlantAndEquipment": 60.0,
        "WeightedAverageNumberOfDilutedSharesOutstanding": 50.0,
    }
    return pd.DataFrame({p: list(base.values()) for p in periodos}, index=list(base))


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def sectores(tmp_path: Path) -> Path:
    ruta = tmp_path / "sectores.csv"
    pd.DataFrame(
        {"ticker": ["AAA", "BBB", "CCC"], "sector_gics": ["Tec"] * 3}
    ).to_csv(ruta, index=False)
    return ruta


def test_the_panel_carries_every_kpi_for_every_ticker(cache_dir, sectores):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, meta, cobertura = build_panel(
            ["AAA", "BBB", "CCC"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert sorted(panel.columns) == sorted(TODOS_LOS_KPIS)
    assert set(panel.index.get_level_values("ticker")) == {"AAA", "BBB", "CCC"}


def test_the_panel_is_indexed_by_ticker_and_period(cache_dir, sectores):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, _ = build_panel(["AAA"], cache_dir=cache_dir, sectores_path=sectores)
    assert panel.index.names == ["ticker", "periodo"]


def test_metadata_carries_the_sector_for_each_ticker(cache_dir, sectores):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        _, meta, _ = build_panel(["AAA"], cache_dir=cache_dir, sectores_path=sectores)
    assert meta.loc["AAA", "sector_gics"] == "Tec"


def test_a_ticker_outside_the_index_keeps_its_kpis_and_loses_only_the_zscore(cache_dir, sectores):
    """Decision de diseno: fuera del S&P 500 no hay GICS, pero los KPIs valen igual."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, meta, cobertura = build_panel(
            ["AAA", "BBB", "CCC", "ZZZ"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert not np.isnan(panel.loc[("ZZZ", "2023Q5"), "margen_bruto"])
    assert "ZZZ" in cobertura.missing_sector
    assert pd.isna(meta.loc["ZZZ", "sector_gics"])


def test_zscores_are_returned_alongside_the_raw_kpis(cache_dir, sectores):
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t, p: _facts(t)), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, _ = build_panel(
            ["AAA", "BBB", "CCC"], cache_dir=cache_dir, sectores_path=sectores, con_zscore=True
        )
    assert "z_margen_bruto" in panel.columns


def test_missing_concepts_are_reported_per_ticker(cache_dir, sectores):
    """Una empresa a la que le falta un renglon entra al panel marcada, no se elimina."""
    def sin_capex(ticker, periods):
        facts = _facts(ticker)
        return facts.drop(index=["PaymentsToAcquirePropertyPlantAndEquipment"])

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_capex), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, cobertura = build_panel(["AAA"], cache_dir=cache_dir, sectores_path=sectores)
    assert "capex" in cobertura.missing_concepts["AAA"]
    assert "AAA" in panel.index.get_level_values("ticker")


def test_the_price_is_taken_after_the_results_became_public():
    """El defecto de look-ahead: los resultados de un trimestre no son publicos
    el dia que el trimestre cierra, sino cuando se presenta el 10-Q semanas
    despues. Cotizar el multiplo al cierre del trimestre usa informacion que el
    mercado no tenia."""
    from fundamentals.run import DIAS_HASTA_PRESENTACION, _precios_por_periodo

    fechas = pd.bdate_range("2024-01-01", periods=400)
    panel = pd.DataFrame(
        {("Close", "AAA"): range(len(fechas))},
        index=fechas,
        columns=pd.MultiIndex.from_tuples([("Close", "AAA")]),
    )

    with patch("research.loader.load_ohlcv", return_value=(panel, None)):
        precios = _precios_por_periodo("AAA", ["2024-03-31"])

    cierre_trimestre = pd.Timestamp("2024-03-31")
    publicacion = cierre_trimestre + pd.Timedelta(days=DIAS_HASTA_PRESENTACION)
    serie = panel[("Close", "AAA")].dropna()
    assert precios.loc["2024-03-31"] == serie.asof(publicacion)
    assert precios.loc["2024-03-31"] != serie.asof(cierre_trimestre)


def test_a_failed_ticker_does_not_abort_the_whole_run(cache_dir, sectores):
    """Una empresa rota no puede costar el universo entero."""
    def una_falla(ticker, periods):
        if ticker == "BBB":
            raise LookupError("sin CIK")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=una_falla), \
         patch("fundamentals.run._precios_por_periodo", return_value=pd.Series(dtype="float64")):
        panel, _, cobertura = build_panel(
            ["AAA", "BBB", "CCC"], cache_dir=cache_dir, sectores_path=sectores
        )
    assert cobertura.unresolved_cik == ["BBB"]
    assert set(panel.index.get_level_values("ticker")) == {"AAA", "CCC"}
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

```bash
python -m pytest tests/test_fundamentals_run.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.run'`

- [ ] **Step 3: Implementar**

Crear `fundamentals/run.py`:

```python
from pathlib import Path

import pandas as pd

from fundamentals.concepts import resolve_lines
from fundamentals.fetch import PERIODOS, CoverageReport, load_facts
from fundamentals.kpis import TODOS_LOS_KPIS, compute_growth, compute_levels, compute_valuation
from fundamentals.sectors import load_sectors, zscore_within_sector
from fundamentals.universe import resolve


# A quarter's results are not public on the day the quarter ends: the 10-Q lands
# weeks later. Pricing a multiple at period end would use figures the market did
# not have, which is look-ahead — the family of defect study D found seven times.
#
# 45 days is just past the SEC deadline for large accelerated filers (40 days),
# so it lands at or after the real filing for almost every company in the index.
# Erring late is the safe direction: a price taken after publication is merely
# stale, whereas one taken before is information nobody had.
#
# If Task 1 found that edgartools exposes the real filing date, use it instead
# and delete this constant.
DIAS_HASTA_PRESENTACION = 45


def _precios_por_periodo(ticker: str, periodos: list[str]) -> pd.Series:
    """Closing price at the date each quarter's results became public.

    Isolated so tests can replace it without touching the network, and so the
    price source stays swappable — it reuses research.loader today.
    """
    from research.loader import load_ohlcv

    if not periodos:
        return pd.Series(dtype="float64")

    cierre_trimestre = pd.to_datetime(pd.Series(periodos), errors="coerce")
    publicacion = cierre_trimestre + pd.Timedelta(days=DIAS_HASTA_PRESENTACION)
    if publicacion.isna().all():
        return pd.Series(float("nan"), index=periodos, dtype="float64")

    panel, _ = load_ohlcv(
        [ticker],
        start=(publicacion.min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(publicacion.max() + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    if panel.empty or ("Close", ticker) not in panel.columns:
        return pd.Series(float("nan"), index=periodos, dtype="float64")

    cierres = panel[("Close", ticker)].dropna()
    # asof: the last close at or before publication, so a date falling on a
    # weekend or holiday takes the previous session rather than nothing.
    valores = [cierres.asof(f) if pd.notna(f) else float("nan") for f in publicacion]
    return pd.Series(valores, index=periodos, dtype="float64")


def build_panel(
    source: str | list[str] = "sp500",
    periods: int = PERIODOS,
    cache_dir: Path | None = None,
    sectores_path: Path | None = None,
    con_zscore: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, CoverageReport]:
    """Build the KPI panel for a universe.

    Returns (panel, metadatos, cobertura):
      - panel: indexed by (ticker, periodo), one column per KPI
      - metadatos: indexed by ticker, carrying sector_gics
      - cobertura: every exclusion, counted and attributed

    A company that fails is recorded and skipped; it never aborts the run.
    """
    tickers = resolve(source)
    hechos, cobertura = load_facts(tickers, periods=periods, cache_dir=cache_dir)
    sectores = load_sectors(sectores_path)

    trozos: list[pd.DataFrame] = []
    filas_meta: list[dict] = []

    for ticker, facts in hechos.items():
        lineas, ausentes = resolve_lines(facts)
        if ausentes:
            cobertura.missing_concepts[ticker] = ausentes
        if lineas.empty:
            continue

        precios = _precios_por_periodo(ticker, list(lineas.index))
        if precios.isna().all():
            cobertura.missing_price.append(ticker)

        kpis = pd.concat(
            [
                compute_levels(lineas),
                compute_growth(lineas),
                compute_valuation(lineas, precios),
            ],
            axis=1,
        ).reindex(columns=list(TODOS_LOS_KPIS))

        kpis.index = pd.MultiIndex.from_product(
            [[ticker], lineas.index], names=["ticker", "periodo"]
        )
        trozos.append(kpis)

        sector = sectores.get(ticker)
        if sector is None:
            cobertura.missing_sector.append(ticker)
        filas_meta.append({"ticker": ticker, "sector_gics": sector})

    if not trozos:
        vacio = pd.DataFrame(columns=list(TODOS_LOS_KPIS), dtype="float64")
        return vacio, pd.DataFrame(columns=["sector_gics"]), cobertura

    panel = pd.concat(trozos).sort_index()
    metadatos = pd.DataFrame(filas_meta).set_index("ticker")

    if con_zscore:
        panel = _anadir_zscores(panel, metadatos)

    return panel, metadatos, cobertura


def _anadir_zscores(panel: pd.DataFrame, metadatos: pd.DataFrame) -> pd.DataFrame:
    """Score each period against sector peers *within that same period*.

    Scoring across periods would rank a company against its own past, which
    measures the business cycle rather than its standing among peers.
    """
    piezas = []
    for periodo, grupo in panel.groupby(level="periodo"):
        tickers = grupo.index.get_level_values("ticker")
        sectores = metadatos["sector_gics"].reindex(tickers)
        sectores.index = grupo.index
        z = zscore_within_sector(grupo, sectores)
        piezas.append(z.add_prefix("z_"))

    return pd.concat([panel, pd.concat(piezas).sort_index()], axis=1)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
python -m pytest tests/test_fundamentals_run.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Ejecutar la suite entera**

```bash
python -m pytest tests/ -q
```

Esperado: los 290 anteriores más los nuevos, todos pasando. Si algo de `research/` o de la app se rompió, pararse aquí: este paquete no debía tocarlos.

- [ ] **Step 6: Commitear**

```bash
git add fundamentals/run.py tests/test_fundamentals_run.py
git commit -m "feat: orquestacion del motor de fundamentales"
```

---

### Task 11: Contraste contra fuente externa

Estándar establecido en el proyecto: implementación nativa contrastada contra una referencia externa, en un test que se omite solo si la librería no está instalada. Ya se usa con Ledoit-Wolf/scikit-learn y con RSI/pandas-ta-classic.

**Files:**
- Create: `tests/test_fundamentals_contraste.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_fundamentals_contraste.py`:

```python
"""Contrasta los KPIs nativos contra los que publica yfinance.

Se omite entero si yfinance no esta instalado o si la red no responde, igual que
el contraste de Ledoit-Wolf contra scikit-learn. Marcado como test de red: no
corre en la suite normal.
"""
import pytest

pytest.importorskip("yfinance")

pytestmark = pytest.mark.red


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "KO"])
def test_native_margins_agree_with_yfinance(ticker):
    """Un margen que difiere mucho de la referencia significa que el renglon
    XBRL elegido no es el que la empresa considera sus ingresos."""
    import os

    import yfinance as yf

    from fundamentals.run import build_panel

    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("Falta EDGAR_IDENTITY")

    from fundamentals.fetch import set_sec_identity

    set_sec_identity()

    panel, _, _ = build_panel([ticker], periods=8)
    nuestro = panel["margen_bruto"].dropna()
    if nuestro.empty:
        pytest.skip(f"Sin margen bruto calculado para {ticker}")

    referencia = yf.Ticker(ticker).info.get("grossMargins")
    if referencia is None:
        pytest.skip(f"yfinance no publica grossMargins para {ticker}")

    # Tolerancia amplia a proposito: yfinance informa sobre doce meses moviles y
    # nosotros por trimestre, asi que no tienen por que coincidir al decimal. Lo
    # que este test atrapa es haber elegido el renglon XBRL equivocado, que
    # produce discrepancias de decenas de puntos, no de decimas.
    assert abs(nuestro.iloc[-1] - referencia) < 0.15
```

- [ ] **Step 2: Registrar el marcador**

Crear `pytest.ini` en la raíz si no existe, o añadir la sección si ya existe:

```ini
[pytest]
markers =
    red: test que necesita red y credenciales; excluido de la suite normal
```

- [ ] **Step 3: Verificar que la suite normal lo excluye**

```bash
python -m pytest tests/ -q -m "not red"
```

Esperado: pasa sin intentar ninguna conexión.

- [ ] **Step 4: Ejecutarlo a mano una vez, con red**

```bash
EDGAR_IDENTITY="tu@correo.com" python -m pytest tests/test_fundamentals_contraste.py -v -m red
```

Esperado: pasa, o se omite con una razón declarada. **Si falla con una discrepancia grande, parar**: significa que la cadena de conceptos de `ingresos` o `coste_de_ventas` está eligiendo el renglón equivocado, y hay que corregir `concepts.py` antes de seguir.

- [ ] **Step 5: Commitear**

```bash
git add tests/test_fundamentals_contraste.py pytest.ini
git commit -m "test: contraste de KPIs nativos contra yfinance"
```

---

### Task 12: Corrida real y documentación

**Files:**
- Modify: `CONTEXTO.md`
- Modify: `.gitignore`

- [ ] **Step 1: Excluir la caché del control de versiones**

Añadir a `.gitignore`:

```
fundamentals/.cache/
```

- [ ] **Step 2: Correr el motor sobre el S&P 500 entero**

```bash
EDGAR_IDENTITY="tu@correo.com" python -c "from fundamentals.fetch import set_sec_identity; set_sec_identity(); from fundamentals.run import build_panel; p, m, c = build_panel('sp500', con_zscore=True); print(c.summary()); print(p.shape); print(p.notna().mean().sort_values().to_string())"
```

Anotar el resumen de cobertura y la tasa de datos presentes por KPI. **Cualquier KPI por debajo del 50% de cobertura indica una cadena de conceptos incompleta en `concepts.py`**, no un fallo de las empresas: hay que añadir la etiqueta que falta y volver a correr.

- [ ] **Step 3: Correr por segunda vez y comprobar que usa caché**

```bash
EDGAR_IDENTITY="tu@correo.com" python -c "import time; t=time.time(); from fundamentals.fetch import set_sec_identity; set_sec_identity(); from fundamentals.run import build_panel; build_panel('sp500'); print(f'{time.time()-t:.1f}s')"
```

Esperado: mucho más rápido que la primera corrida. Si tarda lo mismo, la caché no está funcionando y hay que revisar `_cache_path`.

- [ ] **Step 4: Actualizar CONTEXTO.md**

En la tabla de sub-proyectos, cambiar la fila A a `✅ terminado` y B a `pendiente — siguiente`.

Borrar entera la sección `## ⚠️ Lo primero: hay trabajo sin commitear que se puede perder`: ese trabajo está commiteado desde `0a84a59` y `1e2e970`, y la advertencia ya sólo confunde.

Añadir bajo "Qué hay en el repo":

```markdown
### El motor de fundamentales
```
fundamentals/
├── universe.py     resolución de universo (S&P 500 o lista arbitraria)
├── concepts.py     cadenas de conceptos XBRL con alternativas por emisor
├── fetch.py        descarga con caché por ticker y reporte de cobertura
├── kpis.py         los 16 KPIs, con guardas de división verificadas
├── sectors.py      GICS y z-score sectorial
└── run.py          orquestación
scripts/bootstrap_sectors.py    regenera la tabla de sectores
```

Necesita `EDGAR_IDENTITY` en el entorno: SEC exige un contacto en el User-Agent.
```

Añadir a la lista de comandos:

```bash
EDGAR_IDENTITY="tu@correo.com" python -m pytest tests/ -q -m red   # contraste con red
```

Y en "Decisiones ya tomadas", añadir:

```markdown
- **GICS, no SIC, para agrupar sectores.** Medido, no argumentado: sobre las 502
  empresas del S&P 500 con SIC resuelto, SIC de 4 dígitos deja 87 solas en su
  grupo, donde el z-score vale 0 por construcción. GICS Sector no deja ninguna.
  Detalle en `docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md`.
- **El snapshot de universo de D no se regenera.** Los sectores viven en
  `fundamentals/data/sectores_2026-08-10.csv`, aparte, para no alterar la
  membresía contra la que reproduce el estudio.
```

- [ ] **Step 5: Verificar la suite entera antes de cerrar**

```bash
python -m pytest tests/ -q -m "not red"
```

Esperado: todo verde. Anotar el número final de tests.

- [ ] **Step 6: Commitear**

```bash
git add CONTEXTO.md .gitignore
git commit -m "docs: motor de fundamentales terminado, sub-proyecto A cerrado"
```

---

## Verificación final

- [ ] `python -m pytest tests/ -q -m "not red"` pasa entero
- [ ] `git status --porcelain research/data/` no devuelve nada — el snapshot de D quedó intacto
- [ ] La segunda corrida del motor es notablemente más rápida que la primera
- [ ] Ningún KPI está por debajo del 50% de cobertura sobre el S&P 500
- [ ] `CONTEXTO.md` ya no contiene la advertencia obsoleta de trabajo sin commitear
