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
