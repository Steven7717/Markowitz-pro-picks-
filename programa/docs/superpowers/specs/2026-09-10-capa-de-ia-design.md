# Sub-proyecto I — La capa de IA sobre F, G y H

Fecha: 2026-09-10 (archivo añadido el 2026-09-11, tras revisión del usuario)
Estado: diseño aprobado, sin implementar

## Qué entrega

Dos botones y un archivo. Uno lee los hechos que ya tienes en pantalla y dice
qué significan para **tu** cartera; otro mira la propuesta de rebalanceo y dice
lo que la aritmética no ve. Nada se llama solo, nada se llama al abrir una
pantalla. **Y nada de lo interpretado se tira**: se guarda fechado, se vuelve a
leer sin pagar, y lo que ya se leyó deja de mandarse.

Es lo último del encargo original: F sigue lo comprado, G dice cuándo corregir,
H trae las noticias, e **I las interpreta**.

## Lo que ya existe y esto no repite

| De dónde | Qué se reutiliza tal cual |
|---|---|
| `ranking/verificacion.py` | `verificar_cita`, `sin_digitos`, `MIN/MAX_CARACTERES_CITA` |
| `ranking/llm.py` | El patrón entero: salida estructurada, reintento, degradación a `None`, caché por hash de contenido |
| `noticias/resumen.py` | `resumir` y **`TOPE_HECHOS`**, importado y no recopiado |
| `noticias/texto.py` | El escapado antes de pintar |
| `seguimiento/panel.py` | `Composicion` y sus `Linea` |
| `rebalanceo/propuesta.py` | `Propuesta`, `Operacion` — con `viable` y `descartadas_por_coste` ya calculados |
| `credenciales.py` | La clave; el cliente de Anthropic la lee del entorno por su cuenta |

**Ningún criterio se toca.** Ni `noticias/criterio.py` ni `rebalanceo/criterio.py`
ni `ranking/criterio.py`. Los tres viven congelados y aparte precisamente para
que nadie los ajuste después de haber visto datos reales, y este diseño se
escribió después de mirar expedientes de seis empresas reales — que es
exactamente la situación contra la que existe el congelado.

## Lo que se sondeó antes de decidir nada

Cinco medidas contra las fuentes vivas. Dos tumbaron cosas que este documento
iba a decir mal.

### 1. Un `Hecho` no contiene ni una palabra de la empresa

```
Hecho(ticker, tipos=("2.02","9.01"), descripciones=("Resultados", …),
      url, cuando, enmienda, material)
```

Las `descripciones` son **etiquetas del propio programa**, congeladas en
`noticias/criterio.py`. H nunca abre el documento — a propósito, porque abrir
quince al pintar la pantalla la convertía en una espera.

**Consecuencia:** darle eso a un modelo y pedirle interpretación tiene dos
salidas, repetir la etiqueta que ya está en pantalla o inventarse el contenido
del expediente. Un 4.02 inventado se lee exactamente igual que uno real. Por
eso I baja el documento.

### 2. El cuerpo del 8-K no es donde está la noticia

`filing.text()` del 2.02 de MSFT (2026-07-29): **3.579 caracteres**, de los que
unos 3.100 son carátula de la SEC y advertencias legales. Todo su contenido es
una frase:

> "On July 29, 2026, Microsoft Corporation issued a press release announcing its
> financial results… A copy of the press release is furnished as Exhibit 99.1"

El **`EX-99.1` tiene 52.823 caracteres** y ahí está todo: ingresos, margen, EPS,
el detalle. Se baja en 0,46 s.

Sobre 17 expedientes materiales de MSFT, MU, AAPL y NVDA: **13 traen `EX-99`**.
Los 4 que no son `5.02` (directiva), y ahí el cuerpo sí lleva la sustancia.

**La regla, medida y no supuesta: el anexo si lo hay, el cuerpo si no.**

### 3. El cuerpo se puede recortar por sus marcas, y merece la pena

Los nueve cuerpos sin anexo tienen los dos marcadores. Cortando entre el primer
`Item N.NN` y `SIGNATURE`:

| | Entero | Recortado |
|---|---|---|
| MSFT 5.02 | 3.291 | **761** |
| AAPL 5.02 | 6.465 | **2.693** |
| KO 5.02,9.01 | 7.162 | **2.798** |
| NVDA 5.02 | 5.660 | **2.976** |
| MSFT 5.02,5.07 | 10.167 | **7.539** |

Entre 25% y 80% menos, y lo que queda empieza justo en el `Item`.

**Trampa medida:** MSFT usa `Item 5.02` con **espacio fino** (U+2009), no
un espacio normal. Un literal `"Item "` se lo salta y devuelve el documento
entero — un fallo que no revienta, sólo encarece y ensucia. La expresión usa
`\s+`, y hay un test con el espacio fino dentro.

Si falta cualquiera de las dos marcas, **se manda el cuerpo entero**. Un recorte
que falla no puede llevarse la noticia por delante.

### 4. No hay caracteres rotos en el texto de EDGAR

`U+FFFD` no aparece ni en el cuerpo ni en el anexo. Lo que se ve como `?` o `�`
al imprimir en Windows es la consola, no el dato. El anexo trae `U+2026` (191
veces), `U+2022`, `U+2019`, `U+201C/D`, `U+2014` — todo tipografía legítima.

Esto es lo que hace viable el guardarraíl de la cita literal, y era una
suposición que iba a escribirse sin comprobar.

### 5. `VENTANA = 550 días`, no treinta

Materiales por activo en la ventana real de H:

| MSFT | MU | AAPL | NVDA | JNJ | KO |
|---|---|---|---|---|---|
| 10 | 11 | 12 | 13 | 10 | 11 |

Media **11,2 por activo** → con doce activos, **~134 hechos materiales**. A
28.291 caracteres de media son ~3,7 millones de caracteres, cerca de un millón
de tokens por pulsación. Inviable, y la razón por la que el presupuesto de abajo
no es un detalle de implementación sino una decisión de diseño.

## Decisiones tomadas

- **El modelo explica y señala qué revisar; no propone operaciones propias.**
  Puede decir «esto toca la razón por la que compraste X» y «de las tres que
  propone G, ésta corrige poco para lo que cuesta». No puede nombrar una cuarta.
  G ya propone operaciones, pero las saca por aritmética de **tus** pesos
  objetivo: es tu plan ejecutado, no una opinión sobre qué deberías tener.
- **El modelo no ve dinero.** Ni importes, ni ganancias, ni coste de
  adquisición. Ve pesos en porcentaje, tickers, fechas, códigos de item y texto
  de documento. De la máquina sale lo mismo que ya sale a Yahoo cada vez que se
  abre el panel: qué activos sigues.
- **Nunca se llama sin botón.** Misma regla que K: lo cacheado se enseña, el
  botón trae. Un panel que llama a un modelo al abrirse es un panel que cuesta
  dinero por mirarlo.
- **Se lee exactamente lo que hay en pantalla.** Los `TOPE_HECHOS` más
  recientes, importando la constante de `noticias/resumen.py`. No es sólo el
  presupuesto: es que la IA lee **lo mismo que tú**, así que no puede comentar
  algo que no tienes delante ni callar sobre algo que sí.
- **Los fallos no se cachean.** Regla de B: un corte de red congelado sería un
  veredicto permanente para un problema que quizá no se repite.
- **`verificacion.py` no se amplía.** Su tabla tipográfica no cubre `…`
  (U+2026) ni `•` (U+2022), que el anexo sí trae. Tocarla cambiaría también el
  comportamiento de B, que está en producción. El reintento absorbe el caso y
  la cita que falle sale marcada. Ver «Fallos previstos».
- **Sin clave, `None`.** La pantalla dice que falta y dónde ponerla. El panel
  no deja de funcionar por esto en ningún camino.
- **Lo interpretado se guarda, y se guarda añadiendo.** Un juicio es una opinión
  fechada, de un modelo y una versión concretos; volver a interpretar añade una
  sesión y no pisa la anterior. Misma forma que `Libro.objetivos`. Ver «El
  archivo».
- **Los comentarios de rebalanceo se guardan con su foto.** Sin el estado al que
  apuntaban son texto huérfano, y releerlos junto a la propuesta de hoy sería
  mezclar dos cortes temporales — el defecto que en F dio una `GANANCIA −9.700`.

