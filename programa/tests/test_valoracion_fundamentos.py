import math
from datetime import date
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from fundamentals.concepts import LINEAS
from fundamentals.fallos import SYSTEMIC
from fundamentals.fetch import CorridaAbortada, CoverageReport
from tests.test_fundamentals_panel import _facts, _hecho, _trimestres
from valoracion.fundamentos import (
    TRIMESTRES,
    Ejercicio,
    Fundamentos,
    desde_lineas,
    desde_sec,
)

# Cuánto crece cada flujo por trimestre. Distintos entre sí a propósito: si dos
# columnas se cruzaran al construir el `Ejercicio`, un test con cifras iguales
# no lo notaría.
_MULTIPLOS = {
    "ingresos": 1.0,
    "flujo_operativo": 2.0,
    "capex": 3.0,
    "gasto_por_intereses": 4.0,
    "beneficio_operativo": 5.0,
    "beneficio_neto": 6.0,
}
_BALANCE = {"patrimonio_neto": 2000.0, "deuda_total": 500.0, "efectivo": 100.0}


def lineas(n: int = 20, fechas=None, **columnas) -> pd.DataFrame:
    """Un panel con la forma de `resolve_lines`: trimestres, una columna por línea.

    Cada flujo vale `múltiplo * k` en el trimestre k (1, 2, 3...), de modo que el
    TTM que acaba en el trimestre k vale `múltiplo * (4k - 6)` y cada ejercicio
    tiene cifras distintas de las de su vecino.
    """
    if fechas is None:
        fechas = (
            pd.period_range("2021Q4", periods=n, freq="Q")
            .to_timestamp(how="end")
            .normalize()
        )
    marco = pd.DataFrame(float("nan"), index=fechas, columns=list(LINEAS), dtype="float64")
    valores = {
        linea: [multiplo * k for k in range(1, len(fechas) + 1)]
        for linea, multiplo in _MULTIPLOS.items()
    }
    valores.update(_BALANCE)
    valores.update(columnas)
    for columna, valor in valores.items():
        marco[columna] = valor
    return marco


def flujos(ejercicio: Ejercicio) -> tuple[float, ...]:
    return (
        ejercicio.ingresos,
        ejercicio.flujo_operativo,
        ejercicio.capex,
        ejercicio.gasto_financiero,
        ejercicio.beneficio_operativo,
        ejercicio.beneficio_neto,
    )


def test_los_flujos_de_cada_ejercicio_son_la_suma_de_sus_cuatro_trimestres():
    f = desde_lineas(lineas(), "USD", "sec")
    # 17+18+19+20 = 74 de ingresos; el resto, por su múltiplo.
    assert flujos(f.ultimo) == (74.0, 148.0, 222.0, 296.0, 370.0, 444.0)
    # 13+14+15+16 = 58.
    assert flujos(f.ejercicios[1]) == (58.0, 116.0, 174.0, 232.0, 290.0, 348.0)
    # 1+2+3+4 = 10: el ejercicio más antiguo, que cierra en el cuarto trimestre.
    assert flujos(f.ejercicios[4]) == (10.0, 20.0, 30.0, 40.0, 50.0, 60.0)


def test_un_ejercicio_cada_cuatro_trimestres_del_mas_reciente_al_mas_antiguo():
    f = desde_lineas(lineas(), "USD", "sec")
    assert [e.fin for e in f.ejercicios] == [
        date(2026, 9, 30),
        date(2025, 9, 30),
        date(2024, 9, 30),
        date(2023, 9, 30),
        date(2022, 9, 30),
    ]


