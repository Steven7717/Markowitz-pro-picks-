# Una carpeta que se entiende al abrirla — lanzadores fuera, programa dentro

**Fecha:** 2026-08-26
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Que quien descargue el programa abra la carpeta y sepa qué hacer sin leer nada.

Hoy ve 22 elementos y sólo dos le sirven. Los otros veinte —`optimizer.py`,
`pyproject.toml`, `uv.lock`, `research/`, `tests/`— no le dicen nada y compiten
por su atención con lo único que necesita, que es hacer doble clic en un
lanzador.

Además, el icono del programa pasa a existir de verdad: en la pestaña del
navegador mientras se usa, y en un acceso directo en el Escritorio para no
tener que buscar la carpeta cada vez.

## Qué NO entrega

**Los lanzadores no llevan icono propio, y no pueden.** En Windows el icono de
un `.bat` lo pone la asociación del sistema para esa extensión: es el mismo para
todos los `.bat` de la máquina y no hay forma de incrustar uno dentro. En macOS
el icono de un fichero vive en su *resource fork*, que git no almacena, así que
tampoco viajaría en el repo.

**Tampoco se guarda un `.lnk` en el repo.** Se probó: un acceso directo creado
con una ruta absoluta deja de resolver en cuanto la carpeta se mueve, y el
programa se distribuye en ZIP y acaba en una ruta distinta en cada máquina.

```
TargetPath tras mover la carpeta: C:\...\Temp\lnktest\sub\destino.bat
existe ese destino?               False
```

Por eso el atajo se **genera en la máquina del usuario** en el primer arranque,
donde la ruta absoluta sí es la correcta.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Qué queda visible en la raíz | Los dos lanzadores y `README.md` | El README en la raíz es lo que GitHub muestra como portada del repo; moviéndolo, quien entre a la página ve una lista de ficheros y ninguna explicación. Y junto a dos lanzadores es justo lo que alguien busca si duda cuál abrir |
| Nombre de la carpeta | `programa` | Se lee en español sin ambigüedad. Junto a «Iniciar App», la lectura completa es «esto lo abres, esto es el programa». Se descartó `app` porque invita a hacer doble clic y daría rutas como `app/app.py` |
| Dónde va `.gitignore` | Dentro de `programa/` | Git admite `.gitignore` anidados y sus rutas son relativas al fichero, así que `research/.cache/` y las demás siguen valiendo sin tocarlas. Dejarlo en la raíz obligaría a prefijar cuatro rutas a mano |
| Migración de quien ya tenga la carpeta | Documentada en el README | La población afectada son dos personas y ninguna tiene rankings guardados. Meter lógica de migración en dos lanzadores que hay que mantener en paralelo —y uno sólo se puede probar en un Mac— no se justifica |
| Dónde vive el icono | En la app y en un atajo generado | Es lo único que funciona igual en los dos sistemas y viaja en el repo |
| Cuándo se crea el atajo | Preguntando la primera vez | Crear un fichero en el Escritorio de alguien sin avisar es invasivo, y el `.bat` ya pregunta antes de instalar `uv` |
| `app_icon.ico` | Se borra | No lo referencia ni un `.py`, ni los lanzadores, ni la configuración. Fichero muerto |

## La estructura

```
Markowitz-pro-picks-/
├── Iniciar App.bat
├── Iniciar App.command
├── README.md
└── programa/
    ├── app.py, charts.py, data.py, estimators.py, exporter.py,
    │   optimizer.py, validation.py, credenciales.py
    ├── aprobacion/  fundamentals/  pages/  ranking/  research/
    ├── scripts/  tests/  docs/  salidas_ejemplo/
    ├── pyproject.toml  uv.lock  requirements.txt  pytest.ini  .python-version
    ├── .streamlit/  .gitignore
    ├── CONTEXTO.md
    └── icono.ico
```

De 22 elementos visibles a 4. `.git/` y `.claude/` siguen en la raíz, ocultos.

`.claude/launch.json` lanza `streamlit run app.py` sin ruta, así que después del
movimiento no encuentra el fichero. Se le pone `programa/app.py`. Es
configuración de herramienta y no afecta al programa, pero si no se toca, el
siguiente que use la vista previa se encontrará con un fallo sin causa aparente.

Cada elemento se mueve con `git mv`, para que git detecte los renombrados y la
historia de cada fichero siga siendo navegable.

## El orden dentro de los lanzadores importa

Los dos hacen hoy, en este orden: entrar en la carpeta del script, comprobar si
existe `.git` y actualizar, arrancar.

