"""El gráfico de TradingView: el símbolo y el HTML del widget, sin Streamlit.

El *Advanced Chart* se incrusta con `st.iframe`. Es un script de TradingView
que corre en el navegador del usuario: TradingView sabe qué ticker se mira, sin
conexión no se ve, y sus datos no son los del programa ni entran en ninguna
cuenta. Todo eso se dice debajo.

**La BMV no se ve en el widget.** Con `BMV:WALMEX`, el widget dice «Símbolo
solo disponible en TradingView» y «Este símbolo no existe» (comprobado el
2026-10-26, al planear N2): TradingView no da los datos de esa bolsa en lo que
se incrusta. Para esas bolsas no se incrusta nada; se enlaza a su página.
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
}

# Las bolsas cuyos datos TradingView sólo da en su web, no en el widget. Tabla
# congelada, como `BOLSAS`: medida con BMV:WALMEX el 2026-10-26. Una bolsa nueva
# que falle igual se añade aquí, con su fecha.
SOLO_EN_TRADINGVIEW = frozenset({"MEX"})

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
    "TradingView no da los datos de esta bolsa en el gráfico que se incrusta, "
    "sólo en su web: el enlace lo abre allí. Sus datos no son los del programa ni "
    "entran en ninguna cuenta."
)
_RETRASO_BMV = "En la BMV los datos de TradingView llevan unos 15–20 minutos de retraso."


def simbolo(ticker: str, bolsa: "str | None") -> str:
    """El símbolo de TradingView: `BRK-B` → `NYSE:BRK.B`, `WALMEX.MX` → `BMV:WALMEX`.

    El sufijo de bolsa de Yahoo se quita, y el guion de clase vuelve a ser
    punto, que es como lo escribe TradingView.
    """
    base = ticker.rpartition(".")[0] if tiene_sufijo(ticker) else ticker
    base = base.replace("-", ".")
    prefijo = BOLSAS.get(bolsa or "")
    return f"{prefijo}:{base}" if prefijo else base


def en_widget(bolsa: "str | None") -> bool:
    """Si TradingView da los datos de esa bolsa en el widget incrustado."""
    return bolsa not in SOLO_EN_TRADINGVIEW


def enlace(simbolo_: str) -> str:
    """La página del símbolo en TradingView: `BMV:WALMEX` → `…/symbols/BMV-WALMEX/`."""
    return f"https://es.tradingview.com/symbols/{simbolo_.replace(':', '-')}/"


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


def avisos(bolsa: "str | None") -> "list[str]":
    """Lo que se sabe y se dice debajo del gráfico, o del enlace si no se incrusta."""
    salida = [_LO_QUE_SE_SABE if en_widget(bolsa) else _SOLO_EN_WEB]
    if bolsa == "MEX":
        salida.append(_RETRASO_BMV)
    return salida
