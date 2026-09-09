# La entrada al seguimiento — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que se pueda llegar al seguimiento desde la portada y desde los dos
botones que hoy piden usar el menú, y que estrenar un portafolio sea una
pantalla que propone la compra y la confirma, en vez de un libro vacío con el
formulario escondido.

**Architecture:** Lógica nueva en `seguimiento/alta.py` (sin Streamlit) y
pantalla nueva en `vistas/estrenar.py` (sin lógica), igual que F, G y H. El alta
sale de `vistas/seguimiento.py` a propósito: ese fichero ya tiene 440 líneas y
el sub-proyecto K lo va a rehacer entero.

**Tech Stack:** Python 3.12, Streamlit, pandas, pytest. Ninguna dependencia nueva.

---

## Antes de empezar: tres cosas que cuestan una tarea si se ignoran

**1. `UV_LINK_MODE=copy` es obligatorio en TODOS los comandos de uv.** El repo
vive en OneDrive y `uv` no puede hacer enlaces duros ahí. Sin la variable,
instalar `pyarrow` revienta con `os error 396`.

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

**2. La primera línea de cada bloque de código es un comentario con la ruta, no
un docstring.** Escribirla como `"""ruta.py"""` encima del docstring real deja
dos literales seguidos: Python toma el primero como `__doc__` y **descarta el
segundo en silencio**, así que el módulo pierde toda su documentación sin que
nada falle.

**3. Las firmas que vas a usar, ya comprobadas contra el código:**

```python
# seguimiento/libro.py
Asiento(id, fecha, tipo, ticker=None, acciones=None, precio=None,
        importe=0.0, comision=0.0, precio_estimado=False, anula=None, nota="")
Objetivo(fecha, base, portafolio: dict, veredicto: dict = {})
Libro(nombre, creado, moneda="USD", objetivos=(), asientos=())
guardar(libro, directorio=None) -> Path
anadir(libro, asiento, hoy=None, financiar=False) -> tuple[Libro, list[Asiento]]
desde_portafolio(nombre, portafolio, base, acta=None, ahora=None) -> Libro
BASES = frozenset({"equal_weight", "estrategia"})

# seguimiento/precios.py
descargar(tickers: list[str], desde: str, hasta: str | None = None) -> Historia
cierre_en(historia, ticker: str, fecha: str) -> float | None

# cartera.py
Posicion(ticker: str, peso: float)
Portafolio(nombre, fecha, posiciones, horizonte, estrategia, peso_min,
           peso_max, permitir_cortos, shrinkage, metricas={}, nota="")

# El traspaso entre pantallas, que ya existe:
st.session_state.portafolio_a_seguir = p   # vistas/portafolios.py:83
```

**La suite entera está en 1.079 pasando, 4 omitidos y 8 deselected.** Cada tarea
dice cuántos debe haber después.

---

## Task 1: Los dos campos nuevos del libro

**Files:**
- Modify: `seguimiento/libro.py`
- Test: `tests/test_seguimiento_libro_alta.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
# tests/test_seguimiento_libro_alta.py
import json

import pytest

from seguimiento import libro


def _libro(**kwargs):
    return libro.Libro(nombre="prueba", creado="2026-01-01", **kwargs)


def test_por_defecto_no_hay_fracciones_ni_plan():
    l = _libro()
    assert l.fracciones is False
    assert l.aportacion_prevista is None


def test_se_guardan_y_se_leen(tmp_path):
    l = _libro(
        fracciones=True,
        aportacion_prevista=libro.AportacionPrevista(500.0, "mensual"),
    )
    vuelto = libro.cargar(libro.guardar(l, tmp_path))
    assert vuelto.fracciones is True
    assert vuelto.aportacion_prevista == libro.AportacionPrevista(500.0, "mensual")


def test_un_libro_viejo_sin_los_campos_se_abre_igual(tmp_path):
    """Los libros que ya existen en el disco del usuario no pueden romperse.

    `cargar` lee campo a campo con `crudo.get(...)` -- asi entraron `moneda` y
    `objetivos` -- y esta prueba fija que sigue siendo asi. Un fichero escrito
    antes de esta tarea no tiene las claves nuevas.
    """
    ruta = tmp_path / "viejo.json"
    ruta.write_text(
        json.dumps({"nombre": "viejo", "creado": "2026-01-01", "asientos": []}),
        encoding="utf-8",
    )
    vuelto = libro.cargar(ruta)
    assert vuelto.fracciones is False
    assert vuelto.aportacion_prevista is None


def test_una_cadencia_inventada_no_se_acepta():
    with pytest.raises(ValueError):
        libro.AportacionPrevista(500.0, "cuando me apetezca")


def test_un_importe_previsto_no_positivo_no_se_acepta():
    """Prever aportar cero o menos no es prever nada; es None."""
    with pytest.raises(ValueError):
        libro.AportacionPrevista(0.0, "mensual")
    with pytest.raises(ValueError):
        libro.AportacionPrevista(-100.0, "mensual")


def test_un_importe_previsto_no_finito_no_se_acepta():
    """Misma guarda que los asientos: NaN atraviesa toda comparacion.

    `nan <= 0` es False y NaN es truthy, asi que ninguna guarda de «mayor que
    cero» lo caza. Y entra desde disco sin que nadie lo teclee, porque
    `json.loads` acepta el literal NaN.
    """
    with pytest.raises(ValueError):
        libro.AportacionPrevista(float("nan"), "mensual")
    with pytest.raises(ValueError):
        libro.AportacionPrevista(float("inf"), "mensual")


def test_una_aportacion_prevista_corrupta_en_disco_se_nombra(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text(
        json.dumps({
            "nombre": "malo", "creado": "2026-01-01", "asientos": [],
            "aportacion_prevista": {"importe": 500.0, "cadencia": "semanal"},
        }),
        encoding="utf-8",
    )
    with pytest.raises(libro.LibroIlegible):
        libro.cargar(ruta)


def test_prevista_no_es_un_asiento_de_aportacion():
    """El nombre lleva «prevista» para que no se confundan.

    Una es dinero que entro y vive en `asientos`; la otra es un plan y vive en
    el libro. Si alguien fusionara las dos, el capital aportado incluiria
    dinero que nunca llego y el rendimiento saldria hundido sin causa visible.
    """
    l = _libro(aportacion_prevista=libro.AportacionPrevista(500.0, "mensual"))
    assert l.asientos == ()
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro_alta.py -q`
Expected: FAIL con `AttributeError: module 'seguimiento.libro' has no attribute 'AportacionPrevista'`

