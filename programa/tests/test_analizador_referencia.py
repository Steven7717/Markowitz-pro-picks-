"""La ficha de un ticker frente a su sector, con las funciones del ranking."""

import os
from datetime import date, datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from analizador.referencia import cargar_panel, frente_al_sector
from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import anadir_zscores
from ranking.run import construir_ranking, guardar

SECTORES = {"Information Technology": 6, "Health Care": 6, "Utilities": 5}
TRIMESTRES = ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]


def panel_crudo(semilla: int = 3) -> pd.DataFrame:
    """Un panel con la forma de `salidas/panel.parquet`: KPIs crudos, trimestre y sector."""
    generador = np.random.default_rng(semilla)
    filas, indice = [], []
    for sector, cuantas in SECTORES.items():
        for numero in range(cuantas):
            ticker = f"{sector[:2].upper()}{numero}"
            for trimestre in TRIMESTRES:
                fila = dict(zip(TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))))
                fila["trimestre"] = trimestre
                fila["sector_gics"] = sector
                filas.append(fila)
                indice.append((ticker, pd.Period(trimestre, freq="Q").end_time.normalize()))
    return pd.DataFrame(
        filas, index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"])
    )


def _ranking(crudo):
    """El ranking de siempre sobre el mismo panel, con los z que daría `build_panel`.

    Ordenado antes de los z, como hace `build_panel`: el orden de las filas fija
    el de las sumas, y sin él los z podrían diferir en la última cifra decimal.
    """
    crudo = crudo.sort_index()
    metadatos = crudo["sector_gics"].groupby(level="ticker").last().to_frame("sector_gics")
    con_z = anadir_zscores(crudo.drop(columns="sector_gics"), metadatos)
    with patch("ranking.run.build_panel", return_value=(con_z, metadatos, None)):
        return construir_ranking(con_llm=False, con_valoracion=False, n=5)


def test_un_ticker_del_panel_da_exactamente_su_ficha_de_candidatos():
    crudo = panel_crudo()
    candidata = _ranking(crudo).fichas[0]
    # Barajado porque el panel de prueba ya trae cada sector y trimestre en el
    # orden bueno: sin barajar, nadie notaría que `frente_al_sector` no ordena.
    ref = frente_al_sector(candidata["ticker"], crudo.sample(frac=1, random_state=0))
    for clave in ("sector_gics", "pilares", "destacados", "flojos", "cobertura"):
        assert ref.ficha[clave] == candidata[clave]
    assert ref.compuesto == pytest.approx(candidata["compuesto"])
    assert ref.puesto == candidata["puesto"] == 1
    assert ref.en_panel and ref.exclusion is None


def test_el_puesto_es_el_orden_global_de_las_que_pasan_las_guardas():
    crudo = panel_crudo()
    tabla = _ranking(crudo).tabla
    orden = sorted(tabla.index, key=lambda t: (-tabla.loc[t, "compuesto"], t))
    for ticker in orden[:3] + orden[-2:]:
        ref = frente_al_sector(ticker, crudo)
        assert ref.puesto == orden.index(ticker) + 1
        assert ref.supervivientes == len(tabla)


def _sin(crudo, ticker):
    propias = crudo.xs(ticker, level="ticker").drop(columns="sector_gics")
    return crudo.drop(index=ticker, level="ticker"), propias


def test_insertar_un_ticker_da_lo_mismo_que_si_hubiera_estado_desde_el_principio():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    dentro = frente_al_sector("HE2", crudo)
    insertado = frente_al_sector("HE2", sin_el, sector="Health Care", propias=propias)
    assert insertado.ficha == dentro.ficha
    assert (insertado.puesto, insertado.compuesto) == (dentro.puesto, dentro.compuesto)
    assert dentro.en_panel and not insertado.en_panel


def test_las_filas_posteriores_al_panel_no_entran():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    extra = propias.iloc[[-1]].copy()
    extra.index = pd.DatetimeIndex([pd.Timestamp("2026-09-30")])
    extra["trimestre"] = "2026Q3"
    con_extra = pd.concat([propias, extra])
    assert (
        frente_al_sector("HE2", sin_el, "Health Care", con_extra).ficha
        == frente_al_sector("HE2", sin_el, "Health Care", propias).ficha
    )


def test_una_guarda_que_lo_dejaria_fuera_se_dice_y_no_hay_puesto():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    ref = frente_al_sector("HE2", sin_el, "Health Care", propias.iloc[-2:])
    assert ref.exclusion == "historia_corta"
    assert ref.puesto is None and ref.compuesto is None
    assert ref.ficha["puesto"] is None and ref.ficha["compuesto"] is None


