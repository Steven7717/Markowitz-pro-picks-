# Entorno macro (P; escrito como O) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leer la fase del ciclo de una región con el CLI de la OCDE, enseñarla en una pantalla «Entorno macro» y, si el usuario la activa, inclinar el Top de candidatos ±0,25 desviaciones por sector.

**Architecture:** Paquete nuevo `macro/` en unidades pequeñas: `criterio` (datos congelados), `fase` (regla pura), `fuentes` (red y caché), `contexto` (cuentas de FRED para EE. UU.), `estado` (une fuente, fase y vigencia), `textos` (todo lo de pantalla) y `lectura` (IA opcional). El ranking solo gana `inclinar` en `ranking/score.py` y un parámetro `macro` en `construir_ranking`. Las vistas pintan y no deciden nada.

**Tech Stack:** Python 3, pandas, Streamlit, urllib (sin dependencias nuevas), pydantic + `interprete.cliente` para la IA, pytest (marca `red` para la red real).

**Spec:** `docs/superpowers/specs/2026-11-15-entorno-macro-design.md`. La Task 1 le añade una enmienda que manda sobre el texto de arriba.

**Todos los comandos se ejecutan desde `programa/`.** Suite normal: `uv run pytest tests/ -q -m "not red"`.

---

## Mapa de ficheros

| Fichero | Qué hace |
|---|---|
| `macro/__init__.py` | vacío |
| `macro/criterio.py` | constantes congeladas: regla, regiones, mapa fase → sectores |
| `macro/fase.py` | `Fase`, `fases_por_mes`, `determinar`, `motivo_para_no_inclinar` — sin red |
| `macro/fuentes.py` | `Serie`, `parsear_cli`, `parsear_fred`, `traer_cli`, `traer_fred` — con caché |
| `macro/contexto.py` | `ContextoUSA`, `calcular` — curva, Sahm, inflación; sin red |
| `macro/estado.py` | `Estado`, `leer_region` — lo que consumen las dos vistas |
| `macro/textos.py` | nombres en pantalla, porqués, aviso, resúmenes de corrida |
| `macro/lectura.py` | la lectura con IA, con caché por región y mes |
| `ranking/score.py` | + `ajuste_de`, `inclinar` |
| `ranking/fichas.py` | + `ajuste_macro` en la ficha |
| `ranking/run.py` | + `macro`, `region` en `construir_ranking`; `corrida["macro"]` |
| `preferencias.py` | + `region_macro` |
| `vistas/entorno_macro.py` | pantalla nueva |
| `vistas/candidatos.py` | casilla, selector, bloque «Lo que movió la macro», línea en la ficha |
| `vistas/actas.py` | «con macro…» / «sin macro» |
| `app.py` | página nueva en el menú |
| `.gitignore` | `macro/.cache/` |
| `tests/test_macro_*.py` | uno por módulo, más `test_macro_red.py` |

---

### Task 1: Enmienda del spec con lo comprobado contra la API

Antes de escribir el plan se consultó la API real (2026-11-16): el CLI con ajuste de amplitud está en `OECD.SDD.STES,DSD_STES@DF_CLI` con la clave `{area}.M.LI...AA...H`, y trae dato hasta `2026-10` para `USA`, `MEX`, `CHN` y `G7`. **`EA20` no existe en ese flujo.** Las áreas que hay son `A5M AUS BRA CAN CHN DEU ESP FRA G20 G4E G7 GBR IDN IND ITA JPN KOR MEX NAFTA TUR USA ZAF`. La más cercana a la Eurozona es `G4E`, las cuatro grandes: Alemania, Francia, Italia y España.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-15-entorno-macro-design.md` (añadir al final)

- [ ] **Step 1: Añadir la enmienda al final del spec**

```markdown

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
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-11-15-entorno-macro-design.md
git commit -m "docs: enmienda del spec de O con lo que dijo la API de la OCDE (G4E, no EA20)"
```

---

### Task 2: `macro/criterio.py`, congelado en su propio commit

**Files:**
- Create: `macro/__init__.py` (vacío)
- Create: `macro/criterio.py`
- Create: `tests/test_macro_criterio.py`
- Modify: `.gitignore` (añadir `macro/.cache/` debajo de `analizador/.cache/`)

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_macro_criterio.py
from fundamentals.sectors import load_sectors
from macro import criterio

FASES = {"recuperacion", "expansion", "desaceleracion", "contraccion"}


def test_las_cuatro_fases_y_ninguna_mas():
    assert set(criterio.SECTORES_POR_FASE) == FASES


def test_cada_sector_del_mapa_existe_en_la_tabla_gics():
    """Un nombre mal escrito no inclinaría nada y no daría ningún error."""
    conocidos = set(load_sectors().values())
    for fase, listas in criterio.SECTORES_POR_FASE.items():
        for sector in listas["favorecidos"] + listas["desfavorecidos"]:
            assert sector in conocidos, (fase, sector)


def test_ningun_sector_es_a_la_vez_favorecido_y_desfavorecido():
    for fase, listas in criterio.SECTORES_POR_FASE.items():
        assert not set(listas["favorecidos"]) & set(listas["desfavorecidos"]), fase


def test_cada_fase_tiene_las_dos_listas_no_vacias():
    for listas in criterio.SECTORES_POR_FASE.values():
        assert set(listas) == {"favorecidos", "desfavorecidos"}
        assert listas["favorecidos"] and listas["desfavorecidos"]


def test_regiones_y_su_defecto():
    assert set(criterio.REGIONES) == {"usa", "mex", "eurozona", "china", "g7"}
    assert criterio.REGION_POR_DEFECTO == "usa"
    assert criterio.REGIONES["eurozona"] == "G4E"


def test_la_inclinacion_es_pequena():
    """El compuesto es un z dentro del sector: 0,25 es un cuarto de desviación."""
    assert 0 < criterio.INCLINACION <= 0.5
```

- [ ] **Step 2: Comprobar que falla**

Run: `uv run pytest tests/test_macro_criterio.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'macro'`

- [ ] **Step 3: Escribir el criterio**

```python
# macro/criterio.py
"""El criterio de la fase y de su inclinación, congelado antes de mirar resultados.

Datos, no lógica, como `ranking/criterio.py`: la fecha del commit que introduce
este fichero prueba que ningún número se movió una vez vistas las fases.
Cambiarlo exige una enmienda fechada en
docs/superpowers/specs/2026-11-15-entorno-macro-design.md, nunca una edición
callada.

Aquí no hay texto de pantalla. Los nombres que ve el usuario están en
`macro/textos.py`, y las claves de aquí son lo único que se guarda en disco.
"""

NIVEL_NEUTRO = 100.0
MESES_DIRECCION = 3
MAX_ANTIGUEDAD_MESES = 3
INCLINACION = 0.25

# Clave interna → área de referencia del flujo del CLI de la OCDE.
# `G4E` y no `EA20`: el flujo no tiene la zona euro entera (enmienda 1).
REGIONES: dict[str, str] = {
    "usa": "USA",
    "mex": "MEX",
    "eurozona": "G4E",
    "china": "CHN",
    "g7": "G7",
}
REGION_POR_DEFECTO = "usa"

# La rotación sectorial clásica por fases del ciclo. El porqué de cada
# sector, en palabras, está en `macro/textos.py:POR_QUE`. Un sector que no
# aparece en una fase queda neutro.
SECTORES_POR_FASE: dict[str, dict[str, tuple[str, ...]]] = {
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

`macro/__init__.py`: fichero vacío.

- [ ] **Step 4: Comprobar que pasa**

Run: `uv run pytest tests/test_macro_criterio.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit (solo el criterio: es la prueba de que se congeló antes)**

```bash
git add macro/__init__.py macro/criterio.py tests/test_macro_criterio.py .gitignore
git commit -m "feat(macro): el criterio de la fase, congelado antes de calcular ninguna"
```

---

### Task 3: `macro/fase.py` — la regla, sin red

**Files:**
- Create: `macro/fase.py`
- Create: `tests/test_macro_fase.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_fase.py
from datetime import date

import pandas as pd
import pytest

from macro.fase import Fase, determinar, fases_por_mes, motivo_para_no_inclinar


def _serie(valores, desde="2026-01"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


@pytest.mark.parametrize(
    "valores, clave",
    [
        ([100.5, 100.6, 100.7, 100.8], "expansion"),
        ([101.0, 100.9, 100.8, 100.7], "desaceleracion"),
        ([99.0, 99.1, 99.2, 99.3], "recuperacion"),
        ([99.5, 99.4, 99.3, 99.2], "contraccion"),
    ],
)
def test_las_cuatro_fases(valores, clave):
    fase = determinar(_serie(valores))
    assert fase.clave == clave
    assert fase.motivo is None


def test_en_100_exacto_cuenta_como_por_encima():
    assert determinar(_serie([99.7, 99.8, 99.9, 100.0])).clave == "expansion"


def test_un_giro_del_ultimo_mes_contra_la_tendencia_es_indeterminado():
    # Sube en tres meses (100.0 → 100.4) pero el último mes baja.
    fase = determinar(_serie([100.0, 100.3, 100.5, 100.4]))
    assert fase.clave is None
    assert fase.motivo == "indeterminada"


def test_un_cambio_a_tres_meses_nulo_es_indeterminado():
    fase = determinar(_serie([100.2, 100.1, 100.3, 100.2]))
    assert fase.clave is None and fase.motivo == "indeterminada"


def test_un_ultimo_mes_plano_no_contradice():
    """Enmienda 4: plano no es «en contra»."""
    assert determinar(_serie([100.0, 100.2, 100.4, 100.4])).clave == "expansion"


def test_serie_corta():
    fase = determinar(_serie([100.0, 100.1, 100.2]))
    assert fase.clave is None and fase.motivo == "serie_corta"
    assert fase.meses_en_fase == 0


def test_lleva_mes_nivel_y_cambio():
    fase = determinar(_serie([100.5, 100.6, 100.7, 100.8]))
    assert fase.mes_dato == date(2026, 4, 1)
    assert fase.nivel == pytest.approx(100.8)
    assert fase.cambio == pytest.approx(0.3)


def test_meses_en_fase_cuenta_los_seguidos():
    # Contracción en marzo y abril de 2026; recuperación de mayo a julio.
    valores = [100.4, 100.2, 99.9, 99.6, 99.4, 99.5, 99.7, 99.9, 99.95, 99.97]
    fase = determinar(_serie(valores))
    assert fase.clave == "recuperacion"
    assert fase.meses_en_fase == 4


def test_fases_por_mes_deja_none_donde_no_hay_regla():
    por_mes = fases_por_mes(_serie([100.5, 100.6, 100.7, 100.8, 100.9]))
    assert list(por_mes.iloc[:3]) == [None, None, None]
    assert list(por_mes.iloc[3:]) == ["expansion", "expansion"]


def test_un_nan_en_la_serie_se_descarta_y_no_se_lee_como_cero():
    serie = _serie([100.5, float("nan"), 100.6, 100.7, 100.8])
    assert determinar(serie).clave == "expansion"


def test_no_se_inclina_sin_fase():
    fase = Fase(None, "indeterminada", date(2026, 10, 1), 100.0, 0.0, 0)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) == "indeterminada"


def test_no_se_inclina_con_un_dato_de_hace_mas_de_tres_meses():
    fase = Fase("expansion", None, date(2026, 7, 1), 100.8, 0.3, 5)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) == "dato_rancio"


def test_tres_meses_justos_aun_valen():
    fase = Fase("expansion", None, date(2026, 8, 1), 100.8, 0.3, 5)
    assert motivo_para_no_inclinar(fase, date(2026, 11, 16)) is None
```

