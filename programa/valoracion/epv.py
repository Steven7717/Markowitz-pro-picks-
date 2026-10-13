"""Valor sin crecimiento (EPV de Greenwald): lo que vale el negocio si deja de crecer mañana.

Greenwald ajusta además la diferencia entre la amortización y el capex de
mantenimiento. Aquí no se hace, porque ninguna fuente separa el capex de
mantenimiento del de expansión, y la pantalla lo dice.
"""

import math

from valoracion.criterio import MIN_ANOS_HISTORIA
from valoracion.fundamentos import Fundamentos


def margen_operativo(fundamentos: Fundamentos) -> "float | None":
    """El margen operativo agregado: suma de beneficios operativos entre suma de ingresos.

    Agregado y no mediana, igual que `dcf.margen_fcff` y por la misma razón
    (decisión del 2026-10-12): la mediana pesaba un año pequeño del pasado lo
    mismo que el actual en una empresa que ha crecido mucho.
    """
    validos = [
        e for e in fundamentos.ejercicios
        if e.ingresos > 0 and math.isfinite(e.beneficio_operativo)
    ]
    if len(validos) < MIN_ANOS_HISTORIA:
        return None
    return sum(e.beneficio_operativo for e in validos) / sum(e.ingresos for e in validos)


def epv_por_accion(
    fundamentos: Fundamentos,
    t: float,
    wacc: float,
    deuda: float,
    efectivo: float,
    acciones: float,
) -> "tuple[float | None, str | None]":
    margen = margen_operativo(fundamentos)
    if margen is None:
        return None, "sin_historia"
    operativo = margen * fundamentos.ultimo.ingresos
    if not operativo > 0:
        return None, "ebit_negativo"
    empresa = operativo * (1 - t) / wacc
    return (empresa - deuda + efectivo) / acciones, None


def parte_crecimiento(epv: float, precio: float) -> "float | None":
    """Qué fracción del precio es apuesta por el crecimiento: 1 − EPV / precio."""
    if not (epv > 0 and precio > 0):
        return None
    return 1 - epv / precio
