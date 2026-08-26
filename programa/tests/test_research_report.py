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
    lowered = text.lower()
    assert "optimista" in lowered and "conservador" in lowered


def test_the_markdown_report_warns_when_the_control_passed():
    verdict = build_verdict([_gate_a(signal="random_control")], {"random_control": _gate_b()})
    assert "ALARMA" in to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
