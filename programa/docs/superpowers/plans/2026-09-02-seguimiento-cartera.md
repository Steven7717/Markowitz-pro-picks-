# Libro de posiciones y seguimiento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pantalla donde el usuario registra lo que compró con su dinero y ve cómo va cada activo y la cartera entera, medida contra el objetivo que el optimizador le dio.

**Architecture:** Paquete nuevo `seguimiento/` con la lógica y `vistas/seguimiento.py` con los widgets. El fichero de libro guarda **sólo asientos**; posiciones, pesos, valor, TWR y TIR se derivan en cada apertura. Los precios se descargan **sin ajustar**, en un módulo propio, porque los ajustados cambian hacia atrás y moverían el coste de adquisición solo.

**Tech Stack:** Python 3.12, pandas, numpy, scipy (`brentq`), yfinance 1.6.0, Streamlit 1.62, pytest.

**Diseño:** `docs/superpowers/specs/2026-09-02-seguimiento-cartera-design.md`

---

## Antes de empezar

Todo se ejecuta desde `programa/`.

```bash
cd programa
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

**`UV_LINK_MODE=copy` no es opcional.** El proyecto vive en OneDrive y `uv` no
puede crear enlaces duros ahí: sin esa variable falla instalando `pyarrow` con
un `os error 396` antes de correr un solo test. Los lanzadores ya la ponen; una
terminal, no.

**Línea base antes de tocar nada:** `780 passed, 2 skipped, 6 deselected`.

**Un fallo conocido que no es tuyo:** `tests/test_apagado.py::test_detener_espera_antes_de_forzar`
falla de forma intermitente (3 de cada 5 veces) porque compara tiempo de reloj
contra un suelo exacto que Windows no garantiza — falla por unos 13 ms, la
granularidad del temporizador. No lo arregles en este plan y no lo cuentes como
regresión.

**Lo que NO se toca en ninguna tarea:** `aprobacion/`, `ranking/`,
`fundamentals/`, `research/`, `apagado.py` ni `data.py`. Fuera del paquete
nuevo sólo cambian cuatro cosas, y cada una lleva su tarea: el dict `metrics`
del optimizador (Task 10), un `_rebanada` que pasa a ser público en
`cartera.py` (Task 11), el botón de `vistas/portafolios.py` y la navegación de
`app.py` (Task 12).

**Convenciones de este repo, que hay que respetar:**

- Los tests se llaman en español, con frase descriptiva:
  `test_lo_guardado_vuelve_igual`. Mira `tests/test_cartera.py`.
- Los comentarios explican **por qué**, no qué. Un comentario que repite el
  código sobra; uno que dice qué se rompería sin esa línea, no.
- Los docstrings de funciones públicas van en inglés, en una línea, y el
  párrafo largo de debajo en español. Es el patrón de `cartera.py`.
- Ninguna escritura directa: siempre fichero temporal y `replace()`.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `seguimiento/__init__.py` | Vacío, como `aprobacion/__init__.py` |
| `seguimiento/libro.py` | El asiento y el libro: tipos, validación, alta, lectura y escritura |
| `seguimiento/posiciones.py` | Asientos → acciones, efectivo y valor, día a día, y si el libro cuadra en todo momento |
| `seguimiento/precios.py` | Cierres sin ajustar, dividendos y splits |
| `seguimiento/rendimiento.py` | TWR, TIR, coste medio, ganancia, contribución |
| `seguimiento/comparacion.py` | Objetivo teórico, 1/N y S&P 500 sobre los mismos flujos |
| `vistas/seguimiento.py` | Widgets. Cero lógica |
| `tests/test_seguimiento_libro.py` | Task 1, 3, 10 |
| `tests/test_seguimiento_posiciones.py` | Task 2, 5, 6 |
| `tests/test_seguimiento_precios.py` | Task 4 |
| `tests/test_seguimiento_rendimiento.py` | Task 7, 8 |
| `tests/test_seguimiento_comparacion.py` | Task 8 |
| `libros/` | Datos del usuario. Ignorado en git (Task 12) |

**Orden de dependencias.** `posiciones` no importa nada de `libro`; `libro`
importa `posiciones` dentro de la función que lo necesita, para que no haya
ciclo. `rendimiento` y `comparacion` cuelgan de `posiciones`. La vista es la
única que importa Streamlit.

---

## Task 1: El asiento y su validación de forma

**Files:**
- Create: `seguimiento/__init__.py`
- Create: `seguimiento/libro.py`
- Test: `tests/test_seguimiento_libro.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_seguimiento_libro.py`:

```python
from datetime import date

import pytest

from seguimiento.libro import (
    Asiento,
    AsientoInvalido,
    Libro,
    Objetivo,
    derivar,
    validar,
)

HOY = date(2026, 9, 2)
NAN = float("nan")
INF = float("inf")


def compra(**cambios) -> Asiento:
    campos = {
        "id": "a1",
        "fecha": "2026-09-01",
        "tipo": "compra",
        "ticker": "AAPL",
        "acciones": 10.0,
        "precio": 220.0,
        "importe": 2200.0,
    }
    campos.update(cambios)
    return Asiento(**campos)


# --- Forma del asiento -------------------------------------------------------


def test_una_compra_bien_formada_pasa():
    validar(compra(), hoy=HOY)


def test_una_fecha_futura_no_pasa():
    # Registrar algo que no ha ocurrido dejaria una posicion valorada con
    # precios que todavia no existen.
    with pytest.raises(AsientoInvalido, match="futura"):
        validar(compra(fecha="2026-09-03"), hoy=HOY)


def test_una_fecha_en_formato_basico_no_pasa():
    # date.fromisoformat acepta ISO 8601 entero desde Python 3.11, asi que
    # "20260901" es una fecha valida para el. Pero la reconstruccion ordena por
    # la cadena cruda, y '-' es menor que cualquier digito: "20260215" se va
    # DETRAS de "2026-08-01" al ordenar, y la venta se aplicaria antes que su
    # propia compra.
    with pytest.raises(AsientoInvalido, match="YYYY-MM-DD"):
        validar(compra(fecha="20260901"), hoy=HOY)


def test_una_fecha_de_semana_tampoco_pasa():
    with pytest.raises(AsientoInvalido, match="YYYY-MM-DD"):
        validar(compra(fecha="2026-W36-2"), hoy=HOY)


def test_una_fecha_que_no_es_texto_da_asiento_invalido_y_no_typeerror():
    # Pasar un `date` es el error mas probable del llamante, porque el resto
    # del modulo habla en `date`. El docstring promete AsientoInvalido, y un
    # TypeError crudo llegaria a la pantalla como un traceback de Streamlit en
    # vez de como un mensaje.
    with pytest.raises(AsientoInvalido, match="no es una fecha"):
        validar(compra(fecha=date(2026, 9, 1)), hoy=HOY)


def test_un_precio_de_cero_no_pasa():
    with pytest.raises(AsientoInvalido, match="precio"):
        validar(compra(precio=0.0), hoy=HOY)


def test_un_precio_negativo_no_pasa():
    # Sin este test, la mitad `precio <= 0` de la guarda no se ejecuta en toda
    # la suite: el caso de cero entra por la rama de "esta vacio" y la de
    # negativo no la prueba nadie.
    with pytest.raises(AsientoInvalido, match="precio"):
        validar(compra(precio=-220.0), hoy=HOY)


def test_un_importe_de_cero_no_pasa():
    with pytest.raises(AsientoInvalido, match="importe"):
        validar(compra(importe=0.0), hoy=HOY)


def test_un_importe_negativo_no_pasa():
    with pytest.raises(AsientoInvalido, match="importe"):
        validar(compra(importe=-2200.0), hoy=HOY)


def test_unas_acciones_de_cero_no_pasan():
    with pytest.raises(AsientoInvalido, match="acciones"):
        validar(compra(acciones=0.0), hoy=HOY)


def test_unas_acciones_negativas_no_pasan():
    with pytest.raises(AsientoInvalido, match="acciones"):
        validar(compra(acciones=-10.0), hoy=HOY)


def test_una_compra_sin_ticker_no_pasa():
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(compra(ticker=None), hoy=HOY)


def test_un_ticker_con_forma_rara_no_pasa():
    with pytest.raises(AsientoInvalido, match="forma de ticker"):
        validar(compra(ticker="AAPL!"), hoy=HOY)


def test_un_ticker_con_salto_de_linea_no_pasa():
    # `$` casa tambien justo antes de un salto final, asi que con `match` esto
    # pasaria por ticker valido. Y como el ticker es la clave del diccionario
    # de posiciones, partiria una posicion en dos: "AAPL" y "AAPL\n". El
    # usuario que cree tener veinte acciones veria diez.
    with pytest.raises(AsientoInvalido, match="forma de ticker"):
        validar(compra(ticker="AAPL\n"), hoy=HOY)


def test_una_aportacion_no_lleva_ticker():
    # Dinero que entra no es dinero puesto en algo: si llevara ticker, seria
    # una compra, y contarlo como flujo externo Y como posicion lo duplicaria.
    with pytest.raises(AsientoInvalido, match="ticker"):
        validar(
            Asiento(id="a2", fecha="2026-09-01", tipo="aportacion",
                    ticker="AAPL", importe=1000.0),
            hoy=HOY,
        )


def test_una_comision_negativa_no_pasa():
    with pytest.raises(AsientoInvalido, match="comisión"):
        validar(compra(comision=-1.0), hoy=HOY)


def test_un_tipo_inventado_no_pasa():
    with pytest.raises(AsientoInvalido, match="tipo"):
        validar(compra(tipo="permuta"), hoy=HOY)


# --- Numeros que no son numeros ---------------------------------------------


@pytest.mark.parametrize("campo", ["importe", "acciones", "precio", "comision"])
@pytest.mark.parametrize("veneno", [NAN, INF, -INF])
def test_ningun_campo_numerico_admite_nan_ni_infinito(campo, veneno):
    # Ninguna comparacion con NaN es cierta --`nan <= 0` es False-- y `not nan`
    # tambien es False, porque NaN es truthy. Asi que las guardas de "mayor que
    # cero" lo dejan pasar entero. Y un solo asiento con NaN hace dos cosas a
    # la vez: envenena el efectivo, y BORRA el activo de la tabla de
    # posiciones, porque el filtro de polvo `abs(n) > _POLVO` tambien es False
    # para NaN. El usuario no ve un error: ve una posicion que desaparecio.
    with pytest.raises(AsientoInvalido, match="finito"):
        validar(compra(**{campo: veneno}), hoy=HOY)


def test_el_nan_que_entra_desde_disco_lo_para_la_validacion():
    # No es un caso de laboratorio: json.loads acepta el literal NaN por
    # defecto, asi que un fichero editado a mano o corrompido lo mete en el
    # libro sin que nadie lo teclee. Este test recorre ese camino entero, y no
    # se limita a comprobar lo que hace la libreria estandar.
    import json

    crudo = json.loads(
        '{"id": "a1", "fecha": "2026-09-01", "tipo": "compra", '
        '"ticker": "AAPL", "acciones": 10.0, "precio": 220.0, "importe": NaN}'
    )
    with pytest.raises(AsientoInvalido, match="finito"):
        validar(Asiento(**crudo), hoy=HOY)


# --- La anulacion ------------------------------------------------------------


def test_una_anulacion_necesita_a_quien_anula():
    with pytest.raises(AsientoInvalido, match="anula"):
        validar(Asiento(id="a3", fecha="2026-09-01", tipo="anulacion"), hoy=HOY)


def test_una_anulacion_bien_formada_pasa():
    validar(
        Asiento(id="a3", fecha="2026-09-01", tipo="anulacion", anula="a1"),
        hoy=HOY,
    )


def test_una_anulacion_no_arrastra_importe_ni_ticker():
    # Una anulacion es una nota que tacha otra linea, no un movimiento.
    # Dejarla llevar ticker o dinero guardaria basura con pinta de dato en un
    # fichero que nadie vuelve a validar al leerlo.
    with pytest.raises(AsientoInvalido, match="no lleva ticker"):
        validar(
            Asiento(id="a3", fecha="2026-09-01", tipo="anulacion",
                    anula="a1", ticker="AAPL"),
            hoy=HOY,
        )
    with pytest.raises(AsientoInvalido, match="no mueve dinero"):
        validar(
            Asiento(id="a3", fecha="2026-09-01", tipo="anulacion",
                    anula="a1", importe=9999.0),
            hoy=HOY,
        )


# --- Derivar el tercer campo -------------------------------------------------


def test_de_importe_y_precio_salen_las_acciones():
    assert derivar(importe=2200.0, acciones=None, precio=220.0) == (2200.0, 10.0, 220.0)


def test_de_acciones_y_precio_sale_el_importe():
    assert derivar(importe=None, acciones=10.0, precio=220.0) == (2200.0, 10.0, 220.0)


def test_con_los_tres_puestos_se_respetan_los_tres():
    # El broker cobra redondeos que ninguna division reproduce: si el usuario
    # escribe los tres, mandan los tres, aunque no cuadren al centimo.
    assert derivar(importe=2200.5, acciones=10.0, precio=220.0) == (2200.5, 10.0, 220.0)


def test_sin_precio_no_se_puede_derivar_nada():
    with pytest.raises(AsientoInvalido, match="hace falta el precio"):
        derivar(importe=2200.0, acciones=None, precio=None)


def test_un_precio_negativo_no_sirve_para_derivar():
    with pytest.raises(AsientoInvalido, match="mayor que cero"):
        derivar(importe=2200.0, acciones=None, precio=-220.0)


def test_sin_importe_ni_acciones_no_hay_nada_que_completar():
    with pytest.raises(AsientoInvalido, match="importe o el número de acciones"):
        derivar(importe=None, acciones=None, precio=220.0)


def test_derivar_no_devuelve_un_infinito():
    # Ni el importe ni el precio son absurdos por separado, pero la division
    # desborda. `validar` no lo salvaria despues: `inf > 0` es True, asi que
    # pasa todas las guardas y la cartera acaba con infinitas acciones.
    with pytest.raises(AsientoInvalido, match="no cuadra"):
        derivar(importe=2200.0, acciones=None, precio=1e-320)


@pytest.mark.parametrize("campo", ["importe", "acciones", "precio"])
def test_derivar_rechaza_un_nan_de_entrada(campo):
    # `derivar` corre ANTES que `validar`: recibe lo que el usuario acaba de
    # teclear y no puede apoyarse en nadie.
    campos = {"importe": 2200.0, "acciones": None, "precio": 220.0}
    campos[campo] = NAN
    with pytest.raises(AsientoInvalido, match="finito"):
        derivar(**campos)


# --- El libro ----------------------------------------------------------------


def test_el_objetivo_vigente_es_el_ultimo_apilado():
    libro = Libro(
        nombre="Prueba", creado="2026-01-01T10:00:00",
        objetivos=(
            Objetivo(fecha="2026-01-01", base="estrategia", portafolio={}),
            Objetivo(fecha="2026-06-01", base="equal_weight", portafolio={}),
        ),
    )
    assert libro.objetivo.fecha == "2026-06-01"


def test_un_libro_sin_objetivos_no_tiene_objetivo_vigente():
    # None y no un objetivo vacio: "no hay contra que medir" es un estado real
    # --una cartera creada a mano-- y la pantalla lo dice en vez de ensenar una
    # deriva de cero que nadie calculo.
    assert Libro(nombre="Prueba", creado="2026-01-01T10:00:00").objetivo is None


