"""La pantalla del Analizador, ejecutada de verdad con `AppTest` y sin red.

`test_vistas_analizador.py` lee la fuente con `ast`: comprueba que la pantalla
usa la lógica y no la rehace, pero no ve lo que pasa entre dos pasadas ni lo
que acaba escrito. Aquí se ejecuta el guion entero con dobles en todo lo que
toca la red o el disco, y se mira lo que sale.

Los dobles se ponen en los módulos, no en la pantalla: el guion se vuelve a
ejecutar en cada pasada y vuelve a importar de ellos.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from analizador import sesion
from analizador import valorar as v
from analizador.analisis import Analisis
from analizador.referencia import Frescura
from analizador.resolver import MAX_TICKERS
from aprobacion.carga import ContratoRoto, FaltanFichas
from noticias.agenda import Evento
from tests.test_analizador_valorar import _entradas
from tests.test_medidores_analizador import identidad

GUION = str(Path(__file__).resolve().parent / "guion_analizador.py")
HORA_PANEL = datetime(2026, 10, 20, 9, 0)
TRAIDO = datetime(2026, 11, 1, 12, 0).astimezone()


def _analisis(ticker="MU", pilar=None, **entradas) -> Analisis:
    """Una empresa de la SEC sin ficha (no hay panel), con su valoración de verdad."""
    traidas = _entradas(ticker=ticker, **entradas)
    return Analisis(
        ticker, "sec", identidad(ticker), None, "Information Technology", "sp500",
        None, "sin_panel", traidas, v.valorar(traidas, pilar),
    )


def _disponibilidad(puede_generar: bool):
    return SimpleNamespace(puede_generar=puede_generar, motivo_generacion="Falta el correo para EDGAR.")


@pytest.fixture
def pantalla(monkeypatch, tmp_path):
    """La pantalla con MU ya analizada, y `mundo` para cambiar lo que responden los dobles."""
    mundo = {
        "analizar": lambda ticker, panel, tabla=None: _analisis(ticker),
        "con_precio_nuevo": lambda anterior, panel, tabla=None: anterior,
        "traer": lambda fuente, ticker, descargar, forzar: ((), "", TRAIDO, True),
        "hora_panel": HORA_PANEL,
        "puede_generar": False,
        "construir_panel": lambda: None,
        "candidatos": lambda: SimpleNamespace(fichas=[]),
    }
    monkeypatch.setattr("analizador.referencia.cargar_panel", lambda *a: (None, None))
    monkeypatch.setattr("analizador.referencia.frescura", lambda *a: Frescura(mundo["hora_panel"], None))
    monkeypatch.setattr("aprobacion.generacion.disponibilidad", lambda *a: _disponibilidad(mundo["puede_generar"]))
    monkeypatch.setattr("analizador.referencia.construir_panel", lambda *a: mundo["construir_panel"]())
    monkeypatch.setattr("aprobacion.carga.cargar_candidatos", lambda *a: mundo["candidatos"]())
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


# --- El ticker elegido en el detalle sobrevive a las pasadas -------------------


def _con_dos_tickers(at):
    at.session_state[sesion.CLAVE_TEXTO] = "MU SPY"
    at.session_state[sesion.CLAVE_TICKERS] = ["MU", "SPY"]
    at.session_state[sesion.CLAVE_ANALISIS] = {"MU": _analisis("MU"), "SPY": _analisis("SPY")}
    at.run()
    at.selectbox(key=sesion.CLAVE_ELEGIDO).set_value("SPY").run()
    assert not at.exception
    assert at.selectbox(key=sesion.CLAVE_ELEGIDO).value == "SPY"


def test_actualizar_precios_no_devuelve_el_detalle_al_primero(pantalla):
    # Recorrido de la app real: con SPY en el detalle, «Actualizar precios»
    # volvía a MU. El botón acaba en `st.rerun()` antes de dibujar el
    # desplegable, y Streamlit tira la clave del widget que no se dibujó.
    _con_dos_tickers(pantalla)
    _pulsar(pantalla, "Actualizar precios")
    assert pantalla.selectbox(key=sesion.CLAVE_ELEGIDO).value == "SPY"


def test_el_detalle_elegido_sigue_aunque_cambie_el_nombre(pantalla):
    # El rótulo del desplegable lleva el nombre, que sale de la identidad que
    # trae «Actualizar precios»: no puede contar como otro desplegable.
    _con_dos_tickers(pantalla)
    pantalla.mundo["con_precio_nuevo"] = lambda anterior, *a: replace(
        anterior, identidad=replace(anterior.identidad, nombre=anterior.identidad.nombre + " (nuevo)")
    )
    _pulsar(pantalla, "Actualizar precios")
    assert pantalla.selectbox(key=sesion.CLAVE_ELEGIDO).value == "SPY"


# --- Un supuesto imposible no enseña la clave interna ---------------------------


def test_un_deslizador_imposible_se_dice_en_palabras(pantalla):
    # Decía «Con esos supuestos no hay valoración posible: k_e: con esos
    # supuestos el coste del capital propio sale -25.52%…».
    pantalla.run()
    pantalla.slider(key=sesion.clave_deslizador("MU", "beta")).set_value(-1.0)
    pantalla.slider(key=sesion.clave_deslizador("MU", "r_f")).set_value(0.0).run()
    assert not pantalla.exception
    (error,) = [e.value for e in pantalla.error]
    assert error.startswith(
        "Con esos supuestos no hay valoración posible: el coste del capital propio sale −"
    )
    assert "k_e" not in error and error.count("on esos supuestos") == 1


def test_una_tasa_a_mano_imposible_se_dice_en_palabras(pantalla):
    sin_tasa = _analisis("MU", r_f=None, procedencia_r_f=None, motivo_r_f="sin_token")
    pantalla.session_state[sesion.CLAVE_ANALISIS] = {"MU": sin_tasa}
    pantalla.run()
    pantalla.number_input(key=sesion.clave_a_mano("MU")).set_value(-5.0).run()
    assert not pantalla.exception
    (error,) = [e.value for e in pantalla.error]
    assert error.startswith("Esa tasa no se puede usar: el coste del capital propio sale −")
    assert "k_e" not in error and "con esos supuestos" not in error


# --- Sin 8-K: se miró y no había, o no se pudo mirar ----------------------------


def test_sin_8k_y_con_la_sec_consultada_se_dice_que_se_miro(pantalla):
    pantalla.run()
    escrito = _textos(pantalla)
    assert "se miró y no había ninguno" in escrito
    assert "Ningún 8-K en la ventana consultada." in escrito


def test_si_la_consulta_de_8k_fallo_no_se_afirma_que_no_habia_ninguno(pantalla):
    def traer(fuente, ticker, descargar, forzar):
        if fuente == "hechos":
            return (), "MU: la SEC no responde", None, False
        return (), "", TRAIDO, True

    pantalla.mundo["traer"] = traer
    pantalla.run()
    assert not pantalla.exception
    escrito = _textos(pantalla)
    assert "la SEC no responde" in escrito
    assert "se miró" not in escrito and "Ningún 8-K" not in escrito
    assert "no se sabe si hay alguno" in escrito


def _prensa_caida(cuando):
    def traer(fuente, ticker, descargar, forzar):
        if fuente == "prensa":
            return (), "Yahoo no responde", cuando, False
        return (), "", TRAIDO, True

    return traer


def test_si_la_prensa_fallo_y_no_hay_nada_guardado_no_se_dice_sin_noticias(pantalla):
    # Recorrido de la app real (WALMEX.MX con Yahoo caído): salían a la vez el
    # aviso del fallo y «Sin noticias recientes.», que afirma que se miró.
    pantalla.mundo["traer"] = _prensa_caida(None)
    pantalla.run()
    assert not pantalla.exception
    escrito = _textos(pantalla)
    assert "Yahoo no responde" in escrito
    assert "Sin noticias recientes" not in escrito
    assert "no se sabe si hay noticias" in escrito


def test_si_la_prensa_fallo_con_lo_guardado_vacio_se_dice_de_cuando_es(pantalla):
    pantalla.mundo["traer"] = _prensa_caida(datetime(2026, 10, 30, 12, 0).astimezone())
    pantalla.run()
    escrito = _textos(pantalla)
    assert "Sin noticias recientes" not in escrito
    assert "del 30/10/2026, no traía ninguna noticia" in escrito


def test_si_el_calendario_fallo_no_se_dice_que_no_haya_fechas(pantalla):
    def traer(fuente, ticker, descargar, forzar):
        if fuente == "agenda":
            return (), "Yahoo no responde", None, False
        return (), "", TRAIDO, True

    pantalla.mundo["traer"] = traer
    pantalla.run()
    escrito = _textos(pantalla)
    assert "Ninguna fecha próxima" not in escrito
    assert "no se sabe si hay fechas próximas" in escrito


def test_si_el_calendario_fallo_para_uno_no_se_dice_de_todos(pantalla):
    def traer(fuente, ticker, descargar, forzar):
        if fuente == "agenda" and ticker == "SPY":
            return (), "Yahoo no responde", None, False
        return (), "", TRAIDO, True

    pantalla.mundo["traer"] = traer
    pantalla.session_state[sesion.CLAVE_TICKERS] = ["MU", "SPY"]
    pantalla.session_state[sesion.CLAVE_ANALISIS] = {"MU": _analisis("MU"), "SPY": _analisis("SPY")}
    pantalla.run()
    escrito = _textos(pantalla)
    assert "Ninguna fecha próxima para estos tickers" not in escrito
    assert "de los del aviso de arriba no se sabe" in escrito


# --- Arreglos menores de la revisión de las Tasks 11-19 --------------------------


def test_al_fallar_construir_el_panel_no_se_habla_de_un_panel_de_antes(pantalla):
    def sin_disco():
        raise OSError("disco lleno")

    pantalla.mundo["puede_generar"] = True
    pantalla.mundo["construir_panel"] = sin_disco
    pantalla.run()
    _pulsar(pantalla, "Construir el panel")
    (error,) = [e.value for e in pantalla.error]
    assert "disco lleno" in error and "Sigue sin haber panel" in error
    assert "de antes" not in error


def test_sin_precio_se_dice_que_no_lo_hay(pantalla):
    sin_precio = _analisis("MU")
    sin_precio = replace(sin_precio, identidad=replace(sin_precio.identidad, precio=None))
    pantalla.session_state[sesion.CLAVE_ANALISIS] = {"MU": sin_precio}
    pantalla.run()
    assert not pantalla.exception
    pies = [c.value for c in pantalla.caption]
    assert "Sin precio: Yahoo no dio la cotización." in pies
    assert not any("cotización del —" in pie for pie in pies)


def _resultados(dia: date) -> Evento:
    return Evento("MU", "resultados", dia, f"Resultados del {dia:%d/%m}")


def test_actualizar_noticias_repinta_lo_que_viene_y_el_proximo_evento(pantalla):
    # «Lo que viene» y la columna «Próximo evento» se pintan antes que la
    # pestaña: sin otra pasada, seguían con el calendario de antes del botón.
    lejos, cerca = date.today() + timedelta(days=40), date.today() + timedelta(days=5)
    calendario = {"agenda": (_resultados(lejos),)}

    def traer(fuente, ticker, descargar, forzar):
        if forzar:
            calendario["agenda"] = (_resultados(cerca),)
        return calendario.get(fuente, ()), "", TRAIDO, True

    pantalla.mundo["traer"] = traer
    pantalla.run()
    assert f"**MU** — Resultados del {lejos:%d/%m}" in _textos(pantalla)
    pantalla.button(key="analizador_noticias_MU").click().run()
    assert not pantalla.exception
    escrito = _textos(pantalla)
    assert f"**MU** — Resultados del {cerca:%d/%m}" in escrito
    assert f"Resultados del {lejos:%d/%m}" not in escrito
    assert f"Resultados del {cerca:%d/%m}" in pantalla.dataframe[0].value["Próximo evento"].iloc[0]


def test_si_actualizar_noticias_falla_el_aviso_sobrevive_a_la_pasada_que_repinta(pantalla):
    # Con lo guardado todavía vigente, la pasada siguiente no vuelve a pedir
    # nada: el fallo sólo lo vio la del botón, que termina en `st.rerun()`.
    def traer(fuente, ticker, descargar, forzar):
        problema = "Yahoo no responde" if forzar and fuente == "prensa" else ""
        return (), problema, TRAIDO, not problema

    def fallos():
        return [w.value for w in pantalla.warning if "no se pudo traer" in w.value]

    pantalla.mundo["traer"] = traer
    pantalla.run()
    assert not fallos()
    pantalla.button(key="analizador_noticias_MU").click().run()
    assert not pantalla.exception
    (aviso,) = fallos()
    assert aviso.startswith("**Prensa**") and "Yahoo no responde" in aviso
    # Y se dice una vez: en la pasada siguiente ya no está.
    pantalla.run()
    assert not fallos()


def test_un_libro_con_mas_activos_que_el_tope_lo_dice_antes_de_cargar(pantalla, monkeypatch):
    libro = SimpleNamespace(libro=SimpleNamespace(asientos=(), objetivo=None))
    muchos = [f"T{n}" for n in range(MAX_TICKERS + 2)]
    monkeypatch.setattr("vistas.libros.disponibles", lambda: ([libro], {"Mi libro": libro}))
    monkeypatch.setattr("vistas.libros.desplegable", lambda etiquetas, contenedor=None: libro)
    monkeypatch.setattr("seguimiento.posiciones.tickers_a_mirar", lambda asientos, objetivo: muchos)
    pantalla.run()
    assert not pantalla.exception
    (pie,) = [c.value for c in pantalla.caption if "Sólo viajan los tickers" in c.value]
    assert f"más de los {MAX_TICKERS}" in pie and "quitar 2" in pie


@pytest.mark.parametrize(
    "fallo, dicho",
    [
        (FaltanFichas("No hay candidatos."), "todavía no hay candidatos"),
        (ContratoRoto("falta `fichas`"), "no se puede leer"),
    ],
)
def test_sin_candidatos_no_se_anade_y_se_dice_por_que(pantalla, fallo, dicho):
    # Se añadía igual y se saltaba a Revisar candidatos, que sin candidatos se
    # detiene antes de enseñar los añadidos.
    def sin_candidatos():
        raise fallo

    pantalla.mundo["candidatos"] = sin_candidatos
    pantalla.run()
    assert not pantalla.exception
    assert not pantalla.text_area and "anadidos" not in pantalla.session_state
    (pie,) = [c.value for c in pantalla.caption if "Revisar candidatos" in c.value]
    assert dicho in pie


def test_con_candidatos_el_ticker_entra_en_los_anadidos_con_su_motivo(pantalla, monkeypatch):
    saltos = []
    monkeypatch.setattr("streamlit.switch_page", saltos.append)
    pantalla.run()
    pantalla.text_area(key=sesion.clave_motivo("MU")).set_value("Me gusta su caja.")
    _pulsar(pantalla, "Añadir a la revisión")
    (anadido,) = pantalla.session_state["anadidos"]
    assert (anadido.ticker, anadido.motivo) == ("MU", "Me gusta su caja.")
    assert anadido.valoracion == pantalla.session_state[sesion.CLAVE_ANALISIS]["MU"].valoracion
    assert saltos == ["vistas/candidatos.py"]


def test_uno_que_ya_esta_en_el_ranking_no_se_anade(pantalla):
    pantalla.mundo["candidatos"] = lambda: SimpleNamespace(fichas=[{"ticker": "MU"}])
    pantalla.run()
    _pulsar(pantalla, "Añadir a la revisión")
    assert "anadidos" not in pantalla.session_state or not pantalla.session_state["anadidos"]
    assert len(pantalla.error) == 1
