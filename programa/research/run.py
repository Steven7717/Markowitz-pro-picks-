import sys
from datetime import date
from pathlib import Path

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

    gate_a = []
    for name, build in SIGNALS.items():
        signal = build(panel)
        for horizon in HORIZONS:
            print(f"  Puerta A: {name} @ {horizon}d")
            gate_a.append(evaluate(name, signal, close, horizon=horizon))

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
