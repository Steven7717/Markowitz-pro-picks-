"""Un libro estrenado hoy: por que su valor es «—» y no 0,00.

Sin red, y a proposito. El mismo caso con `precios.descargar` diria lo mismo
casi siempre, pero atado al calendario de mercado del dia en que se corra: un
sabado, o el lunes de un festivo, cambian cual es el ultimo cierre y con el
cuantos asientos quedan por valorar. Construir la `Historia` a mano fija esa
variable y deja el test contando en la suite normal, que es donde protege.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from seguimiento import alta, posiciones, precios

TICKER = "AAPL"


def historia_hasta(ultimo: date, dias: int) -> precios.Historia:
    """Cierres de `dias` jornadas consecutivas que acaban en `ultimo`."""
    fechas = pd.to_datetime(
        [ultimo - timedelta(days=d) for d in reversed(range(dias))]
    )
    ceros = {TICKER: [0.0] * dias}
    return precios.Historia(
        cierres=pd.DataFrame({TICKER: [300.0] * dias}, index=fechas),
        dividendos=pd.DataFrame(ceros, index=fechas),
        splits=pd.DataFrame(ceros, index=fechas),
        sin_datos=[],
    )


# La fila de la tabla del estreno, tal como sale de `vistas/estrenar.py`. La
# fecha no va aqui: `asientos_de` se la pone a todos los asientos de la tanda.
COMPRA = {"ticker": TICKER, "acciones": 10, "precio": 300.0}


def test_un_libro_de_hoy_no_tiene_ningun_dia_valorado():
    """Todos los asientos posteriores al ultimo cierre: nada que valorar.

    Es la condicion que la pantalla usa para decir «—» en vez de 0,00. Un cero
    ahi afirmaria que la cartera no vale nada, cuando lo cierto es que todavia
    no se puede saber.
    """
    hoy = date.today()
    asientos = alta.asientos_de(
        [COMPRA], capital=10_000.0, fecha=hoy.isoformat(),
    )
    marcha = posiciones.serie(
        list(asientos), historia_hasta(hoy - timedelta(days=1), dias=5)
    )

    assert marcha.posteriores == len(asientos)
    # Y el cero del que salia el defecto: la serie existe, tiene dias, y en
    # todos vale cero porque la cartera todavia no habia empezado. `iloc[-1]`
    # es exactamente lo que leia la pantalla.
    assert float(marcha.valor.iloc[-1]) == pytest.approx(0.0)


def test_una_compra_de_hoy_sobre_una_cartera_vieja_si_tiene_valor():
    """Algunos asientos posteriores no es lo mismo que todos.

    El caso mixto --ya tenias cosas y hoy compraste mas-- si tiene dias
    valorados, y sus cifras estan medidas. Taparlas con «—» borraria una medida
    que existe, asi que la pantalla compara `posteriores` con el numero de
    asientos vigentes en vez de mirar solo si hay alguno.
    """
    hoy = date.today()
    viejo = hoy - timedelta(days=10)
    asientos = list(alta.asientos_de(
        [COMPRA], capital=10_000.0, fecha=viejo.isoformat(),
    ))
    asientos += list(alta.asientos_de(
        [COMPRA], capital=None, fecha=hoy.isoformat(),
    ))

    marcha = posiciones.serie(
        asientos, historia_hasta(hoy - timedelta(days=1), dias=12)
    )

    # Los dos de hoy quedan fuera; los dos viejos entraron.
    assert marcha.posteriores == 2
    assert marcha.posteriores != len(asientos)
    assert float(marcha.valor.iloc[-1]) > 0.0
