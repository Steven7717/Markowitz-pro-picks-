"""La cifra con la que Rebalanceo arranca el campo de aportación.

Es un test de la lectura, no del widget: `vistas/rebalanceo.py` es un script de
Streamlit y no se puede importar. Lo que sí se puede fijar aquí es la decisión
que el widget consume, y esa decisión es toda la lógica que J añade a G.
"""

from seguimiento import libro


def test_el_plan_del_libro_es_la_cifra_de_partida():
    """Se eligió al estrenar el libro, y no se vuelve a preguntar.

    Es lo que el usuario pidió: que G use la aportación prevista en vez de
    hacerle escribirla otra vez cada mes.
    """
    plan = libro.AportacionPrevista(500.0, "mensual")
    assert libro.importe_previsto(plan) == 500.0


def test_sin_plan_se_arranca_en_cero_y_no_en_una_invencion():
    """Cero, no una cifra por defecto que parezca razonable.

    Un libro sin plan es uno cuyo dueño dijo que no iba a aportar, o que nunca
    contestó. Cualquier otro arranque repartiría dinero que nadie ha dicho que
    exista, y la propuesta resultante sería plausible y falsa.
    """
    assert libro.importe_previsto(None) == 0.0
