"""Un ticker de punta a punta: qué es, cómo queda frente a su sector y cuánto vale.

Sin Streamlit: N2 pinta lo que sale de aquí. Un ticker que falla sólo se lleva
su fila, que es la política de la descarga de fundamentales y de la valoración
de candidatos; y un defecto propio tampoco tumba a los demás, pero no se calla:
el traceback va al log de la consola y la fila dice `error_interno`. Si el
defecto es al valorar, sólo lo dice la valoración, y la ficha se queda.
"""

import logging
from dataclasses import dataclass, replace
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


def pilar_valoracion(referencia: "Referencia | None") -> "float | None":
    """El pilar de valoración de la ficha, que es lo que vota «frente a sus pares»."""
    return None if referencia is None else referencia.ficha["pilares"].get("valoracion")


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
    try:
        encontrada, motivo_referencia = _frente_al_sector(resuelto, sector, panel)
    except Exception:
        # Un defecto propio al hacer la ficha no se lleva la identidad ni la
        # valoración, que no dependen de ella (nota de la Task 14 de N1): la
        # ficha dice `error_interno`, la traza va al log y lo demás sigue.
        logging.getLogger(__name__).exception(
            "La ficha frente al sector de %s falló por un defecto, no por falta de datos",
            ticker,
        )
        encontrada, motivo_referencia = None, "error_interno"
    traidas, valoracion = _valoracion(resuelto, pilar_valoracion(encontrada))
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


def con_precio_nuevo(
    anterior: Analisis, panel: "pd.DataFrame | None", tabla_sectores: "dict | None" = None
) -> Analisis:
    """El mismo análisis con la cotización de ahora, sin rehacer la ficha frente al sector.

    La ficha no depende del precio de hoy: los múltiplos del panel van con el
    precio del día en que se publicó cada trimestre. Lo que sí depende es la
    identidad (precio y hora) y la valoración (el precio entra en el inverso,
    en el EPV y en el margen). Rehacer la ficha costaría la red de sus filas
    propias y unos 0,3 s de z por ticker.

    Un ticker que no tenía clase, o que ahora sale con otra, se analiza entero:
    no hay ficha que conservar, o la que hay es de otra cosa. El precio sale de
    la caché de `mercado` si tiene menos de quince minutos (`mercado.VALIDEZ`).
    Un defecto propio no se calla --la traza va al log, como en `analizar`--,
    pero tampoco se lleva la fila: se devuelve `anterior`, que seguía bien.
    """
    if anterior.clase is None:
        return analizar(anterior.ticker, panel, tabla_sectores)
    try:
        resuelto = resolver.resolver(anterior.ticker)
        if resuelto.clase != anterior.clase:
            return analizar(anterior.ticker, panel, tabla_sectores)
        if resuelto.clase == "etf":
            return replace(anterior, identidad=resuelto.identidad)
        traidas, valoracion = _valoracion(resuelto, pilar_valoracion(anterior.referencia))
        return replace(anterior, identidad=resuelto.identidad, entradas=traidas, valoracion=valoracion)
    except Exception:
        logging.getLogger(__name__).exception(
            "Actualizar el precio de %s falló por un defecto, no por falta de datos",
            anterior.ticker,
        )
        return anterior


def analizar_varios(
    tickers: "list[str]", ruta_panel=None, tabla_sectores: "dict | None" = None
) -> "tuple[list[Analisis], date | None]":
    """Varios tickers contra el mismo panel, y la fecha de ese panel."""
    panel, fecha = referencia.cargar_panel(ruta_panel)
    tabla = load_sectors() if tabla_sectores is None else tabla_sectores
    return [analizar(ticker, panel, tabla) for ticker in tickers], fecha