## Arquitectura

```
interprete/
  contexto.py     traduce F, G y H a texto — la frontera de privacidad
  documentos.py   baja y recorta el texto de un 8-K. Lo único que toca EDGAR
  cliente.py      la llamada y su degradación. Lo único que toca Anthropic
  noticias.py     prompt congelado + esquema + verificación de citas
  ajuste.py       prompt congelado + esquema + verificación de operaciones
  cache.py        memoización por hash de contenido
  archivo.py      lo interpretado, guardado para siempre
```

Sin `import streamlit` en ninguno. Los widgets van en `vistas/`, como en H y K.

### La frontera de privacidad es una ausencia, no un filtro

`contexto.py` **no tiene ningún parámetro por el que pueda entrar un euro.**
Sus funciones reciben pesos y porcentajes. Los `importe` y `coste` de
`Operacion` se convierten a *porcentaje de lo invertido* antes de cruzar, y no
hacen falta enteros: `viable` y `descartadas_por_coste` los calculó ya
`rebalanceo/criterio.py:merece_la_pena`.

Un filtro que borra euros se puede saltar añadiendo un campo. Una firma que no
los admite, no. Es la misma forma de garantía que `Evento.cuando = None` en H:
la ausencia protegida por un test.

### Las etiquetas, y por qué no son números

Cada hecho y cada operación que se mandan llevan una etiqueta **`A`, `B`, `C`…**
y el esquema exige que el modelo se refiera a ellas por esa letra.

Dos cosas a la vez:

1. La regla de «cero dígitos» de B sigue en pie. Si el modelo tuviera que decir
   «el hecho 2» o «la operación 3», habría que abrirle la puerta a los números
   justo donde más caro sale.
2. **«Sólo puede comentar operaciones que G propuso» se vuelve pertenencia a un
   conjunto de letras**, no comparación de cadenas. No hay forma de nombrar una
   cuarta operación: la letra `D` no existe en el mapa y esa observación se cae.

El código imprime el ticker, la fecha, los códigos de item y el enlace. El
modelo nunca escribe ninguno de los cuatro.

### Las estructuras

```python
# interprete/noticias.py
SIN_CLAVE = "sin_clave"; SIN_HECHOS = "sin_hechos"
FALLO     = "fallo";     HECHA      = "hecha"

@dataclass(frozen=True)
class Juicio:
    ticker: str
    que_dice: str          # qué dice el documento
    por_que_te_toca: str   # qué implica para esta cartera
    cita: str
    verificada: bool

@dataclass(frozen=True)
class Lectura:
    estado: str
    juicios: tuple[Juicio, ...]
    en_conjunto: str                 # lo que sólo se ve mirando los seis juntos
    sin_documento: tuple[str, ...]   # hechos cuyo texto no se pudo bajar
    recortados: tuple[str, ...]      # hechos cuyo documento se cortó por el tope
    descartados: int                 # juicios tirados por etiqueta o ticker inválidos
```

```python
# interprete/ajuste.py
@dataclass(frozen=True)
class Observacion:
    sobre: str      # ticker de la operación etiquetada, resuelto por el código
    dice: str

@dataclass(frozen=True)
class Comentario:
    estado: str
    observaciones: tuple[Observacion, ...]
    en_conjunto: str                 # lo que sólo se ve mirando la propuesta entera
    descartadas: int
```

### `en_conjunto` es la razón de ser de la arquitectura elegida

Una llamada por cartera —y no una por activo— se eligió porque permite decir
**«dos de tus activos, el mismo problema»** o «las tres compras van al mismo
sitio». Eso no cabe en ninguna observación atada a un solo activo: sin este
campo, la única ventaja de la opción escogida frente a llamar activo por activo
desaparecería, y nadie lo notaría al leer el código.

Puede venir vacío, y vacío es una respuesta legítima: seis hechos sin nada en
común no tienen nada en común. Se pinta sólo si trae algo.

Se le aplican **las mismas reglas**: cero dígitos, y sólo tickers de la cartera.

