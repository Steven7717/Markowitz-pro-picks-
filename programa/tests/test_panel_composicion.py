"""La composicion: donde esta el peso de cada activo, y que se quedo fuera.

Como `tests/test_panel_cabecera.py`, estos tests existen porque el
sub-proyecto K sacó la aritmetica de `vistas/seguimiento.py` y por fin se puede
importar. Lo que fijan es la regla que el diseño llama «un activo sin precio no
entra»: sus pesos serian falsos, y unas barras que suman 0,80 sin decir por que
son peor que una lista con un nombre debajo.

Sin red: `rendimiento.por_activo` recibe los precios ya resueltos, asi que
basta con pasarle un diccionario y el resultado no depende del calendario de
mercado del dia en que se corra la suite.
"""

import pytest

from seguimiento import libro as mod, panel

PRECIOS = {"AAPL": 200.0, "MSFT": 400.0, "KO": 50.0}


def compra(i: int, ticker: str, acciones: float, precio: float) -> mod.Asiento:
    return mod.Asiento(
        id=f"c{i}",
        fecha="2026-01-05",
        tipo="compra",
        ticker=ticker,
        acciones=acciones,
        precio=precio,
        importe=precio * acciones,
    )


ASIENTOS = [
    mod.Asiento(id="ap", fecha="2026-01-05", tipo="aportacion", importe=10000.0),
    compra(1, "AAPL", 10, 200.0),   # 2.000
    compra(2, "MSFT", 5, 400.0),    # 2.000
    compra(3, "KO", 20, 50.0),      # 1.000
]


def objetivo_de(pesos: dict) -> mod.Objetivo:
    return mod.Objetivo(
        fecha="2026-01-05",
        base="estrategia",
        portafolio={"posiciones": [
            {"ticker": t, "peso": p} for t, p in pesos.items()
        ]},
    )


def test_los_pesos_suman_uno_sobre_lo_que_tiene_precio():
    """El reparto es un reparto: si no suma 1, no esta repartiendo nada."""
    comp = panel.composicion(ASIENTOS, PRECIOS, None)

    assert len(comp.lineas) == 3
    assert sum(linea.peso for linea in comp.lineas) == pytest.approx(1.0)
    # 2.000 sobre 5.000, y no sobre los 10.000 aportados: el efectivo sin
    # invertir no es una posicion, y meterlo en el denominador encogeria todas
    # las barras a la mitad sin que nadie hubiera cambiado de cartera.
    pesos = {linea.ticker: linea.peso for linea in comp.lineas}
    assert pesos["AAPL"] == pytest.approx(0.4)
    assert pesos["MSFT"] == pytest.approx(0.4)
    assert pesos["KO"] == pytest.approx(0.2)


def test_un_activo_sin_precio_queda_fuera_y_vuelve_nombrado():
    """La regla del diseño, y las dos mitades importan igual.

    Fuera del reparto, porque su peso seria falso; y **nombrado**, porque un
    activo que desaparece de la pantalla sin dejar rastro es lo mismo que un
    activo que no tienes. Los que quedan siguen sumando 1: si el que falta
    contase en el denominador, sumarian 0,80 y nadie sabria por que.
    """
    sin_ko = {t: p for t, p in PRECIOS.items() if t != "KO"}

    comp = panel.composicion(ASIENTOS, sin_ko, None)

    assert comp.sin_precio == ("KO",)
    assert [linea.ticker for linea in comp.lineas] == ["AAPL", "MSFT"]
    assert sum(linea.peso for linea in comp.lineas) == pytest.approx(1.0)


def test_sin_objetivo_no_hay_marca_ni_marca_en_cero():
    """Sin plan no se inventa uno igual al peso real, ni uno en cero.

    Rellenar `objetivo` con el peso real pondria la marca justo encima de la
    barra y diria «ya estas donde querias estar», sobre un plan que nadie ha
    escrito. Un cero diria lo contrario y tambien seria inventado.
    """
    comp = panel.composicion(ASIENTOS, PRECIOS, None)

    assert comp.hay_objetivo is False
    assert all(linea.objetivo is None for linea in comp.lineas)


def test_con_objetivo_cada_linea_trae_el_suyo_y_el_que_falta_trae_none():
    """Estar en el libro y no en el objetivo no es tener un objetivo de cero.

    Un cero seria un juicio --«esto sobra»-- sobre un activo del que el plan no
    dice nada. `None` es lo unico que se ha medido: que no hay marca que pintar.
    """
    comp = panel.composicion(
        ASIENTOS, PRECIOS, objetivo_de({"AAPL": 0.5, "MSFT": 0.5})
    )

    assert comp.hay_objetivo is True
    objetivos = {linea.ticker: linea.objetivo for linea in comp.lineas}
    assert objetivos["AAPL"] == pytest.approx(0.5)
    assert objetivos["MSFT"] == pytest.approx(0.5)
    assert objetivos["KO"] is None
