# Rendimiento real en pesos: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al panel de Seguimiento la TWR y la TIR en pesos, la inflación
del periodo (INPC) y sus versiones reales por la ecuación de Fisher. El tipo de
cambio FIX y el INPC vienen del SIE de Banxico.

**Architecture:** La responsabilidad se reparte en tres unidades.

- `seguimiento/banxico.py` descarga y guarda en caché las dos series. No hace
  cuentas.
- `seguimiento/fisher.py` hace la conversión a pesos, la interpolación y
  extensión del INPC, y Fisher. Son funciones puras, sin red.
- `seguimiento/panel.py` gana una `CabeceraPesos`, separada de `Cabecera`, que
  usa `rendimiento.twr` y `rendimiento.tir_detallada` sin modificarlas.

La pantalla solo pinta. El token de Banxico entra en `credenciales.py` como un
tercer campo.

**Tech Stack:** Python 3, pandas, `urllib.request` de la librería estándar (sin
dependencias nuevas), Streamlit y pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-rendimiento-real-mxn-design.md`

**Comando de tests:** `uv run pytest tests/ -q -m "not red"`, desde `programa/`.
El punto de partida es 1.766 tests pasando.

---

## Mapa de ficheros

| Fichero | Qué cambia |
|---|---|
| `seguimiento/fisher.py` | **Nuevo.** `real`, `en_pesos`, `nivel`, `inflacion_periodo`, `Inflacion` |
| `seguimiento/banxico.py` | **Nuevo.** `traer`, `parsear`, `caduca`, `token`, `Serie` |
| `seguimiento/panel.py` | `CabeceraPesos`, `cabecera_pesos`, `notas_pesos` |
| `credenciales.py` | Campo `banxico_token` y variable `BANXICO_TOKEN` |
| `vistas/perfil.py` | Campo del token con el enlace a Banxico |
| `vistas/seguimiento.py` | Descarga en caché, fila «En pesos (MXN)» y columnas del Excel |
| `.gitignore` | `seguimiento/.cache/` |
| `tests/test_seguimiento_fisher.py` | **Nuevo** |
| `tests/test_seguimiento_banxico.py` | **Nuevo** (incluye un test `red` contra la API real) |
| `tests/test_panel_pesos.py` | **Nuevo** |
| `tests/test_credenciales.py` | Tests del token |

---

### Task 1: Fisher exacto

**Files:**
- Create: `seguimiento/fisher.py`
- Test: `tests/test_seguimiento_fisher.py`

- [ ] **Step 1: Escribir el test que falla**

```python
"""La parte pura del rendimiento real en pesos: conversion, INPC y Fisher."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import fisher


def test_fisher_es_el_exacto_y_no_la_resta():
    # 1,10 / 1,04 − 1 = 5,769...%. La aproximacion `nominal − π` daria 6%.
    assert fisher.real(0.10, 0.04) == pytest.approx(0.0576923077)
    assert fisher.real(0.10, 0.04) != pytest.approx(0.06)


def test_fisher_con_inflacion_cero_es_el_nominal():
    assert fisher.real(0.087, 0.0) == pytest.approx(0.087)


def test_fisher_sin_alguna_de_las_dos_no_inventa():
    assert fisher.real(None, 0.04) is None
    assert fisher.real(0.10, None) is None
```

- [ ] **Step 2: Ejecutarlo y ver que falla**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: FAIL con `ModuleNotFoundError` o `cannot import name 'fisher'`.

- [ ] **Step 3: Implementar lo mínimo**

Crear `seguimiento/fisher.py`:

```python
"""Del rendimiento en dolares al rendimiento real en pesos.

Tres pasos, en este orden y no en otro: convertir a pesos con el FIX de cada
fecha, medir con las mismas funciones de `rendimiento`, y descontar la
inflacion con Fisher. Descontar el INPC de un rendimiento en dolares mezcla dos
monedas y da un numero plausible que no mide nada.

Aqui no hay red: las series llegan ya descargadas de `seguimiento/banxico.py`.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from seguimiento import rendimiento


def real(nominal: "float | None", inflacion_anual: "float | None") -> "float | None":
    """Ecuacion de Fisher exacta: `(1 + nominal) / (1 + π) − 1`.

    No `nominal − π`. Con la inflacion mexicana la aproximacion se equivoca en
    decimas, y en pantalla esa diferencia no se veria. Un `None` en cualquiera
    de las dos entradas es «no se puede medir», y lo sigue siendo a la salida.
    """
    if nominal is None or inflacion_anual is None or inflacion_anual <= -1.0:
        return None
    return (1.0 + nominal) / (1.0 + inflacion_anual) - 1.0
```

- [ ] **Step 4: Ejecutarlo y ver que pasa**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add seguimiento/fisher.py tests/test_seguimiento_fisher.py
git commit -m "feat: la ecuacion de Fisher exacta, no la resta"
```

---

### Task 2: Convertir la serie a pesos

**Files:**
- Modify: `seguimiento/fisher.py`
- Test: `tests/test_seguimiento_fisher.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_seguimiento_fisher.py`:

```python
def _serie(pares):
    return pd.Series(
        [v for _, v in pares], index=pd.DatetimeIndex([d for d, _ in pares]), dtype=float
    )


def test_con_fix_constante_los_pesos_son_los_dolares_por_el_fix():
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 110.0)])
    flujos = _serie([("2026-03-02", 100.0), ("2026-03-03", 0.0)])
    fix = _serie([("2026-03-02", 17.0), ("2026-03-03", 17.0)])

    valor_mxn, flujos_mxn = fisher.en_pesos(valor, flujos, fix)

    assert list(valor_mxn) == [1700.0, 1870.0]
    assert list(flujos_mxn) == [1700.0, 0.0]


def test_cada_flujo_se_convierte_al_fix_de_su_dia():
    # Cartera plana en dolares, el dolar sube un 10% el segundo dia y el tercero
    # entra una aportacion. La TWR en pesos tiene que ser el 10% del tipo de
    # cambio y nada mas: la aportacion no rinde, solo entra.
    valor = _serie([("2026-03-02", 100.0), ("2026-03-03", 100.0), ("2026-03-04", 200.0)])
    flujos = _serie([("2026-03-02", 100.0), ("2026-03-03", 0.0), ("2026-03-04", 100.0)])
    fix = _serie([("2026-03-02", 10.0), ("2026-03-03", 11.0), ("2026-03-04", 11.0)])

    valor_mxn, flujos_mxn = fisher.en_pesos(valor, flujos, fix)

    assert flujos_mxn.loc["2026-03-04"] == pytest.approx(1100.0)
    assert rendimiento.twr(valor_mxn, flujos_mxn) == pytest.approx(0.10)


def test_un_dia_sin_fix_usa_el_ultimo_publicado():
    # Un festivo mexicano que en EE. UU. es habil: hay cierre y no hay FIX.
    valor = _serie([("2026-03-13", 100.0), ("2026-03-16", 100.0)])
    flujos = _serie([("2026-03-13", 100.0), ("2026-03-16", 0.0)])
    fix = _serie([("2026-03-13", 18.0)])

    valor_mxn, _ = fisher.en_pesos(valor, flujos, fix)

    assert valor_mxn.loc["2026-03-16"] == pytest.approx(1800.0)


def test_sin_fix_para_el_primer_dia_no_se_inventa_hacia_atras():
    valor = _serie([("2026-01-02", 100.0), ("2026-01-05", 100.0)])
    flujos = _serie([("2026-01-02", 100.0), ("2026-01-05", 0.0)])
    fix = _serie([("2026-01-05", 17.5)])

    assert fisher.en_pesos(valor, flujos, fix) is None


def test_sin_serie_de_fix_no_hay_conversion():
    valor = _serie([("2026-01-02", 100.0)])
    assert fisher.en_pesos(valor, valor, None) is None
    assert fisher.en_pesos(valor, valor, pd.Series(dtype=float)) is None
```

