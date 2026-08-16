import pytest

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
)
from aprobacion.carga import Candidatos
from tests.test_aprobacion_carga import CORRIDA, FICHA


def candidatos(*tickers: str) -> Candidatos:
    fichas = [
        {**FICHA, "ticker": ticker, "puesto": posicion}
        for posicion, ticker in enumerate(tickers or ("AAA",), start=1)
    ]
    return Candidatos(fichas=fichas, corrida=CORRIDA)


def test_los_aprobados_llevan_su_ficha_y_su_puesto():
    acta = construir_acta(candidatos("AAA", "BBB"), aprobados={"AAA"})
    assert len(acta["aprobados"]) == 1
    entrada = acta["aprobados"][0]
    assert entrada["ticker"] == "AAA"
    assert entrada["origen"] == "ranking"
    assert entrada["puesto"] == 1
    assert entrada["ficha"]["sector_gics"] == "Information Technology"


def test_los_no_aprobados_tambien_llevan_su_ficha():
    # "Por que no tengo X" es tan buena pregunta como la contraria, y si con el
    # tiempo se descarta lo que el score pone arriba, eso dice algo del criterio.
    acta = construir_acta(candidatos("AAA", "BBB"), aprobados={"AAA"})
    assert [e["ticker"] for e in acta["no_aprobados"]] == ["BBB"]
    assert acta["no_aprobados"][0]["ficha"]["ticker"] == "BBB"


def test_el_anadido_a_mano_se_marca_y_no_finge_tener_ficha():
    acta = construir_acta(
        candidatos("AAA"),
        aprobados={"AAA"},
        anadidos=[Anadido(ticker="JPM", motivo="el criterio no evalua bancos")],
    )
    manual = [e for e in acta["aprobados"] if e["origen"] == "manual"][0]
    assert manual["ticker"] == "JPM"
    assert manual["ficha"] is None
    assert manual["puesto"] is None
    assert manual["motivo"] == "el criterio no evalua bancos"


def test_sin_motivo_no_hay_anadido_a_mano():
    # Un ticker sin ranking no tiene ningun respaldo cuantitativo: la razon
    # humana es la unica justificacion que va a existir.
    with pytest.raises(MotivoRequerido):
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="JPM", motivo="   ")])


def test_un_anadido_que_ya_esta_en_el_ranking_se_rechaza():
    # Deduplicar en silencio haria desaparecer el motivo escrito sin avisar.
    with pytest.raises(TickerDuplicado) as error:
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="AAA", motivo="da igual")])
    assert "AAA" in str(error.value)


def test_dos_anadidos_con_el_mismo_ticker_se_rechazan():
    # Sin esta guarda, JPM aparece dos veces en tickers_aprobados() y el
    # optimizador que lo consuma la pesaria dos veces sin que nadie lo note.
    with pytest.raises(TickerDuplicado) as error:
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="JPM", motivo="razon 1"),
                                 Anadido(ticker="JPM", motivo="razon 2")])
    assert "JPM" in str(error.value)


def test_un_ticker_con_forma_imposible_se_rechaza():
    with pytest.raises(TickerInvalido):
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="no es un ticker", motivo="x")])


def test_el_ticker_anadido_se_normaliza_a_mayusculas():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          anadidos=[Anadido(ticker=" brk-b ", motivo="x")])
    assert [e["ticker"] for e in acta["aprobados"]] == ["AAA", "BRK-B"]


def test_aprobar_una_lista_vacia_no_significa_nada():
    with pytest.raises(NadaQueAprobar):
        construir_acta(candidatos("AAA"), aprobados=set())


def test_el_motivo_distingue_un_descarte_de_un_no_mirado():
    # Las casillas nacen desmarcadas, asi que no marcar puede querer decir dos
    # cosas. El motivo escrito es lo unico que las separa.
    acta = construir_acta(
        candidatos("AAA", "BBB", "CCC"),
        aprobados={"AAA"},
        motivos={"BBB": "concentracion de clientes"},
    )
    por_ticker = {e["ticker"]: e for e in acta["no_aprobados"]}
    assert por_ticker["BBB"]["motivo"] == "concentracion de clientes"
    assert por_ticker["CCC"]["motivo"] is None


def test_el_acta_copia_la_corrida_entera():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    assert acta["corrida"] == CORRIDA


def test_el_acta_lleva_fecha_en_iso():
    from datetime import datetime

    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          ahora=datetime(2026, 8, 15, 18, 42))
    assert acta["fecha"] == "2026-08-15T18:42:00"
