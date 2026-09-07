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

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import cartera

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

# Sin anclas, porque se usa con `fullmatch` y no con `match`. Con `match`, un
# `$` casa también justo antes de un salto de línea final, así que "AAPL\n"
# pasaría por ticker válido — y como el ticker es la clave del diccionario de
# posiciones, eso partiría una posición en dos, "AAPL" y "AAPL\n". El usuario
# que cree tener veinte acciones vería diez, sin nada en pantalla que lo
# explicara. `cartera.py` y `aprobacion/acta.py` llevan la variante con `match`
# y el mismo agujero; aquí no se hereda.
_FORMA_TICKER = re.compile(r"[A-Z]+(-[A-Z]+)*")

_CAMPOS_NUMERICOS = (
    ("importe", "el importe"),
    ("acciones", "las acciones"),
    ("precio", "el precio"),
    ("comision", "la comisión"),
)


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
    """Un libro entero: el nombre, los objetivos apilados y los asientos.

    Las dos colecciones son tuplas y no listas. `frozen=True` impide reasignar
    el campo, pero no tocar una lista por dentro: con listas,
    `libro.asientos.append(...)` funcionaría y la regla central de este módulo
    —nunca se edita, nunca se borra— quedaría documentada pero no impuesta.
    """

    nombre: str
    creado: str
    moneda: str = "USD"
    objetivos: tuple[Objetivo, ...] = ()
    asientos: tuple[Asiento, ...] = ()

    @property
    def objetivo(self) -> Objetivo | None:
        """El objetivo vigente: el último que se apiló, o ninguno."""
        return self.objetivos[-1] if self.objetivos else None


