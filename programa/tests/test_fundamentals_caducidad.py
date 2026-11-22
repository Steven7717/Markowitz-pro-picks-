"""La caducidad de la caché de la SEC: sub-proyecto Q.

`hoy` se pasa siempre a mano y el `mtime` de los ficheros se fija con
`os.utime`: ningún test depende del reloj real.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
import pytest

from fundamentals.fetch import (
    DIAS_ENTRE_COMPROBACIONES,
    DIAS_HASTA_INFORME_NUEVO,
    RACHA_MAXIMA,
    CorridaAbortada,
    _cache_path,
    caducado,
    load_facts,
    ultimo_cierre,
)

CIERRE = date(2025, 12, 31)


def _facts(ticker: str = "AAA", n: int = 12, ultimo: date = CIERRE) -> pd.DataFrame:
    """Tabla larga con la forma de facts.to_dataframe(); el último trimestre cierra en `ultimo`."""
    fechas = pd.date_range(end=pd.Timestamp(ultimo), periods=n, freq="QE")
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


def _envejecer(cache_dir: Path, ticker: str, dias: int, hoy: date) -> None:
    """Pone el mtime del fichero de `ticker` a `dias` días antes de `hoy`."""
    momento = datetime.combine(hoy - timedelta(days=dias), datetime.min.time()).timestamp()
    os.utime(_cache_path(cache_dir, ticker), (momento, momento))


# --- La regla ---------------------------------------------------------------


def test_las_constantes_son_las_del_spec():
    assert DIAS_HASTA_INFORME_NUEVO == 75
    assert DIAS_ENTRE_COMPROBACIONES == 7


def test_el_ultimo_cierre_es_el_period_end_mas_reciente():
    assert ultimo_cierre(_facts()) == CIERRE


def test_el_ultimo_cierre_ignora_filas_sin_periodo_trimestral_ni_anual():
    facts = _facts()
    rara = facts.iloc[[0]].copy()
    rara["period_end"] = pd.Timestamp("2030-01-01")
    rara["fiscal_period"] = None
    assert ultimo_cierre(pd.concat([facts, rara])) == CIERRE


def test_el_ultimo_cierre_cuenta_el_anual():
    facts = _facts()
    anual = facts.iloc[[0]].copy()
    anual["period_end"] = pd.Timestamp("2026-03-31")
    anual["fiscal_period"] = "FY"
    assert ultimo_cierre(pd.concat([facts, anual])) == date(2026, 3, 31)


def test_sin_cierre_medible_el_ultimo_cierre_es_none():
    assert ultimo_cierre(pd.DataFrame()) is None
    assert ultimo_cierre(_facts().assign(fiscal_period=None)) is None


@pytest.mark.parametrize(
    "dias_desde_cierre, dias_desde_descarga, esperado",
    [
        (74, 8, False),  # aún no toca informe nuevo
        (76, 6, False),  # se preguntó hace poco
        (76, 8, True),   # las dos condiciones
        (75, 8, False),  # el borde no cuenta: «más de 75»
        (76, 7, False),  # el borde no cuenta: «más de 7»
    ],
)
def test_caduca_solo_con_las_dos_condiciones(dias_desde_cierre, dias_desde_descarga, esperado):
    hoy = CIERRE + timedelta(days=dias_desde_cierre)
    descargado_el = hoy - timedelta(days=dias_desde_descarga)
    assert caducado(_facts(), descargado_el, hoy) is esperado


def test_un_fichero_sin_cierre_medible_no_caduca():
    hoy = CIERRE + timedelta(days=400)
    assert caducado(pd.DataFrame(), hoy - timedelta(days=30), hoy) is False


# --- Un ticker ---------------------------------------------------------------

HOY = CIERRE + timedelta(days=90)  # el cierre tiene 90 días: más de 75


def _sembrar(cache_dir: Path, tickers, dias: int = 10, hoy: date = HOY) -> None:
    """Escribe en caché los `tickers` y los envejece `dias` días."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)):
        load_facts(list(tickers), cache_dir=cache_dir, hoy=hoy)
    for ticker in tickers:
        _envejecer(cache_dir, ticker, dias, hoy)


def test_un_fichero_reciente_se_sirve_sin_red(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=3)
    with patch("fundamentals.fetch._fetch_facts") as red:
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    red.assert_not_called()
    assert cobertura.included == ["AAA"]
    assert cobertura.actualizadas == []
    assert cobertura.servidas_caducadas == []


