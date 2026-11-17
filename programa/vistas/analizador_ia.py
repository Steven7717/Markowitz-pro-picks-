"""La pestaña IA del Analizador: tres lecturas de pago, y lo ya leído sin pagar.

Widgets sin lógica. Lo que se manda al modelo lo preparan `analizador/palabras.py`
y `analizador/informe_anual.py`; lo que vuelve lo filtran `ia_tesis`, `ia_mdna` e
`ia_valoracion`; lo que queda guardado, `analizador/archivo.py`. Este guion
encadena y pinta.

Las reglas de los cuatro botones de IA del Analizador:

- **Nunca se llama sin botón**, y el botón pasa por `panel_ia.confirmar`: dice
  cuánto puede costar como mucho, y la confirmación se desarma antes de llamar.
- **Al terminar se dice lo que costó de verdad.**
- **Se pinta desde el archivo.** Lo ya leído se ve al abrir el ticker, con su
  fecha y su documento, sin pagar.
- **El modelo no ve nada de la cartera**, y aquí no se recomienda nada.
"""

from datetime import datetime

import streamlit as st

import medidores_analizador as ma
from analizador import archivo, ia_costes, ia_mdna, ia_tesis, ia_valoracion, informe_anual, palabras, sesion
from interprete import cliente as cliente_mod
from interprete.archivo import ArchivoIlegible
from noticias import texto
from ranking import llm
from vistas import panel_ia


def _clave(bloque: str, ticker: str) -> str:
    return f"analizador_ia_{bloque}_{ticker}"


def _pintar_avisos(clave: str) -> None:
    """Lo que dejó dicho la pasada anterior: el botón termina en `st.rerun()`."""
    for clase, mensaje in st.session_state.pop(f"{clave}_avisos", []):
        getattr(st, clase)(mensaje)


def _guardar(clave: str, anotar, ruta, lectura, pintar, avisos: list) -> None:
    """Guardar y repintar desde el archivo; si no se puede guardar, enseñar la lectura igual."""
    try:
        anotar(ruta, lectura)
    except (OSError, ArchivoIlegible, ValueError, TypeError) as fallo:
        # Ya se pagó: un traceback aquí perdería la única copia que existe.
        # `ValueError` es la entrada que no se podría leer después
        # (`archivo._anotar`) y `TypeError` lo que `json` no sabe escribir.
        st.error(
            f"**No se pudo guardar la lectura: {texto.plano(fallo)}**\n\n"
            "Lo que se acaba de leer **no ha quedado guardado**, y volver a "
            "pedirlo se cobra otra vez. Aquí abajo está entero."
        )
        for clase, mensaje in avisos:
            getattr(st, clase)(mensaje)
        pintar(lectura)
    else:
        st.session_state[f"{clave}_avisos"] = avisos
        st.rerun()


_FALTA_LA_CLAVE = "Falta la clave de Anthropic. Se pone en **Perfil y ajustes**."


def _no_se_pudo(que: str, resultado, sin_gasto: dict) -> None:
    """El error de una lectura que no llegó a `HECHA`, con lo que costó si algo costó.

    `sin_gasto` dice lo que es cada estado que no es un fallo de la llamada
    (`SIN_DOCUMENTO`, `SIN_CLAVE`, `SIN_VALORACION`): en ésos no se llamó. Un
    `FALLO` sí pudo llamar --y el reintento se cobra aunque no salga nada--, así
    que si trae tokens se dice lo gastado.
    """
    explicado = sin_gasto.get(resultado.estado)
    if explicado is not None:
        st.error(f"{explicado} **No se ha gastado nada.**")
        return
    mensaje = (
        f"No se pudo {que}: "
        + texto.plano(resultado.problema or "la llamada no devolvió nada utilizable")
        + ". **No se ha guardado nada.**"
    )
    if resultado.entrada_tokens or resultado.salida_tokens:
        mensaje += " " + ma.coste_de_lectura(
            cliente_mod.coste(resultado.entrada_tokens, resultado.salida_tokens),
            resultado.entrada_tokens, resultado.salida_tokens,
        )
    st.error(mensaje)


def _informe(ticker: str):
    """El último informe anual, o `None` tras decir por qué no."""
    formulario = informe_anual.formulario_de(ticker)
    if formulario is None:
        st.error(ma.sin_informe("sin_red_edgar"))
        return None
    informe, motivo = informe_anual.cargar(ticker, formulario)
    if informe is None:
        st.error(ma.sin_informe(motivo))
    return informe


