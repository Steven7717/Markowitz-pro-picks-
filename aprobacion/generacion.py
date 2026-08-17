"""Qué se puede generar desde la interfaz, y a qué coste.

Vive aquí y no en la página por la misma razón que el resto de `aprobacion/`:
son decisiones —si la IA está disponible, qué se va a gastar, qué se va a
sobrescribir— y las decisiones se prueban sin arrancar Streamlit.
"""

import os
from dataclasses import dataclass

# Medido con count_tokens contra la API real el 2026-08-16, no estimado: el
# peor caso son 24.231 tokens de entrada por ficha (ver la enmienda 4 del
# diseño de B). Quince fichas con su salida, a la tarifa estándar de Sonnet 5,
# salen por algo más de un dólar. Se redondea hacia arriba a propósito: quien
# lee esto está a punto de decidir si gastar, y una estimación optimista en ese
# sitio es peor que no dar ninguna.
COSTE_APROXIMADO_USD = 1.25


@dataclass(frozen=True)
class Disponibilidad:
    """Whether the AI half can run at all, and why not when it cannot."""

    hay_clave: bool
    hay_identidad: bool

    @property
    def puede_usar_ia(self) -> bool:
        return self.hay_clave and self.hay_identidad

    @property
    def motivo(self) -> str | None:
        """Why the AI option is unavailable, in words the user can act on."""
        if self.puede_usar_ia:
            return None
        faltan = []
        if not self.hay_clave:
            faltan.append("ANTHROPIC_API_KEY")
        if not self.hay_identidad:
            faltan.append("EDGAR_IDENTITY")
        return (
            f"Falta {' y '.join(faltan)} en el entorno. Sin eso el ranking se "
            "genera igual, pero las fichas salen de plantilla y sin narrativa."
        )


def disponibilidad(entorno: dict[str, str] | None = None) -> Disponibilidad:
    """Read the two credentials the AI half needs.

    EDGAR_IDENTITY counts as much as the API key: without it there is no Item
    1A to quote from, so the model would be asked to cite a document nobody
    downloaded. Offering "with AI" in that state would produce fichas that say
    they were AI-generated and carry no citation — exactly the silent
    half-result this project keeps refusing to ship.
    """
    entorno = os.environ if entorno is None else entorno
    return Disponibilidad(
        hay_clave=bool(entorno.get("ANTHROPIC_API_KEY")),
        hay_identidad=bool(entorno.get("EDGAR_IDENTITY")),
    )


def hay_revision_en_curso(aprobados: set[str], anadidos: list) -> bool:
    """Whether regenerating would throw away work the reviewer already did.

    Regenerating overwrites salidas/, which is what the page is currently
    showing. Any ticked checkbox or hand-added company refers to a list that
    is about to stop existing — and the checkboxes would survive the rerun
    keyed by ticker, silently pointing at whatever company now sits there.
    """
    return bool(aprobados) or bool(anadidos)
