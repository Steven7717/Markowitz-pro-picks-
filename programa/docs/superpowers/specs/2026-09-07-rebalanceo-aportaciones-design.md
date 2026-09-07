# Sub-proyecto G — Rebalanceo y aportaciones

**Fecha:** 2026-09-07
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Una pantalla que responde una pregunta que F deja planteada y no contesta:
**¿hay que hacer algo, y qué?**

F muestra lo que pasó: cuánto tienes de cada activo, cuánto vale, cómo ha
rendido y qué peso ocupa frente al objetivo. G toma esa diferencia entre peso
real y peso objetivo y decide si merece una operación — mirando también lo que
esa operación cuesta.

## Lo que ya existe y esto no repite

| Ya existe | G lo usa para |
|---|---|
| `seguimiento.libro.pesos_objetivo` | Los pesos contra los que medir, ya resueltos según `base` |
| `seguimiento.posiciones.estado` | Las acciones y el efectivo sin asignar |
| `seguimiento.rendimiento.por_activo` | El valor actual de cada posición |
| `seguimiento.precios` | Los precios con los que valorar |
| `medidores.py` + `tema.py` | El **esqueleto visual** de la fila, no su escala |
| `cartera.formato_cifra` | La regla «—, nunca 0,00» |

**`medidores.py` presta la forma, no el vocabulario.** Está construido para
z-scores: `nivel()` mapea a *«muy por encima de sus pares»*, con cortes en ±0,5
y ±1,5 sobre una escala de ±3. Una deriva de cartera no compara con ningún par,
así que G define **su propia escala y sus propias palabras** sobre el mismo
esqueleto — barra, veredicto escrito además de en color, y el número al final.
Ese esqueleto vale la pena reutilizarlo tal cual: su comentario explica que el
veredicto va escrito *«porque un medidor que sólo cambia de tono no le dice nada
a quien no distingue el verde del rojo, ni a quien mira la página impresa en
blanco y negro»*.

## Dónde encaja

| # | Sub-proyecto | Entrega | Estado |
|---|---|---|---|
| F | Libro de posiciones y seguimiento | Valoración, rendimiento y referencias | ✅ terminado |
| G | Rebalanceo y aportaciones | Deriva, bandas, reparto del efectivo | **este documento** |
| H | Noticias y calendario | Feed de EDGAR, prensa, eventos | pendiente |
| I | Capa de IA sobre F, G y H | Interpretación y propuestas de ajuste | pendiente |

G depende de F por completo. H es independiente. I depende de los tres.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Criterio de rebalanceo | **Banda 5/25**, congelada en su propio commit | Cubre los dos extremos: para un objetivo del 40% manda la absoluta, para uno del 3% manda la relativa |
| Tope económico | No proponer una operación cuyo coste pase del **1% de su importe** | Sin ventaja demostrada en las señales (sub-proyecto D), operar de más es el único destructor de valor garantizado |
| Denominador del peso real | **Valor invertido**, sin el efectivo | Con el efectivo dentro, una aportación pondría todos los activos por debajo de su peso y el medidor entero se volvería rojo sin que hubiera deriva |
| Qué se propone | Primero el reparto del efectivo; las ventas sólo si con eso no basta | Repartir dinero nuevo corrige deriva sin vender: ni coste de venta ni plusvalía realizada |
| Activos fuera del objetivo | Se listan aparte, **sin recomendación** | Que algo no esté en el plan admite dos lecturas —plan viejo o posición sobrante— y el programa no puede distinguirlas |
| Coste de operar | Mediana de las comisiones **del propio libro** | Lo que este usuario pagó es mejor estimación que el supuesto de nadie |
| Escritura en el libro | **Ninguna.** G propone, el usuario registra en F | El libro registra lo que pasó en el bróker; si G escribiera, mezclaría hechos con intenciones sin forma de separarlos |
| Dónde vive | Pantalla propia, sección Cartera | Separa hechos de propuestas, y `vistas/seguimiento.py` ya son 440 líneas |
| Estructura | Paquete `rebalanceo/` más vista fina | Igual que `seguimiento/`, `aprobacion/` y `ranking/` |

## El criterio, congelado

`rebalanceo/criterio.py`, una veintena de líneas y nada más. Fichero propio por
el mismo motivo que `ranking/criterio.py`: **la fecha de su commit es la prueba
de que el umbral no se movió al ver los números.** Se congela antes de mirar
ninguna cartera real.

```python
BANDA_ABSOLUTA = 0.05    # 5 puntos porcentuales
BANDA_RELATIVA = 0.25    # 25% del peso objetivo
COSTE_MAXIMO = 0.01      # el coste no puede pasar del 1% del importe de la operación
```

