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
    rows = dict(kpi_rows({**_validated_metrics(), "strategy": "Paridad de riesgo"}))
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
    assert "Estimación robusta" in etiquetas


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


# ── R5 y R6 · El informe es el documento que el usuario enseña a terceros ─────
#
# Con las métricas reales de `portafolios/2026-09-10-105238-prueba-1.json` el
# informe imprimía «Sharpe fuera de muestra 2.2389» con cuatro decimales sobre
# un número cuyo propio fichero guarda un error estándar de ±2,10, sin una
# palabra del veredicto contra repartir por igual y sin decir que los pesos de
# la tabla de al lado no están identificados. Las tres cosas caben.

from exporter import notas_pdf  # noqa: E402

# Copiadas del fichero, tal cual, incluido el `beats_equal_weight` nulo y la
# ausencia de `oos_gap_stderr`: es un portafolio guardado antes de que el
# programa midiera el error de la diferencia, y el informe tiene que salir.
_REALES = {
    "sharpe": 1.8593187647949108,
    "annual_return": 0.5414827645535594,
    "annual_vol": 0.2698863723109198,
    "rf_rate": 0.03967796815344062,
    "horizon": "1 Mes",
    "strategy": "Máximo Sharpe (Markowitz)",
    "n_obs": 501.0,
    "oos_sharpe": 2.2389269445873863,
    "oos_equal_weight_sharpe": 2.0706922569408923,
    "oos_windows": 4.0,
    "oos_sharpe_stderr": 2.101918203407456,
    "beats_equal_weight": None,
}

_MEDICION_PESOS = {
    "ident_mejor": "MSFT",
    "ident_peor": "AMZN",
    "ident_brecha": 0.21,
    "ident_stderr": 0.31,
    "ident_anos": 2.0,
}


def test_el_sharpe_fuera_de_muestra_no_se_imprime_a_cuatro_decimales():
    """«2.2389» promete una precisión de 1 entre 10.000 sobre un ±2,10."""
    valor = dict(kpi_rows(_REALES))["Sharpe fuera de muestra"]
    assert "2.2389" not in valor
    assert "2.24" in valor


def test_el_sharpe_fuera_de_muestra_lleva_la_barra_que_el_fichero_ya_guardaba():
    valor = dict(kpi_rows(_REALES))["Sharpe fuera de muestra"]
    assert "±" in valor and "2.10" in valor


def test_el_informe_escribe_el_veredicto_contra_repartir_por_igual():
    assert "ndistinguible de repartir por igual" in " ".join(notas_pdf(_REALES))


def test_un_fichero_sin_el_error_de_la_diferencia_dice_que_no_se_recomprueba():
    """El veredicto guardado se enseña, pero marcado como no recomprobable."""
    assert "recomprobar" in " ".join(notas_pdf(_REALES))


def test_con_el_error_de_la_diferencia_el_veredicto_se_vuelve_a_dictar():
    """Y lleva el listón ya multiplicado, no el error estándar suelto."""
    notas = " ".join(notas_pdf({**_REALES, "oos_gap_stderr": 0.05}))
    assert "Supera a repartir por igual" in notas
    assert "0,10" in notas
    assert "recomprobar" not in notas


def test_el_informe_avisa_de_que_los_pesos_de_la_tabla_no_estan_identificados():
    notas = " ".join(notas_pdf({**_REALES, **_MEDICION_PESOS}))
    assert "MSFT" in notas and "AMZN" in notas
    assert "no están identificados" in notas


def test_un_informe_sin_esa_medicion_no_se_inventa_el_aviso():
    """Los portafolios guardados antes de R6 no la llevan, y ahí no se afirma nada."""
    assert not any("identificad" in nota for nota in notas_pdf(_REALES))


def test_el_pdf_sale_entero_con_el_veredicto_y_el_aviso_dentro():
    """Las frases son largas y van en `multi_cell`, no en una celda de 80mm."""
    completas = {**_REALES, **_MEDICION_PESOS, "oos_gap_stderr": 0.9}
    assert len(to_pdf(_weights_df(), completas, [])) > 0


def test_los_recuentos_del_informe_no_llevan_decimales():
    """Un portafolio guardado vuelve con `4.0` ventanas y `501.0` observaciones.

    `cartera._serializable` pasa por `float()` todo lo que no es texto ni
    booleano, y el informe imprimía el decimal. No hay media ventana.
    """
    filas = dict(kpi_rows(_REALES))
    assert filas["Ventanas de validación"] == "4"
    assert filas["Observaciones usadas"] == "501"


# ── La estrategia se guarda por su clave y se traduce AQUÍ ────────────────────
#
# `cartera.Portafolio.estrategia` guarda `max_sharpe` y explica por qué: la
# etiqueta es texto de pantalla y puede reescribirse en cualquier momento, así
# que guardarla ataría un fichero en disco a una decisión de redacción. El
# diccionario `metricas` que viaja al lado esquivaba esa regla y metía la
# etiqueta, y de ahí salía a `portafolios/*.json` y, copiado entero, a
# `libros/*.json`.
#
# No es hipotético: en septiembre de 2026 se le quitó el sufijo «(ERC)» a
# «Paridad de riesgo (ERC)», y cualquier fichero guardado con esa estrategia se
# habría quedado con el texto viejo dentro para siempre.
#
# El informe es el único que lee ese campo, así que la traducción vive aquí,
# con el mismo `.get(clave, clave)` que ya usan `vistas/comparar.py` y
# `vistas/portafolios.py`.

