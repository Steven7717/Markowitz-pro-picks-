import json
from datetime import datetime
from pathlib import Path

import pytest

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
    guardar_acta,
    tickers_aprobados,
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
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          ahora=datetime(2026, 8, 15, 18, 42))
    assert acta["fecha"] == "2026-08-15T18:42:00"


def test_el_acta_se_escribe_con_su_fecha_en_el_nombre(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          ahora=datetime(2026, 8, 15, 18, 42))
    destino = guardar_acta(acta, tmp_path)
    assert destino.name == "2026-08-15-184200.json"
    assert json.loads(destino.read_text(encoding="utf-8"))["fecha"] == acta["fecha"]


def test_dos_actas_en_el_mismo_segundo_no_se_pisan(tmp_path: Path):
    # El nombre resuelve hasta el segundo: dos aprobaciones muy seguidas
    # todavia pueden coincidir. La segunda debe llevarse un sufijo, no pisar
    # a la primera -- esa es la garantia que le importa al acta como registro.
    misma_marca = datetime(2026, 8, 15, 18, 42, 0)
    primera = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"}, ahora=misma_marca),
        tmp_path)
    segunda = guardar_acta(
        construir_acta(candidatos("BBB"), aprobados={"BBB"}, ahora=misma_marca),
        tmp_path)

    assert primera != segunda
    # La asercion que importa: el contenido de la primera acta sigue intacto,
    # no solo su nombre de fichero.
    assert json.loads(primera.read_text(encoding="utf-8"))["aprobados"][0]["ticker"] == "AAA"
    assert json.loads(segunda.read_text(encoding="utf-8"))["aprobados"][0]["ticker"] == "BBB"


def test_el_acta_sobrevive_a_que_B_se_vuelva_a_correr(tmp_path: Path):
    # La promesa entera del artefacto. Si esto no muerde, el resto es decorado.
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    destino = guardar_acta(acta, tmp_path)

    # B se corre otra vez y deja unas fichas completamente distintas.
    fichas_nuevas = [{**FICHA, "ticker": "ZZZ", "compuesto": -9.9}]
    (tmp_path / "fichas.json").write_text(
        json.dumps(fichas_nuevas), encoding="utf-8"
    )

    guardada = json.loads(destino.read_text(encoding="utf-8"))
    assert guardada["aprobados"][0]["ticker"] == "AAA"
    assert guardada["aprobados"][0]["ficha"]["compuesto"] == 1.42


def test_el_acta_es_json_estricto(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    acta["aprobados"][0]["ficha"]["compuesto"] = float("nan")
    with pytest.raises(ValueError):
        guardar_acta(acta, tmp_path)


def test_no_deja_temporales_a_medias(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    guardar_acta(acta, tmp_path)
    assert [p.suffix for p in tmp_path.iterdir()] == [".json"]


def test_una_escritura_que_truena_a_medias_no_toca_el_acta_ya_guardada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Lo unico que compra el patron tmp-then-replace: si la reescritura de un
    # nombre ya usado truena a mitad, el .json que ya estaba en disco no se
    # ve afectado, porque solo se llega a el via el replace() atomico.
    #
    # El bucle anti-colision de guardar_acta hace que, por la API publica, un
    # segundo guardado JAMAS apunte a un nombre que ya existe -- siempre
    # encuentra un "-2" libre. Para poner a prueba la garantia real hay que
    # forzar la misma carrera TOCTOU que reconoce el docstring de
    # guardar_acta: dos escrituras que ven el nombre libre a la vez porque
    # fichero.exists() miente. Sin este parche, esta prueba no distingue la
    # version correcta de la mutacion que quita el temporal (ver el reporte).
    misma_marca = datetime(2026, 8, 15, 18, 42, 0)
    buena = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"}, ahora=misma_marca),
        tmp_path,
    )

    monkeypatch.setattr(Path, "exists", lambda self: False)

    escritura_original = Path.write_text

    def disco_lleno(self: Path, *args, **kwargs):
        escritura_original(self, "a medias", encoding="utf-8")
        raise OSError("disco lleno (simulado)")

    monkeypatch.setattr(Path, "write_text", disco_lleno)

    with pytest.raises(OSError):
        guardar_acta(
            construir_acta(candidatos("BBB"), aprobados={"BBB"}, ahora=misma_marca),
            tmp_path,
        )

    assert json.loads(buena.read_text(encoding="utf-8"))["aprobados"][0]["ticker"] == "AAA"


def test_dos_actas_seguidas_no_se_pisan(tmp_path: Path):
    primera = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       ahora=datetime(2026, 8, 15, 18, 42)), tmp_path)
    segunda = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       ahora=datetime(2026, 8, 15, 19, 10)), tmp_path)
    assert primera != segunda
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_los_tickers_aprobados_incluyen_los_anadidos_a_mano():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          anadidos=[Anadido(ticker="JPM", motivo="x")])
    assert tickers_aprobados(acta) == ["AAA", "JPM"]
