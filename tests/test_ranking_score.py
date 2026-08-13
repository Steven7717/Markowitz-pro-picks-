import numpy as np
import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import PILARES
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    media_ventana,
    puntuaciones_por_pilar,
)


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


def medias_falsas(por_ticker: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Tabla con la forma que devuelve media_ventana(): ticker x 17 KPIs."""
    marco = pd.DataFrame(
        np.nan,
        index=pd.Index(sorted(por_ticker), name="ticker"),
        columns=list(TODOS_LOS_KPIS),
        dtype="float64",
    )
    for ticker, valores in por_ticker.items():
        for kpi, valor in valores.items():
            marco.loc[ticker, kpi] = valor
    return marco


def test_un_multiplo_alto_penaliza_en_vez_de_premiar():
    # PER con z = +2 significa caro. Sin invertir el signo, el pilar de
    # valoración saldría +2 y el ranking premiaría lo caro.
    medias = medias_falsas({"AAA": {"per": 2.0}})
    pilares, _ = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "valoracion"] == -2.0


def test_la_deuda_alta_penaliza_en_solidez():
    medias = medias_falsas({"AAA": {"deuda_neta_ebitda": 1.0, "razon_corriente": 1.0}})
    pilares, _ = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "solidez"] == 0.0


def test_promedia_solo_los_kpis_con_dato_del_pilar():
    medias = medias_falsas({"AAA": {"roe": 2.0, "roic": 4.0}})
    pilares, conteo = puntuaciones_por_pilar(medias)
    assert pilares.loc["AAA", "calidad"] == 3.0
    assert conteo.loc["AAA", "calidad"] == 2


def test_un_pilar_sin_ningun_dato_queda_en_nan_no_en_cero():
    # Un 0 se leería como "exactamente la media del sector", que es una
    # afirmación; NaN dice "no medido", que es la verdad.
    medias = medias_falsas({"AAA": {"roe": 1.0}})
    pilares, conteo = puntuaciones_por_pilar(medias)
    assert pd.isna(pilares.loc["AAA", "crecimiento"])
    assert conteo.loc["AAA", "crecimiento"] == 0


def test_medias_vacias_no_revientan():
    pilares, conteo = puntuaciones_por_pilar(medias_falsas({}))
    assert list(pilares.columns) == list(PILARES)
    assert pilares.empty and conteo.empty
    # El índice se hereda del panel, no se inventa: media_ventana ya devuelve
    # uno llamado "ticker" y unir resultados de un panel vacío con uno lleno
    # tiene que funcionar.
    assert pilares.index.name == "ticker"
    assert pilares is not conteo


def test_cada_empresa_se_puntua_por_separado():
    # Con un solo ticker, un cálculo por fila y un escalar repartido a todas
    # las filas dan lo mismo. Hacen falta dos empresas con cobertura distinta
    # para que un colapso de eje se note.
    medias = medias_falsas({"AAA": {"roe": 2.0, "roic": 4.0}, "BBB": {"roe": 1.0}})
    pilares, conteo = puntuaciones_por_pilar(medias)
    assert conteo.loc["AAA", "calidad"] == 2
    assert conteo.loc["BBB", "calidad"] == 1
    assert pilares.loc["AAA", "calidad"] == 3.0
    assert pilares.loc["BBB", "calidad"] == 1.0


PILARES_CRECIMIENTO = PILARES["crecimiento"]


def historial_falso(por_ticker: dict[str, tuple[int, str]]) -> pd.DataFrame:
    """Historial con la forma que devuelve media_ventana()."""
    tickers = sorted(por_ticker)
    return pd.DataFrame(
        [
            {"trimestres": por_ticker[t][0], "ultimo_trimestre": por_ticker[t][1]}
            for t in tickers
        ],
        index=pd.Index(tickers, name="ticker"),
    )


def _completa(**cambios) -> dict[str, float]:
    """Empresa que supera todas las guardas, para alterar una sola cosa."""
    base = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
    base.update(cambios)
    return base


def test_una_empresa_completa_no_se_excluye():
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert pd.isna(motivos["AAA"])


def test_historia_corta_excluye():
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (3, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "historia_corta"


def test_datos_rancios_excluye_a_partir_del_tercer_trimestre_de_rezago():
    medias = medias_falsas({"AAA": _completa(), "BBB": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares,
        conteo,
        historial_falso({"AAA": (4, "2024Q4"), "BBB": (4, "2024Q3")}),
        "2025Q2",
    )
    assert pd.isna(motivos["AAA"]), "2 trimestres de rezago están dentro del límite"
    assert motivos["BBB"] == "datos_rancios"


def test_un_pilar_sin_datos_excluye():
    sin_crecimiento = {
        kpi: 1.0 for kpi in TODOS_LOS_KPIS if kpi not in PILARES_CRECIMIENTO
    }
    medias = medias_falsas({"AAA": sin_crecimiento})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "pilar_sin_datos"


def test_menos_de_ocho_kpis_excluye_aunque_haya_cuatro_pilares():
    # Uno en calidad, dos en cada uno de los otros tres: 7 KPIs, 4 pilares.
    escasa = {
        "roe": 1.0,
        "crecimiento_ingresos": 1.0,
        "crecimiento_bpa": 1.0,
        "per": 1.0,
        "ev_ebitda": 1.0,
        "razon_corriente": 1.0,
        "cobertura_intereses": 1.0,
    }
    medias = medias_falsas({"AAA": escasa})
    pilares, conteo = puntuaciones_por_pilar(medias)
    motivos = aplicar_guardas(
        pilares, conteo, historial_falso({"AAA": (4, "2025Q2")}), "2025Q2"
    )
    assert motivos["AAA"] == "cobertura_insuficiente"


def test_una_empresa_ausente_del_historial_se_excluye():
    # NaN < 4 es False: una comparación ingenua dejaría pasar a una empresa de
    # la que no sabemos nada, que es el peor de los casos posibles.
    medias = medias_falsas({"AAA": _completa()})
    pilares, conteo = puntuaciones_por_pilar(medias)
    vacio = pd.DataFrame(columns=["trimestres", "ultimo_trimestre"])
    motivos = aplicar_guardas(pilares, conteo, vacio, "2025Q2")
    assert motivos["AAA"] == "historia_corta"


def test_el_compuesto_se_reestandariza_dentro_del_sector():
    # Tres empresas del mismo sector con compuestos brutos crecientes: tras
    # re-estandarizar, la media del sector es 0 y la desviación 1.
    medias = medias_falsas(
        {
            "AAA": {kpi: 1.0 for kpi in TODOS_LOS_KPIS},
            "BBB": {kpi: 2.0 for kpi in TODOS_LOS_KPIS},
            "CCC": {kpi: 3.0 for kpi in TODOS_LOS_KPIS},
        }
    )
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert abs(puntos.mean()) < 1e-12
    assert abs(puntos.std(ddof=1) - 1.0) < 1e-12
    assert puntos["CCC"] > puntos["BBB"] > puntos["AAA"]


def test_una_empresa_excluida_no_puntua():
    medias = medias_falsas({t: {kpi: 1.0 for kpi in TODOS_LOS_KPIS} for t in "ABC"})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    motivos["A"] = "historia_corta"
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert pd.isna(puntos["A"])


def test_un_pilar_en_nan_deja_el_compuesto_en_nan():
    # Sin esto, una empresa con tres pilares medidos competiría contra otras
    # con cuatro y el compuesto significaría cosas distintas en cada fila.
    completa = {kpi: 1.0 for kpi in TODOS_LOS_KPIS}
    sin_crecimiento = {
        kpi: 1.0 for kpi in TODOS_LOS_KPIS if kpi not in PILARES_CRECIMIENTO
    }
    medias = medias_falsas({"AAA": completa, "BBB": completa, "CCC": sin_crecimiento})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Tech", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)

    assert pd.isna(puntos["CCC"])


def test_un_sector_con_menos_de_tres_pares_se_nombra_como_exclusion():
    # zscore_within_sector devuelve NaN con menos de 3 pares. Sin nombrarlo,
    # esas empresas desaparecerían del ranking sin explicación.
    medias = medias_falsas({t: {kpi: 1.0 for kpi in TODOS_LOS_KPIS} for t in "AB"})
    pilares, _ = puntuaciones_por_pilar(medias)
    motivos = pd.Series(pd.NA, index=pilares.index, dtype="object")
    sectores = pd.Series("Utilities", index=pilares.index)

    puntos = compuesto(pilares, motivos, sectores)
    motivos = marcar_sin_pares(motivos, puntos)

    assert motivos["A"] == "sector_sin_pares"
    assert motivos["B"] == "sector_sin_pares"