- [ ] **Step 3: Añade la clase y los campos**

En `seguimiento/libro.py`, junto a las otras dataclases:

```python
CADENCIAS = frozenset({"mensual", "trimestral", "anual"})


@dataclass(frozen=True)
class AportacionPrevista:
    """El plan de aportar, que NO es un asiento de aportacion.

    El nombre lleva «prevista» a proposito: `Asiento.tipo == "aportacion"` ya
    existe y es un hecho ocurrido. Llamar igual a las dos cosas invita justo a
    la confusion que todo este paquete evita -- una es dinero que entro, la
    otra es dinero que el usuario dice que entrara. Fusionarlas inflaria el
    capital aportado con dinero que nunca llego, y hundiria el rendimiento sin
    causa visible.

    No se aporta cero: eso es no aportar, y se representa con None.
    """

    importe: float
    cadencia: str

    def __post_init__(self):
        _finito(self.importe, "el importe previsto")
        if self.importe <= 0:
            raise ValueError(
                "el importe previsto tiene que ser mayor que cero; para no "
                "aportar, deja la aportacion prevista en None"
            )
        if self.cadencia not in CADENCIAS:
            raise ValueError(
                f"cadencia desconocida: {self.cadencia!r}; "
                f"las validas son {sorted(CADENCIAS)}"
            )
```

En la dataclase `Libro`, después de `moneda`:

```python
    # Si el broker admite fracciones de accion. Decide si el reparto del
    # capital redondea hacia abajo y deja sobrante, o si cuadra al centimo.
    fracciones: bool = False
    # El plan, no un hecho. Rebalanceo lo usa para no volver a preguntarlo.
    # None cuando el usuario dice que no hara aportaciones.
    aportacion_prevista: "AportacionPrevista | None" = None
```

En `cargar`, dentro del `Libro(...)` que ya construye:

```python
            fracciones=bool(crudo.get("fracciones", False)),
            # `or None` y no un ternario: un diccionario vacio en disco
            # significa «sin plan», igual que la clave ausente.
            aportacion_prevista=(
                AportacionPrevista(**crudo["aportacion_prevista"])
                if crudo.get("aportacion_prevista") else None
            ),
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro_alta.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Sabotea dos guardas — PASO OBLIGATORIO**

1. Quita el `if self.cadencia not in CADENCIAS`.
   Expected: cae `test_una_cadencia_inventada_no_se_acepta`.
2. Cambia `crudo.get("fracciones", False)` por `crudo["fracciones"]`.
   Expected: cae `test_un_libro_viejo_sin_los_campos_se_abre_igual`.

**Si un sabotaje no tumba nada, no lo rehagas: averigua qué otra cosa está
devolviendo la respuesta correcta.** Pasó dos veces en el sub-proyecto H —una
jerarquía de excepciones, el texto de un error ajeno— y las dos veces el
problema estaba en el sabotaje, no en la guarda.

Deshaz los cambios y confirma que los 8 vuelven a pasar. Reporta qué cayó.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/libro.py tests/test_seguimiento_libro_alta.py
git commit -m "feat: el libro guarda si hay fracciones y la aportacion prevista"
```

Termina el mensaje con:
```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

**Suite tras esta tarea:** 1.087 pasando (1.079 + 8).

---

## Task 2: El reparto del capital

**Files:**
- Create: `seguimiento/alta.py`
- Test: `tests/test_seguimiento_alta_reparto.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
# tests/test_seguimiento_alta_reparto.py
from seguimiento import alta

PESOS = {"AAPL": 0.5, "MSFT": 0.3, "NVDA": 0.2}
PRECIOS = {"AAPL": 200.0, "MSFT": 400.0, "NVDA": 100.0}


def test_con_fracciones_se_gasta_el_capital_entero():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    assert round(r.gastado, 2) == 10000.00
    assert round(r.sobrante, 2) == 0.00


def test_con_fracciones_cada_uno_recibe_su_peso():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert round(por_ticker["AAPL"].acciones, 6) == 25.0    # 5000 / 200
    assert round(por_ticker["MSFT"].acciones, 6) == 7.5     # 3000 / 400
    assert round(por_ticker["NVDA"].acciones, 6) == 20.0    # 2000 / 100