Y añadir `from seguimiento import rendimiento` a los imports del test.

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: 5 FAIL con `AttributeError: module 'seguimiento.fisher' has no attribute 'en_pesos'`.

- [ ] **Step 3: Implementar**

Añadir a `seguimiento/fisher.py`:

```python
def en_pesos(
    valor: pd.Series, flujos: pd.Series, fix: "pd.Series | None"
) -> "tuple[pd.Series, pd.Series] | None":
    """El valor diario y los flujos, en pesos, con el FIX de cada fecha.

    Flujo a flujo y no con el atajo `(1 + r_USD)(1 + Δtc) − 1`: el atajo da la
    TWR bien, pero la TIR sale mal en cuanto hay aportaciones, porque cada una
    entro a un tipo de cambio distinto.

    Un dia sin FIX (fin de semana, o un festivo mexicano que en EE. UU. es habil)
    usa el ultimo publicado. **Hacia atras no se arrastra nada**: si la serie
    empieza antes del primer FIX disponible devuelve `None`, porque el tipo de
    cambio de ese dia no lo sabe nadie aqui.
    """
    if fix is None or fix.empty:
        return None
    fix = fix.sort_index()
    calendario = valor.index.union(flujos.index)
    alineado = fix.reindex(fix.index.union(calendario)).ffill().reindex(calendario)
    if alineado.isna().any():
        return None
    return valor * alineado.reindex(valor.index), flujos * alineado.reindex(flujos.index)
```

- [ ] **Step 4: Ejecutarlos y ver que pasan**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add seguimiento/fisher.py tests/test_seguimiento_fisher.py
git commit -m "feat: convertir la serie a pesos con el FIX de cada dia"
```

---

### Task 3: La inflación del periodo desde el INPC

**Files:**
- Modify: `seguimiento/fisher.py`
- Test: `tests/test_seguimiento_fisher.py`

Banxico fecha cada dato mensual en el día 1 (`01/08/2026` es el INPC de
agosto). Aquí ese dato se trata como el nivel **al cierre** del mes: el INPC
de agosto se ancla en el 31 de agosto.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_seguimiento_fisher.py`:

```python
# Tal como llega de `banxico.traer`: fechado el dia 1 de cada mes.
INPC = _serie([("2026-01-01", 100.0), ("2026-02-01", 101.0), ("2026-03-01", 102.01)])


def test_el_dato_mensual_es_el_nivel_al_cierre_del_mes():
    anclado = fisher.anclar(INPC)
    assert fisher.nivel(anclado, date(2026, 2, 28)) == pytest.approx(101.0)


def test_dentro_del_mes_se_interpola_de_forma_geometrica():
    # A mitad de febrero (14 de 28 dias): 100 · 1,01^0,5 = 100,4988. La lineal
    # daria 100,5.
    anclado = fisher.anclar(INPC)
    medio = fisher.nivel(anclado, date(2026, 2, 14))
    assert medio == pytest.approx(100.0 * 1.01 ** 0.5)
    assert medio != pytest.approx(100.5)


def test_despues_del_ultimo_inpc_se_extiende_la_ultima_tasa_mensual():
    anclado = fisher.anclar(INPC)
    # 30 dias despues del 31 de marzo, a la tasa de marzo (1%).
    esperado = 102.01 * 1.01 ** (30 * 12 / 365)
    assert fisher.nivel(anclado, date(2026, 4, 30)) == pytest.approx(esperado)


def test_antes_del_primer_inpc_no_hay_nivel():
    assert fisher.nivel(fisher.anclar(INPC), date(2026, 1, 15)) is None


def test_inflacion_de_un_periodo_cubierto_es_oficial():
    inf = fisher.inflacion_periodo(INPC, date(2026, 1, 31), date(2026, 3, 31))
    assert inf.acumulada == pytest.approx(0.0201)
    assert inf.anual == pytest.approx(1.0201 ** (365 / 59) - 1)
    assert inf.oficial_hasta == date(2026, 3, 31)
    assert inf.estimada is False
    assert inf.tasa_extension is None


def test_inflacion_que_pasa_del_ultimo_inpc_queda_marcada_como_estimada():
    inf = fisher.inflacion_periodo(INPC, date(2026, 1, 31), date(2026, 4, 30))
    assert inf.estimada is True
    assert inf.oficial_hasta == date(2026, 3, 31)
    assert inf.tasa_extension == pytest.approx(0.01)


def test_por_debajo_de_treinta_dias_no_se_anualiza():
    inf = fisher.inflacion_periodo(INPC, date(2026, 2, 28), date(2026, 3, 10))
    assert inf.acumulada > 0
    assert inf.anual is None


def test_un_inicio_sin_inpc_no_da_inflacion():
    assert fisher.inflacion_periodo(INPC, date(2026, 1, 15), date(2026, 3, 31)) is None


def test_con_inflacion_cero_lo_real_es_lo_nominal():
    plano = _serie([("2026-01-01", 100.0), ("2026-02-01", 100.0), ("2026-03-01", 100.0)])
    inf = fisher.inflacion_periodo(plano, date(2026, 1, 31), date(2026, 3, 31))
    assert fisher.real(0.12, inf.anual) == pytest.approx(0.12)
```

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: 9 FAIL con `AttributeError: ... has no attribute 'anclar'` o `'inflacion_periodo'`.

- [ ] **Step 3: Implementar**

Añadir a `seguimiento/fisher.py`:

