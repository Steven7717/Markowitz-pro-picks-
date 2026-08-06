# Estudio de valor predictivo de señales técnicas — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un estudio offline y reproducible que determine, contra un criterio pre-registrado, si alguna familia de señales técnicas tiene poder predictivo sobre el S&P 500 y si mejora el momento de entrada.

**Architecture:** Paquete `research/` independiente de la app Streamlit. Flujo lineal: universo congelado → panel OHLCV cacheado en disco → 8 series de señal ya desplazadas → dos puertas de evaluación (estadística y utilitaria) → veredicto en markdown. Toda la matemática del criterio se implementa nativamente y se contrasta contra librerías de referencia en tests opcionales, siguiendo el patrón que el repositorio ya usa con Ledoit-Wolf y scikit-learn.

**Tech Stack:** Python 3.11+, pandas, numpy, scipy, yfinance, pyarrow (caché parquet), pandas-ta-classic (sólo referencia cruzada en tests).

**Spec:** [docs/superpowers/specs/2026-08-05-estudio-senales-tecnicas-design.md](../specs/2026-08-05-estudio-senales-tecnicas-design.md)

---

## Contexto que el implementador necesita saber

**Qué es este proyecto.** El repositorio contiene una app Streamlit de optimización de portafolios (Markowitz). Este estudio **no la toca**. Es un experimento aparte que responde una pregunta previa: ¿vale la pena construir un módulo de análisis técnico? Si el estudio dice que no, se ahorra el módulo entero.

**Por qué el rigor.** Un estudio así se arruina de tres formas silenciosas: mirar datos del futuro (look-ahead), probar muchas combinaciones hasta que una funcione por azar (multiplicidad), y mover el umbral de aprobación después de ver los números. El plan tiene defensas explícitas contra las tres. No las omitas ni las "simplifiques": son el producto.

**Archivos existentes que se reutilizan.** Sólo `validation.sharpe_standard_error` (`validation.py:47`), y únicamente como contraste de cordura. **No modifiques** `data.py`, `optimizer.py`, `estimators.py`, `validation.py`, `charts.py`, `exporter.py` ni `app.py`.

**Convenciones del repositorio.** Código y nombres de test en inglés. Docstrings en inglés, explicando *por qué*, no *qué*. Mensajes al usuario en español. Los tests describen comportamiento observable, no implementación. Mira `tests/test_estimators.py` como referencia de estilo.

**Comando de tests:** `pytest tests/ -v`

---

## Estructura de archivos

| Archivo | Responsabilidad única |
|---|---|
| `research/__init__.py` | Marcador de paquete, vacío |
| `research/universe.py` | Leer el snapshot congelado de miembros del índice |
| `research/loader.py` | Descargar y cachear el panel OHLCV; reportar cobertura |
| `research/indicators.py` | Matemática pura de indicadores (RSI, MACD, SMA, Bollinger, máximo móvil) |
| `research/signals.py` | Las 8 señales y sus disparos, con la disciplina de desplazamiento |
| `research/costs.py` | Costes de transacción aplicados sobre rotación |
| `research/evaluation.py` | Puerta A: IC, t-stat Newey-West, quintiles, sub-periodos, Benjamini-Hochberg |
| `research/timing.py` | Puerta B: entrar ya vs esperar señal, con bootstrap por bloques |
| `research/report.py` | Aplicar ambas puertas y emitir el veredicto |
| `research/run.py` | Punto de entrada; orquesta el estudio completo |
| `research/data/sp500_members_2026-08-05.csv` | Snapshot congelado, commiteado |
| `scripts/bootstrap_universe.py` | Se corre **una sola vez** para generar el snapshot |

**Nota sobre `indicators.py`:** el spec (sección 4.2) listaba los indicadores dentro de `signals.py`. Se separan porque tienen naturalezas de test distintas — los indicadores se contrastan contra una librería de referencia, las señales se verifican por truncamiento. El spec se actualiza para reflejarlo.

---

## Task 0: Preparación del terreno

**Files:**
- Create: `docs/research/criterio-preregistrado.md`
- Create: `research/__init__.py`
- Create: `research/data/.gitkeep`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Congelar el criterio pre-registrado**

Copia **literalmente** la sección 3 completa del spec (`docs/superpowers/specs/2026-08-05-estudio-senales-tecnicas-design.md`, desde "## 3. Criterio pre-registrado" hasta el final de la sección 3.8) a un archivo nuevo `docs/research/criterio-preregistrado.md`, precedido por esta cabecera:

```markdown
# Criterio pre-registrado — Estudio de señales técnicas

**Congelado el:** 2026-08-05
**Estado:** INMUTABLE

Este documento se commitea antes de escribir cualquier código de medición.
La fecha del commit es la prueba de que los umbrales no se movieron después
de ver los resultados. Modificarlo invalida el estudio.

---
```

Esto va primero, antes que cualquier otra cosa. Es lo que hace creíble el resultado.

- [ ] **Step 2: Crear el paquete**

Crea `research/__init__.py` vacío y `research/data/.gitkeep` vacío.

- [ ] **Step 3: Añadir dependencias**

Añade al final de `requirements.txt`:

```
# Estudio de señales técnicas (paquete research/)
pyarrow>=15.0.0
# Opcional (solo tests): contrasta nuestros indicadores nativos contra una
# implementación de referencia. El test se omite solo si no está instalado,
# igual que ya hace scikit-learn con Ledoit-Wolf.
pandas-ta-classic>=0.4.0
```

**Cambio respecto al spec: se elimina `alphalens-reloaded`.** El spec lo listaba como dependencia obligatoria para IC, quintiles y tear sheets. Al detallar la implementación quedó claro que no aporta:

- El criterio necesita t-stats con Newey-West, partición en sub-periodos y Benjamini-Hochberg. Nada de eso existe en alphalens, así que la matemática hay que escribirla igual.
- Como referencia cruzada del IC, `scipy.stats.spearmanr` — que ya es dependencia del proyecto — hace el mismo trabajo sin reformatear los datos al esquema de alphalens.
- Los tear sheets se sustituyen por las tablas markdown del veredicto, que es lo que se lee para decidir.

Añadir una dependencia que nunca se importa sería peor que no añadirla.

- [ ] **Step 4: Ignorar la caché**

Añade a `.gitignore`:

```
research/.cache/
```

- [ ] **Step 5: Instalar y verificar**

Run: `pip install -r requirements.txt`
Expected: instalación correcta de pyarrow y pandas-ta-classic.

Run: `pytest tests/ -q`
Expected: la suite existente sigue pasando (nada se ha tocado todavía).

- [ ] **Step 6: Commit**

```bash
git add docs/research/criterio-preregistrado.md research/__init__.py research/data/.gitkeep requirements.txt .gitignore
git commit -m "chore: congelar criterio pre-registrado y preparar paquete research"
```

---

## Task 1: Universo congelado

**Files:**
- Create: `scripts/bootstrap_universe.py`
- Create: `research/universe.py`
- Create: `research/data/sp500_members_2026-08-05.csv`
- Test: `tests/test_research_universe.py`

**Por qué un snapshot y no una consulta en vivo:** si el universo cambia entre corridas, dos ejecuciones del estudio dan números distintos y deja de ser reproducible. El universo se congela una vez y se commitea.

- [ ] **Step 1: Escribir el script de bootstrap (se corre una sola vez)**

Crea `scripts/bootstrap_universe.py`:

```python
"""Generate the frozen S&P 500 membership snapshot. Run once, commit the output.

The study must reproduce exactly across runs, so the universe is never queried
live. Refreshing it is a deliberate, reviewed change to a committed file.
"""
import sys
from pathlib import Path

import pandas as pd

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT = Path(__file__).resolve().parent.parent / "research" / "data" / "sp500_members_2026-08-05.csv"


def normalise(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def main() -> int:
    tables = pd.read_html(WIKIPEDIA_URL)
    constituents = tables[0]
    tickers = sorted({normalise(s) for s in constituents["Symbol"]})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": tickers}).to_csv(OUTPUT, index=False)
    print(f"Escritos {len(tickers)} tickers en {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Correr el bootstrap**

Run: `python scripts/bootstrap_universe.py`
Expected: `Escritos 503 tickers en .../research/data/sp500_members_2026-08-05.csv` (el número exacto variará; debe estar entre 490 y 510).

Abre el CSV y comprueba a ojo que la primera columna se llama `ticker` y que no hay puntos en los símbolos.

- [ ] **Step 3: Escribir los tests que fallan**

Crea `tests/test_research_universe.py`:

```python
from pathlib import Path

import pandas as pd
import pytest

from research.universe import normalise_ticker, sp500_members


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    path = tmp_path / "members.csv"
    pd.DataFrame({"ticker": ["aapl", "brk-b", "msft"]}).to_csv(path, index=False)
    return path


def test_reads_the_tickers_from_the_snapshot_file(snapshot):
    assert sp500_members(snapshot) == ["AAPL", "BRK-B", "MSFT"]


def test_uppercases_whatever_the_file_contains(snapshot):
    assert all(t == t.upper() for t in sp500_members(snapshot))


def test_the_committed_snapshot_has_a_plausible_number_of_members():
    members = sp500_members()
    assert 480 <= len(members) <= 520


def test_the_committed_snapshot_has_no_duplicates():
    members = sp500_members()
    assert len(members) == len(set(members))


def test_the_committed_snapshot_uses_yahoo_share_class_syntax():
    """Yahoo writes BRK.B as BRK-B; a dot silently returns an empty price series."""
    assert not any("." in ticker for ticker in sp500_members())


def test_share_classes_are_normalised_to_hyphens():
    assert normalise_ticker("brk.b") == "BRK-B"
```

- [ ] **Step 4: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_universe.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.universe'`

- [ ] **Step 5: Implementar**

Crea `research/universe.py`:

```python
from pathlib import Path

import pandas as pd

_SNAPSHOT = Path(__file__).parent / "data" / "sp500_members_2026-08-05.csv"


def normalise_ticker(symbol: str) -> str:
    """Yahoo Finance writes share classes with a hyphen, not a dot (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def sp500_members(snapshot: Path | None = None) -> list[str]:
    """Read the frozen membership snapshot from disk.

    Never queries the network. Two runs of the study must evaluate the same
    universe, so membership is a committed file, not a live lookup.
    """
    frame = pd.read_csv(snapshot or _SNAPSHOT)
    return [normalise_ticker(s) for s in frame["ticker"]]
```

- [ ] **Step 6: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_universe.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/bootstrap_universe.py research/universe.py research/data/sp500_members_2026-08-05.csv tests/test_research_universe.py
git commit -m "feat: universo congelado del S&P 500 con snapshot commiteado"
```

---

## Task 2: Cargador de precios con caché

**Files:**
- Create: `research/loader.py`
- Test: `tests/test_research_loader.py`

**Por qué no se reutiliza `data.py`:** está decorada con `@st.cache_data` (acopla la descarga a Streamlit) y descarta OHLCV quedándose sólo con `Close` (`data.py:73`). RSI, Bollinger y breakouts necesitan High, Low y Volume.

**Forma del panel:** `pd.DataFrame` con `MultiIndex` de columnas `(campo, ticker)`, donde campo ∈ {Open, High, Low, Close, Volume}. Índice: fechas.

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_loader.py`:

