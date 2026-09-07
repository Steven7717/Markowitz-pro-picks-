import random

import pytest

from rebalanceo import reparto

OBJETIVO = {"AAPL": 0.5, "MSFT": 0.5}


def test_sin_efectivo_no_hay_nada_que_repartir():
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                         efectivo=0.0, coste=1.0)
    assert r.asignaciones == {}
    assert r.descartadas == {}


def test_el_dinero_va_donde_falta():
    # 6.000 y 4.000 con objetivo mitad y mitad: los 2.000 nuevos van enteros a
    # MSFT, que es lo que corrige deriva sin vender nada.
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                         efectivo=2000.0, coste=1.0)
    assert r.asignaciones == {"MSFT": pytest.approx(2000.0)}


def test_con_efectivo_suficiente_los_pesos_quedan_exactos():
    # La identidad que hace util al reparto: si el dinero alcanza para cubrir
    # todos los deficits, despues del reparto la cartera esta EXACTAMENTE en su
    # objetivo. Sin vender nada.
    valores = {"AAPL": 6000.0, "MSFT": 4000.0}
    r = reparto.repartir(valores, OBJETIVO, efectivo=4000.0, coste=1.0)
    finales = {t: valores.get(t, 0.0) + r.asignaciones.get(t, 0.0) for t in OBJETIVO}
    total = sum(finales.values())
    for ticker, peso in OBJETIVO.items():
        assert finales[ticker] / total == pytest.approx(peso)


@pytest.mark.parametrize("semilla", range(20))
def test_el_reparto_acerca_la_cartera_a_su_objetivo(semilla):
    # **La propiedad verdadera es agregada, no por activo.** Una version
    # anterior de este test afirmaba que el reparto no aleja a NINGUN activo de
    # su objetivo, y eso es falso: el reparto proporcional al deficit da mas a
    # quien mas le falta, el total crece, y un activo que casi estaba en su
    # sitio ve bajar su peso. Medido con los numeros que tenia este test:
    # MSFT pasaba de 0,0300 a 0,0342 de desviacion.
    #
    # Lo que si se cumple --y es lo que hace util al reparto-- es que la SUMA
    # de las desviaciones nunca sube. Se comprueba sobre casos generados y no
    # sobre uno elegido a mano, que es exactamente como se colo la afirmacion
    # falsa: un solo caso bien elegido la sostenia.
    #
    # Con coste cero para aislar la propiedad del reparto del tope economico,
    # que tiene sus propios tests.
    rnd = random.Random(semilla)
    n = rnd.randint(2, 6)
    tickers = [f"T{i}" for i in range(n)]
    crudos = [rnd.random() + 0.01 for _ in tickers]
    total_w = sum(crudos)
    objetivo = {t: w / total_w for t, w in zip(tickers, crudos)}
    valores = {t: rnd.random() * 10_000 + 1.0 for t in tickers}
    efectivo = rnd.random() * 8_000 + 1.0

    r = reparto.repartir(valores, objetivo, efectivo, coste=0.0)
    despues = {t: valores[t] + r.asignaciones.get(t, 0.0) for t in tickers}

    v_antes, v_despues = sum(valores.values()), sum(despues.values())
    antes = sum(abs(valores[t] / v_antes - objetivo[t]) for t in tickers)
    ahora = sum(abs(despues[t] / v_despues - objetivo[t]) for t in tickers)
    assert ahora <= antes + 1e-9


@pytest.mark.parametrize("semilla", range(20))
def test_los_deficits_nunca_suman_menos_que_el_efectivo(semilla):
    # La propiedad que sostiene la formula sin ramas, comprobada en vez de
    # asumida. Las diferencias CON SIGNO entre valor objetivo y valor actual
    # suman exactamente el efectivo, asi que las positivas --los deficits--
    # suman siempre eso o mas. Si esto fallara, sobraria dinero por colocar y
    # `C * d / sum(d)` repartiria de menos sin que nada lo dijera.
    rnd = random.Random(semilla)
    n = rnd.randint(2, 6)
    tickers = [f"T{i}" for i in range(n)]
    crudos = [rnd.random() + 0.01 for _ in tickers]
    total_w = sum(crudos)
    objetivo = {t: w / total_w for t, w in zip(tickers, crudos)}
    valores = {t: rnd.random() * 10_000 for t in tickers}
    efectivo = rnd.random() * 5_000

    total = sum(valores.values()) + efectivo
    deficits = [max(0.0, total * objetivo[t] - valores[t]) for t in tickers]
    assert sum(deficits) >= efectivo - 1e-6


def test_una_asignacion_que_no_compensa_se_retira_y_se_reparte():
    # 1.000 de efectivo entre dos deficits muy desiguales (950 y 50): la parte
    # pequena no llega al minimo economico (su reparto inicial de 50 no cubre
    # el coste de 1 sobre el 1%), asi que se retira y su importe va a la otra,
    # que pasa de 950 a los 1.000 completos. El dinero tiene que ir a alguna
    # parte -- descartar sin mas dejaria un sobrante que nadie coloca.
    r = reparto.repartir({"AAPL": 5100.0, "MSFT": 4900.0},
                         {"AAPL": 0.55, "MSFT": 0.45},
                         efectivo=1000.0, coste=1.0)
    assert set(r.asignaciones) == {"AAPL"}
    assert r.asignaciones["AAPL"] == pytest.approx(1000.0)
    assert set(r.descartadas) == {"MSFT"}


def test_una_aportacion_demasiado_pequena_no_se_invierte():
    # Si ninguna asignacion compensa, la respuesta util es decirlo, no proponer
    # cuatro compras de tres dolares.
    r = reparto.repartir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                         efectivo=20.0, coste=5.0)
    assert r.asignaciones == {}
    assert set(r.descartadas) == {"AAPL", "MSFT"}


def test_lo_repartido_suma_el_efectivo():
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 3000.0, "NVDA": 1000.0},
                         {"AAPL": 0.34, "MSFT": 0.33, "NVDA": 0.33},
                         efectivo=2500.0, coste=1.0)
    assert sum(r.asignaciones.values()) == pytest.approx(2500.0)


def test_un_activo_del_objetivo_que_no_se_tiene_recibe_dinero():
    r = reparto.repartir({"AAPL": 10_000.0}, {"AAPL": 0.5, "MSFT": 0.5},
                         efectivo=5000.0, coste=1.0)
    assert r.asignaciones["MSFT"] == pytest.approx(5000.0)
