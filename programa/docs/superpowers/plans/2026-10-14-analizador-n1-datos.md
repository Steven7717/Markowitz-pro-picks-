# Analizador individual, parte 1: los datos de cualquier ticker — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el programa sepa analizar cualquier ticker —una empresa de la SEC, una extranjera, una de la BMV o un ETF— con la misma ficha frente al sector y el mismo valor intrínseco que los candidatos, sin pantalla todavía.

**Architecture:** Un paquete nuevo, `analizador/`, sin Streamlit, que resuelve qué es cada ticker (`resolver`), traduce los estados de yfinance a las columnas del motor de fundamentales (`lineas_yf`), decide la moneda y la tasa libre (`divisas`), lo compara con el panel del S&P 500 que el ranking deja en disco (`referencia`) y junta todo en un `Analisis` por ticker (`analisis`). yfinance sigue entrando sólo por `valoracion/mercado.py`, que gana tres fuentes con su caché: la identidad del ticker, sus estados y el tipo de cambio. `valoracion/supuestos.py` gana `aplicar` (los deslizadores de N2) y `valoracion/dcf.py` la tabla de sensibilidad.

**Tech Stack:** Python 3.12, pandas, yfinance 1.6, edgartools 5.52, pyarrow (ya es dependencia), pytest. Sin dependencias nuevas.

---

## Por qué N se parte en tres planes

El spec de N (`docs/superpowers/specs/2026-10-12-analizador-individual-design.md`) abarca subsistemas que se prueban por separado: los datos de cualquier ticker, la pantalla con el gráfico y el gate, y la IA. Este plan es **N1, los datos**: produce un paquete con tests y una función `analisis.analizar(ticker)` que se puede llamar desde un script. **N2** (la pantalla Analizador, que absorbe Noticias y calendario, con el gráfico, los deslizadores, «Analizar a fondo» y «Añadir a la revisión») y **N3** (los cuatro bloques de IA y el archivo `analisis/`) se escriben después, sobre el código real de N1.

## Lo que el sondeo del 2026-10-14 cambió del spec

Antes de escribir este plan se miró yfinance, EDGAR y Banxico en vivo (MU, WALMEX.MX, TSM, JPM, SPY, BRK-B, RY). Lo que salió, y cómo lo recoge el plan; la Task 18 lo lleva al spec como enmienda fechada:

1. **TSM: yfinance ya da el recuento en base ADR.** `Diluted Average Shares` = 5.186 millones, igual que `sharesOutstanding`, y el BPA en TWD por ADR. La trampa de la ADR del spec (un recuento cinco veces mayor en los estados) no aparece con yfinance; sí aparecería con el XBRL del 20-F, que N no usa. El cociente se sigue calculando y avisando (`divisas.cociente_adr`), como guarda.
2. **yfinance da 5 o 6 trimestres, a veces con un hueco** (a WALMEX le falta el 3T 2025 en resultados y flujos; su balance trae la columna vacía). `fundamentals.kpis` compara con `shift(4)` y suma con `rolling(4)`, que cuentan filas: con un hueco, el «mismo trimestre del año pasado» caería en otro. `lineas_yf.rejilla_trimestral` da una fila a cada trimestre natural y `lineas_yf.rellenar_desde_anual` recupera el flujo del trimestre que falta como el año menos los otros tres, que es la aritmética de `fundamentals.panel._cuartos_derivados`.
3. **BRK-B no trae `Operating Income`, sólo `EBIT`; JPM no trae ni coste de ventas ni beneficio operativo.** La cadena `Operating Income` → `EBIT` del spec se resuelve fila a fila, como `fundamentals.concepts.resolve_lines`.
4. **La valoración de yfinance usa ejercicios fiscales completos**, no un TTM trimestral: con cinco trimestres sólo cabe un TTM, y mezclarlo con los ejercicios anuales rompería que `ejercicios[i]` sea «hace i años», que es lo que `supuestos._cagr` da por hecho. `estados_hasta` lo dice en pantalla.
5. **La clase sale de los formularios que la empresa presenta en EDGAR**, no del atributo `is_foreign` de edgartools: RY presenta 40-F y edgartools la marca `is_foreign = False`. 10-K → `sec`; 20-F o 40-F → `extranjera_sec`; ninguno, o no está en EDGAR → `sin_sec`. Un ticker con sufijo de bolsa (`.MX`) no se pregunta a EDGAR.
6. **El Bono M a 10 años es la serie `SF44071`** del SIE: «Valores Gubernamentales. Resultados de la subasta semanal. Tasa de rendimiento. Bono tasa fija 10 años», en porcentaje. Es de subasta y no de mercado secundario, así que el último dato puede tener semanas (el 2026-10-14, el del 24/09/2026); su fecha va en la procedencia. Lo fija un test `red` contra el título de sus metadatos.
7. **Los pares de divisa de Yahoo existen en los dos sentidos** (`TWDUSD=X` y `USDTWD=X`, `MXNUSD=X`, `CADUSD=X`); se usa `<ORIGEN><DESTINO>=X`. `^MXX` es el IPC.
8. **La identidad, los estados y el tipo de cambio se guardan en la caché de `valoracion/mercado.py`** (`valoracion/.cache/`), no en una `analizador/.cache/` aparte: `mercado` ya es la única puerta a yfinance, con su caché, su respaldo y sus motivos con nombre, y una segunda puerta sería la que se queda atrás. `analizador/.cache/` sólo guarda los formularios de EDGAR.
9. **El puesto hipotético es el global** —el orden por nota compuesta entre las que pasan las guardas, sin el tope por sector—, que es el único que existe para un ticker que no compite por las quince plazas. Para el primero de los candidatos coincide con su puesto.
10. **Las filas de un ticker posteriores al último trimestre del panel no entran en la comparación**: en ese trimestre no tiene pares, y su z saldría vacía y le quitaría un trimestre de la ventana.
11. **Si el precio y los estados van en monedas distintas** (TSM: dólares y TWD), los múltiplos del panel trimestral se calculan con el precio de cada fecha convertido al tipo de cambio de esa misma fecha, que se baja con el mismo cargador de precios.

## Mapa de ficheros

| Fichero | Responsabilidad |
|---|---|
| `analizador/__init__.py` | Vacío |
| `analizador/resolver.py` | La forma del ticker (`normalizar`, `separar`), su identidad y su clase (`resolver`) |
| `analizador/sectores.py` | El sector GICS: la tabla del S&P 500 o la de Yahoo traducida |
| `analizador/lineas_yf.py` | Los estados de yfinance en las columnas de `fundamentals.concepts.LINEAS`, los KPIs trimestrales y los `Fundamentos` anuales |
| `analizador/divisas.py` | La moneda de la valoración, la conversión, el Bono M y el cociente de la ADR |
| `analizador/referencia.py` | El panel de referencia en disco y la ficha frente al sector |
| `analizador/kpis.py` | Las filas de KPIs de un ticker que no está en el panel |
| `analizador/valorar.py` | Las entradas de la valoración (una sola vez de la red) y la valoración pura con o sin cambios |
| `analizador/analisis.py` | Un ticker de punta a punta, y varios |
| `valoracion/mercado.py` | Gana `identidad`, `estados`, `tipo_de_cambio` |
| `valoracion/supuestos.py` | `deducir` acepta la procedencia de la tasa libre; gana `aplicar` |
| `valoracion/dcf.py` | Gana `sensibilidad` |
| `valoracion/motor.py` | Gana `datos_dcf`, que `_lectura_flujos` reutiliza |
| `medidores_valoracion.py` | Textos de las fuentes nuevas (Bono M, usuario, recalculado) |
| `fundamentals/run.py` | `anadir_zscores` pública; `_precios_por_periodo` acepta `min_obs` |
| `ranking/run.py` | `Resultado.panel` y `guardar` escribe `salidas/panel.parquet` |
| `scripts/sondear_analizador.py` | El recorrido con datos reales (Task 17) |

## Convenciones del repo, para cada tarea

- Todos los comandos se ejecutan desde `programa/`.
- Comentarios y docstrings en castellano, con acentos, que explican el **porqué**.
- Lógica sin Streamlit; las vistas sólo pintan (N1 no toca vistas).
- Los tests de red llevan `@pytest.mark.red` y la suite normal es `uv run pytest tests/ -q -m "not red"`.
- Nada de texto de pantalla en ficheros de datos: se guardan claves.
- Cada commit termina con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Rama: `feat/analizador-individual`. Nunca commit en `master`, nunca push.

---

### Task 1: La forma del ticker

> **Ejecutada y superada** (43f9f20, c8f8747). La revisión añadió el `&` (`PE&OLES.MX`, `M&M.NS`), `_limpiar` (NFKC y caracteres invisibles de lo que se pega de una web), el choque documentado de `MKC.V` con el sufijo de TSX Venture y tests de casos reales. Manda el código vivo.

**Files:**
- Create: `analizador/__init__.py`
- Create: `analizador/resolver.py`
- Test: `tests/test_analizador_resolver.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_resolver.py`:

```python
"""La forma del ticker: el punto de una clase de acción frente al de una bolsa."""

import pytest

from analizador.resolver import MAX_TICKERS, normalizar, separar, tiene_sufijo


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("BRK.B", "BRK-B"),
        ("BF.B", "BF-B"),
        ("WALMEX.MX", "WALMEX.MX"),
        ("GFNORTEO.MX", "GFNORTEO.MX"),
        ("RY.TO", "RY.TO"),
        ("brk-b", "BRK-B"),
        ("walmex.mx", "WALMEX.MX"),
        ("  mu  ", "MU"),
        ("BRK.B.MX", "BRK-B.MX"),
        # Índices, divisas y cripto pasan la forma: es Yahoo quien dirá que no
        # son acciones, y la pantalla lo dirá con su motivo.
        ("^GSPC", "^GSPC"),
        ("EURUSD=X", "EURUSD=X"),
        ("BTC-USD", "BTC-USD"),
    ],
)
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize(
    "entrada", ["", "   ", "BRK B", "MU;", "A..B", "WALMEX.", "-A", "A" * 21, None, 3]
)
def test_lo_que_no_tiene_forma_de_ticker_se_rechaza(entrada):
    assert normalizar(entrada) is None


def test_las_dos_funciones_de_siempre_rompen_la_bmv_y_por_eso_no_se_usan():
    # Documenta la trampa del spec: las dos funciones existentes sirven al
    # universo del S&P 500 y al acta, y ahí están bien; aquí romperían WALMEX.
    from aprobacion.acta import _FORMA_TICKER
    from research.universe import normalise_ticker

    assert normalise_ticker("WALMEX.MX") == "WALMEX-MX"
    assert _FORMA_TICKER.match("WALMEX.MX") is None


def test_separar_por_comas_y_espacios_sin_repetir():
    assert separar("mu, TSM  walmex.mx,MU\nbrk.b") == (
        ["MU", "TSM", "WALMEX.MX", "BRK-B"],
        [],
    )


def test_separar_devuelve_los_invalidos_tal_como_se_escribieron():
    assert separar("MU, A..B MU;") == (["MU"], ["A..B", "MU;"])


@pytest.mark.parametrize("vacio", ["", "  ,  ", None])
def test_separar_nada(vacio):
    assert separar(vacio) == ([], [])


def test_el_tope_es_el_tamano_del_top_de_candidatos():
    from ranking.criterio import TAMANO_TOP

    assert MAX_TICKERS == TAMANO_TOP


@pytest.mark.parametrize(
    "ticker, esperado",
    [("WALMEX.MX", True), ("RY.TO", True), ("BRK-B", False), ("MU", False)],
)
def test_tiene_sufijo(ticker, esperado):
    assert tiene_sufijo(ticker) is esperado
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_resolver.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'analizador'`.

- [ ] **Step 3: Implementar**

`analizador/__init__.py`: vacío.

`analizador/resolver.py`:

```python
"""Qué es cada ticker y de dónde salen sus números.

**La forma del ticker es una trampa en dos sitios.**
`research.universe.normalise_ticker` cambia todo punto por guion
(`BRK.B` → `BRK-B`), que es como Yahoo escribe las clases de acción, y con eso
`WALMEX.MX` acaba en `WALMEX-MX`, que Yahoo no conoce. `aprobacion.acta`
rechaza cualquier punto. Aquí el punto se distingue por lo que lleva detrás: si
es un sufijo de bolsa de Yahoo se conserva, y si no, es de clase de acción y
pasa a guion. Las dos funciones existentes no se tocan: sirven al universo del
S&P 500 y al acta, y ahí están bien.
"""

import re

from ranking.criterio import TAMANO_TOP

# Los sufijos de bolsa de Yahoo que se reconocen. Tabla cerrada a propósito: con
# un sufijo que no esté, el punto se lee como de clase de acción y el ticker
# sale con guion, que Yahoo no conocerá y la fila lo dirá. Lo contrario --tomar
# por bolsa cualquier cosa detrás de un punto-- convertiría `BF.B` en una bolsa
# llamada «B», y ese error no da ningún aviso.
SUFIJOS_DE_BOLSA = frozenset(
    {
        "MX",  # Bolsa Mexicana de Valores
        "TO", "V", "NE", "CN",  # Toronto, TSX Venture, NEO, CSE
        "L", "IL",  # Londres
        "DE", "F", "BE", "DU", "HM", "HA", "MU", "SG",  # Xetra, Fráncfort y regionales
        "PA", "AS", "BR", "LS", "MI", "MC", "SW", "VI",
        "ST", "HE", "CO", "OL", "IR", "WA", "PR", "AT",
        "HK", "T", "SS", "SZ", "KS", "KQ", "TW", "TWO",
        "SI", "KL", "BK", "JK", "AX", "NZ",
        "SA", "BA", "SN", "JO", "TA", "IS", "NS", "BO",
    }
)

# Cada ticker cuesta varias consultas de red, y el tope es el tamaño del top de
# candidatos: lo que el usuario ya está acostumbrado a revisar de una vez.
MAX_TICKERS = TAMANO_TOP

_LARGO_MAXIMO = 20
# Letras y dígitos, separados por un punto, un guion o un igual, y un `^`
# delante para los índices. Sin separadores seguidos ni al final: `A..B` o
# `WALMEX.` no son tickers mal escritos que se puedan arreglar, son otra cosa.
_FORMA = re.compile(r"^\^?[A-Z0-9]+(?:[.\-=][A-Z0-9]+)*$")
_SEPARADORES = re.compile(r"[,\s]+")


def tiene_sufijo(ticker: str) -> bool:
    """Si lo que va detrás del último punto es una bolsa de la tabla."""
    _, punto, sufijo = ticker.rpartition(".")
    return bool(punto) and sufijo in SUFIJOS_DE_BOLSA


def normalizar(texto: object) -> "str | None":
    """El ticker como lo escribe Yahoo, o `None` si no tiene forma de ticker."""
    if not isinstance(texto, str):
        return None
    limpio = texto.strip().upper()
    if len(limpio) > _LARGO_MAXIMO or not _FORMA.match(limpio):
        return None
    base, punto, sufijo = limpio.rpartition(".")
    if punto and sufijo in SUFIJOS_DE_BOLSA:
        return f"{base.replace('.', '-')}.{sufijo}"
    return limpio.replace(".", "-")


def separar(texto: "str | None") -> "tuple[list[str], list[str]]":
    """Los tickers de un campo de texto, separados por comas o espacios.

    Devuelve `(validos, invalidos)`: los válidos normalizados y sin repetir, en
    el orden en que se escribieron; los inválidos tal como se escribieron, para
    poder decir cuáles. El tope de `MAX_TICKERS` lo aplica quien llama, que es
    quien sabe decirlo en pantalla.
    """
    validos: list[str] = []
    invalidos: list[str] = []
    for trozo in _SEPARADORES.split(texto or ""):
        if not trozo:
            continue
        ticker = normalizar(trozo)
        if ticker is None:
            invalidos.append(trozo)
        elif ticker not in validos:
            validos.append(ticker)
    return validos, invalidos
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_resolver.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/__init__.py analizador/resolver.py tests/test_analizador_resolver.py
git commit -m "feat: la forma del ticker distingue el punto de una bolsa del de una clase de accion

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: El sector GICS de cualquier ticker

> **Ejecutada y superada** (9d4ec40, 598e5d5). La revisión: una celda vacía de la tabla del S&P 500 (NaN) recurre a Yahoo, y el docstring dice que Yahoo clasifica con Morningstar (≈4 % de empresas en otro sector). Manda el código vivo.

**Files:**
- Create: `analizador/sectores.py`
- Test: `tests/test_analizador_sectores.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_sectores.py`:

```python
from analizador.sectores import YAHOO_A_GICS, sector_gics
from fundamentals.sectors import load_sectors


def test_la_tabla_traduce_a_los_nombres_gics_que_usa_el_panel():
    gics = set(load_sectors().values())
    assert set(YAHOO_A_GICS.values()) <= gics
    # Once sectores GICS, once entradas: ninguno se queda sin traducir.
    assert set(YAHOO_A_GICS.values()) == gics


def test_una_empresa_del_sp500_usa_la_tabla_de_siempre():
    # Aunque Yahoo diga otra cosa: el panel de referencia está hecho con ésta.
    assert sector_gics("MU", "Healthcare", {"MU": "Information Technology"}) == (
        "Information Technology",
        "sp500",
    )


def test_fuera_del_sp500_se_traduce_el_de_yahoo():
    assert sector_gics("WALMEX.MX", "Consumer Defensive", {}) == ("Consumer Staples", "yahoo")


def test_un_sector_que_no_esta_en_la_tabla_no_se_adivina():
    assert sector_gics("XYZ", "Conglomerates", {}) == (None, "sin_sector")
    assert sector_gics("XYZ", None, {}) == (None, "sin_sector")
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_sectores.py -q`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

`analizador/sectores.py`:

```python
"""El sector GICS de un ticker, para compararlo con sus pares del S&P 500.

A una empresa del S&P 500 se le saca de la tabla congelada de siempre
(`fundamentals/data/sectores_2026-08-10.csv`): es con la que está hecho el
panel de referencia. A cualquier otra, del `info["sector"]` de Yahoo, que no usa
los nombres GICS y se traduce con esta tabla, también congelada. Un sector que
no esté aquí se queda sin pares, y se dice, en vez de adivinarse.
"""

from fundamentals.sectors import load_sectors

YAHOO_A_GICS = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
}


def sector_gics(
    ticker: str, sector_yahoo: "str | None", tabla: "dict | None" = None
) -> "tuple[str | None, str]":
    """El sector GICS y de dónde salió: `"sp500"`, `"yahoo"` o `"sin_sector"`.

    `tabla` se inyecta para las pruebas; por defecto es la del S&P 500.
    """
    tabla = load_sectors() if tabla is None else tabla
    if tabla.get(ticker):
        return tabla[ticker], "sp500"
    gics = YAHOO_A_GICS.get(sector_yahoo or "")
    return (gics, "yahoo") if gics else (None, "sin_sector")
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_sectores.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/sectores.py tests/test_analizador_sectores.py
git commit -m "feat: el sector GICS de cualquier ticker, de la tabla del S&P 500 o de Yahoo traducido

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: La identidad, los estados y el tipo de cambio, por `mercado`

> **Ejecutada y superada** (9787dbc, adde07b). La revisión encontró que un estado que llega vacío (yfinance se traga los 429) pisaba el guardado, y que Londres cotiza en peniques (`GBp`) y yfinance lo leía como libras: `mercado.SUBUNIDADES`. Además, Yahoo da la capitalización de Londres en libras (SHEL.L: capitalización ÷ precio = acciones ÷ 100), que corrigen `divisas.perfil_en` (Task 7) y `kpis.kpis_yf` (Task 12). Manda el código vivo.

`valoracion/mercado.py` es la única puerta a yfinance, con caché, respaldo cuando falla la red y motivos con nombre. Las tres fuentes nuevas entran por ella y reutilizan `_traer`.

**Files:**
- Modify: `valoracion/mercado.py`
- Test: `tests/test_valoracion_mercado.py` (las puras), `tests/test_valoracion_mercado_red.py` (las de red, con yfinance sustituido)

- [ ] **Step 1: Escribir los tests de las funciones puras**

Al final de `tests/test_valoracion_mercado.py` añade:

```python
# --- Los estados de yfinance, ida y vuelta a la caché --------------------------

from valoracion.mercado import estado_a_plano, estado_de_plano  # noqa: E402


def _estado():
    return pd.DataFrame(
        {
            pd.Timestamp("2026-06-30"): [2.5e11, float("nan")],
            pd.Timestamp("2026-03-31"): [2.45e11, -2.4e9],
        },
        index=["Total Revenue", "Capital Expenditure"],
    )


def test_un_estado_va_a_la_cache_con_nan_como_null_y_vuelve_igual():
    plano = estado_a_plano(_estado())
    assert plano["Capital Expenditure"]["2026-06-30"] is None
    json.dumps(plano, allow_nan=False)
    vuelta = estado_de_plano(plano)
    pd.testing.assert_frame_equal(vuelta, _estado().astype("float64"), check_names=False)


def test_el_estado_vuelve_con_la_columna_mas_reciente_primero():
    vuelta = estado_de_plano(estado_a_plano(_estado().iloc[:, ::-1]))
    assert list(vuelta.columns) == [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-03-31")]


def test_un_estado_vacio_es_un_plano_vacio_y_vuelve_vacio():
    assert estado_a_plano(pd.DataFrame()) == {}
    assert estado_a_plano(None) == {}
    assert estado_de_plano({}).empty


def test_un_plano_que_no_es_un_diccionario_no_se_lee():
    with pytest.raises(TypeError):
        estado_de_plano(["Total Revenue"])
```

y al principio del fichero, junto a los otros imports, `import json`.

- [ ] **Step 2: Escribir los tests de red, con yfinance sustituido**

En `tests/test_valoracion_mercado_red.py`, añade al final:

```python
# --- La identidad, los estados y el tipo de cambio ----------------------------

INFO_ETF = {
    "quoteType": "ETF",
    "exchange": "PCX",
    "currency": "USD",
    "regularMarketPrice": 769.6,
    "regularMarketTime": 1_791_835_140,
    "longName": "State Street SPDR S&P 500 ETF Trust",
}


def test_la_identidad_de_un_etf_se_lee_aunque_no_tenga_capitalizacion():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO_ETF)):
        identidad, motivo = mercado.identidad("SPY")
    assert motivo == "ok"
    assert identidad["quoteType"] == "ETF"
    assert identidad["regularMarketPrice"] == 769.6
    # Y `perfil`, que exige capitalización, no lo valora: es lo que se quiere.
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO_ETF)):
        assert mercado.perfil("SPY") == (None, "sin_precio")


def test_la_identidad_solo_guarda_las_claves_que_sirven():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info=INFO)):
        identidad, _ = mercado.identidad("MU")
    assert set(identidad) == set(mercado.CLAVES_IDENTIDAD_INFO)
    assert "beta" not in identidad


def test_una_identidad_sin_claves_no_se_guarda(tmp_path):
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(info={"trailingPegRatio": None})):
        assert mercado.identidad("ZZZZQ") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def _estados_dobles():
    estado = pd.DataFrame({pd.Timestamp("2026-06-30"): [2.5e11]}, index=["Total Revenue"])
    vacio = empty_df()
    return {nombre: (estado if nombre == "income_stmt" else vacio) for nombre in mercado.ESTADOS}


def test_los_estados_se_descargan_y_vuelven_como_dataframes():
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**_estados_dobles())):
        estados, motivo = mercado.estados("WALMEX.MX")
    assert motivo == "ok"
    assert set(estados) == set(mercado.ESTADOS)
    assert estados["income_stmt"].loc["Total Revenue"].iloc[0] == 2.5e11
    assert estados["cashflow"].empty


def test_seis_estados_vacios_no_se_guardan(tmp_path):
    vacios = {nombre: empty_df() for nombre in mercado.ESTADOS}
    with patch.object(mercado.yf, "Ticker", return_value=_ticker(**vacios)):
        assert mercado.estados("WALMEX.MX") == (None, "sin_red")
    assert _escritos(tmp_path) == []


def test_el_tipo_de_cambio_de_una_moneda_consigo_misma_no_sale_a_la_red():
    with patch.object(mercado.yf, "Ticker", side_effect=AssertionError("a la red no")):
        assert mercado.tipo_de_cambio("MXN", "MXN") == (1.0, "ok")


def test_el_tipo_de_cambio_es_el_ultimo_cierre_del_par():
    doble = _con_historial([0.0309, 0.0311])
    with patch.object(mercado.yf, "Ticker", return_value=doble) as fabrica:
        assert mercado.tipo_de_cambio("TWD", "USD") == (pytest.approx(0.0311), "ok")
    fabrica.assert_called_with("TWDUSD=X")


def test_un_tipo_de_cambio_vacio_no_se_guarda(tmp_path):
    with patch.object(mercado.yf, "Ticker", return_value=_con_historial([])):
        assert mercado.tipo_de_cambio("TWD", "USD") == (None, "sin_red")
    assert _escritos(tmp_path) == []
```

y amplía las tablas de los tests de respaldo, que ya existen en ese fichero, para que cubran las fuentes nuevas. En `_llamar`:

```python
def _llamar(fuente):
    return {
        "perfil": lambda: mercado.perfil("MU"),
        "tasa_libre": mercado.tasa_libre,
        "beta": lambda: mercado.beta("MU"),
        "tasa_efectiva": lambda: mercado.tasa_efectiva("MU"),
        "consenso": lambda: mercado.consenso("MU", "USD"),
        "identidad": lambda: mercado.identidad("MU"),
        "estados": lambda: mercado.estados("MU"),
        "tipo_de_cambio": lambda: mercado.tipo_de_cambio("TWD", "USD"),
    }[fuente]()
```

En `_red_buena`, antes de la última rama:

```python
    if fuente == "tipo_de_cambio":
        return {"return_value": _con_historial([0.0309, 0.0311])}
    if fuente == "estados":
        return {"return_value": _ticker(**_estados_dobles())}
```

Y en `FALLOS`:

```python
FALLOS = {
    "perfil": "sin_red",
    "tasa_libre": "sin_tasa_libre",
    "beta": "sin_red",
    "tasa_efectiva": "sin_red",
    "consenso": "sin_red",
    "identidad": "sin_red",
    "estados": "sin_red",
    "tipo_de_cambio": "sin_red",
}
```

`_estados_dobles` está definida más abajo en el fichero que `_red_buena`; como sólo se llama dentro de la función, en tiempo de ejecución, no importa el orden.

Ojo con los estados en el test de respaldo: `_llamar("estados")` devuelve un diccionario de DataFrames, y `==` entre diccionarios de DataFrames lanza `ValueError`. Cambia la comparación de `test_lo_guardado_sirve_de_respaldo_dentro_de_su_edad_maxima` por una que sirva para todas las fuentes:

```python
def _igual(a, b):
    """`==` no sirve para DataFrames; los estados se comparan con su propia igualdad."""
    if isinstance(a[0], dict) and a[0] and isinstance(next(iter(a[0].values())), pd.DataFrame):
        return a[1] == b[1] and all(a[0][k].equals(b[0][k]) for k in a[0])
    return a == b
```

y en ese test, `assert _igual(_llamar(fuente), bueno)` en lugar de `assert _llamar(fuente) == bueno`.

- [ ] **Step 3: Comprobar que fallan**

Run: `uv run pytest tests/test_valoracion_mercado.py tests/test_valoracion_mercado_red.py -q`
Expected: FAIL con `ImportError` (`estado_a_plano`) y `AttributeError` (`identidad`, `estados`, `tipo_de_cambio`, `CLAVES_IDENTIDAD_INFO`, `ESTADOS`).

- [ ] **Step 4: Implementar**

En `valoracion/mercado.py`:

1. En `VALIDEZ` añade las tres fuentes:

```python
VALIDEZ = {
    "perfil": timedelta(minutes=15),
    "tasa_libre": timedelta(days=1),
    "beta": timedelta(days=1),
    "tasa_efectiva": timedelta(days=1),
    "consenso": timedelta(days=1),
    # La identidad viaja en la misma llamada que el precio: un ETF no tiene
    # perfil, y su precio sólo está aquí.
    "identidad": timedelta(minutes=15),
    # Los estados cambian una vez por trimestre.
    "estados": timedelta(days=1),
    "tipo_de_cambio": timedelta(days=1),
}
```

2. En `ANTIGUEDAD_MAXIMA`:

```python
    # Qué es un ticker no cambia de un día a otro; su precio sí, y lleva su hora.
    "identidad": timedelta(days=7),
    # Un trimestre nuevo llega cada noventa días.
    "estados": timedelta(days=30),
    # Una semana de tipo de cambio mueve la valoración unas décimas.
    "tipo_de_cambio": timedelta(days=7),
```

3. Después de `CLAVES_DE_IDENTIDAD`, las claves que guarda la identidad y los nombres de los estados:

```python
# Lo que `identidad` guarda de `info`: qué es el ticker, dónde cotiza y en qué
# moneda, y su precio con la hora. Nada de beta: ver la docstring de `Perfil`.
CLAVES_IDENTIDAD_INFO = (
    "quoteType",
    "exchange",
    "currency",
    "financialCurrency",
    "sector",
    "industry",
    "country",
    "longName",
    "shortName",
    "currentPrice",
    "regularMarketPrice",
    "regularMarketTime",
)

ESTADOS = (
    "quarterly_income_stmt",
    "quarterly_balance_sheet",
    "quarterly_cashflow",
    "income_stmt",
    "balance_sheet",
    "cashflow",
)
```

4. Las dos funciones puras, junto a las demás `*_desde_*` (antes de la sección «Red»):

```python
def estado_a_plano(estado: "pd.DataFrame | None") -> dict:
    """Un estado de yfinance como `{fila: {fecha ISO: valor}}`, con NaN como None.

    La caché es JSON estricto: un NaN se escribiría como el literal `NaN`, que
    un lector estricto rechaza.
    """
    if estado is None or estado.empty:
        return {}
    plano: dict = {}
    for fila, valores in estado.iterrows():
        plano[str(fila)] = {
            pd.Timestamp(columna).date().isoformat(): _opcional(valor)
            for columna, valor in valores.items()
        }
    return plano


def estado_de_plano(plano: object) -> pd.DataFrame:
    """La inversa de `estado_a_plano`, con la columna más reciente primero, como
    las entrega yfinance. Lanza `TypeError` si no tiene la forma de un estado."""
    if not isinstance(plano, dict):
        raise TypeError("estado guardado sin forma de diccionario")
    if not plano:
        return pd.DataFrame()
    columnas = {
        fila: {
            pd.Timestamp(fecha): (math.nan if valor is None else float(valor))
            for fecha, valor in valores.items()
        }
        for fila, valores in plano.items()
    }
    estado = pd.DataFrame(columnas).T
    return estado.reindex(columns=sorted(estado.columns, reverse=True)).astype("float64")
```

5. Las tres funciones de red, al final del fichero:

```python
def identidad(ticker: str) -> "tuple[dict | None, str]":
    """Las claves de `info` que dicen qué es un ticker, aunque no tenga capitalización.

    Va aparte de `perfil` porque un ETF no tiene capitalización y `perfil` lo
    descarta con `sin_precio`; el Analizador necesita saber que es un ETF para
    enseñarlo sin valorarlo. Igual que en `perfil`, un `info` sin ninguna clave
    de identidad no dice nada --la red, un error de Yahoo o un símbolo que no
    conoce-- y no se guarda.
    """

    def pedir():
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else None

    def interpretar(info):
        if not any(clave in info for clave in CLAVES_DE_IDENTIDAD):
            return None
        return {"identidad": {clave: info.get(clave) for clave in CLAVES_IDENTIDAD_INFO}}

    def leer(datos):
        return dict(datos["identidad"])

    return _traer("identidad", ticker, pedir, interpretar, leer)


def estados(ticker: str) -> "tuple[dict | None, str]":
    """Los seis estados de yfinance, trimestrales y anuales, como DataFrames."""

    def pedir():
        objeto = yf.Ticker(ticker)
        return {nombre: getattr(objeto, nombre) for nombre in ESTADOS}

    def interpretar(crudos):
        # Como `history()`, los estados no lanzan cuando falla la red: llegan
        # vacíos. Con los seis vacíos no se sabe nada, y guardarlo como «no hay
        # estados» es el defecto que la revisión de M encontró en el precio.
        planos = {nombre: estado_a_plano(crudos.get(nombre)) for nombre in ESTADOS}
        if not any(planos.values()):
            return None
        return {"estados": planos}

    def leer(datos):
        return {nombre: estado_de_plano(datos["estados"][nombre]) for nombre in ESTADOS}

    return _traer("estados", ticker, pedir, interpretar, leer)


def tipo_de_cambio(origen: str, destino: str) -> "tuple[float | None, str]":
    """Cuántas unidades de `destino` vale una de `origen`, al último cierre.

    El par de Yahoo es `<ORIGEN><DESTINO>=X`: `TWDUSD=X` da dólares por cada
    dólar taiwanés. Una moneda consigo misma vale 1 sin salir a la red.
    """
    if origen == destino:
        return 1.0, "ok"
    simbolo = f"{origen}{destino}=X"

    def pedir():
        return yf.Ticker(simbolo).history(period="5d")["Close"]

    def interpretar(cierres):
        if _sin_cierres(cierres):
            return None
        ultimo = float(pd.to_numeric(cierres, errors="coerce").dropna().iloc[-1])
        return {"valor": ultimo if ultimo > 0 else None}

    valor, motivo = _traer("tipo_de_cambio", simbolo, pedir, interpretar, _valor)
    if motivo != "ok":
        return None, motivo
    return (float(valor), "ok") if valor is not None else (None, "sin_tipo_de_cambio")
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_valoracion_mercado.py tests/test_valoracion_mercado_red.py -q`
Expected: todos pasan, incluidos los parametrizados de respaldo con las tres fuentes nuevas.

- [ ] **Step 6: Commit**

```bash
git add valoracion/mercado.py tests/test_valoracion_mercado.py tests/test_valoracion_mercado_red.py
git commit -m "feat: mercado trae la identidad, los estados y el tipo de cambio, con su cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: La clase de cada ticker

> **Ejecutada y superada** (769dba7, c7a935c, 1b119e4, 0a7d0a0). La revisión encontró que edgartools memoriza en el proceso un fallo al bajar la lista viva de tickers de la SEC, y un corte se guardaba 30 días como «no la conoce»: ahora se limpia y da `sin_red_edgar`, y un `()` vale un día. La clase sale del último informe anual de la ventana reciente, sin enmiendas (una petición por ticker; JPM costaba 71), y no de «alguna vez presentó». `_limpiar` quita toda la categoría Unicode `Cf`. Manda el código vivo.

**Files:**
- Modify: `analizador/resolver.py`
- Modify: `.gitignore`
- Test: `tests/test_analizador_resolver.py`

- [ ] **Step 1: Escribir los tests**

Añade a `tests/test_analizador_resolver.py`:

```python
from datetime import timedelta  # noqa: E402
from unittest.mock import patch  # noqa: E402

from analizador import resolver  # noqa: E402
from analizador.resolver import Identidad, clase_de, identidad_desde_info  # noqa: E402

INFO_MU = {
    "quoteType": "EQUITY",
    "exchange": "NMS",
    "currency": "USD",
    "financialCurrency": "USD",
    "sector": "Technology",
    "industry": "Semiconductors",
    "country": "United States",
    "longName": "Micron Technology, Inc.",
    "currentPrice": 914.13,
    "regularMarketPrice": 914.13,
    "regularMarketTime": 1_791_835_140,
}


def test_la_identidad_lee_lo_que_hace_falta():
    i = identidad_desde_info("MU", INFO_MU)
    assert (i.tipo, i.bolsa, i.moneda, i.moneda_estados) == ("EQUITY", "NMS", "USD", "USD")
    assert (i.sector, i.industria, i.pais) == ("Technology", "Semiconductors", "United States")
    assert i.nombre == "Micron Technology, Inc."
    assert i.precio == 914.13
    assert i.hora == "2026-10-12T19:59:00+00:00"


def test_sin_precio_actual_la_identidad_toma_el_de_mercado():
    info = {**INFO_MU, "currentPrice": None, "regularMarketPrice": 769.6}
    assert identidad_desde_info("SPY", info).precio == 769.6


def test_la_moneda_de_los_estados_cae_a_la_del_precio():
    info = {k: v for k, v in INFO_MU.items() if k != "financialCurrency"}
    assert identidad_desde_info("MU", info).moneda_estados == "USD"


def _identidad(tipo="EQUITY"):
    return identidad_desde_info("X", {**INFO_MU, "quoteType": tipo})


@pytest.mark.parametrize(
    "tipo, formularios, esperado",
    [
        ("ETF", ("10-K",), ("etf", None)),
        ("EQUITY", ("10-K",), ("sec", None)),
        ("EQUITY", ("20-F",), ("extranjera_sec", None)),
        # RY presenta 40-F y edgartools la marca `is_foreign = False`: la clase
        # sale de los formularios, no de esa marca.
        ("EQUITY", ("40-F",), ("extranjera_sec", None)),
        ("EQUITY", (), ("sin_sec", None)),
        ("INDEX", (), (None, "tipo_no_soportado")),
        ("MUTUALFUND", (), (None, "tipo_no_soportado")),
        ("CRYPTOCURRENCY", (), (None, "tipo_no_soportado")),
        (None, (), (None, "tipo_no_soportado")),
    ],
)
def test_la_clase(tipo, formularios, esperado):
    assert clase_de(_identidad(tipo), formularios) == esperado


@pytest.fixture
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "RAIZ_CACHE", tmp_path)
    monkeypatch.setenv("EDGAR_IDENTITY", "pruebas@example.com")
    return tmp_path


def test_los_formularios_se_preguntan_una_vez_y_se_guardan(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=("10-K",)) as consulta:
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")
    consulta.assert_called_once_with("MU")


def test_un_ticker_que_edgar_no_conoce_no_presenta_nada_y_se_guarda(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=()):
        assert resolver.formularios_sec("ZZZZ") == ((), "ok")
    assert list(cache_aislada.rglob("*.json"))


def test_sin_red_y_sin_nada_guardado_lo_dice(cache_aislada):
    with patch.object(resolver, "_consultar_sec", return_value=None):
        assert resolver.formularios_sec("MU") == (None, "sin_red_edgar")
    assert list(cache_aislada.rglob("*.json")) == []


def test_sin_red_vale_lo_guardado_aunque_haya_caducado(cache_aislada, monkeypatch):
    with patch.object(resolver, "_consultar_sec", return_value=("10-K",)):
        resolver.formularios_sec("MU")
    monkeypatch.setattr(resolver, "VALIDEZ_FORMULARIOS", timedelta(seconds=-1))
    with patch.object(resolver, "_consultar_sec", return_value=None):
        assert resolver.formularios_sec("MU") == (("10-K",), "ok")


def test_sin_identidad_de_edgar_no_se_pregunta(cache_aislada, monkeypatch):
    monkeypatch.delenv("EDGAR_IDENTITY")
    with patch.object(resolver, "_consultar_sec", side_effect=AssertionError("no")):
        assert resolver.formularios_sec("MU") == (None, "sin_identidad_edgar")


def _resolver(ticker, info, formularios=("10-K",)):
    with patch.object(resolver.mercado, "identidad", return_value=(info, "ok")), patch.object(
        resolver, "formularios_sec", return_value=(formularios, "ok")
    ) as sec:
        return resolver.resolver(ticker), sec


def test_resolver_una_empresa_de_la_sec():
    resuelto, _ = _resolver("MU", INFO_MU)
    assert (resuelto.ticker, resuelto.clase, resuelto.motivo) == ("MU", "sec", None)
    assert resuelto.identidad.nombre == "Micron Technology, Inc."


def test_un_ticker_con_sufijo_de_bolsa_no_se_pregunta_a_edgar():
    resuelto, sec = _resolver("WALMEX.MX", {**INFO_MU, "currency": "MXN"})
    assert resuelto.clase == "sin_sec"
    sec.assert_not_called()


def test_un_etf_no_se_pregunta_a_edgar():
    resuelto, sec = _resolver("SPY", {**INFO_MU, "quoteType": "ETF"})
    assert resuelto.clase == "etf"
    sec.assert_not_called()


def test_si_yahoo_no_devuelve_nada_el_motivo_es_el_suyo():
    with patch.object(resolver.mercado, "identidad", return_value=(None, "sin_red")):
        resuelto = resolver.resolver("ZZZZQ")
    assert (resuelto.clase, resuelto.identidad, resuelto.motivo) == (None, None, "sin_red")


def test_un_indice_tiene_identidad_pero_no_clase():
    resuelto, _ = _resolver("^GSPC", {**INFO_MU, "quoteType": "INDEX"})
    assert resuelto.clase is None and resuelto.motivo == "tipo_no_soportado"
    assert resuelto.identidad.tipo == "INDEX"


def test_si_edgar_no_responde_no_se_adivina_la_clase():
    with patch.object(resolver.mercado, "identidad", return_value=(INFO_MU, "ok")), patch.object(
        resolver, "formularios_sec", return_value=(None, "sin_red_edgar")
    ):
        resuelto = resolver.resolver("MU")
    # Tratar a MU como `sin_sec` la valoraría con yfinance en vez de con EDGAR
    # sin decirlo: es mejor no tener clase que tener la equivocada.
    assert resuelto.clase is None and resuelto.motivo == "sin_red_edgar"
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_resolver.py -q`
Expected: FAIL con `ImportError` (`Identidad`, `clase_de`, `identidad_desde_info`).

- [ ] **Step 3: Implementar**

Añade a `analizador/resolver.py`. Los imports nuevos van arriba, con los demás:

```python
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from noticias import cache
from valoracion import mercado

# Privadas y aun así importadas: son la lectura de `info` que `mercado` ya
# hace para el perfil. Una segunda copia aquí es como empiezan a separarse.
from valoracion.mercado import _hora, _num, _texto
```

y al final del fichero:

```python
# --- La clase de cada ticker -----------------------------------------------------
#
# | Clase            | Presenta          | Números                     |
# |------------------|-------------------|-----------------------------|
# | `sec`            | 10-K              | EDGAR, como los candidatos  |
# | `extranjera_sec` | 20-F o 40-F       | yfinance                    |
# | `sin_sec`        | nada en EDGAR     | yfinance                    |
# | `etf`            | —                 | ninguno: no se valora       |
#
# Los motivos de un ticker sin clase son claves, no textos: `sin_red` (Yahoo no
# devolvió nada), `tipo_no_soportado` (un índice, un fondo, una divisa o una
# cripto), `sin_red_edgar` y `sin_identidad_edgar`. Las etiquetas las pone N2.

RAIZ_CACHE = Path(__file__).resolve().parent / ".cache"
# Qué informes anuales presenta una empresa no cambia en meses.
VALIDEZ_FORMULARIOS = timedelta(days=30)
# Para que `cache.leer` devuelva lo guardado tenga la edad que tenga: sin red,
# un formulario de hace meses sigue diciendo la verdad.
_CUALQUIER_EDAD = timedelta(days=36_500)
FORMULARIOS_ANUALES = ("10-K", "20-F", "40-F")
_EXTRANJEROS = ("20-F", "40-F")


@dataclass(frozen=True)
class Identidad:
    """Qué es un ticker según Yahoo. Precio y hora, para enseñarlos; nada de beta."""

    ticker: str
    tipo: "str | None"
    nombre: "str | None"
    bolsa: "str | None"
    moneda: "str | None"
    moneda_estados: "str | None"
    sector: "str | None"
    industria: "str | None"
    pais: "str | None"
    precio: "float | None"
    hora: "str | None"


@dataclass(frozen=True)
class Resuelto:
    """La clase de un ticker, o por qué no tiene. `motivo` es None si hay clase."""

    ticker: str
    clase: "str | None"
    identidad: "Identidad | None"
    motivo: "str | None"


def identidad_desde_info(ticker: str, info: dict) -> Identidad:
    precio = _num(info.get("currentPrice"))
    if not precio > 0:
        precio = _num(info.get("regularMarketPrice"))
    moneda = _texto(info.get("currency"))
    return Identidad(
        ticker=ticker,
        tipo=_texto(info.get("quoteType")),
        nombre=_texto(info.get("longName")) or _texto(info.get("shortName")),
        bolsa=_texto(info.get("exchange")),
        moneda=moneda,
        moneda_estados=_texto(info.get("financialCurrency")) or moneda,
        sector=_texto(info.get("sector")),
        industria=_texto(info.get("industry")),
        pais=_texto(info.get("country")),
        precio=precio if precio > 0 else None,
        hora=_hora(info.get("regularMarketTime")),
    )


def clase_de(
    identidad: Identidad, formularios: "tuple[str, ...]"
) -> "tuple[str | None, str | None]":
    """`(clase, None)`, o `(None, motivo)` si el ticker no es una acción ni un ETF."""
    if identidad.tipo == "ETF":
        return "etf", None
    if identidad.tipo != "EQUITY":
        return None, "tipo_no_soportado"
    if "10-K" in formularios:
        return "sec", None
    if any(f in formularios for f in _EXTRANJEROS):
        return "extranjera_sec", None
    return "sin_sec", None


def _consultar_sec(ticker: str) -> "tuple[str, ...] | None":
    """Qué informes anuales presenta el ticker en EDGAR.

    `()` si EDGAR no conoce el ticker, que es un hecho y se guarda; `None` si no
    se pudo saber. Aislada para los tests. Sólo las llamadas a edgartools van
    dentro del `try`, para que un defecto propio no se disfrace de «sin red».
    """
    from edgar import Company
    from edgar.exceptions import NotFoundError

    try:
        empresa = Company(ticker)
        presentados = tuple(
            forma for forma in FORMULARIOS_ANUALES if len(empresa.get_filings(form=forma)) > 0
        )
    except NotFoundError:
        return ()
    except Exception:
        # edgartools lanza de todo según qué falle --transporte, identidad
        # rechazada, una respuesta a medias-- y aquí sólo importa que no se supo.
        return None
    return presentados


def formularios_sec(ticker: str) -> "tuple[tuple[str, ...] | None, str]":
    """Los informes anuales del ticker en EDGAR, de la caché si vale y si no de la red."""
    if not (os.environ.get("EDGAR_IDENTITY") or "").strip():
        # La SEC rechaza las peticiones sin contacto, y el rechazo llega como un
        # fallo de red: mejor decir qué falta.
        return None, "sin_identidad_edgar"
    guardado = cache.leer(RAIZ_CACHE, "formularios", ticker, _CUALQUIER_EDAD)
    previo = None
    if guardado is not None and isinstance(guardado.datos, list):
        previo = tuple(guardado.datos)
        if guardado.cuando + VALIDEZ_FORMULARIOS > datetime.now(timezone.utc):
            return previo, "ok"
    encontrados = _consultar_sec(ticker)
    if encontrados is None:
        return (previo, "ok") if previo is not None else (None, "sin_red_edgar")
    try:
        cache.guardar(RAIZ_CACHE, "formularios", ticker, list(encontrados))
    except OSError:
        pass
    return encontrados, "ok"


def resolver(ticker: str) -> Resuelto:
    """Qué es un ticker ya normalizado: su identidad de Yahoo y su clase."""
    crudo, motivo = mercado.identidad(ticker)
    if crudo is None:
        return Resuelto(ticker, None, None, motivo)
    identidad = identidad_desde_info(ticker, crudo)
    if identidad.tipo == "EQUITY" and not tiene_sufijo(ticker):
        formularios, motivo = formularios_sec(ticker)
        if formularios is None:
            return Resuelto(ticker, None, identidad, motivo)
    else:
        # Un ETF, un tipo no soportado o una emisora con sufijo de bolsa: la
        # clase no depende de EDGAR, y preguntar costaría un segundo por ticker.
        formularios = ()
    clase, motivo = clase_de(identidad, formularios)
    return Resuelto(ticker, clase, identidad, motivo)
```

`cache.leer` devuelve `None` si no hay nada; su `vigente` no sirve aquí porque se lee con `_CUALQUIER_EDAD` y la vigencia la decide `VALIDEZ_FORMULARIOS`.

En `.gitignore`, junto a `valoracion/.cache/`, añade:

```
analizador/.cache/
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_resolver.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/resolver.py tests/test_analizador_resolver.py .gitignore
git commit -m "feat: la clase de cada ticker sale de Yahoo y de los formularios de EDGAR

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Los estados de yfinance en las columnas del motor

> **Ejecutada y revisada** (3e4645a y su arreglo). Con estados reales de 37 tickers, la revisión encontró que el relleno desde el anual se fiaba de cifras de Yahoo que no cuadran (WALMEX: intereses a 0,0 en los trimestres y el año entero en el 3T, cobertura de 2,09 contra una real de 8,3; HSBC: amortización negativa), y que un anual de transición se trataba como un año. La fila que falta salta con `MonthEnd(3)` desde un fin de mes. Manda el código vivo.

**Files:**
- Create: `analizador/lineas_yf.py`
- Test: `tests/test_analizador_lineas_yf.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_lineas_yf.py`:

```python
"""Los estados de yfinance traducidos a las líneas de `fundamentals.concepts`."""

import numpy as np
import pandas as pd
import pytest

from analizador.lineas_yf import (
    FILAS,
    lineas_desde_estados,
    rejilla_trimestral,
    rellenar_desde_anual,
)
from fundamentals.concepts import LINEAS

NAN = float("nan")


def hoja(fechas: list[str], filas: dict) -> pd.DataFrame:
    """Una hoja como la entrega yfinance: filas por nombre, una columna por fecha."""
    return pd.DataFrame(filas, index=[pd.Timestamp(f) for f in fechas]).T


def test_cada_linea_del_motor_tiene_su_fila_de_yfinance():
    assert set(FILAS) == set(LINEAS)


def test_el_capex_llega_en_positivo_como_en_la_sec():
    flujos = hoja(["2026-06-30"], {"Capital Expenditure": [-9.265e9], "Operating Cash Flow": [1.8e10]})
    lineas = lineas_desde_estados(None, None, flujos)
    assert lineas.loc["2026-06-30", "capex"] == 9.265e9
    assert lineas.loc["2026-06-30", "flujo_operativo"] == 1.8e10


def test_sin_beneficio_operativo_se_usa_el_ebit_fila_a_fila():
    # BRK-B no trae `Operating Income`; otra empresa puede traerlo sólo a ratos.
    resultados = hoja(
        ["2026-06-30", "2026-03-31"],
        {"Operating Income": [NAN, 5.0], "EBIT": [7.0, 9.0]},
    )
    lineas = lineas_desde_estados(resultados, None, None)
    assert lineas["beneficio_operativo"].tolist() == [5.0, 7.0]


def test_el_beneficio_es_el_de_los_accionistas_comunes():
    resultados = hoja(
        ["2026-06-30"],
        {"Net Income": [2.116e10], "Net Income Common Stockholders": [2.075e10]},
    )
    assert lineas_desde_estados(resultados, None, None)["beneficio_neto"].iloc[0] == 2.075e10


def test_las_lineas_van_de_la_mas_antigua_a_la_mas_reciente_y_estan_todas():
    resultados = hoja(["2026-06-30", "2026-03-31"], {"Total Revenue": [2.0, 1.0]})
    lineas = lineas_desde_estados(resultados, None, None)
    assert list(lineas.index) == [pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")]
    assert list(lineas.columns) == list(LINEAS)
    assert lineas["ingresos"].tolist() == [1.0, 2.0]


def test_una_fecha_sin_ningun_dato_no_es_una_fila():
    # El balance de WALMEX trae la columna del 3T 2025 vacía.
    balance = hoja(
        ["2026-06-30", "2025-09-30"],
        {"Total Assets": [5.0e11, NAN], "Stockholders Equity": [2.4e11, NAN]},
    )
    lineas = lineas_desde_estados(None, balance, None)
    assert list(lineas.index) == [pd.Timestamp("2026-06-30")]


def test_sin_ninguna_hoja_no_hay_lineas():
    assert lineas_desde_estados(None, pd.DataFrame(), None).empty


# --- La rejilla trimestral ----------------------------------------------------


def _trimestres(fechas, ingresos):
    lineas = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    lineas["ingresos"] = ingresos
    return lineas


def test_el_trimestre_que_falta_tiene_su_fila_vacia():
    lineas = _trimestres(
        ["2025-03-31", "2025-06-30", "2025-12-31", "2026-03-31", "2026-06-30"],
        [1.0, 2.0, 4.0, 5.0, 6.0],
    )
    rejilla = rejilla_trimestral(lineas)
    assert list(rejilla.index) == list(
        pd.DatetimeIndex(
            ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
        )
    )
    assert np.isnan(rejilla.loc["2025-09-30", "ingresos"])
    assert rejilla.loc["2026-06-30", "ingresos"] == 6.0


def test_un_calendario_fiscal_consecutivo_no_cambia():
    # MU cierra trimestres en mayo, febrero, noviembre y agosto.
    fechas = ["2025-05-31", "2025-08-31", "2025-11-30", "2026-02-28", "2026-05-31"]
    lineas = _trimestres(fechas, [1.0, 2.0, 3.0, 4.0, 5.0])
    pd.testing.assert_frame_equal(
        rejilla_trimestral(lineas), lineas, check_freq=False, check_names=False
    )


def test_la_fila_que_falta_cae_tres_meses_despues_de_la_anterior():
    lineas = _trimestres(["2025-05-31", "2025-11-30"], [1.0, 3.0])
    assert rejilla_trimestral(lineas).index[1] == pd.Timestamp("2025-08-31")


# --- El trimestre que falta, desde el anual -----------------------------------


def _anual(fecha, **valores):
    anual = pd.DataFrame(NAN, index=pd.DatetimeIndex([fecha]), columns=list(LINEAS))
    for linea, valor in valores.items():
        anual[linea] = valor
    return anual


def _rejilla_walmex():
    fechas = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    rejilla = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    rejilla["ingresos"] = [241.0, 246.0, NAN, 283.0, 245.0, 251.0]
    rejilla["acciones_diluidas"] = [17.35, 17.27, NAN, 17.38, 17.29, 17.16]
    rejilla["activos_totales"] = [480.0, 481.0, NAN, 495.0, 497.0, 506.0]
    return rejilla


def test_el_flujo_del_trimestre_que_falta_es_el_ano_menos_los_otros_tres():
    anual = _anual("2025-12-31", ingresos=1011.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert rellena.loc["2025-09-30", "ingresos"] == pytest.approx(1011.0 - 241.0 - 246.0 - 283.0)


def test_una_media_ponderada_se_rellena_como_media_y_no_como_suma():
    anual = _anual("2025-12-31", acciones_diluidas=17.37)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert rellena.loc["2025-09-30", "acciones_diluidas"] == pytest.approx(
        4 * 17.37 - 17.35 - 17.27 - 17.38
    )


def test_un_saldo_de_balance_no_se_rellena():
    # El activo a 30 de septiembre es una foto: el anual no dice nada de ella.
    anual = _anual("2025-12-31", activos_totales=495.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert np.isnan(rellena.loc["2025-09-30", "activos_totales"])


def test_con_dos_trimestres_vacios_no_se_inventa_ninguno():
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-06-30", "ingresos"] = NAN
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", ingresos=1011.0))
    assert rellena["ingresos"].isna().sum() == 2


def test_lo_que_ya_tiene_dato_no_se_toca():
    rejilla = _rejilla_walmex()
    rejilla.loc["2025-09-30", "ingresos"] = 240.0
    rellena = rellenar_desde_anual(rejilla, _anual("2025-12-31", ingresos=9999.0))
    pd.testing.assert_frame_equal(rellena, rejilla)


def test_una_media_que_saldria_absurda_no_se_rellena():
    # Cuatro veces el anual menos tres trimestres multiplica cualquier error por
    # cuatro: fuera del doble o la mitad del anual no es una medición.
    anual = _anual("2025-12-31", acciones_diluidas=30.0)
    rellena = rellenar_desde_anual(_rejilla_walmex(), anual)
    assert np.isnan(rellena.loc["2025-09-30", "acciones_diluidas"])
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_lineas_yf.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'analizador.lineas_yf'`.

