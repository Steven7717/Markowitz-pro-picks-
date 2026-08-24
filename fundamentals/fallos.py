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
# CoverageReport, para que el informe no cambie de vocabulario a mitad. Las
# otras tres — transient, systemic, unknown — no tienen casilla propia ahí:
# las tres colapsan en failed_download.
UNRESOLVED_CIK = "unresolved_cik"
NO_FACTS = "no_facts"
TRANSIENT = "transient"
SYSTEMIC = "systemic"
UNKNOWN = "unknown"

CAUSAS = (UNRESOLVED_CIK, NO_FACTS, TRANSIENT, SYSTEMIC, UNKNOWN)

_IDENTIDAD = (
    "La SEC no aceptó la identidad con la que se piden los datos. Exige un "
    "contacto real en la cabecera de cada petición: revisa que el correo de "
    "EDGAR en el apartado de credenciales sea una dirección completa y válida."
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


# _IDENTIDAD es el diagnóstico que ya nos da IdentityError: la librería
# comprobó la identidad del lado del cliente (edgar/exceptions.py:316, sin
# enviar petición) y sabe que la causa es esa y ninguna otra, así que el
# mensaje puede ser directo. Un 401/403 es distinto: inferimos la causa desde
# un código HTTP que también puede significar «has pedido demasiado seguido»,
# así que sólo esta versión lleva ese matiz — ofrecerlo en la de IdentityError
# sería un remedio que no puede funcionar cuando la causa ya está confirmada
# y no hay petición que espaciar.
def _rechazo_identidad(codigo: int) -> str:
    return (
        f"La SEC ha rechazado la identidad con la que se piden los datos "
        f"(HTTP {codigo}). Revisa que el correo de EDGAR en el apartado de "
        "credenciales sea una dirección completa y válida. Si el correo es "
        "correcto, la otra causa habitual de un rechazo así es haber pedido "
        "demasiado seguido; espera unos minutos y reinténtalo."
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
    def fuente_viva(self) -> bool:
        """Si este fallo prueba que data.sec.gov está sirviendo datos.

        Sólo un `no_facts` lo prueba: para saber que una CIK no tiene hechos hubo
        que preguntarlo y recibir un 404. Esto sólo es cierto porque
        `fetch.py:_fetch_facts` llama a `edgar.get_company_facts(cik)`
        directamente, que levanta `CompanyFactsNotFoundError` para el 404 real;
        la ruta por `Entity.get_facts()` traga ese 404 en un `None`
        indistinguible de una descarga fallida, y por ahí esta propiedad
        también saldría verdadera para un fallo de red. Reinicia la racha
        igual que un acierto.

        Un 5xx no cuenta, aunque técnicamente sea una respuesta: la SEC diciendo
        «estoy rota» diez veces seguidas es exactamente el caso para el que
        existe el cortacircuitos. Por eso la propiedad se llama así y no
        `hubo_respuesta` — con ese nombre, un 503 devolvería False y el nombre
        estaría mintiendo.
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

    - `CompanyFactsNotFoundError` hereda de `NotFoundError`, así que puesta
      después se clasificaría como «sin CIK» y el informe contaría mal.
    - `IdentityError` y `SSLVerificationError` son `TransportError` sin código
      HTTP, así que puestas después del renglón genérico de transporte saldrían
      transitorias — y se reintentarían dos cosas que no mejoran reintentando.

    `TooManyRequestsError` no necesita ese argumento: lleva `status_code=429`, así
    que el renglón de 4xx ya lo declararía sistémico. Su fila está por el mensaje
    que lleva, no por la clasificación.

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
        if codigo in (401, 403):
            # El caso que motivó todo esto llega por aquí, no por IdentityError:
            # SECIdentityError sólo la levanta el parser de SGML
            # (edgar/sgml/sgml_parser.py:195), que es el camino de los filings.
            # La API de facts convierte el 404 en CompanyFactsNotFoundError y
            # deja pasar lo demás como httpx crudo, así que una identidad que
            # EDGAR rechaza aterriza aquí como un 401/403 pelado, no como
            # IdentityError — de ahí que el mensaje sea _rechazo_identidad
            # (con matiz y código) y no el _IDENTIDAD directo.
            return Fallo(SYSTEMIC, f"HTTP {codigo}", _rechazo_identidad(codigo))
        if 400 <= codigo < 500:
            return Fallo(SYSTEMIC, f"HTTP {codigo}", _rechazo(codigo))
        return Fallo(TRANSIENT, f"HTTP {codigo}")
    return Fallo(UNKNOWN, detalle)