En `test_meses_en_fase_cuenta_los_seguidos`, la cuenta mes a mes (índice desde enero de 2026; la regla empieza a funcionar en abril):
- abr, 99.6: cambio a 3 meses −0.8, último mes −0.3, por debajo de 100 → contracción.
- may, 99.4: −0.8 y −0.2 → contracción.
- jun, 99.5: −0.4 en 3 meses y +0.1 el último mes → indeterminada.
- jul, 99.7: +0.1 y +0.2 → recuperación.
- ago, 99.9: +0.5 y +0.2 → recuperación.
- sep, 99.95: +0.45 y +0.05 → recuperación.
- oct, 99.97: +0.27 y +0.02 → recuperación.

Son cuatro meses seguidos de recuperación.

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_fase.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'macro.fase'`

- [ ] **Step 3: Escribir `macro/fase.py`**

```python
# macro/fase.py
"""La fase del ciclo a partir del CLI. Puro: no sabe de dónde viene la serie.

Nivel frente a 100 y dirección a tres meses. Un giro que el último mes
desmiente no es un giro: sale `indeterminada`, y quien llama no inclina nada.
No se elige un lado por defecto, porque un lado por defecto es una fase
inventada.

No mira el reloj. Si el dato es demasiado viejo para mover el Top lo decide
`motivo_para_no_inclinar`, que recibe la fecha de hoy como argumento.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from macro.criterio import MAX_ANTIGUEDAD_MESES, MESES_DIRECCION, NIVEL_NEUTRO


@dataclass(frozen=True)
class Fase:
    clave: "str | None"
    motivo: "str | None"
    mes_dato: "date | None"
    nivel: "float | None"
    cambio: "float | None"
    meses_en_fase: int


def _clave(nivel: float, cambio: float, ultimo: float) -> "str | None":
    if cambio == 0 or (ultimo != 0 and (ultimo > 0) != (cambio > 0)):
        return None
    sube = cambio > 0
    if nivel >= NIVEL_NEUTRO:
        return "expansion" if sube else "desaceleracion"
    return "recuperacion" if sube else "contraccion"


def fases_por_mes(serie: pd.Series) -> pd.Series:
    """La clave de cada mes, o None donde la regla no tiene datos o no decide."""
    limpia = serie.dropna().sort_index()
    valores = limpia.to_numpy()
    claves: list = []
    for i in range(len(valores)):
        if i < MESES_DIRECCION:
            claves.append(None)
            continue
        claves.append(
            _clave(
                valores[i],
                valores[i] - valores[i - MESES_DIRECCION],
                valores[i] - valores[i - 1],
            )
        )
    return pd.Series(claves, index=limpia.index, dtype="object")


def determinar(serie: pd.Series) -> Fase:
    limpia = serie.dropna().sort_index()
    if len(limpia) < MESES_DIRECCION + 1:
        return Fase(None, "serie_corta", None, None, None, 0)

    por_mes = fases_por_mes(limpia)
    clave = por_mes.iloc[-1]
    mes = limpia.index[-1].date().replace(day=1)
    nivel = float(limpia.iloc[-1])
    cambio = float(limpia.iloc[-1] - limpia.iloc[-1 - MESES_DIRECCION])
    if clave is None:
        return Fase(None, "indeterminada", mes, nivel, cambio, 0)

    seguidos = 0
    for anterior in reversed(por_mes.tolist()):
        if anterior != clave:
            break
        seguidos += 1
    return Fase(clave, None, mes, nivel, cambio, seguidos)


def motivo_para_no_inclinar(fase: Fase, hoy: date) -> "str | None":
    """Por qué esta fase no puede mover el Top, o None si puede."""
    if fase.clave is None:
        return fase.motivo
    meses = (hoy.year * 12 + hoy.month) - (fase.mes_dato.year * 12 + fase.mes_dato.month)
    if meses > MAX_ANTIGUEDAD_MESES:
        return "dato_rancio"
    return None
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_fase.py -q`
Expected: `16 passed` (los cuatro parametrizados cuentan por separado)

- [ ] **Step 5: Commit**

```bash
git add macro/fase.py tests/test_macro_fase.py
git commit -m "feat(macro): la fase del ciclo a partir del CLI, sin red"
```

---

### Task 4: `macro/fuentes.py` — OCDE y FRED, con caché y fallos con nombre

**Files:**
- Create: `macro/fuentes.py`
- Create: `tests/test_macro_fuentes.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_fuentes.py
import io
import urllib.error
from datetime import datetime, timezone

import pandas as pd
import pytest

from macro import fuentes

CSV_OCDE = (
    "DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,ADJUSTMENT,TRANSFORMATION,"
    "TIME_HORIZ,METHODOLOGY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,DECIMALS,BASE_PER\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-09,100.931,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-07,100.8179,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-08,100.8874,A,0,2,\n"
)
CSV_FRED = "observation_date,T10Y3M\n2026-11-11,\n2026-11-12,0.78\n2026-11-13,0.83\n"


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _abre(texto):
    def abrir(peticion, timeout):
        abrir.urls.append(peticion.full_url)
        return _Respuesta(texto.encode("utf-8"))

    abrir.urls = []
    return abrir


def _falla(error):
    def abrir(peticion, timeout):
        raise error

    return abrir


def test_parsear_cli_ordena_por_mes():
    serie = fuentes.parsear_cli(CSV_OCDE)
    assert list(serie.index.strftime("%Y-%m")) == ["2026-07", "2026-08", "2026-09"]
    assert serie.iloc[-1] == pytest.approx(100.931)


def test_parsear_fred_descarta_los_huecos():
    serie = fuentes.parsear_fred(CSV_FRED, "T10Y3M")
    assert list(serie) == [0.78, 0.83]


def test_la_url_del_cli_lleva_el_area_de_la_region(tmp_path):
    abrir = _abre(CSV_OCDE)
    fuentes.traer_cli("eurozona", raiz=tmp_path, abrir=abrir)
    assert "/G4E.M.LI...AA...H?" in abrir.urls[0]


def test_traer_cli_ok_y_la_segunda_vez_sale_de_la_cache(tmp_path):
    primera = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(CSV_OCDE))
    assert primera.motivo == "ok" and len(primera.datos) == 3
    segunda = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(AssertionError("red")))
    assert segunda.motivo == "ok" and not segunda.vieja
    assert list(segunda.datos) == list(primera.datos)


def test_sin_red_y_sin_cache_es_sin_red(tmp_path):
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(urllib.error.URLError("x")))
    assert r.datos is None and r.motivo == "sin_red"


def test_un_404_es_serie_desconocida(tmp_path):
    error = urllib.error.HTTPError("u", 404, "NoResultsFound", {}, None)
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_falla(error))
    assert r.motivo == "serie_desconocida"


def test_un_csv_sin_columnas_es_respuesta_ilegible(tmp_path):
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre("<html>caído</html>"))
    assert r.motivo == "respuesta_ilegible"


def test_una_respuesta_vacia_es_serie_desconocida(tmp_path):
    cabecera = CSV_OCDE.splitlines()[0] + "\n"
    r = fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(cabecera))
    assert r.motivo == "serie_desconocida"


def test_con_la_red_caida_se_usa_la_cache_caducada_marcada(tmp_path):
    fuentes.traer_cli("usa", raiz=tmp_path, abrir=_abre(CSV_OCDE))
    manana = datetime.now(timezone.utc) + fuentes.VALIDEZ * 2
    r = fuentes.traer_cli(
        "usa", raiz=tmp_path, abrir=_falla(urllib.error.URLError("x")), ahora=manana
    )
    assert r.motivo == "ok" and r.vieja is True and len(r.datos) == 3


def test_region_desconocida_revienta(tmp_path):
    with pytest.raises(KeyError):
        fuentes.traer_cli("marte", raiz=tmp_path, abrir=_abre(CSV_OCDE))


def test_traer_fred(tmp_path):
    abrir = _abre(CSV_FRED)
    r = fuentes.traer_fred("T10Y3M", raiz=tmp_path, abrir=abrir)
    assert r.motivo == "ok" and list(r.datos) == [0.78, 0.83]
    assert abrir.urls[0].endswith("fredgraph.csv?id=T10Y3M")
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_fuentes.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'macro.fuentes'`

- [ ] **Step 3: Escribir `macro/fuentes.py`**

```python
# macro/fuentes.py
"""El CLI de la OCDE y tres series de FRED. Solo descarga y guarda.

