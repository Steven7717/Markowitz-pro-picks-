# Contexto del proyecto — para retomar en una sesión nueva

**Última actualización:** 2026-08-26
**Rama:** `master` · **Tests:** 688 pasando (`uv run pytest tests/ -q -m "not red"`), 2 omitidos en Windows (permisos POSIX), más 6 marcados `red`
**Remoto:** `https://github.com/Steven7717/Markowitz-pro-picks-.git` — `master` es lo publicado
**Estructura:** el programa vive en `programa/`; en la raíz sólo están los dos
lanzadores y el `README.md`. Los comandos (`uv run pytest`, `uv run streamlit`)
se ejecutan desde `programa/`, no desde la raíz.

> **Al retomar:** la copia local puede estar todavía en `compartir-el-programa`,
> que ya está contenida en `master`. Lo actual y lo publicado es `master`.

---

## Qué es este proyecto

**Markowitz Pro Picks** es una app Streamlit que recibe una lista de tickers y devuelve la asignación óptima de pesos (máximo Sharpe, mínima varianza, paridad de riesgo), con validación out-of-sample y exportación a PDF/Excel.

El objetivo mayor es construir, **aguas arriba de esa app**, un sistema donde uno o más agentes de IA analicen un universo de activos con análisis fundamental, entreguen un top 10–15 razonado, el usuario lo apruebe, y esa lista alimente el optimizador.

## Descomposición en sub-proyectos

| # | Sub-proyecto | Entrega | Estado |
|---|---|---|---|
| A | Universo + motor de fundamentales | Ingesta determinista de KPIs trimestrales | ✅ **terminado** |
| B | Agente(s) de análisis y ranking | Top 10–15 con razones trazables | ✅ **terminado** |
| C | Handoff + gate de aprobación | UI de revisión → tickers al optimizador | ✅ **terminado** |
| D | ¿El análisis técnico aporta ventaja? | Veredicto reproducible | ✅ **terminado** |
| E | Módulo de timing de entrada | — | ❌ **descartado por D** |

## Resultado del sub-proyecto D

**Ninguna de las siete señales técnicas evaluadas tiene ventaja.** Ni momentum 12-1, ni reversión a 1 mes, ni RSI, MACD, distancia a SMA200, breakout de 52 semanas o posición en banda de Bollinger. En ningún horizonte (1, 5, 21, 63 días).

Documentos:
- [`docs/research/criterio-preregistrado.md`](docs/research/criterio-preregistrado.md) — congelado en `cd4db7e` **antes** de escribir código de medición, con dos enmiendas fechadas anexadas debajo. El texto original sigue verificable con `git show cd4db7e:docs/research/criterio-preregistrado.md`.
- [`docs/research/2026-08-06-veredicto-senales-tecnicas.md`](docs/research/2026-08-06-veredicto-senales-tecnicas.md) — resultados.
- [`docs/research/2026-08-06-diagnostico-puerta-b.md`](docs/research/2026-08-06-diagnostico-puerta-b.md) — análisis posterior de por qué el control aleatorio pasó la Puerta B.

Hallazgo clave del diagnóstico: la Puerta B tiene un sesgo positivo de ~0.04 de Sharpe que viene de **dispersión de entradas** (repartir compras en días distintos baja la varianza de la canasta), no de habilidad. Leídas contra el control en vez de contra cero, **seis de las siete señales quedan por debajo del ruido**.

**No hace falta la fase 2** (universo point-in-time). Sólo era necesaria si algo salía positivo: el sesgo de supervivencia infla los resultados, así que un veredicto negativo con el sesgo a favor es más firme, no menos.

---

## Cómo se distribuye

El programa se reparte como **repo descargable**, no como URL pública. Cada
usuario corre su copia en su disco con `uv`, que se encarga de Python y las
dependencias: `Iniciar App.bat` en Windows, `Iniciar App.command` en Mac.

**Se reparte por `git clone`, no por ZIP** (2026-08-26). Un ZIP no guarda
vínculo con el repo: quien lo baja se queda en esa versión para siempre y no hay
forma de hacerle llegar nada. Con un clon, los dos lanzadores hacen `git pull
--ff-only` al arrancar y el usuario se actualiza sin aprender ningún comando. El
`--ff-only` es deliberado: avanza el puntero si se puede y no hace nada más, así
que nunca fabrica un merge ni pisa ficheros de nadie. Un fallo de red no puede
impedir abrir el programa — se avisa y se arranca con lo que haya. El ZIP se
sigue soportando (sin `.git` el bloque entero se salta), documentado como la vía
de quien no pueda instalar git.

