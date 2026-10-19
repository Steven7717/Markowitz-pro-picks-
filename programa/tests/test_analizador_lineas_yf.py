"""Los estados de yfinance traducidos a las líneas de `fundamentals.concepts`."""

import numpy as np
import pandas as pd
import pytest

from analizador.lineas_yf import (
    FILAS,
    lineas_desde_estados,
    rejilla_trimestral,
    rellenar_desde_anual,
)
from fundamentals.concepts import LINEAS

NAN = float("nan")


def hoja(fechas: list[str], filas: dict) -> pd.DataFrame:
    """Una hoja como la entrega yfinance: filas por nombre, una columna por fecha."""
    return pd.DataFrame(filas, index=[pd.Timestamp(f) for f in fechas]).T


def test_cada_linea_del_motor_tiene_su_fila_de_yfinance():
    assert set(FILAS) == set(LINEAS)


def test_el_capex_llega_en_positivo_como_en_la_sec():
    flujos = hoja(["2026-06-30"], {"Capital Expenditure": [-9.265e9], "Operating Cash Flow": [1.8e10]})
    lineas = lineas_desde_estados(None, None, flujos)
    assert lineas.loc["2026-06-30", "capex"] == 9.265e9
    assert lineas.loc["2026-06-30", "flujo_operativo"] == 1.8e10


def test_sin_beneficio_operativo_se_usa_el_ebit_fila_a_fila():
    # BRK-B no trae `Operating Income`; otra empresa puede traerlo sólo a ratos.
    resultados = hoja(
        ["2026-06-30", "2026-03-31"],
        {"Operating Income": [NAN, 5.0], "EBIT": [7.0, 9.0]},
    )
    lineas = lineas_desde_estados(resultados, None, None)
    assert lineas["beneficio_operativo"].tolist() == [5.0, 7.0]


def test_el_beneficio_es_el_de_los_accionistas_comunes():
    resultados = hoja(
        ["2026-06-30"],
        {"Net Income": [2.116e10], "Net Income Common Stockholders": [2.075e10]},
    )
    assert lineas_desde_estados(resultados, None, None)["beneficio_neto"].iloc[0] == 2.075e10


