# Plan — Sub-proyecto K, el panel de seguimiento

**Diseño:** `docs/superpowers/specs/2026-09-09-panel-de-seguimiento-design.md`
**Rama:** `panel-de-seguimiento`
**Punto de partida:** `10a9db9`, suite en **1.115 pasando**, 4 omitidos, 8 deseleccionados

## Cómo se ejecuta

Una tarea por commit. Cada tarea deja la suite en verde antes de pasar a la
siguiente. Todos los comandos se ejecutan **desde `programa/`** y llevan
`UV_LINK_MODE=copy` delante:

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

Sin esa variable `uv` intenta enlazar duro, el repo vive en OneDrive y `pyarrow`
revienta con `os error 396`.

## El orden no es negociable

Las tareas 1 y 2 **sacan aritmética que hoy no tiene tests**. Si la vista se
rehace antes, lo que se saque será lo que haya quedado, no lo que hay. Ver la
sección «La tensión» del diseño: dentro de esa aritmética está el corte temporal
común de `aportado` y `valor`, que en F produjo `GANANCIA −9.700` sin que nadie
perdiera un dólar.

## La cifra de referencia, para comprobar que no se movió nada

Antes de tocar nada, el libro de pruebas de doce activos daba **estas seis
cifras** (medidas en la app el 2026-09-09, con `libros/2026-07-10-090000-mi-cartera-de-dividendos.json`):

| | |
|---|---|
| VALOR | 51,434.74 |
| APORTADO NETO | 40,000.00 |
| GANANCIA | 11,434.74 |
| TWR ANUAL | 19.71% |
| TIR | 350.18% |
| DIVIDENDOS | 60.59 |

**No las claves en un test**: dependen de precios que se descargan y se mueven.
Sirven para lo otro — mirar la pantalla antes de la tarea 1, apuntar lo que da,
y comprobar después de la tarea 2 que da lo mismo. `@st.cache_data(ttl=3600)`
mantiene los precios quietos una hora, así que el antes y el después tienen que
hacerse en la misma sesión.

El libro se crea con:

```bash
cd programa && PYTHONPATH=. UV_LINK_MODE=copy uv run python - <<'EOF'
# (el script está en la tarea 1, paso 1)
EOF
```

---

## Tarea 1 — `seguimiento/panel.py`: las cifras de cabecera

**Commit:** `refactor: las cifras de cabecera salen de la vista, con sus tests`

Mover, **sin cambiar ni una operación**, el bloque `vistas/seguimiento.py:275-340`
a un módulo importable, y escribir por fin los tests de lo que sólo estaba
comentado.

### Paso 1 — el libro de pruebas

Crear `libros/` con un libro de doce activos comprados el 2026-07-10. Guardar el
script en el scratchpad, no en el repo (`libros/` está en `.gitignore`, línea 15).

```python
from seguimiento import libro as mod

TICKERS = [
    ("AAPL", 220.0, 12), ("MSFT", 420.0, 6), ("NVDA", 130.0, 18),
    ("GOOGL", 165.0, 14), ("AMZN", 185.0, 12), ("META", 520.0, 4),
    ("JPM", 215.0, 10), ("V", 275.0, 8), ("JNJ", 155.0, 12),
    ("PG", 170.0, 10), ("XOM", 115.0, 16), ("KO", 70.0, 25),
]
asientos = [mod.Asiento(id="ap", fecha="2026-07-10", tipo="aportacion",
                        importe=40000.0)]
for i, (t, precio, acciones) in enumerate(TICKERS):
    asientos.append(mod.Asiento(
        id=f"c{i}", fecha="2026-07-10", tipo="compra", ticker=t,
        acciones=float(acciones), precio=precio,
        importe=precio * acciones, comision=1.0,
    ))
total = sum(p * a for _, p, a in TICKERS)
l = mod.Libro(
    nombre="Mi cartera de dividendos", creado="2026-07-10T09:00:00",
    aportacion_prevista=mod.AportacionPrevista(500.0, "mensual"),
    objetivos=(mod.Objetivo(
        fecha="2026-07-10", base="estrategia",
        portafolio={"posiciones": [
            {"ticker": t, "peso": (p * a) / total} for t, p, a in TICKERS
        ]},
    ),),
    asientos=tuple(asientos),
)
print(mod.guardar(l))
```

### Paso 2 — apuntar el antes

Arrancar la app, abrir Seguimiento, y **apuntar las seis cifras**. Son la
referencia de la tarea 2. Si no coinciden con la tabla de arriba no pasa nada
—los precios se mueven de un día a otro—; lo que importa es que coincidan
consigo mismas antes y después.

### Paso 3 — `Cabecera`, con el corte temporal dentro

