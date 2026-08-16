import streamlit as st

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
    guardar_acta,
    tickers_aprobados,
)
from aprobacion.carga import ContratoRoto, FaltanFichas, cargar_candidatos, resumen_corrida
from fundamentals.kpis import TODOS_LOS_KPIS

st.set_page_config(page_title="Revisar candidatos", page_icon="✅", layout="wide")
st.title("✅ Revisar candidatos")

try:
    candidatos = cargar_candidatos()
except FaltanFichas as error:
    st.warning(str(error))
    st.stop()
except ContratoRoto as error:
    st.error(f"Las salidas de B no tienen la forma esperada: {error}")
    st.stop()

st.info(resumen_corrida(candidatos.corrida))
st.caption(
    "El orden lo decide un score determinista que **no esta validado "
    "empiricamente**: es un criterio de seleccion transparente, no una "
    "prevision de rentabilidad."
)

if "anadidos" not in st.session_state:
    st.session_state.anadidos = []

aprobados: set[str] = set()
motivos: dict[str, str] = {}

for ficha in candidatos.fichas:
    ticker = ficha["ticker"]
    columna_casilla, columna_titulo = st.columns([1, 11])
    with columna_casilla:
        # Nace desmarcada a proposito: si llegara marcada, aprobar los quince
        # seria un clic y el gate pasaria a ser decorado.
        marcada = st.checkbox("Aprobar", key=f"ok_{ticker}", label_visibility="collapsed")
    with columna_titulo:
        st.markdown(
            f"**{ficha['puesto']}. {ticker}** — {ficha['sector_gics']} · "
            f"compuesto {ficha['compuesto']:+.2f} (z dentro del sector)"
        )
    if marcada:
        aprobados.add(ticker)

    with st.expander(f"Ficha de {ticker}"):
        pilares = " · ".join(
            f"{pilar} {valor:+.2f}" if valor is not None else f"{pilar} n/d"
            for pilar, valor in ficha["pilares"].items()
        )
        st.markdown(f"Pilares (z frente a todo el universo): {pilares}")
        st.markdown(
            "- Fuerte en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["destacados"])
        )
        st.markdown(
            "- Flojo en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["flojos"])
        )
        st.markdown(
            f"- Cobertura: {ficha['cobertura']['kpis_con_dato']} de "
            f"{len(TODOS_LOS_KPIS)} KPIs"
        )
        if ficha["desplazo_a"]:
            st.markdown(
                "- Dejo fuera por el tope sectorial: "
                + ", ".join(ficha["desplazo_a"])
            )

        narrativa = ficha["narrativa"]
        if narrativa is None:
            st.markdown("_Ficha de plantilla: sin narrativa generada._")
        else:
            st.markdown(narrativa["tesis"])
            for riesgo in narrativa["riesgos"]:
                st.markdown(f"- {riesgo['afirmacion']}")
                if not riesgo["verificada"]:
                    # Si el revisor puede leer la ficha entera sin enterarse de
                    # que una cita es inventada, este sub-proyecto ha fallado.
                    st.error("Cita SIN VERIFICAR: no aparece en el documento original")
                st.markdown(f"> {' '.join(riesgo['cita'].split())}")
            fuente = narrativa.get("fuente")
            if fuente:
                recorte = " (recortado)" if fuente["recortado"] else ""
                st.caption(
                    f"Fuente: {fuente['formulario']} de {fuente['fecha']}, "
                    f"{fuente['seccion']}, accession {fuente['accession']}{recorte}"
                )
            else:
                st.warning("Procedencia no disponible: la cita no se puede localizar")

        motivo = st.text_input(
            "Motivo si lo descartas (opcional)", key=f"motivo_{ticker}"
        )
        if motivo.strip() and not marcada:
            motivos[ticker] = motivo.strip()

st.divider()
st.subheader("Anadir una empresa a mano")
st.caption(
    "Para recuperar a una empresa que las guardas excluyeron por como reporta "
    "y no por su calidad. El motivo es obligatorio: sin ranking detras, es la "
    "unica justificacion que va a existir."
)

columna_ticker, columna_motivo, columna_boton = st.columns([1, 3, 1])
nuevo_ticker = columna_ticker.text_input("Ticker", key="nuevo_ticker")
nuevo_motivo = columna_motivo.text_input("Motivo", key="nuevo_motivo")
if columna_boton.button("Anadir", disabled=not (nuevo_ticker and nuevo_motivo.strip())):
    st.session_state.anadidos.append(
        Anadido(ticker=nuevo_ticker, motivo=nuevo_motivo)
    )
    st.rerun()

if st.session_state.anadidos:
    for anadido in st.session_state.anadidos:
        st.markdown(f"- **{anadido.ticker.strip().upper()}** — {anadido.motivo}")
    # No se comprueba aqui si el ticker existe o tiene precio: llamar a yfinance
    # desde el gate lo ataria a la red y a un servicio externo, y es justo lo
    # que permite probar todo este paquete sin nada montado. El optimizador ya
    # falla de forma visible si un ticker no tiene datos.
    st.caption(
        "Solo se comprueba la forma del ticker. Si no existe o no tiene precio, "
        "el fallo aparecera en el optimizador, no aqui."
    )

st.divider()
total = len(aprobados) + len(st.session_state.anadidos)
if st.button(f"Aprobar {total} empresas y pasar al optimizador", disabled=total == 0,
             type="primary"):
    try:
        acta = construir_acta(
            candidatos,
            aprobados=aprobados,
            anadidos=st.session_state.anadidos,
            motivos=motivos,
        )
        # El acta se escribe ANTES del traspaso: el peor resultado posible seria
        # aprobar, perder el registro y seguir adelante creyendo que quedo
        # constancia.
        destino = guardar_acta(acta)
    except (MotivoRequerido, TickerDuplicado, TickerInvalido, NadaQueAprobar) as error:
        st.error(str(error))
    except OSError as error:
        st.error(f"No se pudo escribir el acta, no se aprueba nada: {error}")
    else:
        st.session_state.tickers_aprobados = tickers_aprobados(acta)
        st.success(
            f"Acta escrita en {destino}. Ya puedes pasar a la pagina del "
            "optimizador: los tickers estan puestos."
        )
