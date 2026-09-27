"""Del rendimiento en dolares al rendimiento real en pesos.

Tres pasos, en este orden y no en otro: convertir a pesos con el FIX de cada
fecha, medir con las mismas funciones de `rendimiento`, y descontar la
inflacion con Fisher. Descontar el INPC de un rendimiento en dolares mezcla dos
monedas y da un numero plausible que no mide nada.

Aqui no hay red: las series llegan ya descargadas de `seguimiento/banxico.py`.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from seguimiento import rendimiento


def real(nominal: "float | None", inflacion_anual: "float | None") -> "float | None":
    """Ecuacion de Fisher exacta: `(1 + nominal) / (1 + π) − 1`.

    No `nominal − π`. Con la inflacion mexicana la aproximacion se equivoca en
    decimas, y en pantalla esa diferencia no se veria. Un `None` en cualquiera
    de las dos entradas es «no se puede medir», y lo sigue siendo a la salida.
    """
    if nominal is None or inflacion_anual is None or inflacion_anual <= -1.0:
        return None
    return (1.0 + nominal) / (1.0 + inflacion_anual) - 1.0
