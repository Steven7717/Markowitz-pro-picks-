# Cortacircuitos de descarga — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una corrida condenada se rinda en segundos diciendo por qué, en vez de gastar ~25 minutos para acabar sin nada y sin explicación.

**Architecture:** Un módulo nuevo `fundamentals/fallos.py` traduce las excepciones de `edgar.exceptions` a tres preguntas (en qué casilla del informe va, si aborta ya, si cuenta como prueba de que la fuente no está). `fundamentals/fetch.py` deja de reintentar por su cuenta, deja de disfrazar excepciones, y lleva un cortacircuitos de racha + tope de tiempo que levanta `CorridaAbortada`. La excepción sube sin que nadie la atrape hasta la página, que la pinta.

**Tech Stack:** Python 3.12, pandas, edgartools 5.52.0 (fijada en `uv.lock`), pytest, Streamlit.

**Diseño:** `docs/superpowers/specs/2026-08-24-cortacircuitos-descarga-design.md`

---

## Antes de empezar

Los tests se corren así, desde la raíz del worktree:

```bash
uv run pytest tests/ -q -m "not red"
```

Si `uv` falla al crear el venv con un error de *hardlink* (`os error 396`, pasa
porque el proyecto está en una carpeta sincronizada con OneDrive), usa:

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

**Línea base antes de tocar nada:** `tests/test_fundamentals_fetch.py` pasa 11
tests. Compruébalo antes del Task 1 para no confundir un fallo tuyo con uno que
ya estaba.

**Versión de edgartools:** el plan está escrito contra la **5.52.0**, que es la
que fija `uv.lock`. La 5.47.0 que puede haber instalada en el sistema **no**
tiene `edgar.exceptions` y el código de este plan no funciona contra ella. Si
`uv run python -c "import edgar; print(edgar.__version__)"` no dice 5.52.0,
para y avisa antes de seguir.

---

## Estructura de ficheros

| Fichero | Responsabilidad | Estado |
|---|---|---|
| `fundamentals/fallos.py` | De qué clase es un fallo. Sin red, sin pandas, sin caché | **Crear** |
| `tests/test_fundamentals_fallos.py` | Un test por renglón de la tabla de clasificación | **Crear** |
| `fundamentals/fetch.py` | `_fetch_facts`, `_load_one`, `load_facts`, `CoverageReport`, `CorridaAbortada` | Modificar |
| `tests/test_fundamentals_fetch.py` | Caché, cobertura y cortacircuitos, todo sin red | Modificar |
| `fundamentals/run.py` | Docstring de `build_panel` (el invariante) | Modificar |
| `ranking/run.py` | Docstring de `construir_ranking` (el invariante) | Modificar |
| `ranking/filings.py` | Docstring de `cargar_riesgos` (enumera las casillas) | Modificar |
| `pages/1_Revisar_candidatos.py` | `_generar` atrapa `CorridaAbortada` y la pinta | Modificar |

---

## Task 1: La taxonomía de fallos

**Files:**
- Create: `fundamentals/fallos.py`
- Test: `tests/test_fundamentals_fallos.py`

El módulo no inventa taxonomía: la pone `edgar.exceptions`. Aquí sólo se traduce
a las tres preguntas que `load_facts` necesita responder.

- [ ] **Step 1: Escribir el fichero de tests completo**

Crea `tests/test_fundamentals_fallos.py`:

```python
import httpx
import pytest
from edgar.exceptions import (
    CompanyFactsNotFoundError,
    CompanyNotFoundError,
    IdentityNotSetError,
    NotFoundError,
    SECIdentityError,
    TooManyRequestsError,
)
from edgar.httprequests import SSLVerificationError

from fundamentals.fallos import (
    NO_FACTS,
    SYSTEMIC,
    TRANSIENT,
    UNKNOWN,
    UNRESOLVED_CIK,
    clasificar,
)


def _status(codigo: int) -> httpx.HTTPStatusError:
    """Un HTTPStatusError igual al que levanta edgartools al mirar la respuesta."""
    peticion = httpx.Request(
        "GET", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    with pytest.raises(httpx.HTTPStatusError) as capturada:
        httpx.Response(codigo, request=peticion).raise_for_status()
    return capturada.value


def _ssl() -> SSLVerificationError:
    import ssl

    return SSLVerificationError(
        ssl.SSLError("certificate verify failed"), "https://data.sec.gov/x"
    )


def test_una_empresa_sin_facts_no_es_un_fallo_de_descarga():
    """La SEC contesto: esa CIK existe y no tiene datos. Es permanente y suya."""
    assert clasificar(CompanyFactsNotFoundError(cik=320193)).causa == NO_FACTS


def test_un_ticker_sin_cik_va_a_su_propia_casilla():
    assert clasificar(CompanyNotFoundError("AAA")).causa == UNRESOLVED_CIK


def test_sin_facts_se_comprueba_antes_que_sin_cik():
    """Las dos heredan de NotFoundError; si se invierte el orden, la primera
    se clasifica como la segunda y el informe cuenta mal."""
    assert isinstance(CompanyFactsNotFoundError(cik=1), NotFoundError)
    assert isinstance(CompanyNotFoundError("AAA"), NotFoundError)
    assert clasificar(CompanyFactsNotFoundError(cik=1)).causa == NO_FACTS


def test_un_keyerror_suelto_no_se_confunde_con_un_ticker_sin_cik():
    """KeyError tambien es LookupError. Clasificar por LookupError a secas
    haria que un fallo de pandas apareciera como 'sin CIK' en el informe."""
    assert clasificar(KeyError("period_end")).causa == UNKNOWN


def test_las_dos_formas_del_problema_de_identidad_abortan():
    """La libreria les da un padre comun a proposito: misma causa, mismo arreglo."""
    assert clasificar(IdentityNotSetError()).causa == SYSTEMIC
    assert clasificar(SECIdentityError("rechazada")).causa == SYSTEMIC


def test_una_identidad_rechazada_no_es_un_fallo_transitorio():
    """SECIdentityError ES un TransportError sin codigo HTTP, asi que caeria en
    el renglon generico y saldria transitoria si el orden fuera otro."""
    assert clasificar(SECIdentityError("rechazada")).causa != TRANSIENT


def test_el_429_aborta_en_vez_de_reintentarse():
    """Reintentarlo alarga el bloqueo de IP que causo el fallo."""
    assert clasificar(TooManyRequestsError("https://data.sec.gov/x")).causa == SYSTEMIC


def test_un_fallo_de_certificado_aborta():
    assert clasificar(_ssl()).causa == SYSTEMIC


def test_un_4xx_aborta_porque_no_cambia_por_ticker():
    assert clasificar(_status(403)).causa == SYSTEMIC


def test_un_5xx_es_ambiguo_y_espera_a_repetirse():
    assert clasificar(_status(503)).causa == TRANSIENT


def test_un_timeout_es_ambiguo_y_espera_a_repetirse():
    assert clasificar(httpx.ConnectTimeout("sin red")).causa == TRANSIENT


def test_lo_que_no_reconocemos_no_se_da_por_transitorio():
    assert clasificar(ValueError("algo raro")).causa == UNKNOWN


def test_solo_las_sistemicas_traen_explicacion():
    """Es el texto que acaba en pantalla; pedirlo cuando no se aborta no significa nada."""
    assert clasificar(TooManyRequestsError("u")).explicacion
    assert not clasificar(httpx.ConnectTimeout("x")).explicacion


def test_la_explicacion_del_429_dice_que_esperar_y_no_reintentar():
    texto = clasificar(TooManyRequestsError("u")).explicacion
    assert "10 minutos" in texto
    assert "alarga" in texto


def test_el_detalle_nombra_el_tipo_para_poder_citarlo():
    assert clasificar(httpx.ConnectTimeout("x")).detalle == "ConnectTimeout"
    assert clasificar(_status(503)).detalle == "HTTP 503"


@pytest.mark.parametrize(
    "excepcion, aborta, fuente_viva, cuenta_racha",
    [
        (TooManyRequestsError("u"), True, False, False),
        (CompanyFactsNotFoundError(cik=1), False, True, False),
        (CompanyNotFoundError("AAA"), False, False, False),
        (httpx.ConnectTimeout("x"), False, False, True),
        (ValueError("raro"), False, False, True),
    ],
)
def test_las_tres_preguntas_que_gobiernan_el_cortacircuitos(
    excepcion, aborta, fuente_viva, cuenta_racha
):
    """unresolved_cik es el caso sutil: no toca la red (sale del parquet
    empaquetado), asi que ni reinicia la racha ni la hace avanzar."""
    fallo = clasificar(excepcion)
    assert fallo.aborta is aborta
    assert fallo.fuente_viva is fuente_viva
    assert fallo.cuenta_racha is cuenta_racha
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_fundamentals_fallos.py -q
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fundamentals.fallos'`.

