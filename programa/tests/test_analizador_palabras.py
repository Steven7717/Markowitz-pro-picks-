"""Lo que el modelo ve de la ficha y de la valoración: palabras, y ni un dígito."""

from types import SimpleNamespace

from analizador import palabras
from ranking.verificacion import sin_digitos


def _valoracion(**cambios):
    valoracion = {
        "metodo": "flujos",
        "veredicto": "en_rango",
        "implicito": {"magnitud": "crecimiento", "valor": 0.40, "referencia": 0.40, "margen": 0.2, "fuera_de_limites": None},
        "epv": {"por_accion": 205.4, "parte_crecimiento": 0.70},
        "votos": {
            "flujos": {"voto": "neutra", "motivo": None},
            "sin_crecimiento": {"voto": "neutra", "motivo": None},
            "pares": {"voto": "barata", "motivo": None},
        },
        "supuestos": {
            "beta": {"valor": 2.09, "procedencia": {"fuente": "regresion", "r2": 0.2979}},
            "g_ref": {"valor": 0.40, "procedencia": {"historico": 0.7063, "consenso": 0.1617}},
        },
    }
    valoracion.update(cambios)
    return valoracion


def test_la_valoracion_va_en_palabras_y_sin_un_digito():
    bloque, mapa = palabras.contexto_valoracion("MU", "Information Technology", _valoracion())
    assert sin_digitos(bloque)
    assert mapa == {"A": "flujos", "B": "sin_crecimiento", "C": "pares"}
    assert "Veredicto del programa: en rango." in bloque
    assert "[A] Flujos descontados: no se inclina a ningún lado; el precio exige un crecimiento en línea con su referencia." in bloque
    assert "[B] Valor sin crecimiento: no se inclina a ningún lado; la mayor parte del precio es apuesta por el crecimiento." in bloque
    assert "[C] Frente a sus pares: apunta a que está barata; múltiplos por debajo de los de su sector." in bloque


def test_la_exigencia_del_precio_se_gradua():
    def frase(valor):
        implicito = {"magnitud": "crecimiento", "valor": valor, "referencia": 0.10, "margen": 0.05}
        return palabras.contexto_valoracion("MU", "Tech", _valoracion(implicito=implicito))[0]

    assert "muy por encima de su referencia" in frase(0.25)
    assert "un crecimiento por encima de su referencia" in frase(0.17)
    assert "en línea con su referencia" in frase(0.12)
    assert "un crecimiento por debajo de su referencia" in frase(0.03)
    assert "muy por debajo de su referencia" in frase(-0.05)


def test_un_banco_habla_de_beneficio_residual_y_de_rentabilidad():
    implicito = {"magnitud": "roe", "valor": 0.158, "referencia": 0.15, "margen": 0.03}
    bloque, _ = palabras.contexto_valoracion("JPM", "Financials", _valoracion(metodo="residual", implicito=implicito))
    assert "[A] Beneficio residual:" in bloque
    assert "una rentabilidad sobre el capital en línea con su referencia" in bloque


def test_un_voto_que_no_aplica_se_dice_y_no_lleva_detalle():
    votos = {
        "flujos": {"voto": "neutra"},
        "sin_crecimiento": {"voto": "no_aplica", "motivo": "ebit_negativo"},
        "pares": {"voto": "cara"},
    }
    bloque, mapa = palabras.contexto_valoracion("JPM", "Financials", _valoracion(votos=votos))
    assert "[B] Valor sin crecimiento: no se pudo hacer." in bloque
    assert "múltiplos por encima de los de su sector" in bloque
    assert set(mapa) == {"A", "B", "C"}


def test_una_beta_con_poco_ajuste_se_avisa():
    supuestos = {"beta": {"valor": 0.2, "procedencia": {"r2": 0.03}}}
    bloque, _ = palabras.contexto_valoracion("SHEL", "Energy", _valoracion(supuestos=supuestos))
    assert "La beta es poco fiable: el ajuste de la regresión es débil." in bloque
    assert "poco fiable" not in palabras.contexto_valoracion("MU", "Tech", _valoracion())[0]


