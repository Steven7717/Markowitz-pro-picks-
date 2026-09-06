from datetime import date

import numpy as np
import pandas as pd
import pytest

from seguimiento import rendimiento


def serie(valores, fechas=None) -> pd.Series:
    # `is None` y no `or`: un DatetimeIndex no tiene valor de verdad, asi que
    # `fechas or ...` revienta con ValueError en cuanto alguien pasa fechas.
    if fechas is None:
        fechas = pd.bdate_range("2026-01-05", periods=len(valores))
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


def test_sin_flujos_el_twr_es_el_retorno_simple():
    valor = serie([100.0, 110.0, 121.0])
    flujos = serie([0.0, 0.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_una_aportacion_no_cuenta_como_ganancia():
    # Sin descontar el flujo, meter 100 en una cartera de 100 se leeria como un
    # 100% de rentabilidad en un dia. Es el error que hace falta que no ocurra.
    valor = serie([100.0, 200.0, 200.0])
    flujos = serie([0.0, 100.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.0)


def test_el_twr_calculado_a_mano_no_es_el_retorno_simple():
    # 100 -> 110 (+10%), se aportan 90, 200 -> 220 (+10%). El TWR es 1,1*1,1-1
    # = 21%. El retorno simple sobre lo aportado daria (220-190)/190 = 15,8%.
    # Este test existe para que el dia que alguien "simplifique" la formula,
    # falle.
    valor = serie([100.0, 200.0, 220.0])
    flujos = serie([0.0, 90.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_un_valor_inicial_de_cero_no_revienta_ni_devuelve_infinito():
    # Pasa el primer dia y cada vez que la cartera se vacia y vuelve a empezar.
    valor = serie([0.0, 100.0, 110.0])
    flujos = serie([0.0, 100.0, 0.0])
    resultado = rendimiento.twr(valor, flujos)
    assert np.isfinite(resultado)
    assert resultado == pytest.approx(0.1)


def test_anualizar_por_debajo_del_minimo_no_se_hace():
    # Un 2% en tres dias anualiza a +780%. Devolver eso seria una afirmacion
    # que los datos no sostienen.
    assert rendimiento.anualizar(0.02, dias=3) is None


def test_anualizar_por_encima_del_minimo_si_se_hace():
    assert rendimiento.anualizar(0.10, dias=365) == pytest.approx(0.10)


def test_anualizar_medio_ano_capitaliza():
    assert rendimiento.anualizar(0.10, dias=182.5) == pytest.approx(0.21, abs=1e-3)


def test_el_minimo_es_treinta_dias():
    assert rendimiento.MINIMO_DIAS_ANUALIZAR == 30
    assert rendimiento.anualizar(0.02, dias=29) is None
    assert rendimiento.anualizar(0.02, dias=30) is not None


def test_un_solo_flujo_da_la_tasa_anualizada_conocida():
    # 1.000 fuera hoy, 1.100 dentro de un ano: 10% anual, exacto.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), 1100.0)]
    assert rendimiento.tir(flujos) == pytest.approx(0.10, abs=1e-4)


def test_dos_aportaciones_dan_una_tir_entre_las_dos_tasas():
    flujos = [
        (date(2026, 1, 1), -1000.0),
        (date(2026, 7, 1), -1000.0),
        (date(2027, 1, 1), 2200.0),
    ]
    resultado = rendimiento.tir(flujos)
    assert 0.10 < resultado < 0.30


def test_sin_cambio_de_signo_no_hay_tir_y_se_dice():
    # Todos los flujos negativos: no existe tasa que los anule. Devolver la
    # primera raiz que aparezca seria inventar un numero indistinguible de uno
    # real.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), -500.0)]
    assert rendimiento.tir(flujos) is None


def test_un_solo_flujo_tampoco_tiene_tir():
    assert rendimiento.tir([(date(2026, 1, 1), -1000.0)]) is None


def test_una_lista_de_flujos_vacia_no_revienta():
    # Este es el que pinza `if len(flujos) < 2`. El de un solo flujo NO lo
    # pinza: con un elemento, `dias` sale 0, cae por debajo del minimo de 30 y
    # la guarda de los dias devuelve None igual, asi que el guard se puede
    # borrar entero sin que ese test se entere. Con la lista vacia no hay
    # escapatoria -- sin el guard, `ordenados[-1]` lanza IndexError.
    assert rendimiento.tir([]) is None


def test_un_periodo_corto_no_devuelve_una_tir_anualizada_absurda():
    # 1% en tres dias: la tasa anual equivalente es del 236%, y cae DENTRO del
    # intervalo de busqueda. Sin la guarda de los 30 dias, brentq la encuentra
    # y `tir()` devuelve ese 2,36 como si alguien lo hubiera medido.
    #
    # La version anterior de este test usaba 2%, y pasaba por casualidad: su
    # tasa equivalente es 10,126, apenas por encima del techo de 10, asi que lo
    # cortaba la guarda del INTERVALO y no la de los dias. Con 1,9% el mismo
    # test ya devolvia 8,87. De ahi el assert de la precondicion, que es lo que
    # impide que vuelva a pasar por el motivo equivocado.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2026, 1, 4), 1010.0)]

    ordenados = sorted(flujos, key=lambda par: par[0])
    bajo = rendimiento._valor_actual(ordenados, rendimiento._SUELO_TIR)
    alto = rendimiento._valor_actual(ordenados, rendimiento._TECHO_TIR)
    assert (bajo > 0) != (alto > 0), (
        "la raiz cae fuera del intervalo, asi que este caso no prueba la guarda "
        "de los dias sino la del intervalo"
    )

    assert rendimiento.tir(flujos) is None


def test_control_negativo_una_sola_compra_ata_las_tres_medidas():
    # Cartera de una sola compra, sin aportaciones posteriores, sin dividendos
    # y sin comision. Las tres medidas estan ligadas por identidad:
    #   - TWR sin anualizar == retorno simple
    #   - TIR == TWR anualizado
    # Escrito como "los tres numeros coinciden" el test seria falso: la TIR
    # viene anualizada y el retorno simple no. Pasaria o fallaria por la razon
    # equivocada.
    fechas = pd.bdate_range("2026-01-01", periods=200)
    valores = np.linspace(1000.0, 1200.0, len(fechas))
    valor = serie(valores, fechas)
    flujos = serie([1000.0] + [0.0] * (len(fechas) - 1), fechas)

    simple = valores[-1] / valores[0] - 1.0
    medido = rendimiento.twr(valor, flujos)
    assert medido == pytest.approx(simple, rel=1e-9)

    dias = (fechas[-1].date() - fechas[0].date()).days
    esperada = rendimiento.anualizar(medido, dias=dias)
    calculada = rendimiento.tir([
        (fechas[0].date(), -1000.0),
        (fechas[-1].date(), float(valores[-1])),
    ])
    assert calculada == pytest.approx(esperada, rel=1e-6)


@pytest.mark.parametrize("caso", [
    [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), 1100.0)],
    [(date(2026, 1, 1), -5000.0), (date(2026, 6, 1), -2000.0),
     (date(2027, 3, 1), 7800.0)],
])
def test_contraste_contra_numpy_financial(caso):
    # Implementacion nativa contrastada contra una libreria externa, en un test
    # que se omite solo si no esta instalada: el patron que este repo ya usa con
    # Ledoit-Wolf frente a scikit-learn y con RSI frente a pandas-ta-classic.
    npf = pytest.importorskip("numpy_financial")
    fechas = [f for f, _ in caso]
    importes = [v for _, v in caso]
    referencia = npf.xirr(importes, fechas)
    assert rendimiento.tir(caso) == pytest.approx(referencia, abs=1e-6)
