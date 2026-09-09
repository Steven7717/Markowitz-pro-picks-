# Sub-proyecto J — La entrada al seguimiento

**Fecha:** 2026-09-08
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Que se pueda **llegar** al seguimiento y **empezarlo**, que hoy es donde el
recorrido se rompe.

El programa sabe elegir qué comprar (A–D), seguirlo (F), decidir cuándo tocarlo
(G) y traer sus noticias (H). Pero el camino de una cosa a la siguiente está
sin construir: la portada no menciona que exista la segunda mitad, los dos
botones que deberían encadenar pantallas escriben un mensaje pidiendo que uses
el menú, y un libro recién creado nace **vacío**, con el formulario para
registrar la primera compra plegado dentro de un desplegable, debajo de los
gráficos.

Esto no añade capacidades: hace utilizables las que ya hay.

## Los tres síntomas, medidos en el código

| Síntoma | Dónde está |
|---|---|
| La portada acaba en Optimización | `vistas/inicio.py` tiene tres pasos: Candidatos, Aprobación, Optimización. Seguimiento, Rebalanceo y Noticias no se nombran |
| «Aprobar y pasar al optimizador» no pasa al optimizador | `vistas/candidatos.py:355` escribe «para pasar al optimizador usa el enlace de la barra lateral». El mismo fichero ya usa `st.switch_page` dos veces, en las líneas 110 y 145 |
| Guardar un portafolio deja dos saltos por hacer | `vistas/optimizador.py:605` dice «está en Portafolios guardados»; desde allí hay que entrar y pulsar seguir |
| El alta crea un libro vacío | `vistas/seguimiento.py:57` crea el libro y hace `st.rerun()`. Las compras se registran en `st.expander("Registrar una operación")`, línea 120, una por una |

## La tensión que este diseño resuelve

«Sólo preguntar el capital a invertir» choca de frente con la regla sobre la
que se construyó F, y que el sub-proyecto G respeta al no escribir nunca en el
libro:

> El libro guarda **sólo hechos**. Mezclar hechos con intenciones los vuelve
> inseparables después.

Con 15.000 y un peso del 40%, escribir «compraste 27,27 acciones de AAPL a 220»
**no es un hecho: es una división**. La compra real fue de otro número de
acciones, a otro precio, con comisión, y puede que otro día. Una vez dentro del
libro esa cifra es indistinguible de una medida: contamina el coste de
adquisición, la TIR y el rendimiento, y nadie lo nota porque el número es
plausible.

**La resolución: el programa propone y el usuario confirma.** La lista de la
compra es una propuesta, como las de Rebalanceo. Lo que entra al libro es lo que
el usuario afirma que ejecutó, en una tabla editable, no un «sí, correcto». La
fricción de esa tabla **es la característica**, no un descuido: entre mirar la
propuesta y ejecutarla el precio se mueve, y ese hueco es exactamente donde se
colaría el número inventado.

## Decisiones tomadas

- **Se pregunta si ya compraste o vas a comprar.** Los dos casos son reales y
  ninguno debe fingir ser el otro.
- **Las fracciones de acción se soportan y se preguntan.** No siempre se puede
  comprar entero: con 500 de capital y una acción a 600 no hay ninguna acción
  entera que quepa. `Asiento.acciones` ya es un `float`, así que el modelo no
  cambia; lo que falta es preguntarlo y guardarlo.
- **Con acciones enteras, el sobrante se enseña.** No se reparte a ojo ni se
  esconde: queda como efectivo sin asignar en el libro, que es exactamente lo
  que es, y Rebalanceo ya sabe proponer dónde ponerlo.
- **Guardar un portafolio y empezar a seguirlo son actos distintos.** La acción
  principal pasa a ser «Guardar y empezar a seguirlo», pero se mantiene un
  «Guardar» a secas: se pueden archivar tres corridas y seguir una.
- **La aportación prevista se guarda como importe y cadencia.** Sigue siendo un
  plan: el libro sólo registra la aportación cuando ocurre de verdad.

  > **Corrección del 2026-09-09, al implementarlo.** Aquí decía «Rebalanceo
  > deja de preguntar cuánto vas a aportar», y era **falso**: Rebalanceo nunca
  > lo preguntó. Repartía `posiciones.estado(...).efectivo`, el dinero ya
  > registrado en el libro. Lo que se hizo en su lugar fue **añadir** un campo
  > que se precarga con el plan y se suma al efectivo, con las dos cifras a la
  > vista. Se deja escrito en vez de borrado: la frase pasó al plan sin que
  > nada chirriase, y ese es el defecto que hay que recordar.
