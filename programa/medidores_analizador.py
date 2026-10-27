"""Cómo se enseña lo que sale del Analizador: etiquetas, rótulos y filas, sin Streamlit.

`analizador/` devuelve claves --`sin_red`, `sector_sin_pares`,
`historia_corta`-- y nunca texto de pantalla: es la regla de «La etiqueta de
pantalla que se guardaba en disco». Las palabras viven aquí y sólo aquí, con
tests, y `vistas/analizador.py` pinta lo que sale de este módulo. Va aparte de
`medidores_valoracion.py`, que ya pasa de las setecientas líneas.

**Un motivo es una afirmación** (la lección de M y de N1): cada etiqueta dice a
quién culpa, y una que culpe a la empresa de un fallo de Yahoo, de la SEC o del
panel es falsa. Por eso `sin_red` no dice «Yahoo no conoce este ticker»
--`mercado` no lo distingue de una conexión caída--, y `sin_historia`, en la
ficha frente al sector, habla de trimestres y no de años.

El registro es el de CONTEXTO («Registro del texto»): el lector sabe lo que es
una acción o un sector, y los términos de nivel 2 --z-score, pilares, tasa
libre-- los glosa la pantalla una vez, con los glosarios de `medidores` y de
`medidores_valoracion`.
"""

import re
from datetime import date

import medidores_valoracion
from analizador.divisas import SEPARACION_MAXIMA_SUBASTAS, adr_dudosa
from analizador.resolver import normalizar, tiene_sufijo
from aprobacion.carga import MOTIVOS_EN_CASTELLANO
from fundamentals.sectors import MIN_PARES
from noticias.texto import plano
from ranking.criterio import TOPE_POR_SECTOR

CLASE = {
    "sec": "SEC (10-K)",
    "extranjera_sec": "SEC, extranjera (20-F o 40-F)",
    "sin_sec": "Fuera de la SEC",
    "etf": "ETF",
}

# De dónde salen los números de cada clase (spec, «Las cuatro clases de ticker»).
FUENTE_DE_DATOS = {
    "sec": "los estados de la SEC (EDGAR), con el mismo motor que los candidatos",
    "extranjera_sec": (
        "los estados de Yahoo Finance: los que presenta en la SEC van en IFRS y "
        "son anuales"
    ),
    "sin_sec": "los estados de Yahoo Finance",
    "etf": "sólo la cotización: un ETF no se valora",
}

# Por qué un ticker no tiene clase (`Analisis.motivo`). Sin clase no hay detalle.
MOTIVO_ANALISIS = {
    # `mercado` no distingue un símbolo que Yahoo no conoce de una conexión que
    # falla (ZZZZQ, en el recorrido de N1): «no lo conoce» afirmaría lo que no
    # se sabe. Enmienda del spec del 2026-10-14.
    "sin_red": "Yahoo no devolvió datos (sin conexión o un símbolo que no conoce)",
    "tipo_no_soportado": "Tipo no soportado: sólo acciones y ETFs",
    "sin_red_edgar": (
        "La SEC no respondió al preguntar qué informes presenta; vuelve a "
        "intentarlo en un rato"
    ),
    "sin_identidad_edgar": (
        "Falta el correo para EDGAR, en Perfil y ajustes: sin él la SEC no "
        "responde y no se sabe qué informes presenta"
    ),
    # «al analizarlo» y no «al valorar», que es lo que dice
    # `medidores_valoracion`: aquí falló la fila entera, no la valoración.
    "error_interno": "Error interno del programa al analizarlo",
}

# Por qué no hay ficha frente al sector (`Analisis.motivo_referencia`). La
# valoración sigue, con el voto de pares `no_aplica`.
MOTIVO_REFERENCIA = {
    "sin_panel": (
        "no hay panel de referencia del S&P 500; se construye con el botón de "
        "arriba, sin tocar tus candidatos"
    ),
    "sin_sector": "su sector de Yahoo no tiene equivalente GICS, y no se adivina",
    "sector_sin_pares": (
        f"su sector no llega a {MIN_PARES} empresas en el panel del S&P 500, "
        "contándola a ella: no hay con quién compararla"
    ),
    "sin_estados": "los estados financieros de la SEC no están disponibles o no son legibles",
    "sin_precio": (
        "Yahoo no dio los precios con que se calculan sus múltiplos (PER, "
        "EV/EBITDA…)"
    ),
    # Faltan trimestres, no años: la ficha es trimestral. La etiqueta de
    # `medidores_valoracion` dice «faltan años» porque allí falta historia anual.
    "sin_historia": "Yahoo no trae ningún trimestre de sus cuentas",
    "sin_trimestres_comparables": (
        "todos sus trimestres son posteriores al último del panel: es el panel "
        "el que se quedó atrás"
    ),
    "sin_red": (
        "Yahoo no devolvió sus cuentas o el tipo de cambio (sin conexión o un "
        "error suyo)"
    ),
    "error_interno": "error interno del programa al compararla con su sector",
}