def _fuente(informe, seccion) -> archivo.Fuente:
    return archivo.Fuente(
        informe.formulario, informe.fecha, informe.accession, seccion.nombre, seccion.recortado
    )


def _aviso_de_informe_nuevo(ticker: str, fuente) -> None:
    aviso = ma.aviso_informe_nuevo(
        fuente, informe_anual.ultimo_presentado(ticker, fuente.formulario)
    )
    if aviso:
        st.warning(aviso)


def _pintar_cita(cita: str, verificada: bool) -> None:
    if not verificada:
        st.error("Cita SIN VERIFICAR: no aparece en el documento original")
    bloque = texto.cita_en_bloque(cita)
    if bloque:
        st.markdown(bloque)
    else:
        st.caption("Sin cita: el modelo no escribió ninguna")


# --- Tesis y riesgos ------------------------------------------------------------


def _pintar_tesis(tesis) -> None:
    st.markdown(texto.plano(tesis.tesis))
    for afirmacion, cita, verificada in tesis.riesgos:
        st.markdown(f"- {texto.plano(afirmacion)}")
        _pintar_cita(cita, verificada)
    st.caption(texto.plano(ma.procedencia_de_lectura(tesis.fuente, tesis.cuando)))


def _tesis(analisis, lecturas) -> None:
    ticker = analisis.ticker
    clave = _clave("tesis", ticker)
    st.markdown("**Tesis y riesgos**")
    st.caption(
        "La misma lectura que la ficha de los candidatos: qué hace la empresa y "
        "qué riesgos declara ella misma en su informe anual, cada uno con su "
        "cita literal."
    )
    _pintar_avisos(clave)
    ultima = lecturas.tesis[-1] if lecturas.tesis else None
    if ultima is not None:
        _pintar_tesis(ultima)
        _aviso_de_informe_nuevo(ticker, ultima.fuente)
    if not cliente_mod.hay_clave():
        return
    etiqueta = "Volver a redactar la tesis" if ultima is not None else "Redactar la tesis y los riesgos"
    if not panel_ia.confirmar(st, clave, etiqueta, ma.aviso_de_gasto(ia_costes.tesis())):
        return
    with st.spinner("Bajando el informe anual y leyéndolo…"):
        informe = _informe(ticker)
        if informe is None:
            return
        if informe.riesgos is None:
            st.warning(ma.SIN_RIESGOS)
            return
        redaccion = ia_tesis.redactar(palabras.contexto_tesis(analisis), informe.riesgos.texto)
    gasto = redaccion.gasto
    if redaccion.narrativa is None:
        st.error(
            "No se pudo redactar la tesis: la llamada falló, o la respuesta "
            "traía cifras y no se pudo corregir. **No se ha guardado nada.** "
            + ma.coste_de_lectura(gasto.usd, gasto.entrada_tokens, gasto.salida_tokens)
        )
        return
    tesis = archivo.Tesis(
        datetime.now(),
        llm.MODELO,
        llm.VERSION_PROMPT,
        _fuente(informe, informe.riesgos),
        redaccion.narrativa["tesis"],
        tuple((r["afirmacion"], r["cita"], r["verificada"]) for r in redaccion.narrativa["riesgos"]),
    )
    if redaccion.de_cache:
        avisos = [("info", "Esta tesis ya estaba redactada para este mismo informe: salió de la caché, **sin coste**.")]
    else:
        avisos = [("info", ma.coste_de_lectura(gasto.usd, gasto.entrada_tokens, gasto.salida_tokens))]
    _guardar(clave, archivo.anotar_tesis, archivo.ruta_de(ticker), tesis, _pintar_tesis, avisos)


# --- Contrastar con la empresa ----------------------------------------------------


def _pintar_contraste(contraste) -> None:
    st.caption(f"Lo que se contrastó: {texto.plano(contraste.supuesto)}")
    if not contraste.juicios:
        st.caption(
            "Se leyó el informe de gestión y **no salió nada que decir** sobre "
            "ese escenario. No es que no se haya mirado."
        )
    for afirmacion, postura, cita, verificada in contraste.juicios:
        st.markdown(f"**{ma.etiqueta(ma.POSTURA, postura)}** — {texto.plano(afirmacion)}")
        _pintar_cita(cita, verificada)
    st.caption(texto.plano(ma.procedencia_de_lectura(contraste.fuente, contraste.cuando)))


