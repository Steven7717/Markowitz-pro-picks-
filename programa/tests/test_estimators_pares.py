"""Covarianza por pares: usar todo el dato, no sólo el que comparten todos."""

import numpy as np
import pandas as pd
import pytest

from estimators import estimate_moments, pairwise_cov


def _mercado(n_obs: int = 400, n_assets: int = 4, seed: int = 3) -> pd.DataFrame:
    """Activos correlados por un factor común, todos con historia completa."""
    rng = np.random.default_rng(seed)
    factor = rng.normal(0.0004, 0.010, size=(n_obs, 1))
    betas = np.linspace(0.7, 1.4, n_assets).reshape(1, -1)
    ruido = rng.normal(0, 0.008, size=(n_obs, n_assets))
    return pd.DataFrame(factor @ betas + ruido,
                        columns=[f"A{i}" for i in range(n_assets)])


def _con_recien_llegado(base: pd.DataFrame, desde: int) -> pd.DataFrame:
    """El mismo mercado con un activo que sólo existe a partir de `desde`."""
    d = base.copy()
    d["JOVEN"] = d["A0"] * 0.9 + np.random.default_rng(9).normal(0, 0.01, len(d))
    d.loc[d.index[:desde], "JOVEN"] = np.nan
    return d


# ── Qué dato usa cada entrada ─────────────────────────────────────────────────

def test_sin_huecos_coincide_con_la_covarianza_de_siempre():
    datos = _mercado()
    cov, minimo = pairwise_cov(datos)
    assert np.allclose(cov, datos.cov().values)
    assert minimo == len(datos)


def test_las_parejas_de_activos_viejos_usan_toda_su_historia():
    """Es lo que gana esto: A0-A1 no tiene por qué pagar la juventud de JOVEN.

    Con `dropna(how="any")` esa pareja se estimaba con las 50 fechas que
    comparten los cinco; aquí usa las 400 suyas.
    """
    datos = _con_recien_llegado(_mercado(), desde=350)
    cov, _ = pairwise_cov(datos)
    viejos = datos[["A0", "A1", "A2", "A3"]]
    esperado = viejos.cov().values
    assert np.allclose(cov[:4, :4], esperado)


def test_el_comun_se_queda_muy_por_debajo_de_lo_que_hay():
    datos = _con_recien_llegado(_mercado(), desde=350)
    assert len(datos.dropna(how="any")) == 50
    _, minimo = pairwise_cov(datos)
    assert minimo == 50  # el solape del par peor, que sigue siendo el joven


def test_una_pareja_sin_solape_suficiente_no_se_inventa():
    """Sin fechas en común no hay covarianza que estimar: cero, no ruido."""
    datos = _mercado(n_assets=2)
    datos.loc[datos.index[200:], "A0"] = np.nan
    datos.loc[datos.index[:200], "A1"] = np.nan
    cov, minimo = pairwise_cov(datos, minimo_solape=20)
    assert minimo == 0
    assert cov[0, 1] == 0.0


def test_las_varianzas_salen_de_la_historia_propia_de_cada_activo():
    datos = _con_recien_llegado(_mercado(), desde=350)
    cov, _ = pairwise_cov(datos)
    for i, col in enumerate(datos.columns):
        assert cov[i, i] == pytest.approx(datos[col].var(), rel=1e-9)


# ── La matriz tiene que seguir siendo utilizable ──────────────────────────────

def test_la_matriz_es_simetrica():
    cov, _ = pairwise_cov(_con_recien_llegado(_mercado(), desde=300))
    assert np.allclose(cov, cov.T)


def test_la_matriz_es_definida_positiva_aunque_los_pares_no_encajen():
    """Estimar cada entrada con una muestra distinta puede romper la matriz.

    Una covarianza con un autovalor negativo no describe ningún mundo posible:
    habría carteras con varianza negativa, y el optimizador se iría a ellas
    sin límite. Se repara antes de devolverla.
    """
    rng = np.random.default_rng(1)
    datos = pd.DataFrame(rng.normal(0, 0.02, size=(300, 6)),
                         columns=[f"A{i}" for i in range(6)])
    # Cada activo vivo en un tramo distinto: las entradas salen de muestras
    # que apenas se solapan, que es cuando la matriz deja de ser coherente.
    for i, col in enumerate(datos.columns):
        datos.loc[datos.index[: i * 45], col] = np.nan
    cov, _ = pairwise_cov(datos, minimo_solape=20)
    assert np.linalg.eigvalsh(cov).min() >= -1e-12


def test_reparar_la_matriz_no_toca_las_varianzas():
    """La diagonal está bien estimada; lo que no encaja son las correlaciones."""
    rng = np.random.default_rng(2)
    datos = pd.DataFrame(rng.normal(0, 0.02, size=(300, 6)),
                         columns=[f"A{i}" for i in range(6)])
    for i, col in enumerate(datos.columns):
        datos.loc[datos.index[: i * 45], col] = np.nan
    cov, _ = pairwise_cov(datos, minimo_solape=20)
    for i, col in enumerate(datos.columns):
        assert cov[i, i] == pytest.approx(datos[col].var(), rel=1e-9)


# ── Cómo entra en el resto del programa ───────────────────────────────────────

def test_por_defecto_no_se_usa_y_nada_cambia():
    datos = _con_recien_llegado(_mercado(), desde=350)
    m = estimate_moments(datos.dropna(how="any"))
    assert m["pares"] is False


def test_activarlo_deja_constancia_de_cuanto_dato_ha_usado():
    datos = _con_recien_llegado(_mercado(), desde=350)
    m = estimate_moments(datos, pairwise=True)
    assert m["pares"] is True
    assert m["obs_comunes"] == 50
    assert m["obs_maximas"] == 400


def test_las_medias_siguen_saliendo_de_la_ventana_comun():
    """Y es a propósito, aunque desaproveche dato.

    Una media estimada sobre la ventana propia de cada activo no es comparable
    entre activos: el que empezó a cotizar en una subida sale con una media
    altísima por haber nacido tarde, y máximo Sharpe se iría entero a él. La
    covarianza no tiene ese problema porque no compara niveles.
    """
    datos = _con_recien_llegado(_mercado(), desde=350)
    m = estimate_moments(datos, pairwise=True)
    comun = datos.dropna(how="any")
    assert np.allclose(m["mean"], comun.mean().values)


def test_se_puede_combinar_con_el_shrinkage():
    datos = _con_recien_llegado(_mercado(), desde=350)
    m = estimate_moments(datos, shrinkage=True, pairwise=True)
    assert m["pares"] is True
    assert 0.0 <= m["cov_shrinkage"] <= 1.0
    assert np.linalg.eigvalsh(m["cov"]).min() >= -1e-12


def test_con_historia_completa_activarlo_no_cambia_nada():
    datos = _mercado()
    igual = estimate_moments(datos, pairwise=True)
    normal = estimate_moments(datos)
    assert np.allclose(igual["cov"], normal["cov"])
    assert np.allclose(igual["mean"], normal["mean"])