Las dos son gratis y sin clave. La caché no es opcional: Streamlit vuelve a
ejecutar la página con cada clic, y la OCDE limita las consultas por minuto.

Un fallo es un resultado con nombre, no una excepción, como en
`seguimiento/banxico.py`. Si la red cae y hay algo guardado, se devuelve lo
guardado marcado `vieja=True`: un dato viejo con su fecha a la vista sirve, uno
que se lee como fresco sin serlo no.
"""

import http.client
import io
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from macro.criterio import REGIONES
from noticias import cache

URL_CLI = (
    "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/"
    "{area}.M.LI...AA...H?startPeriod={desde}"
    "&dimensionAtObservation=AllDimensions&format=csvfile"
)
URL_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}"
RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
VALIDEZ = timedelta(hours=24)
ANOS_HISTORIA = 6
_ESPERA_SEGUNDOS = 20
_CUALQUIER_EDAD = timedelta(days=36_500)


@dataclass(frozen=True)
class Serie:
    """`motivo`: ok | sin_red | serie_desconocida | respuesta_ilegible."""

    datos: "pd.Series | None"
    motivo: str
    descargada: "datetime | None" = None
    vieja: bool = False


class _Vacia(ValueError):
    pass


def parsear_cli(texto: str) -> pd.Series:
    marco = pd.read_csv(io.StringIO(texto))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(marco.columns):
        raise ValueError("el CSV de la OCDE no trae TIME_PERIOD/OBS_VALUE")
    marco = marco.dropna(subset=["OBS_VALUE"])
    if marco.empty:
        raise _Vacia()
    indice = pd.PeriodIndex(marco["TIME_PERIOD"].astype(str), freq="M").to_timestamp()
    serie = pd.Series(marco["OBS_VALUE"].astype(float).to_numpy(), index=indice)
    return serie.sort_index()


def parsear_fred(texto: str, serie_id: str) -> pd.Series:
    marco = pd.read_csv(io.StringIO(texto))
    if serie_id not in marco.columns or "observation_date" not in marco.columns:
        raise ValueError(f"el CSV de FRED no trae {serie_id}")
    valores = pd.to_numeric(marco[serie_id], errors="coerce")
    serie = pd.Series(valores.to_numpy(), index=pd.DatetimeIndex(marco["observation_date"]))
    serie = serie.dropna().sort_index()
    if serie.empty:
        raise _Vacia()
    return serie


def _a_plano(serie: pd.Series) -> dict:
    return {d.date().isoformat(): float(v) for d, v in serie.items()}


def _de_plano(plano) -> pd.Series:
    if not isinstance(plano, dict):
        raise TypeError("caché sin forma de serie")
    indice = pd.DatetimeIndex([pd.Timestamp(k) for k in plano])
    return pd.Series([float(v) for v in plano.values()], index=indice, dtype=float).sort_index()


def _traer(url: str, llave: str, parsear, *, raiz: Path, abrir, ahora) -> Serie:
    abrir = abrir or urllib.request.urlopen
    ahora = ahora or datetime.now(timezone.utc)

    guardado = cache.leer(raiz, "macro", llave, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None:
        try:
            previo = _de_plano(guardado.datos)
        except (TypeError, ValueError):
            previo = None
    if previo is not None and ahora - guardado.cuando <= VALIDEZ:
        return Serie(previo, "ok", guardado.cuando)

    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "markowitz-pro-picks"})
        with abrir(peticion, timeout=_ESPERA_SEGUNDOS) as respuesta:
            datos = parsear(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        motivo = "serie_desconocida" if error.code == 404 else "sin_red"
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        motivo = "sin_red"
    except _Vacia:
        motivo = "serie_desconocida"
    except (ValueError, KeyError, TypeError, pd.errors.ParserError):
        motivo = "respuesta_ilegible"
    else:
        try:
            cache.guardar(raiz, "macro", llave, _a_plano(datos))
        except OSError:
            pass
        return Serie(datos, "ok", ahora)

    if previo is not None:
        return Serie(previo, "ok", guardado.cuando, vieja=True)
    return Serie(None, motivo)


def traer_cli(region: str, *, raiz: Path = RAIZ_CACHE, abrir=None, ahora=None) -> Serie:
    """El CLI de una región. `KeyError` si la región no existe: es un defecto, no un fallo de red."""
    area = REGIONES[region]
    hoy = (ahora or datetime.now(timezone.utc)).date()
    desde = f"{hoy.year - ANOS_HISTORIA}-01"
    url = URL_CLI.format(area=area, desde=desde)
    return _traer(url, f"cli_{area}", parsear_cli, raiz=raiz, abrir=abrir, ahora=ahora)


def traer_fred(serie_id: str, *, raiz: Path = RAIZ_CACHE, abrir=None, ahora=None) -> Serie:
    url = URL_FRED.format(serie=serie_id)
    return _traer(
        url, f"fred_{serie_id}", lambda t: parsear_fred(t, serie_id),
        raiz=raiz, abrir=abrir, ahora=ahora,
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_fuentes.py -q`
Expected: `11 passed`

`test_con_la_red_caida_se_usa_la_cache_caducada_marcada` depende de que `cache.guardar` escriba la hora real: `ahora` va dos días por delante, así que la caché ha caducado. Si `cache.leer` devolviera `None` por la edad, el test fallaría. Por eso se lee con `_CUALQUIER_EDAD` y la vigencia la decide `VALIDEZ`.

- [ ] **Step 5: Commit**

```bash
git add macro/fuentes.py tests/test_macro_fuentes.py
git commit -m "feat(macro): el CLI de la OCDE y las series de FRED, con caché y fallos con nombre"
```

---

### Task 5: `macro/contexto.py` — curva, Sahm e inflación de EE. UU.

**Files:**
- Create: `macro/contexto.py`
- Create: `tests/test_macro_contexto.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_contexto.py
import pandas as pd
import pytest

from macro.contexto import UMBRAL_SAHM, calcular


def _mensual(valores, desde="2025-01"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


def test_curva_invertida():
    curva = pd.Series([0.2, -0.1], index=pd.DatetimeIndex(["2026-11-12", "2026-11-13"]))
    c = calcular(curva=curva, desempleo=None, ipc=None)
    assert c.curva == pytest.approx(-0.1) and c.curva_invertida is True


def test_sahm_activada():
    # 12 meses en 4,0 y después 4,5, 4,7 y 4,9: media de 3 = 4,7; mínimo previo = 4,0.
    desempleo = _mensual([4.0] * 12 + [4.5, 4.7, 4.9])
    c = calcular(curva=None, desempleo=desempleo, ipc=None)
    assert c.sahm == pytest.approx(0.7)
    assert c.sahm_activada is (0.7 >= UMBRAL_SAHM)


def test_sahm_sin_historia_suficiente_es_none():
    c = calcular(curva=None, desempleo=_mensual([4.0] * 10), ipc=None)
    assert c.sahm is None and c.sahm_activada is None


def test_inflacion_interanual():
    ipc = _mensual([100.0] + [101.0] * 11 + [103.0])
    c = calcular(curva=None, desempleo=None, ipc=ipc)
    assert c.inflacion == pytest.approx(0.03)


def test_sin_series_todo_es_none():
    c = calcular(curva=None, desempleo=None, ipc=None)
    assert (c.curva, c.sahm, c.inflacion) == (None, None, None)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_contexto.py -q`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Escribir `macro/contexto.py`**

```python
# macro/contexto.py
"""El contexto de EE. UU.: curva, regla de Sahm e inflación. No entra en la fase.

Son tres lecturas que la pantalla enseña al lado de la fase, solo para EE. UU.
Las otras regiones no tienen las mismas series, y meterlas en la regla haría
que «expansión» significara cosas distintas según la región (ver el spec).
"""

from dataclasses import dataclass

import pandas as pd

UMBRAL_SAHM = 0.5
SERIES = {"curva": "T10Y3M", "desempleo": "UNRATE", "ipc": "CPIAUCSL"}


@dataclass(frozen=True)
class ContextoUSA:
    curva: "float | None"
    curva_invertida: "bool | None"
    sahm: "float | None"
    sahm_activada: "bool | None"
    inflacion: "float | None"


def _sahm(desempleo: "pd.Series | None") -> "float | None":
    """Media de 3 meses menos el mínimo de esa media en los 12 meses anteriores."""
    if desempleo is None:
        return None
    media = desempleo.dropna().rolling(3).mean().dropna()
    if len(media) < 13:
        return None
    return float(media.iloc[-1] - media.iloc[-13:-1].min())


def _inflacion(ipc: "pd.Series | None") -> "float | None":
    if ipc is None:
        return None
    limpio = ipc.dropna()
    if len(limpio) < 13:
        return None
    return float(limpio.iloc[-1] / limpio.iloc[-13] - 1)


def calcular(curva, desempleo, ipc) -> ContextoUSA:
    ultima = None if curva is None or curva.dropna().empty else float(curva.dropna().iloc[-1])
    sahm = _sahm(desempleo)
    return ContextoUSA(
        curva=ultima,
        curva_invertida=None if ultima is None else ultima < 0,
        sahm=sahm,
        sahm_activada=None if sahm is None else sahm >= UMBRAL_SAHM,
        inflacion=_inflacion(ipc),
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_contexto.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add macro/contexto.py tests/test_macro_contexto.py
git commit -m "feat(macro): el contexto de EE. UU. —curva, Sahm, inflación— fuera de la fase"
```

---

### Task 6: `macro/estado.py` — lo que leen las dos vistas

**Files:**
- Create: `macro/estado.py`
- Create: `tests/test_macro_estado.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_estado.py
from datetime import date, datetime, timezone

import pandas as pd

from macro.estado import leer_region
from macro.fuentes import Serie


def _serie(valores, desde="2026-07"):
    indice = pd.period_range(desde, periods=len(valores), freq="M").to_timestamp()
    return pd.Series(valores, index=indice, dtype=float)


def test_con_dato_bueno_se_puede_inclinar():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8]), "ok", datetime.now(timezone.utc))
    e = leer_region("usa", date(2026, 11, 16), traer=traer)
    assert e.fase.clave == "expansion"
    assert e.motivo_no_inclinar is None


def test_sin_red_no_hay_fase_y_dice_por_que():
    e = leer_region("usa", date(2026, 11, 16), traer=lambda r: Serie(None, "sin_red"))
    assert e.fase is None and e.serie is None
    assert e.motivo_no_inclinar == "sin_red"


def test_dato_rancio_tiene_fase_pero_no_inclina():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8], desde="2026-01"), "ok")
    e = leer_region("usa", date(2026, 11, 16), traer=traer)
    assert e.fase.clave == "expansion"
    assert e.motivo_no_inclinar == "dato_rancio"


def test_la_cache_vieja_se_avisa():
    traer = lambda region: Serie(_serie([100.5, 100.6, 100.7, 100.8]), "ok", vieja=True)
    assert leer_region("usa", date(2026, 11, 16), traer=traer).vieja is True
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_estado.py -q`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Escribir `macro/estado.py`**

```python
# macro/estado.py
"""Fuente, fase y vigencia juntas: lo único que consumen las vistas.

