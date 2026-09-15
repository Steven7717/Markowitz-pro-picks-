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

## La valla

El texto de los documentos --el anexo EX-99 de un 8-K, treinta mil caracteres
por hecho y seis hechos por pulsacion-- lo escribe la empresa, y aqui entra
crudo. Se manda dentro de `ranking.verificacion.vallar` y **no delimitado a
mano**: la valla anterior era `<<<` y `>>>` a secas, asi que a un anexo le
bastaba con llevar la marca de cierre en una linea suya para terminar el bloque
antes de tiempo y que lo que viniera detras se leyera como instrucciones del
programa.

La unica defensa que quedaba no ve nada: `verificar_cita` compara la cita
contra el mismo texto que escribio quien ataca, asi que una frase plantada
verifica siempre y la pantalla la rotula «Cita literal del documento» al lado
de la casilla de aprobar.

Por este camino ademas **el dano persiste**: lo que salga de ahi lo escribe
`archivo.anotar_hechos` en `libros/interpretaciones/<libro>.json`, que es
append-only, y se repinta en cada apertura de la pestana sin pulsar nada. Por
eso `leidos` --que es justo lo que vuelve de ese fichero-- tambien se limpia:
sin eso, un `que_dice` envenenado una vez volveria al prompt de todas las
sesiones siguientes por su cuenta.

