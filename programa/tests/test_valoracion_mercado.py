import json

import numpy as np
import pandas as pd
import pytest

from valoracion.mercado import (
    Perfil,
    consenso_desde_estimacion,
    perfil_desde_info,
    regresion_beta,
    tasa_efectiva_desde_estado,
    tasa_libre_desde_cierres,
)

INFO = {
    "currentPrice": 989.04,
    "marketCap": 1_119_022_743_552,
    "currency": "USD",
    "financialCurrency": "USD",
    "industry": "Semiconductors",
    "country": "United States",
    "payoutRatio": 0.02,
    "quoteType": "EQUITY",
    "regularMarketTime": 1_791_835_140,
    "beta": 2.226,
}


def test_el_perfil_lee_lo_que_hace_falta():
    p = perfil_desde_info("MU", INFO)
    assert p.precio == 989.04
    assert p.capitalizacion == 1_119_022_743_552
    assert p.moneda == p.moneda_estados == "USD"
    assert p.industria == "Semiconductors"
    assert p.pais == "United States"
    assert p.payout == 0.02
    assert p.tipo == "EQUITY"
    assert p.hora == "2026-10-12T19:59:00+00:00"


def test_el_perfil_no_tiene_donde_guardar_la_beta_de_yahoo():
    # La beta se calcula con `regresion_beta`, nunca se lee de Yahoo: para
    # WALMEX.MX daba 0,016. La garantía es la forma del tipo, no una promesa; y
    # se busca la palabra en cualquier nombre para que `beta_yahoo` tampoco pase.
    assert not any("beta" in nombre for nombre in Perfil.__dataclass_fields__)


def test_sin_precio_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": None}) is None


def test_el_precio_cae_al_de_mercado_si_falta_el_actual():
    p = perfil_desde_info("X", {**INFO, "currentPrice": None, "regularMarketPrice": 50.0})
    assert p.precio == 50.0


def test_sin_capitalizacion_no_hay_perfil():
    assert perfil_desde_info("X", {**INFO, "marketCap": None}) is None


def test_sin_moneda_no_hay_perfil():
    # Un precio sin moneda no se puede comparar con nada.
    assert perfil_desde_info("X", {**INFO, "currency": None}) is None


def test_la_moneda_de_los_estados_cae_a_la_del_precio():
    p = perfil_desde_info("X", {**INFO, "financialCurrency": None})
    assert p.moneda_estados == "USD"


def test_un_precio_actual_no_numerico_cae_al_de_mercado():
    # NaN es verdadero en Python: `nan or 50.0` se queda con el NaN.
    p = perfil_desde_info("X", {**INFO, "currentPrice": float("nan"), "regularMarketPrice": 50.0})
    assert p.precio == 50.0


def test_una_hora_en_milisegundos_no_rompe_el_perfil():
    # Si Yahoo cambiase la unidad, la hora es lo único que se pierde: el perfil
    # sigue siendo válido y no se cae toda la valoración por una marca de tiempo.
    p = perfil_desde_info("X", {**INFO, "regularMarketTime": 1_791_835_140_000})
    assert p.precio == 989.04
    assert p.hora is None


def test_sin_tipo_de_cotizacion_el_perfil_no_inventa_uno():
    p = perfil_desde_info("X", {**INFO, "quoteType": None})
    assert p.tipo is None


def _cierres(rendimientos: np.ndarray) -> pd.Series:
    fechas = pd.date_range("2024-10-07", periods=len(rendimientos) + 1, freq="W-MON")
    return pd.Series(100 * np.cumprod(np.r_[1.0, 1 + rendimientos]), index=fechas)


def test_la_beta_es_la_pendiente_de_la_regresion():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0.002, 0.02, 104)
    activo = 1.5 * mercado + generador.normal(0, 0.002, 104)
    beta = regresion_beta(_cierres(activo), _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.5, abs=0.05)
    assert beta.r2 > 0.95
    assert beta.semanas == 104
    assert beta.indice == "^GSPC"


def test_con_menos_de_un_ano_no_hay_beta():
    generador = np.random.default_rng(7)
    mercado = generador.normal(0, 0.02, 40)
    assert regresion_beta(_cierres(mercado), _cierres(mercado), "^GSPC") is None


