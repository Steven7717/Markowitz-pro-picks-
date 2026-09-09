"""Qué hace este programa y en qué orden, para quien lo abre por primera vez.

Es la pantalla con la que arranca la aplicación hasta que alguien pulsa
«Entendido». A partir de ahí el arranque pasa a ser el optimizador y esta
pantalla se queda disponible en el menú, pero deja de ponerse delante.
"""

import streamlit as st

import preferencias as preferencias_mod
import tema

st.markdown(
    tema.cabecera(
        "Markowitz Pro Picks",
        "Un programa para elegir empresas con criterio y repartir el capital "
        "entre ellas — comprobando, en cada paso, si el método aporta algo.",
    ),
    unsafe_allow_html=True,
)

actuales, _ = preferencias_mod.cargar()

st.markdown("### Elegir qué comprar")

uno, dos, tres = st.columns(3)
with uno:
    with st.container(border=True):
        st.markdown("#### 1 · Candidatos")
        st.markdown(
            "Se descargan los estados financieros de las 500 empresas del S&P "
            "desde la SEC, se calculan **17 indicadores** por empresa y se "
            "ordenan comparando a cada una **con las de su propio sector**.\n\n"
            "Sale una lista corta de 15, cada una con sus medidores de calidad, "
            "crecimiento, valoración y solidez."
        )
        if st.button("Ver candidatos", use_container_width=True,
                     icon=":material/fact_check:"):
            st.switch_page("vistas/candidatos.py")

with dos:
    with st.container(border=True):
        st.markdown("#### 2 · Aprobación")
        st.markdown(
            "Nada pasa a la cartera sin que alguien lo mire. Las casillas nacen "
            "**desmarcadas a propósito**: aprobar es un acto, no el resultado de "
            "no hacer nada.\n\n"
            "De cada revisión queda un acta fechada con lo aprobado, lo "
            "descartado y el motivo escrito."
        )
        if st.button("Ver actas", use_container_width=True,
                     icon=":material/history_edu:"):
            st.switch_page("vistas/actas.py")

with tres:
    with st.container(border=True):
        st.markdown("#### 3 · Optimización")
        st.markdown(
            "Con los aprobados se reparte el capital: máximo Sharpe, mínima "
            "varianza o paridad de riesgo.\n\n"
            "Y después se comprueba **fuera de muestra** si esa optimización "
            "le gana a repartir por igual. Muchas veces no lo hace, y el "
            "programa lo dice."
        )
        if st.button("Ir al optimizador", use_container_width=True,
                     type="primary", icon=":material/insights:"):
            st.switch_page("vistas/optimizador.py")

# La mitad que faltaba. Optimizar reparte el capital, pero ahí no se acaba
# nada: lo que se compra hay que seguirlo, y estas tres pantallas existían sin
# que la portada las nombrara ni una vez.
st.markdown("### Seguir lo que compraste")

cuatro, cinco, seis = st.columns(3)
with cuatro:
    with st.container(border=True):
        st.markdown("#### 4 · Seguimiento")
        st.markdown(
            "Un portafolio guardado es una fotografía; el libro es lo que "
            "pasó después. Qué tienes, cuánto vale hoy y cómo ha rendido, "
            "medido contra el objetivo que dio el optimizador.\n\n"
            "El valor se dibuja junto a **tres referencias** que reciben el "
            "mismo dinero en las mismas fechas que metiste tú, para que la "
            "comparación aísle qué compraste de cuándo lo compraste."
        )
        if st.button("Ver el seguimiento", use_container_width=True,
                     icon=":material/monitoring:"):
            st.switch_page("vistas/seguimiento.py")

with cinco:
    with st.container(border=True):
        st.markdown("#### 5 · Rebalanceo")
        st.markdown(
            "Cuánto se ha separado cada activo de su objetivo, dónde poner el "
            "dinero nuevo —comprar corrige deriva sin vender nada ni realizar "
            "plusvalías— y qué costaría corregir el resto.\n\n"
            "Aquí no se registra nada: son **propuestas**. Las que el coste se "
            "come salen igualmente, con el motivo escrito."
        )
        if st.button("Ver el rebalanceo", use_container_width=True,
                     icon=":material/balance:"):
            st.switch_page("vistas/rebalanceo.py")

with seis:
    with st.container(border=True):
        st.markdown("#### 6 · Noticias")
        st.markdown(
            "Lo que las empresas de tu libro han comunicado a la SEC, lo que "
            "ha escrito la prensa, y las fechas que vienen.\n\n"
            "Los **8-K** —lo que la empresa está obligada a presentar, con "
            "fecha y firma— van separados de los titulares, de los que nadie "
            "responde y que el programa no filtra. Aquí no se recomienda nada."
        )
        if st.button("Ver noticias", use_container_width=True,
                     icon=":material/newspaper:"):
            st.switch_page("vistas/noticias.py")

st.markdown("### Tres cosas que conviene saber antes de usarlo")

with st.container(border=True):
    st.markdown(
        "**El orden de los candidatos no es una previsión de rentabilidad.** "
        "Es un criterio de selección transparente, congelado antes de ver "
        "ningún resultado, y **no está validado empíricamente**. Dice qué "
        "empresas destacan hoy entre sus pares por sus números, no cuáles "
        "subirán."
    )

with st.container(border=True):
    st.markdown(
        "**La lista corta llega con un sesgo sectorial que nadie eligió.** Los "
        "filtros exigen deuda sobre EBITDA, cobertura de intereses y razón "
        "corriente, y un banco no publica ninguna de las tres: no publica "
        "EBITDA, su gasto por intereses es materia prima y su balance no se "
        "clasifica en corriente y no corriente. Dos de cada tres bancos quedan "
        "fuera **por reportar distinto, no por ser peores**. Para recuperar una "
        "empresa concreta está el añadido a mano, que exige un motivo escrito."
    )

with st.container(border=True):
    st.markdown(
        "**El Sharpe que ves al optimizar está inflado.** Se mide sobre los "
        "mismos datos con los que se optimizó, así que es una cota superior. El "
        "número honesto es el de la pestaña de validación, que aparta datos, "
        "optimiza sin verlos y luego los usa para medir. Si ese número no le "
        "gana a repartir por igual, la optimización no está aportando nada."
    )

st.divider()

izquierda, derecha = st.columns([3, 1])
izquierda.caption(
    "Todo ocurre en tu ordenador: los datos que se descargan quedan en caché "
    "local y tus credenciales viven en tu carpeta personal, fuera del proyecto."
)
if derecha.button(
    "Entendido, no volver a mostrar", use_container_width=True,
    type="primary", icon=":material/check:", disabled=actuales.guia_vista,
):
    try:
        preferencias_mod.guardar(
            preferencias_mod.Preferencias(**{
                **actuales.__dict__, "guia_vista": True
            })
        )
    except OSError as error:
        st.error(f"No se pudo guardar la preferencia: {error}")
    else:
        st.rerun()

if actuales.guia_vista:
    st.caption(
        "La aplicación arranca en el optimizador. Esta pantalla sigue en el "
        "menú, en «Primeros pasos»."
    )
