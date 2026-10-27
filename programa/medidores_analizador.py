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

from analizador.resolver import normalizar, tiene_sufijo
from aprobacion.carga import MOTIVOS_EN_CASTELLANO
from fundamentals.sectors import MIN_PARES

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