def test_la_beta_tolera_zonas_horarias_distintas():
    generador = np.random.default_rng(3)
    mercado = generador.normal(0, 0.02, 80)
    activo = _cierres(mercado)
    activo.index = activo.index.tz_localize("America/New_York")
    beta = regresion_beta(activo, _cierres(mercado), "^GSPC")
    assert beta.bruta == pytest.approx(1.0)


def test_solo_cuentan_las_ultimas_104_semanas():
    g = np.random.default_rng(5)
    mercado = g.normal(0, 0.02, 150)
    # Las 46 primeras semanas, al revés: si entrasen en la regresión, la beta
    # dejaría de ser 1,5.
    activo = np.r_[-2.0 * mercado[:46], 1.5 * mercado[46:]]
    beta = regresion_beta(_cierres(activo), _cierres(mercado), "^GSPC")
    assert beta.semanas == 104
    assert beta.bruta == pytest.approx(1.5)


def test_con_52_semanas_hay_beta_y_con_51_no():
    m = np.random.default_rng(5).normal(0, 0.02, 52)
    assert regresion_beta(_cierres(m), _cierres(m), "^GSPC").semanas == 52
    assert regresion_beta(_cierres(m[:51]), _cierres(m[:51]), "^GSPC") is None


def test_la_beta_alinea_zonas_al_este_de_utc():
    # Medianoche en Tokio es el día anterior en UTC: convertir en vez de quitar
    # la zona desalinearía todas las fechas un día.
    m = np.random.default_rng(3).normal(0, 0.02, 80)
    activo = _cierres(m)
    activo.index = activo.index.tz_localize("Asia/Tokyo")
    assert regresion_beta(activo, _cierres(m), "^GSPC").bruta == pytest.approx(1.0)


def test_una_fecha_repetida_cuenta_una_vez():
    m = np.random.default_rng(3).normal(0, 0.02, 80)
    a = _cierres(m)
    repetida = pd.concat([a.iloc[:40], a.iloc[[39]], a.iloc[40:]])
    assert regresion_beta(repetida, _cierres(m), "^GSPC").semanas == 80


def test_de_una_fecha_repetida_vale_la_ultima():
    # Yahoo repite a veces la vela de la semana en curso: la buena es la última.
    m = np.random.default_rng(3).normal(0, 0.02, 80)
    a = _cierres(m)
    vieja = pd.Series([a.iloc[39] * 2], index=[a.index[39]])
    repetida = pd.concat([a.iloc[:39], vieja, a.iloc[39:]])
    assert regresion_beta(repetida, _cierres(m), "^GSPC").bruta == pytest.approx(1.0)


def test_la_beta_alinea_horas_distintas_del_mismo_dia():
    m = np.random.default_rng(3).normal(0, 0.02, 80)
    activo = _cierres(m)
    activo.index = activo.index.shift(14, freq="h")
    assert regresion_beta(activo, _cierres(m), "^GSPC").bruta == pytest.approx(1.0)


def test_r2_es_el_cuadrado_de_la_correlacion():
    # Correlación deliberadamente débil (≈ 0,57 frente a un R² ≈ 0,33): con una
    # casi perfecta, `corr` y `corr**2` se parecerían y el test no los distinguiría.
    m = np.random.default_rng(9).normal(0, .02, 104)
    a = 0.5 * m + np.random.default_rng(10).normal(0, .02, 104)
    beta = regresion_beta(_cierres(a), _cierres(m), "^GSPC")
    assert beta.r2 == pytest.approx(np.corrcoef(m, a)[0, 1] ** 2)


def test_la_beta_no_depende_del_orden_de_las_filas():
    # `tail` y `pct_change` son posicionales: con las filas desordenadas
    # calcularían rendimientos entre fechas que no son vecinas.
    g = np.random.default_rng(11)
    mercado = g.normal(0, 0.02, 80)
    activo = 1.5 * mercado + g.normal(0, 0.002, 80)
    del_derecho = regresion_beta(_cierres(activo), _cierres(mercado), "^GSPC")
    del_reves = regresion_beta(_cierres(activo).iloc[::-1], _cierres(mercado), "^GSPC")
    assert del_reves == del_derecho


def test_un_indice_sin_variacion_no_da_beta():
    a = _cierres(np.random.default_rng(3).normal(0, 0.02, 80))
    assert regresion_beta(a, pd.Series(100.0, index=a.index), "^GSPC") is None


