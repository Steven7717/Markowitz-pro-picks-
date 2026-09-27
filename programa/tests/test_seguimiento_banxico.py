"""La descarga del SIE de Banxico, con la red simulada.

La respuesta tiene la forma que documenta el SIE. El test `red` del final es el
que comprueba que la forma real no ha cambiado y que los ids de serie son los
buenos.
"""

import http.client
import io
import json
import os
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pandas as pd
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


def test_una_lectura_incompleta_de_la_red_es_sin_red(tmp_path):
    error = http.client.IncompleteRead(b"")
    assert _traer(tmp_path, _Red(error=error)).motivo == "sin_red"


def test_una_serie_sin_datos_ni_nulo_es_respuesta_rara(tmp_path):
    # `"datos": None` hace que `.get("datos")` de un `None` en vez de faltar la
    # clave, y `None or []` lo cubriria -- pero un elemento `None` en la lista
    # de series (`"series": [None]`) no tiene ni `.get`: es un AttributeError.
    respuesta = {"bmx": {"series": [None]}}
    assert _traer(tmp_path, _Red(respuesta=respuesta)).motivo == "respuesta_rara"


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


def test_el_inpc_publicado_tarde_no_insiste_mas_de_un_dia():
    import pandas as pd
    agosto = pd.Series([140.0], index=pd.DatetimeIndex(["2026-08-01"]))
    # El dia 10 (limite normal) ya paso cuando se pregunta esto: Banxico se
    # retraso. Sin el suelo de "cuando + 1 dia", `traer` reintentaria la red
    # en cada rerun de Streamlit hasta que salga el dato.
    cuando = datetime(2026, 10, 12, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_INPC, agosto, cuando) == cuando + timedelta(days=1)


def test_una_serie_vacia_no_se_guarda_en_cache(tmp_path):
    # Un FIX de hoy que Banxico aun no publica esta manana viene vacio. Si se
    # guardara, quedaria "congelado" 24 horas y no se reintentaria hasta
    # manana aunque el dato ya este disponible en la red a media mañana.
    respuesta_vacia = {"bmx": {"series": [{"idSerie": "SF43718", "datos": []}]}}
    red = _Red(respuesta=respuesta_vacia)
    primero = _traer(tmp_path, red)
    segundo = _traer(tmp_path, red)
    assert primero.motivo == segundo.motivo == "ok"
    assert len(primero.datos) == 0 and len(segundo.datos) == 0
    assert len(red.peticiones) == 2


def test_un_fallo_al_guardar_en_cache_no_tira_la_descarga(tmp_path, monkeypatch):
    # Un disco lleno o sin permiso de escritura no es motivo para perder el
    # dato que ya se descargo: `traer` debe devolverlo igual, aunque la
    # proxima llamada tenga que volver a pedirlo a la red.
    def _guardar_roto(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(cache, "guardar", _guardar_roto)
    resultado = _traer(tmp_path, _Red())
    assert resultado.motivo == "ok"
    assert list(resultado.datos) == [17.05, 1017.25]


def test_de_plano_de_una_cache_vacia_tiene_indice_de_fechas():
    # Un dict vacio sin forzar el tipo del indice da un Index generico, y
    # `caduca` (con `len(datos)`) o cualquier `.date()` sobre el indice
    # reventaria con un TypeError si el indice no fuera de fechas.
    serie = banxico._de_plano({})
    assert isinstance(serie.index, pd.DatetimeIndex)


def test_parsear_descarta_nan_e_infinito_como_n_e():
    respuesta = {
        "bmx": {
            "series": [
                {
                    "idSerie": "SF43718",
                    "datos": [
                        {"fecha": "02/03/2026", "dato": "17.0500"},
                        {"fecha": "03/03/2026", "dato": "NaN"},
                        {"fecha": "04/03/2026", "dato": "inf"},
                    ],
                }
            ]
        }
    }
    serie = banxico.parsear(respuesta)
    assert [d.date() for d in serie.index] == [date(2026, 3, 2)]
    assert list(serie) == [17.05]


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