Las dos pantallas necesitan lo mismo —la serie para el gráfico, la fase y si
puede mover el Top— y dos copias de esta unión se separarían.
"""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from macro import fuentes
from macro.fase import Fase, determinar, motivo_para_no_inclinar


@dataclass(frozen=True)
class Estado:
    region: str
    serie: "pd.Series | None"
    fase: "Fase | None"
    motivo_no_inclinar: "str | None"
    descargada: "datetime | None"
    vieja: bool


def leer_region(region: str, hoy: date, *, traer=None) -> Estado:
    traer = traer or fuentes.traer_cli
    resultado = traer(region)
    if resultado.datos is None:
        return Estado(region, None, None, resultado.motivo, None, False)
    fase = determinar(resultado.datos)
    return Estado(
        region=region,
        serie=resultado.datos,
        fase=fase,
        motivo_no_inclinar=motivo_para_no_inclinar(fase, hoy),
        descargada=resultado.descargada,
        vieja=resultado.vieja,
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_estado.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add macro/estado.py tests/test_macro_estado.py
git commit -m "feat(macro): el estado de una región, lo que leen las dos pantallas"
```

---

### Task 7: Test `red` contra la OCDE y FRED reales

**Files:**
- Create: `tests/test_macro_red.py`

- [ ] **Step 1: Escribir el test**

```python
# tests/test_macro_red.py
"""Contra la OCDE y FRED de verdad. Excluidos de la suite normal.

