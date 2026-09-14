import io
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import plotly.graph_objects as go


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


def to_excel(weights_df: pd.DataFrame, metrics: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        weights_df.to_excel(writer, sheet_name="Pesos", index=False)
        pd.DataFrame([metrics]).to_excel(writer, sheet_name="Métricas", index=False)
    return buf.getvalue()


def kpi_rows(metrics: dict) -> list[tuple[str, str]]:
    """Build the metric table for the report.

    The in-sample Sharpe is labelled as such and shown next to the walk-forward
    result, so a reader of the exported report cannot mistake the fitted number
    for an expected one.
    """
    rows = []
    if metrics.get("strategy"):
        rows.append(("Estrategia", str(metrics["strategy"])))
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
        rows.append(("Sharpe fuera de muestra", f"{oos:.4f}"))
        benchmark = metrics.get("oos_equal_weight_sharpe")
        if benchmark is not None:
            rows.append(("Sharpe Equal Weight (fuera de muestra)", f"{benchmark:.4f}"))
        rows.append(("Ventanas de validación", str(metrics.get("oos_windows", 0))))

    if "shrinkage" in metrics:
        rows.append(("Estimación robusta (shrinkage)", str(metrics["shrinkage"])))
    if metrics.get("n_obs"):
        rows.append(("Observaciones usadas", str(metrics["n_obs"])))

    return rows


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
            "Sharpe 'fuera de muestra' proviene de una validación walk-forward y es la "
            "referencia relevante. Este reporte es de carácter informativo y no "
            "constituye asesoramiento financiero. Los resultados pasados no garantizan "
            "rendimientos futuros."
        ),
    )

    return bytes(pdf.output())
