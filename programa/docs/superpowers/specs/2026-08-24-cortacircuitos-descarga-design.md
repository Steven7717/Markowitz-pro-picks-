# Cortacircuitos de descarga — distinguir el ticker que falla de la fuente que no está

**Fecha:** 2026-08-24
**Estado:** implementado y en la rama `claude/friendly-albattani-1f4065`
(commits `f1d57fc`..`HEAD`). Este documento se corrigió varias veces durante
la implementación, cuando las revisiones encontraron que afirmaba cosas
falsas sobre la librería; lo que dice ahora es lo que se construyó.

## Qué entrega

Que una corrida condenada se rinda en segundos diciendo por qué, en vez de
gastar ~25 minutos mostrando «Generando candidatos… no cierres ni recargues»
para acabar sin nada y sin explicación.

Tres mecanismos que cubren conjuntos disjuntos de causas:

1. **Clasificar** el fallo en vez de tratar toda excepción igual. Lo que ya es
   inequívocamente global la primera vez que se ve (429, identidad rechazada,
   SSL) aborta en el primer ticker.
2. **Cortacircuitos** para lo que sólo se vuelve inequívoco por repetición
   (5xx, timeouts, connect errors): N fallos seguidos sin respuesta de la SEC,
   o un tope de tiempo sin respuesta.
3. **Dejar de reintentar** por nuestra cuenta lo que la capa de abajo ya
   reintenta mejor, o lo que no mejora reintentando.

## Qué NO entrega

**No hay suelo de cobertura general.** La pregunta «¿vale un ranking construido
con 200 de 503 empresas cuando cada una falló por su cuenta?» es adyacente pero
distinta: aquí sólo se decide qué pasa cuando fallan *todas por la misma causa*.
Un suelo proporcional exigiría elegir un porcentaje y defenderlo contra casos
reales, y es un diseño aparte.

**No se toca `research/loader.py`.** Tiene su propio `max_retries` sobre lotes
de yfinance: otro módulo, otra fuente, otro problema.

## De dónde salen los 25 minutos

Medido leyendo el camino real en **edgartools 5.52.0**, que es la versión que
fija `uv.lock` y la que corre en el venv. (Una primera lectura se hizo contra la
5.47.0 que hay instalada en el sistema; las constantes de reintento y la
estructura son idénticas en las dos, así que esta medición vale para ambas. La
taxonomía de excepciones **no**: ver la sección siguiente.)

`download_file` **no** está decorada con `@retry`, e `inspect_response` —la que
levanta `HTTPStatusError` para cualquier respuesta que no sea 200 o 304— corre
*fuera* del decorador de `get_with_retry`. Consecuencia: stamina no reintenta ni
un 403 ni un 5xx. Sólo reintenta errores de transporte, y ahí hace 5 intentos
con backoff 1-2-4-8 s.

| Causa | Peticiones por ticker | Qué domina el tiempo |
|---|---:|---|
| 403 (identidad rechazada) | 3 | **Nuestros `time.sleep`: 1 s + 2 s por ticker** |
| 5xx | 3 | Igual |
| Sin red / timeout | 15 (5 de stamina × 3 nuestros) | stamina, ~15 s de backoff |
| SEC colgada (read timeout 30 s) | 15 | 5 × 30 s por intento nuestro ≈ 8 min/ticker |

El caso que se midió —identidad presente que EDGAR rechaza— son 503 tickers ×
3 s de esperas nuestras = 25 minutos, más ~63 s de peticiones al tope de 8/s.
**Los 25 minutos son casi enteramente nuestros `time.sleep(2.0**intento)`.**

De ahí que quitar `max_retries` no sea una optimización menor: por sí sola lleva
ese caso de ~28 min a ~1 min, y con el cortacircuitos a un solo ticker.

## Los otros dos defectos que aparecieron por el camino

**El 429 es el caso donde reintentar hace daño activo.** `TooManyRequestsError`
no está en `RETRYABLE_EXCEPTIONS` de edgartools: falla rápido a propósito, y su
propio mensaje avisa de que el bloqueo de IP dura ~10 min y de que seguir
pidiendo **lo alarga**. Nuestro bucle lo reintenta 3× por ticker × 503 tickers.
Hoy, ante un 429, la app prolonga el bloqueo que causó el fallo.