Para que eso funcione hubo que **sacar `salidas/` del repo**: sus cuatro ficheros
estaban versionados y la app los sobrescribe en cada corrida, así que cualquiera
que usara el programa pasaba a tener cambios locales sobre ficheros del repo, y
el primer commit que tocara `salidas/` le bloqueaba la actualización. El ejemplo
—que existe para que quien acaba de clonar vea una lista real sin pagar una
corrida con IA— se conserva en `salidas_ejemplo/`, versionado. `cargar_candidatos()`
cae a él solo por el camino por defecto: quien pasa un directorio a mano está
diciendo exactamente dónde mirar, y sustituírselo convertiría un fallo en un
falso verde.

Las credenciales (`ANTHROPIC_API_KEY` y `EDGAR_IDENTITY`) se meten desde la
página de candidatos y se guardan en `~/.markowitz-pro-picks/credenciales.json`,
fuera del proyecto — ver `credenciales.py`. El entorno gana sobre el fichero,
así que un shell con las variables puestas sigue mandando.

**No hay URL pública a propósito:** `salidas/` y `actas/` son rutas fijas y
globales del proceso, así que dos visitantes simultáneos se pisarían los datos.
Publicarlo exigiría aislarlas por sesión, que es un trabajo aparte.

**El `.command` de Mac ya se probó en un Mac real** (2026-08-26, macOS 12.7.6
Intel, llegado como ZIP desde Safari). Arranca, instala y abre la app. Hicieron
falta cuatro arreglos, y la lista de sospechosos que había aquí acertó poco:

- **Sin permiso sobre la carpeta, uv muere sin decir nada útil.** El proyecto
  estaba en `~/Downloads`, que macOS protege. El `cd` del script funciona igual
  —`chdir` no lee la carpeta— pero uv pide su directorio de trabajo nada más
  arrancar y se cae con `Current directory does not exist`, que no menciona ni
  permisos ni carpetas. Ahora el lanzador lo comprueba antes con `/bin/pwd`, que
  es un proceso hijo llamando a `getcwd()` igual que uv, y explica las dos
  salidas en castellano.
- **Streamlit se para a pedir un email por consola** la primera vez y deja la
  ventana colgada sin explicación. El lanzador crea
  `~/.streamlit/credentials.toml` si no existe, que es la forma oficial de
  declinar.
- **Mover la carpeta rompe el entorno.** Los lanzadores de `.venv/bin` llevan la
  ruta absoluta en el shebang, así que al cambiarla de sitio uv falla con
  `Failed to spawn: streamlit`, que suena a dependencia ausente y no lo es. El
  lanzador compara el shebang con dónde está y rehace el `.venv` si no cuadran
  (con la caché caliente, un segundo).
- **Los errores se perdían.** Terminal cierra la ventana al acabar un `.command`,
  así que cualquier fallo desaparecía antes de poder leerlo. Ahora se para a
  esperar una tecla.

Lo que **no** dio problema: Gatekeeper, que era el primer sospechoso de esta
lista — abrir el `.command` por su ruta desde Terminal no pasa por el diálogo de
Finder. Y el `chmod +x` tampoco hizo falta: el ZIP conservó el bit de ejecución.
Las dos cosas siguen documentadas en el README porque quien haga doble clic
desde Finder sí puede encontrárselas.

**Lo que sigue sin probarse en un Mac es el acceso directo del Escritorio y su
icono:** ese bloque se escribió después de aquella prueba y aquí no hay forma de
ejecutarlo. Al probarlo allí hay que mirar que Finder abra con Terminal el
`.command` que aparece en el Escritorio —es un envoltorio de dos líneas con la
ruta real dentro, y no un enlace simbólico, porque `bash` no resuelve enlaces en
`$0` y el lanzador se orienta con `dirname "$0"`—, que desde él arranque la app,
y que el icono salga. Si el icono no aparece, se borra entero el bloque
`sips`/`Rez`/`SetFile` junto con `programa/icono.icns`, en vez de dejar código
que aparenta hacer algo.

Con esto **la puerta a la siguiente fase está abierta**: toca el rediseño visual
de la interfaz.

Diseño: `docs/superpowers/specs/2026-08-22-compartir-el-programa-design.md`.

## Qué hay en el repo

### La app (no la toca el estudio)
```
app.py           UI Streamlit
data.py          descarga de precios (yfinance, @st.cache_data, sólo Close)
optimizer.py     Markowitz: max Sharpe / mín varianza / paridad de riesgo
estimators.py    Ledoit-Wolf + James-Stein
validation.py    walk-forward out-of-sample
charts.py        Plotly
exporter.py      PDF (fpdf2) + Excel (openpyxl)
```

