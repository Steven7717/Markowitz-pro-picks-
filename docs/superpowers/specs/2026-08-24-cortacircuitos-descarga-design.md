# Cortacircuitos de descarga — distinguir el ticker que falla de la fuente que no está

**Fecha:** 2026-08-24
**Estado:** diseño aprobado, sin implementar

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
| N | 10 | 2 % del universo. Un falso positivo exigiría diez empresas seguidas rotas mientras la SEC va bien |
| Tope de tiempo | ~180 s sin respuesta de la SEC | Un conteo solo no acota el caso «SEC colgada»: a 2,7 min por ticker, N=10 son 27 minutos y no hemos arreglado nada |
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
| `TooManyRequestsError` | `systemic` | El bloqueo es de IP, no de ticker |
| `SSLVerificationError` | `systemic` | Es la red del usuario y es determinista |
| Transporte con `http_status()` 4xx | `systemic` | Lo que está mal es la petición, y no cambia por ticker |
| Resto de `(HTTPError, TransportError)` | `transient` | 5xx, timeouts, connect errors |
| Cualquier otra cosa | `unknown` | No sabemos; la repetición será la única evidencia |

El 404 de company facts no llega al renglón «4xx»: edgartools lo convierte en
`CompanyFactsNotFoundError` mucho antes. Un 404 que llegue por otro camino habla
de la URL, no del ticker, y `systemic` es la lectura correcta.

### `fetch.py::_fetch_facts`

Con la jerarquía de la 5.52.0, la función se queda más corta de lo que estaba:

```python
company = Company(ticker)      # levanta CompanyNotFoundError si no hay CIK
facts = company.get_facts()
if facts is None:              # antes: .to_dataframe() sobre None
    raise CompanyFactsNotFoundError(cik=company.cik)
return facts.to_dataframe()
```

Desaparece el `try/except Exception` que convertía cualquier cosa rota en «sin
CIK»: `CompanyNotFoundError` ya es la excepción correcta y `clasificar` la sabe
leer, así que envolverla sólo perdía información. Desaparece también el guardia
`if company is None`, que era código muerto — `Entity.__init__` levanta, nunca
devuelve `None`.

Y el `None` de `get_facts()` se vuelve a convertir en la excepción **de la propia
librería** en vez de en una nuestra: es la que `clasificar` ya distingue, y no
añade un tipo más al vocabulario del proyecto.

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
    uso_la_red: bool      # un acierto de caché no dice nada sobre si la SEC responde
```

### `fetch.py::load_facts`

```python
RACHA_MAXIMA = 10             # 2 % del universo
SIN_RESPUESTA_MAXIMO = 180.0  # segundos
```

Un solo invariante gobierna las dos guardas:

> **La racha y el reloj se reinician cuando la SEC contesta** — un `facts` bueno
> o un 404. **Avanzan cuando preguntamos y no hubo respuesta** (`transient`,
> `unknown`). **No se tocan cuando no preguntamos** (acierto de caché, o CIK que
> no resuelve en local).

Un `systemic` no cuenta racha: aborta en el ticker en que aparece. El reloj
arranca en el primer intento de red, así que un universo entero en caché nunca lo
dispara.

### `CorridaAbortada`

```python
class CorridaAbortada(RuntimeError):
    """La corrida entera está condenada; seguir sólo gasta tiempo."""
    # lleva: causa, explicacion, y la CoverageReport hasta donde se llegó
```

Llevar la cobertura dentro es lo que permite decir «se bajaron 42 de 503 antes de
abortar» en vez de sólo «falló».

Sube sin que nadie la atrape hasta `_generar`, que la pinta con `st.error`. En
ese `except`, `_generar` **no** limpia el `session_state` ni hace `st.rerun()`:
no se sobrescribió `salidas/`, así que lo que el revisor tenía marcado sigue
siendo válido y borrarlo sería el defecto que arregló `cbe71a0`.

## El invariante, enmendado

Tres docstrings describen hoy la política vieja y hay que corregir los tres:

- `fundamentals/run.py::build_panel`
- `ranking/run.py::construir_ranking` (línea 79)
- `ranking/filings.py::cargar_riesgos` (línea 121, que enumera las casillas de
  fallo por su nombre y ahora son tres)

El invariante pasa a ser:

> Un ticker que falla se registra y se salta. Que fallen todos por la misma causa
> no es un ticker que falla: es que no hay fuente.

## Tests — todos sin red

`tests/test_fundamentals_fallos.py`, nuevo: un test por renglón de la tabla de
clasificación, construyendo excepciones reales (`TooManyRequestsError("url")`,
`SECIdentityError`, `IdentityNotSetError`, `CompanyNotFoundError`,
`CompanyFactsNotFoundError`, `SSLVerificationError`, `httpx.HTTPStatusError` con
respuesta 403 y con 503, `httpx.ConnectTimeout`).

Uno de esos tests es específicamente sobre el **orden**: un `SECIdentityError`
tiene que salir `systemic` y no `transient`, que es lo que saldría si el renglón
genérico de transporte se evaluara antes.

En `tests/test_fundamentals_fetch.py`:

- un fallo sistémico en el primer ticker aborta sin tocar los otros 502
  (`call_count == 1`)
- el 429 en concreto no se reintenta — el caso donde hoy hacemos daño activo
- 10 fallos ambiguos seguidos abortan; 9 y un éxito, no
- un 404 en medio reinicia la racha; un acierto de caché **no**
- un acierto de caché tampoco arranca el reloj
- el tope de tiempo dispara, con `time.monotonic` parcheado
- `no_facts` se reporta aparte de `failed_download`
- la excepción nombra la causa y cuántos tickers se bajaron antes de abortar
- **el invariante conservado**: un ticker que falla solo se registra y se salta

`test_a_transient_failure_is_retried` se reescribe. Su mecánica se va a stamina
—código que no es nuestro y que no nos toca testear— pero su intención se queda
con otro nombre: un fallo transitorio aislado se registra y no tumba la corrida.

El cambio en `_generar` queda sin test, como el resto de la página: Streamlit no
se prueba, y por eso las decisiones viven en `aprobacion/`.