def test_sin_sector_o_sin_filas_no_hay_referencia():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    assert frente_al_sector("HE2", sin_el, None, propias) is None
    assert frente_al_sector("HE2", sin_el, "Health Care", None) is None
    assert frente_al_sector("HE2", sin_el, "Health Care", propias.iloc[0:0]) is None


def test_cargar_panel_lee_lo_que_escribe_guardar(tmp_path):
    crudo = panel_crudo()
    ruta = tmp_path / "panel.parquet"
    crudo.reset_index().to_parquet(ruta, index=False)
    # Una fecha pasada: con la de hoy, devolver `date.today()` también pasaría.
    pasado = datetime(2026, 1, 15, 12, 0).timestamp()
    os.utime(ruta, (pasado, pasado))
    panel, fecha = cargar_panel(ruta)
    assert fecha == date(2026, 1, 15)
    assert frente_al_sector("IN0", panel).ficha == frente_al_sector("IN0", crudo).ficha


def test_el_panel_que_deja_guardar_da_la_misma_ficha(tmp_path):
    # El contrato entre `ranking.run.guardar` y `cargar_panel`, con el fichero
    # que escribe la generación de candidatos y no con uno hecho a mano.
    crudo = panel_crudo()
    resultado = _ranking(crudo)
    guardar(resultado, tmp_path)
    panel, _ = cargar_panel(tmp_path / "panel.parquet")
    ticker = resultado.fichas[0]["ticker"]
    assert frente_al_sector(ticker, panel).ficha == frente_al_sector(ticker, crudo).ficha


def _sin_panel(ruta):
    panel, fecha = cargar_panel(ruta)
    return panel is None and fecha is None


def test_cualquier_fallo_al_leer_el_panel_es_como_si_no_hubiera(tmp_path):
    # pyarrow lanza más que `ValueError` y `OSError` con bytes alterados.
    ruta = tmp_path / "panel.parquet"
    panel_crudo().reset_index().to_parquet(ruta, index=False)
    with patch("pandas.read_parquet", side_effect=KeyError("numpy_type")):
        assert _sin_panel(ruta)


def test_un_periodo_que_no_es_fecha_es_como_si_no_hubiera_panel(tmp_path):
    crudo = panel_crudo().reset_index()
    # Uno distinto por fila: repetidos, los pararía la guarda de duplicados y
    # no la lectura de la fecha.
    crudo["periodo"] = [f"no es una fecha {i}" for i in range(len(crudo))]
    ruta = tmp_path / "panel.parquet"
    crudo.to_parquet(ruta, index=False)
    assert _sin_panel(ruta)


def test_un_panel_vacio_es_como_si_no_hubiera(tmp_path):
    ruta = tmp_path / "panel.parquet"
    panel_crudo().iloc[0:0].reset_index().to_parquet(ruta, index=False)
    assert _sin_panel(ruta)


def test_un_panel_con_filas_repetidas_es_como_si_no_hubiera(tmp_path):
    crudo = panel_crudo().reset_index()
    ruta = tmp_path / "panel.parquet"
    pd.concat([crudo, crudo.iloc[[0]]]).to_parquet(ruta, index=False)
    assert _sin_panel(ruta)


def test_una_columna_de_mas_en_el_panel_se_ignora(tmp_path):
    crudo = panel_crudo()
    ruta = tmp_path / "panel.parquet"
    crudo.assign(comentario="texto").reset_index().to_parquet(ruta, index=False)
    panel, _ = cargar_panel(ruta)
    assert "comentario" not in panel.columns
    assert frente_al_sector("IN0", panel).ficha == frente_al_sector("IN0", crudo).ficha


def test_un_trimestre_como_period_da_la_misma_ficha_que_en_texto():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    como_period = propias.assign(trimestre=pd.PeriodIndex(propias["trimestre"], freq="Q"))
    assert (
        frente_al_sector("HE2", sin_el, "Health Care", como_period).ficha
        == frente_al_sector("HE2", sin_el, "Health Care", propias).ficha
    )


def test_sin_panel_en_disco_no_hay_panel(tmp_path):
    assert cargar_panel(tmp_path / "no_existe.parquet") == (None, None)


def test_un_panel_ilegible_o_sin_una_columna_es_como_si_no_hubiera(tmp_path):
    roto = tmp_path / "roto.parquet"
    roto.write_bytes(b"esto no es parquet")
    assert cargar_panel(roto) == (None, None)
    cojo = tmp_path / "cojo.parquet"
    panel_crudo().drop(columns="sector_gics").reset_index().to_parquet(cojo, index=False)
    assert cargar_panel(cojo) == (None, None)
