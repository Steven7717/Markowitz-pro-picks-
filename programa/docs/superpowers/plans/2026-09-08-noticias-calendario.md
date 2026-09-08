# Noticias y calendario — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pantalla que muestre qué ha pasado con los activos del libro
(hechos de la SEC y prensa, separados) y qué viene (resultados, dividendos y
punteros a las fuentes macro oficiales), sin interpretar nada.

**Architecture:** Paquete `noticias/` con la lógica y sin Streamlit;
`vistas/noticias.py` con los widgets y sin lógica. Misma separación que F y G.
La lista de tipos 8-K materiales va congelada en su propio commit, antes de
mirar los expedientes de ninguna cartera real.

**Tech Stack:** Python 3.12, yfinance 1.6.0, edgartools 5.52, Streamlit, pytest.
Ninguna dependencia nueva.

---

## Antes de empezar: dos cosas que cuestan una tarea si se ignoran

**1. `UV_LINK_MODE=copy` es obligatorio en TODOS los comandos.** El repo vive en
OneDrive y `uv` no puede hacer enlaces duros ahí. Sin la variable, instalar
`pyarrow` revienta con `os error 396`.

```bash
UV_LINK_MODE=copy uv run pytest tests/ -q
```

**2. Las formas de las APIs ya están sondeadas contra la red. No las adivines.**
Se comprobaron el 2026-09-08 y son éstas:

```python
# yfinance -- .news
noticia = yf.Ticker("AAPL").news[0]          # {"id": str, "content": {...}}
c = noticia["content"]
c["title"]                    # str
c["summary"]                  # str -- ESTE es el resumen
c["description"]              # str en HTML CRUDO -- NO USAR
c["pubDate"]                  # "2026-09-08T15:29:15Z"
c["displayTime"]              # puede venir "" -- NO USAR como fecha
c["contentType"]              # "ARTICLE" | "VIDEO"
c["provider"]["displayName"]  # dict, no cadena
c["canonicalUrl"]["url"]      # dict, no cadena

# yfinance -- .calendar  (dict)
{'Dividend Date': date(2026, 8, 12), 'Ex-Dividend Date': date(2026, 8, 9),
 'Earnings Date': [date(2026, 10, 29)],          # LISTA, aunque tenga uno
 'Earnings High': 2.07, 'Earnings Low': 1.93, 'Earnings Average': 1.98124,
 'Revenue High': ..., 'Revenue Low': ..., 'Revenue Average': ...}

# edgartools -- expedientes
df = edgar.Company("AAPL").get_filings(
    form="8-K", filing_date=("2025-01-01", "2026-09-08")
).to_pandas()
# columnas: accession_number, filing_date, reportDate, acceptanceDateTime,
#           act, form, fileNumber, items, size, isXBRL, isInlineXBRL,
#           primaryDocument, primaryDocDescription
# df["items"]  ->  "2.02,9.01"   CADENA CON COMAS, varios items por expediente
# df["form"]   ->  "8-K" o "8-K/A"  (get_filings(form="8-K") trae las enmiendas)
```

**La suite normal no toca la red.** Los tests usan los literales de arriba como
fixtures. Los que llaman a las fuentes vivas van marcados `red` y quedan fuera
de `-m "not red"`.

---

## Task 1: El criterio, congelado

Va **primero y solo en su commit**, antes de que nada mire expedientes reales.
La fecha del commit es la prueba de que la lista no se armó a la vista de lo que
había salido. Mismo estándar que `rebalanceo/criterio.py` y `ranking/criterio.py`.

