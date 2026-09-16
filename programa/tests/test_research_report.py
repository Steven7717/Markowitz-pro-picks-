from pathlib import Path

import pytest

from research.evaluation import (
    FDR,
    MIN_IC,
    MIN_SPREAD_NET,
    MIN_SUBPERIODS,
    MIN_TSTAT,
    GateAResult,
)
from research.report import build_verdict, to_markdown
from research.timing import SIGMAS_PUERTA_B, GateBResult

RAIZ_DOCS = Path(__file__).resolve().parent.parent / "docs" / "research"


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


# ── El listón viaja con el veredicto ─────────────────────────────────────────

def test_the_verdict_records_the_bar_gate_b_was_judged_against():
    """Un veredicto sin su listón es un dogma: nadie puede recomprobarlo.

    Es la lección que este repo ya pagó del lado de la aplicación, donde un
    `beats_equal_weight` escrito con un listón viejo seguía pintando de verde
    meses después. Aquí el informe escribía la medición —delta y error— pero no
    contra qué se juzgó, así que `gate_b` había que creérselo.
    """
    entry = build_verdict([_gate_a()], {"s": _gate_b(delta=0.4, stderr=0.1)})["s"]
    assert entry["gate_b_sigmas"] == SIGMAS_PUERTA_B
    assert entry["gate_b_threshold"] == pytest.approx(SIGMAS_PUERTA_B * 0.1)


def test_gate_b_can_be_recomputed_from_what_the_verdict_carries():
    """La conclusión tiene que salir de los campos que la acompañan, no del código."""
    for delta, stderr in ((0.4, 0.1), (0.01, 0.5), (0.1, 0.1)):
        entry = build_verdict([_gate_a()], {"s": _gate_b(delta=delta, stderr=stderr)})["s"]
        assert entry["gate_b"] == (entry["gate_b_delta"] > entry["gate_b_threshold"])


def test_a_signal_without_a_gate_b_measurement_still_carries_the_bar():
    """El listón es del criterio, no de la medición: existe aunque no se midiera.

    El umbral sale infinito, que es lo que ya decía el error estándar ausente:
    nada lo supera. Pero las sigmas siguen siendo las del criterio, porque no
    dependen de que haya habido experimento.
    """
    entry = build_verdict([_gate_a()], {})["s"]
    assert entry["gate_b_sigmas"] == SIGMAS_PUERTA_B
    assert entry["gate_b_threshold"] == float("inf")
    assert entry["gate_b"] is False


def test_the_markdown_report_states_the_bar_gate_b_was_judged_against():
    """Quien lee el documento tiene que poder comprobar la columna PASA sin el código."""
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    text = to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
    # Excluyendo las filas de tabla: la cabecera ya dice "Puerta B" y "Error
    # estándar" sin explicar nada, y es lo que este test tiene que NO aceptar.
    criterio = [
        l
        for l in text.splitlines()
        if not l.startswith("|") and "Puerta B" in l and "error est" in l.lower()
    ]
    assert criterio, text
    assert f"{SIGMAS_PUERTA_B:.1f}" in criterio[0]


# ── Y el de la Puerta A, que son cinco ───────────────────────────────────────

def _recomputar_puerta_a(stats: dict) -> bool:
    """Las cinco condiciones de §3.4, leídas SOLO de lo que el informe escribe."""
    return bool(
        stats["mean_ic"] >= stats["min_ic"]
        and stats["t_stat"] >= stats["min_t_stat"]
        and stats["survives_bh"]
        and stats["spread_net"] > stats["min_spread_net"]
        and stats["subperiods_passed"] >= stats["min_subperiods"]
    )


def test_the_verdict_records_the_bars_gate_a_was_judged_against():
    """Cinco condiciones, cinco listones. El quinto era un `> 0.0` escrito a mano."""
    stats = build_verdict([_gate_a()], {"s": _gate_b()})["s"]["horizons"][21]
    assert stats["min_ic"] == MIN_IC
    assert stats["min_t_stat"] == MIN_TSTAT
    assert stats["min_subperiods"] == MIN_SUBPERIODS
    assert stats["fdr"] == FDR
    assert stats["min_spread_net"] == MIN_SPREAD_NET


def test_gate_a_can_be_recomputed_from_what_the_verdict_carries():
    """Cada condición, incumplida por separado, tiene que poder rehacerse desde el dict.

    Si una sola de las cinco no viajara, alguno de estos casos saldría distinto
    al recomputarlo y el informe estaría pidiendo un acto de fe.
    """
    # Casos EN EL BORDE de cada listón, uno a cada lado. Con casos lejanos el
    # test sólo comprobaría coherencia interna: un `min_ic` mal escrito en el
    # dict caería del mismo lado que el de verdad y no se notaría.
    casos = [
        _gate_a(),
        _gate_a(mean_ic=MIN_IC - 0.001),
        _gate_a(mean_ic=MIN_IC + 0.001),
        _gate_a(t_stat=MIN_TSTAT - 0.1),
        _gate_a(t_stat=MIN_TSTAT + 0.1),
        _gate_a(p_value=0.50),
        _gate_a(spread_net=MIN_SPREAD_NET - 0.001),
        _gate_a(spread_net=MIN_SPREAD_NET + 0.001),
        _gate_a(subperiods=MIN_SUBPERIODS - 1),
        _gate_a(subperiods=MIN_SUBPERIODS),
    ]
    for caso in casos:
        stats = build_verdict([caso], {"s": _gate_b()})["s"]["horizons"][21]
        assert stats["passes"] == _recomputar_puerta_a(stats), stats


def test_the_markdown_report_states_the_bars_gate_a_was_judged_against():
    """Las tres columnas del detalle tambien habia que creerselas."""
    verdict = build_verdict([_gate_a()], {"s": _gate_b()})
    text = to_markdown(verdict, coverage_summary="n/a", passive_sharpe=0.6)
    criterio = [
        l
        for l in text.splitlines()
        if not l.startswith("|") and "Puerta A" in l and "IC medio" in l
    ]
    assert criterio, text
    assert f"{MIN_IC:.3f}" in criterio[0]
    assert f"{MIN_TSTAT:.1f}" in criterio[0]
    assert f"{MIN_SUBPERIODS}" in criterio[0]


# -- El documento publicado, no solo el generador -----------------------------

def test_every_published_report_states_the_bars_it_was_judged_against():
    """Los listones tienen que estar en el DOCUMENTO, no solo en `to_markdown`.

    `research/run.py` escribe `<fecha>-veredicto-senales-tecnicas.md`: cada
    corrida crea un fichero nuevo con su propia fecha, asi que mejorar el
    generador no alcanza a los informes ya publicados. El del 2026-08-06 se
    quedo sin las dos lineas de criterio durante todo el tiempo que duro el
    defecto, y es el que `CONTEXTO.md` enlaza como «resultados».

    Se comprueba que la linea EXISTE, no que sus numeros sean los de hoy: un
    informe lleva el liston contra el que se dicto, que es el suyo y no el
    vigente. Si algun dia se mueve `MIN_IC`, el documento viejo sigue diciendo
    la verdad y este test sigue en verde.
    """
    informes = sorted(RAIZ_DOCS.glob("*-veredicto-senales-tecnicas.md"))
    assert informes, "no hay ningun informe publicado que comprobar"
    for informe in informes:
        texto = informe.read_text(encoding="utf-8")
        for puerta in ("A", "B"):
            assert f"**Criterio de la Puerta {puerta}:**" in texto, (
                f"{informe.name} no dice contra que liston se dicto su Puerta {puerta}"
            )
