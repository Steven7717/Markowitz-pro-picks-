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
    """El valor por acción de lo que el negocio gana hoy, sin crecer, y el motivo si no hay.

    `Valor = (margen × ingresos_TTM × (1 − t) / wacc − deuda + efectivo) / acciones`:
    el margen operativo es el agregado de los años con dato (`margen_operativo`) y
    los ingresos son los del último ejercicio, el TTM más reciente. Se capitaliza
    el beneficio de hoy y no el de la media, para que el valor sea el del negocio
    que hay y no el de un promedio de lo que fue.

    Devuelve `(valor, None)` o `(None, motivo)`, y los motivos son claves de
    `votos.MOTIVOS`:
    - `sin_historia`: menos de `MIN_ANOS_HISTORIA` ejercicios con ingresos, o los
      ingresos del último no están declarados (sin ellos no hay beneficio que
      capitalizar);
    - `sin_beneficio_operativo`: hay años de sobra pero menos de
      `MIN_ANOS_HISTORIA` declaran el beneficio operativo. Es lo que pasa con XOM,
      JNJ, LLY, MRK, PFE, IBM o GE, que no etiquetan `OperatingIncomeLoss`: lo que
      falta es el dato, no la historia, y decir lo segundo despistaría;
    - `ebit_negativo`: el beneficio operativo normalizado no es positivo.

    El valor puede ser negativo con `motivo` vacío: si la deuda neta supera al
    beneficio capitalizado, el negocio sin crecer no cubre lo que se debe. Es un
    resultado y no un fallo, y el voto es entonces `neutra`.

    Exige `wacc > 0` y `acciones > 0` y no lo comprueba: quien llama lo garantiza.
    """
    margen = margen_operativo(fundamentos)
    if margen is None:
        con_ingresos = sum(1 for e in fundamentos.ejercicios if e.ingresos > 0)
        if con_ingresos >= MIN_ANOS_HISTORIA:
            return None, "sin_beneficio_operativo"
        return None, "sin_historia"
    # Con los ingresos del último sin declarar el producto sería NaN, y NaN no es
    # mayor que cero: saldría `ebit_negativo` cuando la causa es otra.
    if not fundamentos.ultimo.ingresos > 0:
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