Comprueba que la clave del flujo y las cinco áreas siguen dando dato, y que las
tres series de FRED existen. Si la OCDE cambia la versión del flujo o retira un
área, esto lo dice antes que la pantalla.
"""

import pytest

from macro import fuentes
from macro.contexto import SERIES
from macro.criterio import REGIONES

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(fuentes, "RAIZ_CACHE", tmp_path)


@pytest.mark.parametrize("region", sorted(REGIONES))
def test_cada_region_trae_al_menos_cinco_anos_de_cli(region):
    r = fuentes.traer_cli(region, raiz=fuentes.RAIZ_CACHE)
    assert r.motivo == "ok", r.motivo
    assert len(r.datos) >= 60
    assert 80 < r.datos.iloc[-1] < 120


@pytest.mark.parametrize("serie", sorted(SERIES.values()))
def test_las_series_de_fred_existen(serie):
    r = fuentes.traer_fred(serie, raiz=fuentes.RAIZ_CACHE)
    assert r.motivo == "ok", r.motivo
    assert len(r.datos) > 12
```

- [ ] **Step 2: Ejecutarlo**

Run: `uv run pytest tests/test_macro_red.py -q -m red`
Expected: `8 passed`. Si una región falla con `serie_desconocida`, mirar las áreas disponibles con:

```bash
curl -s "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/.M.LI...AA...H?startPeriod=2026-08&dimensionAtObservation=AllDimensions&format=csvfile" | cut -d, -f2 | sort -u
```

y corregir `REGIONES` **con una enmienda fechada en el spec**, no a pelo.

- [ ] **Step 3: Commit**

```bash
git add tests/test_macro_red.py
git commit -m "test(macro): la OCDE y FRED de verdad, marcados red"
```

---

### Task 8: `inclinar` en `ranking/score.py`

**Files:**
- Modify: `ranking/score.py` (añadir al final)
- Test: `tests/test_ranking_score.py` (añadir al final)

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_ranking_score.py`:

```python
from macro.criterio import INCLINACION
from ranking.score import ajuste_de, inclinar


def test_inclinar_suma_y_resta_por_sector_y_deja_neutros():
    compuestos = pd.Series({"F1": 1.0, "S1": 1.0, "E1": 1.0, "X1": float("nan")})
    sectores = pd.Series(
        {"F1": "Financials", "S1": "Utilities", "E1": "Energy", "X1": "Financials"}
    )
    inclinados = inclinar(compuestos, sectores, "recuperacion")
    assert inclinados["F1"] == pytest.approx(1.0 + INCLINACION)
    assert inclinados["S1"] == pytest.approx(1.0 - INCLINACION)
    assert inclinados["E1"] == pytest.approx(1.0)
    assert pd.isna(inclinados["X1"])


def test_inclinar_no_modifica_la_entrada():
    compuestos = pd.Series({"F1": 1.0})
    inclinar(compuestos, pd.Series({"F1": "Financials"}), "recuperacion")
    assert compuestos["F1"] == 1.0


def test_ajuste_de_un_sector_desconocido_es_cero():
    assert ajuste_de(None, "expansion") == 0.0
    assert ajuste_de("Sector inventado", "expansion") == 0.0
```

(`pd` y `pytest` ya están importados en ese fichero. Si no, añadir `import pandas as pd` e `import pytest` arriba.)

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_ranking_score.py -q -k "inclinar or ajuste_de"`
Expected: FAIL con `ImportError: cannot import name 'ajuste_de'`

- [ ] **Step 3: Implementar**

Añadir el import arriba de `ranking/score.py`:

```python
from macro.criterio import INCLINACION, SECTORES_POR_FASE
```

y al final del fichero:

```python
def ajuste_de(sector: "str | None", fase: str) -> float:
    """Lo que la fase suma o resta a un sector: ±INCLINACION, o 0 si es neutro."""
    listas = SECTORES_POR_FASE[fase]
    if sector in listas["favorecidos"]:
        return INCLINACION
    if sector in listas["desfavorecidos"]:
        return -INCLINACION
    return 0.0


def inclinar(compuestos: pd.Series, sectores: pd.Series, fase: str) -> pd.Series:
    """El compuesto desplazado por la fase macro, antes de `seleccionar`.

    Encaja limpio porque `compuesto` ya re-estandariza dentro del sector: todos
    los sectores parten de media 0, así que esto es exactamente el desplazamiento
    de un sector frente a otro, en desviaciones. Un NaN sigue siendo NaN: una
    empresa excluida no vuelve a entrar por la macro.
    """
    ajustes = sectores.reindex(compuestos.index).map(lambda s: ajuste_de(s, fase))
    return compuestos + ajustes.astype(float)
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_ranking_score.py -q`
Expected: todo en verde

- [ ] **Step 5: Commit**

```bash
git add ranking/score.py tests/test_ranking_score.py
git commit -m "feat(ranking): inclinar el compuesto por la fase macro"
```

---

### Task 9: `ajuste_macro` en la ficha

**Files:**
- Modify: `ranking/fichas.py` (`ficha_numerica`)
- Test: `tests/test_ranking_fichas.py` (añadir)

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_ranking_fichas.py` (es autocontenido: construye sus propias series):

```python
def _ficha(**extra):
    import pandas as pd
    from fundamentals.kpis import TODOS_LOS_KPIS
    from ranking.criterio import PILARES
    from ranking.fichas import ficha_numerica

    z = pd.Series({kpi: 0.1 for kpi in TODOS_LOS_KPIS})
    return ficha_numerica(
        ticker="AAA", sector="Financials", puesto=1, compuesto=1.0,
        pilares=pd.Series({p: 0.5 for p in PILARES}),
        conteo=pd.Series({p: len(k) for p, k in PILARES.items()}),
        z=z, valores=z, desplazo_a=[], **extra,
    )


def test_la_ficha_lleva_el_ajuste_macro_y_por_defecto_es_cero():
    assert _ficha()["ajuste_macro"] == 0.0
    assert _ficha(ajuste_macro=0.25)["ajuste_macro"] == 0.25
    assert _ficha(ajuste_macro=0.25)["compuesto"] == 1.0
```

La firma pública queda `ficha_numerica(..., desplazo_a, ajuste_macro=0.0)`.

- [ ] **Step 2: Comprobar que falla**

Run: `uv run pytest tests/test_ranking_fichas.py -q`
Expected: FAIL con `KeyError: 'ajuste_macro'`

- [ ] **Step 3: Implementar**

En `ranking/fichas.py`, añadir el parámetro al final de la firma:

```python
    desplazo_a: list[str],
    ajuste_macro: float = 0.0,
) -> dict:
```

y en el dict devuelto, justo después de `"desplazo_a": list(desplazo_a),`:

```python
        # Aparte del compuesto a propósito (enmienda 3 del spec de O): el
        # compuesto sigue siendo el juicio sobre la empresa, y esto el juicio
        # sobre el ciclo. Sumados en un solo número no se distinguirían.
        "ajuste_macro": float(ajuste_macro),
```

- [ ] **Step 4: Comprobar que pasa**

Run: `uv run pytest tests/test_ranking_fichas.py -q`
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add ranking/fichas.py tests/test_ranking_fichas.py
git commit -m "feat(ranking): la ficha dice cuánto la movió la macro, aparte del compuesto"
```

---

### Task 10: `construir_ranking` con macro

**Files:**
- Modify: `ranking/run.py:96-205`
- Test: `tests/test_ranking_run.py` (añadir al final; usa la fixture `sin_red` de ese fichero, cuyos sectores son `"Tech"`, `"Financials"` y `"Health"`)

- [ ] **Step 1: Escribir los tests que fallan**

```python
from datetime import date as _date

from macro.criterio import INCLINACION
from macro.fase import Fase


def _fase(clave="recuperacion"):
    return Fase(clave, None, _date(2026, 10, 1), 99.5, 0.3, 4)


def test_sin_macro_la_corrida_dice_none_y_nadie_lleva_ajuste(sin_red):
    sin = construir_ranking(con_llm=False, n=5)
    assert sin.corrida["macro"] is None
    assert all(f["ajuste_macro"] == 0.0 for f in sin.fichas)


def test_con_macro_la_corrida_registra_region_fase_y_movimientos(sin_red):
    neutro = construir_ranking(con_llm=False, n=5)
    con = construir_ranking(con_llm=False, n=5, macro=_fase(), region="usa")
    bloque = con.corrida["macro"]
    assert bloque["region"] == "usa" and bloque["fase"] == "recuperacion"
    assert bloque["mes_dato"] == "2026-10-01" and bloque["inclinacion"] == INCLINACION
    antes = {f["ticker"] for f in neutro.fichas}
    despues = {f["ticker"] for f in con.fichas}
    assert set(bloque["entradas"]) == despues - antes
    assert set(bloque["salidas"]) == antes - despues


def test_con_macro_las_financieras_llevan_su_ajuste_y_el_compuesto_no_cambia(sin_red):
    neutro = {f["ticker"]: f["compuesto"] for f in construir_ranking(con_llm=False, n=15).fichas}
    con = construir_ranking(con_llm=False, n=15, macro=_fase(), region="usa")
    for ficha in con.fichas:
        esperado = INCLINACION if ficha["sector_gics"] == "Financials" else 0.0
        assert ficha["ajuste_macro"] == esperado
        if ficha["ticker"] in neutro:
            assert ficha["compuesto"] == neutro[ficha["ticker"]]


def test_una_inclinacion_grande_mete_financieras_en_el_top(sin_red, monkeypatch):
    """Con una inclinación exagerada se ve que de verdad se aplica antes de seleccionar."""
    import ranking.score as score

    monkeypatch.setattr(score, "INCLINACION", 10.0)
    con = construir_ranking(con_llm=False, n=3, tope=3, macro=_fase(), region="usa")
    assert {f["sector_gics"] for f in con.fichas} == {"Financials"}


def test_una_fase_sin_clave_no_se_acepta(sin_red):
    with pytest.raises(ValueError):
        construir_ranking(
            con_llm=False, n=5,
            macro=Fase(None, "indeterminada", _date(2026, 10, 1), 100.0, 0.0, 0),
            region="usa",
        )


def test_una_region_desconocida_no_se_acepta(sin_red):
    with pytest.raises(ValueError):
        construir_ranking(con_llm=False, n=5, macro=_fase(), region="marte")


def test_la_corrida_con_macro_es_json_estricto(sin_red, tmp_path):
    guardar(construir_ranking(con_llm=False, n=5, macro=_fase(), region="usa"), tmp_path)
    corrida = json.loads((tmp_path / "corrida.json").read_text(encoding="utf-8"))
    assert corrida["macro"]["fase"] == "recuperacion"
```

`test_una_inclinacion_grande_mete_financieras_en_el_top` parchea `ranking.score.INCLINACION`. Para que el parche surta efecto, `ajuste_de` tiene que leer la constante del módulo `ranking.score` en tiempo de llamada, que es lo que hace el import de la Task 8. En `test_la_corrida_con_macro_es_json_estricto`, comprobar antes cómo nombra `guardar` el fichero (`test_guardar_escribe_corrida_json` lo dice) y ajustar la ruta si fuera otra.

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_ranking_run.py -q`
Expected: los nuevos fallan con `TypeError: ... unexpected keyword argument 'macro'` o `KeyError: 'macro'`

- [ ] **Step 3: Implementar**

En `ranking/run.py`, imports:

```python
from macro.criterio import INCLINACION, REGIONES
from ranking.score import ajuste_de, inclinar
```

(sumar `ajuste_de` e `inclinar` al import existente de `ranking.score`).

Firma:

```python
def construir_ranking(
    source: str | list[str] = "sp500",
    con_llm: bool = True,
    n: int = TAMANO_TOP,
    tope: int = TOPE_POR_SECTOR,
    cache_dir: Path | None = None,
    con_valoracion: bool = True,
    macro: "Fase | None" = None,
    region: "str | None" = None,
) -> Resultado:
```

con `from macro.fase import Fase` arriba. Al final del docstring, añadir:

```
    `macro` inclina el compuesto por la fase del ciclo antes de seleccionar
    (sub-proyecto O). Con `None`, el Top es el de siempre. Con fase, se
    selecciona dos veces —sin inclinar e inclinado— y la diferencia queda en
    `corrida["macro"]`, como las desplazadas por el tope: un criterio que
    reordena la lista tiene que dejarse ver.
```

Al principio del cuerpo, antes de `build_panel`:

```python
    if macro is not None:
        if macro.clave is None:
            raise ValueError(f"una fase sin clave ({macro.motivo}) no puede inclinar el Top")
        if region not in REGIONES:
            raise ValueError(f"región desconocida: {region!r}")
```

Sustituir la línea `elegidas, desplazadas = seleccionar(puntos, sectores, tope=tope, n=n)` por:

```python
    elegidas, desplazadas = seleccionar(puntos, sectores, tope=tope, n=n)
    bloque_macro = None
    if macro is not None:
        neutras = set(elegidas["ticker"])
        elegidas, desplazadas = seleccionar(
            inclinar(puntos, sectores, macro.clave), sectores, tope=tope, n=n
        )
        inclinadas = set(elegidas["ticker"])
        bloque_macro = {
            "region": region,
            "fase": macro.clave,
            "mes_dato": macro.mes_dato.isoformat(),
            "inclinacion": float(INCLINACION),
            "entradas": sorted(inclinadas - neutras),
            "salidas": sorted(neutras - inclinadas),
        }
```

En el bucle de fichas, cambiar `compuesto=fila.compuesto,` por el compuesto **sin inclinar** y pasar el ajuste:

```python
            compuesto=float(puntos[fila.ticker]),
            ...
            desplazo_a=mapa.get(fila.ticker, []),
            ajuste_macro=ajuste_de(fila.sector, macro.clave) if macro is not None else 0.0,
```

En el dict `corrida=`, tras `"con_llm": bool(con_llm),`:

```python
            "macro": bloque_macro,
```

Sobre `INCLINACION` en el bloque: se importa de `macro.criterio` para registrarla. El test que la parchea en `ranking.score` solo mira las fichas, así que no hay conflicto.

- [ ] **Step 4: Comprobar que pasa todo `ranking`**

Run: `uv run pytest tests/test_ranking_run.py tests/test_ranking_score.py tests/test_ranking_fichas.py tests/test_aprobacion_carga.py -q`
Expected: verde. `test_aprobacion_carga.py` comprueba que una corrida con la clave nueva sigue validando: `_validar_corrida` solo exige campos, no prohíbe los nuevos.

- [ ] **Step 5: Commit**

```bash
git add ranking/run.py tests/test_ranking_run.py
git commit -m "feat(ranking): construir_ranking inclina por la fase macro y registra qué movió"
```

---

### Task 11: `macro/textos.py` — todo lo que se ve en pantalla

**Files:**
- Create: `macro/textos.py`
- Create: `tests/test_macro_textos.py`

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_textos.py
from macro import textos
from macro.criterio import REGIONES, SECTORES_POR_FASE


def test_cada_fase_y_region_tiene_nombre():
    assert set(textos.NOMBRE_FASE) == set(SECTORES_POR_FASE)
    assert set(textos.NOMBRE_REGION) == set(REGIONES)
    assert textos.NOMBRE_REGION["eurozona"] == "Eurozona (4 grandes)"


def test_cada_sector_del_mapa_tiene_su_porque():
    for fase, listas in SECTORES_POR_FASE.items():
        for sector in listas["favorecidos"] + listas["desfavorecidos"]:
            assert textos.POR_QUE[fase][sector].strip(), (fase, sector)
            assert sector in textos.NOMBRE_SECTOR


def test_cada_motivo_tiene_frase():
    for motivo in ("indeterminada", "serie_corta", "dato_rancio",
                   "sin_red", "serie_desconocida", "respuesta_ilegible"):
        assert textos.MOTIVO[motivo].strip()


def test_resumen_sin_macro():
    assert textos.etiqueta_corrida(None) == "sin macro"


def test_resumen_con_macro():
    bloque = {"region": "usa", "fase": "recuperacion", "mes_dato": "2026-10-01",
              "inclinacion": 0.25, "entradas": ["JPM"], "salidas": ["NVDA"]}
    assert textos.etiqueta_corrida(bloque) == "con macro: Recuperación (Estados Unidos, oct 2026)"
    frase = textos.lo_que_movio(bloque)
    assert "JPM" in frase and "NVDA" in frase


def test_lo_que_movio_sin_cambios_lo_dice():
    bloque = {"region": "usa", "fase": "expansion", "mes_dato": "2026-10-01",
              "inclinacion": 0.25, "entradas": [], "salidas": []}
    assert "no cambió" in textos.lo_que_movio(bloque)


def test_ajuste_de_ficha():
    assert textos.ajuste_ficha(0.25) == "La macro la subió (+0,25)."
    assert textos.ajuste_ficha(-0.25) == "La macro la bajó (−0,25)."
    assert textos.ajuste_ficha(0.0) == "La macro no la tocó."
    assert textos.ajuste_ficha(None) is None
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_textos.py -q`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Escribir `macro/textos.py`**

```python
# macro/textos.py
"""Lo que el usuario lee del entorno macro. Nunca se guarda en disco.

