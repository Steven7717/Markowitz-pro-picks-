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
    SIN_RESPUESTA_MAXIMO,
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


def _reloj_por_peticion(segundos: float):
    """time.monotonic falso donde cada intento de red cuesta `segundos`.

    _load_one lo llama dos veces por intento -- antes y despues de
    _fetch_facts -- asi que el reloj avanza en la segunda de cada par. Un
    acierto de cache no entra por ahi y no lo llama nunca, que es justo la
    propiedad que el tope de tiempo necesita y que el reloj de pared no daba.
    """
    estado = {"t": 0.0, "n": 0}

    def reloj():
        estado["n"] += 1
        if estado["n"] % 2 == 0:
            estado["t"] += segundos
        return estado["t"]

    return reloj


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


def test_un_sin_cik_en_medio_no_reinicia_la_racha(cache_dir):
    """La mitad sutil del invariante: no tocar la racha no es reiniciarla.

    Un ticker sin CIK se resuelve contra el parquet empaquetado, sin pedirle
    nada a la SEC, asi que no es evidencia ni a favor ni en contra. El test
    anterior prueba que no la avanza; este prueba que tampoco la reinicia --
    si lo hiciera, harian falta diez fallos MAS despues del hueco, no cinco,
    para abortar.
    """
    def sin_cik_en_medio(ticker):
        if ticker == "SINCIK":
            raise CompanyNotFoundError(ticker)
        raise httpx.ConnectTimeout("sin red")

    tickers = (
        [f"T{i:03d}" for i in range(5)]
        + ["SINCIK"]
        + [f"T{i:03d}" for i in range(5, 20)]
    )
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=sin_cik_en_medio
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts(tickers, cache_dir=cache_dir)
    # 5 fallos antes del hueco + el propio SINCIK + 5 fallos mas para llegar a
    # RACHA_MAXIMA. Si el hueco reiniciara la racha serian 5 + 1 + 10 = 16.
    assert pedido.call_count == RACHA_MAXIMA + 1