def _avisos_de_contraste(contraste, seccion) -> list:
    avisos = [("info", ma.coste_de_lectura(
        cliente_mod.coste(contraste.entrada_tokens, contraste.salida_tokens),
        contraste.entrada_tokens, contraste.salida_tokens,
    ))]
    if seccion.recortado:
        avisos.append((
            "info",
            "El informe de gestión se cortó por el final: era más largo que el "
            "tope. Lo que se leyó es el principio.",
        ))
    if contraste.descartados:
        avisos.append((
            "warning",
            f"Se descartaron {contraste.descartados} juicios: llevaban una cifra "
            "en la afirmación, una postura que no es de las tres, o sobraban.",
        ))
    return avisos


def _mdna(analisis, lecturas) -> None:
    ticker = analisis.ticker
    clave = _clave("mdna", ticker)
    st.markdown("**Contrastar con la empresa**")
    st.caption(
        "Qué dice la dirección en su informe de gestión que respalde, contradiga "
        "o matice el escenario base de la valoración. **No mueve ningún "
        "deslizador**: señala, y decides tú."
    )
    _pintar_avisos(clave)
    ultima = lecturas.mdna[-1] if lecturas.mdna else None
    if ultima is not None:
        _pintar_contraste(ultima)
        _aviso_de_informe_nuevo(ticker, ultima.fuente)
    if palabras.supuesto_crecimiento(analisis.valoracion) is None:
        st.caption("Sin valoración no hay escenario base que contrastar.")
        return
    if not cliente_mod.hay_clave():
        return
    etiqueta = "Volver a contrastar" if ultima is not None else "Contrastar con la empresa"
    if not panel_ia.confirmar(st, clave, etiqueta, ma.aviso_de_gasto(ia_costes.mdna())):
        return
    valoracion, movidos = sesion.valoracion_en_pantalla(st.session_state, analisis)
    supuesto = palabras.supuesto_crecimiento(valoracion, ma.lista_de_supuestos(movidos) if movidos else "")
    with st.spinner("Bajando el informe anual y leyéndolo…"):
        informe = _informe(ticker)
        if informe is None:
            return
        if informe.mdna is None:
            st.warning(ma.SIN_MDNA)
            return
        contraste = ia_mdna.contrastar(ticker, supuesto, informe.mdna.texto)
    if contraste.estado != ia_mdna.HECHA:
        _no_se_pudo("contrastar", contraste, {
            ia_mdna.SIN_DOCUMENTO: "No había informe de gestión que contrastar.",
            ia_mdna.SIN_CLAVE: _FALTA_LA_CLAVE,
        })
        return
    guardable = archivo.Contraste(
        datetime.now(),
        cliente_mod.MODELO,
        ia_mdna.VERSION_PROMPT,
        _fuente(informe, informe.mdna),
        supuesto,
        tuple((j.afirmacion, j.postura, j.cita, j.verificada) for j in contraste.juicios),
    )
    _guardar(
        clave, archivo.anotar_contraste, archivo.ruta_de(ticker), guardable,
        _pintar_contraste, _avisos_de_contraste(contraste, informe.mdna),
    )


# --- Explicar la valoración -----------------------------------------------------


def _pintar_explicacion(explicacion, analisis) -> None:
    # Con la valoración que hay en pantalla ahora, no con la del programa: una
    # explicación hecha con deslizadores movidos guarda los votos de esos supuestos.
    en_pantalla = sesion.valoracion_en_pantalla(st.session_state, analisis)[0]
    valoracion = en_pantalla if isinstance(en_pantalla, dict) else {}
    de_hoy = (archivo.votos_de(valoracion), valoracion.get("veredicto"))
    if (explicacion.votos, explicacion.veredicto) != de_hoy:
        st.warning(ma.de_entonces(explicacion.cuando))
    else:
        st.caption(f"Explicación del {explicacion.cuando:%d/%m/%Y}.")
    if explicacion.movidos:
        st.caption(f"Se explicó con tus supuestos: {ma.lista_de_supuestos(explicacion.movidos)}.")
    for sobre, dice, marcada in explicacion.observaciones:
        st.markdown(f"**{ma.etiqueta(ma.LECTURA_DE_VALORACION, sobre)}** — {texto.plano(dice)}")
        if marcada:
            st.error(
                "Esta observación **suena a recomendación**, y aquí no se "
                "recomienda nada: léela como una opinión del modelo, no del programa."
            )
    if explicacion.en_conjunto:
        st.info(texto.plano(explicacion.en_conjunto))