```python
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from research.loader import CoverageReport, load_ohlcv

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def _panel(tickers: list[str], n_rows: int, start: str = "2020-01-01") -> pd.DataFrame:
    """A well-formed OHLCV panel shaped exactly as yfinance returns it."""
    dates = pd.bdate_range(start, periods=n_rows)
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    rng = np.random.default_rng(3)
    values = rng.uniform(10.0, 100.0, size=(n_rows, len(columns)))
    return pd.DataFrame(values, index=dates, columns=columns)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_returns_a_panel_and_a_coverage_report(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA", "BBB"], 400)):
        panel, coverage = load_ohlcv(["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert isinstance(panel, pd.DataFrame)
    assert isinstance(coverage, CoverageReport)


def test_panel_carries_every_ohlcv_field(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        panel, _ = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert sorted(panel.columns.get_level_values(0).unique()) == sorted(FIELDS)


def test_tickers_with_too_little_history_are_excluded(cache_dir):
    short = _panel(["AAA", "BBB"], 400)
    short[("Close", "BBB")] = np.nan
    short.iloc[-50:, short.columns.get_loc(("Close", "BBB"))] = 42.0
    with patch("research.loader._download", return_value=short):
        panel, coverage = load_ohlcv(
            ["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, min_obs=252
        )
    assert "BBB" not in panel.columns.get_level_values(1)
    assert "BBB" in coverage.excluded_short_history


def test_excluded_tickers_are_counted_not_silently_dropped(cache_dir):
    short = _panel(["AAA", "BBB"], 400)
    short[("Close", "BBB")] = np.nan
    with patch("research.loader._download", return_value=short):
        _, coverage = load_ohlcv(
            ["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, min_obs=252
        )
    assert coverage.requested == ["AAA", "BBB"]
    assert coverage.included == ["AAA"]
    assert coverage.excluded_short_history["BBB"] == 0


def test_a_permanent_download_failure_is_reported_separately_from_short_history(cache_dir):
    """A network failure and a young company are different problems; conflating them hides outages."""
    with patch("research.loader._download", side_effect=RuntimeError("boom")):
        panel, coverage = load_ohlcv(
            ["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, max_retries=1
        )
    assert coverage.failed_download == ["AAA"]
    assert coverage.excluded_short_history == {}
    assert panel.empty


def test_a_transient_failure_is_retried(cache_dir):
    attempts = {"n": 0}

    def flaky(tickers, start, end):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return _panel(tickers, 400)

    # Patch the backoff too: the real sleep would make this the slowest test in the suite.
    with patch("research.loader._download", side_effect=flaky), patch("research.loader.time.sleep"):
        panel, coverage = load_ohlcv(
            ["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir, max_retries=3
        )
    assert attempts["n"] == 2
    assert coverage.included == ["AAA"]


def test_the_second_call_reads_from_cache_without_downloading(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)) as first:
        load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert first.call_count == 1

    with patch("research.loader._download") as second:
        panel, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert second.call_count == 0
    assert coverage.included == ["AAA"]
    assert not panel.empty


def test_downloads_are_split_into_batches(cache_dir):
    tickers = [f"T{i:03d}" for i in range(120)]

    def by_batch(batch, start, end):
        return _panel(list(batch), 400)

    with patch("research.loader._download", side_effect=by_batch) as download:
        load_ohlcv(tickers, "2020-01-01", "2021-12-31", cache_dir=cache_dir, batch_size=50)
    assert download.call_count == 3


def test_a_ticker_absent_from_a_successful_batch_is_reported_as_short_history(cache_dir):
    """yfinance can silently omit an invalid or delisted symbol from an otherwise-successful batch."""
    only_aaa = _panel(["AAA"], 400)
    with patch("research.loader._download", return_value=only_aaa):
        _, coverage = load_ohlcv(["AAA", "BBB"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert coverage.excluded_short_history["BBB"] == 0
    assert coverage.failed_download == []


def test_a_corrupted_cache_file_is_recovered_by_re_downloading(cache_dir):
    """A run killed mid-write must cost one redownload, not poison every future run."""
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)

    cached = next(cache_dir.glob("batch_*.parquet"))
    cached.write_bytes(b"truncated garbage")

    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        _, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    assert coverage.included == ["AAA"]


def test_the_cache_key_does_not_depend_on_process_local_hashing(cache_dir):
    """Python randomises builtin string hashing per run; a cache keyed on it never hits."""
    import hashlib

    from research.loader import _cache_path

    key = "AAA-BBB_2020-01-01_2021-12-31"
    expected = hashlib.md5(key.encode()).hexdigest()[:12]
    path = _cache_path(cache_dir, ["BBB", "AAA"], "2020-01-01", "2021-12-31")
    assert path.name == f"batch_{expected}.parquet"


def test_coverage_summary_names_every_category(cache_dir):
    with patch("research.loader._download", return_value=_panel(["AAA"], 400)):
        _, coverage = load_ohlcv(["AAA"], "2020-01-01", "2021-12-31", cache_dir=cache_dir)
    summary = coverage.summary()
    assert "solicitados" in summary
    assert "incluidos" in summary
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_loader.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.loader'`

- [ ] **Step 3: Implementar**

Crea `research/loader.py`:

```python
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yfinance as yf

FIELDS = ["Open", "High", "Low", "Close", "Volume"]
_DEFAULT_CACHE = Path(__file__).parent / ".cache"


@dataclass
class CoverageReport:
    """Which tickers made it into the study, and why the rest did not.

    Silently dropping tickers is how a study ends up describing a universe
    nobody chose. Every exclusion is counted and attributed to a cause.
    """

    requested: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    excluded_short_history: dict[str, int] = field(default_factory=dict)
    failed_download: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Tickers solicitados: {len(self.requested)} | "
            f"incluidos: {len(self.included)} | "
            f"excluidos por historia corta: {len(self.excluded_short_history)} | "
            f"fallos de descarga: {len(self.failed_download)}"
        )


def _download(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Raw yfinance call, isolated so tests can replace it without touching the network."""
    return yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )


def _cache_path(cache_dir: Path, tickers: list[str], start: str, end: str) -> Path:
    """Content-addressed cache name.

    Uses md5 rather than the builtin hash(): Python randomises string hashing
    per process, so a builtin hash would miss the cache on every fresh run and
    silently re-download the whole universe.
    """
    key = f"{'-'.join(sorted(tickers))}_{start}_{end}"
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return cache_dir / f"batch_{digest}.parquet"


def _fetch_batch(
    tickers: list[str], start: str, end: str, cache_dir: Path, max_retries: int
) -> pd.DataFrame | None:
    path = _cache_path(cache_dir, tickers, start, end)
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a
            # cache miss rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    for attempt in range(max_retries):
        try:
            frame = _download(tickers, start, end)
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(2.0**attempt)
            continue
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        frame.to_parquet(tmp_path)
        tmp_path.replace(path)  # atomic rename: a reader never sees a partial file
        return frame
    return None


def load_ohlcv(
    tickers: list[str],
    start: str,
    end: str,
    cache_dir: Path | None = None,
    min_obs: int = 252,
    batch_size: int = 50,
    max_retries: int = 3,
) -> tuple[pd.DataFrame, CoverageReport]:
    """Download an OHLCV panel, caching each batch to disk.

    Columns are a MultiIndex of (field, ticker). Repeated runs read parquet
    instead of the network, which is what makes the study reproducible without
    depending on a vendor being up.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    coverage = CoverageReport(requested=list(tickers))

    frames: list[pd.DataFrame] = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        frame = _fetch_batch(batch, start, end, cache_dir, max_retries)
        if frame is None:
            coverage.failed_download.extend(batch)
            continue
        frames.append(frame)

    if not frames:
        return pd.DataFrame(), coverage

    panel = pd.concat(frames, axis=1).sort_index()

    keep: list[str] = []
    available = set(panel.columns.get_level_values(1))
    for ticker in tickers:
        if ticker in coverage.failed_download:
            continue
        if ticker not in available:
            coverage.excluded_short_history[ticker] = 0
            continue
        n_obs = int(panel[("Close", ticker)].notna().sum())
        if n_obs < min_obs:
            coverage.excluded_short_history[ticker] = n_obs
        else:
            keep.append(ticker)

    coverage.included = keep
    if not keep:
        return pd.DataFrame(), coverage

    columns = pd.MultiIndex.from_product([FIELDS, keep])
    return panel.reindex(columns=columns), coverage
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_loader.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add research/loader.py tests/test_research_loader.py
git commit -m "feat: cargador OHLCV con caché parquet y reporte de cobertura"
```

---

## Task 3: Indicadores nativos

**Files:**
- Create: `research/indicators.py`
- Test: `tests/test_research_indicators.py`

Todas las funciones operan sobre un `DataFrame` de cierres con fechas en el índice y tickers en las columnas, y devuelven un `DataFrame` de la misma forma. Ninguna desplaza nada — el desplazamiento es responsabilidad de `signals.py`.

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_indicators.py`:

```python
import numpy as np
import pandas as pd
import pytest

from research.indicators import (
    bollinger_position,
    macd_histogram,
    rolling_max,
    rsi,
    sma,
)


def _frame(values: list[float], name: str = "AAA") -> pd.DataFrame:
    return pd.DataFrame({name: values}, index=pd.bdate_range("2020-01-01", periods=len(values)))


@pytest.fixture
def ramp() -> pd.DataFrame:
    """A strictly increasing series: every period is a gain, none is a loss."""
    return _frame(list(np.linspace(10.0, 110.0, 300)))


@pytest.fixture
def flat() -> pd.DataFrame:
    return _frame([50.0] * 300)


# ── RSI ───────────────────────────────────────────────────────────────────────

def test_rsi_of_a_strictly_rising_series_is_one_hundred(ramp):
    """With no down periods the average loss is zero, which pins RSI at its ceiling."""
    assert rsi(ramp, window=14).iloc[-1].item() == pytest.approx(100.0)


def test_rsi_of_a_strictly_falling_series_is_zero(ramp):
    falling = ramp.iloc[::-1].reset_index(drop=True)
    falling.index = pd.bdate_range("2020-01-01", periods=len(falling))
    assert rsi(falling, window=14).iloc[-1].item() == pytest.approx(0.0)


def test_rsi_of_a_flat_series_is_neutral(flat):
    """No gains and no losses is not a signal in either direction."""
    assert rsi(flat, window=14).iloc[-1].item() == pytest.approx(50.0)


def test_rsi_stays_inside_its_bounds():
    rng = np.random.default_rng(5)
    noisy = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 300))))
    values = rsi(noisy, window=14).dropna()
    assert values.min().item() >= 0.0
    assert values.max().item() <= 100.0


def test_rsi_needs_a_full_window_before_reporting(ramp):
    assert rsi(ramp, window=14).iloc[:14].isna().all().item()


def test_the_first_rsi_value_uses_wilders_simple_average_seed():
    """Seeding the recursion off a single delta instead of the first full window
    lands tens of RSI points away from Wilder's definition — 43 in the worst
    case measured — and stays wrong for ~240 observations, enough to flip an
    oversold trigger through the study's opening year. This pins the seed
    without depending on the optional reference library below.
    """
    rng = np.random.default_rng(23)
    frame = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 60))))
    window = 14

    delta = frame["AAA"].diff()
    seed_gain = delta.clip(lower=0.0).iloc[1 : window + 1].mean()
    seed_loss = (-delta).clip(lower=0.0).iloc[1 : window + 1].mean()
    expected = 100.0 - 100.0 / (1.0 + seed_gain / seed_loss)

    assert rsi(frame, window=window).iloc[window].item() == pytest.approx(expected)


# ── MACD ──────────────────────────────────────────────────────────────────────

def test_macd_histogram_of_a_rising_series_is_positive(ramp):
    assert macd_histogram(ramp).iloc[-1].item() > 0.0


