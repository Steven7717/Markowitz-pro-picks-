"""Las cifras de cabecera, que hasta el sub-proyecto K no se podian importar.

Vivian dentro de `vistas/seguimiento.py`, un guion de Streamlit: se ejecuta al
importarlo, pinta widgets y llama a la red, asi que ningun test podia mirarlas.
Lo que protegia sus correcciones era un comentario. Aqui estan por fin escritas
como tests, y en particular la primera: el corte temporal comun de `aportado` y
`valor`, que en el sub-proyecto F produjo GANANCIA -9.700 sin que nadie hubiera
perdido un dolar.

Sin red y con la `Historia` construida a mano, por lo mismo que
`tests/test_seguimiento_recien_estrenado.py`: `precios.descargar` ataria el
resultado al calendario de mercado del dia en que se corra --un sabado, o el
lunes de un festivo, cambian cual es el ultimo cierre-- y con el, cuantos
asientos quedan sin valorar, que es justo la variable que estos tests fijan.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from seguimiento import libro as mod, panel, posiciones, precios

TICKER = "AAPL"


def historia(ultimo: date, cierres: "list[float]") -> precios.Historia:
    """Cierres de jornadas consecutivas que acaban en `ultimo`."""
    dias = len(cierres)
    fechas = pd.to_datetime(
        [ultimo - timedelta(days=d) for d in reversed(range(dias))]
    )
    ceros = {TICKER: [0.0] * dias}
    return precios.Historia(
        cierres=pd.DataFrame({TICKER: cierres}, index=fechas),
        dividendos=pd.DataFrame(ceros, index=fechas),
        splits=pd.DataFrame(ceros, index=fechas),
        sin_datos=[],
    )


def cabecera_de(asientos, hist):
    """Lo mismo que hace la pantalla: la serie, la condicion, y la cabecera.

    `sin_valorar` se calcula aqui igual que en `vistas/seguimiento.py`, porque
    es un parametro de `panel.cabecera` y no algo que el modulo decida por su
    cuenta: es la misma condicion que gobierna el aviso de la pantalla.
    """
    vivos = posiciones.vigentes(asientos)
    marcha = posiciones.serie(vivos, hist)
    sin_valorar = bool(marcha.posteriores) and marcha.posteriores == len(vivos)
    return panel.cabecera(marcha, vivos, sin_valorar), marcha, sin_valorar


def test_una_aportacion_de_hoy_no_inventa_una_perdida():
    """El defecto de F, escrito como test por fin.

    Una cartera vieja que subio, mas una aportacion registrada HOY sobre una
    serie de precios que acaba AYER. El dinero de hoy no esta en la serie
    --no hay precio con que valorarlo-- asi que si `aportado` lo sumara, se
    restarian dos momentos distintos y la ganancia saldria negativa sin que
    nadie hubiera perdido nada. Medido en la app dio VALOR 10.299, APORTADO
    20.000 y GANANCIA -9.700.

    `aportado` sale de `marcha.flujos`, que vive en el calendario de la serie,
    y por eso las dos cifras se restan dentro del mismo corte.
    """
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    # Once cierres, de 300 a 310: la cartera sube de verdad.
    hist = historia(ayer, [300.0 + i for i in range(11)])
    hace_diez = (ayer - timedelta(days=10)).isoformat()

    asientos = [
        mod.Asiento(id="a1", fecha=hace_diez, tipo="aportacion", importe=10_000.0),
        mod.Asiento(id="c1", fecha=hace_diez, tipo="compra", ticker=TICKER,
                    acciones=33.0, precio=300.0, importe=9_900.0),
        # La de hoy: registrada, real, y todavia sin precio con que valorarla.
        mod.Asiento(id="a2", fecha=hoy.isoformat(), tipo="aportacion",
                    importe=10_000.0),
    ]

    cab, _, sin_valorar = cabecera_de(asientos, hist)

    # No es el caso «nada valorado»: hay diez dias medidos. Si lo fuera, la
    # ganancia seria None y este test no estaria midiendo lo que dice.
    assert sin_valorar is False
    assert cab.ganancia is not None

    # Lo que importa: los 10.000 de hoy NO estan en `aportado`, porque tampoco
    # estan en `valor`. Sumando los asientos saldria 20.000.
    assert cab.aportado == pytest.approx(10_000.0)
    # Y la consecuencia, que es el sintoma que se vio en pantalla.
    assert cab.ganancia > 0
    assert cab.ganancia == pytest.approx(cab.valor - cab.aportado)


def test_sin_nada_valorado_las_cifras_de_precio_son_none_y_no_cero():
    """Un libro estrenado hoy: «—», no 0,00.

    Un cero afirma que la cartera no vale nada. Aqui nadie ha medido eso: es
    que todavia no hay un cierre con el que valorarla. Las dos cosas se leen
    igual en un 0,00, y por eso estas cuatro cifras salen `None`.
    """
    hoy = date.today()
    hist = historia(hoy - timedelta(days=1), [300.0] * 5)
    asientos = [
        mod.Asiento(id="a1", fecha=hoy.isoformat(), tipo="aportacion",
                    importe=10_000.0),
        mod.Asiento(id="c1", fecha=hoy.isoformat(), tipo="compra", ticker=TICKER,
                    acciones=10.0, precio=300.0, importe=3_000.0),
    ]

    cab, _, sin_valorar = cabecera_de(asientos, hist)

    assert sin_valorar is True
    assert cab.sin_valorar is True
    assert cab.valor is None
    assert cab.ganancia is None
    assert cab.twr_anual is None
    assert cab.tir is None

    # Y lo que de ahi sale a la pantalla es el «—», no un numero. Es la otra
    # mitad de la misma regla: `None` entra, «—» sale, y en ningun punto del
    # camino aparece un 0,00 que nadie ha medido.
    assert panel._cifra(cab.valor) == "—"
    assert panel._cifra(cab.ganancia) == "—"


def test_aportado_nunca_es_none_porque_es_un_hecho_registrado():
    """El arreglo de J, ahora con test.

    `aportado` no es una medida que dependa del precio: es dinero que entro y
    quedo escrito. Decirle «Aportado neto —» --o peor, 0,00-- a quien acaba de
    meter 10.000 no es una medida que falte, es una afirmacion falsa sobre un
    hecho. Cuando no hay nada valorado sale de los asientos, que es el unico
    sitio donde consta.
    """
    hoy = date.today()
    hist = historia(hoy - timedelta(days=1), [300.0] * 5)
    asientos = [
        mod.Asiento(id="a1", fecha=hoy.isoformat(), tipo="aportacion",
                    importe=10_000.0),
        mod.Asiento(id="r1", fecha=hoy.isoformat(), tipo="retiro",
                    importe=2_500.0),
        mod.Asiento(id="c1", fecha=hoy.isoformat(), tipo="compra", ticker=TICKER,
                    acciones=10.0, precio=300.0, importe=3_000.0),
    ]

    cab, _, sin_valorar = cabecera_de(asientos, hist)

    assert sin_valorar is True
    assert cab.aportado is not None
    # Aportaciones menos retiros. La compra no cuenta: mueve dinero DENTRO de
    # la cartera, no lo mete ni lo saca del bolsillo.
    assert cab.aportado == pytest.approx(7_500.0)


def test_los_dividendos_suman_los_de_todos_los_activos_y_dias():
    """Una sola cifra para toda la tabla de dividendos.

    `marcha.dividendos` es un DataFrame de dias por tickers, asi que la cifra
    de cabecera es la suma de los dos ejes. Con un solo `.sum()` saldria una
    serie por ticker y la pantalla ensenaria la del primero.
    """
    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    hist = historia(ayer, [300.0] * 11)
    hace_diez = (ayer - timedelta(days=10)).isoformat()

    asientos = [
        mod.Asiento(id="a1", fecha=hace_diez, tipo="aportacion", importe=10_000.0),
        mod.Asiento(id="c1", fecha=hace_diez, tipo="compra", ticker=TICKER,
                    acciones=10.0, precio=300.0, importe=3_000.0),
        # Dos cobros, en dos dias distintos.
        mod.Asiento(id="d1", fecha=(ayer - timedelta(days=4)).isoformat(),
                    tipo="dividendo", ticker=TICKER, importe=40.0),
        mod.Asiento(id="d2", fecha=ayer.isoformat(),
                    tipo="dividendo", ticker=TICKER, importe=20.59),
    ]

    cab, marcha, _ = cabecera_de(asientos, hist)

    assert cab.dividendos == pytest.approx(60.59)
    assert cab.dividendos == pytest.approx(float(marcha.dividendos.sum().sum()))
