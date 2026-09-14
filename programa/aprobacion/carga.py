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

# Los codigos con los que `ranking/score.py` marca a las excluidas, en
# castellano. Se imprimian tal cual --«pilar_sin_datos (74), datos_rancios
# (2)»-- en la primera frase que lee el revisor, que es ademas la unica que le
# dice de donde sale la lista que esta mirando.
#
# La traduccion vive aqui y no alli porque `ranking/score.py` no es de este
# paquete: los codigos son su vocabulario interno y estan bien como estan; lo
# que estaba mal era pintarlos. Este modulo es el que pinta.
#
# Cada frase dice **por que** quedo fuera, no solo que quedo fuera: «sin datos
# para algun pilar entero» es lo que permite leer el sesgo de la lista --dos de
# cada tres bancos pierden el pilar de solidez por reportar distinto-- en vez de
# tomarlo por una medida de calidad.
MOTIVOS_EN_CASTELLANO = {
    "historia_corta": "con poco historial publicado",
    "datos_rancios": "con las últimas cuentas demasiado antiguas",
    "pilar_sin_datos": "sin datos para algún pilar entero",
    "cobertura_insuficiente": "con muy pocos KPIs publicados",
    "sector_desconocido": "sin un sector con el que compararlas",
    "sector_sin_pares": "con demasiado pocas empresas en su sector",
    "sin_dispersion_sectorial": "en sectores donde todas puntúan casi igual",
}

_COMO_GENERARLO = (
    "Falta salidas/fichas.json. Genéralo con:\n\n"
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
        raise ContratoRoto(f"{fichero.name} no es JSON válido: {error}") from error


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
            raise ContratoRoto(f"la ficha en la posición {posicion} no es un objeto")
        faltan = _CAMPOS_FICHA - set(ficha)
        if faltan:
            raise ContratoRoto(
                f"a la ficha en la posición {posicion} le faltan campos: "
                f"{', '.join(sorted(faltan))}"
            )
        ticker = ficha["ticker"]
        if not isinstance(ticker, str) or not ticker:
            raise ContratoRoto(
                f"la ficha en la posición {posicion} tiene un ticker inválido: "
                f"{ticker!r}"
            )
        puesto = ficha["puesto"]
        # bool es subclase de int en Python (isinstance(True, int) es True);
        # True/False no son puestos validos aunque pasen ese isinstance.
        if isinstance(puesto, bool) or not isinstance(puesto, int):
            raise ContratoRoto(
                f"la ficha de {ticker!r} en la posición {posicion} "
                f"tiene un puesto inválido: {puesto!r}"
            )
        if ticker in tickers_vistos:
            raise ContratoRoto(
                f"el ticker {ticker!r} aparece más de una vez en fichas.json"
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


def kpis_con_dato(ficha: dict) -> "int | None":
    """Cuantos KPIs traian dato, o `None` si la ficha no lo registra.

    `vistas/candidatos.py` indexaba `ficha["cobertura"]["kpis_con_dato"]`
    directo, mientras `medidores.tarjeta_candidato` y `medidores._nota_pilar`
    leen los mismos campos con `.get(...)` y explican en su docstring que las
    fichas antiguas se pintan sin ellos. `_CAMPOS_FICHA` valida que `cobertura`
    exista, pero no su contenido: una `fichas.json` vieja pasaba la validacion
    entera y reventaba con `KeyError` **a mitad de la lista**, con tarjetas ya
    pintadas encima. El escenario ya esta en el repo -- `salidas_ejemplo`
    trae `kpis_con_dato` pero no `kpis_por_pilar`.

    Devuelve `None` tambien si el valor no es un entero. Ausente y corrupto se
    pintan igual --sin medidor-- porque en los dos casos lo que no hay es el
    numero, y `medidores.medidor_cobertura` lo divide: una cadena ahi revienta
    igual que la ausencia.

    `True` no cuenta: `isinstance(True, int)` es cierto en Python, y un booleano
    dibujaria una barra de un KPI de diecisiete.
    """
    cobertura = ficha.get("cobertura") or {}
    if not isinstance(cobertura, dict):
        return None
    valor = cobertura.get("kpis_con_dato")
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor


def _en_castellano(motivo: str) -> str:
    """Un codigo de `ranking/score.py`, dicho en palabras.

    Un motivo sin traducir se dice entrecomillado en vez de desaparecer: perder
    la fila haria que las cuentas por motivo no sumaran el total, que es
    exactamente el tipo de mentira silenciosa que este resumen existe para
    evitar. Hay un test que recorre los codigos de las guardas y afirma que
    estan todos, asi que anadir uno alli sin traducirlo aqui se ve en rojo
    antes de llegar a la pantalla.
    """
    frase = MOTIVOS_EN_CASTELLANO.get(motivo)
    return frase if frase else f"por «{motivo}»"


def resumen_corrida(corrida: dict | None) -> str:
    """One sentence putting the shortlist in the context of what was dropped.

    This is the whole reason B writes corrida.json. The sector tilt the guards
    produce is documented in a design file nobody reads while deciding; putting
    it in front of the reviewer at the moment of decision is what turns a
    documented bias into one that was actually taken into account.
    """
    if corrida is None:
        return (
            "Sin contexto de corrida: este ranking se generó antes de que se "
            "registraran sus metadatos, así que no se sabe a cuántas empresas "
            "dejaron fuera las guardas."
        )

    excluidas = corrida["n_panel"] - corrida["n_supervivientes"]
    if corrida["exclusiones"]:
        por_motivo = ", ".join(
            f"{cuantas} {_en_castellano(motivo)}"
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