Crear `seguimiento/panel.py`. **Sin `import streamlit`.**

```python
"""Lo que la pantalla de seguimiento enseña, calculado fuera de la pantalla.

Este modulo existe por una razon concreta: hasta el sub-proyecto K, estas
cuentas vivian dentro de `vistas/seguimiento.py`, que es un guion de Streamlit
y **no se puede importar desde un test**. Las correcciones que tienen dentro
--el corte temporal comun, el «—» que no es un cero-- estaban protegidas solo
por un comentario. Un rediseno de la pantalla las habria borrado sin que nada
fallase, porque los numeros que saldrian serian plausibles.
"""

from dataclasses import dataclass


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
```

Y la función que la construye, con el cuerpo **copiado literalmente** de
`vistas/seguimiento.py:275-340`, incluidos sus comentarios:

```python
def cabecera(marcha, vivos, sin_valorar: bool) -> Cabecera:
    ...
```

`panel.py` importa lo que necesite del propio paquete —`from seguimiento import
libro as mod, rendimiento`—, que es la convención que `seguimiento/rendimiento.py`
ya sigue (`from seguimiento import posiciones`). `FLUJOS_EXTERNOS` se lee de
`mod`, no se pasa como parámetro.

**Los comentarios se copian, no se resumen.** El de las líneas 277-284 explica
por qué `aportado` sale de `marcha.flujos` y no de los asientos, y es la única
cosa que impide que alguien lo «arregle» de vuelta.

### Paso 4 — los tests que nunca existieron

Crear `tests/test_panel_cabecera.py`:

1. **El corte temporal.** Una serie de valor que acaba ayer, más una aportación
   registrada **hoy**. `ganancia` no puede salir negativa. Es el defecto de F,
   escrito como test por fin.
2. **`None` no es cero.** Con `sin_valorar=True`, `valor`, `ganancia`,
   `twr_anual` y `tir` son `None` — no `0.0`.
3. **`aportado` nunca es `None`.** Es un hecho registrado, no una medida. Con
   `sin_valorar=True` sale de los asientos y sigue siendo un número (el arreglo
   de J, ahora con test).
4. **Dividendos suma.**

### Paso 5 — la vista llama al módulo

Sustituir el bloque en `vistas/seguimiento.py` por la llamada. Las variables que
el resto del guion usa (`valor_hoy`, `aportado`, `twr_periodo`…) se leen de la
dataclass. **Nada más cambia en esta tarea.**

### Paso 6 — sabotaje

Romper el corte temporal: hacer que `aportado` sume los asientos en vez de
`marcha.flujos`. El test 1 tiene que caer. **Si no cae, el test no prueba lo que
dice** — averiguar qué otra cosa está devolviendo la respuesta correcta antes de
seguir.

### Paso 7 — suite

`1.115 + 4 = 1.119`.

---

## Tarea 2 — `panel.py`: composición y filas por activo

**Commit:** `refactor: la composicion y las filas por activo, tambien fuera`

### Paso 1 — `Composicion`

```python
@dataclass(frozen=True)
class Linea:
    ticker: str
    peso: float                  # sobre el total CON precio
    objetivo: "float | None"     # None cuando el libro no tiene objetivo
    valor: float


@dataclass(frozen=True)
class Composicion:
    lineas: "tuple[Linea, ...]"
    sin_precio: "tuple[str, ...]"
    hay_objetivo: bool
```

Reglas, todas del diseño:

- Los pesos se calculan **sobre el total de lo que tiene precio**. Un activo sin
  precio no entra: su peso sería falso.
- Los que no entran **vuelven nombrados** en `sin_precio`.
- Sin objetivo, `objetivo` es `None` en todas las líneas y `hay_objetivo` es
  `False`. **No se rellena con el peso real**: una marca encima de la barra diría
  que ya estás donde querías estar.

### Paso 2 — `filas_por_activo` y `filas_de_historial`

Mover `vistas/seguimiento.py:401-421` y `432-448`. Devuelven listas de
diccionarios, igual que ahora, porque `to_excel` los consume tal cual y esta
tarea no cambia la exportación.

### Paso 3 — tests

`tests/test_panel_composicion.py`:

1. **Los pesos suman 1** sobre los activos con precio.
2. **Un activo sin precio queda fuera y nombrado**, y los pesos de los demás
   siguen sumando 1 — no se quedan sumando 0,92.
3. **Sin objetivo no hay marca:** `hay_objetivo is False` y todas las
   `linea.objetivo is None`.
4. **Con objetivo, cada línea trae el suyo**, y un activo que está en el libro
   pero no en el objetivo trae `None` en vez de cero.

### Paso 4 — la vista llama, y se comprueba el antes/después

