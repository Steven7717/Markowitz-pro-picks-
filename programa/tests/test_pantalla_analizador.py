"""La pantalla del Analizador, ejecutada de verdad con `AppTest` y sin red.

`test_vistas_analizador.py` lee la fuente con `ast`: comprueba que la pantalla
usa la lógica y no la rehace, pero no ve lo que pasa entre dos pasadas ni lo
que acaba escrito. Aquí se ejecuta el guion entero con dobles en todo lo que
toca la red o el disco, y se mira lo que sale.

Los dobles se ponen en los módulos, no en la pantalla: el guion se vuelve a
ejecutar en cada pasada y vuelve a importar de ellos.
"""

from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from analizador import sesion
from analizador import valorar as v
from analizador.analisis import Analisis
from analizador.referencia import Frescura
from tests.test_analizador_valorar import _entradas
from tests.test_medidores_analizador import identidad

GUION = str(Path(__file__).resolve().parent / "guion_analizador.py")
HORA_PANEL = datetime(2026, 10, 20, 9, 0)


def _analisis(ticker="MU", pilar=None, **entradas) -> Analisis:
    """Una empresa de la SEC sin ficha (no hay panel), con su valoración de verdad."""
    traidas = _entradas(ticker=ticker, **entradas)
    return Analisis(
        ticker, "sec", identidad(ticker), None, "Information Technology", "sp500",
        None, "sin_panel", traidas, v.valorar(traidas, pilar),
    )


class _Disponibilidad:
    puede_generar = False
    motivo_generacion = "Falta el correo para EDGAR."


@pytest.fixture
def pantalla(monkeypatch, tmp_path):
    """La pantalla con MU ya analizada, y `mundo` para cambiar lo que responden los dobles."""
    mundo = {
        "analizar": lambda ticker, panel, tabla=None: _analisis(ticker),
        "con_precio_nuevo": lambda anterior, panel, tabla=None: anterior,
        "traer": lambda fuente, ticker, descargar, forzar: ((), "", datetime(2026, 11, 1, 12, 0).astimezone(), True),
        "hora_panel": HORA_PANEL,
    }
    monkeypatch.setattr("analizador.referencia.cargar_panel", lambda *a: (None, None))
    monkeypatch.setattr("analizador.referencia.frescura", lambda *a: Frescura(mundo["hora_panel"], None))
    monkeypatch.setattr("aprobacion.generacion.disponibilidad", lambda *a: _Disponibilidad())
    monkeypatch.setattr("analizador.analisis.analizar", lambda *a: mundo["analizar"](*a))
    monkeypatch.setattr("analizador.analisis.con_precio_nuevo", lambda *a: mundo["con_precio_nuevo"](*a))
    monkeypatch.setattr("noticias.traer.traer", lambda *a: mundo["traer"](*a))
    monkeypatch.setattr("vistas.libros.disponibles", lambda: ([], {}))
    monkeypatch.setattr("analizador.archivo.DIRECTORIO", tmp_path)
    monkeypatch.setattr("interprete.cliente.hay_clave", lambda: False)
    at = AppTest.from_file(GUION, default_timeout=30)
    at.session_state[sesion.CLAVE_TEXTO] = "MU"
    at.session_state[sesion.CLAVE_TICKERS] = ["MU"]
    at.session_state[sesion.CLAVE_ANALISIS] = {"MU": _analisis("MU")}
    at.session_state[sesion.CLAVE_HORA_PANEL] = HORA_PANEL
    at.mundo = mundo
    return at


def _textos(at) -> str:
    """Todo lo escrito en la pantalla, para buscar una frase sin saber en qué widget va."""
    partes = []
    for clase in ("markdown", "caption", "warning", "error", "info", "success"):
        partes += [e.value for e in getattr(at, clase)]
    return "\n".join(partes)


def test_la_pantalla_se_pinta_entera_sin_red(pantalla):
    pantalla.run()
    assert not pantalla.exception
    assert "MU · Micron Technology, Inc." in _textos(pantalla)


# --- El motivo ya redactado sigue a la valoración -------------------------------


def _pulsar(at, etiqueta: str):
    next(b for b in at.button if b.label == etiqueta).click().run()
    assert not at.exception


def _volver_a_analizar_con_otro_panel(at):
    """El panel se rehízo en otra pantalla: «Analizar» rehace la ficha en esta misma pasada.

    Es el camino en que el campo del motivo sobrevive: se dibuja en la pasada
    que rehace el análisis, y Streamlit no tira su clave.
    """
    at.mundo["hora_panel"] = datetime(2026, 11, 9, 18, 0)
    at.mundo["analizar"] = lambda ticker, *a: _analisis(ticker, pilar=-0.6)
    _pulsar(at, "Analizar")


def test_al_rehacer_el_analisis_el_motivo_sin_tocar_dice_el_veredicto_nuevo(pantalla):
    # Con un `setdefault` a secas, al acta llegaba la valoración nueva con el
    # motivo de la de antes.
    pantalla.run()
    clave = sesion.clave_motivo("MU")
    assert "infravalorada" in pantalla.text_area(key=clave).value
    _volver_a_analizar_con_otro_panel(pantalla)
    assert "señales mixtas" in pantalla.text_area(key=clave).value
    assert "infravalorada" not in pantalla.text_area(key=clave).value
    assert "La valoración cambió desde que escribiste el motivo" not in _textos(pantalla)


def test_al_rehacer_el_analisis_el_motivo_editado_se_conserva_y_se_avisa(pantalla):
    pantalla.run()
    clave = sesion.clave_motivo("MU")
    pantalla.text_area(key=clave).set_value("Me gusta su caja.")
    _volver_a_analizar_con_otro_panel(pantalla)
    assert pantalla.text_area(key=clave).value == "Me gusta su caja."
    aviso = next(w.value for w in pantalla.warning if "escribiste el motivo" in w.value)
    assert "señales mixtas" in aviso


def test_tras_actualizar_precios_el_motivo_dice_el_veredicto_nuevo(pantalla):
    # «Actualizar precios» termina en `st.rerun()` antes de dibujar el detalle,
    # y Streamlit tira la clave del campo: tiene que volver a nacer, y con la
    # valoración nueva.
    pantalla.run()
    pantalla.mundo["con_precio_nuevo"] = lambda anterior, *a: _analisis("MU", pilar=-0.6)
    _pulsar(pantalla, "Actualizar precios")
    assert "señales mixtas" in pantalla.text_area(key=sesion.clave_motivo("MU")).value
