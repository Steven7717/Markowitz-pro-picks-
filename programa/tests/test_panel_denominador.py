"""El peso se mide contra los activos, no contra el valor con el efectivo dentro.

Hasta el sub-proyecto K la tabla dividia entre el valor de la serie, que incluye
el efectivo sin invertir, mientras que el objetivo y `rebalanceo/deriva.py`
reparten sobre los activos. Con 28% del dinero en caja, la misma cartera salia
al 7,32% en Seguimiento y al 10,17% en Rebalanceo, y la columna sumaba 71,9% al
lado de un «Peso objetivo» que suma 100%.
"""

import pytest

from seguimiento import libro as mod, panel


def _libro_con_caja():
    """Dos activos comprados y bastante dinero sin invertir."""
    return (
        mod.Asiento(id="a", fecha="2026-01-02", tipo="aportacion", importe=10000.0),
        mod.Asiento(id="b", fecha="2026-01-02", tipo="compra", ticker="AAA",
                    acciones=10.0, precio=100.0, importe=1000.0),
        mod.Asiento(id="c", fecha="2026-01-02", tipo="compra", ticker="BBB",
                    acciones=10.0, precio=300.0, importe=3000.0),
    )


PRECIOS = {"AAA": 100.0, "BBB": 300.0}


def test_los_pesos_de_la_tabla_suman_uno_sobre_los_activos():
    """Y no el 40% que saldria dividiendo entre los 10.000 aportados."""
    asientos = _libro_con_caja()
    comp = panel.composicion(asientos, PRECIOS, None)
    filas = panel.filas_por_activo(asientos, PRECIOS, comp.invertido, None)

    pesos = [float(f["Peso real"].rstrip("%")) for f in filas]
    assert sum(pesos) == pytest.approx(100.0, abs=0.05)


def test_la_tabla_y_la_composicion_dicen_lo_mismo_del_mismo_activo():
    """Es la contradiccion que esta tarea existe para cerrar.

    Dos numeros distintos bajo la misma palabra, en la misma pantalla, es peor
    que un numero incomodo: quien los vea no puede saber cual creer.
    """
    asientos = _libro_con_caja()
    comp = panel.composicion(asientos, PRECIOS, None)
    filas = panel.filas_por_activo(asientos, PRECIOS, comp.invertido, None)

    de_la_tabla = {f["Ticker"]: float(f["Peso real"].rstrip("%")) for f in filas}
    for linea in comp.lineas:
        assert de_la_tabla[linea.ticker] == pytest.approx(linea.peso * 100, abs=0.05)


def test_el_efectivo_sin_invertir_se_nombra_en_vez_de_desaparecer():
    """4.000 invertidos de 10.000: los 6.000 restantes tienen que salir.

    Antes no aparecian por ningun lado -- solo encogian todos los pesos, que es
    la peor forma de contarlo porque no se ve.
    """
    comp = panel.composicion(_libro_con_caja(), PRECIOS, None)
    assert comp.invertido == pytest.approx(4000.0)
    assert comp.efectivo == pytest.approx(6000.0)
