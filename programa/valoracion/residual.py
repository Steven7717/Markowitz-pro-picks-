"""Beneficio residual, para bancos y aseguradoras.

El flujo de caja libre de un banco no significa nada: prestar es su operación,
no una inversión. Lo que se valora es cuánto rinde su patrimonio por encima de
lo que cuesta. El ROE va desde el de partida hasta el coste del capital en diez
años, en línea recta, y después el exceso es cero: no hay valor terminal aparte.
"""

from dataclasses import dataclass

from valoracion.criterio import INVERSO_ROE_LIMITES

# El mismo horizonte que el DCF, importado y no recalculado: dos copias de una
# suma se separan igual que dos de un número.
from valoracion.dcf import ANOS
from valoracion.inverso import Implicito, biseccion


@dataclass(frozen=True)
class DatosResidual:
    patrimonio: float
    k_e: float
    payout: float
    acciones: float


def rentabilidades(roe_ini: float, k_e: float) -> list[float]:
    return [roe_ini + (k_e - roe_ini) * (ano - 1) / (ANOS - 1) for ano in range(1, ANOS + 1)]


def valor_residual(patrimonio: float, roe_ini: float, k_e: float, payout: float) -> float:
    """Patrimonio más el valor presente del exceso de rentabilidad de cada año.

    El patrimonio crece con lo que se retiene: `(1 + ROE × (1 − payout))`.
    """
    valor = patrimonio
    libros = patrimonio
    for ano, roe in enumerate(rentabilidades(roe_ini, k_e), start=1):
        valor += (roe - k_e) * libros / (1 + k_e) ** ano
        libros *= 1 + roe * (1 - payout)
    return valor


def valor_por_accion(
    datos: DatosResidual, roe_ini: float, k_e: "float | None" = None
) -> "float | None":
    coste = datos.k_e if k_e is None else k_e
    if not coste > 0:
        return None
    return valor_residual(datos.patrimonio, roe_ini, coste, datos.payout) / datos.acciones


def roe_implicito(datos: DatosResidual, precio: float) -> Implicito:
    """El ROE de partida que el precio exige."""
    return biseccion(lambda roe: valor_por_accion(datos, roe), precio, INVERSO_ROE_LIMITES)
