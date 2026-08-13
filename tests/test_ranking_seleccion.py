import pandas as pd

from ranking.seleccion import desplazamientos_por_ticker, seleccionar


def entradas(pares: list[tuple[str, float, str]]):
    tickers = [t for t, _, _ in pares]
    compuestos = pd.Series(
        [c for _, c, _ in pares], index=pd.Index(tickers, name="ticker"), dtype="float64"
    )
    sectores = pd.Series([s for _, _, s in pares], index=compuestos.index)
    return compuestos, sectores


def test_ordena_de_mayor_a_menor():
    compuestos, sectores = entradas(
        [("AAA", 1.0, "Tech"), ("BBB", 3.0, "Health"), ("CCC", 2.0, "Energy")]
    )
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=3)
    assert list(elegidas["ticker"]) == ["BBB", "CCC", "AAA"]
    assert list(elegidas["puesto"]) == [1, 2, 3]


def test_el_tope_sectorial_deja_fuera_a_la_cuarta_del_sector():
    compuestos, sectores = entradas(
        [
            ("T1", 5.0, "Tech"),
            ("T2", 4.0, "Tech"),
            ("T3", 3.0, "Tech"),
            ("T4", 2.5, "Tech"),
            ("H1", 1.0, "Health"),
        ]
    )
    elegidas, desplazadas = seleccionar(compuestos, sectores, tope=3, n=5)
    assert list(elegidas["ticker"]) == ["T1", "T2", "T3", "H1"]
    assert list(desplazadas["ticker"]) == ["T4"]
    assert desplazadas.loc[0, "puesto_global"] == 4
    assert desplazadas.loc[0, "bloqueada_por"] == ("T1", "T2", "T3")


def test_los_empates_se_rompen_por_ticker():
    # Sin desempate determinista, dos corridas sobre el mismo panel pueden
    # devolver listas distintas y el sistema deja de ser auditable.
    compuestos, sectores = entradas(
        [("ZZZ", 1.0, "Tech"), ("AAA", 1.0, "Health"), ("MMM", 1.0, "Energy")]
    )
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=3)
    assert list(elegidas["ticker"]) == ["AAA", "MMM", "ZZZ"]


def test_las_empresas_sin_compuesto_no_entran():
    compuestos, sectores = entradas(
        [("AAA", float("nan"), "Tech"), ("BBB", 1.0, "Tech")]
    )
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=5)
    assert list(elegidas["ticker"]) == ["BBB"]


def test_menos_candidatos_que_el_top_devuelve_los_que_haya():
    compuestos, sectores = entradas([("AAA", 1.0, "Tech")])
    elegidas, _ = seleccionar(compuestos, sectores, tope=3, n=15)
    assert len(elegidas) == 1


def test_el_mapa_de_desplazamientos_atribuye_a_las_bloqueadoras():
    compuestos, sectores = entradas(
        [
            ("T1", 5.0, "Tech"),
            ("T2", 4.0, "Tech"),
            ("T3", 3.0, "Tech"),
            ("T4", 2.5, "Tech"),
        ]
    )
    _, desplazadas = seleccionar(compuestos, sectores, tope=3, n=4)
    mapa = desplazamientos_por_ticker(desplazadas)
    assert mapa == {"T1": ["T4"], "T2": ["T4"], "T3": ["T4"]}


def test_sin_candidatos_no_revienta():
    compuestos, sectores = entradas([])
    elegidas, desplazadas = seleccionar(compuestos, sectores)
    assert elegidas.empty and desplazadas.empty
    assert list(elegidas.columns) == [
        "ticker", "sector", "compuesto", "puesto_global", "puesto"
    ]
