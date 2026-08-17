# Gate de aprobación (sub-proyecto C) — plan de implementación

> **Para agentes:** SUB-SKILL OBLIGATORIA: usa `superpowers:subagent-driven-development` (recomendada) o `superpowers:executing-plans` para ejecutar este plan tarea a tarea. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Objetivo:** una página donde un humano revisa los candidatos de B, aprueba o rechaza, puede añadir empresas a mano con su motivo, y deja un acta fechada; los tickers aprobados llegan al optimizador.

**Arquitectura:** paquete `aprobacion/` con toda la lógica —cargar y validar, fusionar, construir y escribir el acta— probado sin Streamlit y sin red. La página `pages/1_Revisar_candidatos.py` sólo pinta widgets y llama al paquete. `app.py` cambia una línea. B gana un fichero de salida.

**Stack:** Python 3.14, Streamlit, pytest. Sin dependencias nuevas.

**Diseño:** `docs/superpowers/specs/2026-08-15-gate-aprobacion-design.md`

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `ranking/run.py` (modificar) | `Resultado` gana `corrida`; `guardar` escribe `corrida.json` |
| `aprobacion/__init__.py` (crear) | Paquete vacío |
| `aprobacion/carga.py` (crear) | Leer y validar `fichas.json` y `corrida.json`; describir la corrida en una frase |
| `aprobacion/acta.py` (crear) | Fusionar aprobados y añadidos, validar, construir el acta y escribirla |
| `pages/1_Revisar_candidatos.py` (crear) | Widgets. Sin lógica de negocio |
| `app.py` (modificar) | El campo de tickers lee su valor por defecto de la sesión |
| `tests/test_aprobacion_carga.py` (crear) | |
| `tests/test_aprobacion_acta.py` (crear) | |
| `tests/test_ranking_run.py` (modificar) | Cobertura de `corrida.json` |

**Lo que queda sin test automático:** el cableado de widgets de la página. Es aceptable **sólo porque** la lógica vive en `aprobacion/`; si algún paso te lleva a poner una condición de negocio dentro de la página, muévela al paquete.

---

### Task 1: B escribe `corrida.json`

**Files:**
- Modify: `ranking/run.py`
- Test: `tests/test_ranking_run.py`

- [ ] **Step 1: Escribe los tests que fallan**

Añade a `tests/test_ranking_run.py`:

```python
def test_el_resultado_lleva_los_metadatos_de_la_corrida(sin_red):
    resultado = construir_ranking(con_llm=False, n=5, tope=3)
    corrida = resultado.corrida
    assert corrida["universo"] == "sp500"
    assert corrida["tamano_top"] == 5
    assert corrida["tope_por_sector"] == 3
    assert corrida["con_llm"] is False
    assert corrida["n_supervivientes"] == len(resultado.tabla)
    assert corrida["n_panel"] == corrida["n_supervivientes"] + sum(
        resultado.exclusiones.values()
    )
    assert corrida["exclusiones"] == resultado.exclusiones


def test_guardar_escribe_corrida_json(sin_red, tmp_path: Path):
    resultado = construir_ranking(con_llm=False, n=5)
    guardar(resultado, tmp_path)

    corrida = json.loads((tmp_path / "corrida.json").read_text(encoding="utf-8"))
    assert corrida["n_supervivientes"] == len(resultado.tabla)
    assert corrida["tamano_top"] == 5


def test_corrida_json_es_json_estricto(sin_red, tmp_path: Path):
    # Mismo contrato que fichas.json: un NaN se escribiria como el literal
    # `NaN`, que ningun parser estricto acepta. n_panel viene de una suma de
    # enteros de pandas, que es justo donde se cuela un float.
    resultado = construir_ranking(con_llm=False, n=5)
    resultado.corrida["n_panel"] = float("nan")
    with pytest.raises(ValueError):
        guardar(resultado, tmp_path)
```

- [ ] **Step 2: Ejecuta los tests para verificar que fallan**

Run: `pytest tests/test_ranking_run.py -q`
Expected: FAIL con `AttributeError: 'Resultado' object has no attribute 'corrida'`

- [ ] **Step 3: Escribe la implementación**

En `ranking/run.py`, añade el import de `date` arriba:

```python
from datetime import date
```

Añade el campo al dataclass:

```python
@dataclass
class Resultado:
    """Everything a run produced, including what it left out and why."""

    tabla: pd.DataFrame
    fichas: list[dict]
    exclusiones: dict[str, int]
    cobertura_panel: object
    corrida: dict
```

Sustituye el `return Resultado(...)` del final de `construir_ranking` por:

```python
    supervivientes = tabla.loc[motivos.isna()]
    exclusiones = motivos.dropna().value_counts().to_dict()

    return Resultado(
        tabla=supervivientes,
        fichas=fichas,
        exclusiones=exclusiones,
        cobertura_panel=cobertura,
        # Los metadatos se construyen aqui y no en guardar() porque aqui estan
        # en alcance los parametros de la corrida. guardar() se queda tonto: no
        # calcula nada, solo escribe lo que ya se decidio.
        corrida={
            "fecha": date.today().isoformat(),
            "universo": source if isinstance(source, str) else f"{len(source)} tickers",
            "n_panel": int(len(supervivientes) + sum(exclusiones.values())),
            "n_supervivientes": int(len(supervivientes)),
            "exclusiones": {motivo: int(n) for motivo, n in exclusiones.items()},
            "tope_por_sector": int(tope),
            "tamano_top": int(n),
            "con_llm": bool(con_llm),
        },
    )
```

