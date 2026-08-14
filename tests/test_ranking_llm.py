from unittest.mock import MagicMock

import anthropic
import pytest
from pydantic import ValidationError

from ranking.llm import (
    MAX_CARACTERES_CITA,
    MAX_RIESGOS,
    MIN_CARACTERES_CITA,
    Narrativa,
    Riesgo,
    redactar,
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


class ClienteFalso:
    """Devuelve las narrativas que se le den, una por llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.messages = MagicMock()
        self.messages.parse = self._parse

    def _parse(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return MagicMock(parsed_output=siguiente)


def narrativa(cita: str, tesis: str = "Negocio sólido y bien valorado") -> Narrativa:
    return Narrativa(
        tesis=tesis,
        riesgos=[Riesgo(afirmacion="Depende de pocos proveedores", cita=cita)],
    )


def test_devuelve_la_narrativa_con_la_cita_verificada():
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is True
    assert len(cliente.llamadas) == 1


def test_reintenta_una_vez_cuando_la_cita_no_aparece():
    cliente = ClienteFalso(
        narrativa("cita inventada que no está"),
        narrativa("limited number of suppliers"),
    )
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert len(cliente.llamadas) == 2
    assert resultado["riesgos"][0]["verificada"] is True


def test_tras_el_reintento_entrega_el_riesgo_marcado_no_lo_descarta():
    # Una afirmación sin respaldo que se ve es mejor que una que desaparece.
    cliente = ClienteFalso(narrativa("inventada"), narrativa("tambien inventada"))
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is False
    assert resultado["riesgos"][0]["afirmacion"] == "Depende de pocos proveedores"


def test_una_narrativa_con_cifras_se_rechaza_entera():
    # No podemos verificar un número; la regla era que los pone el código.
    cliente = ClienteFalso(
        narrativa("limited number of suppliers", tesis="Márgenes del 30%"),
        narrativa("limited number of suppliers", tesis="Márgenes del 30%"),
    )
    assert redactar("contexto", FUENTE, cliente=cliente) is None
    # El bug que había que arreglar: con las dos citas correctas, `fallidas`
    # queda vacía y el reintento original hablaba sólo de citas, sin decir
    # una palabra del problema real (el dígito). El segundo envío tiene que
    # nombrar el fallo verdadero.
    segundo_envio = cliente.llamadas[1]["messages"][-1]["content"]
    assert "dígito" in segundo_envio
    assert "no aparecen literalmente" not in segundo_envio


def test_un_error_de_api_degrada_a_none():
    cliente = ClienteFalso(anthropic.APIConnectionError(request=MagicMock()))
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_sin_clave_no_intenta_llamar(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert redactar("contexto", FUENTE) is None


def test_no_manda_temperature_ni_prefill():
    # Sonnet 5 rechaza temperature y el prefill de turno final. La propiedad
    # que importa es la del reintento: ahí es donde un mensaje que terminara
    # en turno "assistant" (el eco de la narrativa fallida) sería un prefill
    # de verdad. Por eso se comprueban las dos llamadas, no sólo la primera
    # —donde la aserción se cumple sola porque no hay nada más que un turno
    # de usuario.
    cliente = ClienteFalso(
        narrativa("cita inventada que no está"),
        narrativa("limited number of suppliers"),
    )
    redactar("contexto", FUENTE, cliente=cliente)
    assert len(cliente.llamadas) == 2
    for envio in cliente.llamadas:
        assert "temperature" not in envio
        assert envio["messages"][-1]["role"] == "user"


def test_una_cita_con_cifras_que_verifica_se_acepta():
    # sin_digitos se aplica a la tesis y a la afirmación, nunca a la cita: la
    # cita es texto literal del filing y puede llevar cifras que son de la
    # empresa, no inventadas por el modelo. Nada lo fijaba con un test, así
    # que quedaba abierto a que alguien lo "arreglara" rompiendo el módulo.
    fuente_con_cifras = FUENTE + "\nOur 2024 supplier count fell to three."
    cliente = ClienteFalso(narrativa("Our 2024 supplier count fell to three"))
    resultado = redactar("contexto", fuente_con_cifras, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is True


def test_una_narrativa_vacia_no_se_acepta_como_valida():
    # La pregunta en frío: ¿qué acepta redactar que no debería? Una
    # Narrativa(tesis="", riesgos=[]) pasa las dos verificaciones tal como
    # estaban escritas —ninguna cifra, y ninguna cita fallida porque no hay
    # ninguna cita— y salía con aspecto de ficha válida sin llevar nada
    # dentro. Se cierra tratando la tesis vacía igual que los dígitos: se
    # reintenta una vez y, si sigue vacía, se degrada a None.
    cliente = ClienteFalso(
        Narrativa(tesis="", riesgos=[]),
        Narrativa(tesis="   ", riesgos=[]),
    )
    assert redactar("contexto", FUENTE, cliente=cliente) is None
    assert len(cliente.llamadas) == 2


def test_max_riesgos_limita_los_riesgos_devueltos():
    # El prompt pide "hasta tres", pero nada en el código lo hacía cumplir:
    # si el modelo devolvía diez, salían los diez.
    riesgos_de_sobra = [
        Riesgo(afirmacion=f"Riesgo marcado {letra}", cita="limited number of suppliers")
        for letra in "abcdefghij"
    ]
    cliente = ClienteFalso(Narrativa(tesis="Negocio sólido", riesgos=riesgos_de_sobra))
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert len(resultado["riesgos"]) == MAX_RIESGOS
    assert len(riesgos_de_sobra) > MAX_RIESGOS  # el test no es trivial


def test_un_fallo_de_validacion_de_pydantic_degrada_a_none():
    # messages.parse valida contra el esquema; una respuesta que no encaja no
    # sube como anthropic.APIError, y sin cazarla aparte se escapaba y
    # abortaba la corrida entera de la Task 14 por una sola empresa.
    try:
        Narrativa.model_validate({"tesis": "sin riesgos"})
        raise AssertionError("se esperaba que faltara 'riesgos'")
    except ValidationError as excepcion:
        error_de_validacion = excepcion
    cliente = ClienteFalso(error_de_validacion)
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_un_error_inesperado_no_se_traga():
    # Decisión: sólo anthropic.APIError y pydantic.ValidationError degradan
    # en silencio, porque son los dos fallos que esta función sabe nombrar.
    # Cualquier otra excepción —un bug real, un modo de fallo que nadie
    # documentó— sube: reventar es mejor que degradar sin dejar rastro.
    cliente = ClienteFalso(RuntimeError("fallo que no debería tragarse"))
    with pytest.raises(RuntimeError):
        redactar("contexto", FUENTE, cliente=cliente)
