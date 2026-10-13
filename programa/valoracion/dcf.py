"""El DCF de flujo de caja libre en dos etapas. Aritmética pura, sin red.

Se proyectan los ingresos y no el flujo libre: el flujo libre baila con cada
ciclo de inversión --en MU, un año de capex fuerte lo hunde y el siguiente se
dispara--, y proyectar desde uno u otro daría valores distintos para el mismo
negocio. El margen normalizado es el agregado de los años disponibles: la suma
de sus flujos libres entre la suma de sus ingresos. Alisa el ciclo de inversión
--el motivo para no partir del último año-- pero pesa cada año por su tamaño; la
mediana pesaba igual un valle pequeño que el año actual, y en MU daba un 6,8 %
frente a un 29 % del último año, con los ingresos de los últimos doce meses
2,7 veces los del anterior. El agregado da en MU en torno al 14 %.
"""

import math
from dataclasses import dataclass

from valoracion.criterio import (
    ANOS_ALTO_CRECIMIENTO,
    ANOS_CONVERGENCIA,
    HOLGURA_GORDON,
    MIN_ANOS_HISTORIA,
)
from valoracion.fundamentos import Fundamentos

ANOS = ANOS_ALTO_CRECIMIENTO + ANOS_CONVERGENCIA

# Una holgura exactamente en el listón (0,036 − 0,026) sale en coma flotante
# una pizca por debajo (del orden de 1e-18); sin esta tolerancia decidiría el
# redondeo, no el criterio.
_RUIDO_FLOTANTE = 1e-12


@dataclass(frozen=True)
class Datos:
    """Todo lo que el DCF necesita, en la moneda de los estados."""

    ingresos: float
    margen: float
    wacc: float
    g_perpetuo: float
    deuda: float
    efectivo: float
    acciones: float


@dataclass(frozen=True)
class Escenarios:
    """Valor por acción en tres escenarios. `None` donde no se cumple Gordon."""

    pesimista: "float | None"
    base: "float | None"
    optimista: "float | None"


def crecimientos(g: float, g_perpetuo: float) -> list[float]:
    """`g` cinco años y luego en línea recta hasta `g_perpetuo`, al que llega en el año diez."""
    convergencia = [
        g + (g_perpetuo - g) * k / ANOS_CONVERGENCIA
        for k in range(1, ANOS_CONVERGENCIA + 1)
    ]
    return [g] * ANOS_ALTO_CRECIMIENTO + convergencia


def valor_empresa(
    ingresos: float, margen: float, g: float, g_perpetuo: float, wacc: float
) -> "float | None":
    """Flujos de los años 1 a 10 más el valor terminal de Gordon, a fin de año.

    `None` si el coste de capital no supera al crecimiento perpetuo en al menos
    `HOLGURA_GORDON`: el valor terminal explota y cualquier número sería un
    artefacto. No se recorta el coste de capital para que cuadre: eso sería
    cambiar el escenario sin decirlo.
    """
    if wacc - g_perpetuo < HOLGURA_GORDON - _RUIDO_FLOTANTE:
        return None
    total = 0.0
    flujo = 0.0
    for ano, crecimiento in enumerate(crecimientos(g, g_perpetuo), start=1):
        ingresos *= 1 + crecimiento
        flujo = ingresos * margen
        total += flujo / (1 + wacc) ** ano
    terminal = flujo * (1 + g_perpetuo) / (wacc - g_perpetuo)
    return total + terminal / (1 + wacc) ** ANOS


def valor_por_accion(datos: Datos, g: float, wacc: "float | None" = None) -> "float | None":
    """Del valor de la empresa al de cada acción: menos deuda, más efectivo.

    `datos.acciones` es capitalización ÷ precio, el recuento en la base del
    precio. Con el de los estados, una ADR saldría con el valor multiplicado o
    dividido por su ratio.
    """
    coste = datos.wacc if wacc is None else wacc
    empresa = valor_empresa(datos.ingresos, datos.margen, g, datos.g_perpetuo, coste)
    if empresa is None:
        return None
    return (empresa - datos.deuda + datos.efectivo) / datos.acciones


def margen_fcff(fundamentos: Fundamentos, t: float) -> "float | None":
    """El margen agregado de flujo libre para la empresa de los años con dato.

    Flujo libre para la empresa = flujo operativo − capex + intereses × (1 − t):
    el flujo operativo ya descontó los intereses, y el DCF descuenta al coste de
    capital de toda la empresa, deuda incluida.

    El margen es Σ flujo libre ÷ Σ ingresos de los años que cuentan, no la
    mediana de sus márgenes: con la mediana un año pequeño de valle del ciclo
    pesa lo mismo que el actual, que en MU es casi tres veces mayor. Se descarta
    el año entero de los dos sumandos, no sólo del numerador, para que ningún
    año aporte ingresos sin su flujo.
    """
    flujos = 0.0
    ingresos = 0.0
    anos = 0
    for e in fundamentos.ejercicios:
        if not e.ingresos > 0:
            continue
        # NaN es «no declarado», no cero: NVDA tiene años sin capex, y contarlos
        # como cero inflaría el margen. Se descarta el año entero.
        if not (math.isfinite(e.flujo_operativo) and math.isfinite(e.capex)):
            continue
        # Un gasto financiero negativo es ingreso financiero neto (DIS, FTV en la
        # revisión de la Task 5): sumarlo con `abs` lo trataría como un coste.
        # Uno sin declarar suma cero por la misma cautela, y aquí no se descarta
        # el año: AAPL lo deja en blanco en tres de cinco, y perderlos dejaría
        # sin margen a una empresa sana. No se inventan intereses, así que el
        # flujo libre sólo puede quedarse corto, nunca inflado.
        intereses = (
            e.gasto_financiero
            if math.isfinite(e.gasto_financiero) and e.gasto_financiero > 0
            else 0.0
        )
        flujos += e.flujo_operativo - e.capex + intereses * (1 - t)
        ingresos += e.ingresos
        anos += 1
    if anos < MIN_ANOS_HISTORIA:
        return None
    return flujos / ingresos
