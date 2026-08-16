"""The selection criterion, frozen before any ranking is computed.

Data, not logic: the date of the commit that introduces this file is the proof
that the thresholds did not move once the numbers were visible. Changing it
requires a dated amendment in the design document, never a silent edit.
"""

PILARES: dict[str, tuple[str, ...]] = {
    "calidad": (
        "margen_bruto",
        "margen_operativo",
        "margen_neto",
        "roe",
        "roic",
        "margen_fcf",
        "fcf_sobre_beneficio",
    ),
    "crecimiento": (
        "crecimiento_ingresos",
        "crecimiento_bpa",
        "crecimiento_fcf",
    ),
    "valoracion": (
        "per",
        "ev_ebitda",
        "precio_fcf",
        "precio_valor_libro",
    ),
    "solidez": (
        "deuda_neta_ebitda",
        "cobertura_intereses",
        "razon_corriente",
    ),
}

PESOS: dict[str, float] = {
    "calidad": 0.25,
    "crecimiento": 0.25,
    "valoracion": 0.25,
    "solidez": 0.25,
}

# +1 means higher is better, -1 means higher is worse.
#
# Declared one by one rather than derived from a list of exceptions, so a test
# can assert that all 17 carry a sign. A KPI whose sign was forgotten would
# produce a plausible ranking that is exactly backwards, and nothing about the
# output would look wrong.
SIGNOS: dict[str, int] = {
    "margen_bruto": 1,
    "margen_operativo": 1,
    "margen_neto": 1,
    "roe": 1,
    "roic": 1,
    "margen_fcf": 1,
    "fcf_sobre_beneficio": 1,
    "crecimiento_ingresos": 1,
    "crecimiento_bpa": 1,
    "crecimiento_fcf": 1,
    "razon_corriente": 1,
    "cobertura_intereses": 1,
    "deuda_neta_ebitda": -1,
    "per": -1,
    "ev_ebitda": -1,
    "precio_fcf": -1,
    "precio_valor_libro": -1,
}

# Rationale for each threshold, and the two readings each one deliberately
# excludes, are in the "Umbrales" section of
# docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md
TRIMESTRES_VENTANA = 4
MIN_TRIMESTRES_HISTORIA = 4
MAX_ANTIGUEDAD_TRIMESTRES = 2
MIN_PILARES_CON_DATO = 4
MIN_KPIS_CON_DATO = 8
TOPE_POR_SECTOR = 3
TAMANO_TOP = 15