Añade la escritura al final de `guardar`:

```python
    (destino / "corrida.json").write_text(
        json.dumps(resultado.corrida, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
```

Y amplía su docstring con una frase:

```python
    """Write the four outputs. fichas.json is the contract with sub-project C.
```

- [ ] **Step 4: Ejecuta los tests**

Run: `pytest tests/test_ranking_run.py -q`
Expected: PASS

- [ ] **Step 5: Bite-check**

Para cada test nuevo, rompe a propósito lo que verifica y comprueba que falla. Como mínimo:

- Quita `allow_nan=False` de la escritura de `corrida.json` → debe fallar `test_corrida_json_es_json_estricto`.
- Cambia `n_panel` para que use sólo `len(supervivientes)` → debe fallar el primer test.
- Deja de escribir `corrida.json` → debe fallar el segundo.

Reporta la salida literal de pytest en cada caso.

- [ ] **Step 6: Commit**

```bash
git add ranking/run.py tests/test_ranking_run.py
git commit -m "feat: B escribe corrida.json con los metadatos de la corrida"
```

---

### Task 2: Cargar y validar las entradas

**Files:**
- Create: `aprobacion/__init__.py`, `aprobacion/carga.py`
- Test: `tests/test_aprobacion_carga.py`

- [ ] **Step 1: Escribe los tests que fallan**

`tests/test_aprobacion_carga.py`:

```python
import json
from pathlib import Path

import pytest

from aprobacion.carga import (
    ContratoRoto,
    FaltanFichas,
    cargar_candidatos,
    resumen_corrida,
)

FICHA = {
    "ticker": "AAA",
    "sector_gics": "Information Technology",
    "puesto": 1,
    "compuesto": 1.42,
    "pilares": {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1},
    "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
    "flojos": [{"kpi": "per", "valor": 34.2, "z": 2.0}],
    "cobertura": {"kpis_con_dato": 14, "pilares_con_dato": 4},
    "desplazo_a": ["BBB"],
    "generada_por": "plantilla",
    "narrativa": None,
}

CORRIDA = {
    "fecha": "2026-08-15",
    "universo": "sp500",
    "n_panel": 502,
    "n_supervivientes": 425,
    "exclusiones": {"pilar_sin_datos": 72, "datos_rancios": 2},
    "tope_por_sector": 3,
    "tamano_top": 15,
    "con_llm": False,
}


def escribir(directorio: Path, fichas=None, corrida=None) -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    if fichas is not None:
        (directorio / "fichas.json").write_text(
            json.dumps(fichas, ensure_ascii=False), encoding="utf-8"
        )
    if corrida is not None:
        (directorio / "corrida.json").write_text(
            json.dumps(corrida, ensure_ascii=False), encoding="utf-8"
        )
    return directorio


def test_carga_las_fichas_y_la_corrida(tmp_path: Path):
    directorio = escribir(tmp_path, fichas=[FICHA], corrida=CORRIDA)
    candidatos = cargar_candidatos(directorio)
    assert [f["ticker"] for f in candidatos.fichas] == ["AAA"]
    assert candidatos.corrida["n_supervivientes"] == 425


def test_sin_fichas_dice_que_comando_correr(tmp_path: Path):
    with pytest.raises(FaltanFichas) as error:
        cargar_candidatos(tmp_path)
    assert "construir_ranking" in str(error.value)


def test_una_ficha_a_la_que_le_falta_un_campo_nombra_el_campo(tmp_path: Path):
    incompleta = {k: v for k, v in FICHA.items() if k != "compuesto"}
    directorio = escribir(tmp_path, fichas=[incompleta], corrida=CORRIDA)
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "compuesto" in str(error.value)


def test_un_fichas_json_truncado_falla_visible(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "fichas.json").write_text("[{esto no es json", encoding="utf-8")
    with pytest.raises(ContratoRoto):
        cargar_candidatos(tmp_path)


def test_sin_corrida_json_se_puede_revisar_igual(tmp_path: Path):
    # El salidas/ que existe hoy se genero antes de que corrida.json
    # existiera: este camino se ejercita desde el primer dia.
    directorio = escribir(tmp_path, fichas=[FICHA])
    candidatos = cargar_candidatos(directorio)
    assert candidatos.corrida is None
    assert len(candidatos.fichas) == 1


def test_una_corrida_json_rota_no_se_ignora_en_silencio(tmp_path: Path):
    # Ausente y roto no son lo mismo: ausente significa "lo genero un B
    # antiguo", roto significa que algo fallo y hay que verlo.
    directorio = escribir(tmp_path, fichas=[FICHA], corrida={"universo": "sp500"})
    with pytest.raises(ContratoRoto) as error:
        cargar_candidatos(directorio)
    assert "n_supervivientes" in str(error.value)


def test_el_resumen_nombra_las_exclusiones_y_su_peso():
    texto = resumen_corrida(CORRIDA)
    assert "502" in texto
    assert "425" in texto
    assert "pilar_sin_datos" in texto


def test_el_resumen_sin_corrida_lo_dice_en_vez_de_callarlo():
    texto = resumen_corrida(None)
    assert "sin contexto" in texto.lower()
```

