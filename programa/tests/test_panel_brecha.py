"""El aviso de la brecha TWR/TIR no puede afirmar una causa que no comprueba.

Hasta el sub-proyecto K la pantalla escribia siempre lo mismo: que la separacion
entre las dos medidas «es el efecto de *cuando* aportaste». En el libro de
pruebas, que tiene **una sola aportacion**, se separaban 329 puntos y la frase
salia igual --y con un unico momento no hay ningun «cuando» que pueda explicar
nada. La causa real era otra: el precio de compra registrado no coincidia con el
cierre de mercado de ese dia, asi que la serie de valor arranca en 49.911
mientras la TIR parte de los 40.000 que entraron.

Sin red y con la `Historia` construida a mano, por lo mismo que
`tests/test_panel_cabecera.py`: `precios.descargar` ataria el resultado al
calendario de mercado del dia en que se corra.
"""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from seguimiento import libro as mod, panel, posiciones, precios

TICKER = "AAPL"
AYER = date.today() - timedelta(days=1)


def historia(dias: int) -> precios.Historia:
    """Jornadas consecutivas que acaban ayer, a precio plano."""
    fechas = pd.to_datetime([AYER - timedelta(days=d) for d in reversed(range(dias))])
    ceros = {TICKER: [0.0] * dias}
    return precios.Historia(
        cierres=pd.DataFrame({TICKER: [100.0] * dias}, index=fechas),
        dividendos=pd.DataFrame(ceros, index=fechas),
        splits=pd.DataFrame(ceros, index=fechas),
        sin_datos=[],
    )


def cabecera_con(fechas_de_aportacion: "list[date]") -> panel.Cabecera:
    """La cabecera de un libro que recibio dinero en esas fechas."""
    asientos = []
    for i, cuando in enumerate(fechas_de_aportacion):
        asientos.append(mod.Asiento(
            id=f"ap{i}", fecha=cuando.isoformat(), tipo="aportacion", importe=1000.0,
        ))
    asientos.append(mod.Asiento(
        id="c1", fecha=fechas_de_aportacion[0].isoformat(), tipo="compra",
        ticker=TICKER, acciones=5.0, precio=100.0, importe=500.0,
    ))
    vivos = posiciones.vigentes(asientos)
    marcha = posiciones.serie(vivos, historia(dias=10))
    return panel.cabecera(marcha, vivos, sin_valorar=False)


def test_con_un_solo_flujo_el_aviso_no_atribuye_la_causa():
    """La misma brecha, dicha de dos maneras segun haya «cuando» o no.

    Las dos mitades hacen falta: sin la de dos flujos, un aviso que nunca
    explicara nada pasaria el test igual, y lo que hay que fijar no es que el
    programa se calle sino que **hable solo de lo que ha comprobado**.
    """
    una = cabecera_con([AYER - timedelta(days=9)])
    dos = cabecera_con([AYER - timedelta(days=9), AYER - timedelta(days=4)])
    assert (una.flujos, dos.flujos) == (1, 2)

    # La brecha se fija a mano para que el aviso dependa SOLO del recuento de
    # flujos: con precios planos las dos medidas coinciden, y lo que este test
    # mide no es cuanto se separan sino que se dice cuando se separan.
    brecha = {"twr_anual": 0.10, "tir": 0.45}
    con_una = panel.aviso_de_brecha(replace(una, **brecha))
    con_dos = panel.aviso_de_brecha(replace(dos, **brecha))

    assert "35.0%" in con_una and "35.0%" in con_dos

    # Con dos momentos, la explicacion del calendario se sostiene y se da.
    assert "cuándo* aportaste" in con_dos
    assert "buenos momentos" in con_dos

    # Con uno solo no hay calendario que valga, y el aviso no lo finge: dice
    # que se separan, niega la causa que no puede ser, y deja la otra como
    # posible sin afirmarla.
    assert "no se puede decir" in con_una
    assert "no comprobada" in con_una
    assert "buenos momentos" not in con_una
    assert "momentos peores" not in con_una


