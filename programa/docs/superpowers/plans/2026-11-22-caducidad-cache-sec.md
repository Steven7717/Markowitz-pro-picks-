# Caducidad de la caché de la SEC — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `load_facts` vuelva a pedir a la SEC los ficheros de caché que probablemente tienen un informe nuevo, sin perder empresas ni abortar corridas cuando la SEC no contesta, y que la pantalla de Candidatos diga hasta cuándo llegan los datos.

**Architecture:** La regla de caducidad (dos funciones puras) vive en `fundamentals/fetch.py`. `_load_one` la aplica y, si una descarga de un caducado falla, devuelve el fichero viejo junto con el fallo. `load_facts` cuenta ese fallo para los cortacircuitos, pero en vez de abortar entra en «modo sin red» para los caducados. `CoverageReport` anota qué se actualizó, qué se sirvió caducado y la fecha de descarga de cada empresa. `ranking/run.py` lo resume en `corrida["datos_sec"]` y `aprobacion/carga.py` lo convierte en la línea que pinta `vistas/candidatos.py`.

**Tech Stack:** Python 3.12, pandas 2.x, pytest, Streamlit `AppTest`.

**Spec:** `docs/superpowers/specs/2026-11-22-caducidad-cache-sec-design.md`

**Cómo correr los tests:** desde `programa/`, con `.venv/Scripts/python -m pytest <ruta> -q`.

---

## Mapa de ficheros

| Fichero | Qué cambia |
|---|---|
| `fundamentals/fetch.py` | Constantes, `ultimo_cierre`, `caducado`, campos nuevos de `Intento` y `CoverageReport`, `_load_one` con `hoy` y `sin_red`, `load_facts` con `hoy` y el modo sin red, `resumen_datos_sec` |
| `ranking/run.py` | `corrida["datos_sec"]` |
| `aprobacion/carga.py` | `linea_datos_sec(corrida)` |
| `vistas/candidatos.py` | Pinta la línea debajo del resumen |
| `tests/test_fundamentals_caducidad.py` | **Nuevo.** Regla, `_load_one`, `load_facts` y `resumen_datos_sec` |
| `tests/test_ranking_run.py` | Un test del bloque `datos_sec` |
| `tests/test_aprobacion_carga.py` | Tests de `linea_datos_sec` |
| `tests/test_pantalla_candidatos_datos_sec.py` | **Nuevo.** La línea en la pantalla |

---

### Task 1: La regla de caducidad, como funciones puras

**Files:**
- Modify: `fundamentals/fetch.py` (imports, constantes tras `SIN_RESPUESTA_MAXIMO`)
- Create: `tests/test_fundamentals_caducidad.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_fundamentals_caducidad.py`:

```python
"""La caducidad de la caché de la SEC: sub-proyecto Q.

`hoy` se pasa siempre a mano y el `mtime` de los ficheros se fija con
`os.utime`: ningún test depende del reloj real.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
import pytest

from fundamentals.fetch import (
    DIAS_ENTRE_COMPROBACIONES,
    DIAS_HASTA_INFORME_NUEVO,
    RACHA_MAXIMA,
    CorridaAbortada,
    _cache_path,
    caducado,
    load_facts,
    ultimo_cierre,
)

CIERRE = date(2025, 12, 31)


def _facts(ticker: str = "AAA", n: int = 12, ultimo: date = CIERRE) -> pd.DataFrame:
    """Tabla larga con la forma de facts.to_dataframe(); el último trimestre cierra en `ultimo`."""
    fechas = pd.date_range(end=pd.Timestamp(ultimo), periods=n, freq="QE")
    return pd.DataFrame(
        {
            "concept": ["us-gaap:Revenues"] * n,
            "value": [str(100.0 + i) for i in range(n)],
            "numeric_value": [100.0 + i for i in range(n)],
            "unit": ["USD"] * n,
            "period_type": ["duration"] * n,
            "period_start": fechas - pd.Timedelta(days=89),
            "period_end": fechas,
            "fiscal_year": [f.year for f in fechas],
            "fiscal_period": [f"Q{(f.month - 1) // 3 + 1}" for f in fechas],
        }
    )


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _envejecer(cache_dir: Path, ticker: str, dias: int, hoy: date) -> None:
    """Pone el mtime del fichero de `ticker` a `dias` días antes de `hoy`."""
    momento = datetime.combine(hoy - timedelta(days=dias), datetime.min.time()).timestamp()
    os.utime(_cache_path(cache_dir, ticker), (momento, momento))


# --- La regla ---------------------------------------------------------------


def test_las_constantes_son_las_del_spec():
    assert DIAS_HASTA_INFORME_NUEVO == 75
    assert DIAS_ENTRE_COMPROBACIONES == 7


def test_el_ultimo_cierre_es_el_period_end_mas_reciente():
    assert ultimo_cierre(_facts()) == CIERRE


def test_el_ultimo_cierre_ignora_filas_sin_periodo_trimestral_ni_anual():
    facts = _facts()
    rara = facts.iloc[[0]].copy()
    rara["period_end"] = pd.Timestamp("2030-01-01")
    rara["fiscal_period"] = None
    assert ultimo_cierre(pd.concat([facts, rara])) == CIERRE


def test_el_ultimo_cierre_cuenta_el_anual():
    facts = _facts()
    anual = facts.iloc[[0]].copy()
    anual["period_end"] = pd.Timestamp("2026-03-31")
    anual["fiscal_period"] = "FY"
    assert ultimo_cierre(pd.concat([facts, anual])) == date(2026, 3, 31)


def test_sin_cierre_medible_el_ultimo_cierre_es_none():
    assert ultimo_cierre(pd.DataFrame()) is None
    assert ultimo_cierre(_facts().assign(fiscal_period=None)) is None


@pytest.mark.parametrize(
    "dias_desde_cierre, dias_desde_descarga, esperado",
    [
        (74, 8, False),  # aún no toca informe nuevo
        (76, 6, False),  # se preguntó hace poco
        (76, 8, True),   # las dos condiciones
        (75, 8, False),  # el borde no cuenta: «más de 75»
        (76, 7, False),  # el borde no cuenta: «más de 7»
    ],
)
def test_caduca_solo_con_las_dos_condiciones(dias_desde_cierre, dias_desde_descarga, esperado):
    hoy = CIERRE + timedelta(days=dias_desde_cierre)
    descargado_el = hoy - timedelta(days=dias_desde_descarga)
    assert caducado(_facts(), descargado_el, hoy) is esperado


def test_un_fichero_sin_cierre_medible_no_caduca():
    hoy = CIERRE + timedelta(days=400)
    assert caducado(pd.DataFrame(), hoy - timedelta(days=30), hoy) is False
```