- [ ] **Step 2: Ejecuta los tests para verificar que fallan**

Run: `pytest tests/test_aprobacion_carga.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'aprobacion'`

- [ ] **Step 3: Escribe la implementación**

`aprobacion/__init__.py`: fichero vacío.

`aprobacion/carga.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

SALIDAS = Path("salidas")

_CAMPOS_FICHA = frozenset(
    {
        "ticker",
        "sector_gics",
        "puesto",
        "compuesto",
        "pilares",
        "destacados",
        "flojos",
        "cobertura",
        "desplazo_a",
        "generada_por",
        "narrativa",
    }
)

_CAMPOS_CORRIDA = frozenset(
    {
        "fecha",
        "universo",
        "n_panel",
        "n_supervivientes",
        "exclusiones",
        "tope_por_sector",
        "tamano_top",
        "con_llm",
    }
)

_COMO_GENERARLO = (
    "Falta salidas/fichas.json. Generalo con:\n\n"
    '    python -c "from ranking.run import construir_ranking, guardar; '
    "guardar(construir_ranking(con_llm=False), 'salidas')\""
)


class FaltanFichas(FileNotFoundError):
    """No hay nada que revisar todavia."""


class ContratoRoto(ValueError):
    """Hay un fichero, pero no tiene la forma que este modulo espera."""


@dataclass(frozen=True)
class Candidatos:
    """What sub-project B left on disk, validated.

    `corrida` is None when corrida.json is absent, which is not an error: the
    outputs committed to this repo predate that file. A corrida.json that is
    present but malformed is a different thing and raises — absent means "an
    older B wrote this", malformed means something went wrong and hiding it
    would be the silent failure this package exists to avoid.
    """

    fichas: list[dict]
    corrida: dict | None


def _leer_json(fichero: Path) -> object:
    try:
        return json.loads(fichero.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContratoRoto(f"{fichero.name} no es JSON valido: {error}") from error


def _validar_fichas(crudo: object) -> list[dict]:
    if not isinstance(crudo, list):
        raise ContratoRoto("fichas.json no contiene una lista")
    for posicion, ficha in enumerate(crudo):
        if not isinstance(ficha, dict):
            raise ContratoRoto(f"la ficha en la posicion {posicion} no es un objeto")
        faltan = _CAMPOS_FICHA - set(ficha)
        if faltan:
            raise ContratoRoto(
                f"a la ficha en la posicion {posicion} le faltan campos: "
                f"{', '.join(sorted(faltan))}"
            )
    return crudo


def _validar_corrida(crudo: object) -> dict:
    if not isinstance(crudo, dict):
        raise ContratoRoto("corrida.json no contiene un objeto")
    faltan = _CAMPOS_CORRIDA - set(crudo)
    if faltan:
        raise ContratoRoto(
            f"a corrida.json le faltan campos: {', '.join(sorted(faltan))}"
        )
    return crudo


def cargar_candidatos(directorio: Path | None = None) -> Candidatos:
    """Read and validate what sub-project B wrote.

    Every failure names the field or the file that is wrong. A half-rendered
    ficha is worse than no page at all: the reviewer would be approving on
    incomplete information without knowing it.
    """
    directorio = Path(directorio or SALIDAS)
    fichero_fichas = directorio / "fichas.json"
    if not fichero_fichas.exists():
        raise FaltanFichas(_COMO_GENERARLO)

    fichas = _validar_fichas(_leer_json(fichero_fichas))

    fichero_corrida = directorio / "corrida.json"
    corrida = (
        _validar_corrida(_leer_json(fichero_corrida))
        if fichero_corrida.exists()
        else None
    )
    return Candidatos(fichas=fichas, corrida=corrida)


def resumen_corrida(corrida: dict | None) -> str:
    """One sentence putting the shortlist in the context of what was dropped.

    This is the whole reason B writes corrida.json. The sector tilt the guards
    produce is documented in a design file nobody reads while deciding; putting
    it in front of the reviewer at the moment of decision is what turns a
    documented bias into one that was actually taken into account.
    """
    if corrida is None:
        return (
            "Sin contexto de corrida: este ranking se genero antes de que se "
            "registraran sus metadatos, asi que no se sabe a cuantas empresas "
            "dejaron fuera las guardas."
        )

    excluidas = corrida["n_panel"] - corrida["n_supervivientes"]
    por_motivo = ", ".join(
        f"{motivo} ({cuantas})"
        for motivo, cuantas in sorted(
            corrida["exclusiones"].items(), key=lambda par: -par[1]
        )
    )
    return (
        f"Estos candidatos salen de {corrida['n_panel']} empresas con datos, de "
        f"las que sobrevivieron {corrida['n_supervivientes']} a las guardas. "
        f"Quedaron excluidas {excluidas}: {por_motivo}."
    )
```

