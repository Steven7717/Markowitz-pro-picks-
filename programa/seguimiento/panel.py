"""Lo que la pantalla de seguimiento enseña, calculado fuera de la pantalla.

Este modulo existe por una razon concreta: hasta el sub-proyecto K, estas
cuentas vivian dentro de `vistas/seguimiento.py`, que es un guion de Streamlit
y **no se puede importar desde un test**. Las correcciones que tienen dentro
--el corte temporal comun, el «—» que no es un cero-- estaban protegidas solo
por un comentario. Un rediseno de la pantalla las habria borrado sin que nada
fallase, porque los numeros que saldrian serian plausibles.
"""

from dataclasses import dataclass

from seguimiento import libro as mod, rendimiento


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
    )
