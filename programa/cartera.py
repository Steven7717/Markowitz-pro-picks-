"""Los portafolios que el usuario decide guardar, y cómo vuelven.

Vive en la raíz y no dentro de una vista por la misma razón que `aprobacion/`:
guardar, listar y volver a cargar son decisiones con reglas —qué se copia,
qué pasa si el fichero está a medias, qué significa un portafolio viejo— y las
reglas se prueban sin arrancar Streamlit.

Un portafolio guardado es una **fotografía**, no un enlace. Copia dentro los
pesos y las métricas de la corrida que lo produjo, igual que el acta del gate
copia las fichas: los precios de mañana ya no son los de hoy, y un portafolio
que se recalculase al abrirlo no sería el que se guardó, sino otro con el
mismo nombre.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

DIRECTORIO = Path("portafolios")

# Vive junto a `actas/` y no dentro de `salidas/` por la misma razón: `salidas/`
# es regenerable y se borra sin pensarlo, y lo que el usuario guardó a mano no
# debería irse por delante con ello.

_FORMA_TICKER = re.compile(r"^[A-Z]+(-[A-Z]+)*$")
_MAX_NOMBRE = 60


class ContratoRoto(ValueError):
    """Hay un fichero, pero no tiene la forma que este modulo espera."""


class NombreInvalido(ValueError):
    """Un portafolio sin nombre no se puede volver a encontrar."""


@dataclass(frozen=True)
class Posicion:
    """Un activo y su peso. Juntos, nunca en dos listas paralelas.

    Dos listas —tickers y pesos— se pueden desincronizar: basta con que alguien
    edite el JSON a mano y borre una línea de una sola de ellas. El resultado
    sería una cartera con los pesos corridos un puesto, que se lee perfectamente
    bien y es otra cartera distinta.
    """

    ticker: str
    peso: float


@dataclass(frozen=True)
class Portafolio:
    """Una optimización guardada: qué se pidió, qué salió y cuándo."""

    nombre: str
    fecha: str
    posiciones: list[Posicion]
    horizonte: str
    # La clave interna de la estrategia (`max_sharpe`), no su etiqueta en
    # castellano. La etiqueta es texto de pantalla y puede reescribirse en
    # cualquier momento; guardarla sería atar un fichero en disco a una
    # decisión de redacción, y recargar el portafolio dejaria de funcionar en
    # cuanto alguien mejorase una frase.
    estrategia: str
    peso_min: float
    peso_max: float
    permitir_cortos: bool
    shrinkage: bool
    metricas: dict = field(default_factory=dict)
    nota: str = ""

    @property
    def tickers(self) -> list[str]:
        return [p.ticker for p in self.posiciones]

    @property
    def pesos(self) -> list[float]:
        return [p.peso for p in self.posiciones]

    @property
    def fecha_legible(self) -> str:
        """La fecha en formato humano, o la cruda si no se puede interpretar."""
        try:
            return datetime.fromisoformat(self.fecha).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return self.fecha


def normalizar_nombre(nombre: str) -> str:
    """Trim and check the name a human typed. Empty is not a name."""
    limpio = " ".join(str(nombre).split())
    if not limpio:
        raise NombreInvalido("El portafolio necesita un nombre para poder encontrarlo")
    if len(limpio) > _MAX_NOMBRE:
        raise NombreInvalido(
            f"El nombre no puede pasar de {_MAX_NOMBRE} caracteres (tiene {len(limpio)})"
        )
    return limpio


def _rebanada(nombre: str) -> str:
    """The name reduced to something a filesystem accepts, for the filename.

    Sólo alimenta el nombre del fichero; el nombre de verdad viaja dentro del
    JSON. Así un portafolio llamado "Mi cartera 2026 (v2)" se guarda en un
    fichero legible y sigue mostrándose con sus paréntesis y sus tildes.
    """
    sin_tildes = (
        nombre.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    trozo = re.sub(r"[^a-z0-9]+", "-", sin_tildes).strip("-")
    return trozo[:40] or "portafolio"


def desde_corrida(
    nombre: str,
    tickers: list[str],
    pesos,
    horizonte: str,
    estrategia: str,
    peso_min: float,
    peso_max: float,
    permitir_cortos: bool,
    shrinkage: bool,
    metricas: dict,
    nota: str = "",
    ahora: datetime | None = None,
) -> Portafolio:
    """Build a Portafolio from what the optimiser page has in hand.

    Los pesos llegan como `numpy.ndarray` desde el optimizador y salen de aquí
    como `float` de Python: `json.dumps` no sabe serializar un `numpy.float64`
    y revienta al guardar, que es el peor momento posible para descubrirlo.
    """
    if len(tickers) != len(list(pesos)):
        raise ContratoRoto(
            f"{len(tickers)} tickers y {len(list(pesos))} pesos: no son la misma cartera"
        )
    return Portafolio(
        nombre=normalizar_nombre(nombre),
        fecha=(ahora or datetime.now()).isoformat(timespec="seconds"),
        posiciones=[
            Posicion(ticker=str(t), peso=float(p)) for t, p in zip(tickers, pesos)
        ],
        horizonte=str(horizonte),
        estrategia=str(estrategia),
        peso_min=float(peso_min),
        peso_max=float(peso_max),
        permitir_cortos=bool(permitir_cortos),
        shrinkage=bool(shrinkage),
        metricas={k: _serializable(v) for k, v in (metricas or {}).items()},
        nota=str(nota or "").strip(),
    )


def _serializable(valor):
    """Turn numpy scalars into plain Python so json.dumps can write them."""
    if valor is None or isinstance(valor, (str, bool)):
        return valor
    try:
        return float(valor) if float(valor) == float(valor) else None
    except (TypeError, ValueError):
        return str(valor)


def guardar(portafolio: Portafolio, directorio: Path | None = None) -> Path:
    """Write one portfolio atomically and return where it landed.

    Un fichero por portafolio y no uno que crece, igual que las actas: una
    escritura interrumpida no puede llevarse por delante los demás.

    El nombre lleva la fecha delante para que la carpeta se ordene sola por
    antigüedad, y un sufijo numérico si dos caen en el mismo segundo. Nunca se
    sobrescribe en silencio: guardar dos veces con el mismo nombre deja dos
    fotografías, que es lo que el usuario pidió las dos veces.
    """
    directorio = Path(directorio or DIRECTORIO)
    directorio.mkdir(parents=True, exist_ok=True)

    momento = datetime.fromisoformat(portafolio.fecha).strftime("%Y-%m-%d-%H%M%S")
    base = f"{momento}-{_rebanada(portafolio.nombre)}"
    fichero = directorio / f"{base}.json"
    copia = 2
    while fichero.exists():
        fichero = directorio / f"{base}-{copia}.json"
        copia += 1

    texto = json.dumps(
        asdict(portafolio), ensure_ascii=False, indent=2, allow_nan=False
    )
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(fichero)
    return fichero


_CAMPOS = frozenset(
    {
        "nombre",
        "fecha",
        "posiciones",
        "horizonte",
        "estrategia",
        "peso_min",
        "peso_max",
        "permitir_cortos",
        "shrinkage",
        "metricas",
        "nota",
    }
)


def cargar(ruta: Path) -> Portafolio:
    """Read one portfolio back, naming whatever is wrong with it.

    Se valida antes de devolverlo porque el destino de estos datos es rellenar
    el optimizador: un `peso_max` que resultase ser una cadena no fallaría aquí,
    fallaría tres pantallas después con un error de scipy que no le dice nada a
    nadie.
    """
    ruta = Path(ruta)
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContratoRoto(f"{ruta.name} no se puede leer: {error}") from error

    if not isinstance(crudo, dict):
        raise ContratoRoto(f"{ruta.name} no contiene un objeto")

    faltan = _CAMPOS - set(crudo)
    if faltan:
        raise ContratoRoto(
            f"a {ruta.name} le faltan campos: {', '.join(sorted(faltan))}"
        )

    posiciones = crudo["posiciones"]
    if not isinstance(posiciones, list) or not posiciones:
        raise ContratoRoto(f"{ruta.name} no tiene ninguna posición")

    limpias = []
    for indice, cruda in enumerate(posiciones):
        if not isinstance(cruda, dict) or {"ticker", "peso"} - set(cruda):
            raise ContratoRoto(
                f"la posición {indice} de {ruta.name} no tiene ticker y peso"
            )
        ticker = str(cruda["ticker"]).strip().upper()
        if not _FORMA_TICKER.match(ticker):
            raise ContratoRoto(f"{ticker!r} en {ruta.name} no tiene forma de ticker")
        try:
            peso = float(cruda["peso"])
        except (TypeError, ValueError) as error:
            raise ContratoRoto(
                f"el peso de {ticker} en {ruta.name} no es un número: "
                f"{cruda['peso']!r}"
            ) from error
        limpias.append(Posicion(ticker=ticker, peso=peso))

    try:
        return Portafolio(
            nombre=normalizar_nombre(crudo["nombre"]),
            fecha=str(crudo["fecha"]),
            posiciones=limpias,
            horizonte=str(crudo["horizonte"]),
            estrategia=str(crudo["estrategia"]),
            peso_min=float(crudo["peso_min"]),
            peso_max=float(crudo["peso_max"]),
            permitir_cortos=bool(crudo["permitir_cortos"]),
            shrinkage=bool(crudo["shrinkage"]),
            metricas=crudo["metricas"] if isinstance(crudo["metricas"], dict) else {},
            nota=str(crudo["nota"]),
        )
    except (NombreInvalido, TypeError, ValueError) as error:
        raise ContratoRoto(f"{ruta.name}: {error}") from error


def formato_cifra(valor, decimales: int = 2) -> str:
    """A saved metric, or a dash when it was never recorded.

    Nunca un 0,00. Un portafolio guardado antes de que existiera la validación
    fuera de muestra no tiene `oos_sharpe`, y un cero ahí se leería como "el
    método no aporta nada" — que es una afirmación, y nadie la hizo. Es la misma
    regla que aplican los medidores de candidatos a un pilar sin datos.
    """
    if valor is None:
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    return "—" if numero != numero else f"{numero:.{decimales}f}"


def formato_porcentaje(valor) -> str:
    """The same, for a figure stored as a fraction."""
    if valor is None:
        return "—"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "—"
    return "—" if numero != numero else f"{numero:.2%}"


@dataclass(frozen=True)
class Entrada:
    """Un fichero de la carpeta: el portafolio si se pudo leer, o por qué no.

    Los ilegibles se devuelven en vez de saltarse. Un portafolio que desaparece
    de la lista sin decir nada es indistinguible de uno que nunca se guardó, y
    el usuario se queda buscando en la carpeta equivocada.
    """

    ruta: Path
    portafolio: Portafolio | None
    error: str | None


def listar(directorio: Path | None = None) -> list[Entrada]:
    """Every saved portfolio, newest first, including the broken ones."""
    directorio = Path(directorio or DIRECTORIO)
    if not directorio.is_dir():
        return []

    entradas = []
    for ruta in sorted(directorio.glob("*.json"), reverse=True):
        try:
            entradas.append(Entrada(ruta=ruta, portafolio=cargar(ruta), error=None))
        except ContratoRoto as error:
            entradas.append(Entrada(ruta=ruta, portafolio=None, error=str(error)))
    return entradas


def borrar(ruta: Path) -> None:
    """Delete one saved portfolio. Missing is already the desired state."""
    Path(ruta).unlink(missing_ok=True)
