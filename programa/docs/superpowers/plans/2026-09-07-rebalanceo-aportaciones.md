# Rebalanceo y aportaciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pantalla que dice si la cartera necesita rebalanceo, cuánto costaría, y dónde poner el dinero nuevo.

**Architecture:** Paquete `rebalanceo/` con la lógica y `vistas/rebalanceo.py` con los widgets. El criterio —la banda 5/25 y el tope de coste— vive en su propio fichero y se congela en su propio commit. Todo lo demás cuelga de lo que ya dejó el sub-proyecto F: los pesos objetivo, los valores por activo y el efectivo sin asignar.

**Tech Stack:** Python 3.12, Streamlit 1.62, pytest. Sin dependencias nuevas.

**Diseño:** `docs/superpowers/specs/2026-09-07-rebalanceo-aportaciones-design.md`

---

## Antes de empezar

Todo se ejecuta desde `programa/`.

```bash
cd programa
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

**`UV_LINK_MODE=copy` no es opcional.** El proyecto vive en OneDrive y `uv` no
puede crear enlaces duros ahí: sin esa variable falla instalando `pyarrow` con
un `os error 396` antes de correr un solo test.

**Línea base:** `911 passed, 4 skipped, 6 deselected`.

**Dos fallos conocidos que no son tuyos:**

- `tests/test_apagado.py::test_detener_espera_antes_de_forzar` falla de forma
  intermitente porque compara tiempo de reloj contra un suelo que Windows no
  garantiza. Falla por unos 13 ms.
- Los 4 omitidos son dos pruebas de permisos POSIX en Windows y dos de
  contraste contra `numpy_financial`, que no está instalada. **No la instales:**
  que se omitan solas es el comportamiento correcto.

**Lo que NO se toca:** `seguimiento/`, `aprobacion/`, `ranking/`,
`fundamentals/`, `research/`, `cartera.py` ni `data.py`. Fuera del paquete
nuevo sólo cambia `app.py`, para registrar la página.

**Convenciones que este repo se toma en serio:**

- Los tests se llaman en español, con frase descriptiva:
  `test_una_banda_relativa_no_dispara_con_objetivo_cero`.
- **Los comentarios explican por qué, no qué, y no pueden mentir.** En el plan
  anterior se corrigieron cinco comentarios o tests que prometían una cobertura
  que no daban. Si escribes uno, que sea verdad.
- Docstrings públicos: una línea en inglés, párrafo largo en español debajo.
- Ninguna escritura directa a fichero: siempre temporal y `replace()`.

**Un aviso que sale de la experiencia del plan anterior:** después de implementar
y **commitear**, sabotea las guardas que escribas y comprueba que algún test
cae. Si uno sobrevive, no lo apuntes como «no falló» — averigua qué otra cosa
está devolviendo el resultado correcto. Ese diagnóstico encontró cinco defectos
reales en el sub-proyecto F. Y **commitea antes de sabotear**: `git checkout --`
sobre trabajo sin commitear se lleva por delante tu propia implementación.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `rebalanceo/__init__.py` | Vacío |
| `rebalanceo/criterio.py` | La banda y el tope. **Congelado, commit propio** |
| `rebalanceo/deriva.py` | Pesos reales frente a objetivo, y qué está fuera de banda |
| `rebalanceo/coste.py` | Qué cuesta operar, sacado de las comisiones del libro |
| `rebalanceo/reparto.py` | Cómo se reparte el efectivo disponible |
| `rebalanceo/propuesta.py` | Junta todo: qué comprar, qué vender, a qué coste |
| `vistas/rebalanceo.py` | Widgets. Cero lógica |
| `tests/test_rebalanceo_criterio.py` | Task 1 |
| `tests/test_rebalanceo_deriva.py` | Task 2 |
| `tests/test_rebalanceo_coste.py` | Task 3 |
| `tests/test_rebalanceo_reparto.py` | Task 4 |
| `tests/test_rebalanceo_propuesta.py` | Task 5 |

**Orden de dependencias:** `criterio` no importa nada. `deriva` y `reparto`
importan `criterio`. `coste` no importa nada del paquete. `propuesta` importa a
los cuatro. La vista es la única que importa Streamlit.

---

## Task 1: El criterio, congelado

Esta tarea va sola y en su propio commit **antes de que exista ningún cálculo
que lo use**. La fecha de ese commit es la prueba de que el umbral no se movió
al ver los números — es el estándar metodológico nº 1 de `CONTEXTO.md`, el mismo
que hizo creíble el veredicto del sub-proyecto D.

**Files:**
- Create: `rebalanceo/__init__.py`
- Create: `rebalanceo/criterio.py`
- Test: `tests/test_rebalanceo_criterio.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_rebalanceo_criterio.py`:

```python
import pytest

from rebalanceo import criterio


def test_los_tres_umbrales_son_los_congelados():
    # Si alguien los cambia, este test lo dice. Cambiarlos exige una enmienda
    # fechada en el diseno, no una edicion silenciosa: la fecha del commit que
    # los congelo es la prueba de que no se movieron al ver los numeros.
    assert criterio.BANDA_ABSOLUTA == 0.05
    assert criterio.BANDA_RELATIVA == 0.25
    assert criterio.COSTE_MAXIMO == 0.01


# --- La banda -----------------------------------------------------------------


def test_un_objetivo_grande_lo_manda_la_banda_absoluta():
    # Con objetivo 40%, la relativa exigiria 10 puntos: la absoluta dispara
    # antes, a los 5. Es el extremo que la banda relativa sola cubriria mal.
    assert criterio.fuera_de_banda(0.05, 0.40)
    assert not criterio.fuera_de_banda(0.049, 0.40)


def test_un_objetivo_pequeno_lo_manda_la_banda_relativa():
    # Con objetivo 3%, la absoluta exigiria pasar del 8%: casi triplicarse, o
    # sea que nunca. La relativa dispara a los 0,75 puntos.
    assert criterio.fuera_de_banda(0.0075, 0.03)
    assert not criterio.fuera_de_banda(0.0074, 0.03)


def test_la_banda_es_simetrica():
    # Estar por debajo del objetivo cuenta igual que estar por encima.
    assert criterio.fuera_de_banda(-0.05, 0.40)
    assert criterio.fuera_de_banda(-0.0075, 0.03)


def test_una_desviacion_de_cero_nunca_esta_fuera_de_banda():
    for objetivo in (0.0, 0.03, 0.40, 1.0):
        assert not criterio.fuera_de_banda(0.0, objetivo)


def test_con_objetivo_cero_la_banda_relativa_no_aplica():
    # El 25% de cero es cero, asi que sin esta guarda CUALQUIER desviacion
    # disparia -- incluida la de cero, porque `abs(0) >= 0` es cierto. Los
    # activos fuera del objetivo se tratan aparte justamente por esto.
    assert not criterio.fuera_de_banda(0.02, 0.0)
    assert criterio.fuera_de_banda(0.06, 0.0)


# --- El tope de coste ---------------------------------------------------------


def test_una_operacion_grande_merece_la_pena():
    assert criterio.merece_la_pena(2000.0, coste=1.0)


def test_una_operacion_pequena_no_merece_la_pena():
    # Mover 20 dolares pagando 5 es tirar el 25%. Es el numero que hace el
    # criterio economico y no solo geometrico.
    assert not criterio.merece_la_pena(20.0, coste=5.0)


def test_el_tope_esta_justo_en_el_uno_por_ciento():
    assert criterio.merece_la_pena(1000.0, coste=10.0)
    assert not criterio.merece_la_pena(1000.0, coste=10.01)