- [ ] **Step 4: Ejecuta los tests**

Run: `pytest tests/test_aprobacion_carga.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Bite-check**

Rompe a propósito y comprueba que falla, uno a uno:

- Quita la comprobación `faltan` de `_validar_fichas` → debe fallar el test del campo que falta.
- Haz que `corrida.json` ausente lance en vez de devolver `None` → debe fallar el test de revisar sin corrida.
- Haz que `_validar_corrida` devuelva el crudo sin comprobar campos → debe fallar el test de la corrida rota.
- Quita el `try/except` de `_leer_json` → debe fallar el test del fichero truncado.

Reporta la salida literal.

- [ ] **Step 6: Commit**

```bash
git add aprobacion/__init__.py aprobacion/carga.py tests/test_aprobacion_carga.py
git commit -m "feat: cargar y validar las salidas de B para la revision"
```

---

### Task 3: Construir el acta

**Files:**
- Create: `aprobacion/acta.py`
- Test: `tests/test_aprobacion_acta.py`

- [ ] **Step 1: Escribe los tests que fallan**

`tests/test_aprobacion_acta.py`:

```python
import pytest

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
)
from aprobacion.carga import Candidatos
from tests.test_aprobacion_carga import CORRIDA, FICHA


def candidatos(*tickers: str) -> Candidatos:
    fichas = [
        {**FICHA, "ticker": ticker, "puesto": posicion}
        for posicion, ticker in enumerate(tickers or ("AAA",), start=1)
    ]
    return Candidatos(fichas=fichas, corrida=CORRIDA)


def test_los_aprobados_llevan_su_ficha_y_su_puesto():
    acta = construir_acta(candidatos("AAA", "BBB"), aprobados={"AAA"})
    assert len(acta["aprobados"]) == 1
    entrada = acta["aprobados"][0]
    assert entrada["ticker"] == "AAA"
    assert entrada["origen"] == "ranking"
    assert entrada["puesto"] == 1
    assert entrada["ficha"]["sector_gics"] == "Information Technology"


def test_los_no_aprobados_tambien_llevan_su_ficha():
    # "Por que no tengo X" es tan buena pregunta como la contraria, y si con el
    # tiempo se descarta lo que el score pone arriba, eso dice algo del criterio.
    acta = construir_acta(candidatos("AAA", "BBB"), aprobados={"AAA"})
    assert [e["ticker"] for e in acta["no_aprobados"]] == ["BBB"]
    assert acta["no_aprobados"][0]["ficha"]["ticker"] == "BBB"


def test_el_anadido_a_mano_se_marca_y_no_finge_tener_ficha():
    acta = construir_acta(
        candidatos("AAA"),
        aprobados={"AAA"},
        anadidos=[Anadido(ticker="JPM", motivo="el criterio no evalua bancos")],
    )
    manual = [e for e in acta["aprobados"] if e["origen"] == "manual"][0]
    assert manual["ticker"] == "JPM"
    assert manual["ficha"] is None
    assert manual["puesto"] is None
    assert manual["motivo"] == "el criterio no evalua bancos"


def test_sin_motivo_no_hay_anadido_a_mano():
    # Un ticker sin ranking no tiene ningun respaldo cuantitativo: la razon
    # humana es la unica justificacion que va a existir.
    with pytest.raises(MotivoRequerido):
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="JPM", motivo="   ")])


def test_un_anadido_que_ya_esta_en_el_ranking_se_rechaza():
    # Deduplicar en silencio haria desaparecer el motivo escrito sin avisar.
    with pytest.raises(TickerDuplicado) as error:
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="AAA", motivo="da igual")])
    assert "AAA" in str(error.value)


def test_un_ticker_con_forma_imposible_se_rechaza():
    with pytest.raises(TickerInvalido):
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       anadidos=[Anadido(ticker="no es un ticker", motivo="x")])


def test_el_ticker_anadido_se_normaliza_a_mayusculas():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          anadidos=[Anadido(ticker=" brk-b ", motivo="x")])
    assert [e["ticker"] for e in acta["aprobados"]] == ["AAA", "BRK-B"]


def test_aprobar_una_lista_vacia_no_significa_nada():
    with pytest.raises(NadaQueAprobar):
        construir_acta(candidatos("AAA"), aprobados=set())


def test_el_motivo_distingue_un_descarte_de_un_no_mirado():
    # Las casillas nacen desmarcadas, asi que no marcar puede querer decir dos
    # cosas. El motivo escrito es lo unico que las separa.
    acta = construir_acta(
        candidatos("AAA", "BBB", "CCC"),
        aprobados={"AAA"},
        motivos={"BBB": "concentracion de clientes"},
    )
    por_ticker = {e["ticker"]: e for e in acta["no_aprobados"]}
    assert por_ticker["BBB"]["motivo"] == "concentracion de clientes"
    assert por_ticker["CCC"]["motivo"] is None


def test_el_acta_copia_la_corrida_entera():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    assert acta["corrida"] == CORRIDA