- [ ] **Step 3: Implementar**

`analizador/lineas_yf.py`:

```python
"""Los estados de yfinance en las mismas columnas que la SEC.

Las filas de yfinance se traducen a las columnas que produce
`fundamentals.concepts.resolve_lines`, y de ahí pasan por las mismas funciones
de `fundamentals/kpis.py`. Así el ROE de WALMEX y el de MU salen de la misma
fórmula y en la misma base trimestral.

Los nombres de fila se fijaron contra lo que yfinance 1.6 devuelve de verdad
para MU, WALMEX.MX, TSM, JPM y BRK-B (sondeo del 2026-10-14); el test `red`
comprueba que siguen ahí.

**El capex se cambia de signo**: yfinance lo da negativo, como una salida de
caja, y la SEC lo declara positivo, como un pago. `valoracion.fundamentos` y
`fundamentals.kpis` lo esperan positivo.

**yfinance da cinco o seis trimestres, y a veces se salta uno** (a WALMEX le
falta el 3T 2025). `fundamentals.kpis` compara con `shift(4)` y suma con
`rolling(4)`, que cuentan filas y no trimestres: con un hueco, el «mismo
trimestre del año pasado» caería en otro. `rejilla_trimestral` da una fila a
cada trimestre natural, y `rellenar_desde_anual` recupera el flujo del que falta
como el año menos los otros tres.
"""

import numpy as np
import pandas as pd

from fundamentals.concepts import LINEAS

# Privadas y aun así importadas: son la duración de un trimestre con que
# `fundamentals.panel` decide qué es un trimestre, y el límite con que descarta
# una media derivada que se aleja demasiado de la anual. Una segunda copia aquí
# es como se separan.
from fundamentals.panel import _DIAS_TRIMESTRE, _FACTOR_MAXIMO_MEDIA, _TRIMESTRES_POR_ANO

# Cada línea del motor, la hoja de la que sale y sus filas candidatas por orden.
# La primera con dato **en cada fecha** gana, como en `resolve_lines`.
FILAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ingresos": ("resultados", ("Total Revenue",)),
    "coste_de_ventas": ("resultados", ("Cost Of Revenue",)),
    # BRK-B no trae `Operating Income`, sólo `EBIT`.
    "beneficio_operativo": ("resultados", ("Operating Income", "EBIT")),
    # El de los accionistas comunes, que es el que divide el BPA: en JPM, el
    # `Net Income` total incluye los dividendos de las preferentes.
    "beneficio_neto": ("resultados", ("Net Income Common Stockholders",)),
    "bpa_diluido": ("resultados", ("Diluted EPS",)),
    "depreciacion_amortizacion": ("resultados", ("Reconciled Depreciation",)),
    "gasto_por_intereses": ("resultados", ("Interest Expense",)),
    "acciones_diluidas": ("resultados", ("Diluted Average Shares",)),
    "activos_totales": ("balance", ("Total Assets",)),
    "activos_corrientes": ("balance", ("Current Assets",)),
    "pasivos_corrientes": ("balance", ("Current Liabilities",)),
    "patrimonio_neto": ("balance", ("Stockholders Equity",)),
    "deuda_total": ("balance", ("Total Debt",)),
    "efectivo": ("balance", ("Cash And Cash Equivalents",)),
    "flujo_operativo": ("flujos", ("Operating Cash Flow",)),
    "capex": ("flujos", ("Capital Expenditure",)),
}

# Las líneas que son flujos del periodo: su año es la suma de sus trimestres.
# El recuento medio de acciones es una media ponderada: su año es el promedio.
_FLUJOS = (
    "ingresos",
    "coste_de_ventas",
    "beneficio_operativo",
    "beneficio_neto",
    "depreciacion_amortizacion",
    "gasto_por_intereses",
    "flujo_operativo",
    "capex",
    "acciones_diluidas",
)
_MEDIAS = ("acciones_diluidas",)

# Los trimestres de un ejercicio que cierra en `fin` caen entre unos 273 días
# antes y `fin`; el cuarto trimestre del ejercicio anterior, a unos 365. Tres
# trimestres largos (300 días) separan los dos casos con margen, también en los
# calendarios de 52/53 semanas.
_ANTES_DEL_CIERRE = pd.Timedelta(days=3 * _DIAS_TRIMESTRE[1])
_DESPUES_DEL_CIERRE = pd.Timedelta(days=7)


def _fila(estado: pd.DataFrame, candidatas: "tuple[str, ...]") -> pd.Series:
    """La primera candidata con dato, columna a columna."""
    serie = pd.Series(np.nan, index=estado.columns, dtype="float64")
    for nombre in candidatas:
        if nombre not in estado.index:
            continue
        valores = estado.loc[nombre]
        if isinstance(valores, pd.DataFrame):
            # Un nombre de fila repetido: se queda la primera, como la ordena yfinance.
            valores = valores.iloc[0]
        serie = serie.where(serie.notna(), pd.to_numeric(valores, errors="coerce"))
    return serie


def lineas_desde_estados(
    resultados: "pd.DataFrame | None",
    balance: "pd.DataFrame | None",
    flujos: "pd.DataFrame | None",
) -> pd.DataFrame:
    """Las tres hojas de un periodo (trimestral o anual) en las columnas del motor.

    Una fila por fecha de cierre, de la más antigua a la más reciente, y siempre
    todas las columnas de `LINEAS`: un panel cuyas columnas dependen de la
    empresa no se puede concatenar con otro. Una fecha sin ningún dato no es una
    fila: el balance de WALMEX trae vacía la columna del trimestre que falta.
    """
    hojas = {"resultados": resultados, "balance": balance, "flujos": flujos}
    fechas = sorted(
        {
            pd.Timestamp(columna)
            for hoja in hojas.values()
            if hoja is not None and not hoja.empty
            for columna in hoja.columns
        }
    )
    indice = pd.DatetimeIndex(fechas, name="period_end")
    lineas = pd.DataFrame(np.nan, index=indice, columns=list(LINEAS), dtype="float64")
    for linea, (nombre_hoja, candidatas) in FILAS.items():
        hoja = hojas[nombre_hoja]
        if hoja is None or hoja.empty:
            continue
        serie = _fila(hoja, candidatas)
        serie.index = pd.DatetimeIndex([pd.Timestamp(c) for c in serie.index])
        serie = serie[~serie.index.duplicated(keep="first")]
        lineas[linea] = serie.reindex(indice)
    lineas["capex"] = -lineas["capex"]
    return lineas.dropna(how="all")


def rejilla_trimestral(lineas: pd.DataFrame) -> pd.DataFrame:
    """Una fila por trimestre natural, consecutivos, con el que falta en NaN.

    El que falta lleva la fecha de tres meses después del anterior: así las
    distancias entre fechas siguen siendo las de un trimestre, que es lo que
    miran `valoracion.fundamentos` y `fundamentals.panel`.
    """
    if lineas.empty:
        return lineas
    trimestres = pd.PeriodIndex(lineas.index, freq="Q")
    # El mismo trimestre natural dos veces sería un cambio de calendario fiscal:
    # se queda la fecha más reciente, que es la que la empresa publicó después.
    lineas = lineas[~trimestres.duplicated(keep="last")]
    trimestres = pd.PeriodIndex(lineas.index, freq="Q")
    por_trimestre = dict(zip(trimestres, lineas.index))
    todos = pd.period_range(trimestres.min(), trimestres.max(), freq="Q")
    fechas, anterior = [], None
    for trimestre in todos:
        fecha = por_trimestre.get(trimestre)
        if fecha is None:
            fecha = anterior + pd.DateOffset(months=3)
        fechas.append(fecha)
        anterior = fecha
    rejilla = lineas.set_axis(trimestres).reindex(todos)
    rejilla.index = pd.DatetimeIndex(fechas, name=lineas.index.name)
    return rejilla


def rellenar_desde_anual(trimestres: pd.DataFrame, anuales: pd.DataFrame) -> pd.DataFrame:
    """El flujo del trimestre que falta, como el año menos los otros tres.

    Es la aritmética de `fundamentals.panel._cuartos_derivados`, que reconstruye
    el cuarto trimestre que la SEC no declara suelto, llevada a cualquier
    trimestre: dentro de un ejercicio con exactamente un trimestre vacío y el
    anual declarado, el vacío es el año menos los tres. Con dos vacíos no hay
    aritmética que valga, y se quedan vacíos.

    Sólo para flujos: un saldo de balance es una foto, y la del cierre no dice
    nada de la de septiembre. El recuento medio de acciones es una media: cuatro
    veces el anual menos los tres, y sólo si lo que sale no se aleja más del
    doble o la mitad del anual, que es la guarda de `fundamentals.panel`.
    """
    if trimestres.empty or anuales.empty:
        return trimestres
    rellenas = trimestres.copy()
    fechas = rellenas.index
    for fin, ano in anuales.iterrows():
        dentro = (fechas > fin - _ANTES_DEL_CIERRE) & (fechas <= fin + _DESPUES_DEL_CIERRE)
        posiciones = np.flatnonzero(dentro)
        if len(posiciones) != _TRIMESTRES_POR_ANO:
            continue
        for linea in _FLUJOS:
            anual = ano[linea]
            if not np.isfinite(anual):
                continue
            valores = rellenas[linea].iloc[posiciones]
            vacios = valores.isna().to_numpy()
            if vacios.sum() != 1:
                continue
            media = linea in _MEDIAS
            valor = (_TRIMESTRES_POR_ANO if media else 1) * anual - valores[~vacios].sum()
            if media and not (
                anual / _FACTOR_MAXIMO_MEDIA <= valor <= anual * _FACTOR_MAXIMO_MEDIA
            ):
                continue
            rellenas.iloc[posiciones[vacios][0], rellenas.columns.get_loc(linea)] = valor
    return rellenas
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_lineas_yf.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/lineas_yf.py tests/test_analizador_lineas_yf.py
git commit -m "feat: los estados de yfinance en las columnas del motor, con el trimestre que falta a la vista

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Los KPIs trimestrales y los ejercicios anuales de yfinance

> **Ejecutada y revisada** (2c60fc5, 25f4baa y su arreglo). Con 79 tickers reales: cuatro ejercicios seguidos en todos, el balance del cierre y el crecimiento contra el mismo trimestre. La revisión acotó el trimestre roto a unos ingresos negativos (la guarda amplia tiraba el 1T de NVO, que cuadra con lo publicado), sacó el trimestre roto de los KPIs, quitó las filas sin ningún KPI y midió que los suelos de `fundamentals.kpis` están en dólares: los KPIs de yfinance se calculan en dólares en la Task 12. Manda el código vivo.

**Files:**
- Modify: `analizador/lineas_yf.py`
- Test: `tests/test_analizador_lineas_yf.py`

- [ ] **Step 1: Escribir los tests**

Añade a `tests/test_analizador_lineas_yf.py`:

```python
from datetime import date  # noqa: E402

from analizador.lineas_yf import fundamentos_anuales, kpis_trimestrales, lineas_de  # noqa: E402
from fundamentals.kpis import TODOS_LOS_KPIS  # noqa: E402


def _rejilla(n=6, hueco=None):
    fechas = pd.date_range("2025-03-31", periods=n, freq="QE")
    lineas = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    lineas["ingresos"] = [100.0 + 10 * i for i in range(n)]
    lineas["beneficio_operativo"] = [20.0 + i for i in range(n)]
    lineas["beneficio_neto"] = 10.0
    lineas["acciones_diluidas"] = 10.0
    lineas["bpa_diluido"] = 1.0
    if hueco is not None:
        lineas.iloc[hueco] = NAN
    return lineas


def test_los_kpis_son_los_del_motor_y_llevan_su_trimestre():
    lineas = _rejilla()
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    assert list(kpis.columns) == [*TODOS_LOS_KPIS, "trimestre"]
    assert kpis["margen_operativo"].iloc[0] == pytest.approx(20.0 / 100.0)
    assert kpis["trimestre"].iloc[0] == "2025Q1"
    assert kpis.index.name == "periodo"


def test_el_crecimiento_compara_con_el_mismo_trimestre_aunque_falte_uno():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    # El 1T 2026 (fila 4) contra el 1T 2025 (fila 0), con el 3T 2025 vacío en medio.
    assert kpis.loc["2026-03-31", "crecimiento_ingresos"] == pytest.approx(140.0 / 100.0 - 1)


def test_la_fila_que_solo_ocupaba_su_sitio_no_sale():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    assert pd.Timestamp("2025-09-30") not in kpis.index
    assert len(kpis) == 5


def test_sin_cuatro_trimestres_seguidos_no_hay_multiplo_de_doce_meses():
    lineas = _rejilla(hueco=2)
    kpis = kpis_trimestrales(lineas, pd.Series(20.0, index=lineas.index))
    # Las ventanas de cuatro que pasan por el hueco no suman; la última, tampoco.
    assert kpis["per"].isna().all()
    completa = _rejilla()
    kpis = kpis_trimestrales(completa, pd.Series(20.0, index=completa.index))
    assert kpis["per"].iloc[-1] == pytest.approx(20.0 / 4.0)


def test_sin_lineas_no_hay_kpis():
    vacias = pd.DataFrame(columns=list(LINEAS), dtype="float64")
    assert kpis_trimestrales(vacias, pd.Series(dtype="float64")).empty


# --- Los ejercicios anuales --------------------------------------------------


def _anuales(fechas, **columnas):
    anuales = pd.DataFrame(NAN, index=pd.DatetimeIndex(fechas), columns=list(LINEAS))
    for linea, valores in columnas.items():
        anuales[linea] = valores
    return anuales


def test_los_ejercicios_van_del_mas_reciente_al_mas_antiguo():
    anuales = _anuales(
        ["2022-08-31", "2023-08-31", "2024-08-31", "2025-08-31"],
        ingresos=[30.8, 15.5, 25.1, 37.4],
        flujo_operativo=[15.2, 1.6, 8.5, 17.5],
        capex=[12.1, 7.7, 8.4, 15.9],
        patrimonio_neto=[49.9, 44.1, 45.1, 54.2],
        deuda_total=[7.5, 13.9, 14.0, 15.3],
        efectivo=[8.3, 8.6, 7.0, 9.6],
    )
    f = fundamentos_anuales(anuales, "USD")
    assert [e.fin for e in f.ejercicios] == [
        date(2025, 8, 31), date(2024, 8, 31), date(2023, 8, 31), date(2022, 8, 31)
    ]
    assert f.ultimo.ingresos == 37.4 and f.ultimo.capex == 15.9
    # El balance es el del cierre del último ejercicio.
    assert (f.deuda_total, f.efectivo) == (15.3, 9.6)
    assert (f.moneda, f.fuente) == ("USD", "yfinance")


def test_un_ano_que_falta_corta_la_serie():
    # Saltarse el hueco devolvería ejercicios que ya no son años seguidos, y
    # `supuestos._cagr` toma `ejercicios[i]` como «hace i años».
    anuales = _anuales(["2021-12-31", "2023-12-31", "2024-12-31", "2025-12-31"], ingresos=1.0)
    assert len(fundamentos_anuales(anuales, "MXN").ejercicios) == 3


def test_una_fila_sin_ancla_entre_dos_anos_se_salta_y_no_corta_la_serie():
    # El anual de RY trae columnas a fechas trimestrales con sólo el BPA y el
    # recuento de doce meses móviles: no son años y no deben cortar la serie.
    anuales = _anuales(
        ["2022-10-31", "2023-07-31", "2023-10-31", "2024-07-31", "2024-10-31"],
        ingresos=[50.0, NAN, 55.0, NAN, 60.0],
        bpa_diluido=[1.0, 1.1, 1.2, 1.3, 1.4],
    )
    f = fundamentos_anuales(anuales, "CAD")
    assert [e.fin for e in f.ejercicios] == [
        date(2024, 10, 31), date(2023, 10, 31), date(2022, 10, 31)
    ]


def test_un_ano_que_esta_pero_sin_ingresos_corta_la_serie_por_la_distancia():
    # Saltar la fila sin ancla no puede convertirse en saltarse un año: el
    # siguiente con ancla está a dos años, y la distancia corta.
    anuales = _anuales(
        ["2023-12-31", "2024-12-31", "2025-12-31"], ingresos=[1.0, NAN, 1.0]
    )
    assert len(fundamentos_anuales(anuales, "USD").ejercicios) == 1


def test_un_banco_sin_ingresos_se_ancla_en_el_beneficio():
    anuales = _anuales(["2024-12-31", "2025-12-31"], beneficio_neto=[50.0, 55.0])
    assert len(fundamentos_anuales(anuales, "USD").ejercicios) == 2


def test_sin_ningun_ejercicio_valido_no_hay_fundamentos():
    assert fundamentos_anuales(_anuales(["2025-12-31"], efectivo=1.0), "USD") is None
    assert fundamentos_anuales(pd.DataFrame(columns=list(LINEAS)), "USD") is None


def test_lineas_de_junta_las_seis_hojas():
    trimestre = hoja(
        ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30", "2025-03-31"],
        {"Total Revenue": [251.0, 245.0, 283.0, 246.0, 241.0]},
    )
    anual = hoja(["2025-12-31"], {"Total Revenue": [1011.0]})
    estados = {
        "quarterly_income_stmt": trimestre,
        "quarterly_balance_sheet": pd.DataFrame(),
        "quarterly_cashflow": pd.DataFrame(),
        "income_stmt": anual,
        "balance_sheet": pd.DataFrame(),
        "cashflow": pd.DataFrame(),
    }
    trimestrales, anuales = lineas_de(estados)
    assert trimestrales.loc["2025-09-30", "ingresos"] == pytest.approx(241.0)
    assert anuales.loc["2025-12-31", "ingresos"] == 1011.0
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_lineas_yf.py -q`
Expected: FAIL con `ImportError` (`fundamentos_anuales`, `kpis_trimestrales`, `lineas_de`).

- [ ] **Step 3: Implementar**

En `analizador/lineas_yf.py`, sustituye las dos líneas de imports de `fundamentals.concepts` y de `fundamentals.panel` por éstas:

```python
from fundamentals.concepts import (
    LINEAS,
    completar_bpa_por_identidad,
    reconciliar_recuento_de_acciones,
)
from fundamentals.kpis import (
    TODOS_LOS_KPIS,
    compute_growth,
    compute_levels,
    compute_valuation,
)

# Privadas y aun así importadas: son la duración de un trimestre y de un año
# con que `fundamentals.panel` decide qué es cada cosa, y el límite con que
# descarta una media derivada que se aleja demasiado de la anual. Una segunda
# copia aquí es como se separan.
from fundamentals.panel import (
    _DIAS_ANO,
    _DIAS_TRIMESTRE,
    _FACTOR_MAXIMO_MEDIA,
    _TRIMESTRES_POR_ANO,
)

# Privada y aun así importada: es el cubo de trimestre natural del panel de la
# SEC, y los dos paneles se juntan por él.
from fundamentals.run import _trimestre_natural
from valoracion.fundamentos import Ejercicio, Fundamentos, _num
```

y al final del fichero:

```python
def lineas_de(estados: dict) -> "tuple[pd.DataFrame, pd.DataFrame]":
    """Las líneas trimestrales, en rejilla y con el hueco rellenado, y las anuales.

    `estados` es lo que devuelve `valoracion.mercado.estados`. Las trimestrales
    pasan por las mismas reconciliaciones que el panel de la SEC, en el mismo
    orden; con yfinance casi nunca tocan nada, pero dos caminos para el mismo
    dato se separan, y el que se queda atrás no da error.
    """
    anuales = lineas_desde_estados(
        estados.get("income_stmt"), estados.get("balance_sheet"), estados.get("cashflow")
    )
    trimestrales = lineas_desde_estados(
        estados.get("quarterly_income_stmt"),
        estados.get("quarterly_balance_sheet"),
        estados.get("quarterly_cashflow"),
    )
    trimestrales = rellenar_desde_anual(rejilla_trimestral(trimestrales), anuales)
    trimestrales = completar_bpa_por_identidad(reconciliar_recuento_de_acciones(trimestrales))
    return trimestrales, anuales


def kpis_trimestrales(lineas: pd.DataFrame, precios: pd.Series) -> pd.DataFrame:
    """Los diecisiete KPIs, con las funciones del panel de la SEC, y el trimestre natural.

    `lineas` viene en rejilla: los KPIs se calculan con la fila vacía en su sitio
    --es lo que mantiene el `shift(4)` en el mismo trimestre del año anterior--,
    y esa fila sale después, porque no es un trimestre medido. `precios` va
    indexado por las mismas fechas y en la moneda de los estados.
    """
    columnas = [*TODOS_LOS_KPIS, "trimestre"]
    if lineas.empty:
        return pd.DataFrame(columns=columnas)
    kpis = pd.concat(
        [compute_levels(lineas), compute_growth(lineas), compute_valuation(lineas, precios)],
        axis=1,
    ).reindex(columns=list(TODOS_LOS_KPIS))
    kpis["trimestre"] = _trimestre_natural(lineas.index)
    kpis.index.name = "periodo"
    return kpis[lineas.notna().any(axis=1).to_numpy()]