- [ ] **Step 2: Correrlos para ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py -q`
Expected: FAIL con `ImportError: cannot import name 'DIAS_ENTRE_COMPROBACIONES'`

- [ ] **Step 3: Implementar**

En `fundamentals/fetch.py`, cambiar los imports del principio a:

```python
import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
```

y añadir, justo después de la línea `SIN_RESPUESTA_MAXIMO = 180.0`:

```python

# **Sub-proyecto Q, 2026-11-22: la caché caduca.** Hasta aquí un fichero de
# `.cache` no se volvía a pedir nunca: `refresh=False` era el valor por defecto
# y ninguna pantalla pedía `refresh=True`. Medido ese día, los 503 ficheros eran
# del 2026-08-30 y el ranking no veía ningún 10-Q del tercer trimestre.
#
# Un fichero se vuelve a pedir cuando las dos cosas son ciertas:
#   - su último cierre de periodo tiene más de DIAS_HASTA_INFORME_NUEVO días. Un
#     10-Q se presenta en los 40-45 días siguientes al cierre y un 10-K en
#     60-90: 75 cubre el 10-Q de cualquier empresa sin ir antes de tiempo.
#   - el fichero se escribió hace más de DIAS_ENTRE_COMPROBACIONES días. Sin
#     esto, una empresa que se retrasa en presentar se pediría en cada corrida;
#     con esto, como mucho una vez por semana.
# El razonamiento entero está en
# docs/superpowers/specs/2026-11-22-caducidad-cache-sec-design.md.
DIAS_HASTA_INFORME_NUEVO = 75
DIAS_ENTRE_COMPROBACIONES = 7

_PERIODOS_FISCALES = frozenset({"Q1", "Q2", "Q3", "Q4", "FY"})


def ultimo_cierre(facts: pd.DataFrame) -> "date | None":
    """El cierre de periodo más reciente del fichero, o None si no hay ninguno medible.

    Solo cuentan las filas trimestrales o anuales (`fiscal_period` en Q1-Q4/FY):
    los hechos del documento (`dei:*`) traen fechas que no son cierres y alguna
    va por delante del calendario.
    """
    if facts.empty or not {"period_end", "fiscal_period"} <= set(facts.columns):
        return None
    filas = facts[facts["fiscal_period"].isin(_PERIODOS_FISCALES)]
    fechas = pd.to_datetime(filas["period_end"], errors="coerce").dropna()
    return None if fechas.empty else fechas.max().date()


def caducado(facts: pd.DataFrame, descargado_el: date, hoy: date) -> bool:
    """Si toca volver a pedir este fichero a la SEC.

    Un fichero sin cierre medible no caduca: no hay forma de saber si existe un
    informe nuevo, y pedirlo cada semana no lo arreglaría.
    """
    cierre = ultimo_cierre(facts)
    if cierre is None:
        return False
    return (hoy - cierre).days > DIAS_HASTA_INFORME_NUEVO and (
        hoy - descargado_el
    ).days > DIAS_ENTRE_COMPROBACIONES
```

- [ ] **Step 4: Correrlos para ver que pasan**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add programa/fundamentals/fetch.py programa/tests/test_fundamentals_caducidad.py
git commit -m "feat(fetch): la regla de caducidad de la caché de la SEC"
```

---

### Task 2: `_load_one` vuelve a pedir los caducados y, si falla, sirve el viejo

**Files:**
- Modify: `fundamentals/fetch.py` — `CoverageReport`, `Intento`, `_load_one`
- Test: `tests/test_fundamentals_caducidad.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_fundamentals_caducidad.py`:

