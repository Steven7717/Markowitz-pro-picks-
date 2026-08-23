# Compartir el programa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el programa se pueda pasar a otra persona y arranque en Windows o Mac con doble clic, sin instalar Python, y que cada usuario meta sus propias credenciales desde la interfaz.

**Architecture:** Un módulo nuevo `credenciales.py` en la raíz guarda la clave de Anthropic y el correo de EDGAR en la carpeta personal del usuario y los vuelca en `os.environ`, que es de donde ya los leen edgartools y el cliente de Anthropic — ningún consumidor actual se toca. `uv` sustituye al supuesto de "ya tienes Python": un `pyproject.toml` con lock commiteado y un lanzador por sistema operativo.

**Tech Stack:** Python 3.12, Streamlit, uv (gestor de entorno), pytest.

**Spec:** [`docs/superpowers/specs/2026-08-22-compartir-el-programa-design.md`](../specs/2026-08-22-compartir-el-programa-design.md)

---

## Estructura de ficheros

| Fichero | Estado | Responsabilidad |
|---|---|---|
| `credenciales.py` | crear | Leer, validar, guardar y aplicar las credenciales del usuario. Única pieza que conoce la ruta del fichero |
| `tests/test_credenciales.py` | crear | Toda la lógica anterior, sin red y sin Streamlit |
| `pages/1_Revisar_candidatos.py` | modificar | Añadir el apartado de credenciales y cargarlas al arrancar |
| `pyproject.toml` | crear | Qué instalar: runtime frente a dev |
| `.python-version` | crear | Fijar Python 3.12 para todo el mundo |
| `uv.lock` | crear (generado) | Versiones exactas, idénticas en toda máquina |
| `.gitignore` | modificar | Ignorar `.venv/` que crea uv |
| `requirements.txt` | modificar | Regenerado desde el lock, para quien no use uv |
| `Iniciar App.bat` | modificar | Lanzador de Windows con arranque de uv |
| `Iniciar App.command` | crear | Lanzador de macOS, mismo comportamiento |
| `README.md` | crear | Instrucciones para quien recibe el programa |
| `CONTEXTO.md` | modificar | Reflejar cómo se distribuye ahora |

`credenciales.py` va en la raíz, junto a `data.py` y `charts.py`, porque lo consumen `fundamentals/`, `ranking/` y `aprobacion/`. Meterlo dentro de uno de ellos crearía una dependencia hacia arriba entre paquetes que hoy no se conocen entre sí.

---

## Task 1: El módulo y la ida y vuelta

**Files:**
- Create: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_credenciales.py`:

```python
from credenciales import Credenciales, cargar, guardar


def test_lo_guardado_se_lee_igual(tmp_path):
    ruta = tmp_path / "credenciales.json"
    guardar(
        Credenciales(api_key="sk-ant-abc123456789", edgar_identity="yo@x.com"),
        ruta,
    )
    leidas = cargar(ruta)
    assert leidas.api_key == "sk-ant-abc123456789"
    assert leidas.edgar_identity == "yo@x.com"


def test_guardar_crea_la_carpeta_si_no_existe(tmp_path):
    # El usuario nuevo no tiene ~/.markowitz-pro-picks: si guardar no la crea,
    # el primer guardado de todo el mundo falla.
    ruta = tmp_path / "sin" / "crear" / "credenciales.json"
    guardar(Credenciales(api_key="sk-ant-abc123456789"), ruta)
    assert ruta.exists()
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'credenciales'`

- [ ] **Step 3: Escribir la implementación mínima**

Crear `credenciales.py`:

```python
"""Las credenciales del usuario, guardadas fuera del proyecto.

Vive en la raíz y no dentro de `aprobacion/` porque lo consumen tres paquetes
--`fundamentals`, `ranking` y la página de aprobación--; meterlo en uno de ellos
crearía una dependencia hacia arriba entre paquetes que hoy no se conocen.

El fichero se escribe en la carpeta personal del usuario, nunca dentro del
proyecto: quien recomprima la carpeta y se la pase a otro no manda su clave
dentro, porque nunca estuvo ahí. `.gitignore` protege de git, no de un ZIP.
"""

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

RUTA = Path.home() / ".markowitz-pro-picks" / "credenciales.json"


@dataclass(frozen=True)
class Credenciales:
    """Los dos datos que necesita la mitad con IA."""

    api_key: str | None = None
    edgar_identity: str | None = None

    def limpia(self) -> "Credenciales":
        """Copia sin espacios sobrantes, con lo vacío convertido en ausente.

        Un campo en blanco significa "no lo tengo", no "lo tengo y es la
        cadena vacía": son estados distintos y `disponibilidad()` ya trata el
        segundo como ausente.
        """
        return replace(
            self,
            api_key=_limpiar(self.api_key),
            edgar_identity=_limpiar(self.edgar_identity),
        )


def _limpiar(valor: str | None) -> str | None:
    if valor is None:
        return None
    return valor.strip() or None


def cargar(ruta: Path | None = None) -> Credenciales:
    """Leer el fichero. Que no exista es un usuario nuevo, no un error."""
    ruta = Path(ruta or RUTA)
    if not ruta.exists():
        return Credenciales()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return Credenciales(
        api_key=datos.get("api_key") or None,
        edgar_identity=datos.get("edgar_identity") or None,
    ).limpia()


