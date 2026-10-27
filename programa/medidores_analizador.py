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
from datetime import date, datetime, timezone

import medidores_valoracion
from analizador.divisas import SEPARACION_MAXIMA_SUBASTAS, adr_dudosa
from analizador.resolver import normalizar, tiene_sufijo
from aprobacion.carga import MOTIVOS_EN_CASTELLANO
from fundamentals.sectors import MIN_PARES
from noticias import cache

# Privadas y aun así importadas: son el formato de las cifras de la valoración
# y los nombres de los supuestos. Una segunda copia aquí es como empiezan a
# separarse, y el Analizador tiene que escribir las cifras igual que Revisar
# candidatos.
from medidores_valoracion import _NOMBRE_SUPUESTO, _dinero, _numero, _pct
from noticias.texto import cada, cuanto_falta, hace, plano
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


# --- La moneda del precio -------------------------------------------------------


def en_moneda_del_precio(valoracion):
    """La valoración con las cifras por acción en la moneda del precio.

    `analizador.valorar.valorar` las da en la de la valoración: AMX cotiza en
    dólares y se valora en pesos (554,5 MXN son 29,69 $), y SHEL.L cotiza en
    peniques y se valora en dólares (67,92 $ son 5.079,9 peniques). Se divide
    por `divisa.tipo_precio`, que es el tipo con que `divisas.perfil_en` llevó
    el precio a la moneda de la valoración. El margen de seguridad es un
    cociente y no cambia; las tasas (el crecimiento implícito) tampoco.

    Devuelve una copia: lo de dentro es lo que va al acta, en su moneda. Sin un
    tipo válido no se convierte nada, y una fallida --que no lleva `moneda`--
    toma la del precio de su divisa (revisión final de N1).
    """
    if not isinstance(valoracion, dict):
        return valoracion
    divisa = valoracion.get("divisa")
    if not isinstance(divisa, dict):
        return valoracion
    tipo = _numero(divisa.get("tipo_precio"))
    moneda = divisa.get("moneda_precio")
    if tipo is None or tipo <= 0 or not isinstance(moneda, str):
        return valoracion
    if "veredicto" not in valoracion:
        return {**valoracion, "moneda": moneda}

    def a_precio(valor):
        numero = _numero(valor)
        return None if numero is None else numero / tipo

    salida = {**valoracion, "moneda": moneda, "precio": a_precio(valoracion.get("precio"))}
    valor = valoracion.get("valor")
    if isinstance(valor, dict):
        salida["valor"] = {k: a_precio(valor.get(k)) for k in ("pesimista", "base", "optimista")}
    epv = valoracion.get("epv")
    if isinstance(epv, dict):
        salida["epv"] = {**epv, "por_accion": a_precio(epv.get("por_accion"))}
    return salida


# --- Los deslizadores y sus tablas ----------------------------------------------


def etiqueta_deslizador(nombre: str) -> str:
    """«Crecimiento de referencia (%)», «Beta»: el nombre del supuesto con su unidad."""
    texto = _NOMBRE_SUPUESTO.get(nombre, nombre)
    texto = texto[0].upper() + texto[1:]
    return texto if nombre == "beta" else f"{texto} (%)"


def _y(partes: "list[str]") -> str:
    """«a», «a y b», «a, b y c»; con «e» delante de una i, como pide la RAE."""
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    ultimo = partes[-1]
    inicio = ultimo.lower()
    conjuncion = "e" if inicio.startswith(("i", "hi")) and not inicio.startswith(("ie", "hie")) else "y"
    return f"{', '.join(partes[:-1])} {conjuncion} {ultimo}"


def lista_de_supuestos(nombres) -> str:
    """Los supuestos movidos, en palabras: «beta y crecimiento de referencia»."""
    return _y([_NOMBRE_SUPUESTO.get(nombre, nombre) for nombre in nombres])


