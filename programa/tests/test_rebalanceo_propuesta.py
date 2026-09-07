import pytest

from rebalanceo import propuesta
from seguimiento.libro import Asiento

OBJETIVO = {"AAPL": 0.5, "MSFT": 0.5}


def compra(comision: float, id_: str = "c1") -> Asiento:
    return Asiento(id=id_, fecha="2026-08-01", tipo="compra", ticker="AAPL",
                   acciones=10.0, precio=200.0, importe=2000.0, comision=comision)


def test_una_cartera_en_su_objetivo_no_propone_nada():
    # El control negativo. Si una cartera exactamente en su objetivo, sin
    # efectivo, genera cualquier operacion, algo esta mal.
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert p.con_efectivo == ()
    assert p.y_ademas == ()
    assert p.basta_con_la_aportacion


def test_la_aportacion_sola_puede_bastar():
    # 6.000 y 4.000 con 4.000 de efectivo: el reparto mide el deficit de cada
    # activo contra el total YA CON el efectivo dentro (14.000), asi que AAPL
    # tambien recibe algo aunque hoy este sobreponderado sobre los 10.000
    # actuales -- reparto.repartir ya lo prueba con estos mismos numeros en
    # test_con_efectivo_suficiente_los_pesos_quedan_exactos. Lo que importa
    # aqui es que, sea cual sea el reparto, se llega justo al objetivo y no
    # hace falta vender nada.
    p = propuesta.construir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                            efectivo=4000.0, asientos=[], coste_declarado=1.0)
    importes = {o.ticker: o.importe for o in p.con_efectivo}
    assert importes == {"AAPL": pytest.approx(1000.0), "MSFT": pytest.approx(3000.0)}
    assert p.basta_con_la_aportacion
    assert p.y_ademas == ()


def test_sin_efectivo_suficiente_hacen_falta_ventas():
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert not p.basta_con_la_aportacion
    acciones = {o.ticker: o for o in p.y_ademas}
    assert acciones["AAPL"].accion == "vender"
    assert acciones["MSFT"].accion == "comprar"


def test_las_ventas_y_compras_se_autofinancian():
    # Suman cero por construccion: lo que sale de los sobreponderados es
    # exactamente lo que entra en los infraponderados.
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert sum(o.importe for o in p.y_ademas) == pytest.approx(0.0, abs=1e-6)


def test_una_operacion_que_no_compensa_se_muestra_descartada():
    # No desaparece. Una propuesta omitida en silencio es indistinguible de una
    # que nadie calculo, y el usuario no puede saber cual de las dos fue.
    # 600/400 sobre un total de 1.000 es una desviacion del 10%: supera la
    # banda absoluta del 5% y dispara la deriva, pero el importe a mover -- 100
    # dolares -- es pequeno de verdad, y una comision de 2 dolares (el 2% del
    # importe) ya supera el tope del 1% que fija el criterio.
    p = propuesta.construir({"AAPL": 600.0, "MSFT": 400.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(2.0)],
                            coste_declarado=99.0)
    assert p.y_ademas == ()
    assert {o.ticker for o in p.descartadas_por_coste} == {"AAPL", "MSFT"}
    assert all(not o.viable for o in p.descartadas_por_coste)
    # Aqui es donde importa que `basta_con_la_aportacion` sea un hecho propio:
    # `y_ademas` esta vacia, pero la cartera SIGUE fuera de banda -- lo unico
    # que paso es que arreglarlo no compensa el coste. Deducirlo de `not
    # y_ademas` diria "no hace falta nada" cuando hace falta y no compensa.
    assert not p.basta_con_la_aportacion


def test_el_coste_del_libro_manda_sobre_el_declarado():
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(3.0)],
                            coste_declarado=99.0)
    assert p.coste_por_operacion == pytest.approx(3.0)
    assert p.coste_del_libro


def test_sin_operaciones_en_el_libro_el_coste_es_el_declarado_y_se_marca():
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=2.5)
    assert p.coste_por_operacion == pytest.approx(2.5)
    assert not p.coste_del_libro


def test_el_coste_total_cuenta_una_comision_por_operacion():
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(4.0)],
                            coste_declarado=99.0)
    assert p.coste_total == pytest.approx(4.0 * len(p.y_ademas))


def test_una_cartera_de_solo_efectivo_propone_la_compra_inicial():
    # Un libro recien creado con su aportacion dentro y ninguna compra. No hay
    # deriva que medir --no hay mezcla-- pero si hay todo el dinero por
    # asignar, y el reparto tiene que apuntar al objetivo igualmente.
    p = propuesta.construir({}, OBJETIVO, efectivo=10_000.0, asientos=[],
                            coste_declarado=1.0)
    assert {o.ticker for o in p.con_efectivo} == {"AAPL", "MSFT"}
    assert sum(o.importe for o in p.con_efectivo) == pytest.approx(10_000.0)


def test_la_deriva_viaja_dentro_de_la_propuesta():
    # La pantalla pinta los medidores desde aqui, sin volver a calcular nada.
    # AAPL y MSFT se desvian la misma magnitud (0.3 en valor absoluto), asi que
    # el orden que fija deriva.calcular es el de desempate: insercion
    # alfabetica preservada por un sort estable, no la magnitud de la
    # desviacion -- aqui no hay nada que la distinga.
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert p.deriva.invertido == pytest.approx(10_000.0)
    assert [l.ticker for l in p.deriva.lineas] == ["AAPL", "MSFT"]