Un activo está **fuera de banda** cuando se desvía 5 puntos absolutos **o** un
25% relativo de su peso objetivo, lo que ocurra primero.

Los dos umbrales existen porque ninguno funciona solo. Con sólo la banda
absoluta, un activo cuyo objetivo es el 3% tendría que llegar al 8% —casi
triplicarse— para disparar, así que en la práctica nunca se rebalancearía. Con
sólo la relativa, un activo del 40% dispara al llegar al 50%, que en una cartera
concentrada puede ser una oscilación de dos semanas.

`COSTE_MAXIMO` es lo que hace el criterio económico y no sólo geométrico: **si
mover 20 dólares cuesta 5, la operación no se propone**, por muy fuera de banda
que esté el activo.

## Arquitectura

```
                    ┌─→ rebalanceo.deriva ──┐   (la banda)
rebalanceo.criterio ┤                       │
                    └─────────────────┐     │   (el tope de coste)
                                      ▼     ▼
seguimiento/ (de F) ──→ rebalanceo.reparto, coste ──→ rebalanceo.propuesta ──→ vistas/rebalanceo.py
```

Paquete nuevo `programa/rebalanceo/`:

- **`criterio.py`** — la banda y el tope. Congelado, sin lógica.
- **`deriva.py`** — pesos reales frente a objetivo, y qué está fuera de banda.
- **`reparto.py`** — cómo se reparte el efectivo disponible.
- **`coste.py`** — qué cuesta operar, sacado de las comisiones del libro.
- **`propuesta.py`** — junta todo: qué comprar, qué vender, y a qué coste.

Ninguno importa Streamlit. La vista es `programa/vistas/rebalanceo.py`, y entra
en la sección **Cartera** de `st.navigation`, justo después de «Seguimiento».

## Los cálculos

### La deriva

Sobre el valor invertido `V = Σ vᵢ`, **sin contar el efectivo**:

```
desvᵢ = vᵢ/V − wᵢ
fuera de banda  ⟺  |desvᵢ| ≥ 0,05   o   |desvᵢ| ≥ 0,25 · wᵢ
```

**El efectivo queda fuera del denominador a propósito.** Si entrara, meter
10.000 en una cartera de 10.000 pondría todos los activos al 50% de su peso
objetivo y el medidor entero se volvería rojo — por una aportación que aún no
se ha invertido, no por deriva. La deriva mide la **mezcla**; el efectivo se
trata aparte, como lo que hay por asignar.

Los activos con `wᵢ = 0` no pasan por la prueba: la banda relativa valdría cero
y cualquier tenencia dispararía. Van al bloque «fuera del objetivo».

### El reparto del efectivo, que sale sin ramas

Con efectivo `C`, al activo `i` le tocaría `(V+C)·wᵢ` una vez invertido todo, y
su déficit es `dᵢ = max(0, (V+C)·wᵢ − vᵢ)`.

Hay una identidad que conviene ver, porque es lo que evita un caso especial:

```
Σ [(V+C)·wᵢ − vᵢ]  =  (V+C)·1 − V  =  C
```

Las diferencias **con signo** suman exactamente el efectivo. Los déficits son
sólo las positivas, así que **siempre suman C o más**, con igualdad únicamente
cuando ningún activo está sobreponderado. Nunca sobra dinero por repartir, y la
asignación es una sola fórmula:

```
asignaciónᵢ = C · dᵢ / Σd
```

Que es exactamente «comprar lo más infraponderado, en proporción». Sin ramas y
sin sobrante que colocar.

### Si con la aportación no basta

Se recalcula la deriva tras el reparto. **Si todo vuelve a banda, se dice que no
hace falta vender nada** — ese es el resultado bueno y merece decirse en voz
alta, no deducirse de una lista vacía.

Si no basta, segundo bloque: llevar cada activo fuera de banda a `(V+C)·wᵢ`.
Esas operaciones suman cero por construcción, o sea que se autofinancian.

Cada una se filtra por `COSTE_MAXIMO`. La que no pasa **se muestra igualmente,
diciendo que su coste se come el beneficio**, en vez de desaparecer sin
explicación: una propuesta que se omite en silencio es indistinguible de una que
nadie calculó.

### El tope también se aplica al reparto de la aportación

Y ahí no basta con descartar: el dinero tiene que ir a alguna parte. Una
asignación por debajo del tope se retira **y su importe se reparte entre las que
sí lo pasan**, en la misma proporción, repitiendo hasta que ninguna quede por
debajo. Si al final no queda ninguna, el mensaje es que **la aportación es
demasiado pequeña para que valga la pena invertirla ahora** — que es una
respuesta útil, y bastante mejor que proponer cuatro compras de tres dólares.

### El coste, y un detalle fácil de equivocar

Mediana de la `comision` de las compras y ventas registradas en el libro.

