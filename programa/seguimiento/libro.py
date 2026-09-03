"""El libro de asientos: lo que el usuario compró de verdad, y por cuánto.

Un libro no es un `cartera.Portafolio`. Aquel es una fotografía de una
optimización —pesos y métricas congelados, sin dinero dentro— y este es el
registro vivo de lo que pasó después. La pantalla de seguimiento mide la
distancia entre los dos, así que fundirlos borraría justo lo que hay que medir.

Se guardan **sólo asientos**. Posiciones, pesos, valor y rendimiento se derivan
en cada apertura desde `seguimiento.posiciones`. Guardar también el estado
crearía dos representaciones de la misma verdad que se pueden desincronizar, y
una corrección aplicada a una sola de ellas produce un libro que se lee
perfectamente bien y miente.
"""

import re
from dataclasses import dataclass, field
from datetime import date

TIPOS = frozenset(
    {"aportacion", "retiro", "compra", "venta", "dividendo", "anulacion"}
)

# Los tipos que mueven un activo concreto, y por tanto necesitan ticker.
CON_TICKER = frozenset({"compra", "venta", "dividendo"})

# Los dos únicos que son dinero entrando o saliendo del bolsillo del usuario.
# Todo lo demás mueve dinero *dentro* de la cartera, y por eso cuenta en el
# rendimiento en vez de quedar fuera de él. Un dividendo tomado por flujo
# externo inflaría el capital aportado con lo que la cartera acaba de ganar.
FLUJOS_EXTERNOS = frozenset({"aportacion", "retiro"})

_FORMA_TICKER = re.compile(r"^[A-Z]+(-[A-Z]+)*$")


class AsientoInvalido(ValueError):
    """Lo que se intenta registrar no pudo haber pasado."""


@dataclass(frozen=True)
class Asiento:
    """Una línea del libro. Nunca se edita y nunca se borra."""

    id: str
    fecha: str
    tipo: str
    ticker: str | None = None
    acciones: float | None = None
    precio: float | None = None
    importe: float = 0.0
    comision: float = 0.0
    # True cuando el precio salió del cierre del día y no de lo que el usuario
    # pagó. Viaja con el asiento y se pinta en el historial: una compra
    # intradía en un día volátil se desvía un 3-4% del cierre, y eso tiene que
    # ser visible, no una nota al pie del diseño.
    precio_estimado: bool = False
    anula: str | None = None
    nota: str = ""


@dataclass(frozen=True)
class Objetivo:
    """Los pesos contra los que se mide la deriva, con su fecha y su evidencia."""

    fecha: str
    base: str
    portafolio: dict
    veredicto: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Libro:
    """Un libro entero: el nombre, los objetivos apilados y los asientos."""

    nombre: str
    creado: str
    moneda: str = "USD"
    objetivos: list[Objetivo] = field(default_factory=list)
    asientos: list[Asiento] = field(default_factory=list)

    @property
    def objetivo(self) -> Objetivo | None:
        """El objetivo vigente: el último que se apiló, o ninguno."""
        return self.objetivos[-1] if self.objetivos else None


def validar(asiento: Asiento, hoy: date | None = None) -> None:
    """Check one entry's shape. Raises AsientoInvalido naming what is wrong.

    Sólo comprueba lo que se puede saber mirando el asiento solo. Lo que
    depende del estado —vender más acciones de las que hay, retirar más
    efectivo del que hay— vive en `anadir()`, porque necesita reconstruir el
    libro entero para responderlo.
    """
    hoy = hoy or date.today()

    if asiento.tipo not in TIPOS:
        raise AsientoInvalido(
            f"{asiento.tipo!r} no es un tipo de asiento: "
            f"{', '.join(sorted(TIPOS))}"
        )

    try:
        cuando = date.fromisoformat(asiento.fecha)
    except ValueError as error:
        raise AsientoInvalido(f"{asiento.fecha!r} no es una fecha") from error
    if cuando > hoy:
        raise AsientoInvalido(
            f"{asiento.fecha} es una fecha futura: no se puede registrar algo "
            "que todavía no ha pasado"
        )

    if asiento.comision < 0:
        raise AsientoInvalido("la comisión no puede ser negativa")

    if asiento.tipo == "anulacion":
        if not asiento.anula:
            raise AsientoInvalido("una anulación tiene que decir a qué asiento anula")
        return

    if asiento.tipo in CON_TICKER:
        if not asiento.ticker:
            raise AsientoInvalido(f"un asiento de {asiento.tipo} necesita ticker")
        if not _FORMA_TICKER.match(asiento.ticker):
            raise AsientoInvalido(f"{asiento.ticker!r} no tiene forma de ticker")
    elif asiento.ticker:
        raise AsientoInvalido(
            f"un asiento de {asiento.tipo} no lleva ticker: es dinero entrando o "
            "saliendo, no dinero puesto en algo"
        )

    if asiento.importe <= 0:
        raise AsientoInvalido("el importe tiene que ser mayor que cero")

    if asiento.tipo in {"compra", "venta"}:
        if not asiento.acciones or asiento.acciones <= 0:
            raise AsientoInvalido("las acciones tienen que ser más que cero")
        if not asiento.precio or asiento.precio <= 0:
            raise AsientoInvalido("el precio tiene que ser mayor que cero")


def derivar(
    importe: float | None, acciones: float | None, precio: float | None
) -> tuple[float, float, float]:
    """Complete the third figure from the other two, and return all three.

    Se guardan los tres aunque uno se haya derivado, para que el fichero se lea
    sin recalcular nada y para que un cambio futuro en esta fórmula no mueva los
    datos de ayer.

    Cuando llegan los tres, mandan los tres aunque no cuadren al céntimo: el
    bróker aplica redondeos que ninguna división reproduce, y corregir en
    silencio lo que el usuario copió de su extracto sería inventar.
    """
    if precio is None or precio <= 0:
        raise AsientoInvalido("hace falta el precio para completar la operación")
    if importe is not None and acciones is not None:
        return (float(importe), float(acciones), float(precio))
    if importe is not None:
        return (float(importe), float(importe) / float(precio), float(precio))
    if acciones is not None:
        return (float(acciones) * float(precio), float(acciones), float(precio))
    raise AsientoInvalido("hace falta el importe o el número de acciones")
