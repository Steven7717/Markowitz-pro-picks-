# Compartir el programa — credenciales propias y arranque multiplataforma

**Fecha:** 2026-08-22
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Que el programa se pueda pasar a otra persona y funcione en su máquina, sea
Windows o Mac, sin que quien lo recibe tenga que instalar Python, tocar una
terminal ni pedirle a nadie una clave de API.

Dos piezas independientes:

1. **Credenciales propias.** Un apartado en la página de candidatos donde cada
   usuario mete su clave de Anthropic y su correo para EDGAR. Quedan guardadas
   en su carpeta personal, no dentro del proyecto.
2. **Arranque multiplataforma.** `uv` sustituye al supuesto de "ya tienes Python
   y las dependencias". Un lanzador por sistema: `.bat` en Windows, `.command`
   en Mac.

## Qué NO entrega

**No hay URL pública.** Se descartó publicar la app en un servicio tipo
Streamlit Community Cloud, y no por dificultad de despliegue: `salidas/` y
`actas/` son rutas fijas y globales del proceso
(`aprobacion/carga.py:5`, `ranking/run.py:154`). Con dos visitantes a la vez, el
«Generar» de uno sobrescribe los candidatos que el otro está revisando, y las
actas de todos caen en la misma carpeta. Hacerlo multiusuario exige aislar esas
rutas por sesión, y eso es un sub-proyecto distinto de éste.

Cada usuario corre su copia en su disco. Ahí no hay concurrencia y esas rutas
siguen siendo correctas tal como están.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Distribución | Sólo repo descargable | Sin URL pública no hay problema de concurrencia sobre `salidas/` y `actas/` |
| Dónde se guardan las credenciales | Carpeta personal del usuario (`~/.markowitz-pro-picks/`) | Quien recomprima el proyecto y lo reenvíe no manda su clave dentro: nunca estuvo ahí |
| Precedencia | El entorno gana sobre el fichero | El entorno de desarrollo y los tests siguen mandando; es la convención habitual |
| Validación de la clave | Forma sí, validez no | Verificarla contra la API costaría dinero en cada guardado; la app ya falla de forma visible si es mala |
| Prefijo `sk-ant-` | Avisa, no bloquea | Si Anthropic cambia el formato, este código no debe rechazar claves buenas |
| Dónde vive el módulo | `credenciales.py` en la raíz | Lo consumen `fundamentals/`, `ranking/` y `aprobacion/`; meterlo en uno crearía dependencia hacia arriba |
| Gestor de entorno | `uv` | Se instala solo, baja Python él mismo y fija versiones exactas con un lock |
| Si falta `uv` | Explicar y preguntar s/n | No se descarga nada a espaldas de quien acaba de recibir un ZIP de un conocido |
| Versión de Python | `3.12` pinchada | Cobertura madura de ruedas precompiladas: evita que a alguien le toque compilar scipy |
| Ejecutable nativo (.app/.exe) | Descartado | Exige compilar en cada sistema y, en Mac, firmar y notarizar (99 $/año) o Gatekeeper lo bloquea |

## Parte 1 — Credenciales

### Arquitectura

```
~/.markowitz-pro-picks/credenciales.json
              │
              ▼
        credenciales.py ──aplicar()──→ os.environ
              │                            │
              │                            ├─→ anthropic.Anthropic()   (ranking/llm.py:174)
              ▼                            └─→ edgartools               (lee EDGAR_IDENTITY solo)
   pages/1_Revisar_candidatos.py
              │
              └─→ aprobacion.generacion.disponibilidad()  (sin cambios)
```

Hallazgo que mantiene el cambio pequeño: **nadie llama a
`fundamentals/fetch.py:set_sec_identity()` en el camino de producción**, sólo los
tests. edgartools lee `EDGAR_IDENTITY` del entorno por su cuenta, igual que el
cliente de Anthropic lee `ANTHROPIC_API_KEY`. Poblar `os.environ` basta para los
tres consumidores actuales, sin tocar ninguno.

### Módulo `credenciales.py`

Vive en la raíz, junto a `data.py` y `charts.py`. Contrato calcado del patrón de
`aprobacion/carga.py`:

- `RUTA = Path.home() / ".markowitz-pro-picks" / "credenciales.json"`
- `cargar() -> Credenciales` — dataclass congelada con `api_key` y
  `edgar_identity`, ambos `str | None`.
- `guardar(credenciales) -> Path` — escritura atómica (`.tmp` + `replace`), igual
  que `aprobacion/acta.py:guardar_acta`, y `chmod 600` donde el sistema lo
  respeta.
