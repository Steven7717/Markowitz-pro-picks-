"""Contrasta los KPIs nativos contra los que publica yfinance.

Se omite entero si yfinance no esta instalado o si falta EDGAR_IDENTITY, igual
que el contraste de Ledoit-Wolf contra scikit-learn y el de RSI contra
pandas-ta-classic. Marcado como test de red: no corre en la suite normal.

Lo que atrapa no son diferencias de decimas — yfinance informa sobre doce meses
moviles y nosotros por trimestre, asi que no tienen por que coincidir. Atrapa
haber elegido el concepto XBRL equivocado, que produce discrepancias de decenas
de puntos.
"""
import os

import pytest

pytest.importorskip("yfinance")

pytestmark = pytest.mark.red

TOLERANCIA = 0.15


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "KO"])
def test_native_gross_margin_agrees_with_yfinance(ticker):
    import yfinance as yf

    from fundamentals.fetch import set_sec_identity

    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("Falta EDGAR_IDENTITY")
    set_sec_identity()

    from fundamentals.run import build_panel

    panel, _, _ = build_panel([ticker], periods=8)
    nuestro = panel["margen_bruto"].dropna()
    if nuestro.empty:
        pytest.skip(f"Sin margen bruto calculado para {ticker}")

    referencia = yf.Ticker(ticker).info.get("grossMargins")
    if referencia is None:
        pytest.skip(f"yfinance no publica grossMargins para {ticker}")

    diferencia = abs(float(nuestro.iloc[-1]) - float(referencia))
    assert diferencia < TOLERANCIA, (
        f"{ticker}: margen bruto nativo {nuestro.iloc[-1]:.3f} frente a "
        f"{referencia:.3f} de yfinance. Una diferencia asi sugiere que la cadena "
        f"de conceptos de ingresos o coste_de_ventas elige el renglon equivocado."
    )