def test_el_acta_lleva_fecha_en_iso():
    from datetime import datetime

    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          ahora=datetime(2026, 8, 15, 18, 42))
    assert acta["fecha"] == "2026-08-15T18:42:00"
```

- [ ] **Step 2: Ejecuta los tests para verificar que fallan**

Run: `pytest tests/test_aprobacion_acta.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'aprobacion.acta'`

- [ ] **Step 3: Escribe la implementación**

`aprobacion/acta.py`:

```python
import re
from dataclasses import dataclass
from datetime import datetime

from aprobacion.carga import Candidatos

# Letras y guion, en mayusculas: la forma que usan los tickers del universo
# real (503 nombres, de los que solo BF-B y BRK-B no son alfabeticos puros).
_FORMA_TICKER = re.compile(r"^[A-Z]+(-[A-Z]+)*$")


class MotivoRequerido(ValueError):
    """Un anadido a mano sin razon escrita."""


class TickerDuplicado(ValueError):
    """Se anadio a mano algo que el ranking ya proponia."""


class TickerInvalido(ValueError):
    """El texto no tiene forma de ticker."""


class NadaQueAprobar(ValueError):
    """Un acta sin ningun aprobado no significa nada."""


@dataclass(frozen=True)
class Anadido:
    """A company the reviewer put in by hand, with the reason it went in."""

    ticker: str
    motivo: str


def _normalizar(ticker: str) -> str:
    limpio = ticker.strip().upper()
    if not _FORMA_TICKER.match(limpio):
        raise TickerInvalido(f"{ticker!r} no tiene forma de ticker")
    return limpio


def construir_acta(
    candidatos: Candidatos,
    aprobados: set[str],
    anadidos: list[Anadido] | None = None,
    motivos: dict[str, str] | None = None,
    ahora: datetime | None = None,
) -> dict:
    """Build the dated record of one approval.

    The fichas travel copied inside, not referenced: salidas/fichas.json is
    overwritten on every run of sub-project B, so a reference would rot. That
    copy is the entire point of the artifact.

    The second list is `no_aprobados`, not `rechazados`. Checkboxes start
    unticked, so leaving one unticked can mean two very different things — it
    was considered and dropped, or it was never looked at. Calling it a
    rejection would assert a judgment that may never have happened. `motivo`
    is what separates the two: written means deliberate, absent means only
    that it did not go in.
    """
    anadidos = anadidos or []
    motivos = motivos or {}
    ahora = ahora or datetime.now()

    por_ticker = {ficha["ticker"]: ficha for ficha in candidatos.fichas}

    manuales = []
    for anadido in anadidos:
        if not anadido.motivo.strip():
            raise MotivoRequerido(
                f"{anadido.ticker}: un ticker que entra sin ranking necesita "
                "una razon escrita, porque es la unica justificacion que va a "
                "existir"
            )
        ticker = _normalizar(anadido.ticker)
        if ticker in por_ticker:
            raise TickerDuplicado(
                f"{ticker} ya esta en el ranking: aprobalo con su casilla en "
                "vez de anadirlo a mano"
            )
        manuales.append(
            {
                "ticker": ticker,
                "origen": "manual",
                "puesto": None,
                "ficha": None,
                "motivo": anadido.motivo.strip(),
            }
        )

    if not aprobados and not manuales:
        raise NadaQueAprobar("no hay ningun candidato aprobado")

    del_ranking = [
        {
            "ticker": ficha["ticker"],
            "origen": "ranking",
            "puesto": ficha["puesto"],
            "ficha": ficha,
        }
        for ficha in candidatos.fichas
        if ficha["ticker"] in aprobados
    ]

    no_aprobados = [
        {
            "ticker": ficha["ticker"],
            "puesto": ficha["puesto"],
            "ficha": ficha,
            "motivo": motivos.get(ficha["ticker"]),
        }
        for ficha in candidatos.fichas
        if ficha["ticker"] not in aprobados
    ]

    return {
        "fecha": ahora.isoformat(timespec="seconds"),
        "corrida": candidatos.corrida,
        "aprobados": del_ranking + manuales,
        "no_aprobados": no_aprobados,
    }


def tickers_aprobados(acta: dict) -> list[str]:
    """The list the optimizer needs, in the order the act records it."""
    return [entrada["ticker"] for entrada in acta["aprobados"]]
```

- [ ] **Step 4: Ejecuta los tests**

Run: `pytest tests/test_aprobacion_acta.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Bite-check**

Uno a uno, con salida literal:

- Quita la comprobación de `motivo.strip()` → debe fallar el test del motivo requerido.
- Quita la comprobación `ticker in por_ticker` → debe fallar el del duplicado.
- Haz que `no_aprobados` no lleve `ficha` → debe fallar el test correspondiente.
- Quita la guarda de `NadaQueAprobar` → debe fallar su test.
- Haz que `_normalizar` devuelva el texto sin comprobar la forma → debe fallar el del ticker imposible.

- [ ] **Step 6: Commit**

```bash
git add aprobacion/acta.py tests/test_aprobacion_acta.py
git commit -m "feat: construir el acta de aprobacion con sus fichas dentro"
```

