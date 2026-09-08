# noticias/agenda.py
"""Lo que viene: resultados, ex-dividendo y pago.

El orden es ascendente, al reves que el de las noticias. No es un capricho: en
"lo que paso" lo mas nuevo es lo mas relevante, y en "lo que viene" lo mas
cercano es lo mas urgente.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Evento:
    ticker: "str | None"       # None para lo macro
    clase: str                 # resultados | ex-dividendo | dividendo | macro
    cuando: "date | None"      # None para lo macro: no tenemos la fecha
    detalle: str
    url: "str | None" = None


def _primera_fecha(valor) -> "date | None":
    """`Earnings Date` llega como LISTA aunque traiga una sola fecha."""
    if isinstance(valor, (list, tuple)):
        return valor[0] if valor else None
    return valor if isinstance(valor, date) else None


def desde_calendario(
    ticker: str, calendario: "dict | None", hoy: date
) -> "tuple[Evento, ...]":
    """The asset's upcoming dates, with past ones dropped.

    Una fecha ausente **no inventa evento**. Poner `date.today()` por defecto
    seria afirmar algo que nadie afirmo, que es la misma regla que
    `cartera.formato_cifra` aplica al «--» frente al 0,00.
    """
    if not calendario:
        return ()

    salida = []

    resultados = _primera_fecha(calendario.get("Earnings Date"))
    if resultados:
        estimado = calendario.get("Earnings Average")
        detalle = "Resultados"
        if estimado is not None:
            detalle = f"Resultados — EPS estimado {float(estimado):.2f}"
        salida.append(Evento(ticker, "resultados", resultados, detalle))

    ex = _primera_fecha(calendario.get("Ex-Dividend Date"))
    if ex:
        salida.append(
            Evento(ticker, "ex-dividendo", ex,
                   "Último día para tener las acciones y cobrar")
        )

    pago = _primera_fecha(calendario.get("Dividend Date"))
    if pago:
        salida.append(Evento(ticker, "dividendo", pago, "Fecha de pago"))

    futuros = [e for e in salida if e.cuando and e.cuando >= hoy]
    futuros.sort(key=lambda e: e.cuando)
    return tuple(futuros)