**Un 404 legítimo llega disfrazado de caída de red.** edgartools distingue la
empresa que no tiene *company facts* (`CompanyFactsNotFoundError`), pero
`Entity.get_facts()` la atrapa y devuelve `None`, y `_fetch_facts` hace
`company.get_facts().to_dataframe()` sin mirar. Con `None` eso es un
`AttributeError`, que cae en el `except Exception` genérico, **se reintenta tres
veces con esperas** y acaba archivado como `failed_download`. Una condición
permanente, por-ticker y perfectamente diagnosticada río abajo llega a
`CoverageReport` contada como fallo de descarga.

## La taxonomía la pone edgartools, no nosotros

La 5.52.0 trae `edgar.exceptions`, un módulo que no existía en la 5.47.0 y que
resuelve casi todo lo que este diseño iba a construir a mano:

```
EdgarError
├── TransportError
│   ├── TooManyRequestsError      429: bloqueo de IP
│   ├── SSLVerificationError      certificado (vive en edgar.httprequests)
│   └── IdentityError
│       ├── IdentityNotSetError   no hay identidad configurada (lo vemos nosotros)
│       └── SECIdentityError      la SEC rechazó la identidad (nos lo dice ella)
├── NotFoundError  (LookupError)
│   ├── CompanyNotFoundError          sin CIK
│   └── CompanyFactsNotFoundError     la CIK existe y no tiene facts
├── ParsingError
└── ValidationError
```

Tres consecuencias sobre lo que se pensaba hacer:

- **No hace falta inventar una excepción `SinHechos`.** `CompanyFactsNotFoundError`
  ya existe; `_fetch_facts` sólo tiene que volver a levantarla cuando
  `get_facts()` devuelva `None`.
- **No hace falta olfatear el código 403** para detectar la identidad rechazada.
  `SECIdentityError` tiene nombre propio, y su docstring dice que comparte padre
  con `IdentityNotSetError` justamente para que un solo `except IdentityError`
  atrape las dos: misma causa raíz, mismo arreglo.
- **`http_status(exc)` da el código HTTP o `None`**, y su docstring llama a ese
  `None` «el discriminador entre *la SEC dijo que no* y *no pudimos preguntar*».
  Es literalmente la distinción sobre la que gira el cortacircuitos.

**No se activa `EDGARTOOLS_STRICT_ERRORS`.** Existe y adelanta el comportamiento
de la 6.0, pero cambiaría también los `None` de `ranking/filings.py:_descargar`,
que hoy son parte de su contrato deliberado. Y no hace falta: `TRANSPORT_ERRORS`
en la 5.52.0 es `(HTTPError, TransportError)`, así que atrapar esa tupla cubre
las dos eras sin tocar ningún interruptor global.

Nota de nombres: `IdentityNotSetException` (el nombre viejo, en
`edgar.httprequests`) está deprecado y desaparece en la 6.0. Se usa
`IdentityNotSetError` de `edgar.exceptions`.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Cómo sale la decisión de abortar | Excepción dedicada, `CorridaAbortada` | Un campo en `CoverageReport` obliga a cada consumidor a acordarse de mirarlo, y olvidarlo produce el resultado a medias silencioso que este proyecto rechaza |
| Eje de clasificación | La jerarquía de `edgar.exceptions` (5.52.0) | Ya distingue exactamente lo que hace falta distinguir, con nombres propios: `SECIdentityError`, `CompanyFactsNotFoundError`, `IdentityError`. Clasificar por tipo en vez de por código HTTP evita olfatear respuestas |
| `EDGARTOOLS_STRICT_ERRORS` | No se activa | Cambiaría también los `None` de `ranking/filings.py:_descargar`, que son contrato deliberado. Y no hace falta: `TRANSPORT_ERRORS` es `(HTTPError, TransportError)` y cubre las dos eras |
| Dónde vive la taxonomía | Módulo nuevo `fundamentals/fallos.py` | Es una tabla de decisiones sin red ni pandas, se prueba renglón por renglón; `fetch.py` ya carga con identidad, descarga, caché y cobertura |
| Nuestro `max_retries` | Se quita | Dos capas de reintento con políticas distintas es lo que causó esto, y la de abajo está mejor informada: sabe qué NO reintentar |
| Disparador del cortacircuitos | Racha de N seguidos, en cualquier punto de la corrida | Que la SEC se caiga en el ticker 300 produce el mismo resultado inútil que caerse en el primero; «los N primeros» no lo ve |
| N | 10 | «Seguidas» se cuenta entre los tickers que tocan la red, no entre las posiciones del universo: un acierto de caché no rompe la racha. Lo que topa esta constante no es el 2 % del índice sino el número de empresas permanentemente rotas que haya en él — ver la nota de abajo |
| Tope de tiempo | ~180 s **dentro de la petición**, no de reloj de pared | Un conteo solo no acota el caso «SEC colgada»: a 2,7 min por ticker, N=10 son 27 minutos y no hemos arreglado nada. Cobrar sólo la petición es lo que evita que los aciertos de caché entre dos fallos cuenten como espera |
| Que un acierto de caché reinicie el reloj | Innecesario | Se planteó cuando el tope medía reloj de pared. Cobrando sólo la petición, un acierto aporta cero por construcción y no hay nada que reiniciar |
| El diagnóstico de los dos topes | Una sola función, `_diagnostico` | Los dos mensajes difieren en cómo se llegó, no en la causa. Duplicados, arreglar uno dejó al otro mintiendo — pasó, y por eso están juntos |
| Acierto de caché | Ni reinicia la racha ni arranca el reloj | Un fichero leído de disco no dice nada sobre si la SEC responde; si contara como éxito, con media caché poblada el cortacircuitos no saltaría nunca |
| Panel parcial servido de caché | Se aborta igual | Serían empresas arbitrarias «las que estaban en caché»: un universo que nadie eligió, justo contra lo que existe el docstring de `CoverageReport` |