Sustituir los dos bloques. Después, **arrancar la app y comparar las seis cifras
con las del paso 2 de la tarea 1**. Tienen que ser idénticas. Si alguna cambió,
el defecto está en el movimiento y hay que encontrarlo antes de seguir: es
exactamente lo que estas dos tareas existen para impedir.

### Paso 5 — suite

`1.119 + 4 = 1.123`.

---

## Tarea 3 — `noticias/traer.py`

**Commit:** `refactor: el traer de noticias sale de la vista, para no copiarlo`

### Paso 1 — mover

Crear `noticias/traer.py` con `RAIZ_CACHE` (hoy en `vistas/noticias.py:30`),
`DESCARGA` (línea 37) y la función `_traer` (línea 78), renombrada a `traer` y
**con su docstring entero**: es el que explica el invariante del round-trip por
disco.

**`VALIDEZ` no se mueve.** Vive en `noticias/cache.py:20` y ya está en su sitio;
`traer` la lee como `cache.VALIDEZ[fuente]`, que es lo que `_traer` hace hoy.
Moverla dejaría dos sitios donde mirar cuánto dura una caché.

Añadir además la función que K necesita y la pantalla de noticias no tenía:

```python
def cacheado(fuente: str, ticker: str):
    """Lo que haya en cache, sin tocar la red. `None` si no hay nada.

    Es lo que hace que abrir Seguimiento no dependa de que la red responda.
    Devuelve `(datos, cuando, vigente)`: `vigente` dice si esta dentro de su
    ventana de validez, y **se devuelve en vez de filtrarse** porque una noticia
    vieja marcada como vieja es util y una ausencia silenciosa no.
    """
```

### Paso 2 — `vistas/noticias.py` pasa a llamarlo

Borrar la copia local. La pantalla tiene que seguir funcionando **igual**.

### Paso 3 — tests

`tests/test_noticias_traer.py`, con un `tmp_path` como raíz de caché:

1. **`cacheado` no toca la red.** Monkeypatch de `fuentes.prensa_de` a algo que
   lance; `cacheado` sobre una caché vacía devuelve `None` sin lanzar.
2. **`cacheado` marca lo viejo como viejo** en vez de esconderlo.
3. **Los dos caminos devuelven dataclases.** Descargar y luego releer de caché
   dan objetos del mismo tipo. Es el invariante que justifica el módulo.

### Paso 4 — comprobar la pantalla de noticias

Arrancarla. Tiene que traer lo mismo que antes. Un `refactor` que rompe la
pantalla que refactoriza no es un refactor.

### Paso 5 — suite

`1.123 + 3 = 1.126`.

---

## Tarea 4 — `medidores.barra_de_peso`

**Commit:** `feat: la barra de peso, con la marca del objetivo`

### Paso 1 — la función

En `medidores.py`, junto a los demás constructores de HTML:

```python
def barra_de_peso(ticker: str, peso: float, objetivo: "float | None",
                  escala: float) -> str:
    """Una fila de composicion: la barra es el peso, la marca es el objetivo.

    **Sin veredicto.** `vistas/rebalanceo.py` escribe «Sobreponderado» al lado
    de su barra y hace bien: es la pantalla de propuestas. Esta es la de hechos,
    y la misma barra con una palabra de juicio al lado convierte un dato en un
    consejo. La diferencia entre las dos pantallas es el motivo por el que son
    dos.

    `escala` es el peso mayor de la cartera, no 1.0: con doce activos ninguna
    barra pasaria del 25% del ancho y todas se verian igual de cortas.
    """
```

Usa `.mpp-fila`, `.mpp-pista` y `.mpp-tope`, que ya existen (`medidores.py:222`,
`233`, `244`). **La marca no se pinta cuando `objetivo is None`.**

### Paso 2 — tests

`tests/test_medidores_peso.py`:

1. **Sin objetivo no hay marca:** el HTML no contiene `mpp-tope`.
2. **Con objetivo, la marca va donde toca:** el `left:` es
   `objetivo / escala * 100`.
3. **El ticker se escapa.** Es texto que viene del libro.
4. **No aparece ninguna palabra de veredicto** —«sobreponderado»,
   «infraponderado»— en la salida. Es el test que impide que alguien «mejore» la
   función acercándola a la de Rebalanceo.

### Paso 3 — suite

`1.126 + 4 = 1.130`.

---

## Tarea 5 — el resumen del panel

**Commit:** `feat: seguimiento abre con lo que se mira, no con todo a la vez`

### Paso 1 — la identidad

El nombre del libro **grande**, con el selector al lado, y debajo una línea de
contexto: moneda, fecha de valoración, número de activos. Hoy el nombre sólo
aparece dentro del desplegable.

