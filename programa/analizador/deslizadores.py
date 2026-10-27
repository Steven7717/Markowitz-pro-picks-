"""Los deslizadores de la valoración: qué se mueve, entre qué cifras y qué cuenta como movido.

Sin Streamlit. `analizador.valorar.valorar` y `sensibilidad` son aritmética pura
sobre unas `Entradas` ya traídas, así que mover un deslizador no vuelve a la
red. Lo que decide este módulo es lo de alrededor:

- **Qué se mueve**: los supuestos que el método usa y que
  `valoracion.supuestos.MOVIBLES` deja mover. El coste del capital propio y el
  de capital no: se recalculan de los demás.
- **Entre qué cifras**: un recorrido por supuesto, ensanchado si la cifra del
  programa cae fuera.
- **Qué cuenta como movido**: la pantalla enseña porcentajes y la cuenta usa
  tantos por uno.

**Lo movido no se guarda en ningún sitio.** Vive en las claves de los widgets
mientras dura la sesión; lo que va al acta es siempre la valoración del
programa.
"""

import math
from dataclasses import dataclass

from analizador.valorar import Entradas, supuestos_de
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.supuestos import MOVIBLES, SUPUESTOS_DE, movidos

# En tanto por uno: (mínimo, máximo, paso, se enseña en %). Son recorridos de un
# supuesto razonable, no los límites de las fórmulas: lo imposible --impuestos
# del 100 %, un reparto negativo, un coste de capital que no es positivo-- lo
# rechaza `aplicar` con `ValueError`, y la pantalla enseña por qué.
_RANGOS = {
    "r_f": (0.0, 0.20, 0.001, True),
    "beta": (-1.0, 3.0, 0.01, False),
    "prima": (0.0, 0.12, 0.001, True),
    "k_d": (0.0, 0.25, 0.001, True),
    "t": (0.0, 0.60, 0.005, True),
    "g_ref": (-0.20, 0.60, 0.005, True),
    "g_perpetuo": (-0.02, 0.06, 0.001, True),
    "roe_ref": (-0.20, 0.60, 0.005, True),
    "payout": (0.0, 1.0, 0.01, True),
}

# 4,12 % en pantalla son 0,0412 en la cuenta, y en coma flotante 4.12 / 100 no
# siempre da 0.0412. Sin tolerancia, un deslizador sin tocar contaría como
# movido y la pantalla diría «movido por ti» junto a la cifra del programa.
_TOLERANCIA = 1e-9


@dataclass(frozen=True)
class Rango:
    """El recorrido de un deslizador, en las unidades de la pantalla."""

    minimo: float
    maximo: float
    paso: float
    porcentaje: bool

    @property
    def formato(self) -> str:
        return "%.1f %%" if self.porcentaje else "%.2f"


def metodo(entradas: Entradas) -> str:
    """El método de la valoración, con la misma regla que `valoracion.motor.calcular`."""
    return "residual" if entradas.perfil.industria in INDUSTRIAS_FINANCIERAS else "flujos"


def movibles(metodo_: str) -> "tuple[str, ...]":
    """Los supuestos que se pueden mover en ese método, en el orden en que se enseñan.

    En una financiera el coste de la deuda y los impuestos no entran en ninguna
    cuenta, y `aplicar` los rechaza: ni se dibujan.
    """
    return tuple(nombre for nombre in SUPUESTOS_DE[metodo_] if nombre in MOVIBLES)


def a_pantalla(nombre: str, valor: float) -> float:
    """De tanto por uno a lo que enseña el deslizador."""
    return valor * 100 if _RANGOS[nombre][3] else valor


def de_pantalla(nombre: str, valor: float) -> float:
    """De lo que enseña el deslizador a tanto por uno."""
    return valor / 100 if _RANGOS[nombre][3] else valor


def rango(nombre: str, valor: "float | None") -> Rango:
    """El recorrido del deslizador, ensanchado si la cifra del programa cae fuera.

    Un deslizador que no puede enseñar el valor de partida mentiría sobre él:
    una beta medida de 3,4 se quedaría en 3,0 sólo por dibujarse.
    """
    minimo, maximo, paso, porcentaje = _RANGOS[nombre]
    if valor is not None:
        minimo, maximo = min(minimo, valor), max(maximo, valor)
    escala = 100 if porcentaje else 1
    return Rango(minimo * escala, maximo * escala, paso * escala, porcentaje)


def del_programa(entradas: Entradas, r_f_a_mano: "float | None" = None) -> "dict[str, float | None] | None":
    """Lo que dice el programa de cada supuesto movible, o None sin tasa libre.

    Sin Bono M la tasa libre la pone el usuario (`r_f_a_mano`, en tanto por uno)
    y lo demás se deduce con ella, que es lo que hace `valorar.supuestos_de`.
    Lanza `ValueError` con una tasa a mano que deja un coste de capital no
    positivo.

    Un None es un supuesto que el programa no tiene (sin historia para el
    crecimiento de referencia, sin años para el ROE): la pantalla pide la cifra
    en vez de dibujar un deslizador sin punto de partida.
    """
    if entradas.r_f is None:
        if r_f_a_mano is None:
            return None
        de_partida = {"r_f": r_f_a_mano}
    else:
        de_partida = {}
    supuestos = supuestos_de(entradas, de_partida)
    return {nombre: getattr(supuestos, nombre).valor for nombre in movibles(metodo(entradas))}


def cambios(en_pantalla: dict, programa: dict, r_f_a_mano: "float | None" = None) -> dict:
    """Lo movido, en tanto por uno, listo para `valorar(entradas, pilar, cambios)`.

    `en_pantalla` es lo que enseñan los deslizadores, en sus unidades; un None
    es una casilla vacía y no cuenta. Lo que coincide con el programa, dentro de
    la tolerancia, tampoco. La tasa puesta a mano va siempre: sin ella no hay
    supuestos.
    """
    salida = {} if r_f_a_mano is None else {"r_f": r_f_a_mano}
    for nombre, mostrado in en_pantalla.items():
        if mostrado is None:
            continue
        valor = de_pantalla(nombre, float(mostrado))
        de_antes = programa.get(nombre)
        if de_antes is None or not math.isclose(
            valor, de_antes, rel_tol=_TOLERANCIA, abs_tol=_TOLERANCIA
        ):
            salida[nombre] = valor
    return salida


def nombres_movidos(entradas: Entradas, cambios_: dict) -> "tuple[str, ...]":
    """Los que movió el usuario, con `supuestos.movidos`; la tasa puesta a mano cuenta.

    Lanza `ValueError` como `aplicar`, con lo mismo que lo lanzaría `valorar`.
    """
    supuestos = supuestos_de(entradas, cambios_)
    return () if supuestos is None else movidos(supuestos)
