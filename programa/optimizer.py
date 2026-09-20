import numpy as np
import pandas as pd
from scipy.optimize import minimize

from estimators import estimate_moments

N_SIMULATIONS = 10_000

# Cuantas observaciones necesita un activo en una ventana para que se pueda
# decir algo de el. Por debajo no hay varianza que estimar, y menos covarianza.
_MINIMO_POR_ACTIVO = 3
_N_RANDOM_STARTS = 12

# Cuánto puede separarse de su objetivo la peor aportación al riesgo antes de
# que «paridad de riesgo» deje de describir la cartera. Un 5% de lo que a cada
# activo le toca, y no un punto porcentual absoluto: por debajo de eso la
# diferencia no cambia ninguna decisión, y por encima empieza a haber un activo
# mandando. Los casos medidos que fallaban iban del 2,5% al 47% del objetivo,
# así que el listón no está fino de más.
#
# **Relativo, porque el objetivo depende del número de activos.** El punto
# porcentual absoluto de antes era el 5% del objetivo con los cinco activos del
# caso por defecto, pero el 20% con veinte: el error que la tolerancia tapaba
# crecía con la cartera, y con veinte activos y un tope del 10% salía
# `erc_exacto=True` sobre una cartera cuyo peor activo aportaba un 10,5% menos
# de riesgo del que le tocaba, sin una palabra en pantalla.
_TOLERANCIA_ERC_RELATIVA = 0.05


def _tolerancia_erc(n: int) -> float:
    """Lo que puede desviarse la peor aportación con `n` activos en la cartera.

    El `min` con el punto porcentual de siempre es deliberado: el criterio
    relativo se afloja por debajo de cinco activos (con cuatro daría 1,25
    puntos) y aquí sólo se quiere apretar. Ninguna cartera que hoy se declara
    desigual pasa a declararse exacta por este cambio.
    """
    if n <= 0:
        return 0.01
    return min(0.01, _TOLERANCIA_ERC_RELATIVA / n)


def portfolio_metrics(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    rf_rate: float,
    periods_per_year: int,
) -> tuple[float, float, float]:
    port_return = float(np.dot(weights, mean_returns) * periods_per_year)
    port_vol = float(np.sqrt(weights @ cov_matrix @ weights) * np.sqrt(periods_per_year))
    rf_annual = rf_rate * periods_per_year
    sharpe = float((port_return - rf_annual) / port_vol) if port_vol > 0 else 0.0
    return port_return, port_vol, sharpe


def criterio_sharpe(port_return: float, port_vol: float, rf_annual: float) -> float:
    """Lo que «máximo Sharpe» maximiza de verdad, también en mercado bajista.

    El cociente de Sharpe **no ordena carteras cuando el exceso esperado es
    negativo**. Con el numerador por debajo de cero —2022, 2008, 2000-02: todos
    los activos rentando menos que las letras del Tesoro— agrandar el
    denominador acerca el cociente a cero, así que maximizarlo es literalmente
    maximizar la volatilidad. Medido con tres activos y rf = 4%:

        medias anuales   defensivo -10%   medio -12%   volátil  -8%
        vol anual        defensivo  15%   medio  24%   volátil  46%

    y el optimizador entregaba el volátil al 100%, «convergido», sin un aviso.

    Aquí el criterio es la extensión continua de Israelsen: exceso/σ mientras el
    exceso sea positivo —donde el cociente sí ordena— y exceso×σ cuando es
    negativo, que penaliza la volatilidad en vez de premiarla. Los dos tramos se
    pegan en cero y **no compiten**: cualquier cartera con exceso positivo
    puntúa por encima de cero y ninguna con exceso negativo llega, así que
    mientras exista una cartera factible que supere a las letras el óptimo es
    exactamente el máximo Sharpe de siempre. Sólo cambia el régimen en el que el
    cociente había dejado de significar algo, y ahí `optimize_max_sharpe`
    devuelve `sin_prima=True` para que la pantalla lo diga.

    Reference: Israelsen (2005), "A refinement to the Sharpe ratio and
        information ratio", Journal of Asset Management 5(6).
    """
    if port_vol <= 0:
        return 0.0
    exceso = port_return - rf_annual
    return exceso / port_vol if exceso >= 0 else exceso * port_vol


