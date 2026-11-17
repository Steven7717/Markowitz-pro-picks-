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

from analizador import archivo as archivo_analizador
from analizador import ia_mdna, ia_tesis, ia_valoracion, informe_anual, sesion
from analizador import valorar as v
from analizador.analisis import Analisis
from analizador.referencia import Frescura
from analizador.resolver import MAX_TICKERS
from aprobacion.carga import ContratoRoto, FaltanFichas
from noticias.agenda import Evento
from noticias.texto import plano as texto_plano
from ranking import llm
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


# --- La pestaña IA ------------------------------------------------------------------

BOTONES_IA = {
    "Redactar la tesis y los riesgos", "Volver a redactar la tesis",
    "Contrastar con la empresa", "Volver a contrastar",
    "Explicar la valoración", "Volver a explicar la valoración",
}
FUENTE_IA = archivo_analizador.Fuente("10-K", "2026-10-09", "0000723125-26-000023", "Item 1A", False)
CUANDO_IA = datetime(2026, 11, 15, 10, 30)
INFORME = informe_anual.Informe(
    "MU", "10-K", "2026-10-09", "0000723125-26-000023",
    informe_anual.Seccion("Item 1A", "Los riesgos.", 12, False),
    informe_anual.Seccion("Item 7", "El informe de gestión.", 22, False),
)


def _con_clave(monkeypatch):
    monkeypatch.setattr("interprete.cliente.hay_clave", lambda: True)


def _con_informe(monkeypatch, informe=INFORME, motivo="ok"):
    monkeypatch.setattr("analizador.informe_anual.formulario_de", lambda ticker: "10-K")
    monkeypatch.setattr("analizador.informe_anual.cargar", lambda ticker, formulario: (informe, motivo))
    monkeypatch.setattr("analizador.informe_anual.ultimo_presentado", lambda ticker, formulario: None)


def _etiquetas(at) -> set:
    return {b.label for b in at.button}


def test_la_pestana_ia_existe_y_sin_clave_no_ofrece_gastar(pantalla):
    pantalla.run()
    assert not pantalla.exception
    assert "IA" in [pestana.label for pestana in pantalla.tabs]
    assert "Falta la clave de Anthropic" in _textos(pantalla)
    assert not (_etiquetas(pantalla) & BOTONES_IA)


