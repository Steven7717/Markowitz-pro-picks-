from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pandas as pd
import pytest
from edgar.exceptions import (
    CompanyFactsNotFoundError,
    CompanyNotFoundError,
    TooManyRequestsError,
)

from fundamentals.fetch import (
    RACHA_MAXIMA,
    CorridaAbortada,
    CoverageReport,
    _cache_path,
    _fetch_facts,
    load_facts,
)


def _facts(ticker: str, n: int = 12) -> pd.DataFrame:
    """Tabla larga con la forma que devuelve facts.to_dataframe()."""
    fechas = pd.date_range("2023-03-31", periods=n, freq="QE")
    return pd.DataFrame(
        {
            "concept": ["us-gaap:Revenues"] * n,
            "value": [str(100.0 + i) for i in range(n)],
            "numeric_value": [100.0 + i for i in range(n)],
            "unit": ["USD"] * n,
            "period_type": ["duration"] * n,
            "period_start": fechas - pd.Timedelta(days=89),
            "period_end": fechas,
            "fiscal_year": [f.year for f in fechas],
            "fiscal_period": [f"Q{(f.month - 1) // 3 + 1}" for f in fechas],
        }
    )


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_returns_facts_per_ticker_and_a_coverage_report(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        hechos, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert sorted(hechos) == ["AAA", "BBB"]
    assert isinstance(cobertura, CoverageReport)
    assert cobertura.included == ["AAA", "BBB"]


def test_un_ticker_sin_cik_se_reporta_aparte_de_un_fallo_de_red(cache_dir):
    """Un ticker que no existe y una caida de SEC son problemas distintos.

    Medido durante el diseno: AEP no aparece en el mapa oficial ticker->CIK de
    SEC. Confundirlo con un fallo de red esconderia una caida real.
    """
    def falla(ticker):
        if ticker == "BBB":
            raise CompanyNotFoundError("BBB")
        raise httpx.ConnectTimeout("boom")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert cobertura.unresolved_cik == ["BBB"]
    assert cobertura.failed_download == ["AAA"]


def test_un_ticker_que_falla_solo_se_registra_y_no_aborta_la_corrida(cache_dir):
    """La politica que este cambio NO toca.

    El reintento de lo transitorio se delega en edgartools, que hace 5 intentos
    con backoff y sabe cuales no reintentar. Testear eso aqui seria testear la
    libreria; lo que si es nuestro es que un fallo aislado no tumbe la corrida.
    """
    def uno_falla(ticker):
        if ticker == "BBB":
            raise httpx.ConnectTimeout("tropiezo")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=uno_falla):
        hechos, cobertura = load_facts(["AAA", "BBB", "CCC"], cache_dir=cache_dir)
    assert sorted(hechos) == ["AAA", "CCC"]
    assert cobertura.failed_download == ["BBB"]


def test_no_se_duerme_entre_tickers(cache_dir):
    """Los 25 minutos eran 3 s por ticker de time.sleep nuestro, 503 veces."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")), \
         patch("fundamentals.fetch.time.sleep") as siesta:
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert siesta.call_count == 0


def test_una_empresa_sin_facts_va_a_su_casilla_y_no_a_la_de_descarga(cache_dir):
    def sin_facts(ticker):
        raise CompanyFactsNotFoundError(cik=1)

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_facts):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.no_facts == ["AAA"]
    assert cobertura.failed_download == []


def test_the_second_call_reads_from_cache_without_downloading(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts) as primera:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert primera.call_count == 1

    with patch("fundamentals.fetch._fetch_facts") as segunda:
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert segunda.call_count == 0
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_a_corrupted_cache_file_is_recovered_by_re_downloading(cache_dir):
    """Una corrida matada a media escritura deja un parquet truncado.

    Es el defecto que envenenaba todas las corridas siguientes en el estudio D.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    fichero = next(cache_dir.glob("*.parquet"))
    fichero.write_bytes(b"not a valid parquet file")

    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.included == ["AAA"]
    assert not hechos["AAA"].empty