def test_el_ticker_que_dispara_el_aborto_queda_contado(cache_dir):
    """Suprimir el ticker que dispara el aborto reportaria un fallo sistemico
    junto a una cobertura vacia, como si nada se hubiera intentado siquiera."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert abortada.value.cobertura.failed_download == ["AAA"]


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


def test_una_racha_de_solo_desconocidos_dice_que_es_un_fallo_del_programa(cache_dir):
    """Diez KeyError seguidos no apuntan a la SEC: el mensaje debe decirlo.

    KeyError no es ninguna de las excepciones que `clasificar` reconoce, asi
    que cae en `unknown` -- el mismo camino que un `to_dataframe()` roto sobre
    un payload malformado.
    """
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=KeyError("valor inesperado")
    ) as pedido:
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert pedido.call_count == RACHA_MAXIMA
    assert "fallo del propio programa" in mensaje
    assert "no hay fuente" not in mensaje


def test_una_racha_mezclada_distingue_cuantos_de_cada_causa(cache_dir):
    """9 errores nuestros + 1 timeout de la SEC no pueden leerse igual que 10
    de cualquiera de los dos por separado.

    Los dos numeros salen distintos (9 y 1) a proposito: si el mensaje
    intercambiara `desconocidos` por `racha - desconocidos`, este test lo
    nota porque ninguna de las dos aserciones sobreviviria al canje.
    """
    def nueve_desconocidos_y_un_timeout(ticker):
        if ticker == "T009":
            raise httpx.ConnectTimeout("sin red")
        raise KeyError("valor inesperado")

    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=nueve_desconocidos_y_un_timeout
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "9 con" in mensaje
    assert "1 de la SEC" in mensaje


def test_un_404_en_medio_reinicia_tambien_el_contador_de_desconocidos(cache_dir):
    """El 404 ya reinicia `racha` (ver test_un_404_en_medio_reinicia_la_racha);
    esto prueba que arrastra a `desconocidos` con ella.

    Si no lo hiciera, los KeyError de antes del 404 seguirian contando en el
    diagnostico final aunque la racha que realmente dispara el aborto sea de
    puros timeouts, y el mensaje diria "mezclada" sobre una racha que no lo es.
    """
    def desconocidos_luego_sin_facts_luego_timeouts(ticker):
        if ticker == "SINFACTS":
            raise CompanyFactsNotFoundError(cik=1)
        if ticker.startswith("K"):
            raise KeyError("valor inesperado")
        raise httpx.ConnectTimeout("sin red")

    tickers = (
        [f"K{i:03d}" for i in range(5)]
        + ["SINFACTS"]
        + [f"T{i:03d}" for i in range(20)]
    )
    with patch(
        "fundamentals.fetch._fetch_facts",
        side_effect=desconocidos_luego_sin_facts_luego_timeouts,
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts(tickers, cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "no hay fuente" in mensaje
    assert "mezcladas" not in mensaje


def test_un_exito_de_red_en_medio_reinicia_tambien_el_contador_de_desconocidos(
    cache_dir,
):
    """El otro sitio que reinicia `racha` -- un acierto de red real -- tiene
    que arrastrar a `desconocidos` igual que el 404.

    Un acierto de cache no cuenta aqui a proposito (ver
    test_un_acierto_de_cache_no_reinicia_la_racha): este test usa una empresa
    nueva, sin fichero previo, para forzar el camino de descarga real.
    """
    def desconocidos_luego_exito_luego_timeouts(ticker):
        if ticker == "EXITOSO":
            return _facts(ticker)
        if ticker.startswith("K"):
            raise KeyError("valor inesperado")
        raise httpx.ConnectTimeout("sin red")

    tickers = (
        [f"K{i:03d}" for i in range(5)]
        + ["EXITOSO"]
        + [f"T{i:03d}" for i in range(20)]
    )
    with patch(
        "fundamentals.fetch._fetch_facts",
        side_effect=desconocidos_luego_exito_luego_timeouts,
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts(tickers, cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "no hay fuente" in mensaje
    assert "mezcladas" not in mensaje


def test_el_tope_de_tiempo_aborta_aunque_no_se_llegue_a_la_racha(cache_dir):
    """La SEC colgada: pocos tickers, mucho tiempo. La racha sola no lo acota.

    Cada intento cuesta 100 s, asi que el segundo acumula 200 s y pasa de
    SIN_RESPUESTA_MAXIMO mucho antes de que la racha llegue a diez.
    """
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ReadTimeout("colgada")
    ) as pedido, patch(
        "fundamentals.fetch._ahora", side_effect=_reloj_por_peticion(100.0)
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    assert pedido.call_count == 2
    assert "180" in str(abortada.value)


def test_los_aciertos_de_cache_no_cuentan_contra_el_tope_de_tiempo(cache_dir):
    """El defecto que motivo cobrar solo el tiempo dentro de la peticion.

    Midiendo reloj de pared, los tickers servidos de disco entre dos fallos
    metian en la cuenta el rato que la corrida paso leyendo parquet
    productivamente, y bastaban dos fallos separados para condenar una corrida
    sana culpando a la conexion. Cobrando solo la peticion, esos aciertos no
    llegan siquiera a mirar el reloj.

    Dos fallos de 50 s son 100 s, por debajo de los 180: no aborta. Las cuatro
    llamadas al reloj son dos por intento de red -- antes y despues -- y ni una
    por los 20 aciertos de cache de por medio.
    """
    cacheados = [f"C{i:03d}" for i in range(20)]
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(cacheados, cache_dir=cache_dir)

    reloj = Mock(side_effect=_reloj_por_peticion(50.0))
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ReadTimeout("colgada")
    ) as pedido, patch("fundamentals.fetch._ahora", reloj):
        _, cobertura = load_facts(
            ["NUEVO1"] + cacheados + ["NUEVO2"], cache_dir=cache_dir
        )

    assert pedido.call_count == 2
    assert reloj.call_count == 4
    assert len(cobertura.included) == 20
    assert cobertura.failed_download == ["NUEVO1", "NUEVO2"]


def test_una_corrida_entera_desde_cache_ni_mira_el_reloj(cache_dir):
    """Sin peticiones no hay tiempo que cobrar, ni llamada al reloj."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)

    reloj = Mock(return_value=99_999.0)
    with patch("fundamentals.fetch._fetch_facts") as ninguna, patch(
        "fundamentals.fetch._ahora", reloj
    ):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert ninguna.call_count == 0
    assert reloj.call_count == 0
    assert cobertura.included == ["AAA", "BBB"]


def test_un_exito_de_red_reinicia_el_tiempo_perdido(cache_dir):
    """Si la SEC vuelve, lo que se perdio antes no cuenta contra la corrida.

    Cada intento cuesta 100 s. Sin el reinicio: T000=100, T002=200 -> aborta
    en la tercera peticion. Con el reinicio: T000=100, T001 acierta y pone a
    cero, T002=100, T003=200 -> aborta en la cuarta.
    """
    def falla_salvo_el_segundo(ticker):
        if ticker == "T001":
            return _facts(ticker)
        raise httpx.ReadTimeout("colgada")

    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=falla_salvo_el_segundo
    ) as pedido, patch(
        "fundamentals.fetch._ahora", side_effect=_reloj_por_peticion(100.0)
    ):
        with pytest.raises(CorridaAbortada):
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    assert pedido.call_count == 4