# Por qué falta la tasa libre (`Entradas.motivo_r_f`). Con el Bono M, los de
# Banxico y `sin_dato`; con el Tesoro, el de `mercado.tasa_libre`. La
# valoración fallida sólo dice `sin_bono_m`, y el concreto viaja aquí.
MOTIVO_TASA = {
    "sin_token": "falta el token de Banxico, que se pone en Perfil y ajustes",
    "token_invalido": "Banxico rechazó el token; revísalo en Perfil y ajustes",
    "sin_red": "Banxico no respondió (sin conexión o un error suyo)",
    "respuesta_rara": "Banxico respondió algo que no se pudo leer",
    "sin_dato": "Banxico no tiene ninguna subasta del Bono M en la ventana consultada",
    "sin_tasa_libre": "Yahoo no devolvió el rendimiento del Tesoro a 10 años",
}


def etiqueta(tabla: dict, clave: object) -> str:
    """La etiqueta de una clave de `tabla`.

    Una clave que no se conoce se enseña tal cual, que es mejor que esconderla,
    y una que ni es texto, «n/d»: la regla de `medidores_valoracion.etiqueta_motivo`.
    """
    if not isinstance(clave, str):
        return "n/d"
    return tabla.get(clave, clave)


def etiqueta_exclusion(codigo: object) -> str:
    """La guarda del ranking que dejaría fuera a la empresa, en palabras.

    Reutiliza `aprobacion.carga.MOTIVOS_EN_CASTELLANO`, las frases que el
    revisor lee arriba de Revisar candidatos («Quedaron excluidas 74: … sin
    datos para algún pilar entero»): detrás de «quedaría entre las empresas»
    dicen lo mismo con las mismas palabras.
    """
    if not isinstance(codigo, str):
        return "las guardas del ranking la dejarían fuera"
    frase = MOTIVOS_EN_CASTELLANO.get(codigo)
    if frase is None:
        return f"las guardas del ranking la dejarían fuera («{codigo}»)"
    return f"las guardas del ranking la dejarían fuera: quedaría entre las empresas {frase}"


def nombre(analisis) -> str:
    """El nombre largo de Yahoo, o «—».

    Va en cada fila para que se note un ticker mal partido: `separar("BRK B")`
    da BRK y B, y B es Barrick Mining, no la clase B de Berkshire.
    """
    identidad = analisis.identidad
    if identidad is None or not identidad.nombre:
        return "—"
    return identidad.nombre


def _con_ampersand(texto: str) -> "str | None":
    """El ticker con la Ñ escrita como la escribe Yahoo (`PE&OLES.MX`), o None."""
    mayusculas = texto.upper()
    if "Ñ" not in mayusculas:
        return None
    return normalizar(mayusculas.replace("Ñ", "&"))


def aviso_invalidos(invalidos: "list[str]") -> str:
    """Los trozos sin forma de ticker, tal como se escribieron, con la pista de la Ñ."""
    trozos = []
    for invalido in invalidos:
        sugerido = _con_ampersand(invalido)
        trozos.append(
            f"{invalido} (Yahoo escribe la Ñ como &: prueba {sugerido})" if sugerido else invalido
        )
    return "Sin forma de ticker, y no se analizan: " + ", ".join(trozos) + "."


def sugerencia_sin_red(ticker: str) -> "str | None":
    """La pista para un `.V`, `.L`, `.F` o `.T` que quizá era una clase de acción.

    La tabla de sufijos de bolsa es cerrada, y cuatro de una letra son también
    letras de clase: `MKC.V` se lee como TSX Venture (ver
    `resolver.SUFIJOS_DE_BOLSA`). Con guion la clase funciona siempre.
    """
    base, punto, sufijo = ticker.rpartition(".")
    if not punto or len(sufijo) != 1 or not tiene_sufijo(ticker):
        return None
    return (
        f"Si «.{sufijo}» era una clase de acción y no una bolsa, escríbela con "
        f"guion: {base}-{sufijo}."
    )