def test_un_activo_sin_variacion_no_da_beta():
    # Pendiente 0 y R2 indefinido (NaN): una beta a medias no se devuelve.
    m = _cierres(np.random.default_rng(3).normal(0, 0.02, 80))
    assert regresion_beta(pd.Series(100.0, index=m.index), m, "^GSPC") is None


@pytest.mark.parametrize("posicion", [0, 40, 80])
def test_un_cierre_a_cero_no_da_beta(posicion):
    # Un cero en medio da un rendimiento infinito, que envenenaría el coste del
    # capital y la caché con un NaN. Un cero en la última semana no da infinito
    # sino un -100 %: una beta finita, plausible y falsa, que es peor.
    m = _cierres(np.random.default_rng(3).normal(0, 0.02, 80))
    activo = m.copy()
    activo.iloc[posicion] = 0.0
    assert regresion_beta(activo, m, "^GSPC") is None


def test_la_tasa_libre_es_el_ultimo_cierre_en_tanto_por_uno():
    assert tasa_libre_desde_cierres(pd.Series([4.1, 4.2, 5.24])) == pytest.approx(0.0524)


def test_sin_cierres_no_hay_tasa_libre():
    assert tasa_libre_desde_cierres(pd.Series([], dtype="float64")) is None


def test_la_tasa_efectiva_es_la_mas_reciente_con_dato():
    estado = pd.DataFrame(
        {"2025": [float("nan"), 10.0], "2024": [0.19, 9.0]},
        index=["Tax Rate For Calcs", "Net Income"],
    )
    assert tasa_efectiva_desde_estado(estado) == 0.19


def test_sin_fila_de_impuestos_no_hay_tasa_efectiva():
    estado = pd.DataFrame({"2025": [1.0]}, index=["Net Income"])
    assert tasa_efectiva_desde_estado(estado) is None
    assert tasa_efectiva_desde_estado(None) is None


def test_la_tasa_efectiva_toma_la_mas_reciente_aunque_haya_mas_antiguas():
    estado = pd.DataFrame(
        {"2025": [0.11], "2024": [0.36], "2023": [0.21]},
        index=["Tax Rate For Calcs"],
    )
    assert tasa_efectiva_desde_estado(estado) == 0.11


def _estimacion(moneda: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"avg": [1.0, 2.0], "growth": [1.0663, 0.1648], "currency": [moneda, moneda]},
        index=["0y", "+1y"],
    )


def test_el_consenso_es_el_crecimiento_del_proximo_ano():
    assert consenso_desde_estimacion(_estimacion("USD"), "USD") == pytest.approx(0.1648)


def test_un_consenso_en_otra_moneda_se_descarta():
    # TSM: revenue_estimate en TWD y earnings_estimate en USD, en la misma consulta.
    assert consenso_desde_estimacion(_estimacion("TWD"), "USD") is None


def test_sin_estimacion_no_hay_consenso():
    assert consenso_desde_estimacion(pd.DataFrame(), "USD") is None
    assert consenso_desde_estimacion(None, "USD") is None


# --- Los estados de yfinance, ida y vuelta a la caché --------------------------

from valoracion.mercado import estado_a_plano, estado_de_plano  # noqa: E402


def _estado():
    return pd.DataFrame(
        {
            pd.Timestamp("2026-06-30"): [2.5e11, float("nan")],
            pd.Timestamp("2026-03-31"): [2.45e11, -2.4e9],
        },
        index=["Total Revenue", "Capital Expenditure"],
    )


def test_un_estado_va_a_la_cache_con_nan_como_null_y_vuelve_igual():
    plano = estado_a_plano(_estado())
    assert plano["Capital Expenditure"]["2026-06-30"] is None
    json.dumps(plano, allow_nan=False)
    vuelta = estado_de_plano(plano)
    pd.testing.assert_frame_equal(vuelta, _estado().astype("float64"), check_names=False)