```python
# Para extender el INPC mas alla del ultimo publicado: una tasa mensual se
# aplica en proporcion a los dias, como doce meses por año.
_MESES_POR_DIA = 12 / 365


@dataclass(frozen=True)
class Inflacion:
    """La inflacion de un periodo y hasta donde es oficial.

    `estimada` no es un detalle: el INPC se publica hacia el dia 9 del mes
    siguiente, asi que los ultimos dias de una cartera casi nunca lo tienen. Se
    extienden con la ultima tasa mensual y la pantalla lo dice.
    """

    acumulada: float
    anual: "float | None"
    oficial_hasta: date
    estimada: bool
    tasa_extension: "float | None" = None


def anclar(inpc: pd.Series) -> pd.Series:
    """El INPC fechado al cierre de su mes, no al dia 1 que usa Banxico."""
    serie = inpc.dropna().sort_index()
    serie.index = (
        pd.DatetimeIndex(serie.index).to_period("M").to_timestamp(how="end").normalize()
    )
    return serie


def nivel(anclado: pd.Series, dia: date) -> "float | None":
    """El nivel del indice en un dia, interpolado o extendido.

    Entre dos cierres de mes, geometrico por dias. Despues del ultimo, la ultima
    tasa mensual conocida. Antes del primero, `None`: no se extrapola hacia
    atras.
    """
    cuando = pd.Timestamp(dia)
    if anclado.empty or cuando < anclado.index[0]:
        return None
    if cuando > anclado.index[-1]:
        if len(anclado) < 2:
            return None
        tasa = anclado.iloc[-1] / anclado.iloc[-2]
        dias = (cuando - anclado.index[-1]).days
        return float(anclado.iloc[-1] * tasa ** (dias * _MESES_POR_DIA))
    posicion = int(anclado.index.searchsorted(cuando))
    if anclado.index[posicion] == cuando:
        return float(anclado.iloc[posicion])
    antes, despues = anclado.index[posicion - 1], anclado.index[posicion]
    fraccion = (cuando - antes).days / (despues - antes).days
    razon = anclado.iloc[posicion] / anclado.iloc[posicion - 1]
    return float(anclado.iloc[posicion - 1] * razon ** fraccion)


def inflacion_periodo(inpc: pd.Series, desde: date, hasta: date) -> "Inflacion | None":
    """La inflacion entre dos fechas, anualizada con la misma guarda que la TWR.

    `None` si alguna de las dos fechas no tiene nivel. Por debajo de 30 dias
    devuelve la acumulada con `anual=None`, igual que `rendimiento.anualizar`.
    """
    anclado = anclar(inpc)
    inicio, fin = nivel(anclado, desde), nivel(anclado, hasta)
    if inicio is None or fin is None:
        return None
    acumulada = fin / inicio - 1.0
    dias = (pd.Timestamp(hasta) - pd.Timestamp(desde)).days
    estimada = bool(pd.Timestamp(hasta) > anclado.index[-1])
    return Inflacion(
        acumulada=acumulada,
        anual=rendimiento.anualizar(acumulada, dias=dias),
        oficial_hasta=anclado.index[-1].date(),
        estimada=estimada,
        tasa_extension=(
            float(anclado.iloc[-1] / anclado.iloc[-2] - 1.0) if estimada else None
        ),
    )
```

- [ ] **Step 4: Ejecutarlos y ver que pasan**

Run: `uv run pytest tests/test_seguimiento_fisher.py -q`
Expected: `17 passed`

- [ ] **Step 5: Commit**

```bash
git add seguimiento/fisher.py tests/test_seguimiento_fisher.py
git commit -m "feat: la inflacion del periodo desde el INPC, oficial o estimada"
```

---

### Task 4: El token de Banxico en las credenciales

**Files:**
- Modify: `credenciales.py` (dataclass, `limpia`, `_VARIABLES`, `cargar`, `validar`, `guardar`)
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_credenciales.py`. Si no están ya importados
arriba, añadir `CredencialInvalida`, `guardar`, `cargar`, `aplicar` y
`Credenciales` desde `credenciales`.

```python
TOKEN_BANXICO = "a1" * 32  # 64 alfanumericos, la forma que documenta Banxico


def test_el_token_de_banxico_se_guarda_y_se_lee(tmp_path):
    ruta = guardar(Credenciales(banxico_token=TOKEN_BANXICO), tmp_path / "c.json")
    assert cargar(ruta).banxico_token == TOKEN_BANXICO


def test_el_token_de_banxico_solo_basta_para_guardar(tmp_path):
    # Antes, sin clave ni correo, «no hay nada que guardar».
    guardar(Credenciales(banxico_token=TOKEN_BANXICO), tmp_path / "c.json")


def test_un_token_de_banxico_con_otra_forma_se_rechaza(tmp_path):
    with pytest.raises(CredencialInvalida, match="64"):
        guardar(Credenciales(banxico_token="corto"), tmp_path / "c.json")


def test_el_token_de_banxico_va_a_su_variable_de_entorno():
    entorno = {}
    aplicar(Credenciales(banxico_token=TOKEN_BANXICO), entorno)
    assert entorno["BANXICO_TOKEN"] == TOKEN_BANXICO
```

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_credenciales.py -q`
Expected: 4 FAIL con `TypeError: ... unexpected keyword argument 'banxico_token'`.

- [ ] **Step 3: Implementar**

En `credenciales.py`:

1. Debajo de `_PREFIJO_HABITUAL`:

```python
# La forma que documenta Banxico: 64 caracteres alfanumericos. Solo la forma;
# si el token vale o no lo dice la API al primer uso.
_TOKEN_BANXICO = re.compile(r"^[A-Za-z0-9]{64}$")
```

2. Añadir una fila a `_VARIABLES`:

```python
_VARIABLES = (
    ("ANTHROPIC_API_KEY", "api_key"),
    ("EDGAR_IDENTITY", "edgar_identity"),
    ("BANXICO_TOKEN", "banxico_token"),
)
```

3. En la dataclass, cambiar el docstring a `"""Los datos que necesitan la mitad con IA y el rendimiento en pesos."""`, añadir el campo `banxico_token: str | None = None` y la línea `banxico_token=_limpiar(self.banxico_token),` dentro de `limpia()`.

4. En `cargar`, el bucle pasa a ser
`for campo in ("api_key", "edgar_identity", "banxico_token"):`. Al constructor
se le añade `banxico_token=datos.get("banxico_token"),`.

5. En `validar`, antes del «No hay nada que guardar»:

```python
    token = credenciales.banxico_token
    if token and not _TOKEN_BANXICO.match(token):
        raise CredencialInvalida(
            "El token de Banxico son 64 letras y números, sin espacios. Cópialo "
            "entero de la página donde lo generaste."
        )
```

y la condición final queda así:

```python
    if not (credenciales.api_key or credenciales.edgar_identity
            or credenciales.banxico_token):
        raise CredencialInvalida(
            "No hay nada que guardar: rellena al menos uno de los campos."
        )
```

6. En `guardar`, añadir `"banxico_token": credenciales.banxico_token,` al diccionario del `json.dumps`.

- [ ] **Step 4: Ejecutar el fichero entero y ver que pasa**

Run: `uv run pytest tests/test_credenciales.py -q`
Expected: todos pasan. Si algún test anterior buscaba el texto «los dos campos»,
se actualiza a «los campos».

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: el token de Banxico como tercera credencial"
```

---

### Task 5: Descargar de Banxico, con caché

**Files:**
- Create: `seguimiento/banxico.py`
- Modify: `.gitignore` (añadir `seguimiento/.cache/` debajo de `noticias/.cache/`)
- Test: `tests/test_seguimiento_banxico.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_seguimiento_banxico.py`:

```python
"""La descarga del SIE de Banxico, con la red simulada.

La respuesta tiene la forma que documenta el SIE. El test `red` del final es el
que comprueba que la forma real no ha cambiado y que los ids de serie son los
buenos.
"""

