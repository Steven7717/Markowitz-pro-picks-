"""Lo que la pantalla de seguimiento enseña, calculado fuera de la pantalla.

Este modulo existe por una razon concreta: hasta el sub-proyecto K, estas
cuentas vivian dentro de `vistas/seguimiento.py`, que es un guion de Streamlit
y **no se puede importar desde un test**. Las correcciones que tienen dentro
--el corte temporal comun, el «—» que no es un cero-- estaban protegidas solo
por un comentario. Un rediseno de la pantalla las habria borrado sin que nada
fallase, porque los numeros que saldrian serian plausibles.
"""

from dataclasses import dataclass

import cartera
from seguimiento import libro as mod, posiciones, rendimiento


@dataclass(frozen=True)
class Cabecera:
    """Las cifras de arriba. `None` significa «no se puede medir»."""

    valor: "float | None"
    aportado: float
    ganancia: "float | None"
    twr_periodo: "float | None"
    twr_anual: "float | None"
    tir: "float | None"
    dividendos: float
    sin_valorar: bool
    dias: int
    # Cuantos DIAS del calendario de la serie tienen flujo externo. Se cuenta
    # aqui porque de este numero depende si la brecha entre TWR y TIR se puede
    # atribuir a algo --ver `aviso_de_brecha`-- y contarlo en la pantalla lo
    # dejaria otra vez fuera del alcance de un test.
    #
    # Dias y no asientos, a proposito: dos aportaciones del mismo dia no son dos
    # momentos distintos, y lo que la explicacion por calendario necesita son
    # momentos.
    flujos: int
    # Cuanto se separa el valor del PRIMER dia de la serie del dinero que
    # habia entrado hasta esa fecha. Con los precios de compra registrados al
    # cierre de ese dia deberia ser cero: lo que mide es la otra causa
    # posible de la brecha TWR/TIR, la de coste contra mercado, y medirla es
    # lo que permite dejar de suponerla. `None` si no hay serie valorada.
    salto_inicial: "float | None" = None
    # Los flujos externos POSTERIORES al primer dia, en valor absoluto. Un
    # centimo es un «momento» pero no mueve una TIR ponderada por dinero.
    flujo_posterior: float = 0.0


def _cifra(valor) -> str:
    """El «—» de `cartera.formato_cifra`, con el separador de miles de aqui.

    No se llama a `formato_cifra` directamente porque escribe `10299.00` donde
    esta pantalla lleva `10,299.00` desde siempre, y cambiar el formato del caso
    normal para arreglar el caso vacio seria pagar el arreglo con una regresion.
    Lo que se copia es la regla, que es lo que importa: `None` no es cero.
    """
    return "—" if valor is None else f"{valor:,.2f}"


