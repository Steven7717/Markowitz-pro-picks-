import pytest

from rebalanceo import coste
from seguimiento.libro import Asiento


def compra(comision: float, id_: str = "c1") -> Asiento:
    return Asiento(id=id_, fecha="2026-08-01", tipo="compra", ticker="AAPL",
                   acciones=10.0, precio=200.0, importe=2000.0, comision=comision)


def test_sin_operaciones_registradas_se_usa_el_valor_declarado():
    estimado, del_libro = coste.por_operacion([], declarado=1.5)
    assert estimado == pytest.approx(1.5)
    assert not del_libro


def test_con_operaciones_se_usa_la_mediana_de_sus_comisiones():
    asientos = [compra(1.0, "a"), compra(2.0, "b"), compra(9.0, "c")]
    estimado, del_libro = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)
    assert del_libro


def test_las_comisiones_de_cero_cuentan():
    # El caso que un filtro "quedate con lo que no sea cero" romperia en
    # silencio. Si el broker no cobra y asi se registro, la estimacion correcta
    # es cero -- y filtrarlas convertiria un dato en la ausencia de un dato,
    # bloqueando operaciones por un coste que el usuario no paga.
    asientos = [compra(0.0, "a"), compra(0.0, "b")]
    estimado, del_libro = coste.por_operacion(asientos, declarado=1.5)
    assert estimado == pytest.approx(0.0)
    assert del_libro


def test_solo_cuentan_las_compras_y_las_ventas():
    # Una aportacion o un dividendo no son operaciones de mercado y no dicen
    # nada de lo que cuesta operar.
    asientos = [
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=1000.0,
                comision=50.0),
        compra(2.0, "c"),
    ]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)


def test_los_asientos_anulados_no_cuentan():
    asientos = [
        compra(50.0, "c1"),
        compra(2.0, "c2"),
        Asiento(id="x", fecha="2026-08-02", tipo="anulacion", anula="c1"),
    ]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)


def test_con_dos_comisiones_la_mediana_es_el_promedio():
    asientos = [compra(1.0, "a"), compra(3.0, "b")]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)