def falta_tasa(entradas) -> str:
    """Por qué no hay tasa libre y qué hacer, encima de la casilla donde se pone a mano.

    `fallida("sin_bono_m")` sólo dice que falta; el motivo concreto viaja en
    `Entradas.motivo_r_f` (revisión de la Task 13 de N1).
    """
    motivo = etiqueta(MOTIVO_TASA, entradas.motivo_r_f)
    if entradas.divisa.moneda_valoracion == "MXN":
        que_es = "Para una empresa que se valora en pesos es el rendimiento del Bono M a 10 años de Banxico."
    else:
        que_es = "Es el rendimiento del Tesoro de EE. UU. a 10 años."
    return (
        f"Sin tasa libre de riesgo: {motivo}. {que_es} Ponla a mano y se valora con "
        "ella; no se guarda."
    )


def tabla_sensibilidad(sensibilidad, tipo_precio: float, moneda: str) -> "tuple[list[str], list[list[str]]]":
    """La tabla de sensibilidad del valor base, en la moneda del precio.

    Filas de coste de capital y columnas de crecimiento a perpetuidad, con la
    del programa marcada «(base)». Una casilla vacía, «—», es que ahí no se
    cumple Gordon o el coste no es positivo (`dcf.sensibilidad`).
    """
    centro_g = len(sensibilidad.gs) // 2
    centro_wacc = len(sensibilidad.waccs) // 2
    columnas = ["Coste de capital ↓ · crecimiento a perpetuidad →"] + [
        _pct(g) + (" (base)" if i == centro_g else "") for i, g in enumerate(sensibilidad.gs)
    ]
    filas = []
    for i, (wacc, valores) in enumerate(zip(sensibilidad.waccs, sensibilidad.valores)):
        rotulo = _pct(wacc) + (" (base)" if i == centro_wacc else "")
        filas.append([rotulo] + ["—" if v is None else _dinero(v / tipo_precio, moneda) for v in valores])
    return columnas, filas


def _millones(valor) -> str:
    numero = _numero(valor)
    return "n/d" if numero is None else f"{numero / 1e6:,.0f} M".replace("-", "−")


def tabla_proyeccion(proyeccion, moneda: str) -> "tuple[list[str], list[list[str]]]":
    """Los diez años del escenario base y el valor terminal, en millones.

    En la moneda de la valoración, la de las cuentas: son cifras de la empresa
    entera, no por acción, y no se pasan a la del precio.
    """
    columnas = [
        "Año",
        "Crecimiento de los ingresos",
        f"Ingresos ({moneda})",
        f"Flujo libre ({moneda})",
        f"Valor presente ({moneda})",
    ]
    filas = [
        [str(a.ano), _pct(a.crecimiento), _millones(a.ingresos), _millones(a.flujo), _millones(a.descontado)]
        for a in proyeccion.anos
    ]
    filas.append(["Terminal", "—", "—", "—", _millones(proyeccion.terminal_descontado)])
    return columnas, filas


# --- La fila del resumen ------------------------------------------------------

# El spec pide Ticker, Clase, Precio, Valor base, Margen de seguridad,
# Veredicto, Frente al sector y Próximo evento. Se añaden el nombre largo (un
# `BRK B` mal partido da BRK y B, y B es Barrick), la hora del precio (el precio
# no se refresca solo, a propósito) y los avisos, que es donde una fila que
# falla dice por qué.
COLUMNAS = (
    "Ticker",
    "Nombre",
    "Clase",
    "Precio",
    "Hora del precio",
    "Valor base",
    "Margen de seguridad",
    "Veredicto",
    "Frente al sector",
    "Próximo evento",
    "Avisos",
)


def hora_del_precio(hora: object) -> str:
    """La hora de la cotización en UTC, o «—». Una hora sin zona no se da por UTC."""
    if not isinstance(hora, str):
        return "—"
    try:
        momento = datetime.fromisoformat(hora)
    except ValueError:
        return "—"
    if momento.tzinfo is None:
        return "—"
    return momento.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def texto_evento(evento, hoy: date) -> str:
    """«Resultados, 17/12/2026 (en 52 días)»."""
    return f"{evento.detalle}, {evento.cuando:%d/%m/%Y} ({cuanto_falta(evento.cuando, hoy)})"


