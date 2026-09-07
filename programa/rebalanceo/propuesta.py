"""Qué hacer, en dos bloques separados porque uno es barato y el otro no.

Primero el reparto del efectivo, que corrige deriva sin vender nada. Y sólo si
con eso no basta, las ventas y compras que faltan — cada una con su coste al
lado, y las que no compensan mostradas igualmente en vez de omitidas.

Este módulo **no escribe nada en el libro**. Propone; el usuario registra en la
pantalla de seguimiento lo que de verdad ejecutó en el bróker. Si escribiera,
el libro mezclaría hechos con intenciones sin forma de separarlos después.
"""

from dataclasses import dataclass

from rebalanceo import coste as coste_mod
from rebalanceo import criterio, deriva as deriva_mod, reparto as reparto_mod


@dataclass(frozen=True)
class Operacion:
    """Una compra o una venta propuesta, con lo que costaría."""

    ticker: str
    accion: str
    importe: float
    coste: float
    viable: bool


@dataclass(frozen=True)
class Propuesta:
    """El plan entero: la deriva, qué hacer con el efectivo, y qué falta."""

    deriva: "deriva_mod.Deriva"
    con_efectivo: tuple[Operacion, ...]
    y_ademas: tuple[Operacion, ...]
    descartadas_por_coste: tuple[Operacion, ...]
    basta_con_la_aportacion: bool
    coste_por_operacion: float
    coste_del_libro: bool
    coste_total: float


def construir(
    valores: "dict[str, float | None]",
    objetivo: dict[str, float],
    efectivo: float,
    asientos: "list",
    coste_declarado: float,
) -> Propuesta:
    """Assemble the whole plan from the book's current state.

    `basta_con_la_aportacion` es `True` cuando después de repartir el efectivo
    no queda nada fuera de banda. **Se devuelve como un hecho propio y no se
    deduce de que `y_ademas` esté vacía**: esa lista también sale vacía cuando
    todas las operaciones se descartaron por coste, y las dos situaciones dicen
    cosas opuestas al usuario.
    """
    por_operacion, del_libro = coste_mod.por_operacion(asientos, coste_declarado)

    antes = deriva_mod.calcular(valores, objetivo)
    con_precio = {t: v for t, v in valores.items() if v is not None}
    # De `antes.pesos` y no de `antes.lineas`: con una cartera que todavia no ha
    # comprado nada, `lineas` sale vacia y reconstruir los pesos desde ahi
    # dejaria el reparto sin objetivo al que apuntar -- justo en el caso en que
    # hay todo el efectivo por asignar.
    pesos = antes.pesos

    # Solo lo que el objetivo contempla. Los pesos suman uno, asi que aplicarlos
    # sobre un total que incluye activos que nadie va a vender pediria que el
    # plan ocupase el cien por cien de un dinero del que otra cosa ya se lleva
    # una parte.
    en_plan = {t: v for t, v in con_precio.items() if pesos.get(t, 0.0) > 0}
    reparto = reparto_mod.repartir(en_plan, pesos, efectivo, por_operacion)
    con_efectivo = tuple(
        Operacion(t, "comprar", importe, por_operacion, True)
        for t, importe in sorted(reparto.asignaciones.items())
    )

    # La cartera tal como quedaria tras invertir el efectivo, que es contra lo
    # que se decide si ademas hace falta vender.
    despues_valores = {
        t: en_plan.get(t, 0.0) + reparto.asignaciones.get(t, 0.0)
        for t in set(en_plan) | set(reparto.asignaciones)
    }
    despues = deriva_mod.calcular(despues_valores, pesos)
    pendientes = [l for l in despues.lineas if l.fuera_de_banda]

    y_ademas, descartadas = [], []
    if pendientes:
        # **Se rebalancea el plan entero, no solo lo que rompio la banda.** La
        # banda decide CUANDO tocar la cartera; una vez que se toca, se vuelve al
        # objetivo completo. Y no es una preferencia de estilo: moviendo solo los
        # activos fuera de banda, las ventas no tienen por que cubrir las
        # compras, y la propuesta pide dinero que no hay. Con el plan entero,
        # `Σ(objetivo_i − valor_i) = en_plan − en_plan = 0` por construccion.
        for linea in despues.lineas:
            objetivo_valor = despues.en_plan * linea.peso_objetivo
            importe = objetivo_valor - linea.valor
            if importe == 0:
                continue
            operacion = Operacion(
                ticker=linea.ticker,
                accion="comprar" if importe > 0 else "vender",
                importe=importe,
                coste=por_operacion,
                viable=criterio.merece_la_pena(importe, por_operacion),
            )
            (y_ademas if operacion.viable else descartadas).append(operacion)

    return Propuesta(
        deriva=antes,
        con_efectivo=con_efectivo,
        y_ademas=tuple(y_ademas),
        descartadas_por_coste=tuple(descartadas),
        basta_con_la_aportacion=not pendientes,
        coste_por_operacion=por_operacion,
        coste_del_libro=del_libro,
        coste_total=por_operacion * (len(con_efectivo) + len(y_ademas)),
    )
