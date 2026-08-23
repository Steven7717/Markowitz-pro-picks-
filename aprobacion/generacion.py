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
    """Whether generation can run at all, whether the AI half can, and why not."""

    hay_clave: bool
    hay_identidad: bool

    @property
    def puede_generar(self) -> bool:
        """Whether generation — with or without AI — can run at all.

        EDGAR_IDENTITY is not an AI-half requirement: it is what the SEC
        requires in the User-Agent of *every* request, so it gates fetching
        the fundamentals in the first place. Without it there is nothing to
        download and nothing to rank, AI or not — a previous version of this
        docstring said the opposite, and that is what let "Sin IA" ship as an
        option that actually spends ~25 minutes retrying 503 tickers before
        failing outright (see `fundamentals/fetch.py:_load_one`).
        """
        return self.hay_identidad

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

    @property
    def motivo_generacion(self) -> str | None:
        """Why generation as a whole is blocked, in words the user can act on.

        Distinto de `motivo`: ese explica por qué falta la IA; este explica
        por qué no hay nada que generar, ni siquiera la mitad gratis, porque
        sin EDGAR_IDENTITY no hay descarga posible.
        """
        if self.puede_generar:
            return None
        return (
            "Falta EDGAR_IDENTITY en el entorno. La SEC exige un contacto en "
            "cada petición, así que hace falta también para la mitad sin IA: "
            "sin él no se descarga nada y no hay nada que ordenar."
        )


def disponibilidad(entorno: dict[str, str] | None = None) -> Disponibilidad:
    """Read the two credentials generation needs.

    EDGAR_IDENTITY gates generation as a whole, not just the AI half: the SEC
    requires a contact identifying the requester in the User-Agent of every
    request it receives, so fetching the fundamentals — the part that runs
    with or without AI — needs it just the same. ANTHROPIC_API_KEY only gates
    the AI half on top of that: without it there is no Item 1A to quote from,
    so the model would be asked to cite a document nobody downloaded.
    Offering "with AI" in that state would produce fichas that say they were
    AI-generated and carry no citation — exactly the silent half-result this
    project keeps refusing to ship.
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