## Arquitectura

```
fundamentals/fallos.py   clasificar(exc) -> Fallo        [nuevo]
        │
        ▼
fundamentals/fetch.py    _fetch_facts   (deja de borrar distinciones)
                         _load_one      (un intento, sin bucle)
                         load_facts     (cortacircuitos, levanta CorridaAbortada)
        │
        ▼
fundamentals/run.py      build_panel        no la atrapa
ranking/run.py           construir_ranking  no la atrapa
pages/1_Revisar_candidatos.py  _generar     la pinta con st.error
```

### `fundamentals/fallos.py`

```python
@dataclass(frozen=True)
class Fallo:
    causa: str        # unresolved_cik | no_facts | transient | systemic | unknown
    detalle: str      # type(exc).__name__, para nombrar la causa sin adivinar
    explicacion: str  # frase accionable en castellano; "" salvo en las sistémicas
```

`explicacion` es cadena vacía y no `None` para las no sistémicas: es el texto que
acaba en `st.error`, y sólo se pide cuando ya se decidió abortar.

`clasificar(exc)` decide **en este orden**, que no es opcional: las tres primeras
sistémicas son `TransportError` con `http_status()` a `None`, así que puestas
después del renglón genérico de transporte se clasificarían como transitorias.

| Excepción | causa | Por qué |
|---|---|---|
| `CompanyFactsNotFoundError` | `no_facts` | La SEC contestó: esa CIK no tiene facts. Va antes que `NotFoundError` porque hereda de él |
| `NotFoundError` (incl. `CompanyNotFoundError`) | `unresolved_cik` | Sin CIK. Sale del parquet empaquetado, sin red de por medio |
| `IdentityError` | `systemic` | Cubre `IdentityNotSetError` y `SECIdentityError` de una vez: misma causa raíz, mismo arreglo |
| `TooManyRequestsError` | `systemic` | El bloqueo es de IP, no de ticker. Lleva `status_code=429`, así que la fila de 4xx ya lo declararía sistémico: esta fila está por el mensaje, no por la clasificación |
| `SSLVerificationError` | `systemic` | Es la red del usuario y es determinista |
| Transporte con 401 o 403 | `systemic` | **Por aquí llega el caso estrella**: ver la nota de abajo |
| Transporte con el resto de 4xx | `systemic` | Lo que está mal es la petición, y no cambia por ticker |
| Resto de `(HTTPError, TransportError)` | `transient` | 5xx, timeouts, connect errors |
| Cualquier otra cosa | `unknown` | No sabemos; la repetición será la única evidencia |

El 404 de company facts no llega al renglón «4xx»: edgartools lo convierte en
`CompanyFactsNotFoundError` mucho antes. Un 404 que llegue por otro camino habla
de la URL, no del ticker, y `systemic` es la lectura correcta.

### La identidad rechazada no llega como `SECIdentityError`