def test_con_acciones_enteras_sobra_algo_y_se_informa():
    """MSFT: 3000/400 = 7,5 acciones -> 7, y sobran 200."""
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=False)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert por_ticker["MSFT"].acciones == 7
    assert round(r.sobrante, 2) == 200.00
    assert round(r.gastado + r.sobrante, 2) == 10000.00


def test_el_sobrante_no_se_redistribuye():
    """Repartirlo entre los demas romperia los pesos recien elegidos."""
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=False)
    por_ticker = {l.ticker: l for l in r.lineas}
    assert por_ticker["AAPL"].acciones == 25    # 5000/200 exacto, no 26
    assert por_ticker["NVDA"].acciones == 20    # 2000/100 exacto, no 21


def test_un_peso_pequeno_con_precio_alto_da_cero_y_SE_NOMBRA():
    """Con 1.000 y un 2%, una accion de 600 no cabe.

    El activo tiene que salir en la tabla con cero y su motivo. Que un activo
    del plan desaparezca sin decir nada es el defecto que ya costo una
    correccion en el sub-proyecto G.
    """
    r = alta.repartir(
        1000.0, {"AAPL": 0.98, "BRK-A": 0.02}, {"AAPL": 100.0, "BRK-A": 600.0},
        fracciones=False,
    )
    linea = [l for l in r.lineas if l.ticker == "BRK-A"][0]
    assert linea.acciones == 0
    assert linea.motivo != ""
    assert "600" in linea.motivo or "alcanza" in linea.motivo.lower()


def test_un_activo_sin_precio_vuelve_nombrado_y_sin_acciones():
    r = alta.repartir(
        10000.0, PESOS, {"AAPL": 200.0, "MSFT": None, "NVDA": 100.0},
        fracciones=True,
    )
    linea = [l for l in r.lineas if l.ticker == "MSFT"][0]
    assert linea.acciones == 0
    assert linea.precio is None
    assert linea.motivo != ""
    assert "MSFT" in r.sin_precio


def test_el_capital_del_que_no_tiene_precio_queda_como_sobrante():
    """No se reparte entre los demas: nadie decidio darles mas peso."""
    r = alta.repartir(
        10000.0, PESOS, {"AAPL": 200.0, "MSFT": None, "NVDA": 100.0},
        fracciones=True,
    )
    assert round(r.sobrante, 2) == 3000.00     # el 30% de MSFT


def test_capital_cero_no_calcula_nada():
    r = alta.repartir(0.0, PESOS, PRECIOS, fracciones=True)
    assert r.lineas == ()
    assert r.sobrante == 0.0


def test_capital_negativo_no_calcula_nada():
    r = alta.repartir(-500.0, PESOS, PRECIOS, fracciones=True)
    assert r.lineas == ()


def test_sin_pesos_no_calcula_nada():
    assert alta.repartir(10000.0, {}, PRECIOS, fracciones=True).lineas == ()


def test_las_lineas_salen_de_mayor_a_menor_peso():
    r = alta.repartir(10000.0, PESOS, PRECIOS, fracciones=True)
    assert [l.ticker for l in r.lineas] == ["AAPL", "MSFT", "NVDA"]