def motivo_de_la_valoracion(analisis) -> str:
    """Por qué no hay valoración, con el motivo concreto de la tasa libre si es el Bono M.

    `fallida("sin_bono_m")` sólo dice que falta; lo concreto viaja en
    `Entradas.motivo_r_f` (revisión de la Task 13 de N1).
    """
    valoracion = analisis.valoracion if isinstance(analisis.valoracion, dict) else {}
    motivo = valoracion.get("motivo")
    if motivo == "sin_bono_m" and analisis.entradas is not None:
        return f"sin tasa libre: {etiqueta(MOTIVO_TASA, analisis.entradas.motivo_r_f)}"
    return medidores_valoracion.etiqueta_motivo(motivo)


def fila(analisis, proximo_evento, sp500, trimestre_panel, hoy: date) -> dict:
    """La fila de un ticker en el resumen, como textos, en el orden de `COLUMNAS`.

    El precio es el de la identidad, en la moneda en que cotiza; el valor base,
    el de la valoración pasada a esa misma moneda (`en_moneda_del_precio`). Un
    ticker sin clase sólo dice por qué, y conserva el nombre y el precio si
    Yahoo los dio (sin el correo de EDGAR, por ejemplo).
    """
    salida = dict.fromkeys(COLUMNAS, "—")
    salida["Ticker"] = analisis.ticker
    salida["Nombre"] = nombre(analisis)
    identidad = analisis.identidad
    if identidad is not None and identidad.precio is not None:
        salida["Precio"] = _dinero(identidad.precio, identidad.moneda or "")
        salida["Hora del precio"] = hora_del_precio(identidad.hora)
    if analisis.clase is None:
        salida["Avisos"] = motivo_de_la_fila(analisis)
        return salida
    salida["Clase"] = CLASE.get(analisis.clase, analisis.clase)
    salida["Frente al sector"] = frente_al_sector(analisis)
    if proximo_evento is not None:
        salida["Próximo evento"] = texto_evento(proximo_evento, hoy)
    cortos = [corto for corto, _ in avisos(analisis, sp500, trimestre_panel, hoy)]
    valoracion = en_moneda_del_precio(analisis.valoracion)
    if isinstance(valoracion, dict) and "veredicto" in valoracion:
        etiqueta_, _ = medidores_valoracion.VEREDICTO.get(valoracion["veredicto"], (valoracion["veredicto"], None))
        salida["Veredicto"] = etiqueta_
        base = (valoracion.get("valor") or {}).get("base")
        if _numero(base) is not None:
            salida["Valor base"] = _dinero(base, valoracion.get("moneda") or "")
        if _numero(valoracion.get("margen_seguridad")) is not None:
            salida["Margen de seguridad"] = _pct(valoracion["margen_seguridad"])
    elif isinstance(valoracion, dict):
        salida["Veredicto"] = "Sin valoración"
        cortos.insert(0, motivo_de_la_valoracion(analisis))
    salida["Avisos"] = "; ".join(cortos) or "—"
    return salida


def leyenda_resumen() -> str:
    """Lo que dice cada columna, en markdown, para debajo de la tabla.

    Glosa la identidad de lo que la tabla no explica sola, la primera vez que
    sale en la pantalla («Registro del texto»).
    """
    return (
        "**Valor base**: el valor por acción del escenario base, en la moneda en "
        "que cotiza. **Margen de seguridad**: (valor base − precio) / precio, "
        "cuánto más vale que su precio. **Veredicto**: lo que dicen juntos los "
        "tres votos —flujos, valor sin crecimiento y pares—; las cuentas, en la "
        "pestaña Valoración. **Frente al sector**: su puesto global por la nota "
        "compuesta, que resume los cuatro pilares —calidad, crecimiento, valoración "
        "y solidez— medidos frente a las empresas del S&P 500 de su sector.  \n"
        "El precio no se refresca solo, a propósito: un veredicto que cambia cada "
        "minuto con el precio es ruido. Lleva su hora, y el tiempo real está en el "
        "gráfico."
    )


# --- Lo que viene y las noticias ------------------------------------------------

