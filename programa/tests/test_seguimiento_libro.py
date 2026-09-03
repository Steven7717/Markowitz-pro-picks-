from datetime import date

import pytest

from seguimiento.libro import Asiento, AsientoInvalido, derivar, validar

HOY = date(2026, 9, 2)


def compra(**cambios) -> Asiento:
    campos = {
        "id": "a1",
        "fecha": "2026-09-01",
        "tipo": "compra",
        "ticker": "AAPL",
        "acciones": 10.0,
        "precio": 220.0,
        "importe": 2200.0,
    }
    campos.update(cambios)
    return Asiento(**campos)


def test_una_compra_bien_formada_pasa():
    validar(compra(), hoy=HOY)


def test_una_fecha_futura_no_pasa():
    # Registrar algo que no ha ocurrido dejaria una posicion valorada con
    # precios que todavia no existen.
    with pytest.raises(AsientoInvalido, match="futura"):
        validar(compra(fecha="2026-09-03"), hoy=HOY)


def test_un_precio_de_cero_no_pasa():
    with pytest.raises(AsientoInvalido, match="precio"):
        validar(compra(precio=0.0), hoy=HOY)


def test_una_compra_sin_ticker_no_pasa():
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(compra(ticker=None), hoy=HOY)


def test_un_ticker_con_forma_rara_no_pasa():
    with pytest.raises(AsientoInvalido, match="forma de ticker"):
        validar(compra(ticker="AAPL!"), hoy=HOY)


def test_una_aportacion_no_lleva_ticker():
    # Dinero que entra no es dinero puesto en algo: si llevara ticker, seria
    # una compra, y contarlo como flujo externo Y como posicion lo duplicaria.
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(
            Asiento(id="a2", fecha="2026-09-01", tipo="aportacion",
                    ticker="AAPL", importe=1000.0),
            hoy=HOY,
        )


def test_una_comision_negativa_no_pasa():
    with pytest.raises(AsientoInvalido, match="comisión"):
        validar(compra(comision=-1.0), hoy=HOY)


def test_una_anulacion_necesita_a_quien_anula():
    with pytest.raises(AsientoInvalido, match="anula"):
        validar(Asiento(id="a3", fecha="2026-09-01", tipo="anulacion"), hoy=HOY)


def test_un_tipo_inventado_no_pasa():
    with pytest.raises(AsientoInvalido, match="tipo"):
        validar(compra(tipo="permuta"), hoy=HOY)


# --- Derivar el tercer campo -------------------------------------------------


def test_de_importe_y_precio_salen_las_acciones():
    assert derivar(importe=2200.0, acciones=None, precio=220.0) == (2200.0, 10.0, 220.0)


def test_de_acciones_y_precio_sale_el_importe():
    assert derivar(importe=None, acciones=10.0, precio=220.0) == (2200.0, 10.0, 220.0)


def test_con_los_tres_puestos_se_respetan_los_tres():
    # El bróker cobra redondeos que ninguna division reproduce: si el usuario
    # escribe los tres, mandan los tres, aunque no cuadren al centimo.
    assert derivar(importe=2200.5, acciones=10.0, precio=220.0) == (2200.5, 10.0, 220.0)


def test_sin_precio_no_se_puede_derivar_nada():
    with pytest.raises(AsientoInvalido, match="precio"):
        derivar(importe=2200.0, acciones=None, precio=None)
