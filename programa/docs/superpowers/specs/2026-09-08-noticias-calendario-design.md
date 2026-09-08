# Sub-proyecto H — Noticias y calendario

**Fecha:** 2026-09-08
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Una pantalla que responde dos preguntas que F y G no tocan: **qué ha pasado con
lo que tengo**, y **qué viene**.

F dice cuánto vale la cartera y G si hay que moverla. Ninguno de los dos sabe
que la empresa cambió de auditor la semana pasada ni que presenta resultados el
martes. H trae esos hechos y los pone donde se ven, **sin interpretarlos**: la
interpretación es el sub-proyecto I.

## Lo que ya existe y esto no repite

| Ya existe | H lo usa para |
|---|---|
| `seguimiento.posiciones.vigentes` | La lista de tickers del libro, que es toda la entrada |
| `edgartools>=5.52` (dependencia) | `Company.get_filings(form="8-K")` — expedientes de la SEC |
| `yfinance>=0.2.40` (dependencia) | `.news`, `.calendar` y `.earnings_dates` |
| La resolución ticker → CIK de `fundamentals/` | Encontrar la empresa en EDGAR |
| El patrón de caché de `ranking/.cache` y `fundamentals/.cache` | Frescura por fuente |
| El patrón «falta la clave, el resto sigue» de `ranking/llm.py` | Sin `EDGAR_IDENTITY` |

**H no añade ni una dependencia.** Se comprobó antes de diseñar, no se supuso.

## Lo que se sondeó antes de decidir nada

Contra las fuentes vivas, el 2026-09-08, y no contra la documentación:

| Fuente | Resultado | Contenido útil |
|---|---|---|
| `Ticker.news` | 10 elementos | `title`, `summary`, `description`, `pubDate`, `provider`, `canonicalUrl`. El más reciente era **del mismo día del sondeo**, con sello `15:29Z` |
| `Ticker.calendar` | dict | ex-dividendo, fecha de pago, próximos resultados, **y estimaciones de EPS e ingresos** |
| `Ticker.earnings_dates` | DataFrame | resultados pasados con EPS estimado, real y **la sorpresa en %** |
| `edgar.Company.get_filings` | 17 expedientes de AAPL en 20 meses | `to_pandas()` trae `form`, `filing_date`, `accession_number`, `primaryDocument` **y `items`** |

**El hallazgo que decide el coste del módulo: los items vienen en el índice.**
Una llamada por activo basta; no hay que abrir cada expediente para saber de qué
trata. `filing.obj().items` existe, pero descargaría el documento entero de cada
uno, y con quince activos eso convierte una pantalla en una espera.

Dos cosas más que el sondeo enseñó y que había que ver antes de codificar:

- **Un expediente lleva varios items**, en una cadena separada por comas:
  `"2.02,9.01"`. El 2.02 (resultados) viene con el 9.01 casi siempre.
- **`get_filings(form="8-K")` devuelve también los `8-K/A`**, las enmiendas.
  Entran —no se descarta nada— pero se marcan, porque enmendar un hecho no es
  lo mismo que comunicarlo.

Y el hueco, que es lo que forzó una decisión: **ninguna de las dos librerías da
el calendario macro.** Fed, IPC y empleo no están en yfinance ni en EDGAR.

## Decisiones tomadas

- **Del calendario macro se dan punteros, no fechas.** Copiar fechas al repo
  crea algo que caduca en silencio; un enlace roto se ve roto y una fecha vieja
  no. La autoridad se queda donde está.
- **Hechos y prensa van separados y etiquetados, nunca fundidos.** Un 8-K es
  algo que la empresa está legalmente obligada a comunicar; un titular es la
  copia de alguien. En el sondeo, el resumen de la primera noticia de AAPL era
  «Bring on the new iPhone!». Mezclarlos en una lista cronológica haría que lo
  segundo pareciera lo primero, que es justo lo que el programa evita en todas
  las demás pantallas.
- **No se descarta ningún expediente.** Los tipos de más peso salen desplegados
  y el resto queda plegado a un clic. Ordenar no es excluir: lo que H tirase, I
  no lo vería nunca.
- **El tiempo corre en su dirección natural.** Un bloque para lo que viene y
  otro para lo que pasó, en vez de una línea temporal donde un resultado
  estimado del mes que viene y un titular de ayer comparten fila.
- **H no interpreta.** Deja estructuras; I las lee.

## El criterio, congelado

`noticias/criterio.py` va **en su propio commit, antes de mirar los expedientes
de ninguna cartera real**, por la misma razón que `rebalanceo/criterio.py` y
`ranking/criterio.py`: la fecha del commit es la prueba de que la lista no se
armó a la vista de lo que había salido.

