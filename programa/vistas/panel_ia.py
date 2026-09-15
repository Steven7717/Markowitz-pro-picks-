# programa/vistas/panel_ia.py
"""Lo que se pinta de la capa de IA, fuera del guion del panel.

`vistas/seguimiento.py` ya pasa de novecientas lineas. Esto vive aparte por
tamano, no por capas: sigue siendo una vista y sigue importando Streamlit.

Todo lo que venga del modelo pasa por `noticias/texto.py:plano` antes de
pintarse. En Streamlit `$…$` es LaTeX, y un texto financiero va lleno de
dolares: es un defecto ya pagado en H.
"""

from interprete import archivo as archivo_mod
from interprete import cliente as cliente_mod
from interprete import documentos, noticias as interprete_noticias
from noticias import texto
from ranking.filings import CARACTERES_POR_TOKEN

# Media medida sobre diecisiete expedientes materiales el 2026-09-10: 28.291
# caracteres, con un tope duro de 30.000 por hecho. Sirve para avisar **antes**
# de bajar nada; lo que se cobra de verdad se dice despues, con los tokens que
# la API devuelve.
_CARACTERES_POR_HECHO = 28_291

# La proporcion es la **medida** de `ranking/filings.py`, importada y no
# copiada. Aqui habia un 4 escrito a mano y en `aprobacion/generacion.py` otro,
# los dos con el mismo comentario diciendo que era lo que sale en prosa legal
# en inglés -- y el mismo fichero que dice eso mide 3,30 contra la API real y
# deja escrito que «la regla de tres se quedaba corta en un 21%». Dos copias de
# una constante de coste se separan de la medida igual de facil que dos copias
# de cualquier otra cosa.


def _tokens_de_entrada(caracteres: int) -> int:
    return int(caracteres / CARACTERES_POR_TOKEN)


def coste_estimado(cuantos_hechos: int) -> float:
    """Lo que costaria leer esos hechos, antes de bajar ninguno.

    **Es la estimacion del caso normal, no un tope**, y hace falta decirlo asi
    donde se pinte: la media viene de una medida real, pero los documentos van
    de 3.037 a 112.913 caracteres, y ademas esto cuenta un solo turno. Para lo
    que puede llegar a costar esta `coste_peor_caso`, que es lo que la pantalla
    anuncia como «como mucho».
    """
    caracteres = cuantos_hechos * min(_CARACTERES_POR_HECHO, documentos.TOPE_CARACTERES)
    return cliente_mod.coste(_tokens_de_entrada(caracteres), cliente_mod.MAX_TOKENS)


def coste_peor_caso(cuantos_hechos: int) -> float:
    """Lo mas que puede costar una pulsacion. **Es el peor caso, no la media.**

    La pantalla decia «cuesta unos X $ **como mucho**» con la cifra de
    `coste_estimado`, que es la media y un solo turno. Pero `interprete/
    noticias.py` reenvia el turno de usuario entero en el reintento, y el
    reintento no es mala suerte: lo dispara de forma determinista un documento
    hostil, al que le basta con inducir un digito o una cita que no verifique.
    O sea que el texto de un tercero decidia el gasto por un factor de dos y
    medio sobre lo anunciado.

    Es el mismo defecto que ya se cerro en la pantalla hermana --ver
    `aprobacion/generacion.py:coste_peor_caso`-- y se calcula igual: de las
    constantes que de verdad producen el gasto, y no de una cifra prudente
    escrita a mano. Por eso vive como funcion: quien cambie la politica de
    reintento en `interprete/noticias.py` mueve esto con ella.

    Tres diferencias con `coste_estimado`, y las tres van en la misma
    direccion:

    1. **El tope duro por hecho**, no la media. Una media sirve para estimar;
       para un tope no, porque lo unico que ningun hecho puede pasarse es
       `documentos.TOPE_CARACTERES`.
    2. **Los dos turnos**, y el segundo lleva ademas el eco de la respuesta
       anterior, que como mucho son `MAX_TOKENS`.
    3. **Las dos respuestas** a `MAX_TOKENS`, que es el techo duro de cada una.
    """
    entrada_por_turno = _tokens_de_entrada(
        cuantos_hechos * documentos.TOPE_CARACTERES
    )
    if not cuantos_hechos:
        return 0.0
    entrada = entrada_por_turno * 2 + cliente_mod.MAX_TOKENS
    return cliente_mod.coste(entrada, 2 * cliente_mod.MAX_TOKENS)


def preparar(hechos, guardado):
    """Las entradas para `interprete.noticias.leer`, bajando solo lo no leido.

    Separadas en dos, y a proposito: `entradas` son los hechos sin leer, con su
    documento recien bajado, y son lo que se interpreta esta vez. `leidas` son
    los ya leidos, con su `que_dice` guardado --unos cientos de caracteres en
    vez de treinta mil-- y van al prompt **sin letra** via
    `interprete.contexto.leidos`, solo para que `en_conjunto` siga viendo el
    cuadro completo. Si fueran a la misma lista que `entradas`, `leer` les
    pondria letra, y un juicio nuevo podria citar ese resumen como si fuera el
    documento -- el defecto que rotulaba «Cita literal del documento» un texto
    que en realidad habia escrito el propio modelo en otra sesion.
    """
    leidas_urls = archivo_mod.urls_leidas(guardado)
    entradas, leidas, sin_doc, recortados = [], [], [], []
    for hecho in hechos:
        if hecho.url in leidas_urls:
            anterior = archivo_mod.juicio_guardado(guardado, hecho.url)
            leidas.append((
                hecho.ticker, hecho.cuando, hecho.tipos, hecho.descripciones,
                anterior.juicio.que_dice,
            ))
            continue
        doc = documentos.texto_de(hecho.url)
        if doc.problema:
            sin_doc.append(f"{hecho.ticker}: {doc.problema}")
            continue
        if doc.recortado:
            recortados.append(hecho.ticker)
        entradas.append(
            (hecho.ticker, hecho.cuando, hecho.tipos, hecho.descripciones, doc.texto)
        )
    return tuple(entradas), tuple(leidas), tuple(sin_doc), tuple(recortados)


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
            "No se pudo interpretar: "
            + (lectura.problema or "la llamada no devolvió nada utilizable")
            + ". **No se ha guardado nada.**",
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
    if lectura.entrada_tokens or lectura.salida_tokens:
        _coste = cliente_mod.coste(lectura.entrada_tokens, lectura.salida_tokens)
        mensajes.append((
            "info",
            f"Esta lectura costó **{_coste:.3f} $** "
            f"({lectura.entrada_tokens:,} tokens de entrada y "
            f"{lectura.salida_tokens:,} de salida, a la tarifa de "
            f"{cliente_mod.MODELO}).",
        ))
    return mensajes


def _pintar_juicio(st, juicio, cuando=None, url=None):
    st.markdown(f"**{texto.plano(juicio.ticker)}** — {texto.plano(juicio.que_dice)}")
    st.markdown(texto.plano(juicio.por_que_te_toca))
    if juicio.verificada:
        # «del documento de la empresa» y no «del documento» a secas: lo que el
        # codigo comprueba es que la frase esta en el expediente, y el
        # expediente lo escribio la empresa. Verificada quiere decir «lo dijo
        # ella», no «es verdad», y la etiqueta corta se leia como lo segundo
        # justo encima de una decision de cartera.
        marca = "Cita literal del documento de la empresa"
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