**Files:**
- Create: `noticias/__init__.py` (vacío)
- Create: `noticias/criterio.py`
- Test: `tests/test_noticias_criterio.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_criterio.py"""
import pytest

from noticias import criterio


def test_un_tipo_material_es_material():
    assert criterio.material(("4.02",)) is True


def test_un_tipo_de_rutina_no_es_material():
    assert criterio.material(("8.01",)) is False


def test_varios_items_y_uno_material_basta():
    """El caso mas frecuente que existe, y el que rompe todo si se modela mal.

    Un anuncio de resultados llega SIEMPRE como "2.02,9.01": el 2.02 son los
    resultados y el 9.01 los estados y anexos que los acompanan. Si la
    materialidad exigiera que TODOS los tipos estuvieran en la lista, o si se
    comparase la cadena entera contra la lista, cada anuncio de resultados
    quedaria plegado entre la rutina.
    """
    assert criterio.material(("2.02", "9.01")) is True


def test_varios_items_y_ninguno_material():
    """Contrapeso del anterior: que no pase por 'dos items = material'."""
    assert criterio.material(("7.01", "9.01")) is False


def test_sin_items_no_es_material():
    assert criterio.material(()) is False


def test_hay_descripcion_para_cada_tipo_material():
    """Un tipo material sin texto saldria destacado y mudo en la pantalla."""
    faltan = criterio.MATERIALES - set(criterio.DESCRIPCIONES)
    assert faltan == set(), f"sin descripcion: {sorted(faltan)}"


def test_el_402_esta_en_la_lista():
    """El peor hecho posible para una cartera fundamental.

    Se fija aparte porque es el que justifica el criterio entero: la empresa
    declarando que sus propias cuentas anteriores no son fiables.
    """
    assert "4.02" in criterio.MATERIALES


@pytest.mark.parametrize("tipo", ["7.01", "8.01", "9.01"])
def test_la_rutina_queda_fuera(tipo):
    assert tipo not in criterio.MATERIALES
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_criterio.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'noticias'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/criterio.py"""
"""Que tipos de 8-K salen destacados, y por que esos.

**Este fichero esta congelado.** Vive aparte del codigo que lo usa por la misma
razon que `rebalanceo/criterio.py` y `ranking/criterio.py`: la fecha del commit
que lo introduce es la prueba de que la lista no se armo a la vista de los
expedientes de ninguna cartera real.

La regla que genera la lista, y que hay que poder defender sin ver datos: **son
materiales los tipos que invalidan o alteran los numeros sobre los que se
construyo la tesis.** La cartera sale de un analisis fundamental (sub-proyectos
A y B), asi que lo grave es lo que mueve esos fundamentales o dice que estaban
mal. Nada de esto es una apuesta sobre el precio: es una apuesta sobre si las
cifras que se analizaron siguen siendo las cifras.

**Destacar no es excluir.** Lo que no esta aqui se pliega, no se descarta. Si
se descartara, el sub-proyecto I nunca lo veria.
"""

DESCRIPCIONES = {
    "4.02": "Cuentas anteriores no fiables",
    "4.01": "Cambio de auditor",
    "1.03": "Concurso o quiebra",
    "3.01": "Aviso de exclusion de cotizacion",
    "2.06": "Deterioros materiales",
    "2.02": "Resultados",
    "2.01": "Adquisicion o venta de activos",
    "5.01": "Cambio de control",
    "5.02": "Salidas o nombramientos en la directiva",
    "1.01": "Acuerdo material",
    "1.05": "Incidente material de ciberseguridad",
    # Los de rutina tambien llevan texto: se pliegan, pero se muestran, y un
    # codigo desnudo no le dice nada a nadie.
    "7.01": "Divulgacion Regulation FD",
    "8.01": "Otros eventos",
    "9.01": "Estados financieros y anexos",
    "5.07": "Votacion de accionistas",
    "5.03": "Cambio de estatutos",
    "2.03": "Nueva obligacion financiera",
    "3.02": "Venta de acciones no registrada",
}

MATERIALES = frozenset({
    "4.02", "4.01", "1.03", "3.01", "2.06",
    "2.02", "2.01", "5.01", "5.02", "1.01", "1.05",
})


def material(tipos: "tuple[str, ...]") -> bool:
    """Whether any of the filing's items is one that matters.

    **Basta uno.** Un expediente comunica varias cosas a la vez y el indice de
    la SEC las devuelve juntas: un anuncio de resultados es "2.02,9.01", donde
    el 9.01 son los anexos. Exigir que todos fueran materiales, o comparar la
    cadena entera contra la lista, dejaria plegado el caso mas frecuente que
    existe.
    """
    return any(tipo in MATERIALES for tipo in tipos)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_criterio.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Sabotea la guarda y comprueba que algún test cae**

Cambia `any(` por `all(` en `material`. Corre los tests.
Expected: cae `test_varios_items_y_uno_material_basta`.

Si **no** cae ninguno, no rehagas el sabotaje: averigua qué otra cosa está
devolviendo la respuesta correcta, y arregla eso. Deshaz el cambio después.

- [ ] **Step 6: Commit, solo**

```bash
git add noticias/__init__.py noticias/criterio.py tests/test_noticias_criterio.py
git commit -m "docs: congelar los tipos de 8-K materiales antes de mirar ninguno"
```

---

## Task 2: La prensa

**Files:**
- Create: `noticias/prensa.py`
- Test: `tests/test_noticias_prensa.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_prensa.py"""
from datetime import datetime, timezone

from noticias import prensa

# Copiado de la forma real de yfinance 1.6.0, sondeada el 2026-09-08.
CRUDO = {
    "id": "abc-123",
    "content": {
        "title": "Apple sube tras presentar el iPhone",
        "summary": "La accion subio un 2% en la sesion.",
        "description": '<p>La accion <a href="http://x">subio</a> un 2%.</p>',
        "pubDate": "2026-09-08T15:29:15Z",
        "displayTime": "",
        "contentType": "ARTICLE",
        "provider": {"displayName": "Reuters", "url": "http://r.com"},
        "canonicalUrl": {"url": "https://finance.yahoo.com/n/1", "site": "finance"},
    },
}


def test_extrae_los_campos():
    n = prensa.desde_crudo("AAPL", CRUDO)
    assert n.ticker == "AAPL"
    assert n.titular == "Apple sube tras presentar el iPhone"
    assert n.resumen == "La accion subio un 2% en la sesion."
    assert n.medio == "Reuters"
    assert n.url == "https://finance.yahoo.com/n/1"
    assert n.clase == "ARTICLE"
    assert n.cuando == datetime(2026, 9, 8, 15, 29, 15, tzinfo=timezone.utc)


def test_el_resumen_nunca_sale_de_description():
    """`description` viene en HTML crudo y volcarlo pintaria etiquetas.

    Se fija con `summary` vacio, que es cuando la tentacion de caer a
    `description` existe: el resultado correcto es cadena vacia, no HTML.
    """
    crudo = {"content": dict(CRUDO["content"], summary="")}
    n = prensa.desde_crudo("AAPL", crudo)
    assert n.resumen == ""
    assert "<" not in n.resumen


def test_la_fecha_no_sale_de_displayTime():
    """`displayTime` puede venir vacia, y venia vacia en el sondeo real."""
    crudo = {"content": dict(CRUDO["content"], displayTime="")}
    n = prensa.desde_crudo("AAPL", crudo)
    assert n.cuando.year == 2026


def test_provider_y_canonicalUrl_son_diccionarios():
    """Tratarlos como cadenas es el error natural, y da un medio ilegible."""
    n = prensa.desde_crudo("AAPL", CRUDO)
    assert n.medio == "Reuters"
    assert n.url.startswith("https://")


def test_un_video_se_marca_como_video():
    """Yahoo mete videos entre las noticias; el sondeo vio uno el primero."""
    crudo = {"content": dict(CRUDO["content"], contentType="VIDEO")}
    assert prensa.desde_crudo("AAPL", crudo).clase == "VIDEO"


def test_un_elemento_sin_titulo_se_descarta_sin_reventar():
    """Sin titular no hay nada que ensenar, pero tampoco motivo para caerse."""
    assert prensa.desde_crudo("AAPL", {"content": {"title": ""}}) is None


def test_un_elemento_sin_content_se_descarta():
    assert prensa.desde_crudo("AAPL", {"id": "x"}) is None


def test_las_noticias_salen_de_la_mas_nueva_a_la_mas_vieja():
    viejo = {"content": dict(CRUDO["content"], pubDate="2026-09-01T10:00:00Z")}
    nuevo = {"content": dict(CRUDO["content"], pubDate="2026-09-08T10:00:00Z")}
    salida = prensa.normalizar("AAPL", [viejo, nuevo])
    assert [n.cuando.day for n in salida] == [8, 1]


def test_una_lista_vacia_da_una_tupla_vacia():
    assert prensa.normalizar("AAPL", []) == ()
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_prensa.py -q`
Expected: FAIL con `ImportError: cannot import name 'prensa'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/prensa.py"""
"""La prensa que Yahoo asocia a cada activo, normalizada y sin juzgar.

H no filtra la prensa: no hay criterio defendible para decidir que titular
importa, y fingir uno seria peor que no tenerlo. Lo que si hace es ensenar el
medio y si es texto o video, que es lo que permite descartar de un vistazo.
Hace falta: en el sondeo, la primera "noticia" de MSFT era un video sobre los
resultados de Oracle.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Noticia:
    ticker: str
    titular: str
    resumen: str
    medio: str
    url: str
    cuando: datetime
    clase: str


def desde_crudo(ticker: str, crudo: dict) -> "Noticia | None":
    """One yfinance news item, or None when there is nothing to show.

    `provider` y `canonicalUrl` son **diccionarios**, no cadenas: tratarlos como
    cadenas da un medio ilegible y una url rota, y ninguna de las dos cosas
    lanza excepcion.
    """
    contenido = crudo.get("content") or {}
    titular = (contenido.get("title") or "").strip()
    if not titular:
        return None

    publicado = contenido.get("pubDate")
    if not publicado:
        return None
    try:
        cuando = datetime.fromisoformat(publicado.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None

    proveedor = contenido.get("provider") or {}
    enlace = contenido.get("canonicalUrl") or {}

    return Noticia(
        ticker=ticker,
        titular=titular,
        # **Solo `summary`.** `description` trae el mismo texto en HTML crudo,
        # y volcarlo pintaria etiquetas en la pantalla. Sin resumen se ensena
        # el titular solo, que ya dice algo.
        resumen=(contenido.get("summary") or "").strip(),
        medio=(proveedor.get("displayName") or "").strip(),
        url=(enlace.get("url") or "").strip(),
        # De `pubDate` y no de `displayTime`, que en el sondeo venia vacia.
        cuando=cuando,
        clase=(contenido.get("contentType") or "ARTICLE").strip(),
    )


def normalizar(ticker: str, crudos: list) -> "tuple[Noticia, ...]":
    """De la mas nueva a la mas vieja, sin los elementos que no dicen nada."""
    salida = [n for n in (desde_crudo(ticker, c) for c in crudos) if n]
    salida.sort(key=lambda n: n.cuando, reverse=True)
    return tuple(salida)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_prensa.py -q`
Expected: PASS, 9 tests

- [ ] **Step 5: Sabotea dos guardas**

1. Cambia `contenido.get("summary")` por `contenido.get("description")`.
   Expected: cae `test_el_resumen_nunca_sale_de_description`.
2. Cambia `proveedor.get("displayName")` por `str(proveedor)`.
   Expected: cae `test_provider_y_canonicalUrl_son_diccionarios`.

Deshaz los dos cambios.

- [ ] **Step 6: Commit**

```bash
git add noticias/prensa.py tests/test_noticias_prensa.py
git commit -m "feat: la prensa de yfinance, sin el HTML de description"
```

---

## Task 3: Los hechos de la SEC

**Files:**
- Create: `noticias/hechos.py`
- Test: `tests/test_noticias_hechos.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_hechos.py"""
from datetime import date

import pandas as pd

from noticias import hechos

# Copiado de la forma real de edgartools 5.52 (to_pandas()), 2026-09-08.
INDICE = pd.DataFrame(
    [
        {"form": "8-K/A", "filing_date": date(2026, 9, 1), "items": "5.02",
         "accession_number": "0001140361-26-035325",
         "primaryDocument": "ef20081427_8ka.htm"},
        {"form": "8-K", "filing_date": date(2026, 7, 30), "items": "2.02,9.01",
         "accession_number": "0000320193-26-000018",
         "primaryDocument": "aapl-20260730.htm"},
        {"form": "8-K", "filing_date": date(2026, 2, 24), "items": "5.07,9.01",
         "accession_number": "0001140361-26-006577",
         "primaryDocument": "brhc10.htm"},
    ]
)


def test_parte_los_items_por_comas():
    assert hechos.partir("2.02,9.01") == ("2.02", "9.01")


def test_parte_un_item_solo():
    assert hechos.partir("5.02") == ("5.02",)


def test_parte_con_espacios_y_vacios():
    """La SEC ha servido ' 2.02 , 9.01 ' y tambien cadenas vacias."""
    assert hechos.partir(" 2.02 , 9.01 ") == ("2.02", "9.01")
    assert hechos.partir("") == ()
    assert hechos.partir(None) == ()


def test_los_resultados_salen_materiales():
    """El caso que un modelo de un solo tipo clasificaria mal.

    "2.02,9.01" es como llega SIEMPRE un anuncio de resultados. Si esto sale
    False, cada trimestre de cada activo queda plegado entre la rutina.
    """
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert resultados.material is True
    assert resultados.tipos == ("2.02", "9.01")


def test_una_votacion_de_accionistas_no_es_material():
    """Contrapeso: que no pase por 'dos items = material'."""
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    votacion = [h for h in salida if "5.07" in h.tipos][0]
    assert votacion.material is False


def test_la_enmienda_se_marca_y_no_desaparece():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    enmiendas = [h for h in salida if h.enmienda]
    assert len(enmiendas) == 1
    assert enmiendas[0].tipos == ("5.02",)


def test_no_se_descarta_ningun_expediente():
    """Destacar no es excluir: lo que H tirase, I no lo veria nunca."""
    assert len(hechos.desde_indice("AAPL", 320193, INDICE)) == len(INDICE)


def test_la_url_apunta_al_documento_real():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert resultados.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000018/aapl-20260730.htm"
    )


def test_las_descripciones_acompanan_a_los_tipos():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    resultados = [h for h in salida if "2.02" in h.tipos][0]
    assert "Resultados" in resultados.descripciones


def test_un_tipo_desconocido_no_revienta():
    """La SEC anade items; uno nuevo debe salir con su codigo, no caerse."""
    indice = pd.DataFrame(
        [{"form": "8-K", "filing_date": date(2026, 1, 1), "items": "9.99",
          "accession_number": "0000000000-26-000001",
          "primaryDocument": "x.htm"}]
    )
    h = hechos.desde_indice("AAPL", 1, indice)[0]
    assert h.tipos == ("9.99",)
    assert h.material is False
    assert "9.99" in h.descripciones[0]


def test_un_indice_vacio_da_tupla_vacia():
    assert hechos.desde_indice("AAPL", 1, pd.DataFrame()) == ()


def test_salen_del_mas_nuevo_al_mas_viejo():
    salida = hechos.desde_indice("AAPL", 320193, INDICE)
    assert [h.cuando for h in salida] == sorted(
        [h.cuando for h in salida], reverse=True
    )
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_hechos.py -q`
Expected: FAIL con `ImportError: cannot import name 'hechos'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/hechos.py"""
"""Los 8-K del libro, desde el indice de la SEC y sin abrir ni uno.

**Los items vienen en el indice.** `EntityFilings.to_pandas()` trae una columna
`items` con los codigos, asi que basta una llamada por activo. Existe
`filing.obj().items`, pero descarga el documento entero de cada expediente, y
con quince activos eso convierte una pantalla en una espera.
"""

from dataclasses import dataclass
from datetime import date

from noticias import criterio


@dataclass(frozen=True)
class Hecho:
    ticker: str
    tipos: "tuple[str, ...]"
    descripciones: "tuple[str, ...]"
    url: str
    cuando: date
    enmienda: bool
    material: bool


def partir(items: "str | None") -> "tuple[str, ...]":
    """The SEC returns every item of a filing in one comma-separated string.

    **Aqui es donde se pierde todo si se hace mal.** "2.02,9.01" comparado
    entero contra la lista de materiales no coincide con nada, y cada anuncio
    de resultados -- el hecho mas frecuente que existe -- quedaria plegado
    entre la rutina, sin que nada lo delate.
    """
    if not items:
        return ()
    return tuple(t.strip() for t in str(items).split(",") if t.strip())


def _url(cik: int, accession: str, documento: str) -> str:
    """EDGAR guarda el documento bajo el numero de acceso sin guiones."""
    limpio = str(accession).replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{limpio}/{documento}"
    )


def desde_indice(ticker: str, cik: int, indice) -> "tuple[Hecho, ...]":
    """The filing index as it comes from edgartools, turned into Hechos.

    No se descarta ningun expediente: los materiales saldran destacados y el
    resto plegado, pero todos vuelven. Lo que H tirase, el sub-proyecto I no lo
    veria nunca.
    """
    if indice is None or len(indice) == 0:
        return ()

    salida = []
    for fila in indice.to_dict("records"):
        tipos = partir(fila.get("items"))
        salida.append(
            Hecho(
                ticker=ticker,
                tipos=tipos,
                descripciones=tuple(
                    criterio.DESCRIPCIONES.get(t, f"Tipo {t}") for t in tipos
                ),
                url=_url(
                    cik,
                    fila.get("accession_number", ""),
                    fila.get("primaryDocument", ""),
                ),
                cuando=fila.get("filing_date"),
                # get_filings(form="8-K") devuelve tambien los "8-K/A".
                enmienda=str(fila.get("form", "")).endswith("/A"),
                material=criterio.material(tipos),
            )
        )
    salida.sort(key=lambda h: h.cuando, reverse=True)
    return tuple(salida)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_hechos.py -q`
Expected: PASS, 12 tests

- [ ] **Step 5: Sabotea la guarda que importa**

Cambia el cuerpo de `partir` por `return (str(items),)` — o sea, trata la
cadena entera como un solo tipo, que es el modelo ingenuo.
Expected: cae `test_los_resultados_salen_materiales`.

Si no cae, el test no está midiendo lo que dice. Deshaz el cambio.

- [ ] **Step 6: Commit**

```bash
git add noticias/hechos.py tests/test_noticias_hechos.py
git commit -m "feat: los 8-K desde el indice, con sus varios items por expediente"
```

---

## Task 4: La agenda

**Files:**
- Create: `noticias/agenda.py`
- Test: `tests/test_noticias_agenda.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_agenda.py"""
from datetime import date

from noticias import agenda

# Forma real de yfinance 1.6.0 `.calendar`, sondeada el 2026-09-08.
CALENDARIO = {
    "Dividend Date": date(2026, 8, 12),
    "Ex-Dividend Date": date(2026, 8, 9),
    "Earnings Date": [date(2026, 10, 29)],     # LISTA, aunque tenga uno
    "Earnings High": 2.07,
    "Earnings Low": 1.93,
    "Earnings Average": 1.98124,
}


def test_saca_los_tres_eventos():
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 9, 8))
    clases = {e.clase for e in salida}
    assert clases == {"resultados", "ex-dividendo", "dividendo"}