- **Una cartera cargada a mano elige su objetivo, sin opción marcada:**
  mantener la mezcla de hoy, repartir por igual, o ninguno por ahora. Misma
  regla que la pregunta de pesos que ya existe — el programa no elige por ti
  algo que después usará para decirte que operes.
- **El alta vive en su propio fichero.** `vistas/seguimiento.py` ya tiene 440
  líneas y el sub-proyecto K lo va a rehacer entero. Meter el alta dentro sería
  construir sobre lo que está a punto de moverse.

## Arquitectura

| Fichero | Qué cambia |
|---|---|
| `seguimiento/alta.py` | **nuevo** — la lógica: reparto del capital, sobrante, y los asientos que se derivan de una tabla confirmada |
| `vistas/estrenar.py` | **nuevo** — la pantalla del alta, sin lógica |
| `seguimiento/libro.py` | dos campos nuevos y su lectura |
| `vistas/inicio.py` | el recorrido completo, en dos bloques |
| `vistas/candidatos.py` | `st.switch_page` en vez del aviso del menú |
| `vistas/optimizador.py` | «Guardar y empezar a seguirlo» |
| `vistas/seguimiento.py` | pierde el bloque de alta, que se va a `estrenar.py` |
| `app.py` | registra la pantalla nueva |

`alta.py` no importa Streamlit y `estrenar.py` no calcula nada, igual que en F,
G y H.

### Lo que se añade al libro

```python
@dataclass(frozen=True)
class AportacionPrevista:
    """El plan de aportar, que NO es un asiento de aportacion.

    El nombre lleva «prevista» a proposito: `Asiento.tipo == "aportacion"` ya
    existe y es un hecho ocurrido. Llamar `Aportacion` a las dos cosas invita
    justo a la confusion que todo F evita -- una es dinero que entro, la otra
    es dinero que el usuario dice que entrara.
    """
    importe: float
    cadencia: str      # "mensual" | "trimestral" | "anual"


@dataclass(frozen=True)
class Libro:
    ...
    # Si el broker admite fracciones. Decide si el reparto redondea hacia abajo
    # y deja sobrante, o si cuadra al centimo.
    fracciones: bool = False
    # El plan, no un hecho. Rebalanceo lo usa para no volver a preguntarlo.
    # None cuando el usuario dice que no hara aportaciones.
    aportacion_prevista: "AportacionPrevista | None" = None
```

**Los libros que ya existen siguen abriéndose.** `cargar` lee campo a campo con
`crudo.get(...)` —así entraron `moneda` y `objetivos`— así que un fichero sin
las claves nuevas toma los valores por defecto. Hay que añadir dos líneas a
`cargar`, no cambiar su forma.

## El reparto del capital

```
objetivo_i = capital · peso_i
acciones_i = objetivo_i / precio_i           (con fracciones)
acciones_i = floor(objetivo_i / precio_i)    (con acciones enteras)
gastado    = Σ acciones_i · precio_i
sobrante   = capital − gastado
```

Tres detalles que no son obvios:

- **Un peso pequeño y un precio alto dan cero acciones.** Con 1.000 de capital,
  un peso del 2% y una acción a 600, salen cero. Ese activo **se nombra**: sale
  en la tabla con cero y una nota diciendo por qué, en vez de desaparecer. Un
  activo que se cae del plan sin avisar es el defecto que ya costó una
  corrección en G.
- **Un activo sin precio no se reparte.** Se aparta y vuelve nombrado, como
  hace `rebalanceo.deriva`. Repartirle su parte a ciegas daría un número de
  acciones inventado.
- **El sobrante no se redistribuye.** Con acciones enteras siempre sobra algo, y
  repartirlo entre los demás rompería los pesos que el usuario acaba de elegir.
  Queda como efectivo, que es lo que es.

## Los dos caminos

Los dos terminan en **la misma tabla editable**, y esa tabla es la única cosa
que escribe en el libro.

**«Voy a comprar»** → capital y fracciones → la tabla propuesta, con precios de
hoy, el sobrante y los activos sin precio → *«Ya la ejecuté»* → la tabla
editable, precargada con la propuesta.

