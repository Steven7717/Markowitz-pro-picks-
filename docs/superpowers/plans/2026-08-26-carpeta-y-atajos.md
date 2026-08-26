# Carpeta limpia y atajos con icono — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la carpeta descargada muestre cuatro elementos en vez de veintidós, y que el programa tenga icono propio en la app y en un acceso directo del Escritorio.

**Architecture:** Todo salvo los dos lanzadores y el README se mueve a `programa/` con `git mv`. Los lanzadores hacen el `git pull` desde la raíz —donde está `.git`— y entran en `programa/` después, así que ninguna ruta de Python cambia. El icono va a `page_icon` de Streamlit y a un atajo que cada lanzador genera en la máquina del usuario.

**Tech Stack:** Batch (Windows), Bash (macOS), Python 3.12, Streamlit, uv, git.

**Diseño:** `docs/superpowers/specs/2026-08-26-carpeta-y-atajos-design.md`

---

## Antes de empezar

Trabaja en el clon: `C:\Users\esteb\Desktop\Markowitz-pro-picks-`.

Los tests se corren así. **Hasta el Task 1 se corren desde la raíz; a partir de
ahí, desde `programa/`:**

```bash
uv run pytest tests/ -q -m "not red"
```

**Línea base antes de tocar nada:** `688 passed, 2 skipped, 6 deselected`.
Compruébalo primero, para no confundir un fallo tuyo con uno que ya estaba.

**El icono de origen** está en `C:\Users\esteb\Desktop\Proyectos\Markowits Pro picks\icono.ico`
(256×256, 32 bits). Se copia al repo en el Task 2; no se mueve, se copia.

**Lo que NO se toca en ninguna tarea:** el bloque de `git pull` de los dos
lanzadores, ni la comprobación de permisos de macOS, ni la del shebang del
`.venv`. Ese código costó cuatro arreglos que sólo aparecieron en un Mac real.
Lo único que cambia de sitio es *dónde* está el directorio de trabajo cuando se
ejecutan.

---

## Estructura de ficheros

| Fichero | Qué le pasa |
|---|---|
| `Iniciar App.bat` | Se queda en la raíz. Gana `cd programa` y el bloque del atajo |
| `Iniciar App.command` | Se queda en la raíz. Gana `cd programa` y el bloque del atajo |
| `README.md` | Se queda en la raíz. Gana la sección de migración |
| Todo lo demás | A `programa/` con `git mv` |
| `app_icon.ico` | Se borra |
| `programa/icono.ico` | Nuevo |
| `.claude/launch.json` | Se queda en la raíz, con la ruta corregida |

---

## Task 1: Mover el proyecto a `programa/` y adaptar los lanzadores

**Files:**
- Move: 22 elementos de la raíz a `programa/`
- Modify: `Iniciar App.bat`, `Iniciar App.command`

Esta tarea es una sola unidad a propósito: entre el movimiento y el `cd` de los
lanzadores, el programa no arranca. Separarlas dejaría un commit intermedio con
la app rota.

- [ ] **Step 1: Confirmar la línea base**

```bash
uv run pytest tests/ -q -m "not red"
```

Esperado: `688 passed, 2 skipped, 6 deselected`.

- [ ] **Step 2: Borrar el `.venv` de la raíz**

Va a quedar huérfano: `uv` creará uno nuevo dentro de `programa/`, donde estará
`pyproject.toml`. Dejarlo son ~500 MB muertos.

```bash
rm -rf .venv .pytest_cache __pycache__
```

- [ ] **Step 3: Crear la carpeta y mover todo con `git mv`**

`git mv` y no `mv`: git detecta los renombrados y la historia de cada fichero
sigue siendo navegable con `git log --follow`.

```bash
mkdir programa
git mv app.py charts.py credenciales.py data.py estimators.py exporter.py optimizer.py validation.py programa/
git mv aprobacion fundamentals pages ranking research scripts tests docs salidas_ejemplo programa/
git mv pyproject.toml uv.lock requirements.txt pytest.ini programa/
git mv .python-version .streamlit .gitignore programa/
git mv CONTEXTO.md app_icon.ico programa/
```