```python
# --- Un ticker ---------------------------------------------------------------

HOY = CIERRE + timedelta(days=90)  # el cierre tiene 90 días: más de 75


def _sembrar(cache_dir: Path, tickers, dias: int = 10, hoy: date = HOY) -> None:
    """Escribe en caché los `tickers` y los envejece `dias` días."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)):
        load_facts(list(tickers), cache_dir=cache_dir, hoy=hoy)
    for ticker in tickers:
        _envejecer(cache_dir, ticker, dias, hoy)


def test_un_fichero_reciente_se_sirve_sin_red(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=3)
    with patch("fundamentals.fetch._fetch_facts") as red:
        _, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    red.assert_not_called()
    assert cobertura.included == ["AAA"]
    assert cobertura.actualizadas == []
    assert cobertura.servidas_caducadas == []


def test_un_fichero_caducado_se_vuelve_a_pedir_y_se_reescribe(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=10)
    nuevo = _facts(ultimo=date(2026, 3, 31))
    with patch("fundamentals.fetch._fetch_facts", return_value=nuevo) as red:
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    red.assert_called_once_with("AAA")
    assert ultimo_cierre(hechos["AAA"]) == date(2026, 3, 31)
    assert cobertura.actualizadas == ["AAA"]
    assert cobertura.descargado_el["AAA"] == HOY.isoformat()


def test_un_caducado_cuya_descarga_falla_se_sirve_desde_la_cache(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")):
        hechos, cobertura = load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert ultimo_cierre(hechos["AAA"]) == CIERRE
    assert cobertura.included == ["AAA"]
    assert cobertura.servidas_caducadas == ["AAA"]
    assert cobertura.failed_download == []
    assert cobertura.descargado_el["AAA"] == (HOY - timedelta(days=10)).isoformat()


def test_un_caducado_que_falla_no_toca_el_fichero(cache_dir):
    """Sin mtime nuevo, la próxima corrida lo vuelve a intentar."""
    _sembrar(cache_dir, ["AAA"], dias=10)
    antes = _cache_path(cache_dir, "AAA").stat().st_mtime
    with patch("fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("x")):
        load_facts(["AAA"], cache_dir=cache_dir, hoy=HOY)
    assert _cache_path(cache_dir, "AAA").stat().st_mtime == antes


def test_refresh_sigue_forzando_la_descarga_de_un_fichero_reciente(cache_dir):
    _sembrar(cache_dir, ["AAA"], dias=1)
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)) as red:
        load_facts(["AAA"], cache_dir=cache_dir, refresh=True, hoy=HOY)
    red.assert_called_once()


def test_sin_hoy_se_usa_la_fecha_de_hoy(cache_dir):
    """Un fichero recién escrito no caduca con la fecha real."""
    with patch("fundamentals.fetch._fetch_facts", side_effect=lambda t: _facts(t)):
        load_facts(["AAA"], cache_dir=cache_dir)
    with patch("fundamentals.fetch._fetch_facts") as red:
        load_facts(["AAA"], cache_dir=cache_dir)
    red.assert_not_called()
```

- [ ] **Step 2: Correrlos para ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py -q`
Expected: FAIL con `TypeError: load_facts() got an unexpected keyword argument 'hoy'`

- [ ] **Step 3: Implementar los campos nuevos**

En `CoverageReport`, justo después de `failed_price_download: list[str] = field(default_factory=list)`, añadir:

```python
    # Sub-proyecto Q. `actualizadas`: las que se bajaron de la SEC en esta
    # corrida, nuevas o caducadas. `servidas_caducadas`: caducadas que se
    # sirvieron desde el fichero viejo porque la SEC no las entregó; siguen en
    # `included`, porque tienen datos. `descargado_el`: la fecha (ISO) en que se
    # escribió el fichero de cada incluida, que es de cuándo son sus cifras.
    actualizadas: list[str] = field(default_factory=list)
    servidas_caducadas: list[str] = field(default_factory=list)
    descargado_el: dict[str, str] = field(default_factory=dict)
```

En `summary()`, cambiar la última línea del f-string:

```python
            f"precio no descargado: {len(self.failed_price_download)} | "
            f"servidas sin actualizar: {len(self.servidas_caducadas)}"
        )
```

Sustituir la clase `Intento` entera por:

```python
@dataclass(frozen=True)
class Intento:
    """Qué salió de pedir un ticker, y de dónde salió.

    Lo normal es exactamente uno de los dos: si hay hechos no hay fallo, y al
    revés. La excepción, desde el sub-proyecto Q, es un fichero caducado cuya
    nueva descarga falló: trae los hechos viejos **y** el fallo, con
    `caducado=True`. Los hechos dicen que la empresa entra; el fallo, que se
    preguntó a la SEC y no los entregó, y por tanto cuenta para los
    cortacircuitos de `load_facts`.

    `desde_cache` no es instrumentación: es lo que impide que un fichero leído
    de disco cuente como prueba de que la SEC responde. Sin ese dato, una caché
    a medio poblar apagaría los dos cortacircuitos de `load_facts` -- el de
    racha y el de tiempo, que comparten el mismo reinicio.

    `segundos_de_red` es lo que tardó la petición, y sólo la petición. El tope
    de tiempo lo suma en vez de mirar el reloj de pared porque son cosas
    distintas: con 500 tickers en caché entre dos fallos, el reloj de pared
    marca minutos que la corrida pasó leyendo parquet productivamente, y
    abortaba una corrida sana culpando a la conexión. Un acierto de caché aporta
    cero aquí, que es exactamente lo que aportó a la espera.

    `descargado_el` es la fecha del fichero servido, o la de hoy si se acaba de
    bajar.
    """

    facts: pd.DataFrame | None
    fallo: Fallo | None
    desde_cache: bool = False
    segundos_de_red: float = 0.0
    caducado: bool = False
    descargado_el: "date | None" = None
