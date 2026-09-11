# interprete/documentos.py
"""El texto de un 8-K, que el indice no trae.

H nunca abre un expediente --a proposito: abrir quince al pintar la pantalla la
convertia en una espera--, asi que un `Hecho` llega con codigos y con etiquetas
del propio programa, y **ni una palabra de la empresa**. Interpretar eso solo
puede repetir la etiqueta que ya esta en pantalla o inventarse el documento.

Medido contra EDGAR el 2026-09-10, seis empresas:

- El cuerpo del 2.02 de MSFT son 3.579 caracteres, de los que ~3.100 son
  caratula de la SEC. Su unico contenido es una frase de reenvio al anexo.
- El `EX-99.1` de ese mismo expediente tiene 52.823 caracteres y es la nota de
  prensa entera. Se baja en 0,46 s.
- De 17 expedientes materiales, 13 traen `EX-99`. Los 4 que no son `5.02`, y
  ahi el cuerpo si lleva la sustancia.

De ahi la regla: **el anexo si lo hay, el cuerpo recortado si no.**
"""

import os
import re
from dataclasses import dataclass

# Seis hechos por 30.000 son ~180.000 caracteres, ~48k tokens: el techo duro de
# una pulsacion. Los tamanos medidos van de 3.037 a 112.913, media 28.291, asi
# que el tope muerde justo en los `2.02` grandes y no toca a los `5.02`.
TOPE_CARACTERES = 30_000

# `\s+` y no un espacio literal: MSFT separa el «Item» de su numero con un
# espacio fino U+2009 --escrito «Item\u20095.02»-- y no con uno normal. Se
# nombra el punto de codigo en vez de ponerlo aqui: un caracter invisible
# dentro del comentario que existe para senalarlo no lo ensena, y se pierde
# en cualquier copia-pega. Eso ultimo ya paso al transcribir esta tarea.
# Un literal " " se lo salta y devuelve el documento entero -- un fallo que no
# revienta, solo encarece y llena el prompt de caratula.
_ITEM = re.compile(r"\bItem\s+\d\.\d\d", re.IGNORECASE)
_FIRMA = re.compile(r"\bSIGNATURES?\b", re.IGNORECASE)

# Lo que `noticias/hechos.py:_url` escribe, leido al reves. El numero de acceso
# va sin guiones en la url y son siempre 18 digitos, 10-2-6.
_URL = re.compile(
    r"^https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d{18})/"
)


@dataclass(frozen=True)
class Documento:
    """El texto listo para mandarse, y **el problema como texto**.

    Misma forma que `noticias/fuentes.py:Traida`, y por la misma razon: esto no
    lanza. Que se caiga la pantalla entera por un expediente que no responde es
    peor que ensenar los otros cinco y decir cual fallo.
    """

    texto: str
    recortado: bool
    problema: str


def identificadores(url: str) -> "tuple[int, str] | None":
    """El CIK y el numero de acceso, sacados de la url del `Hecho`.

    **Esto ata este modulo a `noticias/hechos.py:_url`.** Si alguien cambia el
    formato de esa url, esto deja de encontrar nada y no revienta: los hechos
    caerian en `sin_documento` como si fuera un fallo de red. Hay un test que
    construye la url con `hechos._url` y afirma la vuelta.

    Se parsea en vez de anadir `accession` a `Hecho` porque eso cambiaria la
    dataclase de H y el formato de su cache, que hoy tiene entradas escritas.
    """
    encontrado = _URL.match(url)
    if encontrado is None:
        return None
    cik, limpio = encontrado.groups()
    accession = f"{limpio[:10]}-{limpio[10:12]}-{limpio[12:]}"
    return int(cik), accession


def recortar(cuerpo: str) -> str:
    """Del primer `Item N.NN` hasta `SIGNATURE`, que es donde dice algo.

    Medido: 3.291 -> 761, 6.465 -> 2.693, 7.162 -> 2.798, 10.167 -> 7.539.
    Entre un 25% y un 80% menos, y lo que queda empieza justo en el `Item`.

    **Si falta cualquiera de las dos marcas se devuelve el cuerpo entero.** De
    las dos formas de equivocarse, mandar caratula de mas es cara y mandar el
    contenido de menos es mentir: un recorte que falla no puede llevarse la
    noticia por delante.
    """
    item = _ITEM.search(cuerpo)
    firma = _FIRMA.search(cuerpo)
    if item is None or firma is None or firma.start() <= item.start():
        return cuerpo
    return cuerpo[item.start():firma.start()]