- [ ] **Step 3: Escribir el módulo**

Crea `fundamentals/fallos.py`:

```python
"""De qué clase es un fallo de descarga, y si tiene sentido seguir pidiendo.

Vive aparte de `fetch.py` por la misma razón que `concepts.py` vive aparte: es
una tabla de decisiones, sin red y sin pandas, y se prueba renglón por renglón.

La taxonomía no se inventa aquí. La pone `edgar.exceptions`, que distingue por
tipo lo que si no habría que adivinar leyendo códigos HTTP: `SECIdentityError`
para la identidad que la SEC rechaza, `CompanyFactsNotFoundError` para la
empresa que existe y no tiene datos. Este módulo sólo traduce esos tipos a las
tres preguntas que `load_facts` necesita responder: en qué casilla del informe
va el ticker, si hay que abortar ya, y si cuenta como prueba de que la fuente
no está.
"""

from dataclasses import dataclass

# Las dos primeras conservan el nombre de la casilla que ya existía en
# CoverageReport, para que el informe no cambie de vocabulario a mitad.
UNRESOLVED_CIK = "unresolved_cik"
NO_FACTS = "no_facts"
TRANSIENT = "transient"
SYSTEMIC = "systemic"
UNKNOWN = "unknown"

_IDENTIDAD = (
    "La SEC no aceptó la identidad con la que se piden los datos. Exige un "
    "contacto real en la cabecera de cada petición: revisa el correo de EDGAR "
    "en el apartado de credenciales y vuelve a intentarlo."
)
_RATE_LIMIT = (
    "La SEC ha bloqueado tu IP por exceder su límite de peticiones. El bloqueo "
    "dura unos 10 minutos y seguir pidiendo lo alarga, así que la corrida se "
    "para aquí. Espera ese rato y vuelve a darle a Generar: lo ya descargado "
    "está en caché y no se vuelve a bajar."
)
_SSL = (
    "No se pudo verificar el certificado de la SEC. Suele pasar detrás de una "
    "VPN o de un antivirus que inspecciona el tráfico. Prueba en otra red, o "
    "excluye data.sec.gov de esa inspección."
)


def _rechazo(codigo: int) -> str:
    return (
        f"La SEC ha rechazado la petición (HTTP {codigo}). No es un problema de "
        "una empresa concreta: la misma petición va a fallar para todas, así "
        "que la corrida se para aquí."
    )


@dataclass(frozen=True)
class Fallo:
    """Un fallo ya clasificado: dónde se anota y qué implica para la corrida."""

    causa: str
    detalle: str
    explicacion: str = ""

    @property
    def aborta(self) -> bool:
        """Si por sí solo condena la corrida, sin esperar a que se repita."""
        return self.causa == SYSTEMIC

    @property
    def fuente_viva(self) -> bool:
        """Si la SEC llegó a contestar, aunque fuera para decir que no hay datos.

        Un `no_facts` exigió una respuesta de data.sec.gov, así que es prueba de
        que la fuente está viva: reinicia la racha igual que un acierto.
        """
        return self.causa == NO_FACTS

    @property
    def cuenta_racha(self) -> bool:
        """Si preguntamos y no hubo respuesta. Es lo único que avanza la racha.

        Un `unresolved_cik` no cuenta: se resuelve contra el parquet que
        edgartools trae empaquetado, sin pedirle nada a la SEC, así que no dice
        nada sobre si la fuente está. Ni la avanza ni la reinicia.
        """
        return self.causa in (TRANSIENT, UNKNOWN)


def clasificar(exc: BaseException) -> Fallo:
    """De qué clase es este fallo.

    El orden de las comprobaciones no es opcional, y hay dos razones distintas:

    - `CompanyFactsNotFoundError` hereda de `CompanyNotFoundError`, así que
      puesta después se clasificaría como «sin CIK».
    - `IdentityError`, `TooManyRequestsError` y `SSLVerificationError` son todas
      `TransportError`, así que puestas después del renglón genérico de
      transporte se clasificarían como transitorias — y se reintentarían las
      tres cosas que no mejoran reintentando.

    Se importa dentro de la función, como hace `fetch.py` con `Company`: mantiene
    el coste de importar edgartools fuera del arranque de la app.
    """
    from edgar.exceptions import (
        CompanyFactsNotFoundError,
        IdentityError,
        NotFoundError,
        TooManyRequestsError,
        http_status,
    )
    from edgar.httprequests import TRANSPORT_ERRORS, SSLVerificationError

    detalle = type(exc).__name__

    if isinstance(exc, CompanyFactsNotFoundError):
        return Fallo(NO_FACTS, detalle)
    # NotFoundError y no LookupError a secas: KeyError también es LookupError, y
    # un fallo de pandas acabaría contado como un ticker sin CIK.
    if isinstance(exc, NotFoundError):
        return Fallo(UNRESOLVED_CIK, detalle)
    if isinstance(exc, IdentityError):
        return Fallo(SYSTEMIC, detalle, _IDENTIDAD)
    if isinstance(exc, TooManyRequestsError):
        return Fallo(SYSTEMIC, detalle, _RATE_LIMIT)
    if isinstance(exc, SSLVerificationError):
        return Fallo(SYSTEMIC, detalle, _SSL)
    if isinstance(exc, TRANSPORT_ERRORS):
        # http_status devuelve None cuando no llegamos a preguntar (timeout,
        # conexión rechazada) y el código cuando la SEC sí contestó.
        codigo = http_status(exc)
        if codigo is None:
            return Fallo(TRANSIENT, detalle)
        if 400 <= codigo < 500:
            return Fallo(SYSTEMIC, f"HTTP {codigo}", _rechazo(codigo))
        return Fallo(TRANSIENT, f"HTTP {codigo}")
    return Fallo(UNKNOWN, detalle)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

```bash
uv run pytest tests/test_fundamentals_fallos.py -q
```

Esperado: `20 passed` (15 tests sueltos + los 5 casos de la parametrizada).

- [ ] **Step 5: Correr la suite entera para verificar que no se rompió nada**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa, con los tests nuevos sumados a la cuenta.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/fallos.py tests/test_fundamentals_fallos.py && git commit -m "feat: clasificar los fallos de descarga por su tipo"
```

---

## Task 2: La casilla que faltaba en el informe de cobertura

**Files:**
- Modify: `fundamentals/fetch.py` (la clase `CoverageReport`)
- Test: `tests/test_fundamentals_fetch.py`

