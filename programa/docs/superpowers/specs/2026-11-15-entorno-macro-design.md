# Entorno macro — la fase del ciclo y su inclinación del Top

**Fecha:** 2026-11-15
**Estado:** diseño aprobado, sin implementar
**Sub-proyecto:** O

## Qué entrega

Hoy el Top de candidatos no sabe en qué momento del ciclo económico estamos.
Ordena por calidad, crecimiento, valoración y solidez frente al propio sector, y
eso es todo. Este sub-proyecto añade dos cosas:

1. Una pantalla nueva, **«Entorno macro»**, que dice en qué fase del ciclo está
   una región: **EE. UU.** (por defecto), **México**, **Eurozona**, **China** o
   **Global (G7)**. También dice qué la sostiene y qué sectores favorece esa fase.
2. Una casilla en **Revisar candidatos**, *«Inclinar el Top por la fase macro»*,
   **apagada por defecto**. Encendida, sube en el Top las empresas de los
   sectores que la fase favorece y baja las de los que desfavorece. Si la fase
   favorece a Financieras y Consumo, esas empresas suben y las tecnológicas bajan.

La fase la decide **un algoritmo, sin IA**. La IA es una **lectura opcional y de
pago** en la pantalla macro: explica la fase en prosa y **no toca el Top**.

## La decisión central: una sola regla para todas las regiones

La fase sale del **indicador adelantado compuesto de la OCDE** (CLI, *Composite
Leading Indicator*, con ajuste de amplitud), leído en dos ejes:

| CLI | Subiendo | Bajando |
|---|---|---|
| **≥ 100** | Expansión | Desaceleración |
| **< 100** | Recuperación | Contracción |

Se descartaron dos alternativas:

- **Una puntuación con varios indicadores**: curva de tipos, desempleo, inflación
  y PMI. Es más rica para EE. UU., pero México y China no tienen las mismas
  series. «Expansión» significaría cosas distintas según la región que se elija.
- **El reloj de inversión** (crecimiento × inflación): duplica lo que hay que
  fechar, y su mapa a sectores es más discutible que el del ciclo.

El CLI se publica cada mes para las cinco regiones en la API SDMX de la OCDE,
que es gratis y no pide clave. Con la misma serie y la misma regla, la fase se
reproduce exactamente.

**Su punto débil, y hay que decirlo en pantalla:** el CLI llega con uno o dos
meses de retraso y puede dar giros en falso. La regla de dirección de abajo exige
que el giro se sostenga, y la pantalla siempre enseña el mes del dato.

## La región elige el ciclo, no el universo

El universo sigue siendo el S&P 500. Elegir México no rankea empresas de la BMV.
Lee el ciclo de México y con él reordena los sectores del S&P 500. La pregunta
que contesta es *«si manda el ciclo de X, ¿qué candidatos suben?»*. Rankear el
universo de otra región queda fuera de este sub-proyecto.

## Sobre la evidencia: inclina, no promete

El sub-proyecto D encontró que ninguna señal técnica tiene ventaja. La rotación
sectorial por ciclo tiene en la literatura una evidencia **floja**: el ciclo se
fecha bien a toro pasado y mal en tiempo real, que es justo lo que aquí se hace.
Por eso:

- La inclinación es **pequeña y acotada**. Una empresa excelente de un sector
  desfavorecido puede seguir entrando.
- Viene **apagada**. El Top de siempre sigue siendo el criterio congelado.
- La pantalla dice **qué entró y qué salió** del Top por la macro. Nunca afirma
  que eso mejore el rendimiento.
- Medir si aporta, con backtest y criterio preregistrado como en D, queda fuera
  de este sub-proyecto (ver «Fuera de esta entrega»).

## Arquitectura

```
macro/
├── __init__.py
├── criterio.py   datos congelados: regla de fase, mapa fase → sectores, inclinación
├── fuentes.py    CLI de la OCDE y series de FRED, con caché y fallos con nombre
├── fase.py       serie → fase; puro, sin red
└── lectura.py    la lectura con IA, con caché por región y mes del dato
vistas/macro.py   la pantalla «Entorno macro»; widgets, sin lógica
```

Cada unidad se entiende sola. `fase.py` no sabe de dónde viene la serie,
`fuentes.py` no sabe qué es una fase, y el ranking solo recibe una fase ya
decidida.

### `macro/criterio.py` — congelado antes de mirar resultados

Igual que `ranking/criterio.py`: va en un commit propio **antes** de escribir
`fase.py`, y para cambiarlo hace falta una enmienda fechada en este documento.

