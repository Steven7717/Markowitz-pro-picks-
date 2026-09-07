import pytest

from rebalanceo import deriva


def por_ticker(d: deriva.Deriva) -> dict:
    return {l.ticker: l for l in d.lineas}


def test_una_cartera_en_su_objetivo_no_tiene_deriva():
    # El control negativo de esta tarea. Si una cartera exactamente en su
    # objetivo produce cualquier desviacion distinta de cero, o marca algo
    # fuera de banda, el calculo esta mal y no hay forma de que sea casualidad.
    d = deriva.calcular({"AAPL": 5000.0, "MSFT": 5000.0},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert d.invertido == pytest.approx(10_000.0)
    for linea in d.lineas:
        assert linea.desviacion == pytest.approx(0.0)
        assert not linea.fuera_de_banda


def test_el_efectivo_no_entra_en_el_denominador():
    # `calcular` no recibe el efectivo, y esa es la decision: si entrara, meter
    # 10.000 en una cartera de 10.000 pondria todos los activos al 50% de su
    # peso y el medidor entero se volveria rojo por una aportacion sin
    # invertir, no por deriva. Este test fija la firma, que es donde vive la
    # decision.
    import inspect
    assert "efectivo" not in inspect.signature(deriva.calcular).parameters


def test_una_sobreponderacion_grande_sale_fuera_de_banda():
    d = por_ticker(deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                                   {"AAPL": 0.5, "MSFT": 0.5}))
    assert d["AAPL"].peso_real == pytest.approx(0.6)
    assert d["AAPL"].desviacion == pytest.approx(0.1)
    assert d["AAPL"].fuera_de_banda
    assert d["MSFT"].desviacion == pytest.approx(-0.1)
    assert d["MSFT"].fuera_de_banda


def test_un_activo_del_objetivo_que_no_se_tiene_sale_con_deficit_completo():
    # Nunca comprado: peso real cero y desviacion igual a menos su objetivo.
    # Es correcto que aparezca, porque es a donde tiene que ir el dinero.
    d = por_ticker(deriva.calcular({"AAPL": 10_000.0},
                                   {"AAPL": 0.7, "MSFT": 0.3}))
    assert d["MSFT"].valor == pytest.approx(0.0)
    assert d["MSFT"].desviacion == pytest.approx(-0.3)
    assert d["MSFT"].fuera_de_banda


def test_un_activo_sin_objetivo_va_a_su_propio_bloque():
    # No se propone liquidarlo. Que algo no este en el plan admite dos lecturas
    # --el plan esta viejo, o la posicion sobra-- y el programa no puede
    # distinguirlas, asi que no elige por el usuario.
    d = deriva.calcular({"AAPL": 8000.0, "TSLA": 2000.0}, {"AAPL": 1.0})
    assert [l.ticker for l in d.lineas] == ["AAPL"]
    assert [l.ticker for l in d.fuera_del_objetivo] == ["TSLA"]
    assert d.fuera_del_objetivo[0].peso_real == pytest.approx(0.2)


def test_los_del_plan_se_miden_entre_ellos_y_los_de_fuera_sobre_el_total():
    # Dos denominadores, y cada uno responde una pregunta distinta. La banda mide
    # la MEZCLA del plan, asi que sus pesos van sobre lo que el plan contempla:
    # AAPL es el 100% del plan aunque solo sea el 85,7% del dinero. Y TSLA se
    # mide sobre el total, porque ahi la pregunta es cuanto hay fuera del plan.
    #
    # Sin esta separacion, unos pesos que suman uno aplicados sobre un total que
    # incluye TSLA pediran que el plan ocupe el cien por cien de un dinero del
    # que TSLA ya se lleva una parte -- y la propuesta de ventas y compras sale
    # descuadrada en exactamente el valor de TSLA. Medido en la app: 879,48.
    d = deriva.calcular({"AAPL": 6000.0, "TSLA": 1000.0}, {"AAPL": 1.0})
    assert d.invertido == pytest.approx(7000.0)
    assert d.en_plan == pytest.approx(6000.0)
    assert d.lineas[0].peso_real == pytest.approx(1.0)
    assert d.lineas[0].desviacion == pytest.approx(0.0)
    assert not d.lineas[0].fuera_de_banda
    assert d.fuera_del_objetivo[0].peso_real == pytest.approx(1000.0 / 7000.0)


def test_un_activo_sin_precio_se_aparta_y_se_nombra():
    # Valorarlo a cero rebajaria el total y falsearia la deriva de TODOS los
    # demas, no solo la suya. Se aparta del calculo y vuelve nombrado, para que
    # la pantalla pueda decir que el reparto se hizo sin el.
    d = deriva.calcular({"AAPL": 5000.0, "MSFT": 5000.0, "ZZZZ": None},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert d.sin_precio == ("ZZZZ",)
    assert d.invertido == pytest.approx(10_000.0)


def test_unos_pesos_que_no_suman_uno_se_normalizan_y_se_avisa():
    # Puede pasar de verdad: el equal-weight se calcula sobre los tickers del
    # portafolio, y si luego uno no trae precios el resto suma menos de uno.
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                        {"AAPL": 0.4, "MSFT": 0.4})
    assert d.pesos_normalizados
    assert por_ticker(d)["AAPL"].peso_objetivo == pytest.approx(0.5)


def test_unos_pesos_que_ya_suman_uno_no_se_marcan_como_normalizados():
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert not d.pesos_normalizados


def test_una_cartera_sin_valor_no_divide_por_cero():
    # Pasa si todos los precios fallan a la vez. No hay deriva que medir, y eso
    # es distinto de una deriva de cero.
    d = deriva.calcular({"AAPL": None}, {"AAPL": 1.0})
    assert d.invertido == pytest.approx(0.0)
    assert d.lineas == ()
    assert d.sin_precio == ("AAPL",)


def test_los_pesos_normalizados_viajan_aunque_no_haya_nada_invertido():
    # El caso de una cartera recien creada: todo el dinero en efectivo y ningun
    # activo comprado. `lineas` sale vacia, asi que quien reparta el efectivo
    # no puede reconstruir el objetivo desde ahi y lo necesita aparte.
    d = deriva.calcular({}, {"AAPL": 0.4, "MSFT": 0.4})
    assert d.invertido == pytest.approx(0.0)
    assert d.lineas == ()
    assert d.pesos == {"AAPL": pytest.approx(0.5), "MSFT": pytest.approx(0.5)}


def test_las_lineas_vienen_ordenadas_por_desviacion():
    # La pantalla las pinta en este orden, asi que lo mas urgente sale arriba
    # sin que la vista tenga que ordenar nada.
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 3900.0, "NVDA": 100.0},
                        {"AAPL": 0.34, "MSFT": 0.33, "NVDA": 0.33})
    assert [l.ticker for l in d.lineas] == ["NVDA", "AAPL", "MSFT"]
