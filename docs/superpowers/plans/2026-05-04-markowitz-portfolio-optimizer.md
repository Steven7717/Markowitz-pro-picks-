# Markowitz Pro Picks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit web app that receives stock tickers and an investment horizon, then returns the Max Sharpe Ratio portfolio weights with full visualizations and Excel/PDF export.

**Architecture:** Five focused modules — `data.py` fetches prices from yfinance, `optimizer.py` runs Markowitz math, `charts.py` builds Plotly figures, `exporter.py` generates Excel and PDF, and `app.py` wires them together as a Streamlit UI. No business logic lives in `app.py`.

**Tech Stack:** Python 3.11+, Streamlit, yfinance, NumPy, SciPy, Pandas, Plotly, fpdf2, openpyxl, kaleido, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `data.py` | `HORIZON_CONFIG`, `parse_tickers()`, `fetch_market_data()` with `@st.cache_data` |
| `optimizer.py` | `portfolio_metrics()`, `simulate_portfolios()`, `optimize_max_sharpe()`, `equal_weight_portfolio()`, `risk_contribution()`, `validate_constraints()` |
| `charts.py` | `plot_efficient_frontier()`, `plot_weights_pie()`, `plot_correlation_heatmap()`, `plot_comparison()` |
| `exporter.py` | `to_excel()`, `to_pdf()` |
| `app.py` | Streamlit UI — config panel, KPIs, alerts, charts, table, download buttons |
| `requirements.txt` | Pinned dependencies |
| `.streamlit/config.toml` | Dark theme |
| `tests/test_data.py` | Tests for parse_tickers and HORIZON_CONFIG |
| `tests/test_optimizer.py` | Tests for all math functions |
| `tests/test_exporter.py` | Tests for Excel output structure |

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.streamlit/config.toml`
- Create: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
streamlit>=1.32.0
yfinance>=0.2.40
numpy>=1.26.0
scipy>=1.12.0
pandas>=2.2.0
plotly>=5.20.0
fpdf2>=2.7.9
openpyxl>=3.1.2
kaleido>=0.2.1
pytest>=8.0.0
```

- [ ] **Step 2: Create `.streamlit/config.toml`**

```toml
[theme]
base = "dark"
primaryColor = "#7c83fd"
backgroundColor = "#0f1117"
secondaryBackgroundColor = "#1e2130"
textColor = "#cccccc"
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
.superpowers/
*.xlsx
*.pdf
```

- [ ] **Step 4: Create `tests/__init__.py`** (empty file)

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error. If `kaleido` fails on Windows, try `pip install kaleido==0.2.1`.

- [ ] **Step 6: Commit**

```bash
git init
git add requirements.txt .streamlit/config.toml .gitignore tests/__init__.py
git commit -m "chore: project scaffold"
```

---

## Task 2: `data.py` — HORIZON_CONFIG and parse_tickers

**Files:**
- Create: `data.py`
- Create: `tests/test_data.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_data.py`:

```python
from data import parse_tickers, HORIZON_CONFIG, DEFAULT_HORIZON


def test_parse_tickers_comma_separated():
    assert parse_tickers("AAPL, MSFT, GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_space_separated():
    assert parse_tickers("AAPL MSFT GOOGL") == ["AAPL", "MSFT", "GOOGL"]


def test_parse_tickers_mixed_delimiters():
    assert parse_tickers("AAPL, MSFT GOOGL,AMZN") == ["AAPL", "MSFT", "GOOGL", "AMZN"]


def test_parse_tickers_converts_to_uppercase():
    assert parse_tickers("aapl msft") == ["AAPL", "MSFT"]


def test_parse_tickers_empty_string():
    assert parse_tickers("") == []


def test_parse_tickers_only_whitespace():
    assert parse_tickers("   ") == []


def test_horizon_config_has_all_six_horizons():
    expected = {"1 Semana", "1 Mes", "3 Meses", "6 Meses", "1 Año", "3 Años"}
    assert set(HORIZON_CONFIG.keys()) == expected


def test_horizon_config_entries_have_required_fields():
    for key, cfg in HORIZON_CONFIG.items():
        assert "period" in cfg, f"{key} missing 'period'"
        assert "interval" in cfg, f"{key} missing 'interval'"
        assert "periods_per_year" in cfg, f"{key} missing 'periods_per_year'"
        assert cfg["periods_per_year"] in (12, 52, 252), f"{key} has unexpected periods_per_year"


def test_default_horizon_exists_in_config():
    assert DEFAULT_HORIZON in HORIZON_CONFIG
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_data.py -v
```

Expected: `ModuleNotFoundError: No module named 'data'`

- [ ] **Step 3: Implement `HORIZON_CONFIG` and `parse_tickers` in `data.py`**

Create `data.py`:

```python
import re
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

HORIZON_CONFIG: dict[str, dict] = {
    "1 Semana": {"period": "1y",  "interval": "1d",  "periods_per_year": 252},
    "1 Mes":    {"period": "2y",  "interval": "1d",  "periods_per_year": 252},
    "3 Meses":  {"period": "3y",  "interval": "1wk", "periods_per_year": 52},
    "6 Meses":  {"period": "5y",  "interval": "1wk", "periods_per_year": 52},
    "1 Año":    {"period": "10y", "interval": "1mo", "periods_per_year": 12},
    "3 Años":   {"period": "15y", "interval": "1mo", "periods_per_year": 12},
}

DEFAULT_HORIZON = "1 Mes"
RF_FALLBACK = 0.05


def parse_tickers(raw: str) -> list[str]:
    tokens = re.split(r"[,\s]+", raw.strip())
    return [t.upper() for t in tokens if t]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_data.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data.py tests/test_data.py
git commit -m "feat: add HORIZON_CONFIG and parse_tickers"
```