def _avisos_de_explicacion(explicacion) -> list:
    avisos = [("info", ma.coste_de_lectura(
        cliente_mod.coste(explicacion.entrada_tokens, explicacion.salida_tokens),
        explicacion.entrada_tokens, explicacion.salida_tokens,
    ))]
    if explicacion.descartadas:
        avisos.append((
            "warning",
            f"Se descartaron {explicacion.descartadas} observaciones: llevaban "
            "una cifra o hablaban de una lectura que no existe.",
        ))
    if explicacion.conjunto_descartado:
        avisos.append((
            "warning",
            "Se descartó el párrafo de conjunto: llevaba una cifra o una "
            "recomendación. **Las observaciones de arriba no están afectadas.**",
        ))
    if not explicacion.observaciones:
        avisos.append(("warning", "El modelo respondió y **no quedó nada que decir**."))
    return avisos


def _valoracion(analisis, lecturas) -> None:
    ticker = analisis.ticker
    clave = _clave("valoracion", ticker)
    st.markdown("**Explicar la valoración**")
    st.caption(
        "Qué significa cada una de las tres lecturas y de qué depende. El modelo "
        "no lee nada de la empresa ni ve una cifra: sólo los votos y los "
        "supuestos, que el programa le dice en palabras."
    )
    _pintar_avisos(clave)
    ultima = lecturas.valoracion[-1] if lecturas.valoracion else None
    if ultima is not None:
        _pintar_explicacion(ultima, analisis)
    if palabras.contexto_valoracion(ticker, analisis.sector, analisis.valoracion) is None:
        st.caption("Sin valoración no hay nada que explicar.")
        return
    if not cliente_mod.hay_clave():
        return
    etiqueta = "Volver a explicar la valoración" if ultima is not None else "Explicar la valoración"
    if not panel_ia.confirmar(st, clave, etiqueta, ma.aviso_de_gasto(ia_costes.valoracion())):
        return
    valoracion, movidos = sesion.valoracion_en_pantalla(st.session_state, analisis)
    contexto = palabras.contexto_valoracion(
        ticker, analisis.sector, valoracion, ma.lista_de_supuestos(movidos) if movidos else ""
    )
    if contexto is None:
        st.caption("Sin valoración no hay nada que explicar.")
        return
    bloque, mapa = contexto
    with st.spinner("Explicando la valoración…"):
        explicacion = ia_valoracion.explicar(bloque, mapa)
    if explicacion.estado != ia_valoracion.HECHA:
        _no_se_pudo("explicar la valoración", explicacion, {
            ia_valoracion.SIN_VALORACION: "Sin valoración no hay nada que explicar.",
            ia_valoracion.SIN_CLAVE: _FALTA_LA_CLAVE,
        })
        return
    guardable = archivo.Explicacion(
        datetime.now(),
        cliente_mod.MODELO,
        ia_valoracion.VERSION_PROMPT,
        archivo.votos_de(valoracion),
        valoracion.get("veredicto"),
        tuple(movidos),
        tuple((o.sobre, o.dice, o.marcada) for o in explicacion.observaciones),
        explicacion.en_conjunto,
    )
    _guardar(
        clave, archivo.anotar_explicacion, archivo.ruta_de(ticker), guardable,
        lambda guardada: _pintar_explicacion(guardada, analisis), _avisos_de_explicacion(explicacion),
    )


# --- La pestaña ---------------------------------------------------------------------


def pintar(analisis) -> None:
    """La pestaña IA de un ticker que no es un ETF."""
    ticker = analisis.ticker
    st.caption(
        "Nada de esto se llama sin que lo pidas, y cada botón dice antes cuánto "
        "puede costar como mucho. Lo ya leído se queda guardado y se enseña "
        "aquí sin volver a pagar. El modelo no ve nada de tu cartera, y aquí no "
        "se recomienda nada."
    )
    try:
        lecturas = archivo.cargar(archivo.ruta_de(ticker))
    except ArchivoIlegible as error:
        st.error(
            f"{texto.plano(error)}\n\nEl fichero **no se ha tocado**: sigue ahí "
            "por si quieres recuperarlo a mano. Mientras no se pueda leer no se "
            "ofrece ninguna lectura con IA, porque no habría dónde guardarla."
        )
        return
    if not cliente_mod.hay_clave():
        st.info(
            "Falta la clave de Anthropic. Se pone en **Perfil y ajustes**, y hasta "
            "entonces todo lo demás funciona igual."
        )
        if st.button("Configurar mis credenciales", key=f"analizador_ia_perfil_{ticker}", icon=":material/key:"):
            st.switch_page("vistas/perfil.py")
    if analisis.clase == "sin_sec":
        st.caption(ma.SIN_DOCUMENTO_OFICIAL)
    else:
        _tesis(analisis, lecturas)
        st.divider()
        _mdna(analisis, lecturas)
        st.divider()
    _valoracion(analisis, lecturas)