def test_los_asientos_de_un_libro_no_se_pueden_editar_en_el_sitio():
    # `frozen=True` impide reasignar el campo, pero no tocar una lista por
    # dentro. Con una lista, `libro.asientos.append(...)` funcionaria y la
    # regla central del modulo --nunca se edita, nunca se borra-- estaria
    # documentada pero no impuesta.
    libro = Libro(nombre="Prueba", creado="2026-01-01T10:00:00",
                  asientos=(compra(),))
    with pytest.raises(AttributeError):
        libro.asientos.append(compra())
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q
```

Esperado: `ModuleNotFoundError: No module named 'seguimiento'`.

- [ ] **Step 3: Escribe el módulo**

Crea `seguimiento/__init__.py` vacío. Crea `seguimiento/libro.py`:

```python
"""El libro de asientos: lo que el usuario compró de verdad, y por cuánto.

Un libro no es un `cartera.Portafolio`. Aquel es una fotografía de una
optimización —pesos y métricas congelados, sin dinero dentro— y este es el
registro vivo de lo que pasó después. La pantalla de seguimiento mide la
distancia entre los dos, así que fundirlos borraría justo lo que hay que medir.

Se guardan **sólo asientos**. Posiciones, pesos, valor y rendimiento se derivan
en cada apertura desde `seguimiento.posiciones`. Guardar también el estado
crearía dos representaciones de la misma verdad que se pueden desincronizar, y
una corrección aplicada a una sola de ellas produce un libro que se lee
perfectamente bien y miente.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date

TIPOS = frozenset(
    {"aportacion", "retiro", "compra", "venta", "dividendo", "anulacion"}
)

# Los tipos que mueven un activo concreto, y por tanto necesitan ticker.
CON_TICKER = frozenset({"compra", "venta", "dividendo"})

# Los dos únicos que son dinero entrando o saliendo del bolsillo del usuario.
# Todo lo demás mueve dinero *dentro* de la cartera, y por eso cuenta en el
# rendimiento en vez de quedar fuera de él. Un dividendo tomado por flujo
# externo inflaría el capital aportado con lo que la cartera acaba de ganar.
FLUJOS_EXTERNOS = frozenset({"aportacion", "retiro"})

# Sin anclas, porque se usa con `fullmatch` y no con `match`. Con `match`, un
# `$` casa también justo antes de un salto de línea final, así que "AAPL\n"
# pasaría por ticker válido — y como el ticker es la clave del diccionario de
# posiciones, eso partiría una posición en dos, "AAPL" y "AAPL\n". El usuario
# que cree tener veinte acciones vería diez, sin nada en pantalla que lo
# explicara. `cartera.py` y `aprobacion/acta.py` llevan la variante con `match`
# y el mismo agujero; aquí no se hereda.
_FORMA_TICKER = re.compile(r"[A-Z]+(-[A-Z]+)*")

_CAMPOS_NUMERICOS = (
    ("importe", "el importe"),
    ("acciones", "las acciones"),
    ("precio", "el precio"),
    ("comision", "la comisión"),
)


class AsientoInvalido(ValueError):
    """Lo que se intenta registrar no pudo haber pasado."""


@dataclass(frozen=True)
class Asiento:
    """Una línea del libro. Nunca se edita y nunca se borra."""

    id: str
    fecha: str
    tipo: str
    ticker: str | None = None
    acciones: float | None = None
    precio: float | None = None
    importe: float = 0.0
    comision: float = 0.0
    # True cuando el precio salió del cierre del día y no de lo que el usuario
    # pagó. Viaja con el asiento y se pinta en el historial: una compra
    # intradía en un día volátil se desvía un 3-4% del cierre, y eso tiene que
    # ser visible, no una nota al pie del diseño.
    precio_estimado: bool = False
    anula: str | None = None
    nota: str = ""


@dataclass(frozen=True)
class Objetivo:
    """Los pesos contra los que se mide la deriva, con su fecha y su evidencia."""

    fecha: str
    base: str
    portafolio: dict
    veredicto: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Libro:
    """Un libro entero: el nombre, los objetivos apilados y los asientos.

    Las dos colecciones son tuplas y no listas. `frozen=True` impide reasignar
    el campo, pero no tocar una lista por dentro: con listas,
    `libro.asientos.append(...)` funcionaría y la regla central de este módulo
    —nunca se edita, nunca se borra— quedaría documentada pero no impuesta.
    """

    nombre: str
    creado: str
    moneda: str = "USD"
    objetivos: tuple[Objetivo, ...] = ()
    asientos: tuple[Asiento, ...] = ()

    @property
    def objetivo(self) -> Objetivo | None:
        """El objetivo vigente: el último que se apiló, o ninguno."""
        return self.objetivos[-1] if self.objetivos else None


def _finito(valor, campo: str) -> None:
    """Reject NaN, infinity, and anything that is not a number at all.

    **Ninguna de las guardas de más abajo lo caza.** Toda comparación con NaN
    es falsa —`nan <= 0` es `False`— y `not float("nan")` también es `False`,
    porque NaN es *truthy*. Así que un asiento con NaN las atraviesa enteras, y
    entonces hace dos cosas a la vez: envenena el efectivo, y **borra el activo
    de la tabla de posiciones**, porque el filtro de polvo `abs(n) > _POLVO` de
    `seguimiento.posiciones` también es `False` para NaN. El usuario no ve un
    error: ve una posición que desapareció y un efectivo que dice "nan".

    No es un caso de laboratorio. `json.loads` acepta los literales `NaN` e
    `Infinity` por defecto, así que un fichero editado a mano o corrompido los
    mete en el libro sin que nadie los teclee.
    """
    if valor is None:
        return
    try:
        finito = math.isfinite(valor)
    except TypeError as error:
        raise AsientoInvalido(f"{campo} no es un número: {valor!r}") from error
    if not finito:
        raise AsientoInvalido(f"{campo} tiene que ser un número finito, y es {valor!r}")


def validar(asiento: Asiento, hoy: date | None = None) -> None:
    """Check one entry's shape. Raises AsientoInvalido naming what is wrong.

    Sólo comprueba lo que se puede saber mirando el asiento solo. Lo que
    depende del estado —vender más acciones de las que hay, retirar más
    efectivo del que hay— vive en `anadir()`, porque necesita reconstruir el
    libro entero para responderlo.
    """
    hoy = hoy or date.today()

    if asiento.tipo not in TIPOS:
        raise AsientoInvalido(
            f"{asiento.tipo!r} no es un tipo de asiento: "
            f"{', '.join(sorted(TIPOS))}"
        )

    for campo, nombre in _CAMPOS_NUMERICOS:
        _finito(getattr(asiento, campo), nombre)

    try:
        cuando = date.fromisoformat(asiento.fecha)
    except (TypeError, ValueError) as error:
        # TypeError además de ValueError: pasar un `date` es el error más
        # probable del llamante, porque el resto del módulo habla en `date`, y
        # el docstring de arriba promete AsientoInvalido. Sin capturarlo, la
        # pantalla —que sólo atrapa AsientoInvalido— enseñaría un traceback.
        raise AsientoInvalido(f"{asiento.fecha!r} no es una fecha") from error
    if cuando.isoformat() != asiento.fecha:
        # `date.fromisoformat` acepta ISO 8601 entero desde Python 3.11, así
        # que "20260901" y "2026-W36-2" son fechas válidas para él. Pero la
        # reconstrucción ordena por la cadena cruda, y '-' es menor que
        # cualquier dígito: "20260215" acaba DETRÁS de "2026-08-01" al ordenar,
        # y una venta se aplicaría antes que su propia compra.
        raise AsientoInvalido(
            f"{asiento.fecha!r} no está escrita como YYYY-MM-DD"
        )
    if cuando > hoy:
        raise AsientoInvalido(
            f"{asiento.fecha} es una fecha futura: no se puede registrar algo "
            "que todavía no ha pasado"
        )

    if asiento.comision < 0:
        raise AsientoInvalido("la comisión no puede ser negativa")

    if asiento.tipo == "anulacion":
        if not asiento.anula:
            raise AsientoInvalido("una anulación tiene que decir a qué asiento anula")
        # Una anulación es una nota que tacha otra línea, no un movimiento.
        # Dejarla llevar ticker o dinero guardaría basura con pinta de dato en
        # un fichero que nadie vuelve a validar al leerlo.
        for campo in ("ticker", "acciones", "precio"):
            if getattr(asiento, campo) is not None:
                raise AsientoInvalido(f"una anulación no lleva {campo}")
        if asiento.importe or asiento.comision:
            raise AsientoInvalido("una anulación no mueve dinero")
        return

    if asiento.tipo in CON_TICKER:
        if not asiento.ticker:
            raise AsientoInvalido(f"un asiento de {asiento.tipo} necesita ticker")
        if not _FORMA_TICKER.fullmatch(asiento.ticker):
            raise AsientoInvalido(f"{asiento.ticker!r} no tiene forma de ticker")
    elif asiento.ticker:
        raise AsientoInvalido(
            f"un asiento de {asiento.tipo} no lleva ticker: es dinero entrando o "
            "saliendo, no dinero puesto en algo"
        )

    if asiento.importe <= 0:
        raise AsientoInvalido("el importe tiene que ser mayor que cero")

    if asiento.tipo in {"compra", "venta"}:
        if asiento.acciones is None or asiento.acciones <= 0:
            raise AsientoInvalido("las acciones tienen que ser más que cero")
        if asiento.precio is None or asiento.precio <= 0:
            raise AsientoInvalido("el precio tiene que ser mayor que cero")


def derivar(
    importe: float | None, acciones: float | None, precio: float | None
) -> tuple[float, float, float]:
    """Complete the third figure from the other two, and return all three.

    Se guardan los tres aunque uno se haya derivado, para que el fichero se lea
    sin recalcular nada y para que un cambio futuro en esta fórmula no mueva los
    datos de ayer.

    Cuando llegan los tres, mandan los tres aunque no cuadren al céntimo: el
    bróker aplica redondeos que ninguna división reproduce, y corregir en
    silencio lo que el usuario copió de su extracto sería inventar.

    **No puede apoyarse en `validar`, porque corre antes que él.** La pantalla
    llama aquí con lo que el usuario acaba de teclear, construye el `Asiento`
    con el resultado, y sólo entonces llama a `anadir()`, que es quien valida.
    Así que lo que no se compruebe aquí llega contaminado — y algunos venenos
    pasan luego las guardas de "mayor que cero" sin despeinarse, porque un
    `inf` nacido de dividir por un precio diminuto es mayor que cero.
    """
    _finito(importe, "el importe")
    _finito(acciones, "las acciones")
    _finito(precio, "el precio")

    if precio is None:
        raise AsientoInvalido("hace falta el precio para completar la operación")
    if precio <= 0:
        raise AsientoInvalido("el precio tiene que ser mayor que cero")

    if importe is not None and acciones is not None:
        completo = (float(importe), float(acciones), float(precio))
    elif importe is not None:
        completo = (float(importe), float(importe) / float(precio), float(precio))
    elif acciones is not None:
        completo = (float(acciones) * float(precio), float(acciones), float(precio))
    else:
        raise AsientoInvalido("hace falta el importe o el número de acciones")

    for valor, (_, nombre) in zip(completo, _CAMPOS_NUMERICOS):
        if not math.isfinite(valor):
            raise AsientoInvalido(
                f"la operación no cuadra: {nombre} sale {valor}. Revisa el "
                "precio, que es por lo que se divide."
            )
    return completo
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q
```

Esperado: `46 passed` — 31 tests sueltos, más 12 del parametrizado de NaN e
infinito (cuatro campos × tres venenos) y 3 del de `derivar`.

- [ ] **Step 5: Comprueba que las guardas nuevas se disparan de verdad**

Un test que pasa igual con el código roto no es un test. Sabotea estas cuatro
líneas de `seguimiento/libro.py`, una a una, y confirma que **cada sabotaje
rompe al menos un test**. Deshaz cada uno antes del siguiente con
`git checkout -- seguimiento/libro.py`.

| Sabotaje | Tiene que fallar |
|---|---|
| Borrar el bucle `for campo, nombre in _CAMPOS_NUMERICOS` de `validar` | los 12 de NaN/infinito |
| Borrar el bloque `if asiento.importe <= 0` | los de importe cero y negativo |
| `if asiento.precio is None or asiento.precio <= 0` → `if asiento.precio is None` | el de precio negativo |
| `_FORMA_TICKER.fullmatch` → `_FORMA_TICKER.match` | el del salto de línea |

Si alguno de los cuatro sobrevive, el test correspondiente no prueba lo que su
nombre dice y hay que arreglarlo antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/__init__.py seguimiento/libro.py tests/test_seguimiento_libro.py
git commit -m "feat: el asiento del libro, con su validacion de forma"
```

---

## Task 2: Reconstruir el estado desde los asientos

**Files:**
- Create: `seguimiento/posiciones.py`
- Test: `tests/test_seguimiento_posiciones.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_seguimiento_posiciones.py`:

```python
import pytest

from seguimiento import posiciones
from seguimiento.libro import Asiento


def asiento(id_, fecha, tipo, **campos) -> Asiento:
    return Asiento(id=id_, fecha=fecha, tipo=tipo, **campos)


APORTA = asiento("a1", "2026-01-05", "aportacion", importe=10_000.0)
COMPRA = asiento(
    "a2", "2026-01-05", "compra", ticker="AAPL",
    acciones=40.0, precio=200.0, importe=8000.0, comision=1.0,
)


def test_una_compra_deja_acciones_y_baja_el_efectivo():
    estado = posiciones.estado([APORTA, COMPRA])
    assert estado.acciones == {"AAPL": 40.0}
    # 10.000 menos 8.000 de compra menos 1 de comision.
    assert estado.efectivo == pytest.approx(1999.0)


def test_la_comision_sale_del_efectivo_y_no_del_aire():
    # Si la comision no bajara el efectivo, el libro cuadraria con mas dinero
    # del que hay y la primera venta descuadraria sin motivo visible.
    sin = posiciones.estado([APORTA, asiento(
        "a2", "2026-01-05", "compra", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )])
    assert sin.efectivo - posiciones.estado([APORTA, COMPRA]).efectivo == pytest.approx(1.0)


def test_una_venta_devuelve_efectivo_menos_comision():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0, comision=1.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta])
    assert estado.acciones == {"AAPL": 30.0}
    assert estado.efectivo == pytest.approx(1999.0 + 2499.0)


def test_un_ticker_que_se_vende_entero_desaparece_de_las_posiciones():
    # Dejar "AAPL: 0.0" haria que la tabla mostrara una fila de una empresa que
    # ya no se tiene, con peso cero y precio de hoy: ruido que parece dato.
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=40.0, precio=250.0, importe=10_000.0,
    )
    assert posiciones.estado([APORTA, COMPRA, venta]).acciones == {}


def test_un_dividendo_entra_en_efectivo():
    dividendo = asiento(
        "a3", "2026-02-10", "dividendo", ticker="AAPL", importe=9.6
    )
    estado = posiciones.estado([APORTA, COMPRA, dividendo])
    assert estado.efectivo == pytest.approx(1999.0 + 9.6)


def test_un_asiento_anulado_deja_de_contar():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2")
    estado = posiciones.estado([APORTA, COMPRA, anulacion])
    assert estado.acciones == {}
    assert estado.efectivo == pytest.approx(10_000.0)


def test_la_propia_anulacion_tampoco_cuenta_como_asiento():
    anulacion = asiento("a3", "2026-01-06", "anulacion", anula="a2", importe=0.0)
    assert posiciones.vigentes([APORTA, COMPRA, anulacion]) == [APORTA]


def test_el_estado_se_puede_pedir_a_una_fecha_pasada():
    venta = asiento(
        "a3", "2026-02-05", "venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0,
    )
    estado = posiciones.estado([APORTA, COMPRA, venta], hasta="2026-01-31")
    assert estado.acciones == {"AAPL": 40.0}


def test_los_asientos_desordenados_dan_el_mismo_estado():
    # El fichero se escribe en orden de alta, pero nada garantiza que alguien no
    # lo reordene a mano. El estado no puede depender de eso.
    revuelto = posiciones.estado([COMPRA, APORTA])
    derecho = posiciones.estado([APORTA, COMPRA])
    assert revuelto.acciones == derecho.acciones
    assert revuelto.efectivo == pytest.approx(derecho.efectivo)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_posiciones.py -q
```

Esperado: `ImportError: cannot import name 'posiciones'`.

- [ ] **Step 3: Escribe el módulo**

Crea `seguimiento/posiciones.py`:

```python
"""De la lista de asientos a lo que hay en cartera, día a día.

Nada de este módulo guarda estado. Cada llamada reconstruye desde los asientos,
que es lo que hace imposible que las posiciones y el libro se desincronicen: no
hay dos representaciones que puedan discrepar, hay una y una derivación.

No importa nada de `seguimiento.libro` en tiempo de ejecución a propósito.
`libro.anadir` sí necesita a este módulo —para rechazar una venta que no se
puede pagar con lo que hay— y hacerlo en los dos sentidos crearía un ciclo de
importación.
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from seguimiento.libro import Asiento

# Por debajo de esto, una posición es polvo de redondeo de una venta total, no
# una participación. Sin el corte, vender las 40 acciones que se compraron
# puede dejar 3.55e-15 en cartera y una fila fantasma en la tabla.
_POLVO = 1e-9


@dataclass(frozen=True)
class Estado:
    """Lo que hay en cartera en un momento: acciones por ticker y efectivo."""

    acciones: dict[str, float]
    efectivo: float


def vigentes(asientos: "list[Asiento]") -> "list[Asiento]":
    """Entries still standing: drops the annulled ones and the annulments.

    Se resuelve antes de ordenar por fecha porque una anulación puede llevar
    fecha anterior al asiento que anula —se corrige un error el martes sobre
    algo fechado el lunes— y filtrar por fecha primero la dejaría fuera.
    """
    anulados = {a.anula for a in asientos if a.tipo == "anulacion" and a.anula}
    return [
        a for a in asientos if a.tipo != "anulacion" and a.id not in anulados
    ]


def ordenados(asientos: "list[Asiento]") -> "list[Asiento]":
    """By date, keeping insertion order as the tie-break.

    `sorted` es estable, así que dos asientos del mismo día conservan el orden
    en que se dieron de alta. Importa: comprar y vender el mismo día en el
    orden contrario dejaría acciones negativas a mitad del recorrido.
    """
    return sorted(asientos, key=lambda a: a.fecha)


def estado(asientos: "list[Asiento]", hasta: str | date | None = None) -> Estado:
    """Shares per ticker and cash, as of `hasta` (default: everything)."""
    limite = hasta.isoformat() if isinstance(hasta, date) else hasta

    acciones: dict[str, float] = {}
    efectivo = 0.0

    for a in ordenados(vigentes(asientos)):
        if limite is not None and a.fecha > limite:
            break
        if a.tipo == "aportacion":
            efectivo += a.importe
        elif a.tipo == "retiro":
            efectivo -= a.importe
        elif a.tipo == "dividendo":
            efectivo += a.importe
        elif a.tipo == "compra":
            efectivo -= a.importe + a.comision
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
        elif a.tipo == "venta":
            efectivo += a.importe - a.comision
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) - a.acciones

    return Estado(
        acciones={t: n for t, n in acciones.items() if abs(n) > _POLVO},
        efectivo=efectivo,
    )
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_posiciones.py -q
```

Esperado: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/posiciones.py tests/test_seguimiento_posiciones.py
git commit -m "feat: reconstruir acciones y efectivo desde los asientos"
```