def test_las_lineas_van_de_la_mas_antigua_a_la_mas_reciente_y_estan_todas():
    resultados = hoja(["2026-06-30", "2026-03-31"], {"Total Revenue": [2.0, 1.0]})
    lineas = lineas_desde_estados(resultados, None, None)
    assert list(lineas.index) == [pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")]
    assert list(lineas.columns) == list(LINEAS)
    assert lineas["ingresos"].tolist() == [1.0, 2.0]


def test_una_fecha_sin_ningun_dato_no_es_una_fila():
    # El balance de WALMEX trae la columna del 3T 2025 vacía.
    balance = hoja(
        ["2026-06-30", "2025-09-30"],
        {"Total Assets": [5.0e11, NAN], "Stockholders Equity": [2.4e11, NAN]},
    )
    lineas = lineas_desde_estados(None, balance, None)
    assert list(lineas.index) == [pd.Timestamp("2026-06-30")]


def test_sin_ninguna_hoja_no_hay_lineas():
    assert lineas_desde_estados(None, pd.DataFrame(), None).empty


def test_una_fecha_con_zona_y_hora_es_la_misma_fila_que_sin_ellas():
    resultados = hoja(["2026-06-30 16:00-04:00"], {"Total Revenue": [2.0]})
    balance = hoja(["2026-06-30"], {"Total Assets": [5.0]})
    lineas = lineas_desde_estados(resultados, balance, None)
    assert list(lineas.index) == [pd.Timestamp("2026-06-30")]
    assert lineas["ingresos"].iloc[0] == 2.0
    assert lineas["activos_totales"].iloc[0] == 5.0


# --- La rejilla trimestral ----------------------------------------------------


def _trimestres(fechas, ingresos):
    lineas = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    lineas["ingresos"] = ingresos
    return lineas


def test_el_trimestre_que_falta_tiene_su_fila_vacia():
    lineas = _trimestres(
        ["2025-03-31", "2025-06-30", "2025-12-31", "2026-03-31", "2026-06-30"],
        [1.0, 2.0, 4.0, 5.0, 6.0],
    )
    rejilla = rejilla_trimestral(lineas)
    assert list(rejilla.index) == list(
        pd.DatetimeIndex(
            ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
        )
    )
    assert np.isnan(rejilla.loc["2025-09-30", "ingresos"])
    assert rejilla.loc["2026-06-30", "ingresos"] == 6.0


def test_un_calendario_fiscal_consecutivo_no_cambia():
    # MU cierra trimestres en mayo, febrero, noviembre y agosto.
    fechas = ["2025-05-31", "2025-08-31", "2025-11-30", "2026-02-28", "2026-05-31"]
    lineas = _trimestres(fechas, [1.0, 2.0, 3.0, 4.0, 5.0])
    pd.testing.assert_frame_equal(
        rejilla_trimestral(lineas), lineas, check_freq=False, check_names=False
    )


def test_la_fila_que_falta_cae_tres_meses_despues_de_la_anterior():
    lineas = _trimestres(["2025-05-31", "2025-11-30"], [1.0, 3.0])
    assert rejilla_trimestral(lineas).index[1] == pd.Timestamp("2025-08-31")


def test_desde_un_fin_de_mes_la_fila_que_falta_cae_en_fin_de_mes():
    # `DateOffset(months=3)` conserva el día: del 30 de septiembre daría el 30
    # de diciembre, y el ejercicio de un 4T que falta acabaría un día antes.
    lineas = _trimestres(["2025-06-30", "2025-09-30", "2026-03-31"], [1.0, 2.0, 4.0])
    assert rejilla_trimestral(lineas).index[2] == pd.Timestamp("2025-12-31")


def test_desde_el_28_de_febrero_la_fila_que_falta_cae_el_31_de_mayo():
    lineas = _trimestres(["2025-02-28", "2025-08-31"], [1.0, 3.0])
    assert rejilla_trimestral(lineas).index[1] == pd.Timestamp("2025-05-31")


def test_fuera_de_un_fin_de_mes_la_fila_que_falta_conserva_el_dia():
    # `MonthEnd(3)` desde el 28 de enero daría el 31 de marzo: el mismo trimestre.
    lineas = _trimestres(["2025-01-28", "2025-07-29"], [1.0, 3.0])
    assert rejilla_trimestral(lineas).index[1] == pd.Timestamp("2025-04-28")


# --- El trimestre que falta, desde el anual -----------------------------------


def _anual(fecha, **valores):
    anual = pd.DataFrame(NAN, index=pd.DatetimeIndex([fecha]), columns=list(LINEAS))
    for linea, valor in valores.items():
        anual[linea] = valor
    return anual


def _rejilla_walmex():
    fechas = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    rejilla = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    rejilla["ingresos"] = [241.0, 246.0, NAN, 283.0, 245.0, 251.0]
    rejilla["acciones_diluidas"] = [17.35, 17.27, NAN, 17.38, 17.29, 17.16]
    rejilla["activos_totales"] = [480.0, 481.0, NAN, 495.0, 497.0, 506.0]
    return rejilla


def test_el_flujo_del_trimestre_que_falta_es_el_ano_menos_los_otros_tres():
    anual = _anual("2025-12-31", ingresos=1011.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert rellena.loc["2025-09-30", "ingresos"] == pytest.approx(1011.0 - 241.0 - 246.0 - 283.0)


def test_una_media_ponderada_se_rellena_como_media_y_no_como_suma():
    anual = _anual("2025-12-31", acciones_diluidas=17.37)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert rellena.loc["2025-09-30", "acciones_diluidas"] == pytest.approx(
        4 * 17.37 - 17.35 - 17.27 - 17.38
    )


def test_un_saldo_de_balance_no_se_rellena():
    # El activo a 30 de septiembre es una foto: el anual no dice nada de ella.
    anual = _anual("2025-12-31", activos_totales=495.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert np.isnan(rellena.loc["2025-09-30", "activos_totales"])


def test_con_dos_trimestres_vacios_no_se_inventa_ninguno():
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-06-30", "ingresos"] = NAN
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", ingresos=1011.0))
    assert rellena["ingresos"].isna().sum() == 2


def test_lo_que_ya_tiene_dato_no_se_toca():
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-09-30", "ingresos"] = 240.0
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", ingresos=9999.0))
    pd.testing.assert_frame_equal(rellena, rejilla)


def test_una_media_que_saldria_absurda_no_se_rellena():
    # Cuatro veces el anual menos tres trimestres multiplica cualquier error por
    # cuatro: fuera del doble o la mitad del anual no es una medición.
    anual = _anual("2025-12-31", acciones_diluidas=30.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert np.isnan(rellena.loc["2025-09-30", "acciones_diluidas"])


def test_tres_trimestres_a_cero_no_son_un_desglose():
    # WALMEX: Yahoo pone 0,0 de intereses en cada trimestre y 9.115 M en el
    # anual. Rellenar metería el año entero en el 3T 2025.
    rejilla = _rejilla_walmex()
    rejilla["gasto_por_intereses"] = [0.0, 0.0, NAN, 0.0, 0.0, 0.0]
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", gasto_por_intereses=9115.0))
    assert np.isnan(rellena.loc["2025-09-30", "gasto_por_intereses"])


def test_una_amortizacion_que_saldria_negativa_no_se_rellena():
    # HSBC 1T 2025: los tres trimestres conocidos suman más que el año.
    rejilla = _rejilla_walmex()
    rejilla["depreciacion_amortizacion"] = [100.0, 120.0, NAN, 130.0, 110.0, 115.0]
    rellena = rellenar_desde_anual(
        rejilla, _anual("2025-12-31", depreciacion_amortizacion=300.0)
    )
    assert np.isnan(rellena.loc["2025-09-30", "depreciacion_amortizacion"])


def test_unos_ingresos_negativos_entre_los_conocidos_no_rellenan():
    # GFNORTEO: un 2T 2025 con ingresos negativos inflaría el 3T rellenado.
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-06-30", "ingresos"] = -246.0
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", ingresos=1011.0))
    assert np.isnan(rellena.loc["2025-09-30", "ingresos"])


def test_unos_ingresos_negativos_rompen_el_trimestre_y_no_se_rellena_nada_del_ejercicio():
    # GFNORTEO: su 2T 2025 trae ingresos de -13.555 M y beneficio de -670 M, y
    # el beneficio del 3T rellenado salía en 28.296 M, 1,8 veces el resto. El
    # trimestre está roto entero, no sólo en sus ingresos.
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-06-30", "ingresos"] = -246.0
    rejilla["beneficio_neto"] = [10.0, 12.0, NAN, 15.0, 11.0, 13.0]
    rellena = rellenar_desde_anual(
        rejilla, _anual("2025-12-31", ingresos=1011.0, beneficio_neto=60.0)
    )
    assert np.isnan(rellena.loc["2025-09-30", "beneficio_neto"])


def test_un_interes_negativo_no_impide_rellenar_los_ingresos_ni_el_beneficio():
    # NVO: el 4T 2025 que deriva Yahoo trae un gasto por intereses negativo, y
    # los ingresos de su 1T 2025 rellenado (78.087 M DKK) cuadran con lo publicado.
    fechas = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    rejilla = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    rejilla["ingresos"] = [NAN, 76.9, 75.0, 77.0]
    rejilla["beneficio_neto"] = [NAN, 26.0, 20.0, 25.0]
    rejilla["gasto_por_intereses"] = [NAN, 1.0, 1.5, -0.5]
    anual = _anual("2025-12-31", ingresos=307.0, beneficio_neto=100.0, gasto_por_intereses=5.0)
    rellena = rellenar_desde_anual(rejilla, anual)
    assert rellena.loc["2025-03-31", "ingresos"] == pytest.approx(307.0 - 76.9 - 75.0 - 77.0)
    assert rellena.loc["2025-03-31", "beneficio_neto"] == pytest.approx(100.0 - 26.0 - 20.0 - 25.0)
    # La guarda de su propia línea sigue: el interés del 1T no se rellena.
    assert np.isnan(rellena.loc["2025-03-31", "gasto_por_intereses"])


def test_un_beneficio_negativo_si_se_rellena():
    # Perder dinero en un trimestre es posible: el signo no delata nada.
    rejilla = _rejilla_walmex()
    rejilla["beneficio_neto"] = [10.0, 12.0, NAN, 15.0, 11.0, 13.0]
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", beneficio_neto=20.0))
    assert rellena.loc["2025-09-30", "beneficio_neto"] == pytest.approx(-17.0)


def test_un_anual_de_transicion_no_es_un_ano():
    # Un ejercicio de seis meses: restarle tres trimestres no da el que falta.
    fechas = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"]
    rejilla = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    rejilla["beneficio_neto"] = [10.0, 10.0, NAN, 10.0]
    anuales = pd.DataFrame(
        NAN, index=pd.DatetimeIndex(["2024-12-31", "2025-06-30"]), columns=list(LINEAS)
    )
    anuales["beneficio_neto"] = [40.0, 20.0]
    rellena = rellenar_desde_anual(rejilla, anuales)
    assert np.isnan(rellena.loc["2025-03-31", "beneficio_neto"])


def test_las_filas_del_anual_solo_con_bpa_no_cuentan_como_ejercicio_anterior():
    # RY: su anual trae columnas a fechas trimestrales con sólo el BPA y el
    # recuento de doce meses móviles. Si contasen, ningún año suyo sería un año.
    anuales = pd.DataFrame(
        NAN,
        index=pd.DatetimeIndex(["2024-12-31", "2025-09-30", "2025-12-31"]),
        columns=list(LINEAS),
    )
    anuales["ingresos"] = [950.0, NAN, 1011.0]
    anuales["bpa_diluido"] = [3.0, 3.1, 3.2]
    rellena = rellenar_desde_anual(_rejilla_walmex(), anuales)
    assert rellena.loc["2025-09-30", "ingresos"] == pytest.approx(1011.0 - 241.0 - 246.0 - 283.0)


from datetime import date  # noqa: E402

from analizador.lineas_yf import fundamentos_anuales, kpis_trimestrales, lineas_de  # noqa: E402
from fundamentals.kpis import TODOS_LOS_KPIS  # noqa: E402


def _rejilla(n=6, hueco=None):
    fechas = pd.date_range("2025-03-31", periods=n, freq="QE")
    lineas = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    # En miles de millones: por debajo de `_MIN_PARTIDA_DE_BALANCE` (1e8) los
    # ingresos no son denominador y el margen saldría NaN.
    lineas["ingresos"] = [(100.0 + 10 * i) * 1e9 for i in range(n)]
    lineas["beneficio_operativo"] = [(20.0 + i) * 1e9 for i in range(n)]
    lineas["beneficio_neto"] = 10.0
    lineas["acciones_diluidas"] = 10.0
    lineas["bpa_diluido"] = 1.0
    if hueco is not None:
        lineas.iloc[hueco] = NAN
    return lineas


def test_los_kpis_son_los_del_motor_y_llevan_su_trimestre():
    lineas = _rejilla()
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    assert list(kpis.columns) == [*TODOS_LOS_KPIS, "trimestre"]
    assert kpis["margen_operativo"].iloc[0] == pytest.approx(20.0 / 100.0)
    assert kpis["trimestre"].iloc[0] == "2025Q1"
    assert kpis.index.name == "periodo"


def test_el_crecimiento_compara_con_el_mismo_trimestre_aunque_falte_uno():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    # El 1T 2026 (fila 4) contra el 1T 2025 (fila 0), con el 3T 2025 vacío en medio.
    assert kpis.loc["2026-03-31", "crecimiento_ingresos"] == pytest.approx(140.0 / 100.0 - 1)


def test_la_fila_que_solo_ocupaba_su_sitio_no_sale():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    assert pd.Timestamp("2025-09-30") not in kpis.index
    assert len(kpis) == 5


def test_sin_cuatro_trimestres_seguidos_no_hay_multiplo_de_doce_meses():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    # Las ventanas de cuatro que pasan por el hueco no suman; la última, tampoco.
    assert kpis["per"].isna().all()
    completa = _rejilla()
    kpis = kpis_trimestrales(completa, pd.Series(20.0, index=completa.index))
    assert kpis["per"].iloc[-1] == pytest.approx(20.0 / 4.0)


def test_sin_lineas_no_hay_kpis():
    vacias = pd.DataFrame(columns=list(LINEAS), dtype="float64")
    assert kpis_trimestrales(vacias, pd.Series(dtype="float64")).empty


# --- Los ejercicios anuales --------------------------------------------------


def _anuales(fechas, **columnas):
    anuales = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    for linea, valores in columnas.items():
        anuales[linea] = valores
    return anuales


def test_los_ejercicios_van_del_mas_reciente_al_mas_antiguo():
    anuales = _anuales(
        ["2022-08-31", "2023-08-31", "2024-08-31", "2025-08-31"],
        ingresos=[30.8, 15.5, 25.1, 37.4],
        flujo_operativo=[15.2, 1.6, 8.5, 17.5],
        capex=[12.1, 7.7, 8.4, 15.9],
        patrimonio_neto=[49.9, 44.1, 45.1, 54.2],
        deuda_total=[7.5, 13.9, 14.0, 15.3],
        efectivo=[8.3, 8.6, 7.0, 9.6],
    )
    f = fundamentos_anuales(anuales, "USD")
    assert [e.fin for e in f.ejercicios] == [
        date(2025, 8, 31), date(2024, 8, 31), date(2023, 8, 31), date(2022, 8, 31)
    ]
    assert f.ultimo.ingresos == 37.4 and f.ultimo.capex == 15.9
    # El balance es el del cierre del último ejercicio.
    assert (f.deuda_total, f.efectivo) == (15.3, 9.6)
    assert (f.moneda, f.fuente) == ("USD", "yfinance")


def test_un_ano_que_falta_corta_la_serie():
    # Saltarse el hueco devolvería ejercicios que ya no son años seguidos, y
    # `supuestos._cagr` toma `ejercicios[i]` como «hace i años».
    anuales = _anuales(["2021-12-31", "2023-12-31", "2024-12-31", "2025-12-31"], ingresos=1.0)
    assert len(fundamentos_anuales(anuales, "MXN").ejercicios) == 3


def test_una_fila_sin_ancla_entre_dos_anos_se_salta_y_no_corta_la_serie():
    # El anual de RY trae columnas a fechas trimestrales con sólo el BPA y el
    # recuento de doce meses móviles: no son años y no deben cortar la serie.
    anuales = _anuales(
        ["2022-10-31", "2023-07-31", "2023-10-31", "2024-07-31", "2024-10-31"],
        ingresos=[50.0, NAN, 55.0, NAN, 60.0],
        bpa_diluido=[1.0, 1.1, 1.2, 1.3, 1.4],
    )
    f = fundamentos_anuales(anuales, "CAD")
    assert [e.fin for e in f.ejercicios] == [
        date(2024, 10, 31), date(2023, 10, 31), date(2022, 10, 31)
    ]


def test_un_ano_que_esta_pero_sin_ingresos_corta_la_serie_por_la_distancia():
    # Saltar la fila sin ancla no puede convertirse en saltarse un año: el
    # siguiente con ancla está a dos años, y la distancia corta.
    anuales = _anuales(
        ["2023-12-31", "2024-12-31", "2025-12-31"], ingresos=[1.0, NAN, 1.0]
    )
    assert len(fundamentos_anuales(anuales, "USD").ejercicios) == 1


def test_un_banco_sin_ingresos_se_ancla_en_el_beneficio():
    anuales = _anuales(["2024-12-31", "2025-12-31"], beneficio_neto=[50.0, 55.0])
    assert len(fundamentos_anuales(anuales, "USD").ejercicios) == 2


def test_sin_ningun_ejercicio_valido_no_hay_fundamentos():
    assert fundamentos_anuales(_anuales(["2025-12-31"], efectivo=1.0), "USD") is None
    assert fundamentos_anuales(pd.DataFrame(columns=list(LINEAS)), "USD") is None


def test_lineas_de_junta_las_seis_hojas():
    trimestre = hoja(
        ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30", "2025-03-31"],
        {"Total Revenue": [251.0, 245.0, 283.0, 246.0, 241.0]},
    )
    anual = hoja(["2025-12-31"], {"Total Revenue": [1011.0]})
    estados = {
        "quarterly_income_stmt": trimestre,
        "quarterly_balance_sheet": pd.DataFrame(),
        "quarterly_cashflow": pd.DataFrame(),
        "income_stmt": anual,
        "balance_sheet": pd.DataFrame(),
        "cashflow": pd.DataFrame(),
    }
    trimestrales, anuales = lineas_de(estados)
    assert trimestrales.loc["2025-09-30", "ingresos"] == pytest.approx(241.0)
    assert anuales.loc["2025-12-31", "ingresos"] == 1011.0


# --- Los arreglos de la revisión de la Task 6 ---------------------------------


def test_el_trimestre_roto_pierde_sus_flujos_y_conserva_su_balance():
    # GFNORTEO 2T 2025: con ingresos de -13.555 M y beneficio de -670 M, su
    # margen neto salía en +0,049 con el signo al revés, y su ROE en -0,0027
    # entre vecinos de 0,23-0,27.
    fechas = ["2025-12-31", "2025-06-30", "2025-03-31"]
    resultados = hoja(
        fechas,
        {
            "Total Revenue": [57.8, -13.6, 63.4],
            "Net Income Common Stockholders": [15.9, -0.67, 15.3],
        },
    )
    balance = hoja(fechas, {"Stockholders Equity": [270.0, 265.0, 260.0]})
    trimestrales, _ = lineas_de(
        {"quarterly_income_stmt": resultados, "quarterly_balance_sheet": balance}
    )
    roto = trimestrales.loc["2025-06-30"]
    assert np.isnan(roto["ingresos"]) and np.isnan(roto["beneficio_neto"])
    assert roto["patrimonio_neto"] == 265.0
    assert trimestrales.loc["2025-03-31", "ingresos"] == 63.4


def test_el_trimestre_reconstruido_recibe_su_bpa_por_identidad():
    # yfinance no trae el BPA del trimestre que `rellenar_desde_anual`
    # reconstruye, y sin él ninguna ventana de cuatro que lo contenga tiene PER
    # de doce meses. Pasa en 25 de 79 tickers: WALMEX, AMXB, Samsung, TSM...
    fechas = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30", "2025-03-31"]
    beneficio = [12.0, 11.0, 15.0, 12.0, 10.0]
    acciones = [17.16, 17.29, 17.38, 17.27, 17.35]
    resultados = hoja(
        fechas,
        {
            "Total Revenue": [251.0, 245.0, 283.0, 246.0, 241.0],
            "Net Income Common Stockholders": beneficio,
            "Diluted Average Shares": acciones,
            "Diluted EPS": [b / a for b, a in zip(beneficio, acciones)],
        },
    )
    anual = hoja(
        ["2025-12-31"],
        {
            "Total Revenue": [1011.0],
            "Net Income Common Stockholders": [50.0],
            "Diluted Average Shares": [17.33],
        },
    )
    trimestrales, _ = lineas_de({"quarterly_income_stmt": resultados, "income_stmt": anual})
    tercero = trimestrales.loc["2025-09-30"]
    assert tercero["beneficio_neto"] == pytest.approx(50.0 - 10.0 - 12.0 - 15.0)
    assert tercero["bpa_diluido"] == pytest.approx(
        tercero["beneficio_neto"] / tercero["acciones_diluidas"]
    )


def test_una_fila_sin_ningun_kpi_no_ocupa_un_trimestre():
    # TM 2025-03-31, 6861.T o 4063.T: sólo el BPA y el recuento. Con los
    # diecisiete KPIs en NaN ocuparía uno de los cuatro trimestres de la ventana.
    lineas = _rejilla()
    lineas.loc["2025-03-31", ["ingresos", "beneficio_operativo", "beneficio_neto"]] = NAN
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    assert pd.Timestamp("2025-03-31") not in kpis.index
    assert len(kpis) == 5


def test_sin_lineas_el_frame_vacio_tiene_la_forma_del_panel():
    vacias = pd.DataFrame(columns=list(LINEAS), dtype="float64")
    kpis = kpis_trimestrales(vacias, pd.Series(dtype="float64"))
    assert list(kpis.columns) == [*TODOS_LOS_KPIS, "trimestre"]
    assert (kpis[list(TODOS_LOS_KPIS)].dtypes == "float64").all()
    assert kpis.index.name == "periodo"


def test_un_ejercicio_de_transicion_de_seis_meses_corta_la_serie():
    # Seis meses en 2024-06 contra doce en 2025-06: `_cagr` daría un 110 %.
    anuales = _anuales(
        ["2023-12-31", "2024-06-30", "2025-06-30"], ingresos=[100.0, 50.0, 105.0]
    )
    f = fundamentos_anuales(anuales, "USD")
    assert [e.fin for e in f.ejercicios] == [date(2025, 6, 30)]
