"""Qué se puede generar desde la interfaz, y a qué coste.

Vive aquí y no en la página por la misma razón que el resto de `aprobacion/`:
son decisiones —si la IA está disponible, qué se va a gastar, qué se va a
sobrescribir— y las decisiones se prueban sin arrancar Streamlit.
"""

import os
from dataclasses import dataclass

from ranking import llm
from ranking.criterio import TAMANO_TOP
from ranking.filings import CARACTERES_POR_TOKEN

# Medido con count_tokens contra la API real el 2026-08-16, no estimado: el
# peor caso son 24.231 tokens de entrada por ficha (ver la enmienda 4 del
# diseño de B).
TOKENS_POR_FICHA = 24_231

# El ratio se **importa** de `ranking/filings.py`, que es donde se midió.
#
# Aquí había un 4 escrito a mano, justificado con que «cuatro caracteres por
# token es lo que sale en prosa legal en inglés, que es exactamente lo que se
# manda» — y el fichero que produce ese mismo texto lo midió con count_tokens
# contra la API y le salió 3,30, con la nota de que «la regla de tres se
# quedaba corta en un 21%». La estimación estaba escrita al lado de la medida y
# no la había leído. `vistas/panel_ia.py` llevaba la tercera copia del mismo 4.
#
# El test que ataba la cifra anunciada al peor caso pasaba igual, porque los
# dos lados de la comparación usaban el número malo: un ratio equivocado no
# rompe una igualdad consigo mismo.

# Lo que se anuncia antes de pulsar. **Es el peor caso, no el caso típico.**
#
# Decía 1,25 $ mientras el peor caso medido eran 2,13 $ — un 70 % más de lo
# anunciado, en la única pantalla del programa donde una cifra decide si se
# gasta o no. Y el peor caso no era mala suerte: el reintento lo dispara de
# forma determinista un filing hostil, que sólo tiene que inducir un dígito en
# la afirmación o una cita que no verifique. El texto de un tercero decidía el
# gasto del usuario por un factor de dos.
#
# Ahora el reintento ya no reenvía los ochenta mil caracteres del filing (ver
# `ranking/llm.py:MAX_CARACTERES_REINTENTO`) y el peor caso baja a 1,57 $. Se
# anuncia 1,60: redondeado hacia arriba a propósito, como antes — quien lee
# esto está a punto de decidir si gastar, y una estimación optimista en ese
# sitio es peor que no dar ninguna.
#
# Decía 1,55 hasta que el ratio de arriba pasó a ser el medido en vez del
# supuesto. Con 3,30 caracteres por token el mismo recorte del filing son más
# tokens, el peor caso sube a 1,5687 $ y el 1,55 anunciado se quedaba **por
# debajo** — que es el lado caro del error, justo el defecto que esta constante
# existe para no repetir.
#
# Hay un test que lo ata a `coste_peor_caso()` por los dos lados: ni por debajo
# del peor caso, ni tan por encima que deje de servir para decidir.
COSTE_APROXIMADO_USD = 1.60


def coste_peor_caso(fichas: int = TAMANO_TOP) -> float:
    """Lo más que puede costar una corrida con IA: todas las fichas reintentadas.

    No es una estimación prudente inventada: sale de las constantes que de
    verdad producen el gasto —el tamaño medido del turno de usuario, lo que el
    reintento reenvía, y `MAX_TOKENS`, que es el techo duro de cada respuesta—.
    Por eso vive aquí como función y no como un número escrito a mano: quien
    cambie la política de reintento en `ranking/llm.py` mueve esto con ella, y
    el test que compara la cifra anunciada contra esta función se lo dice.

    El peor caso es «todas reintentan» y no «alguna reintenta» porque el
    disparador no es aleatorio: si un filing hostil puede forzar un reintento,
    quince filings hostiles pueden forzar quince.
    """
    entrada_reintento = (
        int(llm.MAX_CARACTERES_REINTENTO / CARACTERES_POR_TOKEN)
        # El eco de la respuesta anterior, que el reintento sí sigue mandando:
        # enseñarle al modelo su propio turno es lo que le permite corregirlo.
        + llm.MAX_TOKENS
    )
    entrada = fichas * (TOKENS_POR_FICHA + entrada_reintento)
    salida = fichas * 2 * llm.MAX_TOKENS
    return (entrada * llm.PRECIO_ENTRADA + salida * llm.PRECIO_SALIDA) / 1_000_000


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
        option that actually aborts on the very first ticker: a rejected
        identity is `systemic` (`fundamentals/fallos.py:clasificar`), so
        `load_facts` raises `CorridaAbortada` with the cause instead of working
        through all 503 tickers to reach the same conclusion (see
        `fundamentals/fetch.py:_load_one`).
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