Hoy una empresa sin *company facts* se cuenta como fallo de descarga. Es una
casilla nueva, aditiva, sin nada que la llene todavía — la llena el Task 3.

- [ ] **Step 1: Escribir el test que falla**

Añade al final de `tests/test_fundamentals_fetch.py`:

```python
def test_el_resumen_cuenta_las_empresas_sin_hechos_aparte(cache_dir):
    """Una empresa que existe y no tiene facts no es una caida de red."""
    cobertura = CoverageReport(requested=["AAA"], no_facts=["AAA"])
    assert "sin hechos: 1" in cobertura.summary()
```

- [ ] **Step 2: Correr el test para verificar que falla**

```bash
uv run pytest tests/test_fundamentals_fetch.py::test_el_resumen_cuenta_las_empresas_sin_hechos_aparte -q
```

Esperado: FAIL con `TypeError: CoverageReport.__init__() got an unexpected keyword argument 'no_facts'`.

- [ ] **Step 3: Añadir el campo y su renglón**

En `fundamentals/fetch.py`, dentro de `class CoverageReport`, añade el campo
justo debajo de `unresolved_cik`:

```python
    unresolved_cik: list[str] = field(default_factory=list)
    no_facts: list[str] = field(default_factory=list)
    failed_download: list[str] = field(default_factory=list)
```

Y en `summary()`, el renglón en el mismo sitio:

```python
    def summary(self) -> str:
        return (
            f"Tickers solicitados: {len(self.requested)} | "
            f"incluidos: {len(self.included)} | "
            f"sin CIK: {len(self.unresolved_cik)} | "
            f"sin hechos: {len(self.no_facts)} | "
            f"fallos de descarga: {len(self.failed_download)} | "
            f"historia corta: {len(self.short_history)} | "
            f"sin sector: {len(self.missing_sector)} | "
            f"sin precio: {len(self.missing_price)}"
        )
```

Actualiza también el docstring de la clase, que enumera el criterio:

```python
    """Which tickers made it into the panel, and why the rest did not.

    Silently dropping tickers is how an engine ends up describing a universe
    nobody chose. Every exclusion is counted and attributed to a cause.

    `unresolved_cik`, `no_facts` y `failed_download` son tres cosas distintas a
    propósito: el ticker que no existe, la empresa que existe y no publica
    facts, y la petición que no llegó a completarse. Meterlas en la misma
    casilla haría que una caída de la SEC se leyera como un universo lleno de
    empresas raras.
    """
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q
```

Esperado: `12 passed`.

- [ ] **Step 5: Commit**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py && git commit -m "feat: casilla propia para la empresa sin company facts"
```

---

## Task 3: Que `_fetch_facts` deje de borrar distinciones

**Files:**
- Modify: `fundamentals/fetch.py` (la función `_fetch_facts`)
- Test: `tests/test_fundamentals_fetch.py`

Dos defectos en una función de diez líneas: un `except Exception` que convierte
cualquier cosa rota en «sin CIK», y un `.to_dataframe()` sobre lo que puede ser
`None`.

- [ ] **Step 1: Escribir los tests que fallan**

Añade a `tests/test_fundamentals_fetch.py`. Los imports nuevos van arriba del
fichero, junto a los que ya hay:

```python
from unittest.mock import Mock, patch

import httpx
from edgar.exceptions import CompanyFactsNotFoundError, CompanyNotFoundError

from fundamentals.fetch import CoverageReport, _cache_path, _fetch_facts, load_facts
```

Y los tests, al final:

```python
def test_un_ticker_sin_cik_deja_pasar_la_excepcion_de_la_libreria():
    """Envolverla en LookupError solo perdia informacion: clasificar ya la lee."""
    with patch("edgar.Company", side_effect=CompanyNotFoundError("AAA")):
        with pytest.raises(CompanyNotFoundError):
            _fetch_facts("AAA")


def test_una_caida_de_red_al_resolver_el_cik_no_se_disfraza_de_sin_cik():
    """Lo que hacia el `except Exception` que habia aqui: un corte de red
    acababa contado como 'este ticker no existe'."""
    with patch("edgar.Company", side_effect=httpx.ConnectTimeout("sin red")):
        with pytest.raises(httpx.ConnectTimeout):
            _fetch_facts("AAA")


def test_una_empresa_sin_facts_deja_pasar_el_404_de_la_libreria():
    """get_company_facts la levanta sola; no hay que sintetizarla."""
    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", side_effect=CompanyFactsNotFoundError(cik=320193)
    ):
        with pytest.raises(CompanyFactsNotFoundError):
            _fetch_facts("AAA")


def test_un_cuerpo_vacio_no_se_confunde_con_una_empresa_sin_hechos():
    """El defecto que habria desarmado el cortacircuitos entero.

    ESTE TEST SOSTIENE LA CORRECCION DE fallos.fuente_viva, no es incidental.
    Esa propiedad solo es cierta porque _fetch_facts pasa por
    get_company_facts; ningun test de test_fundamentals_fallos.py puede
    protegerlo, porque el acoplamiento cruza el borde entre los dos modulos.
    Si alguien devuelve _fetch_facts a Entity.get_facts(), este es el unico
    sitio donde salta.

    get_company_facts devuelve None por dos motivos que no son un 404: una
    descarga que falla en blando y un parseo que no cuaja. Contar eso como
    no_facts pondria fuente_viva a True y reiniciaria la racha en cada ticker,
    asi que con la SEC sirviendo cuerpos vacios la corrida no abortaria nunca.
    """
    from edgar.exceptions import TransportError

    from fundamentals.fallos import clasificar

    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", return_value=None
    ):
        with pytest.raises(TransportError) as levantada:
            _fetch_facts("AAA")
    assert clasificar(levantada.value).cuenta_racha is True
    assert clasificar(levantada.value).fuente_viva is False


def test_el_camino_feliz_devuelve_la_tabla_larga():
    hechos = Mock()
    hechos.to_dataframe.return_value = _facts("AAA")
    with patch("edgar.Company", return_value=Mock(cik=320193)), patch(
        "edgar.get_company_facts", return_value=hechos
    ):
        assert len(_fetch_facts("AAA")) == 12
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q -k "sin_cik or cuerpo_vacio or sin_facts_deja_pasar or camino_feliz"
```

Esperado: fallan **los cinco**, por tres motivos distintos. Estos mensajes están
copiados de una corrida real, no razonados:

```
test_un_ticker_sin_cik_deja_pasar_la_excepcion_de_la_libreria
    LookupError: sin CIK para AAA
test_una_caida_de_red_al_resolver_el_cik_no_se_disfraza_de_sin_cik
    LookupError: sin CIK para AAA
test_una_empresa_sin_facts_deja_pasar_el_404_de_la_libreria
    Failed: DID NOT RAISE CompanyFactsNotFoundError
test_un_cuerpo_vacio_no_se_confunde_con_una_empresa_sin_hechos
    Failed: DID NOT RAISE TransportError
test_el_camino_feliz_devuelve_la_tabla_larga
    TypeError: object of type 'Mock' has no len()
