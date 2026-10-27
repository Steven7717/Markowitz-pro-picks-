"""El gráfico de TradingView: el símbolo y el HTML del widget, sin Streamlit.

El *Advanced Chart* se incrusta con `st.iframe`. Es un script de TradingView
que corre en el navegador del usuario: TradingView sabe qué ticker se mira, sin
conexión no se ve, y sus datos no son los del programa ni entran en ninguna
cuenta. Todo eso se dice debajo.

**La BMV no se ve en el widget.** Con `BMV:WALMEX`, el widget dice «Símbolo
solo disponible en TradingView» y «Este símbolo no existe» (comprobado el
2026-10-26, al planear N2): TradingView no da los datos de esa bolsa en lo que
se incrusta. Para esas bolsas no se incrusta nada; se enlaza a su página.

**Un ticker con sufijo sólo se incrusta si su bolsa está comprobada.** Sin el
prefijo de bolsa, TradingView toma el símbolo por uno de EE. UU.: `T.TO`
(TELUS) enseñaba AT&T, `BA.L` (BAE Systems) enseñaba Boeing, y `RY.TO` o
`SHEL.L` la ADR de Nueva York. Y con prefijo tampoco se sabe si el widget da
los datos (la BMV no los da). Así que un ticker de fuera se enlaza, salvo que su
bolsa esté en `COMPROBADAS_EN_WIDGET`; los de EE. UU., sin sufijo, se incrustan.
"""

import json

import tema
from analizador.resolver import tiene_sufijo

# El `exchange` de yfinance → el prefijo de TradingView. Tabla congelada del
# spec: una bolsa que no esté aquí va sin prefijo, y TradingView lo resuelve.
BOLSAS = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "AMEX",
    "PCX": "AMEX",
    "MEX": "BMV",
    # Sólo para el enlace: su página en TradingView es la de la empresa
    # (TSX-T es TELUS, TSE-7203 Toyota, BME-SAN Santander; 2026-10-27). Londres
    # no entra: TradingView escribe `LSE:BA.` con punto, y `LSE-BA` da 404.
    "TOR": "TSX",
    "JPX": "TSE",
    "MCE": "BME",
}

# Las bolsas de fuera cuyos datos se han visto en el widget incrustado, con su
# fecha. Hoy ninguna: la BMV se midió el 2026-10-26 y no sale («Símbolo solo
# disponible en TradingView»). Una bolsa se añade aquí sólo después de verla.
COMPROBADAS_EN_WIDGET: "frozenset[str]" = frozenset()

_SCRIPT = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
ALTO = 520

ESTUDIO_D = (
    "El sub-proyecto D midió siete señales técnicas sobre el S&P 500 —momentum, "
    "RSI, MACD, medias, máximos de 52 semanas, Bollinger y reversión— y ninguna "
    "mostró ventaja después de costes. El gráfico está para quien quiera mirarlo; "
    "el programa no lo usa para nada."
)

_LO_QUE_SE_SABE = (
    "El gráfico es un script de TradingView: TradingView sabe qué ticker estás "
    "mirando, y sin conexión no se ve. Sus datos no son los del programa ni entran "
    "en ninguna cuenta."
)
_SOLO_EN_WEB = (
    "El gráfico de esta bolsa no se incrusta: TradingView no da sus datos en el "
    "gráfico que se incrusta, o no está comprobado que los dé. El enlace lo abre "
    "en su web. Sus datos no son los del programa ni entran en ninguna cuenta."
)
_EN_YAHOO = (
    "El gráfico de esta bolsa no se incrusta, y el programa no sabe cómo la nombra "
    "TradingView: sin el nombre de la bolsa, TradingView enseñaría otra empresa con "
    "las mismas letras. El enlace abre la cotización en Yahoo Finanzas. Sus datos "
    "no son los del programa ni entran en ninguna cuenta."
)
_RETRASO_BMV = "En la BMV los datos de TradingView llevan unos 15–20 minutos de retraso."


