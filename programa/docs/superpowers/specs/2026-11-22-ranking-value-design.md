# Ranking value — small y mid caps con potencial de crecimiento

**Fecha:** 2026-11-22
**Estado:** diseño, pendiente de plan
**Sub-proyecto:** R (depende de Q, la caducidad de la caché de la SEC)
**Origen:** `algoritmo_de_selecci_n_de_acciones.md` (pseudoalgoritmo del autor),
adaptado a cómo trabaja el programa.

## Qué entrega

Un segundo ranking, aparte del actual. El actual ordena el S&P 500 por calidad,
crecimiento, valoración y solidez frente al sector, y tiende a elegir empresas
grandes y populares cuyo potencial de crecimiento ya se ha estrechado. Este busca
**small y mid caps baratas que crecen** (*value/GARP*):

- Sale de otro universo: **S&P 400 + S&P 600**.
- Primero pasa un **filtro duro** de seis reglas.
- Las que pasan se ordenan con el motor de z-scores sectoriales que ya existe,
  con pesos inclinados a valoración y crecimiento.
- Las compras de directivos (Form 4) suben puntos.

En la pantalla de Candidatos, un selector elige entre «Calidad (actual)» y
«Value small/mid». Las dos listas pasan por la misma revisión, acta y
optimizador.

El ranking actual **no cambia**: ni su criterio congelado (`ranking/criterio.py`)
ni su salida.

## Universo

- Una foto fija nueva, `research/data/sp400_sp600_members_<fecha>.csv`, con las
  columnas `ticker, indice, sector_gics`. La genera un script nuevo,
  `scripts/bootstrap_universe_value.py`, desde las tablas de Wikipedia de los
  dos índices, igual que `bootstrap_universe.py`.
- Se registra en `fundamentals/universe._FUENTES` como `"sp400_sp600"`.
- Sus sectores entran en el mismo mapa que usa `build_panel` (`load_sectors`).
- Se refresca a mano cada trimestre: S&P reequilibra en marzo, junio,
  septiembre y diciembre.
- La primera corrida baja unas 1.000 empresas de la SEC, así que tarda (del
  orden de una hora). Las siguientes las sirve la caché, con la caducidad de Q.

## Datos nuevos

| Dato | De dónde | Caché |
|---|---|---|
| Último cierre y máximo de 52 semanas | `research.loader.load_ohlcv`, ventana de los últimos 365 días, todo el universo en lotes | La clave lleva la fecha de fin, así que caduca sola cada día |
| Capitalización actual | Último cierre × `acciones_diluidas` del último trimestre | — |
| PER actual | Último cierre / BPA diluido TTM | — |
| Deuda/Patrimonio | `deuda_total` / `patrimonio_neto` del último trimestre (líneas que ya existen en `fundamentals/concepts.py`) | — |
| Crecimiento anual compuesto del BPA a 3 años | BPA TTM del último trimestre frente al de 12 trimestres antes, `(actual/base)^(1/3) − 1`. Las dos bases deben ser positivas. Pide 16 trimestres de historia | — |
| Compras de insiders | Form 4 de la SEC con `edgartools`, solo para las que pasan el filtro | Un día, en `ranking_value/.cache/insiders/` |

El PER y la capitalización del filtro usan el **precio actual**, no el de la
fecha de publicación que usan los z-scores. El filtro decide si hoy está en el
tramo y si hoy es barata.

## Paso 1 — Guardas de calidad de dato

Son las mismas de `ranking.score.aplicar_guardas`, sin cambios: `historia_corta`,
`datos_rancios`, `pilar_sin_datos`, `cobertura_insuficiente`, y las de
`marcar_sin_pares`.

## Paso 2 — Filtro duro

Las reglas se aplican en este orden. La primera que falla da el motivo. **Un
dato que falta suspende la regla** con motivo `sin_dato_<regla>`: un filtro no
puede responder por lo que no ha visto.

| # | Motivo de exclusión | Regla | Cambio frente al pseudo |
|---|---|---|---|
| 1 | `fuera_de_tramo` | 300 M$ ≤ capitalización ≤ 10.000 M$ | — |
| 2 | `cara` | PER > 0 y (PER < mediana del PER de su sector **o** PER < 15) | Mediana y no media: un solo PER de 400 deforma la media |
| 3 | `crece_poco` | Crecimiento anual compuesto del BPA a 3 años ≥ 10 % | Calculado sobre BPA TTM, con las dos bases positivas |
| 4 | `endeudada` | Deuda/Patrimonio ≤ mediana de su sector; patrimonio > 0 | Relativo al sector, no < 1 fijo |
| 5 | `rentabilidad_baja` | ROE TTM ≥ mediana de su sector | Relativo al sector, no ≥ 15 % fijo |
| 6 | `quema_caja` | FCF TTM > 0 | — |

- Las medianas sectoriales se calculan sobre las empresas del universo que
  pasaron el paso 1 y tienen el dato, una vez por corrida.
- Si un sector tiene **menos de 3** empresas con el dato, se usa el umbral fijo
  del pseudo: PER < 15, Deuda/Patrimonio < 1, ROE ≥ 15 %.
- Los umbrales y el orden quedan congelados en `ranking_value/criterio.py`, con
  la misma regla que `ranking/criterio.py`: cambiarlos exige una enmienda
  fechada en este documento.

## Paso 3 — Orden de las que pasan