---

## Task 3: Rechazar lo que no puede haber pasado

**Files:**
- Modify: `seguimiento/libro.py` (añadir `anadir`)
- Test: `tests/test_seguimiento_libro.py` (añadir al final)

- [ ] **Step 1: Escribe los tests que fallan**

Añade al final de `tests/test_seguimiento_libro.py`:

```python
from seguimiento.libro import Libro, anadir

VACIO = Libro(nombre="Prueba", creado="2026-01-01T10:00:00")


def con(*asientos) -> Libro:
    from dataclasses import replace
    return replace(VACIO, asientos=tuple(asientos))


def test_no_se_puede_vender_lo_que_no_se_tiene():
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
        acciones=5.0, precio=220.0, importe=1100.0,
    )
    with pytest.raises(AsientoInvalido, match="no tienes"):
        anadir(VACIO, venta, hoy=HOY)


def test_no_se_pueden_vender_mas_acciones_de_las_que_hay():
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", acciones=10.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
        acciones=11.0, precio=220.0, importe=2420.0,
    )
    with pytest.raises(AsientoInvalido, match="10"):
        anadir(libro, venta, hoy=HOY)


def test_no_se_puede_retirar_mas_efectivo_del_que_hay():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=100.0))
    retiro = Asiento(id="r1", fecha="2026-09-01", tipo="retiro", importe=200.0)
    with pytest.raises(AsientoInvalido, match="efectivo"):
        anadir(libro, retiro, hoy=HOY)


def test_una_compra_sin_efectivo_suficiente_arrastra_su_aportacion():
    # El usuario piensa "compre 2.200 de Apple", no "aporte 2.205 y luego
    # compre". Escribir la aportacion por el sonaria a magia si no se dijera,
    # asi que anadir() la devuelve para que la pantalla la ensene.
    libro, escritos = anadir(VACIO, compra(comision=5.0), hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["aportacion", "compra"]
    # La comision va DENTRO de la aportacion. Con comision cero este test
    # pasaria igual sin cubrirla, y el comentario estaria prometiendo una
    # cobertura que no existe -- que es como se cuelan las guardas muertas.
    assert escritos[0].importe == pytest.approx(2205.0)


def test_la_aportacion_que_financia_deja_el_efectivo_a_cero():
    # La comprobacion que de verdad cierra el caso: si la aportacion se
    # quedase corta por el importe de la comision, el efectivo acabaria
    # negativo -- un descuadre pequeno, permanente y sin causa visible.
    from seguimiento import posiciones

    libro, _ = anadir(VACIO, compra(comision=5.0), hoy=HOY, financiar=True)
    assert posiciones.estado(libro.asientos).efectivo == pytest.approx(0.0)


def test_una_compra_con_efectivo_suficiente_no_inventa_aportacion():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0))
    _, escritos = anadir(libro, compra(), hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["compra"]


def test_no_se_puede_anular_un_asiento_que_no_existe():
    anulacion = Asiento(id="x1", fecha="2026-09-01", tipo="anulacion", anula="fantasma")
    with pytest.raises(AsientoInvalido, match="no existe"):
        anadir(VACIO, anulacion, hoy=HOY)


def test_no_se_puede_anular_dos_veces():
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        Asiento(id="x1", fecha="2026-08-02", tipo="anulacion", anula="ap"),
    )
    otra = Asiento(id="x2", fecha="2026-09-01", tipo="anulacion", anula="ap")
    with pytest.raises(AsientoInvalido, match="ya está anulado"):
        anadir(libro, otra, hoy=HOY)


def test_el_asiento_aceptado_se_queda_en_el_libro():
    libro, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    assert len(libro.asientos) == 1
    assert libro.asientos[0].tipo == "aportacion"


def test_no_se_puede_vender_en_una_fecha_anterior_a_la_compra():
    # El caso que rompe comprobar solo el saldo final: hoy tengo diez acciones,
    # asi que una venta de diez "cuadra" -- pero fechada en julio deja la
    # cartera con menos diez acciones en julio, y `estado(hasta=...)` lo
    # devolveria tal cual. No es un caso raro: es lo que pasa siempre que
    # alguien registra lo que ya tenia comprado y mete los asientos en el orden
    # del extracto y no en orden cronologico.
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=5000.0),
        compra(id="c1", fecha="2026-08-01", acciones=10.0),
    )
    venta = Asiento(
        id="v1", fecha="2026-07-01", tipo="venta", ticker="AAPL",
        acciones=10.0, precio=250.0, importe=2500.0,
    )
    with pytest.raises(AsientoInvalido, match="2026-07-01"):
        anadir(libro, venta, hoy=HOY)


def test_un_retiro_fechado_antes_de_su_aportacion_no_pasa():
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion",
                        importe=5000.0))
    retiro = Asiento(id="r1", fecha="2026-07-01", tipo="retiro", importe=1000.0)
    with pytest.raises(AsientoInvalido, match="2026-07-01"):
        anadir(libro, retiro, hoy=HOY)


def test_una_compra_del_pasado_se_financia_con_el_saldo_de_entonces():
    # Aportar 5.000 en agosto no paga una compra fechada en julio. La
    # aportacion que se escribe tiene que cubrirla entera, no la diferencia
    # contra un saldo que en esa fecha todavia no existia.
    libro = con(Asiento(id="ap", fecha="2026-08-01", tipo="aportacion",
                        importe=5000.0))
    _, escritos = anadir(libro, compra(id="c1", fecha="2026-07-01"),
                         hoy=HOY, financiar=True)
    assert [a.tipo for a in escritos] == ["aportacion", "compra"]
    assert escritos[0].importe == pytest.approx(2200.0)


def test_vender_exactamente_lo_que_se_tiene_sigue_valiendo():
    # Las acciones salen de dividir un importe entre un precio, asi que
    # arrastran redondeo. Sin el margen de polvo en la comparacion, vender la
    # posicion entera fallaria por una diferencia de femtoacciones.
    from seguimiento.libro import derivar

    importe, acciones, precio = derivar(importe=1000.0, acciones=None, precio=3.0)
    libro = con(
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=1000.0),
        Asiento(id="c1", fecha="2026-08-01", tipo="compra", ticker="AAPL",
                acciones=acciones, precio=precio, importe=importe),
    )
    venta = Asiento(id="v1", fecha="2026-09-01", tipo="venta", ticker="AAPL",
                    acciones=acciones, precio=4.0, importe=acciones * 4.0)
    libro, _ = anadir(libro, venta, hoy=HOY)
    assert len(libro.asientos) == 3
```

Y cambia el ayudante `compra()` del principio del fichero para que acepte
sobreescribir el `id` y la `fecha` (ya lo hace vía `**cambios`; sólo asegúrate
de que las llamadas nuevas `compra(id="c1", ...)` funcionan).

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q
```

Esperado: `ImportError: cannot import name 'anadir'`.

- [ ] **Step 3: Añade el recorrido a `seguimiento/posiciones.py`**

`estado()` sólo mira dónde acaba el libro. Para aceptar un asiento hace falta
saber si el libro cuadra **en todo momento**, no sólo al final. Añade al final
de `seguimiento/posiciones.py`:

```python
def primer_descubierto(asientos: "list[Asiento]") -> str | None:
    """The first moment the book would go into the red, in words, or None.

    `estado()` responde "qué hay al final". Esta función responde "¿hubo algún
    día en que esto no cuadrara?", que es otra pregunta y la que hace falta
    antes de aceptar un asiento.

    La diferencia importa porque un asiento puede llegar **fechado en el
    pasado**, y es el caso normal: quien empieza a llevar el libro de lo que ya
    tenía comprado mete las operaciones en el orden en que las encuentra en el
    extracto, no en orden cronológico. Comprobar sólo el saldo final acepta una
    venta de julio de acciones compradas en agosto —el final cuadra— y deja la
    cartera con acciones negativas a mitad del recorrido.

    El margen de `_POLVO` en cada comparación es para que vender exactamente lo
    que se tiene siga valiendo: el número de acciones viene de dividir un
    importe entre un precio, así que arrastra error de redondeo y una igualdad
    exacta fallaría por un femtoaccion de diferencia.
    """
    acciones: dict[str, float] = {}
    efectivo = 0.0

    for a in ordenados(vigentes(asientos)):
        if a.tipo == "aportacion":
            efectivo += a.importe
        elif a.tipo == "dividendo":
            efectivo += a.importe
        elif a.tipo == "retiro":
            if a.importe > efectivo + _POLVO:
                return (
                    f"el {a.fecha} no hay efectivo suficiente: harían falta "
                    f"{a.importe:,.2f} y hay {efectivo:,.2f}"
                )
            efectivo -= a.importe
        elif a.tipo == "compra":
            coste = a.importe + a.comision
            if coste > efectivo + _POLVO:
                return (
                    f"el {a.fecha} no hay efectivo suficiente: la compra cuesta "
                    f"{coste:,.2f} y hay {efectivo:,.2f}"
                )
            efectivo -= coste
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
        elif a.tipo == "venta":
            tiene = acciones.get(a.ticker, 0.0)
            if a.acciones > tiene + _POLVO:
                return (
                    f"el {a.fecha} no tienes suficientes acciones de {a.ticker}: "
                    f"harían falta {a.acciones:g} y hay {tiene:g}"
                )
            acciones[a.ticker] = tiene - a.acciones
            efectivo += a.importe - a.comision
    return None
```

- [ ] **Step 4: Implementa `anadir`**

Añade al final de `seguimiento/libro.py`:

```python
def anadir(
    libro: Libro,
    asiento: Asiento,
    hoy: date | None = None,
    financiar: bool = False,
) -> tuple[Libro, list[Asiento]]:
    """Validate against the ledger's state and return the new book.

    Devuelve también **qué se escribió de verdad**, que puede ser más de un
    asiento: una compra que no cabe en el efectivo disponible arrastra la
    aportación que la financia. El usuario piensa "compré dos mil de Apple", no
    "aporté dos mil y luego compré"; escribir la aportación por él sin decirlo
    sería magia, y por eso la lista vuelve para que la pantalla la enseñe antes
    de guardar.

    La aportación cubre la comisión además del importe. Sin eso, el efectivo
    quedaría negativo por el importe exacto de la comisión en cuanto se
    registrase la primera compra — un descuadre pequeño, permanente y sin causa
    visible.
    """
    # Importación local: `posiciones` no importa este módulo en tiempo de
    # ejecución justamente para que no haya ciclo, y hacerlo arriba lo crearía.
    from seguimiento import posiciones

    validar(asiento, hoy=hoy)

    if asiento.tipo == "anulacion":
        por_id = {a.id: a for a in libro.asientos}
        if asiento.anula not in por_id:
            raise AsientoInvalido(
                f"el asiento {asiento.anula} no existe: no hay nada que anular"
            )
        ya = {a.anula for a in libro.asientos if a.tipo == "anulacion"}
        if asiento.anula in ya:
            raise AsientoInvalido(
                f"el asiento {asiento.anula} ya está anulado: anularlo dos veces "
                "no significa nada"
            )
        return (_con_asientos(libro, [asiento]), [asiento])

    escritos = [asiento]

    if asiento.tipo == "compra" and financiar:
        # El efectivo que había **en la fecha del asiento**, no el de hoy. Un
        # asiento puede llegar fechado en el pasado —es el caso normal cuando
        # alguien empieza a registrar lo que ya tenía comprado— y financiarlo
        # con el saldo de hoy escribiría una aportación del tamaño equivocado.
        disponible = posiciones.estado(libro.asientos, hasta=asiento.fecha).efectivo
        coste = asiento.importe + asiento.comision
        if coste > disponible:
            escritos = [
                Asiento(
                    id=f"{asiento.id}-ap",
                    fecha=asiento.fecha,
                    tipo="aportacion",
                    importe=coste - disponible,
                    nota="Financia la compra de " + str(asiento.ticker),
                ),
                asiento,
            ]

    candidato = _con_asientos(libro, escritos)

    # **El recorrido entero, no el saldo final.** Comprobar contra el estado de
    # hoy acepta una venta fechada en julio de acciones compradas en agosto: el
    # saldo final cuadra, y la cartera queda con acciones negativas a mitad del
    # camino — justo lo que `posiciones.ordenados` existe para evitar. Medido
    # antes de escribir esto: `estado(hasta="2026-07-01")` devolvía
    # `{'AAPL': -10.0}` sin que nada lo hubiera impedido.
    motivo = posiciones.primer_descubierto(candidato.asientos)
    if motivo is not None:
        raise AsientoInvalido(motivo)

    return (candidato, escritos)


def _con_asientos(libro: Libro, nuevos: list[Asiento]) -> Libro:
    """A copy of the book with the entries appended. Never mutates in place."""
    from dataclasses import replace

    return replace(libro, asientos=tuple(libro.asientos) + tuple(nuevos))
```

- [ ] **Step 5: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q
```

Esperado: `59 passed` (46 de la Task 1 más 13 nuevos).

- [ ] **Step 6: Commit**

```bash
git add seguimiento/libro.py seguimiento/posiciones.py tests/test_seguimiento_libro.py
git commit -m "feat: rechazar la venta y el retiro que el libro no soporta"
```

---

## Task 4: Precios sin ajustar, dividendos y splits

**Files:**
- Create: `seguimiento/precios.py`
- Test: `tests/test_seguimiento_precios.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_seguimiento_precios.py`:

```python
import pandas as pd
import pytest

from seguimiento import precios


def panel(datos: dict) -> pd.DataFrame:
    """Un DataFrame con la forma que devuelve yfinance: columnas (campo, ticker)."""
    return pd.DataFrame(
        datos,
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
    )


CRUDO = panel({
    ("Close", "AAPL"): [200.0, 202.0, 204.0],
    ("Close", "MSFT"): [400.0, 396.0, 398.0],
    ("Dividends", "AAPL"): [0.0, 0.24, 0.0],
    ("Dividends", "MSFT"): [0.0, 0.0, 0.0],
    ("Stock Splits", "AAPL"): [0.0, 0.0, 4.0],
    ("Stock Splits", "MSFT"): [0.0, 0.0, 0.0],
})


def test_separa_cierres_dividendos_y_splits():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert list(historia.cierres.columns) == ["AAPL", "MSFT"]
    assert historia.cierres.loc["2026-01-06", "AAPL"] == 202.0
    assert historia.dividendos.loc["2026-01-06", "AAPL"] == 0.24
    assert historia.splits.loc["2026-01-07", "AAPL"] == 4.0


def test_el_factor_de_split_multiplica_lo_comprado_antes():
    # Un 4:1 el dia 7 convierte 10 acciones compradas el dia 5 en 40. Sin esto,
    # la cartera parece haber perdido el 75% de un activo de un dia para otro.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.factor_split(historia, "AAPL", "2026-01-05", "2026-01-07") == 4.0
    assert precios.factor_split(historia, "AAPL", "2026-01-07", "2026-01-07") == 1.0


def test_sin_splits_el_factor_es_uno():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.factor_split(historia, "MSFT", "2026-01-05", "2026-01-07") == 1.0


def test_un_ticker_sin_datos_se_reporta_y_no_se_inventa():
    # Devolver una columna de NaN dejaria la cartera valorada en cero sin decir
    # por que. El nombre tiene que volver para que la pantalla lo diga.
    vacio = panel({
        ("Close", "AAPL"): [200.0, 202.0, 204.0],
        ("Close", "ZZZZ"): [float("nan")] * 3,
        ("Dividends", "AAPL"): [0.0, 0.0, 0.0],
        ("Dividends", "ZZZZ"): [0.0, 0.0, 0.0],
        ("Stock Splits", "AAPL"): [0.0, 0.0, 0.0],
        ("Stock Splits", "ZZZZ"): [0.0, 0.0, 0.0],
    })
    historia = precios.desde_panel(vacio, ["AAPL", "ZZZZ"])
    assert historia.sin_datos == ["ZZZZ"]
    assert list(historia.cierres.columns) == ["AAPL"]


def test_el_ultimo_precio_viene_con_su_fecha():
    # Un "valor de hoy" calculado con el cierre de hace un mes es una mentira
    # silenciosa: la fecha viaja con el precio para que se pueda decir.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    precio, cuando = precios.ultimo(historia, "AAPL")
    assert precio == 204.0
    assert cuando == "2026-01-07"


def test_un_ticker_que_no_esta_no_devuelve_un_precio_cualquiera():
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.ultimo(historia, "ZZZZ") == (None, None)


def test_el_cierre_de_un_dia_concreto_se_puede_pedir():
    # Es lo que rellena el precio cuando el usuario no lo recuerda, y lo que
    # marca esa operacion como `precio_estimado`.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.cierre_en(historia, "AAPL", "2026-01-06") == 202.0


def test_un_dia_sin_cotizacion_no_devuelve_el_cierre_de_otro_dia():
    # Festivo, fin de semana, o una fecha anterior a la salida a bolsa. Devolver
    # el cierre mas cercano dejaria registrada una compra a un precio de otro
    # dia sin que nada lo indicara.
    historia = precios.desde_panel(CRUDO, ["AAPL", "MSFT"])
    assert precios.cierre_en(historia, "AAPL", "2026-01-08") is None
    assert precios.cierre_en(historia, "ZZZZ", "2026-01-06") is None
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_precios.py -q
```