```

Sustituir `_load_one` entera por:

```python
def _load_one(
    ticker: str, cache_dir: Path, refresh: bool, hoy: date, sin_red: bool = False
) -> Intento:
    """Un intento por ticker; el reintento de lo transitorio es de edgartools.

    Aquí había un bucle de `max_retries=3` con `time.sleep(2.0**intento)`. Se
    quitó porque no añadía intentos útiles y sí 3 s de espera por ticker: sobre
    503 tickers, esos 3 s eran los ~25 minutos que esta función tardaba en no
    devolver nada cuando la SEC rechazaba la identidad.

    edgartools ya reintenta 5 veces con backoff lo que mejora reintentando, y
    deja pasar al primer intento lo que no —429, SSL, identidad—, que es
    justamente lo que un bucle de fuera no puede distinguir.

    Un fichero caducado (`caducado`) se vuelve a pedir. Si la petición falla, se
    devuelve el fichero viejo junto con el fallo. Con `sin_red`, que
    `load_facts` activa cuando salta un cortacircuitos, un caducado se sirve
    directamente sin preguntar.
    """
    path = _cache_path(cache_dir, ticker)
    guardado = None
    if path.exists() and not refresh:
        try:
            guardado = pd.read_parquet(path)
        except Exception:
            # A run killed mid-write leaves a truncated file. Treat it as a miss
            # rather than letting it poison every future run.
            path.unlink(missing_ok=True)

    if guardado is not None:
        descargado_el = date.fromtimestamp(path.stat().st_mtime)
        viejo = caducado(guardado, descargado_el, hoy)
        if not viejo or sin_red:
            return Intento(
                guardado, None, desde_cache=True, caducado=viejo,
                descargado_el=descargado_el,
            )

    comenzo = _ahora()
    try:
        frame = _fetch_facts(ticker)
    except Exception as exc:
        segundos = _ahora() - comenzo
        if guardado is not None:
            return Intento(
                guardado, clasificar(exc), desde_cache=True, segundos_de_red=segundos,
                caducado=True, descargado_el=descargado_el,
            )
        return Intento(None, clasificar(exc), segundos_de_red=segundos)
    segundos = _ahora() - comenzo

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # SEC mixes types in the raw value column and parquet needs one per
    # column. astype's errors="ignore" does not cover a missing key — it
    # still raises KeyError — so the column is checked before casting.
    if "value" in frame.columns:
        frame = frame.astype({"value": "string"})
    frame.to_parquet(tmp)
    tmp.replace(path)  # atomic rename: a reader never sees a partial file
    return Intento(frame, None, segundos_de_red=segundos, descargado_el=hoy)
```

- [ ] **Step 4: Implementar lo mínimo en `load_facts` para que compile y anote**

Cambiar la firma y el principio de `load_facts`:

```python
def load_facts(
    tickers: list[str],
    cache_dir: Path | None = None,
    refresh: bool = False,
    hoy: "date | None" = None,
) -> tuple[dict[str, pd.DataFrame], CoverageReport]:
```

Justo después de `cache_dir = cache_dir or _DEFAULT_CACHE`, añadir:

```python
    hoy = hoy or date.today()
    sin_red = False
```

Sustituir el principio del bucle, desde `for ticker in tickers:` hasta el primer `continue` incluido, por:

```python
    for ticker in tickers:
        intento = _load_one(ticker, cache_dir, refresh, hoy, sin_red=sin_red)

        if intento.facts is not None:
            hechos[ticker] = intento.facts
            cobertura.included.append(ticker)
            if intento.descargado_el is not None:
                cobertura.descargado_el[ticker] = intento.descargado_el.isoformat()
            if intento.caducado:
                cobertura.servidas_caducadas.append(ticker)
            elif not intento.desde_cache:
                cobertura.actualizadas.append(ticker)

            if intento.fallo is None:
                if not intento.desde_cache:
                    racha = desconocidos = 0
                    segundos_perdidos = 0.0
                continue
            # Task 3 añade aquí lo que hace un caducado que falló con los
            # cortacircuitos.
            continue
```

- [ ] **Step 5: Correr los tests nuevos y los de siempre**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py tests/test_fundamentals_fetch.py -q`
Expected: PASS. Los de `test_fundamentals_fetch.py` siguen verdes: sus ficheros se escriben con el `mtime` de ahora, así que no caducan.

- [ ] **Step 6: Commit**

```bash
git add programa/fundamentals/fetch.py programa/tests/test_fundamentals_caducidad.py
git commit -m "feat(fetch): los ficheros caducados se vuelven a pedir y, si falla, se sirve el viejo"
```

---

### Task 3: Los cortacircuitos con caducados — modo sin red en vez de abortar

**Files:**
- Modify: `fundamentals/fetch.py` — el bucle de `load_facts` y su docstring
- Test: `tests/test_fundamentals_caducidad.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_fundamentals_caducidad.py`:

