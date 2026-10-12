"""El criterio del valor intrínseco, congelado antes de medir nada.

Datos, no lógica. La fecha del commit que introduce este fichero es la prueba de
que ningún listón se movió al ver los veredictos: cambiar cualquiera de estos
valores exige una enmienda fechada en
`docs/superpowers/specs/2026-10-12-valor-intrinseco-design.md`, nunca una edición
silenciosa. El porqué de cada valor está en la tabla de esa sección y no se
repite aquí: dos copias de una justificación se separan igual que dos de un
número.
"""

# Convenciones: toda tupla *_TOPES o *_LIMITES es (bajo, alto) y toda tasa es una
# fracción (0.042 = 4,2 %).

# Viaja dentro de cada valoración guardada, para que una ficha vieja diga con
# qué criterio se calculó.
VERSION = "m1"

# --- Proyección ---------------------------------------------------------------
ANOS_ALTO_CRECIMIENTO = 5
ANOS_CONVERGENCIA = 5

# --- Coste del capital --------------------------------------------------------
PRIMA_RIESGO = 0.0420
PRIMA_RIESGO_FECHA = "2026-10-01"
BETA_SEMANAS = 104
BETA_SEMANAS_MIN = 52
# (pendiente, término independiente): beta ajustada = pendiente * beta + término.
BLUME = (0.67, 0.33)
COSTE_DEUDA_PRIMA_MAXIMA = 0.08
TASA_LEGAL = {"US": 0.21, "MX": 0.30, "otros": 0.24}
TASA_EFECTIVA_TOPES = (0.0, 0.35)

# --- Crecimiento --------------------------------------------------------------
CRECIMIENTO_PERPETUO = {"USD": 0.025, "MXN": 0.035}
CRECIMIENTO_REF_TOPES = (-0.10, 0.40)
CRECIMIENTO_REF_ANOS = 3
HOLGURA_GORDON = 0.01

# --- Votos --------------------------------------------------------------------
MARGEN_MINIMO = 0.05
MARGEN_ROE_MINIMO = 0.03
DELTA_WACC_ESCENARIOS = 0.01
INVERSO_LIMITES = (-0.30, 0.80)
INVERSO_ROE_LIMITES = (-0.20, 0.60)
UMBRAL_PARES = 0.5
MIN_ANOS_HISTORIA = 2
MIN_VOTOS = 2

# --- Beneficio residual -------------------------------------------------------
PAYOUT_SIN_DATO = 0.5

# Cadenas exactas de `info["industry"]` de Yahoo, sondeadas el 2026-10-12, con AXS
# y FAF para Insurance - Specialty.
# Fuera a propósito: Credit Services (Visa, Mastercard, PayPal), Insurance
# Brokers y Asset Management, cuyo flujo de caja sí significa algo.
INDUSTRIAS_FINANCIERAS = frozenset(
    {
        "Banks - Diversified",
        "Banks - Regional",
        "Insurance - Life",
        "Insurance - Property & Casualty",
        "Insurance - Diversified",
        "Insurance - Reinsurance",
        "Insurance - Specialty",
        "Capital Markets",
        "Mortgage Finance",
    }
)
