"""Los riesgos y el informe de gestión (MD&A) del último informe anual en EDGAR.

Es lo que leen dos de los bloques de IA del Analizador: la tesis cita los
riesgos, y el contraste cita el MD&A. Las dos secciones salen del mismo
expediente, así que se bajan juntas y se guardan un día.

Las reglas salen del sondeo del 2026-11-15 (ver el plan de N3):

- **Una sección corta es una remisión, no la sección.** El Item 7 de PGR y de
  WFC son unos cientos de caracteres que dicen «incorporado por referencia».
- **El MD&A incorporado por referencia se busca en el anexo EX-13**, por su
  encabezado al principio de una línea. Si no está, no se localiza y se dice:
  nunca se manda otra sección haciéndola pasar por MD&A.
- **En un 20-F, edgartools da como riesgos el Item 3 entero**: se corta desde
  la línea «Risk Factors».
- **Un 40-F no tiene secciones que citar.**

Los riesgos de un 10-K salen idénticos a los de `ranking.filings.cargar_riesgos`
—la sección entera cortada a `filings.MAX_CARACTERES`—, y por eso la ficha que
candidatos ya pagó sale de la caché por contenido de `ranking.llm`.
"""

import os
import re
from dataclasses import dataclass
from datetime import timedelta

from analizador import resolver
from interprete import documentos
from noticias import cache
from ranking import filings

MAX_RIESGOS = filings.MAX_CARACTERES
# El MD&A de MU, VEEV, SNDK y TSM mide entre 37.000 y 46.000 caracteres: caben
# enteros. El de JPM, 414.000: se corta, y se dice.
TOPE_MDNA = 60_000
MINIMO_SECCION = 5_000
VALIDEZ = timedelta(days=1)
CON_SECCIONES = ("10-K", "20-F")
RAIZ_CACHE = resolver.RAIZ_CACHE

# El encabezado tiene que caer cerca del principio de la sección para contar
# como su principio: MU lo trae tras «Table of Contents» y JPM tras una tabla
# de cifras, en el carácter 5.549.
_BUSCAR_EN = 10_000
# `[^\S\n]` es un blanco que no es salto de línea: VEEV separa con U+00A0 y TSM
# con U+2009. El apóstrofo de «Management’s» es tipográfico en unos y recto en
# otros, de ahí el punto.
_MDNA = re.compile(
    r"^[^\S\n]*(?:item\s*7\.?\s*)?management.s discussion and analysis",
    re.IGNORECASE | re.MULTILINE,
)
_RIESGOS = re.compile(
    r"^[^\S\n]*(?:d\.[^\S\n]*)?risk factors[^\S\n]*$", re.IGNORECASE | re.MULTILINE
)
# Una línea que acaba en un número de página (con o sin puntos de relleno) es de
# un índice; un encabezado, en cambio, va con una línea en blanco por encima.
_PAGINA = re.compile(r"\d+[^\S\n]*$")
_BLANCO_ANTES = re.compile(r"\n[^\S\n]*\n$")
# Una remisión a otro documento: «reference is made», «incorporated by reference».
_REMISION = re.compile(r"reference\s+is\s+made|incorporated\s+by\s+reference", re.IGNORECASE)
_VENTANA_REMISION = 600
_NOMBRES = {"10-K": ("Item 1A", "Item 7"), "20-F": ("Item 3.D", "Item 5")}


@dataclass(frozen=True)
class Seccion:
    """Una sección tal como se manda al modelo, con lo que se dejó fuera."""

    nombre: str
    texto: str
    caracteres_totales: int
    recortado: bool


@dataclass(frozen=True)
class Informe:
    """El último informe anual. Una sección que no se localizó es `None`."""

    ticker: str
    formulario: str
    fecha: str
    accession: str
    riesgos: "Seccion | None"
    mdna: "Seccion | None"


def _desde(texto: str, patron, dentro_de: "int | None" = None) -> "str | None":
    hallado = patron.search(texto)
    if hallado is None or (dentro_de is not None and hallado.start() > dentro_de):
        return None
    return texto[hallado.start():]


def _remite(cuerpo: str) -> bool:
    """Si al principio del cuerpo dice que la sección está en otro documento."""
    return _REMISION.search(cuerpo[:_VENTANA_REMISION]) is not None


def riesgos_10k(seccion: "str | None") -> "str | None":
    """El Item 1A entero, o `None` si es una remisión."""
    if not seccion or len(seccion) < MINIMO_SECCION or _remite(seccion):
        return None
    return seccion


