import pytest

from rebalanceo import criterio


def test_los_tres_umbrales_son_los_congelados():
    # Si alguien los cambia, este test lo dice. Cambiarlos exige una enmienda
    # fechada en el diseno, no una edicion silenciosa: la fecha del commit que
    # los congelo es la prueba de que no se movieron al ver los numeros.
    assert criterio.BANDA_ABSOLUTA == 0.05
    assert criterio.BANDA_RELATIVA == 0.25
    assert criterio.COSTE_MAXIMO == 0.01


# --- La banda -----------------------------------------------------------------


def test_un_objetivo_grande_lo_manda_la_banda_absoluta():
    # Con objetivo 40%, la relativa exigiria 10 puntos: la absoluta dispara
    # antes, a los 5. Es el extremo que la banda relativa sola cubriria mal.
    assert criterio.fuera_de_banda(0.05, 0.40)
    assert not criterio.fuera_de_banda(0.049, 0.40)


def test_un_objetivo_pequeno_lo_manda_la_banda_relativa():
    # Con objetivo 3%, la absoluta exigiria pasar del 8%: casi triplicarse, o
    # sea que nunca. La relativa dispara a los 0,75 puntos.
    assert criterio.fuera_de_banda(0.0075, 0.03)
    assert not criterio.fuera_de_banda(0.0074, 0.03)


def test_la_banda_es_simetrica():
    # Estar por debajo del objetivo cuenta igual que estar por encima.
    assert criterio.fuera_de_banda(-0.05, 0.40)
    assert criterio.fuera_de_banda(-0.0075, 0.03)


def test_una_desviacion_de_cero_nunca_esta_fuera_de_banda():
    for objetivo in (0.0, 0.03, 0.40, 1.0):
        assert not criterio.fuera_de_banda(0.0, objetivo)


def test_con_objetivo_cero_la_banda_relativa_no_aplica():
    # El 25% de cero es cero, asi que sin esta guarda CUALQUIER desviacion
    # disparia -- incluida la de cero, porque `abs(0) >= 0` es cierto. Los
    # activos fuera del objetivo se tratan aparte justamente por esto.
    assert not criterio.fuera_de_banda(0.02, 0.0)
    assert criterio.fuera_de_banda(0.06, 0.0)


# --- El tope de coste ---------------------------------------------------------


def test_una_operacion_grande_merece_la_pena():
    assert criterio.merece_la_pena(2000.0, coste=1.0)


def test_una_operacion_pequena_no_merece_la_pena():
    # Mover 20 dolares pagando 5 es tirar el 25%. Es el numero que hace el
    # criterio economico y no solo geometrico.
    assert not criterio.merece_la_pena(20.0, coste=5.0)


def test_el_tope_esta_justo_en_el_uno_por_ciento():
    assert criterio.merece_la_pena(1000.0, coste=10.0)
    assert not criterio.merece_la_pena(1000.0, coste=10.01)


def test_con_coste_cero_siempre_merece_la_pena():
    # Un broker sin comisiones no bloquea ninguna operacion, por pequena que
    # sea. Es correcto: el criterio mide coste contra importe, y aqui no hay
    # coste que medir.
    assert criterio.merece_la_pena(1.0, coste=0.0)


def test_una_operacion_de_importe_cero_no_merece_la_pena():
    # No es una operacion. Sin esta guarda, `coste <= 0.01 * 0` seria cierto
    # con coste cero y se propondria comprar nada.
    assert not criterio.merece_la_pena(0.0, coste=0.0)


def test_el_signo_del_importe_da_igual():
    # Una venta llega con importe negativo y cuesta lo mismo que la compra
    # equivalente.
    assert criterio.merece_la_pena(-2000.0, coste=1.0)
    assert not criterio.merece_la_pena(-20.0, coste=5.0)