def risk_contribution(weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
    port_variance = float(weights @ cov_matrix @ weights)
    if port_variance <= 0:
        return np.zeros_like(weights)
    marginal = cov_matrix @ weights
    contrib = weights * marginal
    return contrib / port_variance


def effective_bounds(
    weight_bounds: tuple[float, float],
    allow_short: bool,
) -> tuple[float, float]:
    """The single source of truth for the feasible set.

    Under short selling the minimum-weight slider has no meaning — a floor of
    "at least 5% of every asset" contradicts taking short positions. The maximum
    slider is reinterpreted as a cap on absolute position size in either
    direction, so the constraint the user set still binds.
    """
    weight_min, weight_max = weight_bounds
    if allow_short:
        return -weight_max, weight_max
    return weight_min, weight_max


def project_to_bounds(weights: np.ndarray, lb: float, ub: float) -> np.ndarray:
    """Project weights onto {w : sum(w) = 1, lb <= w <= ub}.

    Clipping and then renormalizing does NOT do this — dividing by the sum pushes
    weights straight back out of range. Here any shortfall or excess is absorbed
    only by the coordinates that still have room for it, so the sum constraint and
    the box constraint hold simultaneously.
    """
    w = np.clip(np.asarray(weights, dtype=float), lb, ub)
    for _ in range(64):
        gap = 1.0 - w.sum()
        if abs(gap) < 1e-12:
            break
        room = (ub - w) if gap > 0 else (w - lb)
        total_room = room.sum()
        if total_room <= 1e-15:
            break
        w = np.clip(w + gap * (room / total_room), lb, ub)
    return w


def sample_feasible_weights(
    n_assets: int,
    lb: float,
    ub: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw one random portfolio that actually satisfies the constraints."""
    if lb < 0:
        # Spread around equal weight without dividing by a sum that may be near zero.
        raw = rng.standard_normal(n_assets)
        raw = raw - raw.mean() + 1.0 / n_assets
    else:
        raw = rng.dirichlet(np.ones(n_assets))
    return project_to_bounds(raw, lb, ub)


def validate_constraints(
    n_assets: int,
    weight_min: float,
    weight_max: float,
) -> tuple[bool, str]:
    if weight_min * n_assets > 1.0 + 1e-6:
        return False, (
            f"Restricción infactible: peso mínimo ({weight_min:.0%}) × "
            f"{n_assets} activos = {weight_min * n_assets:.0%} > 100%"
        )
    if weight_max * n_assets < 1.0 - 1e-6:
        return False, (
            f"Restricción infactible: peso máximo ({weight_max:.0%}) × "
            f"{n_assets} activos = {weight_max * n_assets:.0%} < 100%"
        )
    return True, "OK"


def simulate_portfolios(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> pd.DataFrame:
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage, pairwise=pairwise)
    mean_returns, cov_matrix = moments["mean"], moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)
    rf_annual = rf_rate * periods_per_year
    rng = np.random.default_rng(42)
    rows = []

    for _ in range(N_SIMULATIONS):
        w = sample_feasible_weights(n, lb, ub, rng)
        ret, vol, sharpe = portfolio_metrics(w, mean_returns, cov_matrix, rf_rate, periods_per_year)
        rows.append({
            "ret": ret,
            "vol": vol,
            "sharpe": sharpe,
            # **El criterio con el que se elige de verdad, para que el gráfico
            # pueda colorear por él.** La nube salía coloreada por el cociente
            # de Sharpe mientras la estrella se elegía por otra cosa, y en el
            # tramo de exceso negativo los dos ordenan al revés: el 98,1% de
            # estos 10.000 puntos tenía un Sharpe «mejor» que la cartera
            # elegida, y el más brillante era el del 46% de volatilidad. Se
            # calcula aquí, con `criterio_sharpe`, y no en `charts`: dos
            # definiciones del mismo criterio se separan en cuanto alguien
            # toca una.
            "criterio": criterio_sharpe(ret, vol, rf_annual),
            "min_weight": float(w.min()),
            "max_weight": float(w.max()),
        })

    return pd.DataFrame(rows)


def _start_points(n: int, lb: float, ub: float) -> list[np.ndarray]:
    """Equal weight, each single-asset corner, and some random feasible points.

    The Sharpe ratio is a non-convex objective, so a single starting point can
    leave SLSQP parked on a local optimum.
    """
    starts = [project_to_bounds(np.ones(n) / n, lb, ub)]
    for i in range(n):
        corner = np.full(n, max(lb, 0.0))
        corner[i] = ub
        starts.append(project_to_bounds(corner, lb, ub))
    rng = np.random.default_rng(1234)
    starts.extend(sample_feasible_weights(n, lb, ub, rng) for _ in range(_N_RANDOM_STARTS))
    return starts


def optimize_max_sharpe(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage, pairwise=pairwise)
    mean_returns, cov_matrix = moments["mean"], moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)

    rf_annual = rf_rate * periods_per_year

    # **Sin prima no hay Sharpe que repartir, y aquí se decide antes de
    # optimizar.** Una cartera es una combinación convexa, así que su retorno no
    # puede superar al del mejor activo: si ni ése llega a las letras del
    # Tesoro, ninguna cartera factible lo hace.
    #
    # El intento anterior fue maximizar el criterio de Israelsen --`exceso × σ`
    # en la rama negativa-- y no basta. Ese producto tiende a cero por abajo
    # linealmente en las DOS magnitudes, de modo que en cuanto un activo se
    # acerca a la tasa libre de riesgo por debajo su producto gana a cualquier
    # cartera tranquila: con medias (-0.20, -0.22, -0.02) y volatilidades
    # (15 %, 24 %, 46 %) devolvía el 100 % en el activo del 46 %, que es
    # exactamente el defecto que venía a corregir. Y peor: 0,02 puntos básicos
    # de cambio en una media invertían la cartera entera, sobre una media cuyo
    # error estándar es de 35 puntos porcentuales. Elegir ahí es elegir por
    # ruido.
    #
    # Lo defendible es no elegir: si todas las carteras pierden contra las
    # letras, no hay preferencia que los datos sostengan entre ellas salvo
    # arriesgar lo menos posible. Se devuelve mínima varianza y se dice.
    #
    # La comparación es `<=` y no `<`: un retorno exactamente igual al de las
    # letras tampoco es una prima, y con el estricto el aviso se apagaba justo
    # en ese punto dejando la cartera al 100 % en el activo más volátil.
    if float(np.max(mean_returns)) * periods_per_year <= rf_annual:
        refugio = optimize_min_variance(
            returns, rf_rate, periods_per_year, weight_bounds, allow_short,
            shrinkage=shrinkage, pairwise=pairwise,
        )
        if refugio.get("converged"):
            refugio = dict(refugio)
            refugio["sin_prima"] = True
            refugio["message"] = (
                "Ningún activo supera a la tasa libre de riesgo en este "
                "período, así que no hay prima de riesgo que repartir y el "
                "cociente de Sharpe deja de ordenar carteras. Se reparte por "
                "mínima varianza, que es lo único que los datos sostienen aquí: "
                "arriesgar lo menos posible."
            )
        return refugio

    def _puntuacion(w: np.ndarray) -> float:
        port_return, port_vol, _ = portfolio_metrics(
            w, mean_returns, cov_matrix, rf_rate, periods_per_year
        )
        return criterio_sharpe(port_return, port_vol, rf_annual)

    bounds = [(lb, ub)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    best_w, best_score = None, -np.inf
    for x0 in _start_points(n, lb, ub):
        # The start point is itself a feasible candidate, which guarantees the
        # result can never be worse than equal weight.
        s0 = _puntuacion(x0)
        if s0 > best_score:
            best_w, best_score = x0, s0

        result = minimize(
            lambda w: -_puntuacion(w),
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-9},
        )
        if not result.success:
            continue
        w = project_to_bounds(result.x, lb, ub)
        score = _puntuacion(w)
        if score > best_score:
            best_w, best_score = w, score

    if best_w is None:
        return {"converged": False, "message": "SLSQP no encontró una solución factible"}

    ret, vol, sharpe = portfolio_metrics(best_w, mean_returns, cov_matrix, rf_rate, periods_per_year)

    # Llegar aquí significa que algún activo supera a las letras, así que la
    # rama sin prima ya se descartó arriba. Se conserva la clave porque la
    # pantalla y el fichero guardado la leen siempre.
    sin_prima = False
    return {
        "converged": True,
        "weights": best_w,
        "annual_return": ret,
        "annual_vol": vol,
        "sharpe": sharpe,
        "risk_contribution": risk_contribution(best_w, cov_matrix),
        "cov_shrinkage": moments["cov_shrinkage"],
        "mean_shrinkage": moments["mean_shrinkage"],
        "mean": np.asarray(mean_returns, dtype=float),
        "cov": np.asarray(cov_matrix, dtype=float),
        "sin_prima": sin_prima,
        "message": "OK",
    }


def _result(
    weights: np.ndarray,
    moments: dict,
    rf_rate: float,
    periods_per_year: int,
) -> dict:
    ret, vol, sharpe = portfolio_metrics(
        weights, moments["mean"], moments["cov"], rf_rate, periods_per_year
    )
    return {
        "converged": True,
        "weights": weights,
        "annual_return": ret,
        "annual_vol": vol,
        "sharpe": sharpe,
        "risk_contribution": risk_contribution(weights, moments["cov"]),
        "cov_shrinkage": moments["cov_shrinkage"],
        "mean_shrinkage": moments["mean_shrinkage"],
        # Los momentos con los que se ha optimizado de verdad, no los que quien
        # llama pueda recalcular a su manera. La tabla de pesos de la pantalla
        # imprimía la media **muestral** de cada activo mientras el optimizador
        # trabajaba con las encogidas: MSFT «esperaba» un 12,4% y recibía un 27,8%
        # de peso, y nadie podía entender su propia cartera desde la tabla que
        # la describe.
        "mean": np.asarray(moments["mean"], dtype=float),
        "cov": np.asarray(moments["cov"], dtype=float),
        # Ni mínima varianza ni paridad de riesgo miran los retornos esperados,
        # así que su criterio no se rompe en un mercado bajista. Pero «esta
        # cartera pierde contra las letras» se sigue queriendo decir en pantalla,
        # y el contrato de las tres estrategias es el mismo.
        "sin_prima": bool(ret - rf_rate * periods_per_year < 0),
        "message": "OK",
    }


def _resolver_erc(
    cov: np.ndarray,
    n: int,
    lb: float,
    ub: float,
) -> tuple[np.ndarray | None, float]:
    """La mejor cartera de riesgo igualado dentro de la caja, y lo lejos que queda.

    Devuelve `(pesos, desviación)`, donde la desviación es lo que se separa de
    su objetivo la **peor** aportación al riesgo. Un promedio escondería justo
    el caso que importa: una cartera con cuatro activos en su sitio y el quinto
    en el 10% de la varianza cuando le tocaba el 20% es exactamente lo que no se
    puede llamar paridad.

    El objetivo no es convexo, así que un solo arranque puede dejar a SLSQP
    parado en un óptimo local: con ocho activos y ningún tope se quedaba con un
    activo al 0% de la varianza y devolvía «convergido». Los arranques extra
    sólo se pagan cuando el primero no llega, que es el caso raro.
    """
    objetivo = 1.0 / n

    def dispersion(w: np.ndarray) -> float:
        variance = float(w @ cov @ w)
        if variance <= 0:
            return 1e6
        contributions = w * (cov @ w) / variance
        return float(np.sum((contributions - objetivo) ** 2))

    def desviacion(w: np.ndarray) -> float:
        return float(np.max(np.abs(risk_contribution(w, cov) - objetivo)))

    bounds = [(lb, ub)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    def intentar(x0: np.ndarray) -> np.ndarray | None:
        result = minimize(
            dispersion, x0, method="SLSQP", bounds=bounds,
            constraints=constraints, options={"maxiter": 2000, "ftol": 1e-16},
        )
        return project_to_bounds(result.x, lb, ub) if result.success else None

    # La inversa de la volatilidad ES la solución exacta cuando las
    # correlaciones son cero, así que en cualquier mercado real cae muy cerca del
    # óptimo: es el arranque que toca, y el reparto por igual —el único que había—
    # no lo es. Con ocho activos donde uno era mucho más tranquilo que el resto,
    # desde el reparto por igual SLSQP dejaba a ese activo en el 0% de la
    # varianza; desde la inversa de la volatilidad iguala exactamente.
    # El suelo es relativo a la mayor volatilidad y no absoluto: una serie
    # constante daría 1/0 y un arranque de NaN que se lleva por delante el
    # ajuste entero.
    varianzas = np.diag(cov)
    sigma = np.sqrt(np.maximum(varianzas, max(float(np.max(varianzas)), 0.0) * 1e-12))
    inversa = 1.0 / sigma if np.all(sigma > 0) else np.ones(n)
    arranques = [
        project_to_bounds(inversa / inversa.sum(), lb, ub),
        *_start_points(n, lb, ub),
    ]

    mejor_w, mejor_d = None, np.inf
    for x0 in arranques:
        w = intentar(x0)
        if w is None:
            continue
        d = desviacion(w)
        if d < mejor_d:
            mejor_w, mejor_d = w, d
        # La inversa de la volatilidad es el primer arranque y resuelve casi
        # todos los casos; en cuanto uno iguala, los otros veinte no se pagan.
        if mejor_d <= _tolerancia_erc(n):
            break

    return mejor_w, float(mejor_d)


def optimize_min_variance(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    """The portfolio with the smallest possible variance.

    Expected returns are never consulted. That is the point: mean returns carry
    almost all of the estimation error in mean-variance optimisation, so a
    portfolio that ignores them is far more stable out of sample. The trade-off
    is that it makes no attempt to earn a return — it only avoids risk.
    """
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage, pairwise=pairwise)
    cov = moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short)

    result = minimize(
        lambda w: float(w @ cov @ w),
        project_to_bounds(np.ones(n) / n, lb, ub),
        method="SLSQP",
        bounds=[(lb, ub)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}],
        options={"maxiter": 1000, "ftol": 1e-14},
    )
    if not result.success:
        return {"converged": False, "message": result.message}

    return _result(project_to_bounds(result.x, lb, ub), moments, rf_rate, periods_per_year)


def optimize_risk_parity(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool = False,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    """Equal Risk Contribution: every asset supplies the same share of the risk.

    Equal *money* is not equal *risk* — in an equally weighted portfolio a volatile
    asset quietly dominates the total variance. This balances the contributions
    instead of the amounts, using only the covariance matrix, so expected returns
    never enter. Short positions are excluded because a negative weight makes the
    notion of a risk contribution meaningless.
    """
    n = len(returns.columns)
    moments = estimate_moments(returns, shrinkage=shrinkage, pairwise=pairwise)
    cov = moments["cov"]
    lb, ub = effective_bounds(weight_bounds, allow_short=False)
    lb = max(lb, 0.0)

    mejor, desviacion = _resolver_erc(cov, n, lb, ub)
    if mejor is None:
        return {
            "converged": False,
            "message": "SLSQP no encontró una cartera factible para igualar el riesgo",
        }

    if desviacion <= _tolerancia_erc(n):
        return _result(mejor, moments, rf_rate, periods_per_year) | {
            "erc_exacto": True,
            "erc_desviacion": desviacion,
        }

    # No iguala. Quedan dos explicaciones muy distintas y sólo una es culpa del
    # ajuste: si la cartera ERC **sin tope** existe y se sale de la caja que el
    # usuario fijó, entonces ninguna cartera dentro de la caja puede igualar, y
    # lo que hay que decirle es que afloje el tope. Si en cambio la solución
    # libre cabría, el tope no es el problema y no hemos sabido resolverlo.
    libre, desviacion_libre = _resolver_erc(cov, n, 0.0, 1.0)
    tope_manda = (
        libre is not None
        and desviacion_libre <= _tolerancia_erc(n)
        and (libre.max() > ub + 1e-9 or libre.min() < lb - 1e-9)
    )
    if not tope_manda:
        return {
            "converged": False,
            "message": (
                "No se ha podido igualar el riesgo entre los activos: la peor "
                f"aportación se desvía {desviacion:.1%} de su objetivo. Prueba "
                "con menos activos o con más historial."
            ),
        }

    contribuciones = risk_contribution(mejor, cov)
    peor = int(np.argmax(np.abs(contribuciones - 1.0 / n)))
    # Cuál de los dos límites es el que estorba, para no mandar al usuario a
    # mover el deslizador equivocado.
    if libre.max() > ub + 1e-9:
        estorba = f"el peso máximo del {ub:.0%} por activo"
        remedio = "Sube el peso máximo"
    else:
        estorba = f"el peso mínimo del {lb:.0%} por activo"
        remedio = "Baja el peso mínimo"
    return _result(mejor, moments, rf_rate, periods_per_year) | {
        "erc_exacto": False,
        "erc_desviacion": desviacion,
        "message": (
            f"Con estos límites no existe: igualar el riesgo pediría un peso de "
            f"{libre[int(np.argmax(np.abs(libre - np.clip(libre, lb, ub))))]:.0%} "
            f"en algún activo y {estorba} lo impide. Así, "
            f"«{returns.columns[peor]}» aporta el {contribuciones[peor]:.0%} del "
            f"riesgo en vez del {1.0 / n:.0%} que le tocaría. {remedio} si quieres "
            "una paridad exacta."
        ),
    }


STRATEGY_LABELS: dict[str, str] = {
    "max_sharpe": "Máximo Sharpe (Markowitz)",
    "min_variance": "Mínima varianza",
    "risk_parity": "Paridad de riesgo",
}

_STRATEGIES = {
    "max_sharpe": optimize_max_sharpe,
    "min_variance": optimize_min_variance,
    "risk_parity": optimize_risk_parity,
}


def optimize_portfolio(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    weight_bounds: tuple[float, float],
    allow_short: bool,
    strategy: str = "max_sharpe",
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    """Run one of the available allocation strategies behind a common interface."""
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"Estrategia desconocida: {strategy!r}. "
            f"Opciones válidas: {', '.join(_STRATEGIES)}"
        )

    # Con la covarianza por pares los retornos llegan con huecos, y una ventana
    # puede caer entera antes de que un activo existiera. Ahi no hay momentos
    # que estimar --ni varianza propia ni una sola fecha comun de la que sacar
    # las medias-- y devolver "no convergio" deja que el walk-forward salte esa
    # ventana con la maquinaria que ya tiene, en vez de propagar NaN.
    if pairwise:
        por_activo = returns.notna().sum()
        comunes = int(returns.notna().all(axis=1).sum())
        if len(por_activo) and (int(por_activo.min()) < _MINIMO_POR_ACTIVO
                                or comunes < _MINIMO_POR_ACTIVO):
            faltan = list(por_activo[por_activo < _MINIMO_POR_ACTIVO].index)
            return {
                "converged": False,
                "message": (
                    f"Sin historial suficiente en esta ventana"
                    + (f" para {', '.join(map(str, faltan))}" if faltan else "")
                    + f" ({comunes} fechas comunes)"
                ),
            }
    return _STRATEGIES[strategy](
        returns, rf_rate, periods_per_year, weight_bounds, allow_short,
        shrinkage=shrinkage, pairwise=pairwise,
    )


def equal_weight_portfolio(
    returns: pd.DataFrame,
    rf_rate: float,
    periods_per_year: int,
    shrinkage: bool = False,
    pairwise: bool = False,
) -> dict:
    n = len(returns.columns)
    weights = np.ones(n) / n
    moments = estimate_moments(returns, shrinkage=shrinkage, pairwise=pairwise)
    ret, vol, sharpe = portfolio_metrics(
        weights, moments["mean"], moments["cov"], rf_rate, periods_per_year
    )
    return {"weights": weights, "annual_return": ret, "annual_vol": vol, "sharpe": sharpe}
