import json
from dataclasses import dataclass
from pathlib import Path

SALIDAS = Path("salidas")

# salidas/ lo escribe B y no viaja en el repo: cada usuario genera el suyo, y
# versionarlo convertia a cualquiera que abriese el programa en alguien con
# cambios locales sobre ficheros del repo, que es lo que rompia `git pull`.
# El ejemplo se queda versionado aparte para que quien acaba de clonar vea una
# lista real sin pagar una corrida con IA.
EJEMPLO = Path("salidas_ejemplo")

_CAMPOS_FICHA = frozenset(
    {
        "ticker",
        "sector_gics",
        "puesto",
        "compuesto",
        "pilares",
        "destacados",
        "flojos",
        "cobertura",
        "desplazo_a",
        "generada_por",
        "narrativa",
    }
)

_CAMPOS_CORRIDA = frozenset(
    {
        "fecha",
        "universo",
        "n_panel",
        "n_supervivientes",
        "exclusiones",
        "tope_por_sector",
        "tamano_top",
        "con_llm",
    }
)

_COMO_GENERARLO = (
    "Falta salidas/fichas.json. Generalo con:\n\n"
    '    python -c "from ranking.run import construir_ranking, guardar; '
    "guardar(construir_ranking(con_llm=False), 'salidas')\""
)


class FaltanFichas(FileNotFoundError):
    """No hay nada que revisar todavia."""


class ContratoRoto(ValueError):
    """Hay un fichero, pero no tiene la forma que este modulo espera."""


@dataclass(frozen=True)
class Candidatos:
    """What sub-project B left on disk, validated.

    `corrida` is None when corrida.json is absent, which is not an error: the
    outputs committed to this repo predate that file. A corrida.json that is
    present but malformed is a different thing and raises — absent means "an
    older B wrote this", malformed means something went wrong and hiding it
    would be the silent failure this package exists to avoid.
    """

    fichas: list[dict]
    corrida: dict | None


def _leer_json(fichero: Path) -> object:
    try:
        return json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContratoRoto(f"{fichero.name} no es JSON valido: {error}") from error


def _validar_fichas(crudo: object) -> list[dict]:
    """Check presence of every field, plus the identity invariants presence
    alone can't catch: `ticker` as a non-empty string and no repeated
    `ticker` (it is the identifier the rest of the chain, incluida la futura
    acta, usara para identificar cada candidata — vacio o duplicado, la ficha
    se pinta sin nombre o se confunde con otra, en silencio), and `puesto`
    typed as an int (it drives display order and the "#1" label;
    ranking/fichas.py:ficha_numerica always writes int(puesto), so anything
    else can only mean a hand-edited or corrupted file).

    Deliberately NOT type-checked beyond that: a wrong-typed `compuesto` or
    `pilares` renders as visibly wrong text on the page (a reviewer sees
    "compuesto: muy alto" and notices), while a bad identity field can
    corrupt the *set of candidates itself* without looking wrong at a
    glance. Extra, unexpected fields are accepted on purpose: it is what
    lets B add a field later without forcing a simultaneous change here.
    `ticker` is checked only for non-emptiness, not shape — matching it
    against the pattern of a real ticker is the next task's job, once it
    also has to validate tickers a human typed by hand; here the value comes
    from B, code this package already trusts.
    """
    if not isinstance(crudo, list):
        raise ContratoRoto("fichas.json no contiene una lista")
    tickers_vistos: set = set()
    for posicion, ficha in enumerate(crudo):
        if not isinstance(ficha, dict):
            raise ContratoRoto(f"la ficha en la posicion {posicion} no es un objeto")
        faltan = _CAMPOS_FICHA - set(ficha)
        if faltan:
            raise ContratoRoto(
                f"a la ficha en la posicion {posicion} le faltan campos: "
                f"{', '.join(sorted(faltan))}"
            )
        ticker = ficha["ticker"]
        if not isinstance(ticker, str) or not ticker:
            raise ContratoRoto(
                f"la ficha en la posicion {posicion} tiene un ticker invalido: "
                f"{ticker!r}"
            )
        puesto = ficha["puesto"]
        # bool es subclase de int en Python (isinstance(True, int) es True);
        # True/False no son puestos validos aunque pasen ese isinstance.
        if isinstance(puesto, bool) or not isinstance(puesto, int):
            raise ContratoRoto(
                f"la ficha de {ticker!r} en la posicion {posicion} "
                f"tiene un puesto invalido: {puesto!r}"
            )
        if ticker in tickers_vistos:
            raise ContratoRoto(
                f"el ticker {ticker!r} aparece mas de una vez en fichas.json"
            )
        tickers_vistos.add(ticker)
    return crudo