def test_earnings_date_es_una_lista_aunque_traiga_uno():
    """Tratarla como fecha suelta da un evento con una lista dentro."""
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 9, 8))
    resultados = [e for e in salida if e.clase == "resultados"][0]
    assert resultados.cuando == date(2026, 10, 29)


def test_el_eps_estimado_viaja_en_el_detalle():
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 9, 8))
    resultados = [e for e in salida if e.clase == "resultados"][0]
    assert "1,98" in resultados.detalle or "1.98" in resultados.detalle


def test_una_fecha_ausente_no_inventa_evento():
    """Sin fecha no hay evento. Un date() por defecto seria una afirmacion."""
    salida = agenda.desde_calendario("AAPL", {"Earnings Date": []}, hoy=date(2026, 9, 8))
    assert salida == ()


def test_un_calendario_vacio_no_revienta():
    assert agenda.desde_calendario("AAPL", {}, hoy=date(2026, 9, 8)) == ()
    assert agenda.desde_calendario("AAPL", None, hoy=date(2026, 9, 8)) == ()


def test_los_eventos_pasados_no_salen():
    """El bloque se llama 'lo que viene'. Un ex-dividendo de hace un mes no."""
    salida = agenda.desde_calendario("AAPL", CALENDARIO, hoy=date(2026, 9, 8))
    assert all(e.cuando >= date(2026, 9, 8) for e in salida)