def motivo_de_la_fila(analisis) -> str:
    """Por qué un ticker sin clase no tiene análisis, con la pista si la hay."""
    texto = etiqueta(MOTIVO_ANALISIS, analisis.motivo)
    if analisis.motivo == "sin_red":
        pista = sugerencia_sin_red(analisis.ticker)
        if pista:
            texto = f"{texto}. {pista}"
    return texto


# --- La ficha frente al sector -------------------------------------------------


def puesto(referencia) -> str:
    """«25 de 424»: el puesto global entre las que pasan las guardas, o «—»."""
    if referencia is None or referencia.puesto is None:
        return "—"
    return f"{referencia.puesto} de {referencia.supervivientes}"


def puesto_en_tarjeta(referencia) -> str:
    """El rótulo de `medidores.tarjeta_candidato` en el Analizador."""
    if referencia.puesto is None:
        return "Fuera del ranking"
    return f"Puesto global {puesto(referencia)}"


def nota_puesto(referencia, ticker: str) -> str:
    """Qué es ese puesto, para que no se confunda con el de Revisar candidatos.

    Es el orden por nota compuesta entre las que pasan las guardas, sin el tope
    por sector con que se eligen las quince (enmienda del spec: con un tope de
    2 difería en 11 de 96). Y una de fuera del panel se cuenta a sí misma: las
    del S&P 500 salen «de 423» y ella «de 424», y no es un error.
    """
    texto = (
        f"Puesto global: el orden por nota compuesta entre las "
        f"{referencia.supervivientes} empresas que pasan las guardas del ranking, "
        f"sin el tope de {TOPE_POR_SECTOR} por sector con que se eligen los "
        "candidatos. Por eso puede no coincidir con el puesto de Revisar candidatos."
    )
    if not referencia.en_panel:
        texto += (
            f" {ticker} no está en el panel del S&P 500 y se cuenta entre ellas: son "
            "una más que para las del índice, y no es un error."
        )
    return texto


def frente_al_sector(analisis) -> str:
    """La celda «Frente al sector» del resumen."""
    if analisis.clase in (None, "etf"):
        return "—"
    ref = analisis.referencia
    if ref is None:
        return "sin ficha: " + etiqueta(MOTIVO_REFERENCIA, analisis.motivo_referencia)
    if ref.puesto is None:
        return "fuera: " + MOTIVOS_EN_CASTELLANO.get(ref.exclusion, str(ref.exclusion))
    return puesto(ref)


_PANEL_ATRAS = (
    " Pero aquí es el panel el que se quedó atrás: la empresa tiene trimestres "
    "posteriores al último del panel, y ésos no entran en la comparación. Rehacer "
    "el panel lo arregla."
)
_SEMESTRALES = (
    " Yahoo no trae trimestres suficientes de sus cuentas, que es lo que pasa con "
    "las empresas que publican cada semestre, como muchas europeas y las de Hong "
    "Kong: no es que la empresa sea joven."
)


def texto_exclusion(analisis) -> "str | None":
    """La guarda que la dejaría fuera, con su causa cuando la guarda la esconde.

    `historia_corta` culpa a la empresa de tener poca historia, y en el
    Analizador casi nunca es eso: o el panel está atrasado y sus últimos
    trimestres no entran, o la empresa publica cada semestre (NESN.SW, 0700.HK
    y RIO.L en la Task 14 de N1). A una de la SEC no se le inventa causa.
    """
    ref = analisis.referencia
    if ref is None or ref.exclusion is None:
        return None
    texto = etiqueta_exclusion(ref.exclusion)
    texto = texto[0].upper() + texto[1:] + "."
    if ref.exclusion == "historia_corta":
        if ref.filas_posteriores:
            texto += _PANEL_ATRAS
        elif analisis.clase in ("extranjera_sec", "sin_sec"):
            texto += _SEMESTRALES
    return texto


