"""Un ticker de punta a punta: qué es, cómo queda frente a su sector y cuánto vale.

Sin Streamlit: N2 pinta lo que sale de aquí. Un ticker que falla sólo se lleva
su fila, que es la política de la descarga de fundamentales y de la valoración
de candidatos; y un defecto propio tampoco tumba a los demás, pero no se calla:
el traceback va al log de la consola y la fila dice `error_interno`. Si el
defecto es al valorar, sólo lo dice la valoración, y la ficha se queda.
"""

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from analizador import kpis, referencia, resolver
from analizador.lineas_yf import lineas_de
from analizador.referencia import Referencia
from analizador.resolver import Identidad, Resuelto
from analizador.sectores import sector_gics
from analizador.valorar import Entradas, entradas, valorar
from fundamentals.sectors import MIN_PARES, load_sectors
from valoracion import mercado, plano


@dataclass(frozen=True)
class Analisis:
    """Todo lo que se sabe de un ticker. `motivo` dice por qué no hay análisis.

    Con clase, `motivo` es None y lo que falta va en su sitio:
    `motivo_referencia` (`sin_panel`, `sin_sector`, `sector_sin_pares`,
    `sin_estados`, `sin_historia`, `sin_precio`, `sin_trimestres_comparables`,
    o el de la red) y la valoración, que es una fallida con su motivo. Un ETF
    sólo tiene identidad.

    Una valoración `error_interno` puede venir con `entradas`: llegaron bien y
    lo que falló fue la aritmética, que volvería a fallar con cada deslizador.
    """

    ticker: str
    clase: "str | None"
    identidad: "Identidad | None"
    motivo: "str | None"
    sector: "str | None" = None
    fuente_sector: "str | None" = None
    referencia: "Referencia | None" = None
    motivo_referencia: "str | None" = None
    entradas: "Entradas | None" = None
    valoracion: "dict | None" = None


def _filas_propias(resuelto: Resuelto) -> "tuple[pd.DataFrame | None, str]":
    if resuelto.clase == "sec":
        return kpis.kpis_sec(resuelto.ticker)
    crudos, motivo = mercado.estados(resuelto.ticker)
    if crudos is None:
        return None, motivo
    trimestrales, anuales = lineas_de(crudos)
    if trimestrales.empty:
        return None, "sin_historia"
    identidad = resuelto.identidad
    # Sin una de las dos monedas se toma la otra: sin dato no se convierte, y
    # un par inventado («NoneTWD=X») sólo daría un precio vacío.
    moneda_precio = identidad.moneda or identidad.moneda_estados
    moneda_estados = identidad.moneda_estados or identidad.moneda
    if moneda_estados is None:
        # Sin ninguna, el par sería `NoneUSD=X`: un 404 de un par de segundos que
        # culparía a la red. Es la clave de `entradas` sin moneda en el perfil.
        return None, "sin_precio"
    # Los KPIs se calculan en dólares para que los suelos de `fundamentals.kpis`
    # valgan lo mismo que en el panel de referencia (ver `kpis.kpis_yf`).
    tipo_a_usd, motivo = mercado.tipo_de_cambio(moneda_estados, "USD")
    if tipo_a_usd is None:
        return None, motivo
    # `kpis_yf` dice `sin_precio` si no hay precio: unas filas sin valoración
    # saldrían excluidas por un pilar sin datos, que culparía a la empresa.
    return kpis.kpis_yf(
        resuelto.ticker, trimestrales, anuales, moneda_precio, moneda_estados, tipo_a_usd
    )


def _frente_al_sector(
    resuelto: Resuelto, sector: "str | None", panel: "pd.DataFrame | None"
) -> "tuple[Referencia | None, str | None]":
    if panel is None:
        return None, "sin_panel"
    if resuelto.ticker in panel.index.get_level_values("ticker"):
        return referencia.frente_al_sector(resuelto.ticker, panel), None
    if sector is None:
        return None, "sin_sector"
    # Un sector que ni con ella dentro llega a `MIN_PARES` no tiene z: la ficha
    # saldría «pilar sin datos», que culparía a la empresa. La clave es la del
    # ranking, y se mira antes de bajar nada.
    pares = referencia.pares_en_panel(panel, sector)
    if pares + 1 < MIN_PARES:
        return None, "sector_sin_pares"
    propias, motivo = _filas_propias(resuelto)
    if propias is None:
        return None, motivo
    encontrada = referencia.frente_al_sector(resuelto.ticker, panel, sector, propias)
    return (encontrada, None) if encontrada is not None else (None, "sin_trimestres_comparables")


def _valoracion(
    resuelto: Resuelto, pilar: "float | None"
) -> "tuple[Entradas | None, dict]":
    """Las entradas y la valoración, o la fallida que dice por qué no hay valoración.

    Un defecto al traerlas o al valorar no se lleva la fila: la identidad y la
    ficha ya están hechas y siguen valiendo. Es la política de
    `ranking.run._valoracion`: la valoración dice `error_interno` y el
    traceback va al log de la consola. Las entradas que sí llegaron se quedan.
    """
    log = logging.getLogger(__name__)
    try:
        traidas, motivo = entradas(resuelto)
    except Exception:
        log.exception(
            "Las entradas de %s fallaron por un defecto, no por falta de datos", resuelto.ticker
        )
        return None, plano.fallida("error_interno")
    if traidas is None:
        return None, plano.fallida(motivo)
    try:
        return traidas, valorar(traidas, pilar)
    except Exception:
        log.exception(
            "La valoración de %s falló por un defecto del motor, no por falta de datos",
            resuelto.ticker,
        )
        return traidas, plano.fallida("error_interno")


def _analizar(ticker: str, panel: "pd.DataFrame | None", tabla_sectores: "dict | None") -> Analisis:
    resuelto = resolver.resolver(ticker)
    if resuelto.clase is None:
        return Analisis(ticker, None, resuelto.identidad, resuelto.motivo)
    if resuelto.clase == "etf":
        return Analisis(ticker, "etf", resuelto.identidad, None)
    sector, fuente = sector_gics(ticker, resuelto.identidad.sector, tabla_sectores)
    encontrada, motivo_referencia = _frente_al_sector(resuelto, sector, panel)
    pilar = None if encontrada is None else encontrada.ficha["pilares"].get("valoracion")
    traidas, valoracion = _valoracion(resuelto, pilar)
    return Analisis(
        ticker=ticker,
        clase=resuelto.clase,
        identidad=resuelto.identidad,
        motivo=None,
        sector=sector,
        fuente_sector=fuente,
        referencia=encontrada,
        motivo_referencia=motivo_referencia,
        entradas=traidas,
        valoracion=valoracion,
    )


def analizar(
    ticker: str, panel: "pd.DataFrame | None", tabla_sectores: "dict | None" = None
) -> Analisis:
    """Un ticker ya normalizado (`resolver.normalizar`), frente al `panel` de referencia."""
    try:
        return _analizar(ticker, panel, tabla_sectores)
    except Exception:
        logging.getLogger(__name__).exception(
            "El análisis de %s falló por un defecto, no por falta de datos", ticker
        )
        return Analisis(ticker, None, None, "error_interno")


def analizar_varios(
    tickers: "list[str]", ruta_panel=None, tabla_sectores: "dict | None" = None
) -> "tuple[list[Analisis], date | None]":
    """Varios tickers contra el mismo panel, y la fecha de ese panel."""
    panel, fecha = referencia.cargar_panel(ruta_panel)
    tabla = load_sectors() if tabla_sectores is None else tabla_sectores
    return [analizar(ticker, panel, tabla) for ticker in tickers], fecha
