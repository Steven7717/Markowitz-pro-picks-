"""Cuándo una cartera pide rebalanceo, y cuándo la operación no compensa.

**Este fichero está congelado.** Vive aparte del código que lo usa por la misma
razón que `ranking/criterio.py`: la fecha del commit que lo introduce es la
prueba de que los umbrales no se movieron al ver los números de ninguna cartera
real. Cambiarlos exige una enmienda fechada en el diseño, no una edición.

Es el estándar metodológico que hizo creíble el veredicto del sub-proyecto D, y
aquí importa igual: una banda elegida después de mirar tu propia deriva no es un
criterio, es una racionalización.
"""

# Cinco puntos porcentuales de desviación absoluta.
BANDA_ABSOLUTA = 0.05

# O un 25% del peso objetivo, lo que ocurra primero.
BANDA_RELATIVA = 0.25

# El coste de una operación no puede pasar de esta fracción de su importe.
COSTE_MAXIMO = 0.01


def fuera_de_banda(desviacion: float, objetivo: float) -> bool:
    """Whether one asset has drifted far enough to be worth acting on.

    Los dos umbrales existen porque ninguno funciona solo. Con sólo la banda
    absoluta, un activo cuyo objetivo es el 3% tendría que llegar al 8% —casi
    triplicarse— para disparar, así que en la práctica nunca se rebalancearía.
    Con sólo la relativa, un activo del 40% dispara al llegar al 50%, que en una
    cartera concentrada puede ser la oscilación de dos semanas.

    **La banda relativa no se aplica con objetivo cero.** El 25% de cero es
    cero, y `abs(desviacion) >= 0` es cierto incluso para una desviación de
    cero: sin la guarda, un activo que no está en el objetivo dispararía siempre,
    y hasta uno que no se tiene. Esos casos se tratan aparte, en su propio
    bloque de la pantalla.
    """
    if abs(desviacion) >= BANDA_ABSOLUTA:
        return True
    return objetivo > 0 and abs(desviacion) >= BANDA_RELATIVA * objetivo


def merece_la_pena(importe: float, coste: float) -> bool:
    """Whether the trade is big enough that its cost does not eat it.

    Es lo que hace el criterio económico y no sólo geométrico. Sin esto, un
    activo fuera de banda por veinte dólares generaría una propuesta que cuesta
    cinco — y el sub-proyecto D ya concluyó que ninguna de las siete señales
    técnicas evaluadas tiene ventaja, así que operar de más es el único
    destructor de valor garantizado que queda en esta pantalla.

    El importe se toma en valor absoluto: una venta llega con signo negativo y
    cuesta lo mismo que la compra equivalente.
    """
    if importe == 0:
        return False
    return coste <= COSTE_MAXIMO * abs(importe)