```

Los dos primeros son el `except Exception` de hoy haciendo justo lo que este
Task viene a quitar: convierte tanto un `CompanyNotFoundError` como un
`ConnectTimeout` en un `LookupError` pelado. `pytest.raises` no lo acepta —un
`LookupError` no es un `CompanyNotFoundError`, es su padre— y lo deja escapar.

Los tres últimos son consecuencia de que el doble parchea `get_company_facts`
mientras la función de hoy llama a `company.get_facts()`. Sobre un `Mock`, esa
cadena **no** revienta: `Mock` fabrica atributos al vuelo, así que
`company.get_facts().to_dataframe()` devuelve otro `Mock` tan campante. De ahí
que no haya ningún `AttributeError` a la vista y que el camino feliz muera
mucho después, al pedirle `len()` a ese `Mock`.

Vale la pena tenerlo escrito porque la primera versión de este plan predecía
`AttributeError` en tres de los cinco y `pasa hoy` en el cuarto, y las cinco
predicciones eran falsas: estaban razonadas sobre el camino de llamada de la
implementación *nueva* con la *vieja* todavía puesta.

- [ ] **Step 3: Reescribir `_fetch_facts`**

Sustituye la función entera en `fundamentals/fetch.py`:

```python
def _fetch_facts(ticker: str) -> pd.DataFrame:
    """Raw edgartools call, isolated so tests can replace it without the network.

    Returns SEC's long fact table: one row per reported fact, carrying the real
    period_start/period_end dates. The per-statement helpers are not used — they
    label columns by fiscal quarter ('Q3 2026'), and a fiscal quarter is a
    different calendar window for Apple than for JPMorgan, so those labels cannot
    align companies against each other.

    No atrapa nada: las excepciones de edgartools ya distinguen lo que hay que
    distinguir y `fallos.clasificar` las sabe leer. Aquí hubo un
    `except Exception` que las convertía todas en «sin CIK», con lo que un corte
    de red acababa contado como un universo de tickers inexistentes.

    Va por `get_company_facts` y no por `Entity.get_facts()` a propósito. El
    método atrapa `CompanyFactsNotFoundError` y devuelve `None`, que queda
    indistinguible del `None` que la función devuelve por una descarga fallida
    en blando o por un parseo que no cuaja. Confundirlos mandaría un fallo de
    red a la casilla `no_facts`, cuya `fuente_viva` reinicia la racha: con la
    SEC sirviendo cuerpos vacíos, el cortacircuitos no saltaría jamás.
    """
    from edgar import Company, get_company_facts
    from edgar.exceptions import TransportError

    company = Company(ticker)  # levanta CompanyNotFoundError si no hay CIK
    facts = get_company_facts(company.cik)  # levanta CompanyFactsNotFoundError si es un 404
    if facts is None:
        # Aquí sólo se llega por fallo de descarga o de parseo, nunca por un 404.
        # TransportError es de la propia librería y clasificar() ya la lee como
        # transitoria, que es lo que hace avanzar la racha.
        raise TransportError(f"la SEC no devolvió hechos usables para {ticker}")
    return facts.to_dataframe()
```

Dos cosas desaparecen. El guardia `if company is None` era código muerto:
`Entity.__init__` levanta `CompanyNotFoundError`, nunca devuelve `None`. Y ya no
se sintetiza `CompanyFactsNotFoundError`: la levanta la librería, que es quien
sabe si hubo un 404 de verdad.

- [ ] **Step 4: Correr los tests para verificar que pasan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q
```

Esperado: `17 passed` — los 12 que hay tras el Task 2, más los 5 nuevos. Todo
verde, incluidos los tests viejos: cada uno de ellos parchea
`fundamentals.fetch._fetch_facts` entero, así que reescribir su interior no les
afecta. Los que sí cambian de comportamiento —los que dependen de
`max_retries`— los reescribe el Task 4.

- [ ] **Step 5: Correr la suite entera**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py && git commit -m "fix: que _fetch_facts no disfrace un corte de red de ticker inexistente"
```

---

## Task 4: Un intento por ticker, y clasificar el fallo

**Files:**
- Modify: `fundamentals/fetch.py` (`_load_one`, `load_facts`, imports)
- Test: `tests/test_fundamentals_fetch.py`

Aquí desaparecen `max_retries` y sus `time.sleep`, que son los que ponían los
25 minutos. Todavía **sin** cortacircuitos: eso es el Task 5.

- [ ] **Step 1: Adaptar los dos tests que usan `max_retries`**

En `tests/test_fundamentals_fetch.py`, sustituye
`test_an_unresolvable_ticker_is_reported_separately_from_a_network_failure`
(usa `LookupError` pelado y `max_retries=1`) por:

```python
def test_un_ticker_sin_cik_se_reporta_aparte_de_un_fallo_de_red(cache_dir):
    """Un ticker que no existe y una caida de SEC son problemas distintos.

    Medido durante el diseno: AEP no aparece en el mapa oficial ticker->CIK de
    SEC. Confundirlo con un fallo de red esconderia una caida real.
    """
    def falla(ticker):
        if ticker == "BBB":
            raise CompanyNotFoundError("BBB")
        raise httpx.ConnectTimeout("boom")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert cobertura.unresolved_cik == ["BBB"]
    assert cobertura.failed_download == ["AAA"]
```

Y sustituye `test_a_transient_failure_is_retried` por el test que conserva su
intención sin afirmar una mecánica que ya no es nuestra:

```python
def test_un_ticker_que_falla_solo_se_registra_y_no_aborta_la_corrida(cache_dir):
    """La politica que este cambio NO toca.

    El reintento de lo transitorio se delega en edgartools, que hace 5 intentos
    con backoff y sabe cuales no reintentar. Testear eso aqui seria testear la
    libreria; lo que si es nuestro es que un fallo aislado no tumbe la corrida.
    """
    def uno_falla(ticker):
        if ticker == "BBB":
            raise httpx.ConnectTimeout("tropiezo")
        return _facts(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=uno_falla):
        hechos, cobertura = load_facts(["AAA", "BBB", "CCC"], cache_dir=cache_dir)
    assert sorted(hechos) == ["AAA", "CCC"]
    assert cobertura.failed_download == ["BBB"]


