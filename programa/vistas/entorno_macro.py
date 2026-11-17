"""Entorno macro: en qué fase del ciclo está una región, y qué favorece.

Widgets sin lógica. La regla está en `macro/fase.py`, los datos en
`macro/fuentes.py` y las palabras en `macro/textos.py`, todo con tests.

**Aquí no se recomienda nada.** La fase inclina el Top solo si se activa en
Revisar candidatos, y la evidencia de que eso aporte es floja: se dice.

Ningún motivo revienta la pantalla: sin serie o con una demasiado corta se
dice por qué y se para; con huecos o indeterminada se pinta lo que hay (nivel,
gráfico) sin sectores ni lectura con IA, porque no hay fase que explicar.
"""

from dataclasses import replace
from datetime import date

import plotly.graph_objects as go
import streamlit as st

import preferencias as preferencias_mod
import tema
from interprete import cliente as cliente_ia
from macro import contexto as contexto_mod
from macro import fuentes, lectura, textos
from macro.criterio import NIVEL_NEUTRO, REGIONES, SECTORES_POR_FASE
from macro.estado import leer_region
from macro.fase import fases_por_mes
from macro.mensual import mensual

# `interprete.cliente.coste(1500, 2000)` da 0,023 $: un prompt de unos 1.500
# tokens y una salida limitada por `MAX_TOKENS = 2000`.
COSTE_MAXIMO = 0.03
MESES_GRAFICO = 60
COLORES = {
    "recuperacion": tema.AZUL,
    "expansion": tema.VERDE,
    "desaceleracion": tema.AMBAR,
    "contraccion": tema.ROJO,
}

st.markdown(
    tema.cabecera(
        "Entorno macro",
        "La fase del ciclo de una región, leída en el indicador adelantado de la "
        "OCDE, y los sectores que esa fase suele favorecer.",
    ),
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner="Descargando el indicador de la OCDE...")
def _estado(region: str, hoy: date):
    return leer_region(region, hoy)


@st.cache_data(ttl=3600, show_spinner="Descargando FRED...")
def _contexto_usa():
    series = {
        nombre: fuentes.traer_fred(serie).datos
        for nombre, serie in contexto_mod.SERIES.items()
    }
    return contexto_mod.calcular(**series)


def _motivo(clave) -> str:
    """La frase del motivo; uno que no tenga frase se dice crudo, no revienta."""
    return textos.MOTIVO.get(clave, f"No se puede leer la fase ({clave}).")


guardadas, _ = preferencias_mod.cargar()
claves = list(REGIONES)
region = st.selectbox(
    "Región",
    claves,
    index=claves.index(guardadas.region_macro),
    format_func=textos.NOMBRE_REGION.get,
    key="region_macro_pantalla",
)
if region != guardadas.region_macro:
    try:
        preferencias_mod.guardar(replace(guardadas, region_macro=region))
    except OSError:
        pass  # No recordarla no impide verla.

estado = _estado(region, date.today())
fase = estado.fase

# Sin serie, o con tan pocos meses que no hay ni nivel: no hay nada que pintar.
if fase is None or fase.nivel is None:
    st.warning(_motivo(estado.motivo_no_inclinar))
    st.stop()

columna_fase, columna_dato = st.columns([2, 1])
with columna_fase:
    if fase.clave is None:
        st.markdown("### Fase indeterminada")
        st.caption(_motivo(fase.motivo))
    else:
        st.markdown(f"### {textos.NOMBRE_FASE[fase.clave]}")
        st.caption(f"Lleva {fase.meses_en_fase} meses en esta fase.")
with columna_dato:
    st.metric(
        "Indicador adelantado",
        textos.cifra(fase.nivel),
        None if fase.cambio is None else f"{fase.cambio:+.2f} en 3 meses".replace(".", ","),
    )
    if fase.mes_dato is not None:
        st.caption(f"Dato de {textos.mes_legible(fase.mes_dato)}.")

if estado.vieja:
    st.warning("La OCDE no responde: esto es lo último que se guardó.")
if estado.motivo_no_inclinar == "dato_rancio":
    st.warning(textos.MOTIVO["dato_rancio"])

