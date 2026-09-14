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

from seguimiento.precios import celda


def equal_weight(tickers: list[str]) -> dict[str, float]:
    """1/N over the given tickers. Empty in, empty out."""
    if not tickers:
        return {}
    peso = 1.0 / len(tickers)
    return {t: peso for t in tickers}


def referencia(
    flujos: pd.Series, pesos: dict[str, float], historia
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

    ## Por qué recibe la `Historia` entera y no una tabla de cierres

    Porque los cierres van **sin ajustar**, que es el punto entero de
    `seguimiento/precios.py`: un precio ajustado cambia hacia atrás cada vez que
    la empresa parte la acción o reparte un dividendo, y en un libro de
    posiciones eso produce un coste de adquisición que se mueve solo. Lo que
    cuesta esa decisión es que el día de un split el cierre se parte a la mitad,
    y las participaciones compradas antes **tienen que duplicarse** o la línea
    se hunde.

    Mientras esto recibió sólo los cierres no había forma de que se enterara, y
    el resultado estaba medido: con un 2:1 de por medio, «repartir por igual
    (1/N)» marcaba 500,00 donde lo correcto son 1.020,00 —el 51% de su valor
    perdido en un día— y el gráfico concluía que la cartera del usuario le
    sacaba un 114% a repartir por igual. Los dividendos empujaban hacia el mismo
    lado: la referencia no los cobraba y la cartera real sí. **Las dos
    desviaciones favorecían al usuario**, que es la peor dirección posible para
    el error de una comparación que existe precisamente para desengañarle.

    Los dividendos se quedan **como efectivo y no se reinvierten**, igual que en
    `posiciones.serie`. Reinvertirlos haría que la referencia rebalanceara, que
    es justo lo que ninguna de estas líneas hace.
    """
    # Mismo arrastre que en `posiciones.serie`, y por lo mismo: un hueco de
    # precio es un fallo de datos, no una acción que valga cero. Aquí envenena
    # más todavía, porque el valor del día se suma con `float()` uno a uno y un
    # solo NaN convierte el total en NaN en vez de restar sólo su parte.
    cierres = historia.cierres.ffill()
    calendario = cierres.index
    disponibles = [t for t in pesos if t in cierres.columns]

    participaciones = {t: 0.0 for t in disponibles}
    caja = 0.0
    valores = []

    for dia in calendario:
        # 1. El split parte las participaciones lo primero, por lo mismo que en
        #    `posiciones.serie`: lo que se compre hoy se compra ya partido, así
        #    que el factor es de lo que había ayer.
        for ticker in disponibles:
            factor = celda(historia.splits, dia, ticker)
            if factor > 0 and participaciones[ticker]:
                participaciones[ticker] *= factor

        # 2. La foto de la fecha ex, tomada ANTES del flujo del día: para cobrar
        #    hay que tener las participaciones al cierre anterior, y quien
        #    compra el mismo día compra ya sin el dividendo —el mercado acaba de
        #    descontarlo del precio al que compra—.
        ex = dict(participaciones)

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

        # 3. Y el dividendo, sobre la foto de la fecha ex. A caja, como en la
        #    cartera real.
        for ticker in disponibles:
            por_accion = celda(historia.dividendos, dia, ticker)
            if por_accion > 0 and ex[ticker]:
                caja += ex[ticker] * por_accion

        valor = sum(
            participaciones[t] * float(cierres.at[dia, t]) for t in disponibles
        )
        valores.append(valor + caja)

    return pd.Series(valores, index=calendario, dtype=float)