Las claves de `macro/criterio.py` son el dato; esto es solo cómo se dicen. Es
la lección de «La etiqueta de pantalla que se guardaba en disco» (CONTEXTO.md).
"""

from datetime import date

NOMBRE_FASE = {
    "recuperacion": "Recuperación",
    "expansion": "Expansión",
    "desaceleracion": "Desaceleración",
    "contraccion": "Contracción",
}

NOMBRE_REGION = {
    "usa": "Estados Unidos",
    "mex": "México",
    "eurozona": "Eurozona (4 grandes)",
    "china": "China",
    "g7": "Global (G7)",
}

NOMBRE_SECTOR = {
    "Communication Services": "Comunicaciones",
    "Consumer Discretionary": "Consumo discrecional",
    "Consumer Staples": "Consumo básico",
    "Energy": "Energía",
    "Financials": "Financieras",
    "Health Care": "Salud",
    "Industrials": "Industriales",
    "Information Technology": "Tecnología",
    "Materials": "Materiales",
    "Real Estate": "Inmobiliarias",
    "Utilities": "Servicios públicos",
}

POR_QUE = {
    "recuperacion": {
        "Financials": "La curva se empina y el crédito vuelve: el margen de los bancos se ensancha.",
        "Consumer Discretionary": "La renta y el empleo se recuperan, y el gasto que se aplazó vuelve.",
        "Industrials": "Las empresas reponen inventarios y retoman la inversión aplazada.",
        "Utilities": "Su refugio pesa menos cuando el riesgo vuelve a pagarse.",
        "Consumer Staples": "Su estabilidad deja de cotizar con prima cuando todo crece.",
        "Health Care": "Defensiva: sus beneficios no dependen del ciclo y se quedan atrás en el rebote.",
    },
    "expansion": {
        "Information Technology": "La inversión empresarial en tecnología crece con el ciclo asentado.",
        "Communication Services": "Publicidad y suscripciones acompañan al consumo firme.",
        "Industrials": "Los pedidos y la capacidad utilizada siguen subiendo.",
        "Utilities": "Los tipos suben y su dividendo compite peor con la renta fija.",
        "Materials": "Sus precios ya recogieron la recuperación y el margen deja de crecer.",
    },
    "desaceleracion": {
        "Energy": "Al final del ciclo la demanda aprieta la oferta y las materias primas suben.",
        "Materials": "Igual que la energía: precios altos con la capacidad ya al límite.",
        "Consumer Staples": "Se vende lo mismo aunque el ciclo se enfríe.",
        "Health Care": "Beneficios que no dependen del ciclo cuando el ciclo empieza a fallar.",
        "Information Technology": "Las valoraciones altas sufren cuando el crecimiento esperado baja.",
        "Consumer Discretionary": "Es lo primero que se recorta cuando el hogar se aprieta.",
    },
    "contraccion": {
        "Consumer Staples": "Comida, higiene y hogar se compran también en recesión.",
        "Health Care": "La demanda médica no espera al ciclo.",
        "Utilities": "Ingresos regulados y tipos que bajan: el refugio clásico.",
        "Industrials": "Los pedidos se cancelan y la capacidad sobra.",
        "Information Technology": "La inversión en tecnología se aplaza y los múltiplos se comprimen.",
        "Consumer Discretionary": "El gasto que se puede aplazar, se aplaza.",
    },
}

MOTIVO = {
    "indeterminada": "El indicador no se decide: el último mes desmiente la tendencia de tres meses.",
    "serie_corta": "No hay meses suficientes para leer una dirección.",
    "dato_rancio": "El último dato tiene más de tres meses; no se usa para mover el Top.",
    "sin_red": "La OCDE no responde y no hay nada guardado.",
    "serie_desconocida": "La OCDE no tiene esa serie; puede que haya cambiado su catálogo.",
    "respuesta_ilegible": "La OCDE respondió algo que no es la tabla esperada.",
}

AVISO_EVIDENCIA = (
    "La rotación de sectores por fase del ciclo tiene una evidencia floja: el ciclo "
    "se fecha bien a toro pasado y mal en tiempo real. La inclinación es pequeña y "
    "no promete rentabilidad."
)

_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def mes_legible(mes: "date | str") -> str:
    if isinstance(mes, str):
        mes = date.fromisoformat(mes)
    return f"{_MESES[mes.month - 1]} {mes.year}"


def etiqueta_corrida(bloque: "dict | None") -> str:
    if not bloque:
        return "sin macro"
    return (
        f"con macro: {NOMBRE_FASE[bloque['fase']]} "
        f"({NOMBRE_REGION[bloque['region']]}, {mes_legible(bloque['mes_dato'])})"
    )


def lo_que_movio(bloque: dict) -> str:
    cabeza = (
        f"El Top está inclinado por la fase **{NOMBRE_FASE[bloque['fase']]}** de "
        f"{NOMBRE_REGION[bloque['region']]} (dato de {mes_legible(bloque['mes_dato'])}). "
    )
    if not bloque["entradas"] and not bloque["salidas"]:
        return cabeza + "Con esta inclinación la lista no cambió."
    return (
        cabeza
        + f"Entraron por la macro: {', '.join(bloque['entradas']) or 'ninguna'}. "
        + f"Salieron por la macro: {', '.join(bloque['salidas']) or 'ninguna'}."
    )


def ajuste_ficha(ajuste: "float | None") -> "str | None":
    if ajuste is None:
        return None
    # Coma decimal, como el resto de la pantalla: `f"{0.25:.2f}"` da «0.25».
    cifra = f"{abs(ajuste):.2f}".replace(".", ",")
    if ajuste > 0:
        return f"La macro la subió (+{cifra})."
    if ajuste < 0:
        return f"La macro la bajó (−{cifra})."
    return "La macro no la tocó."
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_textos.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add macro/textos.py tests/test_macro_textos.py
git commit -m "feat(macro): los textos de pantalla, aparte de las claves que se guardan"
```

---

### Task 12: `region_macro` en las preferencias

**Files:**
- Modify: `preferencias.py` (dataclass `Preferencias` y `saneadas`)
- Test: `tests/test_preferencias.py` (añadir)

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_la_region_macro_por_defecto_es_usa():
    from preferencias import Preferencias
    assert Preferencias().region_macro == "usa"


def test_una_region_macro_desconocida_cae_a_usa_y_avisa():
    from preferencias import Preferencias
    limpias, avisos = Preferencias(region_macro="marte").saneadas()
    assert limpias.region_macro == "usa"
    assert any("región" in a for a in avisos)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_preferencias.py -q`
Expected: FAIL con `TypeError: ... unexpected keyword argument 'region_macro'`

- [ ] **Step 3: Implementar**

En `preferencias.py`:

```python
from macro.criterio import REGION_POR_DEFECTO, REGIONES
```

En la dataclass, tras `guia_vista: bool = False`:

```python
    region_macro: str = REGION_POR_DEFECTO
```

En `saneadas`, antes de `return (replace(...`:

```python
        if self.region_macro not in REGIONES:
            avisos.append(
                f"La región macro guardada ({self.region_macro!r}) ya no existe; "
                "se usa Estados Unidos."
            )
            cambios["region_macro"] = REGION_POR_DEFECTO
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_preferencias.py -q`
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add preferencias.py tests/test_preferencias.py
git commit -m "feat(preferencias): recordar la región del entorno macro"
```

---

### Task 13: `macro/lectura.py` — la lectura con IA

**Files:**
- Create: `macro/lectura.py`
- Create: `tests/test_macro_lectura.py`
- Modify: `.gitignore` (añadir `lecturas_macro/` en el bloque de `analisis/`: es lo que pagó el usuario)

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_macro_lectura.py
from datetime import date
from types import SimpleNamespace

import pandas as pd

from macro import lectura
from macro.contexto import ContextoUSA
from macro.estado import Estado
from macro.fase import Fase


def _estado(region="usa"):
    serie = pd.Series(
        [100.5, 100.6, 100.7, 100.8],
        index=pd.period_range("2026-07", periods=4, freq="M").to_timestamp(),
    )
    return Estado(region, serie, Fase("expansion", None, date(2026, 10, 1), 100.8, 0.3, 4), None, None, False)


class _Cliente:
    def __init__(self):
        self.llamadas = 0
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.llamadas += 1
        self.ultimo = kwargs
        return SimpleNamespace(
            parsed_output=lectura.SalidaLectura(explicacion="Crece.", vigilar=["El empleo."]),
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        )


def test_el_prompt_lleva_fase_region_sectores_y_contexto():
    texto = lectura.contexto_prompt(_estado(), ContextoUSA(0.8, False, 0.1, False, 0.03))
    assert "Expansión" in texto and "Estados Unidos" in texto
    assert "Tecnología" in texto and "curva" in texto.lower()


def test_sin_contexto_usa_no_lo_inventa():
    texto = lectura.contexto_prompt(_estado("mex"), None)
    assert "curva" not in texto.lower()


def test_leer_llama_una_vez_y_la_segunda_sale_del_archivo(tmp_path):
    cliente = _Cliente()
    primera = lectura.leer(_estado(), None, raiz=tmp_path, cliente=cliente)
    assert primera.explicacion == "Crece." and primera.coste_usd > 0
    segunda = lectura.leer(_estado(), None, raiz=tmp_path, cliente=cliente)
    assert cliente.llamadas == 1
    assert segunda.explicacion == "Crece." and segunda.coste_usd == 0.0


def test_sin_fase_no_se_llama(tmp_path):
    cliente = _Cliente()
    vacio = Estado("usa", None, None, "sin_red", None, False)
    r = lectura.leer(vacio, None, raiz=tmp_path, cliente=cliente)
    assert cliente.llamadas == 0 and r.problema
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_macro_lectura.py -q`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Escribir `macro/lectura.py`**

```python
# macro/lectura.py
"""La lectura con IA del entorno macro. Explica; no toca el Top.

