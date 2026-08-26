from ranking.verificacion import (
    MAX_CARACTERES_CITA,
    MIN_CARACTERES_CITA,
    sin_digitos,
    verificar_cita,
)

FUENTE = (
    "Our business is subject to  intense competition.\n"
    "We depend on a limited number of suppliers for key components."
)

# Sin dígitos y con espacios simples a propósito: sirve para las pruebas de
# frontera de los topes, donde un carácter de más o de menos en la cita
# normalizada tiene que bastar para cruzar la línea.
FUENTE_LARGA = (
    "Our business faces significant operational and regulatory challenges "
    "across every market in which we currently operate or plan to expand "
    "including new jurisdictions where our supply chain partners face "
    "increasing scrutiny from regional authorities and trade groups"
)


def test_acepta_una_cita_literal():
    assert verificar_cita("depend on a limited number of suppliers", FUENTE)


def test_tolera_diferencias_de_espacios_y_mayusculas():
    # Los saltos de línea del informe no deben invalidar una cita real.
    assert verificar_cita("SUBJECT TO INTENSE   competition", FUENTE)


def test_rechaza_una_cita_fabricada():
    # El test que decide si "trazable" significa algo.
    assert not verificar_cita("We expect margins to collapse next year", FUENTE)


def test_rechaza_una_cita_vacia():
    # Caso exigido por el plan. Queda subsumido por el mínimo de longitud de
    # abajo, pero documenta el contrato igual.
    assert not verificar_cita("", FUENTE)


def test_rechaza_una_cita_de_solo_espacios():
    # "   " no es la cadena vacía, pero normaliza a "" (longitud 0), que cae
    # bajo MIN_CARACTERES_CITA igual que la cadena vacía.
    assert not verificar_cita("   ", FUENTE)
    assert not verificar_cita("\n\t ", FUENTE)


def test_rechaza_una_cita_demasiado_larga():
    # Sin tope, "citar" podría ser copiar la sección entera.
    assert not verificar_cita(FUENTE * 10, FUENTE * 10)


def test_tolera_comillas_tipograficas_y_guion_largo():
    # Filings de la SEC: comillas curvas y guion largo. El porqué está en el
    # comentario junto a _EQUIVALENCIAS_TIPOGRAFICAS.
    fuente_tipografica = "We depend on the Company’s suppliers—for now."
    assert verificar_cita("the Company's suppliers-for now", fuente_tipografica)


def test_acepta_cita_justo_en_el_tope_maximo():
    cita = FUENTE_LARGA[:MAX_CARACTERES_CITA]
    assert len(cita) == MAX_CARACTERES_CITA
    assert verificar_cita(cita, FUENTE_LARGA)


def test_rechaza_cita_justo_por_encima_del_tope_maximo():
    cita = FUENTE_LARGA[: MAX_CARACTERES_CITA + 1]
    assert len(cita) == MAX_CARACTERES_CITA + 1
    assert not verificar_cita(cita, FUENTE_LARGA)


def test_acepta_cita_justo_en_el_minimo():
    cita = FUENTE_LARGA[:MIN_CARACTERES_CITA]
    assert len(cita) == MIN_CARACTERES_CITA
    assert verificar_cita(cita, FUENTE_LARGA)


def test_rechaza_cita_justo_por_debajo_del_minimo():
    cita = FUENTE_LARGA[: MIN_CARACTERES_CITA - 1]
    assert len(cita) == MIN_CARACTERES_CITA - 1
    assert not verificar_cita(cita, FUENTE_LARGA)


def test_el_tope_se_aplica_al_texto_normalizado_no_al_crudo():
    # El porqué está en el comentario junto a MAX_CARACTERES_CITA.
    palabras = FUENTE_LARGA.split()[:25]
    cita_con_espacios_de_sobra = "   \n  ".join(palabras)
    assert len(cita_con_espacios_de_sobra) > MAX_CARACTERES_CITA
    assert len(" ".join(palabras)) <= MAX_CARACTERES_CITA
    assert verificar_cita(cita_con_espacios_de_sobra, FUENTE_LARGA)


def test_detecta_digitos_en_la_narrativa():
    assert sin_digitos("Los márgenes están muy por encima de sus pares")
    assert not sin_digitos("Los márgenes superan el 30% del sector")


def test_detecta_fraccion_unicode_como_digito():
    # isdigit() no caza "½"; isnumeric() sí. El porqué está en el docstring
    # de sin_digitos.
    assert not sin_digitos("Los márgenes rondan ½ del sector")