def fundamentos_anuales(anuales: pd.DataFrame, moneda: str) -> "Fundamentos | None":
    """Los ejercicios fiscales de yfinance, del más reciente al más antiguo y seguidos.

    Ejercicios completos y no un TTM trimestral: con cinco trimestres sólo cabe
    un TTM, y ponerlo delante de los anuales rompería que `ejercicios[i]` sea
    «hace i años». `estados_hasta` dice en pantalla de cuándo son.

    El ancla es la de `valoracion.fundamentos.desde_lineas`: los ingresos si
    algún año los tiene, y si no el beneficio, que es lo que declara un banco.
    El más reciente es el último año con ancla; los demás van hacia atrás, y la
    serie se corta en el primer año que no dista un año del anterior. Una fila
    sin ancla se salta en vez de cortar: el anual de RY trae columnas a fechas
    trimestrales con sólo el BPA de doce meses móviles, y cortar en ellas le
    dejaría un solo ejercicio. Un año que de verdad falta lo detecta la
    distancia al siguiente con ancla. El balance es el del cierre del más
    reciente.
    """
    if anuales.empty:
        return None
    ancla = "ingresos" if anuales["ingresos"].notna().any() else "beneficio_neto"
    elegidos: list = []
    for fecha, fila in anuales.sort_index(ascending=False).iterrows():
        if pd.isna(fila[ancla]):
            continue
        if elegidos:
            dias = (elegidos[-1][0] - fecha).days
            if not _DIAS_ANO[0] <= dias <= _DIAS_ANO[1]:
                break
        elegidos.append((fecha, fila))
    if not elegidos:
        return None
    ejercicios = tuple(
        Ejercicio(
            fin=fecha.date(),
            ingresos=_num(fila["ingresos"]),
            flujo_operativo=_num(fila["flujo_operativo"]),
            capex=_num(fila["capex"]),
            gasto_financiero=_num(fila["gasto_por_intereses"]),
            beneficio_operativo=_num(fila["beneficio_operativo"]),
            beneficio_neto=_num(fila["beneficio_neto"]),
            patrimonio_neto=_num(fila["patrimonio_neto"]),
        )
        for fecha, fila in elegidos
    )
    _, ultima = elegidos[0]
    return Fundamentos(
        moneda=moneda,
        fuente="yfinance",
        ejercicios=ejercicios,
        deuda_total=_num(ultima["deuda_total"]),
        efectivo=_num(ultima["efectivo"]),
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_lineas_yf.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/lineas_yf.py tests/test_analizador_lineas_yf.py
git commit -m "feat: KPIs trimestrales y ejercicios anuales de yfinance, con las funciones del motor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: La moneda de la valoración, el Bono M y la ADR

> **Ejecutada y superada** (aa03319, b94f5c0). Recorrida en vivo con SHEL.L, AZN.L, GSK.L, ULVR.L, TSM, RY.TO, WALMEX.MX, AMX y FMX: las unidades salen bien en los nueve. La revisión ancló el `desde` del Bono M al 1 de enero del año anterior (con un `desde` móvil la clave de la caché cambiaba cada día y se perdía el respaldo sin red), y `a_dict` dice `estados_convertidos`, que es lo que mide; la prima país la decide la Task 13. Manda el código vivo.

**Files:**
- Create: `analizador/divisas.py`
- Test: `tests/test_analizador_divisas.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_divisas.py`:

```python
import math
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import divisas
from analizador.divisas import (
    Divisa,
    adr_dudosa,
    cociente_adr,
    convertir,
    moneda_de_valoracion,
    perfil_en,
)
from seguimiento.banxico import Serie
from tests.dobles_valoracion import ejercicio, fundamentos, perfil


@pytest.mark.parametrize(
    "estados, esperado", [("USD", "USD"), ("MXN", "MXN"), ("TWD", "USD"), ("CAD", "USD")]
)
def test_la_moneda_de_la_valoracion(estados, esperado):
    assert moneda_de_valoracion(estados) == esperado


def test_convertir_multiplica_todo_lo_que_es_dinero():
    f = fundamentos(ejercicios=[ejercicio(2025, gasto_financiero=float("nan"))])
    c = convertir(f, 0.031, "USD")
    e, o = c.ultimo, f.ultimo
    assert c.moneda == "USD"
    assert e.ingresos == pytest.approx(o.ingresos * 0.031)
    assert e.capex == pytest.approx(o.capex * 0.031)
    assert e.patrimonio_neto == pytest.approx(o.patrimonio_neto * 0.031)
    assert c.deuda_total == pytest.approx(f.deuda_total * 0.031)
    assert c.efectivo == pytest.approx(f.efectivo * 0.031)
    assert e.fin == o.fin
    # «No declarado» sigue siendo «no declarado».
    assert math.isnan(e.gasto_financiero)


def test_convertir_a_la_misma_moneda_no_cambia_nada():
    f = fundamentos()
    assert convertir(f, 1.0, "USD") is f


def test_el_precio_se_lleva_a_la_moneda_de_la_valoracion():
    p = perfil_en(perfil(precio=100.0, capitalizacion=1000.0, moneda="CAD"), 0.7, "USD")
    assert (p.precio, p.capitalizacion, p.moneda, p.moneda_estados) == (70.0, 700.0, "USD", "USD")


def test_en_londres_la_capitalizacion_va_en_libras_y_el_precio_en_peniques():
    # SHEL.L el 2026-10-14: precio 3.911,5 peniques, capitalización 222.520
    # millones de libras y 5.688,9 millones de acciones. Capitalización ÷ precio
    # sin corregir da las acciones entre cien.
    shel = perfil(precio=3911.5, capitalizacion=222_519_934_976.0, moneda="GBp")
    p = perfil_en(shel, 0.013237, "USD")
    assert p.precio == pytest.approx(3911.5 * 0.013237)
    assert p.capitalizacion / p.precio == pytest.approx(5_688_864_370.0, rel=1e-6)


def test_el_cociente_de_la_adr():
    # TSM: yfinance da el recuento en base ADR, así que cuadra.
    tsm = perfil(precio=430.0, capitalizacion=2_230_183_788_544.0)
    assert cociente_adr(5_186_474_013.0, tsm) == pytest.approx(1.0, abs=1e-3)
    assert not adr_dudosa(cociente_adr(5_186_474_013.0, tsm))
    # Con el recuento de acciones ordinarias, cinco por ADR, saltaría el aviso.
    assert adr_dudosa(cociente_adr(5 * 5_186_474_013.0, tsm))


def test_sin_recuento_no_hay_cociente():
    assert cociente_adr(float("nan"), perfil()) is None
    assert cociente_adr(None, perfil()) is None
    assert not adr_dudosa(None)


def _cambio(tipos):
    def tipo_de_cambio(origen, destino):
        if (origen, destino) in tipos:
            return tipos[(origen, destino)]
        return (1.0, "ok") if origen == destino else (None, "sin_red")

    return tipo_de_cambio


def test_tsm_se_valora_en_dolares_con_los_estados_convertidos():
    cambio = _cambio({("TWD", "USD"): (0.031, "ok")})
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=cambio):
        d, motivo = divisas.divisa("TWD", "USD")
    assert motivo == "ok"
    assert d == Divisa("TWD", "USD", "USD", 0.031, 1.0, "^GSPC")
    assert d.convertida


def test_walmex_se_valora_en_pesos_contra_el_ipc_sin_convertir():
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=_cambio({})):
        d, _ = divisas.divisa("MXN", "MXN")
    assert d == Divisa("MXN", "MXN", "MXN", 1.0, 1.0, "^MXX")
    assert not d.convertida


def test_sin_tipo_de_cambio_no_hay_divisa_y_se_dice_por_que():
    with patch.object(divisas.mercado, "tipo_de_cambio", side_effect=_cambio({})):
        assert divisas.divisa("CAD", "CAD") == (None, "sin_red")


def test_la_divisa_como_diccionario_dice_si_falta_la_prima_pais():
    d = Divisa("TWD", "USD", "USD", 0.031, 1.0, "^GSPC")
    assert d.a_dict() == {
        "moneda_estados": "TWD",
        "moneda_precio": "USD",
        "moneda_valoracion": "USD",
        "tipo_estados": 0.031,
        "tipo_precio": 1.0,
        "indice_beta": "^GSPC",
        "sin_prima_pais": True,
    }


def test_el_bono_m_es_el_ultimo_dato_en_tanto_por_uno_con_su_fecha():
    datos = pd.Series([9.10, 9.25], index=pd.DatetimeIndex(["2026-08-27", "2026-09-24"]))
    with patch.object(divisas.banxico, "traer", return_value=Serie(datos, "ok")) as traer:
        assert divisas.bono_m("t" * 64, hoy=date(2026, 10, 14)) == (
            pytest.approx(0.0925),
            "ok",
            date(2026, 9, 24),
        )
    serie, desde, hasta, clave = traer.call_args.args
    assert serie == "SF44071" and hasta == date(2026, 10, 14)
    assert (hasta - desde).days == divisas.DIAS_BONO_M


def test_sin_token_el_bono_m_lo_dice():
    with patch.object(divisas.banxico, "traer", return_value=Serie(None, "sin_token")):
        assert divisas.bono_m("") == (None, "sin_token", None)


def test_sin_subasta_en_la_ventana_no_hay_bono_m():
    vacia = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    with patch.object(divisas.banxico, "traer", return_value=Serie(vacia, "ok")):
        assert divisas.bono_m("t" * 64) == (None, "sin_dato", None)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_divisas.py -q`
Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar**

`analizador/divisas.py`:

```python
"""En qué moneda se valora un ticker, con qué tasa libre y contra qué índice.

| Estados | Se valora en | Tasa libre                    | Beta contra   |
|---------|--------------|-------------------------------|---------------|
| USD     | dólares      | `^TNX`                        | `^GSPC`       |
| MXN     | pesos        | Bono M a 10 años, de Banxico  | `^MXX` (IPC)  |
| otra    | dólares      | `^TNX`                        | `^GSPC`       |

En el tercer caso los estados se convierten a dólares al tipo del día y la
valoración no lleva prima por riesgo país, y se dice (`Divisa.convertida`). El
precio se lleva a la moneda de la valoración para votar: un valor en dólares
frente a un precio en dólares canadienses no dice nada.

El Bono M se usa tal cual, sin restarle el diferencial soberano que Damodaran
propone quitarle antes de sumar una prima de riesgo país: con una beta cercana
a 1 la diferencia es de décimas, el supuesto se puede mover y la procedencia lo
dice.
"""

import math
from dataclasses import dataclass, fields, replace
from datetime import date, timedelta

from seguimiento import banxico
from valoracion import mercado
from valoracion.fundamentos import Ejercicio, Fundamentos
from valoracion.mercado import Perfil

# «Valores Gubernamentales. Resultados de la subasta semanal. Tasa de
# rendimiento. Bono tasa fija 10 años», en porcentaje. Buscada en el catálogo
# del SIE el 2026-10-14; la fija un test `red` contra el título de sus
# metadatos. Es de subasta, no de mercado secundario: el último dato puede
# tener semanas, y su fecha va en la procedencia.
SERIE_BONO_M_10 = "SF44071"
INDICE_MXN = "^MXX"
# Las monedas con tasa libre propia. Cualquier otra se valora en dólares.
MONEDAS_PROPIAS = ("USD", "MXN")
# La subasta del bono a diez años es cada pocas semanas: cuatro meses de
# ventana traen siempre la última.
DIAS_BONO_M = 120
# Recuento de los estados entre el de la cotización. Fuera de este margen el
# recuento de los estados no es el de la cotización: una ADR con un ratio
# distinto de 1, o una clase de acción que no es la que cotiza.
ADR_TOLERANCIA = (0.8, 1.25)


@dataclass(frozen=True)
class Divisa:
    """Cómo se pasan los estados y el precio a la moneda de la valoración.

    Los tipos son unidades de `moneda_valoracion` por cada unidad de la otra
    moneda; 1 si coinciden.
    """

    moneda_estados: str
    moneda_precio: str
    moneda_valoracion: str
    tipo_estados: float
    tipo_precio: float
    indice_beta: str

    @property
    def convertida(self) -> bool:
        """Si los estados se pasaron a dólares: entonces no hay prima por riesgo país."""
        return self.moneda_estados != self.moneda_valoracion

    def a_dict(self) -> dict:
        datos = {campo.name: getattr(self, campo.name) for campo in fields(self)}
        return {**datos, "sin_prima_pais": self.convertida}


def moneda_de_valoracion(moneda_estados: str) -> str:
    return moneda_estados if moneda_estados in MONEDAS_PROPIAS else "USD"


def divisa(moneda_estados: str, moneda_precio: str) -> "tuple[Divisa | None, str]":
    """La moneda de la valoración y los dos tipos de cambio, o por qué no se pudo."""
    valoracion = moneda_de_valoracion(moneda_estados)
    tipo_estados, motivo = mercado.tipo_de_cambio(moneda_estados, valoracion)
    if tipo_estados is None:
        return None, motivo
    tipo_precio, motivo = mercado.tipo_de_cambio(moneda_precio, valoracion)
    if tipo_precio is None:
        return None, motivo
    indice = INDICE_MXN if valoracion == "MXN" else mercado.INDICE
    return (
        Divisa(moneda_estados, moneda_precio, valoracion, tipo_estados, tipo_precio, indice),
        "ok",
    )


_DINERO = tuple(campo.name for campo in fields(Ejercicio) if campo.name != "fin")


def convertir(fundamentos: Fundamentos, tipo: float, moneda: str) -> Fundamentos:
    """Los mismos fundamentos en otra moneda. NaN, «no declarado», se queda NaN."""
    if tipo == 1.0 and fundamentos.moneda == moneda:
        return fundamentos
    ejercicios = tuple(
        replace(e, **{nombre: getattr(e, nombre) * tipo for nombre in _DINERO})
        for e in fundamentos.ejercicios
    )
    return replace(
        fundamentos,
        moneda=moneda,
        ejercicios=ejercicios,
        deuda_total=fundamentos.deuda_total * tipo,
        efectivo=fundamentos.efectivo * tipo,
    )


def perfil_en(perfil: Perfil, tipo: float, moneda: str) -> Perfil:
    """El precio y la capitalización en la moneda de la valoración, para votar.

    `tipo` es el del precio. El recuento de acciones (capitalización ÷ precio)
    tiene que salir el de verdad: es lo que desactiva la trampa de la ADR,
    como en M. Por eso una cotización en subunidades se corrige: Yahoo da el
    precio de Londres en peniques y la capitalización en libras (SHEL.L:
    capitalización ÷ precio = acciones ÷ 100), así que la capitalización se
    convierte con el tipo de la moneda principal, que es el de la subunidad por
    su escala (`mercado.SUBUNIDADES`).
    """
    _, escala = mercado.SUBUNIDADES.get(perfil.moneda, (perfil.moneda, 1))
    return replace(
        perfil,
        precio=perfil.precio * tipo,
        capitalizacion=perfil.capitalizacion * tipo * escala,
        moneda=moneda,
        moneda_estados=moneda,
    )


def cociente_adr(acciones_estados: "float | None", perfil: Perfil) -> "float | None":
    """El recuento de los estados entre el de la cotización (capitalización ÷ precio).

    Cerca de 1 es lo normal. TSM da 1 con yfinance, que ya trae su recuento en
    base ADR; con el XBRL del 20-F daría 5. El valor por acción se divide
    siempre por el de la cotización, así que esto no corrige nada: avisa.
    `perfil` es el ya convertido por `perfil_en`, que corrige la capitalización
    de las cotizaciones en subunidades; con el de Yahoo tal cual, una empresa de
    Londres saldría con un cociente de 100.
    """
    try:
        estados = float(acciones_estados)
    except (TypeError, ValueError):
        return None
    cotizacion = perfil.capitalizacion / perfil.precio
    if not (math.isfinite(estados) and estados > 0 and cotizacion > 0):
        return None
    return estados / cotizacion


def adr_dudosa(cociente: "float | None") -> bool:
    return cociente is not None and not ADR_TOLERANCIA[0] <= cociente <= ADR_TOLERANCIA[1]


def bono_m(
    clave: "str | None" = None, hoy: "date | None" = None, raiz=None
) -> "tuple[float | None, str, date | None]":
    """El rendimiento de la última subasta del Bono M a diez años, en tanto por uno.

    Con el transporte de `seguimiento/banxico.py`: el token en la cabecera y
    nunca en la URL, su caché y sus motivos (`sin_token`, `token_invalido`,
    `sin_red`, `respuesta_rara`). Sin subasta en la ventana, `sin_dato`.
    Devuelve también la fecha de la subasta, que va a la procedencia. `raiz`
    es la carpeta de la caché, para que los tests no escriban en la de verdad.
    """
    hoy = hoy or date.today()
    clave = banxico.token() if clave is None else clave
    otra_raiz = {} if raiz is None else {"raiz": raiz}
    serie = banxico.traer(
        SERIE_BONO_M_10, hoy - timedelta(days=DIAS_BONO_M), hoy, clave, **otra_raiz
    )
    if serie.motivo != "ok":
        return None, serie.motivo, None
    if serie.datos is None or serie.datos.empty:
        return None, "sin_dato", None
    return float(serie.datos.iloc[-1]) / 100, "ok", serie.datos.index[-1].date()
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_divisas.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/divisas.py tests/test_analizador_divisas.py
git commit -m "feat: la moneda de la valoracion, el Bono M de Banxico y el aviso de la ADR

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: La tasa libre con su procedencia, y `aplicar`

> **Ejecutada y superada** (6f5d434, e3287c1). La revisión encontró que mover la tasa libre no rehacía el crecimiento perpetuo (que `deducir` recorta a ella) ni el tope del coste de la deuda medido: en pesos, la misma tasa del 3 % daba 581 puesta a mano y 646 movida desde el Bono M; ahora 581,41 y 581,38. `aplicar` rechaza con `ValueError` lo que rompe las fórmulas (coste del capital ≤ 0, que dividía por cero en el EPV; reparto fuera de [0, 1]; tasa fuera de [0, 1)), no cuenta un cambio a su propio valor y recalcula el coste de capital en diferencias. Manda el código vivo.

`deducir` fijaba la procedencia de la tasa libre al Tesoro de EE. UU.; con el Bono M tiene que decir otra cosa. Y `aplicar` es la función que M dejó a N: los deslizadores de la pantalla mueven supuestos sin volver a la red.

**Files:**
- Modify: `valoracion/supuestos.py`
- Modify: `medidores_valoracion.py`
- Test: `tests/test_valoracion_supuestos.py`, `tests/test_medidores_valoracion.py`

- [ ] **Step 1: Escribir los tests de `supuestos`**

Añade al final de `tests/test_valoracion_supuestos.py`:

```python
# --- La procedencia de la tasa libre y `aplicar` ------------------------------

from tests.dobles_valoracion import ejercicio as _ejercicio  # noqa: E402
from tests.dobles_valoracion import fundamentos as _fundamentos  # noqa: E402
from tests.dobles_valoracion import perfil as _perfil  # noqa: E402
from valoracion.mercado import Beta as _Beta  # noqa: E402
from valoracion.supuestos import MOVIBLES, aplicar, movidos  # noqa: E402
from valoracion.supuestos import deducir as _deducir  # noqa: E402


def test_sin_procedencia_la_tasa_libre_es_el_tesoro():
    s = _deducir(_fundamentos(), _perfil(), 0.05, None, None, None)
    assert s.r_f.procedencia == {"fuente": "tesoro_10", "serie": "^TNX"}


def test_la_tasa_libre_lleva_la_procedencia_que_se_le_da():
    bono = {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    s = _deducir(_fundamentos(), _perfil(), 0.0925, None, None, None, procedencia_r_f=bono)
    assert s.r_f.procedencia == bono


def _base():
    return _deducir(_fundamentos(), _perfil(), 0.05, _Beta(1.2, 0.4, 104, "^GSPC"), 0.21, 0.10)


def test_sin_cambios_los_supuestos_son_los_mismos():
    s = _base()
    assert aplicar(s, {}) is s


def test_mover_el_crecimiento_no_toca_el_coste_de_capital():
    s = _base()
    n = aplicar(s, {"g_ref": 0.30})
    assert n.g_ref.valor == 0.30
    assert n.g_ref.procedencia == {"fuente": "usuario", "programa": s.g_ref.valor}
    assert (n.k_e, n.wacc) == (s.k_e, s.wacc)


def test_mover_la_beta_recalcula_el_capital_propio_y_el_de_capital():
    s = _base()
    n = aplicar(s, {"beta": 2.0})
    assert n.k_e.valor == pytest.approx(0.05 + 2.0 * s.prima.valor)
    assert n.k_e.procedencia == {**s.k_e.procedencia, "recalculado": True}
    peso = s.wacc.procedencia["peso_deuda"]
    esperado = (1 - peso) * n.k_e.valor + peso * s.k_d.valor * (1 - s.t.valor)
    assert n.wacc.valor == pytest.approx(esperado)
    assert n.wacc.procedencia["recalculado"] is True


def test_mover_la_tasa_libre_arrastra_al_coste_de_la_deuda_sin_dato():
    # Sin gasto financiero declarado, el coste de la deuda ES la tasa libre.
    ejercicios = [_ejercicio(2026 - i, gasto_financiero=float("nan")) for i in range(4)]
    s = _deducir(_fundamentos(ejercicios=ejercicios), _perfil(), 0.05, None, 0.21, 0.10)
    assert s.k_d.procedencia["fuente"] == "sin_dato"
    n = aplicar(s, {"r_f": 0.07})
    assert n.k_d.valor == 0.07
    assert n.k_d.procedencia["recalculado"] is True


def test_un_coste_de_la_deuda_medido_no_sigue_a_la_tasa_libre():
    s = _base()
    assert s.k_d.procedencia["fuente"] == "gasto_entre_deuda"
    assert aplicar(s, {"r_f": 0.07}).k_d == s.k_d


def test_en_una_financiera_el_coste_de_capital_sigue_vacio():
    s = _deducir(_fundamentos(), _perfil(industria="Banks - Regional"), 0.05, None, 0.21, 0.10)
    n = aplicar(s, {"beta": 1.5})
    assert n.wacc.valor is None
    assert n.k_e.procedencia["recalculado"] is True


def test_lo_derivado_no_se_mueve_a_mano():
    with pytest.raises(ValueError, match="k_e"):
        aplicar(_base(), {"k_e": 0.1})
    assert "k_e" not in MOVIBLES and "wacc" not in MOVIBLES


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), "x", None])
def test_un_valor_que_no_es_un_numero_finito_se_rechaza(valor):
    with pytest.raises(ValueError):
        aplicar(_base(), {"g_ref": valor})


def test_movidos_dice_cuales_movio_el_usuario_en_el_orden_de_siempre():
    assert movidos(aplicar(_base(), {"g_ref": 0.3, "beta": 2.0})) == ("beta", "g_ref")
    assert movidos(_base()) == ()
```

Comprueba antes que `_base()` da un `k_d` con fuente `gasto_entre_deuda` con los dobles por defecto (intereses 20 sobre deuda 200: un 10 %, entre la tasa libre y la tasa más ocho puntos). Si no, ajusta el test con el cambio mínimo y dilo en el informe.

- [ ] **Step 2: Escribir los tests de la pantalla**

Añade al final de `tests/test_medidores_valoracion.py`:

```python
# --- Las fuentes nuevas del Analizador ----------------------------------------


def test_la_tasa_libre_del_bono_m_dice_su_serie_su_fecha_y_lo_que_no_resta():
    supuesto = {
        "valor": 0.0925,
        "procedencia": {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"},
    }
    texto = mv.procedencia("r_f", supuesto)
    assert "Bono M a 10 años" in texto
    assert "SF44071" in texto and "2026-09-24" in texto
    assert "diferencial soberano" in texto


@pytest.mark.parametrize(
    "nombre, programa, esperado",
    [
        ("g_ref", 0.2, "movido por ti; el programa decía 20.0%"),
        ("beta", 0.9, "movido por ti; el programa decía 0.90"),
        ("r_f", None, "puesto por ti"),
    ],
)
def test_un_supuesto_movido_dice_lo_que_decia_el_programa(nombre, programa, esperado):
    supuesto = {"valor": 0.1, "procedencia": {"fuente": "usuario", "programa": programa}}
    assert mv.procedencia(nombre, supuesto) == esperado


def test_lo_recalculado_con_los_supuestos_del_usuario_lo_dice():
    supuesto = {"valor": 0.1, "procedencia": {"fuente": "capm", "recalculado": True}}
    assert mv.procedencia("k_e", supuesto) == (
        "tasa libre más beta por prima (recalculado con tus supuestos)"
    )
```

- [ ] **Step 3: Comprobar que fallan**

Run: `uv run pytest tests/test_valoracion_supuestos.py tests/test_medidores_valoracion.py -q`
Expected: FAIL con `ImportError` (`MOVIBLES`, `aplicar`, `movidos`) y con los textos nuevos vacíos.

- [ ] **Step 4: Implementar en `valoracion/supuestos.py`**

1. En los imports, `from dataclasses import dataclass, fields, replace`.

2. En la docstring del módulo, sustituye el último párrafo («M no tiene forma de cambiar supuestos: … La función que aplica los cambios del usuario la añade N, que es quien la usa.») por:

```
M no tiene forma de cambiar supuestos: en Revisar candidatos no hay
deslizadores. `aplicar` es la de N: mueve lo que el usuario pide y recalcula lo
que depende de ello, sin volver a la red.
```

3. En `deducir`, añade el parámetro al final de la firma:

```python
    motivos: "dict | None" = None,
    procedencia_r_f: "dict | None" = None,
) -> Supuestos:
```

añade al final de su docstring:

```
    `procedencia_r_f` dice de dónde salió la tasa libre; por defecto, del
    Tesoro de EE. UU. a 10 años. Para una emisora en pesos es el Bono M (ver
    `analizador.divisas`).
```

y en el `return`, la línea de `r_f`:

```python
        r_f=Supuesto(r_f, procedencia_r_f or {"fuente": "tesoro_10", "serie": BONO_10}),
```

4. Al final del fichero:

```python
# Lo que el usuario puede mover. El coste del capital propio y el de capital no
# se mueven a mano: se recalculan de lo que sí se mueve, y moverlos sueltos
# dejaría en pantalla una tasa libre, una beta y una prima que no dan el coste
# que se usó.
MOVIBLES = ("r_f", "beta", "prima", "k_d", "t", "g_ref", "g_perpetuo", "roe_ref", "payout")
_HACEN_K_E = {"r_f", "beta", "prima"}
_HACEN_WACC = _HACEN_K_E | {"k_d", "t"}


def _numero_finito(nombre: str, valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre}: {valor!r} no es un número") from None
    if not math.isfinite(numero):
        raise ValueError(f"{nombre}: {valor!r} no es un número finito")
    return numero


def _recalculado(supuesto: Supuesto, valor: "float | None") -> Supuesto:
    return Supuesto(valor, {**supuesto.procedencia, "recalculado": True})


def aplicar(supuestos: Supuestos, cambios: dict) -> Supuestos:
    """Los supuestos con lo que el usuario movió, y lo que depende de ello recalculado.

    Lo movido lleva `{"fuente": "usuario", "programa": <lo que decía el
    programa>}`; lo recalculado conserva su fuente y gana `"recalculado": True`,
    para que la pantalla diga las dos cosas. **Lo movido no se guarda en ningún
    sitio**: lo que va al acta es siempre la valoración con los supuestos del
    programa, comparable entre actas.

    El coste de capital se recalcula con el peso de la deuda de su procedencia,
    que va redondeado a cuatro decimales: el error que eso mete es de
    diezmilésimas de punto. Un coste de la deuda «sin dato» es la tasa libre por
    definición, así que la sigue; uno medido, no.
    """
    if not cambios:
        return supuestos
    desconocidos = sorted(set(cambios) - set(MOVIBLES))
    if desconocidos:
        raise ValueError(f"No se pueden mover a mano: {', '.join(desconocidos)}")
    nuevos = {
        nombre: Supuesto(
            _numero_finito(nombre, valor),
            {"fuente": "usuario", "programa": getattr(supuestos, nombre).valor},
        )
        for nombre, valor in cambios.items()
    }
    s = replace(supuestos, **nuevos)
    if (
        "r_f" in cambios
        and "k_d" not in cambios
        and s.k_d.procedencia.get("fuente") == "sin_dato"
    ):
        s = replace(s, k_d=_recalculado(s.k_d, s.r_f.valor))
    if _HACEN_K_E & set(cambios):
        s = replace(s, k_e=_recalculado(s.k_e, s.r_f.valor + s.beta.valor * s.prima.valor))
    if _HACEN_WACC & set(cambios) and s.wacc.valor is not None:
        peso = s.wacc.procedencia.get("peso_deuda") or 0.0
        wacc = (1 - peso) * s.k_e.valor + peso * s.k_d.valor * (1 - s.t.valor)
        s = replace(s, wacc=_recalculado(s.wacc, wacc))
    return s


def movidos(supuestos: Supuestos) -> "tuple[str, ...]":
    """Los supuestos que movió el usuario, en el orden de `Supuestos`."""
    return tuple(
        campo.name
        for campo in fields(supuestos)
        if getattr(supuestos, campo.name).procedencia.get("fuente") == "usuario"
    )
```

- [ ] **Step 5: Implementar en `medidores_valoracion.py`**

En `procedencia`, añade a `textos` la tasa libre del Bono M:

```python
        ("r_f", "bono_m_10"): (
            f"Bono M a 10 años de Banxico ({p.get('serie')}), subasta del {p.get('fecha')}; "
            "sin restar el diferencial soberano"
        ),
```

y sustituye la última línea de la función (`return textos.get((nombre, fuente), "")`) por:

```python
    if fuente == "usuario":
        return _movido(nombre, p)
    texto = textos.get((nombre, fuente), "")
    if texto and p.get("recalculado") is True:
        texto += " (recalculado con tus supuestos)"
    return texto