def guardar(credenciales: Credenciales, ruta: Path | None = None) -> Path:
    """Escribir el fichero de forma atómica y devolver dónde quedó."""
    credenciales = credenciales.limpia()
    ruta = Path(ruta or RUTA)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    texto = json.dumps(
        {
            "api_key": credenciales.api_key,
            "edgar_identity": credenciales.edgar_identity,
        },
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)
    return ruta
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: guardar y leer las credenciales del usuario"
```

---

## Task 2: Fichero ausente frente a fichero corrupto

Ausente y roto son cosas distintas: el primero es un usuario nuevo, el segundo es un fallo que esconderlo dejaría invisible. Mismo criterio que `aprobacion/carga.py` con `FaltanFichas` y `ContratoRoto`.

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
import json

import pytest

from credenciales import ConfigIlegible
```

```python
def test_sin_fichero_las_credenciales_salen_vacias(tmp_path):
    leidas = cargar(tmp_path / "no-existe.json")
    assert leidas.api_key is None
    assert leidas.edgar_identity is None


def test_un_fichero_corrupto_no_se_confunde_con_uno_ausente(tmp_path):
    # Devolver credenciales vacías aquí escondería el fallo: la página diría
    # "falta la clave" cuando lo que pasa es que el fichero está roto, y el
    # usuario buscaría el problema donde no está.
    ruta = tmp_path / "credenciales.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ConfigIlegible):
        cargar(ruta)


def test_un_json_que_no_es_un_objeto_tambien_es_ilegible(tmp_path):
    ruta = tmp_path / "credenciales.json"
    ruta.write_text(json.dumps(["una", "lista"]), encoding="utf-8")
    with pytest.raises(ConfigIlegible):
        cargar(ruta)
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'ConfigIlegible'`

- [ ] **Step 3: Escribir la implementación**

En `credenciales.py`, añadir la excepción después de `RUTA`:

```python
class ConfigIlegible(ValueError):
    """Hay un fichero de credenciales, pero no se puede leer."""
```

Y sustituir el cuerpo de `cargar` por:

```python
def cargar(ruta: Path | None = None) -> Credenciales:
    """Leer el fichero. Que no exista es un usuario nuevo, no un error."""
    ruta = Path(ruta or RUTA)
    if not ruta.exists():
        return Credenciales()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigIlegible(f"No se pudo leer {ruta}: {error}") from error
    if not isinstance(datos, dict):
        raise ConfigIlegible(f"{ruta} no contiene un objeto JSON.")
    return Credenciales(
        api_key=datos.get("api_key") or None,
        edgar_identity=datos.get("edgar_identity") or None,
    ).limpia()
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: distinguir credenciales ausentes de fichero corrupto"
```

---

## Task 3: Validación de forma, y avisos que no bloquean

Se comprueba la forma, nunca la validez: verificar la clave contra la API costaría dinero en cada guardado. Un prefijo inesperado avisa pero no bloquea — si Anthropic cambia el formato, este código no debe rechazar claves buenas.

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
from credenciales import CredencialInvalida, avisos
```

```python
def test_un_correo_sin_forma_de_correo_se_rechaza(tmp_path):
    # La SEC exige un contacto real en el User-Agent; si aceptamos "asdf" la
    # descarga falla mucho más tarde y con un error que no señala aquí.
    with pytest.raises(CredencialInvalida):
        guardar(Credenciales(edgar_identity="asdf"), tmp_path / "c.json")


def test_una_clave_con_espacios_dentro_se_rechaza(tmp_path):
    # Es lo que pasa al pegar desde un correo que partió la línea. Guardarla
    # daría un 401 desde la API, sin pista de que el problema fue el pegado.
    with pytest.raises(CredencialInvalida):
        guardar(Credenciales(api_key="sk-ant-abc 123"), tmp_path / "c.json")


def test_solo_el_correo_es_una_credencial_valida(tmp_path):
    # Guardar solo una de las dos es legítimo: se rellenan en dos momentos.
    ruta = guardar(Credenciales(edgar_identity="yo@x.com"), tmp_path / "c.json")
    assert cargar(ruta).api_key is None


def test_una_clave_con_prefijo_raro_se_guarda_pero_avisa(tmp_path):
    credenciales = Credenciales(api_key="clave-de-otro-formato")
    guardar(credenciales, tmp_path / "c.json")
    assert avisos(credenciales)


def test_una_clave_normal_no_genera_avisos():
    assert avisos(Credenciales(api_key="sk-ant-abc123456789")) == []
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'CredencialInvalida'`

- [ ] **Step 3: Escribir la implementación**

En `credenciales.py`, añadir `import re` arriba y estas constantes junto a `RUTA`:

```python
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PREFIJO_HABITUAL = "sk-ant-"
```

Añadir la excepción junto a `ConfigIlegible`:

```python
class CredencialInvalida(ValueError):
    """Lo que se intenta guardar no tiene forma de credencial."""
```

Añadir las dos funciones:

```python
def validar(credenciales: Credenciales) -> None:
    """Comprobar la forma. Nunca la validez.

    Verificar la clave contra la API costaría dinero y una espera en cada
    guardado, y la app ya falla de forma visible si la clave es mala. Lo que
    sí se puede detectar aquí es un pegado roto o un correo que no lo es.
    """
    credenciales = credenciales.limpia()

    if credenciales.api_key and any(c.isspace() for c in credenciales.api_key):
        raise CredencialInvalida(
            "La clave tiene espacios o saltos de línea dentro. Suele pasar al "
            "copiarla desde un correo: pégala en una sola línea."
        )

    correo = credenciales.edgar_identity
    if correo and not _CORREO.match(correo):
        raise CredencialInvalida(
            f"'{correo}' no tiene forma de correo. La SEC exige un contacto "
            "real en la cabecera de cada petición."
        )