def elegir(cuerpo: str, anexos: "list[str]") -> str:
    """El anexo si lo hay, el cuerpo recortado si no."""
    if anexos:
        return "\n\n".join(anexos)
    return recortar(cuerpo)


def aplicar_tope(texto: str, tope: int = TOPE_CARACTERES) -> "tuple[str, bool]":
    """Cortar por el final, y decir si se corto.

    Por el final y no por el principio: una nota de prensa pone el titular y las
    cifras arriba, asi que la cola es lo prescindible. Y se **dice**, porque un
    recorte silencioso es indistinguible de que no hubiera mas.
    """
    if len(texto) <= tope:
        return texto, False
    cortado = texto[:tope]
    # Retroceder hasta un limite limpio. Lo que sale de aqui es contra lo que
    # despues se verifica una cita caracter a caracter, y un corte a mitad de
    # palabra hace que una cita legitima que cruce el corte se rechace --por el
    # corte, no por invencion--. Medido con el EX-99.1 de MSFT: a 30.000
    # caracteres el texto acababa en «...any forward» y lo que se perdia
    # empezaba por «-looking».
    #
    # Se prueba primero el salto de parrafo y despues el espacio, y si no hay
    # ninguno de los dos se deja el corte duro: un texto de treinta mil
    # caracteres sin un solo espacio no es prosa, y devolver cadena vacia seria
    # peor que devolver un trozo.
    for separador in ("\n\n", " "):
        limite = cortado.rfind(separador)
        if limite > 0:
            return cortado[:limite], True
    return cortado, True


def texto_de(url: str, buscar=None, tope: int = TOPE_CARACTERES) -> Documento:
    """El texto de un expediente, listo para el prompt.

    `buscar` se inyecta para las pruebas; por defecto es `edgar.find`, que
    recupera un expediente por su numero de acceso en ~0,8 s (medido).

    La guarda de `EDGAR_IDENTITY` esta aqui y no solo en `noticias/fuentes.py`
    porque este camino no pasa por alli: es una segunda puerta a la SEC.
    """
    if not os.environ.get("EDGAR_IDENTITY"):
        return Documento(
            "",
            False,
            "Falta EDGAR_IDENTITY. La SEC exige un contacto en el User-Agent: "
            "EDGAR_IDENTITY='tu@correo.com'.",
        )

    ids = identificadores(url)
    if ids is None:
        return Documento("", False, f"La url no tiene forma de expediente: {url}")

    if buscar is None:
        import edgar

        buscar = edgar.find

    try:
        expediente = buscar(ids[1])
        # `adjunto.text()` devuelve `None` para lo que no es texto --un `.pdf`,
        # por ejemplo--, y un expediente puede traer el mismo material en dos
        # formatos: Axos Financial (2026-08-06, 0001299709-26-000056) publica su
        # presentacion como `EX-99.1` en htm **y** `EX-99.2` en pdf. Sin este
        # filtro, el `None` del pdf reventaba el `join` de `elegir`, el
        # `except Exception` lo convertia en `problema`, y los 15.210 caracteres
        # buenos del htm se tiraban con un mensaje que echaba la culpa a la SEC.
        anexos = []
        for adjunto in expediente.attachments:
            if not str(getattr(adjunto, "document_type", "")).startswith("EX-99"):
                continue
            cuerpo_anexo = adjunto.text()
            if cuerpo_anexo:
                anexos.append(cuerpo_anexo)
        crudo = elegir(expediente.text(), anexos)
    except Exception as error:  # la red falla de mil formas y ninguna es del programa
        return Documento("", False, f"{ids[1]}: {error}")

    texto, recortado = aplicar_tope(crudo, tope)
    return Documento(texto, recortado, "")