### Paso 2 — cuatro cifras

`st.columns(4)`: Valor, Aportado neto, Ganancia, TWR anual. TIR y Dividendos
bajan a la pestaña «Por activo».

Medido: a seis columnas la caja de texto son 50px y las seis cifras salen
recortadas (`51,…`); a cuatro caben nueve caracteres enteros.

### Paso 3 — la composición

`medidores.CSS` una vez, y una fila por activo con `barra_de_peso`. Los
`sin_precio` se nombran debajo. Si no hay objetivo, una nota lo dice y no hay
marcas.

### Paso 4 — comprobar a 1024px

Arrancar la app, poner la ventana a 1024px de ancho, y **comprobar que las
cuatro cifras se leen enteras**. Es el síntoma que abre el diseño; si sigue ahí,
la tarea no está hecha.

### Paso 5 — suite

Sin tests nuevos: es disposición. `1.130`.

---

## Tarea 6 — las pestañas

**Commit:** `feat: el detalle va en pestanas, y el resumen se queda arriba`

`st.tabs(["Evolución", "Por activo", "Movimientos", "Noticias"])`.

**No hay que estilarlas.** `st.tabs` ya se usa en `vistas/optimizador.py:414` y
`vistas/perfil.py:44`, y `tema.py:112-124` las tiene estilizadas —con el
comentario que explica por qué el gancho es `data-testid="stTab"` y no
`data-baseweb`, que Streamlit dejó de usar.

- **Evolución:** el gráfico y su pie, tal cual.
- **Por activo:** la tabla, más TIR y Dividendos, más el registro de operaciones
  (`_registrar_operacion`) y el botón de Excel.
- **Movimientos:** el historial.
- **Noticias:** vacía en esta tarea; la llena la 7.

**Cuidado con una cosa:** Streamlit ejecuta el contenido de **todas** las
pestañas en cada pasada, estén visibles o no. Nada de esto ahorra trabajo; lo
que ahorra es scroll. No escribir en el código que "se calcula sólo lo visible",
porque no es verdad.

Suite: `1.130`.

---

## Tarea 7 — la pestaña de noticias

**Commit:** `feat: las noticias del libro, sin salir del panel`

### Paso 1 — sólo caché

Para cada ticker del libro, `traer.cacheado("hechos", ticker)` y
`traer.cacheado("prensa", ticker)`. **Ninguna descarga.**

### Paso 2 — qué se pinta

- Los `Hecho` con `material=True`, primero, con su tipo y su enlace a EDGAR.
- Debajo, los titulares más recientes, pocos.
- El escapado de `$` **se importa**, no se reescribe: Streamlit lee `$…$` como
  LaTeX y un titular financiero va lleno de dólares.

### Paso 3 — los tres estados vacíos, distintos

| Estado | Qué se dice |
|---|---|
| Nada en caché | «No hay noticias descargadas todavía» + el botón |
| Hay, pero vieja | Se pinta, **diciendo de cuándo es** |
| Hay y está al día, pero este ticker no tiene 8-K | «Sin hechos recientes», que no es lo mismo que lo anterior |

Los tres son distintos y **decirlos igual sería mentir en dos de ellos**.

### Paso 4 — el botón

«Actualizar noticias» llama a `traer.traer` para lo que falte, con un spinner que
diga cuántos tickers van. Después, `st.rerun()`.

### Paso 5 — comprobar en la app

Con la caché vacía: la pestaña abre **al instante** y dice que no hay nada.
Pulsar el botón, esperar, y ver que aparecen. Volver a abrir: instantáneo.

### Paso 6 — suite

`1.130 + 2 = 1.132` (dos tests sobre qué estado corresponde a cada caso).

---

## Tarea 8 — CONTEXTO.md

**La hago yo, no un subagente.** Necesita los defectos y las decisiones que están
en la conversación, no en el código.

Marcar K terminado, añadir «Resultado del sub-proyecto K», actualizar el
encabezado y la cuenta de tests, y dejar escrito qué hereda I.

---

## Lo que NO hay que hacer

- **No cambiar ninguna cifra.** Si un número sale distinto después de K, es un
  defecto de K. No es una mejora aunque parezca más correcto: eso sería otra
  decisión, tomada de refilón.
- **No meter el veredicto de Rebalanceo en la composición.** Ver la tarea 4.
- **No descargar noticias al abrir.** Ver el diseño.
- **No tocar `exporter.py`.** El botón de Excel se mueve de sitio y nada más; la
  nota de `vistas/seguimiento.py:452-462` explica por qué `to_pdf` no vale aquí
  y sigue vigente.
- **No arreglar `tests/test_apagado.py`.** Es inestable, es anterior a K y tiene
  su propia tarea de fondo.
