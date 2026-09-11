"""Memoizacion por hash de lo que se manda.

Sonnet 5 no admite `temperature`, asi que dos llamadas identicas pueden
devolver textos distintos. La cache es lo que hace reproducible volver a abrir
la pantalla, y ademas gratis.

**Los fallos no se cachean.** Un corte de red congelado seria un veredicto
permanente para un problema que quiza no se repite. Eso lo decide quien llama:
aqui solo se escribe lo que se pide escribir.
"""

import hashlib
import json
from pathlib import Path

RAIZ = Path(__file__).parent / ".cache"


def clave(carga: dict) -> str:
    """sha256 de exactamente lo que se envia.

    `hashlib` y no `hash()`: Python aleatoriza el hash de las cadenas entre
    procesos, asi que `hash()` daria una clave distinta en cada arranque y la
    cache no acertaria nunca. Esa leccion ya costo una cache envenenada una
    vez -- ver `fundamentals/fetch.py:_cache_path`, que usa md5 por lo mismo.
    """
    texto = json.dumps(carga, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _fichero(nombre: str, clave_: str, directorio: "Path | None") -> Path:
    return Path(directorio or RAIZ) / nombre / f"{clave_}.json"


def leer(nombre: str, clave_: str, directorio: "Path | None" = None) -> "dict | None":
    """Lo cacheado, tratando igual un fallo y un fichero roto.

    El borrado es limpieza: un fichero malo que se quede en disco se parsea y
    se rechaza en cada llamada futura. El `except` se queda estrecho --E/S y
    decodificacion-- porque la comprobacion de forma de abajo cubre «parsea
    pero no es un objeto»; ensancharlo ademas se tragaria un fallo real de esta
    funcion detras de un inocente fallo de cache.
    """
    fichero = _fichero(nombre, clave_, directorio)
    if not fichero.exists():
        return None
    try:
        crudo = json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        fichero.unlink(missing_ok=True)
        return None
    if not isinstance(crudo, dict):
        fichero.unlink(missing_ok=True)
        return None
    return crudo


def escribir(
    nombre: str, clave_: str, datos: dict, directorio: "Path | None" = None
) -> None:
    """Escribir de forma atomica, para que nadie lea un fichero a medias.

    `replace()` es atomico en POSIX y en Windows; escribir el fichero directo
    no lo es.
    """
    fichero = _fichero(nombre, clave_, directorio)
    fichero.parent.mkdir(parents=True, exist_ok=True)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(datos, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    tmp.replace(fichero)