def test_the_cached_frame_survives_the_round_trip(cache_dir):
    """Si el parquet pierde columnas, el panel sale vacio en la segunda corrida."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        primero, _ = load_facts(["AAA"], cache_dir=cache_dir)
    with patch("fundamentals.fetch._fetch_facts"):
        segundo, _ = load_facts(["AAA"], cache_dir=cache_dir)

    esperadas = {"concept", "numeric_value", "period_type", "period_start", "period_end"}
    assert esperadas <= set(segundo["AAA"].columns)
    assert len(segundo["AAA"]) == len(primero["AAA"])


def test_the_cache_key_does_not_depend_on_process_local_hashing(cache_dir):
    """Python aleatoriza el hash de strings entre procesos; una clave asi nunca acierta."""
    import hashlib

    esperado = hashlib.md5(b"AAA").hexdigest()[:12]
    assert _cache_path(cache_dir, "AAA").name == f"facts_{esperado}.parquet"


def test_each_ticker_is_cached_separately(cache_dir):
    """Los trimestrales llegan escalonados; una cache por universo se invalidaria entera."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert len(list(cache_dir.glob("*.parquet"))) == 2


def test_refresh_bypasses_the_cache_and_downloads_again(cache_dir):
    """Refrescar tiene que ser posible sin borrar ficheros a mano."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts) as otra:
        load_facts(["AAA"], cache_dir=cache_dir, refresh=True)
    assert otra.call_count == 1


def test_refresh_is_off_by_default(cache_dir):
    """Un refresco automatico cambiaria los numeros entre dos corridas sin avisar."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts") as ninguna:
        load_facts(["AAA"], cache_dir=cache_dir)
    assert ninguna.call_count == 0


def test_coverage_summary_names_every_category(cache_dir):
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    resumen = cobertura.summary()
    for etiqueta in ("solicitados", "incluidos", "sin CIK", "sin sector", "sin precio"):
        assert etiqueta in resumen


def test_el_resumen_cuenta_las_empresas_sin_hechos_aparte(cache_dir):
    """Una empresa que existe y no tiene facts no es una caida de red."""
    cobertura = CoverageReport(requested=["AAA"], no_facts=["AAA"])
    assert "sin hechos: 1" in cobertura.summary()


def test_un_ticker_sin_cik_deja_pasar_la_excepcion_de_la_libreria():
    """Envolverla en LookupError solo perdia informacion: clasificar ya la lee."""
    with patch("edgar.Company", side_effect=CompanyNotFoundError("AAA")):
        with pytest.raises(CompanyNotFoundError):
            _fetch_facts("AAA")


def test_una_caida_de_red_al_resolver_el_cik_no_se_disfraza_de_sin_cik():
    """Lo que hacia el `except Exception` que habia aqui: un corte de red
    acababa contado como 'este ticker no existe'."""
    with patch("edgar.Company", side_effect=httpx.ConnectTimeout("sin red")):
        with pytest.raises(httpx.ConnectTimeout):
            _fetch_facts("AAA")


def test_una_empresa_sin_facts_deja_pasar_el_404_de_la_libreria():
    """get_company_facts la levanta sola; no hay que sintetizarla."""
    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", side_effect=CompanyFactsNotFoundError(cik=320193)
    ):
        with pytest.raises(CompanyFactsNotFoundError):
            _fetch_facts("AAA")


def test_un_cuerpo_vacio_no_se_confunde_con_una_empresa_sin_hechos():
    """El defecto que habria desarmado el cortacircuitos entero.

    ESTE TEST SOSTIENE LA CORRECCION DE fallos.fuente_viva, no es incidental.
    Esa propiedad solo es cierta porque _fetch_facts pasa por
    get_company_facts; ningun test de test_fundamentals_fallos.py puede
    protegerlo, porque el acoplamiento cruza el borde entre los dos modulos.
    Si alguien devuelve _fetch_facts a Entity.get_facts(), este es el unico
    sitio donde salta.

    get_company_facts devuelve None por dos motivos que no son un 404: una
    descarga que falla en blando y un parseo que no cuaja. Contar eso como
    no_facts pondria fuente_viva a True y reiniciaria la racha en cada ticker,
    asi que con la SEC sirviendo cuerpos vacios la corrida no abortaria nunca.
    """
    from edgar.exceptions import TransportError

    from fundamentals.fallos import clasificar

    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", return_value=None
    ):
        with pytest.raises(TransportError) as levantada:
            _fetch_facts("AAA")
    assert clasificar(levantada.value).cuenta_racha is True
    assert clasificar(levantada.value).fuente_viva is False


