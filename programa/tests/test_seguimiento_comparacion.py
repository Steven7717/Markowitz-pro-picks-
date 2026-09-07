import pandas as pd
import pytest

from seguimiento import comparacion

FECHAS = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])

CIERRES = pd.DataFrame(
    {"AAPL": [100.0, 110.0, 121.0], "MSFT": [100.0, 100.0, 100.0]},
    index=FECHAS,
)


def test_una_referencia_invierte_cada_flujo_a_sus_pesos():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1210.0)


def test_reparte_por_los_pesos_y_no_rebalancea():
    # 50/50 el dia 5. El dia 7 AAPL vale 605 y MSFT 500: los pesos ya no son
    # 50/50, y eso es el punto. La referencia es "si hubieras seguido el plan",
    # no "si hubieras rebalanceado a diario".
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "MSFT": 0.5}, CIERRES)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_flujo_posterior_compra_a_los_precios_de_su_dia():
    # Los 1.000 del dia 6 compran AAPL a 110, no a 100. Si comprara a 100, la
    # referencia se estaria beneficiando de informacion que no tenia.
    flujos = pd.Series([0.0, 1000.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    assert valores.iloc[0] == pytest.approx(0.0)
    assert valores.iloc[1] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1100.0)


def test_un_retiro_saca_dinero_a_prorrata():
    flujos = pd.Series([1000.0, -500.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    # Dia 6: 1.100 menos 500 = 600. Dia 7: 600 * 1,1 = 660.
    assert valores.iloc[1] == pytest.approx(600.0)
    assert valores.iloc[2] == pytest.approx(660.0)


def test_equal_weight_reparte_entre_los_tickers_que_hay():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    pesos = comparacion.equal_weight(["AAPL", "MSFT"])
    assert pesos == {"AAPL": 0.5, "MSFT": 0.5}
    valores = comparacion.referencia(flujos, pesos, CIERRES)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_peso_sobre_un_ticker_sin_precios_no_se_invierte_en_el_aire():
    # Si ZZZZ no tiene precios, su parte se queda como efectivo en vez de
    # desaparecer: hacerla desaparecer haria que la referencia rindiera mejor
    # de lo que habria rendido.
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "ZZZZ": 0.5}, CIERRES)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(500.0 * 1.21 + 500.0)