def test_con_clave_se_ofrecen_los_tres_botones_y_ninguno_llama_solo(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    llamadas = []
    monkeypatch.setattr("analizador.ia_valoracion.explicar", lambda *a, **k: llamadas.append("valoracion"))
    monkeypatch.setattr("analizador.ia_mdna.contrastar", lambda *a, **k: llamadas.append("mdna"))
    monkeypatch.setattr("analizador.ia_tesis.redactar", lambda *a, **k: llamadas.append("tesis"))
    pantalla.run()
    assert {"Redactar la tesis y los riesgos", "Contrastar con la empresa", "Explicar la valoración"} <= _etiquetas(pantalla)
    assert llamadas == []


def _explicacion_hecha():
    return ia_valoracion.Explicacion(
        ia_valoracion.HECHA,
        (ia_valoracion.Observacion("flujos", "Depende de que el crecimiento se sostenga.", False),),
        "Las tres lecturas miran cosas distintas.",
        entrada_tokens=900,
        salida_tokens=300,
    )


def test_explicar_pide_confirmacion_y_solo_entonces_llama_y_guarda(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    llamadas = []

    def explicar(bloque, mapa, **_resto):
        llamadas.append(bloque)
        return _explicacion_hecha()

    monkeypatch.setattr("analizador.ia_valoracion.explicar", explicar)
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    assert llamadas == []
    assert "Esto cuesta dinero" in _textos(pantalla)
    _pulsar(pantalla, "Sí, leer con IA")
    assert len(llamadas) == 1
    assert "Depende de que el crecimiento se sostenga." in _textos(pantalla)
    assert "Esta lectura costó" in _textos(pantalla)
    guardadas = archivo_analizador.cargar(tmp_path / "MU.json").valoracion
    assert len(guardadas) == 1 and guardadas[0].observaciones[0][0] == "flujos"
    # Al volver a abrir se pinta lo guardado, sin llamar.
    pantalla.run()
    assert len(llamadas) == 1
    assert "Depende de que el crecimiento se sostenga." in _textos(pantalla)
    assert "Volver a explicar la valoración" in _etiquetas(pantalla)


def test_el_modelo_no_ve_ni_un_digito_de_la_valoracion(pantalla, monkeypatch):
    from ranking.verificacion import sin_digitos

    _con_clave(monkeypatch)
    vistos = []

    def explicar(bloque, mapa, **_resto):
        vistos.append(bloque)
        return _explicacion_hecha()

    monkeypatch.setattr("analizador.ia_valoracion.explicar", explicar)
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Sí, leer con IA")
    assert vistos and sin_digitos(vistos[0])
    assert vistos[0].startswith("Empresa del sector ") and "MU" not in vistos[0]


def test_un_fallo_no_guarda_nada_ni_deja_el_gasto_a_un_clic(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    llamadas = []

    def explicar(bloque, mapa, **_resto):
        llamadas.append(bloque)
        return ia_valoracion.Explicacion(ia_valoracion.FALLO, problema="La API no respondio")

    monkeypatch.setattr("analizador.ia_valoracion.explicar", explicar)
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Sí, leer con IA")
    assert "No se pudo explicar la valoración" in _textos(pantalla)
    assert not (tmp_path / "MU.json").exists()
    pantalla.run()
    assert "Sí, leer con IA" not in _etiquetas(pantalla)
    assert len(llamadas) == 1


def test_cancelar_no_llama(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    llamadas = []
    monkeypatch.setattr("analizador.ia_valoracion.explicar", lambda *a, **k: llamadas.append(1))
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Cancelar")
    assert llamadas == [] and "Sí, leer con IA" not in _etiquetas(pantalla)


def test_una_explicacion_con_otros_votos_se_pinta_como_de_entonces(pantalla, tmp_path):
    vieja = archivo_analizador.Explicacion(
        CUANDO_IA, "claude-sonnet-5", "n1",
        (("flujos", "cara"), ("sin_crecimiento", "cara"), ("pares", "cara")),
        "sobrevalorada", (), (("flujos", "Estaba cara.", False),), "",
    )
    archivo_analizador.anotar_explicacion(tmp_path / "MU.json", vieja)
    pantalla.run()
    assert "con los números de entonces" in _textos(pantalla)
    assert "Estaba cara." in _textos(pantalla)


def test_una_observacion_que_recomienda_sale_marcada(pantalla, tmp_path):
    hoy = pantalla.session_state[sesion.CLAVE_ANALISIS]["MU"].valoracion
    marcada = archivo_analizador.Explicacion(
        CUANDO_IA, "claude-sonnet-5", "n1", archivo_analizador.votos_de(hoy), hoy.get("veredicto"),
        (), (("pares", "Conviene comprar.", True),), "",
    )
    archivo_analizador.anotar_explicacion(tmp_path / "MU.json", marcada)
    pantalla.run()
    assert "suena a recomendación" in _textos(pantalla)
    assert "con los números de entonces" not in _textos(pantalla)


def _redaccion(verificada=True):
    narrativa = {
        "tesis": "Vende memoria.",
        "riesgos": [{"afirmacion": "Depende de pocos clientes.", "cita": "a small number of customers", "verificada": verificada}],
    }
    return ia_tesis.Redaccion(narrativa, False, llm.Gasto(1, 24_000, 400))


def test_la_tesis_se_redacta_tras_confirmar_y_queda_guardada_con_su_documento(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    vistos = []

    def redactar(contexto, riesgos, **_resto):
        vistos.append((contexto, riesgos))
        return _redaccion(verificada=False)

    monkeypatch.setattr("analizador.ia_tesis.redactar", redactar)
    pantalla.run()
    _pulsar(pantalla, "Redactar la tesis y los riesgos")
    assert vistos == []
    _pulsar(pantalla, "Sí, leer con IA")
    assert vistos == [("Empresa: MU, sector Information Technology.\nNo hay comparación con sus pares del sector.", "Los riesgos.")]
    textos = _textos(pantalla)
    assert "Vende memoria." in textos and "Cita SIN VERIFICAR" in textos
    assert texto_plano("del 10-K presentado el 2026-10-09") in textos
    guardada = archivo_analizador.cargar(tmp_path / "MU.json").tesis[0]
    assert guardada.fuente.accession == "0000723125-26-000023" and guardada.riesgos[0][2] is False


def test_sin_factores_de_riesgo_no_se_llama_y_se_dice_que_no_se_gasto(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch, replace(INFORME, riesgos=None))
    llamadas = []
    monkeypatch.setattr("analizador.ia_tesis.redactar", lambda *a, **k: llamadas.append(1))
    pantalla.run()
    _pulsar(pantalla, "Redactar la tesis y los riesgos")
    _pulsar(pantalla, "Sí, leer con IA")
    assert llamadas == []
    assert "no trae sus factores de riesgo" in _textos(pantalla)


def test_un_informe_que_no_se_pudo_traer_no_gasta(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch, None, "sin_red_edgar")
    llamadas = []
    monkeypatch.setattr("analizador.ia_tesis.redactar", lambda *a, **k: llamadas.append(1))
    pantalla.run()
    _pulsar(pantalla, "Redactar la tesis y los riesgos")
    _pulsar(pantalla, "Sí, leer con IA")
    assert llamadas == [] and "no se pudo consultar la SEC" in _textos(pantalla)


def test_el_contraste_pinta_la_postura_y_marca_la_cita_sin_verificar(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    vistos = []

    def contrastar(ticker, supuesto, documento, **_resto):
        vistos.append((ticker, supuesto, documento))
        return ia_mdna.Contraste(
            ia_mdna.HECHA,
            (ia_mdna.Juicio("La dirección espera más demanda.", "contradice", "we expect demand to grow", False),),
            entrada_tokens=18_000,
            salida_tokens=500,
        )

    monkeypatch.setattr("analizador.ia_mdna.contrastar", contrastar)
    pantalla.run()
    _pulsar(pantalla, "Contrastar con la empresa")
    _pulsar(pantalla, "Sí, leer con IA")
    assert vistos[0][0] == "MU" and vistos[0][2] == "El informe de gestión."
    assert vistos[0][1].startswith("El escenario base supone")
    textos = _textos(pantalla)
    assert "Contradice el escenario base" in textos and "Cita SIN VERIFICAR" in textos
    assert archivo_analizador.cargar(tmp_path / "MU.json").mdna[0].supuesto == vistos[0][1]


def test_un_mdna_que_no_se_localiza_no_se_sustituye_por_otra_seccion(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch, replace(INFORME, mdna=None))
    llamadas = []
    monkeypatch.setattr("analizador.ia_mdna.contrastar", lambda *a, **k: llamadas.append(1))
    pantalla.run()
    _pulsar(pantalla, "Contrastar con la empresa")
    _pulsar(pantalla, "Sí, leer con IA")
    assert llamadas == []
    assert "No se localizó el informe de gestión" in _textos(pantalla)


def test_lo_ya_leido_se_pinta_sin_clave_y_avisa_de_un_informe_mas_nuevo(pantalla, monkeypatch, tmp_path):
    tesis = archivo_analizador.Tesis(
        CUANDO_IA, "claude-sonnet-5", "b3", FUENTE_IA, "Vende memoria.",
        (("Depende de pocos clientes.", "a small number of customers", True),),
    )
    archivo_analizador.anotar_tesis(tmp_path / "MU.json", tesis)
    monkeypatch.setattr(
        "analizador.informe_anual.ultimo_presentado", lambda ticker, formulario: ("0000723125-27-000001", "2027-10-08")
    )
    pantalla.run()
    textos = _textos(pantalla)
    assert "Vende memoria." in textos
    assert "Hay un 10-K más reciente" in textos
    assert not (_etiquetas(pantalla) & BOTONES_IA)


def test_un_archivo_ilegible_se_dice_no_se_toca_y_no_ofrece_leer(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    (tmp_path / "MU.json").write_text("{", encoding="utf-8")
    pantalla.run()
    assert not pantalla.exception
    assert "no se ha tocado" in _textos(pantalla)
    assert not (_etiquetas(pantalla) & BOTONES_IA)
    assert (tmp_path / "MU.json").read_text(encoding="utf-8") == "{"


def test_una_empresa_fuera_de_la_sec_solo_tiene_la_explicacion(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    pantalla.session_state[sesion.CLAVE_ANALISIS] = {"MU": replace(_analisis("MU"), clase="sin_sec")}
    pantalla.run()
    assert not pantalla.exception
    assert "no hay documento" in _textos(pantalla)
    etiquetas = _etiquetas(pantalla)
    assert "Explicar la valoración" in etiquetas
    assert "Redactar la tesis y los riesgos" not in etiquetas and "Contrastar con la empresa" not in etiquetas


def test_una_explicacion_recien_pagada_con_deslizadores_movidos_no_sale_como_de_entonces(pantalla, monkeypatch):
    """Se compara con la valoración que había en pantalla al explicar, no con la del programa."""
    _con_clave(monkeypatch)
    monkeypatch.setattr("analizador.ia_valoracion.explicar", lambda bloque, mapa, **_resto: _explicacion_hecha())
    analisis = pantalla.session_state[sesion.CLAVE_ANALISIS]["MU"]
    pantalla.session_state[sesion.clave_deslizador("MU", "beta")] = 2.6
    # El antecedente del test: con la beta movida los votos cambian de verdad.
    movida, movidos = sesion.valoracion_en_pantalla({sesion.clave_deslizador("MU", "beta"): 2.6}, analisis)
    assert movidos and archivo_analizador.votos_de(movida) != archivo_analizador.votos_de(analisis.valoracion)
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Sí, leer con IA")
    textos = _textos(pantalla)
    assert "Se explicó con tus supuestos" in textos
    assert "con los números de entonces" not in textos


def test_si_el_guardado_lanza_valueerror_la_lectura_pagada_se_ve_igual(pantalla, monkeypatch):
    _con_clave(monkeypatch)
    monkeypatch.setattr("analizador.ia_valoracion.explicar", lambda bloque, mapa, **_resto: _explicacion_hecha())

    def anotar(ruta, explicacion):
        raise ValueError("la entrada no se podría leer después")

    monkeypatch.setattr("analizador.archivo.anotar_explicacion", anotar)
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Sí, leer con IA")
    assert not pantalla.exception
    textos = _textos(pantalla)
    assert "No se pudo guardar la lectura" in textos and "no se podría leer después" in textos
    assert "Depende de que el crecimiento se sostenga." in textos


def test_tras_un_fallo_con_tokens_gastados_se_dice_lo_que_costo(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    monkeypatch.setattr(
        "analizador.ia_valoracion.explicar",
        lambda bloque, mapa, **_resto: ia_valoracion.Explicacion(
            ia_valoracion.FALLO, entrada_tokens=1_200, salida_tokens=300, problema="Se cortó la respuesta"
        ),
    )
    monkeypatch.setattr(
        "analizador.ia_mdna.contrastar",
        lambda ticker, supuesto, documento, **_resto: ia_mdna.Contraste(
            ia_mdna.FALLO, entrada_tokens=40_000, salida_tokens=900, problema="Se cortó la respuesta"
        ),
    )
    pantalla.run()
    _pulsar(pantalla, "Explicar la valoración")
    _pulsar(pantalla, "Sí, leer con IA")
    textos = _textos(pantalla)
    assert "No se pudo explicar la valoración" in textos and "1,200 tokens de entrada" in textos
    _pulsar(pantalla, "Contrastar con la empresa")
    _pulsar(pantalla, "Sí, leer con IA")
    assert "No se pudo contrastar" in _textos(pantalla) and "40,000 tokens de entrada" in _textos(pantalla)
    assert not (tmp_path / "MU.json").exists()


@pytest.mark.parametrize(
    "modulo, funcion, boton, resultado, dicho",
    [
        ("ia_valoracion", "explicar", "Explicar la valoración", ia_valoracion.Explicacion(ia_valoracion.SIN_VALORACION), "Sin valoración"),
        ("ia_valoracion", "explicar", "Explicar la valoración", ia_valoracion.Explicacion(ia_valoracion.SIN_CLAVE), "Falta la clave"),
        ("ia_mdna", "contrastar", "Contrastar con la empresa", ia_mdna.Contraste(ia_mdna.SIN_DOCUMENTO), "No había informe de gestión"),
        ("ia_mdna", "contrastar", "Contrastar con la empresa", ia_mdna.Contraste(ia_mdna.SIN_CLAVE), "Falta la clave"),
    ],
)
def test_un_estado_que_no_es_un_fallo_de_llamada_no_dice_que_la_llamada_fallo(
    pantalla, monkeypatch, modulo, funcion, boton, resultado, dicho
):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    monkeypatch.setattr(f"analizador.{modulo}.{funcion}", lambda *a, **k: resultado)
    pantalla.run()
    _pulsar(pantalla, boton)
    _pulsar(pantalla, "Sí, leer con IA")
    textos = _textos(pantalla)
    assert dicho in textos and "No se ha gastado nada" in textos
    assert "la llamada no devolvió nada utilizable" not in textos


def _pagar_y_confirmar(pantalla, boton):
    _pulsar(pantalla, boton)
    _pulsar(pantalla, "Sí, leer con IA")


def test_una_explicacion_sin_nada_utilizable_no_se_guarda_ni_tapa_la_anterior(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    hoy = pantalla.session_state[sesion.CLAVE_ANALISIS]["MU"].valoracion
    buena = archivo_analizador.Explicacion(
        CUANDO_IA, "claude-sonnet-5", "n1", archivo_analizador.votos_de(hoy), hoy.get("veredicto"),
        (), (("flujos", "La buena de antes.", False),), "",
    )
    archivo_analizador.anotar_explicacion(tmp_path / "MU.json", buena)
    vacia = ia_valoracion.Explicacion(
        ia_valoracion.HECHA, descartadas=2, entrada_tokens=900, salida_tokens=300
    )
    monkeypatch.setattr("analizador.ia_valoracion.explicar", lambda bloque, mapa, **_resto: vacia)
    pantalla.run()
    _pagar_y_confirmar(pantalla, "Volver a explicar la valoración")
    textos = _textos(pantalla)
    assert "no quedó nada utilizable" in textos and "2 observaciones" in textos
    assert "Esta lectura costó" in textos and "La buena de antes." in textos
    assert len(archivo_analizador.cargar(tmp_path / "MU.json").valoracion) == 1


def test_un_contraste_sin_juicios_porque_se_descartaron_no_se_guarda(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    descartado = ia_mdna.Contraste(ia_mdna.HECHA, (), descartados=3, entrada_tokens=18_000, salida_tokens=400)
    monkeypatch.setattr("analizador.ia_mdna.contrastar", lambda ticker, supuesto, documento, **_resto: descartado)
    pantalla.run()
    _pagar_y_confirmar(pantalla, "Contrastar con la empresa")
    textos = _textos(pantalla)
    assert "3 juicios" in textos and "se descartaron" in textos and "Esta lectura costó" in textos
    assert "no salió nada que decir" not in textos
    assert not (tmp_path / "MU.json").exists()


def test_un_contraste_sin_juicios_y_sin_descartes_si_se_guarda_como_no_hay_nada_que_decir(pantalla, monkeypatch, tmp_path):
    _con_clave(monkeypatch)
    _con_informe(monkeypatch)
    limpio = ia_mdna.Contraste(ia_mdna.HECHA, (), descartados=0, entrada_tokens=18_000, salida_tokens=100)
    monkeypatch.setattr("analizador.ia_mdna.contrastar", lambda ticker, supuesto, documento, **_resto: limpio)
    pantalla.run()
    _pagar_y_confirmar(pantalla, "Contrastar con la empresa")
    assert "no salió nada que decir" in _textos(pantalla)
    assert len(archivo_analizador.cargar(tmp_path / "MU.json").mdna) == 1
