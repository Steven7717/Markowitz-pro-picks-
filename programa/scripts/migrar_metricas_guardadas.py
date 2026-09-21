"""Deja en `metricas` el DATO donde un fichero guardó su texto de pantalla.

Se ejecuta una vez, con la app cerrada, sobre `portafolios/` y `libros/`.

**Qué arregla.** El diccionario `metricas` que `vistas/optimizador.py` escribe
no es sólo del informe: se le pasa a `cartera.desde_corrida(metricas=...)`, que
lo guarda en `portafolios/*.json`, y `seguimiento/libro.py:desde_portafolio` lo
copia entero a `libros/*.json`. Dos campos suyos guardaban la forma de pantalla
en vez del dato, **y los dos tenían al lado, en el mismo JSON, el campo tipado
que ya lo decía bien**:

    "estrategia": "max_sharpe"                 "shrinkage": true
    "metricas": {                              "metricas": {
      "strategy": "Máximo Sharpe (Markowitz)"    "shrinkage": "Sí"

La regla la documenta `cartera.Portafolio.estrategia`: en disco va la clave,
porque la etiqueta es texto de pantalla y puede reescribirse en cualquier
momento; guardarla ata un fichero a una decisión de redacción. No es un temor
abstracto — `b8ec37b` le quitó el sufijo a «Paridad de riesgo (ERC)».

**De dónde saca el valor bueno: del campo hermano, no del texto.** Es lo que
hace que esta migración no dependa de ninguna redacción. Traducir «Máximo
Sharpe (Markowitz)» de vuelta a `max_sharpe` obligaría a reconocer la redacción
de cada época, y un fichero anterior a un cambio de texto se quedaría sin
migrar; el campo `estrategia` que vive dos líneas más arriba lo dice sin
ambigüedad y no ha cambiado nunca. Lo mismo con `shrinkage`.

**Lo que no hace.** Si el campo hermano no está o no sirve, se informa y no se
toca. Y si el texto guardado se puede leer y **contradice** al hermano —un
fichero editado a mano—, tampoco: el fichero se contradice a sí mismo y eso lo
mira una persona, no un script.

**Las preferencias no entran aquí, y no hace falta.** El fichero de
`~/.markowitz-pro-picks/` también guarda un horizonte con la redacción de
entonces, pero `preferencias.saneadas()` lo traduce cada vez que se lee y lo
deja en clave la primera vez que el usuario guarde. Un script que entra en la
carpeta personal de alguien para arreglar algo que se arregla solo no se
escribe.

    python scripts/migrar_metricas_guardadas.py --simular
    python scripts/migrar_metricas_guardadas.py
"""

import argparse
import json
import sys
from pathlib import Path

# El script se invoca por su ruta (`python scripts/...`), así que quien entra en
# `sys.path` es `scripts/` y no `programa/`, y `import cartera` no lo
# encontraría. Los tests sí lo importan como `scripts.migrar_metricas_guardadas`
# con `programa/` ya dentro, y ahí esta línea no hace nada.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cartera  # noqa: E402
from data import HORIZON_CONFIG, clave_de_horizonte  # noqa: E402
from optimizer import STRATEGY_LABELS  # noqa: E402

CARPETAS = ("portafolios", "libros")


def _es_clave(valor) -> bool:
    return valor in STRATEGY_LABELS


def _es_booleano(valor) -> bool:
    return isinstance(valor, bool)


def _leer_etiqueta(texto):
    """La clave que una etiqueta de HOY nombra, o None si no se reconoce.

    Derivada del diccionario de pantalla, no escrita a mano: una segunda lista
    de etiquetas se queda vieja el día que alguien mejore una frase, que es el
    defecto que este script viene a limpiar.
    """
    return {etiqueta: clave for clave, etiqueta in STRATEGY_LABELS.items()}.get(texto)


def _leer_palabra(texto):
    """El booleano que «Sí» o «No» nombran, o None si es otra cosa."""
    return {"Sí": True, "No": False}.get(texto)