def _movido(nombre: str, p: dict) -> str:
    """Un supuesto que movió el usuario, con lo que decía el programa."""
    programa = p.get("programa")
    if programa is None:
        # Una tasa libre que el programa no tenía: un Bono M sin token.
        return "puesto por ti"
    valor = _decimales(programa, 2) if nombre == "beta" else _pct(programa)
    return f"movido por ti; el programa decía {valor}"
```

- [ ] **Step 6: Comprobar que pasan**

Run: `uv run pytest tests/test_valoracion_supuestos.py tests/test_medidores_valoracion.py tests/test_valoracion_motor.py -q`
Expected: todos pasan.

- [ ] **Step 7: Commit**

```bash
git add valoracion/supuestos.py medidores_valoracion.py tests/test_valoracion_supuestos.py tests/test_medidores_valoracion.py
git commit -m "feat: la tasa libre dice de donde sale, y aplicar mueve supuestos y recalcula lo que depende

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: La tabla de sensibilidad del DCF

> **Ejecutada y superada** (7d6a530, dad574e). M no cambia en 40.000 combinaciones. La revisión: una casilla con coste de capital no positivo sale vacía, como una sin holgura; `datos_dcf` no mira la holgura de Gordon (la decide `valor_por_accion` casilla a casilla), y el puente del DCF (deuda, efectivo y acciones) vive en `motor.puente`, que usan `calcular` y la tabla de la Task 13. Manda el código vivo.

**Files:**
- Modify: `valoracion/dcf.py`
- Modify: `valoracion/motor.py`
- Test: `tests/test_valoracion_dcf.py`, `tests/test_valoracion_motor.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_valoracion_dcf.py`:

```python
# --- La sensibilidad ---------------------------------------------------------

from dataclasses import replace as _replace  # noqa: E402

from valoracion.criterio import HOLGURA_GORDON as _HOLGURA  # noqa: E402
from valoracion.dcf import Datos as _Datos  # noqa: E402
from valoracion.dcf import sensibilidad  # noqa: E402
from valoracion.dcf import valor_por_accion as _valor_por_accion  # noqa: E402

DATOS_SENSIBILIDAD = _Datos(
    ingresos=1000.0, margen=0.2, wacc=0.09, g_perpetuo=0.025,
    deuda=100.0, efectivo=50.0, acciones=10.0,
)


def test_la_casilla_central_es_el_valor_base():
    s = sensibilidad(DATOS_SENSIBILIDAD, 0.08)
    assert s.valores[2][2] == pytest.approx(_valor_por_accion(DATOS_SENSIBILIDAD, 0.08))
    assert s.waccs == pytest.approx((0.07, 0.08, 0.09, 0.10, 0.11))
    assert s.gs == pytest.approx((0.015, 0.02, 0.025, 0.03, 0.035))


def test_cada_casilla_es_el_dcf_con_ese_coste_y_ese_crecimiento_perpetuo():
    s = sensibilidad(DATOS_SENSIBILIDAD, 0.08)
    otro = _replace(DATOS_SENSIBILIDAD, wacc=0.11, g_perpetuo=0.015)
    assert s.valores[4][0] == pytest.approx(_valor_por_accion(otro, 0.08))


def test_sin_holgura_de_gordon_la_casilla_sale_vacia_y_no_recortada():
    s = sensibilidad(_replace(DATOS_SENSIBILIDAD, wacc=0.045), 0.08)
    vacias = 0
    for wacc, fila in zip(s.waccs, s.valores):
        for g, valor in zip(s.gs, fila):
            sin_holgura = wacc - g < _HOLGURA - 1e-12
            assert (valor is None) == sin_holgura
            vacias += sin_holgura
    assert vacias > 0


def test_mas_coste_de_capital_vale_menos():
    columna = [fila[2] for fila in sensibilidad(DATOS_SENSIBILIDAD, 0.08).valores]
    assert columna == sorted(columna, reverse=True)
```

Al final de `tests/test_valoracion_motor.py`:

```python
# --- Los datos del DCF, para la sensibilidad ---------------------------------

from tests.dobles_valoracion import ejercicio as _ejercicio  # noqa: E402
from tests.dobles_valoracion import fundamentos as _fundamentos  # noqa: E402
from tests.dobles_valoracion import perfil as _perfil  # noqa: E402
from valoracion.dcf import margen_fcff as _margen_fcff  # noqa: E402
from valoracion.dcf import valor_por_accion as _valor_por_accion  # noqa: E402
from valoracion.motor import calcular as _calcular  # noqa: E402
from valoracion.motor import datos_dcf  # noqa: E402
from valoracion.supuestos import deducir as _deducir  # noqa: E402


def test_los_datos_del_dcf_son_los_del_voto_de_flujos():
    f, p = _fundamentos(), _perfil()
    s = _deducir(f, p, 0.05, None, 0.25, 0.10)
    datos, motivo = datos_dcf(f, s, deuda=200.0, efectivo=50.0, acciones=10.0)
    assert motivo is None
    assert datos.margen == pytest.approx(_margen_fcff(f, 0.25))
    v = _calcular(f, p, s, None)
    assert v.valor.base == pytest.approx(_valor_por_accion(datos, s.g_ref.valor))


def test_los_datos_del_dcf_dicen_por_que_no_los_hay():
    f = _fundamentos(ejercicios=[_ejercicio(2026 - i, flujo_operativo=50.0) for i in range(4)])
    s = _deducir(f, _perfil(), 0.05, None, 0.25, 0.10)
    assert datos_dcf(f, s, deuda=200.0, efectivo=50.0, acciones=10.0) == (None, "quema_caja")
```

(si `pytest` no está ya importado en alguno de los dos ficheros, impórtalo arriba).

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_valoracion_dcf.py tests/test_valoracion_motor.py -q`
Expected: FAIL con `ImportError` (`sensibilidad`, `datos_dcf`).

- [ ] **Step 3: Implementar la sensibilidad en `valoracion/dcf.py`**

En los imports, `from dataclasses import dataclass, replace`. Al final del fichero:

```python
# La tabla que describe el spec de M (sección 5): el coste de capital ±2 puntos
# de uno en uno y el crecimiento perpetuo ±1 punto de medio en medio.
PASOS_WACC = (-0.02, -0.01, 0.0, 0.01, 0.02)
PASOS_G_PERPETUO = (-0.01, -0.005, 0.0, 0.005, 0.01)


@dataclass(frozen=True)
class Sensibilidad:
    """El valor base por acción en una rejilla: filas de coste de capital,
    columnas de crecimiento perpetuo. `None` donde no se cumple Gordon."""

    waccs: "tuple[float, ...]"
    gs: "tuple[float, ...]"
    valores: "tuple[tuple[float | None, ...], ...]"


def sensibilidad(datos: Datos, g: float) -> Sensibilidad:
    """Cuánto se mueve el valor base con el coste de capital y el crecimiento perpetuo.

    Las casillas sin holgura de Gordon salen vacías, no recortadas: recortar el
    coste de capital para que cuadre sería cambiar el escenario sin decirlo,
    que es la regla de `valor_empresa`.
    """
    waccs = tuple(datos.wacc + paso for paso in PASOS_WACC)
    gs = tuple(datos.g_perpetuo + paso for paso in PASOS_G_PERPETUO)
    valores = tuple(
        tuple(valor_por_accion(replace(datos, wacc=wacc, g_perpetuo=gp), g) for gp in gs)
        for wacc in waccs
    )
    return Sensibilidad(waccs, gs, valores)
```

- [ ] **Step 4: Sacar `datos_dcf` de `_lectura_flujos` en `valoracion/motor.py`**

Sustituye `_lectura_flujos` por estas dos funciones. La lógica es la misma; lo que cambia es que los datos se pueden pedir sin votar, para la sensibilidad de N2:

```python
def datos_dcf(fundamentos, supuestos, deuda, efectivo, acciones):
    """Lo que el DCF necesita, o el motivo por el que no se puede hacer.

    Devuelve `(Datos, None)` o `(None, motivo)`. Es la primera mitad de la
    lectura de flujos, aparte para que la tabla de sensibilidad use exactamente
    los datos con que se votó.
    """
    g_ref = supuestos.g_ref.valor
    if g_ref is None or not fundamentos.ultimo.ingresos > 0:
        return None, "sin_historia"
    margen = dcf.margen_fcff(fundamentos, supuestos.t.valor)
    if margen is None:
        # Igual que `epv_por_accion` separa `sin_beneficio_operativo` de
        # `sin_historia`: lo que falta es el dato y no la historia. LLY, COST,
        # NEE, VZ o PEP tienen cinco años de ingresos y no declaran el capex
        # nunca; decir «sin historia» de ellas sería falso y despistaría.
        con_ingresos = sum(1 for e in fundamentos.ejercicios if e.ingresos > 0)
        motivo = "sin_flujo_libre" if con_ingresos >= MIN_ANOS_HISTORIA else "sin_historia"
        return None, motivo
    if margen <= 0:
        # Quema caja: valorarla exigiría inventar cuándo deja de hacerlo.
        return None, "quema_caja"
    return (
        dcf.Datos(
            ingresos=fundamentos.ultimo.ingresos,
            margen=margen,
            wacc=supuestos.wacc.valor,
            g_perpetuo=supuestos.g_perpetuo.valor,
            deuda=deuda,
            efectivo=efectivo,
            acciones=acciones,
        ),
        None,
    )


def _lectura_flujos(fundamentos, supuestos, deuda, efectivo, acciones, precio):
    datos, motivo = datos_dcf(fundamentos, supuestos, deuda, efectivo, acciones)
    if datos is None:
        return Voto(NO_APLICA, motivo), None, None
    g_ref = supuestos.g_ref.valor
    base = dcf.valor_por_accion(datos, g_ref)
    if base is None:
        return Voto(NO_APLICA, "wacc_bajo_crecimiento"), None, None
    holgura = margen_voto(g_ref, MARGEN_MINIMO)
    valor = Escenarios(
        pesimista=dcf.valor_por_accion(datos, g_ref - holgura, datos.wacc + DELTA_WACC_ESCENARIOS),
        base=base,
        optimista=dcf.valor_por_accion(datos, g_ref + holgura, datos.wacc - DELTA_WACC_ESCENARIOS),
    )
    implicito = crecimiento_implicito(datos, precio)
    lectura = Lectura("crecimiento", implicito.valor, g_ref, holgura, implicito.fuera_de_limites)
    return voto_implicito(implicito, g_ref, holgura), valor, lectura
```

- [ ] **Step 5: Comprobar que pasan, y que M sigue igual**

Run: `uv run pytest tests/test_valoracion_dcf.py tests/test_valoracion_motor.py tests/test_valoracion_votos.py -q`
Expected: todos pasan; los de motor que ya existían, sin tocarlos.

- [ ] **Step 6: Commit**

```bash
git add valoracion/dcf.py valoracion/motor.py tests/test_valoracion_dcf.py tests/test_valoracion_motor.py
git commit -m "feat: la tabla de sensibilidad del DCF, con los mismos datos con que se vota

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: El panel de referencia en disco

> **Ejecutada y superada** (b14a578, b5b3fc6, 4417d7a). El ranking no cambia: mismas fichas, puestos y corrida, y los cuatro ficheros de siempre iguales byte a byte; el parquet reconstruye exactamente `Resultado.panel` y los z recalculados con `anadir_zscores` coinciden bit a bit. Con un universo vacío `build_panel` no trae el índice `(ticker, periodo)`, así que `Resultado.panel` es `None`. La revisión encontró que el `panel.parquet` de una corrida anterior sobrevivía junto a fichas nuevas (una corrida sin panel, o un fallo al escribirlo): `guardar` convierte el panel a bytes antes de escribir nada y borra el parquet viejo nada más crear la carpeta, de modo que cualquier fallo deja «sin panel» (que la Task 11 trata como ausente) y nunca uno ajeno a los candidatos. Manda el código vivo.

Para comparar un ticker con sus pares hace falta el panel del S&P 500. `ranking/run.guardar` lo escribe junto a las fichas, así que la referencia es siempre la de la última vez que se generaron candidatos.

**Files:**
- Modify: `fundamentals/run.py`
- Modify: `ranking/run.py`
- Test: `tests/test_fundamentals_run.py`, `tests/test_ranking_run.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_fundamentals_run.py`:

```python
def test_el_minimo_de_sesiones_se_puede_bajar_para_paneles_cortos():
    """yfinance da cinco trimestres: la ventana de precios es de poco más de un
    año, y el mínimo por defecto del cargador (252 sesiones) la descartaría."""
    panel = _panel_de_cierres()
    with patch("research.loader.load_ohlcv", return_value=(panel, None)) as carga:
        _precios_por_periodo("AAA", pd.DatetimeIndex([pd.Timestamp("2025-03-31")]), min_obs=1)
    assert carga.call_args.kwargs["min_obs"] == 1
    with patch("research.loader.load_ohlcv", return_value=(panel, None)) as carga:
        _precios_por_periodo("AAA", pd.DatetimeIndex([pd.Timestamp("2025-03-31")]))
    assert carga.call_args.kwargs["min_obs"] == 252


def test_anadir_zscores_es_publica():
    from fundamentals.run import anadir_zscores

    assert callable(anadir_zscores)
```

Al final de `tests/test_ranking_run.py`:

```python
# --- El panel de referencia del Analizador ----------------------------------


def test_el_resultado_lleva_el_panel_crudo_con_su_sector(sin_red):
    resultado = construir_ranking(con_llm=False, n=5)
    panel = resultado.panel
    # Sin los z: se recalculan al insertar una empresa que no estaba.
    assert not any(str(c).startswith("z_") for c in panel.columns)
    assert {"trimestre", "sector_gics", *TODOS_LOS_KPIS} <= set(panel.columns)
    assert list(panel.index.names) == ["ticker", "periodo"]
    assert panel.xs("TE0", level="ticker")["sector_gics"].unique().tolist() == ["Tech"]


def test_guardar_escribe_el_panel_en_parquet(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)
    leido = pd.read_parquet(tmp_path / "panel.parquet")
    assert len(leido) == len(resultado.panel)
    assert set(leido.columns) == {"ticker", "periodo", *resultado.panel.columns}
    fila = leido.iloc[0]
    original = resultado.panel.loc[(fila["ticker"], pd.Timestamp(fila["periodo"]))]
    assert fila["margen_bruto"] == original["margen_bruto"]
    assert fila["sector_gics"] == original["sector_gics"]


def test_sin_panel_no_se_escribe_parquet(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    resultado.panel = None
    guardar(resultado, tmp_path)
    assert not (tmp_path / "panel.parquet").exists()
    assert (tmp_path / "fichas.json").exists()
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_fundamentals_run.py tests/test_ranking_run.py -q`
Expected: FAIL con `TypeError` (`min_obs`), `ImportError` (`anadir_zscores`) y `AttributeError` (`panel`).

- [ ] **Step 3: Implementar en `fundamentals/run.py`**

1. `_precios_por_periodo` gana un parámetro al final de su firma:

```python
def _precios_por_periodo(
    ticker: str,
    periodos: pd.DatetimeIndex,
    cierres_anuales: pd.DatetimeIndex | None = None,
    min_obs: int = 252,
) -> tuple[pd.Series, bool]:
```

un párrafo al final de su docstring:

```
    `min_obs` pasa al cargador. El de siempre (un año de sesiones) sirve al
    panel de la SEC, de doce trimestres; el Analizador lo baja a 1, porque con
    los cinco trimestres de yfinance la ventana es de poco más de un año y el
    cargador la descartaría entera.
```

y la llamada a `load_ohlcv` lo pasa:

```python
    panel, cobertura_precios = load_ohlcv(
        [ticker],
        start=(publicacion.min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        end=(publicacion.max() + pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
        min_obs=min_obs,
    )
```

2. Renombra `_anadir_zscores` a `anadir_zscores` (la definición y su única llamada, en `build_panel`), y añade al principio de su docstring:

```
    Pública porque el Analizador (`analizador/referencia.py`) la aplica al
    panel con una empresa insertada: los z tienen que salir de la misma función
    que los del ranking.
```

- [ ] **Step 4: Implementar en `ranking/run.py`**

1. `Resultado` gana un campo al final, con valor por defecto para no romper a quien lo construye a mano:

```python
    # El panel crudo, para la referencia sectorial del Analizador: los KPIs sin
    # sus z (se recalculan al insertar una empresa que no estaba), el trimestre
    # natural y el sector de cada fila.
    panel: "pd.DataFrame | None" = None
```

2. En `construir_ranking`, antes del `return`:

```python
    crudo = panel.drop(columns=[c for c in panel.columns if str(c).startswith("z_")])
    crudo["sector_gics"] = sectores.reindex(crudo.index.get_level_values("ticker")).to_numpy()
```

y en el `return Resultado(...)`, `panel=crudo,` como último argumento.

3. En `guardar`, al final:

```python
    if resultado.panel is not None and not resultado.panel.empty:
        # Para el Analizador: la referencia sectorial es la de la última vez que
        # se generaron candidatos, y se escribe con ellos para que no se separen.
        resultado.panel.reset_index().to_parquet(destino / "panel.parquet", index=False)
```

y en su docstring, «Write the four outputs» pasa a «Write the four outputs, and the panel the Analizador compares against».

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_fundamentals_run.py tests/test_ranking_run.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add fundamentals/run.py ranking/run.py tests/test_fundamentals_run.py tests/test_ranking_run.py
git commit -m "feat: generar candidatos deja el panel de referencia en salidas/panel.parquet

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: La ficha frente al sector

> **Ejecutada y superada** (b39842f, e61b030, 83fc7d7 y un ajuste). La ficha, el compuesto, el puesto global y la exclusión coinciden exactamente con `construir_ranking` en 468 tickers de 12 paneles sintéticos (NaN, historia corta, sectores de dos, sector `None`), y sacar y reinsertar un ticker da lo mismo en 456 casos, también los que una guarda deja fuera. El test de la ficha idéntica baraja el panel: sin eso, quitar el `sort_index()` no lo notaba nadie. La revisión encontró que `cargar_panel` lanzaba con un fichero alterado (pyarrow lanza su `ArrowException` base, `KeyError` o `TypeError`, no sólo `ValueError`/`OSError`): ahora todo cae en un `except Exception`, porque el panel se regenera gratis; además se queda sólo con sus columnas y trata como ausente un panel vacío o con filas repetidas, y el `trimestre` insertado va como texto. El puesto es el global y `desplazo_a` va vacío: la ficha es idéntica a la de candidatos salvo en eso. Cuesta ~0,3 s por ticker con el panel real. Manda el código vivo.

**Files:**
- Create: `analizador/referencia.py`
- Test: `tests/test_analizador_referencia.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_referencia.py`:

```python
"""La ficha de un ticker frente a su sector, con las funciones del ranking."""

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from analizador.referencia import cargar_panel, frente_al_sector
from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import anadir_zscores
from ranking.run import construir_ranking

SECTORES = {"Information Technology": 6, "Health Care": 6, "Utilities": 5}
TRIMESTRES = ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]


def panel_crudo(semilla: int = 3) -> pd.DataFrame:
    """Un panel con la forma de `salidas/panel.parquet`: KPIs crudos, trimestre y sector."""
    generador = np.random.default_rng(semilla)
    filas, indice = [], []
    for sector, cuantas in SECTORES.items():
        for numero in range(cuantas):
            ticker = f"{sector[:2].upper()}{numero}"
            for trimestre in TRIMESTRES:
                fila = dict(zip(TODOS_LOS_KPIS, generador.normal(size=len(TODOS_LOS_KPIS))))
                fila["trimestre"] = trimestre
                fila["sector_gics"] = sector
                filas.append(fila)
                indice.append((ticker, pd.Period(trimestre, freq="Q").end_time.normalize()))
    return pd.DataFrame(
        filas, index=pd.MultiIndex.from_tuples(indice, names=["ticker", "periodo"])
    )


def _ranking(crudo):
    """El ranking de siempre sobre el mismo panel, con los z que daría `build_panel`.

    Ordenado antes de los z, como hace `build_panel`: el orden de las filas fija
    el de las sumas, y sin él los z podrían diferir en la última cifra decimal.
    """
    crudo = crudo.sort_index()
    metadatos = crudo["sector_gics"].groupby(level="ticker").last().to_frame("sector_gics")
    con_z = anadir_zscores(crudo.drop(columns="sector_gics"), metadatos)
    with patch("ranking.run.build_panel", return_value=(con_z, metadatos, None)):
        return construir_ranking(con_llm=False, con_valoracion=False, n=5)


def test_un_ticker_del_panel_da_exactamente_su_ficha_de_candidatos():
    crudo = panel_crudo()
    candidata = _ranking(crudo).fichas[0]
    ref = frente_al_sector(candidata["ticker"], crudo)
    for clave in ("sector_gics", "pilares", "destacados", "flojos", "cobertura"):
        assert ref.ficha[clave] == candidata[clave]
    assert ref.compuesto == pytest.approx(candidata["compuesto"])
    assert ref.puesto == candidata["puesto"] == 1
    assert ref.en_panel and ref.exclusion is None


def test_el_puesto_es_el_orden_global_de_las_que_pasan_las_guardas():
    crudo = panel_crudo()
    tabla = _ranking(crudo).tabla
    orden = sorted(tabla.index, key=lambda t: (-tabla.loc[t, "compuesto"], t))
    for ticker in orden[:3] + orden[-2:]:
        ref = frente_al_sector(ticker, crudo)
        assert ref.puesto == orden.index(ticker) + 1
        assert ref.supervivientes == len(tabla)


def _sin(crudo, ticker):
    propias = crudo.xs(ticker, level="ticker").drop(columns="sector_gics")
    return crudo.drop(index=ticker, level="ticker"), propias


def test_insertar_un_ticker_da_lo_mismo_que_si_hubiera_estado_desde_el_principio():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    dentro = frente_al_sector("HE2", crudo)
    insertado = frente_al_sector("HE2", sin_el, sector="Health Care", propias=propias)
    assert insertado.ficha == dentro.ficha
    assert (insertado.puesto, insertado.compuesto) == (dentro.puesto, dentro.compuesto)
    assert dentro.en_panel and not insertado.en_panel


def test_las_filas_posteriores_al_panel_no_entran():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    extra = propias.iloc[[-1]].copy()
    extra.index = pd.DatetimeIndex([pd.Timestamp("2026-09-30")])
    extra["trimestre"] = "2026Q3"
    con_extra = pd.concat([propias, extra])
    assert (
        frente_al_sector("HE2", sin_el, "Health Care", con_extra).ficha
        == frente_al_sector("HE2", sin_el, "Health Care", propias).ficha
    )


def test_una_guarda_que_lo_dejaria_fuera_se_dice_y_no_hay_puesto():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    ref = frente_al_sector("HE2", sin_el, "Health Care", propias.iloc[-2:])
    assert ref.exclusion == "historia_corta"
    assert ref.puesto is None and ref.compuesto is None
    assert ref.ficha["puesto"] is None and ref.ficha["compuesto"] is None


def test_sin_sector_o_sin_filas_no_hay_referencia():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    assert frente_al_sector("HE2", sin_el, None, propias) is None
    assert frente_al_sector("HE2", sin_el, "Health Care", None) is None
    assert frente_al_sector("HE2", sin_el, "Health Care", propias.iloc[0:0]) is None


def test_cargar_panel_lee_lo_que_escribe_guardar(tmp_path):
    crudo = panel_crudo()
    ruta = tmp_path / "panel.parquet"
    crudo.reset_index().to_parquet(ruta, index=False)
    panel, fecha = cargar_panel(ruta)
    assert fecha == date.today()
    assert frente_al_sector("IN0", panel).ficha == frente_al_sector("IN0", crudo).ficha


def test_sin_panel_en_disco_no_hay_panel(tmp_path):
    assert cargar_panel(tmp_path / "no_existe.parquet") == (None, None)


def test_un_panel_ilegible_o_sin_una_columna_es_como_si_no_hubiera(tmp_path):
    roto = tmp_path / "roto.parquet"
    roto.write_bytes(b"esto no es parquet")
    assert cargar_panel(roto) == (None, None)
    cojo = tmp_path / "cojo.parquet"
    panel_crudo().drop(columns="sector_gics").reset_index().to_parquet(cojo, index=False)
    assert cargar_panel(cojo) == (None, None)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_referencia.py -q`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

`analizador/referencia.py`:

```python
"""La ficha de un ticker frente a sus pares del S&P 500.

El panel de referencia es el que `ranking.run.guardar` deja en
`salidas/panel.parquet` cada vez que se generan candidatos: los KPIs crudos, el
trimestre natural y el sector de cada fila. La referencia es la de la última
vez que se generaron candidatos, y su fecha se enseña.

**Si el ticker está en el panel**, su ficha sale idéntica a la de Revisar
candidatos. **Si no está**, sus filas se insertan en su sector, trimestre a
trimestre, y se le aplican las mismas funciones que al ranking: el z por sector
con el mismo tope, la media de la ventana, los pilares, las guardas y la nota
compuesta. Insertarla mueve un poco la media y la dispersión de su sector, y
con ellas los z de sus pares: es lo que habría pasado si hubiera estado en el
panel desde el principio, que es justo la comparación que se busca.

El puesto es el **global**: el orden por nota compuesta entre las que pasan las
guardas, sin el tope por sector. Es el único que existe para un ticker que no
compite por las quince plazas, y para el primero de los candidatos coincide con
su puesto.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from fundamentals.kpis import TODOS_LOS_KPIS
from fundamentals.run import anadir_zscores
from ranking.criterio import TRIMESTRES_VENTANA
from ranking.fichas import ficha_numerica
from ranking.score import (
    aplicar_guardas,
    compuesto,
    marcar_sin_pares,
    media_ventana,
    puntuaciones_por_pilar,
)

RUTA_PANEL = Path(__file__).resolve().parent.parent / "salidas" / "panel.parquet"
_COLUMNAS = ("ticker", "periodo", "trimestre", "sector_gics", *TODOS_LOS_KPIS)


@dataclass(frozen=True)
class Referencia:
    """La ficha frente al sector, con la forma de `ranking.fichas.ficha_numerica`.

    `puesto` y `compuesto` son None si una guarda lo deja fuera, y `exclusion`
    dice cuál. `supervivientes` es cuántas pasan las guardas, ésta incluida si
    pasa: el «de cuántas» del puesto.
    """

    ficha: dict
    compuesto: "float | None"
    puesto: "int | None"
    supervivientes: int
    exclusion: "str | None"
    en_panel: bool


def cargar_panel(ruta: "Path | None" = None) -> "tuple[pd.DataFrame | None, date | None]":
    """El panel de referencia y la fecha en que se escribió, o `(None, None)`.

    Un fichero que no se puede leer, o al que le falta una columna, se trata
    como ausente: la pantalla ofrece reconstruirlo, que es gratis. No es
    historial que se pierda, al revés que un archivo de la IA.
    """
    ruta = Path(ruta or RUTA_PANEL)
    if not ruta.exists():
        return None, None
    try:
        crudo = pd.read_parquet(ruta)
    except (OSError, ValueError, ImportError):
        # pyarrow lanza `ArrowInvalid`, que es un `ValueError`, con un fichero
        # que no es parquet, y `ArrowIOError`, que es un `OSError`, al leerlo.
        return None, None
    if not set(_COLUMNAS) <= set(crudo.columns):
        return None, None
    crudo["periodo"] = pd.to_datetime(crudo["periodo"])
    panel = crudo.set_index(["ticker", "periodo"]).sort_index()
    return panel, date.fromtimestamp(ruta.stat().st_mtime)


def frente_al_sector(
    ticker: str,
    panel: pd.DataFrame,
    sector: "str | None" = None,
    propias: "pd.DataFrame | None" = None,
) -> "Referencia | None":
    """La ficha de `ticker` frente a su sector, o `None` si no hay con qué hacerla.

    Si el ticker no está en el panel hacen falta su `sector` GICS y `propias`:
    sus filas de KPIs, indexadas por fecha de cierre y con la columna
    `trimestre`, como las da `analizador.kpis`. Las posteriores al último
    trimestre del panel no entran: en ese trimestre no tiene pares, y su z
    saldría vacía y le quitaría un trimestre de la ventana.
    """
    trimestre_max = str(panel["trimestre"].max())
    en_panel = ticker in panel.index.get_level_values("ticker")
    if en_panel:
        # Ordenado como lo deja `build_panel` antes de los z: el orden de las
        # filas fija el de las sumas, y con otro los z diferirían en la última
        # cifra de los del ranking.
        completo = panel.sort_index()
    else:
        if sector is None or propias is None:
            return None
        propias = propias[propias["trimestre"].astype(str) <= trimestre_max]
        if propias.empty:
            return None
        filas = propias.reindex(columns=[*TODOS_LOS_KPIS, "trimestre"]).copy()
        filas["sector_gics"] = sector
        filas.index = pd.MultiIndex.from_arrays(
            [[ticker] * len(filas), pd.DatetimeIndex(propias.index)],
            names=["ticker", "periodo"],
        )
        completo = pd.concat([panel, filas]).sort_index()

    # Las mismas funciones y en el mismo orden que `ranking.run.construir_ranking`.
    sectores = completo["sector_gics"].groupby(level="ticker").last()
    con_z = anadir_zscores(completo.drop(columns="sector_gics"), sectores.to_frame("sector_gics"))
    z, valores, historial = media_ventana(con_z, n=TRIMESTRES_VENTANA)
    pilares, conteo = puntuaciones_por_pilar(z)
    motivos = aplicar_guardas(pilares, conteo, historial, trimestre_max)
    puntos = compuesto(pilares, motivos, sectores)
    motivos = marcar_sin_pares(motivos, puntos, sectores)

    validos = puntos.dropna()
    orden = sorted(validos.index, key=lambda t: (-validos[t], t))
    puesto = orden.index(ticker) + 1 if ticker in validos.index else None
    nota = float(validos[ticker]) if ticker in validos.index else None
    ficha = ficha_numerica(
        ticker=ticker,
        sector=sectores[ticker],
        puesto=puesto or 0,
        compuesto=float("nan") if nota is None else nota,
        pilares=pilares.loc[ticker],
        conteo=conteo.loc[ticker],
        z=z.loc[ticker],
        valores=valores.loc[ticker],
        desplazo_a=[],
    )
    # `ficha_numerica` exige un puesto y una nota; fuera por una guarda no hay
    # ninguno de los dos, y un 0 o un NaN se leerían como una cifra.
    ficha = {**ficha, "puesto": puesto, "compuesto": nota}
    exclusion = motivos.get(ticker)
    return Referencia(
        ficha=ficha,
        compuesto=nota,
        puesto=puesto,
        supervivientes=len(validos),
        exclusion=None if pd.isna(exclusion) else str(exclusion),
        en_panel=en_panel,
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_referencia.py -q`
Expected: todos pasan. Si `test_un_ticker_del_panel_da_exactamente_su_ficha_de_candidatos` falla por una diferencia de coma flotante en los `z` de `destacados`, **no** lo relajes a `approx` sin mirar por qué: los dos caminos aplican las mismas funciones al mismo panel ordenado igual (por eso `frente_al_sector` ordena), y una diferencia quiere decir que no es así.

- [ ] **Step 5: Commit**

```bash
git add analizador/referencia.py tests/test_analizador_referencia.py
git commit -m "feat: la ficha de cualquier ticker frente a su sector, con las funciones del ranking

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Las filas de KPIs de un ticker que no está en el panel

> **Ejecutada y superada** (3e301bd, 7a18889, 3432130 y un ajuste). `kpis_sec` da filas idénticas a las de ese ticker en un `build_panel` de varios (nada antes de los z depende del universo), y una empresa de la SEC sin sector conserva sus filas. En vivo, sin errores de factor: TSM, SHEL.L (peniques), WALMEX.MX, RY, NVO y TM/7203.T dan PER, márgenes y P/VL del orden de los de Yahoo, y yfinance da las ADR en base ADR (recuento, BPA y precio). La revisión cambió tres cosas: sin precio, la vía de la SEC dice `sin_precio` (con un universo de uno `build_panel` aborta) y no `sin_estados`; `kpis_yf` devuelve `(filas, motivo)` y dice `sin_precio` si no hay ni un precio en dólares, en vez de unas filas sin valoración que saldrían «pilar sin datos»; y los cierres de ejercicio son sólo los años con ancla (el anual de RY y TM trae columnas de doce meses móviles que cotizaban con 65 días en vez de 45). Los plazos de 45/65 días son los de la SEC y fuera de ella una aproximación. Manda el código vivo.

**Files:**
- Create: `analizador/kpis.py`
- Test: `tests/test_analizador_kpis.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_kpis.py`:

```python
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import kpis
from fundamentals.concepts import LINEAS
from fundamentals.fetch import CorridaAbortada
from fundamentals.kpis import TODOS_LOS_KPIS

NAN = float("nan")


def _panel_de(ticker):
    indice = pd.MultiIndex.from_tuples(
        [(ticker, pd.Timestamp("2026-03-31")), (ticker, pd.Timestamp("2026-06-30"))],
        names=["ticker", "periodo"],
    )
    panel = pd.DataFrame(1.0, index=indice, columns=list(TODOS_LOS_KPIS))
    panel["trimestre"] = ["2026Q1", "2026Q2"]
    return panel


def test_una_empresa_de_la_sec_pasa_por_el_mismo_motor_que_el_ranking():
    with patch.object(kpis, "build_panel", return_value=(_panel_de("VEEV"), None, None)) as motor:
        filas, motivo = kpis.kpis_sec("VEEV")
    motor.assert_called_once_with(["VEEV"])
    assert motivo == "ok"
    assert list(filas.index) == [pd.Timestamp("2026-03-31"), pd.Timestamp("2026-06-30")]
    assert "trimestre" in filas.columns


def test_si_la_sec_no_responde_no_hay_filas():
    with patch.object(kpis, "build_panel", side_effect=CorridaAbortada("sin_fuente", "x", None)):
        assert kpis.kpis_sec("VEEV") == (None, "sin_estados")


def test_un_panel_vacio_no_son_filas():
    vacio = pd.DataFrame(columns=[*TODOS_LOS_KPIS, "trimestre"])
    vacio.index = pd.MultiIndex.from_arrays([[], []], names=["ticker", "periodo"])
    with patch.object(kpis, "build_panel", return_value=(vacio, None, None)):
        assert kpis.kpis_sec("VEEV") == (None, "sin_estados")


def _trimestrales():
    fechas = pd.date_range("2025-03-31", periods=5, freq="QE")
    lineas = pd.DataFrame(NAN, index=fechas, columns=list(LINEAS))
    lineas["bpa_diluido"] = 1.0
    lineas["acciones_diluidas"] = 10.0
    return lineas


def _precios(por_simbolo):
    def precios_por_periodo(simbolo, periodos, cierres, min_obs):
        assert min_obs == 1
        return pd.Series(por_simbolo[simbolo], index=periodos), False

    return precios_por_periodo


def test_el_precio_va_en_la_moneda_de_los_estados_al_tipo_de_cada_fecha():
    # TSM cotiza en dólares y presenta en TWD: 10 dólares a 32 TWD por dólar.
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"TSM": 10.0, "USDTWD=X": 32.0})):
        filas = kpis.kpis_yf("TSM", trimestrales, pd.DataFrame(), "USD", "TWD", 0.031)
    # PER = precio en TWD / BPA de doce meses en TWD = 320 / 4.
    assert filas["per"].iloc[-1] == pytest.approx(320.0 / 4.0)


def test_un_precio_en_peniques_se_cambia_con_la_libra_y_se_divide_por_cien():
    # SHEL.L cotiza en peniques y presenta en dólares: el par es GBPUSD=X, y el
    # precio en dólares es el de peniques por el tipo y entre cien.
    trimestrales = _trimestrales()
    dobles = _precios({"SHEL.L": 3900.0, "GBPUSD=X": 1.3})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        filas = kpis.kpis_yf("SHEL.L", trimestrales, pd.DataFrame(), "GBp", "USD", 1.0)
    assert filas["per"].iloc[-1] == pytest.approx(3900.0 * 1.3 / 100 / 4.0)


