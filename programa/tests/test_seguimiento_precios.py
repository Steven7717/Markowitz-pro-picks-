import pandas as pd
import pytest

from seguimiento import precios


def panel(datos: dict) -> pd.DataFrame:
    """Un DataFrame con la forma que devuelve yfinance: columnas (campo, ticker)."""
    return pd.DataFrame(
        datos,
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
    )


CRUDO = panel({
    ("Close", "AAPL"): [200.0, 202.0, 204.0],
    ("Close", "MSFT"): [400.0, 396.0, 398.0],
    ("Dividends", "AAPL"): [0.0, 0.24, 0.0],
    ("Dividends", "MSFT"): [0.0, 0.0, 0.0],
    ("Stock Splits", "AAPL"): [0.0, 0.0, 4.0],
    ("Stock Splits", "MSFT"): [0.0, 0.0, 0.0],
})


def test_separa_cierres_dividendos_y_splits():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert list(historia.cierres.columns) == ["AAPL", "MSFT"]
    assert historia.cierres.loc["2026-01-06", "AAPL"] == 202.0
    assert historia.dividendos.loc["2026-01-06", "AAPL"] == 0.24
    assert historia.splits.loc["2026-01-07", "AAPL"] == 4.0


def test_el_factor_de_split_multiplica_lo_comprado_antes():
    # Un 4:1 el dia 7 convierte 10 acciones compradas el dia 5 en 40. Sin esto,
    # la cartera parece haber perdido el 75% de un activo de un dia para otro.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.factor_split(historia, "AAPL", "2026-01-05", "2026-01-07") == 4.0
    assert precios.factor_split(historia, "AAPL", "2026-01-07", "2026-01-07") == 1.0


def test_sin_splits_el_factor_es_uno():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.factor_split(historia, "MSFT", "2026-01-05", "2026-01-07") == 1.0


def test_un_ticker_sin_datos_se_reporta_y_no_se_inventa():
    # Devolver una columna de NaN dejaria la cartera valorada en cero sin decir
    # por que. El nombre tiene que volver para que la pantalla lo diga.
    vacio = panel({
        ("Close", "AAPL"): [200.0, 202.0, 204.0],
        ("Close", "ZZZZ"): [float("nan")] * 3,
        ("Dividends", "AAPL"): [0.0, 0.0, 0.0],
        ("Dividends", "ZZZZ"): [0.0, 0.0, 0.0],
        ("Stock Splits", "AAPL"): [0.0, 0.0, 0.0],
        ("Stock Splits", "ZZZZ"): [0.0, 0.0, 0.0],
    })
    historia = precios.desde_panel(vacio, ["AAPL", "ZZZZ"])
    assert historia.sin_datos == ["ZZZZ"]
    assert list(historia.cierres.columns) == ["AAPL"]


def test_el_ultimo_precio_viene_con_su_fecha():
    # Un "valor de hoy" calculado con el cierre de hace un mes es una mentira
    # silenciosa: la fecha viaja con el precio para que se pueda decir.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    precio, cuando = precios.ultimo(historia, "AAPL")
    assert precio == 204.0
    assert cuando == "2026-01-07"


def test_un_ticker_que_no_esta_no_devuelve_un_precio_cualquiera():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.ultimo(historia, "ZZZZ") == (None, None)


def test_el_cierre_de_un_dia_concreto_se_puede_pedir():
    # Es lo que rellena el precio cuando el usuario no lo recuerda, y lo que
    # marca esa operacion como `precio_estimado`.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.cierre_en(historia, "AAPL", "2026-01-06") == 202.0


def test_un_dia_sin_cotizacion_no_devuelve_el_cierre_de_otro_dia():
    # Festivo, fin de semana, o una fecha anterior a la salida a bolsa. Devolver
    # el cierre mas cercano dejaria registrada una compra a un precio de otro
    # dia sin que nada lo indicara.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.cierre_en(historia, "AAPL", "2026-01-08") is None
    assert precios.cierre_en(historia, "ZZZZ", "2026-01-06") is None