def detalle_pares(analisis) -> "str | None":
    """Lo que el voto «frente a sus pares» no dice por sí solo, o None.

    El voto sale `no_aplica/sin_pares` en dos casos que no son el mismo (Tasks
    14 y 17 de N1): sin ficha frente al sector, la causa está en
    `motivo_referencia`; con ficha y sin pilar de valoración (BRK-B), el sector
    sí tiene pares, y lo que faltan son los múltiplos de la empresa. Y con
    pilar, una guarda que la dejaría fuera no le quita el voto: en el ranking no
    pasa nunca, aquí sí, y se dice.
    """
    if analisis.clase in (None, "etf"):
        return None
    ref = analisis.referencia
    if ref is None:
        if analisis.motivo_referencia is None:
            return None
        return (
            "Frente a sus pares no vota porque no hay ficha frente al sector: "
            f"{etiqueta(MOTIVO_REFERENCIA, analisis.motivo_referencia)}."
        )
    if ref.ficha["pilares"].get("valoracion") is None:
        return (
            "Frente a sus pares no vota, y no por falta de pares: su sector los "
            "tiene. Lo que faltan son sus propios múltiplos (PER, EV/EBITDA, precio "
            "sobre flujo libre, precio sobre valor contable), así que no tiene "
            "pilar de valoración con que votar."
        )
    voto = ((analisis.valoracion or {}).get("votos") or {}).get("pares") or {}
    if ref.exclusion is not None and voto.get("voto") not in (None, "no_aplica"):
        return (
            "Frente a sus pares vota con su pilar de valoración aunque "
            f"{etiqueta_exclusion(ref.exclusion)}. En el ranking no competiría; aquí "
            "el voto cuenta, y vale lo que vale la ficha que lo sostiene."
        )
    return None


def sin_valor_base(valoracion) -> "str | None":
    """Una valoración con veredicto y sin valor base (7203.T en N1), o None.

    El valor base es la lectura de flujos, o la del beneficio residual: cuando
    ese voto no aplica --quema caja, sin flujo libre-- deciden los otros dos y
    hay veredicto sin cifra con que comparar el precio. Sin decirlo, la fila
    parece rota.
    """
    if not isinstance(valoracion, dict) or "veredicto" not in valoracion:
        return None
    if valoracion.get("valor") is not None:
        return None
    flujos = (valoracion.get("votos") or {}).get("flujos") or {}
    quien = "el del beneficio residual" if valoracion.get("metodo") == "residual" else "el de flujos"
    return (
        f"Hay veredicto pero no valor base: el voto que da el valor, {quien}, no "
        f"aplica ({medidores_valoracion.etiqueta_motivo(flujos.get('motivo'))}), y "
        "lo deciden los otros dos."
    )


# --- Los avisos de un ticker ---------------------------------------------------

# La forma con que Yahoo escribe una preferente: un guion, una P y la letra de
# la serie (JPM-PC, T-PA). En la tabla del S&P 500 sólo BF-B y BRK-B llevan
# guion, y ninguna con P.
_PREFERENTE = re.compile(r"^[A-Z]+-P[A-Z]$")


def aviso_sin_prima_pais(analisis) -> "str | None":
    """Una empresa de fuera de EE. UU. valorada en dólares sin prima por riesgo país.

    Sólo si además no es del S&P 500 (`fuente_sector == "sp500"`, la tabla con
    que se hace el panel): GRMN, ACN o MDT están domiciliadas fuera y se valoran
    exactamente como en M, y avisarlas diría que su valoración es distinta de
    la de candidatos. Decisión del usuario del 2026-10-26.
    """
    divisa = (analisis.valoracion or {}).get("divisa") or {}
    if not divisa.get("sin_prima_pais") or analisis.fuente_sector == "sp500":
        return None
    pais = analisis.identidad.pais if analisis.identidad is not None else None
    # El país lo escribe Yahoo: se escapa, como todo texto ajeno que llega a un
    # `st.warning`.
    return (
        "Valorada en dólares con la tasa libre de EE. UU. y la prima de un mercado "
        f"maduro, sin prima por riesgo país ({plano(pais)}). Si su país tiene más riesgo "
        "que EE. UU., el coste de capital sale bajo y el valor, alto. Se puede "
        "probar a mano con el deslizador de la prima de riesgo."
    )


def aviso_misma_empresa(ticker: str, sp500) -> "str | None":
    """Un ticker del SIC de la BMV cuya base es del S&P 500: la misma empresa.

    En el Sistema Internacional de Cotizaciones las extranjeras cotizan en la
    BMV con su símbolo de origen y `.MX`: AAPL.MX es Apple. Se inserta en su
    sector como si fuera otra, al lado de la propia AAPL y con cifras de Yahoo
    (N1: 217 de 424 y 137,6 $ de valor base frente a 183,0). No se fusionan: se
    avisa y se remite a la base. Sólo `.MX`: en otras bolsas el mismo símbolo es
    otra empresa (T.TO es TELUS y T, AT&T; BA.L es BAE Systems y BA, Boeing).
    """
    if not ticker.endswith(".MX"):
        return None
    base = ticker[: -len(".MX")]
    if base not in sp500:
        return None
    return (
        f"{ticker} es {base} cotizando en la BMV, en el Sistema Internacional de "
        "Cotizaciones: la misma empresa. Aquí sus cifras salen de Yahoo y no de la "
        f"SEC, y se compara con sus pares como si fuera otra, al lado de la propia "
        f"{base}. Para su ficha de la SEC, analiza {base}."
    )