---

### Task 4: Escribir el acta en disco

**Files:**
- Modify: `aprobacion/acta.py`
- Test: `tests/test_aprobacion_acta.py`

- [ ] **Step 1: Escribe los tests que fallan**

Añade a `tests/test_aprobacion_acta.py`:

```python
import json
from datetime import datetime
from pathlib import Path

from aprobacion.acta import guardar_acta, tickers_aprobados


def test_el_acta_se_escribe_con_su_fecha_en_el_nombre(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          ahora=datetime(2026, 8, 15, 18, 42))
    destino = guardar_acta(acta, tmp_path)
    assert destino.name == "2026-08-15-1842.json"
    assert json.loads(destino.read_text(encoding="utf-8"))["fecha"] == acta["fecha"]


def test_el_acta_sobrevive_a_que_B_se_vuelva_a_correr(tmp_path: Path):
    # La promesa entera del artefacto. Si esto no muerde, el resto es decorado.
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    destino = guardar_acta(acta, tmp_path)

    # B se corre otra vez y deja unas fichas completamente distintas.
    fichas_nuevas = [{**FICHA, "ticker": "ZZZ", "compuesto": -9.9}]
    (tmp_path / "fichas.json").write_text(
        json.dumps(fichas_nuevas), encoding="utf-8"
    )

    guardada = json.loads(destino.read_text(encoding="utf-8"))
    assert guardada["aprobados"][0]["ticker"] == "AAA"
    assert guardada["aprobados"][0]["ficha"]["compuesto"] == 1.42


def test_el_acta_es_json_estricto(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    acta["aprobados"][0]["ficha"]["compuesto"] = float("nan")
    with pytest.raises(ValueError):
        guardar_acta(acta, tmp_path)


def test_no_deja_temporales_a_medias(tmp_path: Path):
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"})
    guardar_acta(acta, tmp_path)
    assert [p.suffix for p in tmp_path.iterdir()] == [".json"]


def test_dos_actas_seguidas_no_se_pisan(tmp_path: Path):
    primera = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       ahora=datetime(2026, 8, 15, 18, 42)), tmp_path)
    segunda = guardar_acta(
        construir_acta(candidatos("AAA"), aprobados={"AAA"},
                       ahora=datetime(2026, 8, 15, 19, 10)), tmp_path)
    assert primera != segunda
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_los_tickers_aprobados_incluyen_los_anadidos_a_mano():
    acta = construir_acta(candidatos("AAA"), aprobados={"AAA"},
                          anadidos=[Anadido(ticker="JPM", motivo="x")])
    assert tickers_aprobados(acta) == ["AAA", "JPM"]
```

- [ ] **Step 2: Ejecuta los tests para verificar que fallan**

Run: `pytest tests/test_aprobacion_acta.py -q`
Expected: FAIL con `ImportError: cannot import name 'guardar_acta'`

- [ ] **Step 3: Escribe la implementación**

Añade a `aprobacion/acta.py` (con `import json` y `from pathlib import Path` arriba):

```python
ACTAS = Path("actas")


def guardar_acta(acta: dict, directorio: Path | None = None) -> Path:
    """Write the act atomically and return where it landed.

    One file per approval, named by timestamp, rather than one growing file:
    same reason fundamentals caches one file per ticker — a run killed
    mid-write cannot corrupt the whole history.

    allow_nan=False for the same reason fichas.json uses it: json.dumps writes
    a NaN as the bare literal `NaN`, which no strict parser accepts. An act
    that cannot be read back is not a record.
    """
    directorio = Path(directorio or ACTAS)
    directorio.mkdir(parents=True, exist_ok=True)

    momento = datetime.fromisoformat(acta["fecha"]).strftime("%Y-%m-%d-%H%M")
    fichero = directorio / f"{momento}.json"

    texto = json.dumps(acta, ensure_ascii=False, indent=2, allow_nan=False)
    tmp = fichero.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(fichero)
    return fichero
```

- [ ] **Step 4: Ejecuta los tests**

Run: `pytest tests/test_aprobacion_acta.py -q`
Expected: PASS, 17 passed

- [ ] **Step 5: Bite-check**

- Quita `allow_nan=False` → debe fallar el test de JSON estricto.
- Escribe directamente a `fichero` sin el temporal, y comprueba qué test lo nota. **Si ninguno lo nota, dilo en el reporte**: la escritura atómica no se puede observar sin concurrencia, y es mejor saberlo que fingir que hay cobertura.
- Haz que el nombre del fichero sea fijo → debe fallar el test de dos actas seguidas.

- [ ] **Step 6: Commit**

```bash
git add aprobacion/acta.py tests/test_aprobacion_acta.py
git commit -m "feat: escribir el acta fechada de forma atomica"
```

---

### Task 5: La página de revisión

**Files:**
- Create: `pages/1_Revisar_candidatos.py`
- Modify: `app.py`

**Esta tarea no tiene test automático.** Es aceptable porque toda la lógica está en `aprobacion/`, ya cubierta. Si algún paso te lleva a poner una condición de negocio aquí, **muévela al paquete y escríbele un test**.