def simbolo(ticker: str, bolsa: "str | None") -> "str | None":
    """El símbolo de TradingView: `BRK-B` → `NYSE:BRK.B`, `WALMEX.MX` → `BMV:WALMEX`.

    El sufijo de bolsa de Yahoo se quita, y el guion de clase vuelve a ser
    punto, que es como lo escribe TradingView. Sin sufijo (EE. UU.) y sin bolsa
    conocida va sin prefijo, y TradingView lo resuelve. Con sufijo y sin prefijo
    conocido es `None`: quitarle el sufijo nombraría a otra empresa (`BA.L`,
    BAE, sería `BA`, Boeing).
    """
    prefijo = BOLSAS.get(bolsa or "")
    sufijo = tiene_sufijo(ticker)
    if sufijo and not prefijo:
        return None
    base = ticker.rpartition(".")[0] if sufijo else ticker
    base = base.replace("-", ".")
    return f"{prefijo}:{base}" if prefijo else base


def en_widget(ticker: str, bolsa: "str | None") -> bool:
    """Si el gráfico se incrusta: los de EE. UU. sí; los de fuera, si su bolsa
    está comprobada en el widget."""
    return not tiene_sufijo(ticker) or (
        bolsa in COMPROBADAS_EN_WIDGET and simbolo(ticker, bolsa) is not None
    )


def enlace(ticker: str, bolsa: "str | None") -> "tuple[str, str]":
    """El rótulo y la dirección del enlace cuando el gráfico no se incrusta.

    Con prefijo conocido, la página del símbolo en TradingView
    (`BMV:WALMEX` → `…/symbols/BMV-WALMEX/`). Sin él, la cotización en Yahoo
    Finanzas, que lleva el sufijo y no confunde la empresa.
    """
    simbolo_ = simbolo(ticker, bolsa)
    if simbolo_ is None:
        return (f"Ver {ticker} en Yahoo Finanzas", f"https://finance.yahoo.com/quote/{ticker}/")
    return (
        f"Ver {simbolo_} en TradingView",
        f"https://es.tradingview.com/symbols/{simbolo_.replace(':', '-')}/",
    )


def html(simbolo_: str, oscuro: bool) -> str:
    """El widget a toda la altura del marco, con el tema claro u oscuro de la app.

    Con `autosize`, el script de TradingView reescribe el estilo del contenedor
    a `height:100%`, así que el documento entero tiene que tener altura: sin la
    hoja de `html, body` el gráfico salía de 150 píxeles dentro de un marco de
    520 (visto al planear N2). Lleva el enlace de atribución del código de
    inserción de TradingView.

    No deja cambiar de símbolo: está atado al ticker analizado. Si el script no
    llega --sin conexión, o TradingView no responde--, el `onerror` lo dice en
    vez de dejar un hueco en blanco.
    """
    config = json.dumps(
        {
            "autosize": True,
            "symbol": simbolo_,
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "dark" if oscuro else "light",
            "style": "1",
            "locale": "es",
            "allow_symbol_change": False,
            "calendar": False,
            "support_host": "https://www.tradingview.com",
        }
    )
    # `</` dentro del script cerraría la etiqueta: el símbolo sale de
    # `resolver.normalizar`, que no admite ni `<` ni `/`, pero un JSON no se
    # escapa para HTML por sí solo.
    config = config.replace("</", "<\\/")
    return (
        "<style>html,body{height:100%;margin:0}</style>"
        '<div class="tradingview-widget-container" style="height:100%;width:100%">'
        '<div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>'
        '<div class="tradingview-widget-copyright" style="font-family:sans-serif;font-size:12px">'
        '<a href="https://es.tradingview.com/" rel="noopener nofollow" target="_blank">'
        "Gráfico de TradingView</a></div>"
        f'<p id="sin-grafico" style="display:none;font-family:sans-serif;color:{tema.TEXTO_SUAVE}">'
        "No se pudo cargar el gráfico de TradingView: sin conexión, o TradingView no "
        "responde. El resto del Analizador no depende de él.</p>"
        f'<script type="text/javascript" src="{_SCRIPT}" async '
        "onerror=\"document.getElementById('sin-grafico').style.display='block'\">"
        f"{config}"
        "</script>"
        "</div>"
    )


def avisos(ticker: str, bolsa: "str | None") -> "list[str]":
    """Lo que se sabe y se dice debajo del gráfico, o del enlace si no se incrusta."""
    if en_widget(ticker, bolsa):
        salida = [_LO_QUE_SE_SABE]
    elif simbolo(ticker, bolsa) is None:
        salida = [_EN_YAHOO]
    else:
        salida = [_SOLO_EN_WEB]
    if bolsa == "MEX":
        salida.append(_RETRASO_BMV)
    return salida