---

## Task 3: `data.py` — fetch_market_data

**Files:**
- Modify: `data.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Add tests for fetch_market_data using mocks**

Append to `tests/test_data.py`:

```python
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from data import fetch_market_data, RF_FALLBACK


def _make_mock_download(tickers: list[str], n_rows: int = 100) -> pd.DataFrame:
    """Build a fake yfinance MultiIndex DataFrame."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=n_rows)
    all_tickers = tickers + ["^IRX", "^GSPC"]
    arrays = [["Close"] * len(all_tickers), all_tickers]
    cols = pd.MultiIndex.from_arrays(arrays, names=["Price", "Ticker"])
    data = rng.uniform(100, 200, size=(n_rows, len(all_tickers)))
    # Make ^IRX look like a realistic annualized rate (e.g. 5.25)
    irx_idx = all_tickers.index("^IRX")
    data[:, irx_idx] = 5.25
    return pd.DataFrame(data, index=dates, columns=cols)


@patch("data.yf.download")
def test_fetch_market_data_returns_expected_keys(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL", "MSFT"])
    result = fetch_market_data(("AAPL", "MSFT"), "1 Mes")
    assert "returns" in result
    assert "rf_rate" in result
    assert "benchmark_returns" in result
    assert "invalid_tickers" in result
    assert "periods_per_year" in result
    assert "valid_tickers" in result


@patch("data.yf.download")
def test_fetch_market_data_rf_rate_converted_to_period(mock_dl):
    mock_dl.return_value = _make_mock_download(["AAPL"])
    result = fetch_market_data(("AAPL", "MSFT"), "1 Mes")
    # ^IRX = 5.25% annual → per-day ≈ 5.25/100/252
    expected_rf = 5.25 / 100 / 252
    assert abs(result["rf_rate"] - expected_rf) < 1e-6


@patch("data.yf.download")
def test_fetch_market_data_uses_fallback_when_irx_missing(mock_dl):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-01", periods=100)
    cols = pd.MultiIndex.from_arrays(
        [["Close", "Close", "Close"], ["AAPL", "^IRX", "^GSPC"]],
        names=["Price", "Ticker"],
    )
    data = rng.uniform(100, 200, size=(100, 3))
    data[:, 1] = np.nan  # ^IRX all NaN
    df = pd.DataFrame(data, index=dates, columns=cols)
    mock_dl.return_value = df
    result = fetch_market_data(("AAPL",), "1 Mes")
    assert result["rf_rate"] == RF_FALLBACK / 252
    assert result.get("rf_available") is False
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_data.py::test_fetch_market_data_returns_expected_keys -v
```

Expected: FAIL — `fetch_market_data` not defined yet.

- [ ] **Step 3: Implement `fetch_market_data` in `data.py`**

Append to `data.py` (after `parse_tickers`):

```python
@st.cache_data(ttl=3600)
def fetch_market_data(tickers: tuple[str, ...], horizon: str) -> dict:
    cfg = HORIZON_CONFIG[horizon]
    period = cfg["period"]
    interval = cfg["interval"]
    periods_per_year = cfg["periods_per_year"]

    all_tickers = list(tickers) + ["^IRX", "^GSPC"]
    raw = yf.download(
        all_tickers,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

    prices = prices.dropna(how="all")

    invalid = [t for t in tickers if t not in prices.columns or prices[t].isna().all()]
    valid_tickers = [t for t in tickers if t not in invalid]

    if not valid_tickers:
        return {
            "returns": pd.DataFrame(),
            "rf_rate": RF_FALLBACK / periods_per_year,
            "rf_available": False,
            "benchmark_returns": pd.Series(dtype=float),
            "invalid_tickers": list(invalid),
            "periods_per_year": periods_per_year,
            "valid_tickers": [],
        }

    rf_annual = RF_FALLBACK
    rf_available = True
    if "^IRX" in prices.columns and not prices["^IRX"].isna().all():
        rf_annual = prices["^IRX"].dropna().iloc[-1] / 100.0
    else:
        rf_available = False

    rf_rate = rf_annual / periods_per_year

    benchmark_returns = pd.Series(dtype=float)
    if "^GSPC" in prices.columns and not prices["^GSPC"].isna().all():
        benchmark_returns = prices["^GSPC"].pct_change().dropna()

    asset_prices = prices[valid_tickers].dropna(how="all")
    returns = asset_prices.pct_change().dropna()

    return {
        "returns": returns,
        "rf_rate": rf_rate,
        "rf_available": rf_available,
        "benchmark_returns": benchmark_returns,
        "invalid_tickers": list(invalid),
        "periods_per_year": periods_per_year,
        "valid_tickers": valid_tickers,
    }
```

- [ ] **Step 4: Run all data tests**

```bash
pytest tests/test_data.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data.py tests/test_data.py
git commit -m "feat: implement fetch_market_data with caching and rf fallback"
```

---

## Task 4: `optimizer.py` — portfolio_metrics and validate_constraints

**Files:**
- Create: `optimizer.py`
- Create: `tests/test_optimizer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_optimizer.py`:

```python
import numpy as np
import pandas as pd
import pytest
from optimizer import portfolio_metrics, validate_constraints, risk_contribution


@pytest.fixture
def synthetic_returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    data = rng.normal(
        loc=[0.001, 0.0008, 0.0012],
        scale=[0.015, 0.012, 0.018],
        size=(500, 3),
    )
    return pd.DataFrame(data, columns=["A", "B", "C"])


def test_portfolio_metrics_returns_three_floats(synthetic_returns):
    w = np.array([1/3, 1/3, 1/3])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    ret, vol, sharpe = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0001, periods_per_year=252)
    assert isinstance(ret, float)
    assert isinstance(vol, float)
    assert isinstance(sharpe, float)


def test_portfolio_metrics_vol_is_positive(synthetic_returns):
    w = np.array([0.5, 0.3, 0.2])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    _, vol, _ = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0001, periods_per_year=252)
    assert vol > 0


def test_portfolio_metrics_zero_rf_gives_positive_sharpe(synthetic_returns):
    w = np.array([1/3, 1/3, 1/3])
    mean_ret = synthetic_returns.mean().values
    cov = synthetic_returns.cov().values
    _, _, sharpe = portfolio_metrics(w, mean_ret, cov, rf_rate=0.0, periods_per_year=252)
    assert isinstance(sharpe, float)


def test_risk_contribution_sums_to_one(synthetic_returns):
    w = np.array([0.4, 0.3, 0.3])
    cov = synthetic_returns.cov().values
    contrib = risk_contribution(w, cov)
    assert abs(contrib.sum() - 1.0) < 1e-6


def test_risk_contribution_length_matches_assets(synthetic_returns):
    w = np.array([0.4, 0.3, 0.3])
    cov = synthetic_returns.cov().values
    contrib = risk_contribution(w, cov)
    assert len(contrib) == 3


def test_validate_constraints_feasible():
    ok, msg = validate_constraints(n_assets=5, weight_min=0.05, weight_max=0.40)
    assert ok is True


def test_validate_constraints_min_too_high():
    ok, msg = validate_constraints(n_assets=3, weight_min=0.40, weight_max=1.0)
    assert ok is False
    assert "infactible" in msg.lower()


def test_validate_constraints_max_too_low():
    ok, msg = validate_constraints(n_assets=5, weight_min=0.0, weight_max=0.15)
    assert ok is False
    assert "infactible" in msg.lower()


def test_validate_constraints_exactly_feasible_min():
    # 3 assets, min=1/3 → 3 * 1/3 = 1.0 exactly
    ok, _ = validate_constraints(n_assets=3, weight_min=1/3, weight_max=1.0)
    assert ok is True


def test_validate_constraints_exactly_feasible_max():
    # 3 assets, max=1/3 → 3 * 1/3 = 1.0 exactly
    ok, _ = validate_constraints(n_assets=3, weight_min=0.0, weight_max=1/3)
    assert ok is True
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_optimizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'optimizer'`

- [ ] **Step 3: Implement `portfolio_metrics`, `risk_contribution`, `validate_constraints` in `optimizer.py`**

Create `optimizer.py`:

```python
import numpy as np
import pandas as pd
from scipy.optimize import minimize

N_SIMULATIONS = 10_000


def portfolio_metrics(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> tuple[float, float, float]:
    port_return = float(np.dot(weights, mean_returns) * periods_per_year)
    port_vol = float(np.sqrt(weights @ cov_matrix @ weights) * np.sqrt(periods_per_year))
    rf_annual = rf_rate * periods_per_year
    sharpe = float((port_return - rf_annual) / port_vol) if port_vol > 0 else 0.0
    return port_return, port_vol, sharpe


def risk_contribution(weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
    port_variance = float(weights @ cov_matrix @ weights)
    if port_variance <= 0:
        return np.zeros_like(weights)
    marginal = cov_matrix @ weights
    contrib = weights * marginal
    return contrib / port_variance


def validate_constraints(
    n_assets: int,
    weight_min: float,
    weight_max: float,
) -> tuple[bool, str]:
    if weight_min * n_assets > 1.0 + 1e-6:
        return False, (
            f"Restricción infactible: peso mínimo ({weight_min:.0%}) × "
            f"{n_assets} activos = {weight_min * n_assets:.0%} > 100%"
        )
    if weight_max * n_assets < 1.0 - 1e-6:
        return False, (
            f"Restricción infactible: peso máximo ({weight_max:.0%}) × "
            f"{n_assets} activos = {weight_max * n_assets:.0%} < 100%"
        )
    return True, "OK"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_optimizer.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add optimizer.py tests/test_optimizer.py
git commit -m "feat: portfolio_metrics, risk_contribution, validate_constraints"
```

---

## Task 5: `optimizer.py` — simulate_portfolios

**Files:**
- Modify: `optimizer.py`
- Modify: `tests/test_optimizer.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_optimizer.py`:

```python
from optimizer import simulate_portfolios


def test_simulate_portfolios_returns_dataframe(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"ret", "vol", "sharpe"}


def test_simulate_portfolios_not_empty(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert len(df) > 0


def test_simulate_portfolios_vol_positive(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert (df["vol"] > 0).all()


def test_simulate_portfolios_with_bounds(synthetic_returns):
    df = simulate_portfolios(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.1, 0.6),
        allow_short=False,
    )
    assert len(df) > 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_optimizer.py::test_simulate_portfolios_returns_dataframe -v
```

Expected: FAIL — `cannot import name 'simulate_portfolios'`

- [ ] **Step 3: Implement `simulate_portfolios` in `optimizer.py`**

Append to `optimizer.py`:

```python
def simulate_portfolios(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
) -> pd.DataFrame:
    n = len(returns.columns)
    mean_returns = returns.mean().values
    cov_matrix = returns.cov().values
    lb, ub = weight_bounds
    rng = np.random.default_rng(42)
    rows = []

    for _ in range(N_SIMULATIONS):
        if allow_short:
            w = rng.standard_normal(n)
        else:
            w = rng.dirichlet(np.ones(n))

        w = np.clip(w, lb, ub)
        total = w.sum()
        if total == 0:
            continue
        w = w / total

        ret, vol, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        rows.append({"ret": ret, "vol": vol, "sharpe": sharpe})

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run all optimizer tests**

```bash
pytest tests/test_optimizer.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add optimizer.py tests/test_optimizer.py
git commit -m "feat: Monte Carlo portfolio simulation"
```

---

## Task 6: `optimizer.py` — optimize_max_sharpe, equal_weight_portfolio

**Files:**
- Modify: `optimizer.py`
- Modify: `tests/test_optimizer.py`

- [ ] **Step 1: Add tests**

Append to `tests/test_optimizer.py`:

```python
from optimizer import optimize_max_sharpe, equal_weight_portfolio


def test_optimize_max_sharpe_converges(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert result["converged"] is True


def test_optimize_max_sharpe_weights_sum_to_one(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert abs(result["weights"].sum() - 1.0) < 1e-4


def test_optimize_max_sharpe_weights_non_negative_when_no_short(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert all(w >= -1e-6 for w in result["weights"])


def test_optimize_max_sharpe_returns_risk_contribution(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.0, 1.0),
        allow_short=False,
    )
    assert "risk_contribution" in result
    assert len(result["risk_contribution"]) == 3


def test_optimize_max_sharpe_respects_bounds(synthetic_returns):
    result = optimize_max_sharpe(
        synthetic_returns,
        rf_rate=0.0001,
        periods_per_year=252,
        weight_bounds=(0.1, 0.6),
        allow_short=False,
    )
    if result["converged"]:
        assert all(w >= 0.1 - 1e-4 for w in result["weights"])
        assert all(w <= 0.6 + 1e-4 for w in result["weights"])


def test_equal_weight_portfolio_weights_are_equal(synthetic_returns):
    result = equal_weight_portfolio(synthetic_returns, rf_rate=0.0001, periods_per_year=252)
    assert abs(result["weights"][0] - 1/3) < 1e-6
    assert abs(result["weights"].sum() - 1.0) < 1e-6


def test_equal_weight_portfolio_returns_metrics(synthetic_returns):
    result = equal_weight_portfolio(synthetic_returns, rf_rate=0.0001, periods_per_year=252)
    assert "annual_return" in result
    assert "annual_vol" in result
    assert "sharpe" in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_optimizer.py::test_optimize_max_sharpe_converges -v
```

Expected: FAIL — `cannot import name 'optimize_max_sharpe'`

- [ ] **Step 3: Implement `optimize_max_sharpe` and `equal_weight_portfolio` in `optimizer.py`**

Append to `optimizer.py`:

```python
def optimize_max_sharpe(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
) -> dict:
    n = len(returns.columns)
    mean_returns = returns.mean().values
    cov_matrix = returns.cov().values
    lb = weight_bounds[0] if not allow_short else -1.0
    ub = weight_bounds[1]

    def neg_sharpe(w: np.ndarray) -> float:
        _, _, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        return -sharpe

    bounds = [(lb, ub)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    x0 = np.ones(n) / n

    result = minimize(
        neg_sharpe,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-9},
    )

    if not result.success:
        return {"converged": False, "message": result.message}

    weights = np.clip(result.x, lb, ub)
    weights = weights / weights.sum()

    ret, vol, sharpe = portfolio_metrics(weights, mean_returns, cov_matrix, rf_rate, periods_per_year)
    rc = risk_contribution(weights, cov_matrix)

    return {
        "converged": True,
        "weights": weights,
        "annual_return": ret,
        "annual_vol": vol,
        "sharpe": sharpe,
        "risk_contribution": rc,
        "message": "OK",
    }


def equal_weight_portfolio(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
) -> dict:
    n = len(returns.columns)
    weights = np.ones(n) / n
    mean_returns = returns.mean().values
    cov_matrix = returns.cov().values
    ret, vol, sharpe = portfolio_metrics(weights, mean_returns, cov_matrix, rf_rate, periods_per_year)
    return {"weights": weights, "annual_return": ret, "annual_vol": vol, "sharpe": sharpe}
```

- [ ] **Step 4: Run all optimizer tests**

```bash
pytest tests/test_optimizer.py -v
```

Expected: all 21 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add optimizer.py tests/test_optimizer.py
git commit -m "feat: Max Sharpe optimization and equal-weight portfolio"
```

---

## Task 7: `charts.py` — All four Plotly figures

**Files:**
- Create: `charts.py`

> Charts are tested with smoke tests — we verify they return a `go.Figure` with the right traces, not their pixel output.

- [ ] **Step 1: Write smoke tests**

Create `tests/test_charts.py`:

```python
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from charts import (
    plot_efficient_frontier,
    plot_weights_pie,
    plot_correlation_heatmap,
    plot_comparison,
)


def _sim_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 200
    return pd.DataFrame({
        "ret": rng.uniform(0.05, 0.30, n),
        "vol": rng.uniform(0.05, 0.35, n),
        "sharpe": rng.uniform(0.5, 2.5, n),
    })


def _returns() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.normal(0.001, 0.015, (252, 3)),
        columns=["AAPL", "MSFT", "GOOGL"],
    )


def test_plot_efficient_frontier_returns_figure():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark={"annual_return": 0.12, "annual_vol": 0.16, "sharpe": 0.75},
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 3


def test_plot_efficient_frontier_no_benchmark():
    fig = plot_efficient_frontier(
        sim_df=_sim_df(),
        optimal={"annual_return": 0.18, "annual_vol": 0.14, "sharpe": 1.3, "weights": np.array([0.5, 0.3, 0.2])},
        benchmark=None,
        equal_weight={"annual_return": 0.13, "annual_vol": 0.15, "sharpe": 0.87},
        tickers=["AAPL", "MSFT", "GOOGL"],
    )
    assert isinstance(fig, go.Figure)


def test_plot_weights_pie_returns_figure():
    fig = plot_weights_pie(np.array([0.5, 0.3, 0.2]), ["AAPL", "MSFT", "GOOGL"])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_correlation_heatmap_returns_figure():
    fig = plot_correlation_heatmap(_returns())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_plot_comparison_returns_figure():
    fig = plot_comparison(
        tickers=["AAPL", "MSFT", "GOOGL"],
        opt_weights=np.array([0.5, 0.3, 0.2]),
        ew_weights=np.array([1/3, 1/3, 1/3]),
        opt_ret=0.18,
        ew_ret=0.13,
        opt_vol=0.14,
        ew_vol=0.15,
    )
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_charts.py -v
```

Expected: FAIL — `No module named 'charts'`

- [ ] **Step 3: Implement `charts.py`**

Create `charts.py`:

```python
import numpy as np
import pandas as pd
import plotly.graph_objects as go

_DARK_BG = "#0f1117"
_CARD_BG = "#1e2130"
_ACCENT = "#7c83fd"
_GREEN = "#4ade80"
_ORANGE = "#fb923c"
_BLUE = "#60a5fa"


def _base_layout(**extra) -> dict:
    return dict(
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_CARD_BG,
        font=dict(color="#cccccc", family="sans-serif"),
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        **extra,
    )


def plot_efficient_frontier(
    sim_df: pd.DataFrame,
    optimal: dict,
    benchmark: dict | None,
    equal_weight: dict,
    tickers: list[str],
) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=sim_df["vol"],
        y=sim_df["ret"],
        mode="markers",
        marker=dict(
            color=sim_df["sharpe"],
            colorscale="Viridis",
            size=3,
            opacity=0.5,
            colorbar=dict(title="Sharpe"),
        ),
        name="Portafolios simulados",
        hovertemplate="Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=[equal_weight["annual_vol"]],
        y=[equal_weight["annual_return"]],
        mode="markers",
        marker=dict(symbol="circle", size=13, color=_BLUE, line=dict(color="white", width=1)),
        name=f"Equal Weight (Sharpe: {equal_weight['sharpe']:.2f})",
        hovertemplate="Equal Weight<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    if benchmark:
        fig.add_trace(go.Scatter(
            x=[benchmark["annual_vol"]],
            y=[benchmark["annual_return"]],
            mode="markers",
            marker=dict(symbol="triangle-up", size=15, color=_ORANGE, line=dict(color="white", width=1)),
            name=f"S&P 500 (Sharpe: {benchmark.get('sharpe', 0):.2f})",
            hovertemplate="S&P 500<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=[optimal["annual_vol"]],
        y=[optimal["annual_return"]],
        mode="markers",
        marker=dict(symbol="star", size=20, color=_GREEN, line=dict(color="white", width=1)),
        name=f"Óptimo (Sharpe: {optimal['sharpe']:.2f})",
        hovertemplate="Óptimo<br>Vol: %{x:.2%}<br>Ret: %{y:.2%}<extra></extra>",
    ))

    fig.update_layout(
        title="Frontera Eficiente",
        xaxis=dict(title="Volatilidad Anual", tickformat=".0%"),
        yaxis=dict(title="Retorno Anual Esperado", tickformat=".0%"),
        **_base_layout(),
    )
    return fig


def plot_weights_pie(weights: np.ndarray, tickers: list[str]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=tickers,
        values=weights,
        hole=0.35,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.2%}<extra></extra>",
    ))
    fig.update_layout(title="Distribución de Pesos Óptimos", **_base_layout())
    return fig


def plot_correlation_heatmap(returns: pd.DataFrame) -> go.Figure:
    corr = returns.corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns.tolist(),
        y=corr.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        hovertemplate="%{x} / %{y}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(title="Matriz de Correlación", **_base_layout())
    return fig


def plot_comparison(
    tickers: list[str],
    opt_weights: np.ndarray,
    ew_weights: np.ndarray,
    opt_ret: float,
    ew_ret: float,
    opt_vol: float,
    ew_vol: float,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Equal Weight",
        x=ew_weights,
        y=tickers,
        orientation="h",
        marker_color=_BLUE,
        hovertemplate="%{y}: %{x:.2%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Max Sharpe",
        x=opt_weights,
        y=tickers,
        orientation="h",
        marker_color=_GREEN,
        hovertemplate="%{y}: %{x:.2%}<extra></extra>",
    ))
    fig.update_layout(
        title=(
            f"Óptimo vs Equal Weight — "
            f"Ret: {opt_ret:.1%} vs {ew_ret:.1%} | "
            f"Vol: {opt_vol:.1%} vs {ew_vol:.1%}"
        ),
        barmode="group",
        xaxis=dict(title="Peso", tickformat=".0%"),
        **_base_layout(),
    )
    return fig
```

- [ ] **Step 4: Run all chart tests**

```bash
pytest tests/test_charts.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add charts.py tests/test_charts.py
git commit -m "feat: Plotly chart builders — frontier, pie, heatmap, comparison"
```

---

## Task 8: `exporter.py` — Excel export

**Files:**
- Create: `exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_exporter.py`:

```python
import io
import pandas as pd
import openpyxl
from exporter import to_excel


def _weights_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "GOOGL"],
        "Peso Óptimo (%)": ["50.00%", "30.00%", "20.00%"],
        "Retorno Esperado (%)": ["21.00%", "18.00%", "17.00%"],
        "Volatilidad (%)": ["22.00%", "19.00%", "20.00%"],
        "Contrib. Riesgo (%)": ["48.00%", "32.00%", "20.00%"],
    })


def _metrics() -> dict:
    return {
        "sharpe": 1.42,
        "annual_return": 0.183,
        "annual_vol": 0.128,
        "rf_rate": 0.0525,
        "horizon": "1 Mes",
    }


def test_to_excel_returns_bytes():
    result = to_excel(_weights_df(), _metrics())
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_to_excel_has_pesos_sheet():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    assert "Pesos" in wb.sheetnames


def test_to_excel_has_metricas_sheet():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    assert "Métricas" in wb.sheetnames


def test_to_excel_pesos_sheet_row_count():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    ws = wb["Pesos"]
    # 1 header + 3 data rows
    assert ws.max_row == 4


def test_to_excel_pesos_first_column_header():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    ws = wb["Pesos"]
    assert ws.cell(1, 1).value == "Ticker"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_exporter.py -v
```

Expected: FAIL — `No module named 'exporter'`

- [ ] **Step 3: Implement `to_excel` in `exporter.py`**

Create `exporter.py`:

```python
import io
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd
from fpdf import FPDF
import plotly.graph_objects as go


def to_excel(weights_df: pd.DataFrame, metrics: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        weights_df.to_excel(writer, sheet_name="Pesos", index=False)
        pd.DataFrame([metrics]).to_excel(writer, sheet_name="Métricas", index=False)
    return buf.getvalue()
```

- [ ] **Step 4: Run exporter tests**

```bash
pytest tests/test_exporter.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add exporter.py tests/test_exporter.py
git commit -m "feat: Excel export with Pesos and Métricas sheets"
```

---

## Task 9: `exporter.py` — PDF export

**Files:**
- Modify: `exporter.py`

- [ ] **Step 1: Implement `to_pdf` in `exporter.py`**

Append to `exporter.py`:

```python
def to_pdf(
    weights_df: pd.DataFrame,
    metrics: dict,
    figures: list[go.Figure],
) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Markowitz Pro Picks", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Fecha: {date.today().strftime('%d/%m/%Y')}  |  Horizonte: {metrics.get('horizon', '-')}",
        ln=True,
        align="C",
    )
    pdf.ln(6)

    # KPI table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Métricas del Portafolio Óptimo", ln=True)
    pdf.set_font("Helvetica", "", 10)
    kpis = [
        ("Sharpe Ratio", f"{metrics['sharpe']:.4f}"),
        ("Retorno Anual Esperado", f"{metrics['annual_return']:.2%}"),
        ("Volatilidad Anual", f"{metrics['annual_vol']:.2%}"),
        ("Tasa Libre de Riesgo (anual)", f"{metrics['rf_rate']:.2%}"),
    ]
    for label, value in kpis:
        pdf.cell(100, 7, label, border=1)
        pdf.cell(40, 7, value, border=1, ln=True)
    pdf.ln(4)

    # Weights table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Distribución de Pesos Óptimos", ln=True)
    cols = list(weights_df.columns)
    col_w = 180 // len(cols)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 7, str(col), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for _, row in weights_df.iterrows():
        for val in row:
            pdf.cell(col_w, 6, str(val), border=1)
        pdf.ln()
    pdf.ln(4)

    # Charts
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Gráficas", ln=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, fig in enumerate(figures):
            img_path = os.path.join(tmpdir, f"chart_{i}.png")
            fig.write_image(img_path, width=900, height=500, scale=1.5)
            pdf.image(img_path, w=180)
            pdf.ln(3)

    # Disclaimer
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 5,
        "Este reporte es de carácter informativo y no constituye asesoramiento financiero. "
        "Los resultados pasados no garantizan rendimientos futuros.",
    )

    return bytes(pdf.output())
```

- [ ] **Step 2: Smoke test PDF generation**

Run the following quick test in a Python REPL to confirm no crashes (kaleido must be installed):

```python
import pandas as pd, numpy as np
from exporter import to_pdf
from charts import plot_weights_pie

weights_df = pd.DataFrame({
    "Ticker": ["AAPL", "MSFT"],
    "Peso Óptimo (%)": ["60%", "40%"],
    "Retorno Esperado (%)": ["18%", "15%"],
    "Volatilidad (%)": ["20%", "18%"],
    "Contrib. Riesgo (%)": ["55%", "45%"],
})
metrics = {"sharpe": 1.42, "annual_return": 0.183, "annual_vol": 0.128, "rf_rate": 0.0525, "horizon": "1 Mes"}
fig = plot_weights_pie(np.array([0.6, 0.4]), ["AAPL", "MSFT"])
pdf_bytes = to_pdf(weights_df, metrics, [fig])
print(f"PDF size: {len(pdf_bytes)} bytes")  # should be > 10000
```

Expected output: `PDF size: <number> bytes` with no exceptions.

- [ ] **Step 3: Commit**

```bash
git add exporter.py
git commit -m "feat: PDF report generation with tables and charts"
```

---

## Task 10: `app.py` — Full Streamlit UI

**Files:**
- Create: `app.py`

> No unit tests here — the UI is validated by running the app and exercising the golden path manually.

- [ ] **Step 1: Implement `app.py`**

Create `app.py`:

```python
import numpy as np
import pandas as pd
import streamlit as st

from charts import (
    plot_comparison,
    plot_correlation_heatmap,
    plot_efficient_frontier,
    plot_weights_pie,
)
from data import (
    DEFAULT_HORIZON,
    HORIZON_CONFIG,
    RF_FALLBACK,
    fetch_market_data,
    parse_tickers,
)
from exporter import to_excel, to_pdf
from optimizer import (
    equal_weight_portfolio,
    optimize_max_sharpe,
    simulate_portfolios,
    validate_constraints,
)

st.set_page_config(
    page_title="Markowitz Pro Picks",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Markowitz Pro Picks")
st.caption("Optimización de portafolio — Máximo Sharpe Ratio (Markowitz)")

# ── Configuration panel ───────────────────────────────────────────────────────
with st.container():
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        raw_tickers = st.text_input(
            "Tickers (separados por coma o espacio)",
            value="AAPL, MSFT, GOOGL, AMZN, NVDA",
        )
    with col2:
        horizon = st.selectbox(
            "Horizonte de inversión",
            options=list(HORIZON_CONFIG.keys()),
            index=list(HORIZON_CONFIG.keys()).index(DEFAULT_HORIZON),
        )
    with col3:
        allow_short = st.toggle("Short selling", value=False)

    col4, col5, col6 = st.columns([1, 1, 1])
    with col4:
        weight_min = st.slider("Peso mínimo por activo (%)", 0, 20, 0) / 100
    with col5:
        weight_max = st.slider("Peso máximo por activo (%)", 20, 100, 100) / 100
    with col6:
        st.write("")
        st.write("")
        optimize_btn = st.button("▶ Optimizar", type="primary", use_container_width=True)

if not optimize_btn:
    st.info("Ingresa los tickers y presiona **▶ Optimizar** para calcular el portafolio óptimo.")
    st.stop()

# ── Parse and validate tickers ────────────────────────────────────────────────
tickers = parse_tickers(raw_tickers)
if not tickers:
    st.error("🔴 Ingresa al menos 2 tickers.")
    st.stop()

# ── Fetch market data ─────────────────────────────────────────────────────────
with st.spinner("Descargando datos de mercado..."):
    market = fetch_market_data(tuple(tickers), horizon)

if market["invalid_tickers"]:
    st.warning(f"⚠️ Tickers no encontrados y omitidos: {', '.join(market['invalid_tickers'])}")

valid_tickers = market["valid_tickers"]
if len(valid_tickers) < 2:
    st.error("🔴 Se necesitan al menos 2 tickers válidos para optimizar el portafolio.")
    st.stop()

if not market.get("rf_available", True):
    st.warning(
        f"⚠️ ^IRX no disponible. Usando tasa libre de riesgo de referencia: {RF_FALLBACK:.1%} anual."
    )

returns = market["returns"]
rf_rate = market["rf_rate"]
periods_per_year = market["periods_per_year"]

# ── Validate weight constraints ───────────────────────────────────────────────
feasible, msg = validate_constraints(len(valid_tickers), weight_min, weight_max)
if not feasible:
    st.error(f"🔴 {msg}")
    st.stop()

# ── Run optimization ──────────────────────────────────────────────────────────
weight_bounds = (weight_min, weight_max)
with st.spinner("Optimizando portafolio..."):
    sim_df = simulate_portfolios(returns, rf_rate, periods_per_year, weight_bounds, allow_short)
    optimal = optimize_max_sharpe(returns, rf_rate, periods_per_year, weight_bounds, allow_short)
    ew = equal_weight_portfolio(returns, rf_rate, periods_per_year)

if not optimal["converged"]:
    st.error(
        f"🔴 La optimización no convergió: {optimal['message']}. "
        "Revisa activos muy correlacionados o ajusta los límites de posición."
    )
    st.stop()

# ── Benchmark metrics ─────────────────────────────────────────────────────────
benchmark = None
if not market["benchmark_returns"].empty:
    bm = market["benchmark_returns"]
    bm_ret = float(bm.mean() * periods_per_year)
    bm_vol = float(bm.std() * np.sqrt(periods_per_year))
    bm_sharpe = float((bm_ret - rf_rate * periods_per_year) / bm_vol) if bm_vol > 0 else 0.0
    benchmark = {"annual_return": bm_ret, "annual_vol": bm_vol, "sharpe": bm_sharpe}

# ── KPI cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Sharpe Ratio", f"{optimal['sharpe']:.4f}")
k2.metric("Retorno Anual Esperado", f"{optimal['annual_return']:.2%}")
k3.metric("Volatilidad Anual", f"{optimal['annual_vol']:.2%}")
k4.metric("Tasa Libre de Riesgo", f"{rf_rate * periods_per_year:.2%}")

# ── Concentration warning ─────────────────────────────────────────────────────
max_w = float(optimal["weights"].max())
if max_w > 0.50:
    top = valid_tickers[int(optimal["weights"].argmax())]
    st.warning(
        f"⚠️ Alta concentración: **{top}** recibe **{max_w:.1%}** del portafolio. "
        "Considera establecer un peso máximo menor."
    )

# ── Build shared data structures ──────────────────────────────────────────────
weights_df = pd.DataFrame({
    "Ticker": valid_tickers,
    "Peso Óptimo (%)": [f"{w:.2%}" for w in optimal["weights"]],
    "Retorno Esperado (%)": [
        f"{returns[t].mean() * periods_per_year:.2%}" for t in valid_tickers
    ],
    "Volatilidad (%)": [
        f"{returns[t].std() * np.sqrt(periods_per_year):.2%}" for t in valid_tickers
    ],
    "Contrib. Riesgo (%)": [f"{c:.2%}" for c in optimal["risk_contribution"]],
})

metrics = {
    "sharpe": optimal["sharpe"],
    "annual_return": optimal["annual_return"],
    "annual_vol": optimal["annual_vol"],
    "rf_rate": rf_rate * periods_per_year,
    "horizon": horizon,
}

fig_frontier = plot_efficient_frontier(sim_df, optimal, benchmark, ew, valid_tickers)
fig_pie = plot_weights_pie(optimal["weights"], valid_tickers)
fig_corr = plot_correlation_heatmap(returns)
fig_comp = plot_comparison(
    valid_tickers,
    optimal["weights"],
    ew["weights"],
    optimal["annual_return"],
    ew["annual_return"],
    optimal["annual_vol"],
    ew["annual_vol"],
)

# ── Export buttons ────────────────────────────────────────────────────────────
ex_col, pdf_col = st.columns(2)
with ex_col:
    st.download_button(
        label="⬇ Descargar Excel",
        data=to_excel(weights_df, metrics),
        file_name=f"markowitz_{horizon.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with pdf_col:
    st.download_button(
        label="⬇ Descargar PDF",
        data=to_pdf(weights_df, metrics, [fig_frontier, fig_pie, fig_corr, fig_comp]),
        file_name=f"markowitz_{horizon.replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

# ── Charts 2×2 ────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(fig_frontier, use_container_width=True)
with c2:
    st.plotly_chart(fig_pie, use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.plotly_chart(fig_corr, use_container_width=True)
with c4:
    st.plotly_chart(fig_comp, use_container_width=True)

# ── Weights table ─────────────────────────────────────────────────────────────
st.subheader("📋 Tabla de Pesos Óptimos")
st.dataframe(weights_df, use_container_width=True, hide_index=True)
```

- [ ] **Step 2: Run the app**

```bash
streamlit run app.py
```

Expected: browser opens at `http://localhost:8501`

- [ ] **Step 3: Manual golden path test**

With the app open in the browser:
1. Enter tickers: `AAPL, MSFT, GOOGL, AMZN, NVDA`
2. Select horizon: `1 Mes`
3. Leave short selling Off, min 0%, max 100%
4. Click **▶ Optimizar**
5. Verify: 4 KPI cards appear with numeric values
6. Verify: 4 charts render (frontier, pie, heatmap, comparison)
7. Verify: weights table appears with 5 rows
8. Click **⬇ Descargar Excel** — file downloads
9. Click **⬇ Descargar PDF** — file downloads

- [ ] **Step 4: Test error paths**

1. Enter an invalid ticker: `AAPL, INVALIDXYZ999` → warning appears, continues with AAPL (only 1 valid → error about needing 2)
2. Set min weight 40% with 3 tickers → constraint error appears before download
3. Enter only 1 valid ticker → error message appears

- [ ] **Step 5: Test concentration warning**

Enter only 2 highly asymmetric tickers like `BRK-B, GLD` and optimize — if one gets > 50%, the yellow warning should appear.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat: complete Streamlit UI with all charts, KPIs, alerts, and export"
```

---

## Running the App

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Launch
streamlit run app.py
```

App will be available at `http://localhost:8501`

---

## Running Tests

```bash
pytest tests/ -v
```
