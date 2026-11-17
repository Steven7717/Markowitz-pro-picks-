# programa/tests/test_riesgo_datos.py
import numpy as np
import pandas as pd

from riesgo import datos


def _descarga_falsa(precios):
    def fake(tickers, **kw):
        assert kw["interval"] == "1d" and kw["period"] == datos.PERIODO_DIARIO
        return pd.concat({"Close": precios[tickers]}, axis=1)
    return fake


def test_descarga_diaria_y_devuelve_retornos_comunes(monkeypatch):
    idx = pd.bdate_range("2022-01-03", periods=6)
    precios = pd.DataFrame({"AAA": [10, 11, 12, 11, 12, 13.0],
                            "BBB": [np.nan, np.nan, 20, 21, 22, 23.0]}, index=idx)
    monkeypatch.setattr(datos.yf, "download", _descarga_falsa(precios))
    salida = datos.retornos_diarios.__wrapped__(("AAA", "BBB"))
    assert list(salida["retornos"].columns) == ["AAA", "BBB"]
    assert len(salida["retornos"]) == 3          # sólo donde cotizan los dos
    assert salida["sesiones"] == {"AAA": 6, "BBB": 4}


def test_un_solo_ticker_sin_multiindex(monkeypatch):
    idx = pd.bdate_range("2022-01-03", periods=4)
    crudo = pd.DataFrame({"Close": [10, 11, 12, 13.0]}, index=idx)
    monkeypatch.setattr(datos.yf, "download", lambda *a, **k: crudo)
    salida = datos.retornos_diarios.__wrapped__(("AAA",))
    assert list(salida["retornos"].columns) == ["AAA"]
    assert salida["sesiones"] == {"AAA": 4}