```python
# --- Los cortacircuitos ------------------------------------------------------


def test_sin_red_y_con_todo_caducado_la_corrida_no_aborta(cache_dir):
    """Con la caché llena y sin conexión, todas tienen datos: ninguna se pierde."""
    tickers = [f"T{i:03d}" for i in range(RACHA_MAXIMA + 5)]
    _sembrar(cache_dir, tickers, dias=10)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as red:
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert sorted(hechos) == tickers
    assert cobertura.servidas_caducadas == tickers
    # Tras saltar el cortacircuitos deja de preguntar.
    assert red.call_count == RACHA_MAXIMA


def test_una_identidad_rechazada_en_un_caducado_tampoco_aborta(cache_dir):
    from tests.test_fundamentals_fetch import _status

    tickers = ["AAA", "BBB", "CCC"]
    _sembrar(cache_dir, tickers, dias=10)
    with patch("fundamentals.fetch._fetch_facts", side_effect=_status(403)) as red:
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert sorted(hechos) == tickers
    assert cobertura.servidas_caducadas == tickers
    assert red.call_count == 1


def test_un_fallo_en_un_caducado_cuenta_para_la_racha(cache_dir):
    """Se preguntó a la red, así que cuenta. Tras los caducados, las que no
    tienen fichero abortan antes de llegar a RACHA_MAXIMA fallos propios."""
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    _sembrar(cache_dir, caducados, dias=10)
    nuevos = ["N001", "N002", "N003"]
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ) as red:
        with pytest.raises(CorridaAbortada) as error:
            load_facts(caducados + nuevos, cache_dir=cache_dir, hoy=HOY)
    assert red.call_count == RACHA_MAXIMA
    assert error.value.cobertura.failed_download == ["N001"]
    assert error.value.cobertura.servidas_caducadas == caducados


def test_en_modo_sin_red_una_empresa_sin_fichero_aborta_como_hoy(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA)]
    _sembrar(cache_dir, caducados, dias=10)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ):
        with pytest.raises(CorridaAbortada) as error:
            load_facts(caducados + ["NUEVO"], cache_dir=cache_dir, hoy=HOY)
    assert error.value.cobertura.failed_download == ["NUEVO"]


def test_en_modo_sin_red_los_recientes_siguen_saliendo_de_la_cache(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA)]
    _sembrar(cache_dir, caducados, dias=10)
    _sembrar(cache_dir, ["RECIENTE"], dias=1)
    with patch(
        "fundamentals.fetch._fetch_facts", side_effect=httpx.ConnectTimeout("sin red")
    ):
        hechos, cobertura = load_facts(
            caducados + ["RECIENTE"], cache_dir=cache_dir, hoy=HOY
        )
    assert "RECIENTE" in hechos
    assert "RECIENTE" not in cobertura.servidas_caducadas


def test_un_exito_tras_caducados_fallidos_reinicia_la_racha(cache_dir):
    caducados = [f"C{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    _sembrar(cache_dir, caducados, dias=10)

    def falla_salvo_ok(ticker):
        if ticker == "OK":
            return _facts(ticker)
        raise httpx.ConnectTimeout("sin red")

    tickers = caducados + ["OK"] + [f"N{i:03d}" for i in range(RACHA_MAXIMA - 1)]
    with patch("fundamentals.fetch._fetch_facts", side_effect=falla_salvo_ok):
        hechos, cobertura = load_facts(tickers, cache_dir=cache_dir, hoy=HOY)
    assert "OK" in hechos
    assert len(cobertura.failed_download) == RACHA_MAXIMA - 1
```

- [ ] **Step 2: Correrlos para ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py -q -k "cortacircuitos or sin_red or racha or identidad"`
Expected: FAIL. `test_sin_red_y_con_todo_caducado_la_corrida_no_aborta` hace 15 llamadas en vez de 10; `test_un_fallo_en_un_caducado_cuenta_para_la_racha` no aborta.

- [ ] **Step 3: Implementar**

En el bucle de `load_facts`, sustituir las dos líneas

```python
            # Task 3 añade aquí lo que hace un caducado que falló con los
            # cortacircuitos.
            continue
```

por:

```python
            # Un caducado cuya descarga falló: tiene datos, así que no se
            # pierde ni aborta. Pero se preguntó a la SEC, así que el fallo
            # avanza los cortacircuitos igual que cualquier otro. Cuando
            # saltan, en vez de abortar se deja de preguntar por los
            # caducados (`sin_red`). Las empresas sin fichero siguen
            # preguntando, y con la racha ya en el tope, su primer fallo
            # aborta, como antes de Q.
            fallo = intento.fallo
            if fallo.aborta:
                sin_red = True
                continue
            if fallo.fuente_viva:
                racha = desconocidos = 0
                segundos_perdidos = 0.0
                continue
            if not fallo.cuenta_racha:
                continue
            racha += 1
            if fallo.causa == UNKNOWN:
                desconocidos += 1
            segundos_perdidos += intento.segundos_de_red
            if racha >= RACHA_MAXIMA or segundos_perdidos >= SIN_RESPUESTA_MAXIMO:
                sin_red = True
            continue
```

En el docstring de `load_facts`, sustituir el primer párrafo tras la línea de resumen («`refresh` re-downloads even when…») por:

```python
    `refresh` re-downloads even when a cache entry exists. Without it, a cache
    entry is re-requested only when `caducado` says a new report is probably
    out (sub-proyecto Q). Before Q the cache never expired, on the theory that
    refreshing should be a deliberate act. But no screen ever asked for it, and
    the ranking ran on three-month-old data without anything saying so.
    Reproducibility now rests on `CoverageReport.descargado_el`: two runs that
    used files written on the same dates used the same figures.

    A stale entry whose re-download fails is served from disk and listed in
    `servidas_caducadas`. Its failure still advances the circuit breakers.
    When they trip, stale entries stop asking (`sin_red`) instead of aborting
    the run, because they have data. Only a ticker with no file can abort.
```

- [ ] **Step 4: Correr todo `fundamentals`**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py tests/test_fundamentals_fetch.py tests/test_fundamentals_run.py tests/test_valoracion_fundamentos.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add programa/fundamentals/fetch.py programa/tests/test_fundamentals_caducidad.py
git commit -m "feat(fetch): sin red, los caducados se sirven de la caché en vez de abortar"
```

---

### Task 4: `resumen_datos_sec` y el bloque `datos_sec` de `corrida.json`