Los estados son **datos explícitos**, no se deducen de que las listas vengan
vacías. Es la lección de `noticias/resumen.py`: «no ha presentado ningún 8-K» y
«no lo hemos mirado» se pintan igual de vacíos y son cosas opuestas.

Aquí hay cuatro estados y **un quinto caso que no es un estado**: `HECHA` con
`juicios` vacío significa «se miró, se pagó la llamada, y no salió nada que
decir». No es `FALLO` —la llamada fue bien— ni `SIN_HECHOS` —había hechos—, y
la pantalla tiene que decirlo con esas palabras. Deducirlo de la lista vacía
lo confundiría con los otros dos.

`descartados` se **cuenta y se dice**, no se esconde: que el modelo nombre una
operación inexistente es señal de que algo va mal en el prompt, y un recorte
silencioso es indistinguible de que no hubiera nada.

## Los dos guardarraíles, y por qué no son el mismo

La mitad de noticias tiene verdad contrastable; la de rebalanceo no. Un juicio
sobre un 8-K se ancla a una frase que existe o no existe en el documento. Un
comentario sobre la deriva no tiene texto que citar: su materia prima son
números que puso el código.

**Noticias:**

| Regla | Cómo se comprueba |
|---|---|
| Cada juicio lleva cita literal | `verificar_cita` contra **el texto que se envió**, no el expediente entero |
| Cero dígitos en `que_dice` y `por_que_te_toca` | `sin_digitos`. Nunca sobre `cita`: la empresa sí escribe cifras |
| Sólo etiquetas existentes | pertenencia al mapa `A…F` |
| Cita que no verifica tras un reintento | se **enseña marcada** «sin respaldo literal» |
| Juicio sin `que_dice` o sin `por_que_te_toca` | se cae y se cuenta |
| `en_conjunto` nombra un ticker ajeno o lleva un dígito | se vacía entero, no se recorta a trozos |

**Rebalanceo:**

| Regla | Cómo se comprueba |
|---|---|
| Cero dígitos | `sin_digitos` |
| Sólo operaciones que G propuso | pertenencia al mapa de etiquetas |
| Observación sin texto | se cae y se cuenta |
| `en_conjunto` con ticker ajeno o dígito | se vacía entero |

`en_conjunto` se vacía y no se recorta porque un párrafo al que se le ha quitado
una frase queda diciendo algo que nadie escribió. Un juicio suelto sí se puede
tirar: los demás siguen siendo verdad por su cuenta.

La asimetría con B se hereda entera: una cita fallida se conserva marcada
porque un humano todavía puede juzgarla; un dígito inventado se lee exactamente
igual que uno real y es fatal.

## El archivo: lo interpretado no se tira

### Por qué, y por qué no basta la caché

La caché por hash conserva interpretaciones, pero es una **optimización de
coste**, no un registro: clave opaca, dentro de un `.cache/`, borrable sin
avisar y sin forma de hojearla. El archivo es otra cosa y resuelve algo que la
caché no puede.

**Repara la ceguera del tope de seis.** Un `4.02` —«las cuentas anteriores no
son fiables», lo más grave de la lista congelada— de hace ocho meses hoy no lo
ve nadie: hay seis hechos más nuevos por encima. Pero si se guardó cuando *era*
reciente, se queda leído para siempre. El archivo **acumula cobertura con el
tiempo**, y el tope deja de ser una ceguera permanente para ser una ventana.

### Dónde vive, y una trampa que casi se cuela

```
libros/interpretaciones/<mismo basename que el libro>.json
```

**No en `libros/` a secas.** `libro.listar()` hace `glob("*.json")` sobre esa
carpeta y `libro.cargar` valida lo que encuentre: un fichero de interpretaciones
ahí dentro aparecería como **un libro ilegible**, que es exactamente el defecto
que H pagó —un libro que no se puede leer contándose como que no hay ninguno—.
`Path.glob` no recorre subcarpetas, así que la subcarpeta basta. Hay un test que
mete un archivo de interpretaciones y afirma que `listar()` sigue devolviendo
los mismos libros.

Queda bajo `libros/`, que ya está en `.gitignore`: es dato personal y no entra
en el repo sin que nadie tenga que acordarse.