def _es_clave_horizonte(valor) -> bool:
    return valor in HORIZON_CONFIG


# Qué campo de `metricas` es la copia renderizada de qué campo del portafolio,
# cómo se reconoce que ya está en su forma de dato, y cómo se lee el texto
# viejo — esto último SÓLO para detectar que el fichero se contradice, nunca
# para sacar el valor bueno.
CAMPOS = {
    "strategy": ("estrategia", _es_clave, _leer_etiqueta),
    "shrinkage": ("shrinkage", _es_booleano, _leer_palabra),
    "horizon": ("horizonte", _es_clave_horizonte, clave_de_horizonte),
}


def _portafolios_de(crudo: dict) -> list[dict]:
    """Los objetos con forma de portafolio que hay dentro del fichero.

    Dos formas y no una: `cartera.guardar` escribe el portafolio en la raíz, y
    `seguimiento/libro.py` copia ese mismo objeto dentro de cada objetivo del
    libro. Se devuelve el portafolio entero y no sólo su `metricas` porque el
    valor bueno está justo ahí, en sus campos tipados.
    """
    encontrados = []
    if isinstance(crudo.get("metricas"), dict):
        encontrados.append(crudo)
    for objetivo in crudo.get("objetivos") or ():
        if not isinstance(objetivo, dict):
            continue
        portafolio = objetivo.get("portafolio")
        if isinstance(portafolio, dict) and isinstance(portafolio.get("metricas"), dict):
            encontrados.append(portafolio)
    return encontrados


def arreglos_de(portafolio: dict) -> tuple[dict, list[str]]:
    """Qué hay que cambiar en su `metricas`, y de qué hay que quejarse.

    Pura: no toca nada. Quien llama decide si escribe.
    """
    metricas = portafolio.get("metricas") or {}
    del_portafolio: dict = {}
    cambios: dict = {}
    quejas: list[str] = []

    # **El horizonte es el único que no tiene hermano del que copiar**, porque
    # antes no había clave ninguna: la etiqueta ERA la identidad. Aquí sí hay
    # que traducir el texto, y se puede porque `data._HEREDADOS` es una tabla
    # congelada —la redacción vigente hasta el 2026-09-20, que ya es historia y
    # no se recalcula—. Va primero: `metricas["horizon"]` copia de este campo, y
    # tiene que copiar del arreglado.
    horizonte = portafolio.get("horizonte")
    if horizonte is not None and not _es_clave_horizonte(horizonte):
        clave = clave_de_horizonte(horizonte)
        if clave is None:
            quejas.append(
                f"horizonte={horizonte!r} no es ninguno de los de hoy ni de los "
                "de antes: se queda como está"
            )
        else:
            del_portafolio["horizonte"] = clave

    # Con el horizonte ya arreglado, para que el hermano del que se copia sea el
    # bueno y no el que había cuando empezó esta función.
    portafolio = {**portafolio, **del_portafolio}

    for campo, (hermano, ya_es_dato, leer) in CAMPOS.items():
        if campo not in metricas:
            continue
        guardado = metricas[campo]
        if ya_es_dato(guardado):
            continue

        bueno = portafolio.get(hermano)
        if not ya_es_dato(bueno):
            quejas.append(
                f"metricas.{campo}={guardado!r} no es un dato, y el campo "
                f"«{hermano}» tampoco lo dice ({bueno!r}): se queda como está"
            )
            continue

        # La única lectura del texto viejo que hay en todo el script, y no es
        # para sacar el valor: es para no pisar en silencio un fichero que se
        # contradice a sí mismo. Si el texto no se reconoce --una redacción
        # retirada-- no hay contradicción que detectar y manda el hermano.
        dice = leer(guardado)
        if dice is not None and dice != bueno:
            quejas.append(
                f"metricas.{campo}={guardado!r} y «{hermano}»={bueno!r} no "
                "dicen lo mismo: el fichero se contradice y no se toca"
            )
            continue

        cambios[campo] = bueno

    return del_portafolio, cambios, quejas