def test_ordena_por_fecha_ascendente():
    """Al reves que las noticias: aqui lo mas cercano es lo mas urgente."""
    calendario = dict(CALENDARIO, **{
        "Ex-Dividend Date": date(2026, 11, 5),
        "Dividend Date": date(2026, 11, 20),
    })
    salida = agenda.desde_calendario("AAPL", calendario, hoy=date(2026, 9, 8))
    fechas = [e.cuando for e in salida]
    assert fechas == sorted(fechas)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_agenda.py -q`
Expected: FAIL con `ImportError: cannot import name 'agenda'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/agenda.py"""
"""Lo que viene: resultados, ex-dividendo y pago.

El orden es ascendente, al reves que el de las noticias. No es un capricho: en
"lo que paso" lo mas nuevo es lo mas relevante, y en "lo que viene" lo mas
cercano es lo mas urgente.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Evento:
    ticker: "str | None"       # None para lo macro
    clase: str                 # resultados | ex-dividendo | dividendo | macro
    cuando: "date | None"      # None para lo macro: no tenemos la fecha
    detalle: str
    url: "str | None" = None


def _primera_fecha(valor) -> "date | None":
    """`Earnings Date` llega como LISTA aunque traiga una sola fecha."""
    if isinstance(valor, (list, tuple)):
        return valor[0] if valor else None
    return valor if isinstance(valor, date) else None