def riesgos_20f(item3: "str | None") -> "str | None":
    """El apartado de riesgos del Item 3, desde su línea de encabezado."""
    if not item3:
        return None
    cortado = _desde(item3, _RIESGOS)
    if cortado is None or len(cortado) < MINIMO_SECCION:
        return None
    # El cuerpo empieza tras la línea de encabezado.
    return None if _remite(cortado.partition("\n")[2]) else cortado


def _desde_encabezado_de_anexo(anexo: str) -> "str | None":
    """Desde el primer encabezado del MD&A del anexo que no sea un índice ni una mención.

    Cuenta la coincidencia que va tras una línea en blanco (o al principio) y
    cuya línea no acaba en un número de página.
    """
    for hallado in _MDNA.finditer(anexo):
        antes = anexo[: hallado.start()]
        if antes.strip() and not _BLANCO_ANTES.search(antes):
            continue
        fin = anexo.find("\n", hallado.end())
        linea = anexo[hallado.start(): len(anexo) if fin == -1 else fin]
        if _PAGINA.search(linea):
            continue
        cortado = anexo[hallado.start():]
        if len(cortado) >= MINIMO_SECCION:
            return cortado
    return None


def mdna(seccion: "str | None", anexos: "list[str]") -> "tuple[str | None, str]":
    """El MD&A y de dónde sale: `"informe"`, `"ex_13"` o `""` si no se localizó."""
    if seccion and len(seccion) >= MINIMO_SECCION:
        return (_desde(seccion, _MDNA, _BUSCAR_EN) or seccion), "informe"
    for anexo in sorted((a for a in anexos if a), key=len, reverse=True):
        cortado = _desde_encabezado_de_anexo(anexo)
        if cortado is not None:
            return cortado, "ex_13"
    return None, ""


def componer(ticker: str, crudo: dict) -> Informe:
    """El `Informe` desde lo que devolvió `_descargar`. Aritmética de textos, sin red."""
    formulario = crudo["formulario"]
    nombre_riesgos, nombre_mdna = _NOMBRES[formulario]
    cortar = riesgos_10k if formulario == "10-K" else riesgos_20f
    riesgos = cortar(crudo.get("riesgos"))
    texto_mdna, origen = mdna(crudo.get("mdna"), crudo.get("anexos_13") or [])
    seccion_mdna = None
    if texto_mdna is not None:
        cortado, recortado = documentos.aplicar_tope(texto_mdna, TOPE_MDNA)
        seccion_mdna = Seccion(
            nombre_mdna if origen == "informe" else "EX-13", cortado, len(texto_mdna), recortado
        )
    return Informe(
        ticker,
        formulario,
        crudo["fecha"],
        crudo["accession"],
        None
        if riesgos is None
        else Seccion(nombre_riesgos, riesgos[:MAX_RIESGOS], len(riesgos), len(riesgos) > MAX_RIESGOS),
        seccion_mdna,
    )


def _texto(valor: object) -> "str | None":
    return valor if isinstance(valor, str) and valor else None


def _descargar(ticker: str, formulario: str) -> "dict | None":
    """El último informe de ese formulario: sus dos secciones y, si hacen falta, los EX-13.

    `{}` si la empresa no tiene ninguno, que es un hecho; `None` si no se pudo
    saber. Aislada para los tests. Sin enmiendas: un 10-K/A no es el informe.
    """
    from edgar import Company

    try:
        todas = Company(ticker).get_filings(form=formulario, amendments=False)
        presentacion = todas.latest() if todas is not None and len(todas) else None
        if presentacion is None:
            return {}
        objeto = presentacion.obj()
        riesgos = _texto(getattr(objeto, "risk_factors", None))
        seccion = _texto(getattr(objeto, "management_discussion", None))
        anexos = []
        if formulario == "10-K" and not (seccion and len(seccion) >= MINIMO_SECCION):
            for adjunto in presentacion.attachments:
                if str(getattr(adjunto, "document_type", "")).startswith("EX-13"):
                    cuerpo = _texto(adjunto.text())
                    if cuerpo:
                        anexos.append(cuerpo)
        return {
            "formulario": formulario,
            "fecha": str(presentacion.filing_date),
            "accession": presentacion.accession_no,
            "riesgos": riesgos,
            "mdna": seccion,
            "anexos_13": anexos,
        }
    except Exception:
        # edgartools lanza de todo según qué falle, y aquí sólo importa que no
        # se supo: es la política de `resolver._consultar_sec`.
        return None


