"""La aritmética de enfrentar portafolios guardados. Sin Streamlit.

Esto vivía dentro de `vistas/comparar.py`, mezclado con los widgets, y ahí
nadie podía probarlo: importar una vista ejecuta el script entero. Sale aquí
por el mismo motivo por el que `seguimiento/panel.py` salió de su vista y
`vistas/panel_ia.py` no importa Streamlit — la decisión de qué columna es cada
cartera no es presentación, y se le rompió al programa precisamente donde no
había un test que mirara.
"""

from cartera import Entrada, Portafolio


def etiquetar(entradas: "list[Entrada]") -> "dict[str, Portafolio]":
    """Una etiqueta única por portafolio legible, en el orden en que llegan.

    La etiqueta era `nombre · fecha_legible`, y el texto de ayuda de la pantalla
    decía que la fecha estaba ahí «porque dos guardados pueden llamarse igual».
    Casi: `fecha_legible` se formatea a minutos y el nombre del fichero lleva
    segundos, así que dos carteras con el mismo nombre guardadas dentro del
    mismo minuto producían la misma clave. El diccionario se quedaba con una y
    la otra desaparecía del selector — y en la matriz de pesos, que se indexaba
    por el nombre a secas, bastaba con repetir el nombre para que las dos
    columnas colapsaran en una con las filas mezcladas de ambas y los pesos
    sumando 140 %.

    El desempate por nombre de fichero sólo aparece cuando hace falta: en el
    caso normal la etiqueta sigue siendo la legible. Una etiqueta que siempre
    arrastrara el nombre del fichero sería inequívoca y también ilegible.
    """
    legibles = [e for e in entradas if e.portafolio is not None]

    repetidas: dict[str, int] = {}
    for entrada in legibles:
        base = _base(entrada.portafolio)
        repetidas[base] = repetidas.get(base, 0) + 1

    etiquetas: dict[str, Portafolio] = {}
    for entrada in legibles:
        base = _base(entrada.portafolio)
        clave = base if repetidas[base] == 1 else f"{base} · {entrada.ruta.name}"
        etiquetas[clave] = entrada.portafolio
    return etiquetas


def _base(portafolio: "Portafolio") -> str:
    return f"{portafolio.nombre} · {portafolio.fecha_legible}"


def matriz_de_pesos(elegidos: "dict[str, Portafolio]") -> list[dict]:
    """Una fila por activo, una columna por portafolio, ordenada por ticker.

    Un activo que no está en una cartera sale con un guion, no a cero: son
    cosas distintas. Un cero significaría «se consideró y se le dio peso nulo»,
    y en la mayoría de los casos ni siquiera estaba en la lista de entrada.
    """
    matriz: dict[str, dict[str, float]] = {}
    for etiqueta, portafolio in elegidos.items():
        for ticker, peso in zip(portafolio.tickers, portafolio.pesos):
            matriz.setdefault(ticker, {})[etiqueta] = peso

    return [
        {
            "Ticker": ticker,
            **{
                etiqueta: (
                    f"{columnas[etiqueta]:.2%}" if etiqueta in columnas else "—"
                )
                for etiqueta in elegidos
            },
        }
        for ticker, columnas in sorted(matriz.items())
    ]


def frase_de_cobertura(elegidos: "dict[str, Portafolio]") -> str:
    """Cuántos activos comparten todos, de cuántos distintos en total.

    El número gramatical se ajusta al recuento: decía «1 activos aparecen en
    todos», que es la clase de descuido que hace dudar de las cifras que lo
    rodean.
    """
    conjuntos = [set(p.tickers) for p in elegidos.values()]
    comunes = set.intersection(*conjuntos) if conjuntos else set()
    todos = set.union(*conjuntos) if conjuntos else set()

    cabeza = (
        "1 activo aparece" if len(comunes) == 1
        else f"{len(comunes)} activos aparecen"
    )
    return (
        f"{cabeza} en todos los portafolios elegidos, de {len(todos)} distintos "
        "en total. Un guion significa que ese activo no estaba en esa cartera, "
        "no que se le asignara un peso de cero."
    )