def desde_calendario(
    ticker: str, calendario: "dict | None", hoy: date
) -> "tuple[Evento, ...]":
    """The asset's upcoming dates, with past ones dropped.

    Una fecha ausente **no inventa evento**. Poner `date.today()` por defecto
    seria afirmar algo que nadie afirmo, que es la misma regla que
    `cartera.formato_cifra` aplica al «--» frente al 0,00.
    """
    if not calendario:
        return ()

    salida = []

    resultados = _primera_fecha(calendario.get("Earnings Date"))
    if resultados:
        estimado = calendario.get("Earnings Average")
        detalle = "Resultados"
        if estimado is not None:
            detalle = f"Resultados — EPS estimado {float(estimado):,.2f}"
        salida.append(Evento(ticker, "resultados", resultados, detalle))

    ex = _primera_fecha(calendario.get("Ex-Dividend Date"))
    if ex:
        salida.append(
            Evento(ticker, "ex-dividendo", ex,
                   "Ultimo dia para tener las acciones y cobrar")
        )

    pago = _primera_fecha(calendario.get("Dividend Date"))
    if pago:
        salida.append(Evento(ticker, "dividendo", pago, "Fecha de pago"))

    futuros = [e for e in salida if e.cuando and e.cuando >= hoy]
    futuros.sort(key=lambda e: e.cuando)
    return tuple(futuros)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_agenda.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Sabotea `_primera_fecha`**

Sustituye su cuerpo por `return valor`. Corre los tests.
Expected: cae `test_earnings_date_es_una_lista_aunque_traiga_uno`.

Deshaz el cambio.

- [ ] **Step 6: Commit**

```bash
git add noticias/agenda.py tests/test_noticias_agenda.py
git commit -m "feat: la agenda del activo, con Earnings Date que es una lista"
```

---

## Task 5: Los punteros macro

**Files:**
- Create: `noticias/macro.py`
- Test: `tests/test_noticias_macro.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_macro.py"""
from noticias import macro
from noticias.agenda import Evento


def test_son_cuatro():
    """Cuatro y no cuarenta: una lista larga de enlaces es una que nadie abre."""
    assert len(macro.PUNTEROS) == 4


def test_ninguno_lleva_fecha():
    """Es LA decision del sub-proyecto: punteros a la fuente, no fechas.

    Copiar fechas al repo crea algo que caduca en silencio; un enlace roto se
    ve roto y una fecha vieja no.
    """
    assert all(e.cuando is None for e in macro.PUNTEROS)


def test_todos_llevan_enlace_oficial():
    oficiales = ("federalreserve.gov", "bls.gov", "bea.gov")
    for e in macro.PUNTEROS:
        assert e.url and e.url.startswith("https://")
        assert any(d in e.url for d in oficiales), e.url


def test_ninguno_lleva_ticker():
    assert all(e.ticker is None for e in macro.PUNTEROS)


def test_todos_son_de_clase_macro():
    assert all(e.clase == "macro" for e in macro.PUNTEROS)


def test_el_detalle_dice_la_cadencia():
    """Sin cadencia el puntero no orienta: hay que saber si es mensual."""
    for e in macro.PUNTEROS:
        assert e.detalle.strip()


def test_son_Evento_como_los_del_activo():
    """Misma estructura, para que la pantalla no necesite dos caminos."""
    assert all(isinstance(e, Evento) for e in macro.PUNTEROS)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_macro.py -q`
Expected: FAIL con `ImportError: cannot import name 'macro'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/macro.py"""
"""Quien publica los datos de mercado, no cuando los publica.

**Punteros y no fechas, y es la decision central del sub-proyecto.** Ni
yfinance ni EDGAR dan el calendario macro. Copiar las fechas al repo crearia
algo que caduca en silencio: un calendario viejo se lee igual que uno vigente.
Un enlace roto, en cambio, se ve roto. La autoridad se queda donde esta.

Por eso `Evento.cuando` es None aqui: de la Fed sabemos que publica y donde, no
cuando. Un `date` inventado seria exactamente el defecto que esta decision
existe para evitar.
"""

from noticias.agenda import Evento

PUNTEROS = (
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="Reuniones del FOMC — ocho al ano. Deciden el tipo de interes.",
        url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="IPC — mensual. La inflacion que la Fed dice mirar.",
        url="https://www.bls.gov/schedule/news_release/",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="Situacion del empleo — mensual, normalmente el primer viernes.",
        url="https://www.bls.gov/schedule/news_release/",
    ),
    Evento(
        ticker=None,
        clase="macro",
        cuando=None,
        detalle="PIB trimestral y PCE mensual — la medida de inflacion preferida "
                "por la Fed.",
        url="https://www.bea.gov/news/schedule",
    ),
)
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_macro.py -q`
Expected: PASS, 7 tests

- [ ] **Step 5: Sabotea la decisión**

Ponle `cuando=date(2026, 9, 17)` al puntero del FOMC.
Expected: cae `test_ninguno_lleva_fecha`.

Ese test es el que protege la decisión de diseño, no un detalle. Deshaz.

- [ ] **Step 6: Commit**

```bash
git add noticias/macro.py tests/test_noticias_macro.py
git commit -m "feat: punteros a las fuentes macro oficiales, sin fechas copiadas"
```

---

## Task 6: La caché

