"""El panel de Seguimiento cuando hay un split o un dividendo de por medio.

`seguimiento/panel.py` es la capa que la pantalla llama para no calcular nada
ella misma, y era el ultimo sitio por donde `Historia` no pasaba: aunque
`rendimiento.por_activo` y `posiciones.estado` ya saben de splits y dividendos,
seguian recibiendo el libro a secas desde aqui, asi que la tabla de abajo y la
cabecera de arriba volvian a contar cosas distintas del mismo activo.

El caso es el mismo que en `tests/test_seguimiento_rendimiento.py` --compra de
diez, dividendo de 2,00, split 2:1, venta de cinco-- para que las dos capas se
midan contra los mismos numeros y una discrepancia salte en los dos ficheros a
la vez.

Sin red: la `Historia` se construye a mano y los precios llegan ya resueltos.
"""

import pandas as pd
import pytest

from seguimiento import libro as mod, panel, precios

CALENDARIO = pd.to_datetime([
    "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15",
])


def historia_acme() -> precios.Historia:
    """Dividendo de 2,00 el dia 8 y split 2:1 el dia 12, sobre cierres crudos."""
    return precios.Historia(
        cierres=pd.DataFrame(
            {"ACME": [100.0] * 5 + [50.0] * 4}, index=CALENDARIO
        ),
        dividendos=pd.DataFrame(
            {"ACME": [0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
            index=CALENDARIO,
        ),
        splits=pd.DataFrame(
            {"ACME": [0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0]},
            index=CALENDARIO,
        ),
        sin_datos=[],
    )


ASIENTOS = [
    mod.Asiento(id="a", fecha="2026-01-05", tipo="aportacion", importe=1000.0),
    mod.Asiento(id="c1", fecha="2026-01-05", tipo="compra", ticker="ACME",
                acciones=10.0, precio=100.0, importe=1000.0),
    mod.Asiento(id="v1", fecha="2026-01-14", tipo="venta", ticker="ACME",
                acciones=5.0, precio=60.0, importe=300.0),
]

PRECIOS = {"ACME": 50.0}


def test_la_composicion_valora_las_acciones_que_dejo_el_split():
    # Diez compradas, un 2:1 y menos cinco vendidas: quince a 50,00. Sin la
    # historia salian cinco, y el peso de este activo --y por tanto el de todos
    # los demas, que se reparten el mismo denominador-- quedaba a un tercio.
    comp = panel.composicion(ASIENTOS, PRECIOS, None, historia_acme())
    assert comp.invertido == pytest.approx(750.0)
    assert comp.lineas[0].valor == pytest.approx(750.0)


def test_el_efectivo_de_la_composicion_cobra_el_dividendo_automatico():
    # Mil menos mil de la compra, mas veinte del dividendo, mas trescientos de
    # la venta: 320,00. La cabecera ya decia 320,00 --sale de `serie`-- y esta
    # linea decia 300,00, las dos en la misma pantalla y sin nada que explicara
    # la diferencia.
    comp = panel.composicion(ASIENTOS, PRECIOS, None, historia_acme())
    assert comp.efectivo == pytest.approx(320.0)


def test_la_tabla_por_activo_ensena_las_acciones_y_el_coste_ya_partidos():
    fila = panel.filas_por_activo(
        ASIENTOS, PRECIOS, 750.0, None, historia_acme()
    )[0]
    assert fila["Acciones"] == "15"
    assert fila["Coste medio"] == "50.00"
    assert fila["Dividendos"] == "20.00"
    # Peso real sobre el invertido: todo el dinero esta en el unico activo.
    assert fila["Peso real"] == "100.00%"


def test_sin_historia_el_panel_no_inventa_ninguna_accion_corporativa():
    # El parametro es opcional a proposito --hay sitios sin descarga-- y tiene
    # que seguir dando lo que daba: `None` significa «no se conocen acciones
    # corporativas», no «no hubo ninguna».
    comp = panel.composicion(ASIENTOS, PRECIOS, None)
    assert comp.invertido == pytest.approx(250.0)
    assert comp.efectivo == pytest.approx(300.0)


def test_el_historial_dice_por_cuanto_multiplico_el_split():
    # Un split no lleva acciones, ni precio, ni importe: sin el factor, su fila
    # del historial es la palabra «split» y cuatro rayas. Va pegado al tipo y no
    # en una columna nueva porque esa columna seria un «—» en todas las demas
    # filas de todos los libros.
    asientos = ASIENTOS + [
        mod.Asiento(id="s1", fecha="2026-01-12", tipo="split", ticker="ACME",
                    factor=2.0),
    ]
    fila = next(f for f in panel.filas_de_historial(asientos)
                if f["Tipo"].startswith("split"))
    assert fila["Tipo"] == "split ×2"


def test_el_historial_de_lo_que_no_es_un_split_no_cambia():
    fila = next(f for f in panel.filas_de_historial(ASIENTOS)
                if f["Fecha"] == "2026-01-14")
    assert fila["Tipo"] == "venta"