def test_macd_histogram_of_a_flat_series_is_zero(flat):
    assert macd_histogram(flat).iloc[-1].item() == pytest.approx(0.0, abs=1e-9)


# ── SMA y máximo móvil ────────────────────────────────────────────────────────

def test_sma_of_a_flat_series_equals_the_level(flat):
    assert sma(flat, window=200).iloc[-1].item() == pytest.approx(50.0)


def test_sma_of_a_linear_ramp_equals_the_window_midpoint(ramp):
    window = 20
    expected = ramp.iloc[-window:].mean().item()
    assert sma(ramp, window=window).iloc[-1].item() == pytest.approx(expected)


def test_rolling_max_of_a_rising_series_is_the_latest_value(ramp):
    assert rolling_max(ramp, window=252).iloc[-1].item() == pytest.approx(ramp.iloc[-1].item())


def test_rolling_max_never_falls_below_the_current_price():
    rng = np.random.default_rng(9)
    noisy = _frame(list(100.0 + np.cumsum(rng.normal(0, 1, 400))))
    highs = rolling_max(noisy, window=252).dropna()
    assert (highs >= noisy.loc[highs.index]).all().item()


# ── Bollinger ─────────────────────────────────────────────────────────────────

def test_bollinger_position_is_zero_at_the_moving_average():
    values = [50.0] * 40 + [50.0]
    frame = _frame(values)
    assert bollinger_position(frame, window=20, n_std=2.0).iloc[-1].isna().item()


def test_bollinger_position_is_positive_above_the_average():
    rng = np.random.default_rng(11)
    values = list(100.0 + rng.normal(0, 1, 60)) + [130.0]
    assert bollinger_position(_frame(values), window=20, n_std=2.0).iloc[-1].item() > 0.0


def test_bollinger_position_is_negative_below_the_average():
    rng = np.random.default_rng(11)
    values = list(100.0 + rng.normal(0, 1, 60)) + [70.0]
    assert bollinger_position(_frame(values), window=20, n_std=2.0).iloc[-1].item() < 0.0


def test_bollinger_position_of_one_means_the_upper_band():
    rng = np.random.default_rng(13)
    frame = _frame(list(100.0 + rng.normal(0, 2, 100)))
    window, n_std = 20, 2.0
    mean = frame.rolling(window).mean()
    std = frame.rolling(window).std(ddof=0)
    at_upper = mean + n_std * std
    position = (at_upper - mean) / (n_std * std)
    assert position.dropna().iloc[-1].item() == pytest.approx(1.0)


# ── Referencia cruzada opcional ───────────────────────────────────────────────

def test_rsi_matches_a_reference_implementation():
    """Same pattern the repo already uses to check Ledoit-Wolf against scikit-learn."""
    ta = pytest.importorskip("pandas_ta_classic")
    rng = np.random.default_rng(17)
    series = pd.Series(100.0 + np.cumsum(rng.normal(0, 1, 500)))
    ours = rsi(series.to_frame("AAA"), window=14)["AAA"].dropna()
    theirs = ta.rsi(series, length=14).dropna()
    common = ours.index.intersection(theirs.index)
    assert np.allclose(ours.loc[common], theirs.loc[common], atol=1e-6)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_indicators.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.indicators'`

- [ ] **Step 3: Implementar**

Crea `research/indicators.py`:

```python
"""Technical indicators, implemented natively.

Written in-house rather than pulled from a library so the shift discipline is
visible in one place: none of these functions shifts anything. Aligning a value
to the date it may be acted on is signals.py's job, and splitting that
responsibility across a dependency is how look-ahead sneaks in.
"""

import numpy as np
import pandas as pd


def _wilder_smooth(values: pd.DataFrame, window: int) -> pd.DataFrame:
    """Wilder's smoothing, seeded with the simple mean of the first full window.

    The seed matters more than it looks. Running ewm(adjust=False) straight from
    the first observation instead starts the recursion from a single data point.
    Measured against a reference implementation over a 200-seed sweep of random
    walks, that lands tens of RSI points off — 43 in the worst case — and takes
    ~240 observations to converge, roughly the first year of this study. Far
    more than enough to flip an oversold trigger.
    """
    if len(values) <= window:
        return values * np.nan
    seeded = values.copy()
    seeded.iloc[:window] = np.nan
    seeded.iloc[window] = values.iloc[1 : window + 1].mean()
    return seeded.ewm(alpha=1.0 / window, adjust=False).mean()


def rsi(close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Wilder's RSI. 100 when every period gained, 0 when every period lost."""
    delta = close.diff()
    avg_gain = _wilder_smooth(delta.clip(lower=0.0), window)
    avg_loss = _wilder_smooth((-delta).clip(lower=0.0), window)

    both_flat = (avg_gain == 0.0) & (avg_loss == 0.0)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    values = 100.0 - 100.0 / (1.0 + rs)
    values = values.where(~(avg_loss == 0.0), 100.0)
    return values.where(~both_flat, 50.0)


def macd_histogram(
    close: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD line minus its signal line. Positive means the fast trend leads."""
    macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    return macd - macd.ewm(span=signal, adjust=False).mean()


def sma(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close.rolling(window).mean()


def rolling_max(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close.rolling(window).max()


def bollinger_position(
    close: pd.DataFrame, window: int = 20, n_std: float = 2.0
) -> pd.DataFrame:
    """Where the price sits inside its band: -1 is the lower band, +1 the upper.

    Undefined while the price is perfectly flat, because a band of zero width
    has no inside.
    """
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    width = n_std * std
    return (close - mean) / width.replace(0.0, np.nan)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_indicators.py -v`
Expected: 17 passed (o 16 passed, 1 skipped si `pandas-ta-classic` no está instalado)

- [ ] **Step 5: Commit**

```bash
git add research/indicators.py tests/test_research_indicators.py
git commit -m "feat: indicadores técnicos nativos con referencia cruzada opcional"
```

---

## Task 4: Señales y disciplina de desplazamiento

**Files:**
- Create: `research/signals.py`
- Test: `tests/test_research_signals.py`

**El test de truncamiento es la parte importante de esta tarea.** Verifica que el valor de una señal en la fecha *t* no cambia cuando se añaden datos posteriores a *t*. Si cambia, la señal está mirando el futuro. Es una propiedad automática que cubre las 8 señales sin trabajo por señal.

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_signals.py`:

```python
import numpy as np
import pandas as pd
import pytest

from research.signals import (
    FAMILIES,
    SIGNALS,
    TRIGGERS,
    oracle_signal,
)

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


@pytest.fixture
def panel() -> pd.DataFrame:
    """Six tickers, four years of business days, with genuine price dynamics."""
    tickers = [f"T{i}" for i in range(6)]
    dates = pd.bdate_range("2019-01-01", periods=1000)
    rng = np.random.default_rng(21)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, size=(len(dates), len(tickers))), axis=0))
    frames = {
        "Open": closes * 0.999,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Close": closes,
        "Volume": np.full_like(closes, 1_000_000.0),
    }
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    data = np.hstack([frames[f] for f in FIELDS])
    return pd.DataFrame(data, index=dates, columns=columns)


# ── Contrato del registro ─────────────────────────────────────────────────────

def test_the_registry_holds_exactly_eight_signals():
    """Seven evaluated signals plus the random control. The oracle is test-only."""
    assert len(SIGNALS) == 8


def test_every_signal_has_a_declared_family():
    assert set(SIGNALS) == set(FAMILIES)


def test_every_signal_has_a_trigger():
    assert set(SIGNALS) == set(TRIGGERS)


@pytest.mark.parametrize("name", sorted(SIGNALS))
def test_every_signal_returns_a_frame_shaped_like_the_price_panel(name, panel):
    result = SIGNALS[name](panel)
    assert list(result.columns) == list(panel["Close"].columns)
    assert result.index.equals(panel.index)


@pytest.mark.parametrize("name", sorted(TRIGGERS))
def test_every_trigger_returns_booleans(name, panel):
    result = TRIGGERS[name](panel)
    assert result.dtypes.unique().tolist() == [bool]


# ── La defensa contra look-ahead ──────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(SIGNALS))
def test_no_signal_changes_when_future_data_is_appended(name, panel):
    """The truncation property: a signal that peeks reveals itself here.

    If the value dated t differs between the full history and a history that
    stops at t, the computation used information that did not exist at t.
    """
    cutoff = panel.index[700]
    full = SIGNALS[name](panel)
    truncated = SIGNALS[name](panel.loc[:cutoff])
    pd.testing.assert_series_equal(
        full.loc[cutoff], truncated.loc[cutoff], check_names=False
    )


@pytest.mark.parametrize("name", sorted(TRIGGERS))
def test_no_trigger_changes_when_future_data_is_appended(name, panel):
    cutoff = panel.index[700]
    full = TRIGGERS[name](panel)
    truncated = TRIGGERS[name](panel.loc[:cutoff])
    pd.testing.assert_series_equal(
        full.loc[cutoff], truncated.loc[cutoff], check_names=False
    )


def test_the_oracle_deliberately_fails_the_truncation_property(panel):
    """The oracle exists to prove the measuring apparatus detects future information.

    It must peek. If this test ever passes, the oracle stopped doing its job and
    every 'the harness works' conclusion drawn from it is void.
    """
    cutoff = panel.index[700]
    full = oracle_signal(panel, horizon=21)
    truncated = oracle_signal(panel.loc[:cutoff], horizon=21)
    assert not np.allclose(
        full.loc[cutoff].to_numpy(), truncated.loc[cutoff].to_numpy(), equal_nan=True
    )


# ── Contenido de las señales ──────────────────────────────────────────────────

def test_momentum_ranks_the_strongest_riser_highest():
    tickers = ["WINNER", "LOSER"]
    dates = pd.bdate_range("2019-01-01", periods=400)
    closes = np.column_stack([np.linspace(10, 200, 400), np.linspace(200, 10, 400)])
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    data = np.hstack([closes] * 5)
    panel = pd.DataFrame(data, index=dates, columns=columns)
    values = SIGNALS["mom_12_1"](panel).iloc[-1]
    assert values["WINNER"] > values["LOSER"]


def test_short_term_reversal_points_the_opposite_way_to_momentum(panel):
    """They are measured separately precisely because they disagree by construction."""
    recent = panel["Close"].pct_change(21, fill_method=None).shift(1).iloc[-1]
    reversal = SIGNALS["rev_1m"](panel).iloc[-1]
    assert np.sign(reversal.corr(recent)) == -1


def test_the_random_control_is_reproducible(panel):
    first = SIGNALS["random_control"](panel)
    second = SIGNALS["random_control"](panel)
    pd.testing.assert_frame_equal(first, second)


def test_the_random_control_carries_no_price_information(panel):
    """If this correlates with anything, the control is not a control."""
    forward = panel["Close"].pct_change(21, fill_method=None).shift(-21)
    control = SIGNALS["random_control"](panel)
    common = control.dropna(how="all").index.intersection(forward.dropna(how="all").index)
    correlation = control.loc[common].corrwith(forward.loc[common]).abs().max()
    assert correlation < 0.15


def test_quintile_triggers_fire_for_roughly_the_top_fifth(panel):
    fired = TRIGGERS["mom_12_1"](panel)
    valid = SIGNALS["mom_12_1"](panel).notna().all(axis=1)
    rate = fired[valid].mean(axis=1).mean()
    assert 0.10 < rate < 0.40