def test_no_se_duerme_entre_tickers(cache_dir):
    """Los 25 minutos eran 3 s por ticker de time.sleep nuestro, 503 veces."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")), \
         patch("fundamentals.fetch.time.sleep") as siesta:
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert siesta.call_count == 0


def test_una_empresa_sin_facts_va_a_su_casilla_y_no_a_la_de_descarga(cache_dir):
    def sin_facts(ticker):
        raise CompanyFactsNotFoundError(cik=1)

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_facts):
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir)
    assert cobertura.no_facts == ["AAA"]
    assert cobertura.failed_download == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q -k "no_se_duerme or sin_facts_va_a_su_casilla"
```

Esperado: FAIL. Medido, no razonado:

- `test_no_se_duerme_entre_tickers` → `assert 4 == 0`. Son **cuatro**, no dos:
  `max_retries=3` deja dos esperas por ticker fallido, y el test usa dos tickers.
- `test_una_empresa_sin_facts_va_a_su_casilla...` → falla porque
  `CompanyFactsNotFoundError` hereda de `LookupError` y el `except LookupError`
  de `_load_one` se la traga, mandándola a `unresolved_cik`.

Ese segundo punto describe un defecto **que ya existe en la rama** desde el Task
3, y que este Task es el que lo cierra: desde que `_fetch_facts` levanta
`CompanyFactsNotFoundError` de verdad, una empresa que existe y no publica
hechos se le reporta al usuario como «sin CIK», o sea como un ticker que no
existe. Es exactamente la trampa contra la que avisa el docstring de
`fallos.clasificar` —`CompanyFactsNotFoundError` hereda de `NotFoundError`, así
que comprobada después se clasifica como «sin CIK»— y `_load_one` es el «después».
Ningún test lo cubre entre el Task 3 y el Task 4, y la suite está verde en ese
hueco.

- [ ] **Step 3: Añadir `Intento` y reescribir `_load_one`**

En `fundamentals/fetch.py`, añade el import arriba del fichero:

```python
from fundamentals.fallos import (
    NO_FACTS,
    UNRESOLVED_CIK,
    Fallo,
    clasificar,
)
```

Añade el dataclass justo encima de `_load_one`:

```python
@dataclass(frozen=True)
class Intento:
    """Qué salió de pedir un ticker, y de dónde salió.

    `desde_cache` no es instrumentación: es lo que impide que un fichero leído
    de disco cuente como prueba de que la SEC responde. Sin ese dato, una caché
    a medio poblar apagaría el cortacircuitos de `load_facts`.
    """

    facts: pd.DataFrame | None
    fallo: Fallo | None
    desde_cache: bool = False
```

Y sustituye `_load_one` entera:

```python
def _load_one(ticker: str, cache_dir: Path, refresh: bool) -> Intento:
    """Un intento por ticker; el reintento de lo transitorio es de edgartools.

    Aquí había un bucle de `max_retries=3` con `time.sleep(2.0**intento)`. Se
    quitó porque no añadía intentos útiles y sí 3 s de espera por ticker: sobre
    503 tickers, esos 3 s eran los ~25 minutos que esta función tardaba en no
    devolver nada cuando la SEC rechazaba la identidad.

    edgartools ya reintenta 5 veces con backoff lo que mejora reintentando, y
    deja pasar al primer intento lo que no —429, SSL, identidad—, que es
    justamente lo que un bucle de fuera no puede distinguir.
    """
    path = _cache_path(cache_dir, ticker)
    if path.exists() and not refresh:
        try:
            return Intento(pd.read_parquet(path), None, desde_cache=True)
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a miss
            # rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    try:
        frame = _fetch_facts(ticker)
    except Exception as exc:
        return Intento(None, clasificar(exc))

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # SEC mixes types in the raw value column and parquet needs one per
    # column. astype's errors="ignore" does not cover a missing key — it
    # still raises KeyError — so the column is checked before casting.
    if "value" in frame.columns:
        frame = frame.astype({"value": "string"})
    frame.to_parquet(tmp)
    tmp.replace(path)  # atomic rename: a reader never sees a partial file
    return Intento(frame, None)
```

- [ ] **Step 4: Adaptar `load_facts` al nuevo `_load_one`**

Añade la función auxiliar justo encima de `load_facts`:

```python
def _anotar(cobertura: CoverageReport, ticker: str, fallo: Fallo) -> None:
    """Cada exclusión, en la casilla que le toca."""
    if fallo.causa == UNRESOLVED_CIK:
        cobertura.unresolved_cik.append(ticker)
    elif fallo.causa == NO_FACTS:
        cobertura.no_facts.append(ticker)
    else:
        cobertura.failed_download.append(ticker)
```

Y sustituye la firma y el bucle de `load_facts` (deja el docstring como está de
momento; el Task 5 lo amplía):

```python
def load_facts(
    tickers: list[str],
    cache_dir: Path | None = None,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], CoverageReport]:
    cache_dir = cache_dir or _DEFAULT_CACHE
    cobertura = CoverageReport(requested=list(tickers))
    hechos: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        intento = _load_one(ticker, cache_dir, refresh)
        if intento.fallo is not None:
            _anotar(cobertura, ticker, intento.fallo)
            continue

        hechos[ticker] = (
            intento.facts if intento.facts is not None else pd.DataFrame()
        )
        cobertura.included.append(ticker)

    return hechos, cobertura
```

- [ ] **Step 5: Correr la suite entera**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa. Si falla `tests/test_fundamentals_run.py`, revisa que no
hayas cambiado la firma de retorno de `load_facts` — sigue devolviendo la misma
tupla `(hechos, cobertura)`.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py && git commit -m "refactor: un intento por ticker, y el fallo clasificado"
```

---

## Task 5: El cortacircuitos por racha

**Files:**
- Modify: `fundamentals/fetch.py` (`CorridaAbortada`, `load_facts`)
- Test: `tests/test_fundamentals_fetch.py`

- [ ] **Step 1: Escribir los tests que fallan**

Primero, deja la cabecera de imports de `tests/test_fundamentals_fetch.py` así —
es la definitiva, ya incluye lo que necesita el Task 6:

```python
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pandas as pd
import pytest
from edgar.exceptions import (
    CompanyFactsNotFoundError,
    CompanyNotFoundError,
    TooManyRequestsError,
)

from fundamentals.fetch import (
    RACHA_MAXIMA,
    SIN_RESPUESTA_MAXIMO,
    CorridaAbortada,
    CoverageReport,
    _cache_path,
    _fetch_facts,
    load_facts,
)
```

`SIN_RESPUESTA_MAXIMO` todavía no existe: lo crea el Task 6. Hasta entonces
déjalo fuera del import y añádelo allí. Ahora los tests, al final del fichero:

```python
def _status(codigo: int) -> httpx.HTTPStatusError:
    """Un HTTPStatusError igual al que levanta edgartools al mirar la respuesta."""
    peticion = httpx.Request("GET", "https://data.sec.gov/x")
    with pytest.raises(httpx.HTTPStatusError) as capturada:
        httpx.Response(codigo, request=peticion).raise_for_status()
    return capturada.value


def test_una_identidad_rechazada_aborta_en_el_primer_ticker(cache_dir):
    """Es global por definicion: no hace falta esperar a que se repita 503 veces.

    Llega como un 403 pelado y no como SECIdentityError: esa solo la levanta el
    parser de SGML, que es el camino de los filings, no el de los facts.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)) as pedido:
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(503)], cache_dir=cache_dir)
    assert pedido.call_count == 1
    assert "correo de EDGAR" in str(abortada.value)


def test_el_429_no_se_reintenta_porque_reintentarlo_alarga_el_bloqueo(cache_dir):
    with patch(
        "fundamentals.fetch._fetch_facts",
        side_effect=TooManyRequestsError("https://data.sec.gov/x"),
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert pedido.call_count == 1


def test_diez_fallos_seguidos_sin_respuesta_abortan_la_corrida(cache_dir):
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts([f"T{i:03d}" for i in range(50)], cache_dir=cache_dir)
    assert pedido.call_count == RACHA_MAXIMA


def test_nueve_fallos_y_un_acierto_no_abortan(cache_dir):
    """Un solo exito rompe la racha: un fallo aislado nunca dispara nada."""
    def falla_salvo_el_decimo(ticker):
        if ticker == "T009":
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_salvo_el_decimo):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(19)], cache_dir=cache_dir
        )
    assert cobertura.included == ["T009"]
    assert len(cobertura.failed_download) == 18


def test_un_404_en_medio_reinicia_la_racha(cache_dir):
    """La SEC contesto: la fuente esta viva aunque esa empresa no tenga datos."""
    def sin_facts_en_medio(ticker):
        if ticker == "T005":
            raise CompanyFactsNotFoundError(cik=1)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_facts_en_medio):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(15)], cache_dir=cache_dir
        )
    assert cobertura.no_facts == ["T005"]
    assert len(cobertura.failed_download) == 14


def test_un_acierto_de_cache_no_reinicia_la_racha(cache_dir):
    """Un fichero leido de disco no dice nada sobre si la SEC responde.

    Si contara como exito, una cache a medio poblar apagaria el cortacircuitos:
    con 200 de 503 en disco, la racha no llegaria nunca a diez.
    """
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["CACHEADO"], cache_dir=cache_dir)

    tickers = (
        [f"T{i:03d}" for i in range(5)]
        + ["CACHEADO"]
        + [f"T{i:03d}" for i in range(5, 20)]
    )
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as pedido:
        with pytest.raises(CorridaAbortada):
            load_facts(tickers, cache_dir=cache_dir)
    assert pedido.call_count == RACHA_MAXIMA


