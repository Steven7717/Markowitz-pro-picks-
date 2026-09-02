# Sub-proyecto F — Libro de posiciones y seguimiento

**Fecha:** 2026-09-02
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Una pantalla donde el usuario registra lo que compró **de verdad, con su
dinero**, y ve cómo va cada activo por separado y la cartera en conjunto: valor,
ganancia, rendimiento medido de dos formas distintas, dividendos, y comparación
contra lo que el optimizador le había dicho que hiciera.

## Lo que ya existe y esto no repite

`cartera.py` guarda portafolios y `vistas/portafolios.py` los lista, los carga y
los borra. **Eso no es seguimiento y no hay que confundirlo**: un `Portafolio`
guardado es, en palabras de su propio docstring, *"una fotografía, no un
enlace"* — los pesos y las métricas de una corrida, congelados, sin dinero
dentro. F añade lo contrario: un **libro vivo** de lo que se compró y por
cuánto.

Los dos se necesitan. La fotografía es el **objetivo**; el libro es lo que
**pasó**. La pantalla de F mide la distancia entre ambos.

Se reutiliza, no se reescribe:

| Ya existe | F lo usa para |
|---|---|
| `cartera.Portafolio` | El objetivo de pesos, copiado dentro del libro |
| `cartera.guardar` (tmp + `replace`, sufijo en colisión) | El mismo patrón de escritura para el libro |
| `cartera.Entrada` / `listar` (devuelve los rotos con su motivo) | Listar libros sin esconder los ilegibles |
| `cartera.formato_cifra` / `formato_porcentaje` | La regla "—, nunca 0,00" para lo que no se midió |
| `tema.cabecera` / `tema.etiqueta` | El lenguaje visual de las demás pantallas |
| `medidores.py` | La base de los medidores; la explota **G**, no F |

## Dónde encaja

Es el primero de cuatro sub-proyectos que salieron de descomponer la petición
original, por el mismo criterio con que se descompusieron A, B, C y D:

| # | Sub-proyecto | Entrega | Estado |
|---|---|---|---|
| F | Libro de posiciones y seguimiento | Valoración, rendimiento por activo y agregado, referencias | **este documento** |
| G | Rebalanceo y aportaciones | Medidores de deriva, bandas, reparto de la aportación | pendiente |
| H | Noticias y calendario | Feed de EDGAR, prensa, calendario de eventos | pendiente |
| I | Capa de IA | Interpretación de noticias, propuestas de ajuste | pendiente |

G depende de F por completo: sin libro no hay pesos reales, y sin pesos reales
no hay deriva que medir. H es independiente de F salvo por la lista de tickers.
I depende de los tres.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Qué se guarda | **Sólo asientos.** Posiciones, pesos, valor, TWR y TIR se derivan | Una sola fuente de verdad. Posiciones y asientos no pueden desincronizarse porque las posiciones no se guardan |
| Corregir un error | Asiento de `anulacion` más el asiento bueno | Una edición reescribiría en silencio el rendimiento del mes pasado |
| Precios | Módulo propio con `auto_adjust=False` | Los precios ajustados cambian hacia atrás: el coste de adquisición se movería solo |
| Alta de operación | Importe **o** acciones, más precio; se deriva el tercero y se guardan los tres | El usuario piensa en dinero; el bróker habla en acciones |
| Precio desconocido | Cierre del día, marcado `precio_estimado` | Una compra intradía en un día volátil se desvía 3-4% sin que nada lo indique |
| Efectivo | Explícito, con `aportacion` y `retiro` propios | La TIR necesita los flujos externos fechados, y G necesita saber cuánto hay sin asignar |
| Rendimiento | **TWR y TIR, los dos** | TWR es lo único comparable contra un índice; TIR es lo que ganó el usuario |
| Dividendos | Calculados desde yfinance, corregibles a mano | ~1,3-2% anual en el S&P 500: ignorarlos baja el rendimiento sin que se sepa por qué |
| Coste | Media ponderada, no FIFO | Sólo cambia el reparto realizado/latente, nunca el total; esto no es un cálculo fiscal |
| Origen de la cartera | Portafolio guardado **o** a mano | Sin lo segundo no se puede seguir lo que ya estaba comprado antes del programa |
| Objetivo de pesos | Elección explícita entre estrategia y 1/N, **sin preselección** | El walk-forward ya dice cuándo la optimización no le gana a 1/N; un valor por defecto convertiría esa evidencia en un clic que nadie mira |
| Historial de objetivos | Lista que se apila, no campo único | "¿Contra qué objetivo medía en marzo?" tiene que tener respuesta |
| Estructura | Paquete `seguimiento/` más vista fina | Igual que `aprobacion/` y `cartera.py`: la lógica se prueba sin arrancar Streamlit |
| Moneda | USD única, declarada en pantalla | El universo es el S&P 500; mezclar divisas en silencio daría cifras falsas |

