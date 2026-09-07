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

from dataclasses import dataclass
from datetime import date

import pandas as pd
from scipy.optimize import brentq

from seguimiento import posiciones

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


# El intervalo en el que se busca la raiz. -0,999 y no -1: en -1 el
# denominador (1+r) vale cero y la funcion no esta definida. El techo de 10 son
# 1.000% anual, muy por encima de cualquier cartera real, y acotar es lo que
# convierte "no converge" en "no hay solucion aqui" en vez de en un bucle.
_SUELO_TIR = -0.999
_TECHO_TIR = 10.0


def _valor_actual(flujos: "list[tuple[date, float]]", tasa: float) -> float:
    origen = flujos[0][0]
    return sum(
        importe / (1.0 + tasa) ** ((cuando - origen).days / 365.0)
        for cuando, importe in flujos
    )


def tir(flujos: "list[tuple[date, float]]") -> float | None:
    """Money-weighted return (XIRR), or None when there is no answer.

    Raíz de `Σ CF_i / (1+r)^(d_i/365) = 0`, con `brentq` sobre un intervalo
    acotado. Aportaciones negativas, retiros positivos, y el valor actual de la
    cartera positivo al cierre.

    **Devuelve `None` en vez de un número siempre que no haya una respuesta
    defendible.** Con flujos mezclados la ecuación puede tener varias raíces o
    ninguna, y una TIR inventada es indistinguible de una real: no lleva marca,
    no tiene unidades raras, y el usuario la lee como si alguien la hubiera
    medido. Los tres casos en que se devuelve `None`:

    - **Menos de dos flujos.** No hay ecuación que resolver.
    - **Todos del mismo signo.** No existe tasa que los anule, porque el valor
      actual nunca cruza el cero.
    - **Menos de 30 días.** Misma guarda que `anualizar`: la TIR *es* una tasa
      anual, así que en tres días no hay nada que dar.
    """
    if len(flujos) < 2:
        return None

    ordenados = sorted(flujos, key=lambda par: par[0])
    dias = (ordenados[-1][0] - ordenados[0][0]).days
    if dias < MINIMO_DIAS_ANUALIZAR:
        return None

    importes = [importe for _, importe in ordenados]
    if not (any(v > 0 for v in importes) and any(v < 0 for v in importes)):
        return None

    bajo = _valor_actual(ordenados, _SUELO_TIR)
    alto = _valor_actual(ordenados, _TECHO_TIR)
    if bajo == 0.0:
        return _SUELO_TIR
    if alto == 0.0:
        return _TECHO_TIR
    if (bajo > 0) == (alto > 0):
        # Sin cambio de signo no hay raíz dentro del intervalo. **Esta guarda no
        # cambia lo que se devuelve para ninguna entrada**: sin ella, `brentq`
        # lanzaría `ValueError` y el `except` de abajo devolvería `None` igual.
        # Está porque reconocer explícitamente un caso que sabemos nombrar es
        # mejor que llegar a él por una excepción, y porque así el `except`
        # queda como lo que debe ser — la red para lo que no supimos prever, no
        # el camino normal. Ningún test conductual puede pinzarla, y decirlo
        # aquí evita que alguien escriba uno creyendo que sí.
        return None

    try:
        return float(brentq(lambda r: _valor_actual(ordenados, r), _SUELO_TIR, _TECHO_TIR))
    except (ValueError, RuntimeError):
        return None


@dataclass(frozen=True)
class Linea:
    """Un activo del libro: lo que se tiene, lo que costó y lo que ha dado."""

    ticker: str
    acciones: float
    coste_medio: float
    precio: float | None
    valor: float | None
    latente: float | None
    realizada: float
    dividendos: float
    contribucion: float | None


def por_activo(
    asientos: "list", precios_actuales: dict[str, float]
) -> dict[str, Linea]:
    """Per-asset cost, gain and contribution, in dollars.

    **Coste medio ponderado, no FIFO.** Cambia el reparto entre ganancia
    realizada y latente, nunca el total. Es más simple, no pretende ser un
    cálculo fiscal, y queda declarado en pantalla.

    La contribución va **en dólares**: cuánto de la ganancia total viene de cada
    activo. Es exacto y suma. Un porcentaje de contribución con aportaciones de
    por medio compara cada activo contra un capital que no fue el suyo durante
    todo el periodo, y por eso no se muestra.

    Un activo sin precio actual vuelve con `valor`, `latente` y `contribucion`
    en `None`, no en cero. Valorarlo a cero restaría la posición entera de la
    ganancia sin decir por qué; `None` es lo que hace que quien lo pinta escriba
    "—" con `cartera.formato_cifra`.
    """
    acciones: dict[str, float] = {}
    coste: dict[str, float] = {}
    realizada: dict[str, float] = {}
    dividendos: dict[str, float] = {}

    for a in posiciones.ordenados(posiciones.vigentes(asientos)):
        if a.tipo == "compra":
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
            coste[a.ticker] = coste.get(a.ticker, 0.0) + a.importe + a.comision
        elif a.tipo == "venta":
            tiene = acciones.get(a.ticker, 0.0)
            medio = (coste.get(a.ticker, 0.0) / tiene) if tiene else 0.0
            realizada[a.ticker] = (
                realizada.get(a.ticker, 0.0)
                + (a.precio - medio) * a.acciones
                - a.comision
            )
            acciones[a.ticker] = tiene - a.acciones
            # El coste baja en proporcion a lo vendido, para que el coste medio
            # de lo que queda no se mueva: vender no cambia lo que costo el
            # resto.
            coste[a.ticker] = medio * acciones[a.ticker]
        elif a.tipo == "dividendo":
            dividendos[a.ticker] = dividendos.get(a.ticker, 0.0) + a.importe

    lineas = {}
    for ticker in sorted(set(acciones) | set(realizada) | set(dividendos)):
        n = acciones.get(ticker, 0.0)
        c = coste.get(ticker, 0.0)
        medio = c / n if n else 0.0
        precio = precios_actuales.get(ticker)
        valor = n * precio if precio is not None else None
        latente = valor - c if valor is not None else None
        real = realizada.get(ticker, 0.0)
        divs = dividendos.get(ticker, 0.0)
        lineas[ticker] = Linea(
            ticker=ticker,
            acciones=n,
            coste_medio=medio,
            precio=precio,
            valor=valor,
            latente=latente,
            realizada=real,
            dividendos=divs,
            contribucion=None if latente is None else latente + real + divs,
        )
    return lineas