**Los ceros cuentan.** Si el bróker no cobra comisión y así se registró, la
estimación correcta es cero — filtrar los ceros «para quedarse con datos reales»
convertiría un dato en la ausencia de un dato, y haría que un usuario sin
comisiones viera operaciones bloqueadas por un coste que no paga.

Sólo cuando no hay **ninguna** compra ni venta registrada se usa un valor
declarado, marcado en pantalla como supuesto y no como medido.

Limitación que se dice en pantalla: G sólo conoce lo que se le contó. La
horquilla de compraventa no está registrada en ninguna parte y no entra en la
estimación.

## La pantalla

`programa/vistas/rebalanceo.py`, sólo widgets:

1. Selector de libro, reutilizando `libro.listar()`.
2. Veredicto de una línea: si hace falta rebalancear, con la fecha del objetivo
   vigente y cuánto lleva siéndolo.
3. Medidores de deriva, uno por activo, ordenados por desviación.
4. **«Con tu efectivo»** — qué comprar y de cuánto, si hay efectivo sin asignar.
5. **«Y además haría falta»** — las ventas y compras, sólo si tras el reparto
   sigue habiendo algo fuera de banda.
6. **«Fuera del objetivo»** — los activos con peso objetivo cero, sin
   recomendación.
7. El coste total, y de dónde salió la estimación.

Un libro **sin objetivo** tiene su propia pantalla: ofrece asignarle 1/N sobre
sus tickers o mandar al optimizador. No es un error, es un estado.

## Fallos previstos

| Situación | Qué hace |
|---|---|
| Libro sin objetivo | Pantalla propia con las dos salidas. No es un error |
| Libro sin posiciones, todo efectivo | No hay deriva que medir; se ofrece el reparto inicial contra el objetivo |
| Un activo del objetivo nunca comprado | Déficit completo, se propone comprarlo. Es correcto |
| Un activo sin precio | Se excluye del cálculo **y se dice**: si no, la deriva de los demás saldría sobre un total incompleto sin que nada lo indicara |
| Pesos objetivo que no suman 1 | Se normalizan con aviso. Puede pasar si el equal-weight se calculó sobre tickers que luego no tenían datos |
| `V = 0` con posiciones | Imposible salvo que todos los precios fallen; se trata como «sin precios» y no como división por cero |

## Pruebas

- **Control negativo.** Una cartera exactamente en su objetivo da deriva cero,
  nada fuera de banda y **ninguna propuesta**. Si propone algo, está mal, y este
  test lo dice sin ambigüedad.
- **La identidad de los déficits.** Sobre casos generados con
  `pytest.mark.parametrize`, `Σd ≥ C` siempre. Es la propiedad que sostiene la
  fórmula sin ramas, así que se comprueba en vez de asumirse.
- **El reparto no aleja a nadie** de su objetivo, y con efectivo suficiente los
  deja exactamente en él.
- **Las ventas y compras suman cero**, con tolerancia de redondeo. El test la
  fija él mismo en vez de importar el `_POLVO` de `seguimiento.posiciones`:
  meter la mano en el privado de otro paquete ataría los dos umbrales sin que
  nadie lo hubiera decidido.
- **Fronteras de la banda.** Con objetivo 40% manda la absoluta: dispara en 45%
  y no en 44,9%. Con objetivo 3% manda la relativa: dispara en 3,75%. Cada uno
  con su caso justo por debajo, para que el test falle si alguien cambia un
  `>=` por un `>`.
- **El tope de coste muerde.** Una operación de 20 con coste 5 no se propone, y
  aparece en la lista de descartadas con su motivo.
- **El coste con ceros.** Un libro cuyas comisiones son todas cero estima cero,
  no el valor declarado. Es el caso que un filtro «quédate con lo que no sea
  cero» rompería en silencio.
- **El efectivo fuera del denominador.** Una cartera en su objetivo exacto más
  una aportación sin invertir sigue dando deriva cero. Si el efectivo entrara
  en el denominador, este test fallaría con todos los activos infraponderados.

## Lo que G no resuelve

- **No dice cuándo volver a optimizar.** El objetivo se congela el día que se
  crea el libro y G mide contra él. Que un objetivo de hace un año siga siendo
  el bueno es una pregunta distinta, y responderla exigiría comparar
  optimizaciones, no pesos.
- **No ejecuta.** Propone; el usuario registra en F lo que de verdad hizo en el
  bróker.
- **No sabe de impuestos.** Una venta puede realizar una plusvalía con coste
  fiscal que G no ve. Por eso el reparto del efectivo va primero: es la vía que
  no genera ninguna.
- **No conoce la horquilla de compraventa.** Sólo las comisiones que el usuario
  registró.
- **Una divisa, USD**, heredado de F.