def test_con_coste_cero_siempre_merece_la_pena():
    # Un broker sin comisiones no bloquea ninguna operacion, por pequena que
    # sea. Es correcto: el criterio mide coste contra importe, y aqui no hay
    # coste que medir.
    assert criterio.merece_la_pena(1.0, coste=0.0)


def test_una_operacion_de_importe_cero_no_merece_la_pena():
    # No es una operacion. Sin esta guarda, `coste <= 0.01 * 0` seria cierto
    # con coste cero y se propondria comprar nada.
    assert not criterio.merece_la_pena(0.0, coste=0.0)


def test_el_signo_del_importe_da_igual():
    # Una venta llega con importe negativo y cuesta lo mismo que la compra
    # equivalente.
    assert criterio.merece_la_pena(-2000.0, coste=1.0)
    assert not criterio.merece_la_pena(-20.0, coste=5.0)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_criterio.py -q
```

Esperado: `ModuleNotFoundError: No module named 'rebalanceo'`.

- [ ] **Step 3: Escribe el criterio**

Crea `rebalanceo/__init__.py` vacío. Crea `rebalanceo/criterio.py`:

```python
"""Cuándo una cartera pide rebalanceo, y cuándo la operación no compensa.

**Este fichero está congelado.** Vive aparte del código que lo usa por la misma
razón que `ranking/criterio.py`: la fecha del commit que lo introduce es la
prueba de que los umbrales no se movieron al ver los números de ninguna cartera
real. Cambiarlos exige una enmienda fechada en el diseño, no una edición.

Es el estándar metodológico que hizo creíble el veredicto del sub-proyecto D, y
aquí importa igual: una banda elegida después de mirar tu propia deriva no es un
criterio, es una racionalización.
"""

# Cinco puntos porcentuales de desviación absoluta.
BANDA_ABSOLUTA = 0.05

# O un 25% del peso objetivo, lo que ocurra primero.
BANDA_RELATIVA = 0.25

# El coste de una operación no puede pasar de esta fracción de su importe.
COSTE_MAXIMO = 0.01


def fuera_de_banda(desviacion: float, objetivo: float) -> bool:
    """Whether one asset has drifted far enough to be worth acting on.

    Los dos umbrales existen porque ninguno funciona solo. Con sólo la banda
    absoluta, un activo cuyo objetivo es el 3% tendría que llegar al 8% —casi
    triplicarse— para disparar, así que en la práctica nunca se rebalancearía.
    Con sólo la relativa, un activo del 40% dispara al llegar al 50%, que en una
    cartera concentrada puede ser la oscilación de dos semanas.

    **La banda relativa no se aplica con objetivo cero.** El 25% de cero es
    cero, y `abs(desviacion) >= 0` es cierto incluso para una desviación de
    cero: sin la guarda, un activo que no está en el objetivo dispararía siempre,
    y hasta uno que no se tiene. Esos casos se tratan aparte, en su propio
    bloque de la pantalla.
    """
    if abs(desviacion) >= BANDA_ABSOLUTA:
        return True
    return objetivo > 0 and abs(desviacion) >= BANDA_RELATIVA * objetivo


def merece_la_pena(importe: float, coste: float) -> bool:
    """Whether the trade is big enough that its cost does not eat it.

    Es lo que hace el criterio económico y no sólo geométrico. Sin esto, un
    activo fuera de banda por veinte dólares generaría una propuesta que cuesta
    cinco — y el sub-proyecto D ya concluyó que ninguna de las siete señales
    técnicas evaluadas tiene ventaja, así que operar de más es el único
    destructor de valor garantizado que queda en esta pantalla.

    El importe se toma en valor absoluto: una venta llega con signo negativo y
    cuesta lo mismo que la compra equivalente.
    """
    if importe == 0:
        return False
    return coste <= COSTE_MAXIMO * abs(importe)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_criterio.py -q
```

Esperado: `12 passed`.

- [ ] **Step 5: Commit — y este va solo**

```bash
git add rebalanceo/__init__.py rebalanceo/criterio.py tests/test_rebalanceo_criterio.py
git commit -m "docs: congelar el criterio de rebalanceo antes de medir nada"
```

No metas nada más en este commit. Su valor está en la fecha y en que no
contenga ningún cálculo que lo use.

---

## Task 2: La deriva

**Files:**
- Create: `rebalanceo/deriva.py`
- Test: `tests/test_rebalanceo_deriva.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_rebalanceo_deriva.py`:

```python
import pytest

from rebalanceo import deriva


def por_ticker(d: deriva.Deriva) -> dict:
    return {l.ticker: l for l in d.lineas}


def test_una_cartera_en_su_objetivo_no_tiene_deriva():
    # El control negativo de esta tarea. Si una cartera exactamente en su
    # objetivo produce cualquier desviacion distinta de cero, o marca algo
    # fuera de banda, el calculo esta mal y no hay forma de que sea casualidad.
    d = deriva.calcular({"AAPL": 5000.0, "MSFT": 5000.0},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert d.invertido == pytest.approx(10_000.0)
    for linea in d.lineas:
        assert linea.desviacion == pytest.approx(0.0)
        assert not linea.fuera_de_banda


def test_el_efectivo_no_entra_en_el_denominador():
    # `calcular` no recibe el efectivo, y esa es la decision: si entrara, meter
    # 10.000 en una cartera de 10.000 pondria todos los activos al 50% de su
    # peso y el medidor entero se volveria rojo por una aportacion sin
    # invertir, no por deriva. Este test fija la firma, que es donde vive la
    # decision.
    import inspect
    assert "efectivo" not in inspect.signature(deriva.calcular).parameters


def test_una_sobreponderacion_grande_sale_fuera_de_banda():
    d = por_ticker(deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                                   {"AAPL": 0.5, "MSFT": 0.5}))
    assert d["AAPL"].peso_real == pytest.approx(0.6)
    assert d["AAPL"].desviacion == pytest.approx(0.1)
    assert d["AAPL"].fuera_de_banda
    assert d["MSFT"].desviacion == pytest.approx(-0.1)
    assert d["MSFT"].fuera_de_banda


def test_un_activo_del_objetivo_que_no_se_tiene_sale_con_deficit_completo():
    # Nunca comprado: peso real cero y desviacion igual a menos su objetivo.
    # Es correcto que aparezca, porque es a donde tiene que ir el dinero.
    d = por_ticker(deriva.calcular({"AAPL": 10_000.0},
                                   {"AAPL": 0.7, "MSFT": 0.3}))
    assert d["MSFT"].valor == pytest.approx(0.0)
    assert d["MSFT"].desviacion == pytest.approx(-0.3)
    assert d["MSFT"].fuera_de_banda


def test_un_activo_sin_objetivo_va_a_su_propio_bloque():
    # No se propone liquidarlo. Que algo no este en el plan admite dos lecturas
    # --el plan esta viejo, o la posicion sobra-- y el programa no puede
    # distinguirlas, asi que no elige por el usuario.
    d = deriva.calcular({"AAPL": 8000.0, "TSLA": 2000.0}, {"AAPL": 1.0})
    assert [l.ticker for l in d.lineas] == ["AAPL"]
    assert [l.ticker for l in d.fuera_del_objetivo] == ["TSLA"]
    assert d.fuera_del_objetivo[0].peso_real == pytest.approx(0.2)