El cambio obvio —entrar directamente en `programa/`— **rompe la
autoactualización en silencio**. Desde `programa/` no existe `.git`, la
comprobación falla, el `git pull` se salta entero y el programa arranca igual.
Nadie lo notaría: simplemente dejaría de recibir actualizaciones.

La estructura correcta entra más tarde:

```
cd <carpeta del script>      la raíz, donde está .git
git pull                      sin tocar una línea
cd programa
crear el atajo si toca
arrancar streamlit
```

Así el bloque de git queda intacto, lo que importa porque el `.command` ya
costó cuatro arreglos que sólo aparecieron en un Mac real.

## Las rutas se arreglan solas

`Path("salidas")`, `Path("actas")` y `Path("salidas_ejemplo")` en
`aprobacion/`, y `.streamlit/config.toml`, son relativas al directorio de
trabajo. Como el lanzador entra en `programa/` antes de arrancar, todas
resuelven dentro. **No hay que tocar una sola línea de Python por el
movimiento.** Los rankings y las actas pasan a escribirse en
`programa/salidas` y `programa/actas`.

## El icono

`icono.ico` (256×256, 32 bits) va en `programa/` y sustituye a los emojis de
`page_icon` en `app.py` (hoy `📈`) y en `pages/1_Revisar_candidatos.py` (hoy
`✅`). La ruta relativa `"icono.ico"` resuelve porque el directorio de trabajo
es `programa/`.

## El atajo en el Escritorio

**Windows** — verificado. `WScript.Shell` crea el `.lnk` apuntando al propio
`.bat`, con `IconLocation` al `.ico` y `WorkingDirectory` en la raíz:

```
destino: ...\Iniciar App.bat     existe: True
icono:   ...\icono.ico,0         existe: True
```

**macOS** — sin verificar, y con un obstáculo conocido. El alias se hace con
`ln -s`, que es una línea. El icono es lo difícil: macOS no usa `.ico` sino
`.icns`, así que habría que convertirlo con `sips`, y **no consta que `sips`
lea `.ico` de entrada**. Ponerlo exige además `SetFile`, que viene con las
herramientas de Xcode y no está garantizado.

El diseño es de mejor esfuerzo con guarda: si la conversión o `SetFile` faltan
o fallan, el alias se queda con el icono genérico y el arranque continúa. Nunca
rompe nada, pero puede no lograr el icono.

**Si en la prueba en Mac el icono no llega a ponerse, se quita ese trozo.** Un
código que aparenta hacer algo que no hace es peor que no tenerlo: la próxima
persona que lo lea creerá que el icono debería estar y buscará el fallo en otro
sitio.

## Preguntar una vez, y recordar la respuesta

La primera vez que no exista el atajo, el lanzador pregunta. La respuesta se
guarda en `~/.markowitz-pro-picks/atajo.txt`, junto a las credenciales que ya
viven en esa carpeta. Fichero aparte y no un campo dentro de
`credenciales.json`: ese fichero lo lee y lo valida `credenciales.py`, y meterle
un dato que nada tiene que ver con credenciales obligaría a tocar su contrato y
sus tests por una marca de dos estados.

Guardar la respuesta no es adorno. Comprobando sólo «¿existe el atajo?», a quien
lo borre a propósito se le resucita en cada arranque. Con la marca se pregunta
una vez y se respeta lo que contestó, en los dos sentidos.

## Verificación

1. Borrar el `.venv`, ejecutar el `.bat` de cero: instala, **actualiza** (la
   parte que el orden equivocado habría roto), pregunta por el atajo, arranca.
2. El atajo aparece en el Escritorio con el icono y abre el programa.
3. Volver a arrancar: no vuelve a preguntar.
4. Borrar el atajo y arrancar: no lo resucita.
5. `uv run pytest tests/ -q -m "not red"` desde `programa/`: 688 pasando.
6. **Que Streamlit sirva el `.ico` como `page_icon`.** PIL lo abre —comprobado—
   pero eso no prueba que Streamlit lo entregue bien al navegador. Se comprueba
   mirando la pestaña, no razonándolo.
7. En un Mac: que el `.command` arranque, que el alias aparezca, y si el icono
   llega a ponerse o no.

## Lo que cambia para quien desarrolla

Los comandos pasan a ejecutarse desde `programa/`, no desde la raíz. Es el único
coste del cambio, y recae en quien mantiene el proyecto y no en quien lo usa
— que es la dirección correcta.