Esto se descubrió en la revisión de código de la Task 1 y corrige lo que decía
la primera versión de este documento. `SECIdentityError` se levanta en un solo
sitio de edgartools —`edgar/sgml/sgml_parser.py:195`, el camino de los
*filings*— y **nunca en la API de facts**. `download_company_facts_from_sec`
convierte el 404 en `CompanyFactsNotFoundError` y deja pasar todo lo demás como
`httpx.HTTPStatusError` crudo.

Así que la identidad presente que EDGAR rechaza —el caso de 25 minutos que
motivó todo esto— aterriza como **un 403 pelado**. Sin tratarlo aparte, la
corrida sí abortaría rápido, que es casi toda la victoria, pero el usuario
leería «la SEC ha rechazado la petición (HTTP 403)»: cierto e inútil. El texto
que nombra el arreglo real —revisar el correo de EDGAR— quedaba inalcanzable.

Por eso 401 y 403 tienen su propia fila y llevan el mensaje de identidad. La
fila de `IdentityError` se queda igualmente: cubre el camino de los filings, que
`ranking/filings.py` sí recorre, y la era 6.0 de edgartools.

### `fetch.py::_fetch_facts`

Con la jerarquía de la 5.52.0, la función se queda más corta de lo que estaba:

```python
company = Company(ticker)               # levanta CompanyNotFoundError si no hay CIK
facts = get_company_facts(company.cik)  # levanta CompanyFactsNotFoundError si es un 404
if facts is None:                       # antes: .to_dataframe() sobre None
    raise TransportError(f"la SEC no devolvió hechos usables para {ticker}")
return facts.to_dataframe()
```

Desaparece el `try/except Exception` que convertía cualquier cosa rota en «sin
CIK»: `CompanyNotFoundError` ya es la excepción correcta y `clasificar` la sabe
leer, así que envolverla sólo perdía información. Desaparece también el guardia
`if company is None`, que era código muerto — `Entity.__init__` levanta, nunca
devuelve `None`.

### Por qué `get_company_facts` y no `Entity.get_facts()`

Esto también salió de la revisión de la Task 1, y la primera versión de este
documento se equivocaba. `Entity.get_facts()` **atrapa**
`CompanyFactsNotFoundError` y devuelve `None`. Pero `get_company_facts` devuelve
`None` por otros dos motivos que no son un 404: una descarga que falla en blando
—la propia librería avisa «This is likely a network issue»— y un parseo que no
cuaja. Vistos desde `get_facts()`, los tres son el mismo `None`.

Sintetizar `CompanyFactsNotFoundError` a partir de ese `None`, que es lo que
decía la versión anterior, mandaría **un fallo de red a la casilla `no_facts`**.
Y `no_facts` tiene `fuente_viva` a `True`, o sea que reinicia la racha. Con la
SEC sirviendo cuerpos vacíos, cada ticker reiniciaría el cortacircuitos y la
corrida no abortaría nunca: exactamente la derrota que este diseño existe para
evitar, introducida por el propio diseño.

Llamando a `get_company_facts` directamente, el 404 llega como la excepción que
la librería levanta —no una que nos inventamos— y el `None` que queda sólo puede
ser un fallo de descarga o de parseo, que se señala con `TransportError` y
avanza la racha como debe.

### `fetch.py::CoverageReport`

Un campo nuevo, `no_facts: list[str]`, y su renglón en `summary()`. Es la casilla
que hoy no existe y que hace que un 404 legítimo se cuente como caída de red.

### `fetch.py::_load_one`

Desaparecen `max_retries` y el bucle. Devuelve un frozen dataclass en vez de una
tupla, porque ahora hay un tercer dato que no se puede perder:

```python
@dataclass(frozen=True)
class Intento:
    facts: pd.DataFrame | None
    fallo: Fallo | None
    desde_cache: bool     # un acierto de caché no dice nada sobre si la SEC responde
```

### `fetch.py::load_facts`

```python
RACHA_MAXIMA = 10             # fallos seguidos entre los que tocan la red
SIN_RESPUESTA_MAXIMO = 180.0  # segundos DENTRO de la petición, no de pared
```

Un solo invariante gobierna las dos guardas:

> **La racha y el tiempo perdido se reinician cuando la SEC entrega datos** — un
> `facts` bueno o un 404, que también exigió preguntar. **Avanzan cuando preguntamos y no
> los entregó** (`transient`, `unknown`). **No se tocan cuando no preguntamos**
> (acierto de caché, o CIK que resuelve contra el parquet local).

