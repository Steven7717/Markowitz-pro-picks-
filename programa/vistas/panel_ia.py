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
        mensajes.append(("info", "Falta la clave de Anthropic. Se pone en Perfil y ajustes."))
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
            f"Esta lectura costó **{_coste:.3f} \\$** "
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


def confirmar(st, clave: str, etiqueta: str, aviso: str, icono: str = ":material/auto_awesome:") -> bool:
    """Un botón que gasta, con su confirmación. `True` sólo en la pasada en que se confirma.

    Es el patrón de Revisar candidatos: la bandera **no es de un widget** y se
    desarma **antes** de devolver `True`, así que no sobrevive a nada. Si la
    llamada falla a mitad, hay que volver a pedirla y volver a confirmar: el
    gasto nunca queda a un clic.
    """
    bandera = f"{clave}_confirmar"
    if st.button(etiqueta, icon=icono, key=f"{clave}_pedir"):
        st.session_state[bandera] = True
    if not st.session_state.get(bandera):
        return False
    with st.container(border=True):
        st.warning(aviso)
        columna_si, columna_no, _hueco = st.columns([2, 1, 3])
        if columna_si.button("Sí, leer con IA", key=f"{clave}_si", type="primary"):
            st.session_state[bandera] = False
            return True
        if columna_no.button("Cancelar", key=f"{clave}_no"):
            st.session_state[bandera] = False
            st.rerun()
    return False


