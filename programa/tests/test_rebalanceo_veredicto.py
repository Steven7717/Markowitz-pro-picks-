"""Lo que Rebalanceo dice del veredicto del objetivo, y cuando se calla.

Un test de la lectura, no del widget: `vistas/rebalanceo.py` es un guion de
Streamlit y no se puede importar, asi que la decision vive en
`seguimiento/libro.py` --como `pesos_objetivo` e `importe_previsto`-- y aqui se
fija esa decision entera. Es el mismo reparto que declara `vistas/libros.py`.

Por que esta pantalla y no solo Portafolios: es la unica donde el veredicto se
traduce en dinero. Portafolios lo ENSENA; Rebalanceo propone pagar comisiones
para acercarse a esos pesos. Un objetivo cuyos pesos no se distinguen de
repartir por igual convierte esa propuesta en coste cierto a cambio de una
ventaja no demostrada, y eso hay que decirlo antes de la tabla, no despues.
"""

from seguimiento.libro import Objetivo, nota_del_veredicto, veredicto_de

# El caso del defecto: hueco de +0,35 con error de +-0,20. Pasaba de un error
# estandar --y por eso el fichero guarda True-- y no pasa de dos, que es el
# liston de hoy.
JUSTITO = {
    "oos_sharpe": 2.42, "oos_equal_weight_sharpe": 2.07,
    "oos_gap_stderr": 0.20, "oos_windows": 4,
    "beats_equal_weight": True,
    "oos_umbral_veredicto": 0.20, "oos_sigmas_veredicto": 1.0,
}

# Hueco de +0,55 contra el mismo error: pasa de dos y sigue ganando hoy.
HOLGADO = {**JUSTITO, "oos_sharpe": 2.62,
           "oos_umbral_veredicto": 0.40, "oos_sigmas_veredicto": 2.0}

# Hueco de -0,57: pierde, y con margen.
PIERDE = {**HOLGADO, "oos_sharpe": 1.50, "beats_equal_weight": False}

# Un libro anterior a que existiera el error de la diferencia.
VIEJO = {"oos_sharpe": 2.42, "oos_equal_weight_sharpe": 2.07,
         "oos_windows": 4, "beats_equal_weight": True}


def objetivo(metricas: dict, base: str = "estrategia") -> Objetivo:
    return Objetivo(
        fecha="2026-09-02", base=base,
        portafolio={"posiciones": [{"ticker": "AAPL", "peso": 1.0}]},
        veredicto=veredicto_de(metricas),
    )


def test_sin_objetivo_no_hay_nada_que_decir():
    assert nota_del_veredicto(None) is None


def test_un_libro_que_reparte_por_igual_no_recibe_el_juicio_de_la_optimizacion():
    """Con base `equal_weight` la pantalla se calla, gane o pierda el veredicto.

    El dictamen dice si la OPTIMIZACION superaba a repartir por igual, y este
    libro no esta siguiendo la optimizacion: `pesos_objetivo` le devuelve 1/N e
    ignora los pesos guardados. Pintarlo aqui invitaria a leerlo como un juicio
    sobre el rebalanceo que el usuario esta a punto de hacer, que es otra cosa.
    """
    assert nota_del_veredicto(objetivo(JUSTITO, base="equal_weight")) is None
    assert nota_del_veredicto(objetivo(HOLGADO, base="equal_weight")) is None


def test_un_objetivo_no_distinguible_de_repartir_por_igual_avisa_antes_de_operar():
    """El caso con consecuencia: coste cierto, ventaja no demostrada.

    Es lo unico de esta pantalla que sube de `st.caption` a recuadro. Lo que
    viene debajo --deriva, reparto y coste-- propone acercar la cartera a unos
    pesos que hoy no se distinguen de 1/N, y el usuario tiene que leerlo antes
    de mirar la factura, no despues.
    """
    nivel, texto = nota_del_veredicto(objetivo(JUSTITO))

    assert nivel == "aviso"
    assert "no distinguen" in texto
    assert "no está demostrada" in texto
    # El liston cambio y el fichero guarda otra cosa: se dice, no se cambia en
    # silencio. Misma coletilla que en Portafolios y Estrenar.
    assert "otro veredicto" in texto


def test_un_objetivo_que_pierde_avisa_igual_y_lo_dice_con_su_palabra():
    """«Queda por debajo» no es «no se distingue», y el aviso no los funde."""
    nivel, texto = nota_del_veredicto(objetivo(PIERDE))

    assert nivel == "aviso"
    assert "Queda por debajo" in texto
    assert "no está demostrada" in texto


def test_un_objetivo_que_gana_se_dice_en_gris_y_sin_coletilla():
    """Gana hoy y ganaba en el fichero: no hay nada de que avisar.

    Un recuadro verde aqui competiria con el de «dentro / fuera de banda», que
    es el veredicto que esta pantalla existe para dar. Este es la premisa, y va
    en el mismo gris que la fecha del objetivo.
    """
    nivel, texto = nota_del_veredicto(objetivo(HOLGADO))

    assert nivel == "caption"
    assert "superaban a repartir por igual" in texto
    assert "otro veredicto" not in texto


def test_un_libro_viejo_dice_que_no_se_puede_recomprobar():
    """Ni recuadro ni silencio: el hueco se nombra.

    Callarlo dejaria la tabla de deriva sin su premisa, y afirmar el
    `beats_equal_weight` guardado seria dar por bueno un veredicto que nadie
    puede volver a dictar.
    """
    nivel, texto = nota_del_veredicto(objetivo(VIEJO))

    assert nivel == "caption"
    assert "no se puede" in texto


def test_un_objetivo_hecho_a_mano_no_finge_tener_una_corrida_detras():
    """La «mezcla de hoy» de Empezar un libro tambien nace con base estrategia.

    Ese objetivo son los pesos que el usuario ya tenia, no la salida de un
    optimizador: no hubo walk-forward, asi que no hay veredicto que falte.
    Escribirle «este libro es anterior a que el programa midiera el error de la
    diferencia» seria falso --no llego tarde, es que nunca hubo corrida-- y le
    sugeriria al usuario que le falta una evidencia que no le corresponde.

    La frontera es `oos_sharpe`: si no hay medicion fuera de muestra no hay
    nada de lo que hablar. Es la misma que usa `exporter.notas_pdf`.
    """
    a_mano = Objetivo(
        fecha="2026-09-02", base="estrategia",
        portafolio={"posiciones": [{"ticker": "AAPL", "peso": 1.0}]},
    )

    assert a_mano.veredicto == {}
    assert nota_del_veredicto(a_mano) is None
    # Y un portafolio del optimizador al que no le corrio el walk-forward
    # tampoco: `metricas_de_validacion(None)` deja `oos_sharpe` en None.
    assert nota_del_veredicto(objetivo({"oos_windows": 0})) is None