def avisos(credenciales: Credenciales) -> list[str]:
    """Lo que merece decirse pero no impedir el guardado."""
    credenciales = credenciales.limpia()
    fuera = []
    if credenciales.api_key and not credenciales.api_key.startswith(
        _PREFIJO_HABITUAL
    ):
        fuera.append(
            f"La clave no empieza por '{_PREFIJO_HABITUAL}', que es lo habitual. "
            "Se guarda igual: si Anthropic cambiara el formato, bloquearla aquí "
            "rechazaría claves buenas."
        )
    return fuera
```

Y llamar a `validar` como primera línea del cuerpo de `guardar`:

```python
def guardar(credenciales: Credenciales, ruta: Path | None = None) -> Path:
    """Escribir el fichero de forma atómica y devolver dónde quedó."""
    validar(credenciales)
    credenciales = credenciales.limpia()
    ...
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: validar la forma de las credenciales sin llamar a la API"
```

---

## Task 4: `aplicar()` y la precedencia del entorno

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
from credenciales import aplicar
```

```python
def test_aplicar_pone_las_credenciales_en_el_entorno():
    entorno = {}
    aplicar(Credenciales(api_key="sk-ant-x", edgar_identity="yo@x.com"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "sk-ant-x"
    assert entorno["EDGAR_IDENTITY"] == "yo@x.com"


def test_el_entorno_gana_sobre_el_fichero():
    # Quien tiene la variable puesta en su shell manda: si el fichero la
    # pisara, el entorno de desarrollo y los tests dejarían de ser los que
    # gobiernan, y sería la convención al revés de como está en todas partes.
    entorno = {"ANTHROPIC_API_KEY": "la-del-shell"}
    aplicar(Credenciales(api_key="la-del-fichero"), entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "la-del-shell"


def test_una_credencial_ausente_no_escribe_nada_en_el_entorno():
    entorno = {}
    aplicar(Credenciales(edgar_identity="yo@x.com"), entorno)
    assert "ANTHROPIC_API_KEY" not in entorno
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'aplicar'`

- [ ] **Step 3: Escribir la implementación**

Añadir a `credenciales.py`:

```python
def aplicar(
    credenciales: Credenciales, entorno: dict[str, str] | None = None
) -> None:
    """Volcar en el entorno lo que no venga ya puesto.

    Es todo el cableado que hace falta: nadie llama a
    `fundamentals/fetch.py:set_sec_identity()` en el camino de producción
    --sólo los tests-- porque edgartools lee `EDGAR_IDENTITY` del entorno por
    su cuenta, igual que el cliente de Anthropic lee `ANTHROPIC_API_KEY`.
    """
    entorno = os.environ if entorno is None else entorno
    credenciales = credenciales.limpia()
    for nombre, valor in (
        ("ANTHROPIC_API_KEY", credenciales.api_key),
        ("EDGAR_IDENTITY", credenciales.edgar_identity),
    ):
        if valor and not entorno.get(nombre):
            entorno[nombre] = valor
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: aplicar las credenciales al entorno sin pisar el shell"
```

---

## Task 5: `borrar()` limpia también el entorno

Sin la segunda mitad, "Borrar" no haría nada visible hasta reiniciar: la clave seguiría en `os.environ` y la página seguiría ofreciendo la IA.

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
from credenciales import borrar
```

```python
def test_borrar_quita_el_fichero(tmp_path):
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    borrar(ruta, {})
    assert not ruta.exists()


def test_borrar_retira_del_entorno_lo_que_el_fichero_habia_puesto(tmp_path):
    # Sin esto, "Borrar" no hace nada visible hasta reiniciar: la clave sigue
    # en os.environ y la página sigue ofreciendo la IA como si nada.
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    entorno = {}
    aplicar(cargar(ruta), entorno)
    borrar(ruta, entorno)
    assert "ANTHROPIC_API_KEY" not in entorno


def test_borrar_no_toca_una_variable_que_venia_del_shell(tmp_path):
    # El usuario borra lo que guardó en la app, no lo que puso en su shell.
    ruta = guardar(Credenciales(api_key="la-del-fichero"), tmp_path / "c.json")
    entorno = {"ANTHROPIC_API_KEY": "la-del-shell"}
    borrar(ruta, entorno)
    assert entorno["ANTHROPIC_API_KEY"] == "la-del-shell"


def test_borrar_un_fichero_corrupto_igualmente_lo_quita(tmp_path):
    # Es justo el caso en que el usuario más necesita poder borrar.
    ruta = tmp_path / "c.json"
    ruta.write_text("{roto", encoding="utf-8")
    borrar(ruta, {})
    assert not ruta.exists()
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'borrar'`

- [ ] **Step 3: Escribir la implementación**

Añadir a `credenciales.py`:

```python
def borrar(ruta: Path | None = None, entorno: dict[str, str] | None = None) -> None:
    """Quitar el fichero y retirar del entorno lo que ese fichero había puesto.

    Sólo se retira lo que coincide con lo guardado: una variable que el
    usuario tenía en su shell no se toca, porque él no la puso desde aquí y
    no espera que la app se la borre.

    Un fichero corrupto se borra igual. Es justo el caso en que más falta le
    hace al usuario poder deshacerse de él.
    """
    ruta = Path(ruta or RUTA)
    entorno = os.environ if entorno is None else entorno
    try:
        guardadas = cargar(ruta)
    except ConfigIlegible:
        guardadas = Credenciales()

    ruta.unlink(missing_ok=True)

    for nombre, valor in (
        ("ANTHROPIC_API_KEY", guardadas.api_key),
        ("EDGAR_IDENTITY", guardadas.edgar_identity),
    ):
        if valor and entorno.get(nombre) == valor:
            del entorno[nombre]
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 17 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: borrar las credenciales tambien las retira del entorno"
```

---

## Task 6: Enmascarar la clave

La clave completa nunca vuelve al HTML de la página.

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
from credenciales import enmascarar
```