Se guarda por región y mes del dato: con el mismo dato la explicación sería la
misma, así que preguntar dos veces en un mes no paga dos veces. Vive en
`lecturas_macro/`, fuera de git, como `analisis/`: lo pagó el usuario.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from interprete import cliente as cliente_ia
from macro import textos
from macro.criterio import SECTORES_POR_FASE
from noticias import cache

RAIZ = Path(__file__).resolve().parent.parent / "lecturas_macro"
_PARA_SIEMPRE = timedelta(days=36_500)

SISTEMA = (
    "Eres un analista macroeconómico. Explicas en castellano llano, sin jerga "
    "innecesaria, en qué fase del ciclo está una economía según los datos que se "
    "te dan, y qué indicadores conviene vigilar en los próximos meses. No "
    "recomiendas comprar ni vender nada. No inventas datos que no se te hayan dado."
)


class SalidaLectura(BaseModel):
    explicacion: str
    vigilar: list[str]


@dataclass(frozen=True)
class Lectura:
    explicacion: str = ""
    vigilar: tuple = ()
    coste_usd: float = 0.0
    problema: str = ""


def contexto_prompt(estado, contexto) -> str:
    fase = estado.fase
    listas = SECTORES_POR_FASE[fase.clave]
    nombres = lambda sectores: ", ".join(textos.NOMBRE_SECTOR[s] for s in sectores)
    ultimos = estado.serie.dropna().iloc[-12:]
    lineas = [
        f"Región: {textos.NOMBRE_REGION[estado.region]}.",
        f"Fase según el indicador adelantado de la OCDE: {textos.NOMBRE_FASE[fase.clave]}, "
        f"dato de {textos.mes_legible(fase.mes_dato)}, {fase.meses_en_fase} meses en ella.",
        "Últimos doce meses del indicador (100 es la tendencia): "
        + ", ".join(f"{d:%Y-%m} {v:.2f}" for d, v in ultimos.items()) + ".",
        f"Sectores que la fase favorece: {nombres(listas['favorecidos'])}.",
        f"Sectores que desfavorece: {nombres(listas['desfavorecidos'])}.",
    ]
    if contexto is not None:
        if contexto.curva is not None:
            lineas.append(f"Curva de tipos 10 años menos 3 meses: {contexto.curva:.2f} puntos.")
        if contexto.sahm is not None:
            lineas.append(f"Regla de Sahm: {contexto.sahm:.2f} (se activa en 0,50).")
        if contexto.inflacion is not None:
            lineas.append(f"Inflación interanual: {contexto.inflacion:.1%}.")
    lineas.append(
        "Explica la fase en dos o tres párrafos y da entre tres y cinco cosas que vigilar."
    )
    return "\n".join(lineas)


