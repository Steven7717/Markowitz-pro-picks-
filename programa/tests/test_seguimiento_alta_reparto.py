from seguimiento import alta

PESOS = {"AAPL": 0.5, "MSFT": 0.3, "NVDA": 0.2}
PRECIOS = {"AAPL": 200.0, "MSFT": 400.0, "NVDA": 100.0}


def test_con_fracciones_se_gasta_el_capital_entero():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    assert round(r.gastado, 2) == 10000.00
    assert round(r.sobrante, 2) == 0.00


def test_con_fracciones_cada_uno_recibe_su_peso():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert round(por_ticker["AAPL"].acciones, 6) == 25.0    # 5000 / 200
    assert round(por_ticker["MSFT"].acciones, 6) == 7.5     # 3000 / 400
    assert round(por_ticker["NVDA"].acciones, 6) == 20.0    # 2000 / 100


def test_con_acciones_enteras_sobra_algo_y_se_informa():
    """MSFT: 3000/400 = 7,5 acciones -> 7, y sobran 200."""
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=False)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert por_ticker["MSFT"].acciones == 7
    assert round(r.sobrante, 2) == 200.00
    assert round(r.gastado + r.sobrante, 2) == 10000.00


def test_el_sobrante_no_se_redistribuye():
    """Repartirlo entre los demas romperia los pesos recien elegidos."""
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=False)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert por_ticker["AAPL"].acciones == 25    # 5000/200 exacto, no 26
    assert por_ticker["NVDA"].acciones == 20    # 2000/100 exacto, no 21


def test_un_peso_pequeno_con_precio_alto_da_cero_y_SE_NOMBRA():
    """Con 1.000 y un 2%, una accion de 600 no cabe.

    El activo tiene que salir en la tabla con cero y su motivo. Que un activo
    del plan desaparezca sin decir nada es el defecto que ya costo una
    correccion en el sub-proyecto G.
    """
    r = alta.repartir(
        1000.0, {"AAPL": 0.98, "BRK-A": 0.02}, {"AAPL": 100.0, "BRK-A": 600.0},
        fracciones=False,
    )
    linea = [l for l in r.lineas if l.ticker == "BRK-A"][0]
    assert linea.acciones == 0
    assert linea.motivo != ""
    assert "alcanza" in linea.motivo.lower()


def test_un_activo_sin_precio_vuelve_nombrado_y_sin_acciones():
    r = alta.repartir(
        10000.0, PESOS, {"AAPL": 200.0, "MSFT": None, "NVDA": 100.0},
        fracciones=True,
    )
    linea = [l for l in r.lineas if l.ticker == "MSFT"][0]
    assert linea.acciones == 0
    assert linea.precio is None
    assert linea.motivo != ""
    assert "MSFT" in r.sin_precio


def test_el_capital_del_que_no_tiene_precio_queda_como_sobrante():
    """No se reparte entre los demas: nadie decidio darles mas peso."""
    r = alta.repartir(
        10000.0, PESOS, {"AAPL": 200.0, "MSFT": None, "NVDA": 100.0},
        fracciones=True,
    )
    assert round(r.sobrante, 2) == 3000.00     # el 30% de MSFT


def test_capital_cero_no_calcula_nada():
    r = alta.repartir(0.0, PESOS, PRECIOS, fracciones=True)
    assert r.lineas == ()
    assert r.sobrante == 0.0


def test_capital_negativo_no_calcula_nada():
    r = alta.repartir(-500.0, PESOS, PRECIOS, fracciones=True)
    assert r.lineas == ()


def test_sin_pesos_no_calcula_nada():
    assert alta.repartir(10000.0, {}, PRECIOS, fracciones=True).lineas == ()


def test_las_lineas_salen_de_mayor_a_menor_peso():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    assert [l.ticker for l in r.lineas] == ["AAPL", "MSFT", "NVDA"]


def test_los_pesos_se_normalizan_si_no_suman_uno():
    """Un objetivo puede venir con pesos que no cierran exactamente."""
    r = alta.repartir(
        1000.0, {"AAPL": 0.4, "MSFT": 0.4}, {"AAPL": 100.0, "MSFT": 100.0},
        fracciones=True,
    )
    assert round(r.gastado, 2) == 1000.00
