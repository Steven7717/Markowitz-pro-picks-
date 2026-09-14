import numpy as np
import pandas as pd
import pytest

from fundamentals.concepts import (
    CONCEPTOS,
    LINEAS,
    completar_bpa_por_identidad,
    reconciliar_recuento_de_acciones,
    resolve_lines,
)


def _panel(columnas: dict[str, list[float]], n: int = 1) -> pd.DataFrame:
    fechas = pd.date_range("2025-03-31", periods=n, freq="QE")
    return pd.DataFrame(columnas, index=fechas)


def test_the_first_concept_in_the_chain_wins():
    panel = _panel({"Revenues": [100.0], "SalesRevenueNet": [999.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 100.0


def test_a_later_concept_is_used_when_the_first_is_absent():
    """Apple no declara 'Revenues'; usa la etiqueta larga de ingresos por contrato."""
    panel = _panel({"RevenueFromContractWithCustomerExcludingAssessedTax": [250.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 250.0


def test_a_concept_present_but_entirely_empty_loses_to_the_next_in_the_chain():
    """JPMorgan dejo de etiquetar Revenues trimestral en 2014.

    En una ventana reciente la columna existe y esta vacia. Quedarse con ella
    dejaria al banco sin ingresos teniendolos bajo otra etiqueta.
    """
    panel = _panel({"Revenues": [np.nan], "SalesRevenueNet": [77.0]})
    lineas, _ = resolve_lines(panel)
    assert lineas["ingresos"].iloc[0] == 77.0


def test_a_line_with_no_matching_concept_is_missing_not_zero():
    """Un 0 en ingresos se lee como 'no vendio nada'. Ausente, como 'no lo declara'."""
    panel = _panel({"Revenues": [100.0]})
    lineas, ausentes = resolve_lines(panel)
    assert np.isnan(lineas["beneficio_neto"].iloc[0])
    assert "beneficio_neto" in ausentes


def test_present_lines_are_not_reported_as_missing():
    panel = _panel({"Revenues": [100.0]})
    _, ausentes = resolve_lines(panel)
    assert "ingresos" not in ausentes


def test_every_line_appears_as_a_column_even_when_absent():
    """Un panel con columnas variables segun la empresa no se puede concatenar."""
    panel = _panel({"Revenues": [100.0]})
    lineas, _ = resolve_lines(panel)
    assert sorted(lineas.columns) == sorted(LINEAS)


def test_the_period_index_is_preserved():
    """El calculo interanual usa shift(4) sobre este indice."""
    panel = _panel({"Revenues": [1.0, 2.0, 3.0]}, n=3)
    lineas, _ = resolve_lines(panel)
    assert list(lineas.index) == list(panel.index)


def test_an_empty_panel_yields_an_empty_frame_with_every_column():
    lineas, ausentes = resolve_lines(pd.DataFrame())
    assert lineas.empty
    assert sorted(ausentes) == sorted(LINEAS)


def test_no_line_declares_an_empty_chain():
    """Una cadena vacia haria que la linea nunca se resuelva, en silencio."""
    assert all(len(cadena) > 0 for cadena in LINEAS.values())


def test_the_concept_set_covers_every_chain():
    """panel.py filtra por este conjunto; una omision vaciaria la linea entera."""
    from fundamentals.concepts import _aplanar

    for cadena in LINEAS.values():
        for entrada in cadena:
            assert set(_aplanar(entrada)) <= CONCEPTOS


def test_a_split_line_is_recovered_by_summing_its_parts():
    """76 emisores etiquetan depreciacion y amortizacion por separado.

    Sin sumarlas, el EBITDA de esas empresas no se puede calcular, y con el se
    caen deuda_neta_ebitda y ev_ebitda.
    """
    panel = _panel({"Depreciation": [30.0], "AmortizationOfIntangibleAssets": [20.0]})
    lineas, ausentes = resolve_lines(panel)
    assert lineas["depreciacion_amortizacion"].iloc[0] == 50.0
    assert "depreciacion_amortizacion" not in ausentes


def test_a_split_line_with_one_part_missing_stays_missing():
    """Sumar solo una mitad subestima el importe y parece un dato completo."""
    panel = _panel({"Depreciation": [30.0]})
    lineas, ausentes = resolve_lines(panel)
    assert np.isnan(lineas["depreciacion_amortizacion"].iloc[0])
    assert "depreciacion_amortizacion" in ausentes


def test_the_combined_tag_wins_over_the_summed_parts():
    panel = _panel(
        {
            "DepreciationDepletionAndAmortization": [99.0],
            "Depreciation": [30.0],
            "AmortizationOfIntangibleAssets": [20.0],
        }
    )
    lineas, _ = resolve_lines(panel)
    assert lineas["depreciacion_amortizacion"].iloc[0] == 99.0


def test_operating_income_does_not_fall_back_to_pretax_income():
    """El beneficio antes de impuestos ya tiene los intereses restados.

    Usarlo como alternativa subiria la cobertura de 13 a 17 de 20 empresas, pero
    haria que la cobertura de intereses fuese el cociente de otra magnitud.
    """
    assert LINEAS["beneficio_operativo"] == ("OperatingIncomeLoss",)


# ── La cadena se resuelve fila a fila ─────────────────────────────────────────

def test_the_chain_is_resolved_quarter_by_quarter_not_once_for_the_panel():
    """CPRT dejo de etiquetar StockholdersEquity tras su ejercicio 2023.

    Con la cadena fijada una sola vez para todo el panel, el concepto preferido
    gana por tener dato en los trimestres viejos y la linea queda vacia justo en
    los cuatro que puntuan, aunque la variante posterior si traiga cifra. Medido
    sobre las 502 empresas de la caches: 233 con al menos una linea vacia en la
    ventana de 4T teniendo dato un concepto posterior de su cadena.
    """
    panel = _panel(
        {
            "StockholdersEquity": [10.0, 20.0, np.nan, np.nan],
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest":
                [np.nan, np.nan, 30.0, 40.0],
        },
        n=4,
    )
    lineas, ausentes = resolve_lines(panel)
    assert list(lineas["patrimonio_neto"]) == [10.0, 20.0, 30.0, 40.0]
    assert "patrimonio_neto" not in ausentes


def test_the_preferred_concept_still_wins_in_the_quarters_where_it_has_data():
    """Fila a fila no quiere decir el que mas datos tenga: sigue mandando el orden."""
    panel = _panel(
        {"Revenues": [100.0, np.nan], "SalesRevenueNet": [999.0, 777.0]}, n=2
    )
    lineas, _ = resolve_lines(panel)
    assert list(lineas["ingresos"]) == [100.0, 777.0]


def test_a_split_line_falls_back_row_by_row_when_one_part_is_missing():
    """La regla de la tupla —o todas sus partes o ninguna— es ahora por fila.

    Un trimestre sin la mitad de amortizacion no puede invalidar los otros tres,
    y una suma a medias en ese trimestre subestimaria el EBITDA sin avisar.
    """
    panel = _panel(
        {
            "Depreciation": [30.0, 30.0],
            "AmortizationOfIntangibleAssets": [20.0, np.nan],
        },
        n=2,
    )
    lineas, _ = resolve_lines(panel)
    assert lineas["depreciacion_amortizacion"].iloc[0] == 50.0
    assert np.isnan(lineas["depreciacion_amortizacion"].iloc[1])


def test_a_line_whose_chain_is_empty_in_every_quarter_is_still_reported_missing():
    panel = _panel({"Revenues": [np.nan, np.nan]}, n=2)
    _, ausentes = resolve_lines(panel)
    assert "ingresos" in ausentes


# ── Reconciliación del recuento de acciones ───────────────────────────────────

def _con_acciones(acciones, beneficio=1000.0, bpa=2.0, n=1):
    return pd.DataFrame(
        {
            "acciones_diluidas": [acciones] * n,
            "beneficio_neto": [beneficio] * n,
            "bpa_diluido": [bpa] * n,
        },
        index=pd.date_range("2025-03-31", periods=n, freq="QE"),
    )


def _serie(acciones, beneficios=None, bpas=None):
    """Una serie de trimestres con la identidad cuadrada salvo donde se diga."""
    n = len(acciones)
    if bpas is None:
        bpas = [2.0] * n
    if beneficios is None:
        beneficios = [a * b for a, b in zip(acciones, bpas)]
    return pd.DataFrame(
        {
            "acciones_diluidas": list(acciones),
            "beneficio_neto": list(beneficios),
            "bpa_diluido": list(bpas),
        },
        index=pd.date_range("2023-09-30", periods=n, freq="QE"),
    )


def test_a_share_count_declared_in_millions_is_brought_back_to_shares():
    """McDonald's etiqueta el recuento en millones con unidad 'shares'.

    717,6 en vez de 717.600.000 multiplica por 1e-6 la capitalizacion, y con
    ella los doce trimestres de precio/FCF y precio/valor en libros. La unidad
    del hecho no lo dice —pone 'shares' igual—, pero la identidad contable si:
    beneficio neto entre BPA diluido son las acciones, por definicion.
    """
    # La identidad pide 1000e6 / 2 = 500 millones de acciones; el emisor
    # declara "500", que son esos mismos 500 millones escritos en millones.
    lineas = _con_acciones(500.0, beneficio=1000e6, bpa=2.0)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["acciones_diluidas"].iloc[0] == pytest.approx(500e6)


def test_a_share_count_already_in_shares_is_left_alone():
    lineas = _con_acciones(500e6, beneficio=1000e6, bpa=2.0)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["acciones_diluidas"].iloc[0] == pytest.approx(500e6)


def test_only_scales_that_are_an_exact_power_of_a_thousand_are_corrected():
    """Un REIT declara el beneficio del grupo y el BPA del comun: el cociente no
    son sus acciones y sale un 20% desviado. Reescalar por 1,2 seria inventarse
    un dato; ahi el numero se deja como esta."""
    lineas = _con_acciones(500e6, beneficio=1200e6, bpa=2.0)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["acciones_diluidas"].iloc[0] == pytest.approx(500e6)


def test_the_scale_is_decided_quarter_by_quarter():
    """McDonald's cambio de escala a mitad de la serie: 731.600.000 un trimestre
    y 725,9 el siguiente. Una correccion por empresa se comeria la mitad buena."""
    lineas = pd.DataFrame(
        {
            "acciones_diluidas": [500e6, 500.0],
            "beneficio_neto": [1000e6, 1000e6],
            "bpa_diluido": [2.0, 2.0],
        },
        index=pd.date_range("2025-03-31", periods=2, freq="QE"),
    )
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert list(corregidas["acciones_diluidas"]) == pytest.approx([500e6, 500e6])


def test_a_quarter_without_the_identity_keeps_its_share_count_untouched():
    """Sin beneficio o sin BPA no hay con que contrastar. Tocar el numero a
    ciegas seria peor que dejarlo: el dato entraria cambiado y sin motivo."""
    lineas = _con_acciones(500.0, beneficio=np.nan)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["acciones_diluidas"].iloc[0] == pytest.approx(500.0)
    assert np.isnan(
        reconciliar_recuento_de_acciones(_con_acciones(500.0, bpa=np.nan))
        ["bpa_diluido"].iloc[0]
    )


def test_a_bpa_rounded_to_zero_never_triggers_a_rescale():
    """El BPA se declara al centimo. Por debajo, el cociente es ruido dividido
    por redondeo y podria fabricar un factor de mil de la nada."""
    # Sin la guarda el cociente seria 1000/0,001/500 = 2000, que redondea a un
    # factor de mil y multiplicaria por mil un recuento que estaba bien.
    lineas = _con_acciones(500.0, beneficio=1000.0, bpa=0.001)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["acciones_diluidas"].iloc[0] == pytest.approx(500.0)


def test_the_correction_leaves_every_other_line_untouched():
    lineas = _con_acciones(500.0, beneficio=1000e6, bpa=2.0)
    corregidas = reconciliar_recuento_de_acciones(lineas)
    assert corregidas["beneficio_neto"].iloc[0] == 1000e6
    assert sorted(corregidas.columns) == sorted(lineas.columns)


def test_the_correction_survives_an_empty_frame():
    assert reconciliar_recuento_de_acciones(pd.DataFrame()).empty


# ── La corrección de escala nunca divide ──────────────────────────────────────

def test_the_rescale_never_divides_the_share_count():
    """La regresion de HAL: la identidad tiene dos incognitas y el codigo
    culpaba siempre a las acciones.

    HAL declaro 902.000.000 acciones en 2023-09-30 —correctas— junto a un BPA
    diluido de 790000,0, que es el hecho de la SEC mal escalado: el BPA real fue
    0,79 $. La identidad daba 906 acciones implicitas, un cociente de 1,0e-6 y
    un factor de 1e-6, asi que el recuento acababa en 902 acciones y el
    precio/valor en libros de HAL caia de 1,70 a 0,00. Una escala mal declarada
    hace el numero mas pequeno de lo que es, nunca mas grande: dividir no es una
    correccion posible.
    """
    lineas = _con_acciones(902e6, beneficio=716e6, bpa=790000.0)
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["acciones_diluidas"].iloc[0] == pytest.approx(902e6)


def test_a_broken_bpa_is_dropped_instead_of_wrecking_the_share_count():
    """Cuando la identidad no cuadra y la serie de la empresa le da la razon al
    recuento, quien miente es el BPA. Ese BPA tampoco se puede dejar: sumado al
    TTM pone un PER de casi cero en los cuatro trimestres que lo contienen."""
    lineas = _serie(
        [900e6, 900e6, 900e6, 900e6],
        beneficios=[716e6, 1800e6, 1800e6, 1800e6],
        bpas=[790000.0, 2.0, 2.0, 2.0],
    )
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["acciones_diluidas"].iloc[0] == pytest.approx(900e6)
    assert np.isnan(reconciliadas["bpa_diluido"].iloc[0])
    assert list(reconciliadas["bpa_diluido"].iloc[1:]) == pytest.approx([2.0, 2.0, 2.0])


# ── La banda deja de ser el único juez ────────────────────────────────────────

def test_a_thousandfold_error_is_corrected_even_when_the_quotient_misses_the_band():
    """El falso negativo de ECHO: la misma empresa, el mismo error de mil,
    corregido en cuatro trimestres y no en el quinto.

    El cociente implicito de ECHO en 2023-09-30 era 858,3 —un 14,2% por debajo
    del 1000— y la banda de ±10% lo rechazaba, mientras que el 988,7 del
    trimestre siguiente si pasaba. Con la serie de la empresa delante no hay
    duda: 271.245 acciones contra una base de 286.500.000 es el mismo error de
    mil que los otros cuatro trimestres.
    """
    lineas = _serie(
        [271_245.0, 271_500.0, 286.5e6, 288.1e6],
        beneficios=[232.8e6, 268.4e6, 285.4e6, 288.1e6],
        bpas=[1.0, 1.0, 1.0, 1.0],
    )
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["acciones_diluidas"].iloc[0] == pytest.approx(271.245e6)
    assert reconciliadas["acciones_diluidas"].iloc[1] == pytest.approx(271.5e6)


# ── La base del recuento se contrasta contra la serie de la empresa ───────────

def test_a_share_count_far_from_the_company_series_is_dropped_not_kept():
    """La guarda [½,2]× medía contra el acumulado del informe, no contra la
    serie, y dejaba pasar 44 celdas absurdas en 17 empresas.

    BKNG declaro 794.000.000 acciones en un trimestre contra una base de unos
    33.000.000: no es un error de escala —no es una potencia de mil— y no se
    puede reparar. Multiplicarla por el precio da una capitalizacion que no es
    de nadie, asi que la celda se declara ausente.
    """
    lineas = _serie([33e6, 33e6, 794e6, 33e6])
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert np.isnan(reconciliadas["acciones_diluidas"].iloc[2])
    assert list(reconciliadas["acciones_diluidas"].iloc[[0, 1, 3]]) == pytest.approx(
        [33e6, 33e6, 33e6]
    )


def test_a_buyback_sized_drift_is_not_mistaken_for_a_broken_base():
    """Una empresa recompra o emite unos puntos por trimestre. Tres anos de eso
    mueven el recuento sin que la base cambie, y confundirlo con un desajuste de
    base costaria la capitalizacion de una empresa sana."""
    lineas = _serie([100e6, 97e6, 94e6, 91e6, 88e6, 85e6])
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["acciones_diluidas"].notna().all()


def test_the_base_is_anchored_on_the_most_recent_quarters_not_on_the_majority():
    """El precio viene ajustado hacia atras por los splits, o sea en la base mas
    reciente. La mayoria de la serie puede seguir en la base vieja —BKNG tiene
    ocho trimestres antes del split y cuatro despues— y son los cuatro nuevos
    los que casan con el precio, no los ocho viejos.
    """
    lineas = _serie([33e6] * 8 + [794e6] * 4)
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["acciones_diluidas"].iloc[:8].isna().all()
    assert list(reconciliadas["acciones_diluidas"].iloc[8:]) == pytest.approx([794e6] * 4)


def test_a_quarter_on_an_unknown_base_loses_its_bpa_too():
    """Un BPA anterior al split esta en la misma base que su recuento, y el
    precio no. Dejarlo dentro del TTM es lo que le daba a Booking Holdings el
    unico PER por debajo de 3 de todo el panel."""
    lineas = _serie(
        [33e6] * 8 + [794e6] * 4,
        beneficios=[1000e6] * 12,
        bpas=[30.3] * 8 + [1.26] * 4,
    )
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert reconciliadas["bpa_diluido"].iloc[:8].isna().all()
    assert list(reconciliadas["bpa_diluido"].iloc[8:]) == pytest.approx([1.26] * 4)


def test_a_company_that_never_reports_a_share_count_keeps_its_bpa():
    """Visa, Berkshire y otras catorce no etiquetan el recuento diluido. Sin
    recuento no hay base que contrastar, y quedarse sin BPA por eso les quitaria
    el PER a empresas cuyo dato esta perfectamente bien."""
    lineas = pd.DataFrame(
        {
            "acciones_diluidas": [np.nan] * 4,
            "beneficio_neto": [1000e6] * 4,
            "bpa_diluido": [2.0, 2.1, 2.2, 2.3],
        },
        index=pd.date_range("2023-09-30", periods=4, freq="QE"),
    )
    reconciliadas = reconciliar_recuento_de_acciones(lineas)
    assert list(reconciliadas["bpa_diluido"]) == pytest.approx([2.0, 2.1, 2.2, 2.3])


# ── El BPA que falta, desde la identidad ──────────────────────────────────────

def test_a_missing_bpa_is_recovered_from_the_identity():
    """HAL no declara su cuarto trimestre suelto y su 10-K no trae una ventana
    de doce meses de BPA, asi que el trimestre queda vacio. Con `min_periods=4`
    ese hueco cuesta cuatro trimestres de PER, no uno, y a quien nunca declara
    su Q4 le cuesta el multiplo para siempre.
    """
    lineas = _serie(
        [900e6] * 4,
        beneficios=[1800e6, 1800e6, 660e6, 1800e6],
        bpas=[2.0, 2.0, np.nan, 2.0],
    )
    completadas = completar_bpa_por_identidad(lineas)
    assert completadas["bpa_diluido"].iloc[2] == pytest.approx(660e6 / 900e6)


def test_the_identity_is_only_used_where_the_company_has_proved_it_holds():
    """El beneficio neto no es el del comun cuando hay preferentes o
    minoritarios: en un REIT la identidad se desvia un 20-30%. Rellenar a ciegas
    ahi inventa un BPA. Solo se rellena donde la propia empresa ha ensenado, en
    los trimestres que si declara, que la identidad la describe.
    """
    lineas = _serie(
        [900e6] * 4,
        beneficios=[1800e6, 1800e6, 1800e6, 1800e6],
        bpas=[1.4, 1.4, np.nan, 1.4],  # la identidad daria 2,0: un 43% de error
    )
    completadas = completar_bpa_por_identidad(lineas)
    assert np.isnan(completadas["bpa_diluido"].iloc[2])


def test_a_company_that_never_reports_bpa_is_not_given_one():
    """Monster, Visa y otras catorce no etiquetan el BPA diluido. Fabricarselo
    desde la identidad les daria un PER que la empresa no publica y que nada ha
    podido contrastar."""
    lineas = _serie([900e6] * 4, beneficios=[1800e6] * 4, bpas=[np.nan] * 4)
    completadas = completar_bpa_por_identidad(lineas)
    assert completadas["bpa_diluido"].isna().all()


def test_a_declared_bpa_is_never_overwritten():
    """El hecho declarado manda sobre el estimado, siempre."""
    lineas = _serie([900e6] * 4, beneficios=[1800e6] * 4, bpas=[2.0, 2.0, 1.9, 2.0])
    completadas = completar_bpa_por_identidad(lineas)
    assert completadas["bpa_diluido"].iloc[2] == pytest.approx(1.9)


def test_completing_the_bpa_survives_an_empty_frame():
    assert completar_bpa_por_identidad(pd.DataFrame()).empty
