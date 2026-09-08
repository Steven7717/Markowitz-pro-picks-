# noticias/cache.py
"""Frescura por fuente, y la hora de descarga siempre a la vista.

Quince activos por tres fuentes son cuarenta y cinco llamadas de red, y
Streamlit re-ejecuta el script entero con cada clic en cualquier widget. Sin
cache la pantalla no es usable.

**La hora se ensena siempre, no solo cuando el dato esta viejo.** Misma regla
que `coste_del_libro` en el sub-proyecto G: un dato que se lee como fresco sin
serlo es peor que no tener dato.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

VALIDEZ = {
    # Cambia durante el dia, pero no cada minuto.
    "prensa": timedelta(hours=1),
    # Los 8-K se presentan en horario habil, no en continuo.
    "hechos": timedelta(hours=1),
    # Una fecha de resultados no se mueve por la tarde.
    "agenda": timedelta(days=1),
}

_SEGURO = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class Guardado:
    datos: object
    cuando: datetime
    vigente: bool


def _ruta(raiz: Path, fuente: str, clave: str) -> Path:
    """El ticker viene del libro, asi que nunca compone una ruta a pelo.

    Se sanea y ademas se le pega un digest: sin el digest, "A/B" y "A_B"
    acabarian en el mismo fichero y se pisarian en silencio.
    """
    limpio = _SEGURO.sub("_", clave)[:40]
    digest = hashlib.sha256(clave.encode("utf-8")).hexdigest()[:8]
    return Path(raiz) / fuente / f"{limpio}_{digest}.json"


def guardar(raiz: Path, fuente: str, clave: str, datos) -> None:
    ruta = _ruta(raiz, fuente, clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(
            {"cuando": datetime.now(timezone.utc).isoformat(), "datos": datos},
            default=str,
        ),
        encoding="utf-8",
    )


def leer(raiz: Path, fuente: str, clave: str, validez: timedelta):
    """What is cached, or None when there is nothing usable.

    Un fichero corrupto devuelve None en vez de lanzar: una cache se regenera,
    y caerse por ella no tiene sentido. Al reves que un libro de posiciones,
    que se nombra y no se borra porque no se regenera.
    """
    ruta = _ruta(raiz, fuente, clave)
    if not ruta.exists():
        return None
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        cuando = datetime.fromisoformat(crudo["cuando"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None
    return Guardado(
        datos=crudo.get("datos"),
        cuando=cuando,
        vigente=datetime.now(timezone.utc) - cuando <= validez,
    )
