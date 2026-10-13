"""Beneficio residual, para bancos y aseguradoras.

El flujo de caja libre de un banco no significa nada: prestar es su operación,
no una inversión. Lo que se valora es cuánto rinde su patrimonio por encima de
lo que cuesta: el patrimonio de hoy más el valor presente de ese exceso.

El ROE es constante en los diez años y el exceso sigue después, sin acabarse, a
través de un valor terminal de Gordon. Es la misma regla que el DCF, que
mantiene el margen para siempre: un modelo que mantuviera el margen del negocio
pero hiciera morir el exceso de rentabilidad del banco valoraría con dos varas.
La primera versión llevaba el ROE en línea recta hasta el coste del capital en
diez años y después exceso cero, y con ella todo banco o aseguradora grande
salía «cara» por construcción: la franquicia de calidad, la que gana más de lo
que cuesta de forma duradera, quedaba valorada al libro. Se midió con JPM en la
revisión de la Task 7; las cifras están en el spec, sección 7, y no se repiten
aquí para que las dos copias no se separen.

El valor terminal supone que desde el año 11 el patrimonio, y con él el exceso,
crece a `g_perpetuo` y no al ritmo de retención de los diez primeros años: con
un ROE alto, ese ritmo mantenido para siempre superaría a cualquier economía.
"""

import math
from dataclasses import dataclass

from valoracion.criterio import HOLGURA_GORDON, INVERSO_ROE_LIMITES

# El mismo horizonte que el DCF, importado y no recalculado: dos copias de una
# suma se separan igual que dos de un número. Con la tolerancia de coma flotante
# pasa lo mismo, y por eso no se declara una segunda.
from valoracion.dcf import _RUIDO_FLOTANTE, ANOS
from valoracion.inverso import Implicito, biseccion


@dataclass(frozen=True)
class DatosResidual:
    patrimonio: float
    k_e: float
    payout: float
    g_perpetuo: float
    acciones: float


def valor_residual(
    patrimonio: float, roe: float, k_e: float, payout: float, g_perpetuo: float
) -> "float | None":
    """Patrimonio, más el exceso de rentabilidad de diez años, más su valor terminal.

    `Valor = BV_0 + Σ_{t=1..10} (ROE − k_e) × BV_{t−1} / (1 + k_e)^t + TV / (1 + k_e)^10`,
    con `TV = (ROE − k_e) × BV_10 / (k_e − g_perpetuo)`: desde el año 11 el
    exceso crece a `g_perpetuo`, como el flujo del DCF.

    El patrimonio crece con lo que se retiene: `BV_t = BV_{t−1} × (1 + retenido)`,
    con `retenido = ROE × (1 − payout)` si el ROE es positivo. Con pérdida se
    retiene el ROE entero, negativo: nadie inyecta capital para cubrirla y se la
    come el patrimonio, sin reparto.

    `None` si el coste del capital no es positivo y finito, o no supera a
    `g_perpetuo` en al menos `HOLGURA_GORDON`: el valor terminal explota y
    cualquier número sería un artefacto. Es la misma regla que el DCF, y tampoco
    aquí se recorta nada para que cuadre.
    """
    if not (
        math.isfinite(k_e)
        and k_e > 0
        and k_e - g_perpetuo >= HOLGURA_GORDON - _RUIDO_FLOTANTE
    ):
        return None
    retenido = roe * (1 - payout) if roe > 0 else roe
    valor = patrimonio
    libros = patrimonio
    for ano in range(1, ANOS + 1):
        valor += (roe - k_e) * libros / (1 + k_e) ** ano
        libros *= 1 + retenido
    terminal = (roe - k_e) * libros / (k_e - g_perpetuo)
    return valor + terminal / (1 + k_e) ** ANOS


def valor_por_accion(
    datos: DatosResidual, roe: float, k_e: "float | None" = None
) -> "float | None":
    """Del valor del patrimonio al de cada acción.

    `k_e` sustituye al coste de los datos en los escenarios, y sólo mueve la tasa
    de descuento: no hay ya un ROE que converja hacia él. Sin patrimonio o
    acciones positivos no hay valor: con patrimonio negativo el signo del exceso
    se invierte, y el voto lo trata aparte (`patrimonio_negativo`).
    """
    if not (datos.patrimonio > 0 and datos.acciones > 0):
        return None
    coste = datos.k_e if k_e is None else k_e
    valor = valor_residual(datos.patrimonio, roe, coste, datos.payout, datos.g_perpetuo)
    if valor is None:
        return None
    return valor / datos.acciones


def roe_implicito(datos: DatosResidual, precio: float) -> Implicito:
    """El ROE constante que el precio exige.

    Con `k_e > g_perpetuo` el valor crece con el ROE, que es lo que la bisección
    necesita, en la zona que importa: desde un ROE de cero hacia arriba. Por
    debajo, una pérdida se come el patrimonio y las siguientes pesan menos, y la
    función baja; pero ahí el valor es negativo, así que un precio positivo nunca
    cae en esa zona y la bisección no se equivoca.

    Sin patrimonio o acciones positivos la función no tiene esa forma, y se
    dice aquí y no se fía de que `valor_por_accion` devuelva `None`, igual que
    hace `crecimiento_implicito` con el margen.
    """
    if not (datos.patrimonio > 0 and datos.acciones > 0):
        return Implicito(None, None)
    return biseccion(lambda roe: valor_por_accion(datos, roe), precio, INVERSO_ROE_LIMITES)