import io
import json
import os
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pytest

from noticias import cache
from seguimiento import banxico

TOKEN = "b2" * 32

RESPUESTA = {
    "bmx": {
        "series": [
            {
                "idSerie": "SF43718",
                "titulo": "Tipo de cambio Pesos por dólar E.U.A. FIX",
                "datos": [
                    {"fecha": "02/03/2026", "dato": "17.0500"},
                    {"fecha": "03/03/2026", "dato": "N/E"},
                    {"fecha": "04/03/2026", "dato": "1,017.2500"},
                ],
            }
        ]
    }
}


class _Red:
    """Un `urlopen` falso que apunta cada peticion."""

    def __init__(self, respuesta=RESPUESTA, error=None):
        self.respuesta, self.error, self.peticiones = respuesta, error, []

    def __call__(self, peticion, timeout):
        self.peticiones.append(peticion)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.respuesta).encode("utf-8"))


def _traer(tmp_path, red, **kw):
    return banxico.traer(
        banxico.SERIE_FIX, date(2026, 3, 1), date(2026, 3, 31), TOKEN,
        raiz=tmp_path, abrir=red, **kw,
    )


def test_parsear_lee_fechas_y_comas_y_descarta_n_e():
    serie = banxico.parsear(RESPUESTA)
    assert [d.date() for d in serie.index] == [date(2026, 3, 2), date(2026, 3, 4)]
    assert list(serie) == [17.05, 1017.25]


def test_sin_token_no_se_llama_a_la_red(tmp_path):
    red = _Red()
    resultado = banxico.traer(
        banxico.SERIE_FIX, date(2026, 3, 1), date(2026, 3, 31), None,
        raiz=tmp_path, abrir=red,
    )
    assert resultado.motivo == "sin_token"
    assert resultado.datos is None
    assert red.peticiones == []


def test_el_token_va_en_la_cabecera_y_nunca_en_la_url(tmp_path):
    red = _Red()
    _traer(tmp_path, red)
    peticion = red.peticiones[0]
    assert peticion.get_header("Bmx-token") == TOKEN
    assert TOKEN not in peticion.full_url
    assert peticion.full_url.endswith("/series/SF43718/datos/2026-03-01/2026-03-31")


def test_un_401_es_token_invalido(tmp_path):
    error = urllib.error.HTTPError("u", 401, "Unauthorized", None, None)
    assert _traer(tmp_path, _Red(error=error)).motivo == "token_invalido"


def test_sin_red_y_sin_cache_es_sin_red(tmp_path):
    resultado = _traer(tmp_path, _Red(error=urllib.error.URLError("caido")))
    assert resultado.motivo == "sin_red"
    assert resultado.datos is None


def test_una_respuesta_sin_la_forma_esperada_es_respuesta_rara(tmp_path):
    assert _traer(tmp_path, _Red(respuesta={"otra": 1})).motivo == "respuesta_rara"


def test_lo_descargado_se_guarda_y_la_segunda_vez_no_llama(tmp_path):
    red = _Red()
    primero = _traer(tmp_path, red)
    segundo = _traer(tmp_path, red)
    assert primero.motivo == segundo.motivo == "ok"
    assert len(red.peticiones) == 1
    assert list(segundo.datos) == [17.05, 1017.25]


def test_cache_caducada_y_red_caida_devuelve_la_cache_marcada_vieja(tmp_path):
    _traer(tmp_path, _Red())
    manana_pasado = datetime.now(timezone.utc) + timedelta(days=2)
    resultado = _traer(
        tmp_path, _Red(error=urllib.error.URLError("caido")), ahora=manana_pasado
    )
    assert resultado.motivo == "ok"
    assert resultado.vieja is True
    assert list(resultado.datos) == [17.05, 1017.25]


def test_el_inpc_vale_hasta_el_dia_10_del_mes_en_que_sale_el_siguiente():
    import pandas as pd
    agosto = pd.Series([140.0], index=pd.DatetimeIndex(["2026-08-01"]))
    diciembre = pd.Series([141.0], index=pd.DatetimeIndex(["2026-12-01"]))
    cuando = datetime(2026, 9, 12, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_INPC, agosto, cuando) == datetime(
        2026, 10, 10, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_INPC, diciembre, cuando) == datetime(
        2027, 2, 10, tzinfo=timezone.utc)
    assert banxico.caduca(banxico.SERIE_FIX, agosto, cuando) == cuando + timedelta(days=1)


def test_token_lee_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("BANXICO_TOKEN", f"  {TOKEN} ")
    assert banxico.token() == TOKEN
    monkeypatch.delenv("BANXICO_TOKEN")
    assert banxico.token() is None


@pytest.mark.red
def test_red_las_series_reales_tienen_la_forma_y_los_ids_buenos(tmp_path):
    clave = os.environ.get("BANXICO_TOKEN")
    if not clave:
        pytest.skip("sin BANXICO_TOKEN")
    hoy = date.today()
    fix = banxico.traer(banxico.SERIE_FIX, hoy - timedelta(days=30), hoy, clave,
                        raiz=tmp_path)
    inpc = banxico.traer(banxico.SERIE_INPC, hoy - timedelta(days=200), hoy, clave,
                         raiz=tmp_path)
    assert fix.motivo == "ok" and len(fix.datos) > 5
    # Pesos por dolar, no otra serie: un FIX fuera de este rango es un id malo.
    assert 10 < fix.datos.iloc[-1] < 40
    assert inpc.motivo == "ok" and len(inpc.datos) >= 4
    # Base 2Q jul 2018 = 100; hoy anda por encima de 130.
    assert 100 < inpc.datos.iloc[-1] < 300
```

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_seguimiento_banxico.py -q -m "not red"`
Expected: FAIL con `ImportError: cannot import name 'banxico'`.

- [ ] **Step 3: Implementar**

Crear `seguimiento/banxico.py`:

```python
"""El tipo de cambio FIX y el INPC, del SIE de Banxico.

Solo descarga y guarda. Las cuentas estan en `seguimiento/fisher.py`, que no
sabe que existe una red.

El token viaja en la cabecera `Bmx-Token` y **nunca en la URL**. La API admite
las dos formas, pero una URL acaba en logs, en trazas de error y en el
historial de cualquier proxy.

La cache no es opcional: Banxico inhabilita por un tiempo el token que pasa de
su limite de consultas, y Streamlit vuelve a ejecutar la pagina con cada clic.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from noticias import cache

SERIE_FIX = "SF43718"
SERIE_INPC = "SP1"
URL = (
    "https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
    "{serie}/datos/{desde}/{hasta}"
)
RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
_FUENTE = "banxico"
_ESPERA_SEGUNDOS = 15
# Para que `cache.leer` devuelva lo guardado tenga la edad que tenga. Si esta
# vigente o no lo decide `caduca`, que para el INPC no es un plazo fijo.
_CUALQUIER_EDAD = timedelta(days=36_500)


@dataclass(frozen=True)
class Serie:
    """Lo que vino de Banxico, o por que no vino nada.

    `motivo` es `"ok"`, `"sin_token"`, `"token_invalido"`, `"sin_red"` o
    `"respuesta_rara"`. Con `vieja=True` los datos son de una descarga anterior
    que ya caduco, usada porque la de ahora fallo.
    """

    datos: "pd.Series | None"
    motivo: str
    descargada: "datetime | None" = None
    vieja: bool = False


def token() -> "str | None":
    """El token vigente, del entorno, que es donde lo deja `credenciales.aplicar`."""
    valor = (os.environ.get("BANXICO_TOKEN") or "").strip()
    return valor or None


def parsear(crudo: dict) -> pd.Series:
    """La serie de una respuesta del SIE, por fecha.

    Las fechas vienen como `dd/mm/aaaa` y los valores como texto con comas de
    miles. `"N/E"` es «sin dato» y se descarta: convertirlo en cero seria
    afirmar un tipo de cambio de cero pesos.
    """
    puntos = crudo["bmx"]["series"][0].get("datos") or []
    fechas, valores = [], []
    for punto in puntos:
        try:
            numero = float(str(punto["dato"]).replace(",", "").strip())
        except ValueError:
            continue
        fechas.append(datetime.strptime(punto["fecha"], "%d/%m/%Y"))
        valores.append(numero)
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float).sort_index()


def caduca(serie: str, datos: pd.Series, cuando: datetime) -> datetime:
    """Hasta cuando vale lo descargado.

    El FIX cambia cada dia habil, asi que vale un dia. El INPC mensual sale
    hacia el dia 9 del mes siguiente, asi que el de agosto no tiene sucesor
    hasta el 9 de octubre: vale hasta el 10.
    """
    if serie == SERIE_INPC and len(datos):
        ultimo = datos.index[-1]
        # Meses contados desde el año 0, dos por delante del ultimo dato: agosto
        # da octubre, diciembre da febrero del año siguiente.
        meses = ultimo.year * 12 + (ultimo.month - 1) + 2
        return datetime(meses // 12, meses % 12 + 1, 10, tzinfo=timezone.utc)
    return cuando + timedelta(days=1)


def _a_plano(serie: pd.Series) -> dict:
    return {d.date().isoformat(): float(v) for d, v in serie.items()}


def _de_plano(plano) -> pd.Series:
    if not isinstance(plano, dict):
        raise TypeError("cache de Banxico sin forma de serie")
    serie = pd.Series(
        {pd.Timestamp(k): float(v) for k, v in plano.items()}, dtype=float
    )
    return serie.sort_index()


def _pedir(serie, desde: date, hasta: date, clave: str, abrir) -> dict:
    url = URL.format(serie=serie, desde=desde.isoformat(), hasta=hasta.isoformat())
    peticion = urllib.request.Request(
        url, headers={"Bmx-Token": clave, "Accept": "application/json"}
    )
    with abrir(peticion, timeout=_ESPERA_SEGUNDOS) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def traer(
    serie: str,
    desde: date,
    hasta: date,
    clave: "str | None",
    *,
    raiz: Path = RAIZ_CACHE,
    abrir=None,
    ahora: "datetime | None" = None,
) -> Serie:
    """Una serie de Banxico, de la cache si vale y de la red si no.

    La clave de la cache es la serie y `desde`. `hasta` es siempre hoy, y
    meterlo en la clave haria que ninguna cache sobreviviera a un cambio de dia.
    """
    if not clave:
        return Serie(None, "sin_token")
    abrir = abrir or urllib.request.urlopen
    ahora = ahora or datetime.now(timezone.utc)
    llave = f"{serie}_{desde.isoformat()}"

    guardado = cache.leer(raiz, _FUENTE, llave, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None:
        try:
            previo = _de_plano(guardado.datos)
        except (TypeError, ValueError):
            previo = None
    if previo is not None and ahora < caduca(serie, previo, guardado.cuando):
        return Serie(previo, "ok", guardado.cuando)

    try:
        datos = parsear(_pedir(serie, desde, hasta, clave, abrir))
    except urllib.error.HTTPError as error:
        # Antes que URLError, que es su clase madre.
        if error.code in (401, 403):
            motivo = "token_invalido"
        elif error.code == 429 or error.code >= 500:
            motivo = "sin_red"
        else:
            motivo = "respuesta_rara"
    except (urllib.error.URLError, TimeoutError, OSError):
        motivo = "sin_red"
    except (ValueError, KeyError, IndexError, TypeError):
        motivo = "respuesta_rara"
    else:
        cache.guardar(raiz, _FUENTE, llave, _a_plano(datos))
        return Serie(datos, "ok", ahora)

    if previo is not None:
        return Serie(previo, "ok", guardado.cuando, vieja=True)
    return Serie(None, motivo)
```

Añadir a `.gitignore`, debajo de `noticias/.cache/`:

```
seguimiento/.cache/
```

- [ ] **Step 4: Ejecutarlos y ver que pasan**

Run: `uv run pytest tests/test_seguimiento_banxico.py -q -m "not red"`
Expected: `10 passed, 1 deselected`

- [ ] **Step 5: Commit**

```bash
git add seguimiento/banxico.py tests/test_seguimiento_banxico.py .gitignore
git commit -m "feat: FIX e INPC del SIE de Banxico, con cache y fallos con nombre"
```

---

### Task 6: `CabeceraPesos` en el panel

**Files:**
- Modify: `seguimiento/panel.py` (import de `fisher`, dataclass nueva y función nueva después de `cabecera`)
- Test: `tests/test_panel_pesos.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_panel_pesos.py`:

