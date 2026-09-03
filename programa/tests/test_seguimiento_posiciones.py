import pytest

from seguimiento import posiciones
from seguimiento.libro import Asiento


def asiento(id_, fecha, tipo, **campos) -> Asiento:
    return Asiento(id=id_, fecha=fecha, tipo=tipo, **campos)


APORTA = asiento("a1", "2026-01-05", "aportacion", importe=10_000.0)
COMPRA = asiento(
    "a2", "2026-01-05", "compra", ticker="AAPL",
    acciones=40.0, precio=200.0, importe=8000.0, comision=1.0,
)


def test_una_compra_deja_acciones_y_baja_el_efectivo():
    estado = posiciones.estado([APORTA, COMPRA])
    assert estado.acciones == {"AAPL": 40.0}
    # 10.000 menos 8.000 de compra menos 1 de comision.
    assert estado.efectivo == pytest.approx(1999.0)


def test_la_comision_sale_del_efectivo_y_no_del_aire():
    # Si la comision no bajara el efectivo, el libro cuadraria con mas dinero
    # del que hay y la primera venta descuadraria sin motivo visible.
    sin = posiciones.estado([APORTA, asiento(
        "a2", "2026-01-05", "compra", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )])
    assert sin.efectivo - posiciones.estado([APORTA, COMPRA]).efectivo == pytest.approx(1.0)


def test_una_venta_devuelve_efectivo_menos_comision():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0, comision=1.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta])
    assert estado.acciones == {"AAPL": 30.0}
    assert estado.efectivo == pytest.approx(1999.0 + 2499.0)


def test_un_ticker_que_se_vende_entero_desaparece_de_las_posiciones():
    # Dejar "AAPL: 0.0" haria que la tabla mostrara una fila de una empresa que
    # ya no se tiene, con peso cero y precio de hoy: ruido que parece dato.
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=40.0, precio=250.0, importe=10_000.0,
    )
    assert posiciones.estado([APORTA, COMPRA, venta]).acciones == {}


def test_un_dividendo_entra_en_efectivo():
    dividendo = asiento(
        "a3", "2026-02-10", "dividendo", ticker="AAPL", importe=9.6
    )
    estado = posiciones.estado([APORTA, COMPRA, dividendo])
    assert estado.efectivo == pytest.approx(1999.0 + 9.6)


def test_un_asiento_anulado_deja_de_contar():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2")
    estado = posiciones.estado([APORTA, COMPRA, anulacion])
    assert estado.acciones == {}
    assert estado.efectivo == pytest.approx(10_000.0)


def test_la_propia_anulacion_tampoco_cuenta_como_asiento():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2", importe=0.0)
    assert posiciones.vigentes([APORTA, COMPRA, anulacion]) == [APORTA]


def test_el_estado_se_puede_pedir_a_una_fecha_pasada():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta], hasta="2026-01-31")
    assert estado.acciones == {"AAPL": 40.0}


def test_los_asientos_desordenados_dan_el_mismo_estado():
    # El fichero se escribe en orden de alta, pero nada garantiza que alguien no
    # lo reordene a mano. El estado no puede depender de eso.
    revuelto = posiciones.estado([COMPRA, APORTA])
    derecho = posiciones.estado([APORTA, COMPRA])
    assert revuelto.acciones == derecho.acciones
    assert revuelto.efectivo == pytest.approx(derecho.efectivo)
