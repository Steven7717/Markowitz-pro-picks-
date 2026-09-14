"""Las lineas contra las que se mide la cartera, con las acciones corporativas dentro.

`referencia` recibe la `Historia` entera y no solo los cierres. La razon es la
misma que la de `seguimiento/precios.py`: los cierres van SIN ajustar, asi que
el dia de un split el precio se parte a la mitad y las participaciones compradas
antes tienen que duplicarse o la linea se hunde. Mientras recibio un DataFrame
de cierres no habia forma de que se enterara, y las dos desviaciones --split y
dividendos-- empujaban en la misma direccion: hacia hacer quedar bien a la
cartera del usuario contra su propia referencia.
"""

import pandas as pd
import pytest

from seguimiento import comparacion, precios

FECHAS = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])

CIERRES = pd.DataFrame(
    {"AAPL": [100.0, 110.0, 121.0], "MSFT": [100.0, 100.0, 100.0]},
    index=FECHAS,
)


def hist(cierres: pd.DataFrame, splits=None, dividendos=None) -> precios.Historia:
    """Una `Historia` de laboratorio, sin splits ni dividendos salvo que se pidan."""
    ceros = {t: [0.0] * len(cierres.index) for t in cierres.columns}
    return precios.Historia(
        cierres=cierres,
        dividendos=pd.DataFrame(dividendos or ceros, index=cierres.index),
        splits=pd.DataFrame(splits or ceros, index=cierres.index),
        sin_datos=[],
    )


HISTORIA = hist(CIERRES)


def test_una_referencia_invierte_cada_flujo_a_sus_pesos():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, HISTORIA)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1210.0)


def test_reparte_por_los_pesos_y_no_rebalancea():
    # 50/50 el dia 5. El dia 7 AAPL vale 605 y MSFT 500: los pesos ya no son
    # 50/50, y eso es el punto. La referencia es "si hubieras seguido el plan",
    # no "si hubieras rebalanceado a diario".
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "MSFT": 0.5}, HISTORIA)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_flujo_posterior_compra_a_los_precios_de_su_dia():
    # Los 1.000 del dia 6 compran AAPL a 110, no a 100. Si comprara a 100, la
    # referencia se estaria beneficiando de informacion que no tenia.
    flujos = pd.Series([0.0, 1000.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, HISTORIA)
    assert valores.iloc[0] == pytest.approx(0.0)
    assert valores.iloc[1] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1100.0)


def test_un_retiro_saca_dinero_a_prorrata():
    flujos = pd.Series([1000.0, -500.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, HISTORIA)
    # Dia 6: 1.100 menos 500 = 600. Dia 7: 600 * 1,1 = 660.
    assert valores.iloc[1] == pytest.approx(600.0)
    assert valores.iloc[2] == pytest.approx(660.0)


def test_un_hueco_de_precio_no_hunde_la_referencia_a_cero():
    # Aqui el hueco envenena mas que en `posiciones.serie`. Alli el total sale
    # de `.sum()`, que salta los NaN y los cuenta como cero: se pierde la parte
    # de ese activo. Aqui el valor del dia se suma `float()` a `float()`, asi
    # que un solo NaN convierte el total del dia entero en NaN y la linea de la
    # referencia desaparece del grafico.
    con_hueco = pd.DataFrame(
        {"AAPL": [100.0, float("nan"), 121.0], "MSFT": [100.0, 100.0, 100.0]},
        index=FECHAS,
    )
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, hist(con_hueco))
    assert not valores.isna().any()
    assert valores.iloc[1] == pytest.approx(1000.0)


def test_equal_weight_reparte_entre_los_tickers_que_hay():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    pesos = comparacion.equal_weight(["AAPL", "MSFT"])
    assert pesos == {"AAPL": 0.5, "MSFT": 0.5}
    valores = comparacion.referencia(flujos, pesos, HISTORIA)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_peso_sobre_un_ticker_sin_precios_no_se_invierte_en_el_aire():
    # Si ZZZZ no tiene precios, su parte se queda como efectivo en vez de
    # desaparecer: hacerla desaparecer haria que la referencia rindiera mejor
    # de lo que habria rendido.
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "ZZZZ": 0.5}, HISTORIA)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(500.0 * 1.21 + 500.0)


