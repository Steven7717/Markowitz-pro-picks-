# programa/interprete/archivo.py
"""Lo interpretado, guardado para siempre.

La cache por hash conserva interpretaciones, pero es una **optimizacion de
coste**: clave opaca, dentro de un `.cache/`, borrable sin avisar y sin forma de
hojearla. Esto es otra cosa, y resuelve algo que la cache no puede.

**Repara la ceguera del tope de seis.** Un `4.02` de hace ocho meses hoy no lo
ve nadie, porque hay seis hechos mas nuevos por encima. Pero si se guardo cuando
*era* reciente, se queda leido para siempre: el archivo acumula cobertura con el
tiempo, y el tope deja de ser una ceguera permanente para ser una ventana.

**Y abarata.** Solo hace falta mandar el documento de los hechos cuya url no
este aqui; los ya leidos entran como su `que_dice` guardado, unos cientos de
caracteres en lugar de treinta mil.

## Donde vive, y una trampa que casi se cuela

`libros/interpretaciones/<mismo basename que el libro>.json`.

**No en `libros/` a secas.** `libro.listar()` hace `glob("*.json")` sobre esa
carpeta y `libro.cargar` valida lo que encuentre: un fichero de interpretaciones
ahi dentro apareceria como **un libro ilegible**, que es exactamente el defecto
que H pago -- un libro que no se puede leer contandose como que no hay ninguno.
`Path.glob` no recorre subcarpetas, asi que la subcarpeta basta, y hay un test
que lo afirma. Queda bajo `libros/`, que ya esta en `.gitignore`.

## Es append-only, como el libro

Volver a interpretar **anade**, no pisa. Un juicio es una opinion hecha en un
momento, por un modelo y una version de prompt concretos; reescribirla borraria
que cambio. Misma forma que `Libro.objetivos`, que es una tupla donde `objetivo`
devuelve el ultimo: se conserva todo, se ensena lo ultimo.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from interprete import noticias

SUBCARPETA = "interpretaciones"


class ArchivoIlegible(ValueError):
    """Hay un archivo, pero no se puede leer.

    **No es un fallo de cache.** `cache.leer` borra el fichero roto y devuelve
    `None`, y hace bien: alli lo perdido es una llamada que se puede repetir.
    Aqui lo perdido es historial, y tragarselo en silencio significaria volver a
    pagar Y perder lo guardado sin que nadie se entere.

    Misma distincion que `credenciales.ConfigIlegible` frente a «no hay
    fichero»: uno es un usuario nuevo, el otro es un problema.
    """


@dataclass(frozen=True)
class Anotada:
    """Un hecho leido. Su identidad es la `url` del expediente en EDGAR, que ya
    viaja en `Hecho` y no hay que inventar ninguna."""

    url: str
    ticker: str
    hecho_cuando: date
    tipos: "tuple[str, ...]"
    juicio: noticias.Juicio


@dataclass(frozen=True)
class Sesion:
    """Una pulsacion del boton de hechos.

    `en_conjunto` es de la sesion y no de un hecho: habla de los seis juntos y
    no tiene donde ir si se reparte.
    """

    cuando: datetime
    modelo: str
    version: str
    juicios: "tuple[Anotada, ...]"
    en_conjunto: str


@dataclass(frozen=True)
class Foto:
    """El estado que un comentario de rebalanceo comentaba.

    Sin esto el texto queda huerfano: habla de una deriva que manana ya es otra,
    y releerlo junto a la propuesta de hoy seria mezclar dos cortes temporales
    -- el defecto que en F dio una `GANANCIA -9.700`.
    """

    pesos_reales: "tuple[tuple[str, float], ...]"
    pesos_objetivo: "tuple[tuple[str, float], ...]"
    operaciones: "tuple[tuple[str, str, float], ...]"


@dataclass(frozen=True)
class Comentada:
    cuando: datetime
    modelo: str
    version: str
    foto: Foto
    observaciones: "tuple[tuple[str, str], ...]"
    en_conjunto: str


@dataclass(frozen=True)
class Archivo:
    hechos: "tuple[Sesion, ...]" = ()
    rebalanceo: "tuple[Comentada, ...]" = ()


def ruta_de(ruta_libro: Path) -> Path:
    """Donde va el archivo de un libro. Ver la trampa del docstring de arriba."""
    ruta_libro = Path(ruta_libro)
    return ruta_libro.parent / SUBCARPETA / ruta_libro.name


def cargar(ruta: Path) -> Archivo:
    """Lo guardado. Que no exista es un libro que nadie ha interpretado."""
    ruta = Path(ruta)
    if not ruta.exists():
        return Archivo()
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchivoIlegible(f"No se pudo leer {ruta}: {error}") from error
    if not isinstance(crudo, dict):
        raise ArchivoIlegible(f"{ruta} no contiene un objeto JSON.")
    try:
        return Archivo(
            hechos=tuple(_sesion(s) for s in crudo.get("hechos", [])),
            rebalanceo=tuple(_comentada(c) for c in crudo.get("rebalanceo", [])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ArchivoIlegible(f"{ruta} tiene una forma que no se reconoce: {error}") from error


def _sesion(crudo: dict) -> Sesion:
    return Sesion(
        cuando=datetime.fromisoformat(crudo["cuando"]),
        modelo=crudo["modelo"],
        version=crudo["version"],
        en_conjunto=crudo.get("en_conjunto", ""),
        juicios=tuple(
            Anotada(
                url=j["url"],
                ticker=j["ticker"],
                hecho_cuando=date.fromisoformat(j["hecho_cuando"]),
                tipos=tuple(j["tipos"]),
                juicio=noticias.Juicio(
                    ticker=j["ticker"],
                    que_dice=j["que_dice"],
                    por_que_te_toca=j["por_que_te_toca"],
                    cita=j["cita"],
                    verificada=bool(j["verificada"]),
                ),
            )
            for j in crudo["juicios"]
        ),
    )


def _comentada(crudo: dict) -> Comentada:
    foto = crudo["foto"]
    return Comentada(
        cuando=datetime.fromisoformat(crudo["cuando"]),
        modelo=crudo["modelo"],
        version=crudo["version"],
        foto=Foto(
            pesos_reales=tuple((t, float(p)) for t, p in foto["pesos_reales"]),
            pesos_objetivo=tuple((t, float(p)) for t, p in foto["pesos_objetivo"]),
            operaciones=tuple((t, a, float(p)) for t, a, p in foto["operaciones"]),
        ),
        observaciones=tuple((o["sobre"], o["dice"]) for o in crudo["observaciones"]),
        en_conjunto=crudo.get("en_conjunto", ""),
    )


def urls_leidas(guardado: Archivo) -> "set[str]":
    """Las urls de todo lo ya interpretado, de todas las sesiones.

    Es lo que deriva «que es nuevo», y lo que decide de que hechos hay que bajar
    el documento.
    """
    return {
        anotada.url for sesion in guardado.hechos for anotada in sesion.juicios
    }


def juicio_guardado(guardado: Archivo, url: str) -> "Anotada | None":
    """La **ultima** lectura de ese hecho. Append-only por debajo, lo ultimo por
    arriba: misma forma que `Libro.objetivo` sobre `Libro.objetivos`."""
    ultima = None
    for sesion in guardado.hechos:
        for anotada in sesion.juicios:
            if anotada.url == url:
                ultima = anotada
    return ultima


def _escribir(ruta: Path, guardado: Archivo) -> None:
    """Atomico, y releyendo justo antes.

    Streamlit permite dos ventanas del mismo libro: releer inmediatamente antes
    de escribir reduce la ventana en la que una pisa a la otra. Misma decision
    que `libro.actualizar`. El riesgo residual se acepta: un usuario, una app.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(
        {
            "hechos": [
                {
                    "cuando": s.cuando.isoformat(),
                    "modelo": s.modelo,
                    "version": s.version,
                    "en_conjunto": s.en_conjunto,
                    "juicios": [
                        {
                            "url": a.url,
                            "ticker": a.ticker,
                            "hecho_cuando": a.hecho_cuando.isoformat(),
                            "tipos": list(a.tipos),
                            "que_dice": a.juicio.que_dice,
                            "por_que_te_toca": a.juicio.por_que_te_toca,
                            "cita": a.juicio.cita,
                            "verificada": a.juicio.verificada,
                        }
                        for a in s.juicios
                    ],
                }
                for s in guardado.hechos
            ],
            "rebalanceo": [
                {
                    "cuando": c.cuando.isoformat(),
                    "modelo": c.modelo,
                    "version": c.version,
                    "en_conjunto": c.en_conjunto,
                    "foto": {
                        "pesos_reales": [list(p) for p in c.foto.pesos_reales],
                        "pesos_objetivo": [list(p) for p in c.foto.pesos_objetivo],
                        "operaciones": [list(o) for o in c.foto.operaciones],
                    },
                    "observaciones": [
                        {"sobre": sobre, "dice": dice}
                        for sobre, dice in c.observaciones
                    ],
                }
                for c in guardado.rebalanceo
            ],
        },
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)


def anotar_hechos(
    ruta: Path, modelo: str, version: str, juicios: "tuple[Anotada, ...]",
    en_conjunto: str,
) -> None:
    """Anadir una sesion de lectura. Nunca pisa la anterior."""
    guardado = cargar(ruta)
    sesion = Sesion(datetime.now(), modelo, version, tuple(juicios), en_conjunto)
    _escribir(ruta, Archivo(guardado.hechos + (sesion,), guardado.rebalanceo))


def anotar_rebalanceo(
    ruta: Path, modelo: str, version: str, foto: Foto,
    observaciones: "tuple[tuple[str, str], ...]", en_conjunto: str,
) -> None:
    """Anadir un comentario de rebalanceo, con la foto del estado que comentaba."""
    guardado = cargar(ruta)
    comentada = Comentada(
        datetime.now(), modelo, version, foto, tuple(observaciones), en_conjunto
    )
    _escribir(ruta, Archivo(guardado.hechos, guardado.rebalanceo + (comentada,)))