- [ ] **Step 1: Escribe la página**

`pages/1_Revisar_candidatos.py`:

```python
import streamlit as st

from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
    guardar_acta,
    tickers_aprobados,
)
from aprobacion.carga import ContratoRoto, FaltanFichas, cargar_candidatos, resumen_corrida

st.set_page_config(page_title="Revisar candidatos", page_icon="✅", layout="wide")
st.title("✅ Revisar candidatos")

try:
    candidatos = cargar_candidatos()
except FaltanFichas as error:
    st.warning(str(error))
    st.stop()
except ContratoRoto as error:
    st.error(f"Las salidas de B no tienen la forma esperada: {error}")
    st.stop()

st.info(resumen_corrida(candidatos.corrida))
st.caption(
    "El orden lo decide un score determinista que **no esta validado "
    "empiricamente**: es un criterio de seleccion transparente, no una "
    "prevision de rentabilidad."
)

if "anadidos" not in st.session_state:
    st.session_state.anadidos = []

aprobados: set[str] = set()
motivos: dict[str, str] = {}

for ficha in candidatos.fichas:
    ticker = ficha["ticker"]
    columna_casilla, columna_titulo = st.columns([1, 11])
    with columna_casilla:
        # Nace desmarcada a proposito: si llegara marcada, aprobar los quince
        # seria un clic y el gate pasaria a ser decorado.
        marcada = st.checkbox("Aprobar", key=f"ok_{ticker}", label_visibility="collapsed")
    with columna_titulo:
        st.markdown(
            f"**{ficha['puesto']}. {ticker}** — {ficha['sector_gics']} · "
            f"compuesto {ficha['compuesto']:+.2f} (z dentro del sector)"
        )
    if marcada:
        aprobados.add(ticker)

    with st.expander(f"Ficha de {ticker}"):
        pilares = " · ".join(
            f"{pilar} {valor:+.2f}" if valor is not None else f"{pilar} n/d"
            for pilar, valor in ficha["pilares"].items()
        )
        st.markdown(f"Pilares (z frente a todo el universo): {pilares}")
        st.markdown(
            "- Fuerte en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["destacados"])
        )
        st.markdown(
            "- Flojo en: "
            + ", ".join(f"{i['kpi']} ({i['z']:+.2f})" for i in ficha["flojos"])
        )
        st.markdown(f"- Cobertura: {ficha['cobertura']['kpis_con_dato']} de 17 KPIs")
        if ficha["desplazo_a"]:
            st.markdown(
                "- Dejo fuera por el tope sectorial: "
                + ", ".join(ficha["desplazo_a"])
            )

        narrativa = ficha["narrativa"]
        if narrativa is None:
            st.markdown("_Ficha de plantilla: sin narrativa generada._")
        else:
            st.markdown(narrativa["tesis"])
            for riesgo in narrativa["riesgos"]:
                if riesgo["verificada"]:
                    st.markdown(f"- {riesgo['afirmacion']}")
                else:
                    # Si el revisor puede leer la ficha entera sin enterarse de
                    # que una cita es inventada, este sub-proyecto ha fallado.
                    st.markdown(f"- {riesgo['afirmacion']}")
                    st.error("Cita SIN VERIFICAR: no aparece en el documento original")
                st.markdown(f"> {' '.join(riesgo['cita'].split())}")
            fuente = narrativa.get("fuente")
            if fuente:
                recorte = " (recortado)" if fuente["recortado"] else ""
                st.caption(
                    f"Fuente: {fuente['formulario']} de {fuente['fecha']}, "
                    f"{fuente['seccion']}, accession {fuente['accession']}{recorte}"
                )
            else:
                st.warning("Procedencia no disponible: la cita no se puede localizar")

        motivo = st.text_input(
            "Motivo si lo descartas (opcional)", key=f"motivo_{ticker}"
        )
        if motivo.strip() and not marcada:
            motivos[ticker] = motivo.strip()

st.divider()
st.subheader("Anadir una empresa a mano")
st.caption(
    "Para recuperar a una empresa que las guardas excluyeron por como reporta "
    "y no por su calidad. El motivo es obligatorio: sin ranking detras, es la "
    "unica justificacion que va a existir."
)

columna_ticker, columna_motivo, columna_boton = st.columns([1, 3, 1])
nuevo_ticker = columna_ticker.text_input("Ticker", key="nuevo_ticker")
nuevo_motivo = columna_motivo.text_input("Motivo", key="nuevo_motivo")
if columna_boton.button("Anadir", disabled=not (nuevo_ticker and nuevo_motivo.strip())):
    st.session_state.anadidos.append(
        Anadido(ticker=nuevo_ticker, motivo=nuevo_motivo)
    )
    st.rerun()

if st.session_state.anadidos:
    for anadido in st.session_state.anadidos:
        st.markdown(f"- **{anadido.ticker.strip().upper()}** — {anadido.motivo}")
    # No se comprueba aqui si el ticker existe o tiene precio: llamar a yfinance
    # desde el gate lo ataria a la red y a un servicio externo, y es justo lo
    # que permite probar todo este paquete sin nada montado. El optimizador ya
    # falla de forma visible si un ticker no tiene datos.
    st.caption(
        "Solo se comprueba la forma del ticker. Si no existe o no tiene precio, "
        "el fallo aparecera en el optimizador, no aqui."
    )

st.divider()
total = len(aprobados) + len(st.session_state.anadidos)
if st.button(f"Aprobar {total} empresas y pasar al optimizador", disabled=total == 0,
             type="primary"):
    try:
        acta = construir_acta(
            candidatos,
            aprobados=aprobados,
            anadidos=st.session_state.anadidos,
            motivos=motivos,
        )
        # El acta se escribe ANTES del traspaso: el peor resultado posible seria
        # aprobar, perder el registro y seguir adelante creyendo que quedo
        # constancia.
        destino = guardar_acta(acta)
    except (MotivoRequerido, TickerDuplicado, TickerInvalido, NadaQueAprobar) as error:
        st.error(str(error))
    except OSError as error:
        st.error(f"No se pudo escribir el acta, no se aprueba nada: {error}")
    else:
        st.session_state.tickers_aprobados = tickers_aprobados(acta)
        st.success(
            f"Acta escrita en {destino}. Ya puedes pasar a la pagina del "
            "optimizador: los tickers estan puestos."
        )
```

