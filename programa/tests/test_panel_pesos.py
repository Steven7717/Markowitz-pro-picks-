"""Las cifras en pesos, que pueden faltar sin que falte nada de lo demas."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import fisher, panel, posiciones, rendimiento


def _serie(fechas, valores):
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


FECHAS = ["2026-01-30", "2026-03-02", "2026-03-31"]


def _marcha(valor, flujos):
    return posiciones.Marcha(
        acciones=pd.DataFrame(), efectivo=pd.Series(dtype=float),
        valor=_serie(FECHAS, valor), flujos=_serie(FECHAS, flujos),
        dividendos=pd.DataFrame(),
    )


MARCHA = _marcha([1000.0, 1050.0, 1100.0], [1000.0, 0.0, 0.0])
INPC = _serie(["2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01"],
              [100.0, 100.5, 101.0, 101.5])


def test_con_fix_constante_la_twr_en_pesos_es_la_de_dolares():
    fix = _serie(FECHAS, [17.0, 17.0, 17.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.motivo == "ok"
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial == cp.fix_final == 17.0
    assert cp.movimiento_tc == pytest.approx(0.0)


def test_las_reales_son_fisher_sobre_las_nominales_en_pesos():
    fix = _serie(FECHAS, [17.0, 17.5, 18.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    assert cp.inflacion is not None
    assert cp.twr_real == pytest.approx(
        (1 + cp.twr_anual) / (1 + cp.inflacion.anual) - 1)
    assert cp.tir_real == pytest.approx((1 + cp.tir) / (1 + cp.inflacion.anual) - 1)
    assert cp.movimiento_tc == pytest.approx(18.0 / 17.0 - 1)


def test_un_libro_en_pesos_no_se_convierte():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="MXN",
                              fix=None, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial is None


def test_sin_valorar_todo_es_none():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=True, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=INPC)
    assert cp.motivo == "sin_valorar"
    assert cp.twr_anual is cp.tir is cp.twr_real is cp.tir_real is None


def test_sin_fix_dice_por_que():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=None, inpc=None, motivo_datos="sin_token")
    assert cp.motivo == "sin_token"
    assert cp.twr_anual is None


def test_sin_inpc_las_nominales_salen_y_las_reales_no():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=None,
                              motivo_datos="sin_red")
    assert cp.twr_anual is not None
    assert cp.twr_real is None
    assert cp.motivo == "sin_red"


def test_otra_moneda_no_se_soporta():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="EUR",
                              fix=None, inpc=None)
    assert cp.motivo == "moneda_no_soportada"


def test_un_inpc_que_no_llega_al_inicio_lo_nombra():
    tarde = _serie(["2026-03-01"], [101.5])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=tarde)
    assert cp.inflacion is None
    assert cp.motivo == "inpc_incompleto"


def test_la_nota_del_tipo_de_cambio_dice_de_donde_a_donde():
    cp = panel.CabeceraPesos(motivo="ok", twr_anual=0.1, fix_inicial=17.05,
                             fix_final=18.40)
    notas = panel.notas_pesos(cp)
    assert "17.05 → 18.40" in notas["tc"]
    assert "subió" in notas["tc"]


def test_la_nota_de_inflacion_dice_desde_cuando_es_estimada():
    inf = fisher.Inflacion(acumulada=0.03, anual=0.04, oficial_hasta=date(2026, 8, 31),
                           estimada=True, tasa_extension=0.004)
    notas = panel.notas_pesos(panel.CabeceraPesos(motivo="ok", inflacion=inf))
    assert "ago-2026" in notas["inflacion"]
    assert "estimad" in notas["inflacion"]
    assert "0.40%" in notas["inflacion"]


def test_sin_token_la_nota_dice_como_conseguirlo():
    notas = panel.notas_pesos(panel.CabeceraPesos(motivo="sin_token"))
    assert "Perfil" in notas["motivo"]
    assert "banxico.org.mx" in notas["motivo"]


def test_con_todo_bien_no_hay_nota_de_motivo():
    assert panel.notas_pesos(panel.CabeceraPesos(motivo="ok"))["motivo"] is None


def test_sin_inpc_vacio_tambien_dice_por_que():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="MXN",
                              fix=None, inpc=pd.Series(dtype=float))
    assert cp.motivo == "inpc_incompleto"


def test_inpc_none_tambien_dice_por_que():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="MXN",
                              fix=None, inpc=None)
    assert cp.motivo == "inpc_incompleto"


def test_periodo_corto_dice_que_hacen_falta_30_dias():
    notas = panel.notas_pesos(panel.CabeceraPesos(motivo="ok", twr_anual=None))
    assert notas["periodo"] == "Hacen falta al menos 30 días para anualizar."


FECHAS_CORTAS = ["2026-03-16", "2026-03-20", "2026-03-28"]


def _marcha_corta():
    return posiciones.Marcha(
        acciones=pd.DataFrame(), efectivo=pd.Series(dtype=float),
        valor=_serie(FECHAS_CORTAS, [1000.0, 1020.0, 1050.0]),
        flujos=_serie(FECHAS_CORTAS, [1000.0, 0.0, 0.0]),
        dividendos=pd.DataFrame(),
    )


def test_por_debajo_de_30_dias_la_fila_da_las_cifras_del_periodo():
    fix = _serie(FECHAS_CORTAS, [17.0, 17.2, 17.34])
    cp = panel.cabecera_pesos(_marcha_corta(), sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    fila = panel.fila_pesos(cp)

    assert cp.twr_anual is None
    assert cp.dias == 12
    assert fila["del_periodo"] is True
    # 1.050 dolares a 17,34 contra 1.000 a 17,00: 7,1% en pesos.
    assert fila["twr"] == pytest.approx(1050 * 17.34 / (1000 * 17.0) - 1)
    assert fila["inflacion"] == pytest.approx(cp.inflacion.acumulada)
    # Fisher igual que con las anuales, pero sobre las del periodo.
    assert fila["twr_real"] == pytest.approx(
        (1 + fila["twr"]) / (1 + cp.inflacion.acumulada) - 1)


def test_con_30_dias_o_mas_la_fila_da_las_anuales():
    fix = _serie(FECHAS, [17.0, 17.5, 18.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    fila = panel.fila_pesos(cp)
    assert fila["del_periodo"] is False
    assert fila["twr"] == cp.twr_anual
    assert fila["inflacion"] == cp.inflacion.anual
    assert fila["twr_real"] == cp.twr_real


def test_la_fila_del_periodo_sin_inpc_no_inventa_la_real():
    fix = _serie(FECHAS_CORTAS, [17.0, 17.2, 17.34])
    cp = panel.cabecera_pesos(_marcha_corta(), sin_valorar=False, moneda="USD",
                              fix=fix, inpc=None, motivo_datos="sin_red")
    fila = panel.fila_pesos(cp)
    assert fila["del_periodo"] is True
    assert fila["twr"] is not None
    assert fila["inflacion"] is None and fila["twr_real"] is None


def test_la_nota_del_periodo_dice_cuantos_dias_y_que_la_tir_espera():
    cp = panel.CabeceraPesos(motivo="ok", twr_periodo=0.05, dias=12)
    nota = panel.notas_pesos(cp)["periodo"]
    assert "12 días" in nota
    assert "sin anualizar" in nota
    assert "TIR" in nota


def test_periodo_no_aparece_si_no_es_por_eso():
    assert panel.notas_pesos(panel.CabeceraPesos(motivo="sin_token"))["periodo"] is None
    con_twr = panel.CabeceraPesos(motivo="ok", twr_anual=0.1)
    assert panel.notas_pesos(con_twr)["periodo"] is None


def test_movimiento_tc_con_fix_inicial_cero_no_divide_por_cero():
    cp = panel.CabeceraPesos(motivo="ok", fix_inicial=0.0, fix_final=18.0)
    assert cp.movimiento_tc is None


def _marcha_con_flujo_intermedio():
    return posiciones.Marcha(
        acciones=pd.DataFrame(), efectivo=pd.Series(dtype=float),
        valor=_serie(FECHAS, [1000.0, 1600.0, 1700.0]),
        flujos=_serie(FECHAS, [1000.0, 500.0, 0.0]),
        dividendos=pd.DataFrame(),
    )


def test_un_flujo_intermedio_con_fix_que_se_mueve_cambia_la_tir_en_pesos():
    marcha = _marcha_con_flujo_intermedio()
    usd_flujos_tir = [
        (d.date(), -float(v)) for d, v in marcha.flujos.items() if v
    ]
    usd_flujos_tir.append((marcha.valor.index[-1].date(), float(marcha.valor.iloc[-1])))
    tir_usd, _ = rendimiento.tir_detallada(usd_flujos_tir)

    constante = panel.cabecera_pesos(
        marcha, sin_valorar=False, moneda="USD",
        fix=_serie(FECHAS, [17.0, 17.0, 17.0]), inpc=None,
    )
    assert constante.tir == pytest.approx(tir_usd)

    variable = panel.cabecera_pesos(
        marcha, sin_valorar=False, moneda="USD",
        fix=_serie(FECHAS, [17.0, 18.0, 19.0]), inpc=None,
    )
    assert variable.tir != pytest.approx(tir_usd)


def test_un_fix_que_empieza_despues_del_primer_dia_dice_fix_incompleto():
    tarde = _serie(["2026-03-02", "2026-03-31"], [17.5, 18.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=tarde, inpc=INPC)
    assert cp.motivo == "fix_incompleto"
