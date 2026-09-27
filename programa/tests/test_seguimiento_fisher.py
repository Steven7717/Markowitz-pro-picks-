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