- [ ] **Step 4: Comprobar que la raíz queda limpia**

```bash
ls
```

Esperado, exactamente cuatro elementos visibles:

```
Iniciar App.bat
Iniciar App.command
README.md
programa
```

- [ ] **Step 5: Comprobar que la suite pasa desde `programa/`**

```bash
cd programa && uv run pytest tests/ -q -m "not red"
```

Esperado: `688 passed, 2 skipped, 6 deselected`. Ninguna ruta de Python se ha
tocado: las de `aprobacion/` (`Path("salidas")`, `Path("actas")`,
`Path("salidas_ejemplo")`) son relativas al directorio de trabajo, y las demás
salen de `Path(__file__)`, que se mueve con su módulo.

- [ ] **Step 6: Añadir el `cd` al `.bat`**

En `Iniciar App.bat`, la etiqueta `:lanzar` es hoy la primera línea después del
bloque de git. Añade el `cd` justo debajo de ella:

```bat
:lanzar
rem El git pull de arriba se hace en la raiz, que es donde esta .git. Entrar en
rem programa/ antes de esa comprobacion la haria fallar --alli no hay .git-- y
rem el pull se saltaria en silencio: el programa arrancaria igual y nadie
rem notaria que dejo de actualizarse.
cd /d "%~dp0programa" || exit /b 1
```

- [ ] **Step 7: Añadir el `cd` al `.command`**

En `Iniciar App.command`, justo después del `fi` que cierra el bloque de `git
pull` (la línea 60 hoy) y antes del comentario sobre `~/.local/bin`:

```sh
# El git pull de arriba se hace en la raiz, que es donde esta .git. Entrar en
# programa/ antes de esa comprobacion la haria fallar --alli no hay .git-- y el
# pull se saltaria en silencio: el programa arrancaria igual y nadie notaria que
# dejo de actualizarse.
#
# Tambien tiene que ir antes de la comprobacion del shebang del .venv, que mira
# .venv/bin/streamlit: ese .venv vive ahora dentro de programa/.
RAIZ="$(/bin/pwd)"
cd programa || exit 1
```

`RAIZ` se guarda aquí porque el Task 4 lo necesita para apuntar el atajo al
lanzador, que se queda en la raíz.

- [ ] **Step 8: Arrancar el `.bat` de cero y comprobar**

Cierra la ventana cuando la app abra en el navegador.

```bash
cmd //c "Iniciar App.bat"
```

Esperado, en este orden: «Buscando actualizaciones…» seguido de «Al dia.» —esa
línea es la que prueba que el `cd` no rompió el `git pull`—, luego la
instalación de las librerías en `programa/.venv`, y la app abriendo.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "refactor: el programa a programa/, la raiz solo con los lanzadores"
```

---

## Task 2: El icono en la app

**Files:**
- Create: `programa/icono.ico`
- Modify: `programa/app.py:28-32`, `programa/pages/1_Revisar_candidatos.py:35`
- Delete: `programa/app_icon.ico`

- [ ] **Step 1: Copiar el icono y borrar el viejo**

```bash
cp "C:/Users/esteb/Desktop/Proyectos/Markowits Pro picks/icono.ico" programa/icono.ico
git rm programa/app_icon.ico
```

`app_icon.ico` no lo referencia ni un `.py`, ni los lanzadores, ni la
configuración — comprobado con `grep` sobre todo el repo. Es un fichero muerto.

- [ ] **Step 2: Sustituir el emoji en `app.py`**

Hoy dice:

```python
st.set_page_config(
    page_title="Markowitz Pro Picks",
    page_icon="📈",
    layout="wide",
)
```

Cámbialo por:

```python
st.set_page_config(
    page_title="Markowitz Pro Picks",
    # Ruta relativa: el lanzador entra en programa/ antes de arrancar, asi que
    # resuelve. Streamlit lo pasa por PIL, que lee .ico sin problema.
    page_icon="icono.ico",
    layout="wide",
)
```

- [ ] **Step 3: Sustituir el emoji en la página de candidatos**

En `programa/pages/1_Revisar_candidatos.py`, hoy:

```python
st.set_page_config(page_title="Revisar candidatos", page_icon="✅", layout="wide")
```

Cámbialo por:

```python
st.set_page_config(page_title="Revisar candidatos", page_icon="icono.ico", layout="wide")
```

- [ ] **Step 4: Comprobar que la suite sigue pasando**

```bash
cd programa && uv run pytest tests/ -q -m "not red"
```

Esperado: `688 passed, 2 skipped, 6 deselected`.

- [ ] **Step 5: Comprobar el icono en el navegador**

Arranca la app y **mira la pestaña**. Esto no se puede razonar: PIL abre el
`.ico` —comprobado— pero eso no prueba que Streamlit lo sirva bien al
navegador. Si sale el icono roto o el de Streamlit por defecto, **para y
avisa**: la salida sería convertirlo a `.png`, no insistir.

```bash
cmd //c "Iniciar App.bat"
```

Esperado: la pestaña del navegador muestra el icono, no un emoji.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: el icono del programa en la pestana, y fuera el que no se usaba"
```