### Es append-only, como el libro

Volver a interpretar **añade**, no pisa. Una interpretación es un juicio hecho
en un momento, por un modelo y una versión de prompt concretos; reescribirla
borraría que cambió. Es la misma forma que `Libro.objetivos`, que es una tupla
donde `objetivo` devuelve el último: se conserva todo, se enseña lo último.

Cada entrada lleva estampados `cuando`, `modelo` y `version`, para que dentro de
un año se sepa quién dijo eso y con qué reglas.

### Las estructuras del archivo

```python
@dataclass(frozen=True)
class Sesion:
    """Una pulsación del botón de hechos. `en_conjunto` es de la sesión, no de
    un hecho: habla de los seis juntos y no tiene dónde ir si se reparte."""
    cuando: datetime
    modelo: str
    version: str
    juicios: tuple[Anotada, ...]
    en_conjunto: str

@dataclass(frozen=True)
class Anotada:
    url: str                  # la identidad del hecho: estable, única, ya en `Hecho`
    ticker: str
    hecho_cuando: date
    tipos: tuple[str, ...]
    juicio: Juicio            # incluye `verificada` tal como quedó ese día

@dataclass(frozen=True)
class Foto:
    """El estado que un comentario de rebalanceo comentaba. Sin esto el texto
    queda huérfano: habla de una deriva que mañana ya es otra."""
    pesos_reales: tuple[tuple[str, float], ...]
    pesos_objetivo: tuple[tuple[str, float], ...]
    operaciones: tuple[tuple[str, str, float], ...]   # ticker, acción, % invertido

@dataclass(frozen=True)
class Comentada:
    cuando: datetime
    modelo: str
    version: str
    foto: Foto
    observaciones: tuple[Observacion, ...]
    en_conjunto: str
```

`urls_leidas(archivo) -> set[str]` es lo que deriva «qué es nuevo». La identidad
de un hecho es su `url` —la del expediente en EDGAR—, que ya viaja en `Hecho` y
no hay que inventar ninguna.

### El archivo es lo que se pinta, no una segunda fuente

Un solo camino, y esto evita la pregunta de dónde saca su fecha cada juicio:

1. `interprete.noticias.leer(...)` devuelve una `Lectura` fresca.
2. `archivo.anotar(...)` la añade como una `Sesion`, con su `cuando`.
3. **La pantalla pinta siempre desde el archivo**, nunca desde la `Lectura`.

Mezclar juicios frescos y recuperados en una misma lista obligaría a que cada
`Juicio` cargara su propia fecha, y a que dos sitios distintos supieran
componerla. Así la fecha vive donde pertenece —en la sesión— y hay un único
orden de lectura.

**La excepción es el archivo ilegible.** Ahí no se puede guardar ni leer, así
que la pantalla pinta la `Lectura` recién hecha directamente, con el aviso de
que esa lectura no se ha podido guardar. Es el único camino donde se pinta sin
pasar por el archivo, y existe para que un fichero roto no se lleve por delante
la llamada que el usuario acaba de pagar.

### Un archivo ilegible NO se trata como vacío

`ranking/llm.py:_leer_cache` borra el fichero corrupto y devuelve `None`, y hace
bien: una caché rota es un fallo de caché. **Aquí sería lo contrario.** Un
archivo ilegible es historial perdido, y tragárselo en silencio significaría
volver a pagar y además perder lo guardado sin que nadie se entere.

Se levanta `ArchivoIlegible`, la pantalla lo dice, y **el fichero no se toca**:
mientras esté ahí se puede recuperar a mano. El botón de interpretar sigue
funcionando, pero avisa de que no va a poder guardar.

Es la misma distinción que `credenciales.ConfigIlegible` frente a «no hay
fichero»: uno es un usuario nuevo, el otro es un problema.

## El presupuesto, acotado por construcción

- `TOPE_HECHOS` (= 6) hechos materiales más recientes, importado de
  `noticias/resumen.py`.
- `TOPE_CARACTERES = 30_000` por hecho. Se corta **por el final** —una nota de
  prensa pone las cifras arriba— y el hecho recortado sale nombrado en
  `Lectura.recortados`.
