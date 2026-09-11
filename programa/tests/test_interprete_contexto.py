# programa/tests/test_interprete_contexto.py
"""Lo que sale de esta maquina, y en que forma."""

import inspect

import pytest

from interprete import contexto


def test_las_etiquetas_son_letras():
    assert contexto.etiquetas(3) == ("A", "B", "C")


def test_pasado_el_alfabeto_revienta():
    """Envolver en silencio dejaria dos hechos compartiendo letra, y el mapa
    que valida las respuestas resolveria el segundo como el primero."""
    with pytest.raises(ValueError):
        contexto.etiquetas(27)


def test_la_cartera_sale_en_porcentaje():
    texto = contexto.cartera((("MSFT", 0.18, 0.15), ("MU", 0.07, 0.10)))
    assert "MSFT" in texto and "MU" in texto
    assert "18" in texto and "15" in texto


def test_un_activo_sin_objetivo_no_inventa_uno():
    """`Linea.objetivo` es None cuando el libro no tiene plan. Rellenarlo con
    el peso real diria que ya estas donde querias."""
    texto = contexto.cartera((("MSFT", 0.18, None),))
    assert "18" in texto
    assert "sin objetivo" in texto.lower()


def test_las_operaciones_vuelven_con_su_mapa():
    texto, mapa = contexto.operaciones(
        (("MSFT", "vender", 0.03, True), ("MU", "comprar", 0.03, False))
    )
    assert mapa == {"A": "MSFT", "B": "MU"}
    assert "A" in texto and "B" in texto
    assert "MSFT" in texto and "MU" in texto


def test_las_operaciones_dicen_si_compensan():
    """`viable` ya es el veredicto que `rebalanceo/criterio.py:merece_la_pena`
    calculo con el coste real. El modelo no necesita el coste en euros."""
    texto, _ = contexto.operaciones((("MU", "comprar", 0.03, False),))
    assert "no compensa" in texto.lower()


def test_dos_pesos_distintos_no_se_leen_iguales():
    """Redondeando a entero, 4,3% y 4,4% salian los dos como «4%» y el modelo
    concluia que pesan igual."""
    assert contexto._pct(0.043) != contexto._pct(0.044)


def test_una_posicion_diminuta_no_se_lee_como_cero():
    """«0,0%» se lee como que no la tienes. Tener poco no es no tener nada."""
    assert contexto._pct(0.0004) == "menos de 0,1%"


def test_el_cero_de_verdad_si_es_cero():
    assert contexto._pct(0.0) == "0,0%"


def test_los_hechos_vuelven_con_su_mapa():
    from datetime import date

    texto, mapa = contexto.hechos(
        (
            ("MSFT", date(2026, 7, 29), ("2.02",), ("Resultados",), "el documento"),
            ("MU", date(2026, 6, 24), ("4.02",), ("Cuentas no fiables",), "otro"),
        )
    )
    assert mapa == {"A": "MSFT", "B": "MU"}
    assert "el documento" in texto and "otro" in texto
    assert "Resultados" in texto


# --- La garantia: aqui no entra un euro -------------------------------------

_IMPORTES = ("4711.53", "4.711,53", "98234", "1234567")


def test_ninguna_funcion_publica_admite_un_importe():
    """**La garantia es la firma, no un filtro.** Un filtro que borra euros se
    puede saltar anadiendo un campo; una firma que no los admite, no.

    Este test recorre las funciones publicas del modulo y afirma que ninguna
    tiene un parametro que hable de dinero. Es el sabotaje escrito: quien anada
    `importe=` o `valor=` a una de ellas tumba esto.
    """
    prohibidos = {"importe", "valor", "euros", "dinero", "coste", "efectivo",
                  "aportado", "invertido", "ganancia"}
    for nombre, funcion in vars(contexto).items():
        if nombre.startswith("_") or not callable(funcion):
            continue
        if getattr(funcion, "__module__", None) != contexto.__name__:
            continue
        parametros = set(inspect.signature(funcion).parameters)
        assert not (parametros & prohibidos), (
            f"contexto.{nombre} admite {parametros & prohibidos}: "
            "por ahi entra dinero a un prompt que sale de la maquina"
        )


def test_un_libro_con_importes_distintivos_no_los_filtra_a_la_salida():
    """El otro lado de la misma garantia, por si alguien empaqueta un importe
    dentro de una cadena. Los numeros de abajo no aparecen en ningun sitio del
    programa, asi que si salen es porque cruzaron."""
    from datetime import date

    piezas = [
        contexto.cartera((("MSFT", 0.18, 0.15),)),
        contexto.operaciones((("MSFT", "vender", 0.03, True),))[0],
        contexto.hechos(
            (("MSFT", date(2026, 7, 29), ("2.02",), ("Resultados",), "texto"),)
        )[0],
    ]
    for importe in _IMPORTES:
        for pieza in piezas:
            assert importe not in pieza