«Entrega datos» y no «contesta»: un 5xx es técnicamente una respuesta y aun así
tiene que avanzar la racha —la SEC diciendo «estoy rota» diez veces seguidas es
justo el caso para el que existe el cortacircuitos—, así que la propiedad se
llama `fuente_viva` y no `hubo_respuesta`. Con ese otro nombre, un 503 la haría
devolver `False` y los mensajes al usuario dirían «la SEC no contestó (HTTP
503)», contradiciéndose en la misma frase.

Un `systemic` no cuenta racha: aborta en el ticker en que aparece. El reloj
arranca en el primer fallo contado con delta cero, así que el tope de tiempo no
puede saltar en ese primer fallo, y un universo entero en caché nunca lo dispara.

El tope de tiempo cobra **sólo el tiempo dentro de la petición**, sumado desde
`Intento.segundos_de_red`. Midiendo reloj de pared, 500 tickers servidos de
caché entre dos fallos metían en la cuenta minutos que la corrida pasó leyendo
parquet productivamente, y el segundo fallo condenaba una corrida sana culpando
a la conexión. Hubo un `SIN_RESPUESTA_RACHA_MINIMA = 3` para tapar ese síntoma;
cobrando sólo la petición sobra, porque un acierto de caché aporta cero
segundos — que es exactamente lo que aportó a la espera.

Eso obligó a una costura pequeña y no negociable: `_ahora`, alias de
`time.monotonic` en `fetch.py`. Parchear `fundamentals.fetch.time.monotonic` en
un test parchea el atributo del módulo `time` global, y medido, un banco de
pruebas que leía 500 parquets veía 3,8 millones de llamadas en vez de las dos
por petición que creía contar: pandas y httpx miran el reloj por su cuenta. Con
el alias, la contabilidad es nuestra y nadie más la toca.

### La caché caliente encoge lo que significa «seguidas» — sin resolver

Un acierto de caché no rompe la racha, y eso es correcto: no prueba que la SEC
responda. Pero con la caché caliente los únicos tickers que tocan la red son los
que aún fallan, así que unos pocos fallos permanentes repartidos por el índice
quedan adyacentes **entre sí**, y una corrida sana puede abortar en la segunda
pasada. Hoy no dispara: `salidas/corrida.json` da `n_panel` 502 de 503, o sea ~1
empresa permanentemente rota contra un umbral de 10.

**Se intentó arreglar y se deshizo.** Queda escrito porque el intento enseñó
más que el problema.

La idea era: un payload que llega y no se deja convertir prueba que la fuente
entregó, así que debería reiniciar la racha en vez de avanzarla. Se implementó
envolviendo el `to_dataframe()` en `ParsingError` y dándole una causa propia,
`unparseable`, con `fuente_viva` a verdadero.

Dos cosas lo tumbaron:

1. **Reiniciar la racha y no tener ningún tope son cosas distintas, y se
   confundieron.** Con el cambio puesto, un fallo de parseo *sistémico* —un bug
   nuestro, o edgartools cambiando un atributo— dejaba de abortar por completo:
   503 peticiones, panel vacío, sin mensaje. Medido. O sea que el arreglo
   reintroducía exactamente el fallo que este módulo existe para eliminar, y el
   mensaje que sustituía prometía «en vez de repetirlo 503 veces».
2. **La premisa no se verificó nunca.** Todos los tests inyectaban
   `ParsingError` en un `_fetch_facts` parcheado, así que medían la propia
   inyección. `EntityFactsParser.parse_company_facts` devuelve `None` cuando el
   payload no cuaja, y ese `None` sale por la rama `TransportError` → `transient`,
   que **sí** avanza la racha. Lo que llega al `to_dataframe()` es un
   `EntityFacts` ya materializado, así que la población real de esa causa se
   inclina hacia agotamiento de memoria y bugs propios — justo lo que no debe
   reiniciar nada.

**Lo que hace falta para retomarlo:** una corrida real contra EDGAR que diga por
qué puerta fallan las empresas que fallan. Si salen por el `None`, este enfoque
no arregla nada. Si salen por `to_dataframe()`, el arreglo es viable pero tiene
que llevar su propio contador y su propio aborto con diagnóstico de fallo del
programa, en vez de quedarse sin tope.