def test_un_activo_sin_precio_se_aparta_y_se_nombra():
    # Valorarlo a cero rebajaria el total y falsearia la deriva de TODOS los
    # demas, no solo la suya. Se aparta del calculo y vuelve nombrado, para que
    # la pantalla pueda decir que el reparto se hizo sin el.
    d = deriva.calcular({"AAPL": 5000.0, "MSFT": 5000.0, "ZZZZ": None},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert d.sin_precio == ("ZZZZ",)
    assert d.invertido == pytest.approx(10_000.0)


def test_unos_pesos_que_no_suman_uno_se_normalizan_y_se_avisa():
    # Puede pasar de verdad: el equal-weight se calcula sobre los tickers del
    # portafolio, y si luego uno no trae precios el resto suma menos de uno.
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                        {"AAPL": 0.4, "MSFT": 0.4})
    assert d.pesos_normalizados
    assert por_ticker(d)["AAPL"].peso_objetivo == pytest.approx(0.5)


def test_unos_pesos_que_ya_suman_uno_no_se_marcan_como_normalizados():
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 4000.0},
                        {"AAPL": 0.5, "MSFT": 0.5})
    assert not d.pesos_normalizados


def test_una_cartera_sin_valor_no_divide_por_cero():
    # Pasa si todos los precios fallan a la vez. No hay deriva que medir, y eso
    # es distinto de una deriva de cero.
    d = deriva.calcular({"AAPL": None}, {"AAPL": 1.0})
    assert d.invertido == pytest.approx(0.0)
    assert d.lineas == ()
    assert d.sin_precio == ("AAPL",)


def test_los_pesos_normalizados_viajan_aunque_no_haya_nada_invertido():
    # El caso de una cartera recien creada: todo el dinero en efectivo y ningun
    # activo comprado. `lineas` sale vacia, asi que quien reparta el efectivo
    # no puede reconstruir el objetivo desde ahi y lo necesita aparte.
    d = deriva.calcular({}, {"AAPL": 0.4, "MSFT": 0.4})
    assert d.invertido == pytest.approx(0.0)
    assert d.lineas == ()
    assert d.pesos == {"AAPL": pytest.approx(0.5), "MSFT": pytest.approx(0.5)}


def test_las_lineas_vienen_ordenadas_por_desviacion():
    # La pantalla las pinta en este orden, asi que lo mas urgente sale arriba
    # sin que la vista tenga que ordenar nada.
    d = deriva.calcular({"AAPL": 6000.0, "MSFT": 3900.0, "NVDA": 100.0},
                        {"AAPL": 0.34, "MSFT": 0.33, "NVDA": 0.33})
    assert [l.ticker for l in d.lineas] == ["NVDA", "AAPL", "MSFT"]
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_deriva.py -q
```

Esperado: `ImportError: cannot import name 'deriva' from 'rebalanceo'`.

- [ ] **Step 3: Escribe el módulo**

Crea `rebalanceo/deriva.py`:

```python
"""Cuánto se ha separado la cartera real de la que se decidió tener.

El denominador es el **valor invertido**, no el patrimonio con el efectivo
dentro. Si el efectivo entrara, meter 10.000 en una cartera de 10.000 pondría
todos los activos al 50% de su peso objetivo y el medidor entero se volvería
rojo — por una aportación que aún no se ha invertido, no porque nada se haya
desviado. La deriva mide la **mezcla**; el efectivo es otra cosa y se trata
aparte, en `rebalanceo.reparto`.
"""

from dataclasses import dataclass

from rebalanceo import criterio


@dataclass(frozen=True)
class Desvio:
    """Un activo: lo que vale, el peso que ocupa y el que debería ocupar."""

    ticker: str
    valor: float
    peso_real: float
    peso_objetivo: float
    desviacion: float
    fuera_de_banda: bool


@dataclass(frozen=True)
class Deriva:
    """La cartera entera frente a su objetivo, más lo que no encaja en él."""

    invertido: float
    lineas: tuple[Desvio, ...]
    fuera_del_objetivo: tuple[Desvio, ...]
    sin_precio: tuple[str, ...]
    pesos_normalizados: bool
    # Los objetivo ya normalizados. Viajan aqui porque `lineas` sale vacia
    # cuando no hay nada invertido, y quien reparta el efectivo de una cartera
    # que aun no ha comprado nada los necesita igual.
    pesos: dict[str, float]


def calcular(
    valores: "dict[str, float | None]", objetivo: dict[str, float]
) -> Deriva:
    """Real weights against target weights, and what that puts out of band.

    `valores` viene de `seguimiento.rendimiento.por_activo`, donde un activo sin
    precio actual trae `valor=None`. Esos **no se valoran a cero**: se apartan y
    vuelven nombrados en `sin_precio`. Contarlos como cero rebajaría el total y
    falsearía la deriva de todos los demás, no sólo la suya, y nada en pantalla
    lo explicaría.

    Los pesos objetivo se normalizan si no suman uno, y se avisa. No es
    hipotético: el equal-weight se calcula sobre los tickers del portafolio
    guardado, y si alguno deja de tener precios el resto suma menos de uno.
    """
    sin_precio = tuple(t for t, v in valores.items() if v is None)
    con_precio = {t: float(v) for t, v in valores.items() if v is not None}
    invertido = sum(con_precio.values())

    suma = sum(objetivo.values())
    normalizados = bool(objetivo) and abs(suma - 1.0) > 1e-9
    pesos = {t: w / suma for t, w in objetivo.items()} if normalizados and suma else dict(objetivo)

    if invertido <= 0:
        # Sin valor no hay mezcla que medir, y eso no es lo mismo que una
        # deriva de cero. Se devuelve vacio para que la pantalla lo diga.
        return Deriva(0.0, (), (), sin_precio, normalizados, pesos)

    lineas, ajenos = [], []
    for ticker in sorted(set(con_precio) | set(pesos)):
        valor = con_precio.get(ticker, 0.0)
        peso_real = valor / invertido
        peso_objetivo = pesos.get(ticker, 0.0)
        desviacion = peso_real - peso_objetivo
        desvio = Desvio(
            ticker=ticker,
            valor=valor,
            peso_real=peso_real,
            peso_objetivo=peso_objetivo,
            desviacion=desviacion,
            fuera_de_banda=criterio.fuera_de_banda(desviacion, peso_objetivo),
        )
        (ajenos if peso_objetivo <= 0 else lineas).append(desvio)

    # De mayor a menor urgencia: el tamaño de la desviacion (en valor
    # absoluto) es lo que importa, no su signo — un activo un 30% por debajo
    # de su objetivo pide tanta atencion como uno un 30% por encima. Asi la
    # pantalla pinta arriba lo mas urgente sin ordenar nada por su cuenta.
    lineas.sort(key=lambda d: abs(d.desviacion), reverse=True)
    return Deriva(invertido, tuple(lineas), tuple(ajenos), sin_precio,
                  normalizados, pesos)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_deriva.py -q
```

Esperado: `11 passed`.

- [ ] **Step 5: Commit, y después sabotea**

```bash
git add rebalanceo/deriva.py tests/test_rebalanceo_deriva.py
git commit -m "feat: la deriva de la cartera frente a su objetivo"
```

Después del commit, rompe estas tres y confirma que cae el test que dice
probarlas. Deshaz cada una con `git checkout -- rebalanceo/deriva.py`.

| Sabotaje | Tiene que fallar |
|---|---|
| Meter los `sin_precio` en `invertido` como cero | el del activo sin precio |
| Quitar la normalización de pesos | el de los pesos que no suman uno |
| Ordenar `lineas` por ticker en vez de por desviación | el del orden |

---

## Task 3: El coste, sacado del propio libro

**Files:**
- Create: `rebalanceo/coste.py`
- Test: `tests/test_rebalanceo_coste.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_rebalanceo_coste.py`:

```python
import pytest

from rebalanceo import coste
from seguimiento.libro import Asiento


def compra(comision: float, id_: str = "c1") -> Asiento:
    return Asiento(id=id_, fecha="2026-08-01", tipo="compra", ticker="AAPL",
                   acciones=10.0, precio=200.0, importe=2000.0, comision=comision)


