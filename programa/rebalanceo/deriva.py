"""Cuánto se ha separado la cartera real de la que se decidió tener.

El denominador es el **valor invertido**, no el patrimonio con el efectivo
dentro. Si el efectivo entrara, meter 10.000 en una cartera de 10.000 pondría
todos los activos al 50% de su peso objetivo y el medidor entero se volvería
rojo — por una aportación que aún no se ha invertido, no porque nada se haya
desviado. La deriva mide la **mezcla**; el efectivo es otra cosa y se trata
aparte, en `rebalanceo.reparto`.
"""

from dataclasses import dataclass

from rebalanceo import criterio


@dataclass(frozen=True)
class Desvio:
    """Un activo: lo que vale, el peso que ocupa y el que debería ocupar."""

    ticker: str
    valor: float
    peso_real: float
    peso_objetivo: float
    desviacion: float
    fuera_de_banda: bool


@dataclass(frozen=True)
class Deriva:
    """La cartera entera frente a su objetivo, más lo que no encaja en él."""

    invertido: float
    lineas: tuple[Desvio, ...]
    fuera_del_objetivo: tuple[Desvio, ...]
    sin_precio: tuple[str, ...]
    pesos_normalizados: bool
    # Los objetivo ya normalizados. Viajan aqui porque `lineas` sale vacia
    # cuando no hay nada invertido, y quien reparta el efectivo de una cartera
    # que aun no ha comprado nada los necesita igual.
    pesos: dict[str, float]


def calcular(
    valores: "dict[str, float | None]", objetivo: dict[str, float]
) -> Deriva:
    """Real weights against target weights, and what that puts out of band.

    `valores` viene de `seguimiento.rendimiento.por_activo`, donde un activo sin
    precio actual trae `valor=None`. Esos **no se valoran a cero**: se apartan y
    vuelven nombrados en `sin_precio`. Contarlos como cero rebajaría el total y
    falsearía la deriva de todos los demás, no sólo la suya, y nada en pantalla
    lo explicaría.

    Los pesos objetivo se normalizan si no suman uno, y se avisa. No es
    hipotético: el equal-weight se calcula sobre los tickers del portafolio
    guardado, y si alguno deja de tener precios el resto suma menos de uno.
    """
    sin_precio = tuple(t for t, v in valores.items() if v is None)
    con_precio = {t: float(v) for t, v in valores.items() if v is not None}
    invertido = sum(con_precio.values())

    suma = sum(objetivo.values())
    normalizados = bool(objetivo) and abs(suma - 1.0) > 1e-9
    pesos = {t: w / suma for t, w in objetivo.items()} if normalizados and suma else dict(objetivo)

    if invertido <= 0:
        # Sin valor no hay mezcla que medir, y eso no es lo mismo que una
        # deriva de cero. Se devuelve vacio para que la pantalla lo diga.
        return Deriva(0.0, (), (), sin_precio, normalizados, pesos)

    lineas, ajenos = [], []
    for ticker in sorted(set(con_precio) | set(pesos)):
        valor = con_precio.get(ticker, 0.0)
        peso_real = valor / invertido
        peso_objetivo = pesos.get(ticker, 0.0)
        desviacion = peso_real - peso_objetivo
        desvio = Desvio(
            ticker=ticker,
            valor=valor,
            peso_real=peso_real,
            peso_objetivo=peso_objetivo,
            desviacion=desviacion,
            fuera_de_banda=criterio.fuera_de_banda(desviacion, peso_objetivo),
        )
        (ajenos if peso_objetivo <= 0 else lineas).append(desvio)

    # De mayor a menor urgencia: el tamaño de la desviacion (en valor
    # absoluto) es lo que importa, no su signo — un activo un 30% por debajo
    # de su objetivo pide tanta atencion como uno un 30% por encima. Asi la
    # pantalla pinta arriba lo mas urgente sin ordenar nada por su cuenta.
    lineas.sort(key=lambda d: abs(d.desviacion), reverse=True)
    return Deriva(invertido, tuple(lineas), tuple(ajenos), sin_precio,
                  normalizados, pesos)