```python
"""Las cifras en pesos, que pueden faltar sin que falte nada de lo demas."""

from datetime import date

import pandas as pd
import pytest

from seguimiento import panel, posiciones, rendimiento


def _serie(fechas, valores):
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


FECHAS = ["2026-01-30", "2026-03-02", "2026-03-31"]


def _marcha(valor, flujos):
    return posiciones.Marcha(
        acciones=pd.DataFrame(), efectivo=pd.Series(dtype=float),
        valor=_serie(FECHAS, valor), flujos=_serie(FECHAS, flujos),
        dividendos=pd.DataFrame(),
    )


MARCHA = _marcha([1000.0, 1050.0, 1100.0], [1000.0, 0.0, 0.0])
INPC = _serie(["2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01"],
              [100.0, 100.5, 101.0, 101.5])


def test_con_fix_constante_la_twr_en_pesos_es_la_de_dolares():
    fix = _serie(FECHAS, [17.0, 17.0, 17.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.motivo == "ok"
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial == cp.fix_final == 17.0
    assert cp.movimiento_tc == pytest.approx(0.0)


def test_las_reales_son_fisher_sobre_las_nominales_en_pesos():
    fix = _serie(FECHAS, [17.0, 17.5, 18.0])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=fix, inpc=INPC)
    assert cp.inflacion is not None
    assert cp.twr_real == pytest.approx(
        (1 + cp.twr_anual) / (1 + cp.inflacion.anual) - 1)
    assert cp.tir_real == pytest.approx((1 + cp.tir) / (1 + cp.inflacion.anual) - 1)
    assert cp.movimiento_tc == pytest.approx(18.0 / 17.0 - 1)


def test_un_libro_en_pesos_no_se_convierte():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="MXN",
                              fix=None, inpc=INPC)
    usd = rendimiento.anualizar(rendimiento.twr(MARCHA.valor, MARCHA.flujos), dias=60)
    assert cp.twr_anual == pytest.approx(usd)
    assert cp.fix_inicial is None


def test_sin_valorar_todo_es_none():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=True, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=INPC)
    assert cp.motivo == "sin_valorar"
    assert cp.twr_anual is cp.tir is cp.twr_real is cp.tir_real is None


def test_sin_fix_dice_por_que():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=None, inpc=None, motivo_datos="sin_token")
    assert cp.motivo == "sin_token"
    assert cp.twr_anual is None


def test_sin_inpc_las_nominales_salen_y_las_reales_no():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=None,
                              motivo_datos="sin_red")
    assert cp.twr_anual is not None
    assert cp.twr_real is None
    assert cp.motivo == "sin_red"


def test_otra_moneda_no_se_soporta():
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="EUR",
                              fix=None, inpc=None)
    assert cp.motivo == "moneda_no_soportada"


def test_un_inpc_que_no_llega_al_inicio_lo_nombra():
    tarde = _serie(["2026-03-01"], [101.5])
    cp = panel.cabecera_pesos(MARCHA, sin_valorar=False, moneda="USD",
                              fix=_serie(FECHAS, [17.0] * 3), inpc=tarde)
    assert cp.inflacion is None
    assert cp.motivo == "inpc_incompleto"
```

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_panel_pesos.py -q`
Expected: 8 FAIL con `AttributeError: module 'seguimiento.panel' has no attribute 'cabecera_pesos'`.

- [ ] **Step 3: Implementar**

En `seguimiento/panel.py`, cambiar el import a
`from seguimiento import fisher, libro as mod, posiciones, rendimiento`. Después
de la función `cabecera`, añadir:

```python
@dataclass(frozen=True)
class CabeceraPesos:
    """Las cifras en pesos. Separadas de `Cabecera` a proposito.

    Dependen de Banxico y pueden faltar --un token caducado, la red caida-- sin
    que falte nada de lo que no depende de el. Metidas en `Cabecera`, un fallo
    de Banxico tocaria cifras que no tienen nada que ver.

    `motivo` es `"ok"`, uno de los fallos de `banxico.Serie`, `"sin_valorar"`,
    `"moneda_no_soportada"`, `"fix_incompleto"` o `"inpc_incompleto"`. Con un
    motivo que no es `"ok"` puede haber cifras nominales igualmente: sin INPC,
    la TWR en pesos se mide y solo faltan las reales.
    """

    motivo: str
    twr_periodo: "float | None" = None
    twr_anual: "float | None" = None
    tir: "float | None" = None
    motivo_tir: str = "ok"
    inflacion: "fisher.Inflacion | None" = None
    twr_real: "float | None" = None
    tir_real: "float | None" = None
    fix_inicial: "float | None" = None
    fix_final: "float | None" = None

    @property
    def movimiento_tc(self) -> "float | None":
        if self.fix_inicial is None or self.fix_final is None:
            return None
        return self.fix_final / self.fix_inicial - 1.0


def cabecera_pesos(
    marcha,
    sin_valorar: bool,
    moneda: str,
    fix,
    inpc,
    motivo_datos: str = "ok",
) -> CabeceraPesos:
    """TWR y TIR en pesos, la inflacion del periodo y las dos reales.

    Mismo corte temporal que `cabecera`: la serie valorada y `marcha.flujos`,
    nunca los asientos. `motivo_datos` es el primer fallo de las dos descargas
    de Banxico, o `"ok"`.
    """
    if moneda not in ("USD", "MXN"):
        return CabeceraPesos(motivo="moneda_no_soportada")
    if sin_valorar or len(marcha.valor) < 2:
        return CabeceraPesos(motivo="sin_valorar")

    fix_inicial = fix_final = None
    if moneda == "MXN":
        valor, flujos = marcha.valor, marcha.flujos
    else:
        convertido = fisher.en_pesos(marcha.valor, marcha.flujos, fix)
        if convertido is None:
            # Sin serie, el motivo es el de la descarga. Con serie pero sin dato
            # para el primer dia, es que el FIX no llega tan atras.
            sin_serie = fix is None or fix.empty
            return CabeceraPesos(
                motivo=motivo_datos if sin_serie and motivo_datos != "ok"
                else "fix_incompleto"
            )
        valor, flujos = convertido
        fix_inicial = fisher.fix_en(fix, marcha.valor.index[0])
        fix_final = fisher.fix_en(fix, marcha.valor.index[-1])

    primero, ultimo = valor.index[0], valor.index[-1]
    dias = (ultimo - primero).days
    twr_periodo = rendimiento.twr(valor, flujos)
    twr_anual = rendimiento.anualizar(twr_periodo, dias=dias)

    # La misma ecuacion que en `cabecera`, con los importes en pesos: el dinero
    # que entra es una salida del bolsillo, y el valor final la cierra.
    flujos_tir = [(d.date(), -float(v)) for d, v in flujos.items() if v]
    if flujos_tir:
        flujos_tir.append((ultimo.date(), float(valor.iloc[-1])))
    tir, motivo_tir = rendimiento.tir_detallada(flujos_tir)

    inflacion = None
    motivo = motivo_datos
    if inpc is not None and not inpc.empty:
        inflacion = fisher.inflacion_periodo(inpc, primero.date(), ultimo.date())
        if inflacion is None and motivo == "ok":
            motivo = "inpc_incompleto"
    anual = inflacion.anual if inflacion else None

    return CabeceraPesos(
        motivo=motivo,
        twr_periodo=twr_periodo,
        twr_anual=twr_anual,
        tir=tir,
        motivo_tir=motivo_tir,
        inflacion=inflacion,
        twr_real=fisher.real(twr_anual, anual),
        tir_real=fisher.real(tir, anual),
        fix_inicial=fix_inicial,
        fix_final=fix_final,
    )
```

En `seguimiento/fisher.py`, debajo de `en_pesos`, añadir la función que
`cabecera_pesos` usa para las dos cifras de FIX:

```python
def fix_en(fix: pd.Series, dia) -> "float | None":
    """El FIX vigente un dia: el de ese dia o el ultimo publicado antes."""
    anteriores = fix.sort_index().loc[: pd.Timestamp(dia)]
    return float(anteriores.iloc[-1]) if len(anteriores) else None
```

Y su test en `tests/test_seguimiento_fisher.py`:

```python
def test_fix_en_un_dia_sin_dato_es_el_ultimo_publicado():
    fix = _serie([("2026-03-13", 18.0), ("2026-03-17", 18.2)])
    assert fisher.fix_en(fix, date(2026, 3, 16)) == 18.0
    assert fisher.fix_en(fix, date(2026, 3, 1)) is None