from optimizer import STRATEGY_LABELS  # noqa: E402


def test_el_informe_traduce_la_clave_guardada_a_su_etiqueta():
    """Contra `STRATEGY_LABELS`, nunca contra el texto. Y esto ya se cobró una.

    La primera versión de este test escribía «Paridad de riesgo (ERC)» a mano.
    Lo tumbó `b8ec37b`, que quitó ese sufijo el mismo día — o sea, el cambio de
    redacción del que trata todo este arreglo, cazando de paso al test que lo
    probaba. Un test que copia texto de pantalla tiene el mismo defecto que
    denuncia; el que recorre el diccionario no puede tenerlo.
    """
    for clave, etiqueta in STRATEGY_LABELS.items():
        filas = dict(kpi_rows({**_validated_metrics(), "strategy": clave}))
        assert filas["Estrategia"] == etiqueta
        # Y la clave en crudo no llega al papel, que es la regresión que se
        # evita: el fichero guarda `risk_parity` y el informe no lo imprime.
        assert clave not in filas["Estrategia"]


def test_un_fichero_que_guardo_la_etiqueta_se_sigue_leyendo():
    """La tolerancia, para lo que no pase por la migración.

    `scripts/migrar_metricas_guardadas.py` deja en clave los ficheros de esta
    máquina, pero una copia de seguridad, un portafolio traído de otro sitio o
    un fichero editado a mano pueden seguir trayendo la etiqueta dentro. Un
    valor que no está entre las claves se trata como lo que es: una etiqueta ya
    escrita, que se imprime tal cual. `_REALES` está copiado de un fichero de
    verdad y es exactamente ese caso.
    """
    assert dict(kpi_rows(_REALES))["Estrategia"] == "Máximo Sharpe (Markowitz)"


def test_el_excel_escribe_la_etiqueta_y_no_la_clave():
    """`to_excel` vuelca el diccionario entero, así que traduce igual que el PDF.

    Sin esto, guardar la clave arreglaría el fichero y estropearía la hoja: la
    pestaña «Métricas» pasaría de «Mínima varianza» a «min_variance».
    """
    libro = openpyxl.load_workbook(io.BytesIO(
        to_excel(_weights_df(), {**_metrics(), "strategy": "min_variance"})
    ))
    valores = [c.value for fila in libro["Métricas"].iter_rows() for c in fila]
    assert "Mínima varianza" in valores
    assert "min_variance" not in valores


def test_el_excel_de_un_libro_de_seguimiento_no_gana_una_columna():
    """`vistas/seguimiento.py` pasa por aquí su propio diccionario, sin estrategia.

    La traducción no puede inventarse el campo: la hoja saldría con una columna
    «strategy» vacía que no significa nada.
    """
    libro = openpyxl.load_workbook(io.BytesIO(to_excel(_weights_df(), _metrics())))
    cabecera = [c.value for c in next(libro["Métricas"].iter_rows())]
    assert cabecera == list(_metrics())


# ── Y el de al lado: «Sí»/«No» tampoco es un dato ────────────────────────────
#
# `metrics` escribía `"shrinkage": "Sí" if corrida["shrinkage"] else "No"` --un
# booleano renderizado a castellano-- mientras `Portafolio.shrinkage` guardaba
# el bool de verdad en el MISMO fichero. Es el par exacto de la estrategia,
# encontrado al preguntar «¿dónde más vive esta clase?» en vez de dar el caso
# por cerrado. Cambiar ese «Sí» a «Activada» habría congelado el texto de hoy en
# los ficheros viejos, igual que «(ERC)».

def test_el_informe_escribe_si_y_no_a_partir_del_booleano():
    assert dict(kpi_rows({**_metrics(), "shrinkage": True}))["Estimación robusta"] == "Sí"
    assert dict(kpi_rows({**_metrics(), "shrinkage": False}))["Estimación robusta"] == "No"


def test_el_informe_no_imprime_el_booleano_en_crudo():
    """«True» en un informe que el usuario enseña a terceros no es castellano."""
    for guardado in (True, False):
        valor = dict(kpi_rows({**_metrics(), "shrinkage": guardado}))["Estimación robusta"]
        assert valor not in ("True", "False")


def test_un_fichero_que_guardo_la_palabra_se_sigue_leyendo():
    """La misma tolerancia que la estrategia, por el mismo motivo."""
    for palabra in ("Sí", "No"):
        filas = dict(kpi_rows({**_metrics(), "shrinkage": palabra}))
        assert filas["Estimación robusta"] == palabra


def test_el_shrinkage_apagado_no_desaparece_del_informe():
    """`False` es una respuesta, no una ausencia.

    `kpi_rows` pregunta `if "shrinkage" in metrics` y no por su verdad, que es
    lo correcto y conviene que siga siéndolo: «Estimación robusta: No» dice algo
    sobre la corrida, y callarlo dejaría al lector suponiendo.
    """
    assert "Estimación robusta" in dict(kpi_rows({**_metrics(), "shrinkage": False}))


def test_el_excel_tambien_escribe_la_palabra_y_no_el_booleano():
    libro = openpyxl.load_workbook(io.BytesIO(
        to_excel(_weights_df(), {**_metrics(), "shrinkage": True})
    ))
    valores = [c.value for fila in libro["Métricas"].iter_rows() for c in fila]
    assert "Sí" in valores
    assert True not in valores
