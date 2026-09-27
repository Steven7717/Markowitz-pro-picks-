"""La descarga del SIE de Banxico, con la red simulada.

La respuesta tiene la forma que documenta el SIE. El test `red` del final es el
que comprueba que la forma real no ha cambiado y que los ids de serie son los
buenos.
"""

import io
import json
import os
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pytest

from noticias import cache
from seguimiento import banxico

TOKEN = "b2" * 32

RESPUESTA = {
    "bmx": {
        "series": [
            {
                "idSerie": "SF43718",
                "titulo": "Tipo de cambio Pesos por dólar E.U.A. FIX",
                "datos": [
                    {"fecha": "02/03/2026", "dato": "17.0500"},
                    {"fecha": "03/03/2026", "dato": "N/E"},
                    {"fecha": "04/03/2026", "dato": "1,017.2500"},
                ],
            }
        ]
    }
}


class _Red:
    """Un `urlopen` falso que apunta cada peticion."""

    def __init__(self, respuesta=RESPUESTA, error=None):
        self.respuesta, self.error, self.peticiones = respuesta, error, []

    def __call__(self, peticion, timeout):
        self.peticiones.append(peticion)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.respuesta).encode("utf-8"))


def _traer(tmp_path, red, **kw):
    return banxico.traer(
        banxico.SERIE_FIX, date(2026, 3, 1), date(2026, 3, 31), TOKEN,
        raiz=tmp_path, abrir=red, **kw,
    )


def test_parsear_lee_fechas_y_comas_y_descarta_n_e():
    serie = banxico.parsear(RESPUESTA)
    assert [d.date() for d in serie.index] == [date(2026, 3, 2), date(2026, 3, 4)]
    assert list(serie) == [17.05, 1017.25]


def test_parsear_con_una_fecha_repetida_se_queda_con_la_ultima():
    respuesta = {
        "bmx": {
            "series": [
                {
                    "idSerie": "SF43718",
                    "titulo": "x",
                    "datos": [
                        {"fecha": "02/03/2026", "dato": "17.0500"},
                        {"fecha": "02/03/2026", "dato": "18.0000"},
                    ],
                }
            ]
        }
    }
    serie = banxico.parsear(respuesta)
    assert [d.date() for d in serie.index] == [date(2026, 3, 2)]
    assert list(serie) == [18.0]


def test_sin_token_no_se_llama_a_la_red(tmp_path):
    red = _Red()
    resultado = banxico.traer(
        banxico.SERIE_FIX, date(2026, 3, 1), date(2026, 3, 31), None,
        raiz=tmp_path, abrir=red,
    )
    assert resultado.motivo == "sin_token"
    assert resultado.datos is None
    assert red.peticiones == []


def test_el_token_va_en_la_cabecera_y_nunca_en_la_url(tmp_path):
    red = _Red()
    _traer(tmp_path, red)
    peticion = red.peticiones[0]
    assert peticion.get_header("Bmx-token") == TOKEN
    assert TOKEN not in peticion.full_url
    assert peticion.full_url.endswith("/series/SF43718/datos/2026-03-01/2026-03-31")


def test_un_401_es_token_invalido(tmp_path):
    error = urllib.error.HTTPError("u", 401, "Unauthorized", None, None)
    assert _traer(tmp_path, _Red(error=error)).motivo == "token_invalido"


def test_sin_red_y_sin_cache_es_sin_red(tmp_path):
    resultado = _traer(tmp_path, _Red(error=urllib.error.URLError("caido")))
    assert resultado.motivo == "sin_red"
    assert resultado.datos is None


def test_una_respuesta_sin_la_forma_esperada_es_respuesta_rara(tmp_path):
    assert _traer(tmp_path, _Red(respuesta={"otra": 1})).motivo == "respuesta_rara"


def test_lo_descargado_se_guarda_y_la_segunda_vez_no_llama(tmp_path):
    red = _Red()
    primero = _traer(tmp_path, red)
    segundo = _traer(tmp_path, red)
    assert primero.motivo == segundo.motivo == "ok"
    assert len(red.peticiones) == 1
    assert list(segundo.datos) == [17.05, 1017.25]


def test_cache_caducada_y_red_caida_devuelve_la_cache_marcada_vieja(tmp_path):
    _traer(tmp_path, _Red())
    manana_pasado = datetime.now(timezone.utc) + timedelta(days=2)
    resultado = _traer(
        tmp_path, _Red(error=urllib.error.URLError("caido")), ahora=manana_pasado
    )
    assert resultado.motivo == "ok"
    assert resultado.vieja is True
    assert list(resultado.datos) == [17.05, 1017.25]


def test_el_inpc_vale_hasta_el_dia_10_del_mes_en_que_sale_el_siguiente():
    import pandas as pd
    agosto = pd.Series([140.0], index=pd.DatetimeIndex(["2026-08-01"]))
    diciembre = pd.Series([141.0], index=pd.DatetimeIndex(["2026-12-01"]))
    cuando = datetime(2026, 9, 12, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_INPC, agosto, cuando) == datetime(
        2026, 10, 10, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_INPC, diciembre, cuando) == datetime(
        2027, 2, 10, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_FIX, agosto, cuando) == cuando + timedelta(days=1)


def test_token_lee_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("BANXICO_TOKEN", f"  {TOKEN} ")
    assert banxico.token() == TOKEN
    monkeypatch.delenv("BANXICO_TOKEN")
    assert banxico.token() is None


@pytest.mark.red
def test_red_las_series_reales_tienen_la_forma_y_los_ids_buenos(tmp_path):
    clave = os.environ.get("BANXICO_TOKEN")
    if not clave:
        pytest.skip("sin BANXICO_TOKEN")
    hoy = date.today()
    fix = banxico.traer(banxico.SERIE_FIX, hoy - timedelta(days=30), hoy, clave,
                        raiz=tmp_path)
    inpc = banxico.traer(banxico.SERIE_INPC, hoy - timedelta(days=200), hoy, clave,
                         raiz=tmp_path)
    assert fix.motivo == "ok" and len(fix.datos) > 5
    # Pesos por dolar, no otra serie: un FIX fuera de este rango es un id malo.
    assert 10 < fix.datos.iloc[-1] < 40
    assert inpc.motivo == "ok" and len(inpc.datos) >= 4
    # Base 2Q jul 2018 = 100; hoy anda por encima de 130.
    assert 100 < inpc.datos.iloc[-1] < 300
