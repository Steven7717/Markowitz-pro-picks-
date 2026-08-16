"""Contrastes contra las APIs reales. Necesitan red y credenciales.

    EDGAR_IDENTITY="tu@correo.com" ANTHROPIC_API_KEY=... pytest tests/ -q -m red

Todo lo demás del sub-proyecto B corre con las dos APIs mockeadas. Estos tres
tests son lo único que comprueba que el esquema, el id del modelo y los
parámetros de la llamada existen de verdad tal como el código los usa: hasta que
se ejecutan, esa parte está verificada sólo contra nuestras propias suposiciones.

Coste medido: la llamada de `test_el_modelo_devuelve_el_esquema_y_cita_de_verdad`
son unos cinco céntimos de dólar. Los otros dos no gastan (count_tokens es
gratis, y EDGAR también).
"""

import os

import pytest

from ranking.filings import MAX_CARACTERES, cargar_riesgos
from ranking.llm import MODELO, redactar

# verificar_cita y sin_digitos viven en ranking/verificacion.py desde que la
# Task 11 separó los verificadores de la llamada al modelo. El plan los
# importaba de ranking.llm, que es donde nacieron.
from ranking.verificacion import sin_digitos, verificar_cita

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def identidad():
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("EDGAR_IDENTITY no está en el entorno")
    from fundamentals.fetch import set_sec_identity

    set_sec_identity()


@pytest.fixture
def con_clave():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY no está en el entorno")


def test_edgar_entrega_el_item_1a_con_su_procedencia():
    """La única comprobación de que _descargar habla bien con edgartools.

    No gasta nada y no necesita clave de API: si algo se rompe en la biblioteca
    o en la SEC, este es el test que lo dice.
    """
    riesgos = cargar_riesgos("AAPL", refresh=True)

    assert riesgos is not None, "AAPL no devolvió Item 1A"
    assert riesgos.formulario == "10-K"
    assert riesgos.seccion == "Item 1A"
    assert riesgos.accession.count("-") == 2, riesgos.accession
    assert riesgos.caracteres_totales > 10_000, "sección sospechosamente corta"
    assert "risk" in riesgos.texto[:200].lower()


def test_el_tope_en_caracteres_no_se_pasa_del_presupuesto_de_tokens(con_clave):
    """El tope está en caracteres; el presupuesto real está en tokens.

    Se comprueba con count_tokens, que es lo único que cuenta tokens de Claude.
    Una regla de tres a 4 caracteres por token es una estimación, no una medida.

    JPM a propósito: su Item 1A mide 112.862 caracteres (medido el 2026-08-15),
    así que llega recortado al tope y ejerce el peor caso real del presupuesto.
    """
    import anthropic

    riesgos = cargar_riesgos("JPM", max_caracteres=MAX_CARACTERES)
    assert riesgos is not None
    assert riesgos.recortado, "JPM dejó de recortarse: el peor caso ya no es éste"

    cuenta = anthropic.Anthropic().messages.count_tokens(
        model=MODELO,
        messages=[{"role": "user", "content": riesgos.texto}],
    )
    assert cuenta.input_tokens < 25_000, (
        f"{cuenta.input_tokens} tokens con un tope de {MAX_CARACTERES} caracteres: "
        "ajusta MAX_CARACTERES en ranking/filings.py"
    )


def test_el_modelo_devuelve_el_esquema_y_cita_de_verdad(con_clave):
    """La llamada real: esquema, id del modelo y parámetros, todo a la vez.

    Si `thinking={"type": "disabled"}` no conviviera con `output_format=`, es
    aquí donde se ve. El plan dice qué hacer: quitar ese parámetro de
    ranking/llm.py —Sonnet 5 corre pensamiento adaptativo por defecto, cuesta
    algo más y funciona igual— y no inventar otra combinación sin comprobarla.
    """
    riesgos = cargar_riesgos("AAPL", max_caracteres=20_000)
    assert riesgos is not None

    resultado = redactar(
        "Empresa: AAPL, sector Information Technology.\n"
        "Frente a sus pares: calidad muy por encima de sus pares.",
        riesgos.texto,
    )

    assert resultado is not None, "la API o el esquema fallaron"
    assert resultado["riesgos"], "el modelo no devolvió ningún riesgo"

    # Las dos reglas duras del diseño, contra una respuesta de verdad y no
    # contra una que hayamos escrito nosotros: la cita aparece literalmente en
    # lo que se le envió, y no hay ni una cifra inventada en la prosa.
    for riesgo in resultado["riesgos"]:
        assert verificar_cita(riesgo["cita"], riesgos.texto) == riesgo["verificada"]
        assert sin_digitos(riesgo["afirmacion"]), riesgo["afirmacion"]
    assert sin_digitos(resultado["tesis"]), resultado["tesis"]
