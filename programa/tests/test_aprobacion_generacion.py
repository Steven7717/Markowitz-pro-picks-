from aprobacion.generacion import (
    disponibilidad,
    hay_revision_en_curso,
)


def test_con_las_dos_credenciales_se_puede_usar_ia():
    d = disponibilidad({"ANTHROPIC_API_KEY": "sk-ant-x", "EDGAR_IDENTITY": "yo@x.com"})
    assert d.puede_usar_ia
    assert d.motivo is None
    assert d.puede_generar
    assert d.motivo_generacion is None


def test_sin_identidad_no_se_puede_generar_ni_siquiera_sin_ia():
    # El defecto que motiva este cambio: EDGAR_IDENTITY va en el User-Agent de
    # toda peticion a la SEC, no solo en la mitad con IA. Sin ella no hay nada
    # que descargar, con o sin IA.
    d = disponibilidad({"ANTHROPIC_API_KEY": "sk-ant-x"})
    assert not d.puede_generar
    assert "EDGAR_IDENTITY" in d.motivo_generacion


def test_con_solo_identidad_si_se_puede_generar_sin_ia():
    d = disponibilidad({"EDGAR_IDENTITY": "yo@x.com"})
    assert d.puede_generar
    assert d.motivo_generacion is None
    # La IA sigue sin estar disponible: falta la clave.
    assert not d.puede_usar_ia


def test_sin_nada_tampoco_se_puede_generar():
    d = disponibilidad({})
    assert not d.puede_generar
    assert "EDGAR_IDENTITY" in d.motivo_generacion


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


# --- El coste anunciado, y el peor caso que tiene que cubrir -----------------
#
# `COSTE_APROXIMADO_USD` decia 1,25 $ y el peor caso medido eran 2,13 $: un 70%
# mas de lo anunciado, en la unica pantalla del programa donde una cifra decide
# si se gasta o no. Y el peor caso no era mala suerte: el reintento lo dispara
# de forma **determinista** un filing hostil, que basta con que induzca un
# digito en la afirmacion o una cita que no verifique. El texto de un tercero
# decidia el gasto del usuario por un factor de dos.
#
# Los dos de abajo atan la cifra anunciada a las constantes que de verdad la
# producen, asi que ya no se puede cambiar la politica de reintento sin que la
# cifra de la pantalla se entere.

from aprobacion import generacion
from ranking import llm
from ranking.criterio import TAMANO_TOP


def test_el_coste_anunciado_cubre_el_peor_caso():
    """El saboteador de esta tarea entera: subir MAX_CARACTERES_REINTENTO o
    MAX_TOKENS sin tocar la cifra de la pantalla tumba esto."""
    assert generacion.COSTE_APROXIMADO_USD >= generacion.coste_peor_caso()


def test_el_coste_anunciado_no_se_va_por_las_nubes():
    """La otra mitad: anunciar diez dolares tambien «cubre» el peor caso, y
    seria igual de inutil para decidir. Un margen, no una barra libre."""
    assert generacion.COSTE_APROXIMADO_USD <= generacion.coste_peor_caso() * 1.2


def test_el_peor_caso_crece_con_las_fichas():
    assert generacion.coste_peor_caso(30) > generacion.coste_peor_caso(15)


def test_el_tope_de_la_corrida_deja_pasar_una_corrida_normal():
    """Un tope por debajo del peor caso convertiria una corrida legitima en
    fichas de plantilla a mitad de lista, que es la degradacion silenciosa que
    este programa evita en todas partes. El tope esta para lo que se salga de
    lo previsto, no para lo previsto."""
    assert llm.TOPE_USD_POR_CORRIDA > generacion.coste_peor_caso(TAMANO_TOP)


def test_el_peor_caso_usa_el_ratio_medido_y_no_la_regla_de_tres():
    """`ranking/filings.py` midio 3,30 caracteres por token contra la API real
    y dejo escrito que «la regla de tres se quedaba corta en un 21%». Aqui se
    asumian 4,0 «que es lo que sale en prosa legal en inglés» -- sobre el mismo
    texto que alli se midio. El test de arriba pasaba porque los dos lados
    usaban el mismo numero malo."""
    from ranking import filings

    assert generacion.CARACTERES_POR_TOKEN == filings.CARACTERES_POR_TOKEN
    assert filings.CARACTERES_POR_TOKEN < 4


def test_el_reintento_cuenta_mas_tokens_con_el_ratio_medido():
    """La direccion del error importa: con menos caracteres por token, el mismo
    recorte del filing son MAS tokens y el peor caso sube. Anunciar de menos en
    la pantalla donde se decide gastar es el lado caro."""
    con_el_medido = generacion.coste_peor_caso()
    con_la_regla_de_tres = (
        llm.MAX_CARACTERES_REINTENTO // 4 + llm.MAX_TOKENS
    )
    entrada_mala = TAMANO_TOP * (generacion.TOKENS_POR_FICHA + con_la_regla_de_tres)
    salida = TAMANO_TOP * 2 * llm.MAX_TOKENS
    peor_con_el_malo = (
        entrada_mala * llm.PRECIO_ENTRADA + salida * llm.PRECIO_SALIDA
    ) / 1_000_000
    assert con_el_medido > peor_con_el_malo