```python
def test_la_clave_enmascarada_no_contiene_la_clave():
    clave = "sk-ant-api03-secretosecretosecreto1234"
    mascara = enmascarar(clave)
    assert clave not in mascara
    assert "secretosecreto" not in mascara
    assert mascara.endswith("1234")


def test_una_clave_corta_no_ensena_nada():
    # Con pocos caracteres, mostrar principio y final es mostrarla entera.
    assert "abc" not in enmascarar("sk-abc")


def test_sin_clave_la_mascara_esta_vacia():
    assert enmascarar(None) == ""
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: FAIL — `ImportError: cannot import name 'enmascarar'`

- [ ] **Step 3: Escribir la implementación**

Añadir a `credenciales.py`:

```python
def enmascarar(clave: str | None) -> str:
    """Lo que se puede enseñar de una clave guardada.

    Sirve para que el usuario reconozca cuál tiene puesta, no para leerla. Con
    una clave corta no se enseña nada: mostrar principio y final de algo de
    pocos caracteres es mostrarlo entero.
    """
    if not clave:
        return ""
    if len(clave) < 20:
        return "•" * 8
    return f"{clave[:7]}…{clave[-4:]}"
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 20 tests.

- [ ] **Step 5: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: enmascarar la clave guardada"
```

---

## Task 7: Escritura atómica y permisos del fichero

**Files:**
- Modify: `credenciales.py`
- Test: `tests/test_credenciales.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_credenciales.py`:

```python
import os
import stat
```

```python
def test_un_guardado_que_falla_a_medias_deja_intacto_lo_anterior(tmp_path,
                                                                 monkeypatch):
    ruta = guardar(Credenciales(api_key="sk-ant-la-buena-de-antes"),
                   tmp_path / "c.json")

    def replace_que_falla(self, destino):
        raise OSError("disco lleno")

    monkeypatch.setattr("pathlib.Path.replace", replace_que_falla)
    with pytest.raises(OSError):
        guardar(Credenciales(api_key="sk-ant-la-nueva-que-no-cuaja"), ruta)

    assert cargar(ruta).api_key == "sk-ant-la-buena-de-antes"


@pytest.mark.skipif(os.name == "nt", reason="Windows no usa permisos POSIX")
def test_el_fichero_no_lo_puede_leer_nadie_mas(tmp_path):
    ruta = guardar(Credenciales(api_key="sk-ant-x"), tmp_path / "c.json")
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado en Windows: PASS el primero (la escritura ya es atómica desde Task 1) y SKIP el segundo. En Mac/Linux: FAIL el segundo con `assert 420 == 384` — el fichero nace con permisos por defecto.

Nota: el primer test se escribe igualmente. Verifica una garantía que hoy se cumple por accidente del orden de las líneas y que un refactor podría romper sin que nada más lo notara.

- [ ] **Step 3: Escribir la implementación**

En `credenciales.py`, dentro de `guardar`, entre `tmp.write_text(...)` y `tmp.replace(ruta)`:

```python
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    # Antes del replace, no después: así el fichero nunca existe en su nombre
    # definitivo con permisos abiertos, ni un instante. En Windows chmod sólo
    # cambia el bit de sólo lectura y esto no hace nada -- ahí la protección
    # son los permisos de la carpeta de usuario.
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(ruta)
    return ruta
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

```bash
python -m pytest tests/test_credenciales.py -v
```

Esperado: PASS, 22 tests (uno de ellos SKIP en Windows).

- [ ] **Step 5: Ejecutar la suite entera para comprobar que nada se rompió**

```bash
python -m pytest tests/ -q -m "not red"
```

Esperado: los 576 tests que ya pasaban, más los nuevos.

- [ ] **Step 6: Commit**

```bash
git add credenciales.py tests/test_credenciales.py
git commit -m "feat: permisos restrictivos en el fichero de credenciales"
```

---

## Task 8: El apartado en la página de candidatos

No lleva test automático: es Streamlit. Se verifica arrancando la app, y el paso de verificación es obligatorio.

**Files:**
- Modify: `pages/1_Revisar_candidatos.py`

> **Corregido tras la revisión (commit `2aaff34` y siguientes).** La primera
> versión de esta tarea llamaba a `st.rerun()` dentro del desplegable de
> credenciales, que está **encima** de las casillas de aprobación. Streamlit
> descarta el estado de los widgets que no llegó a dibujar en esa pasada, así
> que guardar credenciales borraba en silencio las casillas marcadas y los
> motivos escritos — y dejaba muda a `hay_revision_en_curso`, que existe justo
> para proteger ese trabajo. Los pasos de abajo ya llevan el rerun aplazado al
> final de la página. No los "simplifiques" volviendo al `st.rerun()` en sitio.

Los pasos se anclan al **contenido**, no a números de línea: cada paso desplaza las líneas del siguiente, así que un número escrito aquí sería falso en cuanto empezaras.

- [ ] **Step 1: Añadir los imports**

Después de la línea `from fundamentals.kpis import TODOS_LOS_KPIS`, añadir:

```python
from credenciales import (
    RUTA as RUTA_CREDENCIALES,
    ConfigIlegible,
    CredencialInvalida,
    Credenciales,
    aplicar,
    avisos,
    borrar,
    cargar,
    enmascarar,
    variables_del_shell,
    reemplazar,
)
from credenciales import guardar as guardar_credenciales
```

`guardar` se importa con alias porque `guardar_acta` ya vive en este espacio de nombres y dos funciones llamadas casi igual en el mismo fichero es una confusión esperando a ocurrir.

- [ ] **Step 2: Añadir la función del apartado**

Justo después de la función `_generar` (su última línea es `st.rerun()`) y antes del comentario que empieza `# A la vista y no dentro de un desplegable`, añadir:

