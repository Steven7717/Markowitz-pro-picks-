# interprete/contexto.py
"""Lo que sale de esta maquina, y en que forma.

**Aqui no entra un euro, y no por un filtro: por la firma.** Ninguna funcion de
este modulo admite un importe. Reciben pesos, porcentajes, tickers, fechas,
codigos de item y texto de documento. Un filtro que borra euros se puede saltar
anadiendo un campo; una firma que no los admite, no. Hay un test que recorre las
firmas y lo afirma.

Es la misma forma de garantia que `Evento.cuando = None` en H: una ausencia
protegida por un test, y no una comprobacion que alguien pueda rodear.

## Las etiquetas

Cada hecho y cada operacion viajan con una letra --`A`, `B`, `C`...-- y el
esquema exige que el modelo se refiera a ellas por esa letra. Dos cosas a la vez:

1. La regla de «cero digitos» de `ranking/llm.py` sigue en pie. Si el modelo
   tuviera que decir «el hecho dos», habria que abrirle la puerta a los numeros
   justo donde mas caro sale.
2. «Solo puede comentar operaciones que G propuso» se vuelve **pertenencia a un
   conjunto de letras**. Si G propuso tres, la `D` no existe y esa observacion
   se cae sola.

El codigo imprime despues el ticker, la fecha, los codigos de item y el enlace.
El modelo no escribe ninguno de los cuatro.
"""

from string import ascii_uppercase

_SIN_OBJETIVO = "sin objetivo en el plan"


def etiquetas(cuantos: int) -> "tuple[str, ...]":
    """`A`, `B`, `C`...

    Revienta pasado el alfabeto en vez de envolver, que es lo correcto: con 27
    elementos dos compartirian letra, y el mapa que valida las respuestas
    resolveria el segundo como el primero sin que nada lo dijera.
    """
    if cuantos > len(ascii_uppercase):
        raise ValueError(
            f"No hay etiquetas para {cuantos} elementos: el alfabeto da "
            f"{len(ascii_uppercase)}."
        )
    return tuple(ascii_uppercase[:cuantos])


def _pct(parte: float) -> str:
    """Un tanto por uno como porcentaje, con un decimal.

    Un decimal y no cero: redondeando a entero, un 4,3% y un 4,4% salen los dos
    como «4%» y el modelo concluye que pesan igual; con doce activos eso pasa a
    menudo. Y tampoco muchos mas: los decimales que el modelo no necesita para
    decir «pesa mucho» son superficie donde copiar una cifra.

    Lo que no llega al decimal se dice con palabras en vez de con un cero. Una
    posicion del 0,04% escrita «0,0%» se lee como que no la tienes, y no es lo
    mismo tener poco que no tener nada -- la misma regla que `panel._cifra`,
    que escribe «—» donde no hay medida en vez de escribir cero.
    """
    porcentaje = parte * 100
    if 0 < porcentaje < 0.05:
        return "menos de 0,1%"
    return f"{porcentaje:.1f}%".replace(".", ",")


def cartera(pesos: "tuple[tuple[str, float, float | None], ...]") -> str:
    """Los pesos de la cartera, en tanto por ciento y sin un solo euro.

    Recibe tripletas `(ticker, peso, objetivo)` y **no `panel.Linea`**, aunque
    `Linea` tenga justo esos tres campos: tambien tiene `valor`, que son euros.
    Pasar el objeto entero metaria el importe en este modulo aunque nadie lo
    leyera, y la garantia de la cabecera dejaria de ser cierta por construccion
    para pasar a depender de que nadie escriba `.valor`.

    `objetivo` puede ser `None` --un libro sin plan-- y entonces se dice que no
    lo hay. **No se rellena con el peso real**, que es la misma regla que
    `panel.composicion`: diria que ya estas donde querias estar.
    """
    filas = []
    for ticker, peso, objetivo in pesos:
        destino = _SIN_OBJETIVO if objetivo is None else f"objetivo {_pct(objetivo)}"
        filas.append(f"- {ticker}: pesa {_pct(peso)}, {destino}")
    return "\n".join(filas)


def operaciones(
    propuestas: "tuple[tuple[str, str, float, bool], ...]",
) -> "tuple[str, dict[str, str]]":
    """Las operaciones que G propuso, etiquetadas. Devuelve el texto y el mapa.

    Cada tupla es `(ticker, accion, parte, viable)`, donde `parte` es el importe
    **en tanto por ciento de lo invertido**, nunca en euros, y `viable` es el
    veredicto que `rebalanceo/criterio.py:merece_la_pena` ya calculo con el
    coste real. El modelo no necesita el coste para decir cual compensa menos:
    se lo estamos diciendo.

    El mapa que vuelve es lo que despues valida las respuestas. Sin el, «solo
    puede comentar operaciones que G propuso» no seria comprobable.
    """
    letras = etiquetas(len(propuestas))
    mapa = {}
    filas = []
    for letra, (ticker, accion, parte, viable) in zip(letras, propuestas):
        mapa[letra] = ticker
        juicio = "compensa su coste" if viable else "no compensa lo que cuesta"
        filas.append(f"[{letra}] {accion} {ticker}, {_pct(parte)} de la cartera — {juicio}")
    return "\n".join(filas), mapa


def hechos(
    entradas: "tuple[tuple[str, object, tuple, tuple, str], ...]",
) -> "tuple[str, dict[str, str]]":
    """Los hechos a interpretar, etiquetados. Devuelve el texto y el mapa.

    Cada tupla es `(ticker, cuando, tipos, descripciones, texto)`. El `texto` es
    o el documento recien bajado y recortado, o el `que_dice` de una lectura
    guardada: los dos entran por la misma puerta porque para el modelo son lo
    mismo, algo que leer sobre ese hecho.
    """
    letras = etiquetas(len(entradas))
    mapa = {}
    bloques = []
    for letra, (ticker, cuando, tipos, descripciones, texto) in zip(letras, entradas):
        mapa[letra] = ticker
        etiqueta = ", ".join(descripciones) or ", ".join(tipos)
        bloques.append(
            f"[{letra}] {ticker} — {etiqueta} — presentado el {cuando}\n"
            f"<<<\n{texto}\n>>>"
        )
    return "\n\n".join(bloques), mapa