# Los nombres de las tres fuentes de `noticias/traer.py`, en el orden de la
# pantalla: lo que viene, los hechos y la prensa.
ETIQUETA_FUENTE = {"agenda": "Calendario", "hechos": "Hechos (8-K)", "prensa": "Prensa"}

# Por encima de esto la lista deja de leerse y empieza a ser un muro. Se recorta
# diciéndolo: un recorte silencioso es indistinguible de que no hubiera más.
# Era el `TOPE` de Noticias, que listaba un libro entero; aquí es por ticker.
TOPE_NOTICIAS = 40

PESTANAS = ("Resumen", "Valoración", "Fundamentales", "Gráfico", "Noticias y calendario")
# Un ETF no se valora ni se compara con un sector: las pestañas que saldrían
# vacías no se dibujan (spec, «Las pestañas del detalle»).
PESTANAS_ETF = ("Resumen", "Gráfico", "Noticias y calendario")


def pestanas_de(clase: "str | None") -> "tuple[str, ...]":
    return PESTANAS_ETF if clase == "etf" else PESTANAS


def proximos(eventos) -> list:
    """Los eventos con fecha, del más cercano al más lejano.

    Los punteros macro van con `cuando=None`: meterlos en el orden sería un
    `TypeError`, y ponerles una fecha sería inventarse el dato que no se tiene.
    """
    return sorted((e for e in eventos if e.cuando is not None), key=lambda e: e.cuando)


def proximo(eventos):
    """El evento más cercano, o None."""
    ordenados = proximos(eventos)
    return ordenados[0] if ordenados else None


def repartir_hechos(hechos) -> "tuple[list, list]":
    """Los 8-K destacados y los de trámite, del más nuevo al más viejo.

    El criterio ya decidió al bajarlos (`Hecho.material`): aquí sólo se reparte.
    Volver a mirar los tipos a mano pondría un segundo criterio en el programa.
    """
    destacados = sorted((h for h in hechos if h.material), key=lambda h: h.cuando, reverse=True)
    plegados = sorted((h for h in hechos if not h.material), key=lambda h: h.cuando, reverse=True)
    return destacados, plegados


def recorte(elementos: list, tope: int = TOPE_NOTICIAS) -> "tuple[list, int]":
    """Los que caben y cuántos se quedaron fuera."""
    return elementos[:tope], max(0, len(elementos) - tope)


def formato_noticia(clase: str) -> str:
    """El formato de un titular, para descartarlo sin abrirlo.

    Yahoo mete vídeos entre las noticias, y en la pasada real de H devolvió
    STORY para casi todo: se pinta lo que venga, y sólo el vídeo lleva nombre
    propio.
    """
    return "Vídeo" if clase.upper() == "VIDEO" else clase.capitalize()


def fuentes_de(clase: "str | None") -> "tuple[str, ...]":
    """Las fuentes de noticias de cada clase: los 8-K sólo los presenta quien hace 10-K."""
    return ("agenda", "hechos", "prensa") if clase == "sec" else ("agenda", "prensa")


_SIN_HECHOS = {
    "extranjera_sec": (
        "Presenta 20-F o 40-F y no 8-K. Sus 6-K no se interpretan: no llevan códigos "
        "de item, y el criterio de qué es material se construyó sobre ellos."
    ),
    "sin_sec": "No presenta en la SEC: aquí hay calendario y prensa, pero no hechos.",
    "etf": "Un ETF no presenta 8-K: aquí hay calendario y prensa, pero no hechos.",
}


def sin_hechos(clase: "str | None") -> "str | None":
    """Por qué una clase no tiene 8-K, o None si los tiene."""
    return _SIN_HECHOS.get(clase)


def linea_de_hora(fuente: str, cuando, vigente: bool) -> str:
    """Cuándo se trajo lo que se está viendo de una fuente, en markdown.

    La hora se enseña siempre, esté el dato fresco o no: un dato que se lee como
    recién traído sin serlo es peor que no tener dato. Es la regla de Noticias.
    """
    nombre_ = ETIQUETA_FUENTE[fuente]
    if cuando is None:
        return f"**{nombre_}**: no se pudo traer nada."
    linea = (
        f"**{nombre_}**: se descargó el {cuando.astimezone():%d/%m/%Y a las %H:%M} "
        f"({hace(cuando)}). Se vuelve a pedir cada {cada(cache.VALIDEZ[fuente])}."
    )
    if not vigente:
        linea += " La descarga falló y se enseña lo último que había guardado."
    return linea