def test_el_balance_es_el_del_ultimo_trimestre():
    marco = lineas()
    marco["deuda_total"] = range(len(marco))
    marco["efectivo"] = [10.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.deuda_total == len(marco) - 1
    assert f.efectivo == 10.0 * (len(marco) - 1)


def test_el_balance_es_el_del_trimestre_que_cierra_el_ultimo_ejercicio():
    # Si el último trimestre no tiene resultados, el ejercicio más reciente cierra
    # en el anterior, y el balance de otro trimestre no es el de ese cierre.
    marco = lineas()
    marco["deuda_total"] = [1000.0 + i for i in range(len(marco))]
    marco["efectivo"] = [10.0 * i for i in range(len(marco))]
    marco.loc[marco.index[-1], ["ingresos", "beneficio_neto"]] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == marco.index[-2].date()
    assert f.deuda_total == 1000.0 + (len(marco) - 2)
    assert f.efectivo == 10.0 * (len(marco) - 2)


def test_el_patrimonio_de_cada_ejercicio_es_el_de_su_cierre():
    marco = lineas()
    marco["patrimonio_neto"] = [100.0 * i for i in range(len(marco))]
    f = desde_lineas(marco, "USD", "sec")
    assert f.ejercicios[0].patrimonio_neto == 1900.0
    assert f.ejercicios[1].patrimonio_neto == 1500.0


def test_el_ultimo_ejercicio_es_el_ultimo_con_resultados_de_doce_meses():
    marco = lineas()
    marco.loc[marco.index[-1], ["ingresos", "beneficio_neto"]] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == date(2026, 6, 30)
    assert len(f.ejercicios) == 4


def test_si_al_ultimo_trimestre_solo_le_faltan_los_ingresos_retrocede_al_ultimo_que_los_tiene():
    # El beneficio neto del último trimestre existe, pero el ancla de una empresa
    # con ingresos son sus ingresos: un ejercicio más reciente con ingresos
    # vacíos le costaría el DCF por una etiqueta que falta en un solo informe.
    marco = lineas()
    marco.loc[marco.index[-1], "ingresos"] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == date(2026, 6, 30)
    assert f.ultimo.ingresos == 70.0  # 16+17+18+19
    assert f.ultimo.beneficio_neto == 420.0
    assert len(f.ejercicios) == 4


def test_un_banco_sin_linea_de_ingresos_tiene_ejercicios_con_beneficio_y_patrimonio():
    f = desde_lineas(lineas(ingresos=float("nan")), "USD", "sec")
    assert math.isnan(f.ultimo.ingresos)
    assert f.ultimo.beneficio_neto == 444.0
    assert f.ultimo.patrimonio_neto == 2000.0
    assert len(f.ejercicios) == 5


def test_un_banco_se_ancla_en_el_ultimo_trimestre_con_beneficio_neto():
    marco = lineas(ingresos=float("nan"))
    marco.loc[marco.index[-1], "beneficio_neto"] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    assert f.ultimo.fin == date(2026, 6, 30)
    assert math.isnan(f.ultimo.ingresos)
    assert f.ultimo.beneficio_neto == 420.0
    assert len(f.ejercicios) == 4


def test_sin_beneficio_neto_los_ingresos_bastan():
    f = desde_lineas(lineas(beneficio_neto=float("nan")), "USD", "sec")
    assert f.ultimo.ingresos == 74.0
    assert math.isnan(f.ultimo.beneficio_neto)
    assert len(f.ejercicios) == 5


def test_sin_ingresos_ni_beneficio_neto_no_hay_fundamentos():
    marco = lineas(ingresos=float("nan"), beneficio_neto=float("nan"))
    assert desde_lineas(marco, "USD", "sec") is None


def test_menos_de_cuatro_trimestres_no_dan_fundamentos():
    assert desde_lineas(lineas(3), "USD", "sec") is None


def test_un_panel_vacio_no_da_fundamentos():
    assert desde_lineas(lineas(0), "USD", "sec") is None


def test_un_hueco_de_datos_corta_la_serie_en_vez_de_saltarse():
    marco = lineas()
    marco.loc[marco.index[11], ["ingresos", "beneficio_neto"]] = float("nan")
    f = desde_lineas(marco, "USD", "sec")
    # Saltar el hueco habría devuelto además 2023-09-30 y 2022-09-30, que ya no
    # distan un año del 2025-09-30: `ejercicios[2]` habría dejado de ser «hace 2 años».
    assert [e.fin for e in f.ejercicios] == [date(2026, 9, 30), date(2025, 9, 30)]


def test_un_trimestre_que_falta_en_el_panel_corta_la_serie_en_vez_de_deriva():
    marco = lineas()
    sin_trimestre = marco.drop(marco.index[6])  # 2023-06-30
    f = desde_lineas(sin_trimestre, "USD", "sec")
    assert [e.fin for e in f.ejercicios] == [
        date(2026, 9, 30),
        date(2025, 9, 30),
        date(2024, 9, 30),
    ]
    fines = [e.fin for e in f.ejercicios]
    assert all((a - b).days <= 380 for a, b in zip(fines, fines[1:]))


def test_un_ejercicio_por_ano_aunque_el_cuarto_trimestre_dure_dieciseis_semanas():
    # 52 semanas son 84+84+84+112 días; la de 53 suma otros siete en un trimestre.
    dias = [0] + [112 if i % 4 == 3 else 84 for i in range(1, 20)]
    dias[11] = 119
    fechas = pd.DatetimeIndex(pd.Timestamp("2021-10-02") + pd.to_timedelta(np.cumsum(dias), unit="D"))
    f = desde_lineas(lineas(fechas=fechas), "USD", "sec")
    assert [e.fin for e in f.ejercicios] == [
        date(2026, 7, 11),
        date(2025, 7, 12),
        date(2024, 7, 13),
        date(2023, 7, 8),
        date(2022, 7, 9),
    ]


@pytest.mark.parametrize("dias", [81, 99])
def test_cuatro_filas_que_no_distan_un_ano_no_forman_dos_ejercicios(dias):
    # Cada ventana de cuatro trimestres es válida por separado (243 o 297 días),
    # pero dos cierres a cuatro filas de distancia quedan a 324 o 396 días: ni
    # uno ni otro es «un año después», así que sólo cuenta el más reciente.
    fechas = pd.Timestamp("2021-01-01") + pd.to_timedelta(np.arange(20) * dias, unit="D")
    f = desde_lineas(lineas(fechas=fechas), "USD", "sec")
    assert len(f.ejercicios) == 1


def test_fundamentos_sin_ejercicios_no_existe():
    with pytest.raises(ValueError):
        Fundamentos(moneda="USD", fuente="sec", ejercicios=(), deuda_total=0.0, efectivo=0.0)


def test_sin_hechos_de_la_sec_lo_dice():
    vacio = ({}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=vacio):
        assert desde_sec("TST") == (None, "sin_estados")


def test_una_corrida_abortada_no_se_propaga():
    error = CorridaAbortada(SYSTEMIC, "x", CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", side_effect=error):
        assert desde_sec("TST") == (None, "sin_estados")


def test_un_fallo_que_no_es_de_la_fuente_se_propaga():
    with patch("valoracion.fundamentos.load_facts", side_effect=OSError("caché ilegible")):
        with pytest.raises(OSError):
            desde_sec("TST")


def test_desde_sec_pide_veinte_trimestres_y_construye():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ) as panel, patch(
        "valoracion.fundamentos.resolve_lines", return_value=(lineas(), [])
    ), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        fundamentos, motivo = desde_sec("TST")
    assert motivo == "ok"
    assert fundamentos.moneda == "USD" and fundamentos.fuente == "sec"
    assert panel.call_args.kwargs["n_periodos"] == TRIMESTRES == 20


def test_desde_sec_sin_historia_suficiente_lo_dice():
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ), patch("valoracion.fundamentos.resolve_lines", return_value=(lineas(2), [])), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", side_effect=lambda x: x
    ), patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ):
        assert desde_sec("TST") == (None, "sin_historia")