def test_un_ticker_sin_cik_ni_avanza_ni_reinicia_la_racha(cache_dir):
    """Se resuelve contra el parquet empaquetado, sin pedirle nada a la SEC."""
    def sin_cik(ticker):
        raise CompanyNotFoundError(ticker)

    with patch("fundamentals.fetch._fetch_facts", side_effect=sin_cik):
        _, cobertura = load_facts(
            [f"T{i:03d}" for i in range(30)], cache_dir=cache_dir
        )
    assert len(cobertura.unresolved_cik) == 30


def test_la_excepcion_dice_la_causa_y_cuanto_se_llego_a_bajar(cache_dir):
    def falla_tras_dos(ticker):
        if ticker in ("T000", "T001"):
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_tras_dos):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(50)], cache_dir=cache_dir)
    mensaje = str(abortada.value)
    assert "2 de 50" in mensaje
    assert "ConnectTimeout" in mensaje
    assert abortada.value.cobertura.included == ["T000", "T001"]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q -k "aborta or racha or 429 or excepcion_dice"
```

Esperado: error de recolección con
`ImportError: cannot import name 'RACHA_MAXIMA' from 'fundamentals.fetch'`.

Es `RACHA_MAXIMA` y no `CorridaAbortada` porque `IMPORT_FROM` falla en el primer
nombre que no existe siguiendo el orden de la tupla, y ahí `RACHA_MAXIMA` va
antes. Y es `ImportError`, no `NameError`: el fallo ocurre al importar, no al
usar. Medido.

- [ ] **Step 3: Añadir `CorridaAbortada` y las constantes**

Primero, amplía el import de `fundamentals.fallos` que dejó el Task 4 para que
incluya `UNKNOWN`, que necesita `_sin_fuente`:

```python
from fundamentals.fallos import (
    NO_FACTS,
    UNKNOWN,
    UNRESOLVED_CIK,
    Fallo,
    clasificar,
)
```

Y en `fundamentals/fetch.py`, junto a `PERIODOS` y `MIN_TRIMESTRES`:

```python
# 2 % del universo. Un falso positivo exigiría diez empresas seguidas rotas
# mientras la SEC va bien, que no es un escenario real.
RACHA_MAXIMA = 10
```

Y la excepción, justo debajo de `CoverageReport`:

```python
class CorridaAbortada(RuntimeError):
    """La corrida entera está condenada; seguir sólo gasta tiempo.

    Vive aquí y no en `fallos.py` porque lleva dentro la `CoverageReport`, que
    también vive aquí: al revés sería un import circular.

    Llevar la cobertura dentro es lo que permite decir cuánto se llegó a bajar
    antes de rendirse. Sin ese número, «falló» y «falló habiendo bajado 480 de
    503» se leen igual, y no son lo mismo en absoluto.
    """

    def __init__(self, causa: str, explicacion: str, cobertura: CoverageReport):
        self.causa = causa
        self.explicacion = explicacion
        self.cobertura = cobertura
        # «reunir» y no «descargar»: con media caché poblada, la mayoría de esas
        # empresas salieron de disco sin una sola petición. Este módulo se apoya
        # en que un acierto de caché no prueba que la SEC responda; llamarlos
        # descargas en el mensaje de aborto lo contradiría.
        super().__init__(
            f"{explicacion} Se abortó tras reunir "
            f"{len(cobertura.included)} de {len(cobertura.requested)} empresas."
        )


def _sin_fuente(racha: int, desconocidos: int, fallo: Fallo) -> str:
    """Por qué se abortó, diagnosticando sobre la racha entera y no sobre su
    último fallo.

    Decidir por el último manda al usuario al sitio equivocado en cuanto la
    racha mezcla causas, y mezclarlas es fácil: `unknown` sale por empresa de un
    `to_dataframe()` sobre un payload malformado, así que unos pocos tickers
    malos repartidos por el universo se entrelazan con los timeouts de una
    caída. Medido sobre la implementación anterior: nueve errores nuestros y un
    timeout final le decían al usuario que revisara una conexión que funciona, y
    nueve timeouts con un error nuestro al final le decían que el programa
    estaba roto en mitad de una caída de la SEC.

    Con tres textos, el mensaje no afirma más de lo que la evidencia sostiene.
    """
    # «el último fallo» y no el detalle a secas: un «(ConnectTimeout)» pelado se
    # lee como si caracterizara los diez fallos, y sólo caracteriza uno. Lleva
    # «fallo» explícito porque sin él el texto sólo funciona en la rama
    # all-unknown («errores... el último») -- en la pura SEC el sustantivo más
    # cercano es «datos» (leería «el último dato») y en la mixta es «la red»
    # (leería «el último de la red» en vez de el último de los diez).
    ultimo = f"el último fallo, {fallo.detalle}"
    if desconocidos == racha:
        return (
            f"{racha} empresas seguidas fallaron con errores que este programa "
            f"no sabe interpretar ({ultimo}). No apunta a la SEC ni a tu "
            "conexión: lo más probable es que sea un fallo del propio programa. "
            "La corrida se para aquí en vez de repetirlo 503 veces."
        )
    if desconocidos == 0:
        # «sin entregar datos» y no «sin contestar»: la racha también avanza con
        # un 5xx, que técnicamente es una respuesta. Decir «no contestó» delante
        # de un «(HTTP 503)» sería contradecirse en la misma frase.
        return (
            f"{racha} empresas seguidas fallaron sin que la SEC entregara datos "
            f"({ultimo}). No es que fallen esas empresas: es que no hay fuente. "
            "Comprueba tu conexión y si data.sec.gov responde."
        )
    # La rama mixta no puede decir «sin entregar datos» de las dos partes: la
    # mitad `unknown` es justo lo contrario, un to_dataframe() que falló sobre
    # un cuerpo que la SEC sí entregó. Y termina diciendo qué hacer, no que el
    # programa no puede decidir: comprobar la conexión es gratis e instantáneo,
    # así que va primero; culpar al programa sólo se justifica una vez que esa
    # comprobación sale limpia.
    sin_interpretar = (
        "un error que este programa no sabe interpretar"
        if desconocidos == 1
        else "errores que este programa no sabe interpretar"
    )
    return (
        f"{racha} empresas seguidas fallaron por causas mezcladas: "
        f"{desconocidos} con {sin_interpretar} y {racha - desconocidos} de la "
        f"SEC o de la red ({ultimo}). Comprueba primero tu conexión y si "
        "data.sec.gov responde; si van bien, es un fallo del propio programa."
    )
```

- [ ] **Step 4: Añadir el cortacircuitos a `load_facts`**

Sustituye el bucle de `load_facts` por:

```python
    racha = 0

    for ticker in tickers:
        intento = _load_one(ticker, cache_dir, refresh)

        if intento.fallo is None:
            hechos[ticker] = (
                intento.facts if intento.facts is not None else pd.DataFrame()
            )
            cobertura.included.append(ticker)
            if not intento.desde_cache:
                racha = 0
            continue

        fallo = intento.fallo
        _anotar(cobertura, ticker, fallo)

        if fallo.aborta:
            raise CorridaAbortada(fallo.causa, fallo.explicacion, cobertura)
        if fallo.fuente_viva:
            racha = 0
            continue
        if not fallo.cuenta_racha:
            continue

        racha += 1
        if fallo.causa == UNKNOWN:
            desconocidos += 1
        if racha >= RACHA_MAXIMA:
            raise CorridaAbortada(
                fallo.causa, _sin_fuente(racha, desconocidos, fallo), cobertura
            )
