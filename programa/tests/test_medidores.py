import re

import pytest

import medidores as m
from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.criterio import MIN_KPIS_CON_DATO, PILARES, SIGNOS
from ranking.fichas import descriptor

FICHA = {
    "ticker": "AAA",
    "sector_gics": "Industrials",
    "puesto": 1,
    "compuesto": 5.71,
    "pilares": {
        "calidad": 1.39,
        "crecimiento": -0.24,
        "valoracion": 0.07,
        "solidez": 6.39,
    },
    "cobertura": {
        "kpis_con_dato": 10,
        "pilares_con_dato": 4,
        "kpis_por_pilar": {
            "calidad": 5,
            "crecimiento": 1,
            "valoracion": 3,
            "solidez": 1,
        },
    },
}


def sin_etiquetas(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


# --- La escala y su vocabulario ---------------------------------------------


@pytest.mark.parametrize(
    "z, veredicto",
    [
        (6.39, "Muy bueno"),
        (1.5, "Muy bueno"),
        (1.4999, "Bueno"),
        (0.5, "Bueno"),
        (0.4999, "Regular"),
        (0.0, "Regular"),
        (-0.4999, "Regular"),
        (-0.5, "Malo"),
        (-1.4999, "Malo"),
        (-1.5, "Muy malo"),
        (-8.6, "Muy malo"),
    ],
)
def test_cada_tramo_de_la_escala_tiene_su_veredicto(z, veredicto):
    assert m.nivel(z).veredicto == veredicto


def test_el_medidor_y_la_narrativa_cortan_la_escala_por_el_mismo_sitio():
    # `descriptor` es el vocabulario que ya viaja al modelo dentro del prompt.
    # Si los dos juegos de cortes se separan, el revisor puede leer "por encima
    # de sus pares" en la narrativa junto a una barra ambar, y nada en la
    # pagina le dice cual de las dos miente. El barrido pasa por los cuatro
    # cortes exactos y por sus vecinos inmediatos a ambos lados.
    sospechosos = [1.5, 0.5, -0.5, -1.5]
    barrido = [
        z + delta for z in sospechosos for delta in (-1e-9, 0.0, 1e-9)
    ] + [i / 10 for i in range(-40, 41)]
    for z in barrido:
        assert m.nivel(z).detalle == descriptor(z), z


def test_la_leyenda_sale_de_los_mismos_cortes_que_pinta_el_medidor():
    # La tabla se genera, no se copia: es lo unico que le explica al revisor
    # que significa lo que ve, y una copia escrita al lado de la pagina se
    # quedaria mintiendo en cuanto alguien moviese un umbral.
    tabla = m.tabla_de_tramos()
    assert [marca for _, marca in m.TRAMOS] == [
        m.MUY_BUENO, m.BUENO, m.REGULAR, m.MALO, m.MUY_MALO
    ]
    for corte in (m.MUY_ALTO, m.ALTO, m.BAJO, m.MUY_BAJO):
        assert f"{corte:+.1f}".replace(".", ",") in tabla
    # SIN_DATOS no es un tramo de la escala: no tiene z que lo situe, y darle
    # una fila entre "Malo" y "Muy malo" lo convertiria en uno.
    assert m.SIN_DATOS.veredicto not in tabla


def test_un_pilar_sin_datos_no_es_un_pilar_mediocre():
    # El fallo que este modulo existe para no cometer: pintar la barra en el
    # centro convierte "no se pudo medir" en "salio del monton", y el revisor
    # aprueba creyendo que hay una medicion donde no la hay.
    assert m.nivel(None) is m.SIN_DATOS
    assert m.nivel(float("nan")) is m.SIN_DATOS
    assert m.nivel(None) is not m.REGULAR

    html = m.medidor("Crecimiento", None)
    assert "mpp-hueco" in html  # rayado, no barra
    assert "mpp-barra" not in html
    assert "Sin datos" in sin_etiquetas(html)


# --- La geometria de la barra ------------------------------------------------


@pytest.mark.parametrize("z", [-8.62, -3.0, -0.7, 0.0, 1.2, 6.39, 8.62])
def test_la_barra_nunca_se_sale_de_la_pista(z):
    # Los z de este motor no estan acotados en ninguna parte (|z| maximo real:
    # 8,62). Una barra calculada sin tope se dibujaria fuera de su carril y se
    # comeria la columna de al lado.
    html = m.medidor("Pilar", z)
    izquierda, ancho = (
        float(x) for x in re.search(
            r'mpp-barra" style="left:([\d.]+)%;width:([\d.]+)%', html
        ).groups()
    )
    assert 0.0 <= izquierda <= 100.0
    assert izquierda + ancho <= 100.0 + 1e-9


def test_un_z_desbordado_se_marca_en_vez_de_hacerse_pasar_por_el_tope():
    # Sin la marca, un +6,39 y un +3,00 se dibujan exactamente igual, y el
    # primer clasificado de la corrida real es el primero por un +6,39.
    desbordado = sin_etiquetas(m.medidor("Solidez", 6.39))
    justo = sin_etiquetas(m.medidor("Solidez", 3.0))
    assert "mpp-tope" in m.medidor("Solidez", 6.39)
    assert "mpp-tope" not in m.medidor("Solidez", 3.0)
    assert "+6.39" in desbordado and "›" in desbordado
    assert "›" not in justo


# --- El signo, que es donde el numero a secas enganaba ------------------------


def test_un_multiplo_caro_sale_en_rojo_y_no_en_verde():
    # El z de `per` llega crudo en la ficha: +2 significa caro. La pagina lo
    # pintaba como "+2.00" debajo de "Flojo en", invitando a leer un buen
    # numero en la lista de defectos.
    assert m.orientar("per", 2.0) == -2.0
    assert m.nivel(m.orientar("per", 2.0)) is m.MUY_MALO
    assert m.nivel(m.orientar("roic", 2.0)) is m.MUY_BUENO

    html = sin_etiquetas(m.medidor_kpi({"kpi": "per", "valor": 34.2, "z": 2.0}))
    assert "Muy malo" in html
    assert "menos es mejor" in html

    # Y al reves: en un margen, valor alto y barra verde apuntan al mismo sitio.
    # Anotar ahi "mas es mejor" es ruido repetido en cada fila, y el ruido
    # constante es lo que hace que nadie lea la advertencia cuando si importa.
    normal = sin_etiquetas(m.medidor_kpi({"kpi": "margen_neto", "valor": 0.3, "z": 2.0}))
    assert "es mejor" not in normal


def test_todos_los_kpis_tienen_nombre_unidad_y_signo():
    # Un KPI nuevo sin entrada aqui reventaria en mitad de la pagina, con la
    # lista de candidatos a medio pintar y las casillas ya marcadas.
    assert set(m.KPIS) == set(TODOS_LOS_KPIS)
    assert set(m.KPIS) == set(SIGNOS)
    assert set(m.PILARES_ETIQUETAS) == set(PILARES)


def test_el_valor_crudo_se_muestra_con_su_unidad():
    # El z dice que la empresa destaca entre sus pares; no dice si su margen es
    # del 4% o del 40%. Para decidir hacen falta los dos.
    assert m.formatear("margen_neto", 0.3349) == "33.5%"
    assert m.formatear("per", 34.2) == "34.2×"
    assert m.formatear("crecimiento_ingresos", -0.062) == "-6.2%"
    assert m.formatear("per", None) == "n/d"
    assert m.formatear("per", float("nan")) == "n/d"


# --- Lo que se lee sin color -------------------------------------------------


def test_el_veredicto_va_escrito_ademas_de_en_color():
    # Un medidor que solo cambia de tono no le dice nada a quien no distingue
    # el verde del rojo.
    for z, palabra in [(2.0, "Muy bueno"), (0.0, "Regular"), (-2.0, "Muy malo")]:
        assert palabra in sin_etiquetas(m.medidor("Pilar", z))


def test_la_tira_resume_los_cuatro_pilares_en_el_orden_del_criterio():
    texto = sin_etiquetas(m.tira_pilares(FICHA))
    assert [p for p in m.PILARES_ETIQUETAS.values() if p in texto] == list(
        m.PILARES_ETIQUETAS.values()
    )
    posiciones = [texto.index(m.PILARES_ETIQUETAS[p]) for p in PILARES]
    assert posiciones == sorted(posiciones)


def test_la_tarjeta_no_promete_que_el_compuesto_sea_la_media_de_los_pilares():
    # Compuesto y pilares no estan en la misma escala (enmienda 1 del diseno de
    # B): el primero es la media ponderada re-estandarizada dentro del sector.
    # Juntos y sin etiqueta, el lector concluye que las cuentas no cuadran.
    texto = sin_etiquetas(m.tarjeta_candidato(FICHA))
    assert "z dentro del sector" in texto
    assert "+5.71" in texto


# --- Cobertura ---------------------------------------------------------------


def test_el_pilar_dice_sobre_cuantos_kpis_se_apoya():
    texto = sin_etiquetas(m.medidores_pilares(FICHA))
    assert "1 de 3 KPIs" in texto  # solidez, el +6,39 sostenido por una linea
    assert "5 de 7 KPIs" in texto  # calidad


def test_una_ficha_anterior_al_recuento_por_pilar_se_pinta_sin_inventarselo():
    # salidas_ejemplo/ y cualquier corrida guardada antes de que B escribiera
    # este campo siguen abriendose: la nota se omite, no se rellena con ceros
    # (que se leerian como "ningun KPI con dato").
    vieja = {**FICHA, "cobertura": {"kpis_con_dato": 10, "pilares_con_dato": 4}}
    texto = sin_etiquetas(m.medidores_pilares(vieja))
    assert "KPIs" not in texto
    assert "Solidez" in texto


def test_la_cobertura_ensena_el_minimo_que_exigen_las_guardas():
    # "10 de 17" no dice si eso es mucho o poco. Con la marca del umbral se ve
    # que el minimo son 8, y que 10 es aprobar raspando.
    html = m.medidor_cobertura(10)
    assert "10 / 17" in sin_etiquetas(html)
    assert f"mínimo {MIN_KPIS_CON_DATO}" in sin_etiquetas(html)
    umbral = float(re.search(r'mpp-tope" style="left:([\d.]+)%', html).group(1))
    ancho = float(re.search(r'mpp-barra" style="left:0;width:([\d.]+)%', html).group(1))
    assert umbral < ancho  # 8 de 17 queda a la izquierda de 10 de 17


# --- Seguridad del pegado ----------------------------------------------------


def test_lo_que_viene_del_fichero_se_escapa_antes_de_pegarlo():
    # fichas.json es un fichero en disco que un usuario puede editar, y la
    # pagina lo pega con unsafe_allow_html. Un ticker con etiquetas dentro no
    # puede convertirse en marcado.
    hostil = {**FICHA, "ticker": "<img src=x onerror=alert(1)>"}
    html = m.tarjeta_candidato(hostil)
    assert "<img" not in html
    assert "&lt;img" in html