# --- La identidad, contra quién se compara y el panel ---------------------------

_ORIGEN_SECTOR = {
    "sp500": "el de la tabla del S&P 500",
    "yahoo": "el de Yahoo, traducido a GICS",
    "sin_sector": "Yahoo no da uno que se pueda traducir",
}


def ficha_de_identidad(analisis) -> str:
    """Nombre aparte, lo demás de un ticker en markdown: clase, datos, sector y monedas.

    Lo que viene de Yahoo pasa por `noticias.texto.plano`: es texto ajeno.
    """
    identidad = analisis.identidad
    lineas = [
        f"**Clase**: {CLASE.get(analisis.clase, '—')} · **Datos**: "
        f"{FUENTE_DE_DATOS.get(analisis.clase, '—')}"
    ]
    if analisis.clase != "etf":
        sector = plano(analisis.sector) if analisis.sector else "sin sector GICS"
        lineas.append(f"**Sector**: {sector} ({_ORIGEN_SECTOR.get(analisis.fuente_sector, '—')})")
    if identidad is not None:
        bolsa = plano(identidad.bolsa) if identidad.bolsa else "—"
        lineas.append(f"**Cotiza en** {plano(identidad.moneda or '—')}, en la bolsa {bolsa}")
    entradas = analisis.entradas
    if entradas is not None:
        divisa = entradas.divisa
        if divisa.moneda_estados != divisa.moneda_valoracion:
            lineas.append(
                f"**Estados** en {plano(divisa.moneda_estados)}, convertidos a "
                f"{plano(divisa.moneda_valoracion)} para valorar"
            )
        elif divisa.moneda_valoracion != divisa.moneda_precio:
            lineas.append(
                f"**Se valora** en {plano(divisa.moneda_valoracion)}, la moneda de sus "
                "estados; el valor se enseña en la del precio"
            )
    return "  \n".join(lineas)


def contra_quien(analisis, pares_del_sector: int, fecha_panel: date) -> str:
    """Con qué empresas se compara la ficha, y con qué panel.

    `pares_del_sector` son las del sector en el panel; una del panel no se
    cuenta a sí misma. Para las de fuera de EE. UU., el texto del spec sobre
    los múltiplos y el riesgo país.
    """
    if analisis.referencia is not None and analisis.referencia.en_panel:
        quienes = f"las otras {pares_del_sector - 1} empresas"
    else:
        quienes = f"las {pares_del_sector} empresas"
    texto = (
        f"Comparada con {quienes} del S&P 500 de {analisis.sector}, con el panel de "
        f"referencia del {fecha_panel:%d/%m/%Y}."
    )
    pais = analisis.identidad.pais if analisis.identidad is not None else None
    if pais not in (None, "United States") and analisis.fuente_sector != "sp500":
        texto += (
            " Márgenes y rentabilidad son comparables; los múltiplos lo son menos, "
            "porque no incluyen el riesgo país."
        )
    return texto


def fecha_del_panel(fecha_panel: date, trimestre: str, frescura) -> str:
    """De cuándo es la referencia sectorial y de cuándo los candidatos."""
    texto = (
        f"Referencia sectorial: el panel del S&P 500 del {fecha_panel:%d/%m/%Y}, con "
        f"trimestres hasta el {trimestre}."
    )
    if frescura.candidatos is None:
        return texto + " No hay candidatos generados: Revisar candidatos enseña la lista de ejemplo."
    return texto + f" Los candidatos son del {frescura.candidatos:%d/%m/%Y}."


SIN_PANEL = (
    "No hay panel de referencia del S&P 500: sin él no hay ficha frente al sector "
    "ni voto de pares, y la valoración sale con dos votos. Se construye aparte, "
    "gratis, sin tocar tus candidatos ni lo que tengas marcado en Revisar candidatos."
)