Esperado: `ImportError: cannot import name 'precios'`.

- [ ] **Step 3: Escribe el módulo**

Crea `seguimiento/precios.py`:

```python
"""Precios tal como se cotizaron, no como se leen hoy.

`data.py` descarga con `auto_adjust=True` y hace bien: el optimizador sólo usa
retornos, y el ajuste es consistente dentro de una descarga. Pero un precio
ajustado **cambia hacia atrás** cada vez que la empresa reparte un dividendo o
parte la acción, así que el precio al que se compró en enero no es el mismo
número dentro de tres meses. En un libro de posiciones eso produce un coste de
adquisición que se mueve solo, y nadie lo ve, porque el número resultante sigue
siendo plausible.

Módulo aparte y no un interruptor en `data.py`: un interruptor arriesga lo
contrario —que el optimizador reciba algún día precios sin ajustar sin que nadie
lo note— y ese fallo es igual de invisible.
"""

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

CAMPOS = ("Close", "Dividends", "Stock Splits")


@dataclass(frozen=True)
class Historia:
    """Cierres sin ajustar, dividendos por acción y splits, más lo que faltó."""

    cierres: pd.DataFrame
    dividendos: pd.DataFrame
    splits: pd.DataFrame
    sin_datos: list[str]


def descargar(tickers: list[str], desde: str, hasta: str | None = None) -> Historia:
    """Download unadjusted closes plus the corporate actions that move them.

    `auto_adjust=False` es el punto entero de este módulo. `actions=True` trae
    dividendos y splits en la misma petición, que es lo que evita una segunda
    ronda por ticker contra el mismo servidor.
    """
    crudo = yf.download(
        list(tickers),
        start=desde,
        end=hasta,
        auto_adjust=False,
        actions=True,
        progress=False,
    )
    return desde_panel(crudo, list(tickers))


def desde_panel(crudo: pd.DataFrame, tickers: list[str]) -> Historia:
    """Split yfinance's MultiIndex frame into the three tables we need.

    Vive separado de `descargar` para que todo lo de abajo se pueda probar sin
    tocar la red: los tests construyen el panel a mano.
    """
    tablas = {}
    for campo in CAMPOS:
        if campo in crudo.columns.get_level_values(0):
            tabla = crudo[campo]
        else:
            tabla = pd.DataFrame(index=crudo.index, columns=tickers, dtype=float)
        tablas[campo] = tabla.reindex(columns=tickers)

    cierres = tablas["Close"]
    # Un ticker que vuelve entero en blanco no es un ticker con precio cero: es
    # uno que no se descargo. Se aparta y se nombra, porque valorarlo a cero
    # dejaria la cartera mas pobre sin decir por que.
    sin_datos = [t for t in tickers if cierres[t].isna().all()]
    vivos = [t for t in tickers if t not in sin_datos]

    return Historia(
        cierres=cierres[vivos],
        dividendos=tablas["Dividends"][vivos].fillna(0.0),
        splits=tablas["Stock Splits"][vivos].fillna(0.0),
        sin_datos=sin_datos,
    )


def factor_split(
    historia: Historia, ticker: str, desde: str, hasta: str
) -> float:
    """How many shares one share bought on `desde` has become by `hasta`.

    El rango excluye `desde` e incluye `hasta`: una acción comprada **el mismo
    día** del split ya se compró partida, así que aplicarle el factor la
    contaría dos veces.
    """
    if ticker not in historia.splits.columns:
        return 1.0
    tramo = historia.splits[ticker]
    tramo = tramo[(tramo.index > pd.Timestamp(desde)) & (tramo.index <= pd.Timestamp(hasta))]
    factor = 1.0
    for valor in tramo:
        if valor and valor > 0:
            factor *= float(valor)
    return factor


def ultimo(historia: Historia, ticker: str) -> tuple[float | None, str | None]:
    """The most recent close and the day it is from, or (None, None).

    La fecha vuelve siempre con el precio, y no como un extra opcional, porque
    es lo único que separa "vale esto hoy" de "vale esto según un cierre de hace
    un mes que nadie ha vuelto a mirar".
    """
    if ticker not in historia.cierres.columns:
        return (None, None)
    serie = historia.cierres[ticker].dropna()
    if serie.empty:
        return (None, None)
    return (float(serie.iloc[-1]), serie.index[-1].strftime("%Y-%m-%d"))


def cierre_en(historia: Historia, ticker: str, fecha: str) -> float | None:
    """That day's close, or None if the market was shut or the ticker unknown.

    **Nunca el cierre más cercano.** Si el día pedido no cotizó —festivo, fin de
    semana, o una fecha anterior a la salida a bolsa— la respuesta es `None`, y
    quien llama rechaza el asiento. Rellenar con el cierre de otro día dejaría
    registrada una compra a un precio que no existió esa fecha, y el número
    resultante sería perfectamente plausible.
    """
    if ticker not in historia.cierres.columns:
        return None
    try:
        valor = historia.cierres.at[pd.Timestamp(fecha), ticker]
    except KeyError:
        return None
    return None if pd.isna(valor) else float(valor)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_precios.py -q
```

Esperado: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/precios.py tests/test_seguimiento_precios.py
git commit -m "feat: precios sin ajustar, con dividendos y splits"
```

---

## Task 5: La serie diaria de valor, con splits aplicados

**Files:**
- Modify: `seguimiento/posiciones.py` (añadir `serie`)
- Test: `tests/test_seguimiento_posiciones.py` (añadir al final)

- [ ] **Step 1: Escribe los tests que fallan**

Añade al final de `tests/test_seguimiento_posiciones.py`:

```python
import pandas as pd

from seguimiento import precios


def historia(cierres: dict, splits: dict | None = None, dividendos: dict | None = None):
    fechas = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    ceros = {t: [0.0] * 3 for t in cierres}
    return precios.Historia(
        cierres=pd.DataFrame(cierres, index=fechas),
        dividendos=pd.DataFrame(dividendos or ceros, index=fechas),
        splits=pd.DataFrame(splits or ceros, index=fechas),
        sin_datos=[],
    )


def test_el_valor_diario_suma_acciones_por_cierre_mas_efectivo():
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # Dia 5: 40 acciones a 200 = 8.000, mas 1.999 de efectivo.
    assert marcha.valor.loc["2026-01-05"] == pytest.approx(9999.0)
    assert marcha.valor.loc["2026-01-07"] == pytest.approx(40 * 204.0 + 1999.0)


def test_un_split_multiplica_las_acciones_compradas_antes():
    h = historia(
        {"AAPL": [200.0, 202.0, 51.0]},
        splits={"AAPL": [0.0, 0.0, 4.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # 40 acciones a 200 pasan a 160 a 51: el valor apenas se mueve, que es lo
    # que de verdad ocurre. Sin aplicar el split, la cartera "perderia" un 75%.
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(160.0)
    assert marcha.valor.loc["2026-01-07"] == pytest.approx(160 * 51.0 + 1999.0)


def test_los_flujos_externos_son_solo_aportaciones_y_retiros():
    # Un dividendo o una compra no son dinero del usuario entrando: contarlos
    # aqui inflaria el capital aportado con lo que la cartera acaba de ganar.
    dividendo = asiento("a3", "2026-01-06", "dividendo", ticker="AAPL", importe=9.6)
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA, dividendo], h)
    assert marcha.flujos.loc["2026-01-05"] == pytest.approx(10_000.0)
    assert marcha.flujos.loc["2026-01-06"] == pytest.approx(0.0)


def test_el_dividendo_calculado_entra_en_efectivo():
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA], h)
    # 40 acciones por 0,24 = 9,60 que entran el dia 6 y siguen el dia 7.
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(1999.0 + 9.6)


def test_un_dividendo_apuntado_a_mano_manda_sobre_el_calculado():
    # El calculado es teorico y bruto; el escrito por el usuario es el neto que
    # le llego de verdad. Sumar los dos contaria el cobro dos veces.
    manual = asiento("a3", "2026-01-06", "dividendo", ticker="AAPL", importe=7.1)
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, manual], h)
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(1999.0 + 7.1)


def test_una_compra_en_la_fecha_ex_no_cobra_ese_dividendo():
    # Para cobrar hay que tener las acciones ANTES de la fecha ex: quien compra
    # ese mismo dia las compra ya sin el dividendo, y el cobro es del vendedor.
    # Medido sobre la version que aplicaba los asientos antes de pagar: una
    # compra de diez acciones el dia ex se llevaba 2,40 que no le tocaban.
    tardia = asiento(
        "a3", "2026-01-06", "compra", ticker="AAPL",
        acciones=10.0, precio=202.0, importe=2020.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, tardia], h)
    assert float(marcha.dividendos.sum().sum()) == pytest.approx(0.0)


def test_una_venta_en_la_fecha_ex_si_cobra_el_dividendo():
    # El reverso, y sale de la misma foto: quien vende en la fecha ex ya tenia
    # las acciones al cierre anterior, asi que el dividendo es suyo.
    venta = asiento(
        "a3", "2026-01-06", "venta", ticker="AAPL",
        acciones=40.0, precio=202.0, importe=8080.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, venta], h)
    assert float(marcha.dividendos.sum().sum()) == pytest.approx(9.6)


