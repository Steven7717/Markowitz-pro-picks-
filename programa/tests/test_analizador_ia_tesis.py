"""La tesis de candidatos, redactada desde el Analizador, y los topes anunciados."""

from types import SimpleNamespace

import pytest

from analizador import ia_costes, ia_tesis, informe_anual
from aprobacion import generacion
from interprete import cliente as cliente_mod
from ranking import llm
from ranking.filings import CARACTERES_POR_TOKEN

RIESGOS = "ITEM 1A. RISK FACTORS\n\nWe depend on a small number of customers for a large part of our revenue. " * 5
CONTEXTO = "Empresa: MU, sector Information Technology."


def _falso(narrativas):
    restantes = list(narrativas)

    class _Mensajes:
        def parse(self, **_kwargs):
            return SimpleNamespace(
                parsed_output=restantes.pop(0),
                usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
            )

    class _Falso:
        messages = _Mensajes()

    return _Falso()


def _narrativa():
    return llm.Narrativa(
        tesis="Vende memoria y depende de pocos compradores.",
        riesgos=[llm.Riesgo(afirmacion="Depende de pocos clientes.", cita="We depend on a small number of customers")],
    )


def test_la_tesis_sale_con_su_cita_verificada_y_con_lo_que_costo(tmp_path):
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path)
    assert redaccion.narrativa["riesgos"][0]["verificada"] is True
    assert redaccion.gasto.llamadas == 1 and redaccion.gasto.usd > 0
    assert redaccion.de_cache is False


def test_la_segunda_vez_sale_de_la_cache_y_no_cuesta(tmp_path):
    ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path)
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([]), cache_dir=tmp_path)
    assert redaccion.narrativa is not None
    assert redaccion.de_cache is True and redaccion.gasto.llamadas == 0


def test_el_gasto_es_el_de_esta_llamada_y_no_el_acumulado(tmp_path):
    ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path / "a")
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path / "b")
    assert redaccion.gasto.llamadas == 1


def test_si_no_se_pudo_redactar_no_hay_narrativa_ni_se_dice_de_cache(tmp_path):
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([None]), cache_dir=tmp_path)
    assert redaccion.narrativa is None and redaccion.de_cache is False


def test_el_tope_de_la_tesis_es_el_de_una_ficha_de_candidatos():
    assert ia_costes.tesis() == generacion.coste_peor_caso(1)


def test_el_tope_del_contraste_usa_la_cota_de_las_tablas_y_no_la_medida_de_la_prosa():
    # El MD&A lleva tablas, más densas que la prosa en la que se midió 3,30.
    assert ia_costes.CARACTERES_POR_TOKEN_CON_TABLAS == 2.5 < CARACTERES_POR_TOKEN
    por_turno = int(informe_anual.TOPE_MDNA / ia_costes.CARACTERES_POR_TOKEN_CON_TABLAS)
    minimo = cliente_mod.coste(2 * por_turno, 2 * cliente_mod.MAX_TOKENS)
    assert ia_costes.mdna() > minimo
    con_prosa = int(informe_anual.TOPE_MDNA / CARACTERES_POR_TOKEN)
    assert ia_costes.mdna() > cliente_mod.coste(2 * con_prosa, 2 * cliente_mod.MAX_TOKENS)


def test_ningun_tope_anunciado_pasa_del_tope_duro_de_la_pulsacion():
    # Si pasara, la pantalla anunciaría un gasto que `dentro_del_tope` corta antes.
    for anunciado in (ia_costes.mdna(), ia_costes.valoracion()):
        assert 0 < anunciado < cliente_mod.TOPE_USD_POR_PULSACION


# --- El contador de gasto es de todo el proceso: no se reinicia por una pulsación ---


@pytest.fixture
def contador_limpio():
    llm.reiniciar_gasto()
    yield
    llm.reiniciar_gasto()


def test_redactar_no_pone_a_cero_el_contador_de_una_corrida_en_marcha(contador_limpio, tmp_path):
    llm._anotar_gasto(50_000, 4_000)
    previo = llm.gasto_acumulado()
    ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path)
    ahora = llm.gasto_acumulado()
    assert ahora.llamadas == previo.llamadas + 1
    assert ahora.entrada_tokens == previo.entrada_tokens + 1000


def test_el_gasto_devuelto_es_solo_el_de_esta_llamada_aunque_hubiera_acumulado_previo(contador_limpio, tmp_path):
    llm._anotar_gasto(50_000, 4_000)
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path)
    assert redaccion.gasto == llm.Gasto(llamadas=1, entrada_tokens=1000, salida_tokens=200)
    assert redaccion.de_cache is False


def test_con_el_acumulado_al_borde_del_tope_se_reinicia_y_la_tesis_se_redacta(contador_limpio, tmp_path):
    # Sin sitio para una ficha, `redactar_con_cache` devolvería None sin llamar,
    # por un tope que no es de esta pulsación.
    al_borde = int((llm.TOPE_USD_POR_CORRIDA - generacion.coste_peor_caso(1)) / llm.PRECIO_SALIDA * 1_000_000) + 1
    llm._anotar_gasto(0, al_borde)
    assert llm.gasto_acumulado().usd + generacion.coste_peor_caso(1) >= llm.TOPE_USD_POR_CORRIDA
    redaccion = ia_tesis.redactar(CONTEXTO, RIESGOS, cliente=_falso([_narrativa()]), cache_dir=tmp_path)
    assert redaccion.narrativa is not None
    assert redaccion.gasto == llm.Gasto(llamadas=1, entrada_tokens=1000, salida_tokens=200)
    assert llm.gasto_acumulado().llamadas == 1