```python
def _apartado_credenciales(guardadas: Credenciales) -> None:
    """Los dos datos que necesita la mitad con IA, y de dónde sale cada uno."""
    for texto in st.session_state.pop("avisos_credenciales", []):
        st.warning(texto)

    st.markdown(
        f"Se guardan en tu carpeta personal (`{RUTA_CREDENCIALES}`), **fuera de "
        "este proyecto**: si comprimes la carpeta y se la pasas a alguien, tu "
        "clave no viaja dentro."
    )

    # La regla de precedencia vive en credenciales.py, no aqui: es la misma
    # que aplica aplicar(), y una pagina de Streamlit no se puede probar.
    desde_entorno = variables_del_shell(guardadas)
    if desde_entorno:
        st.info(
            "Ahora mismo manda el entorno para "
            + " y ".join(f"`{nombre}`" for nombre in desde_entorno)
            + ". Lo que guardes aqui no lo pisa."
        )

    if guardadas.api_key and not st.session_state.get("editando_credenciales"):
        columna_clave, columna_cambiar, columna_borrar = st.columns([4, 1, 1])
        columna_clave.text_input(
            "Clave de Anthropic",
            value=enmascarar(guardadas.api_key),
            disabled=True,
        )
        if columna_cambiar.button("Cambiar", use_container_width=True):
            st.session_state.editando_credenciales = True
            st.rerun()
        if columna_borrar.button("Borrar", use_container_width=True):
            borrar()
            st.rerun()
        st.text_input(
            "Correo para EDGAR",
            value=guardadas.edgar_identity or "",
            disabled=True,
        )
        return

    nueva_clave = st.text_input(
        "Clave de Anthropic",
        type="password",
        key="entrada_clave",
        help="Se saca de console.anthropic.com. Empieza por sk-ant-.",
    )
    nuevo_correo = st.text_input(
        "Correo para EDGAR",
        value=guardadas.edgar_identity or "",
        key="entrada_correo",
        help=(
            "No es un registro: la SEC exige un contacto en la cabecera de "
            "cada peticion y solo se envia ahi."
        ),
    )
    if st.button("Guardar credenciales", type="primary"):
        nuevas = Credenciales(
            api_key=nueva_clave or guardadas.api_key,
            edgar_identity=nuevo_correo,
        )
        try:
            guardar_credenciales(nuevas)
        except CredencialInvalida as error:
            st.error(str(error))
        except OSError as error:
            st.error(f"No se pudieron guardar: {error}")
        else:
            # reemplazar y no aplicar: aplicar() no pisa lo que ya hay en el
            # entorno, y despues de arrancar siempre hay algo -- lo puso el
            # propio aplicar(). Con aplicar() aqui, cambiar una clave revocada
            # la guardaria en disco y el proceso seguiria usando la vieja toda
            # la sesion, con esta pagina mostrando la nueva enmascarada.
            reemplazar(guardadas, nuevas)
            # Los avisos se guardan en sesion en vez de pintarse aqui: el
            # rerun de la linea siguiente borraria la pantalla antes de que
            # nadie los leyera.
            st.session_state.avisos_credenciales = avisos(nuevas)
            st.session_state.editando_credenciales = False
            st.rerun()
```

- [ ] **Step 3: Cargar las credenciales al arrancar**

Sustituir la única línea `puede = disponibilidad()` por:

```python
# Lo guardado ayer no sirve de nada si nadie lo carga hoy: guardar es lo que
# escribe, arrancar es lo que aplica, y hacen falta los dos.
credenciales_rotas = None
try:
    credenciales_guardadas = cargar()
    aplicar(credenciales_guardadas)
except ConfigIlegible as error:
    # Un fichero de configuracion corrupto no deja a nadie sin optimizador:
    # se avisa y se sigue con la mitad gratis.
    credenciales_guardadas = Credenciales()
    credenciales_rotas = str(error)

puede = disponibilidad()
```

- [ ] **Step 4: Colgar el apartado bajo el bloque de generación**

Sustituir estas dos líneas (están justo debajo de la línea que define `pulsado`):

```python
if not puede.puede_usar_ia:
    st.caption(puede.motivo)
```

por:

```python
if not puede.puede_usar_ia:
    st.caption(puede.motivo)

with st.expander("🔑 Mis credenciales", expanded=not puede.puede_usar_ia):
    if credenciales_rotas:
        st.warning(
            f"{credenciales_rotas}\n\nGuarda las credenciales otra vez para "
            "reemplazarlo, o borra el fichero a mano."
        )
    _apartado_credenciales(credenciales_guardadas)
```