## Arquitectura

```
programa/libros/<fecha>-<nombre>.json ─┐
                                       ├─→ seguimiento.posiciones ─→ seguimiento.rendimiento ─┐
yfinance (sin ajustar) ────────────────┘              │                                       ├─→ vistas/seguimiento.py
                                                      └─→ seguimiento.comparacion ────────────┘
                                                                    ▲
                                    portafolios/, cartera.py ───────┘  (el objetivo)
```

Paquete nuevo `programa/seguimiento/`, hermano de `aprobacion/`:

- **`seguimiento/libro.py`** — el asiento: tipos, validación, alta, y la
  escritura atómica del fichero. Rechaza lo que no puede haber pasado (vender lo
  que no se tiene, fecha futura, anular un id inexistente) nombrando el motivo.
  La lectura valida antes de devolver, con `ContratoRoto` como `cartera.cargar`.
- **`seguimiento/precios.py`** — cierres **sin ajustar**, dividendos y splits,
  con caché. Separado de `data.py` a propósito (abajo).
- **`seguimiento/posiciones.py`** — libro más precios → acciones por ticker,
  efectivo y valor, día a día. Aplica splits y calcula los dividendos.
- **`seguimiento/rendimiento.py`** — TWR, TIR, ganancia realizada y latente,
  contribución de cada activo.
- **`seguimiento/comparacion.py`** — objetivo teórico, 1/N y S&P 500 sobre la
  misma línea temporal de flujos.

**El nombre importa.** El paquete no puede llamarse `cartera/`: `cartera.py` ya
existe y es otra cosa. Y el directorio de datos es `libros/`, no `seguimiento/`,
porque un directorio de datos con el mismo nombre que el paquete colisionaría en
el disco.

La vista es `programa/vistas/seguimiento.py`, y entra en la sección **Cartera**
de `st.navigation` en `app.py`, entre "Portafolios guardados" y "Comparar". Es
la sección donde el usuario ya busca lo suyo.

### Lo que cambia en el optimizador

Un cambio pequeño y necesario en `vistas/optimizador.py`. El dict `metrics`
(línea 367) ya guarda `oos_sharpe`, `oos_equal_weight_sharpe` y `oos_windows`,
pero **le faltan `oos_sharpe_stderr` y `beats_equal_weight`**. Sin el error
estándar, el veredicto de tres estados —gana, pierde, o no se distingue del
ruido— no se puede reconstruir a partir de lo guardado: dos Sharpes sueltos no
dicen si la diferencia cabe dentro del ruido. `walk_forward_validation` ya
devuelve los dos campos; sólo hay que dejarlos escritos.

Eso mejora también lo que ya existe: los portafolios guardados a partir de ahora
llevarán su veredicto completo, y `vistas/portafolios.py` podrá mostrarlo.

### Por qué no se reutiliza `data.py`

`data.py` descarga con `auto_adjust=True`. Los precios ajustados **cambian hacia
atrás** con cada dividendo y cada split: el precio al que se compró en enero no
será el mismo número dentro de tres meses. Al optimizador le da igual, porque
sólo usa retornos y el ajuste es consistente dentro de una descarga. A un libro
de posiciones le produce un coste de adquisición que se mueve solo, y nadie lo
vería, porque el número resultante sigue siendo plausible — el modo de fallo que
este repo ya documentó cuatro veces.

Añadir un interruptor a `data.py` arriesga lo contrario: que el optimizador
reciba algún día precios sin ajustar sin que nadie lo note. Módulo aparte.

## El asiento

Seis tipos, y ninguno se edita ni se borra jamás:

| tipo | efecto |
|---|---|
| `aportacion` | entra dinero de fuera |
| `retiro` | sale dinero fuera |
| `compra` | efectivo → acciones |
| `venta` | acciones → efectivo |
| `dividendo` | cobro real; sustituye al calculado para ese ticker y fecha |
| `anulacion` | referencia el `id` de otro asiento y lo deja sin efecto |

```json
{
  "id": "a3f1...",
  "fecha": "2026-09-02",
  "tipo": "compra",
  "ticker": "AAPL",
  "acciones": 12.3456,
  "precio": 178.25,
  "importe": 2200.00,
  "comision": 1.50,
  "precio_estimado": false,
  "anula": null,
  "nota": ""
}
```

**El efectivo es explícito, y no es burocracia.** La TIR necesita saber qué
dinero entró de fuera y en qué fecha; el sub-proyecto G necesita saber cuánto
hay pendiente de asignar, porque es literalmente lo que va a repartir. Para que
eso no dé fricción, el formulario de compra mira el saldo: si hay efectivo
pendiente suficiente lo usa, y si no, escribe la aportación junto a la compra.
Siempre dice cuál de las dos hizo antes de guardar.

**Se guardan `importe`, `acciones` y `precio` los tres**, aunque uno se haya
derivado. Así el fichero se lee sin recalcular nada, y si mañana cambia la
fórmula de derivación los datos de ayer no se mueven.

**Corregir es anular y volver a escribir**, como la contabilidad de verdad. Es
lo que hace que "¿cómo llegué aquí?" tenga siempre respuesta.

**La comisión suma al coste y resta al ingreso.** En una compra, el coste de
adquisición es `importe + comision`; en una venta, lo que entra en efectivo es
`importe − comision`. Sale del efectivo de la cartera y **no es un flujo
externo**: es un coste que la cartera paga, así que arrastra el rendimiento
hacia abajo, que es exactamente lo correcto — las comisiones se pagan de verdad.
Tratarlas como flujo externo las dejaría fuera del cálculo y la cartera se vería
mejor de lo que fue.

Cuando la compra se financia desde fuera, la aportación que se escribe junto a
ella incluye la comisión. Si no, el efectivo quedaría negativo por el importe de
la comisión en cuanto se registrara la primera compra.

## El fichero de libro

`programa/libros/<fecha>-<nombre>.json`, con el mismo esquema de nombre que
`cartera.guardar`: fecha delante para que la carpeta se ordene sola, y sufijo
numérico si dos caen en el mismo segundo.

```json
{
  "nombre": "Cartera principal",
  "creado": "2026-09-02T10:00:00",
  "moneda": "USD",
  "objetivos": [
    {
      "fecha": "2026-09-02",
      "base": "equal_weight",
      "portafolio": { "...": "un cartera.Portafolio copiado entero" },
      "veredicto": {
        "oos_sharpe": 0.41,
        "oos_equal_weight_sharpe": 0.55,
        "oos_sharpe_stderr": 0.09,
        "beats_equal_weight": false,
        "oos_windows": 12
      }
    }
  ],
  "asientos": []
}
```

`objetivos` es **una lista que se apila**, no un campo que se sobrescribe. El
vigente es el último. Sin eso, la deriva que G calcule dentro de seis meses no
sabría contra qué objetivo se estaba midiendo antes.

**El objetivo lleva un `cartera.Portafolio` copiado dentro**, no la ruta al
fichero de `portafolios/`. Misma razón que las fichas dentro del acta y que la
propia `cartera.py` da para no recalcular: un portafolio guardado se puede
borrar desde `vistas/portafolios.py` —hay un botón— y el libro se quedaría
apuntando a nada. Como la validación de `cartera.cargar` ya existe, la lectura
del libro la reutiliza para esa parte en vez de escribir otra.

**`base` distingue "los pesos de la estrategia" de "1/N".** El optimizador ya
mide si la optimización le gana a repartir por igual —`beats_equal_weight`, con
sus tres estados: gana, pierde, o no se distingue del ruido— y ya lo dice en
pantalla. Guardar el objetivo ignorando ese veredicto sería tirar la única
evidencia que el programa produjo sobre si la optimización aportaba algo. Por
eso el diálogo ofrece las dos opciones **sin preseleccionar ninguna**, con el
veredicto delante, y no deja seguir hasta que se elija: mismo razonamiento que
dejó las casillas desmarcadas en C, y aquí cuesta un clic, no quince.