def test_un_hueco_de_precio_no_hunde_el_valor_a_cero():
    # `(acciones * cierres).sum(axis=1)` trata un NaN como cero por defecto, asi
    # que un dia sin dato dibujaria una caida a plomo que nunca ocurrio.
    h = historia({"AAPL": [200.0, float("nan"), 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA], h)
    assert marcha.valor.loc["2026-01-06"] == pytest.approx(40 * 200.0 + 1999.0)


def test_un_asiento_posterior_al_ultimo_cierre_se_cuenta_aparte():
    # Pasa cada vez que se registra una compra de hoy antes de que yfinance
    # tenga el cierre de hoy. La tabla por activo si la ve, porque sale de los
    # asientos; la serie no puede valorarla. Sin este contador, el valor de
    # cabecera y la tabla dirian cosas distintas y nada lo explicaria.
    manana = asiento(
        "a3", "2026-01-08", "compra", ticker="AAPL",
        acciones=1.0, precio=204.0, importe=204.0,
    )
    h = historia({"AAPL": [200.0, 202.0, 204.0]})
    marcha = posiciones.serie([APORTA, COMPRA, manana], h)
    assert marcha.posteriores == 1
    assert marcha.acciones.loc["2026-01-07", "AAPL"] == pytest.approx(40.0)


def test_un_dividendo_posterior_a_la_venta_no_se_cobra():
    venta = asiento(
        "a3", "2026-01-05", "venta", ticker="AAPL",
        acciones=40.0, precio=200.0, importe=8000.0,
    )
    h = historia(
        {"AAPL": [200.0, 202.0, 204.0]},
        dividendos={"AAPL": [0.0, 0.24, 0.0]},
    )
    marcha = posiciones.serie([APORTA, COMPRA, venta], h)
    assert marcha.efectivo.loc["2026-01-07"] == pytest.approx(9999.0)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_posiciones.py -q
```

Esperado: `AttributeError: module 'seguimiento.posiciones' has no attribute 'serie'`.

- [ ] **Step 3: Implementa `serie`**

Añade a `seguimiento/posiciones.py` (arriba, junto a los imports, añade
`import pandas as pd` y `from seguimiento.precios import Historia`):

```python
@dataclass(frozen=True)
class Marcha:
    """La cartera día a día: acciones, efectivo, valor y flujos externos.

    `posteriores` son los asientos fechados **después** del último cierre
    disponible, que la serie no puede reflejar porque no hay precio con el que
    valorarlos. Vuelven contados y no en silencio: la tabla por activo sí los
    incluye —sale de los asientos, no de la serie— así que sin este aviso el
    valor de cabecera y la tabla dirían cosas distintas y nada explicaría por
    qué.
    """

    acciones: pd.DataFrame
    efectivo: pd.Series
    valor: pd.Series
    flujos: pd.Series
    dividendos: pd.DataFrame
    posteriores: int = 0


def serie(asientos: "list[Asiento]", historia: Historia) -> Marcha:
    """Walk the ledger forward one trading day at a time.

    El calendario lo pone el índice de precios, no `pandas.bdate_range`: los
    días hábiles de un calendario genérico incluyen festivos de mercado, y un
    día sin cotización valorado con el cierre anterior inventa un día de
    rendimiento cero que nunca existió.

    Los dividendos calculados —acciones en cartera en la fecha ex, por el
    dividendo por acción— se aplican **salvo** que exista un asiento manual de
    `dividendo` para ese ticker y esa fecha. El manual es el neto que llegó de
    verdad; el calculado es teórico y bruto. Sumar los dos contaría el cobro dos
    veces, y el rendimiento saldría alto sin causa visible.

    **El dividendo se paga sobre la tenencia de antes de los movimientos del
    día, no de después.** Para cobrar hay que tener las acciones *antes* de la
    fecha ex: quien compra ese mismo día las compra ya sin el dividendo, y el
    cobro es del vendedor. Aplicar los asientos primero y pagar después le paga
    al comprador — medido: una compra de diez acciones el día ex cobraba 2,40
    que no le tocaban. El reverso también importa y sale gratis con la misma
    foto: quien vende en la fecha ex sí cobra, porque las tenía al cierre
    anterior.
    """
    vivos = ordenados(vigentes(asientos))
    if not vivos:
        vacio = pd.Series(dtype=float)
        return Marcha(pd.DataFrame(), vacio, vacio, vacio, pd.DataFrame())

    calendario = historia.cierres.index
    tickers = list(historia.cierres.columns)
    # Un hueco de precio en un dia que el mercado abrio es un fallo de datos,
    # no una accion que valga cero. Sin esto, `(acciones * cierres).sum()`
    # trata el NaN como cero --su comportamiento por defecto-- y el grafico
    # ensena una caida a plomo que nunca ocurrio. Arrastrar el ultimo cierre
    # conocido es lo que hace cualquier extracto de broker. Esta acotado:
    # `precios.desde_panel` ya aparta los tickers que no traen ningun dato.
    cierres = historia.cierres.ffill()

    acciones = pd.DataFrame(0.0, index=calendario, columns=tickers)
    efectivo = pd.Series(0.0, index=calendario)
    flujos = pd.Series(0.0, index=calendario)
    dividendos = pd.DataFrame(0.0, index=calendario, columns=tickers)

    # Los dividendos que el usuario apunto a mano, indexados para que el
    # calculado sepa cuando callarse.
    manuales = {
        (a.ticker, a.fecha) for a in vivos if a.tipo == "dividendo"
    }

    tenencia: dict[str, float] = {}
    caja = 0.0
    pendientes = list(vivos)

    for dia in calendario:
        clave = dia.strftime("%Y-%m-%d")

        # 1. Los splits del dia parten lo que ya se tenia.
        for ticker in tickers:
            factor = float(historia.splits.at[dia, ticker] or 0.0)
            if factor > 0 and tenencia.get(ticker):
                tenencia[ticker] *= factor

        # 2. La foto de lo que se tenia al cierre de ayer, ya partida por el
        #    split de hoy si lo hubo. Es la que decide quien cobra el dividendo,
        #    y por eso se toma ANTES de los movimientos del dia.
        tenencia_ex = dict(tenencia)

        # 3. Los asientos fechados hasta hoy que aun no se han aplicado.
        while pendientes and pendientes[0].fecha <= clave:
            a = pendientes.pop(0)
            if a.tipo == "aportacion":
                caja += a.importe
                flujos[dia] += a.importe
            elif a.tipo == "retiro":
                caja -= a.importe
                flujos[dia] -= a.importe
            elif a.tipo == "dividendo":
                caja += a.importe
                if a.ticker in dividendos.columns:
                    dividendos.at[dia, a.ticker] += a.importe
            elif a.tipo == "compra":
                caja -= a.importe + a.comision
                tenencia[a.ticker] = tenencia.get(a.ticker, 0.0) + a.acciones
            elif a.tipo == "venta":
                caja += a.importe - a.comision
                tenencia[a.ticker] = tenencia.get(a.ticker, 0.0) - a.acciones

        # 4. Los dividendos calculados, sobre la foto de la fecha ex.
        for ticker in tickers:
            por_accion = float(historia.dividendos.at[dia, ticker] or 0.0)
            if por_accion <= 0 or (ticker, clave) in manuales:
                continue
            cobro = tenencia_ex.get(ticker, 0.0) * por_accion
            if cobro:
                caja += cobro
                dividendos.at[dia, ticker] += cobro

        for ticker in tickers:
            acciones.at[dia, ticker] = tenencia.get(ticker, 0.0)
        efectivo[dia] = caja

    valor = (acciones * cierres).sum(axis=1) + efectivo
    return Marcha(
        acciones=acciones,
        efectivo=efectivo,
        valor=valor,
        flujos=flujos,
        dividendos=dividendos,
        # Lo que quedo en la cola son asientos posteriores al ultimo cierre
        # disponible. No se pierden --la tabla por activo los ve-- pero la serie
        # no puede valorarlos, y quien pinte esto tiene que poder decirlo.
        posteriores=len(pendientes),
    )
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_posiciones.py -q
```

Esperado: `19 passed`.

- [ ] **Step 5: Comprueba que la foto de la fecha ex se usa de verdad**

Cambia `tenencia_ex.get(ticker, 0.0)` por `tenencia.get(ticker, 0.0)` en el
paso 4 y vuelve a correr los tests. Tiene que fallar
`test_una_compra_en_la_fecha_ex_no_cobra_ese_dividendo` — y sólo ese, porque el
de la venta pasa con las dos versiones. Deshaz el cambio.

Si no falla, la foto no está donde tiene que estar y el libro le paga
dividendos a quien no le tocan.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/posiciones.py tests/test_seguimiento_posiciones.py
git commit -m "feat: la serie diaria de valor, con splits y dividendos"
```

---

## Task 6: TWR, con sus dos guardas

**Files:**
- Create: `seguimiento/rendimiento.py`
- Test: `tests/test_seguimiento_rendimiento.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_seguimiento_rendimiento.py`:

```python
import numpy as np
import pandas as pd
import pytest

from seguimiento import rendimiento


def serie(valores, fechas=None) -> pd.Series:
    fechas = fechas or pd.bdate_range("2026-01-05", periods=len(valores))
    return pd.Series(valores, index=pd.DatetimeIndex(fechas), dtype=float)


def test_sin_flujos_el_twr_es_el_retorno_simple():
    valor = serie([100.0, 110.0, 121.0])
    flujos = serie([0.0, 0.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_una_aportacion_no_cuenta_como_ganancia():
    # Sin descontar el flujo, meter 100 en una cartera de 100 se leeria como un
    # 100% de rentabilidad en un dia. Es el error que hace falta que no ocurra.
    valor = serie([100.0, 200.0, 200.0])
    flujos = serie([0.0, 100.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.0)


def test_el_twr_calculado_a_mano_no_es_el_retorno_simple():
    # 100 -> 110 (+10%), se aportan 90, 200 -> 220 (+10%). El TWR es 1,1*1,1-1
    # = 21%. El retorno simple sobre lo aportado daria (220-190)/190 = 15,8%.
    # Este test existe para que el dia que alguien "simplifique" la formula,
    # falle.
    valor = serie([100.0, 200.0, 220.0])
    flujos = serie([0.0, 90.0, 0.0])
    assert rendimiento.twr(valor, flujos) == pytest.approx(0.21)


def test_un_valor_inicial_de_cero_no_revienta_ni_devuelve_infinito():
    # Pasa el primer dia y cada vez que la cartera se vacia y vuelve a empezar.
    valor = serie([0.0, 100.0, 110.0])
    flujos = serie([0.0, 100.0, 0.0])
    resultado = rendimiento.twr(valor, flujos)
    assert np.isfinite(resultado)
    assert resultado == pytest.approx(0.1)


def test_anualizar_por_debajo_del_minimo_no_se_hace():
    # Un 2% en tres dias anualiza a +780%. Devolver eso seria una afirmacion
    # que los datos no sostienen.
    assert rendimiento.anualizar(0.02, dias=3) is None


def test_anualizar_por_encima_del_minimo_si_se_hace():
    assert rendimiento.anualizar(0.10, dias=365) == pytest.approx(0.10)


def test_anualizar_medio_ano_capitaliza():
    assert rendimiento.anualizar(0.10, dias=182.5) == pytest.approx(0.21, abs=1e-3)


def test_el_minimo_es_treinta_dias():
    assert rendimiento.MINIMO_DIAS_ANUALIZAR == 30
    assert rendimiento.anualizar(0.02, dias=29) is None
    assert rendimiento.anualizar(0.02, dias=30) is not None
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `ImportError: cannot import name 'rendimiento'`.

- [ ] **Step 3: Escribe el módulo**

Crea `seguimiento/rendimiento.py`:

```python
"""Cuánto rindió la cartera, medido de las dos formas que hacen falta.

Con aportaciones de por medio ningún número suelto responde las dos preguntas.
`valor actual / total aportado − 1` no es el rendimiento de la cartera: mezcla
lo que rindieron los activos con cuándo entró el dinero.

- **TWR** neutraliza el calendario de aportaciones y es lo único comparable
  contra el S&P 500 o contra 1/N.
- **TIR** es lo que ganó el usuario de verdad, con su timing dentro.

Cuando los dos se separan, la diferencia *es* el efecto de las aportaciones. Es
información, no ruido, y la pantalla lo dice.
"""

import pandas as pd

# Por debajo de un mes, anualizar convierte un ruido en una afirmación: un 2% en
# tres días sale a +780% anual. Se devuelve el retorno del periodo, sin
# anualizar, y quien lo muestra dice que lo es.
MINIMO_DIAS_ANUALIZAR = 30

# Cualquier valor de cartera por debajo de esto es polvo de redondeo, no
# capital. Sirve de denominador cero.
_MINIMO_DENOMINADOR = 1e-9


def twr(valor: pd.Series, flujos: pd.Series) -> float:
    """Time-weighted return over the whole series, not annualised.

    `r_t = (V_t − F_t) / V_{t−1} − 1`, encadenado. El flujo se trata como si
    llegara al final del día: el dinero que entró hoy no participó del
    movimiento de hoy desde el cierre de ayer, que es lo que este cociente mide.

    Eso deja fuera el movimiento intradía de lo comprado hoy —se compró a un
    precio y cerró a otro— y es la aproximación estándar del TWR diario. El
    efecto es de céntimos frente a la alternativa, que sería valorar la cartera
    dos veces al día con datos que yfinance no da.

    **`V_{t−1} = 0` no es una división por cero, es un día sin cartera.** Pasa el
    primer día y cada vez que se vacía y se vuelve a empezar. El retorno de ese
    día es indefinido y se toma como 0: no hubo capital expuesto, así que no
    hubo nada que rindiera.
    """
    if len(valor) < 2:
        return 0.0

    factor = 1.0
    anterior = float(valor.iloc[0])
    for dia in valor.index[1:]:
        actual = float(valor.loc[dia])
        flujo = float(flujos.loc[dia]) if dia in flujos.index else 0.0
        if anterior > _MINIMO_DENOMINADOR:
            factor *= (actual - flujo) / anterior
        anterior = actual
    return factor - 1.0


def anualizar(retorno: float, dias: float) -> float | None:
    """The period return as an annual rate, or None when the period is too short.

    Devolver `None` y no un número es deliberado: quien lo pinta usa
    `cartera.formato_cifra`, que escribe "—" y nunca un 0,00. Un cero ahí se
    leería como "no rindió nada", que es una afirmación que nadie hizo.
    """
    if dias < MINIMO_DIAS_ANUALIZAR or dias <= 0:
        return None
    return (1.0 + retorno) ** (365.0 / dias) - 1.0
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/rendimiento.py tests/test_seguimiento_rendimiento.py
git commit -m "feat: TWR encadenado, con la guarda del denominador cero"
```

---

## Task 7: TIR (XIRR), y el control negativo que ata las tres medidas

**Files:**
- Modify: `seguimiento/rendimiento.py` (añadir `tir`)
- Test: `tests/test_seguimiento_rendimiento.py` (añadir al final)

- [ ] **Step 1: Escribe los tests que fallan**

Añade al final de `tests/test_seguimiento_rendimiento.py`:

```python
from datetime import date


def test_un_solo_flujo_da_la_tasa_anualizada_conocida():
    # 1.000 fuera hoy, 1.100 dentro de un ano: 10% anual, exacto.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), 1100.0)]
    assert rendimiento.tir(flujos) == pytest.approx(0.10, abs=1e-4)


def test_dos_aportaciones_dan_una_tir_entre_las_dos_tasas():
    flujos = [
        (date(2026, 1, 1), -1000.0),
        (date(2026, 7, 1), -1000.0),
        (date(2027, 1, 1), 2200.0),
    ]
    resultado = rendimiento.tir(flujos)
    assert 0.10 < resultado < 0.30


def test_sin_cambio_de_signo_no_hay_tir_y_se_dice():
    # Todos los flujos negativos: no existe tasa que los anule. Devolver la
    # primera raiz que aparezca seria inventar un numero indistinguible de uno
    # real.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), -500.0)]
    assert rendimiento.tir(flujos) is None


def test_un_solo_flujo_tampoco_tiene_tir():
    assert rendimiento.tir([(date(2026, 1, 1), -1000.0)]) is None


def test_un_periodo_corto_no_devuelve_una_tir_anualizada_absurda():
    # 2% en tres dias. Misma guarda que TWR: por debajo de 30 dias no se
    # anualiza, y aqui la TIR *es* una tasa anual, asi que no hay nada que dar.
    flujos = [(date(2026, 1, 1), -1000.0), (date(2026, 1, 4), 1020.0)]
    assert rendimiento.tir(flujos) is None


def test_control_negativo_una_sola_compra_ata_las_tres_medidas():
    # Cartera de una sola compra, sin aportaciones posteriores, sin dividendos
    # y sin comision. Las tres medidas estan ligadas por identidad:
    #   - TWR sin anualizar == retorno simple
    #   - TIR == TWR anualizado
    # Escrito como "los tres numeros coinciden" el test seria falso: la TIR
    # viene anualizada y el retorno simple no. Pasaria o fallaria por la razon
    # equivocada.
    fechas = pd.bdate_range("2026-01-01", periods=200)
    valores = np.linspace(1000.0, 1200.0, len(fechas))
    valor = serie(valores, fechas)
    flujos = serie([1000.0] + [0.0] * (len(fechas) - 1), fechas)

    simple = valores[-1] / valores[0] - 1.0
    medido = rendimiento.twr(valor, flujos)
    assert medido == pytest.approx(simple, rel=1e-9)

    dias = (fechas[-1].date() - fechas[0].date()).days
    esperada = rendimiento.anualizar(medido, dias=dias)
    calculada = rendimiento.tir([
        (fechas[0].date(), -1000.0),
        (fechas[-1].date(), float(valores[-1])),
    ])
    assert calculada == pytest.approx(esperada, rel=1e-6)


@pytest.mark.parametrize("caso", [
    [(date(2026, 1, 1), -1000.0), (date(2027, 1, 1), 1100.0)],
    [(date(2026, 1, 1), -5000.0), (date(2026, 6, 1), -2000.0),
     (date(2027, 3, 1), 7800.0)],
])
def test_contraste_contra_numpy_financial(caso):
    # Implementacion nativa contrastada contra una libreria externa, en un test
    # que se omite solo si no esta instalada: el patron que este repo ya usa con
    # Ledoit-Wolf frente a scikit-learn y con RSI frente a pandas-ta-classic.
    npf = pytest.importorskip("numpy_financial")
    fechas = [f for f, _ in caso]
    importes = [v for _, v in caso]
    referencia = npf.xirr(importes, fechas)
    assert rendimiento.tir(caso) == pytest.approx(referencia, abs=1e-6)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `AttributeError: module 'seguimiento.rendimiento' has no attribute 'tir'`.

- [ ] **Step 3: Implementa `tir`**

Añade a `seguimiento/rendimiento.py` (y arriba, junto a los imports,
`from datetime import date` y `from scipy.optimize import brentq`):

```python
# El intervalo en el que se busca la raiz. -0,999 y no -1: en -1 el
# denominador (1+r) vale cero y la funcion no esta definida. El techo de 10 son
# 1.000% anual, muy por encima de cualquier cartera real, y acotar es lo que
# convierte "no converge" en "no hay solucion aqui" en vez de en un bucle.
_SUELO_TIR = -0.999
_TECHO_TIR = 10.0


def _valor_actual(flujos: "list[tuple[date, float]]", tasa: float) -> float:
    origen = flujos[0][0]
    return sum(
        importe / (1.0 + tasa) ** ((cuando - origen).days / 365.0)
        for cuando, importe in flujos
    )


def tir(flujos: "list[tuple[date, float]]") -> float | None:
    """Money-weighted return (XIRR), or None when there is no answer.

    Raíz de `Σ CF_i / (1+r)^(d_i/365) = 0`, con `brentq` sobre un intervalo
    acotado. Aportaciones negativas, retiros positivos, y el valor actual de la
    cartera positivo al cierre.

    **Devuelve `None` en vez de un número siempre que no haya una respuesta
    defendible.** Con flujos mezclados la ecuación puede tener varias raíces o
    ninguna, y una TIR inventada es indistinguible de una real: no lleva marca,
    no tiene unidades raras, y el usuario la lee como si alguien la hubiera
    medido. Los tres casos en que se devuelve `None`:

    - **Menos de dos flujos.** No hay ecuación que resolver.
    - **Todos del mismo signo.** No existe tasa que los anule, porque el valor
      actual nunca cruza el cero.
    - **Menos de 30 días.** Misma guarda que `anualizar`: la TIR *es* una tasa
      anual, así que en tres días no hay nada que dar.
    """
    if len(flujos) < 2:
        return None

    ordenados = sorted(flujos, key=lambda par: par[0])
    dias = (ordenados[-1][0] - ordenados[0][0]).days
    if dias < MINIMO_DIAS_ANUALIZAR:
        return None

    importes = [importe for _, importe in ordenados]
    if not (any(v > 0 for v in importes) and any(v < 0 for v in importes)):
        return None

    bajo = _valor_actual(ordenados, _SUELO_TIR)
    alto = _valor_actual(ordenados, _TECHO_TIR)
    if bajo == 0.0:
        return _SUELO_TIR
    if alto == 0.0:
        return _TECHO_TIR
    if (bajo > 0) == (alto > 0):
        # Sin cambio de signo en el intervalo no hay raiz que encontrar dentro
        # de el. brentq lanzaria ValueError; decirlo con None es la respuesta.
        return None

    try:
        return float(brentq(lambda r: _valor_actual(ordenados, r), _SUELO_TIR, _TECHO_TIR))
    except (ValueError, RuntimeError):
        return None
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `15 passed`. Los dos de `numpy_financial` saldrán como `skipped` si
no está instalada — eso es correcto y no hay que instalarla.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/rendimiento.py tests/test_seguimiento_rendimiento.py
git commit -m "feat: TIR con brentq, y no calculable en vez de un numero inventado"
```

---

## Task 8: Coste medio, ganancia y contribución por activo

**Files:**
- Modify: `seguimiento/rendimiento.py` (añadir `por_activo`)
- Test: `tests/test_seguimiento_rendimiento.py` (añadir al final)

- [ ] **Step 1: Escribe los tests que fallan**

Añade al final de `tests/test_seguimiento_rendimiento.py`:

```python
from seguimiento.libro import Asiento


def ap(id_, fecha, importe):
    return Asiento(id=id_, fecha=fecha, tipo="aportacion", importe=importe)


def cp(id_, fecha, ticker, acciones, precio, comision=0.0):
    return Asiento(
        id=id_, fecha=fecha, tipo="compra", ticker=ticker,
        acciones=acciones, precio=precio, importe=acciones * precio,
        comision=comision,
    )


def vt(id_, fecha, ticker, acciones, precio, comision=0.0):
    return Asiento(
        id=id_, fecha=fecha, tipo="venta", ticker=ticker,
        acciones=acciones, precio=precio, importe=acciones * precio,
        comision=comision,
    )


def test_el_coste_medio_pondera_las_dos_compras():
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "AAPL", 10.0, 200.0),
        cp("c2", "2026-02-05", "AAPL", 10.0, 240.0),
    ]
    linea = rendimiento.por_activo(asientos, {"AAPL": 250.0})["AAPL"]
    assert linea.acciones == pytest.approx(20.0)
    assert linea.coste_medio == pytest.approx(220.0)


def test_la_comision_entra_en_el_coste_medio():
    # Es dinero que salio para tener esas acciones. Dejarla fuera haria que el
    # coste medio no fuera el que se pago de verdad.
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "AAPL", 10.0, 200.0, comision=20.0),
    ]
    linea = rendimiento.por_activo(asientos, {"AAPL": 250.0})["AAPL"]
    assert linea.coste_medio == pytest.approx(202.0)


def test_la_ganancia_latente_es_valor_menos_coste_de_lo_que_queda():
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "AAPL", 10.0, 200.0),
    ]
    linea = rendimiento.por_activo(asientos, {"AAPL": 250.0})["AAPL"]
    assert linea.valor == pytest.approx(2500.0)
    assert linea.latente == pytest.approx(500.0)
    assert linea.realizada == pytest.approx(0.0)


def test_una_venta_realiza_ganancia_al_coste_medio():
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "AAPL", 10.0, 200.0),
        cp("c2", "2026-02-05", "AAPL", 10.0, 240.0),
        vt("v1", "2026-03-05", "AAPL", 5.0, 300.0),
    ]
    linea = rendimiento.por_activo(asientos, {"AAPL": 300.0})["AAPL"]
    # Coste medio 220; se venden 5 a 300: (300-220)*5 = 400 realizados.
    assert linea.realizada == pytest.approx(400.0)
    assert linea.acciones == pytest.approx(15.0)
    # El coste medio no cambia al vender: sigue siendo 220.
    assert linea.coste_medio == pytest.approx(220.0)


def test_los_dividendos_cobrados_se_cuentan_aparte_del_precio():
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "AAPL", 10.0, 200.0),
        Asiento(id="d1", fecha="2026-02-05", tipo="dividendo",
                ticker="AAPL", importe=24.0),
    ]
    linea = rendimiento.por_activo(asientos, {"AAPL": 250.0})["AAPL"]
    assert linea.dividendos == pytest.approx(24.0)
    # La contribucion suma las tres piezas: latente, realizada y dividendos.
    assert linea.contribucion == pytest.approx(500.0 + 0.0 + 24.0)


def test_un_activo_sin_precio_no_se_valora_a_cero():
    # Valorarlo a cero restaria toda la posicion de la ganancia sin decir por
    # que. La linea vuelve con valor None y quien la pinta escribe "—".
    asientos = [
        ap("a", "2026-01-05", 10_000.0),
        cp("c1", "2026-01-05", "ZZZZ", 10.0, 200.0),
    ]
    linea = rendimiento.por_activo(asientos, {})["ZZZZ"]
    assert linea.valor is None
    assert linea.latente is None
    assert linea.contribucion is None
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `AttributeError: ... has no attribute 'por_activo'`.

- [ ] **Step 3: Implementa `por_activo`**

Añade a `seguimiento/rendimiento.py` (y arriba, `from dataclasses import
dataclass` y `from seguimiento import posiciones`):

```python
@dataclass(frozen=True)
class Linea:
    """Un activo del libro: lo que se tiene, lo que costó y lo que ha dado."""

    ticker: str
    acciones: float
    coste_medio: float
    precio: float | None
    valor: float | None
    latente: float | None
    realizada: float
    dividendos: float
    contribucion: float | None


def por_activo(
    asientos: "list", precios_actuales: dict[str, float]
) -> dict[str, Linea]:
    """Per-asset cost, gain and contribution, in dollars.

    **Coste medio ponderado, no FIFO.** Cambia el reparto entre ganancia
    realizada y latente, nunca el total. Es más simple, no pretende ser un
    cálculo fiscal, y queda declarado en pantalla.

    La contribución va **en dólares**: cuánto de la ganancia total viene de cada
    activo. Es exacto y suma. Un porcentaje de contribución con aportaciones de
    por medio compara cada activo contra un capital que no fue el suyo durante
    todo el periodo, y por eso no se muestra.

    Un activo sin precio actual vuelve con `valor`, `latente` y `contribucion`
    en `None`, no en cero. Valorarlo a cero restaría la posición entera de la
    ganancia sin decir por qué; `None` es lo que hace que quien lo pinta escriba
    "—" con `cartera.formato_cifra`.
    """
    acciones: dict[str, float] = {}
    coste: dict[str, float] = {}
    realizada: dict[str, float] = {}
    dividendos: dict[str, float] = {}

    for a in posiciones.ordenados(posiciones.vigentes(asientos)):
        if a.tipo == "compra":
            acciones[a.ticker] = acciones.get(a.ticker, 0.0) + a.acciones
            coste[a.ticker] = coste.get(a.ticker, 0.0) + a.importe + a.comision
        elif a.tipo == "venta":
            tiene = acciones.get(a.ticker, 0.0)
            medio = (coste.get(a.ticker, 0.0) / tiene) if tiene else 0.0
            realizada[a.ticker] = (
                realizada.get(a.ticker, 0.0)
                + (a.precio - medio) * a.acciones
                - a.comision
            )
            acciones[a.ticker] = tiene - a.acciones
            # El coste baja en proporcion a lo vendido, para que el coste medio
            # de lo que queda no se mueva: vender no cambia lo que costo el
            # resto.
            coste[a.ticker] = medio * acciones[a.ticker]
        elif a.tipo == "dividendo":
            dividendos[a.ticker] = dividendos.get(a.ticker, 0.0) + a.importe

    lineas = {}
    for ticker in sorted(set(acciones) | set(realizada) | set(dividendos)):
        n = acciones.get(ticker, 0.0)
        c = coste.get(ticker, 0.0)
        medio = c / n if n else 0.0
        precio = precios_actuales.get(ticker)
        valor = n * precio if precio is not None else None
        latente = valor - c if valor is not None else None
        real = realizada.get(ticker, 0.0)
        divs = dividendos.get(ticker, 0.0)
        lineas[ticker] = Linea(
            ticker=ticker,
            acciones=n,
            coste_medio=medio,
            precio=precio,
            valor=valor,
            latente=latente,
            realizada=real,
            dividendos=divs,
            contribucion=None if latente is None else latente + real + divs,
        )
    return lineas
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_rendimiento.py -q
```

Esperado: `21 passed` (o `19 passed, 2 skipped` sin `numpy_financial`).

- [ ] **Step 5: Commit**

```bash
git add seguimiento/rendimiento.py tests/test_seguimiento_rendimiento.py
git commit -m "feat: coste medio, ganancia realizada y latente, contribucion en dolares"
```

---

## Task 9: Las tres referencias sobre los mismos flujos

**Files:**
- Create: `seguimiento/comparacion.py`
- Test: `tests/test_seguimiento_comparacion.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_seguimiento_comparacion.py`:

```python
import pandas as pd
import pytest

from seguimiento import comparacion

FECHAS = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])