---

## Task 3: El atajo en el Escritorio, en Windows

**Files:**
- Modify: `Iniciar App.bat`

- [ ] **Step 1: Añadir el bloque del atajo**

Va en `:lanzar`, **después** del `cd /d "%~dp0programa"` del Task 1 y antes del
bloque que crea `credentials.toml`:

```bat
rem Un .bat no puede llevar icono propio --lo pone la asociacion del sistema
rem para la extension-- y un .lnk guardado en el repo tampoco sirve: al mover
rem la carpeta deja de resolver, y cada usuario la extrae en un sitio distinto.
rem Generarlo aqui es lo que hace que la ruta absoluta sea la correcta.
rem
rem Se pregunta porque crear un fichero en el Escritorio de alguien sin avisar
rem es invasivo, y este lanzador ya pregunta antes de instalar uv. Y se guarda
rem la respuesta: comprobando solo si el atajo existe, a quien lo borre a
rem proposito se le resucita en cada arranque.
set "MARCA=%USERPROFILE%\.markowitz-pro-picks\atajo.txt"
if exist "%MARCA%" goto sin_atajo
echo.
set /p QUIERE="Quieres un acceso directo en el Escritorio? (s/n): "
if not exist "%USERPROFILE%\.markowitz-pro-picks" mkdir "%USERPROFILE%\.markowitz-pro-picks"
if /i not "%QUIERE%"=="s" (
  > "%MARCA%" echo no
  goto sin_atajo
)
rem GetFolderPath y no %USERPROFILE%\Desktop: con OneDrive el Escritorio real
rem puede estar redirigido, y el atajo acabaria en una carpeta que el usuario
rem no ve.
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'Markowitz Pro Picks.lnk')); $s.TargetPath='%~dp0Iniciar App.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0programa\icono.ico'; $s.Description='Markowitz Pro Picks'; $s.Save()"
> "%MARCA%" echo si
echo Acceso directo creado en el Escritorio.
:sin_atajo
```

Las comillas simples dentro del `-Command` no son un descuido: en un `.bat` no
se pueden anidar comillas dobles dentro de un argumento entrecomillado, y
PowerShell trata `'...'` como literal, que es lo que hace falta.

Dos cosas de este bloque están medidas, no razonadas. La línea de PowerShell se
ejecutó desde un `.bat` real y creó un atajo cuyo destino e icono resuelven
(`Test-Path` a `True` en ambos). Y el flujo de las tres ramas —responder `n`,
responder `s`, y arrancar con la marca ya puesta— se probó por separado: escribe
`no` y salta, escribe `si` y crea, y la tercera vez ni pregunta. La redirección
`>` dentro de los paréntesis del `if` es un sitio donde `cmd` a veces falla en
silencio; aquí no lo hace.

- [ ] **Step 2: Probarlo desde cero**

