import time

import apagado
from apagado import Vigilante


class Reloj:
    """Un reloj que sólo avanza cuando se le dice.

    Sin él, probar "noventa segundos sin nadie" costaría noventa segundos, y un
    test que tarda eso no se ejecuta: se marca para saltarlo y deja de proteger
    nada.
    """

    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def vigilante(conectados: list[int], reloj: Reloj, espera: float = 90.0):
    apagados: list[bool] = []
    v = Vigilante(
        contar=lambda: conectados[0],
        apagar=lambda: apagados.append(True),
        espera=espera,
        reloj=reloj,
    )
    return v, apagados


def test_con_alguien_conectado_no_apaga_nunca():
    reloj = Reloj()
    conectados = [1]
    v, apagados = vigilante(conectados, reloj)
    for _ in range(50):
        reloj.avanzar(60)
        assert v.tic() is False
    assert apagados == []


def test_apaga_cuando_se_cierra_la_ultima_pestana():
    reloj = Reloj()
    conectados = [1]
    v, apagados = vigilante(conectados, reloj)
    v.tic()

    conectados[0] = 0
    assert v.tic() is False  # empieza la cuenta atrás
    reloj.avanzar(89)
    assert v.tic() is False  # todavía no
    reloj.avanzar(2)
    assert v.tic() is True
    assert apagados == [True]


def test_no_apaga_antes_de_que_llegue_el_primer_navegador():
    # El caso que lo rompería todo: entre que arranca el servidor y se abre la
    # pestaña hay cero sesiones, y en un primer arranque --descargando Python y
    # las librerias-- pueden pasar minutos. Sin esta guarda, el programa se
    # apagaria solo justo antes de que el usuario lo vea por primera vez.
    reloj = Reloj()
    v, apagados = vigilante([0], reloj)
    for _ in range(20):
        reloj.avanzar(300)
        assert v.tic() is False
    assert apagados == []


def test_una_recarga_de_la_pagina_no_lo_apaga():
    # Recargar tira el websocket y lo vuelve a levantar: hay un instante a cero.
    # Si bastara con verlo una vez, recargar cerraria el programa.
    reloj = Reloj()
    conectados = [1]
    v, apagados = vigilante(conectados, reloj)
    v.tic()

    conectados[0] = 0
    reloj.avanzar(2)
    v.tic()
    reloj.avanzar(2)
    v.tic()

    conectados[0] = 1  # el navegador vuelve
    reloj.avanzar(2)
    assert v.tic() is False

    conectados[0] = 0  # y ahora si se va del todo
    v.tic()
    reloj.avanzar(200)
    assert v.tic() is True
    assert apagados == [True]


def test_la_cuenta_atras_se_reinicia_entera_al_volver_alguien():
    # No basta con no apagar mientras hay alguien: al irse otra vez tiene que
    # volver a contar desde cero, no reanudar lo que llevaba.
    reloj = Reloj()
    conectados = [1]
    v, apagados = vigilante(conectados, reloj)
    v.tic()

    conectados[0] = 0
    v.tic()
    reloj.avanzar(85)  # casi vencido
    v.tic()

    conectados[0] = 1
    v.tic()
    conectados[0] = 0
    v.tic()
    reloj.avanzar(85)  # otros 85: en total 170, pero seguidos solo 85
    assert v.tic() is False
    assert apagados == []


def test_si_streamlit_cambia_por_dentro_se_desactiva_en_vez_de_apagar():
    # Contar sesiones toca un atributo privado de Streamlit. Si desaparece, lo
    # unico inaceptable seria cerrar el programa por sorpresa mientras alguien
    # lo esta usando: ante la duda, no se apaga nada.
    def explota() -> int:
        raise AttributeError("_session_mgr")

    apagados: list[bool] = []
    v = Vigilante(contar=explota, apagar=lambda: apagados.append(True))
    assert v.tic() is False
    assert v.averiado is True
    assert apagados == []

    # Y no lo vuelve a intentar en cada vuelta del bucle.
    llamadas = []

    def cuenta() -> int:
        llamadas.append(1)
        return 0

    v.contar = cuenta
    v.tic()
    assert llamadas == []


