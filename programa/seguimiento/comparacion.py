"""Contra qué se mide la cartera real.

Las tres referencias —el objetivo teórico, 1/N y el S&P 500— reciben **el mismo
dinero en las mismas fechas** que metió el usuario. Eso es lo que aísla la
elección de activos del calendario de aportaciones: si cada referencia tuviera
su propio calendario, la comparación mediría el calendario y no la cartera.

Ninguna rebalancea. El objetivo teórico es "la cartera que tendrías si hubieras
seguido el plan", y seguir el plan no incluye rebalancear a diario — el
rebalanceo es una decisión con coste, y es justo lo que el sub-proyecto G existe
para medir.
"""

import pandas as pd


def equal_weight(tickers: list[str]) -> dict[str, float]:
    """1/N over the given tickers. Empty in, empty out."""
    if not tickers:
        return {}
    peso = 1.0 / len(tickers)
    return {t: peso for t in tickers}


def referencia(
    flujos: pd.Series, pesos: dict[str, float], cierres: pd.DataFrame
) -> pd.Series:
    """Value over time of investing the same cash flows at fixed weights.

    Cada entrada de dinero compra a los precios **de su día**, nunca a los del
    primero: comprar al precio del día uno sería darle a la referencia una
    información que no tenía, y la comparación dejaría de ser justa en la
    dirección que favorece a la referencia.

    Un retiro sale a prorrata de lo que haya, que es lo más parecido a lo que
    hace alguien que necesita dinero y no quiere cambiar su cartera.

    **La parte asignada a un ticker sin precios se queda como efectivo.** No
    desaparece: hacerla desaparecer subiría el rendimiento de la referencia
    repartiendo el mismo dinero entre menos activos, y la cartera real quedaría
    peor por comparación con algo que nunca existió.
    """
    # Mismo arrastre que en `posiciones.serie`, y por lo mismo: un hueco de
    # precio es un fallo de datos, no una acción que valga cero. Aquí envenena
    # más todavía, porque el valor del día se suma con `float()` uno a uno y un
    # solo NaN convierte el total en NaN en vez de restar sólo su parte.
    cierres = cierres.ffill()
    calendario = cierres.index
    disponibles = [t for t in pesos if t in cierres.columns]

    participaciones = {t: 0.0 for t in disponibles}
    caja = 0.0
    valores = []

    for dia in calendario:
        flujo = float(flujos.loc[dia]) if dia in flujos.index else 0.0

        if flujo > 0:
            for ticker in pesos:
                parte = flujo * pesos[ticker]
                if ticker in participaciones:
                    precio = float(cierres.at[dia, ticker])
                    if precio > 0:
                        participaciones[ticker] += parte / precio
                        continue
                caja += parte
        elif flujo < 0:
            invertido = sum(
                participaciones[t] * float(cierres.at[dia, t]) for t in disponibles
            )
            total = invertido + caja
            if total > 0:
                fraccion = min(1.0, -flujo / total)
                for ticker in disponibles:
                    participaciones[ticker] *= 1.0 - fraccion
                caja *= 1.0 - fraccion

        valor = sum(
            participaciones[t] * float(cierres.at[dia, t]) for t in disponibles
        )
        valores.append(valor + caja)

    return pd.Series(valores, index=calendario, dtype=float)
