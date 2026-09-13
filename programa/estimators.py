"""Robust estimators for the inputs of the Markowitz problem.

Sample means and sample covariances are noisy. A mean-variance optimiser fed with
raw sample moments does not maximise the Sharpe ratio — it maximises estimation
error, systematically loading on whichever assets got lucky in the sample. These
shrinkage estimators trade a little bias for a large reduction in variance.

References:
    Ledoit & Wolf (2004), "A Well-Conditioned Estimator for Large-Dimensional
        Covariance Matrices", Journal of Multivariate Analysis 88(2).
    Jorion (1986), "Bayes-Stein Estimation for Portfolio Analysis",
        Journal of Financial and Quantitative Analysis 21(3).
"""

import numpy as np
import pandas as pd


def ledoit_wolf_cov(returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Shrink the sample covariance toward a scaled identity matrix.

    The optimal intensity is derived analytically, so there is nothing to tune.
    Total variance (the trace) is preserved; what changes is how variance is
    distributed, and the resulting matrix is always invertible and better
    conditioned than the sample estimate.

    Returns:
        (shrunk_covariance, shrinkage_intensity) with intensity in [0, 1].
    """
    x = returns.values.astype(float)
    x = x - x.mean(axis=0)
    n_obs, n_assets = x.shape

    if n_assets == 1:
        return returns.cov().values, 0.0

    # Intensity is derived on the maximum-likelihood (1/T) covariance, per the paper.
    sample = x.T @ x / n_obs
    mean_var = np.trace(sample) / n_assets

    # Dispersion of the sample covariance around the shrinkage target.
    dispersion = np.trace(sample @ sample) / n_assets - mean_var**2

    # Expected estimation error of the sample covariance itself.
    sq_norms = np.einsum("ij,ij->i", x, x)
    error = (np.sum(sq_norms**2) / n_obs - np.trace(sample @ sample)) / (n_obs * n_assets)

    if dispersion <= 0:
        intensity = 1.0
    else:
        intensity = float(np.clip(error / dispersion, 0.0, 1.0))

    # Apply that intensity to the unbiased (ddof=1) covariance the rest of the
    # app uses, so variance conventions stay consistent everywhere.
    unbiased = returns.cov().values
    target = np.trace(unbiased) / n_assets * np.eye(n_assets)
    shrunk = intensity * target + (1.0 - intensity) * unbiased
    return shrunk, intensity


def james_stein_mean(
    returns: pd.DataFrame,
    cov_matrix: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Shrink sample mean returns toward the cross-sectional grand mean.

    Mean returns are the least reliable input in mean-variance optimisation: the
    standard error of a sample mean shrinks only with sqrt(T). Bayes-Stein pulls
    the extreme estimates in, which is what stops the optimiser from betting the
    portfolio on the single asset that happened to run hardest.

    Returns:
        (shrunk_means, shrinkage_intensity) with intensity in [0, 1].
    """
    sample_mu = returns.mean().values.astype(float)
    n_obs, n_assets = returns.shape

    if n_assets == 1:
        return sample_mu, 0.0

    if cov_matrix is None:
        cov_matrix = returns.cov().values

    grand_mean = float(sample_mu.mean())
    deviation = sample_mu - grand_mean

    # Precision-weighted size of the cross-sectional spread. pinv keeps this
    # defined even when assets are perfectly collinear.
    precision = np.linalg.pinv(cov_matrix)
    spread = float(deviation @ precision @ deviation)

    intensity = (n_assets + 2) / ((n_assets + 2) + n_obs * max(spread, 0.0))
    intensity = float(np.clip(intensity, 0.0, 1.0))

    shrunk = (1.0 - intensity) * sample_mu + intensity * grand_mean
    return shrunk, intensity


def _encoger_hacia_identidad(cov: np.ndarray, intensidad: float) -> np.ndarray:
    """Mezclar una covarianza ya calculada con la identidad escalada.

    Es el paso final de Ledoit-Wolf separado del cálculo de la intensidad,
    porque con la matriz emparejada la intensidad no se puede derivar de los
    datos: cada entrada viene de una muestra distinta y la fórmula del paper
    supone una sola. Se reutiliza la que Ledoit-Wolf deriva de la ventana común
    —el único tramo donde todos los activos tienen dato— y se aplica aquí.
    """
    n = cov.shape[0]
    objetivo = np.trace(cov) / n * np.eye(n)
    return intensidad * objetivo + (1.0 - intensidad) * cov


def _a_psd(cov: np.ndarray) -> np.ndarray:
    """Reparar una covarianza que no describe ningún mundo posible.

    Estimando cada entrada con una muestra distinta, la matriz puede salir con
    algún autovalor negativo — y entonces hay carteras con varianza negativa,
    a las que el optimizador se iría sin límite. Se recortan los autovalores a
    cero y se reescala para **no tocar la diagonal**: las varianzas están bien
    estimadas, cada una con toda la historia de su activo; lo que no encaja
    entre sí son las correlaciones.
    """
    valores, vectores = np.linalg.eigh(cov)
    if valores.min() >= 0:
        return cov

    reparada = vectores @ np.diag(np.clip(valores, 0.0, None)) @ vectores.T

    # Devolver la diagonal original: D^(1/2) R D^(1/2) con R la correlación de
    # la reparada. Sin esto, recortar autovalores encoge las varianzas.
    d_reparada = np.sqrt(np.clip(np.diag(reparada), 1e-300, None))
    correlacion = reparada / np.outer(d_reparada, d_reparada)
    np.fill_diagonal(correlacion, 1.0)
    d_original = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    return correlacion * np.outer(d_original, d_original)


# Cuántas fechas tiene que compartir un par para que su covarianza signifique
# algo. Por debajo se deja en cero, que es lo único que no se la inventa.
SOLAPE_MINIMO = 24


def pairwise_cov(
    returns: pd.DataFrame,
    minimo_solape: int = SOLAPE_MINIMO,
) -> tuple[np.ndarray, int]:
    """Cada covarianza estimada con las fechas que comparte ESE par.

    Exigir que todos los activos coticen el mismo día es lo correcto para
    calcular un retorno de cartera, pero desperdicia una barbaridad al estimar
    la covarianza: con ocho candidatos del ranking, la pareja AAPL-MSFT se
    estimaba con las 56 fechas que comparten los ocho en vez de con sus 180.

    Las varianzas salen de toda la historia de cada activo. Una pareja que no
    llegue a `minimo_solape` fechas comunes se deja en cero — no hay dato con el
    que estimar esa relación, y cero es la única respuesta que no se la inventa.

    Returns:
        (covarianza, solape mínimo entre los pares que sí se pudieron estimar).
    """
    emparejada = returns.cov(min_periods=minimo_solape)
    cov = emparejada.values.astype(float).copy()

    solapes = returns.notna().astype(float)
    solapes = (solapes.T @ solapes).values
    estimables = np.isfinite(cov) & (solapes >= minimo_solape)
    # La diagonal no es una pareja: mide la historia de un activo consigo mismo
    # y siempre sería la mayor, tapando el solape que de verdad manda.
    np.fill_diagonal(estimables, False)
    minimo = int(solapes[estimables].min()) if estimables.any() else 0

    # Sin solape no hay relación que estimar; cero no se inventa ninguna.
    cov[~np.isfinite(cov)] = 0.0

    # La diagonal, con toda la historia propia de cada activo. Un activo sin
    # dato suficiente en este tramo deja NaN, y un solo NaN impide diagonalizar
    # la matriz entera; se le presta la varianza media para que la reparacion
    # pueda correr. Quien llama deberia haber descartado ese caso antes --
    # `optimizer.optimize_portfolio` lo hace-- y esto es la red de debajo.
    varianzas = returns.var().values.astype(float)
    sanas = varianzas[np.isfinite(varianzas) & (varianzas > 0)]
    varianzas[~np.isfinite(varianzas)] = sanas.mean() if sanas.size else 1.0
    np.fill_diagonal(cov, varianzas)
    cov[~np.isfinite(cov)] = 0.0

    cov = (cov + cov.T) / 2.0
    return _a_psd(cov), minimo


def estimate_moments(
    returns: pd.DataFrame,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    """Produce the (mean, covariance) pair the optimiser consumes.

    With shrinkage disabled this returns plain sample moments, preserving the
    original behaviour of the app.

    Con `pairwise`, la covarianza se estima por pares y aprovecha la historia
    completa de cada pareja. **Las medias siguen saliendo de la ventana común**,
    y eso es deliberado: una media estimada sobre la ventana propia de cada
    activo no es comparable entre activos — el que salió a bolsa en mitad de una
    subida aparece con una media altísima por haber nacido tarde, y máximo
    Sharpe se iría entero a él. La covarianza no tiene ese problema porque no
    compara niveles entre activos.
    """
    comun = returns.dropna(how="any") if pairwise else returns
    extra = {
        "pares": pairwise,
        "obs_comunes": int(len(comun)),
        "obs_maximas": int(returns.notna().sum().max()) if len(returns.columns) else 0,
    }

    if not shrinkage:
        cov = pairwise_cov(returns)[0] if pairwise else returns.cov().values
        return {
            "mean": comun.mean().values.astype(float),
            "cov": cov,
            "cov_shrinkage": 0.0,
            "mean_shrinkage": 0.0,
            **extra,
        }

    if pairwise:
        # El shrinkage se aplica a la matriz ya emparejada: encoger hacia la
        # identidad escalada sigue teniendo sentido, y la deja mejor
        # condicionada justo cuando los pares vienen de muestras distintas.
        # La intensidad, de la ventana común; la matriz a la que se aplica, la
        # emparejada. Con menos de dos fechas comunes no hay nada que derivar.
        cov_intensity = ledoit_wolf_cov(comun)[1] if len(comun) > 2 else 1.0
        cov = _a_psd(_encoger_hacia_identidad(pairwise_cov(returns)[0], cov_intensity))
    else:
        cov, cov_intensity = ledoit_wolf_cov(returns)

    mean, mean_intensity = james_stein_mean(comun, cov_matrix=cov)
    return {
        "mean": mean,
        "cov": cov,
        "cov_shrinkage": cov_intensity,
        "mean_shrinkage": mean_intensity,
        **extra,
    }