**Files:**
- Create: `noticias/cache.py`
- Modify: `programa/.gitignore`
- Test: `tests/test_noticias_cache.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_cache.py"""
from datetime import datetime, timedelta, timezone

import pytest

from noticias import cache


@pytest.fixture
def dir_cache(tmp_path):
    return tmp_path / ".cache"


def test_guarda_y_recupera(dir_cache):
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    assert guardado.datos == {"a": 1}
    assert guardado.vigente is True


def test_lo_caducado_vuelve_marcado_pero_vuelve(dir_cache):
    """Sin conexion, un dato viejo es mejor que nada. Mentir sobre su edad, no."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(0))
    assert guardado.datos == {"a": 1}
    assert guardado.vigente is False


def test_lo_que_no_existe_da_None(dir_cache):
    assert cache.leer(dir_cache, "prensa", "ZZZZ", validez=timedelta(hours=1)) is None


def test_siempre_trae_la_hora_de_descarga(dir_cache):
    """La pantalla la ensena SIEMPRE, no solo cuando esta vieja."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    guardado = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    assert isinstance(guardado.cuando, datetime)
    assert guardado.cuando.tzinfo is not None


def test_cada_fuente_tiene_su_propio_hueco(dir_cache):
    """Prensa y hechos del mismo ticker no deben pisarse."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"quien": "prensa"})
    cache.guardar(dir_cache, "hechos", "AAPL", {"quien": "hechos"})
    p = cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1))
    h = cache.leer(dir_cache, "hechos", "AAPL", validez=timedelta(hours=1))
    assert p.datos["quien"] == "prensa"
    assert h.datos["quien"] == "hechos"


def test_un_fichero_corrupto_no_revienta(dir_cache):
    """Una cache se regenera; caerse por ella no tiene sentido."""
    cache.guardar(dir_cache, "prensa", "AAPL", {"a": 1})
    ruta = next(dir_cache.rglob("*.json"))
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cache.leer(dir_cache, "prensa", "AAPL", validez=timedelta(hours=1)) is None


def test_un_ticker_con_barras_no_escapa_del_directorio(dir_cache):
    """El ticker llega del libro; nunca debe componer una ruta a pelo."""
    cache.guardar(dir_cache, "prensa", "../../evil", {"a": 1})
    assert not (dir_cache.parent.parent / "evil.json").exists()


def test_las_validez_declaradas():
    assert cache.VALIDEZ["prensa"] == timedelta(hours=1)
    assert cache.VALIDEZ["hechos"] == timedelta(hours=1)
    assert cache.VALIDEZ["agenda"] == timedelta(days=1)
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_cache.py -q`
Expected: FAIL con `ImportError: cannot import name 'cache'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/cache.py"""
"""Frescura por fuente, y la hora de descarga siempre a la vista.

Quince activos por tres fuentes son cuarenta y cinco llamadas de red, y
Streamlit re-ejecuta el script entero con cada clic en cualquier widget. Sin
cache la pantalla no es usable.

**La hora se ensena siempre, no solo cuando el dato esta viejo.** Misma regla
que `coste_del_libro` en el sub-proyecto G: un dato que se lee como fresco sin
serlo es peor que no tener dato.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

VALIDEZ = {
    # Cambia durante el dia, pero no cada minuto.
    "prensa": timedelta(hours=1),
    # Los 8-K se presentan en horario habil, no en continuo.
    "hechos": timedelta(hours=1),
    # Una fecha de resultados no se mueve por la tarde.
    "agenda": timedelta(days=1),
}

_SEGURO = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class Guardado:
    datos: object
    cuando: datetime
    vigente: bool


def _ruta(raiz: Path, fuente: str, clave: str) -> Path:
    """El ticker viene del libro, asi que nunca compone una ruta a pelo.

    Se sanea y ademas se le pega un digest: sin el digest, "A/B" y "A_B"
    acabarian en el mismo fichero y se pisarian en silencio.
    """
    limpio = _SEGURO.sub("_", clave)[:40]
    digest = hashlib.sha256(clave.encode("utf-8")).hexdigest()[:8]
    return Path(raiz) / fuente / f"{limpio}_{digest}.json"


def guardar(raiz: Path, fuente: str, clave: str, datos) -> None:
    ruta = _ruta(raiz, fuente, clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(
            {"cuando": datetime.now(timezone.utc).isoformat(), "datos": datos},
            default=str,
        ),
        encoding="utf-8",
    )


def leer(raiz: Path, fuente: str, clave: str, validez: timedelta):
    """What is cached, or None when there is nothing usable.

    Un fichero corrupto devuelve None en vez de lanzar: una cache se regenera,
    y caerse por ella no tiene sentido. Al reves que un libro de posiciones,
    que se nombra y no se borra porque no se regenera.
    """
    ruta = _ruta(raiz, fuente, clave)
    if not ruta.exists():
        return None
    try:
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        cuando = datetime.fromisoformat(crudo["cuando"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None
    return Guardado(
        datos=crudo.get("datos"),
        cuando=cuando,
        vigente=datetime.now(timezone.utc) - cuando <= validez,
    )
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_cache.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Añade la caché al .gitignore**

En `programa/.gitignore`, junto a `ranking/.cache/` y `fundamentals/.cache/`:

```
noticias/.cache/
```

Verifica: `git status --short` no debe listar nada bajo `noticias/.cache/`
después de correr la app.

- [ ] **Step 6: Sabotea la guarda del fichero corrupto**

Quita `json.JSONDecodeError` de la tupla del `except`. Corre los tests.
Expected: cae `test_un_fichero_corrupto_no_revienta`.

Deshaz.

- [ ] **Step 7: Commit**

```bash
git add noticias/cache.py tests/test_noticias_cache.py .gitignore
git commit -m "feat: cache por fuente, con la hora de descarga siempre visible"
```

---

## Task 7: Las descargas, con sus fallos

Es el único módulo que toca la red. Va aparte a propósito: los cinco anteriores
se prueban sin conexión porque no la necesitan.

**Files:**
- Create: `noticias/fuentes.py`
- Test: `tests/test_noticias_fuentes.py`

- [ ] **Step 1: Escribe los tests que fallan**

```python
"""tests/test_noticias_fuentes.py"""
from datetime import date

import pytest

from noticias import fuentes


def test_sin_edgar_identity_los_hechos_dicen_que_falta(monkeypatch):
    """Mismo patron que el ranking sin ANTHROPIC_API_KEY: se explica y sigue."""
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)
    resultado = fuentes.hechos_de("AAPL")
    assert resultado.datos == ()
    assert "EDGAR_IDENTITY" in resultado.problema


def test_un_fallo_de_red_se_nombra_y_no_se_propaga(monkeypatch):
    def revienta(*a, **k):
        raise ConnectionError("sin ruta al host")

    monkeypatch.setattr(fuentes, "_descargar_prensa", revienta)
    resultado = fuentes.prensa_de("AAPL")
    assert resultado.datos == ()
    assert "sin ruta al host" in resultado.problema


def test_una_lista_vacia_no_es_un_fallo(monkeypatch):
    """'Sin noticias recientes' y 'la fuente cayo' no son lo mismo.

    El campo `problema` vacio es lo que las separa, y la pantalla pinta un
    aviso solo cuando trae texto.
    """
    monkeypatch.setattr(fuentes, "_descargar_prensa", lambda t: [])
    resultado = fuentes.prensa_de("AAPL")
    assert resultado.datos == ()
    assert resultado.problema == ""


def test_un_ticker_sin_cik_se_nombra(monkeypatch):
    def sin_cik(ticker):
        raise LookupError(f"{ticker} no resuelve a CIK")

    monkeypatch.setenv("EDGAR_IDENTITY", "x@y.com")
    monkeypatch.setattr(fuentes, "_descargar_hechos", sin_cik)
    resultado = fuentes.hechos_de("ZZZZ")
    assert "ZZZZ" in resultado.problema