```bash
rm -f "$USERPROFILE/.markowitz-pro-picks/atajo.txt"
cmd //c "Iniciar App.bat"
```

Esperado: pregunta por el atajo; al responder `s`, dice «Acceso directo creado
en el Escritorio» y el atajo aparece con el icono.

- [ ] **Step 3: Comprobar que no vuelve a preguntar**

Arranca otra vez. Esperado: **no** pregunta, arranca directo.

- [ ] **Step 4: Comprobar que no resucita un atajo borrado**

Borra el atajo del Escritorio a mano y arranca otra vez. Esperado: **no** lo
vuelve a crear y **no** pregunta. Esa es la razón de ser del fichero de marca;
si lo recrea, la comprobación de `%MARCA%` está mal puesta.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: acceso directo en el Escritorio con el icono, en Windows"
```

---

## Task 4: El atajo en el Escritorio, en macOS

**Files:**
- Modify: `Iniciar App.command`

**Esta tarea no se puede verificar desde Windows.** El bloque está diseñado para
degradar sin romper nada: si falta cualquier herramienta, el alias se queda con
el icono genérico y el arranque continúa. Pero si en la prueba en el Mac el
icono no llega a ponerse, **el trozo del icono se borra**: código que aparenta
hacer algo que no hace es peor que no tenerlo, porque el siguiente que lo lea
buscará el fallo en otro sitio.

- [ ] **Step 1: Añadir el bloque del atajo**

Va después del `cd programa` del Task 1 y antes del bloque de
`credentials.toml`:

```sh
# Mismo razonamiento que en el .bat: el .command no puede llevar icono propio
# --en macOS vive en el resource fork, que git no guarda-- y un alias guardado
# en el repo dejaria de resolver al mover la carpeta. Se genera aqui.
MARCA="$HOME/.markowitz-pro-picks/atajo.txt"
if [ ! -f "$MARCA" ]; then
    echo
    read -r -p 'Quieres un acceso directo en el Escritorio? (s/n): ' QUIERE
    mkdir -p "$HOME/.markowitz-pro-picks"
    case "$QUIERE" in
        s|S|si|Si|SI|y|Y)
            ATAJO="$HOME/Desktop/Markowitz Pro Picks"
            ln -sf "$RAIZ/Iniciar App.command" "$ATAJO"
            echo si > "$MARCA"
            echo 'Acceso directo creado en el Escritorio.'

            # El icono es de mejor esfuerzo y NO esta verificado. macOS quiere
            # .icns, no .ico, asi que hay que convertirlo con sips -- que puede
            # no saber leer .ico -- y ponerlo con Rez y SetFile, que vienen con
            # las herramientas de Xcode y pueden no estar instaladas.
            #
            # Cada paso va con guarda: si algo falta o falla, el alias se queda
            # con el icono generico y el arranque sigue. Si al probarlo en un
            # Mac el icono no aparece nunca, borra este bloque entero en vez de
            # dejarlo aparentando que hace algo.
            if command -v sips >/dev/null 2>&1 \
               && command -v Rez >/dev/null 2>&1 \
               && command -v DeRez >/dev/null 2>&1 \
               && command -v SetFile >/dev/null 2>&1; then
                ICNS="$HOME/.markowitz-pro-picks/icono.icns"
                RSRC="$HOME/.markowitz-pro-picks/icono.rsrc"
                if sips -s format icns "$RAIZ/programa/icono.ico" --out "$ICNS" >/dev/null 2>&1 \
                   && sips -i "$ICNS" >/dev/null 2>&1 \
                   && DeRez -only icns "$ICNS" > "$RSRC" 2>/dev/null \
                   && Rez -append "$RSRC" -o "$ATAJO" 2>/dev/null; then
                    SetFile -a C "$ATAJO" 2>/dev/null
                fi
                rm -f "$RSRC"
            fi
            ;;
        *)
            echo no > "$MARCA"
            ;;
    esac
