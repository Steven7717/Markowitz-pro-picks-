"""Renombrar un portafolio guardado, y saber que nombres ya estan usados.

Se puede cambiar la etiqueta y **no el calculo**: los pesos y las metricas los
produjo el optimizador para una lista exacta de tickers y unos limites exactos,
asi que tocarlos aqui dejaria numeros que pertenecen a otra cartera con pinta de
recien calculados.
"""

import pytest

import cartera


def _portafolio(nombre="Mi cartera", nota=""):
    return cartera.Portafolio(
        nombre=nombre,
        fecha="2026-09-10T09:00:00",
        posiciones=[
            cartera.Posicion(ticker="AAA", peso=0.6),
            cartera.Posicion(ticker="BBB", peso=0.4),
        ],
        horizonte="1y",
        estrategia="max_sharpe",
        peso_min=0.0,
        peso_max=1.0,
        permitir_cortos=False,
        shrinkage=True,
        metricas={"sharpe": 1.23},
        nota=nota,
    )


def test_renombrar_cambia_la_etiqueta_y_deja_el_calculo_intacto(tmp_path):
    """Es la mitad de la regla: lo que se puede cambiar, cambia."""
    ruta = cartera.guardar(_portafolio(), tmp_path)

    nuevo = cartera.reetiquetar(
        cartera.cargar(ruta), ruta, "Cartera conservadora", "revisada en septiembre"
    )
    assert nuevo.nombre == "Cartera conservadora"
    assert nuevo.nota == "revisada en septiembre"

    # Y la otra mitad, que es la que importa: NADA del calculo se movio.
    releido = cartera.cargar(ruta)
    assert releido.nombre == "Cartera conservadora"
    assert [(p.ticker, p.peso) for p in releido.posiciones] == [("AAA", 0.6), ("BBB", 0.4)]
    assert releido.metricas == {"sharpe": 1.23}
    assert releido.estrategia == "max_sharpe"
    assert releido.fecha == "2026-09-10T09:00:00"


def test_renombrar_no_deja_un_fichero_de_mas(tmp_path):
    """Se reescribe en su sitio.

    Con `guardar` cada renombrado dejaria una copia mas, y la lista se llenaria
    de fotografias del mismo calculo con nombres distintos.
    """
    ruta = cartera.guardar(_portafolio(), tmp_path)
    cartera.reetiquetar(cartera.cargar(ruta), ruta, "Otro nombre", "")

    assert len(list(tmp_path.glob("*.json"))) == 1
    assert ruta.exists(), "se reescribe el mismo fichero, no se crea otro"


def test_un_nombre_vacio_se_rechaza_al_renombrar(tmp_path):
    """La misma regla que al guardar: sin nombre no se encuentra despues."""
    ruta = cartera.guardar(_portafolio(), tmp_path)
    with pytest.raises(cartera.NombreInvalido):
        cartera.reetiquetar(cartera.cargar(ruta), ruta, "   ", "")


def test_nombres_usados_ve_los_repetidos(tmp_path):
    """Es lo que hace que el aviso pueda darse ANTES de guardar.

    `guardar` nunca sobrescribe --una fotografia que quiza ya estas siguiendo en
    un libro no se pisa-- pero sin esto tampoco habia forma de avisar, y guardar
    dos veces con el mismo nombre dejaba dos entradas indistinguibles.
    """
    assert cartera.nombres_usados(tmp_path) == set()

    cartera.guardar(_portafolio("Mi cartera"), tmp_path)
    assert cartera.nombres_usados(tmp_path) == {"Mi cartera"}

    cartera.guardar(_portafolio("Mi cartera"), tmp_path)
    cartera.guardar(_portafolio("Otra"), tmp_path)
    assert cartera.nombres_usados(tmp_path) == {"Mi cartera", "Otra"}
    assert len(list(tmp_path.glob("*.json"))) == 3, "guardar sigue sin sobrescribir"
