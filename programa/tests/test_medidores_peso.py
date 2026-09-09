"""La barra de composicion: un peso, una marca, y ninguna palabra de juicio."""

import medidores as m

# Las palabras con las que `vistas/rebalanceo.py` califica una barra igual que
# esta. Estan aqui a mano y no importadas porque `vistas/rebalanceo.py` es un
# guion de Streamlit y no se puede importar desde un test.
VEREDICTOS_DE_REBALANCEO = ("sobreponderado", "infraponderado", "en banda")


def test_sin_objetivo_no_hay_marca():
    """Un libro sin objetivo no recibe una marca en el cero.

    Pintarla ahi diria que el objetivo es cero, que no es lo mismo que no
    tener ninguno.
    """
    assert "mpp-tope" not in m.barra_de_peso("AAPL", 0.20, None, 0.25)


def test_con_objetivo_la_marca_va_donde_toca():
    # La escala es el peso mayor de la cartera, no 1.0: sobre 0,25 un objetivo
    # del 10% cae en el 40% del carril, no en el 10%.
    html = m.barra_de_peso("AAPL", 0.20, 0.10, 0.25)
    assert "mpp-tope" in html
    assert "left:40.00%" in html


def test_el_ticker_se_escapa():
    """Viene del libro, que es texto que escribio el usuario."""
    html = m.barra_de_peso("<script>alert(1)</script>", 0.20, 0.10, 0.25)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_la_fila_no_lleva_veredicto():
    """El test que impide acercar esta funcion a la de Rebalanceo.

    Seguimiento es la pantalla de hechos. La misma barra con una palabra de
    juicio al lado convierte un dato en un consejo, y esa diferencia es la
    razon por la que las dos pantallas existen por separado.
    """
    texto = m.barra_de_peso("AAPL", 0.20, 0.10, 0.25).lower()
    for palabra in VEREDICTOS_DE_REBALANCEO:
        assert palabra not in texto
    for marca in (m.MUY_BUENO, m.BUENO, m.REGULAR, m.MALO, m.MUY_MALO):
        assert marca.veredicto.lower() not in texto
    assert "mpp-vered" not in texto