def test_el_cik_llega_hasta_la_url(monkeypatch):
    """El CIK no viene en el indice, y sin el las urls apuntan a /data/0/.

    Nada lo delata mirando la pantalla: el texto del enlace se ve bien y solo
    falla al pulsarlo.
    """
    import pandas as pd

    indice = pd.DataFrame(
        [{"form": "8-K", "filing_date": date(2026, 7, 30), "items": "2.02",
          "accession_number": "0000320193-26-000018",
          "primaryDocument": "aapl.htm"}]
    )
    monkeypatch.setenv("EDGAR_IDENTITY", "x@y.com")
    monkeypatch.setattr(fuentes, "_descargar_hechos", lambda t: (indice, 320193))
    resultado = fuentes.hechos_de("AAPL")
    assert "/data/320193/" in resultado.datos[0].url


@pytest.mark.red
def test_la_prensa_viva_sigue_teniendo_la_forma_del_sondeo():
    """Un fixture protege de que cambies tu; solo esto, de que cambie Yahoo."""
    crudos = fuentes._descargar_prensa("AAPL")
    assert crudos, "yfinance no devolvio noticias"
    c = crudos[0]["content"]
    assert isinstance(c["provider"], dict)
    assert isinstance(c["canonicalUrl"], dict)
    assert "pubDate" in c


@pytest.mark.red
def test_el_indice_vivo_de_la_sec_sigue_trayendo_items():
    """Si la SEC dejase de servir `items`, todo el criterio se queda mudo.

    Y si dejara de servirlos **sin fallar** -- columna ausente en vez de error
    --, `partir(None)` daria `()` y todos los expedientes saldrian plegados y
    sin descripcion. Verde y vacio, que es la peor forma de romperse.
    """
    indice, cik = fuentes._descargar_hechos("AAPL")
    assert "items" in indice.columns
    assert cik == 320193, "el CIK de Apple no sale de la Company"
```

- [ ] **Step 2: Corre los tests y comprueba que fallan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_fuentes.py -q -m "not red"`
Expected: FAIL con `ImportError: cannot import name 'fuentes'`

- [ ] **Step 3: Escribe el módulo**

```python
"""noticias/fuentes.py"""
"""Lo unico que toca la red, aislado para que el resto no la necesite.

Cada descarga devuelve `Traida`, con los datos y **el problema como texto**. No
lanza: si una fuente cae, la pantalla pinta las otras y dice cual fallo. Que se
caiga la pantalla entera por una de tres es peor que ensenar dos.
"""

import os
from dataclasses import dataclass
from datetime import date, timedelta

from noticias import hechos as hechos_mod, prensa as prensa_mod

# Un ano y medio de expedientes: suficiente para ver el patron de una empresa
# sin traerse una decada que nadie va a leer.
VENTANA = timedelta(days=550)


@dataclass(frozen=True)
class Traida:
    datos: tuple
    problema: str


def _descargar_prensa(ticker: str) -> list:
    import yfinance as yf

    return yf.Ticker(ticker).news or []


def _descargar_hechos(ticker: str) -> tuple:
    """The filing index AND the cik, because the index does not carry it.

    Las columnas de `to_pandas()` se comprobaron una a una: accession_number,
    filing_date, reportDate, acceptanceDateTime, act, form, fileNumber, items,
    size, isXBRL, isInlineXBRL, primaryDocument, primaryDocDescription. **No hay
    cik.** Sacarlo de ahi daria 0, y las urls de los expedientes apuntarian a
    `/data/0/` sin que nada lo delate: el texto del enlace se ve bien.
    """
    import edgar

    hasta = date.today()
    empresa = edgar.Company(ticker)
    indice = empresa.get_filings(
        form="8-K",
        filing_date=(str(hasta - VENTANA), str(hasta)),
    ).to_pandas()
    return indice, int(empresa.cik)


def _descargar_agenda(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).calendar or {}


def prensa_de(ticker: str) -> Traida:
    try:
        crudos = _descargar_prensa(ticker)
    except Exception as e:  # la red falla de mil formas y ninguna es del programa
        return Traida((), f"{ticker}: {e}")
    # Una lista vacia NO es un fallo: "sin noticias recientes" y "la fuente
    # cayo" le dicen al usuario cosas distintas.
    return Traida(prensa_mod.normalizar(ticker, crudos), "")


def hechos_de(ticker: str) -> Traida:
    if not os.environ.get("EDGAR_IDENTITY"):
        return Traida(
            (),
            "Falta EDGAR_IDENTITY. La SEC exige un contacto en el User-Agent: "
            "EDGAR_IDENTITY='tu@correo.com'. La prensa y el calendario "
            "funcionan igual sin ella.",
        )
    try:
        indice, cik = _descargar_hechos(ticker)
    except Exception as e:
        return Traida((), f"{ticker}: {e}")
    return Traida(hechos_mod.desde_indice(ticker, cik, indice), "")


def agenda_de(ticker: str) -> Traida:
    from noticias import agenda as agenda_mod

    try:
        crudo = _descargar_agenda(ticker)
    except Exception as e:
        return Traida((), f"{ticker}: {e}")
    return Traida(agenda_mod.desde_calendario(ticker, crudo, date.today()), "")
```