```

`desconocidos` se declara junto a `racha` (`racha = desconocidos = 0`) y se
reinicia con ella en los dos mismos sitios. Va aparte y no dentro de `Fallo`
porque es una propiedad de la racha, no del fallo suelto.

Y amplía el docstring de `load_facts` con el invariante nuevo:

```python
    """Download SEC's long fact table per ticker, caching each to disk.

    `refresh` re-downloads even when a cache entry exists. It defaults to False
    on purpose: quarterly reports arrive staggered, and a cache that refreshed
    itself would change the numbers between two runs without anyone asking. Like
    the universe snapshot, refreshing is a deliberate act.

    Un ticker que falla se registra y se salta. Que fallen todos por la misma
    causa no es un ticker que falla: es que no hay fuente, y entonces levanta
    `CorridaAbortada` en vez de recorrer el universo entero para no devolver
    nada. La racha se reinicia cuando la SEC entrega datos —un acierto de red o
    un 404, que también exigió preguntar—, avanza cuando preguntamos y no los
    entregó, y no se toca cuando no llegamos a preguntar: un acierto de caché o
    un CIK que resuelve contra el parquet local.
    """
```

- [ ] **Step 5: Correr la suite entera**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py && git commit -m "feat: abortar cuando fallan diez seguidos sin respuesta de la SEC"
```

---

## Task 6: El tope de tiempo

**Files:**
- Modify: `fundamentals/fetch.py` (`load_facts`)
- Test: `tests/test_fundamentals_fetch.py`

La racha sola no acota el caso «SEC colgada»: con un read timeout de 30 s y 5
intentos de stamina, cada ticker cuesta ~2,7 min, y diez son 27 minutos.

- [ ] **Step 1: Escribir los tests que fallan**

Añade `SIN_RESPUESTA_MAXIMO` al import de `fundamentals.fetch` que dejaste
preparado en el Task 5, y los tests al final del fichero:

```python
def test_el_tope_de_tiempo_aborta_aunque_no_se_llegue_a_la_racha(cache_dir):
    """La SEC colgada: pocos tickers, mucho tiempo. La racha sola no lo acota."""
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ReadTimeout("colgada")
    ) as pedido, patch(
        "fundamentals.fetch.time.monotonic",
        side_effect=[0.0, SIN_RESPUESTA_MAXIMO + 1.0],
    ):
        with pytest.raises(CorridaAbortada) as abortada:
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
    assert pedido.call_count == 2
    assert "180" in str(abortada.value)


def test_una_corrida_entera_desde_cache_no_aborta_por_tiempo(cache_dir):
    """El reloj arranca en el primer fallo de red; sin red no hay reloj."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=_facts):
        load_facts(["AAA", "BBB"], cache_dir=cache_dir)

    with patch("fundamentals.fetch._fetch_facts") as ninguna, patch(
        "fundamentals.fetch.time.monotonic", return_value=99_999.0
    ):
        _, cobertura = load_facts(["AAA", "BBB"], cache_dir=cache_dir)
    assert ninguna.call_count == 0
    assert cobertura.included == ["AAA", "BBB"]


def test_un_exito_de_red_reinicia_el_reloj(cache_dir):
    """Si la SEC vuelve, el tiempo que estuvo caida no cuenta contra la corrida."""
    def falla_salvo_el_segundo(ticker):
        if ticker == "T001":
            return _facts(ticker)
        raise httpx.ReadTimeout("colgada")

    # T000 falla (reloj a 0), T001 acierta (reloj a None), T002 falla (reloj a 0
    # otra vez pese al salto), T003 falla ya pasado el tope.
    reloj = [0.0, 500.0, 500.0 + SIN_RESPUESTA_MAXIMO + 1.0]
    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_salvo_el_segundo), \
         patch("fundamentals.fetch.time.monotonic", side_effect=reloj):
        with pytest.raises(CorridaAbortada):
            load_facts([f"T{i:03d}" for i in range(20)], cache_dir=cache_dir)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_fundamentals_fetch.py -q -k "tope_de_tiempo or desde_cache_no_aborta or reinicia_el_reloj"
```

Esperado: FAIL con `NameError: name 'SIN_RESPUESTA_MAXIMO' is not defined`.

- [ ] **Step 3: Añadir la constante y el mensaje**

Junto a `RACHA_MAXIMA` en `fundamentals/fetch.py`:

```python
# Un conteo solo no acota el caso «SEC colgada»: con un read timeout de 30 s y
# los 5 intentos de stamina, cada ticker cuesta ~2,7 min, y RACHA_MAXIMA de esos
# son 27 minutos — que es el problema que este módulo existe para no tener.
SIN_RESPUESTA_MAXIMO = 180.0
```

Y el mensaje, junto a `_sin_fuente`:

```python
def _sin_respuesta(fallo: Fallo) -> str:
    # Mismo cuidado que en _sin_fuente: el reloj también corre con 5xx, así que
    # «no entregó datos» y no «no contestó».
    #
    # Y no dice «en una sola petición», que sería falso por construcción: el
    # reloj arranca en el primer fallo contado con delta 0, así que el tope no
    # puede saltar antes del segundo. El tramo cubre siempre dos peticiones o
    # más, y puede cubrir cientos de lecturas de caché entre medias, porque los
    # aciertos de caché no tocan el reloj.
    return (
        f"Pasaron {SIN_RESPUESTA_MAXIMO:.0f} segundos sin que la SEC entregara "
        f"datos (el último fallo, {fallo.detalle}). Comprueba tu conexión y si "
        "data.sec.gov responde."
    )
```

- [ ] **Step 4: Añadir el reloj a `load_facts`**

**Cuidado con esto:** el bucle ya lleva un contador `desconocidos` en paralelo a
`racha`, que se declara y se reinicia con ella en los mismos tres sitios. Los
bloques de abajo lo conservan. Borrarlo deshace el diagnóstico por racha entera
y cuatro tests se ponen en rojo; si eso pasa, es señal de haber pegado una
versión vieja, no de que los tests estén mal.

Declara el reloj junto a los dos contadores:

```python
    racha = desconocidos = 0
    sin_respuesta_desde: float | None = None
```

Reinícialo en los dos sitios donde ya se reinician los contadores:

```python
            if not intento.desde_cache:
                racha = desconocidos = 0
                sin_respuesta_desde = None
```

```python
        if fallo.fuente_viva:
            racha = desconocidos = 0
            sin_respuesta_desde = None
            continue
```

Y sustituye el bloque final del bucle:

```python
        racha += 1
        if fallo.causa == UNKNOWN:
            desconocidos += 1
        ahora = time.monotonic()
        if sin_respuesta_desde is None:
            sin_respuesta_desde = ahora
        if racha >= RACHA_MAXIMA:
            raise CorridaAbortada(
                fallo.causa, _sin_fuente(racha, desconocidos, fallo), cobertura
            )
        if ahora - sin_respuesta_desde >= SIN_RESPUESTA_MAXIMO:
            raise CorridaAbortada(fallo.causa, _sin_respuesta(fallo), cobertura)
```

El orden importa: `time.monotonic()` se llama **una vez por fallo contado**, y
los tests del tope de tiempo parchean esa llamada con una lista de valores. Si
se llama dos veces, o si se llama también en las ramas que no cuentan racha, la
lista se agota y el test revienta con `StopIteration` en vez de con lo que
mide.

`time` ya está importado en el fichero; ahora se usa para `monotonic` en vez de
para `sleep`.