def _finito(valor, campo: str) -> None:
    """Reject NaN, infinity, and anything that is not a number at all.

    **Ninguna de las guardas de más abajo lo caza.** Toda comparación con NaN
    es falsa —`nan <= 0` es `False`— y `not float("nan")` también es `False`,
    porque NaN es *truthy*. Así que un asiento con NaN las atraviesa enteras, y
    entonces hace dos cosas a la vez: envenena el efectivo, y **borra el activo
    de la tabla de posiciones**, porque el filtro de polvo `abs(n) > _POLVO` de
    `seguimiento.posiciones` también es `False` para NaN. El usuario no ve un
    error: ve una posición que desapareció y un efectivo que dice "nan".

    No es un caso de laboratorio. `json.loads` acepta los literales `NaN` e
    `Infinity` por defecto, así que un fichero editado a mano o corrompido los
    mete en el libro sin que nadie los teclee.
    """
    if valor is None:
        return
    try:
        finito = math.isfinite(valor)
    except TypeError as error:
        raise AsientoInvalido(f"{campo} no es un número: {valor!r}") from error
    if not finito:
        raise AsientoInvalido(f"{campo} tiene que ser un número finito, y es {valor!r}")


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

    for campo, nombre in _CAMPOS_NUMERICOS:
        _finito(getattr(asiento, campo), nombre)

    try:
        cuando = date.fromisoformat(asiento.fecha)
    except (TypeError, ValueError) as error:
        # TypeError además de ValueError: pasar un `date` es el error más
        # probable del llamante, porque el resto del módulo habla en `date`, y
        # el docstring de arriba promete AsientoInvalido. Sin capturarlo, la
        # pantalla —que sólo atrapa AsientoInvalido— enseñaría un traceback.
        raise AsientoInvalido(f"{asiento.fecha!r} no es una fecha") from error
    if cuando.isoformat() != asiento.fecha:
        # `date.fromisoformat` acepta ISO 8601 entero desde Python 3.11, así
        # que "20260901" y "2026-W36-2" son fechas válidas para él. Pero la
        # reconstrucción ordena por la cadena cruda, y '-' es menor que
        # cualquier dígito: "20260215" acaba DETRÁS de "2026-08-01" al ordenar,
        # y una venta se aplicaría antes que su propia compra.
        raise AsientoInvalido(
            f"{asiento.fecha!r} no está escrita como YYYY-MM-DD"
        )
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
        # Una anulación es una nota que tacha otra línea, no un movimiento.
        # Dejarla llevar ticker o dinero guardaría basura con pinta de dato en
        # un fichero que nadie vuelve a validar al leerlo.
        for campo in ("ticker", "acciones", "precio"):
            if getattr(asiento, campo) is not None:
                raise AsientoInvalido(f"una anulación no lleva {campo}")
        if asiento.importe or asiento.comision:
            raise AsientoInvalido("una anulación no mueve dinero")
        return

    if asiento.tipo in CON_TICKER:
        if not asiento.ticker:
            raise AsientoInvalido(f"un asiento de {asiento.tipo} necesita ticker")
        if not _FORMA_TICKER.fullmatch(asiento.ticker):
            raise AsientoInvalido(f"{asiento.ticker!r} no tiene forma de ticker")
    elif asiento.ticker:
        raise AsientoInvalido(
            f"un asiento de {asiento.tipo} no lleva ticker: es dinero entrando o "
            "saliendo, no dinero puesto en algo"
        )

    if asiento.importe <= 0:
        raise AsientoInvalido("el importe tiene que ser mayor que cero")

    if asiento.tipo in {"compra", "venta"}:
        if asiento.acciones is None or asiento.acciones <= 0:
            raise AsientoInvalido("las acciones tienen que ser más que cero")
        if asiento.precio is None or asiento.precio <= 0:
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

    **No puede apoyarse en `validar`, porque corre antes que él.** La pantalla
    llama aquí con lo que el usuario acaba de teclear, construye el `Asiento`
    con el resultado, y sólo entonces llama a `anadir()`, que es quien valida.
    Así que lo que no se compruebe aquí llega contaminado — y algunos venenos
    pasan luego las guardas de "mayor que cero" sin despeinarse, porque un
    `inf` nacido de dividir por un precio diminuto es mayor que cero.
    """
    _finito(importe, "el importe")
    _finito(acciones, "las acciones")
    _finito(precio, "el precio")

    if precio is None:
        raise AsientoInvalido("hace falta el precio para completar la operación")
    if precio <= 0:
        raise AsientoInvalido("el precio tiene que ser mayor que cero")

    if importe is not None and acciones is not None:
        completo = (float(importe), float(acciones), float(precio))
    elif importe is not None:
        completo = (float(importe), float(importe) / float(precio), float(precio))
    elif acciones is not None:
        completo = (float(acciones) * float(precio), float(acciones), float(precio))
    else:
        raise AsientoInvalido("hace falta el importe o el número de acciones")

    for valor, (_, nombre) in zip(completo, _CAMPOS_NUMERICOS):
        if not math.isfinite(valor):
            raise AsientoInvalido(
                f"la operación no cuadra: {nombre} sale {valor}. Revisa el "
                "precio, que es por lo que se divide."
            )
    return completo


def anadir(
    libro: Libro,
    asiento: Asiento,
    hoy: date | None = None,
    financiar: bool = False,
) -> tuple[Libro, list[Asiento]]:
    """Validate against the ledger's state and return the new book.

    Devuelve también **qué se escribió de verdad**, que puede ser más de un
    asiento: una compra que no cabe en el efectivo disponible arrastra la
    aportación que la financia. El usuario piensa "compré dos mil de Apple", no
    "aporté dos mil y luego compré"; escribir la aportación por él sin decirlo
    sería magia, y por eso la lista vuelve para que la pantalla la enseñe antes
    de guardar.

    La aportación cubre la comisión además del importe. Sin eso, el efectivo
    quedaría negativo por el importe exacto de la comisión en cuanto se
    registrase la primera compra — un descuadre pequeño, permanente y sin causa
    visible.
    """
    # Importación local: `posiciones` no importa este módulo en tiempo de
    # ejecución justamente para que no haya ciclo, y hacerlo arriba lo crearía.
    from seguimiento import posiciones

    validar(asiento, hoy=hoy)

    if asiento.tipo == "anulacion":
        por_id = {a.id: a for a in libro.asientos}
        if asiento.anula not in por_id:
            raise AsientoInvalido(
                f"el asiento {asiento.anula} no existe: no hay nada que anular"
            )
        ya = {a.anula for a in libro.asientos if a.tipo == "anulacion"}
        if asiento.anula in ya:
            raise AsientoInvalido(
                f"el asiento {asiento.anula} ya está anulado: anularlo dos veces "
                "no significa nada"
            )
        return (_con_asientos(libro, [asiento]), [asiento])

    escritos = [asiento]

    if asiento.tipo == "compra" and financiar:
        # El efectivo que había **en la fecha del asiento**, no el de hoy. Un
        # asiento puede llegar fechado en el pasado —es el caso normal cuando
        # alguien empieza a registrar lo que ya tenía comprado— y financiarlo
        # con el saldo de hoy escribiría una aportación del tamaño equivocado.
        disponible = posiciones.estado(libro.asientos, hasta=asiento.fecha).efectivo
        coste = asiento.importe + asiento.comision
        if coste > disponible:
            escritos = [
                Asiento(
                    id=f"{asiento.id}-ap",
                    fecha=asiento.fecha,
                    tipo="aportacion",
                    importe=coste - disponible,
                    nota="Financia la compra de " + str(asiento.ticker),
                ),
                asiento,
            ]

    candidato = _con_asientos(libro, escritos)

    # **El recorrido entero, no el saldo final.** Comprobar contra el estado de
    # hoy acepta una venta fechada en julio de acciones compradas en agosto: el
    # saldo final cuadra, y la cartera queda con acciones negativas a mitad del
    # camino — justo lo que `posiciones.ordenados` existe para evitar. Medido
    # antes de escribir esto: `estado(hasta="2026-07-01")` devolvía
    # `{'AAPL': -10.0}` sin que nada lo hubiera impedido.
    motivo = posiciones.primer_descubierto(candidato.asientos)
    if motivo is not None:
        raise AsientoInvalido(motivo)

    return (candidato, escritos)


def _con_asientos(libro: Libro, nuevos: list[Asiento]) -> Libro:
    """A copy of the book with the entries appended. Never mutates in place."""
    from dataclasses import replace

    return replace(libro, asientos=tuple(libro.asientos) + tuple(nuevos))


# Los cinco campos que hacen falta para poder decir "gana", "pierde" o "no se
# distingue del ruido". Sin `oos_sharpe_stderr` los otros cuatro no bastan: dos
# Sharpe sueltos no dicen si la diferencia cabe dentro del error de medicion.
CAMPOS_VEREDICTO = (
    "oos_sharpe",
    "oos_equal_weight_sharpe",
    "oos_sharpe_stderr",
    "beats_equal_weight",
    "oos_windows",
)


def veredicto_de(metricas: dict) -> dict:
    """The out-of-sample verdict as stored, with what is missing left as None.

    Los portafolios guardados antes de que el optimizador escribiera
    `oos_sharpe_stderr` no lo llevan, y ahí `None` no es `False`: uno significa
    "no se midió" y el otro "se midió y no gana". Rellenar el hueco con `False`
    afirmaría un resultado que nadie obtuvo — la misma regla por la que
    `cartera.formato_cifra` escribe "—" y nunca un 0,00.
    """
    return {campo: metricas.get(campo) for campo in CAMPOS_VEREDICTO}


DIRECTORIO = Path("libros")

BASES = frozenset({"estrategia", "equal_weight"})


class LibroIlegible(ValueError):
    """Hay un fichero de libro, pero no se puede leer."""


@dataclass(frozen=True)
class Entrada:
    """Un fichero de la carpeta: el libro si se pudo leer, o por qué no.

    Los ilegibles se devuelven en vez de saltarse, igual que hace
    `cartera.listar`. Un libro que desaparece de la lista sin decir nada es
    indistinguible de uno que nunca existió, y el usuario se queda buscándolo.
    """

    ruta: Path
    libro: Libro | None
    error: str | None


def desde_portafolio(
    nombre: str,
    portafolio,
    base: str,
    acta: str | None = None,
    ahora: datetime | None = None,
) -> Libro:
    """Start a book whose target is a saved portfolio snapshot.

    El portafolio se copia **dentro**, no se referencia por ruta:
    `vistas/portafolios.py` tiene un botón de borrar, y un libro que apuntase a
    un fichero borrado se quedaría sin objetivo contra el que medir.

    `base` no tiene valor por defecto a propósito. El walk-forward ya dice
    cuándo la optimización no le gana a repartir por igual, y elegir por el
    usuario convertiría esa evidencia en un clic que nadie mira. Es el mismo
    razonamiento que dejó las casillas desmarcadas en el gate de aprobación.
    """
    if base not in BASES:
        raise AsientoInvalido(
            f"{base!r} no es una base válida: {', '.join(sorted(BASES))}"
        )
    momento = (ahora or datetime.now()).isoformat(timespec="seconds")
    copia = asdict(portafolio)
    if acta:
        copia["acta"] = acta
    return Libro(
        nombre=cartera.normalizar_nombre(nombre),
        creado=momento,
        objetivos=(
            Objetivo(
                fecha=momento[:10],
                base=base,
                portafolio=copia,
                veredicto=veredicto_de(copia.get("metricas") or {}),
            ),
        ),
    )


def pesos_objetivo(objetivo: Objetivo | None) -> dict[str, float]:
    """The weights the drift is measured against, honouring `base`."""
    if objetivo is None:
        return {}
    posiciones_ = objetivo.portafolio.get("posiciones") or []
    tickers = [p["ticker"] for p in posiciones_]
    if objetivo.base == "equal_weight":
        return {t: 1.0 / len(tickers) for t in tickers} if tickers else {}
    return {p["ticker"]: float(p["peso"]) for p in posiciones_}


def guardar(libro: Libro, directorio: Path | None = None) -> Path:
    """Write the book atomically and return where it landed.

    Mismo esquema que `cartera.guardar` y `aprobacion.acta.guardar_acta`: fecha
    delante para que la carpeta se ordene sola, sufijo numérico en colisión, y
    tmp-then-`replace()` para que un proceso muerto a media escritura no deje el
    libro a medias.
    """
    directorio = Path(directorio or DIRECTORIO)
    directorio.mkdir(parents=True, exist_ok=True)

    momento = datetime.fromisoformat(libro.creado).strftime("%Y-%m-%d-%H%M%S")
    base = f"{momento}-{cartera.rebanada(libro.nombre)}"
    fichero = directorio / f"{base}.json"
    copia = 2
    while fichero.exists():
        fichero = directorio / f"{base}-{copia}.json"
        copia += 1

    texto = json.dumps(asdict(libro), ensure_ascii=False, indent=2, allow_nan=False)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(fichero)
    return fichero


def cargar(ruta: Path) -> Libro:
    """Read a book back, naming whatever is wrong with it.

    **No borra el fichero roto**, a diferencia de las cachés de `ranking/` y
    `fundamentals/`, que sí lo hacen. Una caché se regenera; el historial de lo
    que alguien compró, no.

    **Cada asiento se vuelve a validar al leerlo**, y no sólo al escribirlo.
    `json.loads` acepta los literales `NaN` e `Infinity` por defecto, así que un
    fichero editado a mano o corrompido puede meter un importe que ninguna
    guarda de "mayor que cero" detiene — y un solo `NaN` envenena el efectivo y
    borra un activo de la tabla sin decir nada. Un libro así **está corrupto**, y
    aquí se trata como tal: se nombra el asiento culpable y no se abre.
    """
    ruta = Path(ruta)
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LibroIlegible(f"{ruta.name} no se puede leer: {error}") from error
    if not isinstance(crudo, dict):
        raise LibroIlegible(f"{ruta.name} no contiene un objeto")
    for campo in ("nombre", "creado", "asientos"):
        if campo not in crudo:
            raise LibroIlegible(f"a {ruta.name} le falta el campo {campo}")
    try:
        asientos = tuple(Asiento(**a) for a in crudo["asientos"])
        libro = Libro(
            nombre=cartera.normalizar_nombre(crudo["nombre"]),
            creado=str(crudo["creado"]),
            moneda=str(crudo.get("moneda", "USD")),
            objetivos=tuple(Objetivo(**o) for o in crudo.get("objetivos", [])),
            asientos=asientos,
        )
    except (TypeError, ValueError) as error:
        raise LibroIlegible(f"{ruta.name}: {error}") from error

    for asiento in asientos:
        try:
            validar(asiento)
        except AsientoInvalido as error:
            raise LibroIlegible(
                f"{ruta.name}: el asiento {asiento.id} no es válido ({error})"
            ) from error
    return libro


def listar(directorio: Path | None = None) -> list[Entrada]:
    """Every saved book, newest first, including the broken ones."""
    directorio = Path(directorio or DIRECTORIO)
    if not directorio.is_dir():
        return []
    entradas = []
    for ruta in sorted(directorio.glob("*.json"), reverse=True):
        try:
            entradas.append(Entrada(ruta=ruta, libro=cargar(ruta), error=None))
        except LibroIlegible as error:
            entradas.append(Entrada(ruta=ruta, libro=None, error=str(error)))
    return entradas