- [ ] **Step 5: Verificar arrancando la app de verdad**

```bash
py -m streamlit run app.py
```

Comprobar, en la página "Revisar candidatos", **los seis casos**:

1. Sin credenciales, el apartado nace desplegado y la opción "Con IA" no aparece.
2. Guardar un correo mal formado (`asdf`) muestra el error y no guarda nada.
3. Guardar clave y correo válidos hace aparecer la opción "Con IA" sin reiniciar.
4. Recargar la página mantiene la clave puesta y la enseña enmascarada.
5. "Borrar" hace desaparecer la opción "Con IA" en el acto, sin reiniciar.
6. Con `ANTHROPIC_API_KEY` puesta en el shell, el apartado avisa de que manda el entorno.

- [ ] **Step 6: Commit**

```bash
git add pages/1_Revisar_candidatos.py
git commit -m "feat: apartado de credenciales en la pagina de candidatos"
```

---

## Task 9: `pyproject.toml`, Python fijado y el lock

**Files:**
- Create: `pyproject.toml`, `.python-version`
- Modify: `.gitignore`

- [ ] **Step 1: Crear `pyproject.toml`**

```toml
[project]
name = "markowitz-pro-picks"
version = "0.1.0"
description = "Optimizacion de portafolio con analisis fundamental y gate de aprobacion humana"
requires-python = ">=3.12"

dependencies = [
    "streamlit>=1.32.0",
    "yfinance>=0.2.40",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
    # Tope en la 3 a proposito. Sin el, uv resuelve la 3.0.5, donde .stack()
    # ya no descarta los NaN, y eso rompe test_research_signals.py. Este codigo
    # calcula los KPIs, Ledoit-Wolf y la validacion walk-forward contra el
    # comportamiento de pandas 2.x: lo que se vio romper fue un test, pero lo
    # que preocupa son los cambios que ningun test capture. Migrar a pandas 3
    # es un trabajo aparte, no un efecto secundario de empaquetar.
    "pandas>=2.2.0,<3",
    "plotly>=5.20.0",
    "fpdf2>=2.7.9",
    "openpyxl>=3.1.2",
    # exporter.py:109 mete las graficas en el PDF con fig.write_image, que
    # necesita kaleido.
    "kaleido>=0.2.1",
    # fundamentals/fetch.py:130 cachea el panel de la SEC en parquet, y eso
    # esta en el camino vivo de generar candidatos: es runtime, no solo del
    # estudio.
    "pyarrow>=15.0.0",
    # Motor de fundamentales: XBRL de 10-Q/10-K desde SEC, gratis y sin API
    # key. Necesita EDGAR_IDENTITY, que la app pide por pantalla.
    "edgartools>=5.0",
    # Fichas del sub-proyecto B. Sin ANTHROPIC_API_KEY el ranking sale igual,
    # con fichas de plantilla.
    "anthropic>=0.100",
    "pydantic>=2.0",
]

[dependency-groups]
# Nada de esto hace falta para abrir la app. Quien reciba el proyecto solo
# para usarlo no lo descarga.
dev = [
    "pytest>=8.0.0",
    # Solo tests: valida nuestra implementacion nativa de Ledoit-Wolf contra
    # la de referencia (tests/test_estimators.py:84). El test se omite solo si
    # no esta instalado.
    "scikit-learn>=1.4.0",
    # Solo tests: contrasta nuestros indicadores nativos contra una
    # implementacion de referencia (tests/test_research_indicators.py:146).
    "pandas-ta-classic>=0.4.0",
    # Solo para regenerar el snapshot del universo y la tabla de sectores
    # (scripts/bootstrap_*.py, que usan pandas.read_html).
    "lxml>=5.0",
]

[tool.uv]
# Esto es una aplicacion, no una libreria: no hay paquete que construir ni
# instalar, solo un entorno con dependencias.
package = false
```

- [ ] **Step 2: Fijar la versión de Python**

Crear `.python-version` con una sola línea:

```
3.12
```

Se fija 3.12 y no la 3.14 de la máquina de desarrollo por cobertura de ruedas precompiladas: si a alguien le toca compilar scipy desde fuente, el primer arranque pasa de dos minutos a una tarde.

- [ ] **Step 3: Ignorar el entorno que crea uv**

Añadir al final de `.gitignore`:

```
.venv/
```

`uv.lock` **no** se ignora: es lo que hace que todos instalen las mismas versiones.

- [ ] **Step 4: Generar el lock y el entorno**

```bash
uv sync
```

Esperado: descarga Python 3.12 si no está, resuelve las dependencias y escribe `uv.lock`.

- [ ] **Step 5: Comprobar que la suite entera pasa bajo uv**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: los mismos tests que pasaban con el Python del sistema. Si alguno falla aquí y no fallaba antes, es un problema real de versión de dependencia: hay que resolverlo antes de seguir, no dejarlo pasar.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock
git commit -m "build: declarar el proyecto para uv con lock commiteado"
```

---

## Task 10: `requirements.txt` regenerado

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Regenerar desde el lock**

```bash
uv export --no-hashes --no-dev -o requirements.txt
```

- [ ] **Step 2: Añadir la cabecera que dice que es generado**

Insertar al principio del fichero:

```
# FICHERO GENERADO -- no editar a mano.
# La fuente de verdad es pyproject.toml. Para regenerarlo:
#   uv export --no-hashes --no-dev -o requirements.txt
#
# Existe solo para quien no quiera usar uv. El camino soportado es el
# lanzador ("Iniciar App.bat" o "Iniciar App.command"), que usa uv y el lock.
```

- [ ] **Step 3: Comprobar que el fichero tiene sentido**

```bash
head -20 requirements.txt
```

Esperado: la cabecera, y después las dependencias de runtime con versiones exactas. **No** debe aparecer pytest, scikit-learn, pandas-ta-classic ni lxml.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: regenerar requirements.txt desde el lock"
```