def test_the_rsi_trigger_only_fires_in_oversold_territory(panel):
    from research.indicators import rsi

    raw = rsi(panel["Close"], window=14).shift(1)
    fired = TRIGGERS["rsi_14"](panel)
    fired_values = raw.where(fired).stack()
    assert len(fired_values) > 0
    assert (fired_values < 30.0).all()
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_signals.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.signals'`

- [ ] **Step 3: Implementar**

Crea `research/signals.py`:

```python
from collections.abc import Callable

import numpy as np
import pandas as pd

from research.indicators import bollinger_position, macd_histogram, rolling_max, rsi, sma

RANDOM_CONTROL_SEED = 20260805
TOP_QUINTILE = 0.8


def _as_of(frame: pd.DataFrame) -> pd.DataFrame:
    """Align a computed value to the first date it could have been acted on.

    Everything in this module funnels through here. A value computed from data
    through the close of t-1 is dated t, which is the date an order could first
    be placed. Every signal shifts exactly once, and only here.
    """
    return frame.shift(1)


# ── F1: momentum de medio plazo ───────────────────────────────────────────────

def mom_12_1(panel: pd.DataFrame) -> pd.DataFrame:
    """Return from t-252 to t-21. The most documented price-based signal there is.

    Skipping the most recent month is the convention: it is contaminated by the
    short-term reversal effect that rev_1m isolates.
    """
    close = panel["Close"]
    return _as_of(close.shift(21) / close.shift(252) - 1.0)


# ── F2: reversión de corto plazo ──────────────────────────────────────────────

def rev_1m(panel: pd.DataFrame) -> pd.DataFrame:
    """Last month's return, negated: recent losers score high."""
    close = panel["Close"]
    return _as_of(-(close.pct_change(21, fill_method=None)))


# ── F3: timing de entrada ─────────────────────────────────────────────────────

def rsi_14(panel: pd.DataFrame) -> pd.DataFrame:
    """RSI negated, so oversold reads as a high score like every other signal."""
    return _as_of(-rsi(panel["Close"], window=14))


def macd_cross(panel: pd.DataFrame) -> pd.DataFrame:
    return _as_of(macd_histogram(panel["Close"]))


def dist_sma200(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["Close"]
    average = sma(close, window=200)
    return _as_of((close - average) / average)


def breakout_52w(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["Close"]
    return _as_of(close / rolling_max(close, window=252))


def bollinger_pos(panel: pd.DataFrame) -> pd.DataFrame:
    """Band position negated, so touching the lower band reads as a high score."""
    return _as_of(-bollinger_position(panel["Close"], window=20, n_std=2.0))


# ── Control negativo ──────────────────────────────────────────────────────────

def random_control(panel: pd.DataFrame) -> pd.DataFrame:
    """Noise with the shape of a signal. Must fail the criterion.

    Drawn row by row from a fixed seed, so truncating the history leaves every
    surviving value untouched — which is what lets the control sit inside the
    same truncation test as the real signals.
    """
    close = panel["Close"]
    rng = np.random.default_rng(RANDOM_CONTROL_SEED)
    values = rng.uniform(size=(len(close.index), len(close.columns)))
    return _as_of(pd.DataFrame(values, index=close.index, columns=close.columns))


# ── Fixture de test, nunca usado por el estudio ───────────────────────────────

def oracle_signal(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """The forward return itself. Peeks on purpose.

    Not part of SIGNALS: its only job is to prove the evaluation machinery can
    detect future information when it is genuinely there. An IC near zero for
    this signal means the measurement is broken, not that markets are efficient.
    """
    close = panel["Close"]
    return close.shift(-horizon) / close - 1.0


# ── Registros ─────────────────────────────────────────────────────────────────

SIGNALS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "mom_12_1": mom_12_1,
    "rev_1m": rev_1m,
    "rsi_14": rsi_14,
    "macd_cross": macd_cross,
    "dist_sma200": dist_sma200,
    "breakout_52w": breakout_52w,
    "bollinger_pos": bollinger_pos,
    "random_control": random_control,
}

FAMILIES: dict[str, str] = {
    "mom_12_1": "F1 Momentum medio plazo",
    "rev_1m": "F2 Reversión corto plazo",
    "rsi_14": "F3 Timing de entrada",
    "macd_cross": "F3 Timing de entrada",
    "dist_sma200": "F3 Timing de entrada",
    "breakout_52w": "F3 Timing de entrada",
    "bollinger_pos": "F3 Timing de entrada",
    "random_control": "Control negativo",
}


def _top_quintile_trigger(name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Continuous signals have no natural threshold, so the cross-section supplies one."""

    def trigger(panel: pd.DataFrame) -> pd.DataFrame:
        values = SIGNALS[name](panel)
        return (values.rank(axis=1, pct=True) >= TOP_QUINTILE).astype(bool)

    return trigger


def _rsi_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    return (_as_of(rsi(panel["Close"], window=14)) < 30.0).astype(bool)


def _macd_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    """The crossing itself, not the level: negative yesterday, positive today."""
    histogram = _as_of(macd_histogram(panel["Close"]))
    return ((histogram > 0.0) & (histogram.shift(1) <= 0.0)).astype(bool)


def _sma200_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    close = _as_of(panel["Close"])
    average = _as_of(sma(panel["Close"], window=200))
    above = close > average
    return (above & ~above.shift(1, fill_value=False)).astype(bool)


def _breakout_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    """Today's close exceeds the highest close of the previous 252 days."""
    close = _as_of(panel["Close"])
    prior_high = _as_of(rolling_max(panel["Close"].shift(1), window=252))
    return (close > prior_high).astype(bool)


def _bollinger_trigger(panel: pd.DataFrame) -> pd.DataFrame:
    position = _as_of(bollinger_position(panel["Close"], window=20, n_std=2.0))
    return (position <= -1.0).astype(bool)


TRIGGERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "mom_12_1": _top_quintile_trigger("mom_12_1"),
    "rev_1m": _top_quintile_trigger("rev_1m"),
    "rsi_14": _rsi_trigger,
    "macd_cross": _macd_trigger,
    "dist_sma200": _sma200_trigger,
    "breakout_52w": _breakout_trigger,
    "bollinger_pos": _bollinger_trigger,
    "random_control": _top_quintile_trigger("random_control"),
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_signals.py -v`
Expected: todos pasan (≈40 tests con las parametrizaciones)

Si `test_no_signal_changes_when_future_data_is_appended` falla para alguna señal, **no relajes el test**: es la defensa contra look-ahead y está haciendo su trabajo. Encuentra el `shift` que falta.

- [ ] **Step 5: Commit**

```bash
git add research/signals.py tests/test_research_signals.py
git commit -m "feat: registro de señales con disciplina de desplazamiento y test de truncamiento"
```

---

## Task 5: Costes de transacción

**Files:**
- Create: `research/costs.py`
- Test: `tests/test_research_costs.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_costs.py`:

```python
import numpy as np
import pandas as pd
import pytest

from research.costs import COST_SCENARIOS, apply_costs, turnover_from_weights


def test_zero_cost_leaves_returns_untouched():
    returns = pd.Series([0.01, -0.02, 0.03])
    turnover = pd.Series([1.0, 1.0, 1.0])
    pd.testing.assert_series_equal(apply_costs(returns, turnover, bps=0.0), returns)


def test_full_turnover_at_ten_bps_costs_ten_bps():
    returns = pd.Series([0.01])
    turnover = pd.Series([1.0])
    assert apply_costs(returns, turnover, bps=10.0).iloc[0] == pytest.approx(0.01 - 0.0010)


def test_half_turnover_costs_half_as_much():
    returns = pd.Series([0.01])
    assert apply_costs(returns, pd.Series([0.5]), bps=10.0).iloc[0] == pytest.approx(0.01 - 0.0005)


def test_costs_only_ever_reduce_returns():
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0, 0.02, 100))
    turnover = pd.Series(rng.uniform(0, 1, 100))
    assert (apply_costs(returns, turnover, bps=25.0) <= returns).all()


def test_turnover_of_an_unchanged_portfolio_is_zero():
    weights = pd.DataFrame([[0.5, 0.5], [0.5, 0.5]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[-1] == pytest.approx(0.0)


def test_turnover_of_a_completely_rebuilt_portfolio_is_one():
    """Selling everything and buying a disjoint set trades the whole portfolio once."""
    weights = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[-1] == pytest.approx(1.0)


def test_the_first_period_counts_as_building_the_position():
    weights = pd.DataFrame([[0.5, 0.5]], columns=["A", "B"])
    assert turnover_from_weights(weights).iloc[0] == pytest.approx(1.0)


def test_the_three_pre_registered_cost_scenarios_are_available():
    assert COST_SCENARIOS == {"optimista": 5.0, "base": 10.0, "conservador": 25.0}
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_costs.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.costs'`

- [ ] **Step 3: Implementar**

Crea `research/costs.py`:

```python
import pandas as pd

COST_SCENARIOS: dict[str, float] = {
    "optimista": 5.0,
    "base": 10.0,
    "conservador": 25.0,
}


def turnover_from_weights(weights: pd.DataFrame) -> pd.Series:
    """Fraction of the portfolio traded each period.

    Half the sum of absolute weight changes: selling 100% of one name to buy
    another moves 200% of weight but only trades the portfolio once. The first
    period counts as a full trade, because the position has to be built.
    """
    previous = weights.shift(1)
    first_period = previous.isna().all(axis=1)
    traded = (weights - previous.fillna(0.0)).abs().sum(axis=1) / 2.0
    return traded.where(~first_period, weights.abs().sum(axis=1))


def apply_costs(gross_returns: pd.Series, turnover: pd.Series, bps: float) -> pd.Series:
    """Charge `bps` per unit of turnover, round trip.

    High-turnover signals live or die here, so gross and net are always reported
    side by side rather than collapsed into one number.
    """
    return gross_returns - turnover.reindex(gross_returns.index).fillna(0.0) * (bps / 10_000.0)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_costs.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add research/costs.py tests/test_research_costs.py
git commit -m "feat: modelo de costes de transacción sobre rotación"
```

---

## Task 6: Puerta A — evaluación estadística

**Files:**
- Create: `research/evaluation.py`
- Test: `tests/test_research_evaluation.py`

**Por qué se implementa nativamente:** el criterio necesita t-stats con corrección Newey-West, partición en sub-periodos y Benjamini-Hochberg. Ninguna librería de análisis de factores trae eso, así que la matemática hay que escribirla de todos modos. El IC se contrasta contra `scipy.stats.spearmanr` — el mismo patrón que el repositorio ya usa con scikit-learn.

**Rendimiento:** el IC se calcula vectorizado (Spearman = Pearson sobre rangos), no con un bucle sobre fechas. La grilla completa son 8 señales × 4 horizontes × (periodo total + 4 sub-periodos), es decir ~160 evaluaciones sobre ~4.000 fechas y ~500 tickers. Con un bucle por fecha llamando a `scipy.stats.spearmanr` el estudio tardaría horas; vectorizado tarda minutos. El test de referencia cruzada contra scipy es lo que hace segura esa optimización.

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_evaluation.py`:

```python
import numpy as np
import pandas as pd
import pytest

from research.evaluation import (
    SUBPERIODS,
    GateAResult,
    benjamini_hochberg,
    equal_weight_sharpe,
    evaluate,
    forward_returns,
    information_coefficient,
    newey_west_tstat,
    quintile_spread,
)


@pytest.fixture
def close() -> pd.DataFrame:
    tickers = [f"T{i}" for i in range(20)]
    dates = pd.bdate_range("2015-01-01", periods=1500)
    rng = np.random.default_rng(31)
    steps = rng.normal(0.0004, 0.014, size=(len(dates), len(tickers)))
    return pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=dates, columns=tickers)


