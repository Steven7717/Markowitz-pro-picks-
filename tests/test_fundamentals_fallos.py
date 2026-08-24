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
    assert clasificar(_status(400)).causa == SYSTEMIC


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


def test_una_identidad_rechazada_llega_como_403_pelado():
    """SECIdentityError solo la levanta el parser SGML (camino de los
    filings); la API de facts no pasa por ahi. Convierte el 404 en
    CompanyFactsNotFoundError y deja pasar todo lo demas como httpx crudo, asi
    que una identidad que EDGAR rechaza aterriza aqui como un 403 pelado, no
    como SECIdentityError."""
    assert "correo de EDGAR" in clasificar(_status(403)).explicacion


@pytest.mark.parametrize(
    "excepcion",
    [
        CompanyFactsNotFoundError(cik=1),
        CompanyNotFoundError("AAA"),
        IdentityNotSetError(),
        SECIdentityError("rechazada"),
        TooManyRequestsError("u"),
        _ssl(),
        _status(403),
        _status(400),
        _status(503),
        httpx.ConnectTimeout("x"),
        ValueError("raro"),
    ],
)
def test_solo_las_sistemicas_traen_explicacion(excepcion):
    """Cubre cada renglon de clasificar, no solo dos casos sueltos: una causa
    que aborta con explicacion vacia renderizaria un mensaje sin razon, que es
    el resultado a medias y silencioso que este proyecto rechaza."""
    fallo = clasificar(excepcion)
    assert bool(fallo.explicacion) is fallo.aborta


def test_las_causas_cubiertas_por_la_explicacion_son_todas():
    """Cinturon y tirantes sobre el test anterior: si se agrega una causa
    nueva y se olvida un caso en esa parametrizacion, este test lo nota."""
    excepciones = [
        CompanyFactsNotFoundError(cik=1),
        CompanyNotFoundError("AAA"),
        IdentityNotSetError(),
        TooManyRequestsError("u"),
        _ssl(),
        _status(400),
        _status(503),
        ValueError("raro"),
    ]
    causas = {clasificar(exc).causa for exc in excepciones}
    assert causas == set(CAUSAS)


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
