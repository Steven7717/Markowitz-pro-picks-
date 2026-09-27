"""Del rendimiento en dolares al rendimiento real en pesos.

Tres pasos, en este orden y no en otro: convertir a pesos con el FIX de cada
fecha, medir con las mismas funciones de `rendimiento`, y descontar la
inflacion con Fisher. Descontar el INPC de un rendimiento en dolares mezcla dos
monedas y da un numero plausible que no mide nada.

Aqui no hay red: las series llegan ya descargadas de `seguimiento/banxico.py`.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from seguimiento import rendimiento


def real(nominal: "float | None", inflacion_anual: "float | None") -> "float | None":
    """Ecuacion de Fisher exacta: `(1 + nominal) / (1 + π) − 1`.

    No `nominal − π`. Con la inflacion mexicana la aproximacion se equivoca en
    decimas, y ese error pasaria desapercibido en pantalla: no es que no se
    vea, es que nadie lo notaria. Un `None` en cualquiera de las dos entradas
    es «no se puede medir», y lo sigue siendo a la salida.
    """
    if nominal is None or inflacion_anual is None or inflacion_anual <= -1.0:
        return None
    return (1.0 + nominal) / (1.0 + inflacion_anual) - 1.0


def en_pesos(
    valor: pd.Series, flujos: pd.Series, fix: "pd.Series | None"
) -> "tuple[pd.Series, pd.Series] | None":
    """El valor diario y los flujos, en pesos, con el FIX de cada fecha.

    Flujo a flujo y no con el atajo `(1 + r_USD)(1 + Δtc) − 1`: el atajo da la
    TWR bien, pero la TIR sale mal en cuanto hay aportaciones, porque cada una
    entro a un tipo de cambio distinto.

    Un dia sin FIX (fin de semana, o un festivo mexicano que en EE. UU. es habil)
    usa el ultimo publicado. **Hacia atras no se arrastra nada**: si la serie
    empieza antes del primer FIX disponible devuelve `None`, porque el tipo de
    cambio de ese dia no lo sabe nadie aqui.
    """
    if fix is None or fix.empty:
        return None
    fix = fix.sort_index()
    # Dos publicaciones para el mismo dia no deberian pasar, pero si pasan la
    # ultima es la vigente, no un promedio ni una excepcion.
    fix = fix[~fix.index.duplicated(keep="last")]
    calendario = valor.index.union(flujos.index)
    alineado = fix.reindex(fix.index.union(calendario)).ffill().reindex(calendario)
    if alineado.isna().any():
        return None
    return valor * alineado.reindex(valor.index), flujos * alineado.reindex(flujos.index)


def fix_en(fix: pd.Series, dia) -> "float | None":
    """El FIX vigente un dia: el de ese dia o el ultimo publicado antes."""
    anteriores = fix.sort_index().loc[: pd.Timestamp(dia)]
    return float(anteriores.iloc[-1]) if len(anteriores) else None


# Para extender el INPC mas alla del ultimo publicado: una tasa mensual se
# aplica en proporcion a los dias, como doce meses por año. Es un mes
# promedio (365/12 dias) a proposito: la extension no conoce la duracion real
# del mes siguiente, mientras que la interpolacion dentro de un mes ya
# publicado (en `nivel`) si usa los dias reales entre sus dos anclas.
_MESES_POR_DIA = 12 / 365


@dataclass(frozen=True)
class Inflacion:
    """La inflacion de un periodo y hasta donde es oficial.

    `estimada` no es un detalle: el INPC se publica hacia el dia 9 del mes
    siguiente, asi que los ultimos dias de una cartera casi nunca lo tienen. Se
    extienden con la ultima tasa mensual y la pantalla lo dice.
    """

    acumulada: float
    anual: "float | None"
    oficial_hasta: date
    estimada: bool
    tasa_extension: "float | None" = None


def anclar(inpc: pd.Series) -> pd.Series:
    """El INPC fechado al cierre de su mes, no al dia 1 que usa Banxico.

    Dos publicaciones ancladas al mismo mes no deberian pasar, pero si pasan
    (una revision, un dato duplicado) se queda la ultima por fecha original:
    es la mas reciente, no la primera que llego.
    """
    serie = inpc.dropna().sort_index()
    serie = pd.Series(
        serie.values,
        index=pd.DatetimeIndex(serie.index).to_period("M").to_timestamp(how="end").normalize(),
    )
    return serie[~serie.index.duplicated(keep="last")]


def _tasa_mensual_extension(anclado: pd.Series) -> float:
    """La tasa mensual con la que se extiende el INPC mas alla del ultimo dato.

    No es la razon cruda entre las ultimas dos anclas: si entre ellas hay un
    hueco de varios meses (un INPC que falto por descargar), esa razon es la
    acumulada del hueco entero, no la de un mes. Se reparte entre los meses de
    calendario que separan las dos anclas (minimo uno) para que la extension
    seguida sea siempre una tasa mensual, tenga o no huecos el historico.
    """
    ultimo, penultimo = anclado.index[-1], anclado.index[-2]
    meses = max(1, (ultimo.year * 12 + ultimo.month) - (penultimo.year * 12 + penultimo.month))
    razon = anclado.iloc[-1] / anclado.iloc[-2]
    return float(razon ** (1.0 / meses))


def nivel(anclado: pd.Series, dia: date) -> "float | None":
    """El nivel del indice en un dia, interpolado o extendido.

    Entre dos cierres de mes, geometrico por dias. Despues del ultimo, la ultima
    tasa mensual conocida. Antes del primero, `None`: no se extrapola hacia
    atras.
    """
    cuando = pd.Timestamp(dia)
    if anclado.empty or cuando < anclado.index[0]:
        return None
    if cuando > anclado.index[-1]:
        if len(anclado) < 2:
            return None
        tasa = _tasa_mensual_extension(anclado)
        dias = (cuando - anclado.index[-1]).days
        return float(anclado.iloc[-1] * tasa ** (dias * _MESES_POR_DIA))
    posicion = int(anclado.index.searchsorted(cuando))
    if anclado.index[posicion] == cuando:
        return float(anclado.iloc[posicion])
    antes, despues = anclado.index[posicion - 1], anclado.index[posicion]
    fraccion = (cuando - antes).days / (despues - antes).days
    razon = anclado.iloc[posicion] / anclado.iloc[posicion - 1]
    return float(anclado.iloc[posicion - 1] * razon ** fraccion)


def inflacion_periodo(inpc: pd.Series, desde: date, hasta: date) -> "Inflacion | None":
    """La inflacion entre dos fechas, anualizada con la misma guarda que la TWR.

    `None` si alguna de las dos fechas no tiene nivel, o si el periodo esta al
    reves (`hasta` antes que `desde`: no hay dias que anualizar y la
    "inflacion" saldria con el signo de una resta que nadie pidio). Por debajo
    de 30 dias devuelve la acumulada con `anual=None`, igual que
    `rendimiento.anualizar`.
    """
    if pd.Timestamp(hasta) < pd.Timestamp(desde):
        return None
    anclado = anclar(inpc)
    inicio, fin = nivel(anclado, desde), nivel(anclado, hasta)
    if inicio is None or fin is None:
        return None
    acumulada = fin / inicio - 1.0
    dias = (pd.Timestamp(hasta) - pd.Timestamp(desde)).days
    estimada = bool(pd.Timestamp(hasta) > anclado.index[-1])
    return Inflacion(
        acumulada=acumulada,
        anual=rendimiento.anualizar(acumulada, dias=dias),
        oficial_hasta=anclado.index[-1].date(),
        estimada=estimada,
        tasa_extension=(_tasa_mensual_extension(anclado) - 1.0) if estimada else None,
    )