- [ ] **Step 2: Cambia `app.py`**

Justo antes del bloque de configuración (busca `raw_tickers = st.text_input`), añade la constante:

```python
TICKERS_POR_DEFECTO = "AAPL, MSFT, GOOGL, AMZN, NVDA"
```

Y sustituye el `value=` del campo:

```python
        raw_tickers = st.text_input(
            "Tickers (separados por coma o espacio)",
            value=", ".join(
                st.session_state.get("tickers_aprobados", [])
            ) or TICKERS_POR_DEFECTO,
        )
```

- [ ] **Step 3: Comprueba que la suite sigue verde**

Run: `pytest tests/ -q -m "not red"`
Expected: PASS. `app.py` no tiene tests, pero un error de sintaxis lo cazaria cualquier import.

- [ ] **Step 4: Arranca la app y recorre el flujo**

Run: `streamlit run app.py`

Comprueba, y **reporta lo que veas, no lo que esperes**:

1. La página "Revisar candidatos" aparece en la barra lateral.
2. El resumen de arriba dice cuántas empresas se excluyeron. Con el `salidas/` actual **no habrá `corrida.json`** hasta que se regenere, así que debe salir el aviso de "sin contexto de corrida" en vez de un error.
3. Las quince casillas nacen desmarcadas.
4. El botón de aprobar está deshabilitado hasta marcar algo.
5. Aprobar escribe un fichero en `actas/` y rellena el campo de tickers de la página del optimizador.
6. Añadir un ticker sin motivo no hace nada; con motivo, aparece en la lista.

- [ ] **Step 5: Commit**

```bash
git add pages/1_Revisar_candidatos.py app.py
git commit -m "feat: pagina de revision y traspaso al optimizador"
```

---

### Task 6: Regenerar salidas, ignorar temporales y documentar

**Files:**
- Modify: `.gitignore`, `CONTEXTO.md`

- [ ] **Step 1: Regenera `salidas/` para que tenga `corrida.json`**

```bash
python -c "from ranking.run import construir_ranking, guardar; guardar(construir_ranking(con_llm=False), 'salidas')"
```

Comprueba que `salidas/corrida.json` existe y que sus números coinciden con los de la enmienda 3 del diseño de B: 502 en el panel, 425 supervivientes, 72 `pilar_sin_datos`.

- [ ] **Step 2: Decide qué se versiona**

Las actas son el registro de decisiones de inversión y **no se regeneran**. Añade a `.gitignore` sólo los temporales:

```
actas/*.tmp
```

Deja las actas versionadas: son pequeñas (~25 KB) y su valor es histórico.

- [ ] **Step 3: Actualiza `CONTEXTO.md`**

En la tabla de sub-proyectos, marca C como terminado. Sustituye la sección "Lo siguiente: sub-proyecto C" por un "Resultado del sub-proyecto C" que diga: dónde vive la página, que el acta guarda las fichas copiadas porque `fichas.json` se sobrescribe, que el motivo es obligatorio al añadir a mano, y que el traspaso al optimizador va por `st.session_state`. Actualiza la cuenta de tests.

Añade el comando al bloque correspondiente:

```bash
streamlit run app.py     # la app: optimizador + pagina de revision
```

- [ ] **Step 4: Ejecuta la suite completa**

Run: `pytest tests/ -q -m "not red"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .gitignore CONTEXTO.md salidas/
git commit -m "docs: sub-proyecto C terminado"
```

---

## Comprobación final

- [ ] `pytest tests/ -q -m "not red"` en verde
- [ ] `ranking/criterio.py` sigue sin modificarse desde `b95fcc1`
- [ ] Un acta escrita a mano sobrevive a regenerar `salidas/`
- [ ] La página no revienta cuando falta `corrida.json`
- [ ] Aprobar con `actas/` sin permiso de escritura **no** deja tickers en la sesión