def test_los_pesos_se_normalizan_si_no_suman_uno():
    """Un objetivo puede venir con pesos que no cierran exactamente."""
    r = alta.repartir(
        1000.0, {"AAPL": 0.4, "MSFT": 0.4}, {"AAPL": 100.0, "MSFT": 100.0},
        fracciones=True,
    )
    assert round(r.gastado, 2) == 1000.00
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_alta_reparto.py -q`
Expected: FAIL con `ImportError: cannot import name 'alta'`

- [ ] **Step 3: Escribe el módulo**

```python
# seguimiento/alta.py
"""Repartir un capital entre los pesos de un plan, y decirlo entero.

Esto **no escribe nada en el libro**. Produce una propuesta: cuanto comprar de
cada activo con el dinero que hay. Es lo mismo que hace `rebalanceo.propuesta`
con la aportacion, y por la misma razon -- entre mirar la propuesta y ejecutarla
en el broker, el precio se mueve, asi que lo que acabe en el libro tiene que
salir de lo que el usuario confirme, no de esta division.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Linea:
    """Un activo del plan, con lo que le tocaria y lo que de verdad cabe."""

    ticker: str
    peso: float
    objetivo: float          # capital * peso
    precio: "float | None"
    acciones: float
    importe: float           # acciones * precio
    motivo: str              # "" cuando no hay nada que explicar


@dataclass(frozen=True)
class Reparto:
    lineas: "tuple[Linea, ...]"
    gastado: float
    sobrante: float
    sin_precio: "tuple[str, ...]"


def repartir(
    capital: float,
    pesos: "dict[str, float]",
    precios: "dict[str, float | None]",
    fracciones: bool,
) -> Reparto:
    """What to buy of each asset with this much money.

    **El sobrante no se redistribuye.** Con acciones enteras casi siempre sobra
    algo, y repartirlo entre los demas romperia los pesos que el usuario acaba
    de elegir: nadie decidio darle mas a nadie. Queda como efectivo sin
    asignar, que es exactamente lo que es, y Rebalanceo ya sabe proponer donde
    ponerlo.

    **Un activo que no cabe sale igual, con cero y su motivo.** Con 1.000 de
    capital, un peso del 2% y una accion de 600, salen cero acciones. Omitir la
    linea dejaria un plan de tres activos mostrando dos, sin que nada lo diga.
    """
    if capital <= 0 or not pesos:
        return Reparto((), 0.0, 0.0, ())

    total = sum(pesos.values())
    if total <= 0:
        return Reparto((), 0.0, 0.0, ())

    lineas, sin_precio, gastado = [], [], 0.0
    for ticker, peso in sorted(pesos.items(), key=lambda kv: -kv[1]):
        parte = peso / total
        objetivo = capital * parte
        precio = precios.get(ticker)

        if precio is None or precio <= 0:
            sin_precio.append(ticker)
            lineas.append(Linea(
                ticker, parte, objetivo, None, 0.0, 0.0,
                "sin precio: no se le asignan acciones a ciegas",
            ))
            continue

        crudas = objetivo / precio
        acciones = crudas if fracciones else float(math.floor(crudas))
        importe = acciones * precio
        motivo = ""
        if acciones == 0:
            motivo = (
                f"con {objetivo:,.2f} no alcanza para una accion de "
                f"{precio:,.2f}"
            )
        lineas.append(
            Linea(ticker, parte, objetivo, precio, acciones, importe, motivo)
        )
        gastado += importe

    return Reparto(
        lineas=tuple(lineas),
        gastado=gastado,
        sobrante=capital - gastado,
        sin_precio=tuple(sin_precio),
    )
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_alta_reparto.py -q`
Expected: PASS, 12 tests

- [ ] **Step 5: Sabotea el reparto — PASO OBLIGATORIO**

1. Sustituye `acciones = crudas if fracciones else float(math.floor(crudas))`
   por `acciones = crudas`, o sea ignora el modo entero.
   Expected: cae `test_con_acciones_enteras_sobra_algo_y_se_informa`.
2. Cambia el `continue` de la rama «sin precio» para que la línea **no** se
   añada a `lineas`.
   Expected: cae `test_un_activo_sin_precio_vuelve_nombrado_y_sin_acciones`.

Deshaz los dos y confirma que los 12 vuelven a pasar. Reporta qué cayó.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/alta.py tests/test_seguimiento_alta_reparto.py
git commit -m "feat: repartir el capital inicial, con el sobrante a la vista"
```

**Suite tras esta tarea:** 1.099 pasando (1.087 + 12).

---

## Task 3: De la tabla confirmada a los asientos

Es la única pieza de J que escribe en el libro, y por eso lleva sus propias
guardas.

**Files:**
- Modify: `seguimiento/alta.py`
- Test: `tests/test_seguimiento_alta_asientos.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
# tests/test_seguimiento_alta_asientos.py
import pytest

from seguimiento import alta

FILAS = [
    {"ticker": "AAPL", "acciones": 25.0, "precio": 200.0, "comision": 1.0},
    {"ticker": "MSFT", "acciones": 7.0, "precio": 400.0, "comision": 1.0},
]


def test_una_compra_por_fila_mas_la_aportacion():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    tipos = [a.tipo for a in asientos]
    assert tipos.count("aportacion") == 1
    assert tipos.count("compra") == 2


def test_la_aportacion_va_primero_y_por_el_capital_declarado():
    """Si la compra se aplicase antes, el efectivo pasaria por negativo."""
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    assert asientos[0].tipo == "aportacion"
    assert asientos[0].importe == 10000.0


def test_sin_capital_declarado_la_aportacion_se_deriva():
    """La carga manual no declara capital: se deriva de lo comprado.

    Suma de compras mas comisiones, para que el libro nazca con cero efectivo
    sin asignar. Nadie ha dicho que tenga dinero parado, y suponerlo falsearia
    la TIR desde el primer dia.
    """
    asientos = alta.asientos_de(FILAS, capital=None, fecha="2026-03-02")
    esperado = 25 * 200.0 + 7 * 400.0 + 2.0
    assert asientos[0].importe == esperado


def test_el_importe_de_cada_compra_es_acciones_por_precio():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    compra = [a for a in asientos if a.ticker == "AAPL"][0]
    assert compra.importe == 5000.0
    assert compra.acciones == 25.0
    assert compra.precio == 200.0
    assert compra.comision == 1.0


def test_gastar_mas_que_la_aportacion_se_rechaza_ANTES_de_escribir():
    """Dejaria el efectivo en negativo, y `anadir` lo rechazaria despues.

    Se comprueba aqui para dar un mensaje que se entienda, en vez del de una
    guarda interna que habla de saldos.
    """
    with pytest.raises(alta.AltaInvalida) as error:
        alta.asientos_de(FILAS, capital=1000.0, fecha="2026-03-02")
    # Se comprueba que el mensaje dice CUANTO falta, no un numero literal:
    # `f"{1000.0:,.2f}"` da "1,000.00" con separadores ingleses, asi que
    # buscar "1.000" o "1000" fallaria por el formato y no por la guarda.
    assert "Faltan" in str(error.value)
    # 25*200 + 7*400 + 2 de comisiones = 7.802 de compras, menos 1.000
    # aportados. Calculado a mano y comprobado: los tres casos mal calculados
    # del sub-proyecto G salieron de no hacer esta cuenta.
    assert "6,802" in str(error.value)


def test_una_fila_sin_ticker_se_omite_nombrandola():
    filas = FILAS + [{"ticker": "", "acciones": 5.0, "precio": 10.0}]
    asientos = alta.asientos_de(filas, capital=10000.0, fecha="2026-03-02")
    assert len([a for a in asientos if a.tipo == "compra"]) == 2


def test_una_fila_con_cero_acciones_se_omite():
    """Es la linea del activo que no cabia. No se escribe media compra."""
    filas = FILAS + [{"ticker": "BRK-A", "acciones": 0.0, "precio": 600.0}]
    asientos = alta.asientos_de(filas, capital=10000.0, fecha="2026-03-02")
    assert "BRK-A" not in [a.ticker for a in asientos]


def test_dos_filas_del_mismo_ticker_se_aceptan():
    """Comprar en dos tramos el mismo dia es normal; el coste medio lo resuelve."""
    filas = FILAS + [
        {"ticker": "AAPL", "acciones": 5.0, "precio": 201.0, "comision": 1.0}
    ]
    asientos = alta.asientos_de(filas, capital=12000.0, fecha="2026-03-02")
    assert len([a for a in asientos if a.ticker == "AAPL"]) == 2


def test_todas_las_filas_vacias_es_un_error_y_no_un_libro_vacio():
    """Crear un libro sin una sola compra deja el callejon sin salida que F ya
    tuvo: una pantalla que dice «anade el primero» y no tiene donde."""
    with pytest.raises(alta.AltaInvalida):
        alta.asientos_de([], capital=1000.0, fecha="2026-03-02")


def test_un_precio_no_positivo_se_rechaza():
    filas = [{"ticker": "AAPL", "acciones": 1.0, "precio": 0.0}]
    with pytest.raises(alta.AltaInvalida):
        alta.asientos_de(filas, capital=100.0, fecha="2026-03-02")


def test_los_identificadores_son_distintos():
    """Dos asientos con el mismo id se pisarian al anular uno."""
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    ids = [a.id for a in asientos]
    assert len(set(ids)) == len(ids)


def test_todos_llevan_la_fecha_dada():
    asientos = alta.asientos_de(FILAS, capital=10000.0, fecha="2026-03-02")
    assert {a.fecha for a in asientos} == {"2026-03-02"}
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_alta_asientos.py -q`
Expected: FAIL con `AttributeError: module 'seguimiento.alta' has no attribute 'AltaInvalida'`

- [ ] **Step 3: Añade a `seguimiento/alta.py`**

```python
import uuid

from seguimiento.libro import Asiento


class AltaInvalida(ValueError):
    """Lo que el usuario confirmo no se puede escribir como esta."""


def asientos_de(
    filas: "list[dict]", capital: "float | None", fecha: str
) -> "tuple[Asiento, ...]":
    """The confirmed table, turned into the entries that open the book.

    `capital` es el que el usuario declaro cuando viene del optimizador, y
    **None en la carga manual**, donde no hay capital declarado y se deriva de
    lo comprado. Son casos distintos y mezclarlos deja efectivo fantasma: si en
    la carga manual se supusiera un capital redondo, la diferencia quedaria
    como dinero parado que nadie tiene, y falsearia la TIR desde el primer dia.

    La aportacion va **primero**. Si las compras se aplicasen antes, el efectivo
    pasaria por negativo y `posiciones.primer_descubierto` lo rechazaria.
    """
    compras = []
    for fila in filas:
        ticker = str(fila.get("ticker") or "").strip().upper()
        acciones = float(fila.get("acciones") or 0)
        precio = float(fila.get("precio") or 0)
        # Una fila sin ticker o sin acciones es una linea que el usuario dejo
        # en blanco, o el activo que no cabia. No se escribe media compra.
        if not ticker or acciones <= 0:
            continue
        if precio <= 0:
            raise AltaInvalida(
                f"{ticker}: el precio tiene que ser mayor que cero"
            )
        compras.append((ticker, acciones, precio,
                        float(fila.get("comision") or 0)))

    if not compras:
        raise AltaInvalida(
            "No hay ninguna compra que registrar. Un libro sin asientos no "
            "tiene nada que seguir."
        )

    coste = sum(a * p + c for _, a, p, c in compras)
    if capital is None:
        capital = coste
    elif coste > capital:
        raise AltaInvalida(
            f"Las compras suman {coste:,.2f}, mas que los {capital:,.2f} "
            f"aportados. Faltan {coste - capital:,.2f}."
        )

    asientos = [Asiento(
        id=uuid.uuid4().hex[:12], fecha=fecha, tipo="aportacion",
        importe=capital,
    )]
    asientos += [
        Asiento(
            id=uuid.uuid4().hex[:12], fecha=fecha, tipo="compra",
            ticker=ticker, acciones=acciones, precio=precio,
            importe=acciones * precio, comision=comision,
        )
        for ticker, acciones, precio, comision in compras
    ]
    return tuple(asientos)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_alta_asientos.py -q`
Expected: PASS, 12 tests

- [ ] **Step 5: Sabotea la guarda del capital — PASO OBLIGATORIO**

Quita el `elif coste > capital: raise ...`.
Expected: cae `test_gastar_mas_que_la_aportacion_se_rechaza_ANTES_de_escribir`.

Deshaz y confirma. Reporta qué cayó.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/alta.py tests/test_seguimiento_alta_asientos.py
git commit -m "feat: los asientos de apertura salen de lo que el usuario confirma"
```

**Suite tras esta tarea:** 1.111 pasando (1.099 + 12).

---

## Task 4: La pantalla de estreno

**Files:**
- Create: `vistas/estrenar.py`
- Modify: `app.py`

- [ ] **Step 1: Lee las pantallas hermanas ANTES de escribir nada**

Lee entero `vistas/rebalanceo.py` y las líneas 1–120 de `vistas/seguimiento.py`
(el bloque `pendiente = st.session_state.get("portafolio_a_seguir")` es el que
esta pantalla se lleva). Copia sus patrones.

**Trampas que ya costaron correcciones:**

1. En G, `medidores.CSS` no se inyectaba y los medidores se pintaban como texto
   plano. **Esta pantalla no lleva medidores**; no añadas ninguno.
2. En H, un libro ilegible se filtraba en silencio y la pantalla decía «no
   llevas ningún libro». Si listas libros aquí, **nómbralos**.
3. En F, `guardar` no sobrescribe nunca —a propósito— y dos altas dejaron tres
   ficheros. **Un segundo clic en «Crear libro» no puede crear otro libro.**
   Usa una marca en `st.session_state` y comprueba de verdad que funciona.

- [ ] **Step 2: Escribe la pantalla**

Tres puertas, elegidas con `st.radio` sin opción marcada por defecto:

1. **«Voy a comprar»** — pide capital y fracciones. Descarga precios con
   `precios.descargar(tickers, desde=<hace 5 días>)` y `precios.cierre_en(...)`
   (cinco días porque un fin de semana o un festivo dejan el último cierre
   fuera de una ventana de uno). Llama `alta.repartir(...)` y pinta la tabla con
   `st.dataframe`, el sobrante y los activos sin precio. Botón **«Ya la
   ejecuté»** que pasa a la puerta 2 con la propuesta precargada.

   **Sin conexión, esta puerta no puede hacer su trabajo**, y hay que decirlo en
   vez de enseñar una tabla vacía que parece un error del programa:

   ```python
   try:
       historia = precios.descargar(tickers, desde=desde)
   except Exception as e:      # la red falla de mil formas y ninguna es nuestra
       st.warning(
           f"No se pudieron traer los precios ({e}). Sin ellos no se puede "
           "calcular cuánto comprar de cada activo. Si ya compraste, usa "
           "**«Ya compré»**: ese camino no necesita precios porque los pones tú."
       )
       st.stop()
   ```
2. **«Ya compré»** — `st.data_editor` con columnas ticker, acciones, precio,
   comisión, y un `st.date_input` con la fecha común. Precargado con los tickers
   del portafolio.
3. **«Ya tenía una cartera»** — el mismo `st.data_editor` vacío, más la pregunta
   del objetivo con `st.radio(..., index=None)`: mantener la mezcla de hoy,
   repartir por igual, o ninguno por ahora.

Comunes a las tres: nombre del libro, y la aportación prevista (importe y
cadencia, o «no haré aportaciones»).

Al confirmar: `alta.asientos_de(...)`, se construye el `Libro` con `fracciones`
y `aportacion_prevista`, y se guarda con `libro.guardar`. Después,
`st.switch_page("vistas/seguimiento.py")`.

Para «mantener la mezcla de hoy» se construye un portafolio sintético:

```python
# Los pesos de hoy pasan a ser el objetivo. No hace falta tocar BASES: se
# fabrica un portafolio con esos pesos y se usa base="estrategia", que es
# «los pesos que trae el portafolio».
valor = {t: acciones[t] * precios_hoy[t] for t in acciones}
total = sum(valor.values())
sintetico = {"posiciones": [
    {"ticker": t, "peso": v / total} for t, v in valor.items()
]}
```

- [ ] **Step 3: Regístrala en `app.py`**

En la sección «Cartera», **antes** de Seguimiento, con el patrón exacto de las
entradas que ya hay.

- [ ] **Step 4: ARRANCA LA APP Y RECÓRRELA — el paso que más importa**

```bash
UV_LINK_MODE=copy uv run streamlit run app.py
```

Los cuatro peores defectos de F y los dos de H **sólo aparecieron aquí**, con la
suite entera en verde.

Necesitas un portafolio guardado. Si no hay ninguno, créalo desde el
optimizador con tres o cuatro tickers reales.

Comprueba, y **anota lo que veas, no lo que esperabas ver**:

- [ ] «Voy a comprar» con 10.000 y acciones enteras: la tabla cuadra y **el
      sobrante se ve**.
- [ ] El mismo caso con fracciones: el sobrante es cero.
- [ ] Un capital pequeño (500) con un activo caro: ese activo **sale con cero y
      su motivo**, no desaparece.
- [ ] «Ya la ejecuté» llega con la propuesta precargada y **editable**.
- [ ] Cambiar un precio a mano y confirmar: el libro guarda **lo editado**, no
      lo propuesto.
- [ ] Gastar más que el capital: se rechaza **antes** de escribir, con un
      mensaje que se entiende.
- [ ] **Pulsar «Crear libro» dos veces deja UN fichero**, no dos. Cuéntalos con
      `ls libros/`.
- [ ] La carga manual crea un libro con cero efectivo sin asignar.
- [ ] Tras crear, aterrizas en Seguimiento con el libro ya elegido.

Si algo falla, arréglalo y vuelve a recorrer.

- [ ] **Step 5: Corre la suite entera**

Run: `UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"`
Expected: 1.111 pasando, más los tests que añadas.

**Aviso:** `tests/test_apagado.py::test_detener_espera_antes_de_forzar` es
inestable por tiempos, conocido y ajeno. Si falla, repite la corrida.

- [ ] **Step 6: Commit**

Borra antes los artefactos de prueba: `libros/` y `portafolios/` que hayas
creado. Comprueba con `git status --short`.

```bash
git add vistas/estrenar.py app.py
git commit -m "feat: la pantalla de estreno, que propone la compra y la confirma"
```

---

## Task 5: Seguimiento pierde el alta

**Files:**
- Modify: `vistas/seguimiento.py`

- [ ] **Step 1: Quita el bloque de estreno**

Borra de `vistas/seguimiento.py` el bloque que empieza en
`pendiente = st.session_state.get("portafolio_a_seguir")` y acaba en su
`st.stop()` — ahora vive en `vistas/estrenar.py`.

**El formulario «Registrar una operación» se queda.** Sirve para las compras
posteriores, que no son un estreno.

- [ ] **Step 2: Redirige a quien llegue con un portafolio pendiente**

Si alguien aterriza aquí con `portafolio_a_seguir` puesto —por ejemplo desde
`vistas/portafolios.py`, que aún apunta a esta pantalla— hay que mandarlo a la
nueva:

```python
# `portafolios.py` y el optimizador fijan esto y saltan. El estreno ya no vive
# aqui, asi que se reenvia en vez de dejar la pantalla sin explicar por que no
# pasa nada.
if st.session_state.get("portafolio_a_seguir") is not None:
    st.switch_page("vistas/estrenar.py")
```

- [ ] **Step 3: Apunta `portafolios.py` a la pantalla nueva**

En `vistas/portafolios.py:84`, cambia
`st.switch_page("vistas/seguimiento.py")` por
`st.switch_page("vistas/estrenar.py")`.

- [ ] **Step 4: Corre la suite y arranca la app**

Run: `UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"`

Y comprueba en la app que «Empezar a seguir» desde Portafolios guardados abre
la pantalla de estreno.

- [ ] **Step 5: Commit**

```bash
git add vistas/seguimiento.py vistas/portafolios.py
git commit -m "refactor: el estreno sale de seguimiento a su propia pantalla"
```

---

## Task 6: Los tres arreglos de navegación

**Files:**
- Modify: `vistas/inicio.py`
- Modify: `vistas/candidatos.py:328-360`
- Modify: `vistas/optimizador.py:566-606`

- [ ] **Step 1: La portada cuenta el recorrido entero**

En `vistas/inicio.py`, el bloque `### El recorrido completo` tiene tres columnas.
Pásalo a dos bloques con su encabezado:

- **«Elegir qué comprar»** — Candidatos, Aprobación, Optimización (las tres
  tarjetas que ya existen, sin tocar su texto).
- **«Seguir lo que compraste»** — tres tarjetas nuevas con el mismo patrón
  (`st.container(border=True)`, `st.markdown("#### N · Nombre")`, texto, y un
  `st.button` con `st.switch_page`):
  - **4 · Seguimiento** → `vistas/seguimiento.py`. Qué tienes, cuánto vale y
    cómo ha rendido, contra tres referencias.
  - **5 · Rebalanceo** → `vistas/rebalanceo.py`. Cuánto se ha separado del
    objetivo, dónde poner el dinero nuevo, y qué costaría corregir el resto.
  - **6 · Noticias** → `vistas/noticias.py`. Lo que las empresas han comunicado
    a la SEC, la prensa, y las fechas que vienen.

- [ ] **Step 2: Candidatos pasa al optimizador de verdad**

En `vistas/candidatos.py`, dentro del `else:` del botón «Aprobar … y pasar al
optimizador», sustituye el `st.success(...)` que pide usar el menú por:

```python
        st.session_state.anadidos = []
        # `switch_page` navega DENTRO de la sesion: `tickers_aprobados` sigue
        # en `session_state` al llegar. El aviso que habia aqui —usa el menu,
        # recargar pierde la seleccion— describia el problema de recargar la
        # pagina, que es otra cosa, y este fichero ya usa `switch_page` en las
        # lineas 110 y 145.
        st.session_state.acta_recien_escrita = str(destino)
        st.switch_page("vistas/optimizador.py")
```

Y en `vistas/optimizador.py`, cerca del principio, muestra el acuse una sola vez:

```python
destino_acta = st.session_state.pop("acta_recien_escrita", None)
if destino_acta:
    st.success(f"Acta escrita en {destino_acta}.")
```

- [ ] **Step 3: El optimizador guarda y pasa al estreno**

En `vistas/optimizador.py`, junto al botón «Guardar» que ya existe, añade el
principal. Los dos guardan; sólo uno salta:

Extrae primero el guardado a una función local, porque los dos botones hacen
exactamente lo mismo y duplicar veinte líneas es como se desincronizan:

```python
def _guardar(nombre: str, nota: str):
    """El portafolio guardado, o None si no se pudo, ya avisando en pantalla.

    Devuelve el objeto y no solo la ruta porque el boton de seguir necesita
    metersela a `portafolio_a_seguir`, que es lo que la pantalla de estreno
    lee. Volver a cargarlo del disco seria leer lo que acabamos de escribir.
    """
    portafolio = cartera.desde_corrida(
        nombre=nombre,
        tickers=valid_tickers,
        pesos=optimal["weights"],
        horizonte=corrida["horizonte"],
        estrategia=corrida["estrategia"],
        peso_min=corrida["peso_min"],
        peso_max=corrida["peso_max"],
        permitir_cortos=corrida["cortos"],
        shrinkage=corrida["shrinkage"],
        metricas=metrics,
        nota=nota,
    )
    try:
        destino = cartera.guardar(portafolio)
    except cartera.NombreInvalido as error:
        st.error(str(error))
        return None
    except OSError as error:
        st.error(f"No se pudo guardar: {error}")
        return None
    st.success(f"Guardado en {destino}.")
    return portafolio


# Guardar y seguir son actos distintos: se pueden archivar tres corridas y
# seguir una sola. Por eso hay dos botones y no un salto automatico.
if col_seguir.button("Guardar y empezar a seguirlo", type="primary",
                     use_container_width=True,
                     disabled=not nombre.strip()):
    guardado = _guardar(nombre, nota)
    # Solo se salta si de verdad se guardo: saltar tras un fallo dejaria al
    # usuario en la pantalla de estreno de un portafolio que no existe.
    if guardado is not None:
        st.session_state.portafolio_a_seguir = guardado
        st.switch_page("vistas/estrenar.py")

if col_guardar.button("Guardar", use_container_width=True,
                      icon=":material/save:", disabled=not nombre.strip()):
    _guardar(nombre, nota)
```

- [ ] **Step 4: Arranca la app y recorre el camino entero**

```bash
UV_LINK_MODE=copy uv run streamlit run app.py
```

- [ ] Portada → las seis tarjetas, y las tres nuevas llevan a su pantalla.
- [ ] Candidatos → aprobar → **aterrizas en el optimizador** con los tickers
      puestos y el acuse del acta arriba.
- [ ] Optimizador → «Guardar y empezar a seguirlo» → **aterrizas en el estreno**
      con ese portafolio.
- [ ] «Guardar» a secas sigue guardando sin saltar.

- [ ] **Step 5: Commit**

```bash
git add vistas/inicio.py vistas/candidatos.py vistas/optimizador.py
git commit -m "feat: el recorrido encadena, en vez de pedir que uses el menu"
```

---

## Task 7: Rebalanceo usa la aportación prevista

**Files:**
- Modify: `vistas/rebalanceo.py`
- Test: `tests/test_rebalanceo_prevista.py`

- [ ] **Step 1: Escribe el test que falla**

```python
# tests/test_rebalanceo_prevista.py
from seguimiento import libro


def test_el_libro_sabe_cuanto_se_preveia_aportar():
    """Lo que la pantalla lee para no volver a preguntarlo.

    Es un test de la lectura, no de los widgets: `vistas/rebalanceo.py` es un
    script de Streamlit y no se puede importar desde un test.
    """
    l = libro.Libro(
        nombre="p", creado="2026-01-01",
        aportacion_prevista=libro.AportacionPrevista(500.0, "mensual"),
    )
    assert l.aportacion_prevista.importe == 500.0
    assert l.aportacion_prevista.cadencia == "mensual"


def test_sin_plan_no_hay_importe_que_precargar():
    l = libro.Libro(nombre="p", creado="2026-01-01")
    assert l.aportacion_prevista is None
```

- [ ] **Step 2: Corre y comprueba que pasa**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_prevista.py -q`
Expected: PASS, 2 tests (la Task 1 ya añadió lo que hace falta)

- [ ] **Step 3: Precarga el importe en la pantalla**

En `vistas/rebalanceo.py`, donde se pide cuánto se va a aportar:

```python
# El plan del libro entra como valor inicial, no como valor fijo: sigue siendo
# editable, porque un mes se aporta mas y otro menos.
previsto = actual.aportacion_prevista
efectivo_nuevo = st.number_input(
    "¿Cuánto vas a aportar?",
    min_value=0.0,
    value=float(previsto.importe) if previsto else 0.0,
)
if previsto:
    st.caption(
        f"Viene de tu plan: **{previsto.importe:,.2f} {previsto.cadencia}**. "
        "Puedes cambiarlo aquí sin tocar el plan."
    )
```

- [ ] **Step 4: Arranca la app y compruébalo**

- [ ] Un libro con plan llega a Rebalanceo con la cifra puesta y la nota debajo.
- [ ] Un libro sin plan llega con cero y sin nota.
- [ ] Cambiar la cifra en Rebalanceo **no** modifica el plan del libro.

- [ ] **Step 5: Commit**

```bash
git add vistas/rebalanceo.py tests/test_rebalanceo_prevista.py
git commit -m "feat: rebalanceo ya no pregunta lo que el libro sabe"
```

---

## Task 8: Dejarlo dicho

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Actualiza CONTEXTO.md**

Marca J como terminado en la tabla de sub-proyectos —añadiendo la fila si no
existe— y añade «Resultado del sub-proyecto J» en el mismo tono que las de A, B,
C, F, G y H. Como mínimo:

- **La tensión y cómo se resolvió:** repartir un capital produce una división,
  no un hecho. El programa propone y el usuario confirma; la tabla editable es
  la característica, no fricción sobrante.
- **El sobrante no se redistribuye**, y un activo que no cabe sale con cero y su
  motivo en vez de desaparecer.
- **`AportacionPrevista` no es un asiento de aportación**, y por qué el nombre
  lleva «prevista».
- **En la carga manual la aportación se deriva** de lo comprado, porque no hay
  capital declarado y suponerlo dejaría efectivo fantasma.
- **Los libros viejos siguen abriéndose**: `cargar` lee campo a campo.
- Qué hereda K: la pantalla de seguimiento ya sin el bloque de estreno.

Actualiza el recuento de tests de la lista de comandos.

- [ ] **Step 2: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: la entrada al seguimiento, y por que se confirma la compra"
```

---

## Lo que queda para K

K rehace `vistas/seguimiento.py` como panel de monitoreo. J le deja esa pantalla
**sin el bloque de estreno**, que era lo que la mezclaba con el alta, y dos
datos nuevos que el panel puede mostrar: si el libro admite fracciones y cuánto
se preveía aportar.
