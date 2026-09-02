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


def _o_nulo(valor: float) -> float | None:
    """None rather than NaN: json.dumps writes NaN as a bare literal no strict
    JSON parser accepts, and sub-project C reads this file."""
    return None if pd.isna(valor) else float(valor)


def _item(kpi: str, z: pd.Series, valores: pd.Series) -> dict:
    return {"kpi": kpi, "valor": _o_nulo(valores[kpi]), "z": float(z[kpi])}


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
            # Cuantos KPIs sostienen cada pilar, y no solo cuantos en total: un
            # +6,39 en solidez apoyado en 1 de 3 KPIs y otro apoyado en los 3 se
            # leen igual en la ficha y no significan lo mismo. Es el primer caso
            # de la primera corrida real, no una hipotesis.
            "kpis_por_pilar": {pilar: int(n) for pilar, n in conteo.items()},
        },
        "desplazo_a": list(desplazo_a),
        "generada_por": "plantilla",
        "narrativa": None,
    }
