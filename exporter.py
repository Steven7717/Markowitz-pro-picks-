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
