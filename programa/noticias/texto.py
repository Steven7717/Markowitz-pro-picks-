"""El texto ajeno, preparado para que Streamlit lo pinte y no lo interprete.

Esto vivia dentro de `vistas/noticias.py`, que es un guion de Streamlit y **no
se puede importar**. El panel de seguimiento pinta los mismos hechos y los
mismos titulares, y desde un guion la unica forma de tenerlo habria sido
copiarlo. Es el mismo argumento que saco `noticias/traer.py` en la tarea 3, y
aqui pesa mas todavia: lo que se copiaria es **el escapado**. Dos copias de una
decision de seguridad se separan igual de facil que dos copias de cualquier
otra, con la diferencia de que la que se quede atras no da un numero raro —
sigue pintando titulares, sin mas, hasta el dia en que uno lleve un dolar.

Nada de lo que llega de la red es marcado. Es texto que escribio otro, y se
escapa antes de pintarlo.
"""

from datetime import datetime, timezone

# Streamlit interpreta markdown, y ademas LaTeX entre dolares. Un titular
# financiero va lleno de dolares --"Apple pasa de $4T"-- y el segundo se comeria
# la linea entera hasta el siguiente.
ESPECIALES = str.maketrans({c: "\\" + c for c in "\\`*_[]$"})


def plano(texto: object) -> str:
    """El texto tal cual se escribio, sin que markdown se quede con nada."""
    return str(texto).translate(ESPECIALES)


def cita_en_bloque(cita: object) -> str:
    """Una cita literal, lista para pintarse como bloque citado.

    El `>` lo pone el codigo; lo de dentro, no. Es la diferencia que hacia falta
    en la ficha del candidato, donde la cita **es texto copiado del filing** y se
    pintaba en crudo: un `[texto](url)` dentro de ella salia como enlace pulsable
    al dominio de quien escribio el documento, justo debajo de la palabra
    «verificada» y al lado de la casilla de aprobar.

    Los blancos se colapsan antes de escapar. Un filing trae saltos de linea a
    mitad de frase, y un salto dentro de un bloque citado lo parte en dos: la
    segunda mitad sale como parrafo normal y deja de parecer una cita.

    Una cita en blanco devuelve cadena vacia y no un `>` solo, que se pinta como
    una raya gris sin texto y se lee como «la cita existe y esta vacia». No tener
    cita es otra cosa, y quien llama tiene que poder decirlo con sus palabras.
    """
    limpia = " ".join(str(cita).split())
    if not limpia:
        return ""
    return f"> {plano(limpia)}"


def enlace(texto: str, url: str) -> str:
    """El texto enlazado, o el texto solo si no hay adonde ir.

    Una `Noticia` puede traer la url vacia: yfinance sirve elementos sin
    `canonicalUrl`. Un `[titular]()` se pinta como enlace, invita a pulsarlo y
    no lleva a ninguna parte. El destino va entre `<>` porque las urls de
    prensa traen parentesis y sin ellos el enlace se corta a la mitad.
    """
    if not url:
        return texto
    return f"[{texto}](<{url}>)"


def hace(cuando: datetime) -> str:
    """Cuanto ha pasado, en palabras."""
    minutos = int((datetime.now(timezone.utc) - cuando).total_seconds() // 60)
    if minutos < 1:
        return "hace menos de un minuto"
    if minutos < 60:
        return f"hace {minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"hace {horas} h"
    return f"hace {horas // 24} d"


def cada(validez) -> str:
    """La ventana de frescura en palabras. `str(timedelta)` diria "1:00:00"."""
    total = validez.total_seconds() / 3600
    if total >= 24:
        dias = int(total // 24)
        return "día" if dias == 1 else f"{dias} días"
    enteras = int(total)
    return "hora" if enteras == 1 else f"{enteras} horas"


def linea_de_hecho(hecho) -> str:
    """Un expediente en una linea: que comunico, cuando, y adonde ir a leerlo.

    El mismo formato para los destacados y para los plegados, y **el mismo en
    las dos pantallas**. Si el tramite se pintara mas pequeño o sin enlace,
    plegar acabaria pareciendo descartar.
    """
    etiqueta = " · ".join(plano(d) for d in hecho.descripciones) or "Sin detalle"
    if hecho.enmienda:
        etiqueta += " (enmienda)"
    return (
        f"**{plano(hecho.ticker)}** — {etiqueta}  \n"
        f"{hecho.cuando:%d/%m/%Y} · " + enlace("ver el expediente", hecho.url)
    )