La regla que la genera, y que hay que poder defender sin ver datos: **son
materiales los tipos que invalidan o alteran los números sobre los que se
construyó la tesis.** La cartera sale de un análisis fundamental (A y B), así
que lo grave es lo que mueve esos fundamentales o dice que estaban mal.

| Tipo | Qué es | Por qué entra |
|---|---|---|
| 4.02 | Cuentas anteriores no fiables | La empresa declara que sus propias cifras estaban mal. Para una cartera construida sobre esas cifras, no hay nada peor |
| 4.01 | Cambio de auditor | Precede a un 4.02 con más frecuencia de la que sería cómodo |
| 1.03 | Concurso o quiebra | Fin de la tesis |
| 3.01 | Aviso de exclusión de cotización | Fin de la tesis por otra puerta |
| 2.06 | Deterioros materiales | Un activo del balance valía menos de lo contabilizado |
| 2.02 | Resultados | La actualización trimestral de los KPIs del ranking |
| 2.01 | Adquisición o venta de activos | Cambia la empresa que se analizó |
| 5.01 | Cambio de control | Íd. |
| 5.02 | Salidas en la directiva | Íd., y a veces es la primera señal de lo demás |
| 1.01 | Acuerdo material | Compromiso que el balance aún no refleja |
| 1.05 | Incidente material de ciberseguridad | Obligatorio desde 2023, y de impacto medible |

Fuera de la lista quedan, entre otros, el 7.01 (Regulation FD), el 8.01 (otros
eventos) y el 9.01 (estados y anexos). **No se descartan: se pliegan.**

## Arquitectura

Lógica sin Streamlit en `noticias/`, widgets sin lógica en `vistas/noticias.py`.
Misma separación que F y G.

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `noticias/prensa.py` | `.news` → `Noticia` | yfinance |
| `noticias/hechos.py` | 8-K → `Hecho` | edgartools, la resolución de CIK |
| `noticias/criterio.py` | La lista congelada de tipos materiales | nada |
| `noticias/agenda.py` | `.calendar` y `.earnings_dates` → `Evento` | yfinance |
| `noticias/macro.py` | Punteros a las fuentes oficiales | nada, son datos estáticos |
| `noticias/cache.py` | Frescura por fuente | nada |
| `vistas/noticias.py` | La pantalla | todo lo anterior |

`macro.py` y `criterio.py` no tienen dependencias a propósito: son los dos
ficheros que alguien va a querer leer para discutir el contenido, y deben poder
leerse solos.

### Las estructuras

```python
@dataclass(frozen=True)
class Noticia:
    ticker: str
    titular: str
    # De `summary`, y si viene vacío de `description`: el sondeo vio los dos
    # campos y no son sinónimos garantizados. Si faltan ambos, cadena vacía y
    # la pantalla enseña sólo el titular -- que ya dice algo.
    resumen: str
    medio: str
    url: str
    cuando: datetime

@dataclass(frozen=True)
class Hecho:
    ticker: str
    # Plural, y esto NO es un detalle de estilo. El indice de la SEC devuelve
    # los items en una sola cadena separada por comas -- "2.02,9.01" -- porque
    # un expediente puede comunicar varias cosas a la vez. Modelarlo como un
    # str y compararlo contra la lista congelada haria que "2.02,9.01" no
    # coincidiese con "2.02", y **todos los anuncios de resultados quedarian
    # clasificados como no materiales**, que es el caso mas frecuente que hay.
    # El 2.02 llega acompanado del 9.01 practicamente siempre.
    tipos: tuple[str, ...]
    descripciones: tuple[str, ...]   # una por tipo conocido, de criterio.py
    url: str
    cuando: date
    enmienda: bool       # el formulario venia como "8-K/A" y no como "8-K"
    material: bool       # True si ALGUNO de sus tipos esta en la lista

@dataclass(frozen=True)
class Evento:
    ticker: str | None   # None para lo macro
    clase: str           # "resultados" | "ex-dividendo" | "dividendo" | "macro"
    cuando: date | None  # None para lo macro: no tenemos la fecha, y se dice
    detalle: str
    url: str | None
```

`Evento.cuando` admite `None` **a propósito**, y es lo que hace que lo macro
quepa en la misma estructura sin mentir: de la Fed sabemos qué publica y dónde,
no cuándo. Un `date` inventado ahí sería exactamente el defecto que la decisión
de los punteros existe para evitar.

## Los punteros macro

Datos estáticos en `macro.py`. Cada entrada dice qué es, cada cuánto ocurre, por
qué mueve mercado, y a quién preguntarle la fecha.

| Evento | Cadencia | Fuente oficial |
|---|---|---|
| Reuniones del FOMC | Ocho al año | `federalreserve.gov/monetarypolicy/fomccalendars.htm` |
| IPC | Mensual | `bls.gov/schedule/news_release/` |
| Situación del empleo | Mensual | `bls.gov/schedule/news_release/` |
| PIB y PCE | Trimestral y mensual | `bea.gov/news/schedule` |

