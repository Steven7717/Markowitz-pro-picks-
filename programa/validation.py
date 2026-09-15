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

# Cuántos errores estándar tiene que medir el hueco contra 1/N antes de que la
# pantalla se atreva a decir quién gana. El porqué del número está en
# `veredicto`.
_SIGMAS_VEREDICTO = 2.0


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


def retorno_stderr(
    annual_vol: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    """Con qué precisión se conoce un retorno anual esperado. Muy poca.

    SE(μ anual) = σ anual / √años, sin más: la media es el estadístico peor
    medido de toda la optimización media-varianza, y por eso `estimators`
    encoge las medias mucho más que la covarianza.

    Cuánto pesa, con las cifras que la pantalla enseñaba: «Retorno anual
    esperado 28,76%» sobre 500 observaciones diarias de una cartera al 24,8% de
    volatilidad lleva un error estándar de 15,6 puntos porcentuales. El
    intervalo al 95% va de -1,9% a 59,4% — y el número salía solo, con dos
    decimales, mientras el Sharpe fuera de muestra sí llevaba su barra. El 2%
    que el usuario cree estar leyendo como precisión no existe.
    """
    years = n_periods / periods_per_year
    if years <= 0 or annual_vol < 0:
        return float("inf")
    return float(annual_vol / np.sqrt(years))


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


def veredicto(
    gap: float,
    gap_stderr: float,
    sigmas: float = _SIGMAS_VEREDICTO,
) -> bool | None:
    """¿Gana la optimización a repartir por igual? True, False, o «no se sabe».

    **Dos errores estándar, no uno.** Un error estándar es ~1σ, y el convenio de
    toda la estadística aplicada es 2σ (~95% a dos colas). Con 1σ el recuadro
    verde de `st.success` —«La optimización supera a repartir por igual»— salía
    en el **12%** de 200 mundos sintéticos construidos *sin ninguna ventaja
    real*: uno de cada ocho usuarios sin ventaja leía que la tenía. A 2σ la cola
    normal deja eso en ~2% por lado, que es el precio que este veredicto puede
    permitirse: es la afirmación con más consecuencias de la aplicación.

    El umbral no se revisó cuando `_componer` pasó de `sharpe_stderr` a
    `gap_stderr`, y ese cambio es correcto y no se toca: el hueco es lo único
    que puede justificar el veredicto. Pero el error de la diferencia es entre 3
    y 12 veces menor que el del nivel, así que el mismo «1σ» pasó a ser un
    liston entre 3 y 12 veces más bajo, y lo que antes casi nunca se superaba
    empezó a superarse por azar.

    Y sí, `research/timing.py::SIGMAS_PUERTA_B` se queda en 1σ, a sabiendas
    —y además pre-registrado, así que ahí el número ni se toca—. Aquello es
    una criba interna: un falso positivo cuesta otro experimento, y perder un
    candidato real cuesta una idea. Esto es un recuadro verde en la pantalla de
    alguien que va a repartir su dinero según lo que lea, y ahí el coste de los
    dos errores no se parece en nada. El mismo listón para las dos cosas sería
    la coherencia equivocada.

    None significa «estos datos no distinguen las dos carteras», que no es lo
    mismo que False —«pierde»— y por eso hay tres estados y no dos. El precio de
    pedir 2σ está escrito y medido en
    `tests/test_validation.py::test_el_precio_de_pedir_dos_sigmas_es_callar_en_los_casos_justos`:
    un mundo con ventaja real a 1,91σ ahora se calla.
    """
    if not np.isfinite(gap_stderr) or gap_stderr < 0:
        return None
    if abs(gap) <= sigmas * gap_stderr:
        return None
    return bool(gap > 0)


def _es(x: float, decimales: int = 2) -> str:
    """Un número con la coma decimal que usa el resto de la aplicación."""
    return f"{x:.{decimales}f}".replace(".", ",")


def frase_veredicto(
    gap: float,
    gap_stderr: float,
    sigmas: float = _SIGMAS_VEREDICTO,
) -> str:
    """El veredicto en una línea, **con el liston contra el que se dictó**.

    Vive aquí y no en la pantalla porque hay dos pantallas —el optimizador y los
    portafolios guardados— y sólo una lo escribía. La otra dejaba «Sharpe fuera
    de muestra 2,24» en grande mientras el propio fichero guardaba que era
    2,24 ± 2,10 e indistinguible de repartir por igual.

    Y dice el umbral ya multiplicado. Escribir «±0,28» cuando lo que hay que
    superar es 0,56 invita a que el lector compare su hueco contra el número
    equivocado, que es exactamente el error que se está corrigiendo.
    """
    if not np.isfinite(gap_stderr) or gap_stderr < 0:
        return (
            "Sin error de medición no hay veredicto posible: no se puede decir si "
            "esta cartera le gana a repartir por igual."
        )
    estado = veredicto(gap, gap_stderr, sigmas)
    medida = medida_veredicto(gap, gap_stderr, sigmas)
    if estado is True:
        return f"Supera a repartir por igual. {medida}"
    if estado is False:
        return f"Queda por debajo de repartir por igual. {medida}"
    return f"Estos datos no distinguen esta cartera de repartir por igual. {medida}"


def medida_veredicto(
    gap: float,
    gap_stderr: float,
    sigmas: float = _SIGMAS_VEREDICTO,
) -> str:
    """Sólo la medición: cuánto separa a las dos y contra qué listón se juzga.

    La mitad del veredicto que aporta un número, sin el juicio. Existe porque
    la pantalla del optimizador ya pone su propio titular en negrita —el color
    del recuadro y la frase gruesa ya dicen cuál de los tres casos es— y con la
    frase entera detrás el usuario leía dos veces lo mismo: «Con estos datos no
    se puede distinguir la optimización de repartir por igual. Estos datos no
    distinguen esta cartera de repartir por igual: las separan…».

    `frase_veredicto` se construye sobre esta función y no al revés, para que
    las dos no puedan decir cosas distintas dentro de un año.
    """
    if not np.isfinite(gap_stderr) or gap_stderr < 0:
        return (
            "Sin error de medición no hay veredicto posible: no se puede decir "
            "si esta cartera le gana a repartir por igual."
        )
    return (
        f"Las separan {_es(gap)} de Sharpe y hacen falta {_es(sigmas * gap_stderr)} "
        f"({_es(sigmas, 0)} errores estándar de ±{_es(gap_stderr)})."
    )


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
    oos_chunks: list[np.ndarray],
    benchmark: np.ndarray,
    in_sample_sharpes: list[float],
    rf_rate: float,
    periods_per_year: int,
    n_windows: int,
    train_size: int,
    test_size: int,
) -> dict:
    """El resultado de un recorrido ya terminado, con su veredicto."""
    oos = np.concatenate(oos_chunks)
    in_sample = float(np.mean(in_sample_sharpes)) if in_sample_sharpes else float("nan")
    out_of_sample = _annualised_sharpe(oos, rf_rate, periods_per_year)
    equal_weight = _annualised_sharpe(benchmark, rf_rate, periods_per_year)

    # El MISMO estimador que `in_sample`, para poder restarlos. `in_sample` es la
    # media de un cociente por ventana y `out_of_sample` es el cociente de todas
    # las observaciones juntas: restarlos —lo que hacía `degradation`— cruza dos
    # estimadores distintos del mismo número. En la pantalla salía «-0,57» donde
    # quien leía un 1,13 en muestra y un 0,80 fuera esperaba -0,33, y ninguno de
    # los dos números de esa resta era el que tenía delante.
    #
    # El agrupado se queda como titular porque es el mejor de los dos: usa todas
    # las observaciones a la vez, mientras que la media de cocientes la domina la
    # ventana más afortunada (1,206 · 0,941 · 0,993 · 2,343 en el caso medido).
    por_ventana = [
        _annualised_sharpe(c, rf_rate, periods_per_year) for c in oos_chunks
    ]
    out_of_sample_medio = float(np.mean(por_ventana)) if por_ventana else float("nan")

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

    # Only call a winner when the gap clears the error bar on measuring it, by
    # the 2σ margin `veredicto` argues for. Otherwise the honest answer is
    # "this data cannot tell them apart".
    gap = out_of_sample - equal_weight
    beats_equal_weight = veredicto(gap, gap_stderr)

    return {
        "n_windows": n_windows,
        "n_oos_periods": int(oos.size),
        "in_sample_sharpe": in_sample,
        "out_of_sample_sharpe": out_of_sample,
        "out_of_sample_sharpe_medio": out_of_sample_medio,
        "equal_weight_sharpe": equal_weight,
        "sharpe_stderr": stderr,
        "gap_stderr": gap_stderr,
        # La distancia que el hueco tiene que superar para que haya veredicto,
        # ya multiplicada. La pantalla la escribe tal cual: decir «±0,28» cuando
        # se está juzgando contra 0,56 invita a sumar mal.
        "umbral_veredicto": _SIGMAS_VEREDICTO * gap_stderr,
        "sigmas_veredicto": _SIGMAS_VEREDICTO,
        "beats_equal_weight": beats_equal_weight,
        "oos_return": float(oos.mean() * periods_per_year),
        "oos_vol": float(oos.std(ddof=1) * np.sqrt(periods_per_year)),
        "degradation": in_sample - out_of_sample_medio,
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
        oos_chunks,
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
                oos_chunks[n],
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


# ══ Lo que un portafolio guardado se lleva, y cómo vuelve ═════════════════════
#
# Dos pantallas y un PDF leen un portafolio guardado, y las tres escribían el
# veredicto de su propia manera: una pintaba el color con el `beats_equal_weight`
# GUARDADO —dictado a 1σ— y el texto de al lado lo recalculaba a 2σ, de modo que
# el recuadro salía verde encima de la frase «estos datos no distinguen esta
# cartera de repartir por igual»; otra se limitaba a leer el veredicto viejo sin
# barra de error ni listón; y el PDF no lo escribía en absoluto.
#
# La causa común era que el fichero no guardaba contra qué listón se había
# dictado su propio veredicto, así que nadie podía recomprobarlo. De ahí las dos
# mitades de este contrato: `metricas_de_validacion` escribe la MEDICIÓN entera
# —incluidos el umbral y las sigmas— y `veredicto_guardado` vuelve a dictar la
# conclusión al leer, en un solo sitio, para las tres vistas.


_DE_RECORRIDO_A_FICHERO = {
    "oos_sharpe": "out_of_sample_sharpe",
    "oos_equal_weight_sharpe": "equal_weight_sharpe",
    "oos_sharpe_stderr": "sharpe_stderr",
    # El que justifica el veredicto: el error de la DIFERENCIA, medida sobre las
    # mismas fechas, entre 3 y 12 veces más fino que el del nivel de arriba.
    "oos_gap_stderr": "gap_stderr",
    # Los dos que faltaban. Sin ellos un fichero no puede decir contra qué se
    # juzgó, y `beats_equal_weight` se convierte en un dogma: un True escrito
    # hace meses con otro listón sigue pintando de verde hoy.
    "oos_umbral_veredicto": "umbral_veredicto",
    "oos_sigmas_veredicto": "sigmas_veredicto",
    "beats_equal_weight": "beats_equal_weight",
}


def metricas_de_validacion(wf: dict | None) -> dict:
    """Los campos del recorrido que un portafolio guardado tiene que llevarse.

    Vive aquí y no en la vista del optimizador porque el contrato de ida —qué se
    escribe— y el de vuelta —`veredicto_guardado`— son el mismo contrato, y
    separarlos es como se perdieron el umbral y las sigmas.

    Sin recorrido se escriben huecos, nunca ceros: `None` significa «no se midió»
    y `0` significaría «se midió y salió cero». La única excepción es el recuento
    de ventanas, donde cero ventanas es literalmente cierto.
    """
    guardado = {
        fichero: (wf[recorrido] if wf else None)
        for fichero, recorrido in _DE_RECORRIDO_A_FICHERO.items()
    }
    guardado["oos_windows"] = wf["n_windows"] if wf else 0
    return guardado


# El veredicto en tres palabras, para una celda de tabla. El caso «no se sabe»
# se redacta distinto en `frase_veredicto` —«estos datos no distinguen…», que es
# una oración y aquí no cabe— pero los tres salen del MISMO `estado`, que es lo
# que impide que el titular y la frase se separen.
_TITULAR_VEREDICTO = {
    True: "Supera a repartir por igual",
    False: "Queda por debajo de repartir por igual",
    None: "Indistinguible de repartir por igual",
}


def titular_veredicto(estado: bool | None) -> str:
    """El veredicto en una celda, sin la medición que lo sostiene."""
    return _TITULAR_VEREDICTO[estado]


def veredicto_guardado(metricas: dict) -> dict | None:
    """Vuelve a dictar el veredicto de un portafolio guardado. None si no se puede.

    **El color, el titular y la frase salen de aquí, los tres del mismo
    `estado`.** El defecto que esto cierra era exactamente ese: el recuadro de
    `vistas/portafolios.py` se pintaba con el `beats_equal_weight` del fichero y
    el texto de dentro se recalculaba, así que un hueco de +0,350 con un error de
    ±0,20 —dictado «gana» cuando bastaba un error estándar— salía en verde con la
    frase «estos datos no distinguen esta cartera de repartir por igual» dentro.

    Se re-dicta en vez de leerse porque el listón es una decisión viva
    —`_SIGMAS_VEREDICTO` pasó de 1 a 2— y un fichero es una fotografía de la
    medición, no de la conclusión. `discrepa` dice si la conclusión de hoy
    difiere de la que el fichero lleva escrita, para que la pantalla pueda avisar
    en vez de cambiar el veredicto en silencio.

    Devuelve None cuando el fichero no trae el error de la diferencia: sin él no
    hay veredicto posible, y los portafolios anteriores a `oos_gap_stderr` no lo
    traen. Inventarles un False afirmaría un resultado que nadie obtuvo.
    """
    oos = metricas.get("oos_sharpe")
    equal_weight = metricas.get("oos_equal_weight_sharpe")
    gap_stderr = metricas.get("oos_gap_stderr")
    if oos is None or equal_weight is None or gap_stderr is None:
        return None

    gap_stderr = float(gap_stderr)
    if not np.isfinite(gap_stderr) or gap_stderr < 0:
        return None

    gap = float(oos) - float(equal_weight)
    estado = veredicto(gap, gap_stderr)

    # `bool(...)` a los dos lados porque un JSON puede devolver 1.0 donde se
    # escribió True, y eso no es una discrepancia: es el mismo veredicto.
    anterior = metricas.get("beats_equal_weight")
    if anterior is None or estado is None:
        discrepa = (anterior is None) != (estado is None)
    else:
        discrepa = bool(anterior) != bool(estado)

    return {
        "gap": gap,
        "gap_stderr": gap_stderr,
        "umbral": _SIGMAS_VEREDICTO * gap_stderr,
        "sigmas": _SIGMAS_VEREDICTO,
        "estado": estado,
        "titular": titular_veredicto(estado),
        "frase": frase_veredicto(gap, gap_stderr),
        "medida": medida_veredicto(gap, gap_stderr),
        "discrepa": discrepa,
    }


# ══ ¿Estos datos identifican un reparto, o cualquiera vale igual? ═════════════
#
# El caso por defecto de la aplicación —cinco activos, 501 observaciones
# diarias, tope del 100%, estimación robusta— escribe «MSFT 45,8%» con un
# decimal, con tarta, con tabla y con PDF. Un bootstrap de 300 remuestreos con
# reoptimización completa sobre ese mismo caso da intervalos al 90% de 67,3
# puntos de ancho medio sobre una región factible de 100 —AAPL [0,0%, 77,2%],
# MSFT [0,0%, 76,4%], GOOGL [0,0%, 88,5%]— y en el 54% de los remuestreos manda
# un activo distinto del que la pantalla pone primero. El guardarraíl de muestra
# corta no se dispara: hay 100 observaciones por activo contra un umbral de 30.
# Ese decimal no existía y ninguna vista lo decía.

_MINIMO_IDENTIFICABILIDAD = 3


def _dictamen_identificabilidad(
    mejor: str,
    peor: str,
    brecha: float,
    stderr: float,
    anos: float,
    sigmas: float = _SIGMAS_VEREDICTO,
) -> dict | None:
    """La conclusión, dictada a partir de la medición y del listón de hoy."""
    brecha, stderr, anos = float(brecha), float(stderr), float(anos)
    if not np.isfinite(stderr) or stderr <= 0 or not np.isfinite(brecha):
        return None

    t = abs(brecha) / stderr
    # La precisión de una media crece con la raíz del tiempo, así que para
    # multiplicar t por k hace falta k² veces más historial. De ahí (σ/t)².
    necesarios = anos * (sigmas / t) ** 2 if t > 0 else float("inf")
    return {
        "mejor": mejor,
        "peor": peor,
        "brecha": brecha,
        "stderr": stderr,
        "anos": anos,
        "t": t,
        "anos_necesarios": necesarios,
        "sigmas": sigmas,
        "identificada": bool(t > sigmas),
    }


def identificabilidad(
    returns: pd.DataFrame,
    periods_per_year: int,
    sigmas: float = _SIGMAS_VEREDICTO,
) -> dict | None:
    """¿Hay señal para preferir un reparto a otro? El test más barato que es honesto.

    **Mide la brecha de retorno esperado entre el activo que más promete y el
    que menos, y la compara con su propio error estándar.** Si ni siquiera la
    brecha más ancha de la cartera se distingue del ruido, ningún orden de las
    medias está sostenido, y por tanto ningún reparto media-varianza puede
    defenderse frente a otro: los intervalos anchos del bootstrap son el SÍNTOMA
    y esto es la causa. La media es además el estadístico peor medido de toda la
    optimización —por eso `estimators` la encoge mucho más que la covarianza— así
    que es también donde el problema vive.

    **Por qué esto y no el bootstrap.** El bootstrap con reoptimización mide lo
    mismo mucho mejor —da el intervalo de cada peso, no sólo un sí/no— pero
    cuesta 300 optimizaciones completas por pantalla, decenas de segundos en el
    caso por defecto, y esta aplicación reoptimiza en cada interacción de
    Streamlit. Un aviso que se paga con una pantalla inusable se acaba
    desactivando, y entonces vuelve el decimal sin advertencia. Esto cuesta dos
    medias y una desviación típica sobre la matriz que ya está en memoria
    —microsegundos— y contesta la única pregunta que cambia lo que el usuario
    debe hacer: si puede leer los pesos al decimal o no.

    Y es el MISMO estadístico del veredicto fuera de muestra —una diferencia
    contra su error, juzgada a `_SIGMAS_VEREDICTO`— así que la pantalla no
    enseña dos varas de medir distintas.

    Lo que no hace: no dice cuánto se mueve cada peso, no mira la covarianza
    —que está muchísimo mejor estimada que las medias— ni pretende sustituir al
    bootstrap si alguna vez se quiere pagar. Es la advertencia, no el intervalo.

    Devuelve None cuando no hay ni dos activos ni observaciones suficientes para
    una desviación típica: ahí no se inventa una medida.
    """
    if returns is None or getattr(returns, "shape", (0, 0))[1] < 2:
        return None

    medias = returns.mean(skipna=True).dropna()
    if medias.size < 2:
        return None

    mejor, peor = str(medias.idxmax()), str(medias.idxmin())
    # Sobre las fechas en que cotizan LOS DOS: una diferencia con un NaN dentro
    # no es un número, y el error de la brecha se mide sobre la serie pareada.
    diferencia = (returns[mejor] - returns[peor]).dropna().to_numpy(dtype=float)
    if diferencia.size < _MINIMO_IDENTIFICABILIDAD:
        return None

    n_obs = int(diferencia.size)
    vol_anual = float(diferencia.std(ddof=1) * np.sqrt(periods_per_year))
    return _dictamen_identificabilidad(
        mejor,
        peor,
        float(diferencia.mean() * periods_per_year),
        retorno_stderr(vol_anual, n_obs, periods_per_year),
        n_obs / periods_per_year,
        sigmas,
    )


# Se guarda la MEDICIÓN y no la conclusión, por la misma razón que el veredicto:
# `identificada` depende de `_SIGMAS_VEREDICTO`, que es una decisión viva. Y se
# guarda plano —cinco campos sueltos, no un diccionario anidado— porque
# `cartera._serializable` convierte a `str(...)` lo que no sabe serializar, y un
# dict anidado volvería del JSON como la cadena "{'mejor': 'MSFT', ...}".
_CAMPOS_IDENTIFICABILIDAD = ("mejor", "peor", "brecha", "stderr", "anos")


def metricas_de_identificabilidad(dato: dict | None) -> dict:
    """Los cinco campos que un fichero necesita para repetir el aviso."""
    return {
        f"ident_{campo}": (dato[campo] if dato else None)
        for campo in _CAMPOS_IDENTIFICABILIDAD
    }


def identificabilidad_guardada(metricas: dict) -> dict | None:
    """El aviso de un portafolio guardado, re-dictado. None si no se midió."""
    crudo = {c: metricas.get(f"ident_{c}") for c in _CAMPOS_IDENTIFICABILIDAD}
    if any(crudo[c] is None for c in ("brecha", "stderr", "anos")):
        return None
    return _dictamen_identificabilidad(**crudo)


def _pct(x: float, decimales: int = 1) -> str:
    """Un porcentaje con la coma decimal que usa el resto de la aplicación."""
    return f"{x:.{decimales}%}".replace(".", ",")


def _anos(x: float) -> str:
    """Un número de años con la precisión que merece, y ni una cifra más."""
    if not np.isfinite(x):
        return "incontables años"
    if x >= 1000:
        return f"unos {int(round(x / 100.0) * 100):,}".replace(",", ".") + " años"
    if x >= 10:
        return f"unos {int(round(x))} años"
    return f"unos {_es(x, 1)} años"


def frase_identificabilidad(dato: dict | None) -> str:
    """El aviso que el usuario tiene que leer ANTES de mirar un peso.

    Dice la brecha, su error, cuánto historial haría falta y qué hacer con los
    números de abajo. Lo último es lo que lo hace útil: «no están identificados»
    sin una instrucción es un adorno.

    El estado se re-dicta desde `t` y el listón de hoy, nunca desde el
    `identificada` que venga en el diccionario, para que un fichero viejo no
    pueda imponer una conclusión con un listón derogado.
    """
    if not dato:
        return (
            "No hay historial suficiente para decir si estos datos identifican "
            "un reparto concreto; léelos como una propuesta, no como una medida."
        )

    sigmas = dato.get("sigmas", _SIGMAS_VEREDICTO)
    medida = (
        f"la diferencia de retorno esperado entre {dato['mejor']} y "
        f"{dato['peor']} es {_pct(dato['brecha'])} ± {_pct(dato['stderr'])} "
        f"anual ({_es(dato['t'], 1)} errores estándar"
    )

    if dato["t"] > sigmas:
        return (
            f"El orden de los pesos se sostiene sobre estos datos: {medida}, y "
            f"hacen falta {_es(sigmas, 0)}), medidos sobre {_anos(dato['anos'])} "
            "de historial."
        )

    return (
        f"Estos pesos no están identificados: {medida} frente a los "
        f"{_es(sigmas, 0)} que hacen falta), y para sostener este orden harían "
        f"falta {_anos(dato['anos_necesarios'])} de historial cuando hay "
        f"{_anos(dato['anos'])}. Léelos como uno de los muchos repartos "
        "compatibles con los datos, no como cifras al decimal."
    )