```python
NIVEL_NEUTRO = 100.0
MESES_DIRECCION = 3            # la dirección: signo de CLI[t] − CLI[t−3]
MAX_ANTIGUEDAD_MESES = 3       # dato más viejo que esto → no se inclina
INCLINACION = 0.25             # desviaciones que se suman o restan al compuesto

REGIONES = {                   # clave → (nombre en pantalla, área de referencia de la OCDE)
    "usa": ("Estados Unidos", "USA"),
    "mex": ("México", "MEX"),
    "eurozona": ("Eurozona", "EA20"),
    "china": ("China", "CHN"),
    "g7": ("Global (G7)", "G7"),
}
REGION_POR_DEFECTO = "usa"

SECTORES_POR_FASE = {          # nombres GICS exactos de fundamentals/data/sectores_*.csv
    "recuperacion": {
        "favorecidos": ("Financials", "Consumer Discretionary", "Industrials"),
        "desfavorecidos": ("Utilities", "Consumer Staples", "Health Care"),
    },
    "expansion": {
        "favorecidos": ("Information Technology", "Communication Services", "Industrials"),
        "desfavorecidos": ("Utilities", "Materials"),
    },
    "desaceleracion": {
        "favorecidos": ("Energy", "Materials", "Consumer Staples", "Health Care"),
        "desfavorecidos": ("Information Technology", "Consumer Discretionary"),
    },
    "contraccion": {
        "favorecidos": ("Consumer Staples", "Health Care", "Utilities"),
        "desfavorecidos": ("Industrials", "Information Technology", "Consumer Discretionary"),
    },
}
```

El mapa sigue la rotación sectorial clásica por fases del ciclo. Cada fila lleva
escrito al lado su porqué, en una línea. Por ejemplo, en recuperación las
Financieras ganan con la curva empinada y el crédito que vuelve, y el Consumo
discrecional gana con la renta que se recupera. Un sector que no aparece en una
fase se queda neutro (0). Un test comprueba que cada nombre existe en la tabla
GICS congelada: un sector mal escrito no inclinaría nada y no daría ningún error.

La clave interna (`recuperacion`) es el dato. El texto de pantalla
(«Recuperación») sale de un diccionario aparte y **nunca se guarda en disco**.
Es la lección de «La etiqueta de pantalla que se guardaba en disco» de
CONTEXTO.md.

### `macro/fase.py` — la regla, sin red

```python
@dataclass(frozen=True)
class Fase:
    clave: str | None        # recuperacion | expansion | desaceleracion | contraccion | None
    motivo: str | None       # None si hay fase; si no: indeterminada | serie_corta
    mes_dato: date | None    # el mes al que se refiere el último CLI
    nivel: float | None
    cambio: float | None     # CLI[t] − CLI[t−3]
    meses_en_fase: int       # cuántos meses seguidos lleva la regla dando esta fase

def determinar(serie: pd.Series) -> Fase
```

- **Nivel:** `CLI[t] ≥ NIVEL_NEUTRO`.
- **Dirección:** signo de `CLI[t] − CLI[t−MESES_DIRECCION]`. Si el cambio del
  último mes tiene el signo contrario, el giro no se sostiene y sale
  `motivo="indeterminada"`. Un cambio exactamente nulo también cuenta como
  indeterminado. No se elige un lado por defecto.
- **Menos de `MESES_DIRECCION + 1` datos:** `motivo="serie_corta"`.
- `meses_en_fase` se calcula aplicando la misma regla a cada mes anterior. No
  cambia la fase, pero la pantalla lo enseña: dos meses en una fase no pesan lo
  mismo que catorce.

`determinar` no mira la fecha de hoy. La antigüedad la juzga quien la usa (ver
«Cuándo no se inclina»), con la misma lógica que `_rezago_trimestres`, que mide
contra el panel y no contra el reloj.

### `macro/fuentes.py` — datos gratis, fallos con nombre

| Qué | De dónde | Clave |
|---|---|---|
| CLI de las cinco regiones | API SDMX de la OCDE (`sdmx.oecd.org`), flujo del CLI, ajuste de amplitud | ninguna |
| Curva 10a − 3m (EE. UU.) | FRED `T10Y3M`, `fredgraph.csv?id=…` | ninguna |
| Desempleo (EE. UU.), para la regla de Sahm | FRED `UNRATE` | ninguna |
| Inflación interanual (EE. UU.) | FRED `CPIAUCSL` | ninguna |