def test_un_fichero_caducado_se_vuelve_a_pedir_y_se_reescribe(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=10)
    nuevo = _facts(ultimo=date(2026, 3, 31))
    with patch("fundamentals.fetch._fetch_facts", return_value=nuevo) as red:
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    red.assert_called_once_with("AAA")
    assert ultimo_cierre(hechos["AAA"]) == date(2026, 3, 31)
    assert cobertura.actualizadas == ["AAA"]
    assert cobertura.descargado_el["AAA"] == HOY.isoformat()


def test_un_caducado_cuya_descarga_falla_se_sirve_desde_la_cache(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert ultimo_cierre(hechos["AAA"]) == CIERRE
    assert cobertura.included == ["AAA"]
    assert cobertura.servidas_caducadas == ["AAA"]
    assert cobertura.failed_download == []
    assert cobertura.descargado_el["AAA"] == (HOY - timedelta(days=10)).isoformat()


def test_un_caducado_que_falla_no_toca_el_fichero(cache_dir):
    """Sin mtime nuevo, la próxima corrida lo vuelve a intentar."""
    _sembrar(cache_dir, ["AAA"], dias=10)
    antes = _cache_path(cache_dir, "AAA").stat().st_mtime
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")):
        load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert _cache_path(cache_dir, "AAA").stat().st_mtime == antes


def test_refresh_sigue_forzando_la_descarga_de_un_fichero_reciente(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=1)
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)) as red:
        load_facts(["AAA"], cache_dir=cache_dir, refresh=True, hoy=HOY)
    red.assert_called_once()