**Files:**
- Modify: `fundamentals/fetch.py` (función nueva al final)
- Modify: `ranking/run.py` (import, `construir_ranking`)
- Test: `tests/test_fundamentals_caducidad.py`, `tests/test_ranking_run.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_fundamentals_caducidad.py`:

```python
# --- El resumen ---------------------------------------------------------------

from fundamentals.fetch import CoverageReport, resumen_datos_sec


def test_el_resumen_dice_hasta_cuando_y_cuantas_se_actualizaron():
    cobertura = CoverageReport(
        requested=["AAA", "BBB", "CCC"],
        included=["AAA", "BBB", "CCC"],
        actualizadas=["AAA"],
        servidas_caducadas=["CCC"],
        descargado_el={"AAA": "2026-11-22", "BBB": "2026-11-20", "CCC": "2026-08-30"},
    )
    assert resumen_datos_sec(cobertura, "2026Q3") == {
        "ultimo_trimestre": "2026Q3",
        "descarga_mas_antigua": "2026-08-30",
        "descarga_mas_reciente": "2026-11-22",
        "actualizadas": 1,
        "servidas_caducadas": 1,
    }


def test_sin_cobertura_no_hay_resumen():
    assert resumen_datos_sec(None, "2026Q3") is None


def test_sin_fechas_el_resumen_no_inventa_ninguna():
    resumen = resumen_datos_sec(CoverageReport(), None)
    assert resumen["descarga_mas_antigua"] is None
    assert resumen["descarga_mas_reciente"] is None
    assert resumen["ultimo_trimestre"] is None
```

Añadir al final de `tests/test_ranking_run.py`:

```python
def test_la_corrida_lleva_el_bloque_de_datos_de_la_sec():
    from fundamentals.fetch import CoverageReport

    panel, metadatos = panel_y_metadatos()
    cobertura = CoverageReport(
        included=list(metadatos.index),
        actualizadas=[metadatos.index[0]],
        descargado_el={t: "2026-11-22" for t in metadatos.index},
    )
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, cobertura)):
        corrida = construir_ranking(con_llm=False, con_valoracion=False).corrida
    assert corrida["datos_sec"]["ultimo_trimestre"] == str(panel["trimestre"].max())
    assert corrida["datos_sec"]["actualizadas"] == 1
    assert corrida["datos_sec"]["servidas_caducadas"] == 0


def test_sin_cobertura_la_corrida_lleva_datos_sec_nulo():
    panel, metadatos = panel_y_metadatos()
    with patch("ranking.run.build_panel", return_value=(panel, metadatos, None)):
        corrida = construir_ranking(con_llm=False, con_valoracion=False).corrida
    assert corrida["datos_sec"] is None
```

`panel_y_metadatos` es el constructor del panel sintético que ya existe en `tests/test_ranking_run.py` (línea ~41); devuelve `(panel, metadatos)`.

- [ ] **Step 2: Correrlos para ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py tests/test_ranking_run.py -q -k "resumen or datos_sec"`
Expected: FAIL con `ImportError: cannot import name 'resumen_datos_sec'`

- [ ] **Step 3: Implementar**

Al final de `fundamentals/fetch.py`:

```python
def resumen_datos_sec(
    cobertura: "CoverageReport | None", ultimo_trimestre: "str | None"
) -> "dict | None":
    """De cuándo son los datos de la SEC de una corrida, para `corrida.json`.

    `ultimo_trimestre` es el trimestre natural más reciente del panel. Lo pasa
    quien tiene el panel, porque la cobertura no lo sabe. Sin cobertura (los
    dobles de test de `build_panel` devuelven None) no hay nada que resumir.
    """
    if cobertura is None:
        return None
    fechas = sorted(cobertura.descargado_el.values())
    return {
        "ultimo_trimestre": ultimo_trimestre,
        "descarga_mas_antigua": fechas[0] if fechas else None,
        "descarga_mas_reciente": fechas[-1] if fechas else None,
        "actualizadas": len(cobertura.actualizadas),
        "servidas_caducadas": len(cobertura.servidas_caducadas),
    }
```

En `ranking/run.py`, añadir el import junto a los de `fundamentals`:

```python
from fundamentals.fetch import resumen_datos_sec
from fundamentals.run import build_panel
```

y en el diccionario `corrida={...}` de `construir_ranking`, justo después de `"macro": bloque_macro,`:

```python
            "datos_sec": resumen_datos_sec(
                cobertura if isinstance(cobertura, CoverageReport) else None,
                None if panel.empty else trimestre_max,
            ),
```

con `CoverageReport` importado en la misma línea del import anterior:

```python
from fundamentals.fetch import CoverageReport, resumen_datos_sec
```

El `isinstance` está ahí porque algunos dobles de test pasan un `MagicMock` o un objeto cualquiera como cobertura. Con un mock, `resumen_datos_sec` intentaría ordenar sus atributos y fallaría o devolvería basura. Además, `json.dumps(..., allow_nan=False)` de `guardar` rechaza lo que no sea JSON.

- [ ] **Step 4: Correr los tests**

Run: `.venv/Scripts/python -m pytest tests/test_fundamentals_caducidad.py tests/test_ranking_run.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add programa/fundamentals/fetch.py programa/ranking/run.py programa/tests/test_fundamentals_caducidad.py programa/tests/test_ranking_run.py
git commit -m "feat(ranking): corrida.json dice de cuándo son los datos de la SEC"
```

---

### Task 5: La línea de la pantalla

**Files:**
- Modify: `aprobacion/carga.py` (función nueva tras `resumen_corrida`)
- Modify: `vistas/candidatos.py:305` y su bloque de imports de `aprobacion.carga`
- Test: `tests/test_aprobacion_carga.py`
- Create: `tests/test_pantalla_candidatos_datos_sec.py`

- [ ] **Step 1: Escribir los tests de la función**

Añadir al final de `tests/test_aprobacion_carga.py`:

```python
from aprobacion.carga import linea_datos_sec