def test_sin_operaciones_registradas_se_usa_el_valor_declarado():
    estimado, del_libro = coste.por_operacion([], declarado=1.5)
    assert estimado == pytest.approx(1.5)
    assert not del_libro


def test_con_operaciones_se_usa_la_mediana_de_sus_comisiones():
    asientos = [compra(1.0, "a"), compra(2.0, "b"), compra(9.0, "c")]
    estimado, del_libro = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)
    assert del_libro


def test_las_comisiones_de_cero_cuentan():
    # El caso que un filtro "quedate con lo que no sea cero" romperia en
    # silencio. Si el broker no cobra y asi se registro, la estimacion correcta
    # es cero -- y filtrarlas convertiria un dato en la ausencia de un dato,
    # bloqueando operaciones por un coste que el usuario no paga.
    asientos = [compra(0.0, "a"), compra(0.0, "b")]
    estimado, del_libro = coste.por_operacion(asientos, declarado=1.5)
    assert estimado == pytest.approx(0.0)
    assert del_libro


def test_solo_cuentan_las_compras_y_las_ventas():
    # Una aportacion o un dividendo no son operaciones de mercado y no dicen
    # nada de lo que cuesta operar.
    asientos = [
        Asiento(id="ap", fecha="2026-08-01", tipo="aportacion", importe=1000.0,
                comision=50.0),
        compra(2.0, "c"),
    ]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)


def test_los_asientos_anulados_no_cuentan():
    asientos = [
        compra(50.0, "c1"),
        compra(2.0, "c2"),
        Asiento(id="x", fecha="2026-08-02", tipo="anulacion", anula="c1"),
    ]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)


def test_con_dos_comisiones_la_mediana_es_el_promedio():
    asientos = [compra(1.0, "a"), compra(3.0, "b")]
    estimado, _ = coste.por_operacion(asientos, declarado=99.0)
    assert estimado == pytest.approx(2.0)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_coste.py -q
```

Esperado: `ImportError: cannot import name 'coste' from 'rebalanceo'`.

- [ ] **Step 3: Escribe el módulo**

Crea `rebalanceo/coste.py`:

```python
"""Qué cuesta operar, según lo que este usuario ha pagado de verdad.

La `comision` de cada compra y cada venta ya está en el libro, así que la mejor
estimación de lo que costará la siguiente es la mediana de las anteriores — no
el supuesto de nadie. `research/costs.py` tiene escenarios de 5, 10 y 25 puntos
básicos, pero son supuestos de backtest institucional sobre rotación de cartera:
muchos brókers minoristas ya cobran cero por acciones de EE.UU., así que ese
número podría equivocarse en un orden de magnitud, y en la dirección de
desaconsejar operaciones que son gratis.

Mediana y no media: una sola operación con una comisión rara —un mercado
extranjero, una corrección— no debe mover la estimación de todas las demás.
"""

import statistics

from seguimiento import posiciones

OPERACIONES = frozenset({"compra", "venta"})


def por_operacion(
    asientos: "list", declarado: float
) -> tuple[float, bool]:
    """Estimated cost per trade, and whether it came from the book.

    **Las comisiones de cero cuentan.** Si el bróker no cobra y así se registró,
    la estimación correcta es cero. Filtrarlas «para quedarse con datos reales»
    convertiría un dato en la ausencia de un dato, y haría que un usuario sin
    comisiones viera operaciones bloqueadas por un coste que no paga.

    El segundo valor devuelto es lo que separa una estimación medida de un
    supuesto, y la pantalla lo dice: un número inventado que se lee como medido
    es peor que no tener número.
    """
    comisiones = [
        float(a.comision)
        for a in posiciones.vigentes(asientos)
        if a.tipo in OPERACIONES
    ]
    if not comisiones:
        return (float(declarado), False)
    return (float(statistics.median(comisiones)), True)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_coste.py -q
```

Esperado: `6 passed`.

- [ ] **Step 5: Commit, y después sabotea**

```bash
git add rebalanceo/coste.py tests/test_rebalanceo_coste.py
git commit -m "feat: estimar el coste de operar desde las comisiones del libro"
```

| Sabotaje | Tiene que fallar |
|---|---|
| Filtrar las comisiones de cero (`if a.comision > 0`) | el de las comisiones de cero |
| Quitar el filtro de `vigentes` | el de los asientos anulados |
| Usar la media en vez de la mediana | el de la mediana con tres valores |

---

## Task 4: El reparto del efectivo

**Files:**
- Create: `rebalanceo/reparto.py`
- Test: `tests/test_rebalanceo_reparto.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_rebalanceo_reparto.py`:

```python
import random

import pytest

from rebalanceo import reparto

OBJETIVO = {"AAPL": 0.5, "MSFT": 0.5}


def test_sin_efectivo_no_hay_nada_que_repartir():
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                         efectivo=0.0, coste=1.0)
    assert r.asignaciones == {}
    assert r.descartadas == {}


def test_el_dinero_va_donde_falta():
    # 6.000 y 4.000 con objetivo mitad y mitad: los 2.000 nuevos van enteros a
    # MSFT, que es lo que corrige deriva sin vender nada.
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                         efectivo=2000.0, coste=1.0)
    assert r.asignaciones == {"MSFT": pytest.approx(2000.0)}


def test_con_efectivo_suficiente_los_pesos_quedan_exactos():
    # La identidad que hace util al reparto: si el dinero alcanza para cubrir
    # todos los deficits, despues del reparto la cartera esta EXACTAMENTE en su
    # objetivo. Sin vender nada.
    valores = {"AAPL": 6000.0, "MSFT": 4000.0}
    r = reparto.repartir(valores, OBJETIVO, efectivo=4000.0, coste=1.0)
    finales = {t: valores.get(t, 0.0) + r.asignaciones.get(t, 0.0) for t in OBJETIVO}
    total = sum(finales.values())
    for ticker, peso in OBJETIVO.items():
        assert finales[ticker] / total == pytest.approx(peso)


@pytest.mark.parametrize("semilla", range(20))
def test_el_reparto_acerca_la_cartera_a_su_objetivo(semilla):
    # **La propiedad verdadera es agregada, no por activo.** Una version
    # anterior de este test afirmaba que el reparto no aleja a NINGUN activo de
    # su objetivo, y eso es falso: el reparto proporcional al deficit da mas a
    # quien mas le falta, el total crece, y un activo que casi estaba en su
    # sitio ve bajar su peso. Medido con los numeros que tenia este test:
    # MSFT pasaba de 0,0300 a 0,0342 de desviacion.
    #
    # Lo que si se cumple --y es lo que hace util al reparto-- es que la SUMA
    # de las desviaciones nunca sube. Se comprueba sobre casos generados y no
    # sobre uno elegido a mano, que es exactamente como se colo la afirmacion
    # falsa: un solo caso bien elegido la sostenia.
    #
    # Con coste cero para aislar la propiedad del reparto del tope economico,
    # que tiene sus propios tests.
    rnd = random.Random(semilla)
    n = rnd.randint(2, 6)
    tickers = [f"T{i}" for i in range(n)]
    crudos = [rnd.random() + 0.01 for _ in tickers]
    total_w = sum(crudos)
    objetivo = {t: w / total_w for t, w in zip(tickers, crudos)}
    valores = {t: rnd.random() * 10_000 + 1.0 for t in tickers}
    efectivo = rnd.random() * 8_000 + 1.0

    r = reparto.repartir(valores, objetivo, efectivo, coste=0.0)
    despues = {t: valores[t] + r.asignaciones.get(t, 0.0) for t in tickers}

    v_antes, v_despues = sum(valores.values()), sum(despues.values())
    antes = sum(abs(valores[t] / v_antes - objetivo[t]) for t in tickers)
    ahora = sum(abs(despues[t] / v_despues - objetivo[t]) for t in tickers)
    assert ahora <= antes + 1e-9