---

## Task 11: Los dos lanzadores

**Files:**
- Modify: `Iniciar App.bat`
- Create: `Iniciar App.command`

- [ ] **Step 1: Reescribir `Iniciar App.bat`**

Sin acentos ni caracteres no ASCII: la consola de Windows usa una página de códigos que los rompe.

```bat
@echo off
cd /d "%~dp0"

rem Recien instalado, uv queda en %USERPROFILE%\.local\bin, que no esta en el
rem PATH de esta ventana. Sin esta linea el primer arranque falla justo
rem despues de una instalacion que acaba de decir que fue bien.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>&1
if not errorlevel 1 goto arrancar

echo.
echo Este programa necesita "uv", una herramienta que instala Python y las
echo librerias necesarias por ti. Ahora mismo no lo tienes.
echo.
echo Se descargaria del sitio oficial: https://astral.sh/uv
echo.
set /p RESPUESTA="Quieres instalarlo ahora? (s/n): "
if /i "%RESPUESTA%"=="s" goto instalar

echo.
echo De acuerdo, no se ha instalado nada. Puedes instalarlo tu mismo desde
echo https://docs.astral.sh/uv/getting-started/installation/
echo y volver a ejecutar este archivo.
echo.
pause
exit /b 1

:instalar
echo.
echo Instalando uv...
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>&1
if not errorlevel 1 goto arrancar
echo.
echo La instalacion no ha salido bien. Instala uv a mano desde
echo https://docs.astral.sh/uv/getting-started/installation/
echo y vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:arrancar
echo.
echo Iniciando Markowitz Pro Picks...
echo.
echo La primera vez tarda unos minutos: hay que descargar Python y las
echo librerias, varios cientos de MB. No cierres esta ventana.
echo.
uv run streamlit run app.py
pause
```

El `goto` en vez de un bloque con paréntesis es deliberado: dentro de un bloque, `%RESPUESTA%` se expandiría al leer el bloque entero, antes de que `set /p` la rellene, y la respuesta del usuario se perdería siempre.

- [ ] **Step 2: Crear `Iniciar App.command`**

```bash
#!/bin/bash
cd "$(dirname "$0")" || exit 1

# Recien instalado, uv queda en ~/.local/bin, que no esta en el PATH de esta
# ventana. Sin esta linea el primer arranque falla justo despues de una
# instalacion que acaba de decir que fue bien.
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo
    echo 'Este programa necesita "uv", una herramienta que instala Python y las'
    echo 'librerias necesarias por ti. Ahora mismo no lo tienes.'
    echo
    echo 'Se descargaria del sitio oficial: https://astral.sh/uv'
    echo
    read -r -p 'Quieres instalarlo ahora? (s/n): ' RESPUESTA
    case "$RESPUESTA" in
        s|S|si|Si|SI|y|Y)
            echo
            echo 'Instalando uv...'
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
            ;;
        *)
            echo
            echo 'De acuerdo, no se ha instalado nada. Puedes instalarlo tu mismo desde'
            echo 'https://docs.astral.sh/uv/getting-started/installation/'
            echo 'y volver a abrir este archivo.'
            echo
            read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
            exit 1
            ;;
    esac

    if ! command -v uv >/dev/null 2>&1; then
        echo
        echo 'La instalacion no ha salido bien. Instala uv a mano desde'
        echo 'https://docs.astral.sh/uv/getting-started/installation/'
        echo
        read -r -n 1 -s -p 'Pulsa una tecla para cerrar.'
        exit 1
    fi
fi

echo
echo 'Iniciando Markowitz Pro Picks...'
echo
echo 'La primera vez tarda unos minutos: hay que descargar Python y las'
echo 'librerias, varios cientos de MB. No cierres esta ventana.'
echo
uv run streamlit run app.py
```

- [ ] **Step 3: Marcar el `.command` como ejecutable en el índice de git**

```bash
git add "Iniciar App.command" && git update-index --chmod=+x "Iniciar App.command"
```

Sin esto, en Mac el doble clic da un error de Finder. Este repo tiene `core.fileMode = false` porque se edita desde Windows, así que un `chmod` en el sistema de ficheros no llegaría al repo: hay que marcarlo en el índice.

- [ ] **Step 4: Comprobar que el modo quedó registrado**

```bash
git ls-files -s "Iniciar App.command"
```

Esperado: la línea empieza por `100755`, no por `100644`.

- [ ] **Step 5: Verificar el lanzador de Windows de verdad**

```bash
cmd /c "Iniciar App.bat"
```

Esperado: uv ya está instalado en esta máquina, así que salta la pregunta, imprime el aviso de espera y Streamlit levanta. Abrir el navegador y confirmar que la app carga. Cerrar con Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add "Iniciar App.bat" "Iniciar App.command"
git commit -m "feat: lanzadores con uv para Windows y Mac"
```

**El `.command` de Mac queda sin ejecutar.** No hay ningún Mac en el entorno de desarrollo. Se entrega con la sintaxis revisada y marcado como no probado; la primera ejecución real en macOS es tarea del usuario. No afirmar que funciona.

---

## Task 12: README para quien recibe el programa

**Files:**
- Create: `README.md`

- [ ] **Step 1: Escribir el README**

```markdown
# Markowitz Pro Picks