**«Ya compré»** → la tabla editable directamente, con los tickers del portafolio
puestos y una fecha común por defecto.

**«Ya tenía una cartera»** (carga manual) → la tabla editable vacía, donde el
usuario pone tickers, acciones, coste y fecha → más la pregunta del objetivo.

Columnas de la tabla: ticker, acciones, precio, comisión, fecha. Al confirmar se
escribe una `compra` por línea, más **una `aportacion` que las respalda**. El
sobrante no necesita asiento: es la resta, y `posiciones.estado` ya lo calcula.

**De dónde sale el importe de esa aportación, que no es lo mismo en los tres
caminos:**

- Viniendo del optimizador —las dos primeras puertas— es **el capital que el
  usuario declaró**. El sobrante de las acciones enteras queda dentro del libro
  como efectivo sin asignar, que es exactamente lo que es.
- En la carga manual **no hay capital declarado**, así que se deriva: la suma de
  las compras confirmadas más sus comisiones. El libro nace con cero efectivo
  sin asignar, que es lo honesto — nadie ha dicho que tenga dinero parado.

Quien tenga además efectivo sin invertir lo registra después como una aportación
más, desde el seguimiento. **No se pregunta aquí**, porque sería una cuarta
casilla en la puerta para un caso que no es el común, y equivocarla deja un
efectivo fantasma que después falsea la TIR.

## Fallos previstos

| Fallo | Qué hace la pantalla |
|---|---|
| Sin conexión al pedir precios de hoy | Se dice, y se ofrece el camino «ya compré», que no necesita precios |
| Un ticker sin precio | Se nombra en la tabla con las acciones en blanco; no se reparte a ciegas |
| El capital es cero o negativo | La tabla no se calcula y se explica por qué |
| La tabla confirmada suma más que la aportación | Se avisa antes de escribir: dejaría el efectivo en negativo, y `anadir` lo rechazaría después con un mensaje peor |
| Una fila sin ticker o sin acciones | Se omite esa fila nombrándola, no se escribe media compra |
| Dos filas con el mismo ticker | Se aceptan: comprar en dos tramos el mismo día es normal, y el coste medio ya lo resuelve |
| Se pulsa «Crear libro» dos veces | El segundo clic no debe crear un libro nuevo. Es el defecto que ya ocurrió en F, donde `guardar` no sobrescribe nunca y dos altas dejaron tres ficheros |

## Pruebas

Las tres vías de F, G y H, porque cada una caza una clase distinta: sabotear
cada guarda, sondear las hipótesis con scripts, y **arrancar la app y
recorrerla** — que en las tres entregas anteriores fue lo único que encontró los
defectos de integración.

Casos que deben existir:

- Capital repartido con fracciones: `Σ acciones·precio == capital`, al céntimo.
- Capital repartido con acciones enteras: el sobrante es **positivo y se
  informa**, y `Σ acciones·precio + sobrante == capital`.
- Un peso que da cero acciones: el activo **sale en la tabla**, con cero.
- Un activo sin precio: vuelve nombrado y no se le inventan acciones.
- Un libro sin los campos nuevos se abre igual, con los valores por defecto.
- Una tabla confirmada que gasta más que la aportación se rechaza **antes** de
  escribir nada.
- `st.switch_page` conserva `tickers_aprobados`: es la razón por la que el
  mensaje actual existía, y hay que probar que deja de hacer falta.

## Lo que J no resuelve

- **No rediseña el panel de seguimiento.** Eso es K, y por eso el alta sale a su
  propio fichero: para no construir encima de lo que va a moverse.
- **No ejecuta órdenes.** La lista de la compra es papel; comprar se compra en
  el bróker.
- **No sabe si tu bróker admite fracciones**: lo pregunta y te cree.
- **La aportación prevista no genera avisos ni fechas.** Es un importe y una
  cadencia que Rebalanceo usa para no preguntar. Meterla en el bloque «lo que
  viene» de Noticias mezclaría una previsión tuya con hechos de terceros, y eso
  es otra decisión.
- **Los precios de la propuesta son los del último cierre disponible**, no los
  de tiempo real. Entre mirarlos y ejecutar hay un hueco, y por eso la tabla de
  confirmación es editable.