- Máximo duro: ~180.000 caracteres, ~48k tokens por pulsación.
- El coste real varía **unas doce veces** según qué seis toquen: seis `2.02` con
  anexo llegan al tope; seis `5.02` recortados son ~15.000 caracteres (la media
  de los nueve recortados medidos es 2.429).

### El archivo abarata esto, y por eso va aquí

Sólo se manda el **documento** de los hechos cuya `url` no esté en el archivo.
Los ya leídos entran como su `que_dice` guardado —unos cientos de caracteres en
lugar de treinta mil—, así que `en_conjunto` sigue viendo los seis y sólo se
paga por lo nuevo. En régimen, una pulsación sin hechos nuevos cuesta casi nada.

Es la opción «sólo lo nuevo desde la última vez» que se descartó por pedir
estado propio: con el archivo deja de ser una pieza extra y pasa a ser una
consecuencia.

**Lo que vuelve al prompt es salida del modelo, y se dice.** Ese `que_dice` ya
pasó los guardarraíles el día que se escribió —sin dígitos, ticker de la
cartera—, así que no abre ninguna puerta nueva. Pero su cita **no se vuelve a
verificar**: el documento ya no se envía, y verificar contra un texto que no
está delante sería afirmar algo que no se ha comprobado. Un juicio recuperado
del archivo conserva el `verificada` que tuvo y se pinta con esa misma marca.
Nunca se re-verifica, nunca se re-marca.

La caché es por hash de contenido de **exactamente lo que se envía**, como
`ranking/llm.py:clave_cache`: el prompt renderizado, el sistema, el modelo y una
versión manual. Un hecho nuevo cambia el hash; volver a abrir el panel, no.

**La caché de H y la de I no son la misma y no tienen por qué coincidir.** La de
H caduca por tiempo (`VALIDEZ`); la de I es por contenido. Si H refresca y los
seis hechos son los mismos, el hash de I no cambia y no se vuelve a llamar. Es
lo correcto, y conviene tenerlo escrito para que nadie lo «arregle».

## La pantalla

- **Pestaña «Noticias» del panel**, bajo el resumen: botón *«Interpretar estos
  hechos»*, **con cuántos son nuevos en la propia etiqueta** — un botón que no
  dice si va a costar algo es un botón que se pulsa a ciegas. Cada juicio sale
  con el peso del activo puesto **por el código** al lado, y la cita en
  `caption` con enlace al documento. Es el hueco que K dejó preparado.
- **Lo ya leído se pinta sin pulsar nada.** Es el cambio de carácter que trae el
  archivo: la pestaña deja de estar vacía hasta que pagas, y se va llenando.
  Cada juicio recuperado lleva su fecha de lectura, porque un juicio de hace
  seis meses y uno de esta mañana no valen lo mismo.
- **Página de Rebalanceo**, tras la propuesta y antes de la puerta a Seguimiento:
  botón *«¿Qué se le escapa a la aritmética?»*.
- **Los comentarios anteriores de rebalanceo van plegados y fechados, con su
  foto.** Nunca junto a la propuesta de hoy: hablan de una deriva que ya no es
  la que tienes delante, y pintarlos como si aplicaran sería la misma mentira
  que sumar dos cortes temporales distintos —el defecto que en F dio una
  `GANANCIA −9.700`.
- Todo lo que venga del modelo pasa por `noticias/texto.py` antes de pintarse.
  En Streamlit `$…$` es LaTeX, y un texto financiero va lleno de dólares: es un
  defecto ya pagado en H.

## Fallos previstos