def interpretar_hechos(
    st, a_leer, ruta_archivo, tickers, pesos, clave, *, consultado, con_enlace_a_perfil=False,
    con_confirmacion=False,
):
    """El botón de «Interpretar estos hechos», con su archivo.

    Lo estrenó la pestaña Noticias de Seguimiento y lo reutiliza el Analizador:
    estaba escrito dentro de `vistas/seguimiento.py`, y dos copias de un camino
    que cobra se separan igual que dos de cualquier otra cosa.

    - `a_leer`: los hechos que hay en pantalla, que son los que se interpretan
      (los destacados más recientes, `noticias.resumen.TOPE_HECHOS`).
    - `ruta_archivo`: dónde se guardan las lecturas. El del libro en
      Seguimiento; `analisis/<TICKER>.json` en el Analizador.
    - `tickers` y `pesos`: lo que el modelo puede nombrar y la cartera que ve.
      En el Analizador, el ticker y nada: `pesos=()`, porque allí no hay cartera.
    - `clave`: separa en `session_state` los avisos de cada pantalla, y la clave
      de sus botones.
    - `consultado`: si lo que hay en pantalla sale de haber preguntado por los
      8-K de todos los activos. Sin valor por defecto, a propósito: una lista
      vacía porque no hay ninguno y una vacía porque la SEC no respondió, o
      porque no se ha pedido, llegan iguales, y sólo quien llama sabe cuál es.
    - `con_confirmacion`: si el botón pasa por `confirmar`. El Analizador lo
      pide; Seguimiento sigue como estaba.

    **Se pinta desde el archivo, nunca desde la `Lectura` recién hecha.** Un
    solo camino, y así la fecha de cada juicio vive donde pertenece --en la
    sesión-- en vez de tener que viajar dentro de cada `Juicio`. La excepción
    es el archivo ilegible: ahí no se puede ni leer ni guardar, así que se pinta
    la lectura directamente con el aviso, para que un fichero roto no se lleve
    por delante la llamada que se acaba de pagar.
    """
    try:
        guardado = archivo_mod.cargar(ruta_archivo)
        roto = ""
    except archivo_mod.ArchivoIlegible as error:
        guardado = archivo_mod.Archivo()
        roto = str(error)

    if roto:
        st.error(
            f"{roto}\n\nEl fichero **no se ha tocado**: sigue ahí por si "
            "quieres recuperarlo a mano. Se puede interpretar igual, pero lo "
            "que salga no se va a poder guardar."
        )

    # Las urls ya leídas, que es lo que necesita `pintar_archivo`. No se pisan
    # con lo que devuelve `preparar`: en el guion de Seguimiento compartían
    # nombre, y tras una lectura fallida `pintar_archivo` buscaba urls en una
    # tupla de tuplas y no pintaba nada de lo guardado.
    leidas = archivo_mod.urls_leidas(guardado)
    nuevos = [h for h in a_leer if h.url not in leidas]

    if not a_leer and not consultado:
        st.caption(
            "No hay hechos materiales que interpretar, pero no porque se haya "
            "mirado y no hubiera: los 8-K no se han podido consultar, o no de "
            "todos los activos. Hasta que se consulten, no se sabe si hay alguno."
        )
    elif not a_leer:
        st.caption(
            "No hay hechos materiales que interpretar. No es que no se haya "
            "mirado: se miró y no había ninguno."
        )
    elif not cliente_mod.hay_clave():
        st.info(
            "Falta la clave de Anthropic. Se pone en **Perfil y ajustes**, y hasta "
            "entonces todo lo demás funciona igual."
        )
        if con_enlace_a_perfil and st.button(
            "Configurar mis credenciales", key=f"{clave}_perfil", icon=":material/key:"
        ):
            st.switch_page("vistas/perfil.py")
    else:
        etiqueta = (
            f"Interpretar estos hechos ({len(nuevos)} nuevos)"
            if nuevos else "Volver a interpretar (ninguno nuevo)"
        )
        # «Como mucho» tiene que ir pegado a un tope de verdad. Decía eso con
        # la cifra de `coste_estimado`, que es la media de un solo turno —y el
        # documento puede forzar el segundo cuando quiera—, así que lo
        # anunciado se quedaba en menos de la mitad de lo que podía costar.
        # Ahora se dan las dos cifras y cada una dice lo que es.
        cuantos = len(nuevos) or len(a_leer)
        st.caption(
            f"Leer {cuantos} documentos cuesta como mucho "
            f"**{coste_peor_caso(cuantos):.2f} \\$**, y normalmente "
            f"alrededor de **{coste_estimado(cuantos):.2f} \\$**. El "
            "tope cuenta el reintento, que lo dispara el propio documento. Lo "
            "que costó de verdad se dice al terminar."
        )
        if con_confirmacion:
            pulsado = confirmar(
                st,
                f"{clave}_interpretar",
                etiqueta,
                f"**Esto cuesta dinero: hasta {coste_peor_caso(cuantos):.2f} \\$** en tu "
                "cuenta de Anthropic. Es el peor caso, con el reintento; lo que "
                "cueste de verdad se dice aquí mismo al terminar.",
            )
        else:
            pulsado = st.button(etiqueta, icon=":material/auto_awesome:", key=f"{clave}_interpretar")
        if pulsado:
            with st.spinner("Bajando los documentos y leyéndolos…"):
                if nuevos:
                    entradas, ya_leidas, sin_doc, recortados = preparar(a_leer, guardado)
                else:
                    # «Volver a interpretar» con todo ya leído tiene que ser una
                    # segunda lectura de verdad, no una relectura de resúmenes:
                    # con un Archivo() vacío no hay nada leído, y `preparar`
                    # baja los documentos de nuevo en vez de reenviar lo que el
                    # propio modelo escribió la vez anterior.
                    entradas, ya_leidas, sin_doc, recortados = preparar(a_leer, archivo_mod.Archivo())
                lectura = interprete_noticias.leer(
                    entradas,
                    set(tickers),
                    sin_documento=sin_doc,
                    recortados=recortados,
                    pesos=tuple(pesos),
                    leidos=ya_leidas,
                )
            if lectura.estado == interprete_noticias.HECHA and not roto:
                try:
                    archivo_mod.anotar_hechos(
                        ruta_archivo,
                        cliente_mod.MODELO,
                        interprete_noticias.VERSION_PROMPT,
                        anotadas(lectura, a_leer),
                        lectura.en_conjunto,
                    )
                except OSError as fallo:
                    # Esta lectura ya se pagó. Un traceback aquí perdería además
                    # la única copia que existe de ella, así que el aviso dice
                    # las dos cosas --que no se guardó y que volver a pedirla se
                    # vuelve a cobrar-- y la deja en pantalla.
                    st.error(
                        f"**No se pudo guardar la lectura: {fallo}**\n\n"
                        "El archivo anterior sigue intacto, pero lo que se "
                        "acaba de leer **no ha quedado guardado**, y volver a "
                        "pedirlo se cobra otra vez. Aquí abajo está entero."
                    )
                    pintar_lectura(st, lectura)
                else:
                    st.session_state[f"{clave}_avisos"] = avisos(lectura)
                    st.rerun()
            else:
                # No se guarda y no se rerun: si se fue por `FALLO` o el archivo
                # está roto, el `st.rerun()` se llevaría por delante el único
                # sitio donde se puede decir qué pasó.
                for clase, mensaje in avisos(lectura):
                    getattr(st, clase)(mensaje)
                pintar_lectura(st, lectura)

    for clase, mensaje in st.session_state.pop(f"{clave}_avisos", []):
        getattr(st, clase)(mensaje)

    pintar_archivo(st, guardado, a_leer, leidas)