# --- La causa que SI se puede medir manda sobre la que se supone -------------


def cabecera_con_precio(precio_registrado: float,
                        fechas: "list[date]" = None) -> panel.Cabecera:
    """Un libro que compro a `precio_registrado` mientras el mercado cerro a 100."""
    fechas = fechas or [AYER - timedelta(days=9), AYER - timedelta(days=4)]
    asientos = []
    for i, cuando in enumerate(fechas):
        asientos.append(mod.Asiento(
            id=f"ap{i}", fecha=cuando.isoformat(), tipo="aportacion", importe=1000.0,
        ))
    asientos.append(mod.Asiento(
        id="c1", fecha=fechas[0].isoformat(), tipo="compra", ticker=TICKER,
        acciones=5.0, precio=precio_registrado, importe=5 * precio_registrado,
    ))
    vivos = posiciones.vigentes(asientos)
    marcha = posiciones.serie(vivos, historia(dias=10))
    return panel.cabecera(marcha, vivos, sin_valorar=False)


def test_un_precio_de_registro_que_no_es_el_cierre_se_mide_y_se_nombra():
    """Dos flujos no bastan para culpar al calendario si hay otra causa medida.

    El libro real del proyecto tenia doce compras registradas un 38,7% por
    debajo del cierre de ese dia: el 83% de la «ganancia» aparecio antes de que
    el mercado se moviera. La pantalla decia, con dos flujos y toda confianza,
    que la brecha era «el efecto de cuando aportaste». No lo era, y el programa
    tenia el dato para saberlo.
    """
    cab = cabecera_con_precio(50.0)  # mercado a 100: la serie arranca al doble

    assert cab.salto_inicial is not None and cab.salto_inicial > 0
    aviso = panel.aviso_de_brecha(replace(cab, twr_anual=0.10, tir=0.45))

    assert "Esa diferencia es el efecto" not in aviso, "afirma el calendario"
    assert "cierre de mercado" in aviso, "no nombra la causa que si ha medido"


def test_sin_salto_inicial_la_explicacion_del_calendario_se_mantiene():
    """La mitad que impide que el arreglo sea «callarse siempre»."""
    cab = cabecera_con_precio(100.0)  # registrado al cierre: no hay salto

    assert cab.salto_inicial == 0 or abs(cab.salto_inicial) < 1.0
    aviso = panel.aviso_de_brecha(replace(cab, twr_anual=0.10, tir=0.45))

    assert "Esa diferencia es el efecto de *cuándo* aportaste" in aviso


def test_un_flujo_simbolico_no_licencia_la_explicacion_del_calendario():
    """Un centimo es un «momento», pero no mueve una TIR ponderada por dinero.

    `flujos >= 2` los contaba igual, asi que bastaba una aportacion de 0,01
    para que el programa pasara de dudar honestamente a afirmar una causa.
    """
    fechas = [AYER - timedelta(days=9), AYER - timedelta(days=4)]
    asientos = [
        mod.Asiento(id="ap0", fecha=fechas[0].isoformat(), tipo="aportacion",
                    importe=1000.0),
        mod.Asiento(id="ap1", fecha=fechas[1].isoformat(), tipo="aportacion",
                    importe=0.01),
        mod.Asiento(id="c1", fecha=fechas[0].isoformat(), tipo="compra",
                    ticker=TICKER, acciones=5.0, precio=100.0, importe=500.0),
    ]
    vivos = posiciones.vigentes(asientos)
    cab = panel.cabecera(vivos=vivos, marcha=posiciones.serie(vivos, historia(dias=10)),
                         sin_valorar=False)

    assert cab.flujos == 2
    aviso = panel.aviso_de_brecha(replace(cab, twr_anual=0.10, tir=0.45))

    assert "Esa diferencia es el efecto" not in aviso