def _seccion_a_dict(seccion: "Seccion | None") -> "dict | None":
    if seccion is None:
        return None
    return {
        "nombre": seccion.nombre,
        "texto": seccion.texto,
        "caracteres_totales": seccion.caracteres_totales,
        "recortado": seccion.recortado,
    }


def _a_dict(informe: Informe) -> dict:
    return {
        "ticker": informe.ticker,
        "formulario": informe.formulario,
        "fecha": informe.fecha,
        "accession": informe.accession,
        "riesgos": _seccion_a_dict(informe.riesgos),
        "mdna": _seccion_a_dict(informe.mdna),
    }


def _de_dict(datos: object) -> "Informe | None":
    """Lo guardado como `Informe`, o `None` si no lo es: una caché se regenera."""
    try:
        secciones = {
            clave: None if datos[clave] is None else Seccion(
                str(datos[clave]["nombre"]),
                str(datos[clave]["texto"]),
                int(datos[clave]["caracteres_totales"]),
                bool(datos[clave]["recortado"]),
            )
            for clave in ("riesgos", "mdna")
        }
        return Informe(
            str(datos["ticker"]), str(datos["formulario"]), str(datos["fecha"]),
            str(datos["accession"]), secciones["riesgos"], secciones["mdna"],
        )
    except (KeyError, TypeError, ValueError):
        return None


def _hay_identidad() -> bool:
    return bool((os.environ.get("EDGAR_IDENTITY") or "").strip())


def cargar(ticker: str, formulario: str) -> "tuple[Informe | None, str]":
    """El último informe anual con sus secciones, de la caché si vale y si no de la red.

    Los motivos son claves: `ok`, `sin_secciones` (un 40-F), `sin_identidad_edgar`,
    `sin_red_edgar` y `sin_informe`. Sin red se sirve lo guardado, tenga la edad
    que tenga: su fecha va en el propio informe.
    """
    if formulario not in CON_SECCIONES:
        return None, "sin_secciones"
    if not _hay_identidad():
        return None, "sin_identidad_edgar"
    guardado = cache.leer(RAIZ_CACHE, "informe_anual", ticker, VALIDEZ)
    previo = None if guardado is None else _de_dict(guardado.datos)
    if previo is not None and previo.formulario != formulario:
        previo = None
    if previo is not None and guardado.vigente:
        return previo, "ok"
    crudo = _descargar(ticker, formulario)
    if crudo is None:
        return (previo, "ok") if previo is not None else (None, "sin_red_edgar")
    if not crudo:
        return None, "sin_informe"
    informe = componer(ticker, crudo)
    try:
        cache.guardar(RAIZ_CACHE, "informe_anual", ticker, _a_dict(informe))
    except OSError:
        pass
    return informe, "ok"


def formulario_de(ticker: str) -> "str | None":
    """Qué informe anual presenta el ticker, con la caché de `resolver`."""
    formularios, _motivo = resolver.formularios_sec(ticker)
    return formularios[0] if formularios else None


def _consultar_ultimo(ticker: str, formulario: str) -> "tuple[str, str] | None":
    """`(accession, fecha)` del último informe, en una sola petición si está en la ventana reciente."""
    from edgar import Company

    try:
        empresa = Company(ticker)
        recientes = empresa.get_filings(form=formulario, amendments=False, trigger_full_load=False)
        ultimo = recientes.latest() if recientes is not None and len(recientes) else None
        if ultimo is None:
            todas = empresa.get_filings(form=formulario, amendments=False)
            ultimo = todas.latest() if todas is not None and len(todas) else None
    except Exception:
        return None
    return None if ultimo is None else (ultimo.accession_no, str(ultimo.filing_date))


def ultimo_presentado(ticker: str, formulario: str) -> "tuple[str, str] | None":
    """`(accession, fecha)` del último informe anual, o `None` si no se sabe.

    Es lo que dice si una lectura guardada se quedó vieja. Se pregunta como
    mucho una vez al día, y un fallo no se guarda.
    """
    if not _hay_identidad():
        return None
    guardado = cache.leer(RAIZ_CACHE, "ultimo_informe", ticker, VALIDEZ)
    if guardado is not None and guardado.vigente:
        datos = guardado.datos
        if isinstance(datos, list) and len(datos) == 3 and datos[0] == formulario:
            return str(datos[1]), str(datos[2])
    hallado = _consultar_ultimo(ticker, formulario)
    if hallado is None:
        return None
    try:
        cache.guardar(RAIZ_CACHE, "ultimo_informe", ticker, [formulario, *hallado])
    except OSError:
        pass
    return hallado