Lo que **no** cambia es que la letra viaja fuera de la valla. El mapa de letras
es lo que impide fabricar un hecho o una operacion que no existen, y una letra
escrita dentro del documento seria una letra que el documento elige.
"""

from string import ascii_uppercase

from ranking.verificacion import neutralizar_marcas, vallar

_SIN_OBJETIVO = "sin objetivo en el plan"

# Lo que cabe de un dato ajeno en una linea de cabecera. Las descripciones
# reales son etiquetas --«Resultados», «Acuerdo material»-- y hasta un
# expediente que comunique media docena de items se queda muy por debajo. El
# tope no defiende por si solo, porque media frase de prosa cabe de sobra: lo
# que hace es acotar cuanto texto ajeno puede viajar en una linea que el modelo
# lee como escrita por el programa.
_MAX_CABECERA = 200


def _en_una_linea(valor: object) -> str:
    """Un dato ajeno, apto para una linea que va **fuera** de la valla.

    Las cabeceras de `hechos` y de `operaciones`, y las filas de `cartera`, no
    van dentro de ninguna valla y no pueden ir: la letra y el ticker son lo que
    despues valida las respuestas, y dentro del documento serian una letra y un
    ticker que elige el documento. Pero el resto de esa linea tampoco lo
    escribe este programa: la `etiqueta` sale de `descripciones`, que
    `noticias/hechos.py` rellena con `f"Tipo {t}"` cuando el codigo de item no
    esta en la lista, y `t` es la columna `items` del indice de la SEC.

    Con un salto de linea dentro, esa descripcion se colocaba en una linea
    aparte y el modelo la leia como una instruccion del programa, por encima de
    la valla y sin nada que dijera lo contrario. Dos cosas la desarman:

    1. **Se colapsa todo el blanco.** Una cabecera es una linea, y aqui deja de
       poder ser dos. Es la mitad que de verdad cierra el agujero.
    2. **Se neutralizan las marcas de valla**, como en `leidos`, por si la
       descripcion trae una y el modelo la lee como el final de un bloque.

    Lo que **no** arregla: media frase de prosa en una sola linea sigue
    colandose. Eso no se arregla aqui sino en el origen, validando el codigo de
    item antes de escribir `f"Tipo {t}"` -- `noticias/hechos.py`, que es donde
    vive el fallback. Lo de aqui es la mitad que si se puede hacer desde este
    lado, y es la misma que `noticias/texto.py:linea_de_hecho` ya hacia para
    **pintar** esas mismas descripciones: solo el prompt las dejaba crudas.
    """
    plano = neutralizar_marcas(" ".join(str(valor).split()))
    if len(plano) <= _MAX_CABECERA:
        return plano
    return plano[:_MAX_CABECERA] + "…"


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
        filas.append(f"- {_en_una_linea(ticker)}: pesa {_pct(peso)}, {destino}")
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
        # Ni el ticker ni la accion los escribe este programa, y esta linea va
        # fuera de toda valla: misma puerta que la cabecera de `hechos`.
        filas.append(
            f"[{letra}] {_en_una_linea(accion)} {_en_una_linea(ticker)}, "
            f"{_pct(parte)} de la cartera — {juicio}"
        )
    return "\n".join(filas), mapa


def leidos(entradas: "tuple[tuple[str, object, tuple, tuple, str], ...]") -> str:
    """Lo ya interpretado en sesiones anteriores, **sin etiqueta**.

    Va al prompt para que el parrafo de conjunto vea el cuadro completo, y no
    para que se escriba un juicio nuevo sobre ello. Por eso no lleva letra: sin
    letra no hay a que apuntar, y la guarda que ya existe --una etiqueta que no
    esta en el mapa tira el juicio-- protege esto sola.

    Importa mas de lo que parece. Lo que se manda de un hecho ya leido es el
    `que_dice` que escribio el propio modelo, no el documento. Si tuviera letra,
    un juicio nuevo podria **citar ese resumen** y `verificar_cita` lo daria por
    bueno, porque la fuente contra la que compara seria ese mismo texto. La
    pantalla lo rotularia «Cita literal del documento» y no lo seria.

    Las marcas de valla se neutralizan aunque esto no vaya dentro de una: es el
    texto que sale del fichero del libro, y ese fichero es append-only. Un
    `que_dice` con la marca dentro --escrito bajo el defecto de ayer, o por un
    modelo al que se le convencio de copiarla-- volveria al prompt de cada
    sesion siguiente por su cuenta, sin que nadie pulse nada. **Aqui es donde se
    cierra ese bucle.**

    Se devuelve la cadena vacia cuando no hay nada, y no un bloque vacio:
    `noticias._prompt` decide con eso si escribe la seccion, y «no hay» y «hay,
    pero vacio» no son lo mismo.
    """
    if not entradas:
        return ""
    # La cabecera de cada fila pasa por `_en_una_linea` igual que la de
    # `hechos`, aunque esto si vaya dentro de una valla: lo que se gana no es
    # cerrar el bloque --eso ya lo impide el sufijo-- sino que una fila siga
    # siendo una fila. Un ticker con un salto dentro partia la lista en dos y
    # dejaba media entrada haciendose pasar por otra.
    filas = [
        f"- {_en_una_linea(ticker)} "
        f"({_en_una_linea(', '.join(descripciones) or ', '.join(tipos))}, "
        f"{_en_una_linea(cuando)}): {neutralizar_marcas(texto)}"
        for ticker, cuando, tipos, descripciones, texto in entradas
    ]
    # Vallado entero, y no fila a fila: no hay letras que dejar fuera --esto va
    # sin etiqueta a proposito-- y una valla por fila solo multiplicaria marcas.
    # Lo que importa es que el bloque quede marcado como texto que se lee, que
    # es lo que la primera regla de SISTEMA le dice al modelo que significa.
    return vallar("\n".join(filas))


def hechos(
    entradas: "tuple[tuple[str, object, tuple, tuple, str], ...]",
) -> "tuple[str, dict[str, str]]":
    """Los hechos a interpretar, etiquetados. Devuelve el texto y el mapa.

    Cada tupla es `(ticker, cuando, tipos, descripciones, texto)`. El `texto` es
    o el documento recien bajado y recortado, o el `que_dice` de una lectura
    guardada: los dos entran por la misma puerta porque para el modelo son lo
    mismo, algo que leer sobre ese hecho.

    **Cada hecho lleva su propia valla**, y no una comun a los seis: el sufijo
    de la marca sale del texto que encierra, asi que la marca de cierre de un
    anexo no puede cerrar el bloque de otro. Con una comun, el primer documento
    de la pulsacion podria terminar el ultimo.

    La cabecera --letra, ticker, etiqueta y fecha-- va **fuera**. La letra es lo
    que despues valida las respuestas, y dentro de la valla seria una letra que
    elige el documento.

    Pero de esos cuatro campos la letra es el unico que escribe este programa, y
    por eso los otros tres pasan por `_en_una_linea`: la `etiqueta` sale del
    indice de la SEC --`f"Tipo {t}"` cuando el codigo de item no esta en la
    lista-- y con un salto de linea dentro se colocaba en una linea propia, por
    encima de la valla, donde el modelo la lee como texto del programa.
    """
    letras = etiquetas(len(entradas))
    mapa = {}
    bloques = []
    for letra, (ticker, cuando, tipos, descripciones, texto) in zip(letras, entradas):
        mapa[letra] = ticker
        etiqueta = ", ".join(descripciones) or ", ".join(tipos)
        bloques.append(
            f"[{letra}] {_en_una_linea(ticker)} — {_en_una_linea(etiqueta)} — "
            f"presentado el {_en_una_linea(cuando)}\n"
            f"{vallar(texto)}"
        )
    return "\n\n".join(bloques), mapa