CIERRES = pd.DataFrame(
    {"AAPL": [100.0, 110.0, 121.0], "MSFT": [100.0, 100.0, 100.0]},
    index=FECHAS,
)


def test_una_referencia_invierte_cada_flujo_a_sus_pesos():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1210.0)


def test_reparte_por_los_pesos_y_no_rebalancea():
    # 50/50 el dia 5. El dia 7 AAPL vale 605 y MSFT 500: los pesos ya no son
    # 50/50, y eso es el punto. La referencia es "si hubieras seguido el plan",
    # no "si hubieras rebalanceado a diario".
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "MSFT": 0.5}, CIERRES)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_flujo_posterior_compra_a_los_precios_de_su_dia():
    # Los 1.000 del dia 6 compran AAPL a 110, no a 100. Si comprara a 100, la
    # referencia se estaria beneficiando de informacion que no tenia.
    flujos = pd.Series([0.0, 1000.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    assert valores.iloc[0] == pytest.approx(0.0)
    assert valores.iloc[1] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(1100.0)


def test_un_retiro_saca_dinero_a_prorrata():
    flujos = pd.Series([1000.0, -500.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 1.0}, CIERRES)
    # Dia 6: 1.100 menos 500 = 600. Dia 7: 600 * 1,1 = 660.
    assert valores.iloc[1] == pytest.approx(600.0)
    assert valores.iloc[2] == pytest.approx(660.0)


def test_equal_weight_reparte_entre_los_tickers_que_hay():
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    pesos = comparacion.equal_weight(["AAPL", "MSFT"])
    assert pesos == {"AAPL": 0.5, "MSFT": 0.5}
    valores = comparacion.referencia(flujos, pesos, CIERRES)
    assert valores.iloc[2] == pytest.approx(1105.0)


def test_un_peso_sobre_un_ticker_sin_precios_no_se_invierte_en_el_aire():
    # Si ZZZZ no tiene precios, su parte se queda como efectivo en vez de
    # desaparecer: hacerla desaparecer haria que la referencia rindiera mejor
    # de lo que habria rendido.
    flujos = pd.Series([1000.0, 0.0, 0.0], index=FECHAS)
    valores = comparacion.referencia(flujos, {"AAPL": 0.5, "ZZZZ": 0.5}, CIERRES)
    assert valores.iloc[0] == pytest.approx(1000.0)
    assert valores.iloc[2] == pytest.approx(500.0 * 1.21 + 500.0)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_comparacion.py -q
```

Esperado: `ImportError: cannot import name 'comparacion'`.

- [ ] **Step 3: Escribe el módulo**

Crea `seguimiento/comparacion.py`:

```python
"""Contra qué se mide la cartera real.

Las tres referencias —el objetivo teórico, 1/N y el S&P 500— reciben **el mismo
dinero en las mismas fechas** que metió el usuario. Eso es lo que aísla la
elección de activos del calendario de aportaciones: si cada referencia tuviera
su propio calendario, la comparación mediría el calendario y no la cartera.

Ninguna rebalancea. El objetivo teórico es "la cartera que tendrías si hubieras
seguido el plan", y seguir el plan no incluye rebalancear a diario — el
rebalanceo es una decisión con coste, y es justo lo que el sub-proyecto G existe
para medir.
"""

import pandas as pd


def equal_weight(tickers: list[str]) -> dict[str, float]:
    """1/N over the given tickers. Empty in, empty out."""
    if not tickers:
        return {}
    peso = 1.0 / len(tickers)
    return {t: peso for t in tickers}


def referencia(
    flujos: pd.Series, pesos: dict[str, float], cierres: pd.DataFrame
) -> pd.Series:
    """Value over time of investing the same cash flows at fixed weights.

    Cada entrada de dinero compra a los precios **de su día**, nunca a los del
    primero: comprar al precio del día uno sería darle a la referencia una
    información que no tenía, y la comparación dejaría de ser justa en la
    dirección que favorece a la referencia.

    Un retiro sale a prorrata de lo que haya, que es lo más parecido a lo que
    hace alguien que necesita dinero y no quiere cambiar su cartera.

    **La parte asignada a un ticker sin precios se queda como efectivo.** No
    desaparece: hacerla desaparecer subiría el rendimiento de la referencia
    repartiendo el mismo dinero entre menos activos, y la cartera real quedaría
    peor por comparación con algo que nunca existió.
    """
    # Mismo arrastre que en `posiciones.serie`, y por lo mismo: un hueco de
    # precio es un fallo de datos, no una acción que valga cero. Aquí envenena
    # más todavía, porque el valor del día se suma con `float()` uno a uno y un
    # solo NaN convierte el total en NaN en vez de restar sólo su parte.
    cierres = cierres.ffill()
    calendario = cierres.index
    disponibles = [t for t in pesos if t in cierres.columns]

    participaciones = {t: 0.0 for t in disponibles}
    caja = 0.0
    valores = []

    for dia in calendario:
        flujo = float(flujos.loc[dia]) if dia in flujos.index else 0.0

        if flujo > 0:
            for ticker in pesos:
                parte = flujo * pesos[ticker]
                if ticker in participaciones:
                    precio = float(cierres.at[dia, ticker])
                    if precio > 0:
                        participaciones[ticker] += parte / precio
                        continue
                caja += parte
        elif flujo < 0:
            invertido = sum(
                participaciones[t] * float(cierres.at[dia, t]) for t in disponibles
            )
            total = invertido + caja
            if total > 0:
                fraccion = min(1.0, -flujo / total)
                for ticker in disponibles:
                    participaciones[ticker] *= 1.0 - fraccion
                caja *= 1.0 - fraccion

        valor = sum(
            participaciones[t] * float(cierres.at[dia, t]) for t in disponibles
        )
        valores.append(valor + caja)

    return pd.Series(valores, index=calendario, dtype=float)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_comparacion.py -q
```

Esperado: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/comparacion.py tests/test_seguimiento_comparacion.py
git commit -m "feat: las tres referencias sobre la misma linea de flujos"
```

---

## Task 10: El veredicto completo en las métricas del optimizador

**Files:**
- Modify: `vistas/optimizador.py:367-381`
- Test: `tests/test_seguimiento_libro.py` (añadir al final)

- [ ] **Step 1: Escribe el test que falla**

Añade al final de `tests/test_seguimiento_libro.py`:

```python
from seguimiento.libro import Objetivo, veredicto_de


def test_el_veredicto_se_extrae_de_las_metricas_guardadas():
    metricas = {
        "oos_sharpe": 0.41,
        "oos_equal_weight_sharpe": 0.55,
        "oos_sharpe_stderr": 0.09,
        "beats_equal_weight": False,
        "oos_windows": 12,
    }
    assert veredicto_de(metricas) == metricas


def test_un_portafolio_viejo_sin_error_estandar_no_afirma_un_veredicto():
    # Los ficheros guardados antes de este cambio no llevan sharpe_stderr. Sin
    # el, "gana / pierde / no se distingue" no se puede reconstruir: dos Sharpe
    # sueltos no dicen si la diferencia cabe dentro del ruido. None no es False.
    viejo = {"oos_sharpe": 0.41, "oos_equal_weight_sharpe": 0.55, "oos_windows": 12}
    salida = veredicto_de(viejo)
    assert salida["oos_sharpe_stderr"] is None
    assert salida["beats_equal_weight"] is None


def test_el_veredicto_sobrevive_al_viaje_por_el_objetivo():
    objetivo = Objetivo(
        fecha="2026-09-02", base="equal_weight", portafolio={},
        veredicto=veredicto_de({"oos_sharpe": 0.41, "oos_windows": 12}),
    )
    assert objetivo.veredicto["beats_equal_weight"] is None
```

- [ ] **Step 2: Corre el test y comprueba que falla**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q -k veredicto
```

Esperado: `ImportError: cannot import name 'veredicto_de'`.

- [ ] **Step 3: Implementa `veredicto_de` y añade los dos campos al optimizador**

Añade a `seguimiento/libro.py`:

```python
# Los cinco campos que hacen falta para poder decir "gana", "pierde" o "no se
# distingue del ruido". Sin `oos_sharpe_stderr` los otros cuatro no bastan: dos
# Sharpe sueltos no dicen si la diferencia cabe dentro del error de medicion.
CAMPOS_VEREDICTO = (
    "oos_sharpe",
    "oos_equal_weight_sharpe",
    "oos_sharpe_stderr",
    "beats_equal_weight",
    "oos_windows",
)


def veredicto_de(metricas: dict) -> dict:
    """The out-of-sample verdict as stored, with what is missing left as None.

    Los portafolios guardados antes de que el optimizador escribiera
    `oos_sharpe_stderr` no lo llevan, y ahí `None` no es `False`: uno significa
    "no se midió" y el otro "se midió y no gana". Rellenar el hueco con `False`
    afirmaría un resultado que nadie obtuvo — la misma regla por la que
    `cartera.formato_cifra` escribe "—" y nunca un 0,00.
    """
    return {campo: metricas.get(campo) for campo in CAMPOS_VEREDICTO}
```

En `vistas/optimizador.py`, dentro del dict `metrics` (línea 367), añade las dos
últimas entradas después de `"oos_windows"`:

```python
    "oos_windows": wf["n_windows"] if wf else 0,
    # Sin el error estandar, los dos Sharpe de arriba no permiten reconstruir el
    # veredicto: no dicen si la diferencia entre ellos cabe dentro del ruido.
    # `beats_equal_weight` es de tres estados a proposito -- None significa "no
    # hay ventanas suficientes para distinguirlo", que no es lo mismo que False.
    "oos_sharpe_stderr": wf["sharpe_stderr"] if wf else None,
    "beats_equal_weight": wf["beats_equal_weight"] if wf else None,
}
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py tests/test_cartera.py -q
```

Esperado: `62 passed` en el primero, y `test_cartera.py` sin regresión.

- [ ] **Step 5: Commit**

```bash
git add seguimiento/libro.py vistas/optimizador.py tests/test_seguimiento_libro.py
git commit -m "feat: guardar el error estandar y el veredicto fuera de muestra"
```

---

## Task 11: Guardar y leer el libro en disco

**Files:**
- Modify: `seguimiento/libro.py` (añadir `guardar`, `cargar`, `listar`, `desde_portafolio`)
- Test: `tests/test_seguimiento_libro.py` (añadir al final)

- [ ] **Step 1: Escribe los tests que fallan**

Añade al final de `tests/test_seguimiento_libro.py`:

```python
import json
from datetime import datetime

from seguimiento import libro as mod

AHORA = datetime(2026, 9, 2, 10, 0, 0)


def test_lo_guardado_vuelve_igual(tmp_path):
    original, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(original, tmp_path)
    vuelto = mod.cargar(ruta)
    assert vuelto.nombre == "Prueba"
    assert len(vuelto.asientos) == 1
    assert vuelto.asientos[0].tipo == "aportacion"
    assert vuelto.asientos[0].importe == 1000.0


def test_guardar_dos_veces_no_pisa_el_primero(tmp_path):
    # Un libro solo crece. Sobrescribirlo en silencio nunca es lo correcto.
    uno = mod.guardar(VACIO, tmp_path)
    dos = mod.guardar(VACIO, tmp_path)
    assert uno != dos
    assert uno.exists() and dos.exists()


def test_un_fichero_truncado_se_nombra_y_no_se_borra(tmp_path):
    # A diferencia de las caches de ranking/ y fundamentals/, que se borran y se
    # regeneran. Un libro de posiciones no se regenera.
    roto = tmp_path / "2026-09-02-100000-roto.json"
    roto.write_text('{"nombre": "Prue', encoding="utf-8")
    with pytest.raises(mod.LibroIlegible, match="roto.json"):
        mod.cargar(roto)
    assert roto.exists()


def test_listar_devuelve_los_rotos_con_su_motivo(tmp_path):
    mod.guardar(VACIO, tmp_path)
    (tmp_path / "2026-01-01-000000-roto.json").write_text("{", encoding="utf-8")
    entradas = mod.listar(tmp_path)
    assert len(entradas) == 2
    assert sum(1 for e in entradas if e.libro is None) == 1
    assert all(e.libro is not None or e.error for e in entradas)


def test_un_libro_desde_un_portafolio_copia_los_pesos_dentro(tmp_path):
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="Mi cartera", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True,
        metricas={"oos_sharpe": 0.41, "oos_sharpe_stderr": 0.09,
                  "beats_equal_weight": False},
        ahora=AHORA,
    )
    nuevo = mod.desde_portafolio("Seguimiento", portafolio, base="estrategia",
                                 ahora=AHORA)
    assert nuevo.objetivo.base == "estrategia"
    assert nuevo.objetivo.portafolio["posiciones"][0]["ticker"] == "AAPL"
    assert nuevo.objetivo.veredicto["beats_equal_weight"] is False
    # Copiado dentro, no referenciado: el fichero de portafolios/ se puede
    # borrar desde su pantalla, y el libro se quedaria apuntando a nada.
    assert "ruta" not in nuevo.objetivo.portafolio


