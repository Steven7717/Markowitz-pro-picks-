import io
import pandas as pd
import openpyxl
from fpdf import FPDF

from exporter import kpi_rows, texto_pdf, to_excel, to_pdf


def _weights_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "GOOGL"],
        "Peso Óptimo (%)": ["50.00%", "30.00%", "20.00%"],
        "Retorno Esperado (%)": ["21.00%", "18.00%", "17.00%"],
        "Volatilidad (%)": ["22.00%", "19.00%", "20.00%"],
        "Contrib. Riesgo (%)": ["48.00%", "32.00%", "20.00%"],
    })


def _metrics() -> dict:
    return {
        "sharpe": 1.42,
        "annual_return": 0.183,
        "annual_vol": 0.128,
        "rf_rate": 0.0525,
        "horizon": "1 Mes",
    }


def test_to_excel_returns_bytes():
    result = to_excel(_weights_df(), _metrics())
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_to_excel_has_pesos_sheet():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    assert "Pesos" in wb.sheetnames


def test_to_excel_has_metricas_sheet():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    assert "Métricas" in wb.sheetnames


def test_to_excel_pesos_sheet_row_count():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    ws = wb["Pesos"]
    # 1 header + 3 data rows
    assert ws.max_row == 4


def test_to_excel_pesos_first_column_header():
    wb = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    ws = wb["Pesos"]
    assert ws.cell(1, 1).value == "Ticker"


# ── Reported metrics must not hide the validation result ──────────────────────

from exporter import kpi_rows


def _validated_metrics() -> dict:
    return {**_metrics(), "oos_sharpe": 0.61, "oos_equal_weight_sharpe": 0.74, "oos_windows": 9}


def _labels(metrics: dict) -> list[str]:
    return [label for label, _ in kpi_rows(metrics)]


def test_kpi_rows_label_the_sharpe_as_in_sample():
    assert any("muestra" in label.lower() for label in _labels(_validated_metrics()))


def test_kpi_rows_include_the_out_of_sample_sharpe():
    rows = dict(kpi_rows(_validated_metrics()))
    assert any("0.61" in value for value in rows.values())


def test_kpi_rows_include_the_equal_weight_benchmark():
    rows = dict(kpi_rows(_validated_metrics()))
    assert any("0.74" in value for value in rows.values())


def test_kpi_rows_say_so_when_validation_did_not_run():
    rows = dict(kpi_rows(_metrics()))
    assert any("no disponible" in value.lower() for value in rows.values())


def test_kpi_rows_accept_a_metrics_dict_without_the_new_fields():
    assert len(kpi_rows(_metrics())) > 0


def test_kpi_rows_name_the_strategy_that_produced_the_weights():
    rows = dict(kpi_rows({**_validated_metrics(), "strategy": "Paridad de riesgo (ERC)"}))
    assert any("Paridad de riesgo" in v for v in rows.values())


def test_to_pdf_returns_bytes_for_validated_metrics():
    from exporter import to_pdf
    result = to_pdf(_weights_df(), _validated_metrics(), [])
    assert isinstance(result, bytes)
    assert len(result) > 0


# ── El PDF en castellano ──────────────────────────────────────────────────────
#
# El informe estaba escrito en un castellano sin tildes --«Metricas», «Optimo»,
# «desempeno»-- y lo parecia una limitacion de fpdf2. No lo es: Helvetica es una
# fuente del nucleo del PDF y su codificacion es latin-1, que lleva las tildes,
# la enye y los signos de apertura sin problema. Lo unico que no cabe ahi son
# tres caracteres que el castellano no necesita, y para esos hay un sustituto.

def test_las_etiquetas_del_informe_llevan_tildes():
    completas = _metrics() | {"oos_sharpe": 1.1, "shrinkage": "Sí"}
    etiquetas = [e for e, _ in kpi_rows(completas)]
    assert "Retorno Anual Esperado (aritmético)" in etiquetas
    assert "Ventanas de validación" in etiquetas
    assert "Estimación robusta (shrinkage)" in etiquetas


def test_helvetica_acepta_de_verdad_el_castellano():
    """La comprobación que faltaba antes de rendirse: no era una limitación."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, "Métricas del Portafolio Óptimo · ¿desempeño? «sí» ±1")
    assert len(bytes(pdf.output())) > 0


def test_una_raya_larga_no_puede_tumbar_el_informe():
    """`—`, `“”` y `€` no caben en latin-1 y lanzaban una excepción.

    Los textos del informe vienen en parte de fuera —la etiqueta de la
    estrategia, los nombres de las columnas— así que basta con que alguien
    escriba una raya larga en cualquiera de ellos para que la descarga entera
    reviente en vez de sacar el PDF.
    """
    assert texto_pdf("aquí — allá “eso” 5€") == 'aquí - allá "eso" 5 EUR'


def test_el_informe_sale_aunque_le_metan_caracteres_imposibles():
    df = _weights_df().rename(columns={"Ticker": "Ticker — símbolo"})
    datos = to_pdf(df, _metrics() | {"strategy": "Prueba “rara” —"}, [])
    assert datos.startswith(b"%PDF")
