import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.score import media_ventana


def panel_falso(
    filas: dict[str, list[tuple[str, dict]]], crudos: dict | None = None
) -> pd.DataFrame:
    """Panel con la forma de fundamentals.run.build_panel(con_zscore=True).

    `filas` mapea ticker -> [(trimestre, {kpi: valor_z}), ...], en orden
    cronológico. `crudos` mapea kpi -> valor bruto, iguales en todas las filas.
    Los KPIs no mencionados quedan en NaN, como en el panel real.
    """
    crudos = crudos or {}
    registros, indice = [], []
    for ticker, periodos in filas.items():
        for trimestre, valores in periodos:
            fin = pd.Period(trimestre, freq="Q").end_time.normalize()
            fila = {f"z_{kpi}": np.nan for kpi in TODOS_LOS_KPIS}
            fila.update({f"z_{kpi}": v for kpi, v in valores.items()})
            fila.update({kpi: np.nan for kpi in TODOS_LOS_KPIS})
            fila.update(crudos)
            fila["trimestre"] = trimestre
            registros.append(fila)
            indice.append((ticker, fin))
    return pd.DataFrame(
        registros,
        index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"]),
    )


def test_usa_solo_los_cuatro_trimestres_mas_recientes():
    panel = panel_falso(
        {
            "AAA": [
                ("2024Q1", {"roe": 100.0}),  # fuera de la ventana
                ("2024Q2", {"roe": 100.0}),  # fuera de la ventana
                ("2024Q3", {"roe": 1.0}),
                ("2024Q4", {"roe": 1.0}),
                ("2025Q1", {"roe": 1.0}),
                ("2025Q2", {"roe": 1.0}),
            ]
        }
    )
    z, _, _ = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 1.0


def test_la_ventana_salta_los_huecos_de_presentacion():
    # 2024Q4 no existe. Una implementación que intentara alinear 4 trimestres
    # naturales consecutivos arrastraría el 100.0 y la media cambiaría.
    panel = panel_falso(
        {
            "AAA": [
                ("2023Q4", {"roe": 100.0}),
                ("2024Q1", {"roe": 2.0}),
                ("2024Q2", {"roe": 2.0}),
                ("2024Q3", {"roe": 2.0}),
                ("2025Q1", {"roe": 2.0}),
            ]
        }
    )
    z, _, historial = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 2.0
    assert historial.loc["AAA", "trimestres"] == 4


def test_promedia_solo_los_trimestres_con_dato_de_ese_kpi():
    panel = panel_falso(
        {
            "AAA": [
                ("2024Q3", {"roe": 1.0}),
                ("2024Q4", {}),
                ("2025Q1", {}),
                ("2025Q2", {"roe": 3.0}),
            ]
        }
    )
    z, _, _ = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 2.0


def test_los_valores_brutos_no_salen_de_las_columnas_z():
    # Si `valores` promediara por error las columnas z_, este test lo caza:
    # los brutos y sus z valen cosas distintas a propósito.
    panel = panel_falso(
        {"AAA": [("2025Q1", {"roe": 1.0}), ("2025Q2", {"roe": 1.0})]},
        crudos={"roe": 0.25},
    )
    z, valores, _ = media_ventana(panel)
    assert z.loc["AAA", "roe"] == 1.0
    assert valores.loc["AAA", "roe"] == 0.25


def test_el_historial_registra_cuenta_y_ultimo_trimestre():
    panel = panel_falso(
        {
            "AAA": [("2024Q3", {"roe": 1.0}), ("2024Q4", {"roe": 1.0})],
            "BBB": [("2025Q1", {"roe": 1.0})],
        }
    )
    _, _, historial = media_ventana(panel)
    assert historial.loc["AAA", "trimestres"] == 2
    assert historial.loc["AAA", "ultimo_trimestre"] == "2024Q4"
    assert historial.loc["BBB", "ultimo_trimestre"] == "2025Q1"


def test_panel_vacio_no_revienta():
    z, valores, historial = media_ventana(panel_falso({}))
    assert z.empty and valores.empty and historial.empty
    assert z.index.name == "ticker"
    assert historial.index.name == "ticker"
    # z y valores deben ser objetos distintos: si una edición futura colapsara
    # el return a `vacio, vacio, historial`, ambos serían el mismo objeto y una
    # mutación de uno corrompería al otro sin que ningún test lo notara.
    assert z is not valores