- Los identificadores exactos del flujo de la OCDE y de las áreas (`EA20`, `G7`,
  etc.) **se confirman contra la API real con un test `red` en la primera tarea
  del plan**, como se hizo con los ids de Banxico. Si alguno es distinto del que
  pone este documento, se corrige aquí con una enmienda fechada.
- La caché en disco sigue el patrón de `seguimiento/banxico.py`: guarda la
  respuesta con su fecha de descarga y caduca a las 24 h.
- Los fallos son un resultado y no una excepción: `sin_red`,
  `serie_desconocida` y `respuesta_ilegible`. Si la red falla pero hay caché, se
  devuelve la caché aunque esté caducada, **marcada como tal**.
- Las series de FRED son **solo contexto**: no entran en la fase. Se enseñan
  solo para EE. UU., y con otra región la pantalla dice que no hay contexto
  equivalente. No se omiten en silencio.

### El Top — `ranking/score.py` y `ranking/run.py`

```python
def inclinar(compuestos: pd.Series, sectores: pd.Series, fase: str) -> pd.Series
```

Suma `+INCLINACION` a las empresas de los sectores favorecidos y `−INCLINACION`
a las de los desfavorecidos. Al resto no les suma nada. Se aplica **después de
`compuesto` y antes de `seleccionar`**. Encaja limpio porque `compuesto` ya
re-estandariza dentro de cada sector: todos los sectores parten de media 0, así
que la inclinación es exactamente el desplazamiento de un sector frente a otro,
en desviaciones. `TOPE_POR_SECTOR` no cambia: la macro no puede llenar el Top
con un solo sector.

```python
def construir_ranking(..., macro: Fase | None = None, region: str | None = None)
```

- Con `macro=None` el resultado es **idéntico al de hoy**, y un test lo compara
  bit a bit contra el camino sin inclinación.
- Con fase, la selección se hace dos veces: una sin inclinar y otra inclinada.
  La diferencia entre las dos da `entradas_por_macro` y `salidas_por_macro`, que
  se guardan en la corrida. Es el mismo principio que las `desplazadas` por el
  tope: un criterio que reordena la lista tiene que dejarse ver.
- `corrida["macro"]` vale `None` o
  `{"region", "fase", "mes_dato", "inclinacion", "entradas", "salidas"}`. Son
  claves y datos, nunca texto de pantalla.
- Cada ficha lleva `ajuste_macro`, que vale `+0.25`, `-0.25` o `0`.
- La IA de las fichas (`con_llm`) no recibe la fase. La narrativa sigue
  describiendo los fundamentales, y la macro va aparte para no mezclar un juicio
  sobre la empresa con un juicio sobre el ciclo.

### Pantallas

**«Entorno macro»** (`vistas/macro.py`), en el menú junto a Analizador:

- Selector de región, con EE. UU. por defecto y la elección recordada en
  `preferencias.py`.
- La fase en grande, el mes del dato y cuántos meses lleva en ella.
- El gráfico del CLI de los últimos 5 años, con la línea de 100 y las fases
  coloreadas.
- Qué sectores favorece y desfavorece la fase, con el porqué de cada uno.
- Solo para EE. UU., el contexto: la curva 10a − 3m (si está invertida), la
  regla de Sahm (si está activada) y la inflación interanual.
- El aviso fijo sobre la evidencia, en una frase y no en letra pequeña.
- El botón **«Lectura con IA»**, con el coste a la vista y el tope de gasto de
  la capa de IA que ya existe. Le pasa a la IA la serie, la fase, los sectores y
  el contexto, y le pide que explique la fase y qué indicadores vigilar en los
  próximos meses. La lectura se guarda por `(región, mes_dato)`, así que repetir
  la pregunta en el mismo mes no vuelve a pagar. No toca el Top.

**Revisar candidatos:**

- Casilla *«Inclinar el Top por la fase macro»*, apagada por defecto y **no
  recordada** entre sesiones: activar el criterio no congelado tiene que ser
  siempre un gesto consciente. Debajo lleva un selector de región y una línea
  con la fase y el mes del dato que se usarían.
- Con la corrida hecha, un bloque «Lo que movió la macro» con las empresas que
  entraron y las que salieron.
- La ficha de cada candidato dice si la macro la subió, la bajó o no la tocó.

**Actas** (`vistas/actas.py`): la línea de la corrida añade «con macro: Fase
(Región, mes)» o «sin macro». Las actas viejas, que no tienen la clave, se leen
como «sin macro».

## Cuándo no se inclina