def cabecera(marcha, vivos, sin_valorar: bool) -> Cabecera:
    """Las seis cifras de cabecera, con su corte temporal dentro.

    `marcha` es la `posiciones.Marcha` del libro y `vivos` sus asientos
    vigentes. `sin_valorar` NO se decide aqui: lo pasa quien llama, y en
    `vistas/seguimiento.py` es `bool(marcha.posteriores) and
    marcha.posteriores == len(vivos)`. Es la misma condicion que gobierna el
    aviso de la pantalla, y calcularla en dos sitios son dos sitios donde se
    puede desviar --el aviso diria una cosa y las cifras otra.
    """
    # De `marcha.flujos`, no de los asientos. Los dos numeros de arriba se restan
    # entre si, asi que tienen que salir del MISMO corte temporal: `valor` viene de
    # la serie, que acaba en el ultimo cierre disponible, y sumar aqui los asientos
    # de hoy --que la serie todavia no puede valorar-- producia una ganancia
    # inventada. Medido en la app: una aportacion de 10.000 registrada hoy dejaba
    # VALOR 10.299, APORTADO 20.000 y GANANCIA -9.700 sin que nadie hubiera perdido
    # un dolar. `flujos` son ya las aportaciones menos los retiros dentro del
    # calendario de la serie, asi que la coincidencia es por construccion.
    aportado = float(marcha.flujos.sum())
    if sin_valorar:
        # `flujos` vive en el calendario de la serie, y eso es DELIBERADO:
        # `aportado` y `valor` se restan para dar la ganancia, y si vinieran
        # de cortes temporales distintos daria una ganancia inventada -- en
        # el sub-proyecto F salio GANANCIA -9.700 sin que nadie hubiera
        # perdido un dolar.
        #
        # Cuando NO hay ningun dia valorado esa razon desaparece, porque
        # `ganancia` ya es «—» y no hay dos numeros que restar. Y decir
        # «Aportado neto 0,00» a quien acaba de meter su dinero no es una
        # medida que falte: es una **afirmacion falsa sobre un hecho
        # registrado**, que es peor que un «—». El dinero entro; lo que aun
        # no se puede es valorarlo.
        aportado = sum(
            a.importe if a.tipo == "aportacion" else -a.importe
            for a in vivos
            if a.tipo in mod.FLUJOS_EXTERNOS
        )
    valor_hoy = float(marcha.valor.iloc[-1]) if len(marcha.valor) else 0.0
    dias = (marcha.valor.index[-1] - marcha.valor.index[0]).days if len(marcha.valor) > 1 else 0

    twr_periodo = rendimiento.twr(marcha.valor, marcha.flujos)
    twr_anual = rendimiento.anualizar(twr_periodo, dias=dias)

    # Otra vez desde `marcha.flujos`, y por lo mismo que `aportado`: el valor final
    # de la serie se fecha en el ultimo cierre, asi que meter aqui un flujo
    # POSTERIOR a esa fecha construye una ecuacion que mezcla dos momentos. El
    # signo se invierte porque en `flujos` una aportacion es positiva y para la TIR
    # el dinero que entra es una salida del bolsillo.
    flujos_tir = [
        (dia.date(), -float(importe)) for dia, importe in marcha.flujos.items() if importe
    ]
    # Antes de añadirle el valor final, que no es un flujo externo sino el cierre
    # de la ecuacion. Contarlo aqui haria que un libro con una sola aportacion
    # pareciera tener dos momentos.
    dias_con_flujo = len(flujos_tir)

    # El salto del primer dia: valor de la serie menos el dinero que habia
    # entrado hasta ese dia. Si las compras se registraron al cierre, es cero.
    salto_inicial = None
    flujo_posterior = 0.0
    if len(marcha.valor) and not sin_valorar:
        primer_dia = marcha.valor.index[0]
        entrado = float(marcha.flujos.loc[:primer_dia].sum())
        salto_inicial = float(marcha.valor.iloc[0]) - entrado
        flujo_posterior = float(
            marcha.flujos.loc[marcha.flujos.index > primer_dia].abs().sum()
        )
    if flujos_tir and len(marcha.valor) and not sin_valorar:
        flujos_tir.append((marcha.valor.index[-1].date(), valor_hoy))
    tasa_interna = rendimiento.tir(flujos_tir)

    # Nada que valorar: las cifras que dependen del precio no existen todavia. Se
    # ponen a None y salen «—»; inventarlas con el precio al que se compro daria un
    # numero plausible, sin marca y sin unidades raras, que nadie distinguiria de
    # uno medido de verdad.
    valor_visible = None if sin_valorar else valor_hoy
    ganancia_visible = None if sin_valorar else valor_hoy - aportado
    twr_visible = None if sin_valorar else twr_anual
    tir_visible = None if sin_valorar else tasa_interna

    return Cabecera(
        valor=valor_visible,
        aportado=aportado,
        ganancia=ganancia_visible,
        # Sin anualizar, y apagado por `sin_valorar` como los demas. La
        # pantalla solo lo enseña dentro de la ayuda de TWR anual, que ya esta
        # dentro de ese mismo `if`, y la exportacion lo apagaba en su sitio.
        # Apagarlo aqui deja una sola decision en vez de dos que se pueden
        # desviar, y el valor que sale por los dos caminos es el mismo.
        twr_periodo=None if sin_valorar else twr_periodo,
        twr_anual=twr_visible,
        tir=tir_visible,
        dividendos=float(marcha.dividendos.sum().sum()),
        sin_valorar=sin_valorar,
        dias=dias,
        flujos=dias_con_flujo,
        salto_inicial=salto_inicial,
        flujo_posterior=flujo_posterior,
    )


