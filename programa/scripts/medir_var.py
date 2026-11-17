# programa/scripts/medir_var.py
"""Corre la competencia de VaR sobre carteras reales a pesos iguales.

    uv run python scripts/medir_var.py

Descarga de verdad (no usa la caché de Streamlit). Si un ticker falla o no
tiene historia para el backtest, lo dice y sigue con la cartera siguiente.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
from scipy import stats

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

print(f"Descarga: {date.today().isoformat()}")

for nombre, tickers in CARTERAS.items():
    try:
        datos = retornos_diarios.__wrapped__(tickers)
        r = datos["retornos"].dropna()
        sesiones = datos["sesiones"]
    except Exception as e:  # red, ticker inexistente...
        print(f"\n## {nombre}: no se pudo descargar ({type(e).__name__}: {e})")
        continue
    print(f"\n<!-- sesiones por ticker: {sesiones} -->")
    if len(r) < backtest.MINIMO_OBSERVACIONES:
        print(f"\n## {nombre}: sólo {len(r)} sesiones comunes, hacen falta "
              f"{backtest.MINIMO_OBSERVACIONES}; sesiones por ticker: {sesiones}")
        continue
    rp = r.to_numpy() @ np.full(len(tickers), 1 / len(tickers))
    res = backtest.competir(rp)
    ganador = backtest.elegir(res)
    ult = rp[-500:]
    print(f"\n## {nombre} ({len(rp)} sesiones) — gana {ETIQUETAS[ganador]}\n")
    print(f"Últimas 500 sesiones: asimetría {stats.skew(ult):.2f}, "
          f"curtosis en exceso {stats.kurtosis(ult):.2f}\n")
    print("| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES | VaR medio |")
    print("|---|---|---|---|---|---|---|")
    for m, b in res.items():
        print(f"| {ETIQUETAS[m]} | {b.fraccion_verde:.0%} | {b.zona_actual} | "
              f"{b.tasa:.2%} | {b.kupiec_p:.2f} | {b.razon_es:.2f} | "
              f"{float(np.mean(b.var99)):.2%} |")
