"""Constructores de datos de prueba para `valoracion/`, sin red.

Las cifras por defecto están elegidas para que las cuentas salgan a mano:
ingresos 1.000, flujo operativo 300, capex 100, intereses 20 (margen de flujo
libre para la empresa 0,215 con t = 0,25), beneficio operativo 200, beneficio
neto 120 sobre un patrimonio de 1.000 (ROE 0,12). El perfil cotiza a 100 con
una capitalización de 1.000: diez acciones.
"""

from datetime import date

from valoracion.fundamentos import Ejercicio, Fundamentos
from valoracion.mercado import Perfil


def ejercicio(ano: int = 2026, **sobre) -> Ejercicio:
    valores = dict(
        fin=date(ano, 9, 30),
        ingresos=1000.0,
        flujo_operativo=300.0,
        capex=100.0,
        gasto_financiero=20.0,
        beneficio_operativo=200.0,
        beneficio_neto=120.0,
        patrimonio_neto=1000.0,
    )
    valores.update(sobre)
    return Ejercicio(**valores)


def fundamentos(ejercicios=None, deuda_total=200.0, efectivo=50.0) -> Fundamentos:
    if ejercicios is None:
        ejercicios = [ejercicio(2026 - i) for i in range(4)]
    return Fundamentos(
        moneda="USD",
        fuente="sec",
        ejercicios=tuple(ejercicios),
        deuda_total=deuda_total,
        efectivo=efectivo,
    )


def perfil(**sobre) -> Perfil:
    valores = dict(
        ticker="TST",
        precio=100.0,
        capitalizacion=1000.0,
        moneda="USD",
        moneda_estados="USD",
        industria="Semiconductors",
        pais="United States",
        payout=0.3,
        tipo="EQUITY",
        hora="2026-10-12T19:59:00+00:00",
    )
    valores.update(sobre)
    return Perfil(**valores)