# Un salto inicial por debajo de esta fraccion del dinero aportado es redondeo
# (comisiones, un cierre que se movio un tick) y no una causa que nombrar.
_SALTO_MATERIAL = 0.01

# Y unos flujos posteriores por debajo de esta fraccion no pueden mover una
# TIR ponderada por dinero lo bastante como para explicar una brecha.
_FLUJO_MATERIAL = 0.05

# Por debajo de esto la separacion entre las dos medidas es ruido de redondeo y
# de calendario, y nombrarla haria mirar donde no hay nada.
BRECHA_MINIMA = 0.02


def aviso_de_brecha(cab: Cabecera) -> "str | None":
    """Lo que se puede decir de la separacion entre TWR y TIR. `None` si nada.

    Las dos miden lo mismo de dos maneras, y cuando se separan la explicacion de
    manual es el calendario: la TIR pondera por dinero, asi que meter mas capital
    justo antes de una subida la levanta por encima de la TWR. Esa explicacion
    **exige al menos dos momentos** en los que entrara o saliera dinero. Con uno
    solo no hay ningun «cuando» que pueda favorecer a nada.

    Hasta el sub-proyecto K la pantalla afirmaba la causa del calendario siempre,
    dijeran lo que dijeran los flujos. En el libro de pruebas --una unica
    aportacion-- las dos se separaban 329 puntos y el aviso salia igual. La causa
    real era otra: el precio de compra registrado no coincidia con el cierre de
    mercado de ese dia, asi que la serie de valor arranca en 49.911 mientras la
    TIR parte de los 40.000 que entraron. Es una diferencia de **coste contra
    mercado**, no de calendario.

    Asi que la causa se atribuye solo cuando hay con que atribuirla. Con un flujo
    se dice **que** se separan y no **por que**, que es lo unico que el programa
    sabe. Afirmar un porque sin comprobarlo es la misma falta que «Aportado neto
    0,00»: una frase plausible sobre algo que aqui dentro nadie ha medido.
    """
    if cab.twr_anual is None or cab.tir is None:
        return None
    brecha = cab.tir - cab.twr_anual
    if abs(brecha) <= BRECHA_MINIMA:
        return None

    encabezado = f"**TWR y TIR se separan {abs(brecha):.1%}.**"

    # La causa MEDIDA manda sobre la supuesta. Si la serie de valor arranca lejos
    # del dinero que habia entrado, las compras se registraron a un precio que no
    # era el cierre de ese dia, y ahi esta la brecha entera: el TWR no cuenta ese
    # salto --arranca en `valor.iloc[0]`-- y la TIR si, porque parte de lo que
    # entro. No es una hipotesis, es una resta.
    if cab.salto_inicial is not None and cab.aportado > 0:
        if abs(cab.salto_inicial) > _SALTO_MATERIAL * abs(cab.aportado):
            return (
                f"{encabezado} **No es el efecto de *cuándo* aportaste.** El "
                f"primer día la cartera ya valía {cab.salto_inicial:+,.2f} "
                "respecto del dinero que había entrado, así que los precios con "
                "los que registraste las compras no eran el cierre de mercado de "
                "ese día. Esa diferencia es de **coste contra mercado** y se "
                "quedó dentro de la ganancia desde el primer momento: el TWR no "
                "la cuenta y la TIR sí, y de ahí salen casi todos estos puntos. "
                "Revisa los precios de las primeras operaciones."
            )

    # Y el calendario sólo explica algo si hubo dinero suficiente para moverlo.
    # `flujos >= 2` contaba una aportacion de un centimo como un «momento», de
    # modo que bastaba eso para pasar de dudar honestamente a afirmar una causa.
    calendario_posible = (
        cab.flujos >= 2
        and cab.aportado > 0
        and cab.flujo_posterior > _FLUJO_MATERIAL * abs(cab.aportado)
    )
    if calendario_posible:
        return (
            f"{encabezado} Esa diferencia es el efecto de *cuándo* aportaste, "
            "no de qué compraste: "
            + ("tus aportaciones cayeron en buenos momentos."
               if brecha > 0 else
               "tus aportaciones cayeron en momentos peores que la media.")
        )
    return (
        f"{encabezado} No es el efecto de *cuándo* aportaste: para eso harían "
        "falta al menos dos entradas de dinero en fechas distintas, y este libro "
        "tiene una. **Por qué se separan no se puede decir desde aquí.** Una "
        "causa posible —no comprobada— es que el precio al que registraste las "
        "compras no fuera el cierre de mercado de ese día: entonces la serie de "
        "valor arranca en una cifra y la TIR parte de otra, y las dos se separan "
        "sin que el calendario tenga nada que ver."
    )


