"""Cuánto rindió la cartera, medido de las dos formas que hacen falta.

Con aportaciones de por medio ningún número suelto responde las dos preguntas.
`valor actual / total aportado − 1` no es el rendimiento de la cartera: mezcla
lo que rindieron los activos con cuándo entró el dinero.

- **TWR** neutraliza el calendario de aportaciones y es lo único comparable
  contra el S&P 500 o contra 1/N.
- **TIR** es lo que ganó el usuario de verdad, con su timing dentro.

Cuando los dos se separan, la diferencia *es* el efecto de las aportaciones. Es
información, no ruido, y la pantalla lo dice.
"""

import pandas as pd

# Por debajo de un mes, anualizar convierte un ruido en una afirmación: un 2% en
# tres días sale a +780% anual. Se devuelve el retorno del periodo, sin
# anualizar, y quien lo muestra dice que lo es.
MINIMO_DIAS_ANUALIZAR = 30

# Cualquier valor de cartera por debajo de esto es polvo de redondeo, no
# capital. Sirve de denominador cero.
_MINIMO_DENOMINADOR = 1e-9


def twr(valor: pd.Series, flujos: pd.Series) -> float:
    """Time-weighted return over the whole series, not annualised.

    `r_t = (V_t − F_t) / V_{t−1} − 1`, encadenado. El flujo se trata como si
    llegara al final del día: el dinero que entró hoy no participó del
    movimiento de hoy desde el cierre de ayer, que es lo que este cociente mide.

    Eso deja fuera el movimiento intradía de lo comprado hoy —se compró a un
    precio y cerró a otro— y es la aproximación estándar del TWR diario. El
    efecto es de céntimos frente a la alternativa, que sería valorar la cartera
    dos veces al día con datos que yfinance no da.

    **`V_{t−1} = 0` no es una división por cero, es un día sin cartera.** Pasa el
    primer día y cada vez que se vacía y se vuelve a empezar. El retorno de ese
    día es indefinido y se toma como 0: no hubo capital expuesto, así que no
    hubo nada que rindiera.
    """
    if len(valor) < 2:
        return 0.0

    factor = 1.0
    anterior = float(valor.iloc[0])
    for dia in valor.index[1:]:
        actual = float(valor.loc[dia])
        flujo = float(flujos.loc[dia]) if dia in flujos.index else 0.0
        if anterior > _MINIMO_DENOMINADOR:
            factor *= (actual - flujo) / anterior
        anterior = actual
    return factor - 1.0


def anualizar(retorno: float, dias: float) -> float | None:
    """The period return as an annual rate, or None when the period is too short.

    Devolver `None` y no un número es deliberado: quien lo pinta usa
    `cartera.formato_cifra`, que escribe "—" y nunca un 0,00. Un cero ahí se
    leería como "no rindió nada", que es una afirmación que nadie hizo.
    """
    if dias < MINIMO_DIAS_ANUALIZAR or dias <= 0:
        return None
    return (1.0 + retorno) ** (365.0 / dias) - 1.0
