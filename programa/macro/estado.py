# macro/estado.py
"""Fuente, fase y vigencia juntas: lo único que consumen las vistas.

Las dos pantallas necesitan lo mismo —la serie para el gráfico, la fase y si
puede mover el Top— y dos copias de esta unión se separarían.
"""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from macro import fuentes
from macro.fase import Fase, determinar, motivo_para_no_inclinar


@dataclass(frozen=True)
class Estado:
    region: str
    serie: "pd.Series | None"
    fase: "Fase | None"
    motivo_no_inclinar: "str | None"
    descargada: "datetime | None"
    vieja: bool


def leer_region(region: str, hoy: date, *, traer=None) -> Estado:
    traer = traer or fuentes.traer_cli
    resultado = traer(region)
    if resultado.datos is None:
        return Estado(region, None, None, resultado.motivo, None, False)
    fase = determinar(resultado.datos)
    return Estado(
        region=region,
        serie=resultado.datos,
        fase=fase,
        motivo_no_inclinar=motivo_para_no_inclinar(fase, hoy),
        descargada=resultado.descargada,
        vieja=resultado.vieja,
    )