def _validar_corrida(crudo: object) -> dict:
    """Presence of every field, plus one consistency check: sobrevivientes no
    puede superar al panel del que salieron. Sin esta comprobacion, un
    corrida.json con esos numeros invertidos pasaria en silencio y
    resumen_corrida calcularia un numero de excluidas negativo, mostrandole
    al revisor una frase que no tiene sentido en el peor momento posible
    para no notarlo.
    """
    if not isinstance(crudo, dict):
        raise ContratoRoto("corrida.json no contiene un objeto")
    faltan = _CAMPOS_CORRIDA - set(crudo)
    if faltan:
        raise ContratoRoto(
            f"a corrida.json le faltan campos: {', '.join(sorted(faltan))}"
        )
    if crudo["n_supervivientes"] > crudo["n_panel"]:
        raise ContratoRoto(
            "corrida.json es inconsistente: n_supervivientes "
            f"({crudo['n_supervivientes']}) es mayor que n_panel "
            f"({crudo['n_panel']})"
        )
    return crudo


def cargar_candidatos(directorio: Path | None = None) -> Candidatos:
    """Read and validate what sub-project B wrote.

    Every failure names the field or the file that is wrong. A half-rendered
    ficha is worse than no page at all: the reviewer would be approving on
    incomplete information without knowing it.
    """
    # Solo el camino por defecto cae al ejemplo. Quien pasa un directorio a
    # mano -- los tests, un script -- esta diciendo exactamente donde mirar, y
    # sustituirselo por otra cosa convertiria un fallo en un falso verde.
    if directorio is None:
        directorio = SALIDAS if (SALIDAS / "fichas.json").exists() else EJEMPLO
    else:
        directorio = Path(directorio)
    fichero_fichas = directorio / "fichas.json"
    if not fichero_fichas.exists():
        raise FaltanFichas(_COMO_GENERARLO)

    fichas = _validar_fichas(_leer_json(fichero_fichas))

    fichero_corrida = directorio / "corrida.json"
    corrida = (
        _validar_corrida(_leer_json(fichero_corrida))
        if fichero_corrida.exists()
        else None
    )
    return Candidatos(fichas=fichas, corrida=corrida)


def resumen_corrida(corrida: dict | None) -> str:
    """One sentence putting the shortlist in the context of what was dropped.

    This is the whole reason B writes corrida.json. The sector tilt the guards
    produce is documented in a design file nobody reads while deciding; putting
    it in front of the reviewer at the moment of decision is what turns a
    documented bias into one that was actually taken into account.
    """
    if corrida is None:
        return (
            "Sin contexto de corrida: este ranking se genero antes de que se "
            "registraran sus metadatos, asi que no se sabe a cuantas empresas "
            "dejaron fuera las guardas."
        )

    excluidas = corrida["n_panel"] - corrida["n_supervivientes"]
    if corrida["exclusiones"]:
        por_motivo = ", ".join(
            f"{motivo} ({cuantas})"
            for motivo, cuantas in sorted(
                corrida["exclusiones"].items(), key=lambda par: -par[1]
            )
        )
    else:
        # Mismo caso que ranking/informe.py:render con su seccion de
        # exclusiones vacia: nunca ha pasado y probablemente no pase, pero
        # una frase que termina en "excluidas 0: ." se leeria como que algo
        # se rompio, justo lo contrario de lo que ocurrio.
        por_motivo = "ninguna, todas las empresas del universo pasaron las guardas"
    return (
        f"Estos candidatos salen de {corrida['n_panel']} empresas con datos, de "
        f"las que sobrevivieron {corrida['n_supervivientes']} a las guardas. "
        f"Quedaron excluidas {excluidas}: {por_motivo}."
    )