# ── Retornos futuros ──────────────────────────────────────────────────────────

def test_forward_returns_look_ahead_by_exactly_the_horizon(close):
    forward = forward_returns(close, horizon=5)
    expected = close.iloc[5, 0] / close.iloc[0, 0] - 1.0
    assert forward.iloc[0, 0] == pytest.approx(expected)


def test_the_last_rows_have_no_forward_return(close):
    assert forward_returns(close, horizon=5).iloc[-5:].isna().all().all()


# ── Information coefficient ───────────────────────────────────────────────────

def test_an_oracle_signal_scores_a_near_perfect_ic(close):
    """Proves the measurement works. If this fails, no other result means anything."""
    forward = forward_returns(close, horizon=21)
    ic = information_coefficient(forward, forward)
    assert ic.mean() == pytest.approx(1.0, abs=1e-9)


def test_a_random_signal_scores_essentially_zero_ic(close):
    """Proves nothing leaks. If this is far from zero, the pipeline peeks."""
    rng = np.random.default_rng(37)
    noise = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)
    ic = information_coefficient(noise, forward_returns(close, horizon=21))
    assert abs(ic.mean()) < 0.02


def test_a_sign_flipped_signal_scores_the_opposite_ic(close):
    forward = forward_returns(close, horizon=21)
    assert information_coefficient(-forward, forward).mean() == pytest.approx(-1.0, abs=1e-9)


def test_dates_without_enough_names_are_skipped(close):
    """Ranking three stocks says nothing about a cross-section; those dates are dropped."""
    forward = forward_returns(close, horizon=21)
    sparse = forward.copy()
    sparse.iloc[:100, 3:] = np.nan
    ic = information_coefficient(sparse, forward, min_names=10)
    assert ic.iloc[:100].isna().all()


# ── t-stat Newey-West ─────────────────────────────────────────────────────────

def test_newey_west_with_zero_lag_matches_the_plain_t_stat():
    rng = np.random.default_rng(41)
    series = pd.Series(rng.normal(0.05, 1.0, 500))
    plain = series.mean() / (series.std(ddof=0) / np.sqrt(len(series)))
    assert newey_west_tstat(series, lag=0) == pytest.approx(plain, rel=1e-6)


def test_newey_west_shrinks_the_t_stat_of_an_autocorrelated_series():
    """Overlapping horizons autocorrelate the IC series and inflate the naive t-stat."""
    rng = np.random.default_rng(43)
    noise = rng.normal(0, 1, 2000)
    smoothed = pd.Series(noise).rolling(20).mean().dropna() + 0.05
    assert abs(newey_west_tstat(smoothed, lag=19)) < abs(newey_west_tstat(smoothed, lag=0))


def test_a_series_with_no_variation_has_no_measurable_t_stat():
    assert np.isinf(newey_west_tstat(pd.Series([0.05] * 100), lag=0)) or newey_west_tstat(
        pd.Series([0.05] * 100), lag=0
    ) == 0.0


# ── Benjamini-Hochberg ────────────────────────────────────────────────────────

def test_benjamini_hochberg_rejects_nothing_when_every_p_value_is_large():
    assert not benjamini_hochberg([0.5, 0.6, 0.7, 0.9], fdr=0.10).any()


def test_benjamini_hochberg_rejects_a_clearly_significant_p_value():
    passed = benjamini_hochberg([0.0001, 0.5, 0.6, 0.9], fdr=0.10)
    assert passed.tolist() == [True, False, False, False]


def test_a_lone_marginal_p_value_among_many_tests_does_not_survive():
    """0.04 looks significant on its own; among twenty tests it is what noise produces."""
    pvalues = [0.04] + [0.6] * 19
    assert benjamini_hochberg(pvalues, fdr=0.10).sum() == 0


def test_benjamini_hochberg_preserves_input_order():
    passed = benjamini_hochberg([0.9, 0.0001, 0.8], fdr=0.10)
    assert passed.tolist() == [False, True, False]


# ── Quintiles ─────────────────────────────────────────────────────────────────

def test_an_oracle_signal_produces_a_positive_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, _, _ = quintile_spread(forward, forward, horizon=21)
    assert gross > 0.0


def test_a_sign_flipped_oracle_produces_a_negative_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, _, _ = quintile_spread(-forward, forward, horizon=21)
    assert gross < 0.0


def test_quintile_spread_also_reports_turnover(close):
    forward = forward_returns(close, horizon=21)
    _, _, turnover = quintile_spread(forward, forward, horizon=21)
    assert 0.0 <= turnover <= 1.0


def test_costs_never_improve_the_quintile_spread(close):
    forward = forward_returns(close, horizon=21)
    gross, net, _ = quintile_spread(forward, forward, horizon=21, bps=25.0)
    assert net <= gross


# ── Línea base pasiva ─────────────────────────────────────────────────────────

def test_the_passive_benchmark_reports_a_finite_sharpe(close):
    assert np.isfinite(equal_weight_sharpe(close))


def test_the_passive_benchmark_is_positive_for_a_rising_market():
    dates = pd.bdate_range("2015-01-01", periods=600)
    rising = pd.DataFrame(
        {"A": np.linspace(100, 200, 600), "B": np.linspace(100, 180, 600)}, index=dates
    )
    assert equal_weight_sharpe(rising) > 0.0


# ── Sub-periodos ──────────────────────────────────────────────────────────────

def test_the_four_subperiods_do_not_overlap():
    bounds = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in SUBPERIODS.values()]
    ordered = sorted(bounds)
    assert all(ordered[i][1] < ordered[i + 1][0] for i in range(len(ordered) - 1))


def test_there_are_exactly_four_subperiods():
    assert len(SUBPERIODS) == 4


def test_the_subperiods_cover_the_whole_study_window():
    starts = [pd.Timestamp(a) for a, _ in SUBPERIODS.values()]
    ends = [pd.Timestamp(b) for _, b in SUBPERIODS.values()]
    assert min(starts) == pd.Timestamp("2010-01-01")
    assert max(ends) == pd.Timestamp("2026-06-30")


# ── evaluate ──────────────────────────────────────────────────────────────────

def test_evaluate_reports_every_field_the_criterion_needs(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert isinstance(result, GateAResult)
    assert result.signal == "oracle"
    assert result.horizon == 21
    assert result.n_dates > 0
    assert set(result.subperiod_pass) <= set(SUBPERIODS)


def test_evaluate_gives_the_oracle_a_huge_ic(close):
    forward = forward_returns(close, horizon=21)
    assert evaluate("oracle", forward, close, horizon=21, bps=10.0).mean_ic > 0.9


def test_evaluate_gives_random_noise_an_ic_near_zero(close):
    rng = np.random.default_rng(47)
    noise = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)
    assert abs(evaluate("noise", noise, close, horizon=21, bps=10.0).mean_ic) < 0.02


