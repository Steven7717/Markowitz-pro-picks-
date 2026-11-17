# macro/criterio.py
"""El criterio de la fase y de su inclinación, congelado antes de mirar resultados.

Datos, no lógica, como `ranking/criterio.py`: la fecha del commit que introduce
este fichero prueba que ningún número se movió una vez vistas las fases.
Cambiarlo exige una enmienda fechada en
docs/superpowers/specs/2026-11-15-entorno-macro-design.md, nunca una edición
callada.

Aquí no hay texto de pantalla. Los nombres que ve el usuario están en
`macro/textos.py`, y las claves de aquí son lo único que se guarda en disco.
"""

NIVEL_NEUTRO = 100.0
MESES_DIRECCION = 3
MAX_ANTIGUEDAD_MESES = 3
INCLINACION = 0.25

# Clave interna → área de referencia del flujo del CLI de la OCDE.
# `G4E` y no `EA20`: el flujo no tiene la zona euro entera (enmienda 1).
REGIONES: dict[str, str] = {
    "usa": "USA",
    "mex": "MEX",
    "eurozona": "G4E",
    "china": "CHN",
    "g7": "G7",
}
REGION_POR_DEFECTO = "usa"

# La rotación sectorial clásica por fases del ciclo. El porqué de cada
# sector, en palabras, está en `macro/textos.py:POR_QUE`. Un sector que no
# aparece en una fase queda neutro.
SECTORES_POR_FASE: dict[str, dict[str, tuple[str, ...]]] = {
    "recuperacion": {
        "favorecidos": ("Financials", "Consumer Discretionary", "Industrials"),
        "desfavorecidos": ("Utilities", "Consumer Staples", "Health Care"),
    },
    "expansion": {
        "favorecidos": ("Information Technology", "Communication Services", "Industrials"),
        "desfavorecidos": ("Utilities", "Materials"),
    },
    "desaceleracion": {
        "favorecidos": ("Energy", "Materials", "Consumer Staples", "Health Care"),
        "desfavorecidos": ("Information Technology", "Consumer Discretionary"),
    },
    "contraccion": {
        "favorecidos": ("Consumer Staples", "Health Care", "Utilities"),
        "desfavorecidos": ("Industrials", "Information Technology", "Consumer Discretionary"),
    },
}