Analiza empresas del S&P 500 con datos fundamentales sacados directamente de
sus informes a la SEC, propone un top 10-15 razonado, te deja aprobarlo o
corregirlo a mano, y con esa lista calcula cómo repartir el dinero entre ellas.

**Las decisiones las tomas tú.** El programa propone y deja constancia de lo
que apruebas; no compra ni vende nada, y el orden que produce es un criterio de
selección transparente, no una previsión de rentabilidad.

## Cómo se abre

**Windows:** doble clic en `Iniciar App.bat`
**Mac:** doble clic en `Iniciar App.command`

Si en Mac aparece un error de permisos, abre la Terminal en esta carpeta y
ejecuta una vez:

```
chmod +x "Iniciar App.command"
```

No hace falta instalar Python. La primera vez el programa usa una herramienta
llamada [uv](https://astral.sh/uv) para descargar todo lo que necesita: te
preguntará antes de instalar nada. Esa primera vez tarda unos minutos y baja
varios cientos de MB. Las siguientes, arranca en segundos.

## Las credenciales

El programa funciona en dos mitades:

- **Sin IA — gratis, y no necesita nada.** Descarga los datos de la SEC, calcula
  los KPIs y ordena las empresas.
- **Con IA — cuesta alrededor de 1,25 $ por corrida.** Además redacta una ficha
  por empresa, con una tesis y hasta tres riesgos, cada uno citando textualmente
  el informe original. Cada cita se comprueba contra el documento: si no
  aparece, la ficha lo dice.

Para la segunda mitad hacen falta dos cosas, y se meten desde la propia app, en
**Revisar candidatos → 🔑 Mis credenciales**:

| Qué | De dónde sale |
|---|---|
| Clave de Anthropic | [console.anthropic.com](https://console.anthropic.com) — es tuya y tú pagas su uso |
| Un correo electrónico | El tuyo. La SEC exige un contacto en cada petición; no es un registro y no se envía a nadie más |

Se guardan en tu carpeta personal (`~/.markowitz-pro-picks/`), **no dentro de
esta carpeta**. Si comprimes el programa y se lo pasas a otra persona, tu clave
no viaja dentro.

## Para desarrollar

```
uv sync --all-groups     # entorno con dependencias de desarrollo
uv run pytest tests/ -q -m "not red"
```

Los detalles de diseño están en `CONTEXTO.md` y en `docs/superpowers/specs/`.
```

- [ ] **Step 2: Comprobar que los enlaces y rutas del README existen**

```bash
ls "Iniciar App.bat" "Iniciar App.command" CONTEXTO.md docs/superpowers/specs
```

Esperado: los cuatro existen.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README para quien recibe el programa"
```

---

## Task 13: Actualizar `CONTEXTO.md`

**Files:**
- Modify: `CONTEXTO.md`

- [ ] **Step 1: Añadir la sección de distribución**

Localizar la sección "Qué hay en el repo" y añadir antes de ella:

```markdown
## Cómo se distribuye

El programa se reparte como **repo descargable**, no como URL pública. Cada
usuario corre su copia en su disco con `uv`, que se encarga de Python y las
dependencias: `Iniciar App.bat` en Windows, `Iniciar App.command` en Mac.

Las credenciales (`ANTHROPIC_API_KEY` y `EDGAR_IDENTITY`) se meten desde la
página de candidatos y se guardan en `~/.markowitz-pro-picks/credenciales.json`,
fuera del proyecto — ver `credenciales.py`. El entorno gana sobre el fichero,
así que un shell con las variables puestas sigue mandando.

**No hay URL pública a propósito:** `salidas/` y `actas/` son rutas fijas y
globales del proceso, así que dos visitantes simultáneos se pisarían los datos.
Publicarlo exigiría aislarlas por sesión, que es un trabajo aparte.

Diseño: `docs/superpowers/specs/2026-08-22-compartir-el-programa-design.md`.
```

- [ ] **Step 2: Actualizar la cabecera del fichero**

Cambiar la línea `**Última actualización:** 2026-08-16` por `**Última actualización:** 2026-08-22`, y actualizar el número de tests con lo que devuelva:

```bash
uv run pytest tests/ -q -m "not red"
```

- [ ] **Step 3: Commit**

```bash
git add CONTEXTO.md
git commit -m "docs: reflejar como se distribuye el programa"
```

---

## Verificación final

- [ ] **Suite completa bajo uv**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: todo verde, sin fallos ni errores.

- [ ] **Arranque limpio desde el lanzador**

```bash
cmd /c "Iniciar App.bat"
```

Esperado: Streamlit levanta, la página de candidatos carga, el apartado de credenciales aparece.

- [ ] **Lo que queda sin verificar, y hay que decirlo al entregar**

1. `Iniciar App.command` **no se ha ejecutado en un Mac**. Sintaxis revisada, comportamiento sin comprobar.
2. El bit de ejecución sobrevive a `git clone`; si el programa se distribuye como **ZIP**, puede perderse — por eso el README lleva la línea `chmod +x`.
3. La instalación automática de uv sólo se ha probado en una máquina donde uv **ya estaba instalado**, así que la rama de instalación no se ha recorrido entera.
