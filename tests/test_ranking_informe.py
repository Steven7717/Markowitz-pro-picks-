from fundamentals.kpis import TODOS_LOS_KPIS
from ranking.informe import render

FICHA = {
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "puesto": 1,
    "compuesto": 1.42,
    "pilares": {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1},
    "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
    "flojos": [{"kpi": "per", "valor": 34.2, "z": 2.0}],
    "cobertura": {"kpis_con_dato": 14, "pilares_con_dato": 4},
    "desplazo_a": ["BBB"],
    "generada_por": "sonnet-5",
    "narrativa": {
        "tesis": "Rentabilidad muy por encima de sus pares.",
        "riesgos": [
            {
                "afirmacion": "Depende de pocos proveedores",
                "cita": "limited number of suppliers for key components",
                "verificada": True,
            },
            {
                "afirmacion": "Riesgo regulatorio",
                "cita": "no comprobable en el texto entregado",
                "verificada": False,
            },
        ],
        "fuente": {
            "formulario": "10-K",
            "fecha": "2025-10-31",
            "accession": "0000320193-25-000079",
            "seccion": "Item 1A",
            "caracteres_enviados": 68163,
            "recortado": False,
        },
    },
}

EXCLUSIONES = {"cobertura_insuficiente": 41, "datos_rancios": 3}


def test_incluye_ticker_puesto_y_tesis():
    texto = render([FICHA], EXCLUSIONES)
    assert "AAA" in texto
    assert "Rentabilidad muy por encima" in texto
    # El puesto lo nombra el test desde el plan y no lo comprobaba nadie: es
    # el orden del ranking, que es lo único que este informe transporta.
    assert "## 1. AAA" in texto


def test_marca_visiblemente_los_riesgos_no_verificados():
    # Si esto no se ve, la verificación no sirve de nada.
    texto = render([FICHA], EXCLUSIONES)
    assert "sin verificar" in texto.lower()


def test_marca_el_riesgo_que_toca_y_no_el_verificado():
    # `assert "sin verificar" in texto` pasa igual con la condición invertida:
    # marcaría el riesgo verificado y dejaría limpio el inventado, que es el
    # fallo exacto que este informe existe para no cometer.
    texto = render([FICHA], EXCLUSIONES)
    linea_mala = next(l for l in texto.splitlines() if "Riesgo regulatorio" in l)
    linea_buena = next(l for l in texto.splitlines() if "pocos proveedores" in l)
    assert "sin verificar" in linea_mala.lower()
    assert "sin verificar" not in linea_buena.lower()


def test_reporta_las_exclusiones_al_pie():
    texto = render([FICHA], EXCLUSIONES)
    assert "cobertura_insuficiente" in texto
    # La línea entera, no el "41" suelto: un número de dos cifras aparece por
    # casualidad en cualquier accession o z-score.
    assert "`cobertura_insuficiente`: 41" in texto


def test_las_exclusiones_van_de_mayor_a_menor():
    texto = render([FICHA], EXCLUSIONES)
    assert texto.index("cobertura_insuficiente") < texto.index("datos_rancios")


def test_una_ficha_de_plantilla_no_revienta_el_render():
    plantilla = {**FICHA, "narrativa": None, "generada_por": "plantilla"}
    texto = render([plantilla], EXCLUSIONES)
    assert "AAA" in texto
    assert "plantilla" in texto


def test_distingue_la_escala_del_compuesto_de_la_de_los_pilares():
    # El compuesto es la media ponderada de los pilares re-estandarizada
    # DENTRO del sector (enmienda 1), así que no está en la misma escala que
    # ellos: en una corrida real se ve un compuesto de +1,53 junto a pilares
    # que promedian +0,12. Juntos en una línea y sin etiqueta, el lector
    # concluye que uno es el promedio del otro y que las cuentas no cuadran.
    texto = render([FICHA], EXCLUSIONES)
    assert "Compuesto (z dentro del sector) +1.42" in texto
    assert "Pilares (z frente a todo el universo)" in texto


def test_dice_que_el_score_no_esta_validado():
    # La frase que impide leer este informe como una previsión de rentabilidad.
    # Es la afirmación con más consecuencias del documento y la más fácil de
    # perder en un refactor de plantilla, porque no la usa ningún dato.
    texto = render([FICHA], EXCLUSIONES).lower()
    assert "no está validado" in texto


def test_la_cobertura_no_inventa_el_numero_de_kpis():
    texto = render([FICHA], EXCLUSIONES)
    assert f"14 de {len(TODOS_LOS_KPIS)} KPIs" in texto


def test_una_narrativa_sin_procedencia_se_marca_en_vez_de_reventar():
    # `redactar()` devuelve {tesis, riesgos} y nada más: la procedencia la
    # tiene que inyectar quien orquesta, desde el Riesgos de filings.py. Si no
    # lo hace, una cita queda sin forma de localizarla en el filing original
    # —que es la promesa entera— así que el informe lo dice en vez de callarlo,
    # y desde luego en vez de reventar con KeyError a mitad de la corrida.
    sin_fuente = {
        **FICHA,
        "narrativa": {
            "tesis": FICHA["narrativa"]["tesis"],
            "riesgos": FICHA["narrativa"]["riesgos"],
        },
    }
    texto = render([sin_fuente], EXCLUSIONES)
    assert "Rentabilidad muy por encima" in texto
    assert "procedencia no disponible" in texto.lower()


def test_una_cita_con_saltos_de_linea_no_rompe_la_cita_en_bloque():
    # El texto crudo del Item 1A trae saltos de línea; verificar_cita los
    # normaliza para comparar, pero la cita se guarda tal cual llegó. Sin
    # colapsarlos, la segunda línea sale fuera del bloque y deja de leerse
    # como cita.
    con_saltos = {
        **FICHA,
        "narrativa": {
            **FICHA["narrativa"],
            "riesgos": [
                {
                    "afirmacion": "Depende de pocos proveedores",
                    "cita": "limited number\nof suppliers\tfor key components",
                    "verificada": True,
                }
            ],
        },
    }
    texto = render([con_saltos], EXCLUSIONES)
    cita = next(l for l in texto.splitlines() if "limited number" in l)
    assert "limited number of suppliers for key components" in cita


def test_el_recorte_del_filing_se_declara():
    recortada = {
        **FICHA,
        "narrativa": {
            **FICHA["narrativa"],
            "fuente": {**FICHA["narrativa"]["fuente"], "recortado": True},
        },
    }
    assert "recortado" in render([recortada], EXCLUSIONES)
    assert "recortado" not in render([FICHA], EXCLUSIONES)


def test_sin_exclusiones_no_finge_que_no_hubo_guardas():
    texto = render([FICHA], {})
    assert "ninguna" in texto.lower()
