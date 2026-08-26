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