```

- [ ] **Step 4: Ejecutarlos y ver que pasan**

Run: `uv run pytest tests/test_panel_pesos.py tests/test_seguimiento_fisher.py tests/test_panel_cabecera.py -q`
Expected: todo pasa, y `test_panel_cabecera.py` sigue igual porque `cabecera`
no se ha tocado.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/panel.py seguimiento/fisher.py tests/test_panel_pesos.py tests/test_seguimiento_fisher.py
git commit -m "feat: CabeceraPesos, las cifras en pesos separadas de las de siempre"
```

---

### Task 7: Los textos de la fila en pesos

**Files:**
- Modify: `seguimiento/panel.py`
- Test: `tests/test_panel_pesos.py`

Los textos de ayuda se escriben en `panel` y no en la pantalla por la misma
razón que `aviso_de_brecha`: así un test puede leerlos.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_panel_pesos.py`:

```python
from seguimiento import fisher


def test_la_nota_del_tipo_de_cambio_dice_de_donde_a_donde():
    cp = panel.CabeceraPesos(motivo="ok", twr_anual=0.1, fix_inicial=17.05,
                             fix_final=18.40)
    notas = panel.notas_pesos(cp)
    assert "17.05 → 18.40" in notas["tc"]
    assert "subió" in notas["tc"]


def test_la_nota_de_inflacion_dice_desde_cuando_es_estimada():
    inf = fisher.Inflacion(acumulada=0.03, anual=0.04, oficial_hasta=date(2026, 8, 31),
                           estimada=True, tasa_extension=0.004)
    notas = panel.notas_pesos(panel.CabeceraPesos(motivo="ok", inflacion=inf))
    assert "ago-2026" in notas["inflacion"]
    assert "estimad" in notas["inflacion"]
    assert "0.40%" in notas["inflacion"]


def test_sin_token_la_nota_dice_como_conseguirlo():
    notas = panel.notas_pesos(panel.CabeceraPesos(motivo="sin_token"))
    assert "Perfil" in notas["motivo"]
    assert "banxico.org.mx" in notas["motivo"]


def test_con_todo_bien_no_hay_nota_de_motivo():
    assert panel.notas_pesos(panel.CabeceraPesos(motivo="ok"))["motivo"] is None
```

- [ ] **Step 2: Ejecutarlos y ver que fallan**

Run: `uv run pytest tests/test_panel_pesos.py -q`
Expected: 4 FAIL con `AttributeError: ... 'notas_pesos'`.

- [ ] **Step 3: Implementar**

Añadir a `seguimiento/panel.py`, después de `cabecera_pesos`:

```python
_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")

_MOTIVOS_PESOS = {
    "sin_token": (
        "Sin token de Banxico. Se saca gratis en "
        "https://www.banxico.org.mx/SieAPIRest/service/v1/token (resuelves la "
        "imagen y pulsas «Generar token») y se pega en Perfil."
    ),
    "token_invalido": "Banxico rechazó el token. Revísalo en Perfil.",
    "sin_red": "No se pudo hablar con Banxico. Se reintentará en la próxima carga.",
    "respuesta_rara": "Banxico respondió algo que no tiene forma de serie.",
    "sin_valorar": None,
    "moneda_no_soportada": "Solo se convierten libros en USD o en MXN.",
    "fix_incompleto": "No hay tipo de cambio FIX para el primer día de la cartera.",
    "inpc_incompleto": "No hay INPC para el inicio del periodo.",
}


def notas_pesos(cp: CabeceraPesos) -> "dict[str, str | None]":
    """Las ayudas de la fila en pesos: tipo de cambio, inflacion y motivo."""
    tc = None
    if cp.movimiento_tc is not None:
        verbo = "subió" if cp.movimiento_tc >= 0 else "bajó"
        tc = (
            f"FIX {cp.fix_inicial:.2f} → {cp.fix_final:.2f}: el dólar {verbo} "
            f"{abs(cp.movimiento_tc):.2%} en el periodo. Ya está dentro de la cifra."
        )

    inflacion = None
    if cp.inflacion is not None:
        oficial = cp.inflacion.oficial_hasta
        mes = f"{_MESES[oficial.month - 1]}-{oficial.year}"
        inflacion = f"INPC oficial hasta {mes}."
        if cp.inflacion.estimada:
            inflacion += (
                " Los días posteriores están estimados con la última tasa "
                f"mensual ({cp.inflacion.tasa_extension:.2%})."
            )

    motivo = None if cp.motivo == "ok" else _MOTIVOS_PESOS.get(cp.motivo, cp.motivo)
    return {"tc": tc, "inflacion": inflacion, "motivo": motivo}
```

- [ ] **Step 4: Ejecutarlos y ver que pasan**

Run: `uv run pytest tests/test_panel_pesos.py -q`
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add seguimiento/panel.py tests/test_panel_pesos.py
git commit -m "feat: las notas de la fila en pesos, legibles desde un test"
```

---

### Task 8: El token en la pantalla de Perfil

**Files:**
- Modify: `vistas/perfil.py:65-160`

Esta pantalla es un guion de Streamlit: no hay test unitario y se verifica en la
app (Task 10).

- [ ] **Step 1: Rama de solo lectura**

Justo después del `st.text_input("Correo para EDGAR", ..., disabled=True)` de la
rama `if guardadas.api_key and not editando:`, añadir:

```python
        st.text_input(
            "Token de Banxico",
            value=enmascarar(guardadas.banxico_token), disabled=True,
        )
```

- [ ] **Step 2: Rama de edición**

Después del `nuevo_correo = st.text_input(...)`, añadir:

```python
        nuevo_token = st.text_input(
            "Token de Banxico",
            type="password",
            key="entrada_token_banxico",
            help="Para ver el rendimiento en pesos y descontando la inflación. No "
                 "pide correo: en https://www.banxico.org.mx/SieAPIRest/service/v1/token "
                 "resuelves la imagen, pulsas «Generar token» y pegas aquí los 64 "
                 "caracteres. Se genera una vez y sirve siempre.",
        )
```

y en el constructor de `nuevas`:

```python
            nuevas = Credenciales(
                api_key=nueva_clave or guardadas.api_key,
                edgar_identity=nuevo_correo,
                banxico_token=nuevo_token or guardadas.banxico_token,
            )
```

- [ ] **Step 3: Explicar para qué sirve**

En el `st.markdown("**Para qué sirve cada una**...")`, añadir al final:

```python
        "\n- **Token de Banxico** — opcional. Sólo para la fila «En pesos» de "
        "Seguimiento: el tipo de cambio FIX y el INPC. Sin él esa fila sale con «—»."
```

- [ ] **Step 4: Comprobar que compila y que la suite sigue igual**

Run: `uv run python -c "import ast,sys; ast.parse(open('vistas/perfil.py',encoding='utf-8').read())" && uv run pytest tests/test_vistas_perfil.py -q`
Expected: sin salida del `ast` y los tests de perfil pasan.

- [ ] **Step 5: Commit**

