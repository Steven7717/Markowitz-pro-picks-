"""La parte pura del rendimiento real en pesos: conversion, INPC y Fisher."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import fisher, rendimiento


def test_fisher_es_el_exacto_y_no_la_resta():
    # 1,10 / 1,04 − 1 = 5,769...%. La aproximacion `nominal − π` daria 6%.
    assert fisher.real(0.10, 0.04) == pytest.approx(0.0576923077)
    assert fisher.real(0.10, 0.04) != pytest.approx(0.06)


def test_fisher_con_inflacion_cero_es_el_nominal():
    assert fisher.real(0.087, 0.0) == pytest.approx(0.087)


def test_fisher_sin_alguna_de_las_dos_no_inventa():
    assert fisher.real(None, 0.04) is None
    assert fisher.real(0.10, None) is None


def test_fisher_con_deflacion_total_no_divide_entre_cero():
    assert fisher.real(0.10, -1.0) is None


def _serie(pares):
    return pd.Series(
        [v for _, v in pares], index=pd.DatetimeIndex([d for d, _ in pares]), dtype=float
    )


def test_con_fix_constante_los_pesos_son_los_dolares_por_el_fix():
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 110.0)])
    flujos = _serie([("2026-03-02", 100.0), ("2026-03-03", 0.0)])
    fix = _serie([("2026-03-02", 17.0), ("2026-03-03", 17.0)])

    valor_mxn, flujos_mxn = fisher.en_pesos(valor, flujos, fix)

    assert list(valor_mxn) == [1700.0, 1870.0]
    assert list(flujos_mxn) == [1700.0, 0.0]


def test_cada_flujo_se_convierte_al_fix_de_su_dia():
    # Cartera plana en dolares, el dolar sube un 10% el segundo dia y el tercero
    # entra una aportacion. La TWR en pesos tiene que ser el 10% del tipo de
    # cambio y nada mas: la aportacion no rinde, solo entra.
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 100.0), ("2026-03-04", 200.0)])
    flujos = _serie([("2026-03-02", 100.0), ("2026-03-03", 0.0), ("2026-03-04", 100.0)])
    fix = _serie([("2026-03-02", 10.0), ("2026-03-03", 11.0), ("2026-03-04", 11.0)])

    valor_mxn, flujos_mxn = fisher.en_pesos(valor, flujos, fix)

    assert flujos_mxn.loc["2026-03-04"] == pytest.approx(1100.0)
    assert rendimiento.twr(valor_mxn, flujos_mxn) == pytest.approx(0.10)


def test_un_dia_sin_fix_usa_el_ultimo_publicado():
    # Un festivo mexicano que en EE. UU. es habil: hay cierre y no hay FIX.
    valor = _serie([("2026-03-13", 100.0), ("2026-03-16", 100.0)])
    flujos = _serie([("2026-03-13", 100.0), ("2026-03-16", 0.0)])
    fix = _serie([("2026-03-13", 18.0)])

    valor_mxn, _ = fisher.en_pesos(valor, flujos, fix)

    assert valor_mxn.loc["2026-03-16"] == pytest.approx(1800.0)


def test_sin_fix_para_el_primer_dia_no_se_inventa_hacia_atras():
    valor = _serie([("2026-01-02", 100.0), ("2026-01-05", 100.0)])
    flujos = _serie([("2026-01-02", 100.0), ("2026-01-05", 0.0)])
    fix = _serie([("2026-01-05", 17.5)])

    assert fisher.en_pesos(valor, flujos, fix) is None


def test_sin_serie_de_fix_no_hay_conversion():
    valor = _serie([("2026-01-02", 100.0)])
    assert fisher.en_pesos(valor, valor, None) is None
    assert fisher.en_pesos(valor, valor, pd.Series(dtype=float)) is None


def test_un_fix_con_fecha_duplicada_no_revienta_y_usa_la_ultima():
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 100.0)])
    flujos = _serie([("2026-03-02", 100.0), ("2026-03-03", 0.0)])
    fix = pd.Series(
        [17.0, 17.5, 18.0],
        index=pd.DatetimeIndex(["2026-03-02", "2026-03-02", "2026-03-03"]),
        dtype=float,
    )

    valor_mxn, _ = fisher.en_pesos(valor, flujos, fix)

    assert valor_mxn.loc["2026-03-02"] == pytest.approx(1750.0)
    assert valor_mxn.loc["2026-03-03"] == pytest.approx(1800.0)


def test_flujos_con_menos_fechas_que_el_valor_se_convierten_bien():
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 105.0), ("2026-03-04", 110.0)])
    flujos = _serie([("2026-03-02", 100.0)])
    fix = _serie([("2026-03-02", 17.0), ("2026-03-03", 17.0), ("2026-03-04", 17.0)])

    valor_mxn, flujos_mxn = fisher.en_pesos(valor, flujos, fix)

    assert list(valor_mxn) == [1700.0, 1785.0, 1870.0]
    assert list(flujos_mxn) == [1700.0]


# Tal como llega de `banxico.traer`: fechado el dia 1 de cada mes.
INPC = _serie([("2026-01-01", 100.0), ("2026-02-01", 101.0), ("2026-03-01", 102.01)])


def test_el_dato_mensual_es_el_nivel_al_cierre_del_mes():
    anclado = fisher.anclar(INPC)
    assert fisher.nivel(anclado, date(2026, 2, 28)) == pytest.approx(101.0)


def test_dentro_del_mes_se_interpola_de_forma_geometrica():
    # A mitad de febrero (14 de 28 dias): 100 · 1,01^0,5 = 100,4988. La lineal
    # daria 100,5.
    anclado = fisher.anclar(INPC)
    medio = fisher.nivel(anclado, date(2026, 2, 14))
    assert medio == pytest.approx(100.0 * 1.01 ** 0.5)
    assert medio != pytest.approx(100.5)


def test_despues_del_ultimo_inpc_se_extiende_la_ultima_tasa_mensual():
    anclado = fisher.anclar(INPC)
    # 30 dias despues del 31 de marzo, a la tasa de marzo (1%).
    esperado = 102.01 * 1.01 ** (30 * 12 / 365)
    assert fisher.nivel(anclado, date(2026, 4, 30)) == pytest.approx(esperado)


def test_antes_del_primer_inpc_no_hay_nivel():
    assert fisher.nivel(fisher.anclar(INPC), date(2026, 1, 15)) is None


def test_con_un_solo_ancla_no_se_puede_extender():
    un_solo = _serie([("2026-01-01", 100.0)])
    assert fisher.nivel(fisher.anclar(un_solo), date(2026, 2, 15)) is None


def test_la_extension_usa_la_tasa_mensual_no_la_del_hueco_entre_anclas():
    # Enero y abril, sin febrero ni marzo: el hueco entre anclas es de tres
    # meses, y la tasa que se extiende tiene que ser la mensual (la raiz
    # cubica), no el 3% del tramo completo.
    con_hueco = _serie([("2026-01-01", 100.0), ("2026-04-01", 103.0)])
    inf = fisher.inflacion_periodo(con_hueco, date(2026, 1, 31), date(2026, 6, 30))
    assert inf.tasa_extension == pytest.approx(1.03 ** (1 / 3) - 1)


def test_inpc_con_dos_fechas_en_el_mismo_mes_ancla_una_con_la_ultima():
    con_duplicado = _serie(
        [("2026-01-01", 100.0), ("2026-02-01", 101.0), ("2026-02-15", 101.5)]
    )
    anclado = fisher.anclar(con_duplicado)
    assert len(anclado) == 2
    assert anclado.loc["2026-02-28"] == pytest.approx(101.5)


def test_inflacion_de_un_periodo_cubierto_es_oficial():
    inf = fisher.inflacion_periodo(INPC, date(2026, 1, 31), date(2026, 3, 31))
    assert inf.acumulada == pytest.approx(0.0201)
    assert inf.anual == pytest.approx(1.0201 ** (365 / 59) - 1)
    assert inf.oficial_hasta == date(2026, 3, 31)
    assert inf.estimada is False
    assert inf.tasa_extension is None


def test_inflacion_que_pasa_del_ultimo_inpc_queda_marcada_como_estimada():
    inf = fisher.inflacion_periodo(INPC, date(2026, 1, 31), date(2026, 4, 30))
    assert inf.estimada is True
    assert inf.oficial_hasta == date(2026, 3, 31)
    assert inf.tasa_extension == pytest.approx(0.01)


def test_por_debajo_de_treinta_dias_no_se_anualiza():
    inf = fisher.inflacion_periodo(INPC, date(2026, 2, 28), date(2026, 3, 10))
    assert inf.acumulada > 0
    assert inf.anual is None


def test_un_inicio_sin_inpc_no_da_inflacion():
    assert fisher.inflacion_periodo(INPC, date(2026, 1, 15), date(2026, 3, 31)) is None


def test_un_periodo_al_reves_no_da_inflacion():
    assert fisher.inflacion_periodo(INPC, date(2026, 3, 31), date(2026, 1, 31)) is None


def test_con_inflacion_cero_lo_real_es_lo_nominal():
    plano = _serie([("2026-01-01", 100.0), ("2026-02-01", 100.0), ("2026-03-01", 100.0)])
    inf = fisher.inflacion_periodo(plano, date(2026, 1, 31), date(2026, 3, 31))
    assert fisher.real(0.12, inf.anual) == pytest.approx(0.12)


def test_fix_en_un_dia_sin_dato_es_el_ultimo_publicado():
    fix = _serie([("2026-03-13", 18.0), ("2026-03-17", 18.2)])
    assert fisher.fix_en(fix, date(2026, 3, 16)) == 18.0
    assert fisher.fix_en(fix, date(2026, 3, 1)) is None
