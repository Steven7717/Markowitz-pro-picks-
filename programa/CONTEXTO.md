# Contexto del proyecto — para retomar en una sesión nueva

**Última actualización:** 2026-09-09
**Rama:** `master` · **Tests:** 1.136 pasando (`uv run pytest tests/ -q -m "not red"`), 4 omitidos —dos por permisos POSIX en Windows y dos sin `numpy_financial`— más 8 marcados `red`
**Remoto:** `https://github.com/Steven7717/Markowitz-pro-picks-.git` — `master` es lo publicado
**Estructura:** el programa vive en `programa/`; en la raíz sólo están los dos
lanzadores y el `README.md`. Los comandos (`uv run pytest`, `uv run streamlit`)
se ejecutan desde `programa/`, no desde la raíz.

> **Al retomar:** todo está en `master`, incluido K. F y G entraron desde
> `seguimiento-cartera`, H desde `noticias-calendario`, J desde
> `entrada-al-seguimiento` y K desde `panel-de-seguimiento`, todas en avance
> rápido —F, G y H el 2026-09-08; J y K el 2026-09-09—. Las cuatro ramas
> quedaron en el mismo commit que `master` y ya no hacen falta.

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
| F | Libro de posiciones y seguimiento | Valoración, rendimiento y referencias | ✅ **terminado** |
| G | Rebalanceo y aportaciones | Medidores de deriva, reparto de la aportación | ✅ **terminado** |
| H | Noticias y calendario | Feed de EDGAR, prensa, eventos | ✅ **terminado** |
| I | Capa de IA sobre F, G y H | Interpretación y propuestas de ajuste | ✅ **terminado** |
| J | La entrada al seguimiento | Recorrido encadenado y alta del libro | ✅ **terminado** |
| K | El panel de seguimiento | Monitor real de la cartera | ✅ **terminado** |

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

