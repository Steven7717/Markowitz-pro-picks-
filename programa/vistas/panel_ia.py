# programa/vistas/panel_ia.py
"""Lo que se pinta de la capa de IA, fuera del guion del panel.

`vistas/seguimiento.py` ya pasa de novecientas lineas. Esto vive aparte por
tamano, no por capas: sigue siendo una vista y sigue importando Streamlit.

Todo lo que venga del modelo pasa por `noticias/texto.py:plano` antes de
pintarse. En Streamlit `$…$` es LaTeX, y un texto financiero va lleno de
dolares: es un defecto ya pagado en H.
"""

from interprete import archivo as archivo_mod
from interprete import documentos, noticias as interprete_noticias
from noticias import texto


def preparar(hechos, guardado):
    """Las entradas para `interprete.noticias.leer`, bajando solo lo no leido.

    Un hecho ya leido entra con su `que_dice` guardado --unos cientos de
    caracteres en vez de treinta mil-- para que `en_conjunto` siga viendo los
    seis y solo se pague por lo nuevo.
    """
    leidas = archivo_mod.urls_leidas(guardado)
    entradas, sin_doc, recortados = [], [], []
    for hecho in hechos:
        if hecho.url in leidas:
            anterior = archivo_mod.juicio_guardado(guardado, hecho.url)
            cuerpo = anterior.juicio.que_dice
        else:
            doc = documentos.texto_de(hecho.url)
            if doc.problema:
                sin_doc.append(f"{hecho.ticker}: {doc.problema}")
                continue
            if doc.recortado:
                recortados.append(hecho.ticker)
            cuerpo = doc.texto
        entradas.append(
            (hecho.ticker, hecho.cuando, hecho.tipos, hecho.descripciones, cuerpo)
        )
    return tuple(entradas), tuple(sin_doc), tuple(recortados)


def anotadas(lectura, hechos):
    """Los juicios, atados a la url del hecho del que hablan.

    El emparejamiento es por ticker y no por posicion: el modelo puede escribir
    menos juicios que hechos, y por posicion el tercer juicio se guardaria bajo
    la url del tercer hecho aunque hablara del quinto.
    """
    por_ticker = {}
    for hecho in hechos:
        por_ticker.setdefault(hecho.ticker, hecho)
    salida = []
    for juicio in lectura.juicios:
        hecho = por_ticker.get(juicio.ticker)
        if hecho is None:
            continue
        salida.append(
            archivo_mod.Anotada(
                hecho.url, hecho.ticker, hecho.cuando, hecho.tipos, juicio
            )
        )
    return tuple(salida)


def avisos(lectura):
    """Lo que hay que contar de una lectura, para `session_state`.

    Por `session_state` y no escrito ahi mismo: el boton termina en
    `st.rerun()`, y un `st.rerun()` tira la pasada entera antes de dibujarla.
    """
    mensajes = []
    if lectura.estado == interprete_noticias.SIN_CLAVE:
        mensajes.append(("info", "Falta la clave de Anthropic. Se pone en Aprobación."))
    elif lectura.estado == interprete_noticias.FALLO:
        mensajes.append((
            "error",
            "No se pudo interpretar: o la llamada falló, o lo que volvió traía "
            "cifras inventadas y se descartó entero. **No se ha guardado nada** "
            "y no se ha cobrado ninguna lectura como hecha.",
        ))
    elif lectura.estado == interprete_noticias.HECHA and not lectura.juicios:
        mensajes.append((
            "warning",
            "Se leyeron los documentos y **no salió nada que decir**. No es que "
            "no se haya mirado ni que no haya hechos: se miró y no había nada.",
        ))
    if lectura.sin_documento:
        mensajes.append((
            "warning",
            "No se pudo bajar el documento de: "
            + "; ".join(lectura.sin_documento)
            + ". Esos hechos no se han interpretado.",
        ))
    if lectura.recortados:
        mensajes.append((
            "info",
            "El documento de "
            + ", ".join(lectura.recortados)
            + " se cortó por el final: era más largo que el tope. Lo que se leyó "
            "es el principio, que en una nota de prensa es donde están las cifras.",
        ))
    if lectura.descartados:
        mensajes.append((
            "warning",
            f"Se descartaron {lectura.descartados} juicios que nombraban un "
            "hecho que no se había enviado.",
        ))
    if lectura.conjunto_descartado:
        mensajes.append((
            "warning",
            "Se descartó el párrafo que relacionaba los hechos entre sí: "
            "nombraba algo en mayúsculas que no está en tu cartera, o llevaba "
            "una cifra. **Los juicios de arriba no están afectados.**",
        ))
    return mensajes


def _pintar_juicio(st, juicio, cuando=None, url=None):
    st.markdown(f"**{texto.plano(juicio.ticker)}** — {texto.plano(juicio.que_dice)}")
    st.markdown(texto.plano(juicio.por_que_te_toca))
    if juicio.verificada:
        marca = "Cita literal del documento"
    else:
        marca = "⚠ **Sin respaldo literal**: esta frase no se encontró en el documento"
    pie = f"{marca}: «{texto.plano(juicio.cita)}»"
    if url:
        pie += f" — {texto.enlace('ver el expediente', url)}"
    if cuando:
        pie += f" · leído el {cuando:%d/%m/%Y}"
    st.caption(pie)


def pintar_lectura(st, lectura):
    """El camino de excepcion: pintar sin pasar por el archivo."""
    for juicio in lectura.juicios:
        _pintar_juicio(st, juicio)
    if lectura.en_conjunto:
        st.info(texto.plano(lectura.en_conjunto))


def pintar_archivo(st, guardado, hechos, leidas):
    """Lo ya leido, que se ve **sin pulsar nada**.

    Es el cambio de caracter que trae el archivo: la pestana deja de estar vacia
    hasta que pagas, y se va llenando. Cada juicio lleva su fecha de lectura
    porque uno de hace seis meses y uno de esta manana no valen lo mismo.
    """
    en_pantalla = [h for h in hechos if h.url in leidas]
    if not en_pantalla:
        return
    for hecho in en_pantalla:
        anotada = archivo_mod.juicio_guardado(guardado, hecho.url)
        sesion = next(
            s for s in reversed(guardado.hechos)
            if any(a.url == hecho.url for a in s.juicios)
        )
        _pintar_juicio(st, anotada.juicio, sesion.cuando, hecho.url)
    ultima = guardado.hechos[-1] if guardado.hechos else None
    if ultima is not None and ultima.en_conjunto:
        st.info(texto.plano(ultima.en_conjunto))