@dataclass(frozen=True)
class Linea:
    """Un activo dentro de la composicion: donde esta su peso y donde deberia."""

    ticker: str
    peso: float  # sobre el total CON precio
    objetivo: "float | None"  # None cuando el libro no tiene objetivo
    valor: float


@dataclass(frozen=True)
class Composicion:
    """Como esta repartida la cartera, y que se quedo fuera del reparto."""

    lineas: "tuple[Linea, ...]"
    sin_precio: "tuple[str, ...]"
    hay_objetivo: bool
    # El denominador que se uso: la suma de los activos CON precio. Se
    # devuelve en vez de dejar que quien pinte lo recalcule, que seria un
    # segundo sitio donde puede desviarse.
    invertido: float
    # El efectivo del libro. **Es un hecho registrado, no una valoracion**, y
    # por eso nunca se resta de `valor`: aquel vive en el calendario de la
    # serie y este en el de los asientos. Restar dos cortes distintos es el
    # defecto que en F dio GANANCIA -9.700. Aqui solo se enseña al lado.
    efectivo: float


def composicion(asientos, precios_hoy, objetivo, historia=None) -> Composicion:
    """El reparto de la cartera, sobre el total de lo que TIENE precio.

    Un activo sin precio no entra en el denominador. Meterlo valorado a cero
    encogeria el peso de todos los demas, y meterlo valorado a lo que costo
    mezclaria coste con mercado dentro de la misma suma: en los dos casos las
    barras dirian una proporcion que nadie ha medido. Lo que se hace es
    **dejarlo fuera y nombrarlo** en `sin_precio`, que es la misma regla que la
    tabla por activo ya aplica cuando escribe «—» en vez de 0,00.

    `objetivo` puede ser `None`. En ese caso `hay_objetivo` es `False` y todas
    las lineas traen `objetivo=None`. **No se rellena con el peso real**: una
    marca encima de la barra, justo donde esta la barra, diria que ya estas
    donde querias estar, que es una afirmacion sobre un plan que no existe.

    ## Por que hace falta la `Historia`

    Porque sin ella ni `rendimiento.por_activo` ni `posiciones.estado` pueden
    enterarse de un split ni de un dividendo automatico, y las dos alimentan
    esto: con un 2:1 de por medio las acciones de la linea salian a la mitad,
    asi que **el peso de ese activo y el de todos los demas** --que se reparten
    el mismo denominador-- quedaban falseados a la vez, y el efectivo salia
    corto por los dividendos que solo cobraba `serie()`. La cabecera decia
    320,00 y esta linea 300,00, en la misma pantalla.

    Se queda opcional --`None` es «no se conocen acciones corporativas», no «no
    hubo ninguna»-- para que se pueda llamar desde donde no hay descarga. Las
    dos pantallas que si la tienen la pasan siempre.
    """
    pesos_obj = mod.pesos_objetivo(objetivo)
    lineas_activo = rendimiento.por_activo(asientos, precios_hoy, historia)

    sin_precio = tuple(
        t for t, linea in lineas_activo.items() if linea.valor is None
    )
    con_precio = [
        linea for linea in lineas_activo.values() if linea.valor is not None
    ]
    total = sum(linea.valor for linea in con_precio)

    lineas = tuple(
        Linea(
            ticker=linea.ticker,
            peso=(linea.valor / total) if total else 0.0,
            # `.get`, no `[...]`: un activo que esta en el libro pero no en el
            # objetivo no tiene un objetivo de cero --nadie dijo que sobrara--
            # sino ninguno, y `None` es lo que hace que no se le pinte marca.
            objetivo=pesos_obj.get(linea.ticker),
            valor=linea.valor,
        )
        for linea in con_precio
    )
    return Composicion(
        lineas=lineas,
        sin_precio=sin_precio,
        hay_objetivo=bool(pesos_obj),
        invertido=total,
        efectivo=posiciones.estado(asientos, historia=historia).efectivo,
    )


