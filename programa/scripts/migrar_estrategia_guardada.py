"""Deja la CLAVE de la estrategia donde un fichero guardó su etiqueta.

Se ejecuta una vez, con la app cerrada, sobre `portafolios/` y `libros/`.

**Qué arregla.** `vistas/optimizador.py` metía en `metricas["strategy"]` la
etiqueta castellana —«Máximo Sharpe (Markowitz)»— en vez de la clave
(`max_sharpe`), y de ahí salía a `portafolios/*.json` y, copiada entera por
`seguimiento/libro.py:desde_portafolio`, a `libros/*.json`. La regla que eso
rompe la documenta `cartera.Portafolio.estrategia`: en disco va la clave,
porque la etiqueta es texto de pantalla y puede reescribirse en cualquier
momento; guardarla ata un fichero a una decisión de redacción. El campo
`estrategia` del portafolio siempre la respetó — este script arregla el de al
lado, y no toca aquél.

**Por qué migrar y no sólo tolerar.** `exporter.py` tolera las dos formas, y
tiene que hacerlo: una copia de seguridad, un fichero traído de otra máquina o
uno editado a mano pueden seguir trayendo la etiqueta dentro y este script no
los alcanza. Pero la tolerancia debe ser la red de seguridad, no lo que
sostiene los datos del usuario. Cuando esto se escribió había seis ficheros,
los seis con la misma estrategia; cada corrida que se guarde a partir de
mañana hace la migración más cara y el día de arreglarla, más lejano.

**Lo que no hace.** Un valor que no corresponde a ninguna etiqueta de HOY se
queda como está y se informa. Es el caso que motivó todo esto, y ocurrió de
verdad: `b8ec37b`, el 2026-09-20, le quitó el sufijo a «Paridad de riesgo
(ERC)», así que un fichero anterior a ese commit lleva un texto que ya no
figura en `STRATEGY_LABELS`. Adivinar a qué clave pertenece sería reescribir el
pasado a ojo, y la tolerancia de `exporter.py` ya lo imprime por lo que es: la
etiqueta que se escribió aquel día.

**De ahí que el momento de pasarlo importe: antes de retocar una etiqueta, no
después.** Este script traduce contra el `STRATEGY_LABELS` de cuando se ejecuta,
así que un fichero con «Paridad de riesgo (ERC)» se migra a `risk_parity` si se
pasa antes de `b8ec37b` y se queda sin migrar si se pasa después. Los seis
ficheros que había aquí eran todos `max_sharpe` —etiqueta que no cambió— así que
en esta instalación da igual; en otra puede no darlo.

    python scripts/migrar_estrategia_guardada.py --simular
    python scripts/migrar_estrategia_guardada.py
"""

import argparse
import json
import sys
from pathlib import Path

# El script se invoca por su ruta (`python scripts/...`), así que quien entra en
# `sys.path` es `scripts/` y no `programa/`, y `import cartera` no lo
# encontraría. Los tests sí lo importan como `scripts.migrar_estrategia_guardada`
# con `programa/` ya dentro, y ahí esta línea no hace nada.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cartera  # noqa: E402
from optimizer import STRATEGY_LABELS  # noqa: E402

# La vuelta del diccionario de pantalla, derivada y no escrita a mano: una
# segunda lista de etiquetas se queda vieja el día que alguien mejore una frase,
# que es exactamente el defecto que este script viene a limpiar.
_POR_ETIQUETA = {etiqueta: clave for clave, etiqueta in STRATEGY_LABELS.items()}

CARPETAS = ("portafolios", "libros")


def clave_de(guardado) -> str | None:
    """La clave que le toca a lo que el fichero guardó, o None si no hay que tocarlo.

    None significa las tres cosas que se tratan igual —ya es una clave, es una
    etiqueta de otra redacción, o no es ni una cosa ni otra— y las tres
    comparten respuesta: dejarlo como está.
    """
    return _POR_ETIQUETA.get(guardado)


def _metricas_de(crudo: dict) -> list[dict]:
    """Los diccionarios `metricas` que hay dentro, sea un portafolio o un libro.

    Dos formas y no una: `cartera.guardar` escribe el portafolio en la raíz del
    fichero, y `seguimiento/libro.py` copia ese mismo diccionario dentro de cada
    objetivo del libro. Cada uno con su `metricas`, y todos con el mismo defecto.
    """
    encontrados = []
    if isinstance(crudo.get("metricas"), dict):
        encontrados.append(crudo["metricas"])
    for objetivo in crudo.get("objetivos") or ():
        if not isinstance(objetivo, dict):
            continue
        portafolio = objetivo.get("portafolio")
        if isinstance(portafolio, dict) and isinstance(portafolio.get("metricas"), dict):
            encontrados.append(portafolio["metricas"])
    return encontrados


def migrar(crudo: dict) -> int:
    """Cambia las etiquetas por sus claves, en el sitio. Devuelve cuántas cambió.

    Cero significa que no había nada que hacer, y quien llama lo usa para no
    reescribir el fichero.
    """
    cambiadas = 0
    for metricas in _metricas_de(crudo):
        clave = clave_de(metricas.get("strategy"))
        if clave is not None:
            metricas["strategy"] = clave
            cambiadas += 1
    return cambiadas


def migrar_fichero(ruta: Path, simular: bool = False) -> int:
    """Migra un fichero en su sitio. Devuelve cuántas métricas cambió.

    **Si no cambia nada, no lo toca.** Reescribir un fichero idéntico le movería
    la fecha y, con otros ajustes de `json.dumps`, lo reformatearía entero: seis
    ficheros modificados por una migración que no arregló ni un campo.

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

    cambiadas = migrar(crudo)
    if cambiadas and not simular:
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
    return cambiadas


def _sin_migrar(crudo: dict) -> list[str]:
    """Los valores que se quedan como estaban, para poder nombrarlos en el informe."""
    return [
        m["strategy"] for m in _metricas_de(crudo)
        if isinstance(m.get("strategy"), str) and m["strategy"] not in STRATEGY_LABELS
    ]


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

    tocados = rotos = 0
    for ruta in ficheros:
        try:
            cambiadas = migrar_fichero(ruta, simular=args.simular)
        except (cartera.ContratoRoto, ValueError) as error:
            rotos += 1
            print(f"  SIN TOCAR  {ruta}: {error}")
            continue
        if cambiadas:
            tocados += 1
            verbo = "migraría" if args.simular else "migrado"
            print(f"  {verbo:>9}  {ruta} ({cambiadas} métricas)")
        else:
            # El que ya estaba bien y el que lleva una etiqueta de otra
            # redacción salen distintos: el segundo es el que hay que mirar.
            ajenas = _sin_migrar(json.loads(ruta.read_text(encoding="utf-8")))
            if ajenas:
                print(
                    f"  a mano     {ruta}: {', '.join(repr(a) for a in ajenas)} "
                    "no es ninguna etiqueta de hoy; se queda como está y "
                    "`exporter.py` la sigue imprimiendo tal cual."
                )
            else:
                print(f"  ya estaba  {ruta}")

    print(
        f"{len(ficheros)} ficheros | "
        f"{'a migrar' if args.simular else 'migrados'}: {tocados} | "
        f"ilegibles: {rotos}"
    )
    return 1 if rotos else 0


if __name__ == "__main__":
    sys.exit(main())