@pytest.mark.parametrize("semilla", range(20))
def test_los_deficits_nunca_suman_menos_que_el_efectivo(semilla):
    # La propiedad que sostiene la formula sin ramas, comprobada en vez de
    # asumida. Las diferencias CON SIGNO entre valor objetivo y valor actual
    # suman exactamente el efectivo, asi que las positivas --los deficits--
    # suman siempre eso o mas. Si esto fallara, sobraria dinero por colocar y
    # `C * d / sum(d)` repartiria de menos sin que nada lo dijera.
    rnd = random.Random(semilla)
    n = rnd.randint(2, 6)
    tickers = [f"T{i}" for i in range(n)]
    crudos = [rnd.random() + 0.01 for _ in tickers]
    total_w = sum(crudos)
    objetivo = {t: w / total_w for t, w in zip(tickers, crudos)}
    valores = {t: rnd.random() * 10_000 for t in tickers}
    efectivo = rnd.random() * 5_000

    total = sum(valores.values()) + efectivo
    deficits = [max(0.0, total * objetivo[t] - valores[t]) for t in tickers]
    assert sum(deficits) >= efectivo - 1e-6


def test_una_asignacion_que_no_compensa_se_retira_y_se_reparte():
    # 100 de efectivo entre dos deficits muy desiguales: la parte pequena no
    # llega al minimo economico, asi que se retira y su importe va a la otra.
    # El dinero tiene que ir a alguna parte -- descartar sin mas dejaria un
    # sobrante que nadie coloca.
    r = reparto.repartir({"AAPL": 5100.0, "MSFT": 4900.0},
                         {"AAPL": 0.55, "MSFT": 0.45},
                         efectivo=1000.0, coste=1.0)
    assert set(r.asignaciones) == {"AAPL"}
    assert r.asignaciones["AAPL"] == pytest.approx(100.0)
    assert set(r.descartadas) == {"MSFT"}


def test_una_aportacion_demasiado_pequena_no_se_invierte():
    # Si ninguna asignacion compensa, la respuesta util es decirlo, no proponer
    # cuatro compras de tres dolares.
    r = reparto.repartir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                         efectivo=20.0, coste=5.0)
    assert r.asignaciones == {}
    assert set(r.descartadas) == {"AAPL", "MSFT"}


def test_lo_repartido_suma_el_efectivo():
    r = reparto.repartir({"AAPL": 6000.0, "MSFT": 3000.0, "NVDA": 1000.0},
                         {"AAPL": 0.34, "MSFT": 0.33, "NVDA": 0.33},
                         efectivo=2500.0, coste=1.0)
    assert sum(r.asignaciones.values()) == pytest.approx(2500.0)


def test_un_activo_del_objetivo_que_no_se_tiene_recibe_dinero():
    r = reparto.repartir({"AAPL": 10_000.0}, {"AAPL": 0.5, "MSFT": 0.5},
                         efectivo=5000.0, coste=1.0)
    assert r.asignaciones["MSFT"] == pytest.approx(5000.0)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_reparto.py -q
```

Esperado: `ImportError: cannot import name 'reparto' from 'rebalanceo'`.

- [ ] **Step 3: Escribe el módulo**

Crea `rebalanceo/reparto.py`:

```python
"""Dónde poner el dinero nuevo, que es la forma barata de rebalancear.

Comprar lo infraponderado con una aportación corrige deriva **sin vender nada**:
no paga coste de venta y no realiza ninguna plusvalía. Por eso va primero, antes
de proponer ninguna venta.
"""

from dataclasses import dataclass

from rebalanceo import criterio


@dataclass(frozen=True)
class Reparto:
    """Cuánto va a cada activo, y qué se quedó fuera por no compensar."""

    asignaciones: dict[str, float]
    descartadas: dict[str, float]


def repartir(
    valores: dict[str, float],
    objetivo: dict[str, float],
    efectivo: float,
    coste: float,
) -> Reparto:
    """Split the idle cash across the underweight assets.

    Al activo `i` le tocaría `(V+C)·wᵢ` una vez invertido todo, así que su
    déficit es `max(0, (V+C)·wᵢ − vᵢ)` y la asignación es `C · dᵢ / Σd`.

    **La fórmula no necesita ramas, y merece la pena ver por qué.** Las
    diferencias con signo suman exactamente el efectivo::

        Σ [(V+C)·wᵢ − vᵢ] = (V+C)·1 − V = C

    Los déficits son sólo las positivas, así que suman siempre `C` o más, con
    igualdad únicamente cuando ningún activo está sobreponderado. Nunca sobra
    dinero por colocar, y no hay caso especial que escribir.

    Una asignación que no supera el mínimo económico se retira **y su importe se
    reparte entre las que sí lo pasan**, repitiendo hasta que ninguna quede por
    debajo. Descartar sin redistribuir dejaría dinero sin colocar: aquí no basta
    con decir que no compensa, porque el dinero tiene que ir a alguna parte.
    """
    if efectivo <= 0:
        return Reparto({}, {})

    total = sum(valores.values()) + efectivo
    candidatos = {}
    for ticker, peso in objetivo.items():
        deficit = total * peso - valores.get(ticker, 0.0)
        if deficit > 0:
            candidatos[ticker] = deficit

    descartadas: dict[str, float] = {}
    while candidatos:
        suma = sum(candidatos.values())
        asignaciones = {
            t: efectivo * d / suma for t, d in candidatos.items()
        }
        pequenas = [
            t for t, importe in asignaciones.items()
            if not criterio.merece_la_pena(importe, coste)
        ]
        if not pequenas:
            return Reparto(asignaciones, descartadas)
        for ticker in pequenas:
            descartadas[ticker] = asignaciones[ticker]
            del candidatos[ticker]

    # Ninguna compensa: la aportacion es demasiado pequena para invertirla
    # ahora, que es una respuesta util y bastante mejor que proponer cuatro
    # compras de tres dolares.
    return Reparto({}, descartadas)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_reparto.py -q
```

Esperado: `47 passed` — 7 tests sueltos más 40 de los dos parametrizados,
el de la identidad de los déficits y el de que el reparto acerca la cartera.

- [ ] **Step 5: Commit, y después sabotea**

```bash
git add rebalanceo/reparto.py tests/test_rebalanceo_reparto.py
git commit -m "feat: repartir la aportacion entre lo infraponderado"
```

| Sabotaje | Tiene que fallar |
|---|---|
| No redistribuir tras descartar (romper el `while`, devolver a la primera) | el de la asignación que se retira y se reparte |
| Repartir a pesos objetivo en vez de a déficits (`efectivo * peso`) | el de que el dinero va donde falta |
| Quitar la guarda `if efectivo <= 0` | el de sin efectivo — y fíjate en **cómo** falla: si sale `ZeroDivisionError` en vez de un assert, el test está pinzando la guarda de verdad |

---

## Task 5: La propuesta completa

**Files:**
- Create: `rebalanceo/propuesta.py`
- Test: `tests/test_rebalanceo_propuesta.py`

- [ ] **Step 1: Escribe los tests que fallan**

Crea `tests/test_rebalanceo_propuesta.py`:

```python
import pytest

from rebalanceo import propuesta
from seguimiento.libro import Asiento

OBJETIVO = {"AAPL": 0.5, "MSFT": 0.5}


