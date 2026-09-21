import io
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import plotly.graph_objects as go

from optimizer import STRATEGY_LABELS
from validation import (
    frase_identificabilidad,
    identificabilidad_guardada,
    titular_veredicto,
    veredicto_guardado,
)


# Lo único del castellano que Helvetica NO puede escribir.
#
# Helvetica es una de las catorce fuentes del núcleo del PDF y su codificación
# es latin-1, que lleva las tildes, la eñe, la diéresis y los signos de apertura
# sin problema. **Comprobado**: el informe estaba escrito sin tildes como si
# fuera una limitación técnica, y no lo era. Lo que de verdad no cabe en latin-1
# son tres caracteres que el castellano no necesita —la raya larga, las comillas
# tipográficas y el euro— y que hasta ahora reventaban la descarga entera con
# `FPDFUnicodeEncodingException`. Como parte de estos textos viene de fuera (la
# etiqueta de la estrategia, los nombres de las columnas de la tabla), se
# sustituyen en vez de confiar en que nadie los escriba.
_SUSTITUCIONES = {
    "—": "-",   # raya larga
    "–": "-",   # semirraya
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "€": " EUR",
    "…": "...",
    "→": "->",
    "◄": "<",
}


def texto_pdf(texto: str) -> str:
    """Un texto que Helvetica pueda escribir, conservando todas las tildes."""
    limpio = str(texto)
    for malo, bueno in _SUSTITUCIONES.items():
        limpio = limpio.replace(malo, bueno)
    # Red de seguridad para lo que no esté en la lista: se pierde ese carácter,
    # no el informe.
    return limpio.encode("latin-1", "replace").decode("latin-1")


def etiqueta_estrategia(guardado) -> str:
    """La estrategia, escrita para leerse. En el fichero viaja su clave.

    `cartera.Portafolio.estrategia` dice por qué en disco va `max_sharpe` y no
    «Máximo Sharpe (Markowitz)»: la etiqueta es texto de pantalla y puede
    reescribirse en cualquier momento, así que guardarla ataría un fichero a
    una decisión de redacción. El diccionario `metricas` que se escribe al lado
    esquivaba esa regla, y este informe es el único que lee ese campo — de modo
    que la traducción vive aquí, con el mismo `.get(clave, clave)` que ya usan
    `vistas/comparar.py` y `vistas/portafolios.py`.

    **La tolerancia no es pereza, es el resto del contrato.** Los ficheros
    escritos antes de esto llevan la etiqueta dentro;
    `scripts/migrar_metricas_guardadas.py` alcanza los de esta instalación,
    pero no una copia de seguridad, uno traído de otra máquina ni uno editado a
    mano. Un valor que no está entre las claves es lo que parece —una etiqueta
    ya escrita— y se imprime tal cual, con la redacción de aquel día, que es
    exactamente lo que ese fichero guardó.
    """
    return STRATEGY_LABELS.get(guardado, str(guardado))


def etiqueta_shrinkage(guardado) -> str:
    """«Sí» o «No», dictado aquí. En el fichero va el booleano.

    El de al lado del anterior, y el mismo caso: `metricas` guardaba `"Sí"`/
    `"No"` —el booleano ya renderizado a castellano— mientras
    `cartera.Portafolio.shrinkage` guardaba el bool de verdad en el MISMO
    fichero. Dos formas del mismo hecho, y una de ellas es texto de pantalla:
    reescribir ese «Sí» a «Activada» habría congelado la redacción de hoy en
    todo fichero ya guardado.

    Con la misma tolerancia, y por lo mismo: un fichero anterior trae la
    palabra ya escrita, y una palabra no se vuelve a traducir. Se reconoce por
    el tipo, que es lo que de verdad los distingue —`isinstance(x, bool)`— y no
    por comparar contra «Sí», que sería hacer depender la lectura del fichero
    de una decisión de redacción, justo lo que se está quitando.
    """
    if isinstance(guardado, bool):
        return "Sí" if guardado else "No"
    return str(guardado)


# Lo que el fichero guarda como dato y la hoja tiene que enseñar como texto.
# Se declara una vez y lo consumen `_presentables` y `kpi_rows`, para que el
# PDF y el Excel no puedan divergir en cómo escriben el mismo campo.
_COMO_SE_ENSENA = {
    "strategy": etiqueta_estrategia,
    "shrinkage": etiqueta_shrinkage,
}