# --- El interruptor del lanzador --------------------------------------------


def test_el_autoapagado_solo_se_activa_si_lo_pide_el_lanzador():
    # Arrancar a mano con `streamlit run app.py` --desarrollo, pruebas-- tiene
    # que seguir comportandose como siempre.
    assert apagado.activo({}) is False
    assert apagado.activo({apagado.VARIABLE: "0"}) is False
    assert apagado.activo({apagado.VARIABLE: ""}) is False
    for si in ("1", "true", "TRUE", "si", "sí", " 1 "):
        assert apagado.activo({apagado.VARIABLE: si}) is True, si


def test_vigilar_no_arranca_ningun_hilo_si_no_toca(monkeypatch):
    monkeypatch.delenv(apagado.VARIABLE, raising=False)
    assert apagado.vigilar() is None


def test_vigilar_arranca_el_hilo_cuando_toca(monkeypatch):
    import threading

    monkeypatch.setenv(apagado.VARIABLE, "1")
    antes = {h.name for h in threading.enumerate()}
    v = apagado.vigilar(intervalo=0.01, espera=0.01, contar=lambda: 1,
                        apagar=lambda: None)
    try:
        assert v is not None
        hilos = {h.name for h in threading.enumerate()} - antes
        assert "mpp-autoapagado" in hilos
    finally:
        # Sin esto, el hilo sigue dando vueltas el resto de la sesion de pytest
        # y contamina lo que venga detras. Es lo que paso: tumbo un test de
        # `fundamentals` que comprueba, con un mock global de time.sleep, que
        # la descarga no se duerme entre tickers.
        v.parar()

    for _ in range(100):
        if "mpp-autoapagado" not in {h.name for h in threading.enumerate()}:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("el hilo de vigilancia no se detuvo")


# --- Cerrar de verdad --------------------------------------------------------


def falso_runtime(monkeypatch, al_parar):
    """Sustituye Runtime.instance() por algo que registra la llamada a stop()."""
    from streamlit.runtime import Runtime

    class Falso:
        def stop(self):
            al_parar()

    monkeypatch.setattr(Runtime, "instance", classmethod(lambda cls: Falso()))


def test_detener_pide_el_cierre_ordenado_y_ademas_se_asegura(monkeypatch):
    # Runtime.stop() para el runtime pero NO termina el proceso: el servidor
    # HTTP se queda agarrado al puerto respondiendo 503. Sin la salida forzada,
    # cada apagado automatico dejaba un zombi y el arranque siguiente no podia
    # enlazar el puerto -- que es como el programa dejo de abrirse desde el
    # acceso directo el 2026-09-01.
    llamadas = []
    falso_runtime(monkeypatch, lambda: llamadas.append("stop"))

    salidas = []
    apagado.detener(gracia=0, salir=salidas.append)

    assert llamadas == ["stop"]
    assert salidas == [0]


def test_detener_sale_igual_aunque_no_pueda_pedir_el_cierre(monkeypatch):
    # Si ni siquiera se puede pedir el cierre, forzarlo es mas necesario, no
    # menos: lo unico que no puede quedar es el proceso ocupando el puerto.
    from streamlit.runtime import Runtime

    def explota(cls):
        raise RuntimeError("no hay runtime")

    monkeypatch.setattr(Runtime, "instance", classmethod(explota))

    salidas = []
    apagado.detener(gracia=0, salir=salidas.append)
    assert salidas == [0]


def test_detener_espera_antes_de_forzar(monkeypatch):
    # La gracia no es decorativa: es lo que le da tiempo a stop() a cerrar las
    # sesiones abiertas antes de que el proceso desaparezca de golpe.
    falso_runtime(monkeypatch, lambda: None)
    salidas = []
    inicio = time.monotonic()
    apagado.detener(gracia=0.2, salir=salidas.append)
    assert time.monotonic() - inicio >= 0.2
    assert salidas == [0]