# El gráfico: los últimos cinco años en meses de calendario (un hueco se ve como
# un corte), con la línea de 100 y cada mes coloreado por su fase.
rejilla = mensual(estado.serie)
por_mes = fases_por_mes(estado.serie).reindex(rejilla.index)
rejilla, por_mes = rejilla.iloc[-MESES_GRAFICO:], por_mes.iloc[-MESES_GRAFICO:]
figura = go.Figure()
figura.add_trace(go.Scatter(
    x=rejilla.index, y=rejilla, mode="lines", name="Indicador",
    line={"color": tema.TEXTO_TENUE},
    hovertemplate="%{x|%Y-%m}: %{y:.2f}<extra></extra>",
))
for clave, color in COLORES.items():
    marcados = rejilla[por_mes == clave]
    if marcados.empty:
        continue
    figura.add_trace(go.Scatter(
        x=marcados.index, y=marcados, mode="markers", name=textos.NOMBRE_FASE[clave],
        marker={"color": color, "size": 6},
        hovertemplate="%{x|%Y-%m}: %{y:.2f}<extra></extra>",
    ))
figura.add_hline(y=NIVEL_NEUTRO, line_dash="dot", line_color=tema.TEXTO_SUAVE)
figura.update_layout(
    height=320, margin={"l": 10, "r": 10, "t": 10, "b": 10},
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"color": tema.TEXTO}, legend={"orientation": "h", "bgcolor": "rgba(0,0,0,0)"},
)
st.plotly_chart(figura, width="stretch", key="grafico_cli")

if fase.clave is not None:
    listas = SECTORES_POR_FASE[fase.clave]
    favorecidos, desfavorecidos = st.columns(2)
    for columna, titulo, lado in (
        (favorecidos, "Suele favorecer", "favorecidos"),
        (desfavorecidos, "Suele desfavorecer", "desfavorecidos"),
    ):
        with columna:
            st.markdown(f"**{titulo}**")
            for sector in listas[lado]:
                st.markdown(
                    f"- **{textos.NOMBRE_SECTOR[sector]}**: {textos.POR_QUE[fase.clave][sector]}"
                )

st.info(textos.AVISO_EVIDENCIA)

contexto = None
if region == "usa":
    contexto = _contexto_usa()
    st.markdown("#### Contexto de EE. UU.")
    curva, sahm, inflacion = st.columns(3)
    curva.metric("Curva 10a − 3m", "—" if contexto.curva is None else f"{contexto.curva:+.2f}".replace(".", ","))
    if contexto.curva_invertida:
        curva.caption("Invertida: históricamente ha precedido a las recesiones.")
    sahm.metric("Regla de Sahm", "—" if contexto.sahm is None else textos.cifra(contexto.sahm))
    if contexto.sahm_activada:
        sahm.caption("Activada: el desempleo sube como al empezar una recesión.")
    inflacion.metric(
        "Inflación interanual",
        "—" if contexto.inflacion is None else f"{contexto.inflacion:.1%}".replace(".", ","),
    )
    if contexto.mes_inflacion is not None:
        inflacion.caption(f"Dato de {textos.mes_legible(contexto.mes_inflacion)}.")
    if contexto.sahm is None:
        sahm.caption("FRED no tiene meses suficientes para calcularlo.")
    if contexto.inflacion is None:
        inflacion.caption("FRED no tiene meses suficientes para calcularlo.")
    st.caption("El contexto no entra en la fase: se enseña al lado.")
else:
    st.caption("El contexto de curva, desempleo e inflación solo está para EE. UU.")

st.markdown("#### Lectura con IA")
if fase.clave is None:
    st.caption("Sin una fase determinada no hay nada que leer.")
elif not cliente_ia.hay_clave():
    st.caption("Hace falta la clave de Anthropic, en Perfil y ajustes.")
elif st.button(
    f"Leer con IA (hasta {COSTE_MAXIMO:.2f} \\$)".replace(".", ","),
    icon=":material/auto_awesome:", key="leer_macro",
):
    with st.spinner("Leyendo..."):
        resultado = lectura.leer(estado, contexto)
    if resultado.problema:
        st.error(resultado.problema)
    else:
        st.markdown(resultado.explicacion)
        st.markdown("**Qué vigilar**")
        for punto in resultado.vigilar:
            st.markdown(f"- {punto}")
        st.caption(
            "Guardada de antes: no costó nada." if resultado.coste_usd == 0
            else f"Costó {resultado.coste_usd:.3f} \\$.".replace(".", ",", 1)
        )
