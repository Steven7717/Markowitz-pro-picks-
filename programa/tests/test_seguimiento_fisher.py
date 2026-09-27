"""La parte pura del rendimiento real en pesos: conversion, INPC y Fisher."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import fisher


def test_fisher_es_el_exacto_y_no_la_resta():
    # 1,10 / 1,04 − 1 = 5,769...%. La aproximacion `nominal − π` daria 6%.
    assert fisher.real(0.10, 0.04) == pytest.approx(0.0576923077)
    assert fisher.real(0.10, 0.04) != pytest.approx(0.06)


def test_fisher_con_inflacion_cero_es_el_nominal():
    assert fisher.real(0.087, 0.0) == pytest.approx(0.087)


def test_fisher_sin_alguna_de_las_dos_no_inventa():
    assert fisher.real(None, 0.04) is None
    assert fisher.real(0.10, None) is None