No lo compruebes con `grep`: el docstring de `_load_one` menciona
`time.sleep(2.0**intento)` a propósito, explicando qué se quitó y por qué, así
que un `grep "time\."` da dos aciertos y uno es correcto. Lo que fija que no se
duerme es `test_no_se_duerme_entre_tickers`, y sobrevive a que alguien
reintroduzca la espera con otro nombre.

- [ ] **Step 5: Correr la suite entera**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/fetch.py tests/test_fundamentals_fetch.py && git commit -m "feat: tope de tiempo para la SEC que no cuelga la llamada pero no contesta"
```

---

## Task 7: Que la excepción llegue a la pantalla, y el invariante a los docstrings

**Files:**
- Modify: `pages/1_Revisar_candidatos.py:41-57` (`_generar`)
- Modify: `fundamentals/run.py` (docstring de `build_panel`)
- Modify: `ranking/run.py:77-81` (docstring de `construir_ranking`)
- Modify: `ranking/filings.py:115-123` (docstring de `cargar_riesgos`)
- Modify: `aprobacion/generacion.py:36-37` — dice que la mitad «Sin IA» «spends
  ~25 minutes retrying 503 tickers before failing outright». El Task 4 lo hizo
  falso: ya no hay reintentos ni esperas. Reescribir para que describa lo que
  pasa ahora, que es abortar con la causa.
- Modify: `tests/test_ranking_filings.py:82-83` — repite la enumeración de dos
  casillas («unresolved_cik y failed_download») que ahora son tres.

Ningún test cubre esta tarea: la página es Streamlit y no se prueba, y los otros
tres cambios son docstrings. Es la razón por la que va al final y sola.

- [ ] **Step 1: Que `_generar` atrape y pinte**

En `pages/1_Revisar_candidatos.py`, sustituye la función `_generar` entera:

```python
def _generar(con_ia: bool) -> None:
    """Run sub-project B and overwrite salidas/, then reload the page."""
    from fundamentals.fetch import CorridaAbortada
    from ranking.run import construir_ranking, guardar

    try:
        with st.spinner(
            "Generando candidatos"
            + (" y redactando fichas con IA" if con_ia else " sin IA")
            + "… puede tardar unos minutos. No cierres ni recargues."
        ):
            guardar(construir_ranking(con_llm=con_ia), "salidas")
    except CorridaAbortada as error:
        # Ni se limpia el estado ni se recarga: no se llegó a sobrescribir
        # salidas/, así que lo que el revisor tenga marcado sigue apuntando a la
        # lista que está viendo. Borrarlo aquí sería el defecto que arregló
        # cbe71a0, y encima castigaría al usuario por un fallo que no es suyo.
        st.error(str(error))
        return

    # Lo marcado antes se refiere a una lista que acaba de dejar de existir.
    for clave in [c for c in st.session_state if c.startswith("ok_")]:
        del st.session_state[clave]
    st.session_state.anadidos = []
    st.rerun()
```

- [ ] **Step 2: Enmendar el docstring de `build_panel`**

En `fundamentals/run.py`, sustituye la última línea del docstring de
`build_panel` — hoy dice:

```
    A company that fails is recorded and skipped; it never aborts the run.
```

por:

```
    A company that fails is recorded and skipped. All of them failing for the
    same cause is not a company failing: it means there is no source, and
    `load_facts` raises `CorridaAbortada` rather than walking the whole universe
    to return nothing.
```

- [ ] **Step 3: Enmendar el docstring de `construir_ranking`**

En `ranking/run.py`, sustituye:

```python
    """Panel in, ranked candidates out.

    A company that fails at any stage is recorded and skipped, never aborting
    the run — the same policy fundamentals already applies to downloads.
    """
```

por:

```python
    """Panel in, ranked candidates out.

    A company that fails at any stage is recorded and skipped — the same policy
    fundamentals applies to downloads. The one thing that does abort is
    `CorridaAbortada` from `fundamentals.fetch`, which is not a company failing
    but the source being gone; it is left to propagate on purpose, so the caller
    can say why instead of showing an empty ranking.
    """
```

- [ ] **Step 4: Enmendar el docstring de `cargar_riesgos`**

En `ranking/filings.py`, dentro del docstring de `cargar_riesgos`, sustituye:

```
    fundamentals/fetch.py:_load_one already treats its own two failure modes
    (unresolved_cik, failed_download) the same way — only successful results
    are written to disk.
```

por:

```
    fundamentals/fetch.py:_load_one already treats its own failure modes
    (unresolved_cik, no_facts, failed_download) the same way — only successful
    results are written to disk.
```

- [ ] **Step 5: Comprobar que la página importa sin errores**

```bash
uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('pages/1_Revisar_candidatos.py').read_text(encoding='utf-8')); print('sintaxis ok')"
```

Esperado: `sintaxis ok`.

```bash
uv run python -c "from fundamentals.fetch import CorridaAbortada; print(CorridaAbortada.__mro__[:2])"
```

Esperado: `(<class 'fundamentals.fetch.CorridaAbortada'>, <class 'RuntimeError'>)`.

- [ ] **Step 6: Correr la suite entera**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo pasa.

- [ ] **Step 7: Commit**

```bash
git add pages/1_Revisar_candidatos.py fundamentals/run.py ranking/run.py ranking/filings.py && git commit -m "feat: decir por que se aborto, en vez de dejar la pagina en blanco"
```

---

## Verificación final

- [ ] **Suite completa, sin red**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: el total de la línea base (618 según `CONTEXTO.md`, más los tests
nuevos), 0 fallos, 2 omitidos en Windows.

- [ ] **Que no quede ni un `sleep` ni un `max_retries` en el módulo**

Un `grep` no sirve aquí: el docstring de `_load_one` menciona los dos a
propósito, explicando qué se quitó y por qué, y esa línea tiene que quedarse.
Los `.pyc` de `__pycache__` también acertarían. Se comprueba el comportamiento:

```bash
uv run python -c "import inspect; from fundamentals import fetch; assert 'max_retries' not in inspect.signature(fetch.load_facts).parameters; assert 'max_retries' not in inspect.signature(fetch._load_one).parameters; print('sin max_retries en las firmas')"
```

Esperado: `sin max_retries en las firmas`.

Que no se duerma ya lo fija `test_no_se_duerme_entre_tickers`, que es mejor
guarda que un `grep`: sobrevive a que alguien reintroduzca la espera con otro
nombre.

- [ ] **Que `research/loader.py` siga con el suyo intacto** (era otro módulo, fuera de alcance)

```bash
grep -c "max_retries" research/loader.py
```

Esperado: `4`.

- [ ] **Actualizar `CONTEXTO.md`** con el número de tests nuevo y una línea sobre
  el cortacircuitos, en la sección que corresponda.

---

## Notas para quien lo ejecute

**El orden importa dentro de `clasificar`.** Tiene su propio test
(`test_una_identidad_rechazada_no_es_un_fallo_transitorio`) porque el fallo es
silencioso: si se reordena, un `SECIdentityError` sale `transient`, la corrida no
aborta, y volvemos a los 25 minutos sin que ningún otro test se entere.

**No actives `EDGARTOOLS_STRICT_ERRORS`.** Existe y adelanta el comportamiento de
la 6.0, pero también haría levantar los `None` de `ranking/filings.py:_descargar`,
que son contrato deliberado de esa función.

**Si un test del cortacircuitos cuelga**, es que un doble de `_fetch_facts` está
llegando a la red de verdad. Todos los tests de este plan parchean
`fundamentals.fetch._fetch_facts` o `edgar.Company`; ninguno debe tocar
data.sec.gov.
