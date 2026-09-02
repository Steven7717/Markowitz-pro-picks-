"""Con qué valores arranca el optimizador, decidido por quien lo usa.

Vive en la carpeta personal y no dentro del proyecto, por la misma razón que
`credenciales.py`: quien recomprima la carpeta y se la pase a otro no le manda
sus preferencias dentro, porque nunca estuvieron ahí.

La regla que gobierna todo este módulo: **una preferencia inválida nunca deja a
nadie fuera de su propia aplicación.** Un fichero escrito por una versión
anterior, o editado a mano, cae al valor de fábrica del campo que esté mal y
avisa; no revienta el arranque. Es lo contrario de lo que hace `credenciales`,
que sí rechaza lo que no tiene forma de clave — y la diferencia está en las
consecuencias: una clave mala manda peticiones que fallan, un horizonte
desconocido sólo significa que hay que elegir otro.
"""

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from data import DEFAULT_HORIZON, HORIZON_CONFIG
from optimizer import STRATEGY_LABELS

RUTA = Path.home() / ".markowitz-pro-picks" / "preferencias.json"

ESTRATEGIA_POR_DEFECTO = "max_sharpe"


class ConfigIlegible(ValueError):
    """Hay un fichero de preferencias, pero no se puede leer."""


@dataclass(frozen=True)
class Preferencias:
    """Los valores con los que se rellena el panel del optimizador."""

    tickers: str = ""
    horizonte: str = DEFAULT_HORIZON
    estrategia: str = ESTRATEGIA_POR_DEFECTO
    peso_min: int = 0
    peso_max: int = 100
    permitir_cortos: bool = False
    shrinkage: bool = True
    guia_vista: bool = False

    def saneadas(self) -> tuple["Preferencias", list[str]]:
        """A copy with every impossible value replaced, and what was replaced.

        Devuelve los avisos en vez de escribirlos: quien llama decide si los
        pinta, y este módulo se puede probar sin capturar salida.
        """
        avisos: list[str] = []
        cambios: dict = {}

        if self.horizonte not in HORIZON_CONFIG:
            avisos.append(
                f"El horizonte guardado ({self.horizonte!r}) ya no existe; "
                f"se usa {DEFAULT_HORIZON}."
            )
            cambios["horizonte"] = DEFAULT_HORIZON

        if self.estrategia not in STRATEGY_LABELS:
            avisos.append(
                f"La estrategia guardada ({self.estrategia!r}) ya no existe; "
                "se usa Máximo Sharpe."
            )
            cambios["estrategia"] = ESTRATEGIA_POR_DEFECTO

        minimo = _entero_en_rango(self.peso_min, 0, 20, 0)
        maximo = _entero_en_rango(self.peso_max, 20, 100, 100)
        # El mínimo por activo multiplicado por el número de activos no puede
        # pasar del 100%, pero cuántos activos habrá no se sabe hasta que se
        # escriben los tickers: esa comprobación es de `validate_constraints` y
        # se hace con la cartera delante. Aquí sólo se impide lo que es
        # imposible sea cual sea la cartera.
        if minimo > maximo:
            avisos.append(
                f"El peso mínimo guardado ({minimo}%) superaba al máximo "
                f"({maximo}%); se restablecen los dos."
            )
            minimo, maximo = 0, 100
        if minimo != self.peso_min:
            cambios["peso_min"] = minimo
        if maximo != self.peso_max:
            cambios["peso_max"] = maximo

        return (replace(self, **cambios) if cambios else self), avisos


def _entero_en_rango(valor, minimo: int, maximo: int, defecto: int) -> int:
    """Clamp into the range the slider accepts; anything unusable becomes the default.

    El deslizador de Streamlit revienta si su `value` cae fuera de
    `[min, max]`, y lo hace al construir el widget: la página entera se queda
    en blanco antes de pintar nada, sin un sitio evidente donde mirar.
    """
    try:
        entero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, entero))


def cargar(ruta: Path | None = None) -> tuple[Preferencias, list[str]]:
    """Read the file. Missing is a new user, not an error.

    Un fichero corrupto tampoco es un error que deba parar nada: se devuelven
    las preferencias de fábrica con un aviso, y la primera vez que el usuario
    guarde se reemplaza solo.
    """
    ruta = Path(ruta or RUTA)
    if not ruta.exists():
        return Preferencias(), []

    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return Preferencias(), [
            f"No se pudieron leer las preferencias ({error}); se usan las de fábrica."
        ]
    if not isinstance(datos, dict):
        return Preferencias(), [
            f"{ruta.name} no contiene un objeto; se usan las preferencias de fábrica."
        ]

    conocidos = {campo: datos[campo] for campo in asdict(Preferencias()) if campo in datos}
    try:
        crudas = Preferencias(**conocidos)
    except TypeError as error:  # pragma: no cover -- conocidos ya filtra las claves
        return Preferencias(), [f"Preferencias ilegibles ({error}); se usan las de fábrica."]

    # Los campos desconocidos se ignoran en silencio a proposito: es lo que
    # permite que una version futura anada una preferencia y que este fichero
    # siga abriendose en la version que el usuario tenga instalada.
    return crudas.saneadas()


def guardar(preferencias: Preferencias, ruta: Path | None = None) -> Path:
    """Write the preferences atomically, creating the folder if needed."""
    ruta = Path(ruta or RUTA)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    limpias, _ = preferencias.saneadas()
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(asdict(limpias), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    tmp.replace(ruta)
    return ruta


def borrar(ruta: Path | None = None) -> None:
    """Back to factory settings. Missing is already the desired state."""
    Path(ruta or RUTA).unlink(missing_ok=True)
