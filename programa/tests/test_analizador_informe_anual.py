"""El extractor de los riesgos y del MD&A, con los casos del sondeo del 2026-11-15."""

from datetime import timedelta

import pytest

from analizador import informe_anual as ia

LARGO = "Revenue grew because demand for memory was strong. " * 200  # 10.200 caracteres
ENCABEZADO = "MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS"


# --- El MD&A ---------------------------------------------------------------------


def test_el_mdna_de_un_10k_normal_empieza_en_su_encabezado():
    # MU: la sección llega con «Table of Contents» delante.
    seccion = f"Table of Contents\n\nITEM 7. {ENCABEZADO}\n\n{LARGO}"
    texto, origen = ia.mdna(seccion, [])
    assert texto.startswith("ITEM 7. MANAGEMENT")
    assert origen == "informe"


def test_el_encabezado_con_espacios_duros_tambien_se_reconoce():
    # VEEV escribe «ITEM\xa07.\xa0\xa0\xa0\xa0MANAGEMENT’S…».
    seccion = f"Table of Contents\n\nITEM\xa07.\xa0\xa0\xa0\xa0{ENCABEZADO}\n\n{LARGO}"
    assert ia.mdna(seccion, [])[0].startswith("ITEM\xa07.")


def test_si_el_encabezado_queda_lejos_se_manda_la_seccion_entera():
    # Un encabezado a media sección es una mención, no el principio.
    seccion = LARGO + LARGO + f"\n{ENCABEZADO}\n" + LARGO
    assert ia.mdna(seccion, [])[0] == seccion


def test_un_20f_sin_ese_encabezado_manda_su_item_5_entero():
    # TSM: «ITEM 5.OPERATING AND FINANCIAL REVIEWS AND PROSPECTS».
    seccion = "ITEM 5.OPERATING AND FINANCIAL REVIEWS AND PROSPECTS\n\n" + LARGO
    assert ia.mdna(seccion, []) == (seccion, "informe")


def test_el_mdna_incorporado_por_referencia_se_busca_en_el_anexo_13():
    # PGR: el Item 7 son 243 caracteres y el MD&A está a mitad del EX-13.
    remision = f"ITEM 7. {ENCABEZADO}\n\nIncorporated by reference from the Annual Report."
    anexo = (
        "Notes to the financial statements. " * 300
        + "\n\nManagement’s Discussion and Analysis of Financial Condition and Results of\nOperations\n\n"
        + LARGO
    )
    texto, origen = ia.mdna(remision, [anexo])
    assert texto.startswith("Management’s Discussion and Analysis")
    assert origen == "ex_13"


def test_un_indice_al_principio_del_anexo_no_es_el_encabezado():
    # El índice acaba en un número de página: el MD&A de verdad está mucho después.
    remision = f"ITEM 7. {ENCABEZADO}\n\nIncorporated by reference."
    relleno = "Notes to the financial statements. " * 3_500  # 122.500 caracteres
    anexo = (
        "\nManagement’s Discussion and Analysis of Financial Condition 25\n\n"
        + relleno
        + "\n\nManagement’s Discussion and Analysis of Financial Condition and Results of\nOperations\n\n"
        + LARGO
    )
    texto, origen = ia.mdna(remision, [anexo])
    assert texto.startswith("Management’s Discussion and Analysis of Financial Condition and Results")
    assert len(texto) < 20_000 and origen == "ex_13"


def test_un_indice_con_puntos_de_relleno_tampoco():
    anexo = "\n\nManagement’s Discussion and Analysis ........ 25\n\n" + LARGO
    assert ia.mdna("Incorporated by reference.", [anexo]) == (None, "")


def test_una_mencion_partida_por_el_ajuste_de_linea_no_es_un_encabezado():
    anexo = (
        "These statements should be read together with\n"
        "Management’s Discussion and Analysis included elsewhere in this report. " + LARGO
    )
    assert ia.mdna("Incorporated by reference.", [anexo]) == (None, "")


def test_un_anexo_sin_el_encabezado_no_se_hace_pasar_por_mdna():
    # WFC lo llama «Financial Review»: no se localiza, y no se manda otra cosa.
    remision = f"ITEM 7. {ENCABEZADO}\n\nIncorporated by reference."
    assert ia.mdna(remision, ["Financial Review\n\n" + LARGO]) == (None, "")