| Qué | Por qué pasaría | Qué se hace |
|---|---|---|
| El modelo «limpia» la cita | Reescribe `…` como `...` o `•` como `-`, y `_normalizar` no cubre esos dos códigos | Reintento; si sigue, sale marcada. **No se amplía `verificacion.py`**: B está en producción |
| El recorte se lleva la noticia | Un 8-K sin `SIGNATURE`, o con el `Item` después | Si falta cualquiera de las dos marcas se manda el cuerpo entero |
| `Item` con espacio fino | MSFT lo usa. Un literal `"Item "` no casa | `\s+` en la expresión, y un test con U+2009 |
| Un documento no se puede bajar | Red, o un `EX-99` que revienta al extraer | Ese hecho sale en `sin_documento`, los demás se interpretan igual |
| El modelo inventa una operación | Es lo que hacen los modelos | La letra no existe en el mapa: se cae y se cuenta |
| Streamlit no reimporta `interprete/` | Paquete nuevo en un servidor ya arrancado | Hay que reiniciar. Es la trampa que ya costó un `AttributeError` en J |
| Sin `ANTHROPIC_API_KEY` | El usuario no la ha puesto | `estado = SIN_CLAVE`, la pantalla dice dónde ponerla |
| El archivo se lee como un libro roto | `libro.listar()` globea `*.json` sobre `libros/` | Va en `libros/interpretaciones/`, y hay un test que lo afirma |
| Archivo corrupto tragado en silencio | Copiar el `_leer_cache` de B, que borra y sigue | `ArchivoIlegible`, se dice, y **el fichero no se toca** |
| Dos pestañas escribiendo a la vez | Streamlit permite dos ventanas del mismo libro | Releer justo antes de escribir, como `libro.actualizar`. Riesgo residual aceptado: un usuario, una app |
| Un juicio viejo pintado como fresco | El archivo devuelve texto sin fecha visible | Cada juicio recuperado lleva su fecha de lectura al lado |

## Pruebas

Sin red, con cliente falso:

- **Privacidad:** un libro con importes distintivos, y ninguno aparece en lo que
  `contexto.py` produce. Más el sabotaje: no hay parámetro por donde meterlos.
- **Documentos:** anexo cuando lo hay, cuerpo cuando no; recorte por marcas con
  espacio fino; cuerpo entero cuando falta una marca; tope aplicado y anunciado.
- **Guardarraíles:** cita inventada → marcada; dígito → reintento y luego fuera;
  etiqueta inexistente → se cae y se cuenta; observación sobre operación no
  propuesta → se cae.
- **Estados:** los cuatro se distinguen, ninguno se deduce de una lista vacía, y
  `HECHA` con cero juicios no se confunde con `SIN_HECHOS` ni con `FALLO`.
- **`en_conjunto`:** con dígito o con ticker ajeno se vacía **entero**, y el
  resto de la `Lectura` sobrevive intacta.
- **Caché:** mismo contenido no llama; contenido distinto sí; fallo no se guarda.
- **Archivo:** escribir dos veces **añade** y no pisa; `urls_leidas` encuentra lo
  de sesiones viejas; un hecho ya leído no manda su documento pero sí su
  `que_dice`; un juicio recuperado **conserva su `verificada`** y no se
  re-verifica; un archivo corrupto levanta `ArchivoIlegible` y **el fichero
  sigue en disco**; y `libro.listar()` devuelve los mismos libros con un archivo
  de interpretaciones dentro de `libros/interpretaciones/`.

Dos tests marcados `red` que llaman de verdad a Sonnet 5, como los de B.

## Lo que I no resuelve

- **No propone operaciones propias.** Es la decisión, no una carencia.
- **No lee más de lo que ves, y el archivo sólo cubre hacia delante.** Un `4.02`
  de hace ocho meses no entra hoy, y tampoco está guardado: el archivo empieza
  vacío el día que se estrena. Acumula cobertura desde ahí, no hacia atrás.
  Rellenarlo pediría una pasada histórica —los ~134 materiales de la ventana de
  H, cerca de un millón de tokens—, que es justo lo que el tope evita.
- **No hay botón de «vuelve a leer éste».** Volver a interpretar añade una
  sesión entera; no se puede pedir una segunda lectura de un solo hecho. El
  modelo de datos lo admite —es append-only— y la pantalla no lo ofrece.
- **El archivo no se respalda.** Vive bajo `libros/`, que está en `.gitignore`
  por ser dato personal. Quien borre esa carpeta pierde el historial, igual que
  perdería sus libros.
- **No deduplica la prensa.** Sigue siendo deuda declarada de H.
- **No interpreta el calendario.** `Evento` no entra: H da punteros, no fechas.
- **No toca los 8-K de emisores fuera de la SEC**, que no existen.
