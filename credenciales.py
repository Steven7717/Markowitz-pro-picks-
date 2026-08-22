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
import re
from dataclasses import dataclass, replace
from pathlib import Path

RUTA = Path.home() / ".markowitz-pro-picks" / "credenciales.json"

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PREFIJO_HABITUAL = "sk-ant-"


class ConfigIlegible(ValueError):
    """Hay un fichero de credenciales, pero no se puede leer."""


class CredencialInvalida(ValueError):
    """Lo que se intenta guardar no tiene forma de credencial."""


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
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigIlegible(f"No se pudo leer {ruta}: {error}") from error
    if not isinstance(datos, dict):
        raise ConfigIlegible(f"{ruta} no contiene un objeto JSON.")
    for campo in ("api_key", "edgar_identity"):
        valor = datos.get(campo)
        if valor is not None and not isinstance(valor, str):
            raise ConfigIlegible(f"{ruta}: '{campo}' no es texto.")
    return Credenciales(
        api_key=datos.get("api_key"),
        edgar_identity=datos.get("edgar_identity"),
    ).limpia()


def validar(credenciales: Credenciales) -> None:
    """Comprobar la forma. Nunca la validez.

    Verificar la clave contra la API costaría dinero y una espera en cada
    guardado, y la app ya falla de forma visible si la clave es mala. Lo que
    sí se puede detectar aquí es un pegado roto o un correo que no lo es.
    """
    credenciales = credenciales.limpia()

    if credenciales.api_key and any(c.isspace() for c in credenciales.api_key):
        raise CredencialInvalida(
            "La clave tiene espacios o saltos de línea dentro. Suele pasar al "
            "copiarla desde un correo: pégala en una sola línea."
        )

    correo = credenciales.edgar_identity
    if correo and not _CORREO.match(correo):
        raise CredencialInvalida(
            f"'{correo}' no tiene forma de correo. La SEC exige un contacto "
            "real en la cabecera de cada petición."
        )

    if not credenciales.api_key and not credenciales.edgar_identity:
        raise CredencialInvalida(
            "No hay nada que guardar: rellena al menos uno de los dos campos."
        )


def avisos(credenciales: Credenciales) -> list[str]:
    """Lo que merece decirse pero no impedir el guardado."""
    credenciales = credenciales.limpia()
    fuera = []
    if credenciales.api_key and not credenciales.api_key.startswith(
        _PREFIJO_HABITUAL
    ):
        fuera.append(
            f"La clave no empieza por '{_PREFIJO_HABITUAL}', que es lo habitual. "
            "Se guarda igual: si Anthropic cambiara el formato, bloquearla aquí "
            "rechazaría claves buenas."
        )
    return fuera


def guardar(credenciales: Credenciales, ruta: Path | None = None) -> Path:
    """Escribir el fichero de forma atómica y devolver dónde quedó."""
    validar(credenciales)
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
    # O_TRUNC y no O_EXCL: un guardado que falló antes puede haber dejado un
    # .tmp suelto, y O_EXCL haría que el siguiente intento fallara para
    # siempre. En Windows el modo se ignora salvo el bit de sólo lectura --
    # allí la protección son los permisos de la carpeta de usuario.
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # El modo de os.open sólo se aplica al CREAR el fichero: un .tmp que dejó
    # un guardado reventado conserva los suyos, y el secreto caería dentro con
    # los permisos viejos. fchmod actúa sobre el descriptor y no sobre la ruta,
    # así que no hay ventana entre comprobar y cambiar, y cubre los dos casos.
    # En Windows os.fchmod no existe; allí la protección son los permisos de la
    # carpeta de usuario.
    try:
        os.fchmod(descriptor, 0o600)
    except (AttributeError, OSError):
        pass
    with os.fdopen(descriptor, "w", encoding="utf-8") as fichero:
        fichero.write(texto)
    tmp.replace(ruta)
    return ruta


def aplicar(
    credenciales: Credenciales, entorno: dict[str, str] | None = None
) -> None:
    """Volcar en el entorno lo que no venga ya puesto.

    Es todo el cableado que hace falta: nadie llama a
    `fundamentals/fetch.py:set_sec_identity()` en el camino de producción
    --sólo los tests-- porque edgartools lee `EDGAR_IDENTITY` del entorno por
    su cuenta, igual que el cliente de Anthropic lee `ANTHROPIC_API_KEY`.
    """
    entorno = os.environ if entorno is None else entorno
    credenciales = credenciales.limpia()
    for nombre, valor in (
        ("ANTHROPIC_API_KEY", credenciales.api_key),
        ("EDGAR_IDENTITY", credenciales.edgar_identity),
    ):
        if valor and not entorno.get(nombre):
            entorno[nombre] = valor


def reemplazar(
    anteriores: Credenciales,
    nuevas: Credenciales,
    entorno: dict[str, str] | None = None,
) -> None:
    """Poner en vigor unas credenciales que sustituyen a otras ya aplicadas.

    `aplicar` no pisa lo que ya hay, y después de arrancar siempre hay algo:
    lo puso el propio `aplicar`. Sin esto, cambiar una clave revocada la
    escribiría en disco mientras el proceso sigue usando la vieja toda la
    sesión, con la página mostrando la nueva enmascarada -- el usuario no
    tendría forma de enterarse.

    Sólo se retira lo que coincide con las anteriores, por la misma razón que
    en `borrar`: una variable puesta en el shell no la puso el usuario desde
    aquí y sigue mandando.
    """
    entorno = os.environ if entorno is None else entorno
    anteriores = anteriores.limpia()
    for nombre, valor in (
        ("ANTHROPIC_API_KEY", anteriores.api_key),
        ("EDGAR_IDENTITY", anteriores.edgar_identity),
    ):
        if valor and entorno.get(nombre) == valor:
            del entorno[nombre]
    aplicar(nuevas, entorno)


def borrar(ruta: Path | None = None, entorno: dict[str, str] | None = None) -> None:
    """Quitar el fichero y retirar del entorno lo que ese fichero había puesto.

    Sólo se retira lo que coincide con lo guardado: una variable que el
    usuario tenía en su shell no se toca, porque él no la puso desde aquí y
    no espera que la app se la borre.

    Un fichero corrupto se borra igual. Es justo el caso en que más falta le
    hace al usuario poder deshacerse de él.
    """
    ruta = Path(ruta or RUTA)
    entorno = os.environ if entorno is None else entorno
    try:
        guardadas = cargar(ruta)
    except ConfigIlegible:
        guardadas = Credenciales()

    ruta.unlink(missing_ok=True)

    for nombre, valor in (
        ("ANTHROPIC_API_KEY", guardadas.api_key),
        ("EDGAR_IDENTITY", guardadas.edgar_identity),
    ):
        if valor and entorno.get(nombre) == valor:
            del entorno[nombre]


def enmascarar(clave: str | None) -> str:
    """Lo que se puede enseñar de una clave guardada.

    Sirve para que el usuario reconozca cuál tiene puesta, no para leerla. Con
    una clave corta no se enseña nada: mostrar principio y final de algo de
    pocos caracteres es mostrarlo entero.
    """
    if not clave:
        return ""
    if len(clave) < 20:
        return "•" * 8
    return f"{clave[:7]}…{clave[-4:]}"
