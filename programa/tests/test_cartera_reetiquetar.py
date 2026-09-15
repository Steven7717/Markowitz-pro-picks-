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


# --- El temporal de la reescritura ------------------------------------------


def _escrito_en(directorio):
    """Un portafolio ya guardado en disco, listo para reetiquetar en su sitio."""
    import dataclasses
    import json

    ruta = directorio / "2026-09-10-090000-mi-cartera.json"
    ruta.write_text(
        json.dumps(dataclasses.asdict(_portafolio()), ensure_ascii=False),
        encoding="utf-8",
    )
    return ruta


def test_dos_reetiquetados_no_comparten_el_nombre_del_temporal(tmp_path, monkeypatch):
    """El razonamiento de `seguimiento/libro.py:actualizar` palabra por palabra:
    con `ruta.with_suffix(".tmp")` dos ventanas de Portafolios escriben en el
    MISMO fichero, y si un `replace` cae mientras la otra esta a mitad de su
    escritura, lo que aterriza en el destino es JSON truncado.

    `guardar` nunca sobrescribe y por eso el suyo si esta justificado. Esto si
    sobrescribe: es una reescritura en su sitio.
    """
    from pathlib import Path

    ruta = _escrito_en(tmp_path)

    usados = []
    original = Path.replace

    def anotando(self, destino):
        usados.append(Path(self))
        return original(self, destino)

    monkeypatch.setattr(Path, "replace", anotando)
    cartera.reetiquetar(_portafolio(), ruta, "Uno", "")
    cartera.reetiquetar(_portafolio(), ruta, "Dos", "")

    assert len(usados) == 2
    assert usados[0] != usados[1]
    # En el mismo directorio que el destino: `replace` solo es atomico dentro
    # del mismo volumen, que es lo unico que este patron compra.
    assert {p.parent for p in usados} == {ruta.parent}


def test_un_reetiquetado_no_deja_el_temporal_detras(tmp_path):
    ruta = _escrito_en(tmp_path)
    cartera.reetiquetar(_portafolio(), ruta, "Uno", "")
    assert [p.name for p in tmp_path.iterdir()] == [ruta.name]