def compra(comision: float, id_: str = "c1") -> Asiento:
    return Asiento(id=id_, fecha="2026-08-01", tipo="compra", ticker="AAPL",
                   acciones=10.0, precio=200.0, importe=2000.0, comision=comision)


def test_una_cartera_en_su_objetivo_no_propone_nada():
    # El control negativo. Si una cartera exactamente en su objetivo, sin
    # efectivo, genera cualquier operacion, algo esta mal.
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert p.con_efectivo == ()
    assert p.y_ademas == ()
    assert p.basta_con_la_aportacion


def test_la_aportacion_sola_puede_bastar():
    # 6.000 y 4.000 con 4.000 de efectivo: el reparto mide el deficit de cada
    # activo contra el total YA CON el efectivo dentro (14.000), asi que AAPL
    # tambien recibe algo aunque hoy este sobreponderado sobre los 10.000
    # actuales -- reparto.repartir ya lo prueba con estos mismos numeros en
    # test_con_efectivo_suficiente_los_pesos_quedan_exactos. Lo que importa
    # aqui es que, sea cual sea el reparto, se llega justo al objetivo y no
    # hace falta vender nada.
    p = propuesta.construir({"AAPL": 6000.0, "MSFT": 4000.0}, OBJETIVO,
                            efectivo=4000.0, asientos=[], coste_declarado=1.0)
    importes = {o.ticker: o.importe for o in p.con_efectivo}
    assert importes == {"AAPL": pytest.approx(1000.0), "MSFT": pytest.approx(3000.0)}
    assert p.basta_con_la_aportacion
    assert p.y_ademas == ()


def test_sin_efectivo_suficiente_hacen_falta_ventas():
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert not p.basta_con_la_aportacion
    acciones = {o.ticker: o for o in p.y_ademas}
    assert acciones["AAPL"].accion == "vender"
    assert acciones["MSFT"].accion == "comprar"


def test_las_ventas_y_compras_se_autofinancian():
    # Suman cero por construccion: lo que sale de los sobreponderados es
    # exactamente lo que entra en los infraponderados.
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert sum(o.importe for o in p.y_ademas) == pytest.approx(0.0, abs=1e-6)


def test_una_operacion_que_no_compensa_se_muestra_descartada():
    # No desaparece. Una propuesta omitida en silencio es indistinguible de una
    # que nadie calculo, y el usuario no puede saber cual de las dos fue.
    # 600/400 sobre un total de 1.000 es una desviacion del 10%: supera la
    # banda absoluta del 5% y dispara la deriva, pero el importe a mover -- 100
    # dolares -- es pequeno de verdad, y una comision de 2 dolares (el 2% del
    # importe) ya supera el tope del 1% que fija el criterio.
    p = propuesta.construir({"AAPL": 600.0, "MSFT": 400.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(2.0)],
                            coste_declarado=99.0)
    assert p.y_ademas == ()
    assert {o.ticker for o in p.descartadas_por_coste} == {"AAPL", "MSFT"}
    assert all(not o.viable for o in p.descartadas_por_coste)
    # Aqui es donde importa que `basta_con_la_aportacion` sea un hecho propio:
    # `y_ademas` esta vacia, pero la cartera SIGUE fuera de banda -- lo unico
    # que paso es que arreglarlo no compensa el coste. Deducirlo de `not
    # y_ademas` diria "no hace falta nada" cuando hace falta y no compensa.
    assert not p.basta_con_la_aportacion


def test_el_coste_del_libro_manda_sobre_el_declarado():
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(3.0)],
                            coste_declarado=99.0)
    assert p.coste_por_operacion == pytest.approx(3.0)
    assert p.coste_del_libro


def test_sin_operaciones_en_el_libro_el_coste_es_el_declarado_y_se_marca():
    p = propuesta.construir({"AAPL": 5000.0, "MSFT": 5000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=2.5)
    assert p.coste_por_operacion == pytest.approx(2.5)
    assert not p.coste_del_libro


def test_el_coste_total_cuenta_una_comision_por_operacion():
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[compra(4.0)],
                            coste_declarado=99.0)
    assert p.coste_total == pytest.approx(4.0 * len(p.y_ademas))


def test_una_cartera_de_solo_efectivo_propone_la_compra_inicial():
    # Un libro recien creado con su aportacion dentro y ninguna compra. No hay
    # deriva que medir --no hay mezcla-- pero si hay todo el dinero por
    # asignar, y el reparto tiene que apuntar al objetivo igualmente.
    p = propuesta.construir({}, OBJETIVO, efectivo=10_000.0, asientos=[],
                            coste_declarado=1.0)
    assert {o.ticker for o in p.con_efectivo} == {"AAPL", "MSFT"}
    assert sum(o.importe for o in p.con_efectivo) == pytest.approx(10_000.0)


def test_la_deriva_viaja_dentro_de_la_propuesta():
    # La pantalla pinta los medidores desde aqui, sin volver a calcular nada.
    # AAPL y MSFT se desvian la misma magnitud (0.3 en valor absoluto), asi que
    # el orden que fija deriva.calcular es el de desempate: insercion
    # alfabetica preservada por un sort estable, no la magnitud de la
    # desviacion -- aqui no hay nada que la distinga.
    p = propuesta.construir({"AAPL": 8000.0, "MSFT": 2000.0}, OBJETIVO,
                            efectivo=0.0, asientos=[], coste_declarado=1.0)
    assert p.deriva.invertido == pytest.approx(10_000.0)
    assert [l.ticker for l in p.deriva.lineas] == ["AAPL", "MSFT"]


@dataclass(frozen=True)
class Operacion:
    """Una compra o una venta propuesta, con lo que costaría."""

    ticker: str
    accion: str
    importe: float
    coste: float
    viable: bool


@dataclass(frozen=True)
class Propuesta:
    """El plan entero: la deriva, qué hacer con el efectivo, y qué falta."""

    deriva: "deriva_mod.Deriva"
    con_efectivo: tuple[Operacion, ...]
    y_ademas: tuple[Operacion, ...]
    descartadas_por_coste: tuple[Operacion, ...]
    basta_con_la_aportacion: bool
    coste_por_operacion: float
    coste_del_libro: bool
    coste_total: float


def construir(
    valores: "dict[str, float | None]",
    objetivo: dict[str, float],
    efectivo: float,
    asientos: "list",
    coste_declarado: float,
) -> Propuesta:
    """Assemble the whole plan from the book's current state.

    `basta_con_la_aportacion` es `True` cuando después de repartir el efectivo
    no queda nada fuera de banda. **Se devuelve como un hecho propio y no se
    deduce de que `y_ademas` esté vacía**: esa lista también sale vacía cuando
    todas las operaciones se descartaron por coste, y las dos situaciones dicen
    cosas opuestas al usuario.
    """
    por_operacion, del_libro = coste_mod.por_operacion(asientos, coste_declarado)

    antes = deriva_mod.calcular(valores, objetivo)
    con_precio = {t: v for t, v in valores.items() if v is not None}
    # De `antes.pesos` y no de `antes.lineas`: con una cartera que todavia no ha
    # comprado nada, `lineas` sale vacia y reconstruir los pesos desde ahi
    # dejaria el reparto sin objetivo al que apuntar -- justo en el caso en que
    # hay todo el efectivo por asignar.
    pesos = antes.pesos

    reparto = reparto_mod.repartir(con_precio, pesos, efectivo, por_operacion)
    con_efectivo = tuple(
        Operacion(t, "comprar", importe, por_operacion, True)
        for t, importe in sorted(reparto.asignaciones.items())
    )

    # La cartera tal como quedaria tras invertir el efectivo, que es contra lo
    # que se decide si ademas hace falta vender.
    despues_valores = {
        t: con_precio.get(t, 0.0) + reparto.asignaciones.get(t, 0.0)
        for t in set(con_precio) | set(reparto.asignaciones)
    }
    despues = deriva_mod.calcular(despues_valores, pesos)
    pendientes = [l for l in despues.lineas if l.fuera_de_banda]

    y_ademas, descartadas = [], []
    for linea in pendientes:
        objetivo_valor = despues.invertido * linea.peso_objetivo
        importe = objetivo_valor - linea.valor
        operacion = Operacion(
            ticker=linea.ticker,
            accion="comprar" if importe > 0 else "vender",
            importe=importe,
            coste=por_operacion,
            viable=criterio.merece_la_pena(importe, por_operacion),
        )
        (y_ademas if operacion.viable else descartadas).append(operacion)

    return Propuesta(
        deriva=antes,
        con_efectivo=con_efectivo,
        y_ademas=tuple(y_ademas),
        descartadas_por_coste=tuple(descartadas),
        basta_con_la_aportacion=not pendientes,
        coste_por_operacion=por_operacion,
        coste_del_libro=del_libro,
        coste_total=por_operacion * (len(con_efectivo) + len(y_ademas)),
    )
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