- `borrar()` — elimina el fichero.
- `aplicar(credenciales, entorno=None)` — vuelca en `os.environ` **sin pisar** lo
  que ya venga puesto.

**Ausente y roto son cosas distintas.** Si el fichero no existe, `cargar()`
devuelve credenciales vacías: eso es un usuario nuevo, no un error. Si existe
pero no se puede leer, lanza `ConfigIlegible`, del mismo modo que `carga.py`
distingue `FaltanFichas` de `ContratoRoto`. Tratar ambos casos igual escondería
un fallo real detrás de una pantalla que parece limpia.

**Validación de forma, nunca de validez.** El correo debe parecer un correo — la
SEC rechaza un `User-Agent` sin contacto. La clave no puede venir vacía ni con
espacios. Si no empieza por `sk-ant-` se avisa pero se guarda igual.

### El apartado en la página

Un `st.expander("🔑 Mis credenciales")` en `pages/1_Revisar_candidatos.py`, justo
debajo del bloque de generación, donde hoy aparece `st.caption(puede.motivo)`.
Desplegado por defecto cuando falta alguna credencial, plegado cuando están las
dos.

**La página llama a `aplicar(cargar())` al principio, antes de
`disponibilidad()`.** Sin eso, lo guardado ayer no tendría efecto hoy: el
fichero existiría y la app seguiría diciendo que falta la clave. Guardar es lo
que escribe; arrancar es lo que carga, y hacen falta los dos.
Un `ConfigIlegible` en ese punto no detiene la página: se muestra un aviso y se
sigue con la mitad gratis, porque un fichero de configuración corrupto no debe
dejar a nadie sin optimizador.

- Clave con `type="password"`. Una vez guardada **no se vuelve a mostrar**: se
  enseña enmascarada (`sk-ant-…4f2a`) junto a los botones «Cambiar» y «Borrar».
  La clave completa nunca regresa al HTML.
- Texto que explique el origen de cada una: la clave sale de
  `console.anthropic.com`; el correo **no es un registro** — la SEC exige un
  contacto en la cabecera y sólo viaja ahí.
- Al guardar: `guardar()`, `aplicar()` y `st.rerun()`, para que
  `disponibilidad()` relea y la opción «Con IA» aparezca sola.
- Si las credenciales vienen del entorno, el apartado lo dice, para que no
  parezca que el fichero hace algo que no está haciendo.

`aprobacion/generacion.py:disponibilidad()` **no se toca**: ya acepta un
`entorno` inyectable y sigue leyendo `os.environ`. Lo único nuevo es quién lo
puebla.

**Salvedad:** `os.environ` es global al proceso. Con un usuario en su portátil
da igual. Si esto llegara alguna vez a una URL compartida, esta decisión habría
que rehacerla — y va anotada aquí para que quien la encuentre sepa que fue
deliberada y bajo qué supuesto.

## Parte 2 — Arranque multiplataforma

### Qué declara el proyecto

`pyproject.toml` nuevo en la raíz, con dos grupos. El corte está **verificado
import por import**, no repartido de memoria:

- **Runtime** — streamlit, yfinance, numpy, scipy, pandas, plotly, fpdf2,
  openpyxl, kaleido (`exporter.py:109` exporta imágenes al PDF), edgartools,
  anthropic, pydantic y **pyarrow** (`fundamentals/fetch.py:130` cachea el panel
  en parquet, y eso está en el camino vivo de generar candidatos).
- **dev** — pytest, scikit-learn (`tests/test_estimators.py:84`),
  pandas-ta-classic (`tests/test_research_indicators.py:146`) y lxml (sólo
  `scripts/bootstrap_*.py`).

Quien recibe el ZIP no descarga scikit-learn ni pandas-ta para abrir la app.

`.python-version` con `3.12`. uv se descarga esa versión él solo, sin interferir
con el Python del sistema de nadie.

`uv.lock` commiteado: todos instalan exactamente las mismas versiones. En un
proyecto cuyo argumento central es que el ranking es determinista, dejar que las
dependencias bailen entre máquinas sería una grieta justo debajo de esa
afirmación.

`requirements.txt` se conserva, regenerado con `uv export` y con una cabecera que
declare que es un fichero generado, para quien no quiera usar uv.

### Los lanzadores

`Iniciar App.bat` reescrito y `Iniciar App.command` nuevo. Ambos hacen lo mismo:
ir a su propia carpeta, comprobar si `uv` está, y si no está explicar qué es y de
dónde se baja y **esperar un sí o un no**; luego `uv run streamlit run app.py`.

