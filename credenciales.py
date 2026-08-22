"""Las credenciales del usuario, guardadas fuera del proyecto.

Vive en la raíz y no dentro de `aprobacion/` porque lo consumen tres paquetes
--`fundamentals`, `ranking` y la página de aprobación--; meterlo en uno de ellos
crearía una dependencia hacia arriba entre paquetes que hoy no se conocen.

El fichero se escribe en la carpeta personal del usuario, nunca dentro del
proyecto: quien recomprima la carpeta y se la pase a otro no manda su clave
dentro, porque nunca estuvo ahí. `.gitignore` protege de git, no de un ZIP.
"""

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

RUTA = Path.home() / ".markowitz-pro-picks" / "credenciales.json"


@dataclass(frozen=True)
class Credenciales:
    """Los dos datos que necesita la mitad con IA."""

    api_key: str | None = None
    edgar_identity: str | None = None

    def limpia(self) -> "Credenciales":
        """Copia sin espacios sobrantes, con lo vacío convertido en ausente.

        Un campo en blanco significa "no lo tengo", no "lo tengo y es la
        cadena vacía": son estados distintos y `disponibilidad()` ya trata el
        segundo como ausente.
        """
        return replace(
            self,
            api_key=_limpiar(self.api_key),
            edgar_identity=_limpiar(self.edgar_identity),
        )


def _limpiar(valor: str | None) -> str | None:
    if valor is None:
        return None
    return valor.strip() or None


def cargar(ruta: Path | None = None) -> Credenciales:
    """Leer el fichero. Que no exista es un usuario nuevo, no un error."""
    ruta = Path(ruta or RUTA)
    if not ruta.exists():
        return Credenciales()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return Credenciales(
        api_key=datos.get("api_key") or None,
        edgar_identity=datos.get("edgar_identity") or None,
    ).limpia()


def guardar(credenciales: Credenciales, ruta: Path | None = None) -> Path:
    """Escribir el fichero de forma atómica y devolver dónde quedó."""
    credenciales = credenciales.limpia()
    ruta = Path(ruta or RUTA)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    texto = json.dumps(
        {
            "api_key": credenciales.api_key,
            "edgar_identity": credenciales.edgar_identity,
        },
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)
    return ruta
