from aprobacion.generacion import (
    disponibilidad,
    hay_revision_en_curso,
)


def test_con_las_dos_credenciales_se_puede_usar_ia():
    d = disponibilidad({"ANTHROPIC_API_KEY": "sk-ant-x", "EDGAR_IDENTITY": "yo@x.com"})
    assert d.puede_usar_ia
    assert d.motivo is None


def test_sin_clave_de_api_no_se_puede_y_lo_dice():
    d = disponibilidad({"EDGAR_IDENTITY": "yo@x.com"})
    assert not d.puede_usar_ia
    assert "ANTHROPIC_API_KEY" in d.motivo


def test_sin_identidad_de_edgar_tampoco_se_puede():
    # No es un capricho: sin EDGAR_IDENTITY no hay Item 1A que citar, asi que
    # se le pediria al modelo que citara un documento que nadie descargo. La
    # ficha diria "generada por IA" y llegaria sin una sola cita.
    d = disponibilidad({"ANTHROPIC_API_KEY": "sk-ant-x"})
    assert not d.puede_usar_ia
    assert "EDGAR_IDENTITY" in d.motivo


def test_sin_ninguna_de_las_dos_las_nombra_a_ambas():
    d = disponibilidad({})
    assert "ANTHROPIC_API_KEY" in d.motivo
    assert "EDGAR_IDENTITY" in d.motivo


def test_una_credencial_vacia_cuenta_como_ausente():
    # setx con una cadena vacia deja la variable definida y sin valor: sin esto
    # la pagina ofreceria la IA y la corrida degradaria a plantilla en silencio.
    d = disponibilidad({"ANTHROPIC_API_KEY": "", "EDGAR_IDENTITY": "yo@x.com"})
    assert not d.puede_usar_ia


def test_sin_nada_marcado_no_hay_revision_que_perder():
    assert not hay_revision_en_curso(set(), [])


def test_una_casilla_marcada_ya_es_revision_en_curso():
    assert hay_revision_en_curso({"AAPL"}, [])


def test_un_anadido_a_mano_tambien_cuenta():
    # Es el caso que mas duele: lleva un motivo escrito a mano que no se
    # recupera de ningun sitio si se sobrescribe la corrida.
    assert hay_revision_en_curso(set(), [object()])