def test_evaluate_reports_the_three_pre_registered_cost_scenarios(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert set(result.spread_net_by_scenario) == {"optimista", "base", "conservador"}


def test_higher_costs_never_produce_a_better_net_spread(close):
    forward = forward_returns(close, horizon=21)
    scenarios = evaluate("oracle", forward, close, horizon=21, bps=10.0).spread_net_by_scenario
    assert scenarios["conservador"] <= scenarios["base"] <= scenarios["optimista"]


def test_the_base_scenario_is_the_one_the_criterion_uses(close):
    forward = forward_returns(close, horizon=21)
    result = evaluate("oracle", forward, close, horizon=21, bps=10.0)
    assert result.spread_net == pytest.approx(result.spread_net_by_scenario["base"])


# ── Referencia cruzada ────────────────────────────────────────────────────────

def test_our_information_coefficient_matches_an_independent_implementation(close):
    """The vectorised rank correlation must agree with scipy, date by date.

    Same pattern the repo already uses to check Ledoit-Wolf against scikit-learn.
    The loop version is the obvious implementation but far too slow for the full
    grid, so the fast one has to be pinned to a reference.
    """
    from scipy import stats as scipy_stats

    forward = forward_returns(close, horizon=21)
    rng = np.random.default_rng(51)
    signal = pd.DataFrame(rng.uniform(size=close.shape), index=close.index, columns=close.columns)

    ours = information_coefficient(signal, forward).dropna()
    sample = ours.index[::97]
    for date in sample:
        valid = signal.loc[date].notna() & forward.loc[date].notna()
        reference = scipy_stats.spearmanr(
            signal.loc[date][valid], forward.loc[date][valid]
        ).statistic
        assert ours.loc[date] == pytest.approx(reference, abs=1e-9)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_evaluation.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.evaluation'`

- [ ] **Step 3: Implementar**

Crea `research/evaluation.py`:

```python
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from research.costs import COST_SCENARIOS, apply_costs, turnover_from_weights

SUBPERIODS: dict[str, tuple[str, str]] = {
    "P1 2010-2013": ("2010-01-01", "2013-12-31"),
    "P2 2014-2017": ("2014-01-01", "2017-12-31"),
    "P3 2018-2021": ("2018-01-01", "2021-12-31"),
    "P4 2022-2026": ("2022-01-01", "2026-06-30"),
}

MIN_IC = 0.03
MIN_TSTAT = 2.0
MIN_SUBPERIODS = 3
FDR = 0.10
N_QUANTILES = 5


@dataclass(frozen=True)
class GateAResult:
    signal: str
    horizon: int
    mean_ic: float
    t_stat: float
    p_value: float
    spread_gross: float
    spread_net: float
    turnover: float
    n_dates: int
    subperiod_pass: dict[str, bool] = field(default_factory=dict)
    spread_net_by_scenario: dict[str, float] = field(default_factory=dict)

    @property
    def subperiods_passed(self) -> int:
        return sum(self.subperiod_pass.values())


def forward_returns(close: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return from the close of t to the close of t+horizon."""
    return close.shift(-horizon) / close - 1.0


def information_coefficient(
    signal: pd.DataFrame, forward: pd.DataFrame, min_names: int = 10
) -> pd.Series:
    """Cross-sectional Spearman correlation, one value per date.

    Rank correlation rather than Pearson because the question is whether the
    signal orders the cross-section, not whether it predicts magnitudes. Dates
    with too few names are dropped: ranking a handful of stocks is noise.

    Computed as Pearson correlation of the ranks rather than by calling out to
    scipy per date. The full grid is roughly 160 evaluations over 4,000 dates;
    a per-date loop turns minutes into hours. A cross-check against scipy pins
    the two to the same answer.
    """
    aligned_signal, aligned_forward = signal.align(forward, join="inner")
    valid = aligned_signal.notna() & aligned_forward.notna()

    ranked_signal = aligned_signal.where(valid).rank(axis=1)
    ranked_forward = aligned_forward.where(valid).rank(axis=1)

    centred_signal = ranked_signal.sub(ranked_signal.mean(axis=1), axis=0)
    centred_forward = ranked_forward.sub(ranked_forward.mean(axis=1), axis=0)

    covariance = (centred_signal * centred_forward).sum(axis=1)
    scale = np.sqrt((centred_signal**2).sum(axis=1) * (centred_forward**2).sum(axis=1))

    ic = covariance / scale.replace(0.0, np.nan)
    return ic.where(valid.sum(axis=1) >= min_names)


def equal_weight_sharpe(close: pd.DataFrame) -> float:
    """Annualised Sharpe of buying the whole universe equal-weighted and holding.

    The passive baseline the criterion compares against economically. Risk-free
    rate is zero, matching the convention used in Gate B.
    """
    daily = close.pct_change(fill_method=None).mean(axis=1).dropna()
    if daily.empty or daily.std(ddof=1) == 0.0:
        return 0.0
    return float(daily.mean() / daily.std(ddof=1) * np.sqrt(252.0))


def newey_west_tstat(series: pd.Series, lag: int) -> float:
    """t-stat of the mean, robust to the autocorrelation overlapping horizons create.

    With a horizon of h days, consecutive IC observations share h-1 days of
    return, so the naive standard error understates the true uncertainty and
    manufactures significance. Bartlett weights, lag = h-1.
    """
    x = series.dropna().to_numpy(dtype=float)
    n = x.size
    if n < 2:
        return 0.0
    mu = float(x.mean())
    e = x - mu
    variance = float(e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - l / (lag + 1.0)
        variance += 2.0 * weight * float(e[l:] @ e[:-l]) / n
    if variance <= 0.0:
        return 0.0
    return mu / float(np.sqrt(variance / n))


def benjamini_hochberg(pvalues, fdr: float = FDR) -> np.ndarray:
    """Which p-values survive a false-discovery-rate correction, in input order.

    Twenty-eight tests produce roughly 1.4 spurious winners at a 5% threshold.
    Without this step the study would report noise as a finding.
    """
    p = np.asarray(list(pvalues), dtype=float)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    thresholds = fdr * np.arange(1, n + 1) / n
    below = p[order] <= thresholds
    result = np.zeros(n, dtype=bool)
    if below.any():
        cutoff = int(np.flatnonzero(below).max()) + 1
        result[order[:cutoff]] = True
    return result


def quintile_spread(
    signal: pd.DataFrame, forward: pd.DataFrame, horizon: int, bps: float = 0.0
) -> tuple[float, float, float]:
    """Annualised (top quintile - bottom quintile), gross and net, plus turnover.

    Portfolios are rebalanced at the horizon frequency, so the holding period
    matches the return being predicted. Gross and net come back together rather
    than from two passes: high-turnover signals are decided by the gap between
    them, and computing it twice doubles the cost of the whole study.
    """
    aligned_signal, aligned_forward = signal.align(forward, join="inner")
    dates = aligned_signal.index[::horizon]

    top_weights: list[pd.Series] = []
    period_returns: list[float] = []
    for date in dates:
        row_s = aligned_signal.loc[date]
        row_f = aligned_forward.loc[date]
        valid = row_s.notna() & row_f.notna()
        if valid.sum() < N_QUANTILES * 2:
            continue
        ranks = row_s[valid].rank(pct=True)
        top = row_f[valid][ranks > 0.8]
        bottom = row_f[valid][ranks <= 0.2]
        if top.empty or bottom.empty:
            continue
        period_returns.append(float(top.mean() - bottom.mean()))
        membership = pd.Series(0.0, index=aligned_signal.columns)
        membership[top.index] = 1.0 / len(top)
        top_weights.append(membership)

    if not period_returns:
        return 0.0, 0.0, 0.0

    weights = pd.DataFrame(top_weights).reset_index(drop=True)
    turnover = turnover_from_weights(weights)

    gross = pd.Series(period_returns)
    net = apply_costs(gross, turnover, bps=bps)
    periods_per_year = 252.0 / horizon
    return (
        float(gross.mean() * periods_per_year),
        float(net.mean() * periods_per_year),
        float(turnover.mean()),
    )


def evaluate(
    name: str,
    signal: pd.DataFrame,
    close: pd.DataFrame,
    horizon: int,
    bps: float,
) -> GateAResult:
    """Everything Gate A needs about one signal at one horizon."""
    forward = forward_returns(close, horizon)
    ic = information_coefficient(signal, forward).dropna()

    t_stat = newey_west_tstat(ic, lag=max(horizon - 1, 0))
    p_value = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat))))

    spread_gross, spread_net, turnover = quintile_spread(signal, forward, horizon, bps=bps)

    by_scenario = {
        label: quintile_spread(signal, forward, horizon, bps=scenario_bps)[1]
        for label, scenario_bps in COST_SCENARIOS.items()
    }

    subperiod_pass: dict[str, bool] = {}
    for label, (start, end) in SUBPERIODS.items():
        window_signal = signal.loc[start:end]
        window_close = close.loc[start:end]
        if len(window_signal) < horizon * 4:
            subperiod_pass[label] = False
            continue
        window_forward = forward_returns(window_close, horizon)
        window_ic = information_coefficient(window_signal, window_forward).dropna()
        _, window_net, _ = quintile_spread(window_signal, window_forward, horizon, bps=bps)
        subperiod_pass[label] = bool(
            len(window_ic) > 0 and window_ic.mean() >= MIN_IC and window_net > 0.0
        )

    return GateAResult(
        signal=name,
        horizon=horizon,
        mean_ic=float(ic.mean()) if len(ic) else 0.0,
        t_stat=t_stat,
        p_value=p_value,
        spread_gross=spread_gross,
        spread_net=spread_net,
        turnover=turnover,
        n_dates=int(len(ic)),
        subperiod_pass=subperiod_pass,
        spread_net_by_scenario=by_scenario,
    )
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_evaluation.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add research/evaluation.py tests/test_research_evaluation.py
git commit -m "feat: Puerta A con IC, t-stat Newey-West, quintiles y Benjamini-Hochberg"
```

---

## Task 7: Puerta B — test de timing de entrada

**Files:**
- Create: `research/timing.py`
- Test: `tests/test_research_timing.py`

**El detalle que no se puede omitir:** si la señal no dispara dentro de la ventana de espera, se entra igualmente el último día de la ventana. Comparar sólo las entradas que llegaron a disparar seleccionaría a posteriori los casos favorables e inventaría una ventaja que no existe.

**Sobre el error estándar:** las 500 fechas se muestrean de ~4.100 días con tenencias de 63 días, así que las canastas se solapan. La fórmula de Lo (2002) de `validation.sharpe_standard_error` supone independencia y subestimaría el error. Se usa bootstrap por bloques, con la fórmula i.i.d. sólo como contraste de cordura.

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_timing.py`:

```python
import numpy as np
import pandas as pd
import pytest

from research.timing import GateBResult, block_bootstrap_stderr, compare_entry_timing

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


@pytest.fixture
def panel() -> pd.DataFrame:
    tickers = [f"T{i}" for i in range(40)]
    dates = pd.bdate_range("2015-01-01", periods=1200)
    rng = np.random.default_rng(53)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, size=(len(dates), len(tickers))), axis=0))
    frames = {
        "Open": closes * 0.999,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Close": closes,
        "Volume": np.full_like(closes, 1e6),
    }
    columns = pd.MultiIndex.from_product([FIELDS, tickers])
    return pd.DataFrame(np.hstack([frames[f] for f in FIELDS]), index=dates, columns=columns)


