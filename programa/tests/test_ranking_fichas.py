import json

import numpy as np
import pandas as pd
import pytest

from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.fichas import descriptor, ficha_numerica


def serie(valores: dict[str, float]) -> pd.Series:
    base = pd.Series(np.nan, index=list(TODOS_LOS_KPIS), dtype="float64")
    for kpi, valor in valores.items():
        base[kpi] = valor
    return base


def ficha_ejemplo(**cambios):
    z = serie({kpi: 0.0 for kpi in TODOS_LOS_KPIS})
    z["roic"] = 2.5
    z["per"] = 2.0  # z alto en un múltiplo = caro = flojo
    valores = serie({kpi: 1.0 for kpi in TODOS_LOS_KPIS})
    valores["roic"] = 0.31
    valores["per"] = 34.2
    argumentos = {
        "ticker": "AAA",
        "sector": "Information Technology",
        "puesto": 3,
        "compuesto": 1.42,
        "pilares": pd.Series(
            {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1}
        ),
        "conteo": pd.Series(
            {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3}
        ),
        "z": z,
        "valores": valores,
        "desplazo_a": [],
    }
    argumentos.update(cambios)
    return ficha_numerica(**argumentos)


def test_recoge_identidad_puesto_y_pilares():
    ficha = ficha_ejemplo()
    assert ficha["ticker"] == "AAA"
    assert ficha["puesto"] == 3
    assert ficha["pilares"]["calidad"] == 1.9
    assert ficha["cobertura"] == {
        "kpis_con_dato": 17,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {
            "calidad": 7,
            "crecimiento": 3,
            "valoracion": 4,
            "solidez": 3,
        },
    }


def test_el_multiplo_caro_sale_entre_los_flojos_no_entre_los_destacados():
    # El z crudo de per es +2, el segundo más alto. Sin aplicar el signo, la
    # ficha presumiría de estar cara.
    ficha = ficha_ejemplo()
    assert ficha["destacados"][0]["kpi"] == "roic"
    assert ficha["flojos"][0]["kpi"] == "per"
    assert ficha["flojos"][0]["valor"] == 34.2


def test_destacados_y_flojos_no_se_solapan():
    # Con los 17 KPIs medidos no hay solape que detectar: este test documenta
    # la intención, y el que muerde de verdad es el de pocos KPIs.
    ficha = ficha_ejemplo()
    destacados = {item["kpi"] for item in ficha["destacados"]}
    flojos = {item["kpi"] for item in ficha["flojos"]}
    assert destacados.isdisjoint(flojos)


def test_con_pocos_kpis_no_repite_ninguno():
    # Con menos de seis KPIs medidos, destacados y flojos podrían solaparse.
    z = serie({"roe": 2.0, "roic": 1.0, "per": 1.0, "razon_corriente": 0.5})
    valores = serie({"roe": 0.2, "roic": 0.1, "per": 20.0, "razon_corriente": 1.5})
    ficha = ficha_ejemplo(z=z, valores=valores)
    destacados = [item["kpi"] for item in ficha["destacados"]]
    flojos = [item["kpi"] for item in ficha["flojos"]]
    assert len(set(destacados + flojos)) == len(destacados + flojos)


def test_ignora_los_kpis_sin_dato():
    z = serie({"roe": 1.0, "roic": 0.5})
    valores = serie({"roe": 0.2, "roic": 0.1})
    ficha = ficha_ejemplo(z=z, valores=valores)
    citados = {item["kpi"] for item in ficha["destacados"] + ficha["flojos"]}
    assert citados == {"roe", "roic"}


def test_la_ficha_nace_sin_narrativa():
    ficha = ficha_ejemplo()
    assert ficha["narrativa"] is None
    assert ficha["generada_por"] == "plantilla"


def test_un_pilar_sin_medir_sale_como_nulo_no_como_cero():
    pilares = pd.Series(
        {"calidad": 1.9, "crecimiento": float("nan"), "valoracion": -0.2, "solidez": 1.1}
    )
    conteo = pd.Series({"calidad": 7, "crecimiento": 0, "valoracion": 4, "solidez": 3})
    ficha = ficha_ejemplo(pilares=pilares, conteo=conteo)
    assert ficha["pilares"]["crecimiento"] is None
    assert ficha["cobertura"]["pilares_con_dato"] == 3


def test_la_cobertura_dice_cuantos_kpis_sostienen_cada_pilar():
    # Un pilar que descansa en un solo KPI y otro que descansa en siete dan el
    # mismo numero y no valen lo mismo. Sin este recuento, la interfaz no puede
    # distinguirlos y el revisor lee un +6,39 sostenido por una sola linea del
    # balance como si lo sostuvieran tres.
    conteo = pd.Series({"calidad": 7, "crecimiento": 0, "valoracion": 4, "solidez": 1})
    ficha = ficha_ejemplo(conteo=conteo)
    assert ficha["cobertura"]["kpis_por_pilar"] == {
        "calidad": 7,
        "crecimiento": 0,
        "valoracion": 4,
        "solidez": 1,
    }
    # Enteros de Python, no de numpy: json.dumps revienta con los segundos y
    # fichas.json es el contrato con el sub-proyecto C.
    json.dumps(ficha["cobertura"], allow_nan=False)


def test_la_ficha_es_serializable_a_json_estricto():
    # fichas.json es el contrato con el sub-proyecto C. Dos cosas lo rompen: un
    # tipo de numpy, que hace reventar a json.dumps, y un NaN, que json.dumps
    # acepta por defecto y escribe como el literal `NaN` —que no es JSON válido
    # y que un parser estricto rechaza. allow_nan=False es el contrato de verdad.
    json.dumps(ficha_ejemplo(), allow_nan=False)


def test_una_ficha_con_pilares_sin_medir_sigue_siendo_json_estricto():
    pilares = pd.Series(
        {"calidad": 1.9, "crecimiento": float("nan"), "valoracion": -0.2, "solidez": 1.1}
    )
    conteo = pd.Series({"calidad": 7, "crecimiento": 0, "valoracion": 4, "solidez": 3})
    z = serie({"roe": 1.0, "roic": 0.5})
    valores = serie({"roe": 0.2, "roic": 0.1})
    ficha = ficha_ejemplo(pilares=pilares, conteo=conteo, z=z, valores=valores)

    json.dumps(ficha, allow_nan=False)


def test_una_ficha_sin_compuesto_no_se_puede_serializar():
    # Una empresa sin compuesto no debería haber sido seleccionada: la
    # selección descarta los NaN. Que reviente al escribir el fichero es
    # preferible a un `null` que disimula un estado imposible.
    ficha = ficha_ejemplo(compuesto=float("nan"))
    with pytest.raises(ValueError):
        json.dumps(ficha, allow_nan=False)


def test_el_descriptor_traduce_el_z_a_palabras_sin_digitos():
    assert descriptor(2.0) == "muy por encima de sus pares"
    assert descriptor(0.0) == "en línea con sus pares"
    assert descriptor(-2.0) == "muy por debajo de sus pares"
    for z in (-3.0, -1.0, 0.0, 1.0, 3.0):
        assert not any(c.isdigit() for c in descriptor(z))