1. **Nota compuesta** sobre **todo** el universo que pasó el paso 1, no solo
   sobre las supervivientes del filtro. Los z-scores necesitan pares: entre
   ~100 supervivientes, un sector con una o dos empresas no tendría desviación
   que medir.
   - Pesos value: **valoración 35 %, crecimiento 30 %, calidad 20 %, solidez
     15 %**.
   - `ranking.score.compuesto` gana un parámetro `pesos`, que por defecto es el
     `PESOS` de siempre. El ranking actual no cambia.
2. **Ajustes**, en desviaciones típicas y sumados al compuesto, como la
   inclinación macro:
   - **+0,30, `insiders_compran`:** al menos **2 directivos distintos** con
     compras en mercado abierto (Form 4, código de transacción **P**) en los
     últimos **90 días**, y compra neta (P − S de esos mismos 90 días) de más
     de **100.000 $**. No cuentan ni opciones, ni regalos, ni planes 10b5-1
     marcados como tales.
   - **+0,20, `castigada_con_insiders`:** solo si ya tiene el ajuste anterior y
     el último cierre está al menos un **30 %** por debajo del máximo de 52
     semanas. La caída nunca puntúa sola: sin directivos comprando, una acción
     que se hunde es tan probablemente una trampa de valor como una ganga, y la
     evidencia (George y Hwang, 2004) dice que las acciones cerca de sus
     máximos rinden mejor, no peor.
3. **Macro opcional:** la misma casilla de siempre. `ranking.score.inclinar` se
   aplica después de los ajustes.
4. **Selección:** `ranking.seleccion.seleccionar` sin cambios. Top **15**,
   máximo **3 por sector**, desplazadas registradas.

## Salida

En `salidas_value/`, la misma forma que `salidas/`, para que
`aprobacion.carga.cargar_candidatos(directorio)` la lea sin cambios:

- `fichas.json`: la ficha de siempre (pilares, destacados, narrativa del LLM y
  valoración) más un bloque `value` con capitalización, PER y mediana del
  sector, crecimiento del BPA a 3 años, Deuda/Patrimonio y mediana, ROE y
  mediana, FCF TTM, último cierre, máximo de 52 semanas y caída, insiders
  (número de directivos, importe comprado y vendido, fecha de la última compra,
  o `sin_dato` con su motivo) y ajustes aplicados.
- `corrida.json`: con `"perfil": "value"`, los pesos usados, el bloque
  `datos_sec` de Q y el embudo.
- `embudo.csv`: una fila por empresa del universo con el paso donde cayó y su
  motivo. En `corrida.json` va el recuento por paso, para enseñarlo en pantalla
  como embudo («1.004 → 912 en tramo → 540 baratas → …»).
- `ranking.csv` e `informe.md`, como hoy.
- **No escribe `panel.parquet`.** El Analizador sigue comparando contra el
  S&P 500 de `salidas/`.

## Código

Paquete nuevo, `ranking_value/`:

- `criterio.py`: umbrales, orden de reglas, pesos y ajustes, congelados.
- `mercado.py`: último cierre y máximo de 52 semanas del universo, más la
  capitalización y el PER actuales.
- `filtro.py`: las seis reglas, las medianas sectoriales con su respaldo fijo y
  el embudo. Funciones puras sobre DataFrames.
- `insiders.py`: descarga y lectura de Form 4, la regla de los dos directivos y
  la caché.
- `run.py`: `construir_ranking_value(...) -> Resultado` y
  `guardar(resultado, destino)`. Reutiliza `build_panel`, `ranking.score`,
  `ranking.seleccion`, `ranking.fichas`, `ranking.llm` y `valoracion.motor`.

Cambios fuera del paquete:

- `ranking/score.compuesto`: el parámetro `pesos`.
- `fundamentals/universe.py`, `research/universe.py` y `load_sectors`: el
  universo nuevo.
- `vistas/candidatos.py`: el selector de ranking, el botón de generar que llama
  a uno u otro, y el embudo.
- El acta: cada entrada guarda `ranking: "calidad" | "value"`. Las actas viejas
  sin el campo se leen como `"calidad"`.

## Errores

- Si falla el Form 4 de una empresa, queda como `insiders: sin_dato` con el
  motivo, sin ajuste, y la corrida sigue.
- Si fallan dos seguidas por red, se deja de preguntar y las demás heredan el
  motivo. Es el mismo cortacircuitos que usa la valoración en `ranking/run.py`.
- Si no llega ningún precio actual, se aborta con `CorridaAbortada`
  `sin_precios`: sin capitalización no hay filtro posible.
- Si la SEC no está disponible, se aplica lo que dice Q.
- Si nadie pasa el filtro, no es un error. Se guarda un Top vacío con el embudo
  completo, y la pantalla dice en qué paso se quedaron todas.

## Tests

- `filtro.py`: cada regla en su borde exacto, con NaN y con patrimonio
  negativo; medianas sectoriales con y sin el respaldo de 3 empresas; orden de
  las reglas (la primera que falla da el motivo); embudo.
- Crecimiento a 3 años: bases negativas o nulas, historia de 15 frente a 16
  trimestres.
- `insiders.py` con Form 4 de prueba fijos, sin red: solo cuenta el código P,
  la regla de 2 directivos distintos, el umbral neto, la ventana de 90 días y la
  caché de un día.
- Ajustes: el de caída solo con el de insiders.
- `compuesto` con `pesos`: con los pesos por defecto, el mismo resultado de hoy.
- Una corrida completa sobre un panel sintético. `guardar` escribe lo que
  `cargar_candidatos` acepta.
- La vista: el selector, el embudo y el acta con `ranking`.
- Los tests actuales siguen pasando.
