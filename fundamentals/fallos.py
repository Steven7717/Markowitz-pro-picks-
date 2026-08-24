"""De qué clase es un fallo de descarga, y si tiene sentido seguir pidiendo.

Vive aparte de `fetch.py` por la misma razón que `concepts.py` vive aparte: es
una tabla de decisiones, sin red y sin pandas, y se prueba renglón por renglón.

La taxonomía no se inventa aquí. La pone `edgar.exceptions`, que distingue por
tipo lo que si no habría que adivinar leyendo códigos HTTP: `SECIdentityError`
para la identidad que la SEC rechaza, `CompanyFactsNotFoundError` para la
empresa que existe y no tiene datos. Este módulo sólo traduce esos tipos a las
tres preguntas que `load_facts` necesita responder: en qué casilla del informe
va el ticker, si hay que abortar ya, y si cuenta como prueba de que la fuente
no está.
"""

from dataclasses import dataclass

# Las dos primeras conservan el nombre de la casilla que ya existía en
# CoverageReport, para que el informe no cambie de vocabulario a mitad.
UNRESOLVED_CIK = "unresolved_cik"
NO_FACTS = "no_facts"
TRANSIENT = "transient"
SYSTEMIC = "systemic"
UNKNOWN = "unknown"

_IDENTIDAD = (
    "La SEC no aceptó la identidad con la que se piden los datos. Exige un "
    "contacto real en la cabecera de cada petición: revisa el correo de EDGAR "
    "en el apartado de credenciales y vuelve a intentarlo."
)
_RATE_LIMIT = (
    "La SEC ha bloqueado tu IP por exceder su límite de peticiones. El bloqueo "
    "dura unos 10 minutos y seguir pidiendo lo alarga, así que la corrida se "
    "para aquí. Espera ese rato y vuelve a darle a Generar: lo ya descargado "
    "está en caché y no se vuelve a bajar."
)
_SSL = (
    "No se pudo verificar el certificado de la SEC. Suele pasar detrás de una "
    "VPN o de un antivirus que inspecciona el tráfico. Prueba en otra red, o "
    "excluye data.sec.gov de esa inspección."
)


def _rechazo(codigo: int) -> str:
    return (
        f"La SEC ha rechazado la petición (HTTP {codigo}). No es un problema de "
        "una empresa concreta: la misma petición va a fallar para todas, así "
        "que la corrida se para aquí."
    )


@dataclass(frozen=True)
class Fallo:
    """Un fallo ya clasificado: dónde se anota y qué implica para la corrida."""

    causa: str
    detalle: str
    explicacion: str = ""

    @property
    def aborta(self) -> bool:
        """Si por sí solo condena la corrida, sin esperar a que se repita."""
        return self.causa == SYSTEMIC

    @property
    def hubo_respuesta(self) -> bool:
        """Si la SEC llegó a contestar, aunque fuera para decir que no hay datos.

        Un `no_facts` exigió una respuesta de data.sec.gov, así que es prueba de
        que la fuente está viva: reinicia la racha igual que un acierto.
        """
        return self.causa == NO_FACTS

    @property
    def cuenta_racha(self) -> bool:
        """Si preguntamos y no hubo respuesta. Es lo único que avanza la racha.

        Un `unresolved_cik` no cuenta: se resuelve contra el parquet que
        edgartools trae empaquetado, sin pedirle nada a la SEC, así que no dice
        nada sobre si la fuente está. Ni la avanza ni la reinicia.
        """
        return self.causa in (TRANSIENT, UNKNOWN)


def clasificar(exc: BaseException) -> Fallo:
    """De qué clase es este fallo.

    El orden de las comprobaciones no es opcional, y hay dos razones distintas:

    - `CompanyFactsNotFoundError` hereda de `CompanyNotFoundError`, así que
      puesta después se clasificaría como «sin CIK».
    - `IdentityError`, `TooManyRequestsError` y `SSLVerificationError` son todas
      `TransportError`, así que puestas después del renglón genérico de
      transporte se clasificarían como transitorias — y se reintentarían las
      tres cosas que no mejoran reintentando.

    Se importa dentro de la función, como hace `fetch.py` con `Company`: mantiene
    el coste de importar edgartools fuera del arranque de la app.
    """
    from edgar.exceptions import (
        CompanyFactsNotFoundError,
        IdentityError,
        NotFoundError,
        TooManyRequestsError,
        http_status,
    )
    from edgar.httprequests import TRANSPORT_ERRORS, SSLVerificationError

    detalle = type(exc).__name__

    if isinstance(exc, CompanyFactsNotFoundError):
        return Fallo(NO_FACTS, detalle)
    # NotFoundError y no LookupError a secas: KeyError también es LookupError, y
    # un fallo de pandas acabaría contado como un ticker sin CIK.
    if isinstance(exc, NotFoundError):
        return Fallo(UNRESOLVED_CIK, detalle)
    if isinstance(exc, IdentityError):
        return Fallo(SYSTEMIC, detalle, _IDENTIDAD)
    if isinstance(exc, TooManyRequestsError):
        return Fallo(SYSTEMIC, detalle, _RATE_LIMIT)
    if isinstance(exc, SSLVerificationError):
        return Fallo(SYSTEMIC, detalle, _SSL)
    if isinstance(exc, TRANSPORT_ERRORS):
        # http_status devuelve None cuando no llegamos a preguntar (timeout,
        # conexión rechazada) y el código cuando la SEC sí contestó.
        codigo = http_status(exc)
        if codigo is None:
            return Fallo(TRANSIENT, detalle)
        if 400 <= codigo < 500:
            return Fallo(SYSTEMIC, f"HTTP {codigo}", _rechazo(codigo))
        return Fallo(TRANSIENT, f"HTTP {codigo}")
    return Fallo(UNKNOWN, detalle)