### El paquete del estudio
```
research/
├── universe.py     snapshot congelado de 503 miembros del S&P 500
├── loader.py       panel OHLCV con caché parquet, reporte de cobertura
├── indicators.py   RSI, MACD, SMA, máximo móvil, Bollinger — sin desplazamientos
├── signals.py      8 señales + disparos, todas por _as_of (un solo shift)
├── costs.py        escenarios 5/10/25 bps, rotación
├── evaluation.py   Puerta A: IC, Newey-West, quintiles, Benjamini-Hochberg
├── timing.py       Puerta B: entrada forzosa, bootstrap por bloques
├── report.py       veredicto de doble puerta
└── run.py          orquestación
scripts/bootstrap_universe.py   regenera el snapshot (una sola vez)
```

Correr el estudio: `python -m research.run` (~5 min; la segunda vez lee de caché en `research/.cache/`, que está en `.gitignore`).

### El motor de fundamentales
```
fundamentals/
├── universe.py     S&P 500 congelado o lista arbitraria de tickers
├── panel.py        tabla larga de SEC → panel trimestral
├── concepts.py     cadenas de conceptos XBRL, medidas sobre 20 emisores
├── fallos.py       de qué clase es un fallo de descarga, y si hay que abortar
├── fetch.py        descarga, caché por ticker, reporte de cobertura, cortacircuitos
├── kpis.py         los 17 KPIs, con guardas de división verificadas
├── sectors.py      GICS y z-score sectorial
└── run.py          orquestación
scripts/bootstrap_sectors.py    regenera la tabla de sectores
```

**Una corrida condenada se rinde en segundos, no en 25 minutos.** Antes, si la
causa era sistémica —la SEC caída, sin red, o una identidad que EDGAR rechaza—
`_load_one` reintentaba tres veces por ticker con `time.sleep` entre intentos, y
sobre 503 tickers eso eran 1509 peticiones y 1509 segundos de espera para acabar
sin nada y sin explicar por qué. Medido, no estimado.

Ahora `fallos.clasificar` lee la excepción de edgartools y `load_facts` decide:
una causa sistémica (429, identidad rechazada, SSL) aborta en el primer ticker;
diez fallos seguidos sin que la SEC entregue datos, o 180 s **de petición** sin
entregarlos, abortan también. Son segundos dentro de la petición y no de reloj
de pared a propósito: un acierto de caché no es espera, y midiendo pared una
corrida sana con la caché caliente acababa condenada. En los tres casos levanta
`CorridaAbortada`, que sube sin que nadie la atrape hasta la página y dice la
causa y qué hacer. Un ticker que falla solo se sigue registrando y saltando: eso
no cambió.

Diseño: [`docs/superpowers/specs/2026-08-24-cortacircuitos-descarga-design.md`](docs/superpowers/specs/2026-08-24-cortacircuitos-descarga-design.md).

Necesita `EDGAR_IDENTITY` en el entorno: la SEC exige un contacto en el User-Agent.

```bash
EDGAR_IDENTITY="tu@correo.com" python -c "from fundamentals.fetch import set_sec_identity; set_sec_identity(); from fundamentals.run import build_panel; p,m,c = build_panel('sp500', con_zscore=True); print(c.summary()); print(p.shape)"
```

Primera corrida ~11 min; con caché, ~2 min (dominados por la descarga de precios). La caché vive en `fundamentals/.cache/`, en `.gitignore`.

---

## Decisiones ya tomadas — no relitigar

