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


def cifra(valor: float) -> str:
    """Dos decimales con coma, como el resto de la pantalla."""
    return f"{valor:.2f}".replace(".", ",")


def mes_legible(mes: "date | str") -> str:
    """El mes en palabras; si no es una fecha, el texto tal cual (viene de disco)."""
    try:
        if isinstance(mes, str):
            mes = date.fromisoformat(mes)
        return f"{_MESES[mes.month - 1]} {mes.year}"
    except (ValueError, AttributeError, TypeError):
        return str(mes)


def _nombre(tabla: dict, clave) -> str:
    """El nombre de pantalla, o la clave cruda si el acta trae una que ya no existe."""
    try:
        return tabla.get(clave, str(clave))
    except TypeError:  # clave no hashable
        return str(clave)


def lleva_macro(bloque) -> bool:
    """Si el bloque de la corrida trae una fase: un dict sin ella es una corrida sin macro.

    Una fase que ya no existe («caos») sí cuenta: se enseña cruda, no se esconde.
    """
    return isinstance(bloque, dict) and isinstance(bloque.get("fase"), str) and bool(bloque["fase"])


def etiqueta_corrida(bloque: "dict | None") -> str:
    if not lleva_macro(bloque):
        return "sin macro"
    fase, region = bloque.get("fase"), bloque.get("region")
    return (
        f"con macro: {_nombre(NOMBRE_FASE, fase)} "
        f"({_nombre(NOMBRE_REGION, region)}, {mes_legible(bloque.get('mes_dato'))})"
    )


def _lista(valor) -> list:
    return list(valor) if isinstance(valor, (list, tuple)) else []


def lo_que_movio(bloque: dict) -> str:
    if not lleva_macro(bloque):
        return "Esta corrida no lleva entorno macro."
    cabeza = (
        f"El Top está inclinado por la fase **{_nombre(NOMBRE_FASE, bloque.get('fase'))}** de "
        f"{_nombre(NOMBRE_REGION, bloque.get('region'))} "
        f"(dato de {mes_legible(bloque.get('mes_dato'))}). "
    )
    entradas = [str(t) for t in _lista(bloque.get("entradas"))]
    salidas = [str(t) for t in _lista(bloque.get("salidas"))]
    if not entradas and not salidas:
        return cabeza + "Con esta inclinación la lista no cambió."
    return (
        cabeza
        + f"Entraron por la macro: {', '.join(entradas) or 'ninguna'}. "
        + f"Salieron por la macro: {', '.join(salidas) or 'ninguna'}."
    )


def ajuste_ficha(ajuste: "float | None") -> "str | None":
    if ajuste is None:
        return None
    # Coma decimal, como el resto de la pantalla: `f"{0.25:.2f}"` da «0.25».
    if ajuste > 0:
        return f"La macro la subió (+{cifra(abs(ajuste))})."
    if ajuste < 0:
        return f"La macro la bajó (−{cifra(abs(ajuste))})."
    return "La macro no la tocó."