def test_el_camino_feliz_pide_los_hechos_por_el_cik_que_resolvio():
    """Resolver el ticker y pedir los hechos POR ESE CIK es el eje del diseno.

    Sin el assert_called_once_with, esto lo pasaban por igual tres versiones
    rotas de _fetch_facts -- get_company_facts(ticker), (company) y (0) --
    porque patch(return_value=...) acepta cualquier argumento y el Mock(cik=)
    era pura decoracion. Medido con mutantes, no supuesto.
    """
    hechos = Mock()
    hechos.to_dataframe.return_value = _facts("AAA")
    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", return_value=hechos
    ) as pedido:
        assert len(_fetch_facts("AAA")) == 12
    pedido.assert_called_once_with(320193)


def _status(codigo: int) -> httpx.HTTPStatusError:
    """Un HTTPStatusError igual al que levanta edgartools al mirar la respuesta."""
    peticion = httpx.Request("GET", "https://data.sec.gov/x")
    with pytest.raises(httpx.HTTPStatusError) as capturada:
        httpx.Response(codigo, request=peticion).raise_for_status()
    return capturada.value


def test_una_identidad_rechazada_aborta_en_el_primer_ticker(cache_dir):
    """Es global por definicion: no hace falta esperar a que se repita 503 veces.

    Llega como un 403 pelado y no como SECIdentityError: esa solo la levanta el
    parser de SGML, que es el camino de los filings, no el de los facts.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)) as pedido:
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(503)], cache_dir=cache_dir)
    assert pedido.call_count == 1
    assert "correo de EDGAR" in str(abortada.value)


def test_el_429_no_se_reintenta_porque_reintentarlo_alarga_el_bloqueo(cache_dir):
    with patch(
        "fundamentals.fetch._fetch_facts",
        side_effect=TooManyRequestsError("https://data.sec.gov/x"),
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert pedido.call_count == 1


def test_diez_fallos_seguidos_sin_respuesta_abortan_la_corrida(cache_dir):
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts([f"T{i:03d}" for i in range(50)], cache_dir=cache_dir)
    assert pedido.call_count == RACHA_MAXIMA


def test_nueve_fallos_y_un_acierto_no_abortan(cache_dir):
    """Un solo exito rompe la racha: un fallo aislado nunca dispara nada."""
    def falla_salvo_el_decimo(ticker):
        if ticker == "T009":
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_salvo_el_decimo):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(19)], cache_dir=cache_dir
        )
    assert cobertura.included == ["T009"]
    assert len(cobertura.failed_download) == 18


def test_un_404_en_medio_reinicia_la_racha(cache_dir):
    """La SEC contesto: la fuente esta viva aunque esa empresa no tenga datos."""
    def sin_facts_en_medio(ticker):
        if ticker == "T005":
            raise CompanyFactsNotFoundError(cik=1)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_facts_en_medio):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(15)], cache_dir=cache_dir
        )
    assert cobertura.no_facts == ["T005"]
    assert len(cobertura.failed_download) == 14


def test_un_acierto_de_cache_no_reinicia_la_racha(cache_dir):
    """Un fichero leido de disco no dice nada sobre si la SEC responde.

    Si contara como exito, una cache a medio poblar apagaria el cortacircuitos:
    con 200 de 503 en disco, la racha no llegaria nunca a diez.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["CACHEADO"], cache_dir=cache_dir)

    tickers = (
        [f"T{i:03d}" for i in range(5)]
        + ["CACHEADO"]
        + [f"T{i:03d}" for i in range(5, 20)]
    )
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts(tickers, cache_dir=cache_dir)
    assert pedido.call_count == RACHA_MAXIMA


def test_un_ticker_sin_cik_ni_avanza_ni_reinicia_la_racha(cache_dir):
    """Se resuelve contra el parquet empaquetado, sin pedirle nada a la SEC."""
    def sin_cik(ticker):
        raise CompanyNotFoundError(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_cik):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(30)], cache_dir=cache_dir
        )
    assert len(cobertura.unresolved_cik) == 30


def test_la_excepcion_dice_la_causa_y_cuanto_se_llego_a_bajar(cache_dir):
    def falla_tras_dos(ticker):
        if ticker in ("T000", "T001"):
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_tras_dos):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(50)], cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "2 de 50" in mensaje
    assert "ConnectTimeout" in mensaje
    assert abortada.value.cobertura.included == ["T000", "T001"]
