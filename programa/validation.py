"""Walk-forward validation of the optimised portfolio.

The Sharpe ratio the optimiser reports is measured on the very data it was fitted
to, so it is an upper bound rather than an expectation. This module re-runs the
whole procedure through time — fit on a training window, hold the resulting
weights through the following window without touching them, repeat — and measures
the Sharpe actually achieved on data the optimiser never saw.
"""

import numpy as np
import pandas as pd

from optimizer import STRATEGY_LABELS, optimize_portfolio

# Un año de bolsa son 250-252 sesiones según cómo caigan los festivos, mientras
# que `periods_per_year` es el 252 nominal con el que se anualiza. Comparar el
# conteo real contra el nominal rechazaba justo lo que el horizonte «1 Semana»
# descarga —un año entero, que tras el `pct_change` deja 250 retornos— y ese
# horizonte no llegaba a validarse nunca: la pantalla decía «no hay suficiente
# historial» sobre un año completo de datos.
_TOLERANCIA_CALENDARIO = 0.95


def default_window_sizes(periods_per_year: int) -> tuple[int, int]:
    """Train on roughly two years, hold for roughly one quarter."""
    train = max(2, 2 * periods_per_year)
    test = max(1, periods_per_year // 4)
    return train, test


def _resolve_windows(
    periods_per_year: int,
    n_obs: int,
    train_size: int | None,
    test_size: int | None,
) -> tuple[int, int]:
    """Pick window sizes that actually fit the history available.

    The daily horizons fetch as little as one year of data, which cannot host a
    two-year training window. Rather than silently skipping validation there, the
    windows shrink proportionally — fewer windows, but a real out-of-sample number.
    """
    if train_size is not None and test_size is not None:
        return train_size, test_size

    train, test = default_window_sizes(periods_per_year)
    if train + test <= n_obs:
        return train_size or train, test_size or test

    train = max(2, int(n_obs * 0.6))
    test = max(1, (n_obs - train) // 4)
    return train_size or train, test_size or test


def sharpe_standard_error(
    sharpe: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    """How precisely a Sharpe ratio can be measured from this much data.

    Standard error of an **annualised** Sharpe estimate. Lo's result is stated
    for the per-period Sharpe, sqrt((1 + S_p^2/2) / T); anualizarlo multiplica
    por sqrt(q) y deja sqrt((1 + S_a^2/(2q)) / años). Metiendo el Sharpe anual en
    la fórmula por período —que es lo que hacía esta función— el error salía un
    30% de más con Sharpe 1,3 y el doble con Sharpe 3, siempre en la dirección de
    «no se distingue del ruido».

    Esto mide el **nivel** de un Sharpe suelto. Para comparar dos carteras sobre
    las mismas fechas hace falta `sharpe_difference_standard_error`, que es un
    estadístico distinto y mucho más fino.

    Reference: Lo (2002), "The Statistics of Sharpe Ratios", Financial Analysts
    Journal 58(4).
    """
    years = n_periods / periods_per_year
    if years <= 0:
        return float("inf")
    return float(np.sqrt((1.0 + sharpe**2 / (2.0 * periods_per_year)) / years))


def sharpe_difference_standard_error(
    a: np.ndarray,
    b: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> float:
    """How precisely the GAP between two Sharpe ratios can be measured.

    La pregunta del veredicto no es «con qué precisión conozco este Sharpe», sino
    «con qué precisión conozco la diferencia entre estos dos». No son lo mismo:
    las dos carteras se miden sobre las mismas fechas y tienen los mismos
    activos, así que el movimiento común del mercado se cancela en la resta. En
    esta aplicación la correlación entre la cartera optimizada y 1/N va de 0,90 a
    0,995, y ahí el error de la diferencia es entre 3 y 12 veces menor que el de
    cualquiera de los dos Sharpe por separado.

    Es el mismo argumento que `research/timing.py:block_bootstrap_stderr` ya
    escribió para la Puerta B; la diferencia es que allí el bootstrap por bloques
    además renuncia a la independencia, que aquí sí se asume.

    Reference: Jobson & Korkie (1981), "Performance Hypothesis Testing with the
        Sharpe and Treynor Measures", Journal of Finance 36(4), con la corrección
        de Memmel (2003), "Performance Hypothesis Testing with the Sharpe Ratio",
        Finance Letters 1(1).
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.size != y.size or x.size < 3:
        return float("inf")

    sd_x, sd_y = x.std(ddof=1), y.std(ddof=1)
    if sd_x <= 0 or sd_y <= 0:
        return float("inf")

    # Sharpe por período de cada serie, sobre retornos en exceso: la resta de una
    # constante no toca la correlación, pero sí el numerador de cada Sharpe.
    s_x = (x.mean() - rf_rate) / sd_x
    s_y = (y.mean() - rf_rate) / sd_y

    rho = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(rho):
        rho = 0.0

    variance = (
        2.0 * (1.0 - rho) + 0.5 * (s_x**2 + s_y**2 - 2.0 * s_x * s_y * rho**2)
    ) / x.size
    return float(np.sqrt(max(variance, 0.0)) * np.sqrt(periods_per_year))


def _annualised_sharpe(
    period_returns: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> float:
    vol = period_returns.std(ddof=1) * np.sqrt(periods_per_year)
    if vol <= 0:
        return 0.0
    excess = (period_returns.mean() - rf_rate) * periods_per_year
    return float(excess / vol)


def _ventanas(returns: pd.DataFrame, train_size: int, test_size: int):
    """Cada par (entrenamiento, prueba) del recorrido, en orden.

    Las ventanas de prueba no se solapan —el paso es `test_size`— así que las
    series fuera de muestra se pueden concatenar sin contar dos veces el mismo
    día.
    """
    n_obs = len(returns)
    start = 0
    while start + train_size + test_size <= n_obs:
        yield (
            returns.iloc[start:start + train_size],
            returns.iloc[start + train_size:start + train_size + test_size],
        )
        start += test_size


def _componer(
    oos: np.ndarray,
    benchmark: np.ndarray,
    in_sample_sharpes: list[float],
    rf_rate: float,
    periods_per_year: int,
    n_windows: int,
    train_size: int,
    test_size: int,
) -> dict:
    """El resultado de un recorrido ya terminado, con su veredicto."""
    in_sample = float(np.mean(in_sample_sharpes)) if in_sample_sharpes else float("nan")
    out_of_sample = _annualised_sharpe(oos, rf_rate, periods_per_year)
    equal_weight = _annualised_sharpe(benchmark, rf_rate, periods_per_year)

    # Dos errores estándar porque son dos preguntas distintas. `sharpe_stderr`
    # dice con qué precisión se conoce el Sharpe de arriba; `gap_stderr` dice con
    # qué precisión se conoce la distancia a 1/N, que es lo único que puede
    # justificar el veredicto. Juzgar la diferencia contra el error del nivel
    # —lo que hacía esta función— hacía imposible llegar a decir «gana»: sobre 60
    # muestras sintéticas donde la optimización ganaba de verdad, salió «no se
    # distingue» en las 60.
    stderr = sharpe_standard_error(out_of_sample, int(oos.size), periods_per_year)
    gap_stderr = sharpe_difference_standard_error(
        oos, benchmark, rf_rate, periods_per_year
    )

    # Only call a winner when the gap is bigger than the error bar on measuring
    # it. Otherwise the honest answer is "this data cannot tell them apart".
    gap = out_of_sample - equal_weight
    beats_equal_weight = bool(gap > 0) if abs(gap) > gap_stderr else None

    return {
        "n_windows": n_windows,
        "n_oos_periods": int(oos.size),
        "in_sample_sharpe": in_sample,
        "out_of_sample_sharpe": out_of_sample,
        "equal_weight_sharpe": equal_weight,
        "sharpe_stderr": stderr,
        "gap_stderr": gap_stderr,
        "beats_equal_weight": beats_equal_weight,
        "oos_return": float(oos.mean() * periods_per_year),
        "oos_vol": float(oos.std(ddof=1) * np.sqrt(periods_per_year)),
        "degradation": in_sample - out_of_sample,
        "train_size": train_size,
        "test_size": test_size,
    }


def _preparar(
    returns: pd.DataFrame,
    periods_per_year: int,
    train_size: int | None,
    test_size: int | None,
) -> tuple[int, int] | None:
    """Las ventanas a usar, o None si el historial no da para ninguna."""
    n_obs = len(returns)

    # Below a year of history there is not enough independent data for the
    # out-of-sample figure to mean anything, whatever the window sizes.
    if n_obs < periods_per_year * _TOLERANCIA_CALENDARIO:
        return None

    train_size, test_size = _resolve_windows(periods_per_year, n_obs, train_size, test_size)
    if n_obs < train_size + test_size:
        return None
    return train_size, test_size


def walk_forward_validation(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    pairwise: bool = False,
    strategy: str = "max_sharpe",
    train_size: int | None = None,
    test_size: int | None = None,
) -> dict | None:
    """Return out-of-sample performance, or None if history is too short.

    Los pesos se fijan al empezar la ventana de mantenimiento y no vuelven a
    mirar los datos: no hay look-ahead. Dentro de la ventana la cartera se
    mantiene **en** esos pesos período a período, que es la misma convención con
    la que se calculan el retorno y la varianza en muestra (`w'μ` y `w'Σw` dan
    por supuesto un peso constante), y la misma para las dos ramas de la
    comparación. Lo que no cobra es el coste de mantenerla ahí.
    """
    ventanas = _preparar(returns, periods_per_year, train_size, test_size)
    if ventanas is None:
        return None
    train_size, test_size = ventanas

    equal_weights = np.ones(returns.shape[1]) / returns.shape[1]
    in_sample_sharpes: list[float] = []
    oos_chunks: list[np.ndarray] = []
    benchmark_chunks: list[np.ndarray] = []

    for train, test in _ventanas(returns, train_size, test_size):
        # El ajuste puede mirar fechas incompletas —la covarianza por pares las
        # aprovecha— pero **medir** exige que coticen todos: un retorno de
        # cartera con un activo sin precio no es un numero, es un NaN que se
        # come la serie entera. Sin `pairwise` esto no quita nada.
        evaluable = test.dropna(how="any")
        if evaluable.empty:
            continue
        fitted = optimize_portfolio(
            train, rf_rate, periods_per_year, weight_bounds, allow_short,
            strategy=strategy, shrinkage=shrinkage, pairwise=pairwise,
        )
        if fitted["converged"]:
            in_sample_sharpes.append(fitted["sharpe"])
            oos_chunks.append(evaluable.values @ fitted["weights"])
            benchmark_chunks.append(evaluable.values @ equal_weights)

    if not oos_chunks:
        return None

    return _componer(
        np.concatenate(oos_chunks),
        np.concatenate(benchmark_chunks),
        in_sample_sharpes,
        rf_rate,
        periods_per_year,
        len(oos_chunks),
        train_size,
        test_size,
    )


def walk_forward_comparison(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    pairwise: bool = False,
    strategies: tuple[str, ...] | None = None,
    train_size: int | None = None,
    test_size: int | None = None,
) -> dict | None:
    """Las estrategias recorridas a la vez, sobre exactamente las mismas ventanas.

    Corriendo `walk_forward_validation` una vez por estrategia cada una se queda
    con las ventanas donde *ella* convergió, y con ellas se lleva su propia
    referencia 1/N. Medido con datos reales: paridad de riesgo convergía en 30 de
    31 ventanas y su Equal Weight salía +1,06 donde las otras dos veían +1,13 —
    mientras la tabla de la pantalla imprimía una sola fila de referencia y la
    comparaba con las tres. Aquí una ventana que alguna estrategia no pueda
    resolver se descarta para todas, que es el precio de poder ponerlas en la
    misma tabla.

    Returns:
        {"por_estrategia": {nombre: resultado}, "n_windows", "n_windows_descartadas",
         "train_size", "test_size"}, o None si el historial no da para ninguna ventana.
    """
    nombres = tuple(strategies) if strategies else tuple(STRATEGY_LABELS)

    ventanas = _preparar(returns, periods_per_year, train_size, test_size)
    if ventanas is None:
        return None
    train_size, test_size = ventanas

    equal_weights = np.ones(returns.shape[1]) / returns.shape[1]
    in_sample: dict[str, list[float]] = {n: [] for n in nombres}
    oos_chunks: dict[str, list[np.ndarray]] = {n: [] for n in nombres}
    benchmark_chunks: list[np.ndarray] = []
    descartadas = 0

    for train, test in _ventanas(returns, train_size, test_size):
        evaluable = test.dropna(how="any")
        if evaluable.empty:
            descartadas += 1
            continue
        ajustes = {
            n: optimize_portfolio(
                train, rf_rate, periods_per_year, weight_bounds, allow_short,
                strategy=n, shrinkage=shrinkage, pairwise=pairwise,
            )
            for n in nombres
        }
        if not all(a["converged"] for a in ajustes.values()):
            descartadas += 1
            continue
        for n, ajuste in ajustes.items():
            in_sample[n].append(ajuste["sharpe"])
            oos_chunks[n].append(evaluable.values @ ajuste["weights"])
        benchmark_chunks.append(evaluable.values @ equal_weights)

    if not benchmark_chunks:
        return None

    benchmark = np.concatenate(benchmark_chunks)
    n_windows = len(benchmark_chunks)
    return {
        "por_estrategia": {
            n: _componer(
                np.concatenate(oos_chunks[n]),
                benchmark,
                in_sample[n],
                rf_rate,
                periods_per_year,
                n_windows,
                train_size,
                test_size,
            )
            for n in nombres
        },
        "n_windows": n_windows,
        "n_windows_descartadas": descartadas,
        "train_size": train_size,
        "test_size": test_size,
    }