La casilla se desactiva, explica por qué y la corrida sigue **sin macro**, nunca
con una fase supuesta, en estos casos:

- La fuente no responde y no hay caché.
- La fase es `indeterminada` o `serie_corta`.
- El mes del dato tiene más de `MAX_ANTIGUEDAD_MESES` meses respecto a hoy.

La pantalla macro sí enseña la fase con un dato viejo, con el aviso de la fecha
bien visible. Lo que no hace es dejar que ese dato mueva el Top.

## Tests

- `fase.py`, con series sintéticas: las cuatro fases, el giro no sostenido
  (`indeterminada`), el cambio nulo, la serie corta, el borde exacto en 100 y
  `meses_en_fase`.
- `criterio.py`: cada sector del mapa existe en la tabla GICS, ningún sector
  está a la vez favorecido y desfavorecido en la misma fase, y cada fase tiene
  las dos listas.
- `inclinar`: el desplazamiento exacto por sector, los neutros en 0 y un NaN
  que sigue siendo NaN.
- `construir_ranking` sin macro es idéntico al de antes. Con macro, las
  entradas y salidas cuadran con las dos selecciones.
- `fuentes.py`, con respuestas grabadas: el parseo del SDMX y del CSV de FRED,
  cada fallo con su nombre y la caché caducada usada como respaldo.
- Que la corrida guardada no lleve texto de pantalla (la clave `fase` es una de
  las cuatro claves).
- `red`: los ids reales de la OCDE para las cinco regiones y los de FRED.

## Fuera de esta entrega

- **Medir si la inclinación aporta**: un estudio tipo D, con criterio
  preregistrado antes de medir, que también tendría que resolver el fechado
  histórico del CLI (las revisiones de la OCDE cambian el pasado).
- Rankear el universo de otra región (la BMV, por ejemplo).
- Que el Analizador individual diga si la fase favorece el sector del ticker
  analizado. Es un añadido pequeño y natural una vez exista `macro/`, pero toca
  N3, que está en curso.
- Que la IA pueda proponer otra fase distinta de la del algoritmo.

---

## Enmienda del 2026-11-16 — lo que dijo la API real, y tres precisiones del plan

**Manda sobre el texto de arriba donde se contradigan.**

1. **La Eurozona es `G4E`, no `EA20`.** El flujo del CLI de la OCDE no tiene
   área `EA20` (comprobado el 2026-11-16 listando todas las áreas con dato en
   agosto de 2026). La más cercana es `G4E`: Alemania, Francia, Italia y España,
   las cuatro grandes de la zona. En pantalla se llama «Eurozona (4 grandes)»,
   para que nadie lea en ella a la zona entera. La clave del flujo es
   `OECD.SDD.STES,DSD_STES@DF_CLI` con `{area}.M.LI...AA...H`.
2. **Dos unidades más en `macro/`:** `contexto.py` (curva, Sahm e inflación a
   partir de las series de FRED; puro) y `estado.py` (une fuente, fase y
   vigencia en lo que leen las dos vistas). Y `textos.py` para todo lo de
   pantalla, de modo que `criterio.py` se queda en datos.
3. **El compuesto de la ficha es el SIN inclinar.** `ficha["compuesto"]` sigue
   siendo el de siempre y la inclinación va aparte en `ficha["ajuste_macro"]`.
   Si no, la tarjeta enseñaría un número que mezcla dos juicios sin decirlo.
4. **Un cambio nulo del último mes no contradice.** Solo hay `indeterminada`
   cuando el cambio a 3 meses es exactamente 0 o cuando el del último mes tiene
   signo **contrario**. Un último mes plano no desmiente nada.
5. **La pantalla es `vistas/entorno_macro.py`, no `vistas/macro.py`.** Así el
   nombre de la página no puede tapar al paquete `macro`.
6. **Los huecos no se saltan.** La serie se lee en meses de calendario: si falta t, t−1 o t−3, no hay fase y el motivo es `serie_con_huecos`. Comparar por posición habría convertido «hace tres meses» en «hace cuatro» sin decirlo.
7. **La casilla no se desactiva: avisa.** En «Cuándo no se inclina» el spec decía que la casilla de Revisar candidatos «se desactiva». En el código sigue marcable y, si la fase no puede inclinar, enseña el motivo y avisa de que la corrida saldrá sin macro. Un aviso explica más que una casilla gris (dice *por qué* no se inclina), y el resultado es el mismo: como no se pasa la fase a la corrida, sale sin macro igual.