Con `base: "equal_weight"`, los pesos que se usan son 1/N sobre los tickers del
portafolio; el `portafolio` copiado se guarda igual, porque es lo que documenta
de dónde salió la lista y con qué parámetros.

Un libro creado a mano nace con `objetivos: []` y lo dice en la interfaz; el
medidor de G queda apagado hasta que se le asigne uno, que puede ser 1/N sin
pasar por el optimizador.

### Dónde vive y quién lo ve

**`libros/` se ignora en git, a diferencia de `actas/` y `portafolios/`.** Los
dos hermanos están a la vista a propósito —y el `.gitignore` de la raíz lo dice
con todas las letras— porque guardan decisiones y pesos. Un libro guarda **cuánto
dinero tiene el usuario y en qué**. Es otra categoría, y la excepción tiene que
ser deliberada y estar escrita, no heredada por parecido.

Hacen falta las dos líneas, por la misma razón que explica el `.gitignore` de la
raíz: `/libros/` en el de la raíz, para lo que se genere ahí por error, y
`libros/` en `programa/.gitignore`, que es el que decide de verdad.

Y con la misma advertencia que ya lleva `credenciales.py`: *`.gitignore` protege
de git, no de un ZIP*. Quien recomprima la carpeta para pasársela a alguien
mandaría sus posiciones dentro, así que el README tiene que decirlo.

## Reconstrucción

Asientos ordenados por fecha, con el orden de inserción como desempate. De ahí
salen acciones por ticker y efectivo en cada día hábil, y el valor diario
multiplicando por el cierre sin ajustar.

Dos cosas que es fácil olvidar y que rompen los números en silencio:

- **Splits.** Un 4:1 en junio multiplica por cuatro las acciones compradas
  antes. Sin aplicarlo, la cartera parece haber perdido el 75% de un activo de
  un día para otro. **El asiento no se toca**: el factor se aplica en la
  reconstrucción, igual que todo lo demás. Reescribir el `acciones` guardado
  sería editar el pasado, que es justo lo que este diseño evita.
- **Dividendos calculados.** Para cada fecha ex-dividendo: acciones en cartera
  ese día por dividendo por acción. Es un asiento derivado, no escrito en el
  libro. Se marca como **teórico bruto** —no sabe de retenciones ni de si se
  reinvirtió— y si existe un asiento manual de `dividendo` para ese ticker y esa
  fecha, manda el manual.

El dividendo entra en **efectivo**, y **no es un flujo externo**: es dinero que
la cartera generó, no dinero que el usuario metió. Confundirlo con una
aportación es el error clásico aquí, y tiene una consecuencia concreta y
medible: inflaría el denominador de la TIR y hundiría el rendimiento, porque el
cálculo estaría contando como capital aportado justo lo que la cartera acababa
de ganar. **Los únicos flujos externos son `aportacion` y `retiro`.** Todo lo
demás —compras, ventas, dividendos, comisiones— mueve dinero dentro de la
cartera, y por eso cuenta en el rendimiento en vez de quedar fuera de él.

## Los números

### TWR (ponderado por tiempo)

Con valoración diaria: `r_t = (V_t − F_t) / V_{t−1} − 1`, donde `F_t` es el
flujo externo del día. TWR = Π(1+r_t) − 1.

Dos guardas, y las dos tienen que tener un test que las vea dispararse:

- **`V_{t−1} = 0`.** Pasa el primer día, y si se vacía la cartera y se vuelve a
  empezar. El retorno de ese día es indefinido y se trata como 0, no como una
  división por cero.
- **No anualizar por debajo de 30 días.** Un 2% en tres días anualiza a +780%.
  Debajo del umbral se muestra el retorno del periodo, sin anualizar, y se dice
  que lo es.

### TIR (ponderada por dinero, XIRR)

Raíz de `Σ CF_i / (1+r)^(d_i/365) = 0`, resuelta con `scipy.optimize.brentq`
sobre un intervalo acotado. Flujos: aportaciones negativas, retiros positivos, y
el valor actual positivo al cierre.

