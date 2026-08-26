import httpx
import pytest
from edgar.exceptions import (
    CompanyFactsNotFoundError,
    CompanyNotFoundError,
    IdentityNotSetError,
    NotFoundError,
    SECIdentityError,
    TooManyRequestsError,
)
from edgar.httprequests import SSLVerificationError

from fundamentals.fallos import (
    CAUSAS,
    NO_FACTS,
    SYSTEMIC,
    TRANSIENT,
    UNKNOWN,
    UNRESOLVED_CIK,
    clasificar,
)


def _status(codigo: int) -> httpx.HTTPStatusError:
    """Un HTTPStatusError igual al que levanta edgartools al mirar la respuesta."""
    peticion = httpx.Request(
        "GET", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    with pytest.raises(httpx.HTTPStatusError) as capturada:
        httpx.Response(codigo, request=peticion).raise_for_status()
    return capturada.value


def _ssl() -> SSLVerificationError:
    import ssl

    return SSLVerificationError(
        ssl.SSLError("certificate verify failed"), "https://data.sec.gov/x"
    )


# Fuente unica para las dos pruebas de cobertura de abajo: si se agrega una
# causa nueva a fallos.py y se olvida un caso aqui, ambas lo notan, porque
# ambas leen de esta misma lista en vez de mantener listas propias.
_CASOS = [
    (CompanyFactsNotFoundError(cik=1), NO_FACTS),
    (CompanyNotFoundError("AAA"), UNRESOLVED_CIK),
    (IdentityNotSetError(), SYSTEMIC),
    (SECIdentityError("rechazada"), SYSTEMIC),
    (TooManyRequestsError("u"), SYSTEMIC),
    (_ssl(), SYSTEMIC),
    (_status(401), SYSTEMIC),
    (_status(403), SYSTEMIC),
    (_status(400), SYSTEMIC),
    (_status(503), TRANSIENT),
    (httpx.ConnectTimeout("x"), TRANSIENT),
    (ValueError("raro"), UNKNOWN),
]


def test_una_empresa_sin_facts_no_es_un_fallo_de_descarga():
    """La SEC contesto: esa CIK existe y no tiene datos. Es permanente y suya."""
    assert clasificar(CompanyFactsNotFoundError(cik=320193)).causa == NO_FACTS


def test_un_ticker_sin_cik_va_a_su_propia_casilla():
    assert clasificar(CompanyNotFoundError("AAA")).causa == UNRESOLVED_CIK


def test_sin_facts_se_comprueba_antes_que_sin_cik():
    """CompanyFactsNotFoundError hereda de NotFoundError, igual que
    CompanyNotFoundError; si se invierte el orden, la primera se clasifica
    como la segunda y el informe cuenta mal."""
    assert isinstance(CompanyFactsNotFoundError(cik=1), NotFoundError)
    assert isinstance(CompanyNotFoundError("AAA"), NotFoundError)
    assert clasificar(CompanyFactsNotFoundError(cik=1)).causa == NO_FACTS


def test_un_keyerror_suelto_no_se_confunde_con_un_ticker_sin_cik():
    """KeyError tambien es LookupError. Clasificar por LookupError a secas
    haria que un fallo de pandas apareciera como 'sin CIK' en el informe."""
    assert clasificar(KeyError("period_end")).causa == UNKNOWN


def test_las_dos_formas_del_problema_de_identidad_abortan():
    """La libreria les da un padre comun a proposito: misma causa, mismo arreglo."""
    assert clasificar(IdentityNotSetError()).causa == SYSTEMIC
    assert clasificar(SECIdentityError("rechazada")).causa == SYSTEMIC


def test_una_identidad_rechazada_no_es_un_fallo_transitorio():
    """SECIdentityError ES un TransportError sin codigo HTTP, asi que caeria en
    el renglon generico y saldria transitoria si el orden fuera otro."""
    assert clasificar(SECIdentityError("rechazada")).causa != TRANSIENT


def test_la_explicacion_de_identidad_no_ofrece_reintentar():
    """IdentityNotSetError es un chequeo del lado del cliente
    (edgar/exceptions.py:316): no se envia ninguna peticion, asi que la libreria
    ya sabe que la causa es la identidad y ninguna otra. Sugerir 'espera y
    reintenta' ahi seria un remedio que no puede funcionar nunca: el usuario
    esperaria para siempre. Ese matiz solo tiene sentido en la version por
    codigo HTTP (401/403), donde la causa es una inferencia nuestra."""
    assert "reinténtalo" not in clasificar(IdentityNotSetError()).explicacion


def test_el_429_aborta_en_vez_de_reintentarse():
    """No es una guarda de orden: TooManyRequestsError lleva status_code=429,
    asi que el renglon generico de 4xx ya lo clasificaria sistemico aunque esta
    fila no existiera. Esta fila esta por el mensaje que trae, no por la
    clasificacion; la guarda real es el test de la explicacion del 429."""
    assert clasificar(TooManyRequestsError("https://data.sec.gov/x")).causa == SYSTEMIC


def test_un_fallo_de_certificado_aborta():
    """Guarda de orden: SSLVerificationError es un TransportError sin codigo
    HTTP. Quita este renglon y cae al generico de transporte, que la
    clasificaria transitoria."""
    assert clasificar(_ssl()).causa == SYSTEMIC


def test_un_4xx_aborta_porque_no_cambia_por_ticker():
    assert clasificar(_status(403)).causa == SYSTEMIC


def test_el_400_aborta_por_el_renglon_generico_de_4xx():
    """El renglon de identidad es 401/403, no un rango que incluya 400: si se
    ensanchara a `400 <= codigo <= 403` este test seguiria en verde a menos que
    tambien mirara el mensaje. 400 debe llevar el rechazo generico con su
    propio codigo, no el texto de identidad."""
    fallo = clasificar(_status(400))
    assert fallo.causa == SYSTEMIC
    assert "HTTP 400" in fallo.explicacion
    assert "correo de EDGAR" not in fallo.explicacion


def test_un_5xx_es_ambiguo_y_espera_a_repetirse():
    assert clasificar(_status(503)).causa == TRANSIENT


def test_el_500_es_ambiguo_y_espera_a_repetirse():
    """Frontera baja de la rama 5xx: un off-by-one a `400 <= codigo <= 500`
    haria que todo 500 abortara en el primer ticker, y nada lo detectaria."""
    assert clasificar(_status(500)).causa == TRANSIENT


def test_un_timeout_es_ambiguo_y_espera_a_repetirse():
    assert clasificar(httpx.ConnectTimeout("sin red")).causa == TRANSIENT


def test_lo_que_no_reconocemos_no_se_da_por_transitorio():
    assert clasificar(ValueError("algo raro")).causa == UNKNOWN


def test_una_identidad_rechazada_llega_como_401_o_403_pelado():
    """SECIdentityError solo la levanta el parser SGML (camino de los
    filings); la API de facts no pasa por ahi. Convierte el 404 en
    CompanyFactsNotFoundError y deja pasar todo lo demas como httpx crudo, asi
    que una identidad que EDGAR rechaza aterriza aqui como un 401 o 403
    pelado, no como SECIdentityError."""
    assert "correo de EDGAR" in clasificar(_status(401)).explicacion
    assert "correo de EDGAR" in clasificar(_status(403)).explicacion


def test_la_explicacion_de_identidad_por_estado_nombra_el_codigo():
    """El mensaje del 401/403 lleva su codigo HTTP porque ahi la causa es una
    inferencia nuestra sobre una respuesta ambigua: el codigo es el dato que
    se puede citar en un soporte. La version de IdentityError no lo necesita
    porque no hay codigo del que colgarse — la libreria ya dio el diagnostico."""
    assert "HTTP 401" in clasificar(_status(401)).explicacion
    assert "HTTP 403" in clasificar(_status(403)).explicacion


@pytest.mark.parametrize("excepcion, causa_esperada", _CASOS)
def test_solo_las_sistemicas_traen_explicacion(excepcion, causa_esperada):
    """Cubre cada renglon de clasificar, no solo dos casos sueltos: una causa
    que aborta con explicacion vacia renderizaria un mensaje sin razon, que es
    el resultado a medias y silencioso que este proyecto rechaza."""
    fallo = clasificar(excepcion)
    assert fallo.causa == causa_esperada
    assert bool(fallo.explicacion) is fallo.aborta


def test_las_causas_cubiertas_por_la_explicacion_son_todas():
    """Cinturon y tirantes sobre el test anterior: como ambos leen de _CASOS,
    agregar una causa nueva sin agregar un caso aqui hace fallar esta
    comprobacion de cobertura, no solo la parametrizacion de arriba."""
    assert {causa for _, causa in _CASOS} == set(CAUSAS)


def test_la_explicacion_del_429_dice_que_esperar_y_no_reintentar():
    texto = clasificar(TooManyRequestsError("u")).explicacion
    assert "10 minutos" in texto
    assert "alarga" in texto


def test_el_detalle_nombra_el_tipo_para_poder_citarlo():
    assert clasificar(httpx.ConnectTimeout("x")).detalle == "ConnectTimeout"
    assert clasificar(_status(503)).detalle == "HTTP 503"


@pytest.mark.parametrize(
    "excepcion, aborta, fuente_viva, cuenta_racha",
    [
        (TooManyRequestsError("u"), True, False, False),
        (CompanyFactsNotFoundError(cik=1), False, True, False),
        (CompanyNotFoundError("AAA"), False, False, False),
        (httpx.ConnectTimeout("x"), False, False, True),
        (ValueError("raro"), False, False, True),
    ],
)
def test_las_tres_preguntas_que_gobiernan_el_cortacircuitos(
    excepcion, aborta, fuente_viva, cuenta_racha
):
    """unresolved_cik es el caso sutil: no toca la red (sale del parquet
    empaquetado), asi que ni reinicia la racha ni la hace avanzar."""
    fallo = clasificar(excepcion)
    assert fallo.aborta is aborta
    assert fallo.fuente_viva is fuente_viva
    assert fallo.cuenta_racha is cuenta_racha