```bash
UV_LINK_MODE=copy uv run pytest tests/test_rebalanceo_propuesta.py -q
```

Esperado: `10 passed`.

- [ ] **Step 5: Corre la suite entera**

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

Esperado: `997 passed, 4 skipped, 6 deselected` — los 911 de base más 86
nuevos (12 + 11 + 6 + 47 + 10).

- [ ] **Step 6: Commit, y después sabotea**

```bash
git add rebalanceo/propuesta.py tests/test_rebalanceo_propuesta.py
git commit -m "feat: la propuesta completa, con la aportacion antes que las ventas"
```

| Sabotaje | Tiene que fallar |
|---|---|
| Deducir `basta_con_la_aportacion` de `not y_ademas` | el de la operación descartada — y ahí está el punto: con las dos descartadas, `y_ademas` queda vacía y el usuario leería «no hace falta nada» cuando la cartera sigue fuera de banda |
| Calcular `y_ademas` contra `antes` en vez de contra `despues` | el de que la aportación sola puede bastar |
| Contar el coste una vez en total en vez de por operación | el del coste total |

---

## Task 6: La pantalla

**Files:**
- Create: `vistas/rebalanceo.py`
- Modify: `app.py` (registrar la página)

- [ ] **Step 1: Escribe la vista**

Crea `vistas/rebalanceo.py`. Sólo widgets: todo cálculo sale de `rebalanceo/`,
y si hace falta lógica nueva va al paquete y se prueba allí.

```python
"""Qué hacer con la cartera: la deriva, el reparto y lo que costaría.

Pantalla aparte de «Seguimiento» a propósito. Aquella muestra **hechos** —lo que
se compró y cuánto vale— y esta muestra **propuestas**. Mezclarlas haría más
fácil leer una sugerencia como si fuera un dato registrado, que es la confusión
que este proyecto evita en todas partes.
"""

from datetime import date

import pandas as pd
import streamlit as st

import cartera
import tema
from rebalanceo import criterio, propuesta as prop
from seguimiento import libro as mod, posiciones, precios, rendimiento

# Lo que se supone que cuesta una operación cuando el libro todavía no tiene
# ninguna registrada. Sale del escenario "base" de `research/costs.py` aplicado
# a una operación típica de mil dólares, y se muestra siempre como supuesto.
COSTE_SUPUESTO = 1.0

st.markdown(
    tema.cabecera(
        "Rebalanceo",
        "Cuánto se ha separado tu cartera del objetivo, dónde poner el dinero "
        "nuevo, y qué costaría corregir el resto. Aquí no se registra nada: "
        "esto son propuestas, y lo que ejecutes lo anotas en Seguimiento.",
    ),
    unsafe_allow_html=True,
)

entradas = [e for e in mod.listar() if e.libro is not None]
if not entradas:
    st.info("Todavía no llevas ningún libro. Empieza uno desde **Seguimiento**.")
    if st.button("Ir a seguimiento", icon=":material/monitoring:"):
        st.switch_page("vistas/seguimiento.py")
    st.stop()

etiquetas = {f"{e.libro.nombre} · {e.ruta.name}": e for e in entradas}
elegida = etiquetas[st.selectbox("Libro", options=list(etiquetas))]
actual = elegida.libro

# --- Sin objetivo no hay deriva que medir -----------------------------------

pesos = mod.pesos_objetivo(actual.objetivo)
if not pesos:
    st.info(
        "Este libro no tiene pesos objetivo, así que no hay contra qué medir la "
        "deriva. Puedes asignarle **repartir por igual** sobre los activos que "
        "ya tiene, o pasar por el optimizador y guardar un portafolio nuevo."
    )
    if st.button("Ir al optimizador", icon=":material/insights:"):
        st.switch_page("vistas/optimizador.py")
    st.stop()

st.caption(
    f"Objetivo vigente del **{actual.objetivo.fecha}** "
    f"({(date.today() - date.fromisoformat(actual.objetivo.fecha)).days} días). "
    f"Banda: {criterio.BANDA_ABSOLUTA:.0%} absoluto o "
    f"{criterio.BANDA_RELATIVA:.0%} relativo, lo que ocurra primero."
)

# --- Precios y estado --------------------------------------------------------

vivos = posiciones.vigentes(actual.asientos)
tickers = sorted(set(pesos) | {a.ticker for a in vivos if a.ticker})
desde = min((a.fecha for a in vivos), default=date.today().isoformat())


@st.cache_data(ttl=3600, show_spinner="Descargando precios...")
def _historia(tickers: tuple[str, ...], desde: str):
    return precios.descargar(list(tickers), desde=desde)


historia = _historia(tuple(tickers), desde)
ultimos = {t: precios.ultimo(historia, t)[0] for t in historia.cierres.columns}
lineas = rendimiento.por_activo(actual.asientos, {t: p for t, p in ultimos.items() if p})
valores = {t: l.valor for t, l in lineas.items()}
efectivo = posiciones.estado(actual.asientos).efectivo

plan = prop.construir(valores, pesos, efectivo, actual.asientos, COSTE_SUPUESTO)

if plan.deriva.sin_precio:
    st.warning(
        "Sin precio para: " + ", ".join(plan.deriva.sin_precio) + ". **El "
        "reparto y la deriva se calculan sin esas posiciones**, así que los "
        "pesos de abajo son sobre un total incompleto."
    )
if plan.deriva.pesos_normalizados:
    st.caption(
        "Los pesos objetivo no sumaban 100% y se han normalizado. Pasa cuando "
        "el objetivo se fijó sobre activos que hoy no traen precios."
    )

# --- El veredicto ------------------------------------------------------------

fuera = [l for l in plan.deriva.lineas if l.fuera_de_banda]
if not fuera:
    st.success(
        "**Dentro de banda.** Ningún activo se ha separado lo suficiente de su "
        "objetivo como para que operar compense."
    )
elif plan.basta_con_la_aportacion:
    st.info(
        f"**{len(fuera)} activo(s) fuera de banda, y tu efectivo basta para "
        "corregirlo.** No hace falta vender nada."
    )
else:
    st.warning(
        f"**{len(fuera)} activo(s) fuera de banda.** El efectivo disponible no "
        "llega para corregirlo sólo con compras."
    )

# --- Los medidores -----------------------------------------------------------

st.subheader("Deriva por activo")
st.markdown(_medidores(plan.deriva), unsafe_allow_html=True)

# --- Qué hacer ---------------------------------------------------------------

if plan.con_efectivo:
    st.subheader(f"Con tu efectivo ({efectivo:,.2f} {actual.moneda})")
    st.caption(
        "Comprar con dinero nuevo corrige deriva **sin vender nada**: no paga "
        "coste de venta y no realiza ninguna plusvalía. Por eso va primero."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Comprar": f"{o.importe:,.2f}"}
            for o in plan.con_efectivo
        ]),
        use_container_width=True, hide_index=True,
    )
elif efectivo > 0:
    st.subheader(f"Con tu efectivo ({efectivo:,.2f} {actual.moneda})")
    st.info(
        "La aportación es demasiado pequeña para que compense invertirla ahora: "
        f"con un coste de {plan.coste_por_operacion:,.2f} por operación, "
        "cualquier reparto se comería más del "
        f"{criterio.COSTE_MAXIMO:.0%} de lo comprado."
    )

if plan.y_ademas:
    st.subheader("Y además haría falta")
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Acción": o.accion.capitalize(),
             "Importe": f"{abs(o.importe):,.2f}", "Coste": f"{o.coste:,.2f}"}
            for o in plan.y_ademas
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption("Estas operaciones se autofinancian: lo que sale de unas entra en otras.")

if plan.descartadas_por_coste:
    st.subheader("Descartadas porque el coste se las come")
    st.caption(
        "Están fuera de banda, pero mover ese importe cuesta más del "
        f"{criterio.COSTE_MAXIMO:.0%}. Se enseñan igualmente: una propuesta "
        "omitida en silencio es indistinguible de una que nadie calculó."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": o.ticker, "Acción": o.accion.capitalize(),
             "Importe": f"{abs(o.importe):,.2f}", "Coste": f"{o.coste:,.2f}"}
            for o in plan.descartadas_por_coste
        ]),
        use_container_width=True, hide_index=True,
    )

if plan.deriva.fuera_del_objetivo:
    st.subheader("Fuera del objetivo")
    st.caption(
        "Los tienes pero no están en el plan. **No se propone nada** con ellos: "
        "puede ser que el objetivo esté desactualizado o que la posición sobre, "
        "y el programa no puede distinguir las dos cosas."
    )
    st.dataframe(
        pd.DataFrame([
            {"Ticker": l.ticker, "Valor": f"{l.valor:,.2f}",
             "Peso": f"{l.peso_real:.2%}"}
            for l in plan.deriva.fuera_del_objetivo
        ]),
        use_container_width=True, hide_index=True,
    )

# --- El coste ----------------------------------------------------------------

st.caption(
    f"Coste estimado: **{plan.coste_por_operacion:,.2f} por operación**, "
    + ("mediana de las comisiones que registraste en este libro."
       if plan.coste_del_libro else
       "un supuesto — este libro todavía no tiene ninguna operación registrada.")
    + f" Total de la propuesta: **{plan.coste_total:,.2f}**. No incluye la "
    "horquilla de compraventa, que no está registrada en ninguna parte."
)
```

