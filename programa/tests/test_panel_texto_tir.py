"""El texto y la nota de la TIR: mismo motivo, dolares o pesos.

Extraido de `vistas/seguimiento.py`, donde vivia solo para la TIR en dolares.
La TIR en pesos ignoraba `motivo_tir` y enseñaba un «--» sin explicacion, o
peor, una cifra fuera de escala sin avisar. Con la misma funcion para las dos
no puede volver a pasar.
"""

import pytest

from seguimiento import panel


def test_sobre_escala_dice_que_se_sale_por_arriba():
    texto, nota = panel.texto_tir(None, "sobre_escala", dias=100)
    assert texto == "> 1.000%"
    assert "arriba" in nota


def test_bajo_escala_dice_que_se_sale_por_abajo():
    texto, nota = panel.texto_tir(None, "bajo_escala", dias=100)
    assert texto == "< −99,9%"
    assert "abajo" in nota


def test_periodo_corto_pide_30_dias():
    texto, nota = panel.texto_tir(None, "periodo_corto", dias=10)
    assert texto == "—"
    assert "30 días" in nota


def test_mismo_signo_dice_que_no_hay_tasa_que_los_anule():
    texto, nota = panel.texto_tir(None, "mismo_signo", dias=100)
    assert texto == "—"
    assert "anule" in nota


def test_pocos_flujos_pide_mas_de_un_movimiento():
    texto, nota = panel.texto_tir(None, "pocos_flujos", dias=100)
    assert texto == "—"
    assert "movimiento" in nota


def test_ok_con_menos_de_un_anio_dice_que_extrapola():
    texto, nota = panel.texto_tir(0.325, "ok", dias=60)
    assert texto == "32.50%"
    assert "Anualizada desde 60 días" in nota


def test_ok_con_un_anio_o_mas_dice_ponderada_por_dinero():
    texto, nota = panel.texto_tir(0.10, "ok", dias=400)
    assert texto == "10.00%"
    assert "Ponderada por dinero" in nota


def test_sin_dias_tambien_dice_ponderada_por_dinero():
    # `dias` puede llegar como None (una cabecera sin serie que medir), y
    # `None < 365` reventaria: la rama por defecto es la que no depende de dias.
    texto, nota = panel.texto_tir(0.10, "ok", dias=None)
    assert "Ponderada por dinero" in nota