def filas_por_activo(
    asientos, precios_hoy, invertido, objetivo, historia=None
) -> "list[dict]":
    """La tabla por activo, tal cual la pinta la pantalla y la exporta Excel.

    Devuelve una lista de diccionarios ya formateados, y no dataclases, porque
    `exporter.to_excel` los consume asi y esta tarea mueve la tabla de sitio sin
    tocar la exportacion.

    `invertido` es la suma de los activos CON precio --`Composicion.invertido`--
    y **no** el valor de cabecera. Hasta K se dividia por aquel, que incluye el
    efectivo sin invertir, y la columna quedaba sumando 71,9% al lado de un «Peso
    objetivo» que suma 100%: AAPL salia al 7,32% contra un objetivo del 10,31%
    cuando en realidad estaba al 10,17%, clavado. Se leia como «voy tres puntos
    por debajo» y lo cierto era otra cosa --que el 28% del dinero no estaba
    invertido--, que ademas no se decia en ninguna parte.

    El objetivo reparte sobre los activos y `rebalanceo/deriva.py` mide sobre los
    activos. Esta tabla ahora tambien, que es lo que hace que las dos pantallas
    digan lo mismo del mismo libro.

    `historia` es lo que deja que las siete cifras de cada fila cuenten los
    splits y los dividendos. Va al final y con valor por defecto porque el
    parametro que manda aqui es `invertido`, y el orden de los tres primeros ya
    estaba escrito en las dos llamadas que existen.
    """
    pesos_obj = mod.pesos_objetivo(objetivo)
    filas = []
    lineas = rendimiento.por_activo(asientos, precios_hoy, historia)
    for ticker, linea in lineas.items():
        peso_real = (linea.valor / invertido) if (linea.valor and invertido) else None
        filas.append({
            "Ticker": ticker,
            "Acciones": f"{linea.acciones:,.4f}".rstrip("0").rstrip("."),
            "Coste medio": f"{linea.coste_medio:,.2f}",
            "Precio": cartera.formato_cifra(linea.precio),
            "Valor": cartera.formato_cifra(linea.valor),
            "Peso real": cartera.formato_porcentaje(peso_real),
            "Peso objetivo": cartera.formato_porcentaje(pesos_obj.get(ticker)),
            "Latente": cartera.formato_cifra(linea.latente),
            "Realizada": f"{linea.realizada:,.2f}",
            "Dividendos": f"{linea.dividendos:,.2f}",
            "Contribución": cartera.formato_cifra(linea.contribucion),
        })
    return filas


def filas_de_historial(asientos) -> "list[dict]":
    """El historial, del mas reciente al mas viejo, con los anulados marcados.

    Recorre TODOS los asientos y no solo los vigentes: un asiento anulado sigue
    siendo algo que paso, y borrarlo de la lista dejaria la anulacion sin nada
    que anular a la vista. Por eso el estado se escribe en una columna en vez de
    filtrarse.
    """
    anulados = {a.anula for a in asientos if a.tipo == "anulacion" and a.anula}
    historial = []
    for a in reversed(posiciones.ordenados(asientos)):
        historial.append({
            "Fecha": a.fecha,
            # El factor va pegado al tipo. Un split no lleva acciones, ni
            # precio, ni importe --no se paga ni se cobra nada--, asi que sin
            # esto su fila es la palabra «split» y cuatro rayas: el unico dato
            # que tiene el asiento no se veria. Y no en una columna propia,
            # que seria un «—» en todas las demas filas de todos los libros.
            "Tipo": a.tipo if a.factor is None else f"{a.tipo} ×{a.factor:g}",
            "Ticker": a.ticker or "—",
            "Acciones": cartera.formato_cifra(a.acciones, 4),
            "Precio": cartera.formato_cifra(a.precio) + (" (est.)" if a.precio_estimado else ""),
            "Importe": f"{a.importe:,.2f}",
            "Comisión": f"{a.comision:,.2f}",
            "Estado": "Anulado" if a.id in anulados else "",
            "Nota": a.nota,
        })
    return historial
