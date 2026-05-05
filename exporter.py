import io
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd
from fpdf import FPDF
import plotly.graph_objects as go


def to_excel(weights_df: pd.DataFrame, metrics: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        weights_df.to_excel(writer, sheet_name="Pesos", index=False)
        pd.DataFrame([metrics]).to_excel(writer, sheet_name="Métricas", index=False)
    return buf.getvalue()


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
    pdf.cell(0, 12, "Markowitz Pro Picks", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Fecha: {date.today().strftime('%d/%m/%Y')}  |  Horizonte: {metrics.get('horizon', '-')}",
        ln=True,
        align="C",
    )
    pdf.ln(6)

    # KPI table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Metricas del Portafolio Optimo", ln=True)
    pdf.set_font("Helvetica", "", 10)
    kpis = [
        ("Sharpe Ratio", f"{metrics['sharpe']:.4f}"),
        ("Retorno Anual Esperado", f"{metrics['annual_return']:.2%}"),
        ("Volatilidad Anual", f"{metrics['annual_vol']:.2%}"),
        ("Tasa Libre de Riesgo (anual)", f"{metrics['rf_rate']:.2%}"),
    ]
    for label, value in kpis:
        pdf.cell(100, 7, label, border=1)
        pdf.cell(40, 7, value, border=1, ln=True)
    pdf.ln(4)

    # Weights table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Distribucion de Pesos Optimos", ln=True)
    cols = list(weights_df.columns)
    col_w = 180 // len(cols)
    pdf.set_font("Helvetica", "B", 9)
    for col in cols:
        pdf.cell(col_w, 7, str(col), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for _, row in weights_df.iterrows():
        for val in row:
            pdf.cell(col_w, 6, str(val), border=1)
        pdf.ln()
    pdf.ln(4)

    # Charts
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Graficas", ln=True)
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
        "Este reporte es de caracter informativo y no constituye asesoramiento financiero. "
        "Los resultados pasados no garantizan rendimientos futuros.",
    )

    return bytes(pdf.output())