def test_una_mencion_dentro_de_una_frase_no_es_un_encabezado():
    anexo = "As described in management’s discussion and analysis, results vary. " * 200
    assert ia.mdna("", [anexo]) == (None, "")


def test_sin_seccion_ni_anexos_no_hay_mdna():
    assert ia.mdna(None, []) == (None, "")


# --- Los riesgos -------------------------------------------------------------------


def test_los_riesgos_de_un_20f_se_cortan_desde_su_linea_del_item_3():
    # TSM: `risk_factors` es el Item 3 entero.
    item3 = (
        "ITEM 3.KEY INFORMATION\n\nCapitalization and Indebtedness \n\nNot applicable. \n\n"
        "Risk Factors \n\nWe wish to caution readers. " + LARGO
    )
    assert ia.riesgos_20f(item3).startswith("Risk Factors")


def test_el_apartado_con_su_letra_tambien_se_reconoce():
    item3 = "ITEM 3 KEY INFORMATION\n\nD. RISK FACTORS\n\n" + LARGO
    assert ia.riesgos_20f(item3).startswith("D. RISK FACTORS")


def test_unos_riesgos_que_remiten_a_otro_documento_no_son_los_riesgos():
    # NVO: «For information on risk factors, reference is made to…».
    item3 = "ITEM 3 KEY INFORMATION\n\nD. RISK FACTORS\n\nReference is made to the Annual Report."
    assert ia.riesgos_20f(item3) is None
    assert ia.riesgos_10k("Risk Factors. See the Annual Report.") is None


def test_unos_riesgos_que_remiten_tras_varios_miles_de_caracteres_tampoco_lo_son():
    # NVO: el Item 3 mide 6.897 caracteres, casi todos de lo demás.
    item3 = (
        "ITEM 3 KEY INFORMATION\n\nA. [RESERVED]\n\nB. CAPITALISATION AND INDEBTEDNESS\n\n"
        "Not applicable.\n\nC. REASONS FOR THE OFFER AND USE OF PROCEEDS\n\nNot applicable.\n\n"
        "D. RISK FACTORS\n\nFor information on risk factors, reference is\nmade to ‘Risk management’ "
        "on pages 41-42 of our Annual Report 2025, " + LARGO
    )
    assert ia.riesgos_20f(item3) is None


def test_un_10k_que_incorpora_por_referencia_no_tiene_riesgos_aunque_sea_largo():
    assert ia.riesgos_10k("Incorporated\nby reference from the Annual Report. " + LARGO) is None


def test_los_riesgos_de_un_10k_van_enteros():
    assert ia.riesgos_10k(LARGO) == LARGO


# --- El informe compuesto ------------------------------------------------------------


def _crudo(**cambios):
    crudo = {
        "formulario": "10-K",
        "fecha": "2026-10-09",
        "accession": "0000723125-26-000023",
        "riesgos": "ITEM 1A. RISK FACTORS\n\n" + LARGO,
        "mdna": f"ITEM 7. {ENCABEZADO}\n\n{LARGO}",
        "anexos_13": [],
    }
    crudo.update(cambios)
    return crudo


def test_el_informe_lleva_cada_seccion_con_su_nombre():
    informe = ia.componer("MU", _crudo())
    assert (informe.formulario, informe.fecha, informe.accession) == ("10-K", "2026-10-09", "0000723125-26-000023")
    assert informe.riesgos.nombre == "Item 1A" and not informe.riesgos.recortado
    assert informe.mdna.nombre == "Item 7"


def test_los_riesgos_se_cortan_igual_que_en_candidatos():
    # El mismo texto que `ranking.filings.cargar_riesgos`: la ficha ya pagada en
    # candidatos sale de la caché por contenido.
    largo = "x" * (ia.MAX_RIESGOS + 10)
    informe = ia.componer("MU", _crudo(riesgos=largo))
    assert informe.riesgos.texto == largo[: ia.MAX_RIESGOS]
    assert informe.riesgos.recortado and informe.riesgos.caracteres_totales == len(largo)


def test_el_mdna_largo_se_corta_y_se_dice():
    informe = ia.componer("JPM", _crudo(mdna="palabra " * 20_000))
    assert len(informe.mdna.texto) <= ia.TOPE_MDNA and informe.mdna.recortado


