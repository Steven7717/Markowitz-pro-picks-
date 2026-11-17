# macro/textos.py
"""Lo que el usuario lee del entorno macro. Nunca se guarda en disco.

Las claves de `macro/criterio.py` son el dato; esto es solo cómo se dicen. Es
la lección de «La etiqueta de pantalla que se guardaba en disco» (CONTEXTO.md).
"""

from datetime import date

NOMBRE_FASE = {
    "recuperacion": "Recuperación",
    "expansion": "Expansión",
    "desaceleracion": "Desaceleración",
    "contraccion": "Contracción",
}

NOMBRE_REGION = {
    "usa": "Estados Unidos",
    "mex": "México",
    "eurozona": "Eurozona (4 grandes)",
    "china": "China",
    "g7": "Global (G7)",
}

NOMBRE_SECTOR = {
    "Communication Services": "Comunicaciones",
    "Consumer Discretionary": "Consumo discrecional",
    "Consumer Staples": "Consumo básico",
    "Energy": "Energía",
    "Financials": "Financieras",
    "Health Care": "Salud",
    "Industrials": "Industriales",
    "Information Technology": "Tecnología",
    "Materials": "Materiales",
    "Real Estate": "Inmobiliarias",
    "Utilities": "Servicios públicos",
}

POR_QUE = {
    "recuperacion": {
        "Financials": "La curva se empina y el crédito vuelve: el margen de los bancos se ensancha.",
        "Consumer Discretionary": "La renta y el empleo se recuperan, y el gasto que se aplazó vuelve.",
        "Industrials": "Las empresas reponen inventarios y retoman la inversión aplazada.",
        "Utilities": "Su refugio pesa menos cuando el riesgo vuelve a pagarse.",
        "Consumer Staples": "Su estabilidad deja de cotizar con prima cuando todo crece.",
        "Health Care": "Defensiva: sus beneficios no dependen del ciclo y se quedan atrás en el rebote.",
    },
    "expansion": {
        "Information Technology": "La inversión empresarial en tecnología crece con el ciclo asentado.",
        "Communication Services": "Publicidad y suscripciones acompañan al consumo firme.",
        "Industrials": "Los pedidos y la capacidad utilizada siguen subiendo.",
        "Utilities": "Los tipos suben y su dividendo compite peor con la renta fija.",
        "Materials": "Sus precios ya recogieron la recuperación y el margen deja de crecer.",
    },
    "desaceleracion": {
        "Energy": "Al final del ciclo la demanda aprieta la oferta y las materias primas suben.",
        "Materials": "Igual que la energía: precios altos con la capacidad ya al límite.",
        "Consumer Staples": "Se vende lo mismo aunque el ciclo se enfríe.",
        "Health Care": "Beneficios que no dependen del ciclo cuando el ciclo empieza a fallar.",
        "Information Technology": "Las valoraciones altas sufren cuando el crecimiento esperado baja.",
        "Consumer Discretionary": "Es lo primero que se recorta cuando el hogar se aprieta.",
    },
    "contraccion": {
        "Consumer Staples": "Comida, higiene y hogar se compran también en recesión.",
        "Health Care": "La demanda médica no espera al ciclo.",
        "Utilities": "Ingresos regulados y tipos que bajan: el refugio clásico.",
        "Industrials": "Los pedidos se cancelan y la capacidad sobra.",
        "Information Technology": "La inversión en tecnología se aplaza y los múltiplos se comprimen.",
        "Consumer Discretionary": "El gasto que se puede aplazar, se aplaza.",
    },
}

MOTIVO = {
    "indeterminada": "El indicador no se decide: el último mes desmiente la tendencia de tres meses.",
    "serie_corta": "No hay meses suficientes para leer una dirección.",
    "dato_rancio": "El último dato tiene más de tres meses; no se usa para mover el Top.",
    "sin_red": "La OCDE no responde y no hay nada guardado.",
    "serie_desconocida": "La OCDE no tiene esa serie; puede que haya cambiado su catálogo.",
    "respuesta_ilegible": "La OCDE respondió algo que no es la tabla esperada.",
    "serie_con_huecos": "Faltan meses en los datos recientes del indicador; no se lee la dirección.",
}

AVISO_EVIDENCIA = (
    "La rotación de sectores por fase del ciclo tiene una evidencia floja: el ciclo "
    "se fecha bien a toro pasado y mal en tiempo real. La inclinación es pequeña y "
    "no promete rentabilidad."
)

_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def mes_legible(mes: "date | str") -> str:
    if isinstance(mes, str):
        mes = date.fromisoformat(mes)
    return f"{_MESES[mes.month - 1]} {mes.year}"


def etiqueta_corrida(bloque: "dict | None") -> str:
    if not bloque:
        return "sin macro"
    return (
        f"con macro: {NOMBRE_FASE[bloque['fase']]} "
        f"({NOMBRE_REGION[bloque['region']]}, {mes_legible(bloque['mes_dato'])})"
    )


def lo_que_movio(bloque: dict) -> str:
    cabeza = (
        f"El Top está inclinado por la fase **{NOMBRE_FASE[bloque['fase']]}** de "
        f"{NOMBRE_REGION[bloque['region']]} (dato de {mes_legible(bloque['mes_dato'])}). "
    )
    if not bloque["entradas"] and not bloque["salidas"]:
        return cabeza + "Con esta inclinación la lista no cambió."
    return (
        cabeza
        + f"Entraron por la macro: {', '.join(bloque['entradas']) or 'ninguna'}. "
        + f"Salieron por la macro: {', '.join(bloque['salidas']) or 'ninguna'}."
    )


def ajuste_ficha(ajuste: "float | None") -> "str | None":
    if ajuste is None:
        return None
    # Coma decimal, como el resto de la pantalla: `f"{0.25:.2f}"` da «0.25».
    cifra = f"{abs(ajuste):.2f}".replace(".", ",")
    if ajuste > 0:
        return f"La macro la subió (+{cifra})."
    if ajuste < 0:
        return f"La macro la bajó (−{cifra})."
    return "La macro no la tocó."
