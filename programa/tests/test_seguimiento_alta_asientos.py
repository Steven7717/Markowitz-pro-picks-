import pytest

from seguimiento import alta

FILAS = [
    {"ticker": "AAPL", "acciones": 25.0, "precio": 200.0, "comision": 1.0},
    {"ticker": "MSFT", "acciones": 7.0, "precio": 400.0, "comision": 1.0},
]


def test_una_compra_por_fila_mas_la_aportacion():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    tipos = [a.tipo for a in asientos]
    assert tipos.count("aportacion") == 1
    assert tipos.count("compra") == 2


def test_la_aportacion_va_primero_y_por_el_capital_declarado():
    """Si la compra se aplicase antes, el efectivo pasaria por negativo."""
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    assert asientos[0].tipo == "aportacion"
    assert asientos[0].importe == 10000.0


def test_sin_capital_declarado_la_aportacion_se_deriva():
    """La carga manual no declara capital: se deriva de lo comprado.

    Suma de compras mas comisiones, para que el libro nazca con cero efectivo
    sin asignar. Nadie ha dicho que tenga dinero parado, y suponerlo falsearia
    la TIR desde el primer dia.
    """
    asientos = alta.asientos_de(FILAS, capital=None, fecha="2026-03-02")
    esperado = 25 * 200.0 + 7 * 400.0 + 2.0
    assert asientos[0].importe == esperado


def test_el_importe_de_cada_compra_es_acciones_por_precio():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    compra = [a for a in asientos if a.ticker == "AAPL"][0]
    assert compra.importe == 5000.0
    assert compra.acciones == 25.0
    assert compra.precio == 200.0
    assert compra.comision == 1.0


def test_gastar_mas_que_la_aportacion_se_rechaza_ANTES_de_escribir():
    """Dejaria el efectivo en negativo, y `anadir` lo rechazaria despues.

    Se comprueba aqui para dar un mensaje que se entienda, en vez del de una
    guarda interna que habla de saldos.
    """
    with pytest.raises(alta.AltaInvalida) as error:
        alta.asientos_de(FILAS, capital=1000.0, fecha="2026-03-02")
    # Se comprueba que el mensaje dice CUANTO falta, no un numero literal:
    # `f"{1000.0:,.2f}"` da "1,000.00" con separadores ingleses, asi que
    # buscar "1.000" o "1000" fallaria por el formato y no por la guarda.
    assert "Faltan" in str(error.value)
    # 25*200 + 7*400 + 2 de comisiones = 7.802 de compras, menos 1.000
    # aportados.
    assert "6,802" in str(error.value)


def test_una_fila_sin_ticker_se_omite_nombrandola():
    filas = FILAS + [{"ticker": "", "acciones": 5.0, "precio": 10.0}]
    asientos = alta.asientos_de(filas, capital=10000.0, fecha="2026-03-02")
    assert len([a for a in asientos if a.tipo == "compra"]) == 2


def test_una_fila_con_cero_acciones_se_omite():
    """Es la linea del activo que no cabia. No se escribe media compra."""
    filas = FILAS + [{"ticker": "BRK-A", "acciones": 0.0, "precio": 600.0}]
    asientos = alta.asientos_de(filas, capital=10000.0, fecha="2026-03-02")
    assert "BRK-A" not in [a.ticker for a in asientos]


def test_dos_filas_del_mismo_ticker_se_aceptan():
    """Comprar en dos tramos el mismo dia es normal; el coste medio lo resuelve."""
    filas = FILAS + [
        {"ticker": "AAPL", "acciones": 5.0, "precio": 201.0, "comision": 1.0}
    ]
    asientos = alta.asientos_de(filas, capital=12000.0, fecha="2026-03-02")
    assert len([a for a in asientos if a.ticker == "AAPL"]) == 2


def test_todas_las_filas_vacias_es_un_error_y_no_un_libro_vacio():
    """Crear un libro sin una sola compra deja el callejon sin salida que F ya
    tuvo: una pantalla que dice «anade el primero» y no tiene donde."""
    with pytest.raises(alta.AltaInvalida):
        alta.asientos_de([], capital=1000.0, fecha="2026-03-02")


def test_un_precio_no_positivo_se_rechaza():
    filas = [{"ticker": "AAPL", "acciones": 1.0, "precio": 0.0}]
    with pytest.raises(alta.AltaInvalida):
        alta.asientos_de(filas, capital=100.0, fecha="2026-03-02")


def test_los_identificadores_son_distintos():
    """Dos asientos con el mismo id se pisarian al anular uno."""
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    ids = [a.id for a in asientos]
    assert len(set(ids)) == len(ids)


def test_todos_llevan_la_fecha_dada():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    assert {a.fecha for a in asientos} == {"2026-03-02"}