- [ ] **Step 4: Corre los tests y comprueba que pasan**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_fuentes.py -q -m "not red"`
Expected: PASS, 5 tests (los 2 `red` quedan deseleccionados)

- [ ] **Step 5: Comprueba los `red` a mano, una vez**

Run: `UV_LINK_MODE=copy uv run pytest tests/test_noticias_fuentes.py -q -m red`
Expected: PASS, 2 tests. Necesitan conexión y `EDGAR_IDENTITY`.

Si fallan, **no los borres ni los marques como esperados**: significa que la
fuente cambió de forma y hay que arreglar el módulo.

- [ ] **Step 6: Sabotea la guarda de EDGAR_IDENTITY**

Quita el `if not os.environ.get("EDGAR_IDENTITY")`. Corre los tests sin la
variable.
Expected: cae `test_sin_edgar_identity_los_hechos_dicen_que_falta`.

Deshaz.

- [ ] **Step 7: Commit**

```bash
git add noticias/fuentes.py tests/test_noticias_fuentes.py
git commit -m "feat: las descargas, que dicen que fuente cayo en vez de caerse"
```

---

## Task 8: La pantalla

**Files:**
- Create: `vistas/noticias.py`
- Modify: `app.py`

- [ ] **Step 1: Lee cómo lo hacen las dos pantallas hermanas**

Antes de escribir nada, lee `vistas/rebalanceo.py` entero y las primeras 60
líneas de `vistas/seguimiento.py`. Copia sus patrones: cómo eligen libro, cómo
avisan cuando no hay ninguno, y cómo inyectan CSS.

**Dos trampas que ya costaron una corrección en G:**
1. Si usas `medidores`, **inyecta `medidores.CSS`**. No se inyecta solo, y sin
   él los medidores se pintan como texto plano.
2. Comprueba en `medidores.py` qué clases existen **antes** de usarlas. En G se
   usó `mpp-marca`, que no existe; la real es `mpp-tope`.

- [ ] **Step 2: Escribe la pantalla**

Estructura, de arriba abajo:

1. Selector de libro (patrón de `vistas/rebalanceo.py`). Si no hay libros,
   `st.info` enlazando a Seguimiento y `st.stop()`.
2. Si el libro no tiene tickers, explícalo y para: sin tickers no hay nada que
   consultar. (En F, llamar a yfinance con lista vacía reventaba con
   `No objects to concatenate`.)
3. `st.multiselect` de activos, **todos marcados por defecto**.
4. Botón «Actualizar», que borra la caché de las fuentes y vuelve a pedir.
5. **Lo que viene**: la agenda de los activos elegidos ordenada por fecha, y
   debajo los `macro.PUNTEROS` en su propio bloque, con el enlace, y dejando
   claro que la fecha está en la fuente y no aquí.
6. **Lo que pasó — hechos**: los `material=True` desplegados; el resto dentro de
   un `st.expander` que diga cuántos hay. Marca las enmiendas. La partición, que
   es donde se rompe si se rompe:

```python
# El criterio ya decidio: aqui solo se reparte. No vuelvas a comprobar tipos
# a mano, porque entonces habria dos criterios y uno se quedaria atras.
destacados = [h for h in todos if h.material]
plegados = [h for h in todos if not h.material]

for h in destacados:
    etiqueta = " · ".join(h.descripciones)
    if h.enmienda:
        etiqueta += " (enmienda)"
    st.markdown(
        f"**{h.ticker}** — {etiqueta}  \n"
        f"{h.cuando:%d/%m/%Y} · [Ver el expediente]({h.url})"
    )

if plegados:
    with st.expander(f"Otros {len(plegados)} expedientes de tramite"):
        for h in plegados:
            ...  # mismo formato

# `destacados` vacio y `plegados` lleno NO es "sin novedades": significa que
# hubo movimiento y nada de lo que importa. Dilo, en vez de dejar el hueco.
if not destacados and plegados:
    st.caption("Sin hechos materiales en el periodo; solo tramite.")
```
7. **Lo que pasó — prensa**: titular, medio, clase (vídeo o artículo), fecha y
   enlace.
8. Pie: la hora de descarga de cada fuente, **siempre**, y si algo vino de
   caché vieja, dicho.
9. Cualquier `Traida.problema` no vacío sale como `st.warning` nombrando la
   fuente y el ticker.

Los bloques 6 y 7 van **separados y etiquetados**, nunca fundidos en una lista
cronológica: un 8-K es de declaración obligatoria y un titular es la copia de
alguien.

- [ ] **Step 3: Regístrala en `app.py`**

En la sección «Cartera», después de Rebalanceo, siguiendo el patrón exacto de
las dos entradas que ya hay ahí.

- [ ] **Step 4: Arranca la app y recórrela**

Run: `UV_LINK_MODE=copy uv run streamlit run app.py`

Comprueba, y **anota lo que veas, no lo que esperes ver**:

- [ ] Un libro con tickers reales carga las tres fuentes sin excepción.
- [ ] Un anuncio de resultados (`2.02,9.01`) sale **destacado**, no plegado.
      Es el defecto que este plan más teme.
- [ ] El bloque plegado dice cuántos expedientes tiene y se abre.
- [ ] Los punteros macro no muestran ninguna fecha.
- [ ] La hora de descarga aparece aunque los datos sean recién traídos.
- [ ] Segundo clic en un widget: **no** vuelve a descargar (la caché funciona).
- [ ] «Actualizar» sí vuelve a descargar.
- [ ] Un libro sin tickers no revienta.

Los cuatro peores defectos de F sólo aparecieron en este paso, con la suite
entera en verde. Si algo falla aquí, arréglalo y vuelve a recorrer.

- [ ] **Step 5: Corre la suite entera**

Run: `UV_LINK_MODE=copy uv run pytest tests/ -q -m "not red"`
Expected: PASS. Antes de H eran 1.000 pasando y 4 omitidos. H añade **59 tests**
(10 + 9 + 12 + 8 + 7 + 8 + 5), así que deben salir **1.059 pasando**, más los
2 marcados `red` que quedan deseleccionados. Si sale otro número, alguien
añadió o perdió un test sin decirlo: averigua cuál antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add vistas/noticias.py app.py
git commit -m "feat: la pantalla de noticias, con los hechos separados de la prensa"
```

---

## Task 9: Dejarlo dicho

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Actualiza CONTEXTO.md**

Marca H como terminado en la tabla de sub-proyectos y añade «Resultado del
sub-proyecto H» en el mismo tono que las de A, B, C, F y G. Como mínimo:

- **Punteros a la fuente macro, no fechas copiadas.** Un enlace roto se ve
  roto; una fecha vieja no.
- **Un 8-K lleva varios items** (`"2.02,9.01"`), y modelarlo como uno solo
  habría dejado cada anuncio de resultados clasificado como no material. Se
  descubrió sondeando el índice **antes** de escribir el código.
- **`description` de yfinance viene en HTML** y no se usa; el resumen sale sólo
  de `summary`.
- **Los items vienen en el índice**, así que basta una llamada por activo.
- **H no filtra ni interpreta**: lo que H tirase, I no lo vería nunca.
- **La lista de tipos materiales está congelada** en su propio commit.
- Qué hereda I: las tres estructuras `Noticia`, `Hecho` y `Evento`.

Actualiza el recuento de tests de la lista de comandos.

- [ ] **Step 2: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: las noticias, y por que los items del 8-K son varios"
```

---

## Lo que queda para I

I toma `Noticia`, `Hecho` y `Evento` y le pide a Claude interpretación y
propuestas de ajuste. H no le deja nada más, y a propósito: ninguna decisión
sobre qué importa se toma en H, para que I la vea entera.