def test_el_estado_vuelve_con_la_columna_mas_reciente_primero():
    vuelta = estado_de_plano(estado_a_plano(_estado().iloc[:, ::-1]))
    assert list(vuelta.columns) == [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-03-31")]


def test_un_estado_vacio_es_un_plano_vacio_y_vuelve_vacio():
    assert estado_a_plano(pd.DataFrame()) == {}
    assert estado_a_plano(None) == {}
    assert estado_de_plano({}).empty


def test_un_plano_que_no_es_un_diccionario_no_se_lee():
    with pytest.raises(TypeError):
        estado_de_plano(["Total Revenue"])


def test_lo_que_no_es_un_numero_finito_va_a_null():
    raro = pd.DataFrame(
        {pd.Timestamp("2026-06-30"): ["texto", None, float("inf"), pd.Timestamp("2026-01-01")]},
        index=["Texto", "Nada", "Infinito", "Fecha"],
    )
    plano = estado_a_plano(raro)
    assert all(valores["2026-06-30"] is None for valores in plano.values())
    json.dumps(plano, allow_nan=False)


@pytest.mark.parametrize(
    "plano",
    [
        {"Total Revenue": [2.5e11]},
        {"Total Revenue": {"FY2025": 2.5e11}},
        {"Total Revenue": {"2026-06-30": "n/d"}},
    ],
    ids=["fila_como_lista", "fecha_que_no_es_fecha", "valor_que_no_es_numero"],
)
def test_un_plano_mal_formado_lanza_type_error(plano):
    # `_traer` sólo reconoce `TypeError` y `KeyError` como «forma de una
    # versión anterior»; cualquier otra excepción saldría en cada llamada.
    with pytest.raises(TypeError):
        estado_de_plano(plano)


from valoracion.mercado import precio_convertido  # noqa: E402


def test_el_precio_convertido_es_el_precio_por_el_tipo_de_cada_semana():
    fechas = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    precio = pd.Series([10.0, 11.0, 12.0], index=fechas)
    tipo = pd.Series([18.0, 18.5, 19.0], index=fechas)
    assert precio_convertido(precio, tipo).tolist() == [180.0, 203.5, 228.0]


def test_el_precio_convertido_solo_tiene_las_semanas_con_los_dos_datos():
    fechas = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    precio = pd.Series([10.0, 11.0, 12.0], index=fechas)
    tipo = pd.Series([18.0, float("nan")], index=fechas[:2])
    assert len(precio_convertido(precio, tipo)) == 1


from valoracion.mercado import tipo_sin_picos  # noqa: E402


def test_el_tipo_sin_picos_es_el_semanal_de_yahoo_sin_las_semanas_que_el_diario_desmiente():
    # Un `=X` como lo da Yahoo, en la zona de Londres: el semanal, fechado el
    # lunes; el diario, de lunes a viernes.
    semanas = pd.date_range("2024-12-02", periods=4, freq="W-MON", tz="Europe/London")
    semanal = pd.Series([0.700, 0.712, 0.911, 0.690], index=semanas)
    diario = pd.Series(0.70, index=pd.bdate_range("2024-12-02", periods=20, tz="Europe/London"))
    # Lo que queda es el semanal, no el diario: 0,712 se aparta un 1,7 % de él.
    assert tipo_sin_picos(semanal, diario).to_dict() == {
        pd.Timestamp("2024-12-02"): 0.700,
        pd.Timestamp("2024-12-09"): 0.712,
        pd.Timestamp("2024-12-23"): 0.690,
    }


def test_una_semana_sin_diario_con_que_compararla_se_descarta():
    # De ella no se puede saber si es un pico.
    semanas = pd.date_range("2024-12-02", periods=3, freq="W-MON", tz="Europe/London")
    semanal = pd.Series(0.70, index=semanas)
    dias = pd.bdate_range("2024-12-02", periods=15, tz="Europe/London")
    sin_la_segunda = (dias < semanas[1]) | (dias >= semanas[2])
    diario = pd.Series(0.70, index=dias[sin_la_segunda])
    assert list(tipo_sin_picos(semanal, diario).index) == [
        pd.Timestamp("2024-12-02"),
        pd.Timestamp("2024-12-16"),
    ]


def test_se_compara_con_la_ultima_vela_diaria_de_la_semana_y_no_con_la_primera():
    # La vela del lunes es la foto de medianoche, con el cierre del viernes
    # anterior. Si el lunes se mueve un 7 %, el semanal cierra ya movido, y la
    # semana es buena: con la primera vela parecería un pico.
    semanas = pd.date_range("2024-12-02", periods=2, freq="W-MON", tz="Europe/London")
    semanal = pd.Series([0.70, 0.75], index=semanas)
    dias = pd.bdate_range("2024-12-02", periods=10, tz="Europe/London")
    diario = pd.Series([0.70] * 6 + [0.75] * 4, index=dias)
    assert tipo_sin_picos(semanal, diario).tolist() == [0.70, 0.75]