def test_sin_hoy_se_usa_la_fecha_de_hoy(cache_dir):
    """Un fichero recién escrito no caduca con la fecha real."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)):
        load_facts(["AAA"], cache_dir=cache_dir)
    with patch("fundamentals.fetch._fetch_facts") as red:
        load_facts(["AAA"], cache_dir=cache_dir)
    red.assert_not_called()


# --- Los cortacircuitos ------------------------------------------------------


def test_sin_red_y_con_todo_caducado_la_corrida_no_aborta(cache_dir):
    """Con la caché llena y sin conexión, todas tienen datos: ninguna se pierde."""
    tickers = [f"T{i:03d}" for i in range(RACHA_MAXIMA + 5)]
    _sembrar(cache_dir, tickers, dias=10)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as red:
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert sorted(hechos) == tickers
    assert cobertura.servidas_caducadas == tickers
    # Tras saltar el cortacircuitos deja de preguntar.
    assert red.call_count == RACHA_MAXIMA


def test_una_identidad_rechazada_en_un_caducado_tampoco_aborta(cache_dir):
    from tests.test_fundamentals_fetch import _status

    tickers = ["AAA", "BBB", "CCC"]
    _sembrar(cache_dir, tickers, dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)) as red:
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert sorted(hechos) == tickers
    assert cobertura.servidas_caducadas == tickers
    assert red.call_count == 1


def test_un_fallo_en_un_caducado_cuenta_para_la_racha(cache_dir):
    """Se preguntó a la red, así que cuenta. Tras los caducados, las que no
    tienen fichero abortan antes de llegar a RACHA_MAXIMA fallos propios."""
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    _sembrar(cache_dir, caducados, dias=10)
    nuevos = ["N001", "N002", "N003"]
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as red:
        with pytest.raises(CorridaAbortada) as error:
            load_facts(caducados + nuevos, cache_dir=cache_dir, hoy=HOY)
    assert red.call_count == RACHA_MAXIMA
    assert error.value.cobertura.failed_download == ["N001"]
    assert error.value.cobertura.servidas_caducadas == caducados


def test_en_modo_sin_red_una_empresa_sin_fichero_se_anota_sin_pedirla(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA)]
    _sembrar(cache_dir, caducados, dias=10)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as red:
        hechos, cobertura = load_facts(
            caducados + ["NUEVO"], cache_dir=cache_dir, hoy=HOY
        )
    assert sorted(hechos) == caducados
    assert cobertura.included == caducados
    assert cobertura.failed_download == ["NUEVO"]
    # Ni una petición para NUEVO: sólo las que dispararon el cortacircuitos.
    assert red.call_count == RACHA_MAXIMA


def test_el_orden_de_una_empresa_sin_fichero_no_cambia_el_resultado(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA + 5)]
    _sembrar(cache_dir, caducados, dias=10)
    resultados = []
    for orden in (["NUEVO"] + caducados, caducados + ["NUEVO"]):
        with patch(
            "fundamentals.fetch._fetch_facts",
            side_effect=httpx.ConnectTimeout("sin red"),
        ):
            _, cobertura = load_facts(orden, cache_dir=cache_dir, hoy=HOY)
        resultados.append(
            (sorted(cobertura.included), sorted(cobertura.failed_download))
        )
    assert resultados[0] == resultados[1]
    assert resultados[0] == (sorted(caducados), ["NUEVO"])


def test_con_identidad_rechazada_una_empresa_sin_fichero_tampoco_aborta(cache_dir):
    from tests.test_fundamentals_fetch import _status

    _sembrar(cache_dir, ["AAA"], dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)) as red:
        hechos, cobertura = load_facts(
            ["AAA", "NUEVO"], cache_dir=cache_dir, hoy=HOY
        )
    assert list(hechos) == ["AAA"]
    assert cobertura.failed_download == ["NUEVO"]
    assert red.call_count == 1


def test_el_motivo_de_sin_red_se_guarda(cache_dir):
    from tests.test_fundamentals_fetch import _status

    _sembrar(cache_dir, ["AAA", "BBB"], dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir, hoy=HOY)
    assert "identidad" in cobertura.motivo_sin_red


def test_sin_cortacircuitos_no_hay_motivo_de_sin_red(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert cobertura.motivo_sin_red is None


def test_un_caducado_que_da_404_se_marca_como_comprobado(cache_dir):
    """La SEC contestó: no se le vuelve a preguntar hasta dentro de una semana."""
    from edgar.exceptions import CompanyFactsNotFoundError

    _sembrar(cache_dir, ["AAA"], dias=10)
    antes = _cache_path(cache_dir, "AAA").stat().st_mtime
    with patch(
        "fundamentals.fetch._fetch_facts",
        side_effect=CompanyFactsNotFoundError(cik=1),
    ):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert "AAA" in hechos
    assert cobertura.servidas_caducadas == ["AAA"]
    assert _cache_path(cache_dir, "AAA").stat().st_mtime > antes


def test_en_modo_sin_red_los_recientes_siguen_saliendo_de_la_cache(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA)]
    _sembrar(cache_dir, caducados, dias=10)
    _sembrar(cache_dir, ["RECIENTE"], dias=1)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ):
        hechos, cobertura = load_facts(
            caducados + ["RECIENTE"], cache_dir=cache_dir, hoy=HOY
        )
    assert "RECIENTE" in hechos
    assert "RECIENTE" not in cobertura.servidas_caducadas


def test_un_exito_tras_caducados_fallidos_reinicia_la_racha(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    _sembrar(cache_dir, caducados, dias=10)

    def falla_salvo_ok(ticker):
        if ticker == "OK":
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    tickers = caducados + ["OK"] + [f"N{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_salvo_ok):
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert "OK" in hechos
    assert len(cobertura.failed_download) == RACHA_MAXIMA - 1


# --- El resumen ---------------------------------------------------------------

from fundamentals.fetch import CoverageReport, resumen_datos_sec


def test_el_resumen_dice_hasta_cuando_y_cuantas_se_actualizaron():
    cobertura = CoverageReport(
        requested=["AAA", "BBB", "CCC"],
        included=["AAA", "BBB", "CCC"],
        actualizadas=["AAA"],
        servidas_caducadas=["CCC"],
        descargado_el={"AAA": "2026-11-22", "BBB": "2026-11-20", "CCC": "2026-08-30"},
    )
    assert resumen_datos_sec(cobertura, "2026Q3") == {
        "ultimo_trimestre": "2026Q3",
        "descarga_mas_antigua": "2026-08-30",
        "descarga_mas_reciente": "2026-11-22",
        "actualizadas": 1,
        "servidas_caducadas": 1,
        "motivo_sin_red": None,
    }


def test_sin_cobertura_no_hay_resumen():
    assert resumen_datos_sec(None, "2026Q3") is None


def test_sin_fechas_el_resumen_no_inventa_ninguna():
    resumen = resumen_datos_sec(CoverageReport(), None)
    assert resumen["descarga_mas_antigua"] is None
    assert resumen["descarga_mas_reciente"] is None
    assert resumen["ultimo_trimestre"] is None