DATOS_SEC = {
    "ultimo_trimestre": "2026Q3",
    "descarga_mas_antigua": "2026-11-20",
    "descarga_mas_reciente": "2026-11-22",
    "actualizadas": 41,
    "servidas_caducadas": 0,
}


def test_la_linea_dice_hasta_que_trimestre_y_cuantas_se_actualizaron():
    texto, aviso = linea_datos_sec({**CORRIDA, "datos_sec": DATOS_SEC})
    assert texto == (
        "Datos de la SEC hasta el 3T 2026 · 41 empresas actualizadas en esta "
        "corrida · 0 servidas sin actualizar."
    )
    assert aviso is False


def test_con_servidas_caducadas_la_linea_es_un_aviso_y_dice_por_que():
    datos = {**DATOS_SEC, "servidas_caducadas": 12, "descarga_mas_antigua": "2026-08-30"}
    texto, aviso = linea_datos_sec({**CORRIDA, "datos_sec": datos})
    assert aviso is True
    assert "12 servidas sin actualizar" in texto
    assert "la SEC no respondió" in texto
    assert "2026-08-30" in texto


def test_en_singular_con_una_empresa():
    texto, _ = linea_datos_sec({**CORRIDA, "datos_sec": {**DATOS_SEC, "actualizadas": 1}})
    assert "1 empresa actualizada en esta corrida" in texto


def test_sin_bloque_no_hay_linea():
    assert linea_datos_sec(CORRIDA) is None
    assert linea_datos_sec(None) is None
    assert linea_datos_sec({**CORRIDA, "datos_sec": None}) is None


def test_sin_trimestre_lo_dice():
    texto, _ = linea_datos_sec(
        {**CORRIDA, "datos_sec": {**DATOS_SEC, "ultimo_trimestre": None}}
    )
    assert texto.startswith("Datos de la SEC sin trimestre conocido")
```

- [ ] **Step 2: Correrlos para ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_aprobacion_carga.py -q -k linea`
Expected: FAIL con `ImportError: cannot import name 'linea_datos_sec'`

- [ ] **Step 3: Implementar la función**

En `aprobacion/carga.py`, justo después de la función `resumen_corrida`:

```python
def _trimestre_en_castellano(trimestre: "str | None") -> str:
    """'2026Q3' -> 'hasta el 3T 2026'. Un formato inesperado se dice tal cual."""
    if not trimestre:
        return "sin trimestre conocido"
    partes = re.fullmatch(r"(\d{4})Q([1-4])", str(trimestre))
    if partes is None:
        return f"hasta «{trimestre}»"
    return f"hasta el {partes.group(2)}T {partes.group(1)}"


def linea_datos_sec(corrida: "dict | None") -> "tuple[str, bool] | None":
    """De cuándo son los datos de la SEC, en una línea, y si hay que avisar.

    Sub-proyecto Q. Devuelve (texto, es_aviso), o None si la corrida es
    anterior a Q y no trae el bloque. Es aviso cuando alguna empresa se sirvió
    con sus cifras viejas porque la SEC no contestó: el revisor decide sobre
    esas cifras, y tiene que saberlo.
    """
    datos = (corrida or {}).get("datos_sec")
    if not isinstance(datos, dict):
        return None
    actualizadas = datos.get("actualizadas", 0)
    caducadas = datos.get("servidas_caducadas", 0)
    partes = [
        f"Datos de la SEC {_trimestre_en_castellano(datos.get('ultimo_trimestre'))}",
        (
            "1 empresa actualizada en esta corrida"
            if actualizadas == 1
            else f"{actualizadas} empresas actualizadas en esta corrida"
        ),
        f"{caducadas} servidas sin actualizar",
    ]
    texto = " · ".join(partes)
    if not caducadas:
        return texto + ".", False
    antigua = datos.get("descarga_mas_antigua")
    return (
        texto
        + ": la SEC no respondió al pedir sus informes nuevos, así que sus cifras son "
        + "las de su última descarga"
        + (f" (la más antigua, del {antigua})." if antigua else "."),
        True,
    )
```

Añadir `import re` a los imports de `aprobacion/carga.py`, que hoy empiezan por `import json`. No hace falta pandas.

- [ ] **Step 4: Correr los tests de la función**

Run: `.venv/Scripts/python -m pytest tests/test_aprobacion_carga.py -q`
Expected: PASS

- [ ] **Step 5: Escribir el test de la pantalla**

Crear `tests/test_pantalla_candidatos_datos_sec.py`:

```python
"""La línea de los datos de la SEC en «Revisar candidatos» (sub-proyecto Q),
ejecutada con `AppTest` y sin red. Monta la pantalla igual que
`test_pantalla_candidatos_macro.py`."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from aprobacion import carga

RAIZ = Path(__file__).resolve().parent.parent
GUION = str(Path(__file__).resolve().parent / "guion_vista.py")
DATOS_SEC = {
    "ultimo_trimestre": "2026Q3",
    "descarga_mas_antigua": "2026-08-30",
    "descarga_mas_reciente": "2026-11-22",
    "actualizadas": 41,
    "servidas_caducadas": 0,
}


def _pantalla(monkeypatch, tmp_path, datos_sec):
    destino = tmp_path / "salidas"
    shutil.copytree(RAIZ / "salidas_ejemplo", destino)
    corrida = json.loads((destino / "corrida.json").read_text(encoding="utf-8"))
    corrida["datos_sec"] = datos_sec
    (destino / "corrida.json").write_text(json.dumps(corrida), encoding="utf-8")

    real_cargar = carga.cargar_candidatos
    monkeypatch.setattr("aprobacion.carga.cargar_candidatos", lambda *a: real_cargar(destino))
    monkeypatch.setattr(
        "aprobacion.generacion.disponibilidad",
        lambda *a: SimpleNamespace(puede_generar=True, puede_usar_ia=False,
                                   motivo="Sin clave de Anthropic.", motivo_generacion=""),
    )
    monkeypatch.setattr("preferencias.RUTA", tmp_path / "preferencias.json")
    monkeypatch.setenv("GUION_VISTA", "candidatos.py")
    st.cache_data.clear()
    at = AppTest.from_file(GUION, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture(autouse=True)
def _limpiar_cache():
    yield
    st.cache_data.clear()


def test_la_linea_sale_como_info(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, DATOS_SEC)
    assert any("Datos de la SEC hasta el 3T 2026" in i.value for i in at.info)
    assert not any("Datos de la SEC" in w.value for w in at.warning)


def test_con_caducadas_sale_como_aviso(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, {**DATOS_SEC, "servidas_caducadas": 3})
    assert any("3 servidas sin actualizar" in w.value for w in at.warning)


def test_una_corrida_sin_el_bloque_no_pinta_nada(monkeypatch, tmp_path):
    at = _pantalla(monkeypatch, tmp_path, None)
    textos = [e.value for e in at.info] + [e.value for e in at.warning]
    assert not any("Datos de la SEC" in t for t in textos)
```

- [ ] **Step 6: Correrlo para ver que falla**

Run: `.venv/Scripts/python -m pytest tests/test_pantalla_candidatos_datos_sec.py -q`
Expected: FAIL en `test_la_linea_sale_como_info` y `test_con_caducadas_sale_como_aviso`, porque no se pinta nada todavía. `test_una_corrida_sin_el_bloque_no_pinta_nada` pasa.

- [ ] **Step 7: Pintarla**

En `vistas/candidatos.py`, en el import de `aprobacion.carga` (alrededor de la línea 31), añadir `linea_datos_sec` a la lista, en orden alfabético junto a los demás nombres.

Sustituir la línea `st.info(resumen_corrida(candidatos.corrida))` (línea ~305) por:

```python
st.info(resumen_corrida(candidatos.corrida))
# Sub-proyecto Q: de cuándo son las cifras. Es aviso si alguna se sirvió vieja
# porque la SEC no contestó, que es justo cuando el revisor tiene que saberlo.
_datos_sec = linea_datos_sec(candidatos.corrida)
if _datos_sec is not None:
    _texto_sec, _aviso_sec = _datos_sec
    (st.warning if _aviso_sec else st.info)(_texto_sec)
```

- [ ] **Step 8: Correr los tests de pantalla**

Run: `.venv/Scripts/python -m pytest tests/test_pantalla_candidatos_datos_sec.py tests/test_pantalla_candidatos_macro.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add programa/aprobacion/carga.py programa/vistas/candidatos.py programa/tests/test_aprobacion_carga.py programa/tests/test_pantalla_candidatos_datos_sec.py
git commit -m "feat(candidatos): la pantalla dice de cuándo son los datos de la SEC"
```

---

### Task 6: Suite completa, spec y CONTEXTO

**Files:**
- Modify: `docs/superpowers/specs/2026-11-22-caducidad-cache-sec-design.md` (Estado)
- Modify: `programa/CONTEXTO.md`

- [ ] **Step 1: Suite completa**

Run: `.venv/Scripts/python -m pytest -q`
Expected: todo verde. Hay 4.040 tests de antes más los nuevos, unos 4.070. Si algún test de otro módulo crea ficheros de caché y luego avanza el reloj o fija fechas, puede ver un caducado inesperado. En ese caso, pasar `hoy` explícito en ese test. No relajar la regla.

- [ ] **Step 2: Prueba real, opcional y con red**

Desde `programa/`:

```bash
.venv/Scripts/python -c "from fundamentals.fetch import load_facts; from research.universe import sp500_members; h, c = load_facts(sp500_members()[:20]); print(c.summary()); print(len(c.actualizadas), 'actualizadas')"
```

Expected: con la caché del 2026-08-30, las 20 están caducadas y salen en `actualizadas`, salvo que la SEC no responda. Repetirlo inmediatamente da 0 actualizadas, porque los ficheros ya tienen menos de 7 días.

- [ ] **Step 3: Actualizar el estado del spec y CONTEXTO**

En el spec, cambiar `**Estado:** diseño, pendiente de plan` por `**Estado:** implementado (2026-11-22)`.

En `programa/CONTEXTO.md`, añadir el sub-proyecto Q a la lista de sub-proyectos con una línea: «Q — la caché de la SEC caduca: se vuelve a pedir un fichero cuando su último cierre tiene más de 75 días y él más de 7; sin red se sirve el viejo y la pantalla lo avisa». Actualizar el recuento de tests con el número del Step 1.

- [ ] **Step 4: Commit**

```bash
git add programa/docs/superpowers/specs/2026-11-22-caducidad-cache-sec-design.md programa/CONTEXTO.md
git commit -m "docs: CONTEXTO con la caducidad de la caché de la SEC (Q)"
```
