# tests/test_macro_fuentes.py
import io
import urllib.error
from datetime import datetime, timezone

import pandas as pd
import pytest

from macro import fuentes

CSV_OCDE = (
    "DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,ADJUSTMENT,TRANSFORMATION,"
    "TIME_HORIZ,METHODOLOGY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,DECIMALS,BASE_PER\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-09,100.931,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-07,100.8179,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-08,100.8874,A,0,2,\n"
)
CSV_FRED = "observation_date,T10Y3M\n2026-11-11,\n2026-11-12,0.78\n2026-11-13,0.83\n"


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _abre(texto):
    def abrir(peticion, timeout):
        abrir.urls.append(peticion.full_url)
        return _Respuesta(texto.encode("utf-8"))

    abrir.urls = []
    return abrir


def _falla(error):
    def abrir(peticion, timeout):
        raise error

    return abrir


def test_parsear_cli_ordena_por_mes():
    serie = fuentes.parsear_cli(CSV_OCDE)
    assert list(serie.index.strftime("%Y-%m")) == ["2026-07", "2026-08", "2026-09"]
    assert serie.iloc[-1] == pytest.approx(100.931)


def test_parsear_fred_descarta_los_huecos():
    serie = fuentes.parsear_fred(CSV_FRED, "T10Y3M")
    assert list(serie) == [0.78, 0.83]


def test_la_url_del_cli_lleva_el_area_de_la_region(tmp_path):
    abrir = _abre(CSV_OCDE)
    fuentes.traer_cli("eurozona", raiz=tmp_path, abrir=abrir)
    assert "/G4E.M.LI...AA...H?" in abrir.urls[0]


def test_traer_cli_ok_y_la_segunda_vez_sale_de_la_cache(tmp_path):
    primera = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(CSV_OCDE))
    assert primera.motivo == "ok" and len(primera.datos) == 3
    segunda = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(AssertionError("red")))
    assert segunda.motivo == "ok" and not segunda.vieja
    assert list(segunda.datos) == list(primera.datos)


def test_sin_red_y_sin_cache_es_sin_red(tmp_path):
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(urllib.error.URLError("x")))
    assert r.datos is None and r.motivo == "sin_red"


def test_un_404_es_serie_desconocida(tmp_path):
    error = urllib.error.HTTPError("u", 404, "NoResultsFound", {}, None)
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(error))
    assert r.motivo == "serie_desconocida"


def test_un_csv_sin_columnas_es_respuesta_ilegible(tmp_path):
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre("<html>caído</html>"))
    assert r.motivo == "respuesta_ilegible"


def test_una_respuesta_vacia_es_serie_desconocida(tmp_path):
    cabecera = CSV_OCDE.splitlines()[0] + "\n"
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(cabecera))
    assert r.motivo == "serie_desconocida"


def test_con_la_red_caida_se_usa_la_cache_caducada_marcada(tmp_path):
    fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(CSV_OCDE))
    manana = datetime.now(timezone.utc) + fuentes.VALIDEZ * 2
    r = fuentes.traer_cli(
        "usa", raiz=tmp_path, abrir=_falla(urllib.error.URLError("x")), ahora=manana
    )
    assert r.motivo == "ok" and r.vieja is True and len(r.datos) == 3


def test_region_desconocida_revienta(tmp_path):
    with pytest.raises(KeyError):
        fuentes.traer_cli("marte", raiz=tmp_path, abrir=_abre(CSV_OCDE))


def test_traer_fred(tmp_path):
    abrir = _abre(CSV_FRED)
    r = fuentes.traer_fred("T10Y3M", raiz=tmp_path, abrir=abrir)
    assert r.motivo == "ok" and list(r.datos) == [0.78, 0.83]
    assert abrir.urls[0].endswith("fredgraph.csv?id=T10Y3M")
