# Sub-proyecto K — El panel de seguimiento

**Fecha:** 2026-09-09
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Que «Seguimiento» sea un **panel para mirar la cartera**, y no un informe que
hay que leer entero de arriba abajo.

El síntoma que mejor lo resume está medido más abajo: **a 1024px de ancho, las seis cifras de cabecera salen las seis recortadas con puntos suspensivos.** La pantalla que existe para decirte cuánto vale tu cartera no enseña ni una cifra entera.

J arregló cómo se *llega* al seguimiento y cómo se *empieza*. Lo que queda es la
pantalla en sí: hoy son 484 líneas de un solo scroll donde todo pesa lo mismo,
seis cifras compiten por el mismo renglón, dos tablas de once y nueve columnas
se salen por la derecha, y **no hay ni rastro de las noticias** que el
sub-proyecto H ya sabe traer.

## Los síntomas, medidos en el código

| Síntoma | Dónde está |
|---|---|
| Seis cifras, y **ninguna se puede leer** | `vistas/seguimiento.py:343` — `st.columns(6)`. Medido en la app a 1024px: la columna de contenido son 724px, cada cifra recibe 79px y su caja de texto 50px, y Streamlit las recorta con puntos suspensivos: `51,…` `40,…` `11,…` `19,…` `35…` `60…`. **Las seis.** No es que se aprieten: es que no hay ni un número visible |
| Once columnas en una tabla | `vistas/seguimiento.py:405-420` — Ticker, Acciones, Coste medio, Precio, Valor, Peso real, Peso objetivo, Latente, Realizada, Dividendos, Contribución. Medido: necesita **807px dentro de una caja de 542px**, así que un tercio queda fuera. El historial pide 593px |
| Todo al mismo nivel | Cada bloque es un `st.subheader` (h3): «Valor en el tiempo», «Por activo», «Historial». Nada dice qué es lo importante |
| Las series se distinguen sólo por color | `vistas/seguimiento.py:392` — `st.line_chart` con hasta tres referencias, sin trazo distinto ni etiqueta directa |
| El peso es una columna de texto | «Peso real» y «Peso objetivo» salen formateados en la tabla. No hay nada que se vea de un vistazo |
| No hay noticias | H entrega `Noticia`, `Hecho` y `Evento`, y esta pantalla no las usa |

## La tensión que este diseño resuelve

Un rediseño visual de esta pantalla es **peligroso**, y conviene decir por qué
antes de tocarla. `vistas/seguimiento.py` no es un envoltorio bonito sobre una
librería: dentro tiene correcciones que costaron caro y que **no se ven**.

La principal está comentada en las líneas 277-284:

> `aportado` y `valor` se restan para dar la ganancia, así que tienen que salir
> del **mismo corte temporal**. Medido en la app: una aportación de 10.000
> registrada hoy dejaba VALOR 10.299, APORTADO 20.000 y **GANANCIA −9.700** sin
> que nadie hubiera perdido un dólar.

Hay más de la misma familia: `_cifra` (línea 323) que escribe «—» donde no hay
medida y nunca un cero, el bloque `sin_valorar` que apaga las cifras que
dependen del precio, y la exportación a Excel que arrastra los `None` a propósito
para que una hoja de cálculo no se quede sin el aviso que la pantalla sí lleva.

**Nada de eso está protegido por un test**, porque vive dentro de un guion de
Streamlit que no se puede importar. Si el rediseño reescribe la pantalla y de
paso recalcula esas cifras, el defecto vuelve **y vuelve mudo**: −9.700 es un
número plausible.

**La resolución: primero se saca la aritmética, con tests; después se rehace la
pantalla encima.** Es el mismo reparto que J hizo con `alta.py` / `estrenar.py`
y que F, G y H aplican en todo el proyecto. El orden importa — sacar la lógica
*después* de rehacer la vista sería sacar lo que hubiera quedado, no lo que hay.

## Decisiones tomadas

- **Resumen fijo arriba, pestañas debajo.** Lo que se mira a diario —nombre,
  cifras clave, composición— cabe en una pantalla y no se mueve. El detalle
  —evolución, por activo, movimientos, noticias— va en pestañas. Es lo que
  separa un panel de un informe.
- **La composición se ve, no se lee.** Una fila por activo, la barra es el peso
  real y una marca fina señala el objetivo. Reutiliza `.mpp-tope` de
  `medidores.py` (línea 244), que ya es exactamente eso: una marca de 3px
  colocada por porcentaje.
- **Sin veredicto en Seguimiento.** La barra enseña dónde está el peso y dónde
  debería estar, y **no escribe «sobreponderado»**. Esa palabra es un juicio y
  vive en Rebalanceo. La separación hechos/propuestas es la razón por la que las
  dos pantallas existen por separado, y un rediseño es justo donde se borraría
  sin querer.
- **Las noticias del panel son los hechos materiales más unos titulares.** Los
  8-K que `noticias/criterio.py` marca —reformulación de cuentas, cambio de
  auditor, resultados— son la única parte donde el programa tiene un criterio
  congelado y defendible. La prensa va detrás, corta, y con enlace a la pantalla
  completa.
- **El panel no descarga al abrir.** Lee lo que la caché de H ya tenga, dice de
  cuándo es, y ofrece un botón para traer lo que falte. **Abrir tu cartera no
  puede depender de que la red responda**: con doce activos son doce llamadas, y
  un fallo dejaría la pantalla arrancando con errores encima de las cifras.
- **Ninguna cifra cambia.** K mueve dónde se calculan y cómo se pintan. Si una
  cifra sale distinta después de K, es un defecto de K, no una mejora.

## Arquitectura

