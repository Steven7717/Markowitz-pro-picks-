# tests/test_macro_fase.py
from datetime import date

import pandas as pd
import pytest

from macro.fase import Fase, determinar, fases_por_mes, motivo_para_no_inclinar


def _serie(valores, desde="2026-01"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


@pytest.mark.parametrize(
    "valores, clave",
    [
        ([100.5, 100.6, 100.7, 100.8], "expansion"),
        ([101.0, 100.9, 100.8, 100.7], "desaceleracion"),
        ([99.0, 99.1, 99.2, 99.3], "recuperacion"),
        ([99.5, 99.4, 99.3, 99.2], "contraccion"),
    ],
)
def test_las_cuatro_fases(valores, clave):
    fase = determinar(_serie(valores))
    assert fase.clave == clave
    assert fase.motivo is None


def test_en_100_exacto_cuenta_como_por_encima():
    assert determinar(_serie([99.7, 99.8, 99.9, 100.0])).clave == "expansion"


def test_un_giro_del_ultimo_mes_contra_la_tendencia_es_indeterminado():
    # Sube en tres meses (100.0 → 100.4) pero el último mes baja.
    fase = determinar(_serie([100.0, 100.3, 100.5, 100.4]))
    assert fase.clave is None
    assert fase.motivo == "indeterminada"


def test_un_cambio_a_tres_meses_nulo_es_indeterminado():
    fase = determinar(_serie([100.2, 100.1, 100.3, 100.2]))
    assert fase.clave is None and fase.motivo == "indeterminada"


def test_un_ultimo_mes_plano_no_contradice():
    """Enmienda 4: plano no es «en contra»."""
    assert determinar(_serie([100.0, 100.2, 100.4, 100.4])).clave == "expansion"


def test_serie_corta():
    fase = determinar(_serie([100.0, 100.1, 100.2]))
    assert fase.clave is None and fase.motivo == "serie_corta"
    assert fase.meses_en_fase == 0


def test_lleva_mes_nivel_y_cambio():
    fase = determinar(_serie([100.5, 100.6, 100.7, 100.8]))
    assert fase.mes_dato == date(2026, 4, 1)
    assert fase.nivel == pytest.approx(100.8)
    assert fase.cambio == pytest.approx(0.3)


def test_meses_en_fase_cuenta_los_seguidos():
    # Contracción en marzo y abril de 2026; recuperación de mayo a julio.
    valores = [100.4, 100.2, 99.9, 99.6, 99.4, 99.5, 99.7, 99.9, 99.95, 99.97]
    fase = determinar(_serie(valores))
    assert fase.clave == "recuperacion"
    assert fase.meses_en_fase == 4


def test_fases_por_mes_deja_none_donde_no_hay_regla():
    por_mes = fases_por_mes(_serie([100.5, 100.6, 100.7, 100.8, 100.9]))
    assert list(por_mes.iloc[:3]) == [None, None, None]
    assert list(por_mes.iloc[3:]) == ["expansion", "expansion"]


def test_un_nan_dentro_de_la_ventana_deja_la_serie_con_huecos():
    # Falta t-1: «hace un mes» no puede ser el dato de hace dos.
    fase = determinar(_serie([100.5, 100.6, 100.7, float("nan"), 100.8]))
    assert fase.clave is None and fase.motivo == "serie_con_huecos"
    assert fase.mes_dato == date(2026, 5, 1)
    assert fase.meses_en_fase == 0


def test_un_nan_en_t_menos_3_deja_la_serie_con_huecos():
    fase = determinar(_serie([100.5, 100.6, float("nan"), 100.7, 100.8, 100.9]))
    assert fase.motivo == "serie_con_huecos"


def test_un_nan_fuera_de_la_ventana_no_estorba():
    serie = _serie([100.5, float("nan"), 100.6, 100.7, 100.8, 100.9])
    # t = junio, t-3 = marzo; febrero (NaN) queda fuera de la ventana.
    assert determinar(serie).clave == "expansion"


def test_un_mes_ausente_del_indice_se_lee_por_calendario():
    indice = pd.to_datetime(
        ["2026-01-01", "2026-02-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
    )
    serie = pd.Series([100.5, 100.6, 100.7, 100.8, 100.9, 101.0], index=indice)
    fase = determinar(serie)
    # t-3 = junio: existe, así que hay fase, y la racha son 1 mes (t-1..t-3 existen,
    # pero antes de septiembre solo agosto y julio tienen t-3 en la rejilla).
    assert fase.clave == "expansion"
    assert fase.mes_dato == date(2026, 9, 1)
    assert fase.cambio == pytest.approx(0.3)
    assert fase.meses_en_fase == 1


def test_un_mes_ausente_entre_t_y_t_menos_3_son_huecos():
    indice = pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-05-01"])
    serie = pd.Series([100.5, 100.6, 100.7, 100.8], index=indice)
    fase = determinar(serie)
    assert fase.motivo == "serie_con_huecos"


def test_indices_duplicados_no_cuentan_doble():
    serie = _serie([100.5, 100.6, 100.7, 100.8, 100.9])
    duplicada = pd.concat([serie, serie.iloc[-1:]])
    assert determinar(duplicada).meses_en_fase == determinar(serie).meses_en_fase == 2


def test_serie_desordenada_da_lo_mismo():
    serie = _serie([100.5, 100.6, 100.7, 100.8, 100.9])
    assert determinar(serie.iloc[::-1]) == determinar(serie)


def test_inf_no_se_toma_como_dato():
    serie = _serie([100.5, 100.6, 100.7, 100.8, float("inf")])
    fase = determinar(serie)
    # El último mes con dato es abril; mayo (inf) no existe.
    assert fase.mes_dato == date(2026, 4, 1)
    assert fase.nivel == pytest.approx(100.8)
    assert fase.clave == "expansion"


def test_inf_dentro_de_la_ventana_son_huecos():
    serie = _serie([100.5, 100.6, 100.8, float("inf"), 100.9])
    assert determinar(serie).motivo == "serie_con_huecos"


def test_acepta_fechas_a_mitad_de_mes():
    indice = pd.to_datetime(["2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15"])
    serie = pd.Series([100.5, 100.6, 100.7, 100.8], index=indice)
    assert determinar(serie).clave == "expansion"


def test_no_se_inclina_sin_fase():
    fase = Fase(None, "indeterminada", date(2026, 10, 1), 100.0, 0.0, 0)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) == "indeterminada"


def test_no_se_inclina_con_un_dato_de_hace_mas_de_tres_meses():
    fase = Fase("expansion", None, date(2026, 7, 1), 100.8, 0.3, 5)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) == "dato_rancio"


def test_tres_meses_justos_aun_valen():
    fase = Fase("expansion", None, date(2026, 8, 1), 100.8, 0.3, 5)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) is None