```bash
git add vistas/perfil.py
git commit -m "feat: el token de Banxico en Perfil, con el enlace para sacarlo"
```

---

### Task 9: La fila «En pesos (MXN)» y el Excel

**Files:**
- Modify: `vistas/seguimiento.py` (imports, una función cacheada junto a `_historia` en la línea ~128, la fila en la pestaña «Por activo» después de `d2.metric("Dividendos", ...)` en la línea ~764, y el diccionario del Excel en la línea ~811)

- [ ] **Step 1: Imports y descarga cacheada**

Cambiar el import a
`from seguimiento import banxico, comparacion, libro as mod, panel, posiciones, precios`
y añadir `from datetime import date, timedelta` en lugar de `from datetime import date`.
Debajo de `_historia`:

```python
@st.cache_data(ttl=3600, show_spinner="Descargando datos de Banxico...")
def _banxico(desde: str, hasta: str, clave: "str | None"):
    """FIX e INPC para el periodo. Encima de la cache en disco de `banxico`.

    El INPC se pide desde dos meses antes: el dato mensual se ancla al cierre
    del mes, asi que un periodo que empieza el dia 5 necesita el del mes
    anterior. El FIX, desde diez dias antes, por si el primer dia es festivo.
    """
    inicio = date.fromisoformat(desde)
    fin = date.fromisoformat(hasta)
    fix = banxico.traer(banxico.SERIE_FIX, inicio - timedelta(days=10), fin, clave)
    inpc_desde = (inicio - timedelta(days=62)).replace(day=1)
    inpc = banxico.traer(banxico.SERIE_INPC, inpc_desde, fin, clave)
    return fix, inpc
```

- [ ] **Step 2: Calcular la cabecera en pesos**

Justo después de `cab = panel.cabecera(marcha, vivos, sin_valorar)`:

```python
# Las cifras en pesos. Aparte, porque dependen de Banxico y pueden faltar sin
# que falte nada de arriba. En un libro MXN el FIX sobra; se descarta en vez de
# abrir un segundo camino, porque es una sola llamada cacheada un dia.
_fix = _inpc = None
if len(marcha.valor) and not sin_valorar and actual.moneda in ("USD", "MXN"):
    _fix, _inpc = _banxico(
        marcha.valor.index[0].date().isoformat(), date.today().isoformat(),
        banxico.token(),
    )
    if actual.moneda == "MXN":
        _fix = None
_motivo_datos = next(
    (s.motivo for s in (_fix, _inpc) if s is not None and s.motivo != "ok"), "ok"
)
cab_mxn = panel.cabecera_pesos(
    marcha, sin_valorar, actual.moneda,
    fix=_fix.datos if _fix else None,
    inpc=_inpc.datos if _inpc else None,
    motivo_datos=_motivo_datos,
)
```

- [ ] **Step 3: Pintar la fila**

En la pestaña «Por activo», después de `d2.metric("Dividendos", ...)`:

```python
    # En pesos, y descontando la inflacion. Cinco cifras de porcentaje caben en
    # una fila: el recorte que midio K era con importes de nueve caracteres.
    st.markdown("**En pesos (MXN)**")
    _notas = panel.notas_pesos(cab_mxn)
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("TWR MXN", cartera.formato_porcentaje(cab_mxn.twr_anual),
              help=_notas["tc"])
    p2.metric("TIR MXN", cartera.formato_porcentaje(cab_mxn.tir), help=_notas["tc"])
    p3.metric("Inflación anual",
              cartera.formato_porcentaje(
                  cab_mxn.inflacion.anual if cab_mxn.inflacion else None),
              help=_notas["inflacion"])
    p4.metric("TWR real", cartera.formato_porcentaje(cab_mxn.twr_real),
              help="Fisher: (1 + TWR MXN) / (1 + inflación) − 1. Lo que creció tu "
                   "poder de compra en pesos.")
    p5.metric("TIR real", cartera.formato_porcentaje(cab_mxn.tir_real),
              help="Fisher sobre la TIR en pesos. Supone la inflación del periodo "
                   "constante.")
    if _notas["motivo"]:
        st.caption(_notas["motivo"])
    _hora = next((s.descargada for s in (_fix, _inpc) if s and s.descargada), None)
    if _hora:
        _vieja = any(s and s.vieja for s in (_fix, _inpc))
        st.caption(
            f"Datos: Banxico SIE · descargados el {_hora:%Y-%m-%d %H:%M} UTC"
            + (" · **no se pudieron renovar**" if _vieja else "")
        )
```

- [ ] **Step 4: Columnas del Excel**

En el diccionario de `to_excel`, después de `"TIR": cab.tir,`:

```python
                "TWR MXN": cab_mxn.twr_anual,
                "TIR MXN": cab_mxn.tir,
                "Inflación anual (INPC)": (
                    cab_mxn.inflacion.anual if cab_mxn.inflacion else None),
                "TWR real": cab_mxn.twr_real,
                "TIR real": cab_mxn.tir_real,
                "INPC estimado desde": (
                    cab_mxn.inflacion.oficial_hasta.isoformat()
                    if cab_mxn.inflacion and cab_mxn.inflacion.estimada else None),
```

- [ ] **Step 5: Suite completa**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: los 1.766 anteriores más los nuevos pasan, sin fallos.

- [ ] **Step 6: Commit**

```bash
git add vistas/seguimiento.py
git commit -m "feat: la fila En pesos (MXN) en Seguimiento, y sus columnas en el Excel"
```

---

### Task 10: Verificación en la app y contra Banxico

- [ ] **Step 1: Test contra la API real**

Hace falta el token del usuario. Pedírselo al usuario (**no** generarlo, porque
la página tiene un CAPTCHA). Con el token guardado en Perfil o exportado:

Run: `BANXICO_TOKEN=... uv run pytest tests/test_seguimiento_banxico.py -q -m red`
Expected: `1 passed`. Si falla por rango de valores, el id de serie no es el
bueno: consultar el catálogo del SIE y corregir `SERIE_FIX` o `SERIE_INPC`.

- [ ] **Step 2: La app**

Arrancar con `preview_start` (`.claude/launch.json`). Luego:

1. Perfil: guardar el token. Se ve enmascarado y el Excel no cambia.
2. Seguimiento, pestaña «Por activo»: aparecen las cinco cifras. Las ayudas
   dicen FIX inicial → final y «INPC oficial hasta …».
3. Borrar el token: la fila sale con «—» y el texto de cómo conseguirlo, y el
   resto del panel queda idéntico.
4. Descargar el Excel: tiene las seis columnas nuevas.

Hacer una captura de la fila como prueba.

- [ ] **Step 3: Actualizar `CONTEXTO.md`**

Actualizar el recuento de tests de la línea 4 y añadir un párrafo corto: qué
hace el sub-proyecto, dónde viven `banxico.py` y `fisher.py`, y que el token no
se puede automatizar porque hay un CAPTCHA.

```bash
git add CONTEXTO.md
git commit -m "docs: CONTEXTO con el rendimiento real en pesos"
```
