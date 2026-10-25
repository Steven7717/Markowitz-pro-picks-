"""Las filas de KPIs de un ticker que no está en el panel de referencia.

Una empresa de la SEC pasa por el mismo motor que el ranking: `build_panel` con
un universo de una. Las demás salen de yfinance (`analizador.lineas_yf`), con el
precio de cada trimestre en la moneda de sus estados.
"""

import pandas as pd

from analizador.lineas_yf import kpis_trimestrales
from fundamentals.fetch import CorridaAbortada
from valoracion.mercado import SUBUNIDADES

# Privada y aun así importada: es el precio del día en que se publicaron las
# cuentas de cada trimestre, con el plazo del 10-Q o del 10-K. Una segunda
# copia aquí sería el look-ahead que el estudio D encontró siete veces.
from fundamentals.run import _precios_por_periodo, build_panel


def kpis_sec(ticker: str) -> "tuple[pd.DataFrame | None, str]":
    """Las filas del panel de la SEC de un ticker, indexadas por fecha de cierre.

    Devuelve `(filas, "ok")`; `(None, "sin_precio")` si Yahoo no dio el precio;
    o `(None, "sin_estados")` si la SEC no respondió o no tiene sus cuentas.
    """
    try:
        panel, _, _ = build_panel([ticker])
    except CorridaAbortada as abortada:
        # Con un universo de uno, que no llegue el precio también aborta
        # `build_panel`: decir `sin_estados` culparía a la SEC de un fallo de
        # Yahoo, que es de donde baja `load_ohlcv`.
        if abortada.causa == "sin_precios":
            return None, "sin_precio"
        # Si no, es que la fuente no responde o rechaza la identidad: no es la
        # empresa, pero para esta ficha el efecto es el mismo.
        return None, "sin_estados"
    if panel.empty or ticker not in panel.index.get_level_values("ticker"):
        return None, "sin_estados"
    return panel.xs(ticker, level="ticker"), "ok"


def _cierres_de_ejercicio(anuales: pd.DataFrame) -> pd.DatetimeIndex:
    """Las fechas de los anuales que son ejercicios de verdad.

    El anual de yfinance trae además columnas de doce meses móviles con sólo el
    BPA y el recuento (RY: 2025-01-31, 04-30 y 07-31; TM: 06-30 y 09-30).
    Tomadas por cierres, esos trimestres cotizarían con el plazo del 10-K, 65
    días, en vez de los 45 del 10-Q. Un ejercicio se reconoce por el ancla de
    `analizador.lineas_yf.fundamentos_anuales`: los ingresos si algún año los
    tiene, y si no el beneficio, que es lo que declara un banco.

    No sirve `lineas_yf._de_doce_meses`: deja pasar la primera fila sin mirar si
    trae dato, y descarta un ejercicio de transición y el que sigue a un hueco,
    que sí son cierres de ejercicio.
    """
    if anuales.empty:
        return pd.DatetimeIndex([])
    ancla = "ingresos" if anuales["ingresos"].notna().any() else "beneficio_neto"
    return pd.DatetimeIndex(anuales.index[anuales[ancla].notna()])


def kpis_yf(
    ticker: str,
    trimestrales: pd.DataFrame,
    anuales: pd.DataFrame,
    moneda_precio: str,
    moneda_estados: str,
    tipo_a_usd: float,
) -> "tuple[pd.DataFrame | None, str]":
    """Los KPIs trimestrales de un ticker de yfinance.

    Devuelve `(filas, "ok")`; `(None, "sin_precio")` si Yahoo no dio ni un
    precio o ni un tipo de cambio; o `(None, "sin_historia")` si no hay
    trimestres, la misma clave con que `analizador.analisis` dice eso mismo
    (`sin_estados` habla de la SEC).

    El precio de cada trimestre es el del día en que sus cuentas se hicieron
    públicas, con los plazos de `fundamentals.run`. Son los de la SEC, 45 días
    para el trimestre y 65 para el ejercicio, y fuera de ella son una
    aproximación: Tencent publicó su ejercicio 77 días después del cierre. Si
    cotiza en otra moneda que la de sus estados (TSM: dólares y TWD), se
    convierte al tipo de cambio de ese mismo día, que se baja con el mismo
    cargador: un tipo de hoy para precios de hace un año movería los múltiplos
    con la divisa, no con la empresa. `min_obs=1` porque con cinco trimestres
    la ventana de precios es de poco más de un año, y el mínimo del cargador la
    descartaría.

    Después, las líneas y el precio se pasan a dólares con **un único** tipo,
    `tipo_a_usd` (dólares por unidad de la moneda de los estados, el último
    cierre). Los suelos económicos de `fundamentals.kpis` están pensados en
    dólares --1e8 de partida de balance y 1e6 de gasto financiero--, y en wones
    el del gasto financiero valdría 745 $: una pequeña de la BMV o de KOSDAQ
    sacaría márgenes y coberturas que el panel de referencia le taparía a una
    empresa de EE. UU. de su tamaño. Un tipo constante no cambia ningún cociente
    ni ningún crecimiento; con el de cada fecha, la divisa entraría en el
    crecimiento interanual.
    """
    # Antes que el precio: sin trimestres la serie de precios sale vacía, y
    # pasaría por «sin precio» lo que es que no hay cuentas.
    if trimestrales.empty:
        return None, "sin_historia"
    cierres = _cierres_de_ejercicio(anuales)
    precios, _ = _precios_por_periodo(ticker, trimestrales.index, cierres, min_obs=1)
    # Una cotización en subunidades (Londres, en peniques) se cambia con su
    # moneda principal y se divide por la escala: yfinance pasa el par a
    # mayúsculas, y «GBpUSD=X» sería el tipo de la libra, cien veces mayor.
    base, escala = SUBUNIDADES.get(moneda_precio, (moneda_precio, 1))
    if base != moneda_estados:
        par = f"{base}{moneda_estados}=X"
        tipos, _ = _precios_por_periodo(par, trimestrales.index, cierres, min_obs=1)
        precios = precios * tipos
    precio_en_dolares = precios / escala * tipo_a_usd
    # Sin un solo precio, la valoración saldría vacía y la ficha, excluida por
    # «pilar sin datos»: culparía a la empresa de un fallo de Yahoo, el mismo
    # error de etiqueta que `kpis_sec` evita con `sin_precio`.
    if precio_en_dolares.isna().all():
        return None, "sin_precio"
    dinero = [linea for linea in trimestrales.columns if linea != "acciones_diluidas"]
    en_dolares = trimestrales.copy()
    en_dolares[dinero] = en_dolares[dinero] * tipo_a_usd
    return kpis_trimestrales(en_dolares, precio_en_dolares), "ok"
