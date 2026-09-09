# seguimiento/alta.py
"""Repartir un capital entre los pesos de un plan, y decirlo entero.

Esto **no escribe nada en el libro**. Produce una propuesta: cuanto comprar de
cada activo con el dinero que hay. Es lo mismo que hace `rebalanceo.propuesta`
con la aportacion, y por la misma razon -- entre mirar la propuesta y ejecutarla
en el broker, el precio se mueve, asi que lo que acabe en el libro tiene que
salir de lo que el usuario confirme, no de esta division.
"""

import math
import uuid
from dataclasses import dataclass

from seguimiento.libro import Asiento


@dataclass(frozen=True)
class Linea:
    """Un activo del plan, con lo que le tocaria y lo que de verdad cabe."""

    ticker: str
    peso: float
    objetivo: float          # capital * peso
    precio: "float | None"
    acciones: float
    importe: float           # acciones * precio
    motivo: str              # "" cuando no hay nada que explicar


@dataclass(frozen=True)
class Reparto:
    lineas: "tuple[Linea, ...]"
    gastado: float
    sobrante: float
    sin_precio: "tuple[str, ...]"


def repartir(
    capital: float,
    pesos: "dict[str, float]",
    precios: "dict[str, float | None]",
    fracciones: bool,
) -> Reparto:
    """What to buy of each asset with this much money.

    **El sobrante no se redistribuye.** Con acciones enteras casi siempre sobra
    algo, y repartirlo entre los demas romperia los pesos que el usuario acaba
    de elegir: nadie decidio darle mas a nadie. Queda como efectivo sin
    asignar, que es exactamente lo que es, y Rebalanceo ya sabe proponer donde
    ponerlo.

    **Un activo que no cabe sale igual, con cero y su motivo.** Con 1.000 de
    capital, un peso del 2% y una accion de 600, salen cero acciones. Omitir la
    linea dejaria un plan de tres activos mostrando dos, sin que nada lo diga.

    **Un activo sin precio no se reparte a ciegas.** Vuelve nombrado y con cero
    acciones, y su parte del capital queda como sobrante -- igual que en
    `rebalanceo.deriva`, no se valora a cero ni se reparte entre los demas.
    """
    if capital <= 0 or not pesos:
        return Reparto((), 0.0, 0.0, ())

    total = sum(pesos.values())
    if total <= 0:
        return Reparto((), 0.0, 0.0, ())

    lineas, sin_precio, gastado = [], [], 0.0
    for ticker, peso in sorted(pesos.items(), key=lambda kv: -kv[1]):
        parte = peso / total
        objetivo = capital * parte
        precio = precios.get(ticker)

        if precio is None or precio <= 0:
            sin_precio.append(ticker)
            lineas.append(Linea(
                ticker, parte, objetivo, None, 0.0, 0.0,
                "sin precio: no se le asignan acciones a ciegas",
            ))
            continue

        crudas = objetivo / precio
        acciones = crudas if fracciones else float(math.floor(crudas))
        importe = acciones * precio
        motivo = ""
        if acciones == 0:
            motivo = (
                f"con {objetivo:,.2f} no alcanza para una accion de "
                f"{precio:,.2f}"
            )
        lineas.append(
            Linea(ticker, parte, objetivo, precio, acciones, importe, motivo)
        )
        gastado += importe

    return Reparto(
        lineas=tuple(lineas),
        gastado=gastado,
        sobrante=capital - gastado,
        sin_precio=tuple(sin_precio),
    )


class AltaInvalida(ValueError):
    """Lo que el usuario confirmo no se puede escribir como esta."""


def asientos_de(
    filas: "list[dict]", capital: "float | None", fecha: str
) -> "tuple[Asiento, ...]":
    """The confirmed table, turned into the entries that open the book.

    `capital` es el que el usuario declaro cuando viene del optimizador, y
    **None en la carga manual**, donde no hay capital declarado y se deriva de
    lo comprado. Son casos distintos y mezclarlos deja efectivo fantasma: si en
    la carga manual se supusiera un capital redondo, la diferencia quedaria
    como dinero parado que nadie tiene, y falsearia la TIR desde el primer dia.

    La aportacion va **primero**. Si las compras se aplicasen antes, el efectivo
    pasaria por negativo y `posiciones.primer_descubierto` lo rechazaria.
    """
    compras = []
    for fila in filas:
        ticker = str(fila.get("ticker") or "").strip().upper()
        acciones = float(fila.get("acciones") or 0)
        precio = float(fila.get("precio") or 0)
        # Una fila sin ticker o sin acciones es una linea que el usuario dejo
        # en blanco, o el activo que no cabia. No se escribe media compra.
        if not ticker or acciones <= 0:
            continue
        if precio <= 0:
            raise AltaInvalida(
                f"{ticker}: el precio tiene que ser mayor que cero"
            )
        compras.append((ticker, acciones, precio,
                        float(fila.get("comision") or 0)))

    if not compras:
        raise AltaInvalida(
            "No hay ninguna compra que registrar. Un libro sin asientos no "
            "tiene nada que seguir."
        )

    coste = sum(a * p + c for _, a, p, c in compras)
    if capital is None:
        capital = coste
    elif coste > capital:
        raise AltaInvalida(
            f"Las compras suman {coste:,.2f}, mas que los {capital:,.2f} "
            f"aportados. Faltan {coste - capital:,.2f}."
        )

    asientos = [Asiento(
        id=uuid.uuid4().hex[:12], fecha=fecha, tipo="aportacion",
        importe=capital,
    )]
    asientos += [
        Asiento(
            id=uuid.uuid4().hex[:12], fecha=fecha, tipo="compra",
            ticker=ticker, acciones=acciones, precio=precio,
            importe=acciones * precio, comision=comision,
        )
        for ticker, acciones, precio, comision in compras
    ]
    return tuple(asientos)