### El libro de posiciones
```
seguimiento/
├── libro.py        el asiento: tipos, validación, alta, persistencia
├── posiciones.py   asientos → acciones, efectivo y valor, día a día
├── precios.py      cierres SIN ajustar, dividendos y splits
├── rendimiento.py  TWR, TIR, coste medio, contribución por activo
└── comparacion.py  objetivo teórico, 1/N y S&P 500 sobre los mismos flujos
vistas/seguimiento.py   widgets, sin lógica
libros/                 datos del usuario, ignorado en git
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

## Resultado del sub-proyecto F

Paquete `seguimiento/` (lógica, sin Streamlit) y `vistas/seguimiento.py` (widgets,
sin lógica), con **131 tests nuevos**. Fuera del paquete cambian tres cosas y
nada más: `vistas/optimizador.py` guarda dos campos más en `metrics`,
`cartera.py` hace público `rebanada`, y `app.py` registra la pantalla.

El libro guarda **sólo asientos**. Posiciones, pesos, valor y rendimiento se
derivan en cada apertura, así que no hay estado guardado que pueda
desincronizarse con el historial — porque no hay estado guardado. Corregir un
error es añadir un asiento de anulación, nunca editar.

Un `cartera.Portafolio` guardado y un libro no son lo mismo y no hay que
fundirlos: aquel es *una fotografía* de una optimización, congelada y sin dinero
dentro; este es el registro vivo de lo que pasó después. La pantalla mide la
distancia entre los dos, que es justo lo que se borraría al unirlos.

### Decisiones que no hay que relitigar

- **Los precios del seguimiento van sin ajustar, y `data.py` sigue ajustando.**
  Un precio ajustado cambia hacia atrás con cada dividendo y cada split, así que
  el precio al que se compró en enero no es el mismo número tres meses después.
  Al optimizador le da igual —sólo usa retornos, y el ajuste es consistente
  dentro de una descarga— pero a un libro de posiciones le mueve el coste de
  adquisición solo, y nadie lo ve porque el número sigue siendo plausible.
  Módulo aparte y no un interruptor en `data.py`: un interruptor arriesga lo
  contrario, que el optimizador reciba algún día precios sin ajustar.
- **El dividendo no es un flujo externo.** Sólo `aportacion` y `retiro` lo son.
  Contarlo como aportación infla el capital aportado con lo que la cartera
  acaba de ganar, y hunde el rendimiento sin causa visible.
- **El dividendo se paga sobre la tenencia de antes de los movimientos del
  día.** Para cobrarlo hay que tener las acciones *antes* de la fecha ex.
- **Coste medio ponderado, no FIFO.** Cambia el reparto entre ganancia
  realizada y latente, nunca el total. No pretende ser un cálculo fiscal, y la
  pantalla lo dice.
- **`libros/` se ignora en git, a diferencia de `actas/` y `portafolios/`.**
  Aquellos están a la vista a propósito y guardan decisiones y pesos; un libro
  guarda cuánto dinero tiene el usuario y en qué. Es otra categoría, y la
  excepción es deliberada.
- **Un fichero de libro corrupto se nombra y no se borra**, al revés que las
  cachés de `ranking/` y `fundamentals/`. Una caché se regenera; el historial de
  lo que alguien compró, no. Y cada asiento se revalida al leerlo, porque
  `json.loads` acepta el literal `NaN` por defecto.
- **La elección entre los pesos de la estrategia y 1/N no viene
  preseleccionada,** y `desde_portafolio` no le da valor por defecto a `base`.
  El walk-forward ya dice cuándo la optimización no le gana a repartir por
  igual; elegir por el usuario convertiría esa evidencia en un clic que nadie
  mira. Hay un test que protege la ausencia del valor por defecto, porque sin
  él nadie se enteraría de que alguien se lo devuelve.
- **Lo que no se puede medir se muestra como «—», nunca como 0,00.** Misma
  regla que `cartera.formato_cifra` ya aplicaba: un cero es una afirmación, y
  ahí no la hizo nadie.

### Dieciséis defectos, y ninguno se veía leyendo

F se ejecutó con un plan escrito por adelantado, un subagente por tarea, y
**revisión por sabotaje**: romper a mano la línea que cada guarda protege y
comprobar que algún test cae. **Los dieciséis eran defectos del plan, no de quien
lo implementó**: el código se copiaba literal y se verificaba con un diff. Lo que los encontró se reparte en tres métodos, y
cada uno caza una clase distinta:

**Sabotear una guarda y ver si algún test se entera** — caza guardas decorativas:

| Defecto | Qué pasaba |
|---|---|
| `NaN` e infinito atraviesan toda la validación | `nan <= 0` es `False` y `not nan` también. Un asiento con `NaN` envenena el efectivo **y borra el activo de la tabla**, porque el filtro de polvo también falla con `NaN`. Y entra desde disco sin que nadie lo teclee |
| Cinco mutantes vivos en la Task 1 | Ningún test tocaba las guardas de `importe` ni de `acciones`, y el de precio cero pasaba por la rama de *truthiness*, dejando sin cubrir `precio <= 0` |
| La guarda de los 30 días pasaba por 0,126 de casualidad | El caso usaba 2% en tres días, cuya tasa anual (10,126) se sale del techo del intervalo por una décima: lo cortaba **la guarda del intervalo**. Con 1,9% ya devolvía 8,87 |
| `if len(flujos) < 2` tapada por la de los 30 días | Con un solo flujo, `dias` sale 0 y cae bajo el mínimo. La guarda hace falta —con lista vacía, `ordenados[-1]` lanza `IndexError`— pero nada la probaba |
| `base` sin valor por defecto no estaba protegida | Los tres tests pasaban `base=` explícito, así que devolverle un default no rompía nada |

**Sondear una hipótesis con un script** — caza lógica que se lee bien:

| Defecto | Qué pasaba |
|---|---|
| El dividendo se le pagaba a quien compraba **el día de la fecha ex** | Los asientos se aplicaban antes de pagar. Medido: una compra de diez acciones el día ex se llevaba 2,40 que no le tocaban |
| `anadir` validaba contra el saldo final, no el del día del asiento | Una venta fechada en julio de acciones compradas en agosto se aceptaba y dejaba **−10 acciones en julio**. No es raro: es lo que pasa al registrar lo que ya tenías comprado, en el orden del extracto |
| Un hueco de precio valía cero | `.sum()` salta los `NaN` por defecto, así que el gráfico dibujaba una caída a plomo que nunca ocurrió. En `comparacion` era peor: un solo `NaN` convertía el día entero en `NaN` |
| Los asientos posteriores al último cierre desaparecían en silencio | Pasa al registrar una compra de hoy antes de que yfinance tenga el cierre de hoy |
| El regex aceptaba `"AAPL\n"` y `fromisoformat` aceptaba `"20260901"` | El primero parte una posición en dos claves de diccionario; el segundo, ordenado como cadena, se va detrás de `"2026-08-01"` y aplica una venta antes que su compra |

**Arrancar la app y recorrerla** — caza lo que ninguna prueba unitaria puede ver:

| Defecto | Qué pasaba |
|---|---|
| Un libro recién creado era un callejón sin salida | Decía «añade el primero abajo» y hacía `st.stop()` antes de dibujar el formulario |
| Registrar una operación **bifurcaba el libro** | `guardar` nunca sobrescribe, a propósito. Pero un alta no crea un libro, hace crecer el que hay. Medido: dos altas, tres ficheros, y la pantalla leyendo siempre el primero |
| Un libro con aportación y sin compras reventaba | Sin tickers, la descarga llamaba a yfinance con lista vacía: `No objects to concatenate` |
| `GANANCIA −9.700` sin que nadie hubiera perdido un dólar | `aportado` se sumaba sobre todos los asientos y `valor` salía de la serie, que acaba en el último cierre. Dos cortes temporales distintos restándose. La TIR tenía el mismo defecto y salía «no calculable» |

La lección que confirma: **los tres métodos son necesarios y ninguno sustituye a
los otros.** Los sabotajes cazan tests que mienten; las sondas, lógica plausible
y falsa; arrancar la app, todo lo que sólo existe cuando las piezas se tocan
entre sí. Los cuatro últimos habrían llegado a manos del usuario con la suite
entera en verde.

### Qué hereda G

F deja exactamente tres cosas, y ninguna más:

- `libro.pesos_objetivo(l.objetivo)` — los pesos contra los que medir la deriva,
  ya resueltos según `base`.
- La columna «peso real» de la tabla por activo — el otro lado de la resta.
- `posiciones.estado(asientos).efectivo` — el dinero sin asignar, que es
  literalmente lo que G va a repartir.

`medidores.py` ya existe y es la base visual de los medidores de deriva.

### Lo que F no resuelve

- **Una divisa, USD.** Un ticker de otra moneda daría cifras mezcladas; se
  declara en pantalla en vez de fingir soporte.
- **No es un cálculo fiscal.** Media ponderada y no lotes, dividendos brutos.
- **Una posición sin precio rebaja el valor sin poder valorarla.** El dinero
  salió del efectivo y las acciones no tienen precio, así que el total mostrado
  es un mínimo. La pantalla lo dice; inventarle un valor sería peor.
- **PDF no.** `exporter.to_pdf` pasa por `kpi_rows`, que indexa claves de una
  corrida del optimizador que un libro no tiene. Sólo Excel.

## Resultado del sub-proyecto G

Paquete `rebalanceo/` (lógica, sin Streamlit) y `vistas/rebalanceo.py` (widgets,
sin lógica), con **89 tests nuevos**. Fuera del paquete cambia **una sola cosa**:
`app.py` registra la pantalla. G lee el libro de F y no lo toca.

Cinco módulos, y el orden importa: `criterio` dice cuándo actuar, `deriva` mide
la distancia, `coste` estima lo que cuesta cerrarla, `reparto` la cierra con
dinero nuevo, y `propuesta` los junta.

### Decisiones que no hay que relitigar

- **La banda 5/25 está congelada en su propio commit** (`5300f3a`, «congelar el
  criterio de rebalanceo antes de medir nada»), y ese fichero no tiene ningún
  otro commit. La fecha es la prueba de que los umbrales no se movieron al ver
  la deriva de ninguna cartera real. Cambiarlos exige una **enmienda fechada** en
  el diseño, no una edición — el mismo estándar que hizo creíble el veredicto de
  D. Una banda elegida después de mirar tu propia deriva no es un criterio, es
  una racionalización.
- **Los dos umbrales existen porque ninguno funciona solo.** Con sólo la banda
  absoluta de 5 puntos, un activo cuyo objetivo es el 3% tendría que llegar al
  8% —casi triplicarse— para disparar: en la práctica no se rebalancearía nunca.
  Con sólo la relativa del 25%, un activo del 40% dispara al llegar al 50%, que
  en una cartera concentrada es la oscilación de dos semanas. Y **la relativa no
  se aplica con objetivo cero**: el 25% de cero es cero, y `abs(desviacion) >= 0`
  es cierto incluso para una desviación nula, así que sin la guarda dispararía
  siempre, y hasta para un activo que no se tiene.
- **El tope de coste del 1% es lo que hace el criterio económico y no sólo
  geométrico,** y viene directamente del veredicto de D: sin ventaja demostrada
  en ninguna de las siete señales evaluadas, **operar de más es el único
  destructor de valor garantizado** que queda en esta pantalla. Sin el tope, un
  activo fuera de banda por veinte dólares generaría una propuesta que cuesta
  cinco.
- **El efectivo no entra en el denominador del peso real.** Si entrara, meter
  10.000 en una cartera de 10.000 pondría todos los activos al 50% de su peso
  objetivo y el medidor entero se volvería rojo — por una aportación que aún no
  se ha invertido, no porque nada se hubiera desviado. La deriva mide la
  **mezcla**; el efectivo es otra cosa y se reparte aparte.
- **Hay dos denominadores, y confundirlos rompe la propuesta.** Los activos que
  el objetivo contempla se miden entre ellos (`en_plan`); los que se tienen pero
  el plan no incluye, sobre el total invertido. Unos pesos que suman uno
  aplicados sobre un total que incluye algo que nadie va a vender piden que el
  plan ocupe el cien por cien de un dinero del que otra cosa ya se lleva parte.
- **Las comisiones de cero cuentan** al estimar el coste. Si el bróker no cobra
  y así se registró, la estimación correcta es cero; filtrarlas «para quedarse
  con datos reales» convierte un dato en la ausencia de un dato, y le bloquea
  operaciones a quien no paga por ellas. Mediana y no media, para que una
  comisión rara no mueva la estimación de todas las demás. Y la pantalla dice
  siempre si el número está medido o supuesto: un supuesto que se lee como
  medido es peor que no tener número. Por eso tampoco se usan los 5/10/25 puntos
  básicos de `research/costs.py`: son supuestos de backtest institucional, y hoy
  muchos brókers minoristas cobran cero por acciones de EE.UU.
- **G no escribe en el libro.** Propone; el usuario registra en Seguimiento lo
  que de verdad ejecutó en el bróker. Si escribiera, el libro mezclaría hechos
  con intenciones sin forma de separarlos después — y todo F se apoya en que el
  libro sea sólo hechos.
- **La aportación va antes que las ventas.** Repartir dinero nuevo corrige
  deriva sin vender nada, así que las ventas se deciden sobre la cartera *ya con
  el efectivo dentro*. Decidirlas antes vendería lo que la aportación iba a
  arreglar sola y gratis.
- **Cuando algo rompe la banda se rebalancea el plan entero**, no sólo lo que la
  rompió. La banda decide **cuándo** tocar la cartera; una vez que se toca, se
  vuelve al objetivo completo. No es preferencia de estilo: moviendo sólo los
  activos fuera de banda, las ventas no tienen por qué cubrir las compras y la
  propuesta pide dinero que no hay.
- **`basta_con_la_aportacion` se devuelve como un hecho propio**, no se deduce de
  que la lista de ventas esté vacía: esa lista también sale vacía cuando todo se
  descartó por coste, y las dos situaciones le dicen al usuario cosas opuestas.
- **Una posición sin precio no vale cero.** Se aparta y vuelve nombrada.
  Contarla como cero falsearía la deriva de todos los demás, no sólo la suya.

### Seis defectos, y los seis eran míos

Misma disciplina que F —plan por adelantado, un subagente por tarea, revisión
por sabotaje— y el mismo reparto en tres métodos. **Ninguno de los seis venía de
quien implementó: todos estaban en el plan o en el diseño.**

**Sabotear una guarda y ver si algún test se entera:**

| Defecto | Qué pasaba |
|---|---|
| El sabotaje más importante no tumbaba nada | Romper `basta_con_la_aportacion` dejaba la suite entera en verde, porque ningún test lo aseveraba: se comprobaba la lista de operaciones, que es justo lo que no lo distingue. La aserción entró en su propio commit (`e35cdd3`) |

**Sondear una hipótesis con un script:**

| Defecto | Qué pasaba |
|---|---|
| El código ordenaba la deriva de una forma y mi propio test afirmaba otra | Y los dos pasaban, porque el caso elegido no distinguía entre las dos ordenaciones |
| «El reparto no aleja a nadie de su objetivo» era falsa | Medido: MSFT pasaba de 0,0300 a 0,0342 de desviación **recibiendo** dinero. La propiedad verdadera es agregada, no por activo — la sustituta se verificó sobre 2.000 carteras aleatorias |
| Tres casos mal calculados a mano | El mejor: con 6.000/4.000 y 4.000 de aportación, AAPL está sobreponderada al 60% de 10.000 y **infraponderada al 42,9% de 14.000**. Recibe dinero, y mi plan decía que no |

**Arrancar la app y recorrerla:**

| Defecto | Qué pasaba |
|---|---|
| Los medidores se habrían pintado como texto plano | `medidores.CSS` no se inyectaba en ninguna parte, y la clase que mi plan mandaba usar (`mpp-marca`) no existe — la real es `mpp-tope` |
| La propuesta pedía dinero que no había | Con TSLA en cartera y fuera del objetivo: «vender 2.138 y comprar 3.017». El descuadre de 879,48 era, a la centésima, **el valor de TSLA**. No ejecutable, y en pantalla los pesos del plan sumaban 91,5%, así que cada activo parecía menos desviado de lo que estaba |

El último cambió el diseño y no sólo el código: el spec afirmaba que las ventas
y las compras «suman cero por construcción», y eso sólo es cierto rebalanceando
el plan entero. Corregido, la suma con signo pasó de 879,48 a 0,00.

### Qué hereda H

**Nada de G.** Los dos sub-proyectos son independientes: H trae noticias y
calendario, y no necesita ni la deriva ni el reparto. Lo único que hereda es la
**lista de tickers del libro**, que ya venía de F.

### Lo que G no resuelve

- **Propone importes, no acciones.** No redondea a títulos enteros ni sabe si el
  bróker admite fracciones; el usuario traduce al ejecutar.
- **El coste es plano y por operación.** No modela la horquilla de compraventa
  —que no está registrada en ninguna parte, y la pantalla lo dice— ni el impacto
  de mercado.
- **No hay impuestos.** Vender realiza ganancias, y eso puede costar bastante más
  que la comisión. El tope del 1% mide comisión contra importe, nada más.
- **No guarda las propuestas.** Cada apertura recalcula desde el libro; no hay
  histórico de qué se propuso ni de qué se hizo con ello.

## Resultado del sub-proyecto H

Paquete `noticias/` (lógica, sin Streamlit) y `vistas/noticias.py` (widgets, sin
lógica), con **81 tests nuevos** —79 normales y 2 marcados `red`—. Fuera del
paquete cambian tres cosas: `app.py` registra la pantalla, `.gitignore` añade
`noticias/.cache/`, y `vistas/rebalanceo.py` recibe un arreglo que se explica
más abajo. **Ninguna dependencia nueva:** yfinance y edgartools ya estaban.

Ocho módulos: `criterio` (congelado) dice qué 8-K se destacan, `prensa` y
`hechos` normalizan las dos fuentes, `agenda` saca lo que viene, `macro` guarda
los punteros oficiales, `cache` la frescura, `fuentes` es lo único que toca la
red, y `plano` traduce estructuras a diccionarios y vuelta.

### Decisiones que no hay que relitigar

- **Del calendario macro se dan punteros, no fechas.** Ni yfinance ni EDGAR lo
  publican, y copiarlo al repo crearía algo que caduca en silencio: un
  calendario viejo se lee exactamente igual que uno vigente. **Un enlace roto se
  ve roto.** Por eso `Evento.cuando` admite `None`, y hay un test que protege esa
  ausencia: es lo único que impide que alguien «mejore» el módulo metiendo las
  fechas que aquí se decidió no tener.
- **Hechos y prensa van separados y etiquetados, nunca fundidos.** Un 8-K es un
  documento que la empresa está obligada a presentar, firmado y con
  consecuencias si miente. Un titular es lo que alguien decidió escribir.
  Ordenarlos juntos en una lista cronológica —lo que hace cualquier agregador—
  borra esa diferencia justo donde más cara sale: el aviso de que las cuentas
  anteriores no son fiables quedaría entre dos artículos de opinión.
- **No se descarta ningún expediente.** Los materiales salen desplegados y el
  resto plegado. Ordenar no es excluir: lo que H tirase, I no lo vería nunca.
- **Un 8-K lleva varios items**, y el índice los sirve en una sola cadena con
  comas: `"2.02,9.01"`. Modelarlo como un tipo único dejaría **cada anuncio de
  resultados clasificado como no material**, porque el 2.02 llega con el 9.01
  casi siempre. La materialidad es «alguno de sus tipos está en la lista».
- **Los items vienen en el índice**, así que basta una llamada por activo.
  `filing.obj().items` existe pero descarga el documento entero de cada
  expediente, y con quince activos eso convierte una pantalla en una espera.
- **El resumen sale sólo de `summary`.** `description` trae el mismo texto en
  **HTML crudo**, y volcarlo pintaría etiquetas. Sin resumen se enseña el
  titular solo, que ya dice algo.
- **`contentType` no se traduce contra una lista cerrada.** El primer sondeo vio
  un `VIDEO` y se supuso que el resto serían `ARTICLE`. Medido de verdad sobre
  diez noticias: **ocho `STORY`, dos `VIDEO`, ningún `ARTICLE`.** Un diccionario
  de traducción habría dejado el ochenta por ciento sin etiqueta.
- **El camino de la descarga recién hecha también da la vuelta por disco.**
  `cache.guardar` usa `default=str`, así que pasarle una dataclase no revienta:
  la guarda como su `repr` y vuelve convertida en cadena. Falla sólo en la
  **segunda** visita. Si el camino corto no diera la vuelta, existiría un tipo
  que sólo aparece en la primera pasada.
- **`Hecho.material` se recalcula al leer**, no se lee del fichero. No es un
  segundo criterio: es el mismo, aplicado tarde. Un fichero escrito por un
  formato anterior daría `bool(None) → False` y plegaría los resultados a partir
  de la segunda visita.
- **La hora de descarga se enseña siempre**, no sólo cuando el dato está viejo.
  Misma regla que `coste_del_libro` en G.
- **H no interpreta ni filtra la prensa.** No hay criterio defendible para
  decidir qué titular importa, y fingir uno sería peor. Lo que sí se hace es
  enseñar el medio y el formato, para que el usuario descarte de un vistazo.

### Trece defectos, y una lección nueva sobre el método

Tres se cazaron **sondeando las fuentes vivas antes de escribir el spec**, uno
en la auto-revisión del plan, y nueve durante la ejecución. Como en F y G,
prácticamente todos estaban en el plan o el diseño, no en quien implementó.

**Sondear la fuente antes de diseñar** — caza suposiciones que se leen bien:

| Defecto | Qué pasaba |
|---|---|
| El spec modelaba `tipo: str` para el 8-K | El índice sirve `"2.02,9.01"`. Comparado entero contra la lista congelada no coincide con nada, y **todos los anuncios de resultados** habrían salido plegados entre la rutina |
| `description` viene en HTML crudo | La regla del spec era «resumen de `summary`, y si falta de `description`». Habría metido `<p><a href=...>` en la pantalla |
| `provider` y `canonicalUrl` son diccionarios | Tratarlos como cadenas da un medio ilegible y una url rota, y ninguna de las dos cosas lanza |
| El CIK **no está** en el índice | Cazado revisando el plan contra el spec. Las trece columnas de `to_pandas()` se comprobaron una a una. Habría dado `cik=0` y urls a `/data/0/`: el texto del enlace se ve perfecto y sólo falla al pulsarlo |

**Sabotear una guarda** — y aquí está la lección nueva:

| Defecto | Qué pasaba |
|---|---|
| La ruta como docstring mataba el docstring real | Los bloques del plan empezaban con `"""ruta.py"""` y el docstring de verdad debajo. Python toma el primer literal como `__doc__` y **descarta el segundo en silencio**: los ocho módulos habrían perdido su documentación entera |
| El sabotaje de `JSONDecodeError` era **inerte** | Quitarlo del `except` no tumbaba nada, porque **es subclase de `ValueError`**, que seguía en la tupla |
| El sabotaje de `EDGAR_IDENTITY` era inerte, y el test **decorativo** | Sin la guarda, el `IdentityNotSetError` que lanza el propio edgartools ya trae la cadena `EDGAR_IDENTITY` en su mensaje, así que la comparación por subcadena se satisfacía igual. **El test pasaba con guarda y sin ella.** Se sustituyó por uno que intercepta la descarga y afirma que no se llega a preguntar |

**La lección: el paso de sabotaje también puede ser decorativo.** Dos veces
seguidas el sabotaje no tumbó nada, y las dos veces la causa era una relación
invisible leyendo —una jerarquía de excepciones, el texto de un error ajeno—.
Un «saboteé y no cayó nada» aceptado sin más habría dejado creer que esas
guardas estaban protegidas. **La regla que funciona es: si el sabotaje no tumba
nada, el trabajo no es repetirlo, es averiguar qué otra cosa está devolviendo
la respuesta correcta.**

**Arrancar la app y recorrerla** — lo que ninguna prueba unitaria ve:

| Defecto | Qué pasaba |
|---|---|
| Un libro **ilegible** se contaba como que no hay ninguno | `[e for e in listar() if e.libro is not None]` y después «Todavía no llevas ningún libro». Son cosas opuestas, y la segunda deja al usuario sin nada que buscar. `vistas/seguimiento.py` ya lo hacía bien; el defecto se introdujo en `rebalanceo.py` y **se copió a `noticias.py` al pedir que siguiera a la pantalla hermana**. Arreglado en las dos |
| Streamlit interpreta `$…$` como LaTeX | Un titular financiero va lleno de dólares, y el segundo se come la línea hasta el siguiente. Todo lo que llega de la red se escapa antes de pintarlo |
| La caché devolvía diccionarios donde la pantalla esperaba dataclases | Y sólo a partir de la **segunda** visita, porque `default=str` no revienta al guardar |
| «Reuniones del FOMC — ocho al **ano**» | Los literales del plan iban sin acentos y se quedaron en cadenas visibles. Ésta no era un descuido tipográfico: *ano* y *año* no son la misma palabra |
| Tres casos de la Task 4 mal calculados | Pasaban `hoy=2026-09-08` con un ex-dividendo del 9 de agosto: el filtro de «lo que viene» los descartaba, y el test exigía tres clases teniendo una. Habrían fallado nada más escribirse |

### Qué hereda I

Las tres estructuras, y nada más: `Noticia`, `Hecho` y `Evento`. H las deja
normalizadas y **sin ningún juicio aplicado** — ni filtrado, ni resumen, ni
orden por importancia más allá de destacar los tipos de la lista congelada. Esa
abstinencia es deliberada: cualquier cosa que H descartase, I no la vería.

`plano.reconstruir` es además el camino por el que I puede leer lo ya cacheado
sin volver a descargar.

### Lo que H no resuelve

- **No da fechas macro**, sólo quién las publica. Es la decisión, no una carencia.
- **No guarda histórico.** La caché caduca y se pisa; no hay forma de mirar qué
  se publicó hace tres meses si ya no está en la ventana de las fuentes.
- **No interpreta ni recomienda.** Eso es I, y H existe para darle de comer.
- **Un 8-K sólo existe para emisores registrados en la SEC.** Un ticker de otro
  mercado tendrá prensa y calendario, pero no hechos, y la pantalla lo dice en
  vez de dejar el bloque vacío.
- **Yahoo devuelve el mismo artículo bajo varios tickers**, y la pantalla lo
  enseña una vez por cada uno. Es honesto —cada asociación es real— pero se ve
  como duplicado. Deduplicar por url y listar los tickers juntos está sin hacer.
- **La prensa incluye el relleno de Yahoo.** En el sondeo, la primera «noticia»
  de MSFT era un vídeo sobre los resultados de Oracle. H no filtra porque no
  tiene criterio defendible, y fingir uno sería peor.

## Resultado del sub-proyecto J

`seguimiento/alta.py` (lógica, sin Streamlit) y `vistas/estrenar.py` (widgets,
sin lógica), con **36 tests nuevos**. Fuera de esos dos ficheros cambian
`app.py`, que registra la pantalla, y siete pantallas que ya existían:
`candidatos`, `inicio`, `noticias`, `optimizador`, `portafolios`, `rebalanceo` y
`seguimiento` —esta última **pierde** el alta, que se va entera a `estrenar.py`.
**Ninguna dependencia nueva.**

J no añade capacidades: **hace utilizables las que ya había.** Antes se podía
elegir qué comprar (A–D), seguirlo (F), decidir cuándo tocarlo (G) y traer sus
noticias (H), pero el camino de una cosa a la siguiente estaba sin construir. La
portada no mencionaba la segunda mitad del programa, los dos botones que debían
encadenar pantallas escribían un aviso pidiendo que usaras el menú lateral, y un
libro recién creado nacía **vacío**, con el formulario de la primera compra
plegado dentro de un desplegable, debajo de los gráficos.

### Decisiones que no hay que relitigar

- **El programa propone y el usuario confirma.** «Que sólo pregunte el capital a
  invertir» choca de frente con la regla sobre la que se construyó F: el libro
  guarda **sólo hechos**. Con 15.000 y un peso del 40%, escribir «compraste
  27,27 acciones de AAPL a 220» *no es un hecho: es una división*. La compra real
  fue de otro número de acciones, a otro precio, con comisión, y puede que otro
  día. Dentro del libro esa cifra es indistinguible de una medida y contamina el
  coste de adquisición, la TIR y el rendimiento, sin que nadie lo note porque el
  número es plausible. Por eso lo que entra es lo que el usuario **afirma que
  ejecutó**, en una tabla editable. **La fricción de esa tabla es la
  característica**, no un descuido: entre mirar la propuesta y ejecutarla el
  precio se mueve, y ese hueco es exactamente donde se colaría el número
  inventado.
- **El sobrante no se redistribuye.** Con acciones enteras siempre sobra algo, y
  repartirlo entre los demás rompería los pesos que el usuario acaba de elegir.
  Queda como efectivo sin asignar, que es lo que es, y Rebalanceo ya sabe
  proponer dónde ponerlo.
- **Un activo que no cabe sale nombrado, con cero.** Un peso pequeño y un precio
  alto dan cero acciones. Ese activo aparece en la tabla con un cero y el motivo
  escrito, en vez de desaparecer. Un activo que se cae del plan sin avisar es el
  defecto que ya costó una corrección en G.
- **`AportacionPrevista` no es `Asiento.tipo == "aportacion"`.** El nombre lleva
  «prevista» a propósito: una es dinero que **entró**, la otra es dinero que el
  usuario **dice que entrará**. Llamarlas igual invita justo a la confusión que
  todo F evita.
- **La aportación prevista se SUMA al efectivo registrado, nunca lo sustituye.**
  Sustituirlo haría que un libro con efectivo parado y sin plan no propusiera
  nada, y que el encabezado nombrase un dinero que el usuario no tiene. Las dos
  cifras se enseñan **separadas** —«3.998,00 registrados y 500,00 que vas a
  aportar»— porque el único riesgo que esto añade es contarlas dos veces.
- **En la carga manual el importe de la aportación se deriva**, no se pregunta:
  es la suma de las compras confirmadas más sus comisiones, así que el libro nace
  con cero efectivo sin asignar. Es lo honesto — nadie ha dicho que tenga dinero
  parado. Quien además lo tenga lo registra después como una aportación más.
- **Los libros viejos siguen abriéndose.** `cargar` lee campo a campo con
  `crudo.get(...)` —así entraron `moneda` y `objetivos`—, así que un fichero sin
  las claves nuevas toma los valores por defecto.
- **El alta vive en su propio fichero** porque K va a rehacer
  `vistas/seguimiento.py` entero. Meterla dentro habría sido construir encima de
  lo que está a punto de moverse.

### Ocho defectos, y una lección nueva sobre el método

Los seis primeros salieron de mis propios documentos, no de quien los
implementó. Es el mismo reparto que en G y en H.

1. **El spec afirmaba algo falso sobre el código.** Escribí «Rebalanceo deja de
   preguntar cuánto vas a aportar», y Rebalanceo **nunca lo preguntó**: repartía
   `posiciones.estado(...).efectivo`, el dinero ya registrado. No había ninguna
   pregunta que quitar. El plan heredó la frase entera y la tarea 7 se construyó
   sobre ella. El agente se paró en vez de adaptar los nombres hasta que
   encajaran, que es lo que la habría dejado plausible y rota.
2. **`desde_corrida` estaba fuera del `try`** que capturaba `NombreInvalido` —y
   es justo la llamada que la lanza—, así que el `except` era código muerto.
3. **Un libro recién estrenado decía valer 0,00**, contradiciendo la regla que
   `cartera.formato_cifra` aplica en todas partes: lo que no se puede medir se
   escribe «—». No le faltaba valor, le faltaba **precio**, que es otra cosa.
4. **«Aportado neto 0,00» era una afirmación falsa sobre un hecho registrado.**
   El dinero había entrado. Se arregló *sólo* dentro de la rama sin valorar,
   para que no pudiera repetirse el defecto de F donde restar dos cortes
   temporales distintos dio una `GANANCIA −9.700` sin que nadie hubiera perdido
   un dólar.
5. **Los estados vacíos apuntaban al sitio viejo** («Empieza uno desde
   Portafolios guardados») después de que el alta se mudara a su propia pantalla.
6. **Una aserción buscaba `"1.000"` dentro de un `"1,000.00"`**, y la aritmética
   con la que la sustituí también estaba mal. Misma clase que los tres fixtures
   mal calculados de G y los tres de H: cuentas mías, escritas a mano, dentro de
   un plan.
7. **Faltaba `mod.validar(asiento)` antes de escribir.** `alta.asientos_de` no
   comprueba la forma del ticker y `libro.cargar` sí, así que un libro podía
   nacer y no volver a abrirse. Lo encontró el agente de la tarea 4.
8. **Dos tests decorativos.** Construían una `AportacionPrevista` con 500 y
   afirmaban que valía 500: probaban la dataclass de la tarea 1, no la decisión
   de la tarea 7. Ningún sabotaje de la tarea 7 podía tumbarlos. Se sustituyeron
   por dos que sí caen, uno en cada dirección.

**La lección nueva:** en H aprendimos que *un sabotaje puede ser decorativo*. En
J, que **la premisa puede serlo también** — un spec puede afirmar un hecho sobre
el código que sencillamente no es cierto, y el plan lo hereda entero sin que
nada chirríe, porque la frase es plausible. La regla que queda: **antes de
escribir «X deja de hacer Y», comprobar que X hacía Y.** Un `grep` habría bastado.

### Qué hereda K

El camino ya encadena y el alta ya está fuera. `vistas/seguimiento.py` puede
rehacerse entero sin tocar el estreno, que es exactamente para lo que se separó.
El libro sabe además dos cosas nuevas que K puede mostrar: `fracciones` y
`aportacion_prevista`.

Lo que K tiene que construir: el panel de verdad —nombre del portafolio con
desplegable para cambiarlo, los activos, su peso en porcentaje, el capital
invertido, un panel de noticias y elementos visuales.

### Lo que J no resuelve

- **No rediseña el panel de seguimiento.** Eso es K.
- **No ejecuta órdenes.** La lista de la compra es papel; comprar se compra en el
  bróker.
- **No sabe si tu bróker admite fracciones**: lo pregunta y te cree.
- **No detecta la doble cuenta de la aportación.** Si ya ingresaste la del mes y
  la registraste, el campo de Rebalanceo sigue precargándose con el plan y queda
  en tu mano ponerlo a cero. La pantalla lo dice y enseña las dos cifras por
  separado para que se vea, pero **el programa no lo comprueba**. Comprobarlo
  pediría una ventana por cadencia —¿cuántos días son «este mes»?—, y eso es un
  criterio, que en este proyecto se congela en su propio commit antes de ver
  ningún número. J no lo tomó.
- **La aportación prevista no genera avisos ni fechas.** Es un importe y una
  cadencia que Rebalanceo usa para no volver a preguntar.
- **Los precios de la propuesta son los del último cierre disponible**, no los de
  tiempo real. Entre mirarlos y ejecutar hay un hueco, y por eso la tabla de
  confirmación es editable.
- **`tests/test_apagado.py::test_detener_espera_antes_de_forzar` es inestable.**
  Compara un tiempo medido contra un umbral fijo de 0,2 s y ha fallado con
  0,187 s. No se tocó dentro de J a propósito: es anterior y no tiene que ver.

## Resultado del sub-proyecto K

«Seguimiento» pasa de ser un informe de 484 líneas en un solo scroll a un panel:
identidad del libro, cuatro cifras, la composición en barras, y el detalle en
cuatro pestañas —Evolución, Por activo, Movimientos y Noticias—. **21 tests
nuevos.**

Cuatro módulos nuevos, ninguno con Streamlit dentro:

| Módulo | Qué decide |
|---|---|
| `seguimiento/panel.py` | La aritmética que vivía dentro de la vista: cifras de cabecera, composición, filas por activo e historial |
| `noticias/traer.py` | Caché-o-descarga, y `cacheado()`, que lee sin tocar la red |
| `noticias/texto.py` | El escapado y el formato que las dos pantallas de noticias comparten |
| `noticias/resumen.py` | Qué se enseña del libro y **de cuándo es**, con el estado como dato |

Más `medidores.barra_de_peso`, y `tema.py`, que cambia el escalón tipográfico de
las métricas por una razón medida.

### La razón de ser: la aritmética no tenía tests

`vistas/seguimiento.py` guardaba correcciones que costaron caro y **no se ven**:
el corte temporal común de `aportado` y `valor` —el que en F dio `GANANCIA
−9.700` sin que nadie perdiera un dólar—, el «—» que nunca es un cero, el bloque
`sin_valorar`. Ninguna estaba protegida por un test, porque vivían dentro de un
guion de Streamlit que no se puede importar.

Por eso el orden fue **primero sacar la aritmética con tests, después rehacer la
vista encima**. Al revés se habría sacado lo que quedara, no lo que había. El
defecto de F es hoy `tests/test_panel_cabecera.py::test_una_aportacion_de_hoy_no_inventa_una_perdida`.

### Decisiones que no hay que relitigar

- **Resumen fijo arriba, pestañas debajo.** Lo que se mira a diario cabe en una
  pantalla y **no se mueve al cambiar de pestaña**. Es lo que separa un panel de
  un informe.
- **Las pestañas no ahorran cálculo.** Streamlit ejecuta las cuatro en cada
  pasada. Ahorran scroll, y en el código está escrito así a propósito para que
  nadie escriba lo contrario.
- **Sin veredicto en la composición.** La barra enseña dónde está el peso y
  dónde debería estar, y **no escribe «sobreponderado»**. Esa palabra es un
  juicio y vive en Rebalanceo. Un test lo fija: la salida no puede contener
  ninguna palabra de veredicto.
- **El peso es sobre los activos**, no sobre el valor de la serie. Ver el
  defecto 2.
- **El efectivo sin invertir se nombra**, y **nunca se resta de `valor`**: uno
  vive en el calendario de los asientos y el otro en el de la serie.
- **El panel no descarga al abrir.** Lee la caché de H y ofrece un botón.
  Comprobado sustituyendo `socket.socket` por algo que revienta al construirse:
  **doce activos en 6 ms con la red inutilizada**. No es que no descargue en la
  práctica; es que no puede.
- **Los tres estados vacíos se distinguen con un dato, no deduciéndolos.** «No
  lo hemos mirado», «lo miramos hace rato» y «lo miramos y no hay nada» salen
  todos como listas vacías; deducir el estado de la lista los haría iguales, y
  dos de los tres mensajes serían mentira.
- **Lo que se enseña lleva la marca MÁS ANTIGUA de todo lo que hay en pantalla**,
  no la más nueva: la antigüedad de lo peor que estás mirando.

### Ocho defectos, y una lección nueva sobre el método

1. **Medí que cuatro cifras caben, y no cabían.** Simulé cuatro columnas
   escondiendo dos de las seis y leí `scrollWidth`. Streamlit recorta con CSS,
   así que `scrollWidth == clientWidth` y la medida dice «cabe» mientras la
   pantalla enseña `51,405…`. **Ese aviso lo había escrito yo mismo dos párrafos
   más arriba en ese documento**, para el caso de seis columnas, donde lo cacé
   mirando la captura. La segunda vez me fié del número.
2. **«Peso real» dividía por un total que incluye el efectivo.** El mismo libro
   daba AAPL al 7,32% en Seguimiento y al 10,17% en Rebalanceo, y la columna
   sumaba 71,9% al lado de un «Peso objetivo» que suma 100%. Invitaba a leer
   «voy tres puntos por debajo» cuando el activo estaba clavado y lo que pasaba
   era que **el 28% del dinero no estaba invertido** — cifra que no aparecía en
   ninguna parte, sólo encogía todos los pesos.
3. **El aviso de la brecha TWR/TIR afirmaba una causa que no comprobaba.** Decía
   que la separación «es el efecto de cuándo aportaste», y salía igual con **una
   sola aportación**, donde no hay ningún «cuándo» posible.
4. **La escala de las barras perdía la marca que existe para salvar.** Aun
   contando los objetivos, `.mpp-tope` son 3px anclados por su borde izquierdo:
   una marca en `left:100%` empieza donde la pista acaba y `overflow:hidden` se
   la come. Hace falta holgura, y **no un recorte al 100%** — aparcarla en el
   borde afirmaría que el objetivo es el peso mayor.
5. **«Están enteros en Noticias» era falso.** Aquella pantalla también recorta a
   40, y con doce activos deja fuera casi noventa de los 128 hechos. El enlace
   mandaba a un sitio donde tampoco estaban.
6. **Una rama muerta**: un caso escrito para «faltan todos los tickers» dentro
   de la rama que sólo corre cuando hay caché. Código que afirma algo que no
   puede pasar.
7. **Los números de línea del plan caducaron** en cuanto la tarea 1 movió
   bloques. El agente de la tarea 2 lo dijo en vez de seguir a ciegas.
8. **El plan mandaba mover `VALIDEZ`** a `noticias/traer.py`, y ya vivía en
   `noticias/cache.py`. Habría dejado dos sitios donde mirar cuánto dura una
   caché.

**La lección nueva:** en H, *un sabotaje puede ser decorativo*. En J, *la premisa
puede serlo*. En K, **la medición**. Un número medido con la herramienta
equivocada miente con más autoridad que una suposición, porque viene con cifras.
La regla que queda: **cuando lo que se mide es lo que se ve, la captura es la
medida** — y un `scrollWidth` sobre algo que se recorta con CSS no lo es.

### Qué hereda I

`noticias/resumen.py` le da los hechos **ya filtrados por el criterio congelado**
y con la marca de cuándo se miraron, sin bajar nada. `seguimiento/panel.py` le da
todas las cifras del libro como dataclases importables y probadas, que hasta K
sólo existían dentro de un guion de Streamlit.

La pestaña «Noticias» del panel es además el hueco natural donde I pondrá su
interpretación: el sitio ya existe, ya sabe de cuándo son sus datos, y ya
distingue «no hay» de «no lo hemos mirado».

### Lo que K no resuelve

- **No interpreta las noticias.** Las enseña. Interpretarlas es I.
- **No añade métricas nuevas** —ni volatilidad, ni drawdown, ni comparación
  contra un índice—. No estaba en el encargo.
- **No deduplica la prensa.** Se ve el mismo titular bajo dos activos, y ahora se
  ve más porque están juntos. Es deuda declarada de H.
- **No descarga en segundo plano.** Streamlit no tiene dónde hacerlo sin
  complicar el ciclo, y el botón resuelve el caso real.
- **`st.dataframe` dentro de una pestaña oculta nace sin medir sus columnas** y
  se recompone sola en dos o tres segundos. Es cosmético y nuevo: antes ninguna
  tabla nacía oculta.
- **`vistas/rebalanceo.py:52` interpola el ticker en HTML con
  `unsafe_allow_html=True`.** **No es explotable:** `_FORMA_TICKER` sólo admite
  `[A-Z]+(-[A-Z]+)*` y `libro.cargar` valida cada asiento al leerlo, así que un
  libro con un ticker que lleve HTML se rechaza —comprobado—. El escapado es
  defensa en profundidad y merece su propio commit.
- **`tests/test_apagado.py::test_detener_espera_antes_de_forzar` sigue
  inestable.** Compara un tiempo medido contra un umbral fijo de 0,2 s.

## Resultado del sub-proyecto I

Paquete `interprete/` (lógica, sin Streamlit) y `vistas/panel_ia.py` (widgets),
con **91 tests nuevos** —90 normales y 1 marcado `red`—. Fuera del paquete
cambian tres cosas: `vistas/seguimiento.py` gana el bloque de interpretación en
su pestaña «Noticias», `vistas/rebalanceo.py` el botón y el historial, y
`.gitignore` añade `interprete/.cache/`. **Ninguna dependencia nueva:**
`anthropic` y `edgartools` ya estaban.

Siete módulos: `contexto` es la frontera de privacidad, `documentos` lo único
que toca EDGAR, `cliente` lo único que toca Anthropic, `noticias` y `ajuste` las
dos mitades con sus guardarraíles, `cache` la memoización y `archivo` el
registro permanente.

### Las dos mitades no tienen la misma verdad, y por eso no llevan el mismo guardarraíl

Es la decisión de la que cuelga todo lo demás.

**Un juicio sobre un 8-K tiene verdad contrastable:** se ancla a una frase que
existe o no existe en el documento, y `ranking/verificacion.py` lo comprueba
carácter a carácter. Lo que falle sale **marcado**, no escondido.

**Un comentario sobre la deriva no la tiene:** no hay texto que citar, y su
única materia prima son números que puso el código. Así que el guardarraíl es
otro: cada observación va dirigida a una **letra**, y las letras son exactamente
las operaciones que G propuso. Si propuso tres, la `D` no existe. Eso convierte
«no puede inventarse una operación» en pertenencia a un conjunto — comprobable
sin criterio.

### Decisiones que no hay que relitigar

- **El modelo explica y señala qué revisar; no propone operaciones propias.** G
  ya propone operaciones, pero las saca por aritmética de los pesos objetivo que
  fijó el usuario: es su plan ejecutado, no una opinión sobre qué debería tener.
- **El modelo no ve un euro, y la garantía es la firma y no un filtro.** Ninguna
  función de `contexto.py` admite un parámetro que sea un importe, y hay un test
  que recorre las firmas con `inspect.signature` y lo afirma. Por eso `cartera()`
  recibe tripletas `(ticker, peso, objetivo)` y **no** `panel.Linea`, que tiene
  esos tres campos **más `valor`**. Un filtro se rodea añadiendo un campo; una
  firma que no los admite, no.
- **Las etiquetas `A`, `B`, `C`… no son un capricho.** Hacen dos cosas a la vez:
  mantienen la regla de «cero dígitos» de B —si el modelo dijera «el hecho dos»
  habría que abrirle la puerta a los números justo donde más caro sale— y
  convierten la pertenencia en comprobable. El código imprime después el ticker,
  la fecha, los códigos de item y el enlace; el modelo no escribe ninguno.
- **Nunca se llama sin botón.** Misma regla que K. Un panel que llama a un modelo
  al abrirse es un panel que cuesta dinero por mirarlo.
- **Se lee exactamente lo que hay en pantalla**, `TOPE_HECHOS` importado de
  `noticias/resumen.py` y no recopiado. No es sólo presupuesto: es que la IA lee
  **lo mismo que el usuario**, así que no puede comentar algo que no tiene
  delante ni callar sobre algo que sí.
- **`verificacion.py` no se amplía.** Su tabla tipográfica no cubre `…` ni `•`,
  que los anexos sí traen, pero tocarla cambiaría el comportamiento de B, que
  está en producción. El reintento absorbe el caso.
- **Un archivo ilegible NO se trata como vacío**, al revés que una caché.
  `cache.leer` borra el fichero roto y sigue —lo perdido es una llamada que se
  repite—; `archivo.cargar` levanta `ArchivoIlegible` y **no toca el fichero**,
  porque lo perdido es historial. Los dos módulos hacen algo parecido y su
  comportamiento ante lo mismo es opuesto, a propósito.
- **El archivo va en `libros/interpretaciones/`, no en `libros/`.**
  `libro.listar()` hace `glob("*.json")` sobre esa carpeta y valida lo que
  encuentre: un archivo ahí dentro aparecería como **un libro ilegible**, que es
  el defecto que H pagó. `Path.glob` no recorre subcarpetas, y hay un test que lo
  afirma.
- **El archivo es append-only**, como el libro. Volver a interpretar añade una
  sesión; un juicio es una opinión fechada y reescribirla borraría que cambió.
  Misma forma que `Libro.objetivos`.
- **`en_conjunto` se vacía entero, nunca a trozos.** Un párrafo al que se le
  quita una frase queda diciendo algo que nadie escribió. Un juicio suelto sí se
  tira, porque los demás siguen siendo verdad por su cuenta.
- **Un juicio recuperado del archivo conserva su `verificada` y no se
  re-verifica.** El documento ya no se envía, y verificar contra un texto que no
  está delante sería afirmar algo que no se ha comprobado.

### Lo que se sondeó antes de escribir el spec

Cinco medidas contra EDGAR vivo, y dos tumbaron cosas que el diseño iba a decir
mal:

| Qué se midió | Qué salió |
|---|---|
| Qué trae un `Hecho` | **Ni una palabra de la empresa.** Sus `descripciones` son etiquetas del propio programa. Interpretar eso sólo podía repetir la etiqueta o inventarse el expediente |
| Dónde está la noticia | **No en el cuerpo.** El 2.02 de MSFT son 3.579 caracteres de carátula y una frase de reenvío; el `EX-99.1` son 52.823 con la nota de prensa entera. 13 de 17 materiales traen anexo; los 4 que no son `5.02` |
| Si el cuerpo se puede recortar | Sí, entre `Item N.NN` y `SIGNATURE`: de 25% a 80% menos. **MSFT usa espacio fino U+2009**, así que un literal `"Item "` se lo salta |
| Si el texto trae caracteres rotos | **No hay `U+FFFD`.** Los interrogantes eran la consola de Windows. Sin eso el guardarraíl de la cita no sería viable |
| Cuántos materiales hay de verdad | `VENTANA` son **550 días**, no treinta: ~134 materiales con doce activos, cerca de un millón de tokens. De ahí que el presupuesto sea una decisión de diseño |

### Dieciséis defectos, y una lección nueva sobre el método

Todos menos uno estaban en el spec o el plan, no en quien implementó. Y el
detector más productivo no fue ninguno de los tres conocidos:

**El sabotaje inerte, que en H era una advertencia, en I fue la mejor
herramienta — y nunca encontró lo que se buscaba.** Cuatro veces un sabotaje no
tumbó nada, y las cuatro la causa fue distinta, y ninguna era «la guarda está
sin proteger»:

| Sabotaje inerte | Lo que había detrás |
|---|---|
| El espacio fino de `_ITEM` | La transcripción se había **comido el carácter invisible**, y el test comparaba una cadena consigo misma |
| La guarda de `EDGAR_IDENTITY` | El test afirmaba por subcadena sobre el mensaje de **su propio doble**, que contenía la cadena buscada. Pasaba con guarda y sin ella |
| Los dígitos de `ajuste._limpiar_conjunto` | El sabotaje apuntaba a una guarda y el único test que había dependía de otra. Detrás: **no existía el test de dígitos**, que su gemelo `noticias.py` sí tenía |
| El bucle de claves de `archivo.cargar` | Sin él, `crudo["hechos"]` lanza `KeyError` y el `except` lo convierte igual. **La guarda no aporta el rechazo, aporta el mensaje** — y los tests sólo miraban el tipo |

**La regla que queda: un sabotaje inerte no es un resultado, es una pregunta. Y
la respuesta casi nunca es la que se esperaba.**

**Los defectos que sólo aparecieron mirando datos reales:**

| Defecto | Qué pasaba |
|---|---|
| Un anexo en **PDF** tiraba el anexo bueno de al lado | `adjunto.text()` devuelve `None` para lo que no es texto, el `join` reventaba y el `except` lo reportaba **como si hubiera fallado la SEC**. Reproducido con Axos Financial: 15.210 caracteres buenos descartados |
| `aplicar_tope` cortaba a mitad de palabra | Una cita legítima que cruzara el corte se habría rechazado **por el corte y no por invención** |
| **El arreglo del anterior era peor que el defecto** | Retrocedía al último salto de párrafo estuviera donde estuviera; con el `EX-99.1` de MSFT eso tiraba **veinticinco mil caracteres** para salvar una palabra. Lo cazó el test `red` |
| `_pct` redondeaba a entero | 4,3% y 4,4% se leían los dos como «4%», y un 0,4% como «0%»: el modelo podía concluir que esa posición no existe |
| **`bool("false")` es `True`** | Un fichero editado a mano convertía una cita **sin respaldo** en una respaldada — al revés de lo único que ese campo significa, y sin poder re-verificar porque el documento ya no está delante |
| `tuple("4.02")` daba `('4','.','0','2')` | Cuatro items que nadie presentó |
| `{}` se aceptaba como archivo vacío | Indistinguible de «nadie ha interpretado este libro», que es la confusión que el módulo existe para evitar |

**Los huecos de cobertura, que no eran defectos pero lo habrían sido:**
`juicio_guardado` sin ningún test; `anotar_rebalanceo` sin prueba de
append-only mientras su mitad gemela sí la tenía; la rama `viable=True` de
`contexto.operaciones` sin cubrir.

**Y una lección que es sobre quien escribió esto, no sobre el método:** tres
veces se dijo «arreglado» sin medir el resultado. Los caracteres de ancho cero
se «escaparon» dos veces sin escaparse —una barra invertida donde hacían falta
dos, con un comentario encima afirmando lo contrario de lo que el código
hacía— y un comentario que existía para señalar un carácter invisible lo
llevaba dentro, donde no se ve. **Decir que algo está arreglado sin medirlo es
no haberlo arreglado.**

### Lo que I no resuelve

- **No propone operaciones propias.** Es la decisión, no una carencia.
- **No lee más de lo que se ve, y el archivo sólo cubre hacia delante.** Un
  `4.02` de hace ocho meses no entra hoy y tampoco está guardado: el archivo
  empieza vacío el día que se estrena y acumula desde ahí. Rellenarlo pediría los
  ~134 materiales de la ventana de H, cerca de un millón de tokens.
- **No hay botón de «vuelve a leer éste».** El modelo de datos lo admite —es
  append-only— y la pantalla no lo ofrece.
- **El archivo no se respalda.** Vive bajo `libros/`, que está en `.gitignore`
  por ser dato personal.
- **No deduplica la prensa.** Sigue siendo deuda declarada de H.
- **No interpreta el calendario.** `Evento` no entra: H da punteros, no fechas.
- **`interprete/cache.py` está escrito y probado pero sólo lo usa `ajuste.py`.**
  En la mitad de hechos el archivo ya evita la llamada, y dos memorias sobre lo
  mismo es una que se queda atrás.
- **Los dos caminos que llaman al modelo no se han recorrido en pantalla.** Se
  verificó todo lo demás con la app arrancada —la cuenta de nuevos, lo guardado
  pintándose sin pulsar, las dos marcas de respaldo, el archivo roto avisando y
  sobreviviendo—, pero pulsar el botón gasta saldo y se dejó al dueño de la clave.

## Lo siguiente

El sistema está completo de punta a punta: A ingiere, B ordena y razona, C
decide, el optimizador reparte pesos, **F sigue lo que se compró de verdad**,
**G dice cuándo hace falta corregir el rumbo y qué cuesta**, H trae las
noticias e **I las interpreta**.

**El encargo original está entregado entero.** Lo que queda son mejoras, no
piezas que falten.

Lo único de I sin recorrer en pantalla son los dos caminos que llaman al
modelo: se verificó todo lo demás con la app arrancada, pero pulsar el botón
gasta saldo y se dejó al dueño de la clave.

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
pytest tests/ -q -m "not red"       # 1.230 tests, sin red
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