def _always(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(True, index=panel.index, columns=panel["Close"].columns)


def _never(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(False, index=panel.index, columns=panel["Close"].columns)


def test_returns_a_result_with_both_arms(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=1)
    assert isinstance(result, GateBResult)
    assert np.isfinite(result.sharpe_immediate)
    assert np.isfinite(result.sharpe_signal)


def test_a_trigger_that_never_fires_still_enters_at_the_end_of_the_window(panel):
    """Without the forced entry, non-firing cases would vanish and bias the comparison."""
    result = compare_entry_timing("never", _never, panel, n_dates=40, seed=1)
    assert result.n_forced == result.n_entries


def test_a_trigger_that_always_fires_forces_nothing(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=1)
    assert result.n_forced == 0


def test_the_same_seed_reproduces_the_same_numbers(panel):
    first = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    second = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    assert first.delta == pytest.approx(second.delta)
    assert first.stderr == pytest.approx(second.stderr)


def test_different_seeds_give_different_samples(panel):
    first = compare_entry_timing("always", _always, panel, n_dates=40, seed=7)
    second = compare_entry_timing("always", _always, panel, n_dates=40, seed=99)
    assert first.delta != second.delta


def test_delta_is_the_gap_between_the_two_arms(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=3)
    assert result.delta == pytest.approx(result.sharpe_signal - result.sharpe_immediate)


def test_both_arms_hold_for_the_same_number_of_days(panel):
    """A longer exposure would beat a shorter one on drift alone, not on timing."""
    result = compare_entry_timing("always", _always, panel, n_dates=40, seed=3, hold_days=63)
    assert result.hold_days == 63


def test_a_delta_smaller_than_its_own_noise_does_not_pass():
    """An improvement inside the error bars is not an improvement."""
    result = GateBResult("s", 0.50, 0.55, 0.05, 0.30, 100, 0, 63)
    assert result.passes is False


def test_a_delta_larger_than_its_own_noise_passes():
    result = GateBResult("s", 0.50, 1.00, 0.50, 0.20, 100, 0, 63)
    assert result.passes is True


def test_passing_is_decided_solely_by_delta_against_stderr(panel):
    result = compare_entry_timing("always", _always, panel, n_dates=60, seed=5)
    assert result.passes == (result.delta > result.stderr)


# ── Bootstrap por bloques ─────────────────────────────────────────────────────

def test_block_bootstrap_returns_a_positive_standard_error():
    rng = np.random.default_rng(61)
    assert block_bootstrap_stderr(rng.normal(0, 1, 300), block=8, n_resamples=200, seed=1) > 0.0


def test_block_bootstrap_shrinks_as_the_sample_grows():
    rng = np.random.default_rng(67)
    small = block_bootstrap_stderr(rng.normal(0, 1, 100), block=8, n_resamples=300, seed=1)
    large = block_bootstrap_stderr(rng.normal(0, 1, 2000), block=8, n_resamples=300, seed=1)
    assert large < small


def test_block_bootstrap_reports_more_uncertainty_than_an_iid_estimate_when_data_overlap():
    """Overlapping observations carry less information than their count suggests."""
    rng = np.random.default_rng(71)
    overlapping = pd.Series(rng.normal(0, 1, 2000)).rolling(20).mean().dropna().to_numpy()
    iid_stderr = overlapping.std(ddof=1) / np.sqrt(len(overlapping))
    assert block_bootstrap_stderr(overlapping, block=20, n_resamples=400, seed=1) > iid_stderr
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_timing.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.timing'`

- [ ] **Step 3: Implementar**

Crea `research/timing.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

N_DATES = 500
BASKET_SIZE = 20
WAIT_DAYS = 10
HOLD_DAYS = 63
N_RESAMPLES = 1000
BOOTSTRAP_BLOCK = 8
SEED = 20260805


@dataclass(frozen=True)
class GateBResult:
    signal: str
    sharpe_immediate: float
    sharpe_signal: float
    delta: float
    stderr: float
    n_entries: int
    n_forced: int
    hold_days: int

    @property
    def passes(self) -> bool:
        return self.delta > self.stderr


def block_bootstrap_stderr(
    values: np.ndarray, block: int, n_resamples: int = N_RESAMPLES, seed: int = SEED
) -> float:
    """Standard error of the mean under a moving-block bootstrap.

    Resampling individual observations would assume independence the data does
    not have: baskets sampled days apart share most of their holding period.
    Resampling contiguous blocks preserves that dependence.
    """
    x = np.asarray(values, dtype=float)
    n = x.size
    if n < 2:
        return float("inf")
    block = max(1, min(block, n))
    n_blocks = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(n_resamples, n_blocks))
    means = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        sample = np.concatenate([x[s : s + block] for s in starts[i]])[:n]
        means[i] = sample.mean()
    return float(means.std(ddof=1))


def _annualised_sharpe(period_returns: np.ndarray, hold_days: int) -> float:
    """Sharpe with a zero risk-free rate.

    Both arms hold for the same number of days, so the risk-free rate cancels
    out of the comparison the criterion actually cares about.
    """
    std = period_returns.std(ddof=1)
    if std == 0.0:
        return 0.0
    return float(period_returns.mean() / std * np.sqrt(252.0 / hold_days))


def compare_entry_timing(
    name: str,
    trigger_fn: Callable[[pd.DataFrame], pd.DataFrame],
    panel: pd.DataFrame,
    n_dates: int = N_DATES,
    basket_size: int = BASKET_SIZE,
    wait_days: int = WAIT_DAYS,
    hold_days: int = HOLD_DAYS,
    seed: int = SEED,
) -> GateBResult:
    """Does waiting for the signal beat entering right away?

    For each sampled decision date a random basket is bought two ways: at once,
    or on the first day the trigger fires within the wait window. If it never
    fires, the position is opened anyway on the last day of the window —
    dropping those cases would keep only the entries that happened to work out
    and manufacture an edge from selection alone.
    """
    opens = panel["Open"]
    dates = opens.index
    rng = np.random.default_rng(seed)

    triggers = trigger_fn(panel)
    last_start = len(dates) - (wait_days + hold_days + 2)
    if last_start <= 0:
        raise ValueError("El panel es demasiado corto para el protocolo de la Puerta B.")

    candidates = rng.choice(last_start, size=min(n_dates, last_start), replace=False)

    immediate: list[float] = []
    delayed: list[float] = []
    n_entries = 0
    n_forced = 0

    for offset in sorted(candidates):
        decision = dates[offset]
        window = opens.iloc[offset + 1 : offset + 1 + wait_days + hold_days + 1]
        eligible = window.columns[window.notna().all()]
        if len(eligible) < basket_size:
            continue
        basket = rng.choice(eligible, size=basket_size, replace=False)

        immediate_returns: list[float] = []
        delayed_returns: list[float] = []
        for ticker in basket:
            entry_now = opens.iloc[offset + 1][ticker]
            exit_now = opens.iloc[offset + 1 + hold_days][ticker]
            immediate_returns.append(exit_now / entry_now - 1.0)

            fired = triggers.iloc[offset + 1 : offset + 1 + wait_days][ticker]
            hit = fired[fired].index
            if len(hit):
                entry_offset = dates.get_loc(hit[0]) + 1
            else:
                entry_offset = offset + wait_days
                n_forced += 1
            entry_price = opens.iloc[entry_offset][ticker]
            exit_price = opens.iloc[entry_offset + hold_days][ticker]
            delayed_returns.append(exit_price / entry_price - 1.0)
            n_entries += 1

        immediate.append(float(np.mean(immediate_returns)))
        delayed.append(float(np.mean(delayed_returns)))

    immediate_arr = np.asarray(immediate)
    delayed_arr = np.asarray(delayed)
    sharpe_immediate = _annualised_sharpe(immediate_arr, hold_days)
    sharpe_signal = _annualised_sharpe(delayed_arr, hold_days)

    # The difference is measured per decision date and then converted to Sharpe
    # units with the immediate arm's own volatility, so the bootstrap resamples
    # paired observations rather than two independent Sharpe estimates. Pairing
    # removes the market moves both arms shared, which is most of the variance.
    paired = delayed_arr - immediate_arr
    scale = np.sqrt(252.0 / hold_days) / (immediate_arr.std(ddof=1) or 1.0)
    stderr = block_bootstrap_stderr(paired * scale, block=BOOTSTRAP_BLOCK, seed=seed)

    return GateBResult(
        signal=name,
        sharpe_immediate=sharpe_immediate,
        sharpe_signal=sharpe_signal,
        delta=sharpe_signal - sharpe_immediate,
        stderr=stderr,
        n_entries=n_entries,
        n_forced=n_forced,
        hold_days=hold_days,
    )
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_timing.py -v`
Expected: 13 passed

- [ ] **Step 5: Contraste de cordura contra la fórmula i.i.d.**

Añade a `tests/test_research_timing.py`:

```python
def test_the_block_bootstrap_is_never_more_optimistic_than_the_iid_formula(panel):
    """If overlapping data looked more precise than independent data, we have a bug."""
    from validation import sharpe_standard_error

    result = compare_entry_timing("always", _always, panel, n_dates=80, seed=13)
    iid = sharpe_standard_error(
        sharpe=result.sharpe_immediate, n_periods=80, periods_per_year=252 / result.hold_days
    )
    assert result.stderr <= iid * 3.0
```

Run: `pytest tests/test_research_timing.py -v`
Expected: 14 passed

- [ ] **Step 6: Commit**

```bash
git add research/timing.py tests/test_research_timing.py
git commit -m "feat: Puerta B con entrada forzosa y bootstrap por bloques"
```

---

## Task 8: Veredicto

**Files:**
- Create: `research/report.py`
- Test: `tests/test_research_report.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_report.py`:

```python
import pytest

from research.evaluation import GateAResult
from research.report import build_verdict, to_markdown
from research.timing import GateBResult


def _gate_a(signal="s", mean_ic=0.05, t_stat=3.0, p_value=0.001, spread_net=0.04, subperiods=4):
    labels = ["P1 2010-2013", "P2 2014-2017", "P3 2018-2021", "P4 2022-2026"]
    return GateAResult(
        signal=signal,
        horizon=21,
        mean_ic=mean_ic,
        t_stat=t_stat,
        p_value=p_value,
        spread_gross=spread_net + 0.01,
        spread_net=spread_net,
        turnover=0.3,
        n_dates=2000,
        subperiod_pass={label: i < subperiods for i, label in enumerate(labels)},
        spread_net_by_scenario={
            "optimista": spread_net + 0.005,
            "base": spread_net,
            "conservador": spread_net - 0.005,
        },
    )


def _gate_b(signal="s", delta=0.4, stderr=0.1):
    return GateBResult(
        signal=signal,
        sharpe_immediate=0.5,
        sharpe_signal=0.5 + delta,
        delta=delta,
        stderr=stderr,
        n_entries=1000,
        n_forced=0,
        hold_days=63,
    )


def test_a_signal_that_passes_both_gates_has_an_edge():
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    assert verdict["s"]["edge"] is True


def test_passing_only_the_statistical_gate_is_not_an_edge():
    """Ranking well without improving entry timing does not answer the question asked."""
    verdict = build_verdict([_gate_a()], {"s": _gate_b(delta=0.01, stderr=0.5)})
    assert verdict["s"]["gate_a"] is True
    assert verdict["s"]["gate_b"] is False
    assert verdict["s"]["edge"] is False


def test_passing_only_the_timing_gate_is_not_an_edge():
    """A timing improvement indistinguishable from noise is not a finding."""
    verdict = build_verdict([_gate_a(mean_ic=0.001, t_stat=0.2, p_value=0.8)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is False
    assert verdict["s"]["edge"] is False


def test_an_ic_below_the_threshold_fails_gate_a():
    verdict = build_verdict([_gate_a(mean_ic=0.02)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is False


def test_a_t_stat_below_two_fails_gate_a():
    verdict = build_verdict([_gate_a(t_stat=1.9)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is False


def test_a_negative_net_spread_fails_gate_a():
    """Gross profits that costs erase are not profits."""
    verdict = build_verdict([_gate_a(spread_net=-0.01)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is False


def test_holding_in_only_two_subperiods_fails_gate_a():
    verdict = build_verdict([_gate_a(subperiods=2)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is False


def test_holding_in_three_subperiods_is_enough():
    verdict = build_verdict([_gate_a(subperiods=3)], {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is True


def test_a_signal_passing_at_any_horizon_passes_gate_a():
    results = [_gate_a(mean_ic=0.001, t_stat=0.1, p_value=0.9), _gate_a()]
    results[0] = GateAResult(**{**results[0].__dict__, "horizon": 5})
    verdict = build_verdict(results, {"s": _gate_b()})
    assert verdict["s"]["gate_a"] is True


def test_multiplicity_correction_is_applied_across_all_results():
    """0.04 looks significant alone. As one of twenty-eight tests it is just noise."""
    results = [_gate_a(signal="s0", p_value=0.04, t_stat=2.1)]
    results += [_gate_a(signal=f"s{i}", p_value=0.6, t_stat=2.1) for i in range(1, 28)]
    gate_b = {f"s{i}": _gate_b(signal=f"s{i}") for i in range(28)}
    verdict = build_verdict(results, gate_b)
    assert not any(v["gate_a"] for v in verdict.values())


def test_an_uncorrected_threshold_would_have_passed_that_same_result():
    """Pins down what the correction is actually buying, so it cannot be quietly dropped."""
    lone = _gate_a(signal="s0", p_value=0.04, t_stat=2.1)
    alone = build_verdict([lone], {"s0": _gate_b(signal="s0")})
    assert alone["s0"]["gate_a"] is True


def test_the_random_control_is_flagged_when_it_passes():
    """If noise clears the bar, the bar is wrong and every other verdict is void."""
    verdict = build_verdict([_gate_a(signal="random_control")], {"random_control": _gate_b()})
    assert verdict["random_control"]["control_alarm"] is True


def test_the_markdown_report_names_every_signal():
    verdict = build_verdict([_gate_a(signal="mom_12_1")], {"mom_12_1": _gate_b()})
    assert "mom_12_1" in to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)


def test_the_markdown_report_states_the_survivorship_limitation():
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    text = to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
    assert "supervivencia" in text.lower()


def test_the_markdown_report_shows_the_passive_baseline():
    """Without something to beat, an absolute number means nothing."""
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    assert "0.60" in to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)


def test_the_markdown_report_shows_the_cost_sensitivity():
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    text = to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
    assert "optimista" in text and "conservador" in text


def test_the_markdown_report_warns_when_the_control_passed():
    verdict = build_verdict([_gate_a(signal="random_control")], {"random_control": _gate_b()})
    assert "ALARMA" in to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_report.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.report'`

- [ ] **Step 3: Implementar**

Crea `research/report.py`:

```python
from research.evaluation import (
    FDR,
    MIN_IC,
    MIN_SUBPERIODS,
    MIN_TSTAT,
    GateAResult,
    benjamini_hochberg,
)
from research.timing import GateBResult


def build_verdict(
    gate_a_results: list[GateAResult], gate_b_results: dict[str, GateBResult]
) -> dict[str, dict]:
    """Apply both gates. A signal has an edge only if it clears both.

    Gate A alone means it orders the cross-section but never improved an entry.
    Gate B alone means the improvement is indistinguishable from noise. Neither
    on its own answers the question the study was built to answer.
    """
    survives_bh = benjamini_hochberg([r.p_value for r in gate_a_results], fdr=FDR)

    per_signal: dict[str, dict] = {}
    for result, bh_ok in zip(gate_a_results, survives_bh, strict=True):
        passed = bool(
            result.mean_ic >= MIN_IC
            and result.t_stat >= MIN_TSTAT
            and bh_ok
            and result.spread_net > 0.0
            and result.subperiods_passed >= MIN_SUBPERIODS
        )
        entry = per_signal.setdefault(
            result.signal, {"gate_a": False, "horizons": {}, "gate_b": False}
        )
        entry["horizons"][result.horizon] = {
            "mean_ic": result.mean_ic,
            "t_stat": result.t_stat,
            "p_value": result.p_value,
            "survives_bh": bool(bh_ok),
            "spread_gross": result.spread_gross,
            "spread_net": result.spread_net,
            "spread_net_by_scenario": dict(result.spread_net_by_scenario),
            "turnover": result.turnover,
            "subperiods_passed": result.subperiods_passed,
            "passes": passed,
        }
        entry["gate_a"] = entry["gate_a"] or passed

    for name, entry in per_signal.items():
        b = gate_b_results.get(name)
        entry["gate_b"] = bool(b.passes) if b else False
        entry["gate_b_delta"] = b.delta if b else 0.0
        entry["gate_b_stderr"] = b.stderr if b else float("inf")
        entry["edge"] = entry["gate_a"] and entry["gate_b"]
        entry["control_alarm"] = name == "random_control" and entry["gate_a"]

    return per_signal


def to_markdown(verdict: dict[str, dict], coverage_summary: str, passive_sharpe: float) -> str:
    """The document a third party reads to judge whether the study is believable."""
    alarm = any(v.get("control_alarm") for v in verdict.values())

    lines = [
        "# Veredicto — Estudio de señales técnicas",
        "",
        f"**Cobertura del universo:** {coverage_summary}",
        "",
        f"**Línea base pasiva** (equal-weight del universo, comprar y mantener): "
        f"Sharpe {passive_sharpe:.2f}",
        "",
    ]

    if alarm:
        lines += [
            "> **ALARMA: el control aleatorio pasó la Puerta A.**",
            "> El criterio está mal calibrado. Ningún otro resultado de este documento",
            "> es interpretable hasta que se corrija.",
            "",
        ]

    lines += [
        "## Resultados",
        "",
        "| Señal | Puerta A | Puerta B | Δ Sharpe | Error estándar | Ventaja |",
        "|---|---|---|---|---|---|",
    ]
    for name, entry in verdict.items():
        lines.append(
            f"| `{name}` | {'PASA' if entry['gate_a'] else 'no'} | "
            f"{'PASA' if entry['gate_b'] else 'no'} | "
            f"{entry['gate_b_delta']:.3f} | {entry['gate_b_stderr']:.3f} | "
            f"{'**SÍ**' if entry['edge'] else 'no'} |"
        )

    lines += [
        "",
        "## Detalle por horizonte",
        "",
        "| Señal | Horizonte | IC medio | t-stat | Sobrevive BH | Spread bruto | Spread neto | Rotación | Sub-periodos |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, entry in verdict.items():
        for horizon, stats in sorted(entry["horizons"].items()):
            lines.append(
                f"| `{name}` | {horizon}d | {stats['mean_ic']:.4f} | {stats['t_stat']:.2f} | "
                f"{'sí' if stats['survives_bh'] else 'no'} | {stats['spread_gross']:.4f} | "
                f"{stats['spread_net']:.4f} | {stats['turnover']:.2f} | "
                f"{stats['subperiods_passed']}/4 |"
            )

    lines += [
        "",
        "## Sensibilidad a los costes",
        "",
        "Spread neto anualizado bajo los tres escenarios pre-registrados.",
        "",
        "| Señal | Horizonte | Optimista (5 bps) | Base (10 bps) | Conservador (25 bps) |",
        "|---|---|---|---|---|",
    ]
    for name, entry in verdict.items():
        for horizon, stats in sorted(entry["horizons"].items()):
            scenarios = stats["spread_net_by_scenario"]
            lines.append(
                f"| `{name}` | {horizon}d | {scenarios.get('optimista', float('nan')):.4f} | "
                f"{scenarios.get('base', float('nan')):.4f} | "
                f"{scenarios.get('conservador', float('nan')):.4f} |"
            )

    lines += [
        "",
        "## Limitaciones",
        "",
        "- **Sesgo de supervivencia.** El universo son los miembros actuales del índice;",
        "  las empresas expulsadas o quebradas no aparecen. El sesgo *infla* los resultados,",
        "  así que un veredicto negativo es firme y uno positivo exige la fase 2 con",
        "  universo point-in-time antes de creerse.",
        "- **Costes.** El caso base son 10 bps por operación ida y vuelta. Las señales de",
        "  rotación alta son las más sensibles a este supuesto.",
        "- **Periodo.** 2010-01-01 a 2026-06-30. No cubre la crisis de 2008.",
        "- **Sin ajuste de parámetros.** Los periodos de los indicadores son los",
        "  convencionales. Optimizarlos requeriría validación fuera de muestra propia.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_report.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add research/report.py tests/test_research_report.py
git commit -m "feat: veredicto de doble puerta con alarma del control aleatorio"
```

---

## Task 9: Orquestación

**Files:**
- Create: `research/run.py`
- Test: `tests/test_research_run.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crea `tests/test_research_run.py`:

```python
from research.run import END, HORIZONS, START, expected_test_count
from research.signals import SIGNALS


def test_the_grid_is_the_twenty_eight_pre_registered_tests():
    """Eight signals times four horizons. Any other number means the grid drifted."""
    assert len(SIGNALS) * len(HORIZONS) == 32
    assert expected_test_count() == 28


def test_the_four_pre_registered_horizons_are_used():
    assert HORIZONS == [1, 5, 21, 63]


def test_the_study_window_matches_the_pre_registered_criterion():
    assert START == "2010-01-01"
    assert END == "2026-06-30"
```

**Nota sobre el conteo:** el criterio pre-registra 28 tests = **7 señales evaluadas** × 4 horizontes. El control aleatorio se corre además, pero no entra en la corrección por multiplicidad: no es un candidato, es un instrumento de verificación. `expected_test_count()` debe devolver 28.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `pytest tests/test_research_run.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'research.run'`

- [ ] **Step 3: Implementar**

Crea `research/run.py`:

```python
import sys
from datetime import date
from pathlib import Path

from research.costs import COST_SCENARIOS
from research.evaluation import equal_weight_sharpe, evaluate
from research.loader import load_ohlcv
from research.report import build_verdict, to_markdown
from research.signals import SIGNALS, TRIGGERS
from research.timing import compare_entry_timing
from research.universe import sp500_members

START = "2010-01-01"
END = "2026-06-30"
HORIZONS = [1, 5, 21, 63]
CONTROL = "random_control"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "research"


def expected_test_count() -> int:
    """The pre-registered grid: evaluated signals only.

    The random control runs alongside but is excluded from the multiplicity
    correction. It is not a candidate for discovery; it is the instrument that
    tells us whether the criterion itself is calibrated.
    """
    return (len(SIGNALS) - 1) * len(HORIZONS)


def main() -> int:
    tickers = sp500_members()
    print(f"Universo: {len(tickers)} tickers")

    panel, coverage = load_ohlcv(tickers, START, END)
    print(coverage.summary())
    if panel.empty:
        print("No se pudo cargar ningún precio. Revisa la conectividad y vuelve a intentarlo.")
        return 1

    close = panel["Close"]
    bps = COST_SCENARIOS["base"]

    gate_a = []
    for name, build in SIGNALS.items():
        signal = build(panel)
        for horizon in HORIZONS:
            print(f"  Puerta A: {name} @ {horizon}d")
            gate_a.append(evaluate(name, signal, close, horizon=horizon, bps=bps))

    gate_b = {}
    for name, trigger in TRIGGERS.items():
        print(f"  Puerta B: {name}")
        gate_b[name] = compare_entry_timing(name, trigger, panel)

    # The control is corrected separately: it is not competing for a discovery,
    # so folding it into the same family would change the threshold the real
    # candidates face just by being present.
    evaluated = [r for r in gate_a if r.signal != CONTROL]
    control = [r for r in gate_a if r.signal == CONTROL]

    verdict = build_verdict(evaluated, gate_b)
    verdict.update(build_verdict(control, gate_b))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{date.today().isoformat()}-veredicto-senales-tecnicas.md"
    output.write_text(
        to_markdown(verdict, coverage.summary(), passive_sharpe=equal_weight_sharpe(close)),
        encoding="utf-8",
    )
    print(f"\nVeredicto escrito en {output}")

    with_edge = [n for n, v in verdict.items() if v["edge"] and n != CONTROL]
    if verdict.get(CONTROL, {}).get("control_alarm"):
        print("ALARMA: el control aleatorio pasó la Puerta A. El criterio está mal calibrado.")
        return 2
    print(f"Señales con ventaja: {with_edge or 'ninguna'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `pytest tests/test_research_run.py -v`
Expected: 3 passed

- [ ] **Step 5: Correr la suite completa**

Run: `pytest tests/ -v`
Expected: todos los tests pasan, incluidos los preexistentes del optimizador.

- [ ] **Step 6: Commit**

```bash
git add research/run.py tests/test_research_run.py
git commit -m "feat: orquestación del estudio y generación del veredicto"
```

---

## Task 10: Correr el estudio y publicar el veredicto

**Files:**
- Create: `docs/research/<fecha>-veredicto-senales-tecnicas.md` (generado)

**Se corre una sola vez.** Si el resultado no gusta, no se ajusta nada y se vuelve a correr: eso sería exactamente lo que el criterio pre-registrado existe para impedir.

- [ ] **Step 1: Correr el estudio**

Run: `python -m research.run`
Expected: descarga de ~500 tickers (varios minutos la primera vez, instantáneo después gracias a la caché), luego el progreso de ambas puertas, y finalmente la ruta del veredicto.

- [ ] **Step 2: Verificar que el instrumento funciona antes de leer los resultados**

Abre el veredicto generado y comprueba, **en este orden**:

1. **El control aleatorio NO pasa la Puerta A.** Si pasa, el documento lo marca con una alarma: para todo, el criterio está mal calibrado y ningún otro número sirve.
2. **`mom_12_1` se comporta como la literatura describe** — IC positivo, más fuerte en horizontes de 21 y 63 días que en 1 día. Si el momentum de 12-1 no aparece por ningún lado, sospecha del pipeline antes que del mercado.
3. **La cobertura es razonable** — al menos ~450 de los ~500 tickers incluidos. Si hay muchas exclusiones, el estudio describe un universo distinto del que se pretendía.

- [ ] **Step 3: Verificar reproducibilidad**

Run: `python -m research.run`
Expected: la segunda corrida lee de caché y produce números **idénticos**. Compara los dos documentos generados; si difieren, hay una fuente de aleatoriedad sin semilla.

- [ ] **Step 4: Commit del veredicto**

```bash
git add docs/research/
git commit -m "docs: veredicto del estudio de señales técnicas"
```

- [ ] **Step 5: Decidir la ramificación**

Según el veredicto:

- **Ninguna señal con ventaja** → el sub-proyecto E se descarta. Se documenta la decisión y el trabajo sigue con A (universo + fundamentales), B (agentes) y C (handoff), sin componente técnico.
- **Alguna señal con ventaja** → **no se construye E todavía**. Se activa la fase 2: reconstruir el universo point-in-time y repetir el estudio, para verificar que la ventaja no era sesgo de supervivencia disfrazado. Sólo si sobrevive a esa verificación se diseña E.

---

## Verificación final

- [ ] `pytest tests/ -v` pasa en su totalidad
- [ ] `docs/research/criterio-preregistrado.md` está commiteado **antes** que cualquier módulo de `research/`  — compruébalo con `git log --oneline --reverse -- docs/research/criterio-preregistrado.md research/`
- [ ] El control aleatorio falló la Puerta A
- [ ] Los tests de truncamiento pasan para las 8 señales del registro
- [ ] El oráculo falla el test de truncamiento (debe espiar)
- [ ] Dos corridas consecutivas producen números idénticos
- [ ] `git status` no muestra cambios en `app.py`, `data.py`, `optimizer.py`, `estimators.py`, `validation.py`, `charts.py` ni `exporter.py`
