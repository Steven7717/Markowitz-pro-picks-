"""Dónde se guarda lo que la IA dice de un ticker del Analizador.

`analisis/<TICKER>.json`, en la raíz del programa, junto a `actas/` y
`libros/`, y fuera de git. N2 guarda ahí sólo las lecturas de los 8-K, con el
formato y las funciones de `interprete/archivo.py` tal cual: append-only, un
archivo ilegible no se trata como vacío ni se pisa, y lo ya leído se pinta sin
pagar.

N3 guarda aquí las otras tres lecturas —`tesis`, `mdna` y `valoracion`— en el
mismo fichero, bajo sus propias claves. `interprete.archivo` conserva las claves
que no son suyas al escribir, y este módulo hace lo mismo con las de aquél.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from interprete.archivo import ArchivoIlegible, _booleano, escribir_crudo, leer_crudo

# Relativa, como `aprobacion.acta.ACTAS` y `seguimiento.libro.DIRECTORIO`: los
# lanzadores arrancan en programa/.
DIRECTORIO = Path("analisis")


def ruta_de(ticker: str) -> Path:
    """`analisis/<TICKER>.json`.

    El ticker llega normalizado (`resolver.normalizar`): letras, dígitos y
    `.-=&^`, que Windows admite en el nombre de un fichero.
    """
    return DIRECTORIO / f"{ticker}.json"


NOMBRES_DE_VOTO = ("flujos", "sin_crecimiento", "pares")


@dataclass(frozen=True)
class Fuente:
    """De qué documento sale una lectura. Es lo que dice si hay uno más nuevo."""

    formulario: str
    fecha: str
    accession: str
    seccion: str
    recortado: bool


@dataclass(frozen=True)
class Tesis:
    cuando: datetime
    modelo: str
    version: str
    fuente: Fuente
    tesis: str
    # (afirmación, cita, verificada)
    riesgos: "tuple[tuple[str, str, bool], ...]"


@dataclass(frozen=True)
class Contraste:
    cuando: datetime
    modelo: str
    version: str
    fuente: Fuente
    supuesto: str
    # (afirmación, postura, cita, verificada)
    juicios: "tuple[tuple[str, str, str, bool], ...]"


@dataclass(frozen=True)
class Explicacion:
    """Una explicación, con los votos que tenía delante.

    Sin ellos el texto queda huérfano: mañana los votos son otros, y pintarlo
    junto a los de hoy sería hacerle decir algo de unos números que no vio.
    """

    cuando: datetime
    modelo: str
    version: str
    votos: "tuple[tuple[str, str | None], ...]"
    veredicto: "str | None"
    movidos: "tuple[str, ...]"
    # (lectura comentada, lo que dice, marcada por recomendar)
    observaciones: "tuple[tuple[str, str, bool], ...]"
    en_conjunto: str


@dataclass(frozen=True)
class Lecturas:
    tesis: "tuple[Tesis, ...]" = ()
    mdna: "tuple[Contraste, ...]" = ()
    valoracion: "tuple[Explicacion, ...]" = ()


def votos_de(valoracion: object) -> "tuple[tuple[str, str | None], ...]":
    """Los tres votos de una valoración, en orden fijo; `None` el que no hay."""
    votos = (valoracion.get("votos") if isinstance(valoracion, dict) else None) or {}
    return tuple((nombre, (votos.get(nombre) or {}).get("voto")) for nombre in NOMBRES_DE_VOTO)


def _texto(valor: object, campo: str) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"'{campo}' no es un texto: {valor!r}")
    return valor


def _fuente(crudo: dict) -> Fuente:
    return Fuente(
        _texto(crudo["formulario"], "formulario"),
        _texto(crudo["fecha"], "fecha"),
        _texto(crudo["accession"], "accession"),
        _texto(crudo["seccion"], "seccion"),
        _booleano(crudo["recortado"], "recortado"),
    )


def _tesis(crudo: dict) -> Tesis:
    return Tesis(
        datetime.fromisoformat(crudo["cuando"]),
        _texto(crudo["modelo"], "modelo"),
        _texto(crudo["version"], "version"),
        _fuente(crudo["fuente"]),
        _texto(crudo["tesis"], "tesis"),
        tuple(
            (_texto(r["afirmacion"], "afirmacion"), _texto(r["cita"], "cita"), _booleano(r["verificada"]))
            for r in crudo["riesgos"]
        ),
    )


def _contraste(crudo: dict) -> Contraste:
    return Contraste(
        datetime.fromisoformat(crudo["cuando"]),
        _texto(crudo["modelo"], "modelo"),
        _texto(crudo["version"], "version"),
        _fuente(crudo["fuente"]),
        _texto(crudo["supuesto"], "supuesto"),
        tuple(
            (
                _texto(j["afirmacion"], "afirmacion"),
                _texto(j["postura"], "postura"),
                _texto(j["cita"], "cita"),
                _booleano(j["verificada"]),
            )
            for j in crudo["juicios"]
        ),
    )


def _texto_o_nada(valor: object, campo: str) -> "str | None":
    return None if valor is None else _texto(valor, campo)


def _votos(valor: object) -> "tuple[tuple[str, str | None], ...]":
    """Exactamente los tres pares `[nombre, voto]`, con los nombres y el orden de siempre."""
    if not isinstance(valor, list) or len(valor) != len(NOMBRES_DE_VOTO):
        raise ValueError(f"'votos' no son los tres pares esperados: {valor!r}")
    votos = []
    for par, esperado in zip(valor, NOMBRES_DE_VOTO):
        if not isinstance(par, list) or len(par) != 2 or par[0] != esperado:
            raise ValueError(f"'votos' no trae el par de '{esperado}' en su sitio: {par!r}")
        votos.append((esperado, _texto_o_nada(par[1], "voto")))
    return tuple(votos)


def _movidos(valor: object) -> "tuple[str, ...]":
    """`tuple("beta")` da `('b', 'e', 't', 'a')` y no se queja: se exige una lista."""
    if not isinstance(valor, list):
        raise ValueError(f"'movidos' no es una lista de textos: {valor!r}")
    return tuple(_texto(m, "movidos") for m in valor)


def _explicacion(crudo: dict) -> Explicacion:
    return Explicacion(
        datetime.fromisoformat(crudo["cuando"]),
        _texto(crudo["modelo"], "modelo"),
        _texto(crudo["version"], "version"),
        _votos(crudo["votos"]),
        _texto_o_nada(crudo["veredicto"], "veredicto"),
        _movidos(crudo["movidos"]),
        tuple(
            (_texto(o["sobre"], "sobre"), _texto(o["dice"], "dice"), _booleano(o["marcada"], "marcada"))
            for o in crudo["observaciones"]
        ),
        _texto(crudo["en_conjunto"], "en_conjunto"),
    )


_LECTORES = {"tesis": _tesis, "mdna": _contraste, "valoracion": _explicacion}


def cargar(ruta: Path) -> Lecturas:
    """Las lecturas guardadas de un ticker. Sin fichero, o sin las claves, ninguna.

    **Levanta `ArchivoIlegible`** si el fichero no se puede leer o una clave
    tiene una forma que no se reconoce: no se trata como vacío.
    """
    crudo = leer_crudo(ruta)
    if crudo is None:
        return Lecturas()
    leidas = {}
    for clave, lector in _LECTORES.items():
        entradas = crudo.get(clave, [])
        if not isinstance(entradas, list):
            raise ArchivoIlegible(f"{Path(ruta).name}: '{clave}' no es una lista.")
        try:
            leidas[clave] = tuple(lector(e) for e in entradas)
        except (KeyError, TypeError, ValueError) as error:
            raise ArchivoIlegible(
                f"{Path(ruta).name}: '{clave}' tiene una forma que no se reconoce: {error}"
            ) from error
    return Lecturas(**leidas)


def _fuente_a_dict(fuente: Fuente) -> dict:
    return {
        "formulario": fuente.formulario,
        "fecha": fuente.fecha,
        "accession": fuente.accession,
        "seccion": fuente.seccion,
        "recortado": fuente.recortado,
    }


def _anotar(ruta: Path, clave: str, entrada: dict) -> None:
    """Añadir una entrada bajo `clave`, sin tocar lo demás.

    Antes valida lo que hay: escribir encima de un fichero que no se entiende
    perdería el historial. Y valida lo que va a escribir con su propio lector:
    una entrada que luego no se pudiera leer dejaría el fichero ilegible para
    siempre. Un fichero nuevo nace con `hechos` y `rebalanceo` vacías, que es
    lo que `interprete.archivo.cargar` exige para leerlo.
    """
    cargar(ruta)
    try:
        _LECTORES[clave](entrada)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"No se guarda: la entrada de '{clave}' no se podría leer después ({error}).") from error
    crudo = leer_crudo(ruta)
    if crudo is None:
        crudo = {"hechos": [], "rebalanceo": []}
    crudo[clave] = list(crudo.get(clave, [])) + [entrada]
    escribir_crudo(ruta, crudo)


def anotar_tesis(ruta: Path, tesis: Tesis) -> None:
    _anotar(ruta, "tesis", {
        "cuando": tesis.cuando.isoformat(),
        "modelo": tesis.modelo,
        "version": tesis.version,
        "fuente": _fuente_a_dict(tesis.fuente),
        "tesis": tesis.tesis,
        "riesgos": [
            {"afirmacion": a, "cita": c, "verificada": v} for a, c, v in tesis.riesgos
        ],
    })


def anotar_contraste(ruta: Path, contraste: Contraste) -> None:
    _anotar(ruta, "mdna", {
        "cuando": contraste.cuando.isoformat(),
        "modelo": contraste.modelo,
        "version": contraste.version,
        "fuente": _fuente_a_dict(contraste.fuente),
        "supuesto": contraste.supuesto,
        "juicios": [
            {"afirmacion": a, "postura": p, "cita": c, "verificada": v}
            for a, p, c, v in contraste.juicios
        ],
    })


def anotar_explicacion(ruta: Path, explicacion: Explicacion) -> None:
    _anotar(ruta, "valoracion", {
        "cuando": explicacion.cuando.isoformat(),
        "modelo": explicacion.modelo,
        "version": explicacion.version,
        "votos": [list(v) for v in explicacion.votos],
        "veredicto": explicacion.veredicto,
        "movidos": list(explicacion.movidos),
        "observaciones": [
            {"sobre": s, "dice": d, "marcada": m} for s, d, m in explicacion.observaciones
        ],
        "en_conjunto": explicacion.en_conjunto,
    })