def test_equal_weight_como_base_reparte_por_igual(tmp_path):
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="Mi cartera", tickers=["AAPL", "MSFT"], pesos=[0.6, 0.4],
        horizonte="1 Mes", estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True, metricas={}, ahora=AHORA,
    )
    nuevo = mod.desde_portafolio("Seguimiento", portafolio,
                                 base="equal_weight", ahora=AHORA)
    assert mod.pesos_objetivo(nuevo.objetivo) == {"AAPL": 0.5, "MSFT": 0.5}


def test_una_base_inventada_no_pasa():
    import cartera
    portafolio = cartera.desde_corrida(
        nombre="X", tickers=["AAPL"], pesos=[1.0], horizonte="1 Mes",
        estrategia="max_sharpe", peso_min=0.0, peso_max=1.0,
        permitir_cortos=False, shrinkage=True, metricas={}, ahora=AHORA,
    )
    with pytest.raises(AsientoInvalido, match="base"):
        mod.desde_portafolio("X", portafolio, base="a_ojo", ahora=AHORA)


def test_los_objetivos_se_apilan_y_manda_el_ultimo():
    from dataclasses import replace
    con_dos = replace(VACIO, objetivos=[
        Objetivo(fecha="2026-01-01", base="estrategia", portafolio={}),
        Objetivo(fecha="2026-06-01", base="equal_weight", portafolio={}),
    ])
    assert con_dos.objetivo.fecha == "2026-06-01"


def test_un_nan_escrito_a_mano_en_el_fichero_impide_abrirlo(tmp_path):
    # json.loads acepta el literal NaN por defecto, asi que un fichero editado
    # a mano lo mete en el libro sin pasar por ningun formulario. Un NaN
    # envenena el efectivo y borra un activo de la tabla sin decir nada: el
    # libro esta corrupto, y se trata como tal en vez de abrirse a medias.
    ruta = tmp_path / "2026-09-02-100000-envenenado.json"
    ruta.write_text(
        '{"nombre": "Prueba", "creado": "2026-09-02T10:00:00", "moneda": "USD",'
        ' "objetivos": [], "asientos": [{"id": "a1", "fecha": "2026-09-01",'
        ' "tipo": "compra", "ticker": "AAPL", "acciones": 10.0,'
        ' "precio": 220.0, "importe": NaN}]}',
        encoding="utf-8",
    )
    with pytest.raises(mod.LibroIlegible, match="a1"):
        mod.cargar(ruta)
    # Y sigue en disco: una cache se regenera, un libro no.
    assert ruta.exists()