def leer(estado, contexto, *, raiz: Path = RAIZ, cliente=None) -> Lectura:
    if estado.fase is None or estado.fase.clave is None:
        return Lectura(problema="Sin una fase determinada no hay nada que leer.")

    llave = f"{estado.region}_{estado.fase.mes_dato.isoformat()}"
    guardada = cache.leer(raiz, "macro", llave, _PARA_SIEMPRE)
    if guardada is not None and isinstance(guardada.datos, dict):
        return Lectura(guardada.datos["explicacion"], tuple(guardada.datos["vigilar"]))

    respuesta = cliente_ia.preguntar(
        SISTEMA,
        [{"role": "user", "content": contexto_prompt(estado, contexto)}],
        SalidaLectura,
        cliente=cliente,
    )
    if respuesta.salida is None:
        return Lectura(problema=respuesta.problema)

    salida = respuesta.salida
    try:
        cache.guardar(raiz, "macro", llave, {"explicacion": salida.explicacion, "vigilar": salida.vigilar})
    except OSError:
        pass
    return Lectura(
        salida.explicacion,
        tuple(salida.vigilar),
        cliente_ia.coste(respuesta.entrada_tokens, respuesta.salida_tokens),
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_macro_lectura.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add macro/lectura.py tests/test_macro_lectura.py .gitignore
git commit -m "feat(macro): la lectura con IA del entorno, guardada por región y mes"
```

---

### Task 14: La pantalla «Entorno macro»

**Files:**
- Create: `vistas/entorno_macro.py`
- Modify: `app.py` (menú «Análisis», tras Analizador)
- Test: `tests/test_navegacion.py` (añadir)

- [ ] **Step 1: Escribir el test de navegación que falla**

```python
def test_entorno_macro_esta_en_analisis_tras_el_analizador():
    assert "vistas/entorno_macro.py" in _paginas_declaradas()
    fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
    analisis = fuente.split('"Análisis":', 1)[1].split('"Cartera":', 1)[0]
    assert analisis.index("vistas/analizador.py") < analisis.index("vistas/entorno_macro.py")
```

Se llama `entorno_macro.py` y no `macro.py` para que el nombre de la página no pueda tapar al paquete `macro` en ningún `sys.path`.

- [ ] **Step 2: Comprobar que falla**

Run: `uv run pytest tests/test_navegacion.py -q`
Expected: FAIL

- [ ] **Step 3: Añadir la página al menú**

En `app.py`, dentro de `"Análisis": [`, tras la página del Analizador:

```python
            st.Page(
                "vistas/entorno_macro.py", title="Entorno macro",
                icon=":material/public:",
            ),
```

- [ ] **Step 4: Escribir `vistas/entorno_macro.py`**

```python
"""Entorno macro: en qué fase del ciclo está una región, y qué favorece.

Widgets sin lógica. La regla está en `macro/fase.py`, los datos en
`macro/fuentes.py` y las palabras en `macro/textos.py`, todo con tests.

**Aquí no se recomienda nada.** La fase inclina el Top solo si se activa en
Revisar candidatos, y la evidencia de que eso aporte es floja: se dice.
"""

from datetime import date

import plotly.graph_objects as go
import streamlit as st

import preferencias as preferencias_mod
import tema
from interprete import cliente as cliente_ia
from macro import contexto as contexto_mod
from macro import fuentes, lectura, textos
from macro.criterio import NIVEL_NEUTRO, REGIONES, SECTORES_POR_FASE
from macro.estado import leer_region
from macro.fase import fases_por_mes

COSTE_MAXIMO = 0.03

st.markdown(
    tema.cabecera(
        "Entorno macro",
        "La fase del ciclo de una región, leída en el indicador adelantado de la "
        "OCDE, y los sectores que esa fase suele favorecer.",
    ),
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner="Descargando el indicador de la OCDE...")
def _estado(region: str, hoy: date):
    return leer_region(region, hoy)


@st.cache_data(ttl=3600, show_spinner="Descargando FRED...")
def _contexto_usa():
    series = {
        nombre: fuentes.traer_fred(serie).datos
        for nombre, serie in contexto_mod.SERIES.items()
    }
    return contexto_mod.calcular(**series)


guardadas, _ = preferencias_mod.cargar()
claves = list(REGIONES)
region = st.selectbox(
    "Región",
    claves,
    index=claves.index(guardadas.region_macro),
    format_func=textos.NOMBRE_REGION.get,
    key="region_macro_pantalla",
)
if region != guardadas.region_macro:
    from dataclasses import replace

    preferencias_mod.guardar(replace(guardadas, region_macro=region))

estado = _estado(region, date.today())

# Sin serie, o con tan pocos meses que no hay ni nivel: no hay nada que pintar.
if estado.fase is None or estado.fase.motivo == "serie_corta":
    st.warning(textos.MOTIVO[estado.motivo_no_inclinar])
    st.stop()

fase = estado.fase
columna_fase, columna_dato = st.columns([2, 1])
with columna_fase:
    if fase.clave is None:
        st.markdown("### Fase indeterminada")
        st.caption(textos.MOTIVO[fase.motivo])
    else:
        st.markdown(f"### {textos.NOMBRE_FASE[fase.clave]}")
        st.caption(f"Lleva {fase.meses_en_fase} meses en esta fase.")
with columna_dato:
    st.metric("Indicador adelantado", f"{fase.nivel:.2f}", f"{fase.cambio:+.2f} en 3 meses")
    st.caption(f"Dato de {textos.mes_legible(fase.mes_dato)}.")

if estado.vieja:
    st.warning("La OCDE no responde: esto es lo último que se guardó.")
if estado.motivo_no_inclinar == "dato_rancio":
    st.warning(textos.MOTIVO["dato_rancio"])

# El gráfico: los últimos cinco años, con la línea de 100 y cada mes coloreado por su fase.
colores = {"recuperacion": "#4c9be8", "expansion": "#3fb37f",
           "desaceleracion": "#e8a33c", "contraccion": "#d9534f"}
serie = estado.serie.iloc[-60:]
por_mes = fases_por_mes(estado.serie).reindex(serie.index)
figura = go.Figure()
figura.add_trace(go.Scatter(x=serie.index, y=serie, mode="lines", name="CLI",
                            line={"color": "#888"}))
for clave, color in colores.items():
    marcados = serie[por_mes == clave]
    figura.add_trace(go.Scatter(x=marcados.index, y=marcados, mode="markers",
                                name=textos.NOMBRE_FASE[clave], marker={"color": color, "size": 6}))
figura.add_hline(y=NIVEL_NEUTRO, line_dash="dot")
figura.update_layout(height=320, margin={"l": 10, "r": 10, "t": 10, "b": 10})
st.plotly_chart(figura, use_container_width=True)

if fase.clave is not None:
    listas = SECTORES_POR_FASE[fase.clave]
    favorecidos, desfavorecidos = st.columns(2)
    with favorecidos:
        st.markdown("**Suele favorecer**")
        for sector in listas["favorecidos"]:
            st.markdown(f"- **{textos.NOMBRE_SECTOR[sector]}**: {textos.POR_QUE[fase.clave][sector]}")
    with desfavorecidos:
        st.markdown("**Suele desfavorecer**")
        for sector in listas["desfavorecidos"]:
            st.markdown(f"- **{textos.NOMBRE_SECTOR[sector]}**: {textos.POR_QUE[fase.clave][sector]}")

st.info(textos.AVISO_EVIDENCIA)

contexto = None
if region == "usa":
    contexto = _contexto_usa()
    st.markdown("#### Contexto de EE. UU.")
    curva, sahm, inflacion = st.columns(3)
    curva.metric("Curva 10a − 3m", "—" if contexto.curva is None else f"{contexto.curva:+.2f}")
    if contexto.curva_invertida:
        curva.caption("Invertida: históricamente ha precedido a las recesiones.")
    sahm.metric("Regla de Sahm", "—" if contexto.sahm is None else f"{contexto.sahm:.2f}")
    if contexto.sahm_activada:
        sahm.caption("Activada: el desempleo sube como al empezar una recesión.")
    inflacion.metric("Inflación interanual",
                     "—" if contexto.inflacion is None else f"{contexto.inflacion:.1%}")
    st.caption("El contexto no entra en la fase: se enseña al lado.")
else:
    st.caption("El contexto de curva, desempleo e inflación solo está para EE. UU.")

st.markdown("#### Lectura con IA")
if not cliente_ia.hay_clave():
    st.caption("Hace falta la clave de Anthropic, en Perfil y ajustes.")
elif fase.clave is not None and st.button(
    f"Leer con IA (hasta {COSTE_MAXIMO:.2f} \\$)", icon=":material/auto_awesome:"
):
    with st.spinner("Leyendo..."):
        resultado = lectura.leer(estado, contexto)
    if resultado.problema:
        st.error(resultado.problema)
    else:
        st.markdown(resultado.explicacion)
        st.markdown("**Qué vigilar**")
        for punto in resultado.vigilar:
            st.markdown(f"- {punto}")
        st.caption(
            "Guardada de antes: no costó nada." if resultado.coste_usd == 0
            else f"Costó {resultado.coste_usd:.3f} \\$."
        )
```

`COSTE_MAXIMO = 0.03` sale de `interprete.cliente.coste(1500, 2000)`, que da 0,023 $: un prompt de unos 1.500 tokens y una salida limitada por `MAX_TOKENS = 2000`.

- [ ] **Step 5: Comprobarlo en la app**

Run: `uv run pytest tests/test_navegacion.py -q` → verde.

Después, abrir la app con `preview_start` (configuración de `.claude/launch.json` de la raíz) e ir a «Entorno macro». Comprobar que:
- con EE. UU. sale una fase, el gráfico, los sectores, el contexto y el aviso;
- al cambiar a Eurozona sale «Eurozona (4 grandes)» y desaparece el contexto;
- no hay errores en consola ni en `preview_logs`.

- [ ] **Step 6: Commit**

```bash
git add vistas/entorno_macro.py app.py tests/test_navegacion.py
git commit -m "feat: la pantalla Entorno macro, con su región, su fase y su lectura con IA"
```

---

### Task 15: La casilla en Revisar candidatos

**Files:**
- Modify: `vistas/candidatos.py` (`_generar`, el contenedor de generación, tras `st.info(resumen_corrida(...))` y dentro de «Ver la ficha completa»)

- [ ] **Step 1: Pasar la fase a la corrida**

Cambiar la firma y la llamada de `_generar`:

```python
def _generar(con_ia: bool, estado_macro=None) -> None:
```

```python
            guardar(
                construir_ranking(
                    con_llm=con_ia,
                    macro=estado_macro.fase if estado_macro else None,
                    region=estado_macro.region if estado_macro else None,
                ),
                "salidas",
            )
```

- [ ] **Step 2: La casilla y el selector, dentro del contenedor de generación**

Imports nuevos arriba:

```python
from datetime import date

import preferencias as preferencias_mod
from macro import textos as textos_macro
from macro.criterio import REGIONES
from macro.estado import leer_region
```

Y una función cacheada junto a `_generar`:

```python
@st.cache_data(ttl=3600, show_spinner="Leyendo la fase macro...")
def _estado_macro(region: str, hoy: date):
    return leer_region(region, hoy)
```

Dentro de `with st.container(border=True):`, después del bloque de `columna_modo, columna_boton` y **antes** de que se use `pulsado`:

```python
    # Apagada y sin recordar entre sesiones, a propósito: el Top de siempre es el
    # criterio congelado, y activar uno que no lo es tiene que ser un gesto
    # consciente cada vez (spec de O, «Pantallas»).
    inclinar = st.checkbox("Inclinar el Top por la fase macro", value=False, key="inclinar_macro")
    estado_macro = None
    if inclinar:
        guardadas, _ = preferencias_mod.cargar()
        claves = list(REGIONES)
        region = st.selectbox(
            "Región del ciclo", claves,
            index=claves.index(guardadas.region_macro),
            format_func=textos_macro.NOMBRE_REGION.get,
            key="region_macro_candidatos",
        )
        estado = _estado_macro(region, date.today())
        if estado.motivo_no_inclinar:
            st.warning(
                textos_macro.MOTIVO[estado.motivo_no_inclinar]
                + " La corrida saldrá sin macro."
            )
        else:
            estado_macro = estado
            st.caption(
                f"Se usará la fase **{textos_macro.NOMBRE_FASE[estado.fase.clave]}** "
                f"(dato de {textos_macro.mes_legible(estado.fase.mes_dato)})."
            )
```

Y donde la página llama a `_generar(con_ia)` (dentro del flujo del botón y de su confirmación de pago, en la sección «El paso que separa un clic de un dólar y medio»), pasar `_generar(con_ia, estado_macro)`. Revisar con `grep -n "_generar(" vistas/candidatos.py` todas las llamadas: si la del modo con IA ocurre en un rerun posterior (tras confirmar el pago), `estado_macro` se recalcula en ese rerun con la casilla en el mismo estado, así que vale el mismo valor.

- [ ] **Step 3: Lo que movió la macro, y la línea de la ficha**

Tras `st.info(resumen_corrida(candidatos.corrida))`:

```python
_bloque_macro = (candidatos.corrida or {}).get("macro")
if _bloque_macro:
    st.info(textos_macro.lo_que_movio(_bloque_macro))
```

Dentro de `with st.expander(f"Ver la ficha completa de {ticker}"):`, al principio:

```python
        if _bloque_macro:
            st.caption(textos_macro.ajuste_ficha(ficha.get("ajuste_macro")))
```

(`.get`: las fichas anteriores a O no traen la clave.)

- [ ] **Step 4: Comprobarlo en la app**

Con `preview_start`, en Revisar candidatos:
- la casilla sale desmarcada;
- al marcarla salen el selector y la fase;
- «Generar gratis» con la casilla marcada termina con el bloque «El Top está inclinado…» y la línea de ajuste en las fichas;
- con la casilla desmarcada no sale ninguna de las dos cosas.

Sin `EDGAR_IDENTITY` no se puede generar: en ese caso comprobar solo la casilla y el selector, y decirlo en el commit.

Run: `uv run pytest tests/ -q -m "not red"` → verde.

- [ ] **Step 5: Commit**

```bash
git add vistas/candidatos.py
git commit -m "feat: Revisar candidatos puede inclinar el Top por la fase macro"
```

---

### Task 16: Las actas dicen si hubo macro

**Files:**
- Modify: `vistas/actas.py:70-76`

- [ ] **Step 1: Añadir la etiqueta**

Sustituir el `st.caption(...)` de la corrida por:

```python
                st.caption(
                    f"Universo {corrida.get('universo', '?')} · "
                    f"{corrida.get('n_supervivientes', '?')} supervivientes de "
                    f"{corrida.get('n_panel', '?')} empresas con datos · "
                    + ("con IA" if corrida.get("con_llm") else "sin IA")
                    + " · "
                    + textos_macro.etiqueta_corrida(corrida.get("macro"))
                )
```

con `from macro import textos as textos_macro` arriba. Un acta vieja sin la clave lee `None`, que da «sin macro». Eso ya lo cubre `test_resumen_sin_macro`.

- [ ] **Step 2: Comprobarlo en la app**

Abrir «Actas de aprobación» con `preview_start`: las actas existentes dicen «sin macro» y no hay error.

- [ ] **Step 3: Commit**

```bash
git add vistas/actas.py
git commit -m "feat: las actas dicen si la corrida llevaba macro"
```

---

### Task 17: Suite completa y CONTEXTO.md

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Suite completa**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: los 3.494 de antes más los nuevos, todos pasando, con los mismos 3 omitidos.

Run: `uv run pytest tests/test_macro_red.py -q -m red`
Expected: `8 passed`

- [ ] **Step 2: Actualizar CONTEXTO.md**

- En la tabla de sub-proyectos, añadir: `| O | Entorno macro | Fase del ciclo por región (CLI OCDE) e inclinación opcional del Top | ✅ **terminado** |`.
- Actualizar la cabecera: fecha, número de tests y la rama.
- Añadir una sección «Resultado del sub-proyecto O» que cuente:
  - la regla (nivel frente a 100 y dirección a 3 meses);
  - por qué la Eurozona es `G4E`;
  - que la inclinación viene apagada y no se recuerda;
  - que el compuesto de la ficha es el sin inclinar;
  - que si la OCDE cambia la versión del flujo, el primer aviso es `test_macro_red.py`;
  - que sigue pendiente medir si la inclinación aporta, con un estudio tipo D preregistrado.
- En «Qué hay en el repo», añadir el árbol de `macro/`.

- [ ] **Step 3: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: CONTEXTO con el sub-proyecto O, el entorno macro"
```