- [ ] **Step 2: Añade el medidor de deriva**

`medidores.py` presta el esqueleto visual pero **no su escala**: está hecho para
z-scores y su vocabulario habla de «pares», que aquí no significa nada. Añade
esta función al principio de `vistas/rebalanceo.py`, justo después de
`COSTE_SUPUESTO`:

```python
def _medidores(deriva) -> str:
    """Una fila por activo, con su barra y su veredicto escrito.

    El veredicto va en palabras además de en color, como en `medidores.py`,
    porque un medidor que sólo cambia de tono no le dice nada a quien no
    distingue el verde del rojo ni a quien mira la página en blanco y negro.

    La escala es propia: va de −10 a +10 puntos de desviación, con la banda
    absoluta marcada. La de `medidores.py` es de z-scores y sus cortes no
    significan nada aquí.
    """
    tope = 0.10
    filas = []
    for linea in deriva.lineas:
        pct = max(-tope, min(tope, linea.desviacion))
        posicion = (pct + tope) / (2 * tope) * 100
        if not linea.fuera_de_banda:
            color, veredicto = tema.VERDE, "En banda"
        elif linea.desviacion > 0:
            color, veredicto = tema.AMBAR, "Sobreponderado"
        else:
            color, veredicto = tema.AMBAR, "Infraponderado"
        filas.append(
            f'<div class="mpp-fila">'
            f'<span class="mpp-nombre">{linea.ticker}</span>'
            f'<span class="mpp-valor">{linea.peso_real:.1%} '
            f'<span class="mpp-nota">de {linea.peso_objetivo:.1%}</span></span>'
            f'<span class="mpp-pista"><span class="mpp-marca" '
            f'style="left:{posicion:.1f}%;background:{color}"></span></span>'
            f'<span class="mpp-vered" style="color:{color}">{veredicto}</span>'
            f'<span class="mpp-z">{linea.desviacion:+.1%}</span>'
            "</div>"
        )
    return "".join(filas)
```

- [ ] **Step 3: Registra la página**

En `app.py`, dentro de la sección `"Cartera"` de `st.navigation`, **justo
después** de la de Seguimiento:

```python
            st.Page(
                "vistas/rebalanceo.py", title="Rebalanceo",
                icon=":material/balance:",
            ),
```

- [ ] **Step 4: Comprueba que no hay regresión y recorre la pantalla**

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"
```

Esperado: el mismo recuento que al final de la Task 5. Esta tarea no añade
tests porque no añade lógica: todo lo que decide algo está en `rebalanceo/` y
probado allí. Si te ves escribiendo una regla aquí, va al paquete.

Después arranca la app y comprueba cinco cosas a mano, porque son de interfaz:

```bash
UV_LINK_MODE=copy uv run streamlit run app.py
```

1. Un libro **sin objetivo** enseña su pantalla propia y no revienta.
2. Un libro **en su objetivo** dice «dentro de banda» y no propone nada.
3. Un libro **desviado con efectivo** enseña el bloque «Con tu efectivo» y dice
   que no hace falta vender.
4. Un libro **desviado sin efectivo** enseña «Y además haría falta».
5. Un activo **que no está en el objetivo** aparece en su bloque, sin
   recomendación.

- [ ] **Step 5: Commit**

```bash
git add vistas/rebalanceo.py app.py
git commit -m "feat: la pantalla de rebalanceo, con la aportacion antes que las ventas"
```

---

## Task 7: Dejarlo dicho

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Actualiza CONTEXTO.md**

Marca G como terminado en la tabla de sub-proyectos, y añade una sección
«Resultado del sub-proyecto G» en el mismo tono que las de A, B, C y F. Tiene
que decir, como mínimo:

- **La banda 5/25 está congelada** en su propio commit, y cambiarla exige una
  enmienda fechada. Los dos umbrales existen porque ninguno funciona solo.
- **El tope de coste del 1%** es lo que hace el criterio económico y no sólo
  geométrico, y viene directamente del veredicto de D: sin ventaja demostrada en
  ninguna señal, operar de más es el único destructor de valor garantizado.
- **El efectivo no entra en el denominador del peso real**, para que una
  aportación sin invertir no ponga el medidor entero en rojo.
- **Las comisiones de cero cuentan** al estimar el coste.
- **G no escribe en el libro.**
- Qué hereda H, que es sólo la lista de tickers.

Y actualiza el recuento de tests de la lista de comandos.

- [ ] **Step 2: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: el rebalanceo, y por que la banda va congelada"
```

---

## Lo que queda para H

G no deja nada para H salvo la lista de tickers del libro, que ya estaba en F.
Los dos sub-proyectos son independientes: H trae noticias y calendario, y no
necesita ni la deriva ni el reparto.