def test_un_fallo_a_media_escritura_no_deja_medio_libro_en_el_destino(tmp_path, monkeypatch):
    # El patron tmp-then-replace existe justo para esto: lo que se escribe a
    # medias es el .tmp, y el destino solo aparece a traves del replace, que es
    # atomico. Sin el, un proceso muerto a mitad deja un .json con medio JSON
    # dentro, y ese historial no se regenera -- nadie recuerda que compro en
    # marzo.
    primero, _ = anadir(VACIO, Asiento(
        id="ap", fecha="2026-09-01", tipo="aportacion", importe=1000.0), hoy=HOY)
    ruta = mod.guardar(primero, tmp_path)
    antes = ruta.read_text(encoding="utf-8")

    def revienta(self, *args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("pathlib.Path.replace", revienta)
    with pytest.raises(OSError):
        mod.guardar(primero, tmp_path)

    # Ni un .json nuevo a medias, ni el anterior tocado. El .tmp puede quedar de
    # escombro: es el mismo compromiso, escrito y aceptado, que documenta
    # `aprobacion/acta.py:guardar_acta`.
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [ruta.name]
    assert ruta.read_text(encoding="utf-8") == antes
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py -q
```

Esperado: `AttributeError: module 'seguimiento.libro' has no attribute 'guardar'`.

- [ ] **Step 3: Haz público el ayudante de nombres de fichero**

`cartera._rebanada` convierte "Mi cartera 2026 (v2)" en algo que un sistema de
ficheros acepta, y el libro necesita exactamente lo mismo. Duplicarlo dejaría
dos reglas que se pueden separar; llamarlo desde fuera con el guion bajo delante
sería meter la mano en las tripas de otro módulo.

En `cartera.py`, renombra `_rebanada` a `rebanada` (línea 103) y actualiza su
única llamada, en `guardar` (línea 185). No hay más referencias en el repo —
compruébalo antes:

```bash
grep -rn "_rebanada" --include=*.py .
```

Esperado después del cambio: **ninguna** línea con `_rebanada`.

- [ ] **Step 4: Implementa la persistencia**

Añade a `seguimiento/libro.py` (arriba: `import json`, `from dataclasses import
asdict`, `from datetime import datetime`, `from pathlib import Path`,
`import cartera`):

```python
DIRECTORIO = Path("libros")

BASES = frozenset({"estrategia", "equal_weight"})


class LibroIlegible(ValueError):
    """Hay un fichero de libro, pero no se puede leer."""


@dataclass(frozen=True)
class Entrada:
    """Un fichero de la carpeta: el libro si se pudo leer, o por qué no.

    Los ilegibles se devuelven en vez de saltarse, igual que hace
    `cartera.listar`. Un libro que desaparece de la lista sin decir nada es
    indistinguible de uno que nunca existió, y el usuario se queda buscándolo.
    """

    ruta: Path
    libro: Libro | None
    error: str | None


def desde_portafolio(
    nombre: str,
    portafolio,
    base: str,
    acta: str | None = None,
    ahora: datetime | None = None,
) -> Libro:
    """Start a book whose target is a saved portfolio snapshot.

    El portafolio se copia **dentro**, no se referencia por ruta:
    `vistas/portafolios.py` tiene un botón de borrar, y un libro que apuntase a
    un fichero borrado se quedaría sin objetivo contra el que medir.

    `base` no tiene valor por defecto a propósito. El walk-forward ya dice
    cuándo la optimización no le gana a repartir por igual, y elegir por el
    usuario convertiría esa evidencia en un clic que nadie mira. Es el mismo
    razonamiento que dejó las casillas desmarcadas en el gate de aprobación.
    """
    if base not in BASES:
        raise AsientoInvalido(
            f"{base!r} no es una base válida: {', '.join(sorted(BASES))}"
        )
    momento = (ahora or datetime.now()).isoformat(timespec="seconds")
    copia = asdict(portafolio)
    if acta:
        copia["acta"] = acta
    return Libro(
        nombre=cartera.normalizar_nombre(nombre),
        creado=momento,
        objetivos=(
            Objetivo(
                fecha=momento[:10],
                base=base,
                portafolio=copia,
                veredicto=veredicto_de(copia.get("metricas") or {}),
            ),
        ),
    )


def pesos_objetivo(objetivo: Objetivo | None) -> dict[str, float]:
    """The weights the drift is measured against, honouring `base`."""
    if objetivo is None:
        return {}
    posiciones_ = objetivo.portafolio.get("posiciones") or []
    tickers = [p["ticker"] for p in posiciones_]
    if objetivo.base == "equal_weight":
        return {t: 1.0 / len(tickers) for t in tickers} if tickers else {}
    return {p["ticker"]: float(p["peso"]) for p in posiciones_}


def guardar(libro: Libro, directorio: Path | None = None) -> Path:
    """Write the book atomically and return where it landed.

    Mismo esquema que `cartera.guardar` y `aprobacion.acta.guardar_acta`: fecha
    delante para que la carpeta se ordene sola, sufijo numérico en colisión, y
    tmp-then-`replace()` para que un proceso muerto a media escritura no deje el
    libro a medias.
    """
    directorio = Path(directorio or DIRECTORIO)
    directorio.mkdir(parents=True, exist_ok=True)

    momento = datetime.fromisoformat(libro.creado).strftime("%Y-%m-%d-%H%M%S")
    base = f"{momento}-{cartera.rebanada(libro.nombre)}"
    fichero = directorio / f"{base}.json"
    copia = 2
    while fichero.exists():
        fichero = directorio / f"{base}-{copia}.json"
        copia += 1

    texto = json.dumps(asdict(libro), ensure_ascii=False, indent=2, allow_nan=False)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(fichero)
    return fichero


def cargar(ruta: Path) -> Libro:
    """Read a book back, naming whatever is wrong with it.

    **No borra el fichero roto**, a diferencia de las cachés de `ranking/` y
    `fundamentals/`, que sí lo hacen. Una caché se regenera; el historial de lo
    que alguien compró, no.

    **Cada asiento se vuelve a validar al leerlo**, y no sólo al escribirlo.
    `json.loads` acepta los literales `NaN` e `Infinity` por defecto, así que un
    fichero editado a mano o corrompido puede meter un importe que ninguna
    guarda de "mayor que cero" detiene — y un solo `NaN` envenena el efectivo y
    borra un activo de la tabla sin decir nada. Un libro así **está corrupto**, y
    aquí se trata como tal: se nombra el asiento culpable y no se abre.
    """
    ruta = Path(ruta)
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LibroIlegible(f"{ruta.name} no se puede leer: {error}") from error
    if not isinstance(crudo, dict):
        raise LibroIlegible(f"{ruta.name} no contiene un objeto")
    for campo in ("nombre", "creado", "asientos"):
        if campo not in crudo:
            raise LibroIlegible(f"a {ruta.name} le falta el campo {campo}")
    try:
        asientos = tuple(Asiento(**a) for a in crudo["asientos"])
        libro = Libro(
            nombre=cartera.normalizar_nombre(crudo["nombre"]),
            creado=str(crudo["creado"]),
            moneda=str(crudo.get("moneda", "USD")),
            objetivos=tuple(Objetivo(**o) for o in crudo.get("objetivos", [])),
            asientos=asientos,
        )
    except (TypeError, ValueError) as error:
        raise LibroIlegible(f"{ruta.name}: {error}") from error

    for asiento in asientos:
        try:
            validar(asiento)
        except AsientoInvalido as error:
            raise LibroIlegible(
                f"{ruta.name}: el asiento {asiento.id} no es válido ({error})"
            ) from error
    return libro


def listar(directorio: Path | None = None) -> list[Entrada]:
    """Every saved book, newest first, including the broken ones."""
    directorio = Path(directorio or DIRECTORIO)
    if not directorio.is_dir():
        return []
    entradas = []
    for ruta in sorted(directorio.glob("*.json"), reverse=True):
        try:
            entradas.append(Entrada(ruta=ruta, libro=cargar(ruta), error=None))
        except LibroIlegible as error:
            entradas.append(Entrada(ruta=ruta, libro=None, error=str(error)))
    return entradas
```

- [ ] **Step 5: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_seguimiento_libro.py tests/test_cartera.py -q
```

Esperado: `72 passed` en el primero, y `test_cartera.py` sin regresión por el
renombrado de `rebanada`.

- [ ] **Step 6: Commit**

```bash
git add seguimiento/libro.py cartera.py tests/test_seguimiento_libro.py
git commit -m "feat: guardar y leer el libro, con el objetivo copiado dentro"
```

---

## Task 12: Crear un libro y verlo

Todo salvo el alta de operaciones, que es la Task 13. Al terminar esta tarea se
puede crear un libro desde un portafolio guardado y abrirlo; lo que no se puede
todavía es meterle nada.

**Files:**
- Create: `vistas/seguimiento.py`
- Modify: `vistas/portafolios.py` (botón "Empezar a seguir")
- Modify: `app.py` (registrar la página)
- Modify: `.gitignore` de la raíz y `programa/.gitignore`

- [ ] **Step 1: Ignora los datos del usuario antes de que existan**

Hazlo primero, no al final: en cuanto la pantalla funcione habrá un fichero con
posiciones reales dentro y basta un `git add -A` distraído para commitearlo.

En `.gitignore` de la **raíz** del repo, junto a `/portafolios/`:

```
/libros/
```

En `programa/.gitignore`, junto a `salidas/`:

```
libros/
```

**Esto rompe con `actas/` y `portafolios/` a propósito**, que están a la vista de
git deliberadamente. Aquellos guardan decisiones y pesos; un libro guarda cuánto
dinero tiene el usuario y en qué. Es otra categoría, y la excepción tiene que
ser deliberada y estar escrita.

Comprueba que funciona:

```bash
mkdir -p libros && echo '{}' > libros/prueba.json && git status --short
```

Esperado: `libros/` **no** aparece. Borra el fichero de prueba después.

- [ ] **Step 2: Escribe la pantalla**

Crea `vistas/seguimiento.py`. Sólo widgets: todo cálculo sale de
`seguimiento/`, y si hace falta lógica nueva, va al paquete y se prueba allí.

```python
"""El libro de posiciones: lo que se compró de verdad y cómo va."""

from datetime import date

import pandas as pd
import streamlit as st

import cartera
import tema
from exporter import to_excel
from seguimiento import comparacion, libro as mod, posiciones, precios, rendimiento

st.markdown(
    tema.cabecera(
        "Seguimiento",
        "Lo que compraste con tu dinero, medido contra el objetivo que te dio "
        "el optimizador. Los portafolios guardados son fotografías; esto es el "
        "libro de lo que pasó después.",
    ),
    unsafe_allow_html=True,
)

entradas = mod.listar()

if not entradas:
    st.info(
        "Todavía no llevas ningún libro. Empieza uno desde **Portafolios "
        "guardados**, o crea uno a mano si ya tenías acciones compradas."
    )
    if st.button("Ir a portafolios guardados", icon=":material/folder_open:"):
        st.switch_page("vistas/portafolios.py")
    st.stop()

# Los ilegibles se pintan con su motivo, como en vistas/portafolios.py. Aqui no
# hay boton de borrar: alli lo peor que se pierde es una fotografia repetible, y
# aqui es el historial entero de lo que alguien compro.
for entrada in entradas:
    if entrada.libro is None:
        st.error(f"`{entrada.ruta.name}` no se puede leer: {entrada.error}")

sanos = [e for e in entradas if e.libro is not None]
if not sanos:
    st.stop()

etiquetas = {f"{e.libro.nombre} · {e.ruta.name}": e for e in sanos}
elegida = etiquetas[st.selectbox("Libro", options=list(etiquetas))]
actual = elegida.libro

st.caption(
    f"Moneda: **{actual.moneda}**. Coste calculado por **media ponderada**, no "
    "por lotes: cambia el reparto entre ganancia realizada y latente, nunca el "
    "total. Esto no es un cálculo fiscal."
)

# --- Precios ----------------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
if not vivos:
    st.info("Este libro todavía no tiene ningún asiento. Añade el primero abajo.")
    st.stop()

tickers = sorted({a.ticker for a in vivos if a.ticker})
desde = min(a.fecha for a in vivos)


@st.cache_data(ttl=3600, show_spinner="Descargando precios...")
def _historia(tickers: tuple[str, ...], desde: str):
    return precios.descargar(list(tickers), desde=desde)


historia = _historia(tuple(tickers), desde)

if historia.sin_datos:
    st.warning(
        "Sin precios para: " + ", ".join(historia.sin_datos) + ". Esas "
        "posiciones se muestran sin valorar — no valen cero, es que no se "
        "pudieron descargar."
    )

marcha = posiciones.serie(actual.asientos, historia)
ultimos = {t: precios.ultimo(historia, t) for t in historia.cierres.columns}
precios_hoy = {t: p for t, (p, _) in ultimos.items() if p is not None}

fechas = [f for _, f in ultimos.values() if f]
if fechas and max(fechas) < date.today().isoformat():
    st.caption(
        f"Último cierre disponible: **{max(fechas)}**. Todo lo de abajo está "
        "valorado a esa fecha, no a hoy."
    )

if marcha.posteriores:
    # La tabla por activo si los ve, porque sale de los asientos; el valor de
    # cabecera no, porque sale de la serie y la serie no tiene precio con que
    # valorarlos. Sin decirlo, las dos cifras se contradicen sin explicacion.
    st.warning(
        f"{marcha.posteriores} asiento(s) con fecha posterior al último cierre "
        "disponible. Aparecen en la tabla por activo, pero todavía no en el "
        "valor ni en el gráfico: no hay precio con el que valorarlos."
    )

# --- Los numeros de cabecera -------------------------------------------------

aportado = sum(
    a.importe if a.tipo == "aportacion" else -a.importe
    for a in vivos
    if a.tipo in mod.FLUJOS_EXTERNOS
)
valor_hoy = float(marcha.valor.iloc[-1]) if len(marcha.valor) else 0.0
dias = (marcha.valor.index[-1] - marcha.valor.index[0]).days if len(marcha.valor) > 1 else 0

twr_periodo = rendimiento.twr(marcha.valor, marcha.flujos)
twr_anual = rendimiento.anualizar(twr_periodo, dias=dias)

flujos_tir = [
    (date.fromisoformat(a.fecha), a.importe if a.tipo == "retiro" else -a.importe)
    for a in vivos
    if a.tipo in mod.FLUJOS_EXTERNOS
]
if flujos_tir and len(marcha.valor):
    flujos_tir.append((marcha.valor.index[-1].date(), valor_hoy))
tasa_interna = rendimiento.tir(flujos_tir)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Valor", f"{valor_hoy:,.2f}")
k2.metric("Aportado neto", f"{aportado:,.2f}",
          help="Aportaciones menos retiros: el dinero tuyo que hay dentro ahora "
               "mismo, no la suma de todo lo que pasó por la cartera.")
k3.metric("Ganancia", f"{valor_hoy - aportado:,.2f}")
k4.metric(
    "TWR anual", cartera.formato_porcentaje(twr_anual),
    help="Ponderado por tiempo: neutraliza cuándo metiste el dinero, así que "
         "mide la cartera y no tu timing. Es el único comparable con un índice. "
         f"Sin anualizar, el periodo entero rindió {twr_periodo:.2%}.",
)
k5.metric(
    "TIR", cartera.formato_porcentaje(tasa_interna),
    help="Ponderada por dinero: lo que ganaste tú, con tu timing dentro. "
         "Aparece «—» cuando no hay una respuesta defendible.",
)
k6.metric("Dividendos", f"{float(marcha.dividendos.sum().sum()):,.2f}")

if twr_anual is not None and tasa_interna is not None:
    brecha = tasa_interna - twr_anual
    if abs(brecha) > 0.02:
        st.info(
            f"**TWR y TIR se separan {abs(brecha):.1%}.** Esa diferencia es el "
            "efecto de *cuándo* aportaste, no de qué compraste: "
            + ("tus aportaciones cayeron en buenos momentos."
               if brecha > 0 else
               "tus aportaciones cayeron en momentos peores que la media.")
        )

# --- Valor en el tiempo, contra las tres referencias -------------------------

st.subheader("Valor en el tiempo")

objetivo = actual.objetivo
lineas = {"Tu cartera": marcha.valor}
if objetivo is not None:
    pesos = mod.pesos_objetivo(objetivo)
    if pesos:
        lineas["Si hubieras seguido el plan"] = comparacion.referencia(
            marcha.flujos, pesos, historia.cierres
        )
lineas["Repartir por igual (1/N)"] = comparacion.referencia(
    marcha.flujos,
    comparacion.equal_weight(list(historia.cierres.columns)),
    historia.cierres,
)

st.line_chart(pd.DataFrame(lineas))
st.caption(
    "Las tres referencias reciben **el mismo dinero en las mismas fechas** que "
    "metiste tú. Así la comparación aísla qué compraste de cuándo lo compraste. "
    "Ninguna rebalancea: rebalancear es una decisión con coste."
)

# --- Por activo --------------------------------------------------------------

st.subheader("Por activo")

pesos_obj = mod.pesos_objetivo(objetivo)
filas = []
for ticker, linea in rendimiento.por_activo(actual.asientos, precios_hoy).items():
    peso_real = (linea.valor / valor_hoy) if (linea.valor and valor_hoy) else None
    filas.append({
        "Ticker": ticker,
        "Acciones": f"{linea.acciones:,.4f}".rstrip("0").rstrip("."),
        "Coste medio": f"{linea.coste_medio:,.2f}",
        "Precio": cartera.formato_cifra(linea.precio),
        "Valor": cartera.formato_cifra(linea.valor),
        "Peso real": cartera.formato_porcentaje(peso_real),
        "Peso objetivo": cartera.formato_porcentaje(pesos_obj.get(ticker)),
        "Latente": cartera.formato_cifra(linea.latente),
        "Realizada": f"{linea.realizada:,.2f}",
        "Dividendos": f"{linea.dividendos:,.2f}",
        "Contribución": cartera.formato_cifra(linea.contribucion),
    })

st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
st.caption(
    "La contribución va en dólares y suma. Un porcentaje de contribución con "
    "aportaciones de por medio compararía cada activo contra un capital que no "
    "fue el suyo durante todo el periodo."
)

# --- Historial ---------------------------------------------------------------

st.subheader("Historial")

anulados = {a.anula for a in actual.asientos if a.tipo == "anulacion" and a.anula}
historial = []
for a in reversed(posiciones.ordenados(actual.asientos)):
    historial.append({
        "Fecha": a.fecha,
        "Tipo": a.tipo,
        "Ticker": a.ticker or "—",
        "Acciones": cartera.formato_cifra(a.acciones, 4),
        "Precio": cartera.formato_cifra(a.precio) + (" (est.)" if a.precio_estimado else ""),
        "Importe": f"{a.importe:,.2f}",
        "Comisión": f"{a.comision:,.2f}",
        "Estado": "Anulado" if a.id in anulados else "",
        "Nota": a.nota,
    })
st.dataframe(pd.DataFrame(historial), use_container_width=True, hide_index=True)

# --- Exportar ----------------------------------------------------------------
#
# Solo Excel. `exporter.to_pdf` pasa por `kpi_rows`, que indexa directamente
# `sharpe`, `annual_return`, `annual_vol` y `rf_rate` -- claves de una corrida
# del optimizador que un libro de seguimiento no tiene, y que reventarian con
# KeyError. `to_excel` si es generico: acepta cualquier DataFrame y cualquier
# dict. Hacer que kpi_rows tolere dos formas distintas de metricas es un cambio
# a un modulo compartido, y se hace cuando se decida, no de refilon.
st.download_button(
    "Descargar Excel",
    data=to_excel(
        pd.DataFrame(filas),
        {
            "Libro": actual.nombre,
            "Moneda": actual.moneda,
            "Valorado a": max(fechas) if fechas else "—",
            "Valor": valor_hoy,
            "Aportado neto": aportado,
            "Ganancia": valor_hoy - aportado,
            "TWR del periodo": twr_periodo,
            "TWR anual": twr_anual,
            "TIR": tasa_interna,
            "Dividendos": float(marcha.dividendos.sum().sum()),
            "Metodo de coste": "media ponderada",
        },
    ),
    file_name=f"seguimiento_{elegida.ruta.stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table_view:",
)
```

- [ ] **Step 3: Registra la página y el botón de arranque**

En `app.py`, dentro de la sección `"Cartera"` de `st.navigation`, **entre**
"Portafolios guardados" y "Comparar":

```python
            st.Page(
                "vistas/seguimiento.py", title="Seguimiento",
                icon=":material/monitoring:",
            ),
```

En `vistas/portafolios.py`, en la columna `acciones`, justo debajo del botón
"Cargar en el optimizador":

```python
            if st.button(
                "Empezar a seguir", key=f"seguir_{entrada.ruta.name}",
                use_container_width=True, icon=":material/monitoring:",
            ):
                st.session_state.portafolio_a_seguir = p
                st.switch_page("vistas/seguimiento.py")
```

Y en `vistas/seguimiento.py`, justo después de `entradas = mod.listar()`, el
diálogo que elige la base — **sin preseleccionar ninguna**:

```python
pendiente = st.session_state.get("portafolio_a_seguir")
if pendiente is not None:
    st.markdown(f"### Empezar a seguir «{pendiente.nombre}»")
    v = mod.veredicto_de(pendiente.metricas or {})
    if v["beats_equal_weight"] is True:
        st.success(
            f"Fuera de muestra, la optimización superó a repartir por igual: "
            f"{v['oos_sharpe']:.2f} frente a {v['oos_equal_weight_sharpe']:.2f}."
        )
    elif v["beats_equal_weight"] is False:
        st.warning(
            f"Fuera de muestra, la optimización quedó **por debajo** de repartir "
            f"por igual: {v['oos_sharpe']:.2f} frente a "
            f"{v['oos_equal_weight_sharpe']:.2f}."
        )
    else:
        st.info(
            "Con estos datos no se pudo distinguir la optimización de repartir "
            "por igual. La diferencia cabía dentro del error de medición."
        )

    # Sin indice por defecto: el veredicto de arriba es la unica evidencia que
    # el programa produjo sobre si la optimizacion aportaba algo, y un valor
    # preseleccionado la convertiria en un clic que nadie mira.
    base = st.radio(
        "¿Contra qué pesos quieres medir la deriva?",
        options=["estrategia", "equal_weight"],
        format_func=lambda b: (
            "Los pesos de la estrategia" if b == "estrategia"
            else "Repartir por igual (1/N)"
        ),
        index=None,
    )
    nombre = st.text_input("Nombre del libro", value=pendiente.nombre, max_chars=60)
    if st.button("Crear libro", type="primary", disabled=base is None):
        ruta = mod.guardar(mod.desde_portafolio(nombre, pendiente, base=base))
        st.session_state.pop("portafolio_a_seguir")
        st.success(f"Creado en {ruta}.")
        st.rerun()
    st.stop()
```

- [ ] **Step 4: Comprueba que la app arranca y la pantalla responde**

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

Esperado: **126 tests nuevos** sobre la base. Con `numpy_financial` instalada,
`907 passed, 2 skipped`; sin ella, `905 passed, 4 skipped` — los dos de
contraste se omiten solos y eso es correcto. En ambos casos, `6 deselected`.

Ese recuento cuenta `test_apagado.py::test_detener_espera_antes_de_forzar` como
aprobado. Es el intermitente conocido, así que un test menos en la columna de
aprobados y uno en la de fallos sigue siendo correcto.

El fallo intermitente conocido de `test_apagado` es la única excepción
tolerada. Cualquier otro fallo es tuyo.

Después arranca la app y recorre el camino hasta donde llega esta tarea:
optimiza cinco tickers, guárdalos, pulsa "Empezar a seguir", elige una base, y
comprueba que el libro aparece vacío sin reventar. Un libro sin asientos tiene
que decir que está vacío, no fallar al dividir por un valor de cero.

```bash
UV_LINK_MODE=copy uv run streamlit run app.py
```

- [ ] **Step 5: Commit**

```bash
git add vistas/seguimiento.py vistas/portafolios.py app.py .gitignore
git add ../.gitignore
git commit -m "feat: la pantalla de seguimiento, con las tres referencias"
```

---

## Task 13: Registrar operaciones

Cierra el círculo: hasta aquí un libro sólo se puede crear y mirar. El
formulario va en su propia tarea porque es lo único de la pantalla que
**escribe**, y porque arrastra la única pieza de precios que no existía todavía
— el cierre de un día concreto para un ticker que el libro aún no conoce.

**Files:**
- Modify: `vistas/seguimiento.py`

- [ ] **Step 1: Añade el ayudante que busca el cierre de un día**

En `vistas/seguimiento.py`, justo después de la línea
`historia = _historia(tuple(tickers), desde)`:

```python
@st.cache_data(ttl=3600, show_spinner=False)
def _cierre_del_dia(ticker: str, fecha: str):
    """El cierre de un ticker en una fecha, aunque no esté ya en el libro.

    Se descarga aparte y no se busca en `historia` porque el ticker puede ser
    nuevo — la primera compra de una empresa que el libro todavía no conoce — y
    entonces no hay ninguna columna donde mirar. La ventana pide dos días
    porque `yf.download` trata `end` como exclusivo.
    """
    from datetime import timedelta

    hasta = (date.fromisoformat(fecha) + timedelta(days=1)).isoformat()
    return precios.cierre_en(precios.descargar([ticker], desde=fecha, hasta=hasta),
                             ticker, fecha)
```

- [ ] **Step 2: Añade el formulario**

En `vistas/seguimiento.py`, entre el bloque "Por activo" y el de "Historial":

```python
# --- Alta de asiento ---------------------------------------------------------

with st.expander("Registrar una operación"):
    tipo = st.selectbox("Tipo", options=sorted(mod.TIPOS - {"anulacion"}))
    cuando = st.date_input("Fecha", value=date.today(), max_value=date.today())
    ticker = st.text_input("Ticker").strip().upper() if tipo in mod.CON_TICKER else None

    importe = acciones = precio = None
    del_cierre = False
    if tipo in {"compra", "venta"}:
        col_a, col_b, col_c = st.columns(3)
        importe = col_a.number_input("Importe", min_value=0.0, value=0.0) or None
        acciones = col_b.number_input("Acciones", min_value=0.0, value=0.0) or None
        precio = col_c.number_input("Precio", min_value=0.0, value=0.0) or None
        del_cierre = st.checkbox(
            "No recuerdo el precio: usa el cierre de ese día",
            help="La operación queda marcada como precio estimado y se ve así en "
                 "el historial. Una compra intradía en un día volátil se desvía "
                 "un 3-4% del cierre.",
        )
        st.caption(
            "Rellena el importe **o** las acciones, más el precio. El tercero se "
            "calcula solo. Si escribes los tres, mandan los tres: el bróker "
            "aplica redondeos que ninguna división reproduce."
        )
    else:
        importe = st.number_input("Importe", min_value=0.0, value=0.0) or None

    comision = st.number_input("Comisión", min_value=0.0, value=0.0)
    nota = st.text_input("Nota (opcional)")

    if st.button("Registrar", type="primary", icon=":material/add:"):
        try:
            estimado = False
            if tipo in {"compra", "venta"}:
                # El cierre de ese dia, siempre: si no existe, ese dia no
                # cotizo -- festivo, fin de semana, o antes de la salida a
                # bolsa -- y guardar el asiento dejaria una posicion que la
                # serie diaria no puede valorar.
                cierre = _cierre_del_dia(ticker, cuando.isoformat())
                if cierre is None:
                    raise mod.AsientoInvalido(
                        f"{ticker} no cotizó el {cuando.isoformat()}: revisa la "
                        "fecha, o el ticker si la empresa aún no había salido a "
                        "bolsa."
                    )
                if del_cierre or precio is None:
                    precio, estimado = cierre, True
                importe, acciones, precio = mod.derivar(importe, acciones, precio)
            nuevo = mod.Asiento(
                id=f"{cuando.isoformat()}-{len(actual.asientos) + 1}",
                fecha=cuando.isoformat(), tipo=tipo, ticker=ticker or None,
                acciones=acciones, precio=precio, importe=importe or 0.0,
                comision=comision, precio_estimado=estimado, nota=nota,
            )
            actualizado, escritos = mod.anadir(actual, nuevo, financiar=True)
        except mod.AsientoInvalido as error:
            st.error(str(error))
        else:
            mod.guardar(actualizado, elegida.ruta.parent)
            if len(escritos) > 1:
                st.info(
                    f"No había efectivo suficiente, así que se registró también "
                    f"una aportación de {escritos[0].importe:,.2f} que financia "
                    "la compra."
                )
            if estimado:
                st.info(
                    f"Precio tomado del cierre del {cuando.isoformat()}: "
                    f"{precio:,.2f}. Queda marcado como estimado en el historial."
                )
            st.success("Registrado.")
            st.rerun()
```

- [ ] **Step 3: Recorre el camino entero en la app**

```bash
UV_LINK_MODE=copy uv run streamlit run app.py
```

Cinco cosas que tienen que pasar, y las cinco se comprueban a mano porque son de
interfaz:

1. Una aportación de 10.000 y una compra: la tabla por activo sale con su coste
   medio y su peso real.
2. Una compra sin efectivo suficiente: aparece el aviso de que se registró
   también la aportación que la financia.
3. Una compra con "no recuerdo el precio": se rellena con el cierre y el
   historial la marca como estimada.
4. Una compra fechada en sábado: se rechaza diciendo que ese día no cotizó, y
   **no** se guarda.
5. Una venta de más acciones de las que hay: se rechaza diciendo cuántas hay.

- [ ] **Step 4: Comprueba que no hay regresión**

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

Esperado: el mismo recuento que al final de la Task 12. Esta tarea no añade
tests porque no añade lógica: todo lo que decide algo ya está en `seguimiento/`
y probado allí. Si te ves escribiendo una regla nueva aquí, va al paquete.

- [ ] **Step 5: Commit**

```bash
git add vistas/seguimiento.py
git commit -m "feat: registrar operaciones, con el cierre del dia cuando no se sabe el precio"
```

---

## Task 14: Dejarlo dicho en el README y en CONTEXTO

**Files:**
- Modify: `../README.md`
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Avisa en el README de que el libro no se comparte**

En la sección donde el README explica que las credenciales viven fuera del
proyecto, añade:

```markdown
**Tus posiciones tampoco viajan con la carpeta... pero casi.** El libro de
seguimiento se guarda en `programa/libros/`, ignorado por git. Eso lo protege de
un commit, **no de un ZIP**: si recomprimes la carpeta para pasársela a alguien,
tus posiciones van dentro. Bórrala antes, o mándale el enlace de descarga en vez
de tu copia.
```

- [ ] **Step 2: Actualiza CONTEXTO.md**

Añade una sección de resultado del sub-proyecto F, en el mismo tono que las de
A, B y C: qué entrega, qué decisiones no hay que relitigar, y qué hereda G.
Incluye los tres puntos que costaron pensar:

- Los precios del seguimiento van **sin ajustar**, y `data.py` sigue ajustando.
- El dividendo **no es flujo externo**; sólo `aportacion` y `retiro` lo son.
- `libros/` se ignora en git a diferencia de `actas/` y `portafolios/`.

Y actualiza el número de tests de la lista de comandos.

- [ ] **Step 3: Commit**

```bash
git add ../README.md CONTEXTO.md
git commit -m "docs: el libro de seguimiento, y que un ZIP se lleva las posiciones"
```

---

## Lo que queda para G

F deja exactamente tres cosas que G necesita y ninguna más:

- `mod.pesos_objetivo(libro.objetivo)` — los pesos contra los que medir.
- La columna "Peso real" de la tabla por activo — de dónde sale la deriva.
- `posiciones.estado(asientos).efectivo` — el dinero pendiente de asignar, que
  es literalmente lo que G va a repartir.

`medidores.py` ya existe y es la base visual de los medidores de deriva. No lo
toques en este plan.