PANEL_POSTERIOR = (
    "El panel es más nuevo que los candidatos: se rehízo aparte. La ficha de un "
    "candidato aquí puede diferir un poco de la de Revisar candidatos, que se "
    "calculó con el panel de entonces."
)

PANEL_ATRASADO = (
    "El panel se ha quedado atrás: algún ticker de los de abajo tiene trimestres "
    "posteriores al último del panel, y ésos no entran en su comparación. "
    "Rehacer el panel lo pone al día."
)

AYUDA_PANEL = (
    "La misma descarga que «Generar gratis», pero sólo escribe el panel "
    "(salidas/panel.parquet): ni las fichas, ni las casillas marcadas, ni los "
    "añadidos a mano. Unos dos minutos con la caché llena, y bastantes más la "
    "primera vez."
)


# --- El gate --------------------------------------------------------------------


def puerta(analisis) -> "str | None":
    """Por qué este ticker no puede ir a la revisión, o None si puede.

    Sólo pasa lo que cotiza en dólares (decisión del usuario del 2026-10-26).
    El optimizador baja precios sin convertir divisas y los libros van en
    dólares: una serie en pesos entre series en dólares mezclaría dos monedas
    en la misma covarianza, el error que el sub-proyecto L evitó. AMX y TSM
    cotizan en dólares y pasan; WALMEX.MX, no. Un ETF no se valora, y desde aquí
    no se lleva (D5).
    """
    if analisis.clase == "etf":
        return (
            "Un ETF no se valora, así que el Analizador no lo lleva a la revisión. "
            "Si lo quieres en el optimizador, añádelo a mano en Revisar candidatos."
        )
    moneda = analisis.identidad.moneda if analisis.identidad is not None else None
    if moneda == "USD":
        return None
    return (
        f"{analisis.ticker} cotiza en {moneda or 'una moneda que Yahoo no dio'}, y sólo "
        "pasan a la revisión las que cotizan en dólares. El optimizador baja los "
        "precios sin convertir divisas y los libros van en dólares: una serie en otra "
        "moneda entre series en dólares mezclaría dos monedas en la misma covarianza. "
        "Una ADR, como TSM, cotiza en dólares y sí pasa."
    )


_VOTO_CORTO = {"flujos": "flujos", "sin_crecimiento": "valor sin crecimiento", "pares": "pares"}


def motivo_para_la_revision(valoracion, hoy: date) -> str:
    """El motivo ya redactado de «Añadir a la revisión», con los supuestos del programa.

    «Analizador, 12/10/2026: infravalorada (flujos y pares a favor), supuestos
    del programa», como en el spec. Es editable, y el acta guarda lo que quede
    escrito: es texto del usuario, no una etiqueta de pantalla.
    """
    fecha = f"{hoy:%d/%m/%Y}"
    if not isinstance(valoracion, dict) or "veredicto" not in valoracion:
        motivo = valoracion.get("motivo") if isinstance(valoracion, dict) else None
        return (
            f"Analizador, {fecha}: sin valoración "
            f"({medidores_valoracion.etiqueta_motivo(motivo)})."
        )
    etiqueta_, _ = medidores_valoracion.VEREDICTO.get(valoracion["veredicto"], (valoracion["veredicto"], None))
    veredicto = etiqueta_[0].lower() + etiqueta_[1:]
    nombres = dict(_VOTO_CORTO)
    if valoracion.get("metodo") == "residual":
        nombres["flujos"] = "beneficio residual"
    votos = valoracion.get("votos") or {}
    a_favor = [nombres[c] for c in _VOTO_CORTO if (votos.get(c) or {}).get("voto") == "barata"]
    en_contra = [nombres[c] for c in _VOTO_CORTO if (votos.get(c) or {}).get("voto") == "cara"]
    partes = []
    if a_favor:
        partes.append(f"{_y(a_favor)} a favor")
    if en_contra:
        partes.append(f"{_y(en_contra)} en contra")
    detalle = f" ({', '.join(partes)})" if partes else ""
    return f"Analizador, {fecha}: {veredicto}{detalle}, supuestos del programa."