- **Enfoque escalonado.** D se corrió primero, con universo actual y sesgo de supervivencia documentado, porque el sesgo infla resultados: un negativo es concluyente sin pagar la corrección cara.
- **`alphalens-reloaded` descartado.** No trae Newey-West, sub-periodos ni Benjamini-Hochberg — la matemática hay que escribirla igual. `scipy.stats.spearmanr` sirve de referencia cruzada del IC.
- **TradingAgents / ai-hedge-fund: referencia arquitectónica, no dependencia.** Producen señales buy/sell por ticker en vez de rankings de candidatos, son no deterministas (misma entrada → distinta salida) y no tienen evidencia publicada de rentabilidad.
- **edgartools es la fuente de A**, no OpenBB. [edgartools](https://github.com/dgunning/edgartools) da XBRL de 10-Q/10-K gratis y sin API key, y trae fecha de presentación. [OpenBB](https://github.com/OpenBB-finance/OpenBB) queda descartado: AGPLv3, y sus proveedores buenos piden API key de pago. yfinance tampoco sirve como fuente — no dice cuándo se publicó cada cifra, así que no permite verificar ausencia de look-ahead; queda como contraste externo en test opcional.
- **GICS, no SIC, para agrupar sectores.** Medido, no argumentado: sobre las 502 empresas del S&P 500 con SIC resuelto, SIC de 4 dígitos deja **87 solas en su grupo**, donde el z-score sectorial vale 0 por construcción y es indistinguible de "esta empresa es el promedio de su sector". GICS Sector no deja ninguna: 11 grupos, mínimo 21 empresas. Detalle y tabla completa en el diseño de A.
- **El snapshot de universo de D no se regenera.** `research/data/sp500_members_2026-08-05.csv` es la membresía contra la que reproduce el estudio; regenerarlo la cambiaría. Los sectores van en un fichero nuevo y aparte.
- **Los múltiplos se cotizan en la fecha de publicación, no al cierre del trimestre.** Un trimestre que cierra el 31 de marzo no es público hasta que se presenta el 10-Q, semanas después. Cotizar al cierre es look-ahead.
- **B no admite backtest honesto.** Los LLM ya conocen lo que pasó con estas acciones en su entrenamiento; ver [Look-Ahead-Bench](https://arxiv.org/abs/2601.13770). Cualquier validación histórica de los agentes estará contaminada. Hay que diseñar B sabiéndolo.
- **Los agentes proponen, nunca ejecutan.** El gate humano de C no es opcional.

---

## Estándares metodológicos establecidos — aplicarlos a A, B y C

Lo que hizo creíble el resultado de D, y que conviene repetir:

1. **Congelar el criterio antes de medir**, en un commit propio. La fecha del commit es la prueba de que el umbral no se movió al ver los números.
2. **Control negativo obligatorio.** Ruido con la misma forma que la señal real. Si pasa el criterio, el criterio está mal calibrado y ningún otro número es interpretable. En D esto funcionó: el control quedó limpio en la Puerta A (IC entre −0.0007 y +0.0009) y delató un sesgo de diseño en la Puerta B.
3. **Referencia positiva.** Algo que la literatura dice que existe, para verificar que el aparato detecta efectos cuando los hay.
4. **Implementación nativa + contraste contra una librería externa** en test opcional que se omite solo si no está instalada. Patrón ya usado con Ledoit-Wolf/scikit-learn y con RSI/pandas-ta-classic.
5. **Enmiendas fechadas, nunca ediciones.** Si el código diverge del criterio congelado, se anexa una enmienda debajo que diga qué decía el texto, qué hace el código, por qué difieren y **en qué dirección afecta a la conclusión**. No se toca el original.

---

## Trampas encontradas durante D (siete defectos reales)

Todos estaban en código escrito con cuidado y revisado a ojo. Ninguno era visible leyendo:

| Defecto | Cómo se detectó |
|---|---|
| Caché parquet truncada envenena todas las corridas siguientes | Un revisor truncó un archivo a propósito |
| RSI mal sembrado — hasta 43 puntos de error durante ~240 observaciones | Contraste contra `pandas-ta-classic` |
| Guard de varianza que nunca dispara (devolvía t = 3.6e16) | Test con serie constante |
| Costes cobrados sólo en la pata larga de un libro long-short | Un revisor leyó el criterio congelado y fue a comprobar |
| Retraso de un día inventado contra el brazo de la señal | Análisis de asimetría en la entrada forzosa |
| Test cuyo nombre prometía cobertura que no existía | Se midió y salió 10-15× de discrepancia |
| Código que fallaba su propio test (mayúsculas vs minúsculas) | Al ejecutarlo |

Lección: **ejecutar y medir, no leer y asumir.** Y `hashlib.md5` en vez de `hash()` para claves de caché — Python aleatoriza el hash de strings entre procesos.

La misma disciplina atrapó dos defectos más al **diseñar** A, antes de escribir código:

| Defecto | Cómo se detectó |
|---|---|
| SIC recomendado sobre GICS con dos ejemplos falsos y sin medir | Se midieron los tamaños de grupo: 87 empresas quedaban solas |
| Múltiplos cotizados al cierre del trimestre, cuando los resultados aún no eran públicos | Al revisar el plan contra el spec, buscando huecos |

Y cuatro más al **implementarlo**. Ninguno lanzaba error; todos producían un panel plausible con menos datos o con datos mal alineados:

| Defecto | Cómo se detectó |
|---|---|
| Empresas agrupadas por trimestre fiscal, que no es el mismo periodo natural para Apple que para JPMorgan | El spike de verificación, antes de escribir código |
| Flujo de caja descartado en 3 de cada 4 trimestres: viene acumulado, no suelto | La corrida real dejó `crecimiento_fcf` en 11,9% |
| Depreciación y amortización etiquetadas por separado en 76 emisores, dejando su EBITDA sin calcular | Se midió qué declaraban las empresas a las que faltaba la línea |
| `astype(errors="ignore")` no ignora una clave ausente: sigue lanzando `KeyError` | Los tests de orquestación |

El de mayor coste evitado fue el primero: los z-scores habrían comparado trimestres distintos entre empresas, produciendo rankings plausibles y falsos.

---

## Resultado del sub-proyecto A

**503 de 503 empresas del S&P 500, cero fallos de descarga, cero sin CIK, cero sin sector.** Panel de 6.004 filas: 502 empresas × hasta 12 trimestres, cubriendo 17 trimestres naturales distintos porque los cierres fiscales no coinciden entre empresas.

Documentos:
- [`docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md`](docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md) — diseño, más dos enmiendas fechadas con lo que la implementación desmintió.
- [`docs/superpowers/plans/2026-08-10-motor-fundamentales.md`](docs/superpowers/plans/2026-08-10-motor-fundamentales.md) — el plan de implementación.

Cobertura más alta: ROE 95,7%, margen neto 93,8%, PER 89,0%. Más baja: EV/EBITDA 37,3%, cobertura de intereses 37,4%.

**Dos advertencias para leer esas cifras sin sacar conclusiones falsas:**

Los tres KPIs de crecimiento **tienen un techo del 66,7%**: los primeros cuatro trimestres de cada empresa no tienen homólogo interanual. `crecimiento_ingresos` al 63,3% está en su máximo, no bajo.

Los cuatro por debajo del 50% lo están por **carencia real, no por cadena incompleta** — se midió antes de concluirlo. Dependen del beneficio operativo, que falta en 106 empresas; lo que esas empresas declaran es `CostsAndExpenses` y `OperatingExpenses`, que son gastos y no beneficio. Bancos, aseguradoras y REITs no publican beneficio operativo. Financials queda en 51,1% de cobertura media frente al 76,7% de tecnología, y como el z-score es sectorial se comparan entre ellas — que era justamente el argumento para normalizar dentro del sector.

---

## Resultado del sub-proyecto B

Paquete `ranking/`: criterio pre-registrado y congelado, score por cuatro pilares sobre z-scores sectoriales, guardas de cobertura, tope de 3 por sector, ficha determinista, narrativa opcional de Sonnet 5 con **cada cita verificada por código**, y tres salidas (`ranking.csv`, `fichas.json`, `informe.md`).

Primera corrida real, sin LLM, sobre el universo del 2026-08-05:

| Etapa | Empresas |
|---|---:|
| Pedidas | 503 |
| Con fila en el panel | 502 |
| Sobreviven a las guardas | 425 |
| Top final tras el tope sectorial | 15 |

**Las guardas no excluyen de forma uniforme, y hay que saberlo antes de usar la lista:** Financials pierde el **65,8%** de sus empresas y Real Estate el **41,9%**, frente a menos del 9% en todos los demás sectores. La causa es estructural — el pilar `solidez` (`deuda_neta_ebitda`, `cobertura_intereses`, `razon_corriente`) está indefinido para un banco por construcción — así que **dos de cada tres bancos no son evaluables por este criterio, y no por ser peores**. El único financiero del top es CBOE, un operador de mercados.

**Eso se hereda al sub-proyecto C:** una cartera optimizada sobre esta lista corta llevará un ladeo sectorial que no decidió el optimizador.

Dos hallazgos más, medidos y sin corregir a propósito, en la enmienda 3 de `docs/superpowers/specs/2026-08-12-agentes-analisis-ranking-design.md`:

- **Los z-scores no están acotados en ninguna parte.** El |z| máximo del panel es 8,62 y 201 celdas pasan de 6. El primer clasificado lo es en buena parte por un único KPI a +6,37. No se toca porque el criterio está congelado: es el primer candidato a revisar cuando se reabra.
- **El tope de 80.000 caracteres del Item 1A recorta a 9 de los 15**, y el 31% del texto nunca llega al modelo. La mediana real son 101k caracteres, no los 68k de Apple que sirvieron de referencia.

**Lo único sin ejecutar:** de los tres tests de `tests/test_ranking_contraste.py`, el de EDGAR pasa; los dos que llaman a Sonnet 5 **saltan sin `ANTHROPIC_API_KEY`** y cuestan unos cinco céntimos de dólar cuando se corran. Son lo único que comprueba que el esquema, el id del modelo y los parámetros existen de verdad tal como el código los usa. Sin clave el ranking sale igual, con fichas de plantilla.

```bash
EDGAR_IDENTITY="tu@correo.com" ANTHROPIC_API_KEY=... pytest tests/ -q -m red
```

---

## Resultado del sub-proyecto C

Paquete `aprobacion/` (lógica, sin Streamlit, 34 tests) y la página de candidatos (widgets, sin lógica; vive en `vistas/candidatos.py` desde el rediseño). `app.py` cambió una constante y una línea: su campo de tickers lee de `st.session_state`.

El flujo: la página lee `salidas/`, muestra los 15 candidatos con **las casillas desmarcadas** —si llegaran marcadas, aprobar los quince sería un clic y el gate sería decorado—, y al aprobar escribe un acta fechada en `actas/` y deja los tickers en la sesión.

**El acta es el artefacto con valor a largo plazo del proyecto.** Guarda las fichas **copiadas dentro**, no referenciadas, porque `salidas/fichas.json` se sobrescribe en cada corrida de B: una referencia se pudriría. Guarda también los **no aprobados** con su ficha, porque "por qué no tengo X" es tan buena pregunta como la contraria, y porque descartar sistemáticamente lo que el score pone arriba dice algo del criterio.

Detalles que no son obvios y conviene no deshacer:

- **`no_aprobados`, no `rechazados`.** Con las casillas desmarcadas por defecto, no marcar una puede significar que se miró y se descartó, o que no se llegó a mirar. El `motivo` escrito es lo único que las separa; llamarlas rechazadas afirmaría un juicio que quizá nunca ocurrió.
- **El motivo es obligatorio al añadir a mano.** Un ticker que entra sin ranking no tiene respaldo cuantitativo: la razón humana es la única justificación que existirá.
- **Un añadido que ya está en el ranking se rechaza, no se deduplica**, porque deduplicar en silencio borraría el motivo escrito.
- **El acta se escribe antes del traspaso.** Lo peor sería aprobar, perder el registro y seguir creyendo que quedó constancia.
- **El traspaso va por `st.session_state`**, así que hay que pasar al optimizador **por el enlace de la barra lateral**: recargar por URL abre una sesión nueva de Streamlit y pierde la selección. Desde el rediseño hay una segunda vía que no depende de la sesión: la pantalla de actas relee el acta del disco y carga sus tickers.

`actas/` vive en la raíz del programa (`programa/actas`, junto a `salidas/`) y no
dentro de `salidas/` a propósito: salidas se regenera, un acta no se regenera nunca. Ninguna de las dos está versionada, para que una actualización no pueda pisarlas — ver «Cómo se distribuye».

---

## Resultado del rediseño de la interfaz

Hecho el 2026-09-01. Era el punto 1 del plan, acordado el 2026-08-25.

**Estructura.** `app.py` pasó de ser el optimizador entero a un enrutador de
veinte líneas: fija el tema, aplica las credenciales una vez y declara las
pantallas con `st.navigation`. Las ocho pantallas viven en `vistas/`, agrupadas
en Análisis, Cartera y Cuenta. Desapareció `pages/`, que no permitía ni agrupar
ni tener un único `set_page_config`.

**Módulos nuevos, todos sin Streamlit y con tests:**

| Módulo | Qué decide |
|---|---|
| `tema.py` | La paleta y la hoja de estilo. Fuente única: `charts.py` y `medidores.py` leen sus colores de aquí. |
| `cartera.py` | Guardar, listar, releer y borrar portafolios en `portafolios/`. |
| `preferencias.py` | Los valores con los que arranca el optimizador, en la carpeta personal. |
| `medidores.py` | (del rediseño anterior) z-score → bueno / regular / malo. |

**Dos defectos que el rediseño arregló, y que no son de estilo:**

- **Los resultados desaparecían al descargar el informe.** El optimizador
  terminaba en `st.stop()` si no se acababa de pulsar el botón, y cualquier
  interacción posterior —una descarga, una pestaña— reejecutaba el guion con el
  botón ya en falso. Ahora la corrida vive en `st.session_state`.
- **Cada deslizador relanzaba todo.** Mover un límite de peso volvía a descargar
  los precios y a correr el walk-forward de las tres estrategias. Los controles
  están dentro de un `st.form`.

**Sobre el CSS.** La hoja se cuelga de los `data-testid` de Streamlit. La regla
que lo hace aceptable, y que `tests/test_tema.py` comprueba: **ninguna regla
cambia lo que la aplicación hace** —nada de `display:none` ni de
`position:fixed`—, así que un `data-testid` renombrado sólo deja algo sin
pintar. Tres selectores del primer intento no casaban con nada (Streamlit dejó
de usar `data-baseweb` en las pestañas) y el estilo no se aplicaba en silencio:
por eso el test fija la lista de ganchos comprobados y obliga a mirarlos en la
aplicación en marcha antes de añadir uno. Otro test comprueba que todo color
que lleva texto contrasta 4,5:1 sobre el fondo.

**Un detalle que confunde al leer el código:** `_recargar_si_toca` ya no existe.
Existía porque un `st.rerun()` desde el desplegable de credenciales se disparaba
antes de dibujar las casillas de aprobación y Streamlit descartaba su estado.
Las credenciales se mudaron a «Perfil y ajustes», donde no hay ningún trabajo a
medias que una recarga pueda tirar, y el peligro dejó de existir. El defecto que
cita `cbe71a0` sí sigue vigente y su comentario sigue en su sitio.

---

## Arranque sin ventana de consola

Hecho el 2026-09-01, a continuación del rediseño.

El acceso directo del Escritorio apunta ahora a `Iniciar App.vbs`, que envuelve
al `.bat` de siempre y decide **si esa ventana tiene que verse**. Se ve en tres
casos, y los tres son deliberados: primer arranque —el `.bat` hace dos preguntas
y oculto se quedaría colgado esperando una respuesta que nadie puede dar—, un
servidor ya vivo —entonces no arranca otro, abre el navegador contra el que
hay— y un arranque oculto que no llega a levantar el servidor, que reabre con
ventana para que el error se pueda leer.

**El problema que esto crea, y cómo se resuelve.** Sin ventana, cerrarla deja de
ser la forma de parar el programa. Hay dos respuestas y hacen falta las dos:

- El botón **«Salir del programa»** en la barra lateral, para quien lo busca.
- `apagado.py`, para quien no: un hilo pregunta cada 5 s cuántas pestañas hay
  conectadas y, si lleva 90 s sin ninguna, cierra el programa.

**`Runtime.stop()` no cierra el proceso, y darlo por hecho rompió el programa en
manos del usuario el mismo día.** Para el runtime de Streamlit, pero el servidor
HTTP se queda en pie agarrado al puerto respondiendo **503** a todo. Medido: tras
el apagado automático, `netstat` seguía mostrando el 8501 en LISTENING; el
siguiente doble clic en el acceso directo arrancaba un Streamlit que no podía
enlazar el puerto, y el lanzador se quedaba esperando en silencio hasta el aviso
de los dos minutos. Justo el zombi que este módulo existe para evitar.

Por eso `detener()` pide el cierre y, pasados 5 segundos de gracia, sale a la
fuerza con `os._exit`. No se pierde nada: portafolios y actas se escriben con
fichero temporal y `replace`, así que ya están completos en disco. Verificado
después del arreglo — el proceso termina con código 0 y el puerto queda
enlazable.

Dos avisos para quien vuelva a tocar esto:

- **Comprobar el puerto con `bind` no vale en Windows.** Enlazar `127.0.0.1:8501`
  tiene éxito aunque otro socket tenga `0.0.0.0:8501`, así que un test hecho así
  da el puerto por libre cuando no lo está. Hay que **conectar**, o mirar
  `netstat`.
- **El lanzador distingue tres estados del puerto, no dos.** Libre, sano y
  ocupado-por-otra-cosa. Con solo «vivo o no», un puerto tomado por un tercero
  se trata como libre, se arranca un servidor que no puede enlazarlo y el
  usuario espera dos minutos mirando nada. Ahora se le dice al momento.

Dos guardas que no son opcionales, y que están en los tests:

- **No cuenta hasta que llega el primer navegador.** Entre arrancar el servidor
  y abrirse la pestaña hay cero sesiones, y en un primer arranque pueden ser
  minutos: sin esta guarda el programa se apagaría justo antes de que el usuario
  lo vea por primera vez.
- **El cero tiene que sostenerse.** Recargar la página tira el websocket un
  instante. Si bastara con verlo una vez, recargar cerraría el programa.

`sesiones_activas()` toca `_session_mgr`, que es privado de Streamlit. Si un día
desaparece, el vigilante se desactiva a sí mismo y el programa sigue igual que
antes; lo único inaceptable sería cerrarse por sorpresa mientras alguien lo usa.

**Un detalle que costó un test.** El primer intento del hilo de vigilancia usaba
`time.sleep` y no se podía parar. El test que lo arrancaba dejaba el hilo vivo
el resto de la sesión de pytest y tumbaba
`test_fundamentals_fetch.py::test_no_se_duerme_entre_tickers`, que comprueba con
un mock **global** de `time.sleep` que la descarga no se duerme entre tickers.
Por eso el bucle espera sobre un `threading.Event`: se puede parar, y no toca
`time.sleep`.

La marca del atajo (`~/.markowitz-pro-picks/atajo.txt`) ganó una tercera línea
con la versión. Sin ella, quien ya tuviera un atajo creado por la versión
anterior no lo vería cambiar nunca —la ruta coincidía, así que no se tocaba— y
seguiría abriendo la consola. Con la versión, el atajo viejo se rehace en su
sitio y sin volver a preguntar: ya dijo que sí una vez.

**En Mac se queda como está, y no es trabajo pendiente: se miró y se
descartó.** `.command` abre Terminal.app siempre, y esconderla exigiría
envolver el lanzador en un `.app`. Los cuatro motivos, por orden de peso:

- **Gatekeeper empeora.** Hoy el rodeo de la primera vez es «clic derecho →
  Abrir», que sigue existiendo para ficheros sueltos. Para *aplicaciones*,
  macOS 15 lo quitó: hay que ir a Ajustes del Sistema → Privacidad y seguridad
  después de que el intento haya fallado. Quitar el diálogo del todo exige
  firmar y notarizar, con cuenta de Apple Developer de pago.
- **El bundle viaja peor.** Es una carpeta, y depende de que el bit de ejecución
  sobreviva a git, al ZIP de GitHub y al descompresor. Cuando no sobrevive, el
  fallo es mudo — y el README ofrece explícitamente la vía «descargar ZIP»,
  donde no hay un `chmod +x` de una línea que sirva dentro de un bundle.
- **Reabre el permiso TCC** de Archivos y carpetas. Hoy recae sobre Terminal y
  está resuelto en el README; un `.app` es otra identidad para el sistema.
- **No ahorra el trabajo difícil.** Seguiría haciendo falta la lógica de cuándo
  mostrar la ventana —primer arranque con preguntas, servidor ya vivo, arranque
  que falla—, que es el grueso.

Si el tema se reabre, **la alternativa barata no es el `.app`**: es quedarse con
el `.command` y cerrarle la ventana — lanzar Streamlit desacoplado (`nohup` +
`disown`) y cerrar la ventana de Terminal con `osascript`, exportando
`MPP_AUTOAPAGADO=1` igual que hace el `.vbs`. Mismo resultado visible sin tocar
Gatekeeper ni TCC. Su único riesgo propio es que Terminal pregunte por los
procesos en marcha si el desacoplo no está bien hecho.

---

## Lo siguiente

El sistema está completo de punta a punta: A ingiere, B ordena y razona, C
decide, y el optimizador reparte pesos.

El rediseño de la interfaz, que era el punto 1 de esta lista, se hizo el
2026-09-01 — ver la sección anterior. El arranque en Mac, que fue el punto 1
antes que él, se probó el 2026-08-26 — ver «Cómo se distribuye».

**Lo único sin ejecutar** son los dos tests `red` que llaman a Sonnet 5 (~5 céntimos), que saltan sin `ANTHROPIC_API_KEY`. Sin clave el ranking sale igual, con fichas de plantilla.

Trabajo posterior anotado, por orden de valor:

1. **El cortacircuitos puede condenar una corrida sana con la caché caliente.** Un
   acierto de caché no rompe la racha —correcto, no prueba que la SEC responda—
   pero eso hace que con la caché llena sólo toquen la red los tickers que aún
   fallan, y unos pocos fallos permanentes repartidos por el índice queden
   adyacentes *entre sí*. Hoy no dispara: ~1 empresa rota contra un umbral de
   10. **Se intentó arreglar y se deshizo**, y el intento enseñó más que el
   problema — está contado entero en el diseño del cortacircuitos. Para
   retomarlo hace falta un dato que no se puede obtener sin red: **por qué
   puerta fallan las empresas que fallan** (¿levantan desde `to_dataframe()`, o
   `get_company_facts` devuelve `None` antes?). Sin eso, cualquier arreglo es
   maquinaria para un escenario que puede no existir.
2. **Los z-scores no están acotados.** El |z| máximo del panel es 8,62 y el primer clasificado lo es en buena parte por un único KPI a +6,37. Es el primer candidato a revisar cuando se reabra el criterio de B — que hoy está congelado por pre-registro.
3. **Validar los pesos empíricamente.** Requiere ampliar el panel a ~40 trimestres con universo point-in-time.
4. **¿Cuántas acciones debería tener el portafolio final?** Sigue sin responder, e interactúa con que Markowitz concentra pesos: 15 candidatos no son 15 posiciones.

Sigue sin responder: **¿cuántas acciones debería tener el portafolio final?** Interactúa con que Markowitz concentra pesos, así que 15 candidatos no son 15 posiciones.

---

## Comandos

```bash
# Todos estos se ejecutan desde programa/, no desde la raiz del repo.
pytest tests/ -q -m "not red"       # 688 tests, sin red
python -m research.run              # correr el estudio (~5 min, luego caché)
streamlit run app.py                # la app: optimizador + pagina de revision
python scripts/bootstrap_universe.py   # regenerar el snapshot del universo
python scripts/bootstrap_sectors.py    # regenerar la tabla de sectores GICS
python -c "from ranking.run import construir_ranking, guardar; guardar(construir_ranking(con_llm=False), 'salidas')"   # ranking sin LLM (~2 min)
```

Los tests marcados `red` contrastan los KPIs nativos contra yfinance y necesitan conexión y `EDGAR_IDENTITY`:

```bash
EDGAR_IDENTITY="tu@correo.com" pytest tests/ -q -m red
```