def _presentables(metrics: dict) -> dict:
    """Las métricas tal y como se enseñan, sin tocar las que no lo necesitan.

    La hoja vuelca el diccionario entero, así que sin esto la pestaña
    «Métricas» habría pasado de «Mínima varianza» a `min_variance` y de «Sí» a
    `True` el día que el fichero empezó a guardar el dato: el arreglo del
    fichero habría roto la exportación. `vistas/seguimiento.py` pasa por
    `to_excel` su propio diccionario, que no tiene ninguno de los dos campos, y
    ahí no se inventa la columna.
    """
    presentes = {c: f for c, f in _COMO_SE_ENSENA.items() if c in metrics}
    if not presentes:
        return metrics
    return {**metrics, **{c: f(metrics[c]) for c, f in presentes.items()}}


def to_excel(weights_df: pd.DataFrame, metrics: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        weights_df.to_excel(writer, sheet_name="Pesos", index=False)
        pd.DataFrame([_presentables(metrics)]).to_excel(
            writer, sheet_name="Métricas", index=False
        )
    return buf.getvalue()


def _conteo(valor) -> str:
    """Un recuento, escrito como recuento.

    `cartera._serializable` pasa por `float()` todo lo que no es texto ni
    booleano para que `json.dumps` no reviente con un `numpy.int64`, así que un
    portafolio guardado vuelve con `oos_windows: 4.0` y `n_obs: 501.0`. El
    informe los imprimía tal cual —«Ventanas de validación: 4.0»,
    «Observaciones usadas: 501.0»— y un decimal sobre algo que se cuenta con
    los dedos no significa nada: no hay media ventana.
    """
    try:
        return str(int(float(valor)))
    except (TypeError, ValueError):
        return str(valor)


def kpi_rows(metrics: dict) -> list[tuple[str, str]]:
    """Build the metric table for the report.

    The in-sample Sharpe is labelled as such and shown next to the walk-forward
    result, so a reader of the exported report cannot mistake the fitted number
    for an expected one.
    """
    rows = []
    if metrics.get("strategy"):
        rows.append(("Estrategia", etiqueta_estrategia(metrics["strategy"])))
    rows += [
        ("Sharpe del ajuste único (en muestra)", f"{metrics['sharpe']:.4f}"),
        ("Retorno Anual Esperado (aritmético)", f"{metrics['annual_return']:.2%}"),
        ("Volatilidad Anual", f"{metrics['annual_vol']:.2%}"),
        ("Tasa Libre de Riesgo (anual, promedio)", f"{metrics['rf_rate']:.2%}"),
    ]

    oos = metrics.get("oos_sharpe")
    if oos is None:
        rows.append(("Sharpe fuera de muestra", "No disponible (historial insuficiente)"))
    else:
        # **Con su barra y a dos decimales.** El informe imprimía «2.2389»
        # mientras el mismo fichero guardaba que ese número se conoce con un
        # error estándar de ±2,10: cuatro decimales prometen una precisión de 1
        # entre 10.000 sobre una cifra que no distingue el 2 del 4. Y el ± ya
        # estaba guardado, así que no costaba nada.
        error = metrics.get("oos_sharpe_stderr")
        rows.append((
            "Sharpe fuera de muestra",
            f"{oos:.2f} ± {error:.2f}" if error is not None else f"{oos:.2f}",
        ))
        benchmark = metrics.get("oos_equal_weight_sharpe")
        if benchmark is not None:
            rows.append(("Sharpe Equal Weight (fuera de muestra)", f"{benchmark:.2f}"))
        # El veredicto en la tabla, en tres palabras; la medición que lo
        # sostiene va entera en `notas_pdf`, que sí tiene sitio para una frase.
        dictamen = veredicto_guardado(metrics)
        rows.append((
            "Veredicto contra repartir por igual",
            dictamen["titular"] if dictamen is not None
            else titular_veredicto(metrics.get("beats_equal_weight")),
        ))
        rows.append(("Ventanas de validación", _conteo(metrics.get("oos_windows", 0))))

    # `in` y no la verdad del valor: «Estimación robusta: No» dice algo de la
    # corrida, y callarlo dejaría al lector suponiendo cuál de las dos fue.
    if "shrinkage" in metrics:
        rows.append(("Estimación robusta", etiqueta_shrinkage(metrics["shrinkage"])))
    if metrics.get("n_obs"):
        rows.append(("Observaciones usadas", _conteo(metrics["n_obs"])))

    return rows


def notas_pdf(metrics: dict) -> list[str]:
    """Lo que el informe tiene que decir y no cabe en una celda de 80 milímetros.

    El PDF es el documento que el usuario enseña a terceros, y salía con los dos
    Sharpe fuera de muestra a cuatro decimales y ni una palabra sobre si la
    diferencia entre ellos cabía dentro del error, ni sobre si los pesos de la
    tabla de al lado están sostenidos por los datos. Las dos frases se dictan en
    `validation`, las mismas que ve la pantalla, para que el papel y el monitor
    no puedan decir cosas distintas del mismo portafolio.
    """
    notas: list[str] = []

    dictamen = veredicto_guardado(metrics)
    if dictamen is not None:
        notas.append(f"Veredicto contra repartir por igual: {dictamen['frase']}")
    elif metrics.get("oos_sharpe") is not None:
        # Un portafolio anterior a `oos_gap_stderr`: la conclusión guardada es
        # todo lo que hay, y se enseña marcada como lo que es. Callarla dejaría
        # el Sharpe grande solo en la página, que es el defecto de origen;
        # darla por buena escondería que se dictó con otro listón.
        notas.append(
            f"Veredicto contra repartir por igual: "
            f"{titular_veredicto(metrics.get('beats_equal_weight')).lower()}, "
            "según el veredicto guardado el día de la corrida. No se puede "
            "recomprobar: este portafolio es anterior a que el programa midiera "
            "el error de la diferencia contra 1/N."
        )

    identificabilidad = identificabilidad_guardada(metrics)
    if identificabilidad is not None:
        notas.append(
            f"Identificabilidad de los pesos: "
            f"{frase_identificabilidad(identificabilidad)}"
        )

    return notas


def to_pdf(
    weights_df: pd.DataFrame,
    metrics: dict,
    figures: list[go.Figure],
) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Markowitz Pro Picks", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        texto_pdf(
            f"Fecha: {date.today().strftime('%d/%m/%Y')}  |  "
            f"Horizonte: {metrics.get('horizon', '-')}"
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )
    pdf.ln(6)

    # KPI table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, texto_pdf("Métricas del Portafolio Óptimo"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    for label, value in kpi_rows(metrics):
        pdf.cell(100, 7, texto_pdf(label), border=1)
        pdf.cell(80, 7, texto_pdf(value), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # `multi_cell` y no `cell`: estas frases pasan de los 200 caracteres y en
    # una celda de 80 milímetros se saldrían por el borde derecho de la hoja.
    notas = notas_pdf(metrics)
    if notas:
        pdf.set_font("Helvetica", "", 9)
        for nota in notas:
            pdf.multi_cell(0, 5, texto_pdf(nota))
            pdf.ln(1)
        pdf.ln(3)

    # Weights table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, texto_pdf("Distribución de Pesos Óptimos"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    cols = list(weights_df.columns)
    col_w = 180 // len(cols)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 7, texto_pdf(col), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for _, row in weights_df.iterrows():
        for val in row:
            pdf.cell(col_w, 6, texto_pdf(val), border=1)
        pdf.ln()
    pdf.ln(4)

    # Charts
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, texto_pdf("Gráficas"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, fig in enumerate(figures):
            img_path = os.path.join(tmpdir, f"chart_{i}.png")
            fig.write_image(img_path, width=900, height=500, scale=1.5)
            pdf.image(img_path, w=180)
            pdf.ln(3)

    # Disclaimer
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 5,
        texto_pdf(
            "El Sharpe 'en muestra' se mide sobre los mismos datos con los que se "
            "optimizó el portafolio, por lo que sobrestima el desempeño esperado. El "
            "Sharpe 'fuera de muestra' se mide sobre datos que el cálculo no llegó a "
            "ver: se optimiza en una ventana, se mantienen los pesos fijos en la "
            "siguiente y se repite (validación walk-forward). Es la referencia "
            "relevante. Este reporte es de carácter informativo y no "
            "constituye asesoramiento financiero. Los resultados pasados no garantizan "
            "rendimientos futuros."
        ),
    )

    return bytes(pdf.output())