| Fichero | Qué cambia |
|---|---|
| `seguimiento/panel.py` | **nuevo** — la aritmética que hoy vive en la vista: cifras de cabecera, composición, filas por activo e historial |
| `noticias/traer.py` | **nuevo** — el `_traer` de `vistas/noticias.py:78`, movido tal cual para que dos pantallas no tengan dos copias |
| `medidores.py` | una función nueva: la barra de peso con marca de objetivo |
| `vistas/seguimiento.py` | se rehace: widgets y disposición, sin aritmética |
| `vistas/noticias.py` | pasa a llamar a `noticias/traer.py` en vez de a su copia local |

`panel.py` y `traer.py` no importan Streamlit. `vistas/seguimiento.py` no calcula
nada.

### Por qué `traer.py` sale, y no se copia

`vistas/noticias.py:78` tiene sesenta líneas de caché-o-descarga con un
invariante que su propio docstring explica: **lo recién descargado también se
guarda, se relee y se reconstruye**, para que ninguna diferencia de tipo —una
tupla que vuelve como lista, una fecha que vuelve como texto— se estrene en la
segunda visita, cuando el usuario ya se fue y volvió.

Una segunda copia en Seguimiento no tendría esa disciplina, o la tendría hoy y
la perdería en el primer arreglo que se aplique sólo a una. Es la clase de
duplicado que no falla al escribirlo y falla seis meses después.

## El panel

```
┌─────────────────────────────────────────────────────────┐
│  Mi cartera de dividendos          [ ▼ cambiar libro ]  │
│  USD · valorado al 2026-09-08 · 12 activos              │
├─────────────────────────────────────────────────────────┤
│   VALOR         APORTADO        GANANCIA      TWR ANUAL │
│   47.312,80     40.000,00       +7.312,80     +11,4%    │
├─────────────────────────────────────────────────────────┤
│  Composición                                            │
│  AAPL  ████████████▏  ¦          24,1%   (obj. 25,0%)   │
│  MSFT  ██████████▌ ¦             19,8%   (obj. 20,0%)   │
│  ...                                                    │
├─────────────────────────────────────────────────────────┤
│ [ Evolución ] [ Por activo ] [ Movimientos ] [ Noticias ]│
└─────────────────────────────────────────────────────────┘
```

**Cuatro cifras arriba, no seis.** TIR y Dividendos bajan a la pestaña «Por
activo», donde están sus detalles. Cuatro caben con holgura a 1024px y se leen
sin partir palabras; seis no.

**La marca del objetivo (`¦`) no se pinta cuando el libro no tiene objetivo.**
Un libro cargado a mano puede no tenerlo —J lo permite— y una marca en el cero
diría que el objetivo es cero.

## Fallos previstos

| Fallo | Qué hace el panel |
|---|---|
| Libro sin ningún día valorado | Ya resuelto en J: las cifras que dependen del precio salen «—». K lo conserva, y es lo primero que hay que comprobar después de mover la aritmética |
| Libro sin objetivo | La composición sale sin marcas, con una nota. No se inventa un objetivo igual al peso real |
| Un activo sin precio | Se nombra, como ya hace la tabla. No entra en la composición: su peso sería falso |
| Caché de noticias vacía | «No hay noticias descargadas todavía» y el botón. No un panel vacío sin explicación |
| Caché vieja | Se pinta **diciendo de cuándo es**. Es la regla que H ya aplica |
| Un ticker sin 8-K | Normal fuera de la SEC. Se dice, no se deja el hueco |
| Titular con `$` | Ya resuelto en H: Streamlit lee `$…$` como LaTeX y se come la línea. El escapado se mueve con el código, no se reescribe |

## Pruebas

Las tres vías de F, G, H y J, porque cada una caza una clase distinta.

El punto de apoyo de K es que **la aritmética pasa a ser importable**, así que
por primera vez se puede fijar con tests lo que hoy sólo está comentado:

- **El corte temporal.** Una aportación registrada hoy sobre una serie que acaba
  ayer **no** puede producir una ganancia negativa. Es el defecto de F, escrito
  como test por fin.
- **`None` no es cero** en todas las cifras que dependen del precio.
- **Los pesos de la composición suman 1** sobre los activos con precio, y los
  que no lo tienen quedan fuera y nombrados.
- **Sin objetivo no hay marca**, y no una marca en cero.
- **`traer` devuelve dataclases por los dos caminos** —caché y descarga—, que es
  el invariante que justifica sacarlo.
- **Las cifras antes y después de K coinciden**: se fija un libro de ejemplo y se
  comparan los números con los que la pantalla daba antes. Es la única prueba que
  detecta una regresión introducida al mover, y hay que escribirla **antes** de
  mover nada.

Y arrancar la app y recorrerla, que en las cuatro entregas anteriores fue lo
único que encontró los defectos de integración.

## Lo que K no resuelve

- **No cambia ninguna cifra.** Si algo sale distinto, es un defecto.
- **No añade métricas nuevas.** Ni volatilidad, ni drawdown, ni comparación
  contra un índice de mercado. Eso es otra decisión y no estaba en el encargo.
- **No interpreta las noticias.** Las enseña. Interpretarlas es I.
- **No descarga en segundo plano.** Streamlit no tiene un hilo donde hacerlo sin
  complicar el ciclo de ejecución, y el botón resuelve el caso real.
- **No deduplica la prensa.** Yahoo devuelve el mismo artículo bajo varios
  tickers y se verá repetido, igual que en la pantalla de Noticias. Es una deuda
  de H, anotada allí.
- **No toca Rebalanceo.** Sus medidores con veredicto se quedan donde están: es
  la pantalla de propuestas.