El `.bat` actual da por ciertas dos cosas que en una máquina ajena no lo son:
que Python está instalado y que las dependencias también — no las instala. Y
`py` es el lanzador de Windows, que en macOS no existe.

Dos detalles que, omitidos, rompen precisamente el primer arranque:

- **El PATH.** Recién instalado, `uv` queda en `~/.local/bin`, que no está en el
  PATH de la ventana ya abierta. Si el lanzador no lo añade él mismo antes de
  seguir, el primer arranque falla justo después de una instalación que acaba de
  informar de que fue bien.
- **El aviso de espera.** La primera vez uv descarga Python y varios cientos de
  MB de ruedas. Sin un mensaje que lo anuncie, el usuario cree que se colgó y lo
  mata a mitad.

### El bit de ejecución en Mac

Un `.command` sin permiso de ejecución **no arranca con doble clic**: Finder
devuelve un error. Este repo tiene `core.fileMode = false` (se edita desde
Windows), así que un `chmod` hecho en el sistema de ficheros no se propagaría al
repo por sí solo.

Se resuelve marcándolo en el índice de git:

```
git update-index --chmod=+x "Iniciar App.command"
```

Así el modo viaja dentro del repo aunque el fichero se edite desde Windows, y un
`git clone` en Mac lo deja ejecutable.

**Salvedad, dicha en vez de prometida:** si en lugar de clonar se descarga un
ZIP, el permiso puede perderse según cómo se genere ese ZIP. Por eso el README
incluye la línea de rescate `chmod +x "Iniciar App.command"` en lugar de dar por
hecho que nunca hará falta.

### README

Hoy no existe ninguno — sólo `CONTEXTO.md`, que está escrito para retomar el
desarrollo, no para alguien que acaba de recibir el programa. Hace falta uno que
cubra: qué es, que basta con hacer doble clic, qué ocurre la primera vez y cuánto
tarda, dónde se pone la clave, y qué cuesta — la mitad sin IA es gratis y la
corrida con IA ronda 1,25 $ (`aprobacion/generacion.py:COSTE_APROXIMADO_USD`).

## Pruebas

`tests/test_credenciales.py`, sin red y sin arrancar Streamlit, como el resto de
`aprobacion/`:

- Ida y vuelta con `tmp_path`: lo guardado se lee igual.
- Fichero ausente devuelve credenciales vacías; fichero corrupto lanza
  `ConfigIlegible`.
- `aplicar()` no pisa una variable que ya venga del entorno.
- La escritura atómica deja intacto el fichero anterior si el guardado falla a
  medias.

**Los lanzadores no van a pytest.** Un test que comprobase que un `.bat` contiene
ciertas líneas no verifica nada: sería exactamente la clase de test que no puede
fallar que este proyecto ya se ha encontrado antes.

Verificación real, y sus límites:

- El `.bat` **se ejecuta de verdad** en la máquina de desarrollo (uv 0.11.24 ya
  está instalado ahí) y se comprueba que la app levanta.
- El `.command` de Mac **no se puede ejecutar** desde el entorno de desarrollo:
  no hay ningún Mac disponible. Se entrega con la sintaxis revisada y **marcado
  explícitamente como no probado en Mac**. La primera ejecución real en macOS es
  una tarea pendiente para el usuario o para alguien con acceso a un Mac; el
  README y el mensaje de entrega deben decirlo, no darlo por bueno.

## Alternativas descartadas

- **Ejecutable nativo (PyInstaller / py2app).** Es lo único que elimina Python
  del cuadro de verdad, pero hay que compilar por separado en cada sistema —el
  binario de Mac no se puede generar desde Windows—, el bundle ronda los cientos
  de MB, y sin firmar y notarizar con cuenta de Apple Developer (99 $/año) el
  usuario de Mac se topa con «no se puede abrir, no se pudo verificar el
  desarrollador». uv da la mayor parte de la comodidad por una fracción del
  trabajo, y es mantenible en solitario desde Windows sin comprar nada.
- **Docker.** Exige instalar Docker Desktop, que es una barrera mayor que
  instalar Python.
- **Credenciales en un `.env` dentro del proyecto.** Más fácil de editar a mano,
  pero quien reenvíe la carpeta comprimida manda su clave dentro sin enterarse:
  `.gitignore` protege de git, no de un ZIP.
- **No guardar las credenciales.** Lo más seguro posible y lo más incómodo:
  pegar la clave en cada arranque.