def test_un_404_en_medio_reinicia_el_tiempo_perdido(cache_dir):
    """El otro sitio que reinicia -- un 404 -- tiene que arrastrarlo igual.

    Mismos numeros que test_un_exito_de_red_reinicia_el_tiempo_perdido, con
    un 404 en vez de un acierto en el punto que resetea.
    """
    def sin_facts_en_medio(ticker):
        if ticker == "T001":
            raise CompanyFactsNotFoundError(cik=1)
        raise httpx.ReadTimeout("colgada")

    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=sin_facts_en_medio
    ) as pedido, patch(
        "fundamentals.fetch._ahora", side_effect=_reloj_por_peticion(100.0)
    ):
        with pytest.raises(CorridaAbortada):
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    assert pedido.call_count == 4


def test_una_racha_de_solo_desconocidos_que_tarda_tambien_dice_fallo_del_programa(
    cache_dir,
):
    """El arreglo de 6068951 para _sin_fuente, alcanzando el camino lento.

    Un to_dataframe() roto solo revienta despues de descargar de verdad, asi
    que una racha 100% unknown no es gratis: puede tardar lo bastante para
    disparar el tope de tiempo en vez del de racha. Antes de compartir
    _diagnostico, _sin_respuesta tenia su propio texto fijo que decia
    "comprueba tu conexion" sin mirar nunca `desconocidos` -- exactamente la
    confusion que 6068951 le quito a _sin_fuente, alcanzando por el camino
    lento a su hermana.
    """
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=KeyError("valor inesperado")
    ), patch(
        "fundamentals.fetch._ahora", side_effect=_reloj_por_peticion(100.0)
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "fallo del propio programa" in mensaje
    assert "Comprueba tu conexión y si data.sec.gov responde." not in mensaje


def test_un_payload_que_no_se_deja_convertir_no_es_un_fallo_de_descarga(cache_dir):
    """La SEC entrego y no supimos leerlo: casilla propia, no failed_download.

    _fetch_facts envuelve el to_dataframe() en ParsingError justo porque ese
    punto es el unico donde se sabe que el payload llego. Sin esa etiqueta
    llegaria aqui como un `unknown` cualquiera.
    """
    from edgar.exceptions import ParsingError

    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=ParsingError("no convierte")
    ):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.unparseable == ["AAA"]
    assert cobertura.failed_download == []
    assert "ilegibles: 1" in cobertura.summary()


def test_una_cache_caliente_con_empresas_rotas_no_condena_la_corrida(cache_dir):
    """La regresion que encontro la revision final del conjunto.

    Un acierto de cache no rompe la racha -- correcto, no prueba que la SEC
    responda -- asi que con la cache caliente los unicos tickers que tocan la
    red son los que aun fallan, y unos fallos permanentes repartidos por el
    indice quedan adyacentes ENTRE SI. Medido antes del arreglo: 11 empresas
    con el payload roto, una cada 50 posiciones y la SEC sana, entraban 492 en
    la primera corrida y la segunda abortaba a la decima peticion diciendo que
    no habia fuente.

    Lo que lo arregla es que un payload ilegible prueba que la fuente entrego,
    asi que reinicia la racha en vez de avanzarla. Si alguien quita
    UNPARSEABLE de `Fallo.fuente_viva`, este test vuelve a rojo.
    """
    from edgar.exceptions import ParsingError

    universo = [f"T{i:03d}" for i in range(503)]
    rotos = {universo[i] for i in range(0, 503, 50)}

    def efecto(ticker):
        if ticker in rotos:
            raise ParsingError("payload malformado")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=efecto):
        _, primera = load_facts(universo, cache_dir=cache_dir)
    assert len(primera.included) == 503 - len(rotos)

    # Segunda pasada: las 492 buenas salen de cache y solo los 11 rotos tocan
    # la red, uno detras de otro. Antes del arreglo, esto abortaba.
    with patch("fundamentals.fetch._fetch_facts", side_effect=efecto) as pedido:
        _, segunda = load_facts(universo, cache_dir=cache_dir)
    assert pedido.call_count == len(rotos)
    assert len(segunda.included) == 503 - len(rotos)
    assert sorted(segunda.unparseable) == sorted(rotos)