def aviso_preferente(ticker: str) -> "str | None":
    """Un ticker con forma de acción preferente (`JPM-PC`, `T-PA`).

    Yahoo las da como `EQUITY` y en la SEC comparten CIK con la común, así que
    salen `sec` y se valoran con los estados y la capitalización de la empresa
    entera: el valor por acción no es el de la preferente.
    """
    if not _PREFERENTE.match(ticker):
        return None
    return (
        "Parece una acción preferente. Yahoo la da como una acción más y la SEC la "
        "tiene bajo la misma empresa, así que su ficha y su valoración son las de "
        "la empresa entera: el valor por acción no corresponde a la preferente."
    )


def aviso_adr(cociente) -> "str | None":
    """El recuento de los estados no cuadra con el de la cotización (`divisas.adr_dudosa`)."""
    if not adr_dudosa(cociente):
        return None
    return (
        f"El recuento de acciones de sus estados es {cociente:.2f} veces el de su "
        "cotización (capitalización ÷ precio): puede ser una ADR con un ratio "
        "distinto de 1, o una clase de acción que no es la que cotiza. El valor por "
        "acción se calcula con el de la cotización, como en M: esto avisa, no corrige."
    )


def aviso_panel_atrasado(analisis, trimestre_panel) -> "str | None":
    """El panel acaba antes que los trimestres del ticker, y los últimos no entran."""
    if trimestre_panel is None:
        return None
    ref = analisis.referencia
    atrasado = analisis.motivo_referencia == "sin_trimestres_comparables" or (
        ref is not None and ref.filas_posteriores > 0
    )
    if not atrasado:
        return None
    return (
        f"El panel de referencia llega hasta el {trimestre_panel} y "
        f"{analisis.ticker} ya tiene trimestres posteriores, que no entran en la "
        "comparación. Rehacer el panel lo pone al día."
    )


def aviso_bono_m(procedencia, hoy: date) -> "str | None":
    """La subasta del Bono M que da la tasa libre, si es más vieja de lo normal.

    `divisas.bono_m` sirve la última subasta guardada tenga la edad que tenga,
    mientras el `^TNX` deja de servirse a los siete días (revisión final de N1).
    Su fecha va siempre en la procedencia de la tasa libre; esto avisa cuando
    pasa de la mayor separación medida entre dos subastas.
    """
    if not isinstance(procedencia, dict) or procedencia.get("fuente") != "bono_m_10":
        return None
    try:
        subasta = date.fromisoformat(procedencia.get("fecha"))
    except (TypeError, ValueError):
        return None
    dias = (hoy - subasta).days
    if dias <= SEPARACION_MAXIMA_SUBASTAS.days:
        return None
    return (
        f"La tasa libre es la del Bono M de la subasta del {subasta:%d/%m/%Y}, hace "
        f"{dias} días: más que la mayor separación medida entre dos subastas "
        f"({SEPARACION_MAXIMA_SUBASTAS.days} días). Puede que Banxico no esté "
        "respondiendo y se esté usando la última guardada."
    )


def avisos(analisis, sp500, trimestre_panel, hoy: date) -> "list[tuple[str, str]]":
    """Los avisos de un ticker: `(forma corta para la fila, forma larga para el detalle)`."""
    ticker = analisis.ticker
    entradas = analisis.entradas
    base = ticker[: -len(".MX")] if ticker.endswith(".MX") else ticker
    candidatos = (
        (f"misma empresa que {base}", aviso_misma_empresa(ticker, sp500)),
        ("parece preferente", aviso_preferente(ticker)),
        ("sin prima por riesgo país", aviso_sin_prima_pais(analisis)),
        ("recuento de acciones dudoso", aviso_adr(None if entradas is None else entradas.cociente_adr)),
        ("panel atrasado", aviso_panel_atrasado(analisis, trimestre_panel)),
        ("Bono M antiguo", aviso_bono_m(None if entradas is None else entradas.procedencia_r_f, hoy)),
        ("sin valor base", sin_valor_base(analisis.valoracion)),
    )
    return [(corto, largo) for corto, largo in candidatos if largo]