Con flujos mezclados puede haber varias raíces o ninguna. **Si no hay cambio de
signo en el intervalo, la respuesta es "no calculable"**, no la primera raíz que
aparezca: un número inventado aquí es indistinguible de uno real. Misma guarda
de 30 días que TWR.

Lo que no se pudo medir se muestra con `cartera.formato_cifra`, que devuelve
"—" y nunca un 0,00 — la misma regla que ya aplican los portafolios guardados y
los medidores de candidatos, y por el mismo motivo: un cero ahí se leería como
una afirmación que nadie hizo.

### Aportaciones y por qué hacen falta los dos

Con dos aportaciones en fechas distintas, `valor actual / total aportado − 1` no
es el rendimiento de la cartera: mezcla lo que rindieron los activos con cuándo
entró el dinero. TWR neutraliza eso y es lo único comparable contra el S&P 500 y
contra 1/N. TIR es lo que ganó el usuario de verdad. **Cuando los dos se separan
mucho, la página lo dice**: esa diferencia es exactamente el efecto del timing
de las aportaciones, y es información, no ruido.

La ganancia en dólares (valor menos aportado neto) se muestra siempre, porque
esa sí es exacta sin condiciones.

### Coste y ganancia

Media ponderada. La ganancia latente es el valor actual menos el coste de las
acciones que se siguen teniendo; la realizada sale de las ventas. El método
queda declarado en pantalla, porque cambia el reparto entre las dos aunque no el
total.

### Contribución por activo

**En dólares.** Cuánto de la ganancia total viene de cada activo. Es exacto y
suma. Los porcentajes de contribución con aportaciones de por medio son
engañosos y no se muestran.

### Las tres referencias

El objetivo teórico, 1/N y el S&P 500 reciben **el mismo dinero en las mismas
fechas** que metió el usuario. Así la comparación aísla la elección de activos
del timing de las aportaciones; si cada referencia tuviera su propio calendario,
se estaría comparando el calendario, no la cartera.

El objetivo teórico invierte cada flujo a los pesos objetivo vigentes ese día y
no rebalancea después: es la cartera que habría si se hubiera seguido el plan.
**1/N aparece siempre**, se haya elegido lo que se haya elegido como objetivo —
misma filosofía que el Equal Weight de la pantalla del optimizador.

## La vista

`programa/vistas/seguimiento.py`, sólo widgets, con `tema.cabecera` y
`tema.etiqueta` como el resto de pantallas:

1. Selector de libro y botón de crear. Los ilegibles se pintan con su motivo,
   como hace `vistas/portafolios.py`, en vez de desaparecer de la lista.
2. Fila de KPI con `st.metric`: **Valor · Aportado neto · Ganancia $ · TWR ·
   TIR · Dividendos**. Aportado neto es aportaciones menos retiros — el dinero
   propio que hay dentro ahora mismo, no la suma de todo lo que pasó por la
   cartera.
3. El aviso cuando TWR y TIR se separan.
4. Gráfico de valor en el tiempo con las tres referencias superpuestas y una
   marca en cada aportación.
5. Tabla por activo: acciones, coste medio, precio, valor, peso real frente al
   objetivo, ganancia en dólares y en porcentaje, dividendos, contribución.
6. Barras de contribución por activo.
7. Formulario de alta de asiento, en un expander.
8. Historial de asientos, con los anulados tachados y los de `precio_estimado`
   marcados, para que se vea de un vistazo qué números salieron del bróker y
   cuáles del cierre del día.
9. Exportar a Excel y PDF reutilizando `exporter.py`.

Crear un libro desde un portafolio guardado se ofrece también en
`vistas/portafolios.py`, junto a "Cargar en el optimizador": es donde el usuario
está mirando la fotografía que quiere empezar a seguir.

## Fallos previstos

Se rechaza el asiento, nombrando el motivo:

| Situación | Por qué no se guarda |
|---|---|
| Vender más acciones de las que hay | Produciría una posición negativa que nadie pidió |
| Retirar más efectivo del que hay | Igual |
| Precio, acciones o importe ≤ 0 | No es una operación |
| Fecha futura | No ha pasado |
| Ticker sin precio esa fecha | Festivo, o anterior a su salida a bolsa: guardarlo dejaría una posición fantasma sin valorar |
| `anulacion` a un id inexistente o ya anulado | Anular dos veces no significa nada |