# --- Las acciones corporativas -----------------------------------------------

DIAS = pd.to_datetime([
    "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15",
])


def historia_acme() -> precios.Historia:
    """El mismo libro de prueba que el resto de la auditoria: 2:1 y 2,00/accion.

    Cierres SIN ajustar: 100 hasta el split del dia 12 y 50 a partir de el.
    """
    return precios.Historia(
        cierres=pd.DataFrame({"ACME": [100.0] * 5 + [50.0] * 4}, index=DIAS),
        dividendos=pd.DataFrame(
            {"ACME": [0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=DIAS
        ),
        splits=pd.DataFrame(
            {"ACME": [0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0]}, index=DIAS
        ),
        sin_datos=[],
    )


def test_un_split_no_hunde_la_linea_de_referencia():
    """El defecto, medido: 500,00 donde lo correcto son 1.020,00.

    Diez participaciones compradas a 100 valen 1.000. El dia del split pasan a
    ser veinte y el cierre baja a 50, asi que la linea no se mueve. Sin aplicar
    el split, las diez se valoran al cierre partido y la referencia pierde el
    51% de su valor en un dia -- y el grafico concluye que la cartera del
    usuario le saca un 114% a repartir por igual.
    """
    flujos = pd.Series([1000.0] + [0.0] * 8, index=DIAS)
    valores = comparacion.referencia(flujos, {"ACME": 1.0}, historia_acme())
    assert valores.iloc[-1] == pytest.approx(1020.0)


def test_el_dividendo_de_la_referencia_se_queda_como_efectivo():
    """Ni desaparece ni se reinvierte.

    Desaparecer rebajaria la referencia con un cobro que si ocurrio. Y
    reinvertirlo la haria rebalancear, que es justo lo que ninguna de estas
    lineas hace: `posiciones.serie` lo deja en caja, y la comparacion tiene que
    medir lo mismo de las dos partes.
    """
    sin_split = precios.Historia(
        cierres=pd.DataFrame({"ACME": [100.0] * 9}, index=DIAS),
        dividendos=pd.DataFrame(
            {"ACME": [0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=DIAS
        ),
        splits=pd.DataFrame({"ACME": [0.0] * 9}, index=DIAS),
        sin_datos=[],
    )
    flujos = pd.Series([1000.0] + [0.0] * 8, index=DIAS)
    valores = comparacion.referencia(flujos, {"ACME": 1.0}, sin_split)
    # Diez participaciones por 2,00 son 20 de caja, y las diez siguen a 100.
    assert valores.iloc[3] == pytest.approx(1020.0)
    assert valores.iloc[-1] == pytest.approx(1020.0)


def test_quien_compra_el_dia_ex_no_cobra_ese_dividendo():
    # Misma regla que en `posiciones.serie`: para cobrar hay que tener las
    # participaciones al cierre anterior. Sin esta foto, la referencia cobra un
    # dividendo que el mercado ya habia descontado del precio al que compro.
    flujos = pd.Series([0.0, 0.0, 0.0, 1000.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=DIAS)
    valores = comparacion.referencia(flujos, {"ACME": 1.0}, historia_acme())
    assert valores.iloc[3] == pytest.approx(1000.0)


def test_una_referencia_con_split_cuadra_con_lo_que_valdria_a_mano():
    # 1.000 el dia 5 y 1.000 mas el dia 13, ya despues del split. Las primeras
    # diez participaciones son veinte; las segundas son veinte compradas a 50.
    # Cuarenta a 50 son 2.000, mas los 20 del dividendo.
    flujos = pd.Series(
        [1000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1000.0, 0.0, 0.0], index=DIAS
    )
    valores = comparacion.referencia(flujos, {"ACME": 1.0}, historia_acme())
    assert valores.iloc[-1] == pytest.approx(2020.0)