def migrar(crudo: dict) -> tuple[int, list[str]]:
    """Aplica los arreglos en el sitio. Devuelve cuántos campos cambió y las quejas.

    Cero significa que no había nada que hacer, y quien llama lo usa para no
    reescribir el fichero.
    """
    cambiados = 0
    quejas: list[str] = []
    for portafolio in _portafolios_de(crudo):
        propios, arreglos, suyas = arreglos_de(portafolio)
        portafolio.update(propios)
        portafolio["metricas"].update(arreglos)
        cambiados += len(propios) + len(arreglos)
        quejas += suyas
    return cambiados, quejas


def migrar_fichero(ruta: Path, simular: bool = False) -> tuple[int, list[str]]:
    """Migra un fichero en su sitio. Devuelve cuántos campos cambió y las quejas.

    **Si no cambia nada, no lo toca.** Reescribir un fichero idéntico le movería
    la fecha y, con otros ajustes de `json.dumps`, lo reformatearía entero.

    Un fichero ilegible se deja como está y se informa, igual que hacen
    `cartera.cargar` y `seguimiento/libro.py:cargar`. Lo que hay ahí dentro es la
    única copia de una corrida guardada, y un script de limpieza no es quien
    decide tirarla.
    """
    ruta = Path(ruta)
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise cartera.ContratoRoto(f"{ruta.name} no se puede leer: {error}") from error
    if not isinstance(crudo, dict):
        raise cartera.ContratoRoto(f"{ruta.name} no contiene un objeto")

    cambiados, quejas = migrar(crudo)
    if cambiados and not simular:
        # Los mismos ajustes que `cartera.guardar` y `seguimiento/libro.py`, para
        # que el fichero migrado sea indistinguible de uno recién escrito por el
        # programa: `indent=2` y `ensure_ascii=False` —las tildes se quedan
        # legibles fuera de Python— y `allow_nan=False`, que hace ruido en vez de
        # escribir un literal `NaN` que ningún otro lector de JSON acepta.
        texto = json.dumps(crudo, ensure_ascii=False, indent=2, allow_nan=False)
        # El helper privado de `cartera` a propósito: es el `mkstemp`+`replace`
        # en el mismo directorio, con el porqué de cada detalle escrito encima.
        # De ese patrón ya hay dos copias en el programa; una tercera aquí sería
        # la que se quede vieja.
        cartera._escribir_encima(ruta, texto)
    return cambiados, quejas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "base", nargs="?", type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="La carpeta `programa/` cuyos portafolios/ y libros/ se migran "
             "(por defecto, la de este script).",
    )
    parser.add_argument(
        "--simular", action="store_true",
        help="Dice lo que haría y no escribe nada.",
    )
    args = parser.parse_args(argv)

    ficheros = sorted(
        ruta
        for carpeta in CARPETAS
        for ruta in (args.base / carpeta).glob("*.json")
    )
    if not ficheros:
        print(f"No hay nada que migrar en {args.base}/{{{','.join(CARPETAS)}}}/")
        return 0

    tocados = rotos = a_mano = 0
    for ruta in ficheros:
        try:
            cambiados, quejas = migrar_fichero(ruta, simular=args.simular)
        except (cartera.ContratoRoto, ValueError) as error:
            rotos += 1
            print(f"  SIN TOCAR  {ruta}: {error}")
            continue
        if cambiados:
            tocados += 1
            verbo = "migraría" if args.simular else "migrado"
            print(f"  {verbo:>9}  {ruta} ({cambiados} campos)")
        elif not quejas:
            print(f"  ya estaba  {ruta}")
        for queja in quejas:
            a_mano += 1
            print(f"  a mano     {ruta}: {queja}")

    print(
        f"{len(ficheros)} ficheros | "
        f"{'a migrar' if args.simular else 'migrados'}: {tocados} | "
        f"a mano: {a_mano} | ilegibles: {rotos}"
    )
    return 1 if rotos else 0


if __name__ == "__main__":
    sys.exit(main())
