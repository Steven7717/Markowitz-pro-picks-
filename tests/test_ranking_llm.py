import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import anthropic
import pytest
from pydantic import ValidationError

import ranking.llm as llm
from ranking.llm import (
    MAX_RIESGOS,
    MAX_TOKENS,
    SISTEMA,
    VERSION_PROMPT,
    Narrativa,
    Riesgo,
    clave_cache,
    redactar,
    redactar_con_cache,
    sin_digitos,
)
from ranking.verificacion import MAX_CARACTERES_CITA, MIN_CARACTERES_CITA

RAIZ_REPO = Path(__file__).resolve().parent.parent

FUENTE = (
    "Our business is subject to  intense competition.\n"
    "We depend on a limited number of suppliers for key components."
)


class ClienteFalso:
    """Devuelve las narrativas que se le den, una por llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        # spec= en los dos MagicMock: un método o atributo que redactar no
        # llama de verdad (un rename de parse->create, un narrativa.usage
        # que nadie definió) tiene que fallar con AttributeError, no
        # devolver un Mock silencioso que hace pasar el test por accidente.
        self.messages = MagicMock(spec=["parse"])
        self.messages.parse = self._parse

    def _parse(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return MagicMock(spec=["parsed_output"], parsed_output=siguiente)


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


def test_respuesta_sin_parsed_output_degrada_a_none():
    # Alcanzable de verdad: una respuesta cuyo único bloque no sea de texto
    # estructurado deja parsed_output en None. Sin este test la guarda era
    # robustez sin cobertura.
    cliente = ClienteFalso(None)
    assert redactar("contexto", FUENTE, cliente=cliente) is None
    assert len(cliente.llamadas) == 1


def test_una_afirmacion_vacia_no_sobrevive_al_reintento():
    # H1: una afirmación vacía (o de sólo espacios) con una cita real se
    # aceptaba en la primera pasada, sellada "verificada: true" sobre nada
    # —peor que la tesis vacía cerrada antes, porque a simple vista trae una
    # cita de verdad del filing. Invalida sólo ese riesgo, no la narrativa
    # entera: si sigue vacía tras el reintento, se descarta y se conserva
    # el resto (aquí, nada más que quede).
    vacio = Riesgo(
        afirmacion="",
        cita="We depend on a limited number of suppliers for key components",
    )
    solo_espacios = Riesgo(
        afirmacion="   ",
        cita="Our business is subject to intense competition",
    )
    primera = Narrativa(tesis="Negocio sólido", riesgos=[vacio, solo_espacios])
    segunda = Narrativa(tesis="Negocio sólido", riesgos=[vacio, solo_espacios])
    cliente = ClienteFalso(primera, segunda)
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado == {"tesis": "Negocio sólido", "riesgos": []}
    assert len(cliente.llamadas) == 2


def test_detecta_digitos_en_la_afirmacion_no_solo_en_la_tesis():
    # El spec pedía cifras fuera de la tesis Y de cada afirmación; sólo la
    # tesis tenía cobertura. Borrar el término de afirmacion en con_digitos
    # dejaba esto en verde sin que nada lo notara.
    riesgo_con_cifra = Riesgo(
        afirmacion="Los márgenes caen 30 puntos básicos",
        cita="depend on a limited number of suppliers",
    )
    con_cifra = Narrativa(tesis="Negocio sólido", riesgos=[riesgo_con_cifra])
    cliente = ClienteFalso(con_cifra, con_cifra)
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_el_reintento_explica_la_afirmacion_vacia():
    vacio = Riesgo(afirmacion="", cita="depend on a limited number of suppliers")
    primera = Narrativa(tesis="Negocio sólido", riesgos=[vacio])
    segunda = Narrativa(tesis="Negocio sólido", riesgos=[vacio])
    cliente = ClienteFalso(primera, segunda)
    redactar("contexto", FUENTE, cliente=cliente)
    segundo_envio = cliente.llamadas[1]["messages"][-1]["content"]
    assert "afirmación" in segundo_envio


def test_el_prompt_original_sobrevive_al_reintento():
    # El bug posible: `[] + [...]` en vez de `mensajes + [...]` en el
    # reintento manda al modelo a citar un texto que ya no ve.
    cliente = ClienteFalso(
        narrativa("cita inventada que no está"),
        narrativa("limited number of suppliers"),
    )
    redactar("contexto", FUENTE, cliente=cliente)
    primer_envio = cliente.llamadas[0]["messages"]
    segundo_envio = cliente.llamadas[1]["messages"]
    assert segundo_envio[0] == primer_envio[0]
    assert segundo_envio[0]["role"] == "user"
    assert "Empresa candidata" in segundo_envio[0]["content"]


def test_el_reintento_es_exactamente_uno():
    # El tope real no lo pone range(2) —intento == 1 decide, así que
    # range(2) -> range(3) no cambiaría nada— sino el propio contrato: un
    # cliente con tres respuestas en cola sólo debe recibir dos llamadas.
    cliente = ClienteFalso(
        narrativa("cita totalmente inventada y ausente, uno"),
        narrativa("cita totalmente inventada y ausente, dos"),
        narrativa("limited number of suppliers"),
    )
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert len(cliente.llamadas) == 2
    assert resultado["riesgos"][0]["verificada"] is False


def test_la_llamada_lleva_la_forma_esperada():
    # Nada fijaba system=, thinking=, output_format=, max_tokens= ni que se
    # respetara el parámetro modelo — todas esas mutaciones sobrevivían.
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    redactar("contexto", FUENTE, cliente=cliente, modelo="modelo-de-prueba")
    envio = cliente.llamadas[0]
    assert envio["model"] == "modelo-de-prueba"
    assert envio["max_tokens"] == MAX_TOKENS
    assert envio["system"] == SISTEMA
    assert envio["output_format"] is Narrativa
    assert envio["thinking"] == {"type": "disabled"}


def test_el_sistema_comunica_el_minimo_de_la_cita():
    # La enmienda 2 del diseño (mínimo de 25 caracteres) no se le había
    # comunicado nunca al modelo; ningún test importaba SISTEMA para
    # comprobarlo.
    assert "veinticinco" in SISTEMA


def test_tesis_de_solo_caracteres_invisibles_no_se_acepta():
    # str.strip() no ve el espacio de ancho cero (U+200B): no es whitespace
    # para Python aunque se lea vacío. "   ".strip() sí lo cazaba; esto no.
    cliente = ClienteFalso(
        Narrativa(tesis="\u200b", riesgos=[]),
        Narrativa(tesis="\u200b", riesgos=[]),
    )
    assert redactar("contexto", FUENTE, cliente=cliente) is None


def test_las_citas_se_verifican_contra_la_fuente_no_contra_el_prompt():
    # Barato de romper: mutar el verificar_cita(riesgo.cita, fuente) de
    # _a_dict —el que de verdad decide "verificada" en la salida— por algo
    # que incluyera el prompt completo ampliaría la falsa aceptación: una
    # cita tomada de la propia instrucción, no del filing, pasaría como
    # verificada. No está en `fuente`, así que la primera pasada cuenta
    # como fallo y hace falta una segunda respuesta para llegar al
    # resultado final.
    de_la_instruccion = narrativa("cada uno con su cita literal")
    cliente = ClienteFalso(de_la_instruccion, de_la_instruccion)
    resultado = redactar("contexto", FUENTE, cliente=cliente)
    assert resultado["riesgos"][0]["verificada"] is False


def test_el_sistema_avisa_que_las_cifras_de_empresa_candidata_no_se_copian():
    assert "Empresa candidata" in SISTEMA


def test_el_contexto_va_delimitado_igual_que_la_fuente():
    # Sin delimitar, el bloque "Empresa candidata" —lleno de cifras del
    # panel real en la Task 14— es indistinguible del resto del prompt y es
    # lo más copiable a la tesis.
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    redactar("un contexto con AAPL", FUENTE, cliente=cliente)
    prompt = cliente.llamadas[0]["messages"][0]["content"]
    assert "<<<\nun contexto con AAPL\n>>>" in prompt


def test_el_prompt_de_usuario_no_lleva_digitos():
    # {MAX_RIESGOS} se interpolaba como dígito literal ("3") en el turno de
    # usuario — el mismo riesgo de copiado que motivó escribir "doscientos"
    # y "veinticinco" en SISTEMA en vez de las cifras, pero sin cerrar aquí.
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    redactar("un contexto sin cifras", FUENTE, cliente=cliente)
    prompt = cliente.llamadas[0]["messages"][0]["content"]
    assert sin_digitos(prompt)


def test_el_eco_del_reintento_no_lleva_mas_de_max_riesgos():
    # El eco llevaba los diez riesgos aunque el código sólo verificó tres:
    # el modelo veía diez ecos y una queja sobre tres, sin señal de que el
    # resto se descartó.
    riesgos_de_sobra = [
        Riesgo(
            afirmacion=f"Riesgo marcado {letra}",
            cita="cita inventada que no aparece nunca en el filing",
        )
        for letra in "abcdefghij"
    ]
    primera = Narrativa(tesis="Negocio sólido", riesgos=riesgos_de_sobra)
    cliente = ClienteFalso(primera, narrativa("limited number of suppliers"))
    redactar("contexto", FUENTE, cliente=cliente)
    eco_assistant = cliente.llamadas[1]["messages"][1]["content"]
    assert eco_assistant.count("Riesgo marcado") == MAX_RIESGOS


# --- Task 12: caché de fichas por hash de contenido -----------------------


def _ruta_cache(directorio: Path, contexto: str, fuente: str, modelo: str = None) -> Path:
    modelo = modelo or llm.MODELO
    return directorio / f"{clave_cache(contexto, fuente, modelo, VERSION_PROMPT)}.json"


def test_la_clave_es_estable_entre_procesos():
    # hashlib, no hash(): Python aleatoriza el hash de strings entre
    # procesos. Llamar dos veces *en el mismo proceso* no prueba eso —
    # hash() también es estable dentro de un mismo proceso, así que ese
    # test pasaría igual con la implementación rota que dice descartar. Se
    # lanza un subproceso real y se compara con el proceso actual, que es lo
    # que el comentario original decía estar probando.
    primera = clave_cache("ctx", "fuente", "modelo", "b1")
    codigo = (
        "from ranking.llm import clave_cache\n"
        "print(clave_cache('ctx', 'fuente', 'modelo', 'b1'))"
    )
    proceso = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=RAIZ_REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    segunda = proceso.stdout.strip()
    assert primera == segunda
    assert len(primera) == 64


def test_la_clave_cambia_si_cambia_cualquier_pieza():
    base = clave_cache("ctx", "fuente", "modelo", "b1")
    assert clave_cache("otro", "fuente", "modelo", "b1") != base
    assert clave_cache("ctx", "otra", "modelo", "b1") != base
    assert clave_cache("ctx", "fuente", "otro", "b1") != base
    assert clave_cache("ctx", "fuente", "modelo", "b2") != base


def test_la_clave_incluye_el_sistema():
    # La Task 11 cambió SISTEMA dos veces sin que nada obligara a subir
    # VERSION_PROMPT a mano; si alguien lo cambia y se olvida, la caché
    # tenía que servir narrativas generadas bajo reglas viejas sin avisar.
    base = clave_cache("ctx", "fuente", "modelo", "b1", sistema="Reglas A")
    assert clave_cache("ctx", "fuente", "modelo", "b1", sistema="Reglas B") != base


def test_la_clave_por_defecto_usa_el_sistema_vigente_del_modulo():
    # Sin pasar sistema=, clave_cache tiene que usar el SISTEMA vigente —el
    # mismo que redactar() manda de verdad—, no un valor congelado aparte.
    assert clave_cache("ctx", "fuente", "modelo", "b1") == clave_cache(
        "ctx", "fuente", "modelo", "b1", sistema=SISTEMA
    )


def test_la_clave_incluye_el_minimo_de_caracteres_de_cita(monkeypatch):
    # La enmienda 2 del diseño cambió MIN_CARACTERES_CITA a mitad de este
    # sub-proyecto: una entrada de caché calculada bajo una cota vieja no es
    # una respuesta válida bajo la cota nueva, porque "verificada" depende
    # de esa cota y viaja horneada dentro del diccionario cacheado.
    base = clave_cache("ctx", "fuente", "modelo", "b1")
    monkeypatch.setattr(llm, "MIN_CARACTERES_CITA", MIN_CARACTERES_CITA + 1)
    assert clave_cache("ctx", "fuente", "modelo", "b1") != base


def test_la_clave_incluye_el_maximo_de_caracteres_de_cita(monkeypatch):
    base = clave_cache("ctx", "fuente", "modelo", "b1")
    monkeypatch.setattr(llm, "MAX_CARACTERES_CITA", MAX_CARACTERES_CITA + 1)
    assert clave_cache("ctx", "fuente", "modelo", "b1") != base


def test_la_segunda_corrida_no_vuelve_a_llamar(tmp_path: Path):
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    primera = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    segunda = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert primera == segunda
    assert len(cliente.llamadas) == 1


def test_no_cachea_los_fallos(tmp_path: Path):
    # Cachear un None congelaría un fallo transitorio para siempre.
    fallo = ClienteFalso(anthropic.APIConnectionError(request=MagicMock()))
    assert redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=fallo) is None
    # No basta con comprobar el resultado de la segunda llamada: _forma_valida
    # rechazaría un `null` cacheado igual que rechaza cualquier forma que no
    # sea la de una ficha, así que "escribir siempre, incluso en fallo" podría
    # colarse sin que la aserción de abajo lo note. Lo que fija de verdad
    # "no cachea los fallos" es que no se haya escrito nada en absoluto.
    assert list(tmp_path.glob("*.json")) == []

    bueno = ClienteFalso(narrativa("limited number of suppliers"))
    assert redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=bueno) is not None


def test_cache_corrupta_se_trata_como_fallo_y_se_regenera(tmp_path: Path):
    # Mismo trato que ranking/filings.py:_leer_cache da a un JSON truncado
    # por una corrida abortada a mitad de escritura: fallo de caché, no
    # error fatal, y se regenera.
    fichero = _ruta_cache(tmp_path, "ctx", FUENTE)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fichero.write_text("{esto no es json valido", encoding="utf-8")

    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert resultado is not None
    assert len(cliente.llamadas) == 1
    assert json.loads(fichero.read_text(encoding="utf-8")) == resultado


def test_cache_con_forma_inesperada_se_trata_como_fallo_y_se_regenera(tmp_path: Path):
    # JSON válido pero con otra forma —p.ej. un esquema de una versión
    # anterior de este módulo, o un riesgo sin "verificada"—: sin este
    # saneado, esto pasaría _leer_cache y reventaría más abajo con
    # KeyError en vez de tratarse como caché rota.
    fichero = _ruta_cache(tmp_path, "ctx", FUENTE)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fichero.write_text(
        json.dumps({"tesis": "de un esquema viejo sin riesgos"}), encoding="utf-8"
    )

    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert len(cliente.llamadas) == 1
    assert resultado["riesgos"][0]["verificada"] is True
    assert json.loads(fichero.read_text(encoding="utf-8")) == resultado


def test_cache_con_riesgo_sin_verificada_se_trata_como_fallo(tmp_path: Path):
    # Un riesgo con "afirmacion" y "cita" pero sin "verificada" es
    # exactamente lo que _a_dict nunca produce por sí solo: una forma que
    # sólo puede venir de un esquema distinto al actual.
    fichero = _ruta_cache(tmp_path, "ctx", FUENTE)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fichero.write_text(
        json.dumps(
            {
                "tesis": "Negocio sólido",
                "riesgos": [{"afirmacion": "a", "cita": "b"}],
            }
        ),
        encoding="utf-8",
    )

    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert len(cliente.llamadas) == 1
    assert resultado["riesgos"][0]["verificada"] is True


def test_cache_con_riesgos_que_no_es_una_lista_se_trata_como_fallo(tmp_path: Path):
    fichero = _ruta_cache(tmp_path, "ctx", FUENTE)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fichero.write_text(
        json.dumps({"tesis": "x", "riesgos": "no es una lista"}), encoding="utf-8"
    )

    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    resultado = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert len(cliente.llamadas) == 1
    assert resultado is not None


def test_una_ficha_con_riesgos_vacios_se_cachea_y_se_relee_igual(tmp_path: Path):
    # Forma válida en el extremo: riesgos=[] no debe confundirse con "forma
    # inesperada". Nace de test_una_afirmacion_vacia_no_sobrevive_al_reintento
    # en redactar(), que sí produce esta forma en producción.
    vacio = Riesgo(afirmacion="", cita="depend on a limited number of suppliers")
    primera = Narrativa(tesis="Negocio sólido", riesgos=[vacio])
    segunda = Narrativa(tesis="Negocio sólido", riesgos=[vacio])
    cliente = ClienteFalso(primera, segunda)
    resultado = redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    assert resultado == {"tesis": "Negocio sólido", "riesgos": []}

    releida = redactar_con_cache(
        "ctx", FUENTE, cache_dir=tmp_path, cliente=ClienteFalso()
    )
    assert releida == resultado


def test_cache_dir_que_no_se_puede_crear_falla_en_vez_de_devolver_algo_mal(
    tmp_path: Path,
):
    # La pregunta en frío: ¿qué pasa si cache_dir apunta a un sitio que no
    # se puede escribir? La respuesta no puede ser "una ficha equivocada
    # servida en silencio". Igual que la Task 9 dejó anotado que enmascarar
    # un fallo real de escritura acaba ocultando que la caché dejó de
    # funcionar (ver memoria "ranking-tests-que-no-fallan"), aquí se prefiere
    # reventar de forma ruidosa a degradar en silencio y pagar la llamada
    # cada vez sin que nadie lo note.
    bloqueado = tmp_path / "bloqueado"
    bloqueado.write_text("soy un fichero, no un directorio", encoding="utf-8")
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    with pytest.raises(OSError):
        redactar_con_cache("ctx", FUENTE, cache_dir=bloqueado, cliente=cliente)


def test_la_escritura_no_deja_ficheros_tmp_sueltos(tmp_path: Path):
    cliente = ClienteFalso(narrativa("limited number of suppliers"))
    redactar_con_cache("ctx", FUENTE, cache_dir=tmp_path, cliente=cliente)
    restos = list(tmp_path.glob("*.tmp"))
    assert restos == []