def test_peniques_frente_a_libras_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    dobles = _precios({"X.L": 400.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles) as precios:
        filas = kpis.kpis_yf("X.L", trimestrales, pd.DataFrame(), "GBp", "GBP", 1.32)
    assert precios.call_count == 1
    assert filas["per"].iloc[-1] == pytest.approx(4.0 / 4.0)


def test_los_suelos_de_los_kpis_se_aplican_en_dolares():
    # Unos ingresos de 1.500 millones de pesos son 81 millones de dólares: por
    # debajo del suelo de 100 millones de `fundamentals.kpis`, como lo estaría
    # una empresa de EE. UU. de ese tamaño en el panel de referencia. En pesos
    # el suelo no actuaría, y la comparación con los pares no sería la misma.
    trimestrales = _trimestrales()
    trimestrales["ingresos"] = 1.5e9
    trimestrales["beneficio_operativo"] = 3.0e8
    dobles = _precios({"PEQ.MX": 10.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        en_dolares = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        sin_convertir = kpis.kpis_yf("PEQ.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert en_dolares["margen_operativo"].isna().all()
    assert sin_convertir["margen_operativo"].iloc[-1] == pytest.approx(0.2)


def test_el_tipo_a_dolares_no_cambia_ningun_cociente():
    trimestrales = _trimestrales()
    dobles = _precios({"X.MX": 48.0})
    with patch.object(kpis, "_precios_por_periodo", side_effect=dobles):
        a = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
        b = kpis.kpis_yf("X.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 1.0)
    assert a["per"].iloc[-1] == pytest.approx(b["per"].iloc[-1])


def test_en_la_misma_moneda_no_se_baja_ningun_tipo_de_cambio():
    trimestrales = _trimestrales()
    with patch.object(kpis, "_precios_por_periodo", side_effect=_precios({"WALMEX.MX": 48.0})) as precios:
        filas = kpis.kpis_yf("WALMEX.MX", trimestrales, pd.DataFrame(), "MXN", "MXN", 0.054)
    assert precios.call_count == 1
    assert filas["per"].iloc[-1] == pytest.approx(48.0 / 4.0)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_kpis.py -q`
Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar**

`analizador/kpis.py`:

```python
"""Las filas de KPIs de un ticker que no está en el panel de referencia.

Una empresa de la SEC pasa por el mismo motor que el ranking: `build_panel` con
un universo de una. Las demás salen de yfinance (`analizador.lineas_yf`), con el
precio de cada trimestre en la moneda de sus estados.
"""

import pandas as pd

from analizador.lineas_yf import kpis_trimestrales
from fundamentals.fetch import CorridaAbortada
from valoracion.mercado import SUBUNIDADES

# Privada y aun así importada: es el precio del día en que se publicaron las
# cuentas de cada trimestre, con el plazo del 10-Q o del 10-K. Una segunda
# copia aquí sería el look-ahead que el estudio D encontró siete veces.
from fundamentals.run import _precios_por_periodo, build_panel


def kpis_sec(ticker: str) -> "tuple[pd.DataFrame | None, str]":
    """Las filas del panel de la SEC de un ticker, indexadas por fecha de cierre."""
    try:
        panel, _, _ = build_panel([ticker])
    except CorridaAbortada:
        # Con un solo ticker, abortar es que la fuente no responde o rechaza la
        # identidad: no es la empresa, pero para esta ficha el efecto es el mismo.
        return None, "sin_estados"
    if panel.empty or ticker not in panel.index.get_level_values("ticker"):
        return None, "sin_estados"
    return panel.xs(ticker, level="ticker"), "ok"


def kpis_yf(
    ticker: str,
    trimestrales: pd.DataFrame,
    anuales: pd.DataFrame,
    moneda_precio: str,
    moneda_estados: str,
    tipo_a_usd: float,
) -> pd.DataFrame:
    """Los KPIs trimestrales de un ticker de yfinance.

    El precio de cada trimestre es el del día en que sus cuentas se hicieron
    públicas, con los plazos de `fundamentals.run`. Si cotiza en otra moneda
    que la de sus estados (TSM: dólares y TWD), se convierte al tipo de cambio
    de ese mismo día, que se baja con el mismo cargador: un tipo de hoy para
    precios de hace un año movería los múltiplos con la divisa, no con la
    empresa. `min_obs=1` porque con cinco trimestres la ventana de precios es
    de poco más de un año, y el mínimo del cargador la descartaría.

    Después, las líneas y el precio se pasan a dólares con **un único** tipo,
    `tipo_a_usd` (dólares por unidad de la moneda de los estados, el último
    cierre). Los suelos económicos de `fundamentals.kpis` están pensados en
    dólares --1e8 de partida de balance y 1e6 de gasto financiero--, y en wones
    el del gasto financiero valdría 745 $: una pequeña de la BMV o de KOSDAQ
    sacaría márgenes y coberturas que el panel de referencia le taparía a una
    empresa de EE. UU. de su tamaño. Un tipo constante no cambia ningún cociente
    ni ningún crecimiento; con el de cada fecha, la divisa entraría en el
    crecimiento interanual.
    """
    cierres = pd.DatetimeIndex(anuales.index)
    precios, _ = _precios_por_periodo(ticker, trimestrales.index, cierres, min_obs=1)
    # Una cotización en subunidades (Londres, en peniques) se cambia con su
    # moneda principal y se divide por la escala: yfinance pasa el par a
    # mayúsculas, y «GBpUSD=X» sería el tipo de la libra, cien veces mayor.
    base, escala = SUBUNIDADES.get(moneda_precio, (moneda_precio, 1))
    if base != moneda_estados:
        par = f"{base}{moneda_estados}=X"
        tipos, _ = _precios_por_periodo(par, trimestrales.index, cierres, min_obs=1)
        precios = precios * tipos
    dinero = [linea for linea in trimestrales.columns if linea != "acciones_diluidas"]
    en_dolares = trimestrales.copy()
    en_dolares[dinero] = en_dolares[dinero] * tipo_a_usd
    return kpis_trimestrales(en_dolares, precios / escala * tipo_a_usd)
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_kpis.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/kpis.py tests/test_analizador_kpis.py
git commit -m "feat: las filas de KPIs de un ticker fuera del panel, de la SEC o de yfinance

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: La valoración de cualquier ticker

> **Ejecutada y superada** (901a692, 2b40841, cba4a9c, f40051d). Para MU, AAPL, JPM y KO, `valorar(entradas(...))` da exactamente lo mismo que `valoracion.motor.valorar` (M no cambia). En vivo, sin errores de factor: TSM (TWD→USD), AMX (ADR en USD, valorada en MXN contra el IPC), WALMEX.MX (Bono M), SHEL.L (peniques, estados en USD), RY y RY.TO (CAD→USD) y NVO (DKK→USD). Las revisiones cambiaron la beta con par: el **semanal** de los pares `=X` de Yahoo trae velas corruptas (CADUSD=X marcaba 0,911 entre dos semanas de 0,70: RY.TO salía con beta 0,27 en vez de 0,46), y su **diario** no trae el cierre del día sino una foto a medianoche de Londres (un día por detrás: AMX daba 0,90 en vez de 0,79). Se usa el semanal de Yahoo y el diario sólo para descartar las semanas que se apartan más de un 5 % (`mercado.tipo_sin_picos`); en USDTRY, USDARS o el USDMXN de marzo de 2020 no descarta ninguna buena, y a NPN.JO le quita seis picos de ZARUSD. Además, la tasa libre puesta a mano sin Bono M pasa por las mismas guardas que `aplicar` (`supuestos.exigir_costes_positivos`), juzgadas sobre el resultado. Manda el código vivo.

`entradas` sale a la red una vez y deja todo en la moneda de la valoración; `valorar` es puro, y es lo que llamarán los deslizadores de N2 sin volver a pedir nada.

Una valoración que no se calcula puede terminar ahora con un motivo que M no tenía: `sin_bono_m`, una emisora en pesos sin el Bono M de Banxico, normalmente por no tener token. `sin_tasa_libre` no sirve: su etiqueta culpa a Yahoo, y aquí sería falso. Un tipo de cambio que no llega se dice `sin_red`, que es lo que devuelve `mercado.tipo_de_cambio` desde la revisión de la Task 3: un par que Yahoo no conoce no se distingue de un fallo de red.

**Files:**
- Create: `analizador/valorar.py`
- Modify: `valoracion/votos.py` (`MOTIVOS`)
- Modify: `medidores_valoracion.py` (`MOTIVO`)
- Modify: `valoracion/mercado.py` (`beta` con el precio convertido)
- Test: `tests/test_analizador_valorar.py`, `tests/test_medidores_valoracion.py`, `tests/test_valoracion_mercado.py`, `tests/test_valoracion_mercado_red.py`

**La beta de un precio en otra moneda que la de la valoración.** AMX cotiza en dólares y presenta en pesos: se valora en pesos y su beta va contra el IPC. Regresar el precio en dólares contra un índice en pesos mezcla dos monedas, la misma clase de error que la docstring de `Perfil` cuenta con WALMEX contra el S&P 500. Medido el 2026-10-19 a 104 semanas: AMX (en dólares) da 1,036 contra el IPC y AMXB.MX (en pesos) 0,834; FMX 0,841 frente a FEMSAUBD.MX 0,644. Son unos 0,2 de beta, un punto de coste del capital. Por eso `mercado.beta` gana un par de divisas con el que pasar el precio a la moneda del índice antes de regresar.

**La prima por riesgo país.** `Divisa.a_dict` dice si los estados se convirtieron (`estados_convertidos`), que no es lo mismo: TEVA o NPN presentan en dólares y se valoran sin prima por riesgo país igual que TSM. `valorar` añade `sin_prima_pais`, que es verdadero cuando se valora en dólares una empresa de fuera de EE. UU.; en pesos, el Bono M ya lleva el riesgo de México.

- [ ] **Step 1: Escribir los tests**

En `tests/test_medidores_valoracion.py`, añade dos casos a la tabla de `test_cada_motivo_dice_de_que_se_trata`:

```python
        ("sin_bono_m", "Bono M"),
```

y los dos motivos a `_MOTIVOS_DE_UNA_FALLIDA`:

```python
_MOTIVOS_DE_UNA_FALLIDA = (
    "sin_red", "sin_precio", "sin_tasa_libre", "sin_estados", "sin_historia", "error_interno",
    "sin_bono_m",
)
```

`tests/test_analizador_valorar.py`:

```python
"""La valoración de cualquier ticker, con la red sustituida."""

import json
from dataclasses import replace
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import valorar as v
from analizador.divisas import Divisa
from analizador.resolver import Resuelto
from tests.dobles_valoracion import fundamentos, perfil
from valoracion.mercado import Beta

USD = Divisa("USD", "USD", "USD", 1.0, 1.0, "^GSPC")
MXN = Divisa("MXN", "MXN", "MXN", 1.0, 1.0, "^MXX")


def _entradas(**sobre):
    valores = dict(
        ticker="TST",
        fundamentos=fundamentos(),
        perfil=perfil(),
        divisa=USD,
        r_f=0.05,
        procedencia_r_f={"fuente": "tesoro_10", "serie": "^TNX"},
        motivo_r_f="ok",
        beta=Beta(1.1, 0.4, 104, "^GSPC"),
        tasa=0.21,
        consenso=0.10,
        motivos={"beta": "ok", "tasa": "ok", "consenso": "ok"},
        cociente_adr=None,
    )
    valores.update(sobre)
    return v.Entradas(**valores)


def test_la_valoracion_con_los_supuestos_del_programa_es_json_estricto_y_lleva_la_divisa():
    plano = v.valorar(_entradas(), 0.6, hoy=date(2026, 10, 14))
    json.dumps(plano, allow_nan=False)
    assert plano["version"] == "m1" and "veredicto" in plano
    assert plano["divisa"] == {**USD.a_dict(), "sin_prima_pais": False}
    assert plano["votos"]["pares"]["voto"] == "barata"


def test_con_cambios_la_valoracion_es_la_de_los_deslizadores():
    sin = v.valorar(_entradas(), None)
    con = v.valorar(_entradas(), None, cambios={"g_ref": 0.30})
    assert con["supuestos"]["g_ref"]["procedencia"]["fuente"] == "usuario"
    assert con["valor"]["base"] > sin["valor"]["base"]


def test_valorar_es_puro_mismas_entradas_mismo_resultado():
    e = _entradas()
    assert v.valorar(e, 0.1, hoy=date(2026, 10, 14)) == v.valorar(e, 0.1, hoy=date(2026, 10, 14))


def test_una_emisora_en_pesos_sin_bono_m_no_se_valora_hasta_que_se_pone_la_tasa():
    e = _entradas(divisa=MXN, r_f=None, motivo_r_f="sin_token",
                  procedencia_r_f={"fuente": "bono_m_10", "serie": "SF44071", "fecha": None})
    assert v.valorar(e, None)["motivo"] == "sin_bono_m"
    con_tasa = v.valorar(e, None, cambios={"r_f": 0.092})
    assert con_tasa["supuestos"]["r_f"] == {
        "valor": 0.092,
        "procedencia": {"fuente": "usuario", "programa": None},
    }
    assert "veredicto" in con_tasa


def test_sin_tasa_libre_en_dolares_el_motivo_es_el_de_siempre():
    assert v.valorar(_entradas(r_f=None, motivo_r_f="sin_tasa_libre"), None)["motivo"] == "sin_tasa_libre"


def test_una_tasa_puesta_a_mano_que_no_es_un_numero_se_rechaza():
    e = _entradas(divisa=MXN, r_f=None)
    with pytest.raises(ValueError):
        v.valorar(e, None, cambios={"r_f": "nueve"})


def test_la_sensibilidad_usa_los_mismos_datos_que_el_voto():
    e = _entradas()
    tabla = v.sensibilidad(e, None)
    plano = v.valorar(e, None)
    assert tabla.valores[2][2] == pytest.approx(plano["valor"]["base"])


def test_sin_holgura_de_gordon_hay_tabla_con_la_casilla_central_vacia():
    e = _entradas()
    tabla = v.sensibilidad(e, {"g_perpetuo": 0.085})
    assert tabla is not None
    assert tabla.valores[2][2] is None
    assert any(valor is not None for fila in tabla.valores for valor in fila)


def test_una_financiera_no_tiene_tabla_de_sensibilidad():
    e = _entradas(perfil=perfil(industria="Banks - Regional"))
    assert v.sensibilidad(e, None) is None


# --- `entradas`, con la red sustituida ---------------------------------------


class _Red:
    """Lo que cada función de red devolvería, por nombre."""

    def __init__(self, **sobre):
        self.respuestas = dict(
            perfil=(perfil(), "ok"),
            tasa_libre=(0.05, "ok"),
            beta=(Beta(1.1, 0.4, 104, "^GSPC"), "ok"),
            tasa_efectiva=(0.21, "ok"),
            consenso=(0.10, "ok"),
            estados=(None, "sin_red"),
        )
        self.respuestas.update(sobre)
        self.llamadas = []

    def __enter__(self):
        self._parches = []
        for nombre, respuesta in self.respuestas.items():
            parche = patch.object(v.mercado, nombre, side_effect=self._registrar(nombre, respuesta))
            parche.start()
            self._parches.append(parche)
        return self

    def __exit__(self, *_):
        for parche in self._parches:
            parche.stop()

    def _registrar(self, nombre, respuesta):
        def llamada(*args):
            self.llamadas.append((nombre, args))
            return respuesta

        return llamada


SEC = Resuelto("MU", "sec", None, None)


def test_una_empresa_de_la_sec_se_valora_con_edgar_en_dolares():
    with _Red() as red, patch.object(v, "desde_sec", return_value=(fundamentos(), "ok")):
        e, motivo = v.entradas(SEC)
    assert motivo == "ok"
    assert e.divisa == USD
    assert e.procedencia_r_f == {"fuente": "tesoro_10", "serie": "^TNX"}
    assert ("beta", ("MU", "^GSPC", None)) in red.llamadas


def test_sin_perfil_no_hay_entradas():
    with _Red(perfil=(None, "sin_red")):
        assert v.entradas(SEC) == (None, "sin_red")
    with _Red(perfil=(None, "sin_precio")):
        assert v.entradas(SEC) == (None, "sin_precio")


def _estados_walmex():
    def hoja(fechas, filas):
        return pd.DataFrame(filas, index=[pd.Timestamp(f) for f in fechas]).T

    anios = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
    return {
        "quarterly_income_stmt": hoja(["2026-06-30"], {"Diluted Average Shares": [17.16e9]}),
        "quarterly_balance_sheet": pd.DataFrame(),
        "quarterly_cashflow": pd.DataFrame(),
        "income_stmt": hoja(anios, {
            "Total Revenue": [1.011e12, 9.575e11, 8.857e11, 8.182e11],
            "Operating Income": [7.849e10, 7.736e10, 7.328e10, 6.801e10],
            "Net Income Common Stockholders": [4.989e10, 5.383e10, 5.159e10, 4.897e10],
            "Interest Expense": [9.115e9, 8.593e9, 7.837e9, 7.05e9],
        }),
        "balance_sheet": hoja(anios, {
            "Stockholders Equity": [2.356e11, 2.329e11, 1.991e11, 2.025e11],
            "Total Debt": [8.085e10, 7.973e10, 7.525e10, 6.984e10],
            "Cash And Cash Equivalents": [2.859e10, 3.651e10, 4.067e10, 4.743e10],
        }),
        "cashflow": hoja(anios, {
            "Operating Cash Flow": [8.244e10, 7.264e10, 8.512e10, 6.447e10],
            "Capital Expenditure": [-3.898e10, -3.476e10, -2.879e10, -2.13e10],
        }),
    }


WALMEX = Resuelto("WALMEX.MX", "sin_sec", None, None)
PERFIL_WALMEX = perfil(
    ticker="WALMEX.MX", precio=47.71, capitalizacion=8.2158e11, moneda="MXN",
    moneda_estados="MXN", industria="Discount Stores", pais="Mexico",
)


def test_walmex_se_valora_en_pesos_con_el_bono_m_y_contra_el_ipc():
    red = _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(_estados_walmex(), "ok"),
               tipo_de_cambio=(1.0, "ok"))
    with red, patch.object(v.divisas, "bono_m", return_value=(0.0925, "ok", date(2026, 9, 24))):
        e, motivo = v.entradas(WALMEX)
    assert motivo == "ok"
    assert e.divisa.moneda_valoracion == "MXN" and e.divisa.indice_beta == "^MXX"
    assert e.r_f == 0.0925
    assert e.procedencia_r_f == {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    assert ("beta", ("WALMEX.MX", "^MXX", None)) in red.llamadas
    assert e.fundamentos.fuente == "yfinance" and len(e.fundamentos.ejercicios) == 4
    assert e.cociente_adr == pytest.approx(17.16e9 / (8.2158e11 / 47.71), rel=1e-3)
    plano = v.valorar(e, None)
    assert plano["supuestos"]["r_f"]["procedencia"]["fuente"] == "bono_m_10"
    assert plano["moneda"] == "MXN"


def test_sin_token_de_banxico_walmex_tiene_entradas_pero_no_valoracion():
    red = _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(_estados_walmex(), "ok"),
               tipo_de_cambio=(1.0, "ok"))
    with red, patch.object(v.divisas, "bono_m", return_value=(None, "sin_token", None)):
        e, motivo = v.entradas(WALMEX)
    assert motivo == "ok" and e.r_f is None and e.motivo_r_f == "sin_token"
    assert v.valorar(e, None)["motivo"] == "sin_bono_m"


def test_tsm_convierte_los_estados_a_dolares_y_compara_el_consenso_en_su_moneda():
    perfil_tsm = perfil(ticker="TSM", precio=430.0, capitalizacion=2.23e12,
                        moneda="USD", moneda_estados="TWD", pais="Taiwan")

    def tipo_de_cambio(origen, destino):
        return {("TWD", "USD"): (0.031, "ok"), ("USD", "USD"): (1.0, "ok")}[(origen, destino)]

    tsm = Resuelto("TSM", "extranjera_sec", None, None)
    red = _Red(perfil=(perfil_tsm, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", side_effect=tipo_de_cambio):
        e, _ = v.entradas(tsm)
    assert e.divisa.convertida and e.divisa.moneda_valoracion == "USD"
    assert e.fundamentos.moneda == "USD"
    assert e.fundamentos.ultimo.ingresos == pytest.approx(1.011e12 * 0.031)
    assert ("consenso", ("TSM", "TWD")) in red.llamadas
    assert v.valorar(e, None)["divisa"]["sin_prima_pais"] is True


def test_una_adr_en_dolares_con_estados_en_pesos_regresa_su_precio_en_pesos():
    perfil_amx = perfil(ticker="AMX", precio=22.885, capitalizacion=6.83e10, moneda="USD",
                        moneda_estados="MXN", pais="Mexico")

    def tipo_de_cambio(origen, destino):
        return {("MXN", "MXN"): (1.0, "ok"), ("USD", "MXN"): (18.40, "ok")}[(origen, destino)]

    amx = Resuelto("AMX", "extranjera_sec", None, None)
    red = _Red(perfil=(perfil_amx, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", side_effect=tipo_de_cambio), \
            patch.object(v.divisas, "bono_m", return_value=(0.0925, "ok", date(2026, 9, 24))):
        e, _ = v.entradas(amx)
    assert e.divisa.moneda_valoracion == "MXN"
    assert ("beta", ("AMX", "^MXX", "USDMXN=X")) in red.llamadas
    # En pesos el Bono M ya lleva el riesgo de México.
    assert v.valorar(e, None)["divisa"]["sin_prima_pais"] is False


def test_una_extranjera_que_presenta_en_dolares_tambien_va_sin_prima_pais():
    teva = _entradas(perfil=perfil(pais="Israel"))
    assert v.valorar(teva, None)["divisa"]["sin_prima_pais"] is True


def test_sin_tipo_de_cambio_no_hay_entradas():
    perfil_cad = perfil(ticker="RY.TO", moneda="CAD", moneda_estados="CAD")
    red = _Red(perfil=(perfil_cad, "ok"), estados=(_estados_walmex(), "ok"))
    with red, patch.object(v.mercado, "tipo_de_cambio", return_value=(None, "sin_red")):
        assert v.entradas(Resuelto("RY.TO", "sin_sec", None, None)) == (None, "sin_red")


def test_sin_estados_de_yahoo_no_hay_entradas():
    with _Red(perfil=(PERFIL_WALMEX, "ok"), estados=(None, "sin_red")):
        assert v.entradas(WALMEX) == (None, "sin_red")
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_valorar.py tests/test_medidores_valoracion.py -q`
Expected: FAIL con `ModuleNotFoundError` y con los motivos nuevos sin etiqueta.

- [ ] **Step 3: El motivo nuevo**

En `valoracion/votos.py`, añade a `MOTIVOS`:

```python
        "sin_bono_m",
```

En `medidores_valoracion.py`, añade a `MOTIVO` (junto a `sin_tasa_libre`):

```python
    "sin_bono_m": "Banxico no dio el rendimiento del Bono M a 10 años (falta el token o no respondió)",
```

No lleva «:»: una fallida se pinta como «Sin valoración: …» y un test exige un solo «:».

- [ ] **Step 3b: La beta con el precio convertido, en `valoracion/mercado.py`**

Tests, al final de `tests/test_valoracion_mercado.py`:

```python
from valoracion.mercado import precio_convertido  # noqa: E402


def test_el_precio_convertido_es_el_precio_por_el_tipo_de_cada_semana():
    fechas = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    precio = pd.Series([10.0, 11.0, 12.0], index=fechas)
    tipo = pd.Series([18.0, 18.5, 19.0], index=fechas)
    assert precio_convertido(precio, tipo).tolist() == [180.0, 203.5, 228.0]


def test_el_precio_convertido_solo_tiene_las_semanas_con_los_dos_datos():
    fechas = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    precio = pd.Series([10.0, 11.0, 12.0], index=fechas)
    tipo = pd.Series([18.0, float("nan")], index=fechas[:2])
    assert len(precio_convertido(precio, tipo)) == 1
```

Y al final de `tests/test_valoracion_mercado_red.py`:

```python
def test_la_beta_con_par_regresa_el_precio_convertido():
    g = np.random.default_rng(7)
    m = g.normal(0.002, 0.02, 104)
    a = 2 * m + g.normal(0, 0.002, 104)
    # Un tipo de cambio constante no cambia ningún rendimiento: la beta es la misma.
    dobles = {
        "AMX": _con_historial(_cierres(a)),
        "^MXX": _con_historial(_cierres(m)),
        "USDMXN=X": _con_historial(_cierres(np.zeros(104))),
    }
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]) as fabrica:
        beta, motivo = mercado.beta("AMX", "^MXX", "USDMXN=X")
    assert motivo == "ok" and beta.bruta == pytest.approx(2.0, abs=0.1)
    assert {c.args[0] for c in fabrica.call_args_list} == {"AMX", "^MXX", "USDMXN=X"}


def test_la_beta_con_y_sin_par_no_comparten_cache(tmp_path):
    dobles = _dobles_de_beta()
    dobles["USDMXN=X"] = _con_historial(_cierres(np.zeros(104)))
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        mercado.beta("MU", "^GSPC")
        mercado.beta("MU", "^GSPC", "USDMXN=X")
    assert len(_escritos(tmp_path)) == 2


def test_sin_cierres_del_tipo_de_cambio_no_hay_beta_ni_se_guarda(tmp_path):
    dobles = _dobles_de_beta()
    dobles["USDMXN=X"] = _con_historial([])
    with patch.object(mercado.yf, "Ticker", side_effect=lambda s: dobles[s]):
        assert mercado.beta("MU", "^GSPC", "USDMXN=X") == (None, "sin_red")
    assert _escritos(tmp_path) == []
```

Implementación en `valoracion/mercado.py`. La función pura, junto a `regresion_beta`:

```python
def precio_convertido(precio: pd.Series, tipo: pd.Series) -> pd.Series:
    """El precio semanal por el tipo de cambio de esa misma semana.

    Para regresar contra un índice en otra moneda: AMX cotiza en dólares y su
    índice, el IPC, en pesos. Sólo quedan las semanas con los dos datos.
    """
    juntos = pd.concat([_semanal(precio), _semanal(tipo)], axis=1, join="inner").dropna()
    return juntos.iloc[:, 0] * juntos.iloc[:, 1]
```

Y `beta` gana el par, que entra en la clave de la caché:

```python
def beta(
    ticker: str, indice: str = INDICE, par: "str | None" = None
) -> "tuple[Beta | None, str]":
    """La beta del ticker contra el índice. Con `par` (`USDMXN=X`), el precio se
    pasa a la moneda del índice semana a semana antes de regresar: un precio en
    dólares contra un índice en pesos mezclaría dos monedas."""

    def pedir():
        activo = yf.Ticker(ticker).history(period="2y", interval="1wk")["Close"]
        referencia = yf.Ticker(indice).history(period="2y", interval="1wk")["Close"]
        tipo = (
            None if par is None else yf.Ticker(par).history(period="2y", interval="1wk")["Close"]
        )
        return activo, referencia, tipo

    def interpretar(series):
        activo, referencia, tipo = series
        # `history()` no lanza cuando falla la red: devuelve un marco vacío. Eso
        # es "no lo sé"; un historial corto pero real (una salida a bolsa
        # reciente) es un hecho estable, y ése sí se guarda como "sin beta".
        if _sin_cierres(activo) or _sin_cierres(referencia):
            return None
        if tipo is not None:
            if _sin_cierres(tipo):
                return None
            activo = precio_convertido(activo, tipo)
        encontrada = regresion_beta(activo, referencia, indice)
        return {"beta": None if encontrada is None else asdict(encontrada)}
```

(el resto de la función, `leer` y la llamada a `_traer`, igual), con la clave:

```python
    clave = f"{ticker}|{indice}" if par is None else f"{ticker}|{indice}|{par}"
    encontrada, motivo = _traer("beta", clave, pedir, interpretar, leer)
```

Comprueba que los tests de `beta` que ya existen siguen pasando: sin par, nada cambia, ni la clave.

- [ ] **Step 4: Implementar `analizador/valorar.py`**

```python
"""La valoración de cualquier ticker: una sola vez a la red, y luego aritmética.

`entradas` trae de la red todo lo que la valoración necesita --perfil,
fundamentos, tasa libre, beta, tasa efectiva, consenso y tipos de cambio-- y lo
deja en la moneda de la valoración (ver `analizador.divisas`). `valorar` es
puro: con las mismas entradas y los mismos cambios da siempre lo mismo, y es lo
que llamarán los deslizadores de N2 sin volver a pedir nada.

Sin cambios, `valorar` da la valoración con los supuestos del programa: la que
va al acta. Con cambios, la de los deslizadores, que no se guarda en ningún
sitio.
"""

from dataclasses import dataclass

from analizador import divisas
from analizador.divisas import Divisa
from analizador.lineas_yf import fundamentos_anuales, lineas_de
from analizador.resolver import Resuelto
from valoracion import dcf, mercado, plano
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.fundamentos import Fundamentos, desde_sec
from valoracion.mercado import Beta, Perfil
from valoracion.motor import calcular, datos_dcf, puente
from valoracion.supuestos import Supuestos, aplicar, deducir

# Privada y aun así importada: es la misma validación que `aplicar` hace con
# cualquier supuesto movido, y la tasa que el usuario pone a mano lo es.
from valoracion.supuestos import _numero_finito


@dataclass(frozen=True)
class Entradas:
    """Todo lo que la valoración necesita, ya en la moneda de la valoración.

    `r_f` puede faltar: una emisora en pesos sin el Bono M de Banxico se queda
    sin tasa libre hasta que el usuario la ponga. `motivo_r_f` dice por qué
    falta (`sin_token`, `token_invalido`, `sin_red`, `sin_dato`,
    `sin_tasa_libre`). `cociente_adr` es el de `divisas.cociente_adr`, o None.
    """

    ticker: str
    fundamentos: Fundamentos
    perfil: Perfil
    divisa: Divisa
    r_f: "float | None"
    procedencia_r_f: dict
    motivo_r_f: str
    beta: "Beta | None"
    tasa: "float | None"
    consenso: "float | None"
    motivos: dict
    cociente_adr: "float | None"


def _ultimo(serie) -> "float | None":
    validos = serie.dropna()
    return float(validos.iloc[-1]) if len(validos) else None


def entradas(resuelto: Resuelto, cache_dir=None) -> "tuple[Entradas | None, str]":
    """Todo lo que la valoración necesita, o el motivo por el que no se pudo traer.

    El mismo orden de preguntas que `valoracion.motor.valorar`: sin precio no
    hay acciones, y sin estados no hay nada que proyectar. La tasa libre se trae
    pero no se exige aquí: sin ella todavía se puede pintar todo lo demás, y el
    deslizador la pide (ver `valorar`).
    """
    ticker = resuelto.ticker
    perfil, motivo = mercado.perfil(ticker)
    if perfil is None:
        return None, "sin_red" if motivo == "sin_red" else "sin_precio"
    acciones_estados = None
    if resuelto.clase == "sec":
        fundamentos, motivo = desde_sec(ticker, cache_dir=cache_dir)
    else:
        crudos, motivo = mercado.estados(ticker)
        if crudos is None:
            return None, motivo
        trimestrales, anuales = lineas_de(crudos)
        fundamentos = fundamentos_anuales(anuales, perfil.moneda_estados)
        motivo = "ok" if fundamentos is not None else "sin_historia"
        if not trimestrales.empty:
            acciones_estados = _ultimo(trimestrales["acciones_diluidas"])
    if fundamentos is None:
        return None, motivo
    divisa, motivo = divisas.divisa(fundamentos.moneda, perfil.moneda)
    if divisa is None:
        return None, motivo
    # El consenso es una tasa de crecimiento, y Yahoo lo da en la moneda de los
    # estados originales (en TSM, TWD): se compara antes de convertir.
    consenso, motivo_consenso = mercado.consenso(ticker, fundamentos.moneda)
    if divisa.moneda_valoracion == "MXN":
        r_f, motivo_r_f, fecha = divisas.bono_m()
        procedencia = {
            "fuente": "bono_m_10",
            "serie": divisas.SERIE_BONO_M_10,
            "fecha": None if fecha is None else fecha.isoformat(),
        }
    else:
        r_f, motivo_r_f = mercado.tasa_libre()
        procedencia = {"fuente": "tesoro_10", "serie": mercado.BONO_10}
    # La beta se regresa con el precio en la moneda de la valoración, que es la
    # del índice: AMX en dólares contra el IPC en pesos mezclaría dos monedas.
    base_precio, _ = mercado.SUBUNIDADES.get(perfil.moneda, (perfil.moneda, 1))
    par_beta = (
        None
        if base_precio == divisa.moneda_valoracion
        else f"{base_precio}{divisa.moneda_valoracion}=X"
    )
    beta, motivo_beta = mercado.beta(ticker, divisa.indice_beta, par_beta)
    tasa, motivo_tasa = mercado.tasa_efectiva(ticker)
    perfil_valoracion = divisas.perfil_en(perfil, divisa.tipo_precio, divisa.moneda_valoracion)
    return (
        Entradas(
            ticker=ticker,
            fundamentos=divisas.convertir(fundamentos, divisa.tipo_estados, divisa.moneda_valoracion),
            perfil=perfil_valoracion,
            divisa=divisa,
            r_f=r_f,
            procedencia_r_f=procedencia,
            motivo_r_f=motivo_r_f,
            beta=beta,
            tasa=tasa,
            consenso=consenso,
            motivos={"beta": motivo_beta, "tasa": motivo_tasa, "consenso": motivo_consenso},
            cociente_adr=divisas.cociente_adr(acciones_estados, perfil_valoracion),
        ),
        "ok",
    )


def supuestos_de(entradas: Entradas, cambios: "dict | None" = None) -> "Supuestos | None":
    """Los supuestos del programa con los cambios del usuario, o None sin tasa libre.

    Sin tasa libre (un Bono M sin token) sólo hay supuestos si el usuario la
    pone, y entra como `{"fuente": "usuario", "programa": None}`: el programa no
    tenía ninguna.
    """
    cambios = dict(cambios or {})
    r_f, procedencia = entradas.r_f, entradas.procedencia_r_f
    if r_f is None:
        if "r_f" not in cambios:
            return None
        r_f = _numero_finito("r_f", cambios.pop("r_f"))
        procedencia = {"fuente": "usuario", "programa": None}
    supuestos = deducir(
        entradas.fundamentos,
        entradas.perfil,
        r_f,
        entradas.beta,
        entradas.tasa,
        entradas.consenso,
        entradas.motivos,
        procedencia_r_f=procedencia,
    )
    return aplicar(supuestos, cambios)


def _sin_prima_pais(entradas: Entradas) -> bool:
    """Si se valora en dólares una empresa de fuera de EE. UU.

    Con la tasa libre del Tesoro y la prima de un mercado maduro, a una empresa
    de Taiwán o de Israel le falta la prima por riesgo país. En pesos no: el
    Bono M ya lleva el riesgo soberano de México. Sin país conocido no se
    afirma nada.
    """
    pais = entradas.perfil.pais
    return (
        entradas.divisa.moneda_valoracion == "USD"
        and pais is not None
        and pais != "United States"
    )


def _sin_tasa(entradas: Entradas) -> str:
    return "sin_bono_m" if entradas.divisa.moneda_valoracion == "MXN" else "sin_tasa_libre"


def valorar(
    entradas: Entradas,
    pilar_valoracion: "float | None",
    cambios: "dict | None" = None,
    hoy=None,
) -> dict:
    """La valoración como diccionario, con la divisa y el cociente de la ADR al lado.

    JSON estricto, como `plano.a_dict`. Las dos claves de más (`divisa`,
    `cociente_adr`) las ignora quien no las conoce: `medidores_valoracion` y
    `aprobacion.carga.valoracion_de` sólo miran las suyas.
    """
    divisa = {**entradas.divisa.a_dict(), "sin_prima_pais": _sin_prima_pais(entradas)}
    extra = {"divisa": divisa, "cociente_adr": entradas.cociente_adr}
    supuestos = supuestos_de(entradas, cambios)
    if supuestos is None:
        return {**plano.fallida(_sin_tasa(entradas), hoy), **extra}
    v = calcular(entradas.fundamentos, entradas.perfil, supuestos, pilar_valoracion, hoy)
    return {**plano.a_dict(v), **extra}


def sensibilidad(entradas: Entradas, cambios: "dict | None" = None) -> "dcf.Sensibilidad | None":
    """La tabla de sensibilidad del DCF con los mismos datos con que se votó.

    None si no hay DCF que tabular: una financiera (se valora por beneficio
    residual), sin tasa libre, o sin datos para el DCF (sin historia, sin flujo
    libre, quema caja). Con el coste de capital sin holgura sobre el
    crecimiento perpetuo sí hay tabla: la casilla central sale vacía y las
    demás enseñan desde qué coste vuelve a haber valor.
    """
    if entradas.perfil.industria in INDUSTRIAS_FINANCIERAS:
        return None
    supuestos = supuestos_de(entradas, cambios)
    if supuestos is None:
        return None
    # El mismo puente que `calcular`: si la tabla tratara la deuda o las
    # acciones de otra forma, su casilla central no sería el valor base.
    deuda, efectivo, acciones = puente(entradas.fundamentos, entradas.perfil)
    datos, _ = datos_dcf(entradas.fundamentos, supuestos, deuda, efectivo, acciones)
    if datos is None:
        return None
    return dcf.sensibilidad(datos, supuestos.g_ref.valor)
```

La tabla usa `valoracion.motor.puente`, el mismo puente que `calcular` (deuda y efectivo sin declarar a cero, y las acciones como capitalización ÷ precio): su casilla central es el valor base. `puente` lo añadió la revisión de la Task 9.

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_valorar.py tests/test_medidores_valoracion.py tests/test_valoracion_votos.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add analizador/valorar.py valoracion/votos.py medidores_valoracion.py valoracion/mercado.py tests/test_analizador_valorar.py tests/test_medidores_valoracion.py tests/test_valoracion_mercado.py tests/test_valoracion_mercado_red.py
git commit -m "feat: la valoracion de cualquier ticker, una vez a la red y luego aritmetica pura

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Un ticker de punta a punta

> **Ejecutada y superada** (e7e30b3, 7bc4523 y un ajuste). En vivo contra el panel real del S&P 500 (502 empresas, 423 supervivientes, 2026Q3), ningún motivo culpa a quien no es: MU y NVDA dan su ficha de candidatas idéntica; DUOL, TSM, AMX, WALMEX.MX, SHEL.L y 7203.T se insertan con un puesto creíble; SPY sólo identidad, ZZZZQ `sin_red`, CEF `sin_sector` sin bajar nada. La revisión añadió los tests de la rama de yfinance de `_filas_propias` (el par invertido o las monedas cruzadas pasaban los 11 tests), una guarda que dice `sin_precio` sin ninguna moneda en vez de pedir `NoneUSD=X`, y aisló `entradas` y `valorar` como `ranking.run._valoracion`: un defecto en la valoración deja `error_interno` en ella y conserva la clase, la identidad, la referencia y, si llegaron, las entradas. Coste: 10 tickers en frío 38 s (90 % red). Manda el código vivo.

**Files:**
- Create: `analizador/analisis.py`
- Test: `tests/test_analizador_analisis.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_analisis.py`:

```python
"""Un ticker de punta a punta, con cada pieza sustituida en su frontera."""

import logging
from unittest.mock import patch

import pandas as pd
import pytest

from analizador import analisis
from analizador.resolver import Identidad, Resuelto
from tests.test_analizador_referencia import panel_crudo


def _identidad(ticker="IN0", tipo="EQUITY", sector="Technology", moneda="USD"):
    return Identidad(ticker, tipo, "Una empresa", "NMS", moneda, moneda, sector,
                     "Semiconductors", "United States", 100.0, None)


def _resuelto(ticker="IN0", clase="sec", **sobre):
    return Resuelto(ticker, clase, _identidad(ticker, **sobre), None)


class _Valoracion:
    """Sustituye a `entradas` y `valorar`, y apunta con qué pilar se valoró."""

    def __init__(self):
        self.pilares = []

    def __enter__(self):
        self._a = patch.object(analisis, "entradas", return_value=("ENTRADAS", "ok"))
        self._b = patch.object(analisis, "valorar", side_effect=self._valorar)
        self._a.start(), self._b.start()
        return self

    def __exit__(self, *_):
        self._a.stop(), self._b.stop()

    def _valorar(self, entradas, pilar):
        self.pilares.append(pilar)
        return {"version": "m1", "veredicto": "en_rango"}


def test_un_ticker_del_panel_toma_su_ficha_del_panel_y_vota_con_su_pilar():
    panel = panel_crudo()
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.kpis, "kpis_sec", side_effect=AssertionError("no hace falta")), \
            _Valoracion() as valoracion:
        a = analisis.analizar("IN0", panel, {"IN0": "Information Technology"})
    assert (a.clase, a.motivo, a.sector, a.fuente_sector) == ("sec", None, "Information Technology", "sp500")
    assert a.referencia.en_panel and a.motivo_referencia is None
    assert valoracion.pilares == [a.referencia.ficha["pilares"]["valoracion"]]
    assert a.valoracion == {"version": "m1", "veredicto": "en_rango"}


def test_un_ticker_de_la_sec_fuera_del_panel_se_inserta_con_sus_filas():
    panel = panel_crudo()
    propias = panel.xs("IN1", level="ticker").drop(columns="sector_gics")
    sin_el = panel.drop(index="IN1", level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto("IN1")), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(propias, "ok")), \
            _Valoracion():
        a = analisis.analizar("IN1", sin_el, {})
    assert a.sector == "Information Technology" and a.fuente_sector == "yahoo"
    assert not a.referencia.en_panel and a.referencia.puesto is not None


def test_sin_panel_se_valora_igual_y_se_dice():
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            _Valoracion() as valoracion:
        a = analisis.analizar("IN0", None, {})
    assert a.referencia is None and a.motivo_referencia == "sin_panel"
    assert valoracion.pilares == [None]


def test_sin_sector_no_hay_pares_y_se_dice():
    panel = panel_crudo().drop(index="IN0", level="ticker")
    resuelto = _resuelto(sector="Conglomerates")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), _Valoracion():
        a = analisis.analizar("IN0", panel, {})
    assert a.sector is None and a.motivo_referencia == "sin_sector"


def test_un_sector_con_menos_pares_de_los_que_pide_el_z_no_tiene_referencia():
    # Con ella dentro, Utilities tendría dos empresas: menos de `MIN_PARES`, sin
    # z, y la ficha saldría «pilar sin datos», que culparía a la empresa.
    panel = panel_crudo().drop(index=["UT0", "UT1", "UT2", "UT3"], level="ticker")
    resuelto = _resuelto("UT0", sector="Utilities")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), \
            patch.object(analisis.kpis, "kpis_sec", side_effect=AssertionError("no hace falta")), \
            _Valoracion():
        a = analisis.analizar("UT0", panel, {})
    assert a.referencia is None and a.motivo_referencia == "sector_sin_pares"


def test_con_los_pares_justos_si_hay_referencia():
    crudo = panel_crudo()
    propias = crudo.xs("UT0", level="ticker").drop(columns="sector_gics")
    panel = crudo.drop(index=["UT0", "UT1", "UT2"], level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto("UT0", sector="Utilities")), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(propias, "ok")), \
            _Valoracion():
        a = analisis.analizar("UT0", panel, {})
    assert a.motivo_referencia is None and a.referencia is not None


def test_si_no_hay_filas_propias_el_motivo_es_el_suyo():
    panel = panel_crudo().drop(index="IN0", level="ticker")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.kpis, "kpis_sec", return_value=(None, "sin_estados")), \
            _Valoracion():
        a = analisis.analizar("IN0", panel, {})
    assert a.motivo_referencia == "sin_estados"


def test_un_etf_solo_tiene_su_identidad():
    resuelto = _resuelto("SPY", "etf", tipo="ETF")
    with patch.object(analisis.resolver, "resolver", return_value=resuelto), \
            patch.object(analisis, "entradas", side_effect=AssertionError("no se valora")):
        a = analisis.analizar("SPY", panel_crudo(), {})
    assert (a.clase, a.motivo, a.valoracion, a.referencia) == ("etf", None, None, None)
    assert a.identidad.tipo == "ETF"


def test_un_ticker_sin_clase_dice_por_que():
    with patch.object(analisis.resolver, "resolver", return_value=Resuelto("ZZZZQ", None, None, "sin_red")):
        a = analisis.analizar("ZZZZQ", None, {})
    assert (a.clase, a.motivo) == (None, "sin_red")


def test_sin_entradas_la_valoracion_es_una_fallida_con_su_motivo():
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis, "entradas", return_value=(None, "sin_precio")):
        a = analisis.analizar("IN0", None, {})
    assert a.valoracion["motivo"] == "sin_precio"
    assert isinstance(a.valoracion["version"], str)


def test_un_defecto_en_un_ticker_no_tumba_a_los_demas_y_deja_traza(caplog):
    def resolver(ticker):
        if ticker == "ROTO":
            raise KeyError("un defecto propio")
        return Resuelto(ticker, None, None, "sin_red")

    with patch.object(analisis.resolver, "resolver", side_effect=resolver), \
            patch.object(analisis.referencia, "cargar_panel", return_value=(None, None)), \
            caplog.at_level(logging.ERROR):
        resultados, fecha = analisis.analizar_varios(["ROTO", "MU"], tabla_sectores={})
    assert [a.motivo for a in resultados] == ["error_interno", "sin_red"]
    assert fecha is None
    assert "ROTO" in caplog.text
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_analisis.py -q`
Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar**

`analizador/analisis.py`:

```python
"""Un ticker de punta a punta: qué es, cómo queda frente a su sector y cuánto vale.

Sin Streamlit: N2 pinta lo que sale de aquí. Un ticker que falla sólo se lleva
su fila, que es la política de la descarga de fundamentales y de la valoración
de candidatos; y un defecto propio tampoco tumba a los demás, pero no se calla:
el traceback va al log de la consola y la fila dice `error_interno`.
"""

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from analizador import kpis, referencia, resolver
from analizador.lineas_yf import lineas_de
from analizador.referencia import Referencia
from analizador.resolver import Identidad, Resuelto
from analizador.sectores import sector_gics
from analizador.valorar import Entradas, entradas, valorar
from fundamentals.sectors import MIN_PARES, load_sectors
from valoracion import mercado, plano


@dataclass(frozen=True)
class Analisis:
    """Todo lo que se sabe de un ticker. `motivo` dice por qué no hay análisis.

    Con clase, `motivo` es None y lo que falta va en su sitio:
    `motivo_referencia` (`sin_panel`, `sin_sector`, `sector_sin_pares`,
    `sin_estados`, `sin_precio`, `sin_trimestres_comparables`, o el de la red) y
    la valoración, que es una
    fallida con su motivo. Un ETF sólo tiene identidad.
    """

    ticker: str
    clase: "str | None"
    identidad: "Identidad | None"
    motivo: "str | None"
    sector: "str | None" = None
    fuente_sector: "str | None" = None
    referencia: "Referencia | None" = None
    motivo_referencia: "str | None" = None
    entradas: "Entradas | None" = None
    valoracion: "dict | None" = None


def _filas_propias(resuelto: Resuelto) -> "tuple[pd.DataFrame | None, str]":
    if resuelto.clase == "sec":
        return kpis.kpis_sec(resuelto.ticker)
    crudos, motivo = mercado.estados(resuelto.ticker)
    if crudos is None:
        return None, motivo
    trimestrales, anuales = lineas_de(crudos)
    if trimestrales.empty:
        return None, "sin_historia"
    identidad = resuelto.identidad
    # Sin una de las dos monedas se toma la otra: sin dato no se convierte, y
    # un par inventado («NoneTWD=X») sólo daría un precio vacío.
    moneda_precio = identidad.moneda or identidad.moneda_estados
    moneda_estados = identidad.moneda_estados or identidad.moneda
    # Los KPIs se calculan en dólares para que los suelos de `fundamentals.kpis`
    # valgan lo mismo que en el panel de referencia (ver `kpis.kpis_yf`).
    tipo_a_usd, motivo = mercado.tipo_de_cambio(moneda_estados, "USD")
    if tipo_a_usd is None:
        return None, motivo
    # `kpis_yf` dice `sin_precio` si no hay precio: unas filas sin valoración
    # saldrían excluidas por un pilar sin datos, que culparía a la empresa.
    return kpis.kpis_yf(
        resuelto.ticker, trimestrales, anuales, moneda_precio, moneda_estados, tipo_a_usd
    )


def _frente_al_sector(
    resuelto: Resuelto, sector: "str | None", panel: "pd.DataFrame | None"
) -> "tuple[Referencia | None, str | None]":
    if panel is None:
        return None, "sin_panel"
    if resuelto.ticker in panel.index.get_level_values("ticker"):
        return referencia.frente_al_sector(resuelto.ticker, panel), None
    if sector is None:
        return None, "sin_sector"
    # Un sector que ni con ella dentro llega a `MIN_PARES` no tiene z: la ficha
    # saldría «pilar sin datos», que culparía a la empresa. La clave es la del
    # ranking, y se mira antes de bajar nada.
    pares = panel.index.get_level_values("ticker")[panel["sector_gics"] == sector].nunique()
    if pares + 1 < MIN_PARES:
        return None, "sector_sin_pares"
    propias, motivo = _filas_propias(resuelto)
    if propias is None:
        return None, motivo
    encontrada = referencia.frente_al_sector(resuelto.ticker, panel, sector, propias)
    return (encontrada, None) if encontrada is not None else (None, "sin_trimestres_comparables")


def _analizar(ticker: str, panel: "pd.DataFrame | None", tabla_sectores: "dict | None") -> Analisis:
    resuelto = resolver.resolver(ticker)
    if resuelto.clase is None:
        return Analisis(ticker, None, resuelto.identidad, resuelto.motivo)
    if resuelto.clase == "etf":
        return Analisis(ticker, "etf", resuelto.identidad, None)
    sector, fuente = sector_gics(ticker, resuelto.identidad.sector, tabla_sectores)
    encontrada, motivo_referencia = _frente_al_sector(resuelto, sector, panel)
    traidas, motivo = entradas(resuelto)
    pilar = None if encontrada is None else encontrada.ficha["pilares"].get("valoracion")
    valoracion = plano.fallida(motivo) if traidas is None else valorar(traidas, pilar)
    return Analisis(
        ticker=ticker,
        clase=resuelto.clase,
        identidad=resuelto.identidad,
        motivo=None,
        sector=sector,
        fuente_sector=fuente,
        referencia=encontrada,
        motivo_referencia=motivo_referencia,
        entradas=traidas,
        valoracion=valoracion,
    )


def analizar(
    ticker: str, panel: "pd.DataFrame | None", tabla_sectores: "dict | None" = None
) -> Analisis:
    """Un ticker ya normalizado (`resolver.normalizar`), frente al `panel` de referencia."""
    try:
        return _analizar(ticker, panel, tabla_sectores)
    except Exception:
        logging.getLogger(__name__).exception(
            "El análisis de %s falló por un defecto, no por falta de datos", ticker
        )
        return Analisis(ticker, None, None, "error_interno")


def analizar_varios(
    tickers: "list[str]", ruta_panel=None, tabla_sectores: "dict | None" = None
) -> "tuple[list[Analisis], date | None]":
    """Varios tickers contra el mismo panel, y la fecha de ese panel."""
    panel, fecha = referencia.cargar_panel(ruta_panel)
    tabla = load_sectors() if tabla_sectores is None else tabla_sectores
    return [analizar(ticker, panel, tabla) for ticker in tickers], fecha
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_analisis.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/analisis.py tests/test_analizador_analisis.py
git commit -m "feat: un ticker de punta a punta, y un defecto en uno no tumba a los demas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Tests contra las fuentes vivas

> **Ejecutada** (46df8d4), idéntica a la tarea. Los 12 pasan contra las fuentes vivas el 2026-10-25: con las credenciales que guarda la app (`credenciales.aplicar(credenciales.cargar())`), 12 passed; sin `BANXICO_TOKEN` en el entorno, 11 passed y el del Bono M omitido, con WALMEX en `sin_bono_m`. yfinance no ha renombrado ninguna fila de `FILAS`. La caché de Banxico no se puede aislar (su `raiz` por defecto se fija al definir la función), como la tarea ya decía.

**Files:**
- Create: `tests/test_analizador_red.py`

- [ ] **Step 1: Escribir los tests `red`**

`tests/test_analizador_red.py`:

```python
"""Contra yfinance, EDGAR y Banxico de verdad. Excluidos de la suite normal.

Comprueban que las fuentes siguen teniendo la forma que el código espera: las
clases de cuatro tickers reales, los nombres de fila de yfinance y el id de la
serie del Bono M por el título de sus metadatos. Las empresas de la SEC
necesitan `EDGAR_IDENTITY`, y el Bono M `BANXICO_TOKEN`; sin ellos se omiten.
"""

import json
import os
import urllib.request

import pytest

from analizador import divisas, resolver
from analizador.analisis import analizar
from analizador.lineas_yf import FILAS, lineas_de
from valoracion import mercado

pytestmark = pytest.mark.red


@pytest.fixture(autouse=True)
def caches_aisladas(tmp_path, monkeypatch):
    monkeypatch.setattr(mercado, "RAIZ_CACHE", tmp_path / "mercado")
    monkeypatch.setattr(resolver, "RAIZ_CACHE", tmp_path / "resolver")


def _con_edgar():
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("Falta EDGAR_IDENTITY")


@pytest.mark.parametrize(
    "ticker, clase",
    [
        ("MU", "sec"),
        ("TSM", "extranjera_sec"),
        # RY presenta 40-F y edgartools la marca `is_foreign = False`.
        ("RY", "extranjera_sec"),
        ("WALMEX.MX", "sin_sec"),
        ("SPY", "etf"),
    ],
)
def test_las_cuatro_clases_con_casos_reales(ticker, clase):
    if clase in ("sec", "extranjera_sec"):
        _con_edgar()
    r = resolver.resolver(ticker)
    assert (r.clase, r.motivo) == (clase, None)


def test_un_indice_no_es_una_accion():
    assert resolver.resolver("^GSPC").motivo == "tipo_no_soportado"


@pytest.mark.parametrize("ticker", ["MU", "WALMEX.MX", "TSM"])
def test_las_filas_de_yfinance_siguen_llamandose_asi(ticker):
    estados, motivo = mercado.estados(ticker)
    assert motivo == "ok"
    _, anuales = lineas_de(estados)
    vacias = [linea for linea in FILAS if anuales[linea].isna().all()]
    assert vacias == []


def test_el_bono_m_es_la_serie_buena(tmp_path):
    clave = os.environ.get("BANXICO_TOKEN")
    if not clave:
        pytest.skip("sin BANXICO_TOKEN")
    url = f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{divisas.SERIE_BONO_M_10}"
    peticion = urllib.request.Request(url, headers={"Bmx-Token": clave, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=20) as respuesta:
        titulo = json.loads(respuesta.read().decode("utf-8"))["bmx"]["series"][0]["titulo"]
    normalizado = " ".join(titulo.split()).lower()
    assert "tasa de rendimiento" in normalizado
    assert "bono tasa fija 10 años" in normalizado
    valor, motivo, _ = divisas.bono_m(clave, raiz=tmp_path)
    # En tanto por uno: un 9 % es 0,09. Fuera de esto es la serie equivocada.
    assert motivo == "ok" and 0.02 < valor < 0.20


def test_walmex_de_punta_a_punta():
    a = analizar("WALMEX.MX", panel=None)
    assert (a.clase, a.sector) == ("sin_sec", "Consumer Staples")
    assert a.entradas.divisa.moneda_valoracion == "MXN"
    assert a.entradas.divisa.indice_beta == "^MXX"
    json.dumps(a.valoracion, allow_nan=False)
    if os.environ.get("BANXICO_TOKEN"):
        assert a.valoracion["supuestos"]["r_f"]["procedencia"]["fuente"] == "bono_m_10"
    else:
        assert a.valoracion["motivo"] == "sin_bono_m"


def test_tsm_se_valora_en_dolares_sin_aviso_de_adr():
    _con_edgar()
    a = analizar("TSM", panel=None)
    assert a.clase == "extranjera_sec"
    assert a.entradas.divisa.convertida and a.entradas.divisa.moneda_estados == "TWD"
    assert not divisas.adr_dudosa(a.entradas.cociente_adr)
    json.dumps(a.valoracion, allow_nan=False)
```

`test_walmex_de_punta_a_punta` escribe el Bono M en la caché de Banxico de verdad (`seguimiento/.cache/`), porque `analizar` no expone la carpeta: es un dato válido, el mismo que guardaría la app.

- [ ] **Step 2: Correrlos**

Run: `uv run pytest tests/test_analizador_red.py -v -m red`
Expected: todos pasan o se omiten por falta de credenciales; ninguno falla. Si uno de las filas de yfinance falla, **no** cambies `FILAS` en silencio: yfinance renombró una fila, y el cambio va al spec con su fecha.

- [ ] **Step 3: Comprobar que la suite normal los excluye**

Run: `uv run pytest tests/test_analizador_red.py -q -m "not red"`
Expected: `12 deselected`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_analizador_red.py
git commit -m "test: el analizador contra yfinance, EDGAR y Banxico vivos (red)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Sabotaje de las guardas

Cada sabotaje se aplica, se corre el test indicado, se comprueba que **falla**, y se deshace con `git checkout -- <fichero>`. No se commitea nada. Si un sabotaje no tumba ningún test, el trabajo no es repetirlo: es averiguar qué otra cosa está devolviendo la respuesta correcta, y escribir el test que falta (ése sí se commitea).

| # | Sabotaje | Test que debe caer |
|---|---|---|
| 1 | En `resolver.normalizar`, quita la rama del sufijo: todo punto pasa a guion | `test_normalizar[WALMEX.MX-WALMEX.MX]` |
| 2 | En `resolver.resolver`, pregunta a EDGAR también con sufijo de bolsa (quita `and not tiene_sufijo(ticker)`) | `test_un_ticker_con_sufijo_de_bolsa_no_se_pregunta_a_edgar` |
| 3 | En `resolver.formularios_sec`, guarda en caché el `None` de una consulta fallida | `test_sin_red_y_sin_nada_guardado_lo_dice` |
| 4 | En `lineas_yf.lineas_desde_estados`, quita el cambio de signo del capex | `test_el_capex_llega_en_positivo_como_en_la_sec` |
| 5 | `rejilla_trimestral` devuelve `lineas` sin tocar | `test_el_trimestre_que_falta_tiene_su_fila_vacia` y `test_el_crecimiento_compara_con_el_mismo_trimestre_aunque_falte_uno` |
| 6 | En `rellenar_desde_anual`, quita la guarda del doble o la mitad de la media | `test_una_media_que_saldria_absurda_no_se_rellena` |
| 7 | `kpis_trimestrales` no quita la fila que sólo ocupaba su sitio | `test_la_fila_que_solo_ocupaba_su_sitio_no_sale` |
| 8 | En `fundamentos_anuales`, `continue` en vez de `break` al encontrar un año que falta | `test_un_ano_que_falta_corta_la_serie` |
| 9 | En `divisas.convertir`, deja `deuda_total` sin convertir | `test_convertir_multiplica_todo_lo_que_es_dinero` |
| 10 | En `divisas.divisa`, el índice es siempre `mercado.INDICE` | `test_walmex_se_valora_en_pesos_contra_el_ipc_sin_convertir` |
| 11 | En `supuestos.aplicar`, no recalcula `k_e` | `test_mover_la_beta_recalcula_el_capital_propio_y_el_de_capital` |
| 12 | Añade `"k_e"` a `MOVIBLES` | `test_lo_derivado_no_se_mueve_a_mano` |
| 13 | En `referencia.frente_al_sector`, quita el filtro de las filas posteriores al panel | `test_las_filas_posteriores_al_panel_no_entran` |
| 14 | En `kpis.kpis_yf`, quita la conversión del precio a la moneda de los estados | `test_el_precio_va_en_la_moneda_de_los_estados_al_tipo_de_cada_fecha` |
| 15 | En `valorar.supuestos_de`, sin tasa libre usa 0 en vez de devolver None | `test_una_emisora_en_pesos_sin_bono_m_no_se_valora_hasta_que_se_pone_la_tasa` |
| 16 | En `mercado.estados`, guarda también los seis vacíos | `test_seis_estados_vacios_no_se_guardan` |
| 17 | En `ranking.run.construir_ranking`, no quites las columnas `z_` del panel | `test_el_resultado_lleva_el_panel_crudo_con_su_sector` |
| 18 | En `analisis.analizar`, quita el `try` | `test_un_defecto_en_un_ticker_no_tumba_a_los_demas_y_deja_traza` |
| 19 | En `medidores_valoracion._movido`, ignora `programa` y di siempre «movido por ti» | `test_un_supuesto_movido_dice_lo_que_decia_el_programa` |

- [ ] **Step 1: Aplicar cada sabotaje, correr su test y deshacerlo**

Para cada fila: aplica el cambio, corre `uv run pytest <fichero del test> -q`, anota qué cae, y `git checkout -- <fichero saboteado>`.

- [ ] **Step 2: Comprobar que todo quedó como estaba**

Run: `git status --short`
Expected: vacío, salvo un test nuevo commiteado si algún sabotaje no tumbó nada.

---

### Task 17: Suite completa y recorrido con datos reales

**Files:**
- Create: `scripts/sondear_analizador.py`

- [ ] **Step 1: La suite normal entera**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: todo verde. El total es el de antes de empezar (2791 pasando, 5 omitidos) más los tests nuevos de este plan. Si algo que no es del analizador falla, es una regresión de este trabajo: arréglala antes de seguir.

- [ ] **Step 2: Escribir el script del recorrido**

`scripts/sondear_analizador.py`:

```python
"""El Analizador sobre tickers reales, sin pantalla: qué es cada uno y cómo sale.

Uso, desde programa/:
    uv run python scripts/sondear_analizador.py MU WALMEX.MX TSM JPM SPY BRK-B RY.TO

Lee las credenciales guardadas en Perfil (EDGAR, Banxico), como la app. Compara
contra `salidas/panel.parquet` si existe; si no, construye el panel en memoria
con la misma corrida que «Generar gratis» (unos dos minutos con la caché
llena) y no escribe nada en `salidas/`: las fichas de los candidatos son del
usuario.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import credenciales  # noqa: E402
from analizador.analisis import analizar  # noqa: E402
from analizador.divisas import adr_dudosa  # noqa: E402
from analizador.referencia import cargar_panel  # noqa: E402
from analizador.resolver import separar  # noqa: E402
from fundamentals.sectors import load_sectors  # noqa: E402


def _panel():
    panel, fecha = cargar_panel()
    if panel is not None:
        return panel, f"salidas/panel.parquet del {fecha}"
    from ranking.run import construir_ranking

    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    return resultado.panel, "construido en memoria, sin escribir nada"


def _fila(ticker, a, segundos):
    v = a.valoracion or {}
    e = a.entradas
    ref = a.referencia
    puesto = "-" if ref is None or ref.puesto is None else f"{ref.puesto}/{ref.supervivientes}"
    estado_ref = a.motivo_referencia or (ref.exclusion if ref else None) or "ok"
    r_f = v.get("supuestos", {}).get("r_f", {}).get("procedencia", {}).get("fuente", "-")
    return "  ".join(
        [
            f"{ticker:<10}",
            f"clase={a.clase or '-'}",
            f"motivo={a.motivo or '-'}",
            f"sector={a.sector or '-'} ({a.fuente_sector or '-'})",
            f"puesto={puesto}",
            f"ref={estado_ref}",
            f"moneda={e.divisa.moneda_valoracion if e else '-'}",
            f"r_f={r_f}",
            f"metodo={v.get('metodo', '-')}",
            f"veredicto={v.get('veredicto') or v.get('motivo') or '-'}",
            f"adr={'DUDOSA' if e and adr_dudosa(e.cociente_adr) else 'ok'}",
            f"{segundos:.1f}s",
        ]
    )


def main(argv: "list[str]") -> None:
    credenciales.aplicar(credenciales.cargar())
    tickers, invalidos = separar(" ".join(argv))
    if invalidos:
        print("Sin forma de ticker:", ", ".join(invalidos))
    panel, origen = _panel()
    print(f"Panel de referencia: {origen}\n")
    tabla = load_sectors()
    for ticker in tickers:
        inicio = time.perf_counter()
        analisis = analizar(ticker, panel, tabla)
        print(_fila(ticker, analisis, time.perf_counter() - inicio))


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 3: Correrlo**

Run: `uv run python scripts/sondear_analizador.py MU WALMEX.MX TSM JPM SPY BRK-B RY.TO`
Expected, ticker a ticker:
- **MU**: `clase=sec`, en el panel, con puesto, `moneda=USD`, `r_f=tesoro_10`, `metodo=flujos`, un veredicto.
- **WALMEX.MX**: `clase=sin_sec`, `sector=Consumer Staples (yahoo)`, con puesto o una exclusión con nombre, `moneda=MXN`, `r_f=bono_m_10` (o `veredicto=sin_bono_m` sin token de Banxico).
- **TSM**: `clase=extranjera_sec`, `sector=Information Technology (yahoo)`, `moneda=USD`, `adr=ok`.
- **JPM**: `clase=sec`, en el panel con la exclusión que le pone el ranking (`pilar_sin_datos`), `metodo=residual`.
- **SPY**: `clase=etf`, sin nada más.
- **BRK-B**: `clase=sec`, `metodo=residual` (*Insurance - Diversified*).
- **RY.TO**: `clase=sin_sec` (sufijo de bolsa), `sector=Financials (yahoo)`, `moneda=USD` convertida desde CAD, `metodo=residual`.

Anota en el informe la línea de cada uno y los segundos. Un ticker que salga distinto de lo esperado **no se arregla aquí**: se anota, se mira por qué y, si es un defecto, se arregla con su test antes de la Task 18.

- [ ] **Step 4: Commit**

```bash
git add scripts/sondear_analizador.py
git commit -m "feat: script para recorrer el analizador sobre tickers reales, sin pantalla

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: El spec y CONTEXTO.md

**Files:**
- Modify: `docs/superpowers/specs/2026-10-12-analizador-individual-design.md`
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Enmiendas al spec**

1. **Estado**, en la cabecera:

```
**Estado:** N1 (los datos de cualquier ticker) implementado en la rama
`feat/analizador-individual`; N2 (la pantalla) y N3 (la IA) pendientes
```

2. Al final del spec, una sección nueva:

```markdown
## Enmiendas del 2026-10-14, al planear y ejecutar N1

N se parte en tres planes que se ejecutan en orden: **N1, los datos** (`docs/superpowers/plans/2026-10-14-analizador-n1-datos.md`), **N2, la pantalla** y **N3, la IA**. El sondeo de yfinance, EDGAR y Banxico del 2026-10-14 cambió esto:
```

seguida de los once puntos de «Lo que el sondeo del 2026-10-14 cambió del spec» de este plan, uno por párrafo y con sus cifras, y de estos dos:

```markdown
- **Un motivo nuevo para una valoración que no se calcula**: `sin_bono_m`
  (una emisora en pesos sin el Bono M, normalmente por no tener token de
  Banxico; el deslizador de la tasa libre lo resuelve). `sin_tasa_libre` no
  servía: su etiqueta culpa a Yahoo. Un tipo de cambio que no llega es
  `sin_red`.
- **La tabla de «Cachés y frescura»**: los estados de yfinance, la identidad y
  los tipos de cambio van en `valoracion/.cache/` (estados un día, identidad
  quince minutos, tipos de cambio un día), y `analizador/.cache/` sólo guarda
  los formularios de EDGAR (treinta días).
```

3. En «Cachés y frescura», cambia la fila de los estados de yfinance a `valoracion/.cache/` y añade la de los formularios de EDGAR, con una referencia a la enmienda.

- [ ] **Step 2: CONTEXTO.md**

1. En «Descomposición en sub-proyectos», la fila de N:

```markdown
| N | Analizador individual | La mecánica de candidatos para cualquier ticker, con gráfico, noticias e IA | 🔨 **en curso**: N1 (datos) hecho; N2 (pantalla) y N3 (IA) pendientes |
```

2. Antes de «La auditoría», una sección `## Sub-proyecto N, parte 1: los datos de cualquier ticker` con:
   - **Qué entrega**: el paquete `analizador/` (resolver, sectores, lineas_yf, divisas, referencia, kpis, valorar, analisis), las fuentes nuevas de `valoracion/mercado.py`, `supuestos.aplicar`, `dcf.sensibilidad`, `salidas/panel.parquet` y `scripts/sondear_analizador.py`. Sin pantalla.
   - **Decisiones que no hay que relitigar**: las once de la enmienda del spec, en una línea cada una.
   - **Defectos encontrados**: los que salgan al ejecutar este plan, en una tabla «Defecto | Cómo se detectó».
   - **El recorrido de la Task 17**: la línea de cada ticker.
   - **Lo que queda para N2 y N3**: la pantalla entera (absorbe Noticias y calendario), el gráfico, los deslizadores con `aplicar` y `sensibilidad`, «Analizar a fondo», el gate con `Anadido.valoracion`, y los cuatro bloques de IA con su archivo `analisis/`.

3. La cabecera: «Última actualización», el número de tests y el bloque «Al retomar» (N1 en `feat/analizador-individual`, sin fusionar; lo siguiente es el plan de N2).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-12-analizador-individual-design.md CONTEXTO.md
git commit -m "docs: N1 hecho, con sus enmiendas al spec y CONTEXTO al dia

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cobertura del spec

| Sección del spec | Dónde |
|---|---|
| Las cuatro clases de ticker | Tasks 3, 4 |
| La forma del ticker (sufijos de bolsa) | Task 1 |
| Empresas de la SEC: los mismos números que M | Tasks 12, 13 (`desde_sec`, `build_panel`) |
| `lineas_yf`: filas, signo del capex, TTM con cuatro trimestres seguidos, `financialCurrency` | Tasks 3, 5, 6 |
| Divisas: USD, MXN con Bono M e IPC, otras convertidas, la ADR | Task 7, 13 |
| La referencia sectorial, el panel en disco, el puesto hipotético, la guarda que lo dejaría fuera | Tasks 10, 11, 12 |
| El sector fuera del S&P 500 (tabla congelada) | Task 2 |
| `aplicar` y `sensibilidad` (movidos de M) | Tasks 8, 9 |
| Cachés y frescura | Tasks 3, 4, 7 |
| Errores: ticker desconocido, tipo no soportado, falla la red, sin panel, sin token de Banxico | Tasks 4, 11, 13, 14 |
| Cómo se prueba, puntos 2 a 5, 10 y 11 | Tasks 1, 5–7, 11, 15, 16 |
| La pantalla, el gráfico, el menú, «Analizar a fondo», el gate | **N2** |
| La IA y su archivo; cómo se prueba, puntos 1 (sondeo del MD&A), 6 a 8 | **N3** |
| Cómo se prueba, punto 9 (el gate) y 12 (recorrido con la app) | **N2** y **N3** |