fi
```

- [ ] **Step 2: Comprobar la sintaxis sin ejecutarlo**

Desde Windows sólo se puede comprobar que el script es sintácticamente válido:

```bash
bash -n "Iniciar App.command" && echo "sintaxis ok"
```

Esperado: `sintaxis ok`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: acceso directo en el Escritorio en macOS, con el icono de mejor esfuerzo"
```

- [ ] **Step 4: Probar en un Mac y decidir**

Esto lo hace una persona con un Mac, no el agente. Qué mirar:

1. Que el `.command` arranque igual que antes.
2. Que pregunte por el atajo y lo cree en el Escritorio.
3. Que al arrancar otra vez no vuelva a preguntar.
4. **Si el atajo tiene el icono del programa o el genérico.**

Si es el genérico, borra el bloque `if command -v sips ...` entero y deja sólo
el `ln -sf`.

---

## Task 5: README, `launch.json` y `CONTEXTO.md`

**Files:**
- Modify: `README.md`, `.claude/launch.json`, `programa/CONTEXTO.md`

- [ ] **Step 1: Corregir `launch.json`**

Hoy lanza `streamlit run app.py` sin ruta, así que tras el movimiento no
encuentra el fichero. Cambia el argumento `"app.py"` por `"programa/app.py"`:

```json
"runtimeArgs": ["-m", "streamlit", "run", "programa/app.py", "--server.port", "8501", "--server.headless", "true"],
```

No afecta al programa —es configuración de la vista previa del editor— pero sin
esto el siguiente que la use se topa con un fallo sin causa aparente.

- [ ] **Step 2: Añadir la sección de migración al README**

Al final del `README.md`:

```markdown
## Si vienes de una versión anterior

La estructura cambió: ahora el programa vive dentro de `programa/` y en la
carpeta principal sólo quedan los dos lanzadores y este archivo. Los lanzadores
entran solos donde toca, así que no tienes que hacer nada para usarlo.

Dos restos que puedes limpiar a mano:

- **Un `.venv` en la carpeta principal**, de unos 500 MB. Ya no se usa: el
  nuevo se crea dentro de `programa/`. Bórralo.
- **`salidas/` y `actas/`**, si habías generado rankings antes del cambio. El
  programa ahora los busca en `programa/salidas` y `programa/actas`. Muévelos
  ahí y los vuelves a ver; no se han perdido, sólo están donde ya no se mira.
```

- [ ] **Step 3: Actualizar `CONTEXTO.md`**

En `programa/CONTEXTO.md`, en la cabecera, añade bajo la línea de `Remoto:`:

```markdown
**Estructura:** el programa vive en `programa/`; en la raíz sólo están los dos
lanzadores y el `README.md`. Los comandos (`uv run pytest`, `uv run streamlit`)
se ejecutan desde `programa/`, no desde la raíz.
```

- [ ] **Step 4: Comprobar que todo sigue en pie**

```bash
cd programa && uv run pytest tests/ -q -m "not red"
```

Esperado: `688 passed, 2 skipped, 6 deselected`.

- [ ] **Step 5: Commit y subir**

```bash
git add -A && git commit -m "docs: como migrar de la estructura anterior, y las rutas que cambian"
git push origin master
```

---

## Verificación final

- [ ] **La raíz tiene cuatro elementos visibles**

```bash
ls
```

Esperado: `Iniciar App.bat`, `Iniciar App.command`, `README.md`, `programa`.

- [ ] **La suite pasa desde `programa/`**

```bash
cd programa && uv run pytest tests/ -q -m "not red"
```

Esperado: `688 passed, 2 skipped, 6 deselected`.

- [ ] **Arranque limpio de punta a punta**

Borra `programa/.venv` y el fichero de marca, y ejecuta el `.bat`. Esperado, en
orden: busca actualizaciones y dice «Al dia.», pregunta por el atajo, instala
las librerías, arranca, y la pestaña muestra el icono.

- [ ] **La historia de los ficheros movidos sigue navegable**

```bash
git log --follow --oneline programa/fundamentals/fetch.py | head -3
```

Esperado: los commits del cortacircuitos, no sólo el del movimiento. Si sólo
sale uno, los `git mv` no se registraron como renombrados.
