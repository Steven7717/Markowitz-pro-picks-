import re

import pytest

import tema

# Los ganchos de Streamlit de los que cuelga la hoja de estilo, comprobados uno
# a uno contra la aplicación en marcha (Streamlit 1.62, 2026-09-01) mirando
# cuántos elementos casaba cada selector en el DOM real.
#
# Este test no comprueba que sigan existiendo — para eso haría falta un
# navegador. Lo que hace es impedir que la lista crezca sin que nadie la mire:
# tres de los selectores originales (`stAppViewBlockContainer` y los dos de
# `data-baseweb`) no casaban con nada y el estilo simplemente no se aplicaba,
# en silencio, que es como fallan siempre estas cosas.
GANCHOS = {
    "stMetricValue",
    "stMetricLabel",
    "stMetric",
    "stDataFrame",
    "stTable",
    "stMainBlockContainer",
    "stTabs",
    "stTab",
    "stBaseButton-",
    "stExpander",
    "stSidebar",
    "stSidebarNav",
}


def test_la_hoja_solo_se_cuelga_de_ganchos_ya_comprobados():
    usados = set(re.findall(r'data-testid\^?="([^"]+)"', tema.CSS))
    nuevos = usados - GANCHOS
    assert not nuevos, (
        f"Selectores sin comprobar: {sorted(nuevos)}. Míralos en la aplicación "
        "en marcha (querySelectorAll) antes de añadirlos a GANCHOS."
    )


def test_la_hoja_no_vuelve_a_apoyarse_en_data_baseweb():
    # Ya se pudrió una vez: Streamlit dejó de montar las pestañas sobre BaseWeb
    # y los selectores se quedaron apuntando al vacío sin que nada fallara.
    #
    # Se busca la forma de selector, `[data-baseweb=`, y no el nombre suelto:
    # el comentario de la hoja que cuenta esta misma historia lo menciona, y un
    # test que prohíbe explicar por qué existe es un test que se borra.
    assert "[data-baseweb" not in tema.CSS


def test_ninguna_regla_esconde_nada():
    # La promesa que hace aceptable colgarse de los interiores de Streamlit es
    # que ninguna regla cambia lo que la aplicación hace. Un `display:none` o un
    # `position:fixed` sí podría: dejaría un botón inalcanzable, y el usuario no
    # tendría forma de saber que está ahí.
    for prohibido in ("display:none", "display: none", "visibility:hidden",
                      "position:fixed", "position: fixed"):
        assert prohibido not in tema.CSS, prohibido


def test_el_anillo_de_foco_nunca_se_quita():
    # Es la única pista de dónde está quien navega con el teclado.
    assert "outline: none" not in tema.CSS
    assert ":focus-visible" in tema.CSS


def test_se_respeta_el_movimiento_reducido():
    assert "prefers-reduced-motion" in tema.CSS


# --- Contraste ---------------------------------------------------------------


def _luminancia(color: str) -> float:
    limpio = color.lstrip("#")
    canales = []
    for i in (0, 2, 4):
        c = int(limpio[i : i + 2], 16) / 255
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canales
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(primero: str, segundo: str) -> float:
    a, b = _luminancia(primero), _luminancia(segundo)
    claro, oscuro = max(a, b), min(a, b)
    return (claro + 0.05) / (oscuro + 0.05)


@pytest.mark.parametrize(
    "nombre",
    ["TEXTO", "TEXTO_SUAVE", "TEXTO_TENUE", "VERDE", "AMBAR", "ROJO", "AZUL",
     "ACENTO", "NARANJA"],
)
def test_todo_lo_que_lleva_texto_contrasta_sobre_el_fondo(nombre):
    # WCAG AA para texto normal. Sin esto, "afinar" la paleta un poco más oscura
    # es un cambio de una línea que nadie revisa y que deja media aplicación
    # ilegible con poca luz — y los veredictos de los medidores van en estos
    # colores.
    color = getattr(tema, nombre)
    assert contraste(color, tema.FONDO) >= 4.5, (
        f"{nombre} ({color}) queda en {contraste(color, tema.FONDO):.2f}:1 "
        "sobre el fondo"
    )


def test_las_superficies_se_distinguen_del_fondo():
    # No es contraste de texto: es que una tarjeta se vea como una tarjeta. Por
    # debajo de esto el borde es lo único que la separa del fondo, y en una
    # pantalla mal calibrada desaparece.
    for nombre in ("TARJETA", "SUPERFICIE", "ELEVADA"):
        assert contraste(getattr(tema, nombre), tema.FONDO) > 1.05, nombre


# --- Los ayudantes de HTML ---------------------------------------------------


def test_la_cabecera_escapa_lo_que_le_dan():
    html = tema.cabecera("<script>alert(1)</script>", "y <b>esto</b>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;" in html


def test_una_cabecera_sin_subtitulo_no_deja_un_parrafo_vacio():
    assert "<p>" not in tema.cabecera("Solo título")


def test_un_tono_desconocido_cae_en_neutro_en_vez_de_reventar():
    # Las etiquetas se pintan en bucles sobre datos; una falta de ortografía en
    # el tono no puede dejar una pantalla entera sin dibujar.
    assert tema.etiqueta("hola", "turquesa") == tema.etiqueta("hola", "neutro")


def test_rgba_convierte_el_color_de_la_paleta():
    assert tema.rgba("#f87171", 0.13) == "rgba(248,113,113,0.13)"
    assert tema.rgba(tema.VERDE, 1) == "rgba(74,222,128,1)"