def test_el_mdna_del_anexo_dice_que_sale_del_anexo():
    anexo = f"\n{ENCABEZADO.title()}\n\n{LARGO}"
    informe = ia.componer("PGR", _crudo(mdna="Incorporated by reference.", anexos_13=[anexo]))
    assert informe.mdna.nombre == "EX-13"


def test_un_20f_nombra_sus_secciones():
    item3 = "ITEM 3\n\nRisk Factors\n\n" + LARGO
    informe = ia.componer("TSM", _crudo(formulario="20-F", riesgos=item3, mdna="ITEM 5.\n\n" + LARGO))
    assert (informe.riesgos.nombre, informe.mdna.nombre) == ("Item 3.D", "Item 5")


def test_una_seccion_que_falta_queda_en_none_y_la_otra_no():
    informe = ia.componer("WFC", _crudo(mdna="Incorporated by reference."))
    assert informe.mdna is None and informe.riesgos is not None


# --- La caché y la red -----------------------------------------------------------------


@pytest.fixture
def red(monkeypatch, tmp_path):
    llamadas = []
    estado = {"crudo": _crudo()}

    def descargar(ticker, formulario):
        llamadas.append((ticker, formulario))
        return estado["crudo"]

    monkeypatch.setenv("EDGAR_IDENTITY", "prueba@example.com")
    monkeypatch.setattr(ia, "RAIZ_CACHE", tmp_path)
    monkeypatch.setattr(ia, "_descargar", descargar)
    estado["llamadas"] = llamadas
    return estado


def test_el_informe_se_baja_una_vez_y_luego_sale_de_la_cache(red):
    primero, motivo = ia.cargar("MU", "10-K")
    segundo, _ = ia.cargar("MU", "10-K")
    assert motivo == "ok" and primero == segundo
    assert red["llamadas"] == [("MU", "10-K")]


def test_caducado_y_sin_red_se_sirve_lo_guardado(red, monkeypatch):
    ia.cargar("MU", "10-K")
    monkeypatch.setattr(ia, "VALIDEZ", timedelta(0))
    red["crudo"] = None
    informe, motivo = ia.cargar("MU", "10-K")
    assert informe is not None and motivo == "ok"


def test_sin_red_y_sin_nada_guardado_se_dice(red):
    red["crudo"] = None
    assert ia.cargar("MU", "10-K") == (None, "sin_red_edgar")


def test_una_empresa_sin_ese_informe_se_dice(red):
    red["crudo"] = {}
    assert ia.cargar("MU", "10-K") == (None, "sin_informe")


def test_un_40f_no_tiene_secciones_y_no_se_baja_nada(red):
    assert ia.cargar("RY", "40-F") == (None, "sin_secciones")
    assert red["llamadas"] == []


def test_sin_identidad_no_se_pregunta_a_la_sec(red, monkeypatch):
    monkeypatch.delenv("EDGAR_IDENTITY")
    assert ia.cargar("MU", "10-K") == (None, "sin_identidad_edgar")
    assert red["llamadas"] == []


def test_el_ultimo_presentado_se_pregunta_una_vez_al_dia(red, monkeypatch):
    preguntas = []

    def consultar(ticker, formulario):
        preguntas.append(ticker)
        return ("0000723125-26-000023", "2026-10-09")

    monkeypatch.setattr(ia, "_consultar_ultimo", consultar)
    assert ia.ultimo_presentado("MU", "10-K") == ("0000723125-26-000023", "2026-10-09")
    assert ia.ultimo_presentado("MU", "10-K") == ("0000723125-26-000023", "2026-10-09")
    assert preguntas == ["MU"]


def test_si_no_se_pudo_preguntar_no_se_guarda_nada(red, monkeypatch):
    monkeypatch.setattr(ia, "_consultar_ultimo", lambda *a: None)
    assert ia.ultimo_presentado("MU", "10-K") is None
    monkeypatch.setattr(ia, "_consultar_ultimo", lambda *a: ("x", "2026-10-09"))
    assert ia.ultimo_presentado("MU", "10-K") == ("x", "2026-10-09")


def test_el_formulario_de_un_ticker_es_el_del_resolver(monkeypatch):
    monkeypatch.setattr("analizador.resolver.formularios_sec", lambda t: (("20-F",), "ok"))
    assert ia.formulario_de("TSM") == "20-F"
    monkeypatch.setattr("analizador.resolver.formularios_sec", lambda t: (None, "sin_red_edgar"))
    assert ia.formulario_de("TSM") is None