Son cuatro y no cuarenta a propósito: una lista larga de enlaces es una lista
que nadie abre.

## La frescura

Quince activos por tres fuentes son cuarenta y cinco llamadas de red, y
Streamlit re-ejecuta el script entero con cada clic en cualquier widget. Sin
caché la pantalla no es usable.

| Fuente | Validez | Por qué |
|---|---|---|
| Prensa | 1 hora | Cambia durante el día, pero no cada minuto |
| Hechos (8-K) | 1 hora | Se presentan en horario hábil, no en continuo |
| Calendario | 1 día | Una fecha de resultados no se mueve por la tarde |

Caché en `noticias/.cache/`, añadida a `programa/.gitignore` junto a las de
`ranking/` y `fundamentals/`. Un botón fuerza la descarga.

**La hora de descarga se muestra siempre**, no sólo cuando está vieja. Es la
misma regla que `coste_del_libro` en G: un dato que se lee como fresco sin serlo
es peor que no tener dato.

## Fallos previstos

| Fallo | Qué hace la pantalla |
|---|---|
| Falta `EDGAR_IDENTITY` | El bloque de hechos dice qué variable falta y cómo ponerla. **Prensa y calendario siguen funcionando.** Mismo patrón que el ranking sin `ANTHROPIC_API_KEY` |
| Un ticker no resuelve a CIK | Se nombra en el bloque de hechos. No se calla y no se cuenta como «sin noticias» |
| Sin conexión | Se muestra lo cacheado **marcado como viejo**, con su hora. Nunca en silencio |
| Una fuente cae y las otras no | Se dice cuál cayó y se pinta el resto. La pantalla no se va entera por una fuente |
| `.news` devuelve lista vacía | «Sin noticias recientes», que no es lo mismo que un fallo, y se distingue |
| Un campo que el sondeo vio y un día no viene | Se omite ese elemento nombrándolo, no se pinta con `None` ni con cadena vacía |
| El libro no tiene tickers | Se explica y se enlaza a Seguimiento, como hace Rebalanceo |

## Pruebas

Las tres vías que encontraron los veintidós defectos de F y G, porque cada una
caza una clase distinta:

1. **Sabotear cada guarda** y comprobar que algún test cae. Si sobrevive, el
   paso no es rehacer el sabotaje: es averiguar qué otra cosa está devolviendo
   la respuesta correcta.
2. **Sondear las hipótesis con scripts** antes de codificarlas.
3. **Arrancar la app y recorrerla.** Los cuatro peores defectos de F sólo
   aparecieron así, con la suite entera en verde.

**Fixtures grabados** de las respuestas reales de las tres fuentes, para que la
suite normal no toque la red. Más tests marcados `red` que contrastan los
fixtures contra las fuentes vivas — el mismo mecanismo con el que `ranking`
comprueba que el esquema de Anthropic sigue siendo el que el código usa. Un
fixture grabado protege del cambio de tu código; sólo el test `red` protege del
cambio del proveedor.

Casos que deben existir sí o sí:

- **Un expediente con varios items, `"2.02,9.01"`, tiene que salir material.**
  Es el caso más frecuente que existe y el que un modelo de un solo tipo
  clasificaría mal, dejando cada anuncio de resultados plegado entre la rutina.
- Uno con `"7.01,9.01"`, ningún tipo material, tiene que quedar plegado — para
  que el test anterior no pase por «todo lo que tenga dos items es material».
- Un `8-K/A` marcado como enmienda, y presente igual.
- Un 8-K de un tipo material y otro de uno plegado, y que **ninguno de los dos
  desaparece**.
- `Evento.cuando is None` para lo macro, y que la pantalla no lo ordena junto a
  las fechas reales.
- Caché caducada y caché vigente, con la hora mostrada en ambos casos.
- `EDGAR_IDENTITY` ausente con prensa y calendario intactos.

## Lo que H no resuelve

- **No da fechas macro**, sólo quién las publica. Es la decisión, no una carencia.
- **No guarda histórico.** La caché caduca y se pisa. Poder mirar atrás es otro
  almacenamiento y otra decisión.
- **No interpreta ni recomienda.** Eso es I, y H existe para darle de comer.
- **Una divisa y un mercado, US.** Un 8-K sólo existe para emisores registrados
  en la SEC; un ticker de otro mercado tendrá prensa y calendario, pero no
  hechos, y la pantalla lo dirá en vez de dejar el bloque vacío.
- **La prensa es la que Yahoo agrega**, con su relleno incluido. H no la filtra
  porque no tiene criterio defendible para hacerlo, y fingir uno sería peor.