def test_desde_sec_reconcilia_el_recuento_de_acciones_antes_de_completar_el_bpa():
    # El mismo orden que `fundamentals.run.build_panel`: la identidad del BPA se
    # apoya en un recuento de acciones que ya está en la base correcta.
    resueltas = lineas()
    reconciliadas = lineas()
    hechos = ({"TST": pd.DataFrame({"concept": ["x"]})}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos), patch(
        "valoracion.fundamentos.quarterly_panel", return_value=pd.DataFrame()
    ), patch("valoracion.fundamentos.resolve_lines", return_value=(resueltas, [])), patch(
        "valoracion.fundamentos.reconciliar_recuento_de_acciones", return_value=reconciliadas
    ) as reconciliar, patch(
        "valoracion.fundamentos.completar_bpa_por_identidad", side_effect=lambda x: x
    ) as completar:
        padre = Mock()
        padre.attach_mock(reconciliar, "reconciliar")
        padre.attach_mock(completar, "completar")
        desde_sec("TST")
    assert [llamada[0] for llamada in padre.mock_calls] == ["reconciliar", "completar"]
    assert reconciliar.call_args.args[0] is resueltas
    assert completar.call_args.args[0] is reconciliadas


def _flujo_trimestral(concepto: str, multiplo: float) -> list[dict]:
    """Veinte trimestres naturales (2021-2025) con `multiplo * k` en el k-ésimo."""
    filas: list[dict] = []
    for i, ano in enumerate(range(2021, 2026)):
        valores = [multiplo * (4 * i + q) for q in range(1, 5)]
        filas += _trimestres(concepto, valores=valores, ano=ano)
    return filas


def _balance_trimestral(concepto: str, valores: list[float]) -> list[dict]:
    fines = pd.date_range("2021-03-31", periods=len(valores), freq="QE")
    return [
        _hecho(concepto, valor, None, fin.strftime("%Y-%m-%d"), tipo="instant")
        for valor, fin in zip(valores, fines)
    ]


def test_desde_sec_de_punta_a_punta_con_el_motor_de_verdad():
    # Sólo se sustituye la red: `quarterly_panel`, `resolve_lines` y las
    # reconciliaciones son las reales, y es donde se rompe el contrato de signos.
    filas = (
        _flujo_trimestral("us-gaap:Revenues", 1.0)
        + _flujo_trimestral("us-gaap:NetCashProvidedByUsedInOperatingActivities", 2.0)
        # Un pago, y la SEC lo declara en positivo.
        + _flujo_trimestral("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", 3.0)
        + _balance_trimestral("us-gaap:LongTermDebt", [1000.0 + k for k in range(1, 21)])
        + _balance_trimestral("us-gaap:CashAndCashEquivalentsAtCarryingValue", [10.0 * k for k in range(1, 21)])
    )
    hechos = ({"TST": _facts(filas)}, CoverageReport(requested=["TST"]))
    with patch("valoracion.fundamentos.load_facts", return_value=hechos):
        f, motivo = desde_sec("TST")
    assert motivo == "ok"
    assert [e.fin for e in f.ejercicios] == [
        date(2025, 12, 31),
        date(2024, 12, 31),
        date(2023, 12, 31),
        date(2022, 12, 31),
        date(2021, 12, 31),
    ]
    assert f.ultimo.ingresos == 74.0
    assert f.ultimo.flujo_operativo == 148.0
    assert f.ultimo.capex == 222.0 > 0
    assert f.ejercicios[1].ingresos == 58.0
    assert f.ejercicios[1].flujo_operativo == 116.0
    assert f.ejercicios[1].capex == 174.0
    assert f.deuda_total == 1020.0
    assert f.efectivo == 200.0