Y dos que no son rechazos sino formas de no mentir:

- **yfinance caído o ticker deslistado** → se muestra la cartera con el último
  precio conocido **y su fecha**, marcado como obsoleto. Nunca un "valor de hoy"
  calculado con precios de hace un mes en silencio.
- **Fichero de libro corrupto o truncado** → se avisa y no se abre, pero **no se
  borra**, a diferencia de las cachés de `ranking/` y `fundamentals/`. Una caché
  se regenera; un libro de posiciones no. A diferencia de
  `vistas/portafolios.py`, que ofrece borrar el fichero roto, aquí **no hay
  botón de borrar**: allí lo peor que se pierde es una fotografía repetible, y
  aquí es el historial entero de lo que alguien compró.

La escritura es tmp-then-`replace()`, como `cartera.guardar` y
`aprobacion/acta.py`, por la misma razón: un proceso muerto a media escritura no
puede dejar el libro a medias.

## Pruebas

En `programa/tests/`, con los nombres que ya usa el repo:
`test_seguimiento_libro.py`, `test_seguimiento_posiciones.py`,
`test_seguimiento_rendimiento.py`.

Además de la reconstrucción contra libros conocidos, incluyendo un split y una
anulación:

- **Control negativo.** Cartera de una sola compra, sin aportaciones
  posteriores, sin dividendos y sin comisión. En ese caso las tres medidas están
  ligadas por identidad y el test las comprueba una a una: el TWR **sin
  anualizar** tiene que ser exactamente el retorno simple `V_final/V_inicial −
  1`, y la TIR tiene que coincidir con el TWR **anualizado**. Escrito como "los
  tres números coinciden" el test sería falso —la TIR viene anualizada y el
  retorno simple no—, y pasaría o fallaría por la razón equivocada.
- **TWR contra un caso calculado a mano donde el retorno simple da otra cosa**,
  para que el test falle si alguien "simplifica" la fórmula más adelante.
- **Contraste externo.** XIRR contra `numpy_financial` en un test opcional que
  se omite si no está instalada — el patrón ya usado con Ledoit-Wolf frente a
  scikit-learn y con RSI frente a `pandas-ta-classic`.
- **Las guardas se disparan de verdad.** Serie que empieza en cero (no debe
  devolver `inf`), tres días de historia (no debe devolver 780%), flujos sin
  cambio de signo (debe decir "no calculable"). Este proyecto ya se comió una
  guarda de varianza que nunca disparaba y devolvía t = 3.6e16; la lección
  aplicada es que una guarda sin test que la vea saltar no es una guarda.
- **Dividendo cuya fecha ex cae después de la venta** → no se cobra.
- **El veredicto sobrevive al viaje.** Guardar un objetivo y volver a leerlo
  tiene que devolver los cinco campos, `beats_equal_weight` incluido con sus
  tres estados — y `None` tiene que seguir siendo `None`, no `False`.
- **Escritura atómica.** Un fallo a media escritura deja el libro anterior
  intacto.

## Lo que este sub-proyecto no resuelve

- **Los medidores de rebalanceo y el reparto de la aportación son G.** F deja
  los pesos reales, los objetivo y el efectivo sin asignar, que es lo que G
  necesita, y nada más. `medidores.py` ya existe y es lo que G explotará.
- **Una divisa.** Un ticker que no cotice en USD daría cifras mezcladas. Se
  declara en pantalla en vez de fingir soporte.
- **No es un cálculo fiscal.** Media ponderada y no lotes FIFO, dividendos
  brutos y no netos de retención.
- **Rutas globales.** `libros/` es una ruta fija del proceso, como `portafolios/`
  y `actas/`. Sigue vigente lo que dice `CONTEXTO.md`: por eso no hay URL
  pública, y este sub-proyecto no la acerca.
- **Los portafolios ya guardados no tienen veredicto completo.** El
  `sharpe_stderr` se empieza a escribir a partir de este cambio; los ficheros
  anteriores no lo llevan y su veredicto se mostrará como "—", no como "no
  gana". Es la misma regla de `formato_cifra`: lo que no se midió no se afirma.
- **Sigue sin responderse cuántas acciones debería tener la cartera.** F permite
  por fin medirlo con dinero real en vez de discutirlo, pero no lo responde.