def test_lo_que_movio_el_usuario_se_dice():
    bloque, _ = palabras.contexto_valoracion("MU", "Tech", _valoracion(), "la beta y el crecimiento de referencia")
    assert "El usuario movió estos supuestos del programa: la beta y el crecimiento de referencia." in bloque


def test_sin_votos_no_hay_nada_que_explicar():
    assert palabras.contexto_valoracion("MU", "Tech", {"motivo": "sin_red"}) is None
    assert palabras.contexto_valoracion("MU", "Tech", None) is None


def test_el_supuesto_de_crecimiento_se_compara_con_la_historia():
    def frase(valor, historico):
        supuestos = {"g_ref": {"valor": valor, "procedencia": {"historico": historico}}}
        return palabras.supuesto_crecimiento(_valoracion(supuestos=supuestos))

    assert frase(0.40, 0.7063) == "El escenario base supone que los ingresos crecen muy por debajo de su ritmo de los últimos años."
    assert "crecen por debajo de su ritmo" in frase(0.10, 0.15)
    assert "crecen en línea con su ritmo" in frase(0.10, 0.11)
    assert "crecen por encima de su ritmo" in frase(0.15, 0.10)
    assert "crecen muy por encima de su ritmo" in frase(0.30, 0.10)
    assert "sin historia propia" in frase(0.10, None)
    assert sin_digitos(frase(0.40, 0.7063))


def test_el_supuesto_de_un_banco_habla_de_rentabilidad():
    frase = palabras.supuesto_crecimiento(_valoracion(metodo="residual"))
    assert "rentabilidad sobre el capital" in frase


def test_el_supuesto_dice_lo_movido_y_falta_sin_valoracion():
    frase = palabras.supuesto_crecimiento(_valoracion(), "el crecimiento de referencia")
    assert frase.endswith("El usuario movió estos supuestos del programa: el crecimiento de referencia.")
    assert palabras.supuesto_crecimiento({"motivo": "sin_red"}) is None


def test_el_contexto_de_la_tesis_es_el_de_candidatos_cuando_hay_ficha():
    ficha = {
        "ticker": "MU",
        "sector_gics": "Information Technology",
        "pilares": {"calidad": 0.64, "valoracion": None},
        "destacados": [{"kpi": "Margen operativo"}],
        "flojos": [{"kpi": "Deuda"}],
    }
    analisis = SimpleNamespace(ticker="MU", sector="Information Technology", referencia=SimpleNamespace(ficha=ficha))
    from ranking.run import contexto

    assert palabras.contexto_tesis(analisis) == contexto(ficha)


def test_sin_ficha_el_contexto_de_la_tesis_lo_dice():
    analisis = SimpleNamespace(ticker="TSM", sector=None, referencia=None)
    assert palabras.contexto_tesis(analisis) == (
        "Empresa: TSM, sector sin clasificar.\nNo hay comparación con sus pares del sector."
    )


def test_el_bloque_no_nombra_el_ticker_y_dice_el_sector():
    bloque, _ = palabras.contexto_valoracion("MU", "Information Technology", _valoracion())
    assert bloque.splitlines()[0] == "Empresa del sector Information Technology."
    assert "MU" not in bloque
    sin_sector, _ = palabras.contexto_valoracion("MU", None, _valoracion())
    assert sin_sector.splitlines()[0] == "Empresa del sector sin clasificar."


def test_un_ticker_con_digitos_no_los_mete_en_el_bloque():
    bloque, _ = palabras.contexto_valoracion("7203.T", "Consumer Discretionary", _valoracion())
    assert sin_digitos(bloque)


def test_con_votos_pero_ninguno_con_valor_no_hay_nada_que_comentar():
    votos = {"flujos": {"voto": None}, "sin_crecimiento": {}, "pares": {"voto": None}}
    assert palabras.contexto_valoracion("MU", "Tech", _valoracion(votos=votos)) is None
