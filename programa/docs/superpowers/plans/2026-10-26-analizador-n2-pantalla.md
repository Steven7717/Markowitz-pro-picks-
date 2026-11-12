# Analizador individual, parte 2: la pantalla — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que desde la app se pueda analizar cualquier ticker —una empresa de la SEC, una extranjera, una de la BMV o un ETF— con su ficha frente al sector, su valor intrínseco con deslizadores, un gráfico de TradingView, sus noticias y su calendario; que se pueda llevar a Revisar candidatos con su valoración en el acta; y que «Noticias y calendario» salga del menú sin que se pierda nada de lo que hacía.

**Architecture:** Una pantalla nueva, `vistas/analizador.py`, que sólo pinta. Todo lo que decide vive en módulos sin Streamlit y con tests: `medidores_analizador.py` (las palabras: etiquetas de cada motivo, rótulos, avisos y filas del resumen), `analizador/sesion.py` (lo que se guarda en la sesión y los encargos que llegan de otras pantallas), `analizador/deslizadores.py`, `analizador/grafico.py` y `analizador/archivo.py`. Los módulos de N1 ganan lo que la pantalla necesita (`referencia.construir_panel`, `analisis.con_precio_nuevo`, `valorar.proyeccion`), y el gate es el de siempre: «Añadir a la revisión» mete un `Anadido` con su valoración en Revisar candidatos, y `construir_acta` la escribe.

**Tech Stack:** Python 3.12, Streamlit 1.62 (`st.fragment`, `st.tabs(key=)`, `st.context.theme`, `st.iframe`), pandas, pytest. El widget *Advanced Chart* de TradingView, cargado desde su CDN en el navegador del usuario. Sin dependencias nuevas.

---

## Qué es este plan, y qué queda para N3

El spec (`docs/superpowers/specs/2026-10-12-analizador-individual-design.md`) parte N en tres planes. **N1, los datos**, está hecho en esta rama (`docs/superpowers/plans/2026-10-14-analizador-n1-datos.md`). Éste es **N2, la pantalla**: lo que el spec pide en «La pantalla», «El gráfico», «El menú», «El gate», «Cachés y frescura» (la hora de cada dato), «Errores» y los puntos 9, 10 y 12 de «Cómo se prueba». Las «Enmiendas del 2026-10-14» del final del spec mandan sobre el texto de arriba, y este plan las sigue.

**N3, la IA**, se escribe después sobre el código de éste: la pestaña IA con sus tres bloques (tesis y riesgos, contraste con el MD&A y explicación de la valoración), su confirmación con bandera y lo que falta de `analizador/archivo.py`. N2 no dibuja la pestaña IA. Sí trae **«Interpretar con IA» junto a los 8-K**, porque ya existe (`interprete/` y el bloque de la pestaña Noticias de Seguimiento) y se reutiliza.

## Decisiones tomadas con el usuario (2026-10-26) — no se reabren

1. **El panel de referencia se construye aparte.** Un botón del Analizador construye sólo `salidas/panel.parquet` con una función nueva, `analizador.referencia.construir_panel(ruta=RUTA_PANEL)`, que corre `construir_ranking(con_llm=False, con_valoracion=False)` y escribe de forma atómica (temporal y `os.replace`). *Por qué:* «Generar gratis» (`guardar(construir_ranking(...))`) pisaría las fichas con IA que el usuario pagó y, con ellas, sus casillas marcadas y sus añadidos a mano (revisión final de N1). `ranking.run.guardar` sigue escribiendo el panel junto a los candidatos como hoy. Como el panel y los candidatos ya no tienen por qué ser de la misma corrida, la pantalla enseña las dos fechas y avisa si el panel es más nuevo (la ficha de un candidato puede diferir un poco de la de Revisar candidatos). Hay también un botón para rehacerlo cuando se ha quedado atrás del último trimestre de los tickers analizados: con un panel viejo, los de yfinance salen `historia_corta`.
2. **La IA es de N3.** N2 no dibuja la pestaña IA. «Interpretar con IA» junto a los 8-K sí está en N2 y se reutiliza tal cual. *Por qué:* ya existe y lo que Noticias aportaba sobre los hechos no debe perderse al quitarla del menú.
3. **El valor se enseña en la moneda del precio**: `valor / divisa.tipo_precio`. El margen de seguridad es un cociente y sale igual en las dos. *Por qué:* `valorar` da los valores en la moneda de la valoración (AMX: 554,5 MXN, que son 29,69 $), y el spec pide la del precio.
4. **El gate deja pasar sólo lo que cotiza en dólares.** AMX y TSM pasan; WALMEX.MX no. Lo que va al acta es la valoración de los supuestos del programa tal cual sale de `valorar`, con sus claves `moneda` y `divisa`: la de AMX va en MXN y el acta lo dice con esas claves. No se convierte ni se bloquea. *Por qué:* el optimizador baja precios sin convertir divisas (mezclar una serie en pesos con series en dólares es el error que L evitó), y lo guardado tiene que ser comparable entre actas.
5. **`sin_prima_pais` sólo se enseña si el país no es EE. UU. y el ticker no es del S&P 500.** GRMN, ACN o MDT se valoran exactamente como en M y no llevan el aviso. *Por qué:* avisarlas diría que su valoración es distinta de la de candidatos, y no lo es.
6. **AAPL.MX y parecidos**: si un ticker con sufijo de bolsa tiene su base en el S&P 500, la fila y el detalle avisan de que es la misma empresa y remiten a analizar la base para su ficha de la SEC. No se fusionan. *Por qué:* en N1 AAPL.MX entraba en IT al lado de la propia AAPL (217 de 424, 137,6 $ frente a 183,0), con cifras de Yahoo.
7. **El Bono M**: se enseña la fecha de la subasta (ya va en la procedencia de la tasa libre) y se avisa si tiene más de 56 días. *Por qué:* `divisas.bono_m` sirve la última subasta guardada tenga la edad que tenga, y 56 días es la mayor separación medida entre dos subastas.
8. **Las etiquetas de todos los motivos van en un módulo puro con tests**, `medidores_analizador.py`, al lado de `medidores.py` y `medidores_valoracion.py`. Las exclusiones reutilizan las frases de `aprobacion/carga.py`. El texto sigue el registro de CONTEXTO y en disco no se guarda texto de pantalla.
9. **Casos con rótulo propio:** el puesto es «global, entre N» (las del panel salen «de 423» y las insertadas «de 424»); una ficha con veredicto y sin valor base (7203.T, `quema_caja`); BRK-B, cuyo `sin_pares` no viene del sector sino de que le faltan sus propios múltiplos; un voto de pares sobre una empresa excluida por una guarda; los emisores semestrales en `historia_corta`.
10. **Los deslizadores** viven en un `st.fragment` y sólo llaman a `valorar`, `sensibilidad` (y `proyeccion`) con las `Entradas` guardadas, sin red; cada llamada va en un `try`, porque `aplicar` lanza `ValueError` con lo que escribe el usuario, y el mensaje se enseña; con `valoracion["motivo"] == "error_interno"` no se dibujan; «Restaurar los del programa» los vuelve a su sitio; lo movido no se guarda.
11. **El `Analisis` de cada ticker se cachea en `st.session_state`.** Quince tickers en frío tardan cerca de un minuto: lleva barra de progreso. «Actualizar precios» sólo rehace lo que depende del precio.
12. **El gráfico es el Advanced Chart de TradingView** (incrustado con `st.iframe`, que en Streamlit 1.62 sustituye a `streamlit.components.v1.html`: D23), con la tabla congelada de bolsas del spec. La traducción del símbolo es una función pura con tests (`BRK-B` → `NYSE:BRK.B`, `WALMEX.MX` → `BMV:WALMEX`, bolsa desconocida sin prefijo). Debajo, el texto del spec sobre el estudio D y lo que se sabe y se dice: TradingView sabe qué ticker se mira, sin conexión no carga, y la BMV va con retraso.

## Decisiones de este plan, que el spec no fijaba (para revisarlas)

- **D1. «La misma empresa» sólo con `.MX`.** En el Sistema Internacional de Cotizaciones de la BMV las extranjeras cotizan con su símbolo de origen y `.MX`. En otras bolsas el mismo símbolo es otra empresa: T.TO es TELUS y T es AT&T; BA.L es BAE Systems y BA es Boeing. Afirmar «es la misma empresa» ahí sería falso.
- **D2. «Del S&P 500» es la tabla congelada de sectores** (`fuente_sector == "sp500"`), no la presencia en el panel. Es el universo con que se construye el panel, y funciona también sin panel. Vale para `sin_prima_pais` (decisión 5) y para la base de AAPL.MX (decisión 6).
- **D3. Las preferentes** (`JPM-PC`, `T-PA`) se reconocen por la forma que usa Yahoo (`^[A-Z]+-P[A-Z]$`; ninguna clase del S&P 500 la tiene, sólo BF-B y BRK-B llevan guion) y se avisan: su ficha y su valoración son las de la empresa entera. No se bloquean ni en el análisis ni en el gate. La nota de N1 las dejaba «sin comprobar ni decidir».
- **D4. El detalle se elige con un desplegable debajo del resumen, no pulsando la fila.** La tabla de Streamlit es un lienzo (glide-data-grid): la selección de filas no la lee bien un lector de pantalla ni la pulsa con fiabilidad el navegador del recorrido. El desplegable lleva clave y sobrevive a la navegación.
- **D5. Un ETF no tiene «Añadir a la revisión».** No se valora, y el spec le deja sólo precio y clase en el Resumen. Se dice que, si se quiere en el optimizador, se añade a mano en Revisar candidatos.
- **D6. «Analizar a fondo» manda los quince candidatos** (son exactamente `MAX_TICKERS`) y, desde la ficha de uno, deja ése elegido en el detalle. Hay un botón general encima de la lista y uno en cada ficha.
- **D7. El bloque de «Interpretar con IA» de Seguimiento se saca a `vistas/panel_ia.interpretar_hechos`** y lo usan las dos pantallas: copiarlo serían dos copias de un camino que cobra. Lee los seis 8-K destacados más recientes (`noticias.resumen.TOPE_HECHOS`, el mismo tope que Seguimiento, que mantiene el peor caso por debajo de `TOPE_USD_POR_PULSACION`), con `pesos=()` y `tickers={ticker}`, y guarda en `analisis/<TICKER>.json` con el formato y las funciones de `interprete/archivo.py`, que es lo que el spec pide para N3. **Aviso para N3**: `interprete.archivo.anotar_hechos` reescribe el fichero sólo con `hechos` y `rebalanceo`; una clave más que N3 guarde ahí se perdería en la siguiente lectura de 8-K si no cambia antes cómo se escribe. Sin confirmación adicional, como en Seguimiento: la confirmación con bandera del spec la añade N3 a los cuatro bloques a la vez.
- **D8. «Actualizar precios» respeta la caché de quince minutos de `mercado`** (`VALIDEZ["perfil"]` e `identidad`). Pulsarlo dos veces seguidas no vuelve a Yahoo; la fila enseña la hora de la cotización, así que se ve.
- **D9. Un defecto al hacer la ficha frente al sector ya no se lleva la fila entera** (nota 31 de N1): `motivo_referencia = "error_interno"`, la traza va al log, y la identidad y la valoración se quedan.
- **D10. La proyección a 10 años sale de `dcf.proyeccion`**, y `valor_empresa` pasa a sumarla: la tabla plegada y el valor base no pueden separarse.
- **D11. «El panel es más nuevo que los candidatos» se mide por la hora de los ficheros**, con un minuto de holgura: `guardar` los escribe con segundos de diferencia y `construir_panel` tarda al menos dos minutos. `corrida.json` lleva el día pero no la hora.
- **D12. «El panel se quedó atrás» se mide con `Referencia.filas_posteriores`**, las filas propias que no entraron por ser posteriores al último trimestre del panel, y con `sin_trimestres_comparables`, que es cuando no entra ninguna.
- **D13. «Cargar de un libro» rellena el campo de tickers y no analiza.** Si el libro trae más de quince, se dice cuántos sobran y no se analiza hasta que se quiten. Noticias permitía elegir activos con un selector; aquí el campo es editable.
- **D14. Sin `EDGAR_IDENTITY` el resolver no cambia** (nota 40): sin el correo tampoco se bajan los estados de la SEC, así que servir la clase de la caché no daría una ficha. La pantalla lo avisa una vez, con el botón a Perfil.
- **D15. En el recorrido, «Aprobar» escribe un acta de verdad en `actas/`**, que es el registro del usuario y no se borra desde la app. Se le pide permiso antes de pulsarlo, igual que con los botones de IA, y el informe dice qué fichero se escribió.
- **D16. El glosario del valor intrínseco y «Cómo se leen los medidores» van una vez, encima de las pestañas del detalle** («la primera vez en cada pantalla»). El texto de los medidores sale a `medidores.como_se_leen()`, que Revisar candidatos pasa a usar: era una cadena dentro de su guion.
- **D17. El motivo que se redacta para «Añadir a la revisión» habla de los supuestos del programa** y no se reescribe al mover deslizadores; es editable, y la pantalla recuerda que, si se movieron, conviene decirlo.
- **D18. La pantalla no usa `analizar_varios`**: necesita el panel para otras cosas (su fecha, su último trimestre, cuántos pares tiene cada sector) y llama a `analizar` con él, ticker a ticker, para la barra de progreso. `analizar_varios` se queda para `scripts/sondear_analizador.py`.
- **D19. No se tocan las dos `.info` por ticker (nota 29) ni las duplicaciones de la nota 45**: son rendimiento y diseño, no corrección, y sus tests las cubren.
- **D20. En Seguimiento, «Ver todas las noticias» pasa a «Abrir en el Analizador»**, que manda los tickers del libro por el mismo canal que «Analizar a fondo».
- **D21. El gráfico no deja cambiar de símbolo** (`allow_symbol_change: false`): está atado al ticker analizado, y TradingView no tiene por qué ver nada más.
- **D22. La BMV no se incrusta: se enlaza.** Al arrancar la pantalla, el widget con `BMV:WALMEX` dijo «Símbolo solo disponible en TradingView» y «Este símbolo no existe»; `NASDAQ:MU` y `AMEX:SPY` sí se vieron. Para las bolsas de `grafico.SOLO_EN_TRADINGVIEW` (hoy sólo `MEX`) la pestaña dice por qué no hay gráfico y enlaza a la página del símbolo en TradingView. El spec daba por hecho que se vería.
- **D23. `st.iframe` y `width="stretch"`, no `components.v1.html` ni `use_container_width`.** Streamlit 1.62 avisa en la consola de que se retiran. El resto de la app sigue usando `use_container_width`; cambiarlo es trabajo aparte.

## Este plan se aplicó entero antes de entregarlo

Al escribirlo se aplicaron sus diecinueve tareas de código, tal cual están aquí, en un worktree temporal: la suite quedó en verde (de 3166 pasando a 3376, con 5 omitidos: 210 tests nuevos) y la pantalla arrancó en otro puerto con MU, WALMEX.MX, TSM, JPM, SPY y ZZZZQ, sin pulsar la IA ni construir el panel. De ahí salieron D22, D23 y el arreglo de la altura del gráfico (Task 8): con `autosize`, TradingView reescribe el estilo del contenedor y, sin altura en `html` y `body`, el gráfico salía de 150 píxeles en un marco de 520. Los deslizadores (moverlos, «con tus supuestos», «Restaurar», el error de un coste no positivo), la puerta de WALMEX.MX y las pestañas de un ETF se vieron funcionar, y la versión final de la pantalla, con el enlace de la BMV, corrió sin excepciones con `streamlit.testing.v1.AppTest`. El worktree se borró después.

## Las notas de N1 para N2, y dónde queda cada una

De `notas-para-n2-y-plan.md` (líneas «Para N2» y «De la revisión final de N1»). Las que eran para la Task 18 de N1 ya están en el spec y en CONTEXTO.

| Nota | Dónde se resuelve |
|---|---|
| `separar("BRK B")` da BRK y B (Barrick) | Task 1, `nombre`; Task 11, columna «Nombre» del resumen |
| `PEÑOLES.MX` podría sugerir `PE&OLES.MX` | Task 1, `aviso_invalidos` |
| `MKC.V` como TSX Venture: sugerir el guion | Task 1, `sugerencia_sin_red` y `motivo_de_la_fila` |
| AAPL.MX par de sí misma | Decisión 6 y D1; Task 4, `aviso_misma_empresa` |
| Las preferentes (JPM-PC, T-PA) | D3; Task 4, `aviso_preferente` |
| BRK-A y BRK-B comparten CIK | Ya comprobada en la Task 17 de N1 (mismo valor en su base); nada que hacer |
| Un ticker que Yahoo no conoce sale `sin_red` | Task 1, `MOTIVO_ANALISIS["sin_red"]` |
| El puesto es el global, `desplazo_a` vacío | Decisión 9; Task 4, `puesto`, `nota_puesto`, `puesto_en_tarjeta` |
| Sector sin pares antes de bajar nada | Hecho en N1 (`sector_sin_pares`); Task 1, su etiqueta |
| Panel viejo deja fuera a los de yfinance (`historia_corta`) | Decisión 1, D12; Tasks 2, 4 (`texto_exclusion`, `aviso_panel_atrasado`) y 14 (botón «Rehacer el panel») |
| Plazos de la SEC fuera de ella (Tencent), split de HDB, SHEL.L y 7203.T sin PER | Ya en el spec y en CONTEXTO («Lo que N1 no resuelve») |
| `_fetch_batch` guarda una descarga vacía | Fuera de N2: sigue en «Lo que N1 no resuelve» como tarea aparte |
| `valorar` da los valores en la moneda de la valoración | Decisión 3; Task 5, `en_moneda_del_precio` |
| `fallida("sin_bono_m")` pierde el motivo concreto | Task 1, `MOTIVO_TASA`; Task 7, `falta_tasa`; Task 11, `motivo_de_la_valoracion` |
| `sin_prima_pais` en las del S&P 500 domiciliadas fuera; GRMN | Decisión 5, D2; Task 4, `aviso_sin_prima_pais` |
| La beta de SHEL.L con r² ≈ 0 | Ya resuelta: `medidores_valoracion.procedencia` enseña el R² junto a la beta, en la lista de supuestos que pinta el Analizador |
| Voto de pares con una guarda que excluye; `historia_corta` semestral | Decisión 9; Task 4, `detalle_pares` y `texto_exclusion` |
| Sin ficha, el motivo está en `motivo_referencia` | Task 4, `detalle_pares`; Task 11, `frente_al_sector` |
| 15 tickers en frío ≈ 1 minuto; dos `.info` por ticker | Decisión 11 (barra de progreso, Task 14); D19 |
| Panel real en el scratchpad | No hace falta: el recorrido usa el de `salidas/` o lo construye (decisión 1) |
| `error_interno` con `entradas`: sin deslizadores, cada llamada en un `try`; defecto en `_filas_propias` se lleva la fila | Decisión 10 (Task 16); D9 (Task 9) |
| BRK-B `sin_pares` sin que falten pares | Decisión 9; Task 4, `detalle_pares` |
| 7203.T con veredicto y sin valor base | Decisión 9; Task 4, `sin_valor_base` |
| «de 423» y «de 424» | Decisión 9; Task 4, `nota_puesto` |
| Coste de `frente_al_sector`: cachear el `Analisis` | Decisión 11; Tasks 10 y 14 |
| AMX al acta en pesos | Decisión 4; Task 12 |
| «Construir el panel» no puede ser «Generar gratis» | Decisión 1; Task 3 |
| Motivos sin rótulo (`tipo_no_soportado`, `sin_red_edgar`, `sin_identidad_edgar`, `error_interno`, `sin_panel`, `sin_sector`, `sector_sin_pares`, `sin_trimestres_comparables`, `sin_historia` como trimestres, toda la lista de `motivo_r_f`); exclusiones con `aprobacion/carga.py` | Decisión 8; Task 1 |
| Sin `EDGAR_IDENTITY`, un ticker del panel sin clase | D14; Task 14 (aviso con botón a Perfil) |
| El Bono M caducado se sirve con cualquier antigüedad | Decisión 7; Task 4, `aviso_bono_m` |
| Una fallida trae `moneda=None`: sacarla de `divisa` | Task 5, `en_moneda_del_precio` |
| `RUTA_PANEL` absoluta y `guardar` con `"salidas"` relativo | Task 2, test `test_las_fichas_van_al_lado_del_panel` (lo fija) y `RUTA_FICHAS` |
| Interfaz que N2 consume: `analizar_varios`, `MAX_TICKERS`, `supuestos.movidos`, `adr_dudosa`, `valorar.sensibilidad` | `MAX_TICKERS` (Task 14), `movidos` (Task 7, `nombres_movidos`), `adr_dudosa` (Task 4), `sensibilidad` (Task 16); `analizar_varios`, D18 |
| Duplicaciones (cinco pasos del ranking, regla del ancla, respaldo del precio, `estados` dos veces) | D19: fuera de N2 |

## Lo que hacía «Noticias y calendario», y adónde va

Leída entera `vistas/noticias.py` (332 líneas) antes de borrarla:

| Lo que hacía | Dónde queda |
|---|---|
| Cabecera: hechos separados de la prensa, «Aquí no se recomienda nada» | Cabecera del Analizador y pie de su pestaña de noticias (Tasks 14 y 17) |
| Elegir un libro (`libros.disponibles`, `libros.desplegable`), nombrando los ilegibles | «Cargar de un libro» (Task 14) |
| Sin libros: «Todavía no llevas ningún libro» y botón a Seguimiento | El desplegable de «Cargar de un libro» lo dice (Task 14) |
| Tickers = lo que se tiene más lo que el objetivo dice que se debería tener | `seguimiento.posiciones.tickers_a_mirar` (Task 10) |
| Libro sin activos: mensaje | «Cargar de un libro» lo dice (Task 14) |
| Selector de activos y «Actualizar» con `forzar` | El campo de tickers es el selector; «Actualizar noticias» por ticker en su pestaña (Task 17) |
| Agenda, hechos y prensa por `traer.traer`, problemas agrupados por fuente | Agenda de todos al analizar, agrupando problemas (Task 14); las tres fuentes del ticker en su pestaña (Task 17) |
| «Lo que viene»: fechas en orden, «hoy», «mañana», «en N días»; vacío explicado | «Lo que viene» bajo el resumen, de todos los tickers (Task 14), y en cada pestaña (Task 17); `noticias.texto.cuanto_falta` (Task 11) |
| Punteros macro (FOMC, IPC, empleo, PIB/PCE) con su explicación | Bajo «Lo que viene» del resumen (Task 14) |
| Hechos: destacados por fecha, tope de 40 con aviso; plegados en un desplegable; «sólo trámite»; «ningún 8-K» explicado | Pestaña «Noticias y calendario» (Task 17), con `ma.repartir_hechos` y `ma.recorte` (Task 11) |
| Prensa: medio y formato (el vídeo con nombre), fecha, resumen de 240 caracteres, tope de 40 | Pestaña (Task 17), con `ma.formato_noticia` (Task 11) |
| La hora de cada descarga, su validez y lo caducado; «La hora se enseña siempre» | Pestaña (Task 17), con `ma.linea_de_hora` (Task 11) |
| `st.switch_page("vistas/noticias.py")` desde Seguimiento y Primeros pasos | «Abrir en el Analizador» y la tarjeta 6 de Primeros pasos (Task 19) |

Lo único que no se conserva igual es **la lista conjunta de 8-K de todo un libro**: el Analizador los da ticker a ticker. La pestaña Noticias de Seguimiento sigue dando el resumen conjunto de los seis más recientes, con su interpretación, y el spec lo pide así («la pestaña de noticias del panel de Seguimiento se queda como está»).

## Mapa de ficheros

| Fichero | Qué hace | Tasks |
|---|---|---|
| `medidores_analizador.py` (nuevo) | Las palabras del Analizador: etiquetas, rótulos, avisos, filas, textos del panel y del gate | 1, 4, 5, 7, 11, 12 |
| `analizador/referencia.py` | `Referencia.filas_posteriores`, `trimestre_final`, `pares_en_panel`, `Frescura`, `frescura`, `construir_panel` | 2, 3 |
| `analizador/divisas.py` | `SEPARACION_MAXIMA_SUBASTAS` | 4 |
| `analizador/analisis.py` | `pilar_valoracion`, la ficha que falla no se lleva la fila, `con_precio_nuevo` | 2, 9 |
| `analizador/valorar.py` | `proyeccion` | 6 |
| `analizador/deslizadores.py` (nuevo) | Qué se mueve, entre qué cifras y qué cuenta como movido | 7 |
| `analizador/grafico.py` (nuevo) | El símbolo de TradingView y el HTML del widget | 8 |
| `analizador/sesion.py` (nuevo) | Las claves de la sesión, los encargos y la caché de análisis | 10 |
| `analizador/archivo.py` (nuevo) | Dónde se guardan las lecturas de la IA de un ticker | 13 |
| `valoracion/dcf.py` | `Ano`, `Proyeccion`, `cumple_gordon`, `proyeccion`, `terminal`, `proyeccion_de`; `valor_empresa` suma la proyección | 6 |
| `medidores.py` | `tarjeta_candidato(ficha, puesto=None)` sin nota compuesta; `como_se_leen()` | 4, 15 |
| `medidores_valoracion.py` | `con_tus_supuestos` en `distintivo` y `resumen`; `valoracion_en_una_linea` | 5 |
| `aprobacion/acta.py` | `Anadido.valoracion`, `problema_al_anadir`, `valoracion_de_entrada` | 12 |
| `noticias/texto.py` | `cuanto_falta` | 11 |
| `seguimiento/posiciones.py` | `tickers_a_mirar` | 10 |
| `vistas/analizador.py` (nuevo) | La pantalla | 14–18 |
| `vistas/panel_ia.py` | `interpretar_hechos`, el bloque de Seguimiento | 13 |
| `vistas/seguimiento.py` | Usa `interpretar_hechos`; «Abrir en el Analizador» | 13, 19 |
| `vistas/candidatos.py` | `problema_al_anadir`; la valoración de los añadidos; `como_se_leen`; «Analizar a fondo» | 12, 15, 18 |
| `vistas/actas.py` | La valoración con que entró cada aprobada | 12 |
| `vistas/perfil.py` | `analisis/` y las cachés del Analizador en «Dónde vive todo» | 13 |
| `vistas/inicio.py`, `vistas/libros.py`, `seguimiento/libro.py` | Primeros pasos y comentarios sin Noticias | 19 |
| `app.py` | El Analizador en «Análisis»; Noticias fuera | 14, 19 |
| `vistas/noticias.py` | **Se borra** | 19 |
| `.gitignore`, `../README.md` | `analisis/`; el README sin Noticias y con el Analizador | 13, 19 |
| Tests nuevos | `test_medidores_analizador.py`, `test_analizador_deslizadores.py`, `test_analizador_grafico.py`, `test_analizador_sesion.py`, `test_analizador_archivo.py`, `test_vistas_analizador.py`, `test_navegacion.py` | — |

## Convenciones del repo, para cada tarea

- Todos los comandos se ejecutan desde `programa/`. La suite normal es `uv run pytest tests/ -q -m "not red"`; antes de este plan da **3166 passed, 5 skipped** (3171 recogidos).
- Comentarios y docstrings en castellano, con acentos, que explican el **porqué**.
- Lógica sin Streamlit; las vistas sólo pintan. Las vistas se prueban leyendo su fuente con `ast`, como `tests/test_vistas_optimizador.py`.
- En disco no se escribe texto de pantalla: se guardan claves.
- En código nuevo de Streamlit, `width="stretch"` y no `use_container_width=True`, y `st.iframe` y no `streamlit.components.v1.html`: la 1.62 los da por obsoletos (D23).
- Todo texto que no escribió el programa (Yahoo, la SEC, el modelo, la prensa) pasa por `noticias.texto.plano` antes de un `st.markdown`, `st.caption`, `st.info`, `st.warning` o `st.error`. En `st.dataframe` no hace falta: no interpreta markdown.
- Ningún test escribe en `salidas/`, `actas/`, `libros/` ni `analisis/`: usan `tmp_path`.
- Cada commit termina con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Rama `feat/analizador-individual`; nunca commit en `master`, nunca push, nunca `git add -A`, `stash`, `reset` ni `checkout -- .`.

---
### Task 1: Las etiquetas de los motivos del Analizador

> **Ejecutada** (bbf824f) el 2026-10-26. De la revisión de las Tasks 1-10 (2026-10-27, d1c8480): `historia_corta` fuera de la SEC ya no niega que la empresa sea joven —«suele pasar con las que publican cada semestre»—, «ADR» va glosado y la celda dice «fuera del ranking». De la revisión de las Tasks 11-19 (2026-11-10, c11051b): «Sin ficha frente al sector» sin dos veces dos puntos. Manda el código vivo.

`analizador/` devuelve claves y N1 dejó once sin rótulo en ningún sitio. Este módulo las dice todas, culpando a quien toca. Las exclusiones del ranking reutilizan las frases de `aprobacion/carga.py`.

**Files:**
- Create: `medidores_analizador.py`
- Test: `tests/test_medidores_analizador.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_medidores_analizador.py`:

```python
"""Las palabras del Analizador.

Cada clave que escribe `analizador/` tiene su etiqueta, y cada etiqueta culpa a
quien toca: un motivo es una afirmación (la lección de M y de N1). Las tablas se
contrastan contra las cadenas que aparecen de verdad en el código, para que una
etiqueta no hable de una clave que nadie escribe.
"""

import ast
from pathlib import Path

import pytest

import medidores_analizador as ma
from analizador.analisis import Analisis
from analizador.resolver import Identidad
from aprobacion.carga import MOTIVOS_EN_CASTELLANO

RAIZ = Path(__file__).resolve().parent.parent


def _literales(*rutas: str) -> set:
    """Las cadenas escritas en esos ficheros: las claves que el código puede devolver."""
    salida = set()
    for ruta in rutas:
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        salida |= {
            n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    return salida


def identidad(ticker="MU", moneda="USD", pais="United States",
              nombre="Micron Technology, Inc.", bolsa="NMS", precio=100.0):
    return Identidad(ticker, "EQUITY", nombre, bolsa, moneda, moneda, "Technology",
                     "Semiconductors", pais, precio, "2026-10-26T20:00:00+00:00")


# Las claves de `Analisis.motivo`: `resolver.resolver`, `resolver.clase_de`,
# `resolver.formularios_sec`, `mercado._traer` y `analisis.analizar`.
MOTIVOS_DEL_ANALISIS = {
    "sin_red", "tipo_no_soportado", "sin_red_edgar", "sin_identidad_edgar", "error_interno",
}
# Las de `Analisis.motivo_referencia`: las de su docstring, de `kpis` y de `mercado`.
MOTIVOS_DE_LA_REFERENCIA = {
    "sin_panel", "sin_sector", "sector_sin_pares", "sin_estados", "sin_historia",
    "sin_precio", "sin_trimestres_comparables", "sin_red", "error_interno",
}
# Las de `Entradas.motivo_r_f` que no son «ok»: Banxico, `divisas.bono_m` y el Tesoro.
MOTIVOS_DE_LA_TASA = {
    "sin_token", "token_invalido", "sin_red", "respuesta_rara", "sin_dato", "sin_tasa_libre",
}


def test_cada_clase_tiene_su_etiqueta_y_su_fuente_de_datos():
    assert set(ma.CLASE) == set(ma.FUENTE_DE_DATOS) == {"sec", "extranjera_sec", "sin_sec", "etf"}


def test_cada_motivo_del_analisis_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_ANALISIS) == MOTIVOS_DEL_ANALISIS
    escritos = _literales("analizador/resolver.py", "analizador/analisis.py", "valoracion/mercado.py")
    assert MOTIVOS_DEL_ANALISIS <= escritos


def test_cada_motivo_de_la_referencia_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_REFERENCIA) == MOTIVOS_DE_LA_REFERENCIA
    escritos = _literales("analizador/analisis.py", "analizador/kpis.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_REFERENCIA <= escritos


def test_cada_motivo_de_la_tasa_tiene_etiqueta_y_existe_en_el_codigo():
    assert set(ma.MOTIVO_TASA) == MOTIVOS_DE_LA_TASA
    escritos = _literales("seguimiento/banxico.py", "analizador/divisas.py", "valoracion/mercado.py")
    assert MOTIVOS_DE_LA_TASA <= escritos


def test_sin_red_no_afirma_que_yahoo_no_conozca_el_ticker():
    # Enmienda del spec: desde fuera de `mercado` no se distingue un símbolo
    # desconocido de una conexión caída (ZZZZQ, en el recorrido de N1).
    texto = ma.MOTIVO_ANALISIS["sin_red"]
    assert "sin conexión" in texto and "no conoce" in texto


def test_sin_historia_en_la_ficha_habla_de_trimestres_y_no_de_anos():
    assert "trimestre" in ma.MOTIVO_REFERENCIA["sin_historia"]
    assert "año" not in ma.MOTIVO_REFERENCIA["sin_historia"]


def test_sin_trimestres_comparables_culpa_al_panel_y_no_a_la_empresa():
    assert "panel" in ma.MOTIVO_REFERENCIA["sin_trimestres_comparables"]


def test_el_error_interno_de_la_fila_no_dice_que_fallo_la_valoracion():
    assert "valorar" not in ma.MOTIVO_ANALISIS["error_interno"]


@pytest.mark.parametrize(
    "tabla, clave",
    [
        (ma.MOTIVO_ANALISIS, "sin_identidad_edgar"),
        (ma.MOTIVO_TASA, "sin_token"),
        (ma.MOTIVO_TASA, "token_invalido"),
    ],
)
def test_lo_que_arregla_el_usuario_dice_donde(tabla, clave):
    assert "Perfil y ajustes" in tabla[clave]


def test_una_clave_desconocida_se_ensena_tal_cual_y_una_que_no_es_texto_no():
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, "motivo_nuevo") == "motivo_nuevo"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, ["sin_red"]) == "n/d"
    assert ma.etiqueta(ma.MOTIVO_ANALISIS, None) == "n/d"


@pytest.mark.parametrize("codigo", sorted(MOTIVOS_EN_CASTELLANO))
def test_la_exclusion_usa_las_frases_de_revisar_candidatos(codigo):
    texto = ma.etiqueta_exclusion(codigo)
    assert texto.endswith(MOTIVOS_EN_CASTELLANO[codigo])
    assert "dejarían fuera" in texto


def test_una_exclusion_desconocida_se_dice_entre_comillas():
    assert "«guarda_nueva»" in ma.etiqueta_exclusion("guarda_nueva")


def test_el_nombre_largo_deja_ver_un_ticker_mal_partido():
    # `separar("BRK B")` da BRK y B, y B es Barrick, no la clase B de Berkshire.
    b = Analisis("B", "sec", identidad("B", nombre="Barrick Mining Corporation"), None)
    assert ma.nombre(b) == "Barrick Mining Corporation"
    assert ma.nombre(Analisis("ZZZZQ", None, None, "sin_red")) == "—"


def test_una_ene_se_sugiere_con_el_ampersand_de_yahoo():
    aviso = ma.aviso_invalidos(["PEÑOLES.MX", "A..B"])
    assert "PE&OLES.MX" in aviso and "A..B" in aviso
    assert ma.aviso_invalidos(["A..B"]) == "Sin forma de ticker, y no se analizan: A..B."


@pytest.mark.parametrize(
    "ticker, pista",
    [("MKC.V", "MKC-V"), ("SHEL.L", "SHEL-L"), ("WALMEX.MX", None), ("MU", None), ("BRK-B", None)],
)
def test_un_sufijo_de_una_letra_puede_ser_una_clase_de_accion(ticker, pista):
    sugerencia = ma.sugerencia_sin_red(ticker)
    assert (sugerencia is None) == (pista is None)
    if pista:
        assert pista in sugerencia


def test_la_fila_de_un_ticker_sin_clase_dice_por_que_y_da_la_pista():
    assert "MKC-V" in ma.motivo_de_la_fila(Analisis("MKC.V", None, None, "sin_red"))
    assert ma.motivo_de_la_fila(Analisis("^GSPC", None, None, "tipo_no_soportado")) == (
        ma.MOTIVO_ANALISIS["tipo_no_soportado"]
    )
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_medidores_analizador.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'medidores_analizador'`.

- [ ] **Step 3: Crear `medidores_analizador.py`**

```python
"""Cómo se enseña lo que sale del Analizador: etiquetas, rótulos y filas, sin Streamlit.

`analizador/` devuelve claves --`sin_red`, `sector_sin_pares`,
`historia_corta`-- y nunca texto de pantalla: es la regla de «La etiqueta de
pantalla que se guardaba en disco». Las palabras viven aquí y sólo aquí, con
tests, y `vistas/analizador.py` pinta lo que sale de este módulo. Va aparte de
`medidores_valoracion.py`, que ya pasa de las setecientas líneas.

**Un motivo es una afirmación** (la lección de M y de N1): cada etiqueta dice a
quién culpa, y una que culpe a la empresa de un fallo de Yahoo, de la SEC o del
panel es falsa. Por eso `sin_red` no dice «Yahoo no conoce este ticker»
--`mercado` no lo distingue de una conexión caída--, y `sin_historia`, en la
ficha frente al sector, habla de trimestres y no de años.

El registro es el de CONTEXTO («Registro del texto»): el lector sabe lo que es
una acción o un sector, y los términos de nivel 2 --z-score, pilares, tasa
libre-- los glosa la pantalla una vez, con los glosarios de `medidores` y de
`medidores_valoracion`.
"""

from analizador.resolver import normalizar, tiene_sufijo
from aprobacion.carga import MOTIVOS_EN_CASTELLANO
from fundamentals.sectors import MIN_PARES

CLASE = {
    "sec": "SEC (10-K)",
    "extranjera_sec": "SEC, extranjera (20-F o 40-F)",
    "sin_sec": "Fuera de la SEC",
    "etf": "ETF",
}

# De dónde salen los números de cada clase (spec, «Las cuatro clases de ticker»).
FUENTE_DE_DATOS = {
    "sec": "los estados de la SEC (EDGAR), con el mismo motor que los candidatos",
    "extranjera_sec": (
        "los estados de Yahoo Finance: los que presenta en la SEC van en IFRS y "
        "son anuales"
    ),
    "sin_sec": "los estados de Yahoo Finance",
    "etf": "sólo la cotización: un ETF no se valora",
}

# Por qué un ticker no tiene clase (`Analisis.motivo`). Sin clase no hay detalle.
MOTIVO_ANALISIS = {
    # `mercado` no distingue un símbolo que Yahoo no conoce de una conexión que
    # falla (ZZZZQ, en el recorrido de N1): «no lo conoce» afirmaría lo que no
    # se sabe. Enmienda del spec del 2026-10-14.
    "sin_red": "Yahoo no devolvió datos (sin conexión o un símbolo que no conoce)",
    "tipo_no_soportado": "Tipo no soportado: sólo acciones y ETFs",
    "sin_red_edgar": (
        "La SEC no respondió al preguntar qué informes presenta; vuelve a "
        "intentarlo en un rato"
    ),
    "sin_identidad_edgar": (
        "Falta el correo para EDGAR, en Perfil y ajustes: sin él la SEC no "
        "responde y no se sabe qué informes presenta"
    ),
    # «al analizarlo» y no «al valorar», que es lo que dice
    # `medidores_valoracion`: aquí falló la fila entera, no la valoración.
    "error_interno": "Error interno del programa al analizarlo",
}

# Por qué no hay ficha frente al sector (`Analisis.motivo_referencia`). La
# valoración sigue, con el voto de pares `no_aplica`.
MOTIVO_REFERENCIA = {
    "sin_panel": (
        "no hay panel de referencia del S&P 500; se construye con el botón de "
        "arriba, sin tocar tus candidatos"
    ),
    "sin_sector": "su sector de Yahoo no tiene equivalente GICS, y no se adivina",
    "sector_sin_pares": (
        f"su sector no llega a {MIN_PARES} empresas en el panel del S&P 500, "
        "contándola a ella: no hay con quién compararla"
    ),
    "sin_estados": "los estados financieros de la SEC no están disponibles o no son legibles",
    "sin_precio": (
        "Yahoo no dio los precios con que se calculan sus múltiplos (PER, "
        "EV/EBITDA…)"
    ),
    # Faltan trimestres, no años: la ficha es trimestral. La etiqueta de
    # `medidores_valoracion` dice «faltan años» porque allí falta historia anual.
    "sin_historia": "Yahoo no trae ningún trimestre de sus cuentas",
    "sin_trimestres_comparables": (
        "todos sus trimestres son posteriores al último del panel: es el panel "
        "el que se quedó atrás"
    ),
    "sin_red": (
        "Yahoo no devolvió sus cuentas o el tipo de cambio (sin conexión o un "
        "error suyo)"
    ),
    "error_interno": "error interno del programa al compararla con su sector",
}

# Por qué falta la tasa libre (`Entradas.motivo_r_f`). Con el Bono M, los de
# Banxico y `sin_dato`; con el Tesoro, el de `mercado.tasa_libre`. La
# valoración fallida sólo dice `sin_bono_m`, y el concreto viaja aquí.
MOTIVO_TASA = {
    "sin_token": "falta el token de Banxico, que se pone en Perfil y ajustes",
    "token_invalido": "Banxico rechazó el token; revísalo en Perfil y ajustes",
    "sin_red": "Banxico no respondió (sin conexión o un error suyo)",
    "respuesta_rara": "Banxico respondió algo que no se pudo leer",
    "sin_dato": "Banxico no tiene ninguna subasta del Bono M en la ventana consultada",
    "sin_tasa_libre": "Yahoo no devolvió el rendimiento del Tesoro a 10 años",
}


def etiqueta(tabla: dict, clave: object) -> str:
    """La etiqueta de una clave de `tabla`.

    Una clave que no se conoce se enseña tal cual, que es mejor que esconderla,
    y una que ni es texto, «n/d»: la regla de `medidores_valoracion.etiqueta_motivo`.
    """
    if not isinstance(clave, str):
        return "n/d"
    return tabla.get(clave, clave)


def etiqueta_exclusion(codigo: object) -> str:
    """La guarda del ranking que dejaría fuera a la empresa, en palabras.

    Reutiliza `aprobacion.carga.MOTIVOS_EN_CASTELLANO`, las frases que el
    revisor lee arriba de Revisar candidatos («Quedaron excluidas 74: … sin
    datos para algún pilar entero»): detrás de «quedaría entre las empresas»
    dicen lo mismo con las mismas palabras.
    """
    if not isinstance(codigo, str):
        return "las guardas del ranking la dejarían fuera"
    frase = MOTIVOS_EN_CASTELLANO.get(codigo)
    if frase is None:
        return f"las guardas del ranking la dejarían fuera («{codigo}»)"
    return f"las guardas del ranking la dejarían fuera: quedaría entre las empresas {frase}"


def nombre(analisis) -> str:
    """El nombre largo de Yahoo, o «—».

    Va en cada fila para que se note un ticker mal partido: `separar("BRK B")`
    da BRK y B, y B es Barrick Mining, no la clase B de Berkshire.
    """
    identidad = analisis.identidad
    if identidad is None or not identidad.nombre:
        return "—"
    return identidad.nombre


def _con_ampersand(texto: str) -> "str | None":
    """El ticker con la Ñ escrita como la escribe Yahoo (`PE&OLES.MX`), o None."""
    mayusculas = texto.upper()
    if "Ñ" not in mayusculas:
        return None
    return normalizar(mayusculas.replace("Ñ", "&"))


def aviso_invalidos(invalidos: "list[str]") -> str:
    """Los trozos sin forma de ticker, tal como se escribieron, con la pista de la Ñ."""
    trozos = []
    for invalido in invalidos:
        sugerido = _con_ampersand(invalido)
        trozos.append(
            f"{invalido} (Yahoo escribe la Ñ como &: prueba {sugerido})" if sugerido else invalido
        )
    return "Sin forma de ticker, y no se analizan: " + ", ".join(trozos) + "."


def sugerencia_sin_red(ticker: str) -> "str | None":
    """La pista para un `.V`, `.L`, `.F` o `.T` que quizá era una clase de acción.

    La tabla de sufijos de bolsa es cerrada, y cuatro de una letra son también
    letras de clase: `MKC.V` se lee como TSX Venture (ver
    `resolver.SUFIJOS_DE_BOLSA`). Con guion la clase funciona siempre.
    """
    base, punto, sufijo = ticker.rpartition(".")
    if not punto or len(sufijo) != 1 or not tiene_sufijo(ticker):
        return None
    return (
        f"Si «.{sufijo}» era una clase de acción y no una bolsa, escríbela con "
        f"guion: {base}-{sufijo}."
    )


def motivo_de_la_fila(analisis) -> str:
    """Por qué un ticker sin clase no tiene análisis, con la pista si la hay."""
    texto = etiqueta(MOTIVO_ANALISIS, analisis.motivo)
    if analisis.motivo == "sin_red":
        pista = sugerencia_sin_red(analisis.ticker)
        if pista:
            texto = f"{texto}. {pista}"
    return texto
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_medidores_analizador.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add medidores_analizador.py tests/test_medidores_analizador.py
git commit -m "feat: las etiquetas de los motivos del Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Lo que la pantalla necesita saber del panel

> **Ejecutada** (7f347a5) el 2026-10-26, como estaba en el plan.

Cuatro preguntas que la pantalla hace al panel: hasta qué trimestre llega, cuántas empresas tiene un sector, si un ticker tenía trimestres que no entraron (el panel se quedó atrás) y si el panel es más nuevo que los candidatos (decisión 1, D11, D12).

**Files:**
- Modify: `analizador/referencia.py`
- Modify: `analizador/analisis.py:94-96`
- Test: `tests/test_analizador_referencia.py`

- [ ] **Step 1: Escribir los tests**

En `tests/test_analizador_referencia.py`, cambia las dos primeras importaciones de fechas y de la referencia por:

```python
from datetime import date, datetime, timedelta
```

```python
from analizador.referencia import (
    HOLGURA_MISMA_CORRIDA,
    cargar_panel,
    frente_al_sector,
    frescura,
    pares_en_panel,
    trimestre_final,
)
```

y añade al final:

```python
# --- Lo que la pantalla necesita saber del panel ------------------------------


def test_las_filas_posteriores_al_panel_se_cuentan():
    crudo = panel_crudo()
    sin_el, propias = _sin(crudo, "HE2")
    extra = propias.iloc[[-1, -1]].copy()
    extra.index = pd.DatetimeIndex([pd.Timestamp("2026-09-30"), pd.Timestamp("2026-12-31")])
    extra["trimestre"] = ["2026Q3", "2026Q4"]
    con_extra = pd.concat([propias, extra])
    assert frente_al_sector("HE2", sin_el, "Health Care", con_extra).filas_posteriores == 2
    assert frente_al_sector("HE2", sin_el, "Health Care", propias).filas_posteriores == 0
    # Una del panel nunca tiene filas fuera: el panel es su propia referencia.
    assert frente_al_sector("HE2", crudo).filas_posteriores == 0


def test_el_trimestre_final_es_el_ultimo_del_panel():
    assert trimestre_final(panel_crudo()) == "2026Q2"


def test_los_pares_de_un_sector_son_sus_empresas_en_el_panel():
    crudo = panel_crudo()
    assert pares_en_panel(crudo, "Information Technology") == 6
    assert pares_en_panel(crudo, "Utilities") == 5
    assert pares_en_panel(crudo, "Energy") == 0


def _con_hora(ruta, momento: datetime) -> None:
    ruta.write_text("x", encoding="utf-8")
    os.utime(ruta, (momento.timestamp(), momento.timestamp()))


def test_un_panel_escrito_con_sus_candidatos_no_es_posterior(tmp_path):
    # `ranking.run.guardar` escribe las fichas y el panel con segundos de diferencia.
    hora = datetime(2026, 10, 16, 12, 0, 0)
    _con_hora(tmp_path / "fichas.json", hora)
    _con_hora(tmp_path / "panel.parquet", hora + timedelta(seconds=5))
    f = frescura(tmp_path / "panel.parquet", tmp_path / "fichas.json")
    assert (f.panel, f.candidatos) == (hora + timedelta(seconds=5), hora)
    assert not f.panel_posterior


def test_un_panel_rehecho_aparte_es_posterior(tmp_path):
    hora = datetime(2026, 10, 16, 12, 0, 0)
    _con_hora(tmp_path / "fichas.json", hora)
    _con_hora(tmp_path / "panel.parquet", hora + HOLGURA_MISMA_CORRIDA + timedelta(seconds=1))
    assert frescura(tmp_path / "panel.parquet", tmp_path / "fichas.json").panel_posterior


def test_sin_candidatos_o_sin_panel_no_hay_comparacion(tmp_path):
    _con_hora(tmp_path / "panel.parquet", datetime(2026, 10, 16, 12, 0))
    f = frescura(tmp_path / "panel.parquet", tmp_path / "fichas.json")
    assert f.candidatos is None and not f.panel_posterior
    assert frescura(tmp_path / "no.parquet", tmp_path / "fichas.json").panel is None


def test_las_fichas_van_al_lado_del_panel():
    from analizador.referencia import RUTA_FICHAS, RUTA_PANEL
    from aprobacion.carga import SALIDAS

    assert RUTA_FICHAS.parent == RUTA_PANEL.parent
    # `guardar` escribe en «salidas» relativo y `RUTA_PANEL` es absoluta:
    # coinciden porque los lanzadores arrancan en programa/ (revisión final de N1).
    assert RUTA_PANEL.parent.name == SALIDAS.name
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_referencia.py -q`
Expected: FAIL con `ImportError: cannot import name 'HOLGURA_MISMA_CORRIDA'`.

- [ ] **Step 3: Implementar en `analizador/referencia.py`**

1. Cambia `from datetime import date` por:

```python
from datetime import date, datetime, timedelta
```

2. Debajo de `RUTA_PANEL`:

```python
# Las fichas de los candidatos, al lado del panel: `ranking.run.guardar` escribe
# los dos en la misma carpeta.
RUTA_FICHAS = RUTA_PANEL.parent / "fichas.json"
# Lo que separa el panel de las fichas cuando los escribe la misma corrida de
# `guardar`: unos segundos. Un panel más nuevo que eso se rehízo aparte, con
# `construir_panel`, que tarda al menos dos minutos.
HOLGURA_MISMA_CORRIDA = timedelta(minutes=1)
```

3. En `Referencia`, después de `en_panel: bool`:

```python
    # Cuántas filas propias se quedaron fuera por ser posteriores al último
    # trimestre del panel. Más de cero es que el panel se quedó atrás: con los
    # cinco trimestres de yfinance y el panel dos por detrás quedan tres, y la
    # guarda dice `historia_corta` cuando el problema es el panel (revisión de la
    # Task 11 de N1). Una del panel, siempre cero.
    filas_posteriores: int = 0
```

4. Antes de `def frente_al_sector`:

```python
def trimestre_final(panel: pd.DataFrame) -> str:
    """El último trimestre natural del panel (`"2026Q3"`): hasta dónde llega la referencia."""
    return str(panel["trimestre"].max())


def pares_en_panel(panel: pd.DataFrame, sector: str) -> int:
    """Cuántas empresas del panel son de `sector`."""
    return int(panel.index.get_level_values("ticker")[panel["sector_gics"] == sector].nunique())


@dataclass(frozen=True)
class Frescura:
    """De cuándo son el panel y los candidatos, por la hora de sus ficheros; None si no hay."""

    panel: "datetime | None"
    candidatos: "datetime | None"

    @property
    def panel_posterior(self) -> bool:
        """Si el panel se rehízo aparte después de generar los candidatos.

        Entonces la ficha de un candidato en el Analizador puede diferir un poco
        de la de Revisar candidatos, que se calculó con el panel de entonces.
        Sin candidatos no hay con qué compararlo.
        """
        if self.panel is None or self.candidatos is None:
            return False
        return self.panel - self.candidatos > HOLGURA_MISMA_CORRIDA


def _hora_del_fichero(ruta: Path) -> "datetime | None":
    try:
        return datetime.fromtimestamp(Path(ruta).stat().st_mtime)
    except OSError:
        return None


def frescura(ruta_panel: "Path | None" = None, ruta_fichas: "Path | None" = None) -> Frescura:
    """La hora del panel y la de los candidatos.

    Por la hora de los ficheros y no por `corrida.json`, que lleva el día pero
    no la hora: un panel rehecho la misma tarde no se distinguiría. Desde que el
    panel se construye aparte (`construir_panel`), panel y candidatos no tienen
    por qué ser de la misma corrida, y la pantalla enseña las dos fechas.
    """
    return Frescura(
        _hora_del_fichero(ruta_panel or RUTA_PANEL),
        _hora_del_fichero(ruta_fichas or RUTA_FICHAS),
    )
```

5. En `frente_al_sector`, la primera línea pasa a ser:

```python
    trimestre_max = trimestre_final(panel)
```

el bloque desde `en_panel = ...` hasta `if propias.empty: return None` pasa a ser:

```python
    en_panel = ticker in panel.index.get_level_values("ticker")
    posteriores = 0
    if en_panel:
        # Ordenado como lo deja `build_panel` antes de los z: el orden de las
        # filas fija el de las sumas, y con otro los z diferirían en la última
        # cifra de los del ranking.
        completo = panel.sort_index()
    else:
        if sector is None or propias is None:
            return None
        dentro = propias[propias["trimestre"].astype(str) <= trimestre_max]
        posteriores = len(propias) - len(dentro)
        propias = dentro
        if propias.empty:
            return None
```

(lo que sigue —`filas = propias.reindex(...)` hasta `completo = pd.concat(...)`— no cambia), y el `return Referencia(...)` del final gana el campo:

```python
    return Referencia(
        ficha=ficha,
        compuesto=nota,
        puesto=puesto,
        supervivientes=len(validos),
        exclusion=None if pd.isna(exclusion) else str(exclusion),
        en_panel=en_panel,
        filas_posteriores=posteriores,
    )
```

- [ ] **Step 4: Usar `pares_en_panel` en `analizador/analisis.py`**

En `_frente_al_sector`, la línea

```python
    pares = panel.index.get_level_values("ticker")[panel["sector_gics"] == sector].nunique()
```

pasa a ser:

```python
    pares = referencia.pares_en_panel(panel, sector)
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_referencia.py tests/test_analizador_analisis.py -q`
Expected: todos pasan, también los de N1 (`test_un_sector_con_menos_pares_de_los_que_pide_el_z_no_tiene_referencia` usa ahora `pares_en_panel`).

- [ ] **Step 6: Commit**

```bash
git add analizador/referencia.py analizador/analisis.py tests/test_analizador_referencia.py
git commit -m "feat: la referencia dice hasta dónde llega el panel y si es más nuevo que los candidatos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Construir sólo el panel

> **Ejecutada** (bb87027) el 2026-10-26. Su revisión añadió el test de que un panel vacío no pisa el de antes (c80aa47), y la revisión de las Tasks 1-10 (2026-10-27), el reintento de `os.replace` cuando otra sesión de Windows lee el panel (e16f150). `construir_panel` puede lanzar `OSError`, además de `CorridaAbortada`: la pantalla captura los dos. Manda el código vivo.

Decisión 1: un botón del Analizador construye el panel sin tocar los candidatos, sus fichas ni sus marcas. La escritura es atómica.

**Files:**
- Modify: `analizador/referencia.py`
- Test: `tests/test_analizador_referencia.py`

- [ ] **Step 1: Escribir los tests**

En `tests/test_analizador_referencia.py`, añade `from types import SimpleNamespace` a las importaciones, `construir_panel` a la lista importada de `analizador.referencia`, y al final:

```python
# --- El panel, construido aparte de los candidatos ----------------------------


def test_construir_el_panel_solo_escribe_el_panel(tmp_path):
    # Los candidatos de al lado, con su revisión: «Generar gratis» los pisaría.
    for nombre in ("fichas.json", "corrida.json", "ranking.csv", "informe.md"):
        (tmp_path / nombre).write_text(f"intacto {nombre}", encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    crudo = panel_crudo()
    with patch("ranking.run.construir_ranking", return_value=SimpleNamespace(panel=crudo)) as corrida, \
            patch("ranking.run.guardar", side_effect=AssertionError("guardar pisaría los candidatos")):
        panel, fecha = construir_panel(tmp_path / "panel.parquet")
    assert corrida.call_args.kwargs == {"con_llm": False, "con_valoracion": False}
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.name in antes} == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([*antes, "panel.parquet"])
    assert frente_al_sector("IN0", panel).ficha == frente_al_sector("IN0", crudo).ficha
    assert fecha == date.today()


def test_un_corte_al_escribir_deja_el_panel_de_antes_y_ningun_temporal(tmp_path):
    ruta = tmp_path / "panel.parquet"
    panel_crudo(semilla=1).reset_index().to_parquet(ruta, index=False)
    de_antes = ruta.read_bytes()
    with patch("ranking.run.construir_ranking", return_value=SimpleNamespace(panel=panel_crudo())), \
            patch("analizador.referencia.os.replace", side_effect=OSError("disco lleno")):
        with pytest.raises(OSError):
            construir_panel(ruta)
    assert ruta.read_bytes() == de_antes
    assert list(tmp_path.iterdir()) == [ruta]


def test_una_corrida_sin_panel_no_escribe_nada(tmp_path):
    with patch("ranking.run.construir_ranking", return_value=SimpleNamespace(panel=None)):
        assert construir_panel(tmp_path / "panel.parquet") == (None, None)
    assert list(tmp_path.iterdir()) == []


def test_si_la_corrida_aborta_sale_tal_cual_y_no_se_escribe_nada(tmp_path):
    # `CorridaAbortada` (la SEC no responde, o rechaza la identidad) la dice la
    # pantalla, como en Revisar candidatos.
    with patch("ranking.run.construir_ranking", side_effect=RuntimeError("la SEC no responde")):
        with pytest.raises(RuntimeError):
            construir_panel(tmp_path / "panel.parquet")
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_referencia.py -q`
Expected: FAIL con `ImportError: cannot import name 'construir_panel'`.

- [ ] **Step 3: Implementar en `analizador/referencia.py`**

1. Añade a las importaciones de arriba:

```python
import io
import os
import tempfile
```

2. Después de `cargar_panel`:

```python
def construir_panel(ruta: "Path | None" = None) -> "tuple[pd.DataFrame | None, date | None]":
    """El panel de referencia, construido y escrito aparte de los candidatos.

    Es la corrida de «Generar gratis» sin la valoración
    --`construir_ranking(con_llm=False, con_valoracion=False)`, unos dos minutos
    con la caché llena--, pero **sólo escribe el panel**: ni las fichas, ni la
    corrida, ni el informe. `ranking.run.guardar` habría pisado las fichas con
    IA que el usuario pagó y, con ellas, sus casillas marcadas y sus añadidos a
    mano (revisión final de N1). Decisión del usuario del 2026-10-26.

    Escribe de forma atómica, un temporal en la misma carpeta y `os.replace`: un
    corte a mitad deja el panel de antes, que sigue siendo un panel válido de
    una corrida anterior. `guardar` hace otra cosa --borra el viejo antes de
    escribir-- porque allí el viejo es ajeno a las fichas nuevas.

    Devuelve lo que `cargar_panel` lee del fichero escrito. Una corrida sin panel
    (un universo vacío) no escribe nada y devuelve `(None, None)`.
    `CorridaAbortada` se deja salir: quien llama sabe decirlo.
    """
    # Aquí y no arriba: `ranking.run` arrastra la IA y la valoración, y este
    # módulo lo importan el análisis de un ticker y los tests, que no las necesitan.
    from ranking.run import construir_ranking

    ruta = Path(ruta or RUTA_PANEL)
    resultado = construir_ranking(con_llm=False, con_valoracion=False)
    if resultado.panel is None or resultado.panel.empty:
        return None, None
    buffer = io.BytesIO()
    resultado.panel.reset_index().to_parquet(buffer, index=False)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # `mkstemp` y no un nombre fijo: dos pestañas pueden pulsar a la vez, y en
    # la misma carpeta porque `os.replace` sólo es atómico dentro de un volumen.
    descriptor, provisional = tempfile.mkstemp(dir=ruta.parent, prefix=".panel-", suffix=".tmp")
    temporal = Path(provisional)
    try:
        with os.fdopen(descriptor, "wb") as destino:
            destino.write(buffer.getvalue())
        os.replace(temporal, ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return cargar_panel(ruta)
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_referencia.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/referencia.py tests/test_analizador_referencia.py
git commit -m "feat: construir el panel de referencia sin tocar los candidatos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Los rótulos de los casos propios y los avisos de un ticker

> **Ejecutada** (e2c3439) el 2026-10-27. Al ejecutar la Task 14, `texto_exclusion`, `detalle_pares` y `sin_ficha` ganaron `panel_dicho`: con 7203.T el panel atrasado se leía tres veces. De la revisión de las Tasks 11-19 (2026-11-10, c11051b): `guarda_dicha_por_pares` y `texto_exclusion(..., guarda_dicha=)`, porque con AMX la guarda se leía dos veces seguidas. Manda el código vivo.

Decisión 9 y las notas de N1: el puesto global, la ficha fuera del ranking, BRK-B, la excluida que vota, los semestrales, la ficha sin valor base; y los avisos de un ticker (decisiones 5, 6 y 7, D1, D3): sin prima por riesgo país, la misma empresa que su base, la preferente, la ADR, el panel atrasado y el Bono M viejo. Cada aviso tiene una forma corta, para la fila del resumen, y una larga, para el detalle.

`medidores.tarjeta_candidato` aprende a pintar una ficha sin puesto ni nota (fuera del ranking por una guarda) y a llevar otro rótulo de puesto: hoy revienta con `compuesto=None`.

**Files:**
- Modify: `analizador/divisas.py`
- Modify: `medidores.py:423-448`
- Modify: `medidores_analizador.py`
- Test: `tests/test_medidores_analizador.py`, `tests/test_medidores.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_medidores.py`:

```python
# --- La tarjeta en el Analizador ----------------------------------------------


def test_la_tarjeta_puede_llevar_otro_rotulo_de_puesto():
    texto = sin_etiquetas(m.tarjeta_candidato(FICHA, puesto="Puesto global 25 de 424"))
    assert "Puesto global 25 de 424" in texto
    assert "#1" not in texto


def test_una_ficha_fuera_del_ranking_se_pinta_sin_nota_en_vez_de_reventar():
    # `analizador.referencia` deja puesto y compuesto en None cuando una guarda
    # la deja fuera: un 0 o un NaN se leerían como cifras.
    fuera = {**FICHA, "puesto": None, "compuesto": None}
    texto = sin_etiquetas(m.tarjeta_candidato(fuera, puesto="Fuera del ranking"))
    assert "Sin nota compuesta" in texto and "Fuera del ranking" in texto
```

En `tests/test_medidores_analizador.py`, añade a las importaciones:

```python
from datetime import date
from types import SimpleNamespace

from analizador.referencia import Referencia
from fundamentals.sectors import load_sectors
from ranking.criterio import TOPE_POR_SECTOR
from tests.test_medidores_valoracion import _fija
```

y al final:

```python
# --- La ficha frente al sector ----------------------------------------------


def ficha(pilar=0.4, puesto=1):
    return {
        "ticker": "MU",
        "sector_gics": "Information Technology",
        "puesto": puesto,
        "compuesto": None if puesto is None else 1.2,
        "pilares": {"calidad": 0.5, "crecimiento": 0.1, "valoracion": pilar, "solidez": 0.2},
        "destacados": [],
        "flojos": [],
        "cobertura": {
            "kpis_con_dato": 14,
            "pilares_con_dato": 4,
            "kpis_por_pilar": {"calidad": 7, "crecimiento": 3, "valoracion": 4, "solidez": 3},
        },
        "desplazo_a": [],
    }


def referencia(puesto=1, supervivientes=423, exclusion=None, en_panel=True, pilar=0.4, posteriores=0):
    return Referencia(
        ficha(pilar, puesto), None if puesto is None else 1.2, puesto,
        supervivientes, exclusion, en_panel, posteriores,
    )


def analisis(ticker="MU", clase="sec", ref=None, motivo_referencia=None, valoracion=None,
             entradas=None, fuente_sector="sp500", **ident):
    return Analisis(ticker, clase, identidad(ticker, **ident), None, "Information Technology",
                    fuente_sector, ref, motivo_referencia, entradas, valoracion)


def test_el_puesto_es_el_global_entre_las_que_pasan_las_guardas():
    assert ma.puesto(referencia(25, 423)) == "25 de 423"
    assert ma.puesto(referencia(None, 423, "historia_corta")) == "—"
    assert ma.puesto(None) == "—"
    assert ma.puesto_en_tarjeta(referencia(25, 423)) == "Puesto global 25 de 423"
    assert ma.puesto_en_tarjeta(referencia(None, 423, "historia_corta")) == "Fuera del ranking"


def test_la_nota_del_puesto_dice_que_es_global_y_por_que_puede_no_coincidir():
    nota = ma.nota_puesto(referencia(25, 423), "MU")
    assert "global" in nota and f"tope de {TOPE_POR_SECTOR} por sector" in nota
    assert "una más" not in nota


def test_una_insertada_se_cuenta_a_si_misma_y_se_dice_que_no_es_un_error():
    nota = ma.nota_puesto(referencia(25, 424, en_panel=False), "TSM")
    assert "424" in nota and "TSM" in nota and "no es un error" in nota


def test_la_celda_frente_al_sector():
    assert ma.frente_al_sector(analisis(clase="etf")) == "—"
    assert ma.frente_al_sector(analisis(motivo_referencia="sin_panel")).startswith("sin ficha: ")
    assert ma.frente_al_sector(analisis(ref=referencia(None, 423, "pilar_sin_datos"))) == (
        "fuera: " + MOTIVOS_EN_CASTELLANO["pilar_sin_datos"]
    )
    assert ma.frente_al_sector(analisis(ref=referencia(25, 424, en_panel=False))) == "25 de 424"


def test_historia_corta_con_el_panel_atrasado_culpa_al_panel():
    a = analisis("WALMEX.MX", "sin_sec", ref=referencia(None, 423, "historia_corta", False, posteriores=2))
    texto = ma.texto_exclusion(a)
    assert texto.startswith("Las guardas") and "panel el que se quedó atrás" in texto


def test_historia_corta_de_una_de_yahoo_apunta_a_las_que_publican_cada_semestre():
    a = analisis("NESN.SW", "sin_sec", ref=referencia(None, 423, "historia_corta", False))
    assert "cada semestre" in ma.texto_exclusion(a)


def test_historia_corta_de_una_de_la_sec_no_se_inventa_la_causa():
    texto = ma.texto_exclusion(analisis(ref=referencia(None, 423, "historia_corta", False)))
    assert "semestre" not in texto and "panel" not in texto
    assert ma.texto_exclusion(analisis(ref=referencia())) is None


def _votos(pares="neutra", motivo=None):
    return {
        "flujos": {"voto": "neutra", "motivo": None},
        "sin_crecimiento": {"voto": "neutra", "motivo": None},
        "pares": {"voto": pares, "motivo": motivo},
    }


def test_brk_b_no_vota_por_sus_multiplos_y_no_por_falta_de_pares():
    # Task 17 de N1: el XBRL de Berkshire no trae recuento ni BPA diluidos.
    a = analisis("BRK-B", ref=referencia(None, 423, "pilar_sin_datos", pilar=None),
                 valoracion=_fija(votos=_votos("no_aplica", "sin_pares")))
    texto = ma.detalle_pares(a)
    assert "no por falta de pares" in texto and "múltiplos" in texto


def test_una_excluida_que_vota_lo_dice():
    a = analisis("JPM", ref=referencia(None, 423, "pilar_sin_datos", pilar=0.3),
                 valoracion=_fija(votos=_votos("neutra")))
    texto = ma.detalle_pares(a)
    assert "vota con su pilar" in texto and MOTIVOS_EN_CASTELLANO["pilar_sin_datos"] in texto


def test_sin_ficha_el_voto_de_pares_remite_a_su_causa():
    a = analisis(motivo_referencia="sin_precio", valoracion=_fija(votos=_votos("no_aplica", "sin_pares")))
    assert ma.MOTIVO_REFERENCIA["sin_precio"] in ma.detalle_pares(a)


def test_con_ficha_sin_guarda_y_con_pilar_no_hay_nada_que_anadir():
    assert ma.detalle_pares(analisis(ref=referencia(), valoracion=_fija())) is None
    assert ma.detalle_pares(analisis(clase="etf")) is None


def test_un_veredicto_sin_valor_base_lleva_su_rotulo():
    # 7203.T en la Task 17 de N1: quema caja por su financiera cautiva.
    votos = {**_votos(), "flujos": {"voto": "no_aplica", "motivo": "quema_caja"}}
    texto = ma.sin_valor_base(_fija(valor=None, votos=votos))
    assert "no valor base" in texto and "quema caja" in texto
    assert ma.sin_valor_base(_fija()) is None
    assert ma.sin_valor_base({"version": "m1", "motivo": "sin_red"}) is None
    assert ma.sin_valor_base(None) is None


# --- Los avisos de un ticker --------------------------------------------------


def _con_divisa(sin_prima: bool) -> dict:
    return _fija(divisa={"moneda_precio": "USD", "tipo_precio": 1.0, "sin_prima_pais": sin_prima})


def test_sin_prima_pais_solo_fuera_del_sp500():
    tsm = analisis("TSM", "extranjera_sec", valoracion=_con_divisa(True), fuente_sector="yahoo", pais="Taiwan")
    assert "Taiwan" in ma.aviso_sin_prima_pais(tsm)
    # GRMN está domiciliada en Suiza y se valora exactamente como en M.
    grmn = analisis("GRMN", valoracion=_con_divisa(True), fuente_sector="sp500", pais="Switzerland")
    assert ma.aviso_sin_prima_pais(grmn) is None
    assert ma.aviso_sin_prima_pais(analisis(valoracion=_con_divisa(False), fuente_sector="yahoo")) is None


def test_la_misma_empresa_solo_en_el_sic_de_la_bmv():
    sp500 = set(load_sectors())
    assert "AAPL" in ma.aviso_misma_empresa("AAPL.MX", sp500)
    # T.TO es TELUS y T es AT&T: en otras bolsas el mismo símbolo es otra empresa.
    assert ma.aviso_misma_empresa("T.TO", sp500) is None
    assert ma.aviso_misma_empresa("WALMEX.MX", sp500) is None
    assert ma.aviso_misma_empresa("AAPL", sp500) is None


def test_una_preferente_se_reconoce_por_su_forma():
    assert ma.aviso_preferente("JPM-PC") and ma.aviso_preferente("T-PA")
    assert ma.aviso_preferente("BRK-B") is None and ma.aviso_preferente("MU") is None
    # Ninguna del S&P 500 tiene esa forma: no hay falsos positivos en el panel.
    assert [t for t in load_sectors() if ma.aviso_preferente(t)] == []


def test_el_recuento_de_una_adr_que_no_cuadra_se_avisa():
    assert "5.00" in ma.aviso_adr(5.0)
    assert ma.aviso_adr(1.0) is None and ma.aviso_adr(None) is None


def test_el_panel_atrasado_se_avisa():
    con_filas = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False, posteriores=1))
    assert "2026Q2" in ma.aviso_panel_atrasado(con_filas, "2026Q2")
    sin_ninguna = analisis("TSM", "extranjera_sec", motivo_referencia="sin_trimestres_comparables")
    assert ma.aviso_panel_atrasado(sin_ninguna, "2026Q2")
    assert ma.aviso_panel_atrasado(analisis(ref=referencia()), "2026Q2") is None
    assert ma.aviso_panel_atrasado(con_filas, None) is None


def test_el_bono_m_viejo_se_avisa_y_el_reciente_no():
    procedencia = {"fuente": "bono_m_10", "serie": "SF44071", "fecha": "2026-09-24"}
    assert ma.aviso_bono_m(procedencia, date(2026, 10, 26)) is None
    texto = ma.aviso_bono_m(procedencia, date(2026, 11, 25))
    assert "24/09/2026" in texto and "62 días" in texto
    assert ma.aviso_bono_m({"fuente": "tesoro_10", "serie": "^TNX"}, date(2027, 1, 1)) is None
    assert ma.aviso_bono_m({"fuente": "bono_m_10", "fecha": None}, date(2027, 1, 1)) is None


def test_los_avisos_llevan_su_forma_corta_y_la_larga():
    entradas = SimpleNamespace(cociente_adr=5.0, procedencia_r_f={"fuente": "tesoro_10"})
    a = analisis("AAPL.MX", "sin_sec", entradas=entradas, valoracion=_con_divisa(False),
                 fuente_sector="yahoo", moneda="MXN")
    cortos = [corto for corto, _ in ma.avisos(a, set(load_sectors()), "2026Q2", date(2026, 10, 26))]
    assert cortos == ["misma empresa que AAPL", "recuento de acciones dudoso"]
    assert all(largo for _, largo in ma.avisos(a, set(load_sectors()), "2026Q2", date(2026, 10, 26)))
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_medidores_analizador.py tests/test_medidores.py -q`
Expected: FAIL con `TypeError: tarjeta_candidato() got an unexpected keyword argument 'puesto'` y `AttributeError: module 'medidores_analizador' has no attribute 'puesto'`.

- [ ] **Step 3: La separación entre subastas, en `analizador/divisas.py`**

Cambia `from datetime import date` por `from datetime import date, timedelta`, y debajo de `ADR_TOLERANCIA`:

```python
# La mayor separación medida entre dos subastas del Bono M a 10 años. Una
# subasta más vieja que esto no es una que falte: es que Banxico no está
# respondiendo y `banxico.traer` sirve lo último guardado, tenga la edad que
# tenga (revisión final de N1). La pantalla lo avisa.
SEPARACION_MAXIMA_SUBASTAS = timedelta(days=56)
```

- [ ] **Step 4: La tarjeta, en `medidores.py`**

`tarjeta_candidato` pasa a ser:

```python
def tarjeta_candidato(ficha: dict, puesto: "str | None" = None) -> str:
    """The whole collapsed row: who it is, its composite, and the four pillars.

    `puesto` sustituye al «#3» de la ficha: el Analizador enseña el puesto
    global («Puesto global 25 de 424»), que no es el de candidatos. Y una ficha
    fuera del ranking por una guarda no tiene puesto ni nota compuesta
    (`analizador.referencia`): se dice, en vez de pintar un 0 o un NaN que se
    leerían como cifras.
    """
    cobertura = ficha.get("cobertura", {})
    con_dato = cobertura.get("kpis_con_dato")
    resumen_cobertura = (
        f" · {con_dato} de {len(TODOS_LOS_KPIS)} KPIs con dato"
        if con_dato is not None
        else ""
    )
    compuesto = ficha.get("compuesto")
    nota = (
        "Sin nota compuesta"
        if compuesto is None
        else f"Compuesto {compuesto:+.2f} (z dentro del sector)"
    )
    rotulo = f"#{ficha['puesto']}" if puesto is None else puesto
    return (
        '<div class="mpp-tarjeta">'
        '<div class="mpp-cab">'
        f'<span class="mpp-puesto">{_esc(rotulo)}</span>'
        f'<span class="mpp-ticker">{_esc(ficha["ticker"])}</span>'
        f'<span class="mpp-chip">{_esc(ficha["sector_gics"])}</span>'
        # `valoracion_de` y no `ficha.get("valoracion")`: es el mismo lector
        # que el bloque de la ficha, y con otro una valoración editada a mano y
        # sin `version` pintaba la píldora mientras el bloque decía «ficha de
        # una versión anterior».
        f"{medidores_valoracion.distintivo(valoracion_de(ficha))}"
        f'<span class="mpp-cab-der">{_esc(nota)}{_esc(resumen_cobertura)}</span>'
        "</div>"
        f"{tira_pilares(ficha)}"
        "</div>"
    )
```

- [ ] **Step 5: Los rótulos, en `medidores_analizador.py`**

Añade a las importaciones de arriba:

```python
import re
from datetime import date

import medidores_valoracion
from analizador.divisas import SEPARACION_MAXIMA_SUBASTAS, adr_dudosa
from noticias.texto import plano
from ranking.criterio import TOPE_POR_SECTOR
```

y al final del fichero:

```python
# --- La ficha frente al sector -------------------------------------------------


def puesto(referencia) -> str:
    """«25 de 424»: el puesto global entre las que pasan las guardas, o «—»."""
    if referencia is None or referencia.puesto is None:
        return "—"
    return f"{referencia.puesto} de {referencia.supervivientes}"


def puesto_en_tarjeta(referencia) -> str:
    """El rótulo de `medidores.tarjeta_candidato` en el Analizador."""
    if referencia.puesto is None:
        return "Fuera del ranking"
    return f"Puesto global {puesto(referencia)}"


def nota_puesto(referencia, ticker: str) -> str:
    """Qué es ese puesto, para que no se confunda con el de Revisar candidatos.

    Es el orden por nota compuesta entre las que pasan las guardas, sin el tope
    por sector con que se eligen las quince (enmienda del spec: con un tope de
    2 difería en 11 de 96). Y una de fuera del panel se cuenta a sí misma: las
    del S&P 500 salen «de 423» y ella «de 424», y no es un error.
    """
    texto = (
        f"Puesto global: el orden por nota compuesta entre las "
        f"{referencia.supervivientes} empresas que pasan las guardas del ranking, "
        f"sin el tope de {TOPE_POR_SECTOR} por sector con que se eligen los "
        "candidatos. Por eso puede no coincidir con el puesto de Revisar candidatos."
    )
    if not referencia.en_panel:
        texto += (
            f" {ticker} no está en el panel del S&P 500 y se cuenta entre ellas: son "
            "una más que para las del índice, y no es un error."
        )
    return texto


def frente_al_sector(analisis) -> str:
    """La celda «Frente al sector» del resumen."""
    if analisis.clase in (None, "etf"):
        return "—"
    ref = analisis.referencia
    if ref is None:
        return "sin ficha: " + etiqueta(MOTIVO_REFERENCIA, analisis.motivo_referencia)
    if ref.puesto is None:
        return "fuera: " + MOTIVOS_EN_CASTELLANO.get(ref.exclusion, str(ref.exclusion))
    return puesto(ref)


_PANEL_ATRAS = (
    " Pero aquí es el panel el que se quedó atrás: la empresa tiene trimestres "
    "posteriores al último del panel, y ésos no entran en la comparación. Rehacer "
    "el panel lo arregla."
)
_SEMESTRALES = (
    " Yahoo no trae trimestres suficientes de sus cuentas, que es lo que pasa con "
    "las empresas que publican cada semestre, como muchas europeas y las de Hong "
    "Kong: no es que la empresa sea joven."
)


def texto_exclusion(analisis) -> "str | None":
    """La guarda que la dejaría fuera, con su causa cuando la guarda la esconde.

    `historia_corta` culpa a la empresa de tener poca historia, y en el
    Analizador casi nunca es eso: o el panel está atrasado y sus últimos
    trimestres no entran, o la empresa publica cada semestre (NESN.SW, 0700.HK
    y RIO.L en la Task 14 de N1). A una de la SEC no se le inventa causa.
    """
    ref = analisis.referencia
    if ref is None or ref.exclusion is None:
        return None
    texto = etiqueta_exclusion(ref.exclusion)
    texto = texto[0].upper() + texto[1:] + "."
    if ref.exclusion == "historia_corta":
        if ref.filas_posteriores:
            texto += _PANEL_ATRAS
        elif analisis.clase in ("extranjera_sec", "sin_sec"):
            texto += _SEMESTRALES
    return texto


def detalle_pares(analisis) -> "str | None":
    """Lo que el voto «frente a sus pares» no dice por sí solo, o None.

    El voto sale `no_aplica/sin_pares` en dos casos que no son el mismo (Tasks
    14 y 17 de N1): sin ficha frente al sector, la causa está en
    `motivo_referencia`; con ficha y sin pilar de valoración (BRK-B), el sector
    sí tiene pares, y lo que faltan son los múltiplos de la empresa. Y con
    pilar, una guarda que la dejaría fuera no le quita el voto: en el ranking no
    pasa nunca, aquí sí, y se dice.
    """
    if analisis.clase in (None, "etf"):
        return None
    ref = analisis.referencia
    if ref is None:
        if analisis.motivo_referencia is None:
            return None
        return (
            "Frente a sus pares no vota porque no hay ficha frente al sector: "
            f"{etiqueta(MOTIVO_REFERENCIA, analisis.motivo_referencia)}."
        )
    if ref.ficha["pilares"].get("valoracion") is None:
        return (
            "Frente a sus pares no vota, y no por falta de pares: su sector los "
            "tiene. Lo que faltan son sus propios múltiplos (PER, EV/EBITDA, precio "
            "sobre flujo libre, precio sobre valor contable), así que no tiene "
            "pilar de valoración con que votar."
        )
    voto = ((analisis.valoracion or {}).get("votos") or {}).get("pares") or {}
    if ref.exclusion is not None and voto.get("voto") not in (None, "no_aplica"):
        return (
            "Frente a sus pares vota con su pilar de valoración aunque "
            f"{etiqueta_exclusion(ref.exclusion)}. En el ranking no competiría; aquí "
            "el voto cuenta, y vale lo que vale la ficha que lo sostiene."
        )
    return None


def sin_valor_base(valoracion) -> "str | None":
    """Una valoración con veredicto y sin valor base (7203.T en N1), o None.

    El valor base es la lectura de flujos, o la del beneficio residual: cuando
    ese voto no aplica --quema caja, sin flujo libre-- deciden los otros dos y
    hay veredicto sin cifra con que comparar el precio. Sin decirlo, la fila
    parece rota.
    """
    if not isinstance(valoracion, dict) or "veredicto" not in valoracion:
        return None
    if valoracion.get("valor") is not None:
        return None
    flujos = (valoracion.get("votos") or {}).get("flujos") or {}
    quien = "el del beneficio residual" if valoracion.get("metodo") == "residual" else "el de flujos"
    return (
        f"Hay veredicto pero no valor base: el voto que da el valor, {quien}, no "
        f"aplica ({medidores_valoracion.etiqueta_motivo(flujos.get('motivo'))}), y "
        "lo deciden los otros dos."
    )


# --- Los avisos de un ticker ---------------------------------------------------

# La forma con que Yahoo escribe una preferente: un guion, una P y la letra de
# la serie (JPM-PC, T-PA). En la tabla del S&P 500 sólo BF-B y BRK-B llevan
# guion, y ninguna con P.
_PREFERENTE = re.compile(r"^[A-Z]+-P[A-Z]$")


def aviso_sin_prima_pais(analisis) -> "str | None":
    """Una empresa de fuera de EE. UU. valorada en dólares sin prima por riesgo país.

    Sólo si además no es del S&P 500 (`fuente_sector == "sp500"`, la tabla con
    que se hace el panel): GRMN, ACN o MDT están domiciliadas fuera y se valoran
    exactamente como en M, y avisarlas diría que su valoración es distinta de
    la de candidatos. Decisión del usuario del 2026-10-26.
    """
    divisa = (analisis.valoracion or {}).get("divisa") or {}
    if not divisa.get("sin_prima_pais") or analisis.fuente_sector == "sp500":
        return None
    pais = analisis.identidad.pais if analisis.identidad is not None else None
    # El país lo escribe Yahoo: se escapa, como todo texto ajeno que llega a un
    # `st.warning`.
    return (
        "Valorada en dólares con la tasa libre de EE. UU. y la prima de un mercado "
        f"maduro, sin prima por riesgo país ({plano(pais)}). Si su país tiene más riesgo "
        "que EE. UU., el coste de capital sale bajo y el valor, alto. Se puede "
        "probar a mano con el deslizador de la prima de riesgo."
    )


def aviso_misma_empresa(ticker: str, sp500) -> "str | None":
    """Un ticker del SIC de la BMV cuya base es del S&P 500: la misma empresa.

    En el Sistema Internacional de Cotizaciones las extranjeras cotizan en la
    BMV con su símbolo de origen y `.MX`: AAPL.MX es Apple. Se inserta en su
    sector como si fuera otra, al lado de la propia AAPL y con cifras de Yahoo
    (N1: 217 de 424 y 137,6 $ de valor base frente a 183,0). No se fusionan: se
    avisa y se remite a la base. Sólo `.MX`: en otras bolsas el mismo símbolo es
    otra empresa (T.TO es TELUS y T, AT&T; BA.L es BAE Systems y BA, Boeing).
    """
    if not ticker.endswith(".MX"):
        return None
    base = ticker[: -len(".MX")]
    if base not in sp500:
        return None
    return (
        f"{ticker} es {base} cotizando en la BMV, en el Sistema Internacional de "
        "Cotizaciones: la misma empresa. Aquí sus cifras salen de Yahoo y no de la "
        f"SEC, y se compara con sus pares como si fuera otra, al lado de la propia "
        f"{base}. Para su ficha de la SEC, analiza {base}."
    )


def aviso_preferente(ticker: str) -> "str | None":
    """Un ticker con forma de acción preferente (`JPM-PC`, `T-PA`).

    Yahoo las da como `EQUITY` y en la SEC comparten CIK con la común, así que
    salen `sec` y se valoran con los estados y la capitalización de la empresa
    entera: el valor por acción no es el de la preferente.
    """
    if not _PREFERENTE.match(ticker):
        return None
    return (
        "Parece una acción preferente. Yahoo la da como una acción más y la SEC la "
        "tiene bajo la misma empresa, así que su ficha y su valoración son las de "
        "la empresa entera: el valor por acción no corresponde a la preferente."
    )


def aviso_adr(cociente) -> "str | None":
    """El recuento de los estados no cuadra con el de la cotización (`divisas.adr_dudosa`)."""
    if not adr_dudosa(cociente):
        return None
    return (
        f"El recuento de acciones de sus estados es {cociente:.2f} veces el de su "
        "cotización (capitalización ÷ precio): puede ser una ADR con un ratio "
        "distinto de 1, o una clase de acción que no es la que cotiza. El valor por "
        "acción se calcula con el de la cotización, como en M: esto avisa, no corrige."
    )


def aviso_panel_atrasado(analisis, trimestre_panel) -> "str | None":
    """El panel acaba antes que los trimestres del ticker, y los últimos no entran."""
    if trimestre_panel is None:
        return None
    ref = analisis.referencia
    atrasado = analisis.motivo_referencia == "sin_trimestres_comparables" or (
        ref is not None and ref.filas_posteriores > 0
    )
    if not atrasado:
        return None
    return (
        f"El panel de referencia llega hasta el {trimestre_panel} y "
        f"{analisis.ticker} ya tiene trimestres posteriores, que no entran en la "
        "comparación. Rehacer el panel lo pone al día."
    )


def aviso_bono_m(procedencia, hoy: date) -> "str | None":
    """La subasta del Bono M que da la tasa libre, si es más vieja de lo normal.

    `divisas.bono_m` sirve la última subasta guardada tenga la edad que tenga,
    mientras el `^TNX` deja de servirse a los siete días (revisión final de N1).
    Su fecha va siempre en la procedencia de la tasa libre; esto avisa cuando
    pasa de la mayor separación medida entre dos subastas.
    """
    if not isinstance(procedencia, dict) or procedencia.get("fuente") != "bono_m_10":
        return None
    try:
        subasta = date.fromisoformat(procedencia.get("fecha"))
    except (TypeError, ValueError):
        return None
    dias = (hoy - subasta).days
    if dias <= SEPARACION_MAXIMA_SUBASTAS.days:
        return None
    return (
        f"La tasa libre es la del Bono M de la subasta del {subasta:%d/%m/%Y}, hace "
        f"{dias} días: más que la mayor separación medida entre dos subastas "
        f"({SEPARACION_MAXIMA_SUBASTAS.days} días). Puede que Banxico no esté "
        "respondiendo y se esté usando la última guardada."
    )


def avisos(analisis, sp500, trimestre_panel, hoy: date) -> "list[tuple[str, str]]":
    """Los avisos de un ticker: `(forma corta para la fila, forma larga para el detalle)`."""
    ticker = analisis.ticker
    entradas = analisis.entradas
    base = ticker[: -len(".MX")] if ticker.endswith(".MX") else ticker
    candidatos = (
        (f"misma empresa que {base}", aviso_misma_empresa(ticker, sp500)),
        ("parece preferente", aviso_preferente(ticker)),
        ("sin prima por riesgo país", aviso_sin_prima_pais(analisis)),
        ("recuento de acciones dudoso", aviso_adr(None if entradas is None else entradas.cociente_adr)),
        ("panel atrasado", aviso_panel_atrasado(analisis, trimestre_panel)),
        ("Bono M antiguo", aviso_bono_m(None if entradas is None else entradas.procedencia_r_f, hoy)),
        ("sin valor base", sin_valor_base(analisis.valoracion)),
    )
    return [(corto, largo) for corto, largo in candidatos if largo]
```

- [ ] **Step 6: Comprobar que pasan**

Run: `uv run pytest tests/test_medidores_analizador.py tests/test_medidores.py tests/test_analizador_divisas.py -q`
Expected: todos pasan; los de `tarjeta_candidato` que ya había siguen dando «Compuesto +5.71 (z dentro del sector)».

- [ ] **Step 7: Commit**

```bash
git add analizador/divisas.py medidores.py medidores_analizador.py tests/test_medidores.py tests/test_medidores_analizador.py
git commit -m "feat: los rótulos del puesto global, de la ficha fuera del ranking y los avisos de un ticker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: La valoración en la moneda del precio y «con tus supuestos»

> **Ejecutada** (dbdd6e8) el 2026-10-27. De la revisión de las Tasks 1-10 (2026-10-27, d94cc9e): los formatos que comparte con `medidores_valoracion` pasan a públicos (`dinero`, `pct`, `como_numero`, `NOMBRE_SUPUESTO`), sin cambiar su comportamiento. Manda el código vivo.

Decisión 3: los valores por acción se enseñan en la moneda del precio. Y el spec: con los deslizadores movidos, el distintivo dice «con tus supuestos» y el título de la lista deja de decir «del programa». Una línea con la valoración, para el acta y para los añadidos de Revisar candidatos.

**Files:**
- Modify: `medidores_valoracion.py` (`distintivo`, `_cabecera`, `_supuestos`, `resumen`; nueva `valoracion_en_una_linea`)
- Modify: `medidores_analizador.py`
- Test: `tests/test_medidores_valoracion.py`, `tests/test_medidores_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_medidores_valoracion.py`:

```python
# --- Los deslizadores del Analizador --------------------------------------------


def test_con_tus_supuestos_lo_dicen_la_pildora_y_el_titulo():
    texto = _texto(mv.resumen(_fija(), con_tus_supuestos=True))
    assert "En rango · con tus supuestos" in texto
    assert "Supuestos del programa" not in texto
    assert "con los que moviste" in texto


def test_sin_mover_nada_la_valoracion_es_la_del_programa():
    texto = _texto(mv.resumen(_fija()))
    assert "con tus supuestos" not in texto
    assert "Supuestos del programa" in texto


def test_la_valoracion_en_una_linea_para_el_acta():
    assert mv.valoracion_en_una_linea(_fija()) == (
        "En rango; valor base 1,234.50 USD, con los supuestos del programa"
    )
    assert mv.valoracion_en_una_linea(fallida("sin_red")).startswith("Sin valoración: Yahoo")
    # Un añadido a mano en Revisar candidatos, o un acta anterior a N2.
    assert mv.valoracion_en_una_linea(None) == ""
    assert mv.valoracion_en_una_linea({"veredicto": "en_rango"}) == ""
```

En `tests/test_medidores_analizador.py`, al final:

```python
# --- La moneda del precio -----------------------------------------------------


def _amx() -> dict:
    """AMX: cotiza en dólares y se valora en pesos, a 20 pesos por dólar."""
    return _fija(
        moneda="MXN",
        precio=500.0,
        valor={"pesimista": 300.0, "base": 600.0, "optimista": None},
        epv={"por_accion": 400.0, "parte_crecimiento": 0.1},
        margen_seguridad=0.2,
        divisa={"moneda_precio": "USD", "moneda_valoracion": "MXN", "tipo_precio": 20.0},
    )


def test_los_valores_se_ensenan_en_la_moneda_del_precio():
    original = _amx()
    v = ma.en_moneda_del_precio(original)
    assert v["moneda"] == "USD"
    assert v["precio"] == pytest.approx(25.0)
    assert v["valor"] == {"pesimista": pytest.approx(15.0), "base": pytest.approx(30.0), "optimista": None}
    assert v["epv"]["por_accion"] == pytest.approx(20.0)
    # El margen es un cociente, y el crecimiento implícito una tasa: no cambian.
    assert v["margen_seguridad"] == 0.2 and v["implicito"] == original["implicito"]
    # Lo guardado no se toca: es lo que va al acta.
    assert original["moneda"] == "MXN" and original["valor"]["base"] == 600.0


def test_una_cotizacion_en_peniques_vuelve_a_peniques():
    # SHEL.L: 67,92 $ de valor base son 5.079,9 peniques (N1).
    shel = _fija(precio=54.0, valor={"pesimista": None, "base": 67.92, "optimista": None},
                 divisa={"moneda_precio": "GBp", "moneda_valoracion": "USD", "tipo_precio": 0.01337})
    v = ma.en_moneda_del_precio(shel)
    assert v["moneda"] == "GBp"
    assert v["valor"]["base"] == pytest.approx(67.92 / 0.01337)


def test_una_fallida_toma_la_moneda_de_su_divisa():
    # `fallida("sin_bono_m")` no lleva moneda: sale de la divisa (revisión final de N1).
    fallida_ = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_bono_m",
                "divisa": {"moneda_precio": "MXN", "tipo_precio": 1.0}}
    assert ma.en_moneda_del_precio(fallida_)["moneda"] == "MXN"


@pytest.mark.parametrize("tipo", [None, 0.0, -1.0, "20", float("nan")])
def test_sin_un_tipo_valido_no_se_convierte_nada(tipo):
    amx = _amx()
    amx["divisa"] = {**amx["divisa"], "tipo_precio": tipo}
    assert ma.en_moneda_del_precio(amx) == amx
    assert ma.en_moneda_del_precio(None) is None
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_medidores_valoracion.py tests/test_medidores_analizador.py -q`
Expected: FAIL con `TypeError: resumen() got an unexpected keyword argument 'con_tus_supuestos'` y `AttributeError: ... 'en_moneda_del_precio'`.

- [ ] **Step 3: Implementar en `medidores_valoracion.py`**

1. `distintivo` pasa a ser:

```python
def distintivo(valoracion: "dict | None", con_tus_supuestos: bool = False) -> str:
    """El veredicto en una píldora de color, o nada si no hay veredicto que enseñar.

    Con `con_tus_supuestos` la píldora lo dice: es el veredicto de los
    deslizadores del Analizador, no el del programa. La de Revisar candidatos
    no lo lleva nunca, porque allí no hay nada que mover.
    """
    clave = _dic(valoracion).get("veredicto")
    if not isinstance(clave, str) or clave not in VEREDICTO:
        return ""
    etiqueta, color = VEREDICTO[clave]
    if con_tus_supuestos:
        etiqueta = f"{etiqueta} · con tus supuestos"
    return f'<span class="mpp-veredicto" style="color:{color}">{_esc(etiqueta)}</span>'
```

2. En `_cabecera`, la firma pasa a `def _cabecera(valoracion: dict, con_tus_supuestos: bool = False) -> str:` y la llamada de dentro a `distintivo(valoracion, con_tus_supuestos)`.

3. En `_supuestos`, la firma pasa a `def _supuestos(valoracion: dict, con_tus_supuestos: bool = False) -> str:` y el `return` del final a:

```python
    titulo = (
        "Supuestos, con los que moviste tú marcados como tuyos"
        if con_tus_supuestos
        else "Supuestos del programa"
    )
    return (
        '<div class="mpp-val-sup">'
        f'<div class="mpp-val-sup-titulo">{_esc(titulo)}</div>{cuerpo}</div>'
    )
```

4. `resumen` gana el mismo argumento:

```python
def resumen(valoracion: dict, con_tus_supuestos: bool = False) -> str:
    """Los tres votos en una línea cada uno, el rango y la procedencia de los supuestos.

    No explica los términos: de eso se encarga `glosario()`, una vez por pantalla.
    `con_tus_supuestos` es la valoración de los deslizadores del Analizador: lo
    dicen la píldora y el título de los supuestos.
    """
```

y en su `return` final, `_cabecera(valoracion, con_tus_supuestos)` y `_supuestos(valoracion, con_tus_supuestos)`.

5. Después de `resumen`:

```python
def valoracion_en_una_linea(valoracion: object) -> str:
    """La valoración en una línea, para el acta y los añadidos de Revisar candidatos.

    En la moneda en que se guardó (la de la valoración, con su clave `moneda`),
    porque es el registro. Vacío si no hay ninguna reconocible: un añadido a
    mano o un acta anterior a N2.
    """
    if not isinstance(valoracion, dict) or not isinstance(valoracion.get("version"), str):
        return ""
    if "veredicto" not in valoracion:
        return f"Sin valoración: {etiqueta_motivo(valoracion.get('motivo'))}"
    etiqueta, _ = _entrada(VEREDICTO, valoracion.get("veredicto"), ("n/d", None))
    base = _dinero(_dic(valoracion.get("valor")).get("base"), _moneda(valoracion))
    return f"{etiqueta}; valor base {base}, con los supuestos del programa"
```

- [ ] **Step 4: Implementar en `medidores_analizador.py`**

Añade a las importaciones de arriba:

```python
# Privadas y aun así importadas: son el formato de las cifras de la valoración
# y los nombres de los supuestos. Una segunda copia aquí es como empiezan a
# separarse, y el Analizador tiene que escribir las cifras igual que Revisar
# candidatos.
from medidores_valoracion import _numero
```

y al final:

```python
# --- La moneda del precio -------------------------------------------------------


def en_moneda_del_precio(valoracion):
    """La valoración con las cifras por acción en la moneda del precio.

    `analizador.valorar.valorar` las da en la de la valoración: AMX cotiza en
    dólares y se valora en pesos (554,5 MXN son 29,69 $), y SHEL.L cotiza en
    peniques y se valora en dólares (67,92 $ son 5.079,9 peniques). Se divide
    por `divisa.tipo_precio`, que es el tipo con que `divisas.perfil_en` llevó
    el precio a la moneda de la valoración. El margen de seguridad es un
    cociente y no cambia; las tasas (el crecimiento implícito) tampoco.

    Devuelve una copia: lo de dentro es lo que va al acta, en su moneda. Sin un
    tipo válido no se convierte nada, y una fallida --que no lleva `moneda`--
    toma la del precio de su divisa (revisión final de N1).
    """
    if not isinstance(valoracion, dict):
        return valoracion
    divisa = valoracion.get("divisa")
    if not isinstance(divisa, dict):
        return valoracion
    tipo = _numero(divisa.get("tipo_precio"))
    moneda = divisa.get("moneda_precio")
    if tipo is None or tipo <= 0 or not isinstance(moneda, str):
        return valoracion
    if "veredicto" not in valoracion:
        return {**valoracion, "moneda": moneda}

    def a_precio(valor):
        numero = _numero(valor)
        return None if numero is None else numero / tipo

    salida = {**valoracion, "moneda": moneda, "precio": a_precio(valoracion.get("precio"))}
    valor = valoracion.get("valor")
    if isinstance(valor, dict):
        salida["valor"] = {k: a_precio(valor.get(k)) for k in ("pesimista", "base", "optimista")}
    epv = valoracion.get("epv")
    if isinstance(epv, dict):
        salida["epv"] = {**epv, "por_accion": a_precio(epv.get("por_accion"))}
    return salida
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_medidores_valoracion.py tests/test_medidores_analizador.py tests/test_medidores.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add medidores_valoracion.py medidores_analizador.py tests/test_medidores_valoracion.py tests/test_medidores_analizador.py
git commit -m "feat: la valoración en la moneda del precio y con tus supuestos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: La proyección a 10 años

> **Ejecutada** (ffa2c78) el 2026-10-27. Si se enseña un total de la proyección, se suma en orden, como `valor_empresa`, nunca con `sum()`.

El spec pide, en la pestaña Valoración, «la proyección a 10 años (plegada)». `valor_empresa` la calculaba por dentro y la tiraba. D10: sale a `dcf.proyeccion`, y `valor_empresa` la suma en el mismo orden, así que la tabla y el valor base dan lo mismo hasta el último bit.

**Files:**
- Modify: `valoracion/dcf.py`
- Modify: `analizador/valorar.py:213-233`
- Test: `tests/test_valoracion_dcf.py`, `tests/test_analizador_valorar.py`

- [ ] **Step 1: Escribir los tests**

En `tests/test_valoracion_dcf.py`, la importación de `valoracion.dcf` pasa a ser:

```python
from valoracion.dcf import (
    ANOS,
    Datos,
    crecimientos,
    cumple_gordon,
    margen_fcff,
    proyeccion,
    proyeccion_de,
    terminal,
    valor_empresa,
    valor_por_accion,
)
```

y al final:

```python
# --- La proyección, que el Analizador enseña plegada ---------------------------


@pytest.mark.parametrize("g, wacc", [(0.20, 0.09), (0.05, 0.12), (-0.03, 0.08), (0.40, 0.036)])
def test_el_valor_de_la_empresa_es_la_suma_exacta_de_su_proyeccion(g, wacc):
    anos = proyeccion(1000.0, 0.15, g, 0.025, wacc)
    esperado = sum(a.descontado for a in anos) + terminal(anos[-1].flujo, 0.025, wacc) / (1 + wacc) ** ANOS
    # Igualdad exacta, no aproximada: la tabla y el valor base son la misma cuenta.
    assert valor_empresa(1000.0, 0.15, g, 0.025, wacc) == esperado


def test_la_proyeccion_son_diez_anos_con_los_crecimientos_del_dcf():
    anos = proyeccion(1000.0, 0.15, 0.20, 0.02, 0.09)
    assert [a.ano for a in anos] == list(range(1, ANOS + 1))
    assert [a.crecimiento for a in anos] == crecimientos(0.20, 0.02)
    assert anos[0].ingresos == pytest.approx(1200.0)
    assert anos[0].flujo == pytest.approx(180.0)
    assert anos[0].descontado == pytest.approx(180.0 / 1.09)


def test_la_holgura_de_gordon_es_la_misma_para_el_valor_y_para_la_tabla():
    assert not cumple_gordon(0.03, 0.025)
    assert valor_empresa(1000.0, 0.15, 0.10, 0.025, 0.03) is None
    assert proyeccion_de(replace(DATOS, wacc=0.03), 0.10) is None
    p = proyeccion_de(DATOS, 0.10)
    assert len(p.anos) == ANOS
    assert sum(a.descontado for a in p.anos) + p.terminal_descontado == valor_empresa(
        DATOS.ingresos, DATOS.margen, 0.10, DATOS.g_perpetuo, DATOS.wacc
    )
```

En `tests/test_analizador_valorar.py`, dentro de `test_valorar_es_puro_mismas_entradas_mismo_resultado`, después de `v.sensibilidad(e, {"g_ref": 0.30})`, añade:

```python
        v.proyeccion(e, {"g_ref": 0.30})
```

y al final del fichero:

```python
# --- La proyección a 10 años ----------------------------------------------------


def test_la_proyeccion_suma_el_valor_base_con_los_mismos_datos_que_el_voto():
    e = _entradas()
    plano = v.valorar(e, None)
    p = v.proyeccion(e)
    empresa = sum(a.descontado for a in p.anos) + p.terminal_descontado
    acciones = e.perfil.capitalizacion / e.perfil.precio
    base = (empresa - e.fundamentos.deuda_total + e.fundamentos.efectivo) / acciones
    assert base == pytest.approx(plano["valor"]["base"])


def test_la_proyeccion_sigue_a_los_deslizadores():
    assert v.proyeccion(_entradas(), {"g_ref": 0.30}).anos[0].crecimiento == pytest.approx(0.30)


def test_sin_dcf_no_hay_proyeccion():
    assert v.proyeccion(_entradas(perfil=perfil(industria="Banks - Regional"))) is None
    assert v.proyeccion(_en_pesos(r_f=None, motivo_r_f="sin_token")) is None
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_valoracion_dcf.py tests/test_analizador_valorar.py -q`
Expected: FAIL con `ImportError: cannot import name 'cumple_gordon'`.

- [ ] **Step 3: Implementar en `valoracion/dcf.py`**

1. Después de la clase `Escenarios`:

```python
@dataclass(frozen=True)
class Ano:
    """Un año de la proyección del escenario base: lo que `valor_empresa` descuenta."""

    ano: int
    crecimiento: float
    ingresos: float
    flujo: float
    descontado: float


@dataclass(frozen=True)
class Proyeccion:
    """Los diez años del escenario base y el valor terminal, ya descontados."""

    anos: "tuple[Ano, ...]"
    terminal_descontado: float
```

2. Antes de `valor_empresa`:

```python
def cumple_gordon(wacc: float, g_perpetuo: float) -> bool:
    """Si el coste de capital supera al crecimiento perpetuo en al menos `HOLGURA_GORDON`."""
    return wacc - g_perpetuo >= HOLGURA_GORDON - _RUIDO_FLOTANTE


def proyeccion(
    ingresos: float, margen: float, g: float, g_perpetuo: float, wacc: float
) -> "tuple[Ano, ...]":
    """Los años 1 a 10, uno a uno, a fin de año: lo que `valor_empresa` suma.

    La misma aritmética y en el mismo orden, para que la tabla que el
    Analizador enseña plegada y el valor base no puedan separarse.
    """
    anos = []
    for ano, crecimiento in enumerate(crecimientos(g, g_perpetuo), start=1):
        ingresos *= 1 + crecimiento
        flujo = ingresos * margen
        anos.append(Ano(ano, crecimiento, ingresos, flujo, flujo / (1 + wacc) ** ano))
    return tuple(anos)


def terminal(flujo: float, g_perpetuo: float, wacc: float) -> float:
    """El valor terminal de Gordon al final del año diez, sin descontar."""
    return flujo * (1 + g_perpetuo) / (wacc - g_perpetuo)
```

3. `valor_empresa` pasa a ser:

```python
def valor_empresa(
    ingresos: float, margen: float, g: float, g_perpetuo: float, wacc: float
) -> "float | None":
    """Flujos de los años 1 a 10 más el valor terminal de Gordon, a fin de año.

    `None` si el coste de capital no supera al crecimiento perpetuo en al menos
    `HOLGURA_GORDON`: el valor terminal explota y cualquier número sería un
    artefacto. No se recorta el coste de capital para que cuadre: eso sería
    cambiar el escenario sin decirlo.

    Suma `proyeccion`, año a año y en orden: la tabla plegada del Analizador y
    este valor son la misma cuenta.
    """
    if not cumple_gordon(wacc, g_perpetuo):
        return None
    anos = proyeccion(ingresos, margen, g, g_perpetuo, wacc)
    total = 0.0
    for ano in anos:
        total += ano.descontado
    return total + terminal(anos[-1].flujo, g_perpetuo, wacc) / (1 + wacc) ** ANOS
```

4. Después de `valor_por_accion`:

```python
def proyeccion_de(datos: Datos, g: float) -> "Proyeccion | None":
    """La proyección del escenario base con los datos del DCF, o None sin holgura de Gordon."""
    if not cumple_gordon(datos.wacc, datos.g_perpetuo):
        return None
    anos = proyeccion(datos.ingresos, datos.margen, g, datos.g_perpetuo, datos.wacc)
    descontado = terminal(anos[-1].flujo, datos.g_perpetuo, datos.wacc) / (1 + datos.wacc) ** ANOS
    return Proyeccion(anos, descontado)
```

- [ ] **Step 4: Implementar en `analizador/valorar.py`**

`sensibilidad` pasa a apoyarse en una función común, y al lado va `proyeccion`:

```python
def _datos_del_dcf(entradas: Entradas, cambios: "dict | None") -> "tuple[dcf.Datos, Supuestos] | None":
    """Los datos del DCF con que se votó y sus supuestos, o None si no hay DCF.

    Los comparten la sensibilidad y la proyección. El mismo puente que
    `calcular`: si la tabla tratara la deuda o las acciones de otra forma, su
    casilla central no sería el valor base.
    """
    if entradas.perfil.industria in INDUSTRIAS_FINANCIERAS:
        return None
    supuestos = supuestos_de(entradas, cambios)
    if supuestos is None:
        return None
    deuda, efectivo, acciones = puente(entradas.fundamentos, entradas.perfil)
    datos, _ = datos_dcf(entradas.fundamentos, supuestos, deuda, efectivo, acciones)
    return None if datos is None else (datos, supuestos)


def sensibilidad(entradas: Entradas, cambios: "dict | None" = None) -> "dcf.Sensibilidad | None":
    """La tabla de sensibilidad del DCF con los mismos datos con que se votó.

    None si no hay DCF que tabular: una financiera (se valora por beneficio
    residual), sin tasa libre, o sin datos para el DCF (sin historia, sin flujo
    libre, quema caja). Con el coste de capital sin holgura sobre el
    crecimiento perpetuo sí hay tabla: la casilla central sale vacía y las
    demás enseñan desde qué coste vuelve a haber valor.
    """
    hechos = _datos_del_dcf(entradas, cambios)
    if hechos is None:
        return None
    datos, supuestos = hechos
    return dcf.sensibilidad(datos, supuestos.g_ref.valor)


def proyeccion(entradas: Entradas, cambios: "dict | None" = None) -> "dcf.Proyeccion | None":
    """Los diez años del escenario base del DCF, con los mismos datos con que se votó.

    None donde `sensibilidad` también lo es y, además, sin holgura de Gordon:
    ahí no hay valor base que desglosar. Es la tabla plegada de la pestaña
    Valoración del Analizador.
    """
    hechos = _datos_del_dcf(entradas, cambios)
    if hechos is None:
        return None
    datos, supuestos = hechos
    return dcf.proyeccion_de(datos, supuestos.g_ref.valor)
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_valoracion_dcf.py tests/test_analizador_valorar.py tests/test_valoracion_motor.py tests/test_valoracion_votos.py -q`
Expected: todos pasan, también los de M: `valor_empresa` da exactamente lo mismo.

- [ ] **Step 6: Commit**

```bash
git add valoracion/dcf.py analizador/valorar.py tests/test_valoracion_dcf.py tests/test_analizador_valorar.py
git commit -m "feat: la proyección a 10 años del DCF, que valor_empresa suma

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Los deslizadores

> **Ejecutada** (a9d1df5) el 2026-10-27. De la revisión de las Tasks 1-10 (2026-10-27, d94cc9e): la lista de supuestos de cada método pasa a `valoracion/supuestos.py` como `SUPUESTOS_DE`, para que los deslizadores no dependan de un módulo de pantalla. De la revisión de las Tasks 11-19 (2026-11-10, e3fbbc5): `aplicar` lanza `SupuestoImposible` y `CosteNoPositivo`, y `ma.supuesto_imposible` lo dice en palabras, sin la clave `k_e`. En la Task 20, el sabotaje de `cambios` no lo ve `test_un_deslizador_sin_tocar_no_cuenta_como_movido` sino `test_el_redondeo_de_ida_y_vuelta_no_cuenta_como_movido`. Manda el código vivo.

Decisión 10. Qué supuestos se mueven en cada método, entre qué cifras, y qué cuenta como movido; más las palabras de alrededor: la etiqueta de cada deslizador, la lista de lo movido, por qué falta la tasa libre y las dos tablas (sensibilidad y proyección).

**Files:**
- Create: `analizador/deslizadores.py`
- Modify: `medidores_analizador.py`
- Test: `tests/test_analizador_deslizadores.py`, `tests/test_medidores_analizador.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_deslizadores.py`:

```python
"""Los deslizadores de la valoración: qué se mueve, entre qué cifras y qué cuenta como movido."""

import pytest

from analizador import deslizadores as d
from analizador import valorar as v
from tests.dobles_valoracion import perfil
from tests.test_analizador_valorar import _en_pesos, _entradas


def test_en_una_de_flujos_se_mueven_los_supuestos_del_dcf():
    assert d.movibles(d.metodo(_entradas())) == ("r_f", "beta", "prima", "k_d", "t", "g_ref", "g_perpetuo")


def test_en_una_financiera_no_se_mueven_la_deuda_ni_los_impuestos():
    banco = _entradas(perfil=perfil(industria="Banks - Regional"))
    assert d.metodo(banco) == "residual"
    assert d.movibles("residual") == ("r_f", "beta", "prima", "roe_ref", "payout", "g_perpetuo")


def test_lo_derivado_nunca_tiene_deslizador():
    for metodo in ("flujos", "residual"):
        assert not {"k_e", "wacc"} & set(d.movibles(metodo))


def test_un_porcentaje_se_ensena_en_puntos_y_la_beta_tal_cual():
    assert d.a_pantalla("r_f", 0.0412) == pytest.approx(4.12)
    assert d.de_pantalla("r_f", 4.12) == pytest.approx(0.0412)
    assert d.a_pantalla("beta", 1.13) == 1.13


def test_el_recorrido_se_ensancha_para_que_quepa_la_cifra_del_programa():
    r = d.rango("beta", 3.4)
    assert (r.minimo, r.maximo, r.porcentaje) == (-1.0, 3.4, False)
    r = d.rango("g_ref", 0.05)
    assert (r.minimo, r.maximo) == pytest.approx((-20.0, 60.0))
    assert r.formato.endswith("%%")
    assert d.rango("g_ref", None).maximo == pytest.approx(60.0)


def test_las_cifras_del_programa_son_las_de_sus_supuestos():
    e = _entradas()
    s = v.supuestos_de(e)
    assert d.del_programa(e) == {n: getattr(s, n).valor for n in d.movibles("flujos")}


def test_sin_tasa_libre_no_hay_cifras_hasta_que_se_pone_a_mano():
    sin = _en_pesos(r_f=None, motivo_r_f="sin_token")
    assert d.del_programa(sin) is None
    programa = d.del_programa(sin, 0.09)
    assert programa["r_f"] == 0.09
    # Lo demás se deduce con ella: el crecimiento perpetuo no la pasa.
    assert programa["g_perpetuo"] <= 0.09


def test_una_tasa_a_mano_que_rompe_las_formulas_se_rechaza():
    with pytest.raises(ValueError):
        d.del_programa(_en_pesos(r_f=None, motivo_r_f="sin_token"), -0.50)


def test_un_deslizador_sin_tocar_no_cuenta_como_movido():
    e = _entradas()
    programa = d.del_programa(e)
    en_pantalla = {n: d.a_pantalla(n, valor) for n, valor in programa.items()}
    assert d.cambios(en_pantalla, programa) == {}
    # Y la valoración es la del programa, sin un solo «movido por ti».
    assert v.valorar(e, 0.4, d.cambios(en_pantalla, programa)) == v.valorar(e, 0.4)


def test_lo_movido_llega_en_tanto_por_uno():
    e = _entradas()
    programa = d.del_programa(e)
    en_pantalla = {n: d.a_pantalla(n, valor) for n, valor in programa.items()}
    en_pantalla["g_ref"] = 30.0
    en_pantalla["beta"] = 1.5
    assert d.cambios(en_pantalla, programa) == {"g_ref": pytest.approx(0.30), "beta": 1.5}


def test_una_casilla_vacia_no_cuenta_y_una_cifra_sin_programa_si():
    assert d.cambios({"g_ref": None}, {"g_ref": 0.05}) == {}
    assert d.cambios({"roe_ref": 12.0}, {"roe_ref": None}) == {"roe_ref": pytest.approx(0.12)}


def test_la_tasa_puesta_a_mano_va_siempre():
    assert d.cambios({}, {"r_f": 0.09}, r_f_a_mano=0.09) == {"r_f": 0.09}


def test_los_movidos_salen_de_supuestos_movidos():
    e = _entradas()
    assert d.nombres_movidos(e, {}) == ()
    assert d.nombres_movidos(e, {"beta": 1.5, "g_ref": 0.30}) == ("beta", "g_ref")
    assert d.nombres_movidos(_en_pesos(r_f=None, motivo_r_f="sin_token"), {"r_f": 0.09}) == ("r_f",)
```

En `tests/test_medidores_analizador.py`, añade a las importaciones:

```python
from tests.test_analizador_valorar import _en_pesos
from valoracion.dcf import Ano, Proyeccion, Sensibilidad
```

y al final:

```python
# --- Los deslizadores y sus tablas ----------------------------------------------


def test_la_etiqueta_de_un_deslizador_dice_su_unidad():
    assert ma.etiqueta_deslizador("beta") == "Beta"
    assert ma.etiqueta_deslizador("g_ref") == "Crecimiento de referencia (%)"


def test_la_lista_de_lo_movido_se_lee_en_castellano():
    assert ma.lista_de_supuestos(("beta",)) == "beta"
    assert ma.lista_de_supuestos(("beta", "g_ref")) == "beta y crecimiento de referencia"
    # «e» y no «y» delante de una i.
    assert ma.lista_de_supuestos(("beta", "g_ref", "t")) == (
        "beta, crecimiento de referencia e impuestos"
    )


def test_sin_tasa_libre_se_dice_por_que_y_que_hacer():
    texto = ma.falta_tasa(_en_pesos(r_f=None, motivo_r_f="sin_token"))
    assert ma.MOTIVO_TASA["sin_token"] in texto and "Bono M" in texto and "no se guarda" in texto


def test_la_sensibilidad_va_en_la_moneda_del_precio_y_marca_la_base():
    s = Sensibilidad(
        waccs=(0.07, 0.08, 0.09),
        gs=(0.02, 0.025, 0.03),
        valores=((40.0, 50.0, None), (30.0, 36.0, 44.0), (24.0, 28.0, 33.0)),
    )
    columnas, filas = ma.tabla_sensibilidad(s, 20.0, "USD")
    assert columnas[2] == "2.5% (base)" and filas[1][0] == "8.0% (base)"
    assert filas[1][2] == "1.80 USD"
    assert filas[0][3] == "—"


def test_la_proyeccion_va_en_millones_con_el_terminal_al_final():
    p = Proyeccion((Ano(1, 0.2, 1.2e9, 1.8e8, 1.65e8),), 2.5e9)
    columnas, filas = ma.tabla_proyeccion(p, "USD")
    assert columnas[2] == "Ingresos (USD)"
    assert filas[0] == ["1", "20.0%", "1,200 M", "180 M", "165 M"]
    assert filas[-1] == ["Terminal", "—", "—", "—", "2,500 M"]
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_deslizadores.py tests/test_medidores_analizador.py -q`
Expected: FAIL con `ImportError: cannot import name 'deslizadores' from 'analizador'` y `AttributeError: ... 'etiqueta_deslizador'`.

- [ ] **Step 3: Crear `analizador/deslizadores.py`**

```python
"""Los deslizadores de la valoración: qué se mueve, entre qué cifras y qué cuenta como movido.

Sin Streamlit. `analizador.valorar.valorar` y `sensibilidad` son aritmética pura
sobre unas `Entradas` ya traídas, así que mover un deslizador no vuelve a la
red. Lo que decide este módulo es lo de alrededor:

- **Qué se mueve**: los supuestos que el método usa y que
  `valoracion.supuestos.MOVIBLES` deja mover. El coste del capital propio y el
  de capital no: se recalculan de los demás.
- **Entre qué cifras**: un recorrido por supuesto, ensanchado si la cifra del
  programa cae fuera.
- **Qué cuenta como movido**: la pantalla enseña porcentajes y la cuenta usa
  tantos por uno.

**Lo movido no se guarda en ningún sitio.** Vive en las claves de los widgets
mientras dura la sesión; lo que va al acta es siempre la valoración del
programa.
"""

import math
from dataclasses import dataclass

from analizador.valorar import Entradas, supuestos_de
from valoracion.criterio import INDUSTRIAS_FINANCIERAS
from valoracion.supuestos import MOVIBLES, movidos

# Privada y aun así importada: es la lista de supuestos que la pantalla enseña
# de cada método, y en su orden. Con otra copia aquí, un deslizador podría mover
# un supuesto que la lista de debajo no enseña.
from medidores_valoracion import _SUPUESTOS_DE

# En tanto por uno: (mínimo, máximo, paso, se enseña en %). Son recorridos de un
# supuesto razonable, no los límites de las fórmulas: lo imposible --impuestos
# del 100 %, un reparto negativo, un coste de capital que no es positivo-- lo
# rechaza `aplicar` con `ValueError`, y la pantalla enseña por qué.
_RANGOS = {
    "r_f": (0.0, 0.20, 0.001, True),
    "beta": (-1.0, 3.0, 0.01, False),
    "prima": (0.0, 0.12, 0.001, True),
    "k_d": (0.0, 0.25, 0.001, True),
    "t": (0.0, 0.60, 0.005, True),
    "g_ref": (-0.20, 0.60, 0.005, True),
    "g_perpetuo": (-0.02, 0.06, 0.001, True),
    "roe_ref": (-0.20, 0.60, 0.005, True),
    "payout": (0.0, 1.0, 0.01, True),
}

# 4,12 % en pantalla son 0,0412 en la cuenta, y en coma flotante 4.12 / 100 no
# siempre da 0.0412. Sin tolerancia, un deslizador sin tocar contaría como
# movido y la pantalla diría «movido por ti» junto a la cifra del programa.
_TOLERANCIA = 1e-9


@dataclass(frozen=True)
class Rango:
    """El recorrido de un deslizador, en las unidades de la pantalla."""

    minimo: float
    maximo: float
    paso: float
    porcentaje: bool

    @property
    def formato(self) -> str:
        return "%.1f %%" if self.porcentaje else "%.2f"


def metodo(entradas: Entradas) -> str:
    """El método de la valoración, con la misma regla que `valoracion.motor.calcular`."""
    return "residual" if entradas.perfil.industria in INDUSTRIAS_FINANCIERAS else "flujos"


def movibles(metodo_: str) -> "tuple[str, ...]":
    """Los supuestos que se pueden mover en ese método, en el orden en que se enseñan.

    En una financiera el coste de la deuda y los impuestos no entran en ninguna
    cuenta, y `aplicar` los rechaza: ni se dibujan.
    """
    return tuple(nombre for nombre in _SUPUESTOS_DE[metodo_] if nombre in MOVIBLES)


def a_pantalla(nombre: str, valor: float) -> float:
    """De tanto por uno a lo que enseña el deslizador."""
    return valor * 100 if _RANGOS[nombre][3] else valor


def de_pantalla(nombre: str, valor: float) -> float:
    """De lo que enseña el deslizador a tanto por uno."""
    return valor / 100 if _RANGOS[nombre][3] else valor


def rango(nombre: str, valor: "float | None") -> Rango:
    """El recorrido del deslizador, ensanchado si la cifra del programa cae fuera.

    Un deslizador que no puede enseñar el valor de partida mentiría sobre él:
    una beta medida de 3,4 se quedaría en 3,0 sólo por dibujarse.
    """
    minimo, maximo, paso, porcentaje = _RANGOS[nombre]
    if valor is not None:
        minimo, maximo = min(minimo, valor), max(maximo, valor)
    escala = 100 if porcentaje else 1
    return Rango(minimo * escala, maximo * escala, paso * escala, porcentaje)


def del_programa(entradas: Entradas, r_f_a_mano: "float | None" = None) -> "dict[str, float | None] | None":
    """Lo que dice el programa de cada supuesto movible, o None sin tasa libre.

    Sin Bono M la tasa libre la pone el usuario (`r_f_a_mano`, en tanto por uno)
    y lo demás se deduce con ella, que es lo que hace `valorar.supuestos_de`.
    Lanza `ValueError` con una tasa a mano que deja un coste de capital no
    positivo.

    Un None es un supuesto que el programa no tiene (sin historia para el
    crecimiento de referencia, sin años para el ROE): la pantalla pide la cifra
    en vez de dibujar un deslizador sin punto de partida.
    """
    if entradas.r_f is None:
        if r_f_a_mano is None:
            return None
        de_partida = {"r_f": r_f_a_mano}
    else:
        de_partida = {}
    supuestos = supuestos_de(entradas, de_partida)
    return {nombre: getattr(supuestos, nombre).valor for nombre in movibles(metodo(entradas))}


def cambios(en_pantalla: dict, programa: dict, r_f_a_mano: "float | None" = None) -> dict:
    """Lo movido, en tanto por uno, listo para `valorar(entradas, pilar, cambios)`.

    `en_pantalla` es lo que enseñan los deslizadores, en sus unidades; un None
    es una casilla vacía y no cuenta. Lo que coincide con el programa, dentro de
    la tolerancia, tampoco. La tasa puesta a mano va siempre: sin ella no hay
    supuestos.
    """
    salida = {} if r_f_a_mano is None else {"r_f": r_f_a_mano}
    for nombre, mostrado in en_pantalla.items():
        if mostrado is None:
            continue
        valor = de_pantalla(nombre, float(mostrado))
        de_antes = programa.get(nombre)
        if de_antes is None or not math.isclose(
            valor, de_antes, rel_tol=_TOLERANCIA, abs_tol=_TOLERANCIA
        ):
            salida[nombre] = valor
    return salida


def nombres_movidos(entradas: Entradas, cambios_: dict) -> "tuple[str, ...]":
    """Los que movió el usuario, con `supuestos.movidos`; la tasa puesta a mano cuenta.

    Lanza `ValueError` como `aplicar`, con lo mismo que lo lanzaría `valorar`.
    """
    supuestos = supuestos_de(entradas, cambios_)
    return () if supuestos is None else movidos(supuestos)
```

- [ ] **Step 4: Las palabras, en `medidores_analizador.py`**

La importación privada de `medidores_valoracion` que añadió la Task 5 pasa a traer también los nombres y el formato de las cifras:

```python
from medidores_valoracion import _NOMBRE_SUPUESTO, _dinero, _numero, _pct
```

y al final del fichero:

```python
# --- Los deslizadores y sus tablas ----------------------------------------------


def etiqueta_deslizador(nombre: str) -> str:
    """«Crecimiento de referencia (%)», «Beta»: el nombre del supuesto con su unidad."""
    texto = _NOMBRE_SUPUESTO.get(nombre, nombre)
    texto = texto[0].upper() + texto[1:]
    return texto if nombre == "beta" else f"{texto} (%)"


def _y(partes: "list[str]") -> str:
    """«a», «a y b», «a, b y c»; con «e» delante de una i, como pide la RAE."""
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    ultimo = partes[-1]
    inicio = ultimo.lower()
    conjuncion = "e" if inicio.startswith(("i", "hi")) and not inicio.startswith(("ie", "hie")) else "y"
    return f"{', '.join(partes[:-1])} {conjuncion} {ultimo}"


def lista_de_supuestos(nombres) -> str:
    """Los supuestos movidos, en palabras: «beta y crecimiento de referencia»."""
    return _y([_NOMBRE_SUPUESTO.get(nombre, nombre) for nombre in nombres])


def falta_tasa(entradas) -> str:
    """Por qué no hay tasa libre y qué hacer, encima de la casilla donde se pone a mano.

    `fallida("sin_bono_m")` sólo dice que falta; el motivo concreto viaja en
    `Entradas.motivo_r_f` (revisión de la Task 13 de N1).
    """
    motivo = etiqueta(MOTIVO_TASA, entradas.motivo_r_f)
    if entradas.divisa.moneda_valoracion == "MXN":
        que_es = "Para una empresa que se valora en pesos es el rendimiento del Bono M a 10 años de Banxico."
    else:
        que_es = "Es el rendimiento del Tesoro de EE. UU. a 10 años."
    return (
        f"Sin tasa libre de riesgo: {motivo}. {que_es} Ponla a mano y se valora con "
        "ella; no se guarda."
    )


def tabla_sensibilidad(sensibilidad, tipo_precio: float, moneda: str) -> "tuple[list[str], list[list[str]]]":
    """La tabla de sensibilidad del valor base, en la moneda del precio.

    Filas de coste de capital y columnas de crecimiento a perpetuidad, con la
    del programa marcada «(base)». Una casilla vacía, «—», es que ahí no se
    cumple Gordon o el coste no es positivo (`dcf.sensibilidad`).
    """
    centro_g = len(sensibilidad.gs) // 2
    centro_wacc = len(sensibilidad.waccs) // 2
    columnas = ["Coste de capital ↓ · crecimiento a perpetuidad →"] + [
        _pct(g) + (" (base)" if i == centro_g else "") for i, g in enumerate(sensibilidad.gs)
    ]
    filas = []
    for i, (wacc, valores) in enumerate(zip(sensibilidad.waccs, sensibilidad.valores)):
        rotulo = _pct(wacc) + (" (base)" if i == centro_wacc else "")
        filas.append([rotulo] + ["—" if v is None else _dinero(v / tipo_precio, moneda) for v in valores])
    return columnas, filas


def _millones(valor) -> str:
    numero = _numero(valor)
    return "n/d" if numero is None else f"{numero / 1e6:,.0f} M".replace("-", "−")


def tabla_proyeccion(proyeccion, moneda: str) -> "tuple[list[str], list[list[str]]]":
    """Los diez años del escenario base y el valor terminal, en millones.

    En la moneda de la valoración, la de las cuentas: son cifras de la empresa
    entera, no por acción, y no se pasan a la del precio.
    """
    columnas = [
        "Año",
        "Crecimiento de los ingresos",
        f"Ingresos ({moneda})",
        f"Flujo libre ({moneda})",
        f"Valor presente ({moneda})",
    ]
    filas = [
        [str(a.ano), _pct(a.crecimiento), _millones(a.ingresos), _millones(a.flujo), _millones(a.descontado)]
        for a in proyeccion.anos
    ]
    filas.append(["Terminal", "—", "—", "—", _millones(proyeccion.terminal_descontado)])
    return columnas, filas
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_deslizadores.py tests/test_medidores_analizador.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add analizador/deslizadores.py medidores_analizador.py tests/test_analizador_deslizadores.py tests/test_medidores_analizador.py
git commit -m "feat: los deslizadores de la valoración y sus tablas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: El gráfico de TradingView

> **Ejecutada** (6f43635) el 2026-10-27. De la revisión de las Tasks 1-10 (2026-10-27, ec3024c): sin prefijo de bolsa TradingView tomaba T.TO (TELUS) por AT&T y BA.L (BAE) por Boeing. Ahora `en_widget(ticker, bolsa)`, `enlace(ticker, bolsa)` → `(rotulo, url)` y `avisos(ticker, bolsa)`; `simbolo` puede dar `None`; un ticker con sufijo sólo se incrusta si su bolsa está en `COMPROBADAS_EN_WIDGET`, hoy vacía. **`SOLO_EN_TRADINGVIEW` ya no existe**: donde este plan y la D22 la nombran, manda el código vivo.

Decisión 12. El símbolo sale de una tabla congelada de bolsas; el HTML del widget lleva el símbolo como JSON, ocupa todo el marco y dice si no carga. Debajo, el texto del spec sobre el estudio D y lo que se sabe y se dice.

Dos cosas que se vieron al aplicar este plan en un worktree temporal, con la app arrancada (D22):
- **Con `autosize`, el script de TradingView reescribe el estilo del contenedor a `height:100%`.** Sin altura en `html` y `body`, el gráfico salía de 150 píxeles dentro de un marco de 520. La hoja `html,body{height:100%}` lo arregla.
- **La BMV no se ve en el widget.** Con `BMV:WALMEX`, TradingView dice «Símbolo solo disponible en TradingView» y «Este símbolo no existe». Para esas bolsas (`SOLO_EN_TRADINGVIEW`) no se incrusta nada: se enlaza a la página del símbolo en su web. NASDAQ (`NASDAQ:MU`) y Arca (`AMEX:SPY`) sí se ven.

**Files:**
- Create: `analizador/grafico.py`
- Test: `tests/test_analizador_grafico.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_grafico.py`:

```python
"""El gráfico de TradingView: el símbolo y el HTML del widget."""

import json
import re

import pytest

from analizador import grafico


@pytest.mark.parametrize(
    "ticker, bolsa, simbolo",
    [
        ("MU", "NMS", "NASDAQ:MU"),
        ("DUOL", "NGM", "NASDAQ:DUOL"),
        ("JPM", "NYQ", "NYSE:JPM"),
        ("BRK-B", "NYQ", "NYSE:BRK.B"),
        ("BF-B", "NYQ", "NYSE:BF.B"),
        ("SPY", "PCX", "AMEX:SPY"),
        ("WALMEX.MX", "MEX", "BMV:WALMEX"),
        ("PE&OLES.MX", "MEX", "BMV:PE&OLES"),
        # Una bolsa que no está en la tabla va sin prefijo, y TradingView lo resuelve.
        ("RY.TO", "TOR", "RY"),
        ("7203.T", "JPX", "7203"),
        ("MU", None, "MU"),
    ],
)
def test_el_simbolo_de_tradingview(ticker, bolsa, simbolo):
    assert grafico.simbolo(ticker, bolsa) == simbolo


def _config(html: str) -> dict:
    return json.loads(re.search(r"<script[^>]*>\s*(\{.*?\})\s*</script>", html, re.S).group(1))


def test_el_widget_lleva_el_simbolo_el_tema_y_el_castellano():
    config = _config(grafico.html("NYSE:BRK.B", oscuro=True))
    assert config["symbol"] == "NYSE:BRK.B"
    assert config["theme"] == "dark" and config["locale"] == "es"
    assert config["allow_symbol_change"] is False
    assert _config(grafico.html("NASDAQ:MU", oscuro=False))["theme"] == "light"


def test_sin_conexion_el_widget_lo_dice():
    html = grafico.html("NASDAQ:MU", oscuro=True)
    assert 'onerror="' in html and "No se pudo cargar el gráfico" in html


def test_el_widget_ocupa_todo_el_marco():
    # Con `autosize`, TradingView reescribe el contenedor a `height:100%`: sin
    # altura en html y body, el gráfico salía de 150 píxeles en un marco de 520.
    assert "html,body{height:100%" in grafico.html("NASDAQ:MU", oscuro=True)


def test_la_bmv_no_se_incrusta_y_se_enlaza_a_tradingview():
    # Con BMV:WALMEX el widget dice «Símbolo solo disponible en TradingView»
    # (2026-10-26, al planear N2).
    assert not grafico.en_widget("MEX")
    assert grafico.en_widget("NMS") and grafico.en_widget(None)
    assert grafico.enlace("BMV:WALMEX") == "https://es.tradingview.com/symbols/BMV-WALMEX/"


def test_nada_del_simbolo_puede_cerrar_la_etiqueta_del_script():
    html = grafico.html("</script><img src=x>", oscuro=True)
    assert "</script><img" not in html


def test_lo_que_se_dice_debajo():
    assert "ninguna mostró ventaja después de costes" in grafico.ESTUDIO_D
    avisos = grafico.avisos("NMS")
    assert len(avisos) == 1 and "TradingView sabe qué ticker" in avisos[0]
    bmv = grafico.avisos("MEX")
    assert "sólo en su web" in bmv[0] and any("15–20 minutos" in aviso for aviso in bmv)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_grafico.py -q`
Expected: FAIL con `ImportError: cannot import name 'grafico' from 'analizador'`.

- [ ] **Step 3: Crear `analizador/grafico.py`**

```python
"""El gráfico de TradingView: el símbolo y el HTML del widget, sin Streamlit.

El *Advanced Chart* se incrusta con `st.iframe`. Es un script de TradingView
que corre en el navegador del usuario: TradingView sabe qué ticker se mira, sin
conexión no se ve, y sus datos no son los del programa ni entran en ninguna
cuenta. Todo eso se dice debajo.

**La BMV no se ve en el widget.** Con `BMV:WALMEX`, el widget dice «Símbolo
solo disponible en TradingView» y «Este símbolo no existe» (comprobado el
2026-10-26, al planear N2): TradingView no da los datos de esa bolsa en lo que
se incrusta. Para esas bolsas no se incrusta nada; se enlaza a su página.
"""

import json

import tema
from analizador.resolver import tiene_sufijo

# El `exchange` de yfinance → el prefijo de TradingView. Tabla congelada del
# spec: una bolsa que no esté aquí va sin prefijo, y TradingView lo resuelve.
BOLSAS = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "AMEX",
    "PCX": "AMEX",
    "MEX": "BMV",
}

# Las bolsas cuyos datos TradingView sólo da en su web, no en el widget. Tabla
# congelada, como `BOLSAS`: medida con BMV:WALMEX el 2026-10-26. Una bolsa nueva
# que falle igual se añade aquí, con su fecha.
SOLO_EN_TRADINGVIEW = frozenset({"MEX"})

_SCRIPT = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
ALTO = 520

ESTUDIO_D = (
    "El sub-proyecto D midió siete señales técnicas sobre el S&P 500 —momentum, "
    "RSI, MACD, medias, máximos de 52 semanas, Bollinger y reversión— y ninguna "
    "mostró ventaja después de costes. El gráfico está para quien quiera mirarlo; "
    "el programa no lo usa para nada."
)

_LO_QUE_SE_SABE = (
    "El gráfico es un script de TradingView: TradingView sabe qué ticker estás "
    "mirando, y sin conexión no se ve. Sus datos no son los del programa ni entran "
    "en ninguna cuenta."
)
_SOLO_EN_WEB = (
    "TradingView no da los datos de esta bolsa en el gráfico que se incrusta, "
    "sólo en su web: el enlace lo abre allí. Sus datos no son los del programa ni "
    "entran en ninguna cuenta."
)
_RETRASO_BMV = "En la BMV los datos de TradingView llevan unos 15–20 minutos de retraso."


def simbolo(ticker: str, bolsa: "str | None") -> str:
    """El símbolo de TradingView: `BRK-B` → `NYSE:BRK.B`, `WALMEX.MX` → `BMV:WALMEX`.

    El sufijo de bolsa de Yahoo se quita, y el guion de clase vuelve a ser
    punto, que es como lo escribe TradingView.
    """
    base = ticker.rpartition(".")[0] if tiene_sufijo(ticker) else ticker
    base = base.replace("-", ".")
    prefijo = BOLSAS.get(bolsa or "")
    return f"{prefijo}:{base}" if prefijo else base


def en_widget(bolsa: "str | None") -> bool:
    """Si TradingView da los datos de esa bolsa en el widget incrustado."""
    return bolsa not in SOLO_EN_TRADINGVIEW


def enlace(simbolo_: str) -> str:
    """La página del símbolo en TradingView: `BMV:WALMEX` → `…/symbols/BMV-WALMEX/`."""
    return f"https://es.tradingview.com/symbols/{simbolo_.replace(':', '-')}/"


def html(simbolo_: str, oscuro: bool) -> str:
    """El widget a toda la altura del marco, con el tema claro u oscuro de la app.

    Con `autosize`, el script de TradingView reescribe el estilo del contenedor
    a `height:100%`, así que el documento entero tiene que tener altura: sin la
    hoja de `html, body` el gráfico salía de 150 píxeles dentro de un marco de
    520 (visto al planear N2). Lleva el enlace de atribución del código de
    inserción de TradingView.

    No deja cambiar de símbolo: está atado al ticker analizado. Si el script no
    llega --sin conexión, o TradingView no responde--, el `onerror` lo dice en
    vez de dejar un hueco en blanco.
    """
    config = json.dumps(
        {
            "autosize": True,
            "symbol": simbolo_,
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "dark" if oscuro else "light",
            "style": "1",
            "locale": "es",
            "allow_symbol_change": False,
            "calendar": False,
            "support_host": "https://www.tradingview.com",
        }
    )
    # `</` dentro del script cerraría la etiqueta: el símbolo sale de
    # `resolver.normalizar`, que no admite ni `<` ni `/`, pero un JSON no se
    # escapa para HTML por sí solo.
    config = config.replace("</", "<\\/")
    return (
        "<style>html,body{height:100%;margin:0}</style>"
        '<div class="tradingview-widget-container" style="height:100%;width:100%">'
        '<div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>'
        '<div class="tradingview-widget-copyright" style="font-family:sans-serif;font-size:12px">'
        '<a href="https://es.tradingview.com/" rel="noopener nofollow" target="_blank">'
        "Gráfico de TradingView</a></div>"
        f'<p id="sin-grafico" style="display:none;font-family:sans-serif;color:{tema.TEXTO_SUAVE}">'
        "No se pudo cargar el gráfico de TradingView: sin conexión, o TradingView no "
        "responde. El resto del Analizador no depende de él.</p>"
        f'<script type="text/javascript" src="{_SCRIPT}" async '
        "onerror=\"document.getElementById('sin-grafico').style.display='block'\">"
        f"{config}"
        "</script>"
        "</div>"
    )


def avisos(bolsa: "str | None") -> "list[str]":
    """Lo que se sabe y se dice debajo del gráfico, o del enlace si no se incrusta."""
    salida = [_LO_QUE_SE_SABE if en_widget(bolsa) else _SOLO_EN_WEB]
    if bolsa == "MEX":
        salida.append(_RETRASO_BMV)
    return salida
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_grafico.py -q`
Expected: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add analizador/grafico.py tests/test_analizador_grafico.py
git commit -m "feat: el símbolo y el widget de TradingView

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: Actualizar el precio sin rehacer la ficha

> **Ejecutada** (f1c42d5) el 2026-10-27. De la revisión de las Tasks 1-10 (2026-10-27, f8b0268): ante un defecto, `con_precio_nuevo` devuelve la fila de antes, que seguía bien, y deja la traza en el log; la pantalla no afirma «precio actualizado» y dice la hora del precio que tiene la fila. Manda el código vivo.

Decisión 11 y D9. «Actualizar precios» rehace la identidad y la valoración, y conserva la ficha frente al sector, que no depende del precio de hoy. Y un defecto al hacer esa ficha ya no se lleva la fila entera: la identidad y la valoración se quedan.

**Files:**
- Modify: `analizador/analisis.py`
- Test: `tests/test_analizador_analisis.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_analizador_analisis.py`:

```python
# --- Lo que necesita la pantalla -------------------------------------------------


def test_el_pilar_que_vota_es_el_de_valoracion_de_la_ficha():
    panel = panel_crudo()
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), _Valoracion():
        a = analisis.analizar("IN0", panel, {"IN0": "Information Technology"})
    assert analisis.pilar_valoracion(a.referencia) == a.referencia.ficha["pilares"]["valoracion"]
    assert analisis.pilar_valoracion(None) is None


def test_un_defecto_en_la_ficha_no_se_lleva_la_identidad_ni_la_valoracion(caplog):
    panel = panel_crudo()
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), \
            patch.object(analisis.referencia, "frente_al_sector", side_effect=RuntimeError("defecto")), \
            _Valoracion() as valoracion, \
            caplog.at_level(logging.ERROR, logger="analizador.analisis"):
        a = analisis.analizar("IN0", panel, {"IN0": "Information Technology"})
    assert a.clase == "sec" and a.identidad is not None and a.motivo is None
    assert a.referencia is None and a.motivo_referencia == "error_interno"
    assert valoracion.pilares == [None]
    assert a.valoracion == {"version": "m1", "veredicto": "en_rango"}
    assert "RuntimeError" in caplog.text


def _analizado(panel):
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), _Valoracion():
        return analisis.analizar("IN0", panel, {"IN0": "Information Technology"})


def test_actualizar_el_precio_no_rehace_la_ficha_frente_al_sector():
    panel = panel_crudo()
    antes = _analizado(panel)
    nueva = Resuelto("IN0", "sec", replace(_identidad(), precio=120.0), None)
    with patch.object(analisis.resolver, "resolver", return_value=nueva), \
            patch.object(analisis.referencia, "frente_al_sector", side_effect=AssertionError("no se rehace")), \
            patch.object(analisis.kpis, "kpis_sec", side_effect=AssertionError("no se rehace")), \
            _Valoracion() as valoracion:
        despues = analisis.con_precio_nuevo(antes, panel, {"IN0": "Information Technology"})
    assert despues.identidad.precio == 120.0
    assert despues.referencia is antes.referencia
    assert valoracion.pilares == [antes.referencia.ficha["pilares"]["valoracion"]]


def test_un_ticker_sin_clase_se_analiza_entero_al_actualizar():
    panel = panel_crudo()
    sin_red = analisis.Analisis("IN0", None, None, "sin_red")
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto()), _Valoracion():
        despues = analisis.con_precio_nuevo(sin_red, panel, {"IN0": "Information Technology"})
    assert despues.clase == "sec" and despues.referencia is not None


def test_si_cambia_de_clase_se_analiza_entero():
    panel = panel_crudo()
    antes = _analizado(panel)
    with patch.object(analisis.resolver, "resolver", return_value=_resuelto(clase="sin_sec")), \
            patch.object(analisis, "analizar", return_value="ANALIZADO") as entero:
        assert analisis.con_precio_nuevo(antes, panel, {}) == "ANALIZADO"
    entero.assert_called_once()


def test_un_etf_solo_cambia_su_identidad():
    etf = analisis.Analisis("SPY", "etf", _identidad("SPY", tipo="ETF"), None)
    nueva = Resuelto("SPY", "etf", replace(_identidad("SPY", tipo="ETF"), precio=600.0), None)
    with patch.object(analisis.resolver, "resolver", return_value=nueva):
        assert analisis.con_precio_nuevo(etf, None).identidad.precio == 600.0


def test_un_defecto_al_actualizar_deja_la_traza_y_dice_error_interno(caplog):
    antes = _analizado(panel_crudo())
    with patch.object(analisis.resolver, "resolver", side_effect=RuntimeError("defecto")), \
            caplog.at_level(logging.ERROR, logger="analizador.analisis"):
        despues = analisis.con_precio_nuevo(antes, panel_crudo())
    assert (despues.clase, despues.motivo) == (None, "error_interno")
    assert "RuntimeError" in caplog.text
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_analisis.py -q`
Expected: FAIL con `AttributeError: module 'analizador.analisis' has no attribute 'pilar_valoracion'` y, en el del defecto, con el `RuntimeError` saliendo de `analizar` como `error_interno` de la fila entera.

- [ ] **Step 3: Implementar en `analizador/analisis.py`**

1. Añade `from dataclasses import dataclass, replace` en lugar de `from dataclasses import dataclass`.

2. Antes de `_filas_propias`:

```python
def pilar_valoracion(referencia: "Referencia | None") -> "float | None":
    """El pilar de valoración de la ficha, que es lo que vota «frente a sus pares»."""
    return None if referencia is None else referencia.ficha["pilares"].get("valoracion")
```

3. En `_analizar`, las dos líneas

```python
    encontrada, motivo_referencia = _frente_al_sector(resuelto, sector, panel)
    pilar = None if encontrada is None else encontrada.ficha["pilares"].get("valoracion")
    traidas, valoracion = _valoracion(resuelto, pilar)
```

pasan a ser:

```python
    try:
        encontrada, motivo_referencia = _frente_al_sector(resuelto, sector, panel)
    except Exception:
        # Un defecto propio al hacer la ficha no se lleva la identidad ni la
        # valoración, que no dependen de ella (nota de la Task 14 de N1): la
        # ficha dice `error_interno`, la traza va al log y lo demás sigue.
        logging.getLogger(__name__).exception(
            "La ficha frente al sector de %s falló por un defecto, no por falta de datos",
            ticker,
        )
        encontrada, motivo_referencia = None, "error_interno"
    traidas, valoracion = _valoracion(resuelto, pilar_valoracion(encontrada))
```

4. Después de `analizar`:

```python
def con_precio_nuevo(
    anterior: Analisis, panel: "pd.DataFrame | None", tabla_sectores: "dict | None" = None
) -> Analisis:
    """El mismo análisis con la cotización de ahora, sin rehacer la ficha frente al sector.

    La ficha no depende del precio de hoy: los múltiplos del panel van con el
    precio del día en que se publicó cada trimestre. Lo que sí depende es la
    identidad (precio y hora) y la valoración (el precio entra en el inverso,
    en el EPV y en el margen). Rehacer la ficha costaría la red de sus filas
    propias y unos 0,3 s de z por ticker.

    Un ticker que no tenía clase, o que ahora sale con otra, se analiza entero:
    no hay ficha que conservar, o la que hay es de otra cosa. El precio sale de
    la caché de `mercado` si tiene menos de quince minutos (`mercado.VALIDEZ`).
    Un defecto propio no se calla: `error_interno` y la traza al log, como en
    `analizar`.
    """
    if anterior.clase is None:
        return analizar(anterior.ticker, panel, tabla_sectores)
    try:
        resuelto = resolver.resolver(anterior.ticker)
        if resuelto.clase != anterior.clase:
            return analizar(anterior.ticker, panel, tabla_sectores)
        if resuelto.clase == "etf":
            return replace(anterior, identidad=resuelto.identidad)
        traidas, valoracion = _valoracion(resuelto, pilar_valoracion(anterior.referencia))
        return replace(anterior, identidad=resuelto.identidad, entradas=traidas, valoracion=valoracion)
    except Exception:
        logging.getLogger(__name__).exception(
            "Actualizar el precio de %s falló por un defecto, no por falta de datos",
            anterior.ticker,
        )
        return Analisis(anterior.ticker, None, None, "error_interno")
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_analisis.py -q`
Expected: todos pasan, también los de N1.

- [ ] **Step 5: Commit**

```bash
git add analizador/analisis.py tests/test_analizador_analisis.py
git commit -m "feat: actualizar el precio sin rehacer la ficha, y una ficha que falla no se lleva la fila

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: La sesión del Analizador y los tickers de un libro

> **Ejecutada** (a7798d3) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10, a2839b2): `preparar_motivo`, para que el motivo redactado siga a la valoración mientras no se edite. Del recorrido de la Task 21 (98ab58c): `recordar_elegido`, porque «Actualizar precios» devolvía el detalle al primer ticker. Manda el código vivo.

Decisión 11 y la lección de «El formulario que se quedaba en blanco»: el campo de tickers se declara con clave y sin valor, lo que llega de otras pantallas se consume al usarlo, y los análisis se guardan mientras no cambie el panel. Y la regla de Noticias para los tickers de un libro sale de su guion a `seguimiento/posiciones.py`.

**Files:**
- Create: `analizador/sesion.py`
- Modify: `seguimiento/posiciones.py`
- Test: `tests/test_analizador_sesion.py`, `tests/test_seguimiento_posiciones.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_sesion.py`:

```python
"""Lo que el Analizador guarda en la sesión, con un diccionario en lugar de `st.session_state`."""

from datetime import datetime
from types import SimpleNamespace

from analizador import sesion


def test_un_encargo_rellena_el_campo_y_elige_el_detalle():
    estado = {}
    sesion.encargar(estado, ["MU", "TSM"], "TSM")
    encargo = sesion.recoger(estado)
    assert encargo.tickers == ("MU", "TSM")
    assert estado[sesion.CLAVE_TEXTO] == "MU TSM"
    assert estado[sesion.CLAVE_ELEGIDO] == "TSM"


def test_un_encargo_se_consume_al_usarlo():
    # Si se quedase, volvería a pisar lo que el usuario escriba después.
    estado = {}
    sesion.encargar(estado, ["MU"])
    sesion.recoger(estado)
    estado[sesion.CLAVE_TEXTO] = "JPM"
    assert sesion.recoger(estado) is None
    assert estado[sesion.CLAVE_TEXTO] == "JPM"


def test_un_encargo_sin_elegido_no_toca_el_detalle():
    estado = {sesion.CLAVE_ELEGIDO: "MU"}
    sesion.encargar(estado, ["JPM"])
    sesion.recoger(estado)
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"


def test_lo_que_no_es_un_encargo_se_tira():
    estado = {sesion.CANAL: ["MU"]}
    assert sesion.recoger(estado) is None
    assert sesion.CANAL not in estado and sesion.CLAVE_TEXTO not in estado


def test_cargar_de_un_libro_solo_rellena_el_campo():
    estado = {}
    sesion.cargar_texto(estado, ["AAPL", "MSFT"])
    assert estado == {sesion.CLAVE_TEXTO: "AAPL MSFT"}


def test_los_analisis_valen_mientras_no_cambie_el_panel():
    hora = datetime(2026, 10, 16, 12, 0)
    estado = {}
    hechos = sesion.preparar(estado, hora)
    hechos["MU"] = "ANALISIS"
    assert sesion.preparar(estado, hora) == {"MU": "ANALISIS"}
    assert not sesion.panel_cambiado(estado, hora)
    assert sesion.panel_cambiado(estado, datetime(2026, 10, 26, 9, 0))
    assert sesion.preparar(estado, datetime(2026, 10, 26, 9, 0)) == {}


def test_sin_analisis_no_hay_panel_que_haya_cambiado():
    assert not sesion.panel_cambiado({}, datetime(2026, 10, 26))


def test_se_analiza_lo_que_falta_y_lo_que_fallo_en_su_orden():
    # Un ticker que salió sin clase (sin red, la SEC sin responder) se vuelve
    # a intentar al pulsar «Analizar»; uno con clase sale de la caché.
    hechos = {"TSM": SimpleNamespace(clase="extranjera_sec"), "JPM": SimpleNamespace(clase=None)}
    assert sesion.pendientes(["MU", "TSM", "JPM"], hechos) == ["MU", "JPM"]


def test_el_detalle_elegido_tiene_que_estar_entre_las_opciones():
    estado = {sesion.CLAVE_ELEGIDO: "ZZZZQ"}
    sesion.fijar_elegido(estado, ["MU", "TSM"])
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"
    sesion.fijar_elegido(estado, ["MU", "TSM"])
    assert estado[sesion.CLAVE_ELEGIDO] == "MU"
    vacio = {sesion.CLAVE_ELEGIDO: "MU"}
    sesion.fijar_elegido(vacio, [])
    assert vacio[sesion.CLAVE_ELEGIDO] == "MU"


def test_restaurar_borra_lo_movido_y_deja_la_tasa_puesta_a_mano():
    estado = {
        sesion.clave_deslizador("MU", "beta"): 1.5,
        sesion.clave_deslizador("MU", "g_ref"): 30.0,
        sesion.clave_a_mano("MU"): 9.0,
        sesion.clave_deslizador("MU.DE", "beta"): 1.2,
        sesion.clave_deslizador("BRK-B", "beta"): 0.4,
    }
    sesion.restaurar_deslizadores(estado, "MU")
    assert estado == {
        sesion.clave_a_mano("MU"): 9.0,
        sesion.clave_deslizador("MU.DE", "beta"): 1.2,
        sesion.clave_deslizador("BRK-B", "beta"): 0.4,
    }


def test_un_analisis_nuevo_olvida_todo_lo_movido_de_su_ticker():
    estado = {sesion.clave_deslizador("MU", "beta"): 1.5, sesion.clave_a_mano("MU"): 9.0, "otra": 1}
    sesion.olvidar_deslizadores(estado, "MU")
    assert estado == {"otra": 1}
```

Al final de `tests/test_seguimiento_posiciones.py`:

```python
# --- Los tickers de un libro, para el Analizador ------------------------------


def test_los_tickers_de_un_libro_son_lo_que_tiene_mas_lo_que_deberia_tener():
    from seguimiento.libro import Objetivo

    objetivo = Objetivo(
        fecha="2026-01-05",
        base="estrategia",
        portafolio={"posiciones": [{"ticker": "MSFT", "peso": 0.5}, {"ticker": "AAPL", "peso": 0.5}]},
    )
    vendida = [
        asiento("a3", "2026-01-06", "compra", ticker="KO", acciones=1.0, precio=60.0, importe=60.0),
        asiento("a4", "2026-02-05", "venta", ticker="KO", acciones=1.0, precio=65.0, importe=65.0),
    ]
    tickers = posiciones.tickers_a_mirar([APORTA, COMPRA, *vendida], objetivo)
    # Lo que se vendió del todo no entra; lo que aún no se ha comprado, sí.
    assert tickers == ["AAPL", "MSFT"]
    assert posiciones.tickers_a_mirar([APORTA, COMPRA], None) == ["AAPL"]
    assert posiciones.tickers_a_mirar([], None) == []
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_sesion.py tests/test_seguimiento_posiciones.py -q`
Expected: FAIL con `ImportError: cannot import name 'sesion' from 'analizador'` y `AttributeError: ... 'tickers_a_mirar'`.

- [ ] **Step 3: Crear `analizador/sesion.py`**

```python
"""Lo que el Analizador guarda en la sesión, y cómo le llegan tickers de otras pantallas.

Sin Streamlit: recibe `st.session_state`, o un diccionario en los tests. Es el
reparto de `configuracion.py` con el formulario del optimizador, y por las
mismas dos razones:

- **El campo de tickers se declara con `key=` y sin `value=`.** Un widget sin
  clave deriva su identidad de sus parámetros, y un `value` que cambia entre
  pasadas lo reinicia: es «El formulario que se quedaba en blanco». Lo que
  viene de fuera --«Analizar a fondo», «Abrir en el Analizador», «Cargar de un
  libro»-- escribe en esa clave antes de que se dibuje el campo, o desde un
  callback.
- **Un encargo se consume al usarlo.** Si se quedase, volvería a pisar lo que
  el usuario escriba después.

Los análisis se guardan porque cuestan: quince tickers en frío, cerca de un
minuto. Valen mientras no cambie el panel de referencia con que se hicieron;
si cambia, se tiran enteros, porque una ficha contra el panel de ayer y otra
contra el de hoy no van en la misma tabla.
"""

from dataclasses import dataclass

CLAVE_TEXTO = "analizador_texto"
CLAVE_TICKERS = "analizador_tickers"
CLAVE_ANALISIS = "analizador_analisis"
CLAVE_HORA_PANEL = "analizador_hora_panel"
CLAVE_ELEGIDO = "analizador_elegido"
# El canal por el que otras pantallas mandan tickers a analizar.
CANAL = "analizador_encargo"

_PREFIJO_DESLIZADOR = "analizador_desl"
_A_MANO = "r_f_a_mano"


@dataclass(frozen=True)
class Encargo:
    """Tickers que otra pantalla manda analizar, y cuál dejar elegido en el detalle."""

    tickers: "tuple[str, ...]"
    elegido: "str | None" = None


def encargar(estado, tickers, elegido: "str | None" = None) -> None:
    """Lo que llama «Analizar a fondo» o «Abrir en el Analizador» antes de saltar aquí."""
    estado[CANAL] = Encargo(tuple(tickers), elegido)


def recoger(estado) -> "Encargo | None":
    """El encargo pendiente, ya consumido: deja los tickers en el campo y, si lo hay, el elegido.

    Se llama antes de dibujar el campo. Lo que no es un `Encargo` se tira: un
    valor de otra versión no puede tumbar la pantalla.
    """
    encargo = estado.pop(CANAL, None)
    if not isinstance(encargo, Encargo):
        return None
    estado[CLAVE_TEXTO] = " ".join(encargo.tickers)
    if encargo.elegido is not None:
        estado[CLAVE_ELEGIDO] = encargo.elegido
    return encargo


def cargar_texto(estado, tickers) -> None:
    """Para el callback de «Cargar de un libro»: rellena el campo y no analiza (D13)."""
    estado[CLAVE_TEXTO] = " ".join(tickers)


def preparar(estado, hora_panel) -> dict:
    """La caché de análisis de esta sesión, vaciada si el panel cambió desde que se llenó."""
    if estado.get(CLAVE_HORA_PANEL) != hora_panel or not isinstance(estado.get(CLAVE_ANALISIS), dict):
        estado[CLAVE_ANALISIS] = {}
        estado[CLAVE_HORA_PANEL] = hora_panel
    return estado[CLAVE_ANALISIS]


def panel_cambiado(estado, hora_panel) -> bool:
    """Si hay análisis guardados hechos con otro panel que el de ahora."""
    return bool(estado.get(CLAVE_ANALISIS)) and estado.get(CLAVE_HORA_PANEL) != hora_panel


def pendientes(tickers, hechos: dict) -> "list[str]":
    """Los tickers por analizar, en el orden en que se escribieron.

    Los que no tienen análisis y los que lo tienen sin clase: un `sin_red` o un
    `sin_red_edgar` es un fallo de la red, no un hecho de la empresa, y pulsar
    «Analizar» otra vez tiene que volver a intentarlo. Los demás salen de la
    caché de la sesión.
    """
    return [t for t in tickers if t not in hechos or getattr(hechos[t], "clase", None) is None]


def fijar_elegido(estado, opciones) -> None:
    """Antes de dibujar el desplegable del detalle.

    Streamlit tumba la pasada entera si la clave guarda una opción que no está
    entre las de ahora (`seguimiento.libro.fijar_eleccion`): un ticker que ya no
    se analiza, o uno que llegó por un encargo y salió sin clase. Sin opciones
    no se toca.
    """
    if opciones and estado.get(CLAVE_ELEGIDO) not in opciones:
        estado[CLAVE_ELEGIDO] = opciones[0]


def clave_deslizador(ticker: str, nombre: str) -> str:
    """La clave del widget del supuesto `nombre` de `ticker`."""
    return f"{_PREFIJO_DESLIZADOR}_{ticker}_{nombre}"


def clave_a_mano(ticker: str) -> str:
    """La clave de la casilla donde se pone la tasa libre que falta."""
    return clave_deslizador(ticker, _A_MANO)


def _de_su_ticker(estado, ticker: str) -> "list[str]":
    prefijo = clave_deslizador(ticker, "")
    return [clave for clave in estado if isinstance(clave, str) and clave.startswith(prefijo)]


def restaurar_deslizadores(estado, ticker: str) -> None:
    """«Restaurar los del programa»: borra lo movido y deja la tasa puesta a mano.

    Sin claves, cada deslizador vuelve a nacer en la cifra del programa. La
    tasa puesta a mano se queda porque no hay programa al que volver: sin ella,
    no hay valoración.
    """
    for clave in _de_su_ticker(estado, ticker):
        if clave != clave_a_mano(ticker):
            del estado[clave]


def olvidar_deslizadores(estado, ticker: str) -> None:
    """Al rehacer el análisis de un ticker: las cifras del programa pueden haber cambiado."""
    for clave in _de_su_ticker(estado, ticker):
        del estado[clave]
```

- [ ] **Step 4: Implementar `tickers_a_mirar` en `seguimiento/posiciones.py`**

Después de `estado`:

```python
def tickers_a_mirar(asientos: "list[Asiento]", objetivo) -> "list[str]":
    """Lo que se tiene ahora más lo que el objetivo dice que se debería tener.

    Lo segundo entra porque una noticia sobre un activo que aún no has comprado
    sigue siendo sobre tu plan; lo que ya vendiste del todo, no. Vivía dentro
    de `vistas/noticias.py`; ahora lo usan «Cargar de un libro» del Analizador y
    «Abrir en el Analizador» de Seguimiento, y un guion de Streamlit no se
    puede importar.
    """
    # Aquí y no arriba: `libro` no importa este módulo, pero así no se ata el
    # orden de importación de los dos.
    from seguimiento.libro import pesos_objetivo

    return sorted(set(estado(asientos).acciones) | set(pesos_objetivo(objetivo)))
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_sesion.py tests/test_seguimiento_posiciones.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add analizador/sesion.py seguimiento/posiciones.py tests/test_analizador_sesion.py tests/test_seguimiento_posiciones.py
git commit -m "feat: la sesión del Analizador y los tickers de un libro

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: Las filas del resumen, «Lo que viene» y las noticias de un ticker

> **Ejecutada** (5f6415c) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10, c11051b): `precio_y_hora`, `pie_del_libro`, `fallo_al_escribir_el_panel` y las glosas de GICS, IFRS, 6-K y los códigos de los 8-K. Del recorrido de la Task 21 (7b7095e): `sin_prensa`. Manda el código vivo.

Las palabras de la pantalla que faltan: la fila de cada ticker en el resumen (con el nombre largo, la hora del precio y los avisos cortos), «Lo que viene» y lo que Noticias decía de los hechos, la prensa y la hora de cada descarga (sale del guion borrado a funciones con tests), qué pestañas tiene cada clase, la identidad del ticker, contra quién se compara y los textos del panel.

**Files:**
- Modify: `noticias/texto.py`
- Modify: `medidores_analizador.py`
- Test: `tests/test_noticias_texto.py`, `tests/test_medidores_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_noticias_texto.py`:

```python
# --- Lo que viene ---------------------------------------------------------------


def test_cuanto_falta_para_una_fecha():
    from datetime import date

    hoy = date(2026, 10, 26)
    assert texto.cuanto_falta(date(2026, 10, 26), hoy) == "hoy"
    assert texto.cuanto_falta(date(2026, 10, 25), hoy) == "hoy"
    assert texto.cuanto_falta(date(2026, 10, 27), hoy) == "mañana"
    assert texto.cuanto_falta(date(2026, 11, 5), hoy) == "en 10 días"
```

En `tests/test_medidores_analizador.py`, añade a las importaciones:

```python
from datetime import datetime, timedelta, timezone

from analizador.referencia import Frescura
from noticias.agenda import Evento
from noticias.hechos import Hecho
```

y al final:

```python
# --- La fila del resumen ------------------------------------------------------

HOY = date(2026, 10, 26)
SP500 = {"MU", "AAPL", "GRMN"}


def test_la_fila_de_un_ticker_analizado():
    a = analisis(ref=referencia(1, 423), valoracion=_fija(), precio=877.55)
    evento = Evento("MU", "resultados", date(2026, 12, 17), "Resultados")
    fila = ma.fila(a, evento, SP500, "2026Q2", HOY)
    assert list(fila) == list(ma.COLUMNAS)
    assert fila["Ticker"] == "MU" and fila["Nombre"] == "Micron Technology, Inc."
    assert fila["Clase"] == "SEC (10-K)"
    assert fila["Precio"] == "877.55 USD"
    assert fila["Hora del precio"] == "26/10/2026 20:00 UTC"
    assert fila["Valor base"] == "1,234.50 USD" and fila["Margen de seguridad"] == "20.3%"
    assert fila["Veredicto"] == "En rango"
    assert fila["Frente al sector"] == "1 de 423"
    assert fila["Próximo evento"] == "Resultados, 17/12/2026 (en 52 días)"
    assert fila["Avisos"] == "—"


def test_la_fila_de_un_ticker_sin_clase_lo_dice_y_no_inventa_el_resto():
    fila = ma.fila(Analisis("ZZZZQ", None, None, "sin_red"), None, SP500, None, HOY)
    assert fila["Avisos"] == ma.MOTIVO_ANALISIS["sin_red"]
    assert {fila[c] for c in ma.COLUMNAS if c not in ("Ticker", "Avisos")} == {"—"}


def test_sin_identidad_de_edgar_la_fila_conserva_el_nombre_y_el_precio():
    a = Analisis("MU", None, identidad(), "sin_identidad_edgar")
    fila = ma.fila(a, None, SP500, None, HOY)
    assert fila["Nombre"] == "Micron Technology, Inc." and fila["Precio"] == "100.00 USD"
    assert "Perfil" in fila["Avisos"]


def test_el_valor_de_la_fila_va_en_la_moneda_del_precio():
    amx = analisis("AMX", "extranjera_sec", valoracion=_amx(), fuente_sector="yahoo", precio=25.0)
    assert ma.fila(amx, None, SP500, None, HOY)["Valor base"] == "30.00 USD"


def test_una_fallida_por_el_bono_m_dice_el_motivo_concreto():
    fallida = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_bono_m",
               "divisa": {"moneda_precio": "MXN", "tipo_precio": 1.0}}
    entradas = SimpleNamespace(motivo_r_f="sin_token", cociente_adr=None, procedencia_r_f={})
    a = analisis("WALMEX.MX", "sin_sec", valoracion=fallida, entradas=entradas, fuente_sector="yahoo", moneda="MXN")
    fila = ma.fila(a, None, SP500, None, HOY)
    assert fila["Veredicto"] == "Sin valoración"
    assert ma.MOTIVO_TASA["sin_token"] in fila["Avisos"]


def test_los_avisos_cortos_van_en_la_fila():
    tsm = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False, posteriores=1),
                   valoracion=_con_divisa(True), fuente_sector="yahoo", pais="Taiwan")
    assert ma.fila(tsm, None, SP500, "2026Q2", HOY)["Avisos"] == "sin prima por riesgo país; panel atrasado"


def test_un_etf_no_tiene_veredicto_ni_sector():
    spy = analisis("SPY", "etf", fuente_sector=None)
    fila = ma.fila(spy, None, SP500, None, HOY)
    assert (fila["Clase"], fila["Veredicto"], fila["Frente al sector"]) == ("ETF", "—", "—")


def test_la_hora_del_precio_sin_zona_no_se_inventa():
    assert ma.hora_del_precio("2026-10-26T20:00:00+00:00") == "26/10/2026 20:00 UTC"
    assert ma.hora_del_precio("2026-10-26T20:00:00") == "—"
    assert ma.hora_del_precio(None) == "—"


def test_la_leyenda_glosa_lo_que_no_se_explica_solo():
    leyenda = ma.leyenda_resumen()
    for termino in ("Margen de seguridad", "Frente al sector", "pilares", "no se refresca solo"):
        assert termino in leyenda


# --- Lo que viene y las noticias ------------------------------------------------


def test_lo_que_viene_en_orden_y_sin_los_punteros_sin_fecha():
    eventos = [
        Evento("MU", "resultados", date(2026, 12, 17), "Resultados"),
        Evento(None, "macro", None, "FOMC"),
        Evento("TSM", "dividendo", date(2026, 11, 2), "Fecha de pago"),
    ]
    assert [e.ticker for e in ma.proximos(eventos)] == ["TSM", "MU"]
    assert ma.proximo(eventos).ticker == "TSM"
    assert ma.proximo([]) is None


def _hecho(cuando, material, url):
    return Hecho("MU", ("2.02",), ("Resultados",), url, cuando, False, material)


def test_los_hechos_se_reparten_por_material_y_del_mas_nuevo_al_mas_viejo():
    a = _hecho(date(2026, 9, 1), True, "a")
    b = _hecho(date(2026, 10, 1), True, "b")
    c = _hecho(date(2026, 8, 1), False, "c")
    destacados, plegados = ma.repartir_hechos([a, c, b])
    assert [h.url for h in destacados] == ["b", "a"] and [h.url for h in plegados] == ["c"]


def test_el_recorte_dice_cuantos_quedan_fuera():
    assert ma.recorte(list(range(45))) == (list(range(ma.TOPE_NOTICIAS)), 5)
    assert ma.recorte([1, 2]) == ([1, 2], 0)


@pytest.mark.parametrize("clase, esperado", [("VIDEO", "Vídeo"), ("video", "Vídeo"), ("STORY", "Story"), ("", "")])
def test_el_formato_de_la_noticia_se_pinta_tal_cual_menos_el_video(clase, esperado):
    assert ma.formato_noticia(clase) == esperado


def test_solo_las_de_la_sec_tienen_hechos():
    assert ma.fuentes_de("sec") == ("agenda", "hechos", "prensa")
    for clase in ("extranjera_sec", "sin_sec", "etf"):
        assert ma.fuentes_de(clase) == ("agenda", "prensa")
        assert ma.sin_hechos(clase)
    assert "6-K" in ma.sin_hechos("extranjera_sec")
    assert ma.sin_hechos("sec") is None


def test_la_hora_de_cada_descarga_se_dice_y_lo_caducado_tambien():
    reciente = datetime.now(timezone.utc) - timedelta(minutes=5)
    linea = ma.linea_de_hora("hechos", reciente, True)
    assert linea.startswith("**Hechos (8-K)**") and "hace 5 min" in linea and "cada hora" in linea
    assert "lo último que había guardado" in ma.linea_de_hora("hechos", reciente, False)
    assert ma.linea_de_hora("prensa", None, False) == "**Prensa**: no se pudo traer nada."


def test_un_etf_solo_tiene_tres_pestanas():
    assert ma.pestanas_de("etf") == ("Resumen", "Gráfico", "Noticias y calendario")
    assert ma.pestanas_de("sin_sec") == ma.PESTANAS
    assert "Valoración" in ma.PESTANAS and "Fundamentales" in ma.PESTANAS


# --- La identidad, contra quién se compara y el panel ---------------------------


def test_la_identidad_dice_clase_fuente_sector_y_monedas():
    divisa = SimpleNamespace(moneda_estados="TWD", moneda_valoracion="USD", moneda_precio="USD")
    entradas = SimpleNamespace(divisa=divisa)
    tsm = analisis("TSM", "extranjera_sec", entradas=entradas, fuente_sector="yahoo", pais="Taiwan")
    texto = ma.ficha_de_identidad(tsm)
    assert "SEC, extranjera" in texto and "Yahoo" in texto
    assert "Information Technology" in texto
    assert "TWD" in texto and "convertidos a USD" in texto


def test_contra_quien_se_compara_y_con_que_panel():
    mu = analisis(ref=referencia(1, 423))
    assert ma.contra_quien(mu, 70, date(2026, 10, 16)).startswith(
        "Comparada con las otras 69 empresas del S&P 500 de Information Technology"
    )
    tsm = analisis("TSM", "extranjera_sec", ref=referencia(25, 424, en_panel=False),
                   fuente_sector="yahoo", pais="Taiwan")
    texto = ma.contra_quien(tsm, 70, date(2026, 10, 16))
    assert "con las 70 empresas" in texto and "riesgo país" in texto


def test_la_fecha_del_panel_y_la_de_los_candidatos():
    hora = datetime(2026, 10, 16, 12, 0)
    texto = ma.fecha_del_panel(date(2026, 10, 16), "2026Q3", Frescura(hora, hora))
    assert "16/10/2026" in texto and "2026Q3" in texto and "candidatos son del 16/10/2026" in texto
    assert "ejemplo" in ma.fecha_del_panel(date(2026, 10, 16), "2026Q3", Frescura(hora, None))


def test_los_textos_del_panel_dicen_lo_que_hay_que_saber():
    assert "sin tocar tus candidatos" in ma.SIN_PANEL
    assert "Revisar candidatos" in ma.PANEL_POSTERIOR
    assert "Rehacer" in ma.PANEL_ATRASADO
    assert "salidas/panel.parquet" in ma.AYUDA_PANEL and "añadidos" in ma.AYUDA_PANEL
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_noticias_texto.py tests/test_medidores_analizador.py -q`
Expected: FAIL con `AttributeError: module 'noticias.texto' has no attribute 'cuanto_falta'` y `... 'medidores_analizador' has no attribute 'fila'`.

- [ ] **Step 3: `cuanto_falta`, en `noticias/texto.py`**

Cambia `from datetime import datetime, timezone` por `from datetime import date, datetime, timezone`, y después de `cada`:

```python
def cuanto_falta(cuando: date, hoy: "date | None" = None) -> str:
    """Cuánto queda para una fecha, en palabras: la pareja de `hace`, para lo que viene.

    Vivía dentro de `vistas/noticias.py`, que se borró al pasar sus noticias al
    Analizador; un guion de Streamlit no se puede importar ni probar.
    """
    dias = (cuando - (hoy or date.today())).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    return f"en {dias} días"
```

- [ ] **Step 4: Implementar en `medidores_analizador.py`**

En las importaciones de arriba, `from datetime import date` pasa a `from datetime import date, datetime, timezone`, `from noticias.texto import plano` pasa a `from noticias.texto import cada, cuanto_falta, hace, plano`, y se añade:

```python
from noticias import cache
```

y al final del fichero:

```python
# --- La fila del resumen ------------------------------------------------------

# El spec pide Ticker, Clase, Precio, Valor base, Margen de seguridad,
# Veredicto, Frente al sector y Próximo evento. Se añaden el nombre largo (un
# `BRK B` mal partido da BRK y B, y B es Barrick), la hora del precio (el precio
# no se refresca solo, a propósito) y los avisos, que es donde una fila que
# falla dice por qué.
COLUMNAS = (
    "Ticker",
    "Nombre",
    "Clase",
    "Precio",
    "Hora del precio",
    "Valor base",
    "Margen de seguridad",
    "Veredicto",
    "Frente al sector",
    "Próximo evento",
    "Avisos",
)


def hora_del_precio(hora: object) -> str:
    """La hora de la cotización en UTC, o «—». Una hora sin zona no se da por UTC."""
    if not isinstance(hora, str):
        return "—"
    try:
        momento = datetime.fromisoformat(hora)
    except ValueError:
        return "—"
    if momento.tzinfo is None:
        return "—"
    return momento.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def texto_evento(evento, hoy: date) -> str:
    """«Resultados, 17/12/2026 (en 52 días)»."""
    return f"{evento.detalle}, {evento.cuando:%d/%m/%Y} ({cuanto_falta(evento.cuando, hoy)})"


def motivo_de_la_valoracion(analisis) -> str:
    """Por qué no hay valoración, con el motivo concreto de la tasa libre si es el Bono M.

    `fallida("sin_bono_m")` sólo dice que falta; lo concreto viaja en
    `Entradas.motivo_r_f` (revisión de la Task 13 de N1).
    """
    valoracion = analisis.valoracion if isinstance(analisis.valoracion, dict) else {}
    motivo = valoracion.get("motivo")
    if motivo == "sin_bono_m" and analisis.entradas is not None:
        return f"sin tasa libre: {etiqueta(MOTIVO_TASA, analisis.entradas.motivo_r_f)}"
    return medidores_valoracion.etiqueta_motivo(motivo)


def fila(analisis, proximo_evento, sp500, trimestre_panel, hoy: date) -> dict:
    """La fila de un ticker en el resumen, como textos, en el orden de `COLUMNAS`.

    El precio es el de la identidad, en la moneda en que cotiza; el valor base,
    el de la valoración pasada a esa misma moneda (`en_moneda_del_precio`). Un
    ticker sin clase sólo dice por qué, y conserva el nombre y el precio si
    Yahoo los dio (sin el correo de EDGAR, por ejemplo).
    """
    salida = dict.fromkeys(COLUMNAS, "—")
    salida["Ticker"] = analisis.ticker
    salida["Nombre"] = nombre(analisis)
    identidad = analisis.identidad
    if identidad is not None and identidad.precio is not None:
        salida["Precio"] = _dinero(identidad.precio, identidad.moneda or "")
        salida["Hora del precio"] = hora_del_precio(identidad.hora)
    if analisis.clase is None:
        salida["Avisos"] = motivo_de_la_fila(analisis)
        return salida
    salida["Clase"] = CLASE.get(analisis.clase, analisis.clase)
    salida["Frente al sector"] = frente_al_sector(analisis)
    if proximo_evento is not None:
        salida["Próximo evento"] = texto_evento(proximo_evento, hoy)
    cortos = [corto for corto, _ in avisos(analisis, sp500, trimestre_panel, hoy)]
    valoracion = en_moneda_del_precio(analisis.valoracion)
    if isinstance(valoracion, dict) and "veredicto" in valoracion:
        etiqueta_, _ = medidores_valoracion.VEREDICTO.get(valoracion["veredicto"], (valoracion["veredicto"], None))
        salida["Veredicto"] = etiqueta_
        base = (valoracion.get("valor") or {}).get("base")
        if _numero(base) is not None:
            salida["Valor base"] = _dinero(base, valoracion.get("moneda") or "")
        if _numero(valoracion.get("margen_seguridad")) is not None:
            salida["Margen de seguridad"] = _pct(valoracion["margen_seguridad"])
    elif isinstance(valoracion, dict):
        salida["Veredicto"] = "Sin valoración"
        cortos.insert(0, motivo_de_la_valoracion(analisis))
    salida["Avisos"] = "; ".join(cortos) or "—"
    return salida


def leyenda_resumen() -> str:
    """Lo que dice cada columna, en markdown, para debajo de la tabla.

    Glosa la identidad de lo que la tabla no explica sola, la primera vez que
    sale en la pantalla («Registro del texto»).
    """
    return (
        "**Valor base**: el valor por acción del escenario base, en la moneda en "
        "que cotiza. **Margen de seguridad**: (valor base − precio) / precio, "
        "cuánto más vale que su precio. **Veredicto**: lo que dicen juntos los "
        "tres votos —flujos, valor sin crecimiento y pares—; las cuentas, en la "
        "pestaña Valoración. **Frente al sector**: su puesto global por la nota "
        "compuesta, que resume los cuatro pilares —calidad, crecimiento, valoración "
        "y solidez— medidos frente a las empresas del S&P 500 de su sector.  \n"
        "El precio no se refresca solo, a propósito: un veredicto que cambia cada "
        "minuto con el precio es ruido. Lleva su hora, y el tiempo real está en el "
        "gráfico."
    )


# --- Lo que viene y las noticias ------------------------------------------------

# Los nombres de las tres fuentes de `noticias/traer.py`, en el orden de la
# pantalla: lo que viene, los hechos y la prensa.
ETIQUETA_FUENTE = {"agenda": "Calendario", "hechos": "Hechos (8-K)", "prensa": "Prensa"}

# Por encima de esto la lista deja de leerse y empieza a ser un muro. Se recorta
# diciéndolo: un recorte silencioso es indistinguible de que no hubiera más.
# Era el `TOPE` de Noticias, que listaba un libro entero; aquí es por ticker.
TOPE_NOTICIAS = 40

PESTANAS = ("Resumen", "Valoración", "Fundamentales", "Gráfico", "Noticias y calendario")
# Un ETF no se valora ni se compara con un sector: las pestañas que saldrían
# vacías no se dibujan (spec, «Las pestañas del detalle»).
PESTANAS_ETF = ("Resumen", "Gráfico", "Noticias y calendario")


def pestanas_de(clase: "str | None") -> "tuple[str, ...]":
    return PESTANAS_ETF if clase == "etf" else PESTANAS


def proximos(eventos) -> list:
    """Los eventos con fecha, del más cercano al más lejano.

    Los punteros macro van con `cuando=None`: meterlos en el orden sería un
    `TypeError`, y ponerles una fecha sería inventarse el dato que no se tiene.
    """
    return sorted((e for e in eventos if e.cuando is not None), key=lambda e: e.cuando)


def proximo(eventos):
    """El evento más cercano, o None."""
    ordenados = proximos(eventos)
    return ordenados[0] if ordenados else None


def repartir_hechos(hechos) -> "tuple[list, list]":
    """Los 8-K destacados y los de trámite, del más nuevo al más viejo.

    El criterio ya decidió al bajarlos (`Hecho.material`): aquí sólo se reparte.
    Volver a mirar los tipos a mano pondría un segundo criterio en el programa.
    """
    destacados = sorted((h for h in hechos if h.material), key=lambda h: h.cuando, reverse=True)
    plegados = sorted((h for h in hechos if not h.material), key=lambda h: h.cuando, reverse=True)
    return destacados, plegados


def recorte(elementos: list, tope: int = TOPE_NOTICIAS) -> "tuple[list, int]":
    """Los que caben y cuántos se quedaron fuera."""
    return elementos[:tope], max(0, len(elementos) - tope)


def formato_noticia(clase: str) -> str:
    """El formato de un titular, para descartarlo sin abrirlo.

    Yahoo mete vídeos entre las noticias, y en la pasada real de H devolvió
    STORY para casi todo: se pinta lo que venga, y sólo el vídeo lleva nombre
    propio.
    """
    return "Vídeo" if clase.upper() == "VIDEO" else clase.capitalize()


def fuentes_de(clase: "str | None") -> "tuple[str, ...]":
    """Las fuentes de noticias de cada clase: los 8-K sólo los presenta quien hace 10-K."""
    return ("agenda", "hechos", "prensa") if clase == "sec" else ("agenda", "prensa")


_SIN_HECHOS = {
    "extranjera_sec": (
        "Presenta 20-F o 40-F y no 8-K. Sus 6-K no se interpretan: no llevan códigos "
        "de item, y el criterio de qué es material se construyó sobre ellos."
    ),
    "sin_sec": "No presenta en la SEC: aquí hay calendario y prensa, pero no hechos.",
    "etf": "Un ETF no presenta 8-K: aquí hay calendario y prensa, pero no hechos.",
}


def sin_hechos(clase: "str | None") -> "str | None":
    """Por qué una clase no tiene 8-K, o None si los tiene."""
    return _SIN_HECHOS.get(clase)


def linea_de_hora(fuente: str, cuando, vigente: bool) -> str:
    """Cuándo se trajo lo que se está viendo de una fuente, en markdown.

    La hora se enseña siempre, esté el dato fresco o no: un dato que se lee como
    recién traído sin serlo es peor que no tener dato. Es la regla de Noticias.
    """
    nombre_ = ETIQUETA_FUENTE[fuente]
    if cuando is None:
        return f"**{nombre_}**: no se pudo traer nada."
    linea = (
        f"**{nombre_}**: se descargó el {cuando.astimezone():%d/%m/%Y a las %H:%M} "
        f"({hace(cuando)}). Se vuelve a pedir cada {cada(cache.VALIDEZ[fuente])}."
    )
    if not vigente:
        linea += " La descarga falló y se enseña lo último que había guardado."
    return linea


# --- La identidad, contra quién se compara y el panel ---------------------------

_ORIGEN_SECTOR = {
    "sp500": "el de la tabla del S&P 500",
    "yahoo": "el de Yahoo, traducido a GICS",
    "sin_sector": "Yahoo no da uno que se pueda traducir",
}


def ficha_de_identidad(analisis) -> str:
    """Nombre aparte, lo demás de un ticker en markdown: clase, datos, sector y monedas.

    Lo que viene de Yahoo pasa por `noticias.texto.plano`: es texto ajeno.
    """
    identidad = analisis.identidad
    lineas = [
        f"**Clase**: {CLASE.get(analisis.clase, '—')} · **Datos**: "
        f"{FUENTE_DE_DATOS.get(analisis.clase, '—')}"
    ]
    if analisis.clase != "etf":
        sector = plano(analisis.sector) if analisis.sector else "sin sector GICS"
        lineas.append(f"**Sector**: {sector} ({_ORIGEN_SECTOR.get(analisis.fuente_sector, '—')})")
    if identidad is not None:
        bolsa = plano(identidad.bolsa) if identidad.bolsa else "—"
        lineas.append(f"**Cotiza en** {plano(identidad.moneda or '—')}, en la bolsa {bolsa}")
    entradas = analisis.entradas
    if entradas is not None:
        divisa = entradas.divisa
        if divisa.moneda_estados != divisa.moneda_valoracion:
            lineas.append(
                f"**Estados** en {plano(divisa.moneda_estados)}, convertidos a "
                f"{plano(divisa.moneda_valoracion)} para valorar"
            )
        elif divisa.moneda_valoracion != divisa.moneda_precio:
            lineas.append(
                f"**Se valora** en {plano(divisa.moneda_valoracion)}, la moneda de sus "
                "estados; el valor se enseña en la del precio"
            )
    return "  \n".join(lineas)


def contra_quien(analisis, pares_del_sector: int, fecha_panel: date) -> str:
    """Con qué empresas se compara la ficha, y con qué panel.

    `pares_del_sector` son las del sector en el panel; una del panel no se
    cuenta a sí misma. Para las de fuera de EE. UU., el texto del spec sobre
    los múltiplos y el riesgo país.
    """
    if analisis.referencia is not None and analisis.referencia.en_panel:
        quienes = f"las otras {pares_del_sector - 1} empresas"
    else:
        quienes = f"las {pares_del_sector} empresas"
    texto = (
        f"Comparada con {quienes} del S&P 500 de {analisis.sector}, con el panel de "
        f"referencia del {fecha_panel:%d/%m/%Y}."
    )
    pais = analisis.identidad.pais if analisis.identidad is not None else None
    if pais not in (None, "United States") and analisis.fuente_sector != "sp500":
        texto += (
            " Márgenes y rentabilidad son comparables; los múltiplos lo son menos, "
            "porque no incluyen el riesgo país."
        )
    return texto


def fecha_del_panel(fecha_panel: date, trimestre: str, frescura) -> str:
    """De cuándo es la referencia sectorial y de cuándo los candidatos."""
    texto = (
        f"Referencia sectorial: el panel del S&P 500 del {fecha_panel:%d/%m/%Y}, con "
        f"trimestres hasta el {trimestre}."
    )
    if frescura.candidatos is None:
        return texto + " No hay candidatos generados: Revisar candidatos enseña la lista de ejemplo."
    return texto + f" Los candidatos son del {frescura.candidatos:%d/%m/%Y}."


SIN_PANEL = (
    "No hay panel de referencia del S&P 500: sin él no hay ficha frente al sector "
    "ni voto de pares, y la valoración sale con dos votos. Se construye aparte, "
    "gratis, sin tocar tus candidatos ni lo que tengas marcado en Revisar candidatos."
)

PANEL_POSTERIOR = (
    "El panel es más nuevo que los candidatos: se rehízo aparte. La ficha de un "
    "candidato aquí puede diferir un poco de la de Revisar candidatos, que se "
    "calculó con el panel de entonces."
)

PANEL_ATRASADO = (
    "El panel se ha quedado atrás: algún ticker de los de abajo tiene trimestres "
    "posteriores al último del panel, y ésos no entran en su comparación. "
    "Rehacer el panel lo pone al día."
)

AYUDA_PANEL = (
    "La misma descarga que «Generar gratis», pero sólo escribe el panel "
    "(salidas/panel.parquet): ni las fichas, ni las casillas marcadas, ni los "
    "añadidos a mano. Unos dos minutos con la caché llena, y bastantes más la "
    "primera vez."
)
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_noticias_texto.py tests/test_medidores_analizador.py -q`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add noticias/texto.py medidores_analizador.py tests/test_noticias_texto.py tests/test_medidores_analizador.py
git commit -m "feat: las filas del resumen, lo que viene y las noticias de un ticker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 12: El gate, en el acta

> **Ejecutada** (e3cf215) el 2026-10-27. De la revisión de las Tasks 1-10 (2026-10-27, ce2a853): el test de escapes no notaba quitar el `texto.plano` de «Valor intrínseco al añadirla» en candidatos; ahora sí.

Decisión 4 y el punto 9 de «Cómo se prueba». `Anadido` gana `valoracion`, el acta la escribe y las actas viejas se siguen leyendo. Las tres comprobaciones de «Añadir a mano» salen del guion de Revisar candidatos a `aprobacion.acta.problema_al_anadir`, para que el Analizador use las mismas. La puerta (sólo lo que cotiza en dólares) y el motivo ya redactado van en `medidores_analizador`. Y la valoración con que entró cada aprobada se enseña en Actas y en la lista de añadidos: un dato que se guarda y no se enseña es el defecto de «El aviso que se calculaba y no se enseñaba».

**Files:**
- Modify: `aprobacion/acta.py`
- Modify: `medidores_analizador.py`
- Modify: `vistas/candidatos.py:468-524`
- Modify: `vistas/actas.py:106-118`
- Test: `tests/test_aprobacion_acta.py`, `tests/test_medidores_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_aprobacion_acta.py`:

```python
# --- El Analizador: «Añadir a la revisión» --------------------------------------

_VALORACION = {
    "version": "m1",
    "fecha": "2026-10-26",
    "moneda": "MXN",
    "veredicto": "en_rango",
    "valor": {"pesimista": 300.0, "base": 600.0, "optimista": None},
    "divisa": {"moneda_precio": "USD", "moneda_valoracion": "MXN", "tipo_precio": 20.0},
}


def test_el_anadido_desde_el_analizador_llega_al_acta_con_su_valoracion(tmp_path):
    from aprobacion.acta import listar_actas

    acta = construir_acta(
        candidatos("AAA"),
        aprobados=set(),
        anadidos=[Anadido(ticker="AMX", motivo="Analizador, 26/10/2026: en rango", valoracion=_VALORACION)],
    )
    manual = acta["aprobados"][0]
    # En pesos, como sale de `valorar`: el acta lo dice con `moneda` y `divisa`.
    assert manual["valoracion"] == _VALORACION
    guardar_acta(acta, tmp_path)
    leida = listar_actas(tmp_path)[0].acta
    assert leida["aprobados"][0]["valoracion"]["moneda"] == "MXN"


def test_un_anadido_a_mano_lleva_la_valoracion_vacia():
    acta = construir_acta(
        candidatos("AAA"), aprobados=set(), anadidos=[Anadido(ticker="JPM", motivo="bancos")]
    )
    assert acta["aprobados"][0]["valoracion"] is None


def test_un_acta_vieja_sin_valoracion_en_sus_anadidos_se_sigue_leyendo(tmp_path):
    from aprobacion.acta import listar_actas, valoracion_de_entrada

    vieja = {
        "fecha": "2026-08-20T10:00:00",
        "corrida": None,
        "aprobados": [
            {"ticker": "JPM", "origen": "manual", "puesto": None, "ficha": None, "motivo": "bancos"},
        ],
        "no_aprobados": [],
    }
    (tmp_path / "2026-08-20-100000.json").write_text(json.dumps(vieja), encoding="utf-8")
    guardada = listar_actas(tmp_path)[0]
    assert guardada.error is None
    assert tickers_aprobados(guardada.acta) == ["JPM"]
    assert valoracion_de_entrada(guardada.acta["aprobados"][0]) is None


def test_la_valoracion_de_una_aprobada_del_ranking_sale_de_su_ficha():
    from aprobacion.acta import valoracion_de_entrada

    ficha = {**FICHA, "valoracion": _VALORACION}
    assert valoracion_de_entrada({"origen": "ranking", "ficha": ficha}) == _VALORACION
    assert valoracion_de_entrada({"origen": "manual", "valoracion": _VALORACION}) == _VALORACION
    # Sin `version` no se reconoce, como en `carga.valoracion_de`.
    assert valoracion_de_entrada({"origen": "manual", "valoracion": {"veredicto": "x"}}) is None
    assert valoracion_de_entrada({"origen": "ranking", "ficha": None}) is None


def test_problema_al_anadir_dice_lo_mismo_que_dira_el_acta():
    from aprobacion.acta import problema_al_anadir

    anadidos = [Anadido(ticker="msft", motivo="ya")]
    assert "no tiene forma de ticker" in problema_al_anadir("WALMEX.MX", "x", set(), anadidos)
    assert "necesita un motivo" in problema_al_anadir("JPM", "   ", set(), anadidos)
    assert "ya está en el ranking" in problema_al_anadir("aaa", "x", {"AAA"}, anadidos)
    assert "ya está en la lista" in problema_al_anadir("MSFT", "x", set(), anadidos)
    assert problema_al_anadir("JPM", "bancos", {"AAA"}, anadidos) is None
```

En `tests/test_medidores_analizador.py`, al final:

```python
# --- El gate --------------------------------------------------------------------


def test_lo_que_cotiza_en_dolares_puede_ir_a_la_revision():
    assert ma.puerta(analisis("TSM", "extranjera_sec")) is None
    # AMX cotiza en dólares aunque se valore en pesos: pasa.
    assert ma.puerta(analisis("AMX", "extranjera_sec", valoracion=_amx())) is None


def test_lo_que_cotiza_en_pesos_no_y_se_explica():
    texto = ma.puerta(analisis("WALMEX.MX", "sin_sec", moneda="MXN"))
    assert "MXN" in texto and "covarianza" in texto


def test_un_etf_no_va_a_la_revision_desde_aqui():
    assert "a mano en Revisar candidatos" in ma.puerta(analisis("SPY", "etf"))


def test_el_motivo_ya_redactado_es_el_del_spec():
    votos = {
        "flujos": {"voto": "barata", "motivo": None},
        "sin_crecimiento": {"voto": "neutra", "motivo": None},
        "pares": {"voto": "barata", "motivo": None},
    }
    texto = ma.motivo_para_la_revision(_fija(veredicto="infravalorada", votos=votos), date(2026, 10, 12))
    assert texto == (
        "Analizador, 12/10/2026: infravalorada (flujos y pares a favor), supuestos del programa."
    )


def test_el_motivo_dice_lo_que_vota_en_contra_y_lo_que_no_hay():
    votos = {
        "flujos": {"voto": "cara", "motivo": None},
        "sin_crecimiento": {"voto": "neutra", "motivo": None},
        "pares": {"voto": "barata", "motivo": None},
    }
    texto = ma.motivo_para_la_revision(_fija(veredicto="mixtas", votos=votos), date(2026, 10, 26))
    assert "señales mixtas (pares a favor, flujos en contra)" in texto
    assert ma.motivo_para_la_revision(_fija(), date(2026, 10, 26)) == (
        "Analizador, 26/10/2026: en rango (pares a favor), supuestos del programa."
    )
    fallida = {"version": "m1", "fecha": "2026-10-26", "motivo": "sin_estados"}
    assert ma.motivo_para_la_revision(fallida, date(2026, 10, 26)).startswith(
        "Analizador, 26/10/2026: sin valoración (los estados"
    )
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_aprobacion_acta.py tests/test_medidores_analizador.py -q`
Expected: FAIL con `TypeError: Anadido.__init__() got an unexpected keyword argument 'valoracion'` y `AttributeError: ... 'puerta'`.

- [ ] **Step 3: Implementar en `aprobacion/acta.py`**

1. `Anadido` pasa a ser:

```python
@dataclass(frozen=True)
class Anadido:
    """A company the reviewer put in by hand, with the reason it went in.

    `valoracion` es la del Analizador cuando llega por «Añadir a la revisión»:
    la de los supuestos del programa, tal cual sale de
    `analizador.valorar.valorar`, con sus claves `moneda` y `divisa` (la de AMX
    va en pesos, y el acta lo dice con ellas). Lo movido en los deslizadores no
    viaja nunca: lo guardado tiene que ser comparable entre actas. Añadida a
    mano en Revisar candidatos, `None`. Las actas anteriores no la llevan, y nada
    que las lea puede exigirla (`valoracion_de_entrada`).
    """

    ticker: str
    motivo: str
    valoracion: "dict | None" = None
```

2. En `construir_acta`, el diccionario de cada manual gana la clave:

```python
        manuales.append(
            {
                "ticker": ticker,
                "origen": "manual",
                "puesto": None,
                "ficha": None,
                "motivo": anadido.motivo.strip(),
                "valoracion": anadido.valoracion,
            }
        )
```

3. Después de `normalizar`:

```python
def problema_al_anadir(ticker: str, motivo: str, del_ranking, anadidos) -> "str | None":
    """Por qué no se puede añadir este ticker a mano, o None si se puede.

    Son las tres comprobaciones de `construir_acta` --forma, motivo y que no
    esté ya en el ranking ni entre los añadidos-- dichas en el momento de
    añadir, cuando el revisor todavía recuerda lo que tecleó, y no al final de
    la revisión. `construir_acta` sigue siendo la autoridad y las repite.
    Estaban escritas dentro de `vistas/candidatos.py`; el Analizador necesita
    las mismas, y dos copias de una regla del gate se separan.
    """
    try:
        candidato = normalizar(ticker)
    except TickerInvalido as error:
        return str(error)
    if not motivo.strip():
        return (
            f"{candidato} necesita un motivo escrito: sin ranking detrás, es la "
            "única justificación que va a existir."
        )
    if candidato in del_ranking:
        return (
            f"{candidato} ya está en el ranking: apruébalo con su casilla en vez de "
            "añadirlo a mano."
        )
    if candidato in {a.ticker.strip().upper() for a in anadidos}:
        return f"{candidato} ya está en la lista de añadidos a mano."
    return None
```

4. Después de `tickers_aprobados`:

```python
def valoracion_de_entrada(entrada: dict) -> "dict | None":
    """La valoración con que entró una aprobada, o None.

    La de su ficha si vino del ranking; la del Analizador si se añadió a mano.
    Un acta anterior a N2 no la lleva en sus añadidos, y una añadida a mano en
    Revisar candidatos la lleva vacía. Se exige `version`, como
    `carga.valoracion_de`: es lo único que tienen en común una valoración
    calculada y una fallida.
    """
    if entrada.get("origen") == "manual":
        valor = entrada.get("valoracion")
    else:
        ficha = entrada.get("ficha")
        valor = ficha.get("valoracion") if isinstance(ficha, dict) else None
    if not isinstance(valor, dict) or not isinstance(valor.get("version"), str):
        return None
    return valor
```

- [ ] **Step 4: Implementar en `medidores_analizador.py`**

Al final:

```python
# --- El gate --------------------------------------------------------------------


def puerta(analisis) -> "str | None":
    """Por qué este ticker no puede ir a la revisión, o None si puede.

    Sólo pasa lo que cotiza en dólares (decisión del usuario del 2026-10-26).
    El optimizador baja precios sin convertir divisas y los libros van en
    dólares: una serie en pesos entre series en dólares mezclaría dos monedas
    en la misma covarianza, el error que el sub-proyecto L evitó. AMX y TSM
    cotizan en dólares y pasan; WALMEX.MX, no. Un ETF no se valora, y desde aquí
    no se lleva (D5).
    """
    if analisis.clase == "etf":
        return (
            "Un ETF no se valora, así que el Analizador no lo lleva a la revisión. "
            "Si lo quieres en el optimizador, añádelo a mano en Revisar candidatos."
        )
    moneda = analisis.identidad.moneda if analisis.identidad is not None else None
    if moneda == "USD":
        return None
    return (
        f"{analisis.ticker} cotiza en {moneda or 'una moneda que Yahoo no dio'}, y sólo "
        "pasan a la revisión las que cotizan en dólares. El optimizador baja los "
        "precios sin convertir divisas y los libros van en dólares: una serie en otra "
        "moneda entre series en dólares mezclaría dos monedas en la misma covarianza. "
        "Una ADR, como TSM, cotiza en dólares y sí pasa."
    )


_VOTO_CORTO = {"flujos": "flujos", "sin_crecimiento": "valor sin crecimiento", "pares": "pares"}


def motivo_para_la_revision(valoracion, hoy: date) -> str:
    """El motivo ya redactado de «Añadir a la revisión», con los supuestos del programa.

    «Analizador, 12/10/2026: infravalorada (flujos y pares a favor), supuestos
    del programa», como en el spec. Es editable, y el acta guarda lo que quede
    escrito: es texto del usuario, no una etiqueta de pantalla.
    """
    fecha = f"{hoy:%d/%m/%Y}"
    if not isinstance(valoracion, dict) or "veredicto" not in valoracion:
        motivo = valoracion.get("motivo") if isinstance(valoracion, dict) else None
        return (
            f"Analizador, {fecha}: sin valoración "
            f"({medidores_valoracion.etiqueta_motivo(motivo)})."
        )
    etiqueta_, _ = medidores_valoracion.VEREDICTO.get(valoracion["veredicto"], (valoracion["veredicto"], None))
    veredicto = etiqueta_[0].lower() + etiqueta_[1:]
    nombres = dict(_VOTO_CORTO)
    if valoracion.get("metodo") == "residual":
        nombres["flujos"] = "beneficio residual"
    votos = valoracion.get("votos") or {}
    a_favor = [nombres[c] for c in _VOTO_CORTO if (votos.get(c) or {}).get("voto") == "barata"]
    en_contra = [nombres[c] for c in _VOTO_CORTO if (votos.get(c) or {}).get("voto") == "cara"]
    partes = []
    if a_favor:
        partes.append(f"{_y(a_favor)} a favor")
    if en_contra:
        partes.append(f"{_y(en_contra)} en contra")
    detalle = f" ({', '.join(partes)})" if partes else ""
    return f"Analizador, {fecha}: {veredicto}{detalle}, supuestos del programa."
```

- [ ] **Step 5: Usar `problema_al_anadir` y enseñar la valoración en `vistas/candidatos.py`**

1. En la importación de `aprobacion.acta`, cambia `normalizar` por `problema_al_anadir` (`TickerInvalido` se queda: lo usa el `except` del botón de aprobar):

```python
from aprobacion.acta import (
    Anadido,
    MotivoRequerido,
    NadaQueAprobar,
    TickerDuplicado,
    TickerInvalido,
    construir_acta,
    guardar_acta,
    problema_al_anadir,
    tickers_aprobados,
)
```

2. El bloque `if enviado:` (de `_ya_anadidos = ...` al `st.rerun()`) pasa a ser:

```python
if enviado:
    # `problema_al_anadir` no sustituye a `construir_acta`, que sigue siendo la
    # autoridad y repite las comprobaciones al escribir el acta: lo dice
    # **ahora**, cuando el revisor todavía recuerda lo que tecleó. El Analizador
    # usa la misma función con «Añadir a la revisión».
    _problema = problema_al_anadir(
        nuevo_ticker,
        nuevo_motivo,
        {f["ticker"] for f in candidatos.fichas},
        st.session_state.anadidos,
    )
    if _problema:
        st.error(_problema)
    else:
        st.session_state.anadidos.append(Anadido(ticker=nuevo_ticker, motivo=nuevo_motivo))
        st.rerun()
```

3. En la lista de añadidos, el `st.markdown` de cada uno pasa a ser:

```python
            # El motivo lo escribió el propio revisor, pero se escapa igual: un
            # «PER < $20» se comería la línea hasta el siguiente dólar y le
            # borraría de la vista la razón que él mismo tecleó. La valoración
            # es la que llegó del Analizador, y es la que irá al acta.
            _valor = medidores_valoracion.valoracion_en_una_linea(anadido.valoracion)
            st.markdown(
                f"- **{texto.plano(anadido.ticker.strip().upper())}** — "
                f"{texto.plano(anadido.motivo)}"
                + (f"  \n  Valor intrínseco al añadirla: {texto.plano(_valor)}" if _valor else "")
            )
```

- [ ] **Step 6: Enseñar la valoración en `vistas/actas.py`**

Añade `import medidores_valoracion` a las importaciones y cambia la de `aprobacion.acta` por:

```python
from aprobacion.acta import listar_actas, tickers_aprobados, valoracion_de_entrada
```

y la tabla de «Aprobadas» pasa a ser:

```python
            st.dataframe(
                pd.DataFrame([
                    {
                        "Ticker": entrada["ticker"],
                        "Puesto": entrada.get("puesto") or "añadida a mano",
                        "Motivo": entrada.get("motivo") or "",
                        # La valoración con que entró: la de su ficha, o la del
                        # Analizador. Un acta anterior a N2 no la lleva, y se
                        # deja en blanco en vez de reventar.
                        "Valor intrínseco": medidores_valoracion.valoracion_en_una_linea(
                            valoracion_de_entrada(entrada)
                        ),
                    }
                    for entrada in aprobados
                ]),
                use_container_width=True, hide_index=True,
            )
```

- [ ] **Step 7: Comprobar que pasan**

Run: `uv run pytest tests/test_aprobacion_acta.py tests/test_medidores_analizador.py tests/test_noticias_texto.py -q`
Expected: todos pasan; `test_la_ficha_del_candidato_no_pinta_nada_ajeno_sin_escapar` sigue verde con la valoración escapada.

- [ ] **Step 8: Commit**

```bash
git add aprobacion/acta.py medidores_analizador.py vistas/candidatos.py vistas/actas.py tests/test_aprobacion_acta.py tests/test_medidores_analizador.py
git commit -m "feat: el acta registra la valoración de lo que llega del Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: El archivo de las lecturas y el bloque de «Interpretar con IA»

> **Ejecutada** (3a6b095) el 2026-10-27. `interpretar_hechos` gana `clave=`, y el Analizador la llama con `pesos=()` y `clave=f"analizador_ia_{ticker}"`. De la revisión de las Tasks 11-19 (2026-11-10, 484c078): `consultado`, sin valor por defecto, para no afirmar «se miró y no había ninguno» si la SEC no respondió. Del recorrido de la Task 21 (a88e486): los `$` del coste, que se leían como LaTeX, van escapados. Manda el código vivo.

Decisión 2 y D7. El bloque de Seguimiento que interpreta los 8-K —el archivo, el botón con su coste, la lectura, lo guardado— sale de su guion a `vistas/panel_ia.interpretar_hechos`, parametrizado, para que el Analizador lo use igual. Las lecturas de un ticker se guardan en `analisis/<TICKER>.json`, con el formato de `interprete/archivo.py`, y `analisis/` va a `.gitignore` y a «Dónde vive todo».

Al moverlo sale un defecto latente: en el guion, `_leidas` eran las urls ya leídas y, tras pulsar, pasaba a ser lo que devuelve `preparar` (una tupla de tuplas); si la lectura fallaba, `pintar_archivo` buscaba urls en esa tupla y no pintaba nada de lo guardado. Aquí van con dos nombres.

**Files:**
- Create: `analizador/archivo.py`
- Modify: `vistas/panel_ia.py`
- Modify: `vistas/seguimiento.py:21-23, 1162-1285`
- Modify: `vistas/perfil.py:20-23, 287-299`
- Modify: `.gitignore`
- Test: `tests/test_analizador_archivo.py`, `tests/test_panel_ia.py`, `tests/test_vistas_perfil.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_analizador_archivo.py`:

```python
"""Dónde se guardan las lecturas de la IA de un ticker del Analizador."""

from datetime import date
from pathlib import Path

from analizador import archivo
from interprete import archivo as interprete_archivo
from interprete import noticias

RAIZ = Path(__file__).resolve().parent.parent


def test_cada_ticker_tiene_su_archivo_en_analisis():
    assert archivo.ruta_de("MU") == Path("analisis") / "MU.json"
    assert archivo.ruta_de("BRK-B").name == "BRK-B.json"


def test_el_archivo_de_un_ticker_es_el_de_interprete_tal_cual(tmp_path, monkeypatch):
    monkeypatch.setattr(archivo, "DIRECTORIO", tmp_path / "analisis")
    ruta = archivo.ruta_de("MU")
    # Que no exista es un ticker que nadie ha interpretado.
    assert interprete_archivo.cargar(ruta) == interprete_archivo.Archivo()
    juicio = noticias.Juicio("MU", "qué dice", "por qué", "una cita literal del documento", True)
    anotada = interprete_archivo.Anotada("https://www.sec.gov/x", "MU", date(2026, 10, 1), ("2.02",), juicio)
    interprete_archivo.anotar_hechos(ruta, "modelo", "i3", (anotada,), "")
    assert interprete_archivo.urls_leidas(interprete_archivo.cargar(ruta)) == {"https://www.sec.gov/x"}
    assert ruta.parent == tmp_path / "analisis"


def test_las_lecturas_quedan_fuera_de_git():
    assert "analisis/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
```

En `tests/test_panel_ia.py`, `test_la_pantalla_pega_el_como_mucho_a_un_tope_de_verdad` pasa a ser (y se añaden los dos de debajo):

```python
def _interpretar_hechos():
    import ast

    fuente = (RAIZ / "vistas" / "panel_ia.py").read_text(encoding="utf-8")
    funcion = next(
        n for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.FunctionDef) and n.name == "interpretar_hechos"
    )
    return fuente, funcion


def test_la_pantalla_pega_el_como_mucho_a_un_tope_de_verdad():
    """«Cuesta unos X $ **como mucho**» iba con la cifra de `coste_estimado`,
    que es la media y un solo turno. El saboteador: devolver la llamada a
    `coste_estimado` a la linea del «como mucho» tumba esto. Vive en
    `panel_ia.interpretar_hechos` desde que Seguimiento y el Analizador
    comparten el bloque."""
    import ast

    fuente, funcion = _interpretar_hechos()
    cuerpo = ast.get_source_segment(fuente, funcion)
    anuncio = next(
        bloque for bloque in cuerpo.split("st.caption(")[1:] if "como mucho" in bloque
    ).split(")\n")[0]
    assert "coste_peor_caso(" in anuncio
    detras = anuncio.split("como mucho", 1)[1]
    assert detras.split("coste_", 1)[1].startswith("peor_caso")


def test_tras_un_fallo_lo_guardado_se_sigue_pintando():
    """En el guion de Seguimiento, `_leidas` eran las urls leídas y, tras
    pulsar, lo que devolvía `preparar`: con una lectura fallida,
    `pintar_archivo` buscaba urls en una tupla de tuplas y no pintaba nada de
    lo guardado. El nombre que llega a `pintar_archivo` sólo se asigna una vez,
    con `urls_leidas`."""
    import ast

    _fuente, funcion = _interpretar_hechos()
    llamada = next(
        n for n in ast.walk(funcion)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "pintar_archivo"
    )
    nombre = llamada.args[3].id
    asignaciones = [
        n for n in ast.walk(funcion)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == nombre for o in n.targets for t in ast.walk(o))
    ]
    assert len(asignaciones) == 1
    assert "urls_leidas" in ast.unparse(asignaciones[0].value)


def test_seguimiento_usa_el_bloque_compartido():
    fuente = (RAIZ / "vistas" / "seguimiento.py").read_text(encoding="utf-8")
    assert "panel_ia.interpretar_hechos(" in fuente
    assert "interprete_noticias.leer(" not in fuente
```

En `tests/test_vistas_perfil.py`, añade `from analizador import archivo as archivo_analizador` a las importaciones; en `test_las_rutas_salen_de_las_constantes_y_no_escritas_a_mano`, la tupla pasa a ser `("`actas/`", "`salidas/`", "`libros/`", "`portafolios/`", "`analisis/`")`; en `test_las_constantes_que_la_tabla_usa_son_las_que_el_programa_escribe`, añade `assert archivo_analizador.DIRECTORIO.name == "analisis"`; y al final:

```python
def test_la_tabla_nombra_las_lecturas_del_analizador():
    """Se pagaron con la clave del usuario, como las de los libros."""
    assert "archivo_analizador.DIRECTORIO" in _tabla()


def test_la_tabla_nombra_las_caches_que_usa_el_analizador():
    for carpeta in ("valoracion/.cache/", "analizador/.cache/", "noticias/.cache/"):
        assert carpeta in _tabla()
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_analizador_archivo.py tests/test_panel_ia.py tests/test_vistas_perfil.py -q`
Expected: FAIL con `ImportError: cannot import name 'archivo' from 'analizador'` y `StopIteration` (no hay `interpretar_hechos` en `panel_ia.py`).

- [ ] **Step 3: Crear `analizador/archivo.py`**

```python
"""Dónde se guarda lo que la IA dice de un ticker del Analizador.

`analisis/<TICKER>.json`, en la raíz del programa, junto a `actas/` y
`libros/`, y fuera de git. N2 guarda ahí sólo las lecturas de los 8-K, con el
formato y las funciones de `interprete/archivo.py` tal cual: append-only, un
archivo ilegible no se trata como vacío ni se pisa, y lo ya leído se pinta sin
pagar. N3 añade aquí lo de los otros tres bloques.

**Aviso para N3.** `interprete.archivo.anotar_hechos` reescribe el fichero
entero con sólo `hechos` y `rebalanceo`: una clave más que N3 guarde en el
mismo fichero se perdería en la siguiente lectura de 8-K si antes no cambia
cómo se escribe.
"""

from pathlib import Path

# Relativa, como `aprobacion.acta.ACTAS` y `seguimiento.libro.DIRECTORIO`: los
# lanzadores arrancan en programa/.
DIRECTORIO = Path("analisis")


def ruta_de(ticker: str) -> Path:
    """`analisis/<TICKER>.json`.

    El ticker llega normalizado (`resolver.normalizar`): letras, dígitos y
    `.-=&^`, que Windows admite en el nombre de un fichero.
    """
    return DIRECTORIO / f"{ticker}.json"
```

- [ ] **Step 4: `.gitignore`**

Debajo de `portafolios/`, en el bloque de los datos personales:

```
# Lo que la IA del Analizador dijo de cada ticker: se pagó con la clave del
# usuario y es historial, como las interpretaciones de `libros/`.
analisis/
```

- [ ] **Step 5: `interpretar_hechos`, en `vistas/panel_ia.py`**

1. El mensaje de `SIN_CLAVE` en `avisos` decía «Se pone en Aprobación», y las credenciales viven en «Perfil y ajustes» desde el rediseño:

```python
    if lectura.estado == interprete_noticias.SIN_CLAVE:
        mensajes.append(("info", "Falta la clave de Anthropic. Se pone en Perfil y ajustes."))
```

2. Al final del fichero:

```python
def interpretar_hechos(st, a_leer, ruta_archivo, tickers, pesos, clave, con_enlace_a_perfil=False):
    """El botón de «Interpretar estos hechos», con su archivo.

    Lo estrenó la pestaña Noticias de Seguimiento y lo reutiliza el Analizador:
    estaba escrito dentro de `vistas/seguimiento.py`, y dos copias de un camino
    que cobra se separan igual que dos de cualquier otra cosa.

    - `a_leer`: los hechos que hay en pantalla, que son los que se interpretan
      (los destacados más recientes, `noticias.resumen.TOPE_HECHOS`).
    - `ruta_archivo`: dónde se guardan las lecturas. El del libro en
      Seguimiento; `analisis/<TICKER>.json` en el Analizador.
    - `tickers` y `pesos`: lo que el modelo puede nombrar y la cartera que ve.
      En el Analizador, el ticker y nada: `pesos=()`, porque allí no hay cartera.
    - `clave`: separa en `session_state` los avisos de cada pantalla, y la clave
      de sus botones.

    **Se pinta desde el archivo, nunca desde la `Lectura` recién hecha.** Un
    solo camino, y así la fecha de cada juicio vive donde pertenece --en la
    sesión-- en vez de tener que viajar dentro de cada `Juicio`. La excepción
    es el archivo ilegible: ahí no se puede ni leer ni guardar, así que se pinta
    la lectura directamente con el aviso, para que un fichero roto no se lleve
    por delante la llamada que se acaba de pagar.
    """
    try:
        guardado = archivo_mod.cargar(ruta_archivo)
        roto = ""
    except archivo_mod.ArchivoIlegible as error:
        guardado = archivo_mod.Archivo()
        roto = str(error)

    if roto:
        st.error(
            f"{roto}\n\nEl fichero **no se ha tocado**: sigue ahí por si "
            "quieres recuperarlo a mano. Se puede interpretar igual, pero lo "
            "que salga no se va a poder guardar."
        )

    # Las urls ya leídas, que es lo que necesita `pintar_archivo`. No se pisan
    # con lo que devuelve `preparar`: en el guion de Seguimiento compartían
    # nombre, y tras una lectura fallida `pintar_archivo` buscaba urls en una
    # tupla de tuplas y no pintaba nada de lo guardado.
    leidas = archivo_mod.urls_leidas(guardado)
    nuevos = [h for h in a_leer if h.url not in leidas]

    if not a_leer:
        st.caption(
            "No hay hechos materiales que interpretar. No es que no se haya "
            "mirado: se miró y no había ninguno."
        )
    elif not cliente_mod.hay_clave():
        st.info(
            "Falta la clave de Anthropic. Se pone en **Perfil y ajustes**, y hasta "
            "entonces todo lo demás funciona igual."
        )
        if con_enlace_a_perfil and st.button(
            "Configurar mis credenciales", key=f"{clave}_perfil", icon=":material/key:"
        ):
            st.switch_page("vistas/perfil.py")
    else:
        etiqueta = (
            f"Interpretar estos hechos ({len(nuevos)} nuevos)"
            if nuevos else "Volver a interpretar (ninguno nuevo)"
        )
        # «Como mucho» tiene que ir pegado a un tope de verdad. Decía eso con
        # la cifra de `coste_estimado`, que es la media de un solo turno —y el
        # documento puede forzar el segundo cuando quiera—, así que lo
        # anunciado se quedaba en menos de la mitad de lo que podía costar.
        # Ahora se dan las dos cifras y cada una dice lo que es.
        cuantos = len(nuevos) or len(a_leer)
        st.caption(
            f"Leer {cuantos} documentos cuesta como mucho "
            f"**{coste_peor_caso(cuantos):.2f} $**, y normalmente "
            f"alrededor de **{coste_estimado(cuantos):.2f} $**. El "
            "tope cuenta el reintento, que lo dispara el propio documento. Lo "
            "que costó de verdad se dice al terminar."
        )
        if st.button(etiqueta, icon=":material/auto_awesome:", key=f"{clave}_interpretar"):
            with st.spinner("Bajando los documentos y leyéndolos…"):
                if nuevos:
                    entradas, ya_leidas, sin_doc, recortados = preparar(a_leer, guardado)
                else:
                    # «Volver a interpretar» con todo ya leído tiene que ser una
                    # segunda lectura de verdad, no una relectura de resúmenes:
                    # con un Archivo() vacío no hay nada leído, y `preparar`
                    # baja los documentos de nuevo en vez de reenviar lo que el
                    # propio modelo escribió la vez anterior.
                    entradas, ya_leidas, sin_doc, recortados = preparar(a_leer, archivo_mod.Archivo())
                lectura = interprete_noticias.leer(
                    entradas,
                    set(tickers),
                    sin_documento=sin_doc,
                    recortados=recortados,
                    pesos=tuple(pesos),
                    leidos=ya_leidas,
                )
            if lectura.estado == interprete_noticias.HECHA and not roto:
                try:
                    archivo_mod.anotar_hechos(
                        ruta_archivo,
                        cliente_mod.MODELO,
                        interprete_noticias.VERSION_PROMPT,
                        anotadas(lectura, a_leer),
                        lectura.en_conjunto,
                    )
                except OSError as fallo:
                    # Esta lectura ya se pagó. Un traceback aquí perdería además
                    # la única copia que existe de ella, así que el aviso dice
                    # las dos cosas --que no se guardó y que volver a pedirla se
                    # vuelve a cobrar-- y la deja en pantalla.
                    st.error(
                        f"**No se pudo guardar la lectura: {fallo}**\n\n"
                        "El archivo anterior sigue intacto, pero lo que se "
                        "acaba de leer **no ha quedado guardado**, y volver a "
                        "pedirlo se cobra otra vez. Aquí abajo está entero."
                    )
                    pintar_lectura(st, lectura)
                else:
                    st.session_state[f"{clave}_avisos"] = avisos(lectura)
                    st.rerun()
            else:
                # No se guarda y no se rerun: si se fue por `FALLO` o el archivo
                # está roto, el `st.rerun()` se llevaría por delante el único
                # sitio donde se puede decir qué pasó.
                for clase, mensaje in avisos(lectura):
                    getattr(st, clase)(mensaje)
                pintar_lectura(st, lectura)

    for clase, mensaje in st.session_state.pop(f"{clave}_avisos", []):
        getattr(st, clase)(mensaje)

    pintar_archivo(st, guardado, a_leer, leidas)
```

- [ ] **Step 6: Seguimiento usa el bloque compartido**

En `vistas/seguimiento.py`:

1. Quita las dos importaciones que dejan de usarse: `from interprete import cliente as interprete_cliente` y `from interprete import noticias as interprete_noticias` (`from interprete import archivo` se queda: da `archivo.ruta_de`).

2. Todo lo que va desde `_ruta_archivo = archivo.ruta_de(elegida.ruta)` hasta `panel_ia.pintar_archivo(st, _guardado, _a_leer, _leidas)`, ambos incluidos, pasa a ser:

```python
    panel_ia.interpretar_hechos(
        st,
        resumen_noticias.hechos[:resumen.TOPE_HECHOS],
        archivo.ruta_de(elegida.ruta),
        {l.ticker for l in comp.lineas},
        tuple((l.ticker, l.peso, l.objetivo) for l in comp.lineas),
        # «ia» deja la clave de los avisos en `ia_avisos`, la de siempre.
        clave="ia",
    )
```

El comentario de encima («La interpretación», con «Se pinta desde el archivo…») se reduce a:

```python
    # --- La interpretación -------------------------------------------------
    #
    # El bloque vive en `vistas/panel_ia.interpretar_hechos`, que comparte con
    # el Analizador. Sin `st.divider()` propio: el de más arriba ya cerraba
    # Titulares, y dos seguidos se ven como una raya doble sin nada en medio.
```

y `st.markdown("**Qué significan estos hechos para tu cartera**")` se queda donde está, antes de la llamada.

- [ ] **Step 7: «Dónde vive todo», en `vistas/perfil.py`**

Añade `from analizador import archivo as archivo_analizador` a las importaciones, y en la tabla, debajo de la fila de «Interpretaciones de la IA», y cambiando la de la caché:

```
| Lecturas de la IA del Analizador | `{archivo_analizador.DIRECTORIO}/` | Sí, pero volver a leerlas cuesta dinero |
```

```
| Caché de descargas | `fundamentals/.cache/`, `ranking/.cache/`, `valoracion/.cache/`, `analizador/.cache/`, `noticias/.cache/` | Sí, se vuelven a bajar |
```

- [ ] **Step 8: Comprobar que pasan**

Run: `uv run pytest tests/test_analizador_archivo.py tests/test_panel_ia.py tests/test_vistas_perfil.py tests/test_panel_noticias.py tests/test_interprete_archivo.py -q`
Expected: todos pasan.

- [ ] **Step 9: Comprobar que Seguimiento sigue arrancando**

Run: `uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('vistas/seguimiento.py').read_text(encoding='utf-8')); ast.parse(pathlib.Path('vistas/panel_ia.py').read_text(encoding='utf-8')); print('ok')"`
Expected: `ok`. Y `grep -n "interprete_cliente\|interprete_noticias\|_leidas\|_guardado" vistas/seguimiento.py` no devuelve nada.

- [ ] **Step 10: Commit**

```bash
git add analizador/archivo.py vistas/panel_ia.py vistas/seguimiento.py vistas/perfil.py .gitignore tests/test_analizador_archivo.py tests/test_panel_ia.py tests/test_vistas_perfil.py
git commit -m "feat: el bloque de interpretar los 8-K, compartido, y el archivo de lecturas del Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 14: La pantalla, arriba y el resumen

> **Ejecutada** (d97f858) el 2026-10-27. Sobre el plan: construir el panel captura también `OSError`, y el panel atrasado se dice una vez. `AppTest.from_file("vistas/analizador.py")` choca con un import circular que en la app no existe: el primer AppTest (a2839b2) usa `tests/guion_analizador.py`, que la ejecuta con `runpy`. De la revisión de las Tasks 11-19 (2026-11-10, c11051b): «el panel de antes» sólo si lo había, «Cargar de un libro» dice el tope antes de cargar. Manda el código vivo.

La primera mitad de `vistas/analizador.py`: el campo de tickers con «Cargar de un libro» y «Analizar», el panel de referencia (su fecha, si es más nuevo que los candidatos, el botón para construirlo o rehacerlo), el resumen con «Actualizar precios», «Lo que viene» con los punteros macro, y el detalle con su primera pestaña, Resumen. Las demás pestañas llegan en las Tasks 15 a 17: `_PESTANAS` dice qué pestaña dibuja quién, y una pestaña sin función no se dibuja. El Analizador entra en el menú, en «Análisis», detrás de Revisar candidatos; Noticias sigue en el suyo hasta la Task 19.

**Files:**
- Create: `vistas/analizador.py`
- Modify: `app.py:101-148`
- Test: `tests/test_vistas_analizador.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_vistas_analizador.py`:

```python
"""Lo que la pantalla del Analizador tiene que hacer, leído de su fuente.

La pantalla es un guion de Streamlit --se ejecuta al importarse-- así que no se
pueden llamar sus funciones: se lee su fuente con `ast`, como
`test_vistas_optimizador.py`. La lógica tiene sus tests en
`test_medidores_analizador.py` y en los de `analizador/`; aquí se comprueba que
la pantalla la usa y no la rehace.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = (RAIZ / "vistas" / "analizador.py").read_text(encoding="utf-8")
ARBOL = ast.parse(FUENTE)


def _funcion(nombre: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(ARBOL) if isinstance(n, ast.FunctionDef) and n.name == nombre)


def _cuerpo(nombre: str) -> str:
    return ast.get_source_segment(FUENTE, _funcion(nombre))


def _llamadas_a(atributo: str) -> list:
    return [
        n for n in ast.walk(ARBOL)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == atributo
    ]


def test_el_tope_de_tickers_es_el_del_resolver():
    assert "MAX_TICKERS" in FUENTE
    assert not any(isinstance(n, ast.Constant) and n.value == 15 for n in ast.walk(ARBOL))


def test_el_campo_de_tickers_se_declara_con_clave_y_sin_valor():
    # «El formulario que se quedaba en blanco»: un `value` que cambia entre
    # pasadas reinicia el widget y tira lo escrito.
    (campo,) = _llamadas_a("text_input")
    claves = {k.arg: ast.unparse(k.value) for k in campo.keywords}
    assert claves.get("key") == "sesion.CLAVE_TEXTO"
    assert "value" not in claves


def test_el_encargo_se_recoge_antes_de_dibujar_el_campo():
    assert FUENTE.index("sesion.recoger(") < FUENTE.index("st.text_input(")


def test_analizar_lleva_barra_de_progreso_y_guarda_en_la_sesion():
    cuerpo = _cuerpo("_analizar_tickers")
    assert "st.progress(" in cuerpo and "analizar(" in cuerpo
    assert "sesion.preparar(" in FUENTE and "sesion.pendientes(" in FUENTE


def test_actualizar_precios_no_rehace_la_ficha():
    cuerpo = _cuerpo("_actualizar_precios").replace("con_precio_nuevo(", "")
    assert "con_precio_nuevo" in _cuerpo("_actualizar_precios")
    assert "analizar(" not in cuerpo


def test_cargar_de_un_libro_solo_lleva_tickers():
    cuerpo = _cuerpo("_cargar_de_un_libro")
    assert "posiciones.tickers_a_mirar(" in cuerpo
    assert "on_click=sesion.cargar_texto" in cuerpo
    # Ni pesos ni importes: la pantalla no calcula nada del libro.
    assert "pesos_objetivo(" not in cuerpo and "posiciones.estado(" not in cuerpo


def test_construir_el_panel_no_pasa_por_generar_candidatos():
    assert "referencia.construir_panel(" in _cuerpo("_panel_de_referencia")
    assert "guardar(" not in FUENTE and "construir_ranking(" not in FUENTE


def test_el_resumen_sale_de_las_filas_con_tests():
    assert "ma.fila(" in FUENTE and "ma.COLUMNAS" in FUENTE


def test_el_detalle_elegido_se_fija_antes_del_desplegable():
    assert FUENTE.index("sesion.fijar_elegido(") < FUENTE.index("key=sesion.CLAVE_ELEGIDO")


def test_las_pestanas_salen_de_la_clase():
    assert "ma.pestanas_de(" in _cuerpo("_detalle")


def test_el_codigo_nuevo_no_usa_lo_que_streamlit_da_por_obsoleto():
    # Streamlit 1.62 avisa en la consola de que `use_container_width` y
    # `st.components.v1.html` se retiran (visto al arrancar la pantalla en un
    # worktree, al planear N2): lo nuevo usa `width` y `st.iframe`.
    assert "use_container_width" not in FUENTE and "components.v1" not in FUENTE


# --- Lo que no escribió el programa se escapa -----------------------------------

_PINTAN = {"markdown", "caption", "write", "info", "warning", "error", "success"}
# Lo que llega de Yahoo, de la SEC o de la prensa. `cuando` es una fecha que se
# formatea, no texto.
_AJENOS = {"noticia", "evento", "hecho", "identidad", "juicio"}
_INOCUOS = {"cuando"}


def _ajenos_fuera_de_texto(nodo) -> list:
    """Recorre el árbol y para en cuanto entra en una llamada a `texto.algo`."""
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and isinstance(nodo.func.value, ast.Name)
        and nodo.func.value.id == "texto"
    ):
        return []
    crudos = []
    if (
        isinstance(nodo, ast.Attribute)
        and isinstance(nodo.value, ast.Name)
        and nodo.value.id in _AJENOS
        and nodo.attr not in _INOCUOS
    ):
        crudos.append(nodo)
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "nombre"
        and getattr(nodo.func.value, "id", None) == "ma"
    ):
        crudos.append(nodo)
    for hijo in ast.iter_child_nodes(nodo):
        crudos.extend(_ajenos_fuera_de_texto(hijo))
    return crudos


def _sin_escapar(arbol) -> list:
    crudos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in _PINTAN:
            crudos.extend(_ajenos_fuera_de_texto(nodo))
    return crudos


def test_lo_que_no_escribio_el_programa_se_escapa_antes_de_pintarlo():
    crudos = _sin_escapar(ARBOL)
    assert crudos == [], "sin escapar en las líneas " + ", ".join(str(n.lineno) for n in crudos)


def test_el_saboteador_de_ese_test_lo_tumba():
    assert len(_sin_escapar(ast.parse('st.markdown(f"{noticia.titular}")'))) == 1
    assert len(_sin_escapar(ast.parse("st.caption(ma.nombre(a))"))) == 1
    assert _sin_escapar(ast.parse("st.markdown(texto.plano(noticia.titular))")) == []
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: FAIL con `FileNotFoundError: ... vistas/analizador.py`.

- [ ] **Step 3: Crear `vistas/analizador.py`**

```python
"""El Analizador: cualquier acción con la ficha de los candidatos, su gráfico y sus noticias.

Widgets sin lógica, como el resto de `vistas/`. Lo que se decide --qué es cada
ticker, cuánto vale, qué se dice de él-- vive en `analizador/`,
`medidores_analizador.py` y `medidores_valoracion.py`, con tests: este guion
pinta.

Absorbe «Noticias y calendario», que salió del menú: lo que aquella pantalla
hacía para un libro entero se hace aquí con «Cargar de un libro», y cada ticker
tiene sus hechos, su prensa y su calendario en su pestaña.

**El precio no se refresca solo, a propósito.** Un veredicto que cambia cada
minuto con el precio es ruido: cada fila lleva la hora de su cotización, y
«Actualizar precios» la vuelve a pedir. El tiempo real está en el gráfico, que
no es del programa ni entra en ninguna cuenta.

**Aquí no se recomienda nada.** Ni comprar, ni vender, ni esperar.
"""

from datetime import date

import pandas as pd
import streamlit as st

import medidores
import medidores_analizador as ma
import medidores_valoracion
import tema
from analizador import referencia, sesion
from analizador.analisis import analizar, con_precio_nuevo
from analizador.resolver import MAX_TICKERS, separar
from aprobacion.generacion import disponibilidad
from fundamentals.fetch import CorridaAbortada
from fundamentals.sectors import load_sectors
from noticias import macro, texto, traer
from seguimiento import posiciones
from vistas import libros

st.markdown(
    tema.cabecera(
        "Analizador",
        "Cualquier acción —de la SEC, extranjera o de la BMV— o un ETF, con la "
        "misma ficha frente a su sector y el mismo valor intrínseco que los "
        "candidatos, más su gráfico, sus noticias y su calendario. Aquí no se "
        "recomienda nada.",
    ),
    unsafe_allow_html=True,
)
st.markdown(medidores.CSS, unsafe_allow_html=True)
st.markdown(medidores_valoracion.CSS, unsafe_allow_html=True)


# --- Arriba: los tickers --------------------------------------------------------


def _cargar_de_un_libro() -> None:
    """«Cargar de un libro»: el desplegable de Seguimiento y Rebalanceo. Sólo viajan los tickers."""
    _en_disco, etiquetas = libros.disponibles()
    if not etiquetas:
        st.caption("Todavía no llevas ningún libro. Empiézalo en **Empezar un libro**.")
        return
    elegida = libros.desplegable(etiquetas)
    tickers = posiciones.tickers_a_mirar(elegida.libro.asientos, elegida.libro.objetivo)
    if not tickers:
        st.caption(
            "Este libro no tiene ningún activo: ni posiciones abiertas ni pesos "
            "objetivo. Registra una compra en **Seguimiento**, o dale un objetivo "
            "desde el optimizador."
        )
        return
    st.caption(
        f"{len(tickers)} activos: lo que tienes ahora más lo que el objetivo dice "
        "que deberías tener. Sólo viajan los tickers, ni pesos ni importes."
    )
    st.button(
        "Cargar en el campo",
        key="analizador_cargar_libro",
        icon=":material/download:",
        # En un callback: el campo ya está dibujado arriba, y Streamlit no deja
        # escribir en su clave después de dibujarlo en la misma pasada.
        on_click=sesion.cargar_texto,
        args=(st.session_state, tickers),
    )


def _analizar_tickers(tickers, hechos, panel, tabla) -> None:
    """Analiza los que faltan, con barra: quince en frío tardan cerca de un minuto."""
    barra = st.progress(0.0, text="Analizando…")
    for numero, ticker in enumerate(tickers, start=1):
        barra.progress(
            (numero - 1) / len(tickers),
            text=(
                f"Analizando {ticker} ({numero} de {len(tickers)}). En frío, "
                "quince tickers tardan cerca de un minuto."
            ),
        )
        hechos[ticker] = analizar(ticker, panel, tabla)
        sesion.olvidar_deslizadores(st.session_state, ticker)
        if hechos[ticker].clase is not None:
            # El calendario entra en el resumen («Próximo evento» y «Lo que
            # viene»): se trae aquí, dentro de la barra, y luego sale de la
            # caché, que vale un día.
            traer.traer("agenda", ticker, traer.DESCARGA["agenda"], False)
    barra.empty()


def _actualizar_precios(tickers, hechos, panel, tabla) -> None:
    """Rehace la identidad y la valoración de cada ticker; la ficha frente al sector se queda."""
    barra = st.progress(0.0, text="Actualizando precios…")
    for numero, ticker in enumerate(tickers, start=1):
        barra.progress((numero - 1) / len(tickers), text=f"Actualizando {ticker} ({numero} de {len(tickers)})…")
        hechos[ticker] = con_precio_nuevo(hechos[ticker], panel, tabla)
        sesion.olvidar_deslizadores(st.session_state, ticker)
    barra.empty()


def _panel_de_referencia(panel, fecha_panel, frescura, analizados) -> None:
    """De cuándo es la referencia sectorial y, si falta o se quedó atrás, el botón para hacerla."""
    trimestre = None if panel is None else referencia.trimestre_final(panel)
    atrasado = trimestre is not None and any(
        ma.aviso_panel_atrasado(a, trimestre) for a in analizados
    )
    if panel is None:
        st.warning(ma.SIN_PANEL)
    else:
        st.caption(ma.fecha_del_panel(fecha_panel, trimestre, frescura))
        if frescura.panel_posterior:
            st.info(ma.PANEL_POSTERIOR)
        if atrasado:
            st.warning(ma.PANEL_ATRASADO)
    if panel is not None and not atrasado:
        return
    puede = disponibilidad()
    if not puede.puede_generar:
        st.warning(puede.motivo_generacion)
        if st.button("Configurar mis credenciales", key="analizador_credenciales_panel", icon=":material/key:"):
            st.switch_page("vistas/perfil.py")
        return
    if st.button(
        "Construir el panel" if panel is None else "Rehacer el panel",
        key="analizador_panel",
        icon=":material/construction:",
        help=ma.AYUDA_PANEL,
    ):
        try:
            with st.spinner(
                "Construyendo el panel del S&P 500… unos dos minutos con la caché "
                "llena, y bastantes más la primera vez. No cierres ni recargues."
            ):
                referencia.construir_panel()
        except CorridaAbortada as error:
            # Como en Revisar candidatos: la causa con nombre, y nada escrito.
            st.error(str(error))
            return
        # Con el panel nuevo los análisis guardados ya no valen
        # (`sesion.preparar`): se rehacen los de la tabla, con el mismo elegido.
        if analizados:
            sesion.encargar(
                st.session_state,
                [a.ticker for a in analizados],
                st.session_state.get(sesion.CLAVE_ELEGIDO),
            )
        st.rerun()


# --- El resumen y lo que viene ------------------------------------------------


def _agenda(analizados) -> "tuple[dict, dict]":
    """El calendario de cada ticker, de la caché de un día, y los fallos agrupados por mensaje."""
    agenda, problemas = {}, {}
    for a in analizados:
        if a.clase is None:
            continue
        datos, problema, _cuando, _vigente = traer.traer("agenda", a.ticker, traer.DESCARGA["agenda"], False)
        agenda[a.ticker] = list(datos)
        if problema:
            problemas.setdefault(problema, []).append(a.ticker)
    return agenda, problemas


def _macro() -> None:
    """Los punteros macro, en su propio bloque y sin ninguna fecha."""
    st.markdown("##### Datos de mercado")
    st.caption(
        "Aquí no hay fechas, y es a propósito: el calendario macro no lo publica "
        "ninguna de las fuentes que usa el programa, y copiarlo al repositorio "
        "crearía algo que caduca en silencio —un calendario viejo se lee igual "
        "que uno vigente—. Lo que se guarda es quién publica cada dato y dónde, "
        "que no caduca."
    )
    for evento in macro.PUNTEROS:
        st.markdown(
            f"- {texto.plano(evento.detalle)} — "
            + texto.enlace("ver el calendario", evento.url or "")
        )


def _lo_que_viene(agenda, problemas) -> None:
    """«Lo que viene» de todos los tickers juntos, y los punteros macro."""
    st.subheader("Lo que viene")
    # Agrupados por mensaje y no por ticker, como hacía Noticias: el mismo
    # fallo para quince tickers son quince avisos que no dicen más que uno.
    for problema, afectados in problemas.items():
        st.warning(
            f"**Calendario** — no se pudo traer lo de {', '.join(afectados)}. "
            f"{texto.plano(problema)}"
        )
    proximos = ma.proximos([e for eventos in agenda.values() for e in eventos])
    for evento in proximos:
        st.markdown(
            f"**{texto.plano(evento.ticker)}** — {texto.plano(evento.detalle)}  \n"
            f"{evento.cuando:%d/%m/%Y} · {texto.cuanto_falta(evento.cuando)}"
        )
    if not proximos:
        st.caption(
            "Ninguna fecha próxima para estos tickers. El calendario sólo trae "
            "resultados y dividendos, y no todas las empresas los tienen "
            "publicados: que esto esté vacío no significa que no vaya a pasar nada."
        )
    _macro()


# --- El detalle -------------------------------------------------------------------


def _valor_y_sector(analisis) -> None:
    """El veredicto con sus tres votos, en la moneda del precio, y la tarjeta frente al sector."""
    valoracion = ma.en_moneda_del_precio(analisis.valoracion)
    st.markdown("**Valor intrínseco**, con los supuestos del programa")
    st.markdown(medidores_valoracion.resumen(valoracion), unsafe_allow_html=True)
    if (analisis.valoracion or {}).get("motivo") == "sin_bono_m" and analisis.entradas is not None:
        st.caption(ma.falta_tasa(analisis.entradas) + " Se pone en la pestaña Valoración.")
    pares = ma.detalle_pares(analisis)
    if pares:
        st.caption(pares)
    for nota in medidores_valoracion.pie(valoracion):
        st.caption(nota)
    st.markdown("**Frente a su sector**")
    ref = analisis.referencia
    if ref is None:
        st.caption(
            "Sin ficha frente al sector: "
            f"{ma.etiqueta(ma.MOTIVO_REFERENCIA, analisis.motivo_referencia)}."
        )
        return
    st.markdown(
        medidores.tarjeta_candidato(
            {**ref.ficha, "valoracion": valoracion}, puesto=ma.puesto_en_tarjeta(ref)
        ),
        unsafe_allow_html=True,
    )
    if ref.puesto is not None:
        st.caption(ma.nota_puesto(ref, analisis.ticker))
    exclusion = ma.texto_exclusion(analisis)
    if exclusion:
        st.caption(exclusion)


def _resumen(analisis, contexto) -> None:
    """La pestaña Resumen: quién es, sus avisos, el veredicto con sus votos y la tarjeta."""
    st.markdown(f"#### {texto.plano(analisis.ticker)} · {texto.plano(ma.nombre(analisis))}")
    st.markdown(ma.ficha_de_identidad(analisis))
    fila = ma.fila(analisis, None, contexto["sp500"], contexto["trimestre"], date.today())
    st.caption(f"Precio: {fila['Precio']}, cotización del {fila['Hora del precio']}.")
    for _corto, largo in ma.avisos(analisis, contexto["sp500"], contexto["trimestre"], date.today()):
        st.warning(largo)
    if analisis.clase == "etf":
        st.caption(
            "Un ETF no se valora ni se compara con un sector: aquí están su precio, "
            "su gráfico y sus noticias."
        )
    else:
        _valor_y_sector(analisis)


# Qué función dibuja cada pestaña de `ma.pestanas_de`. Una pestaña sin función
# no se dibuja, en vez de salir vacía.
_PESTANAS = {
    "Resumen": _resumen,
}


def _detalle(analisis, contexto) -> None:
    """El detalle del ticker elegido, en pestañas.

    Un ETF sólo tiene las suyas: las demás no se dibujan, en vez de salir
    vacías. Streamlit ejecuta el contenido de todas las pestañas en cada
    pasada, estén a la vista o no.
    """
    if analisis.clase != "etf":
        # Una vez por pantalla, encima de las pestañas: la regla del registro es
        # glosar la primera vez que algo sale en una pantalla.
        with st.expander(medidores_valoracion.TITULO_GLOSARIO):
            st.markdown(medidores_valoracion.glosario())
    nombres = [n for n in ma.pestanas_de(analisis.clase) if n in _PESTANAS]
    for nombre_, pestana in zip(nombres, st.tabs(nombres, key=f"analizador_pestanas_{analisis.ticker}")):
        with pestana:
            _PESTANAS[nombre_](analisis, contexto)


# --- La pasada --------------------------------------------------------------------

# Antes de dibujar el campo: un encargo de otra pantalla escribe en su clave.
encargo = sesion.recoger(st.session_state)

with st.container(border=True):
    st.text_input(
        f"Tickers, separados por comas o espacios (hasta {MAX_TICKERS})",
        key=sesion.CLAVE_TEXTO,
        placeholder="MU, WALMEX.MX, TSM, JPM, SPY",
        help=(
            "Una empresa de la SEC (MU), una extranjera (TSM), una de la BMV con "
            "su sufijo (WALMEX.MX) o un ETF (SPY). Las clases de acción, con punto "
            "o con guion: BRK.B o BRK-B."
        ),
    )
    izquierda, derecha = st.columns([4, 1], vertical_alignment="top")
    with izquierda.expander("Cargar de un libro"):
        _cargar_de_un_libro()
    pulsado = derecha.button("Analizar", type="primary", width="stretch", icon=":material/search:")

validos, invalidos = separar(st.session_state.get(sesion.CLAVE_TEXTO, ""))
if invalidos:
    st.warning(ma.aviso_invalidos(invalidos))
if len(validos) > MAX_TICKERS:
    st.warning(
        f"Hay {len(validos)} tickers y el tope es {MAX_TICKERS}: cada uno cuesta "
        f"varias consultas a Yahoo y a la SEC. Quita {len(validos) - MAX_TICKERS} "
        "para poder analizar."
    )

panel, fecha_panel = referencia.cargar_panel()
frescura = referencia.frescura()
tabla = load_sectors()
contexto = {
    "panel": panel,
    "fecha_panel": fecha_panel,
    # La tabla congelada del S&P 500: es con la que se hace el panel, y vale
    # también sin él (D2 del plan de N2).
    "sp500": set(tabla),
    "trimestre": None if panel is None else referencia.trimestre_final(panel),
}

if (pulsado or encargo is not None) and validos and len(validos) <= MAX_TICKERS:
    hechos = sesion.preparar(st.session_state, frescura.panel)
    st.session_state[sesion.CLAVE_TICKERS] = validos
    faltan = sesion.pendientes(validos, hechos)
    if faltan:
        _analizar_tickers(faltan, hechos, panel, tabla)

tickers = st.session_state.get(sesion.CLAVE_TICKERS, [])
hechos = st.session_state.get(sesion.CLAVE_ANALISIS, {})
analizados = [hechos[t] for t in tickers if t in hechos]

_panel_de_referencia(panel, fecha_panel, frescura, analizados)

if not analizados:
    st.info(
        "Escribe uno o varios tickers y pulsa **Analizar**. De cada uno salen su "
        "ficha frente a las empresas del S&P 500 de su sector, su valor "
        "intrínseco con los supuestos del programa —que puedes mover—, su gráfico "
        "y sus noticias."
    )
    st.stop()

if sesion.panel_cambiado(st.session_state, frescura.panel):
    st.warning(
        "El panel de referencia cambió desde que se analizaron estos tickers: "
        "pulsa **Analizar** para rehacer sus fichas con el nuevo."
    )

if any(a.motivo == "sin_identidad_edgar" for a in analizados):
    # D14 del plan de N2: el resolver no cambia; se dice una vez y se manda a Perfil.
    st.warning(
        "Falta el correo para EDGAR: sin él la SEC no responde, y las empresas que "
        "presentan en ella se quedan sin clase y sin ficha."
    )
    if st.button("Configurar mis credenciales", key="analizador_credenciales_edgar", icon=":material/key:"):
        st.switch_page("vistas/perfil.py")

agenda, problemas_agenda = _agenda(analizados)

st.subheader("Resumen")
st.dataframe(
    pd.DataFrame(
        [
            ma.fila(a, ma.proximo(agenda.get(a.ticker, [])), contexto["sp500"], contexto["trimestre"], date.today())
            for a in analizados
        ],
        columns=list(ma.COLUMNAS),
    ),
    hide_index=True,
    width="stretch",
)
st.caption(ma.leyenda_resumen())
if st.button(
    "Actualizar precios",
    icon=":material/refresh:",
    help=(
        "Vuelve a pedir la cotización y rehace la valoración con ella; la ficha "
        "frente al sector no depende del precio de hoy y no se rehace. Yahoo se "
        "consulta como mucho cada quince minutos: antes sale el precio guardado, "
        "con su hora. Un ticker que falló se analiza otra vez entero."
    ),
):
    _actualizar_precios([a.ticker for a in analizados], hechos, panel, tabla)
    st.rerun()

_lo_que_viene(agenda, problemas_agenda)

st.divider()
st.subheader("Detalle")
con_detalle = [a.ticker for a in analizados if a.clase is not None]
if not con_detalle:
    st.info("Ninguno de estos tickers tiene detalle: el motivo de cada uno está en su fila.")
    st.stop()
sesion.fijar_elegido(st.session_state, con_detalle)
elegido = st.selectbox(
    "Ticker",
    con_detalle,
    key=sesion.CLAVE_ELEGIDO,
    format_func=lambda t: f"{t} — {ma.nombre(hechos[t])}",
)
_detalle(hechos[elegido], contexto)
```

- [ ] **Step 4: Entrar en el menú, en `app.py`**

En el bloque `"Análisis"`, detrás de Revisar candidatos:

```python
        "Análisis": [
            optimizador,
            st.Page(
                "vistas/candidatos.py", title="Revisar candidatos",
                icon=":material/fact_check:",
            ),
            st.Page(
                "vistas/analizador.py", title="Analizador",
                icon=":material/query_stats:",
            ),
        ],
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: todos pasan.

- [ ] **Step 6: Comprobar que el guion se lee y arranca**

Run: `uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('vistas/analizador.py').read_text(encoding='utf-8')); print('ok')"`
Expected: `ok`.

Arranca la app (`preview_start` con `markowitz-app`, de `.claude/launch.json`), abre «Analizador», escribe `MU SPY ZZZZQ` y pulsa «Analizar». Expected: la barra de progreso; tres filas (MU con su clase y veredicto, SPY como ETF, ZZZZQ con «Yahoo no devolvió datos…»); «Lo que viene» con los punteros macro; el desplegable del detalle con MU y SPY; la pestaña Resumen de cada uno, SPY sin valoración. Para la app con `preview_stop`.

- [ ] **Step 7: Commit**

```bash
git add vistas/analizador.py app.py tests/test_vistas_analizador.py
git commit -m "feat: la pantalla del Analizador, arriba y el resumen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 15: La pantalla, Fundamentales y Gráfico

> **Ejecutada** (9ecda38) el 2026-10-27. Sobre el plan: el gráfico decide con ticker y bolsa (`en_widget`, `enlace` y `avisos` de ec3024c), y en Fundamentales el panel atrasado se dice una vez. Manda el código vivo.

Las pestañas Fundamentales (la ficha de candidatos, con `medidores.py` sin cambios en lo que pinta) y Gráfico (TradingView, con el tema de la app y lo que se dice debajo). «Cómo se leen los medidores» sale del guion de Revisar candidatos a `medidores.como_se_leen()`, y las dos pantallas lo enseñan con las mismas palabras (D16).

**Files:**
- Modify: `medidores.py`
- Modify: `vistas/candidatos.py:42, 268-298`
- Modify: `vistas/analizador.py`
- Test: `tests/test_medidores.py`, `tests/test_vistas_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_medidores.py` (y `from pathlib import Path` a sus importaciones):

```python
def test_como_se_leen_los_medidores_lo_cuentan_las_dos_pantallas_igual():
    from ranking.criterio import TRIMESTRES_VENTANA

    texto = m.como_se_leen()
    assert m.tabla_de_tramos() in texto
    assert f"últimos {TRIMESTRES_VENTANA} trimestres" in texto
    raiz = Path(__file__).resolve().parent.parent
    candidatos = (raiz / "vistas" / "candidatos.py").read_text(encoding="utf-8")
    assert "medidores.como_se_leen()" in candidatos
    assert "tabla_de_tramos()" not in candidatos
```

Al final de `tests/test_vistas_analizador.py`:

```python
def test_el_grafico_sigue_el_tema_de_la_app_y_dice_lo_que_se_sabe():
    cuerpo = _cuerpo("_grafico")
    assert "st.context.theme" in cuerpo
    assert "grafico.html(" in cuerpo and "st.iframe(" in cuerpo
    # La BMV no se ve en el widget: se enlaza a TradingView.
    assert "grafico.en_widget(" in cuerpo and "grafico.enlace(" in cuerpo
    assert "grafico.ESTUDIO_D" in cuerpo and "grafico.avisos(" in cuerpo


def test_la_tarjeta_lleva_el_puesto_global():
    cuerpo = _cuerpo("_valor_y_sector")
    assert "puesto=ma.puesto_en_tarjeta(" in cuerpo and "ma.nota_puesto(" in cuerpo


def test_los_fundamentales_son_los_medidores_de_candidatos():
    cuerpo = _cuerpo("_fundamentales")
    for llamada in (
        "medidores.medidores_pilares(",
        "medidores.medidor_cobertura(",
        "medidores.medidor_kpi(",
        "ma.contra_quien(",
        "ma.texto_exclusion(",
    ):
        assert llamada in cuerpo


def test_como_se_leen_los_medidores_va_una_vez_encima_de_las_pestanas():
    cuerpo = _cuerpo("_detalle")
    assert cuerpo.index("medidores.como_se_leen()") < cuerpo.index("st.tabs(")
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_medidores.py tests/test_vistas_analizador.py -q`
Expected: FAIL con `AttributeError: module 'medidores' has no attribute 'como_se_leen'` y `StopIteration` (no hay `_grafico`).

- [ ] **Step 3: `como_se_leen`, en `medidores.py`**

Cambia `from ranking.criterio import MIN_KPIS_CON_DATO, PILARES, SIGNOS` por `from ranking.criterio import MIN_KPIS_CON_DATO, PILARES, SIGNOS, TRIMESTRES_VENTANA`, y después de `tabla_de_tramos`:

```python
def como_se_leen() -> str:
    """Cómo se leen los medidores, en markdown, para el desplegable de cada pantalla.

    Era una cadena dentro del guion de Revisar candidatos; el Analizador pinta
    los mismos medidores y tiene que explicarlos con las mismas palabras. Es una
    función y no una constante porque lleva números del criterio.
    """
    return f"""
Cada medidor compara a la empresa **con las de su propio sector**, no con todo
el mercado: un margen del 40 % no significa lo mismo en software que en un
supermercado. La unidad es el z-score — cuántas desviaciones típicas se separa
de la media de sus pares — y la barra crece desde la línea central, que es esa
media.

{tabla_de_tramos()}

- **«Regular» no es un defecto**: significa que la empresa está donde está la
  media de su sector en esa área, ni mejor ni peor.
- **El rayado gris no es un cero ni un "regular"**: es que el dato no existe.
  Dos de cada tres bancos pierden el pilar de solidez entero así, porque no
  publican EBITDA ni clasifican su balance en corriente y no corriente. Quedan
  fuera por reportar distinto, no por ser peores.
- **El signo ya viene aplicado.** En `PER`, `EV / EBITDA` o `Deuda neta /
  EBITDA` menos es mejor, así que un múltiplo caro se pinta en rojo aunque su
  z sea positivo. Esos llevan escrito **«menos es mejor»** junto al nombre; los
  demás no lo llevan porque ahí el valor alto y la barra verde ya apuntan al
  mismo sitio.
- **La barra se corta en ±3.** Cuando el valor se sale, una marca blanca lo
  avisa y el número de la derecha, precedido de `›`, sigue siendo el real: en
  este panel hay z de hasta 8,6.
- **Los valores son la media de los últimos {TRIMESTRES_VENTANA} trimestres**
  publicados, así que el ROE y el ROIC son trimestrales, no anuales.
- Un pilar puede apoyarse en 1 KPI o en 7, y no vale lo mismo: el recuento va
  junto a su nombre.
"""
```

- [ ] **Step 4: Revisar candidatos usa `como_se_leen`**

En `vistas/candidatos.py`, el desplegable «📏 Cómo se leen los medidores» pasa a ser:

```python
with st.expander("📏 Cómo se leen los medidores"):
    st.markdown(medidores.como_se_leen())
```

y se quita `from ranking.criterio import TRIMESTRES_VENTANA`, que ya no usa nadie en ese guion (compruébalo: `grep -n TRIMESTRES_VENTANA vistas/candidatos.py` no devuelve nada).

- [ ] **Step 5: Las dos pestañas, en `vistas/analizador.py`**

1. A las importaciones (la primera línea sustituye a `from analizador import referencia, sesion`):

```python
from analizador import grafico, referencia, sesion
from aprobacion.carga import kpis_con_dato
```

El gráfico va con `st.iframe` y no con `streamlit.components.v1.html`, que Streamlit 1.62 da por obsoleto (D23).

2. Antes de `_PESTANAS`:

```python
def _fundamentales(analisis, contexto) -> None:
    """La pestaña Fundamentales: la ficha de candidatos, contra quién y con qué panel."""
    ref = analisis.referencia
    if ref is None:
        st.info(
            "Sin ficha frente al sector: "
            f"{ma.etiqueta(ma.MOTIVO_REFERENCIA, analisis.motivo_referencia)}."
        )
        return
    aviso = ma.aviso_panel_atrasado(analisis, contexto["trimestre"])
    if aviso:
        st.warning(aviso)
    exclusion = ma.texto_exclusion(analisis)
    if exclusion:
        st.warning(exclusion)
    if contexto["panel"] is not None:
        st.caption(
            ma.contra_quien(
                analisis,
                referencia.pares_en_panel(contexto["panel"], analisis.sector),
                contexto["fecha_panel"],
            )
        )
    st.markdown(
        "**Los cuatro pilares** —calidad, crecimiento, valoración y solidez—, "
        "frente a sus pares del sector"
    )
    st.markdown(medidores.medidores_pilares(ref.ficha), unsafe_allow_html=True)
    con_dato = kpis_con_dato(ref.ficha)
    if con_dato is not None:
        st.markdown(medidores.medidor_cobertura(con_dato), unsafe_allow_html=True)
    # «Sus tres más fuertes» y no «Fuerte en»: la lista es relativa a la propia
    # empresa, y sus tres peores KPIs pueden estar en «Regular».
    st.markdown("**Sus tres puntos más fuertes**")
    st.markdown("".join(medidores.medidor_kpi(i) for i in ref.ficha["destacados"]), unsafe_allow_html=True)
    st.markdown("**Sus tres puntos más flojos**")
    st.markdown("".join(medidores.medidor_kpi(i) for i in ref.ficha["flojos"]), unsafe_allow_html=True)


def _grafico(analisis, contexto) -> None:
    """La pestaña Gráfico: TradingView, y lo que se sabe y se dice de él."""
    bolsa = analisis.identidad.bolsa
    simbolo = grafico.simbolo(analisis.ticker, bolsa)
    if grafico.en_widget(bolsa):
        # El tema de la app: la paleta de `tema.py` es oscura, pero el menú de
        # ajustes de Streamlit deja cambiarlo y el gráfico tiene que seguirlo.
        oscuro = (st.context.theme.type or "dark") == "dark"
        st.iframe(grafico.html(simbolo, oscuro), height=grafico.ALTO)
    else:
        # La BMV no se ve en el widget («Símbolo solo disponible en
        # TradingView»): un enlace a su página, en vez de un recuadro vacío.
        st.info(
            "TradingView no enseña los datos de esta bolsa en el gráfico que se "
            "incrusta, sólo en su web."
        )
        st.markdown(
            texto.enlace(texto.plano(f"Ver {simbolo} en TradingView"), grafico.enlace(simbolo))
        )
    st.caption(f"Símbolo en TradingView: {texto.plano(simbolo)}")
    st.info(grafico.ESTUDIO_D)
    for aviso in grafico.avisos(bolsa):
        st.caption(aviso)
```

3. `_PESTANAS` pasa a ser:

```python
_PESTANAS = {
    "Resumen": _resumen,
    "Fundamentales": _fundamentales,
    "Gráfico": _grafico,
}
```

4. En `_detalle`, el bloque de los desplegables pasa a ser:

```python
    if analisis.clase != "etf":
        # Una vez por pantalla, encima de las pestañas: la regla del registro es
        # glosar la primera vez que algo sale en una pantalla.
        with st.expander("📏 Cómo se leen los medidores"):
            st.markdown(medidores.como_se_leen())
        with st.expander(medidores_valoracion.TITULO_GLOSARIO):
            st.markdown(medidores_valoracion.glosario())
```

- [ ] **Step 6: Comprobar que pasan**

Run: `uv run pytest tests/test_medidores.py tests/test_vistas_analizador.py tests/test_noticias_texto.py -q`
Expected: todos pasan.

- [ ] **Step 7: Comprobar en la app**

`preview_start` con `markowitz-app`; en el Analizador, `MU WALMEX.MX`. Expected: en MU, Fundamentales con los cuatro pilares, la cobertura y «Comparada con las otras N empresas del S&P 500 de Information Technology»; en WALMEX.MX, la frase del riesgo país; Gráfico: en MU, el de TradingView (`NASDAQ:MU`) a toda la altura del marco, con el texto del estudio D; en WALMEX.MX, el aviso de que TradingView sólo lo enseña en su web, el enlace a `BMV-WALMEX` y el retraso de la BMV. En Revisar candidatos, el desplegable «Cómo se leen los medidores» dice lo mismo que antes. `preview_stop`.

- [ ] **Step 8: Commit**

```bash
git add medidores.py vistas/candidatos.py vistas/analizador.py tests/test_medidores.py tests/test_vistas_analizador.py
git commit -m "feat: las pestañas Fundamentales y Gráfico del Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: La pantalla, la valoración con sus deslizadores

> **Ejecutada** (9ddfb07) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10, e3fbbc5): el error de un deslizador o de la tasa a mano se pinta con `ma.supuesto_imposible`, sin la clave interna ni el «con esos supuestos» repetido. Manda el código vivo.

Decisión 10. La pestaña Valoración: los supuestos con su deslizador y su procedencia, «Restaurar los del programa», las lecturas con el distintivo «con tus supuestos», la tabla de sensibilidad y la proyección a 10 años plegada. Todo en un `st.fragment`, sin red; cada cuenta en un `try`; sin deslizadores con `error_interno`; lo movido no se guarda. Sin tasa libre (WALMEX sin token de Banxico), una casilla la pide.

**Files:**
- Modify: `vistas/analizador.py`
- Test: `tests/test_vistas_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_vistas_analizador.py`:

```python
# --- Los deslizadores -------------------------------------------------------------


def _nombre_de(funcion) -> "str | None":
    if isinstance(funcion, ast.Name):
        return funcion.id
    if isinstance(funcion, ast.Attribute):
        return funcion.attr
    return None


def test_los_deslizadores_viven_en_un_fragmento():
    assert [ast.unparse(d) for d in _funcion("_deslizadores").decorator_list] == ["st.fragment"]


_CUENTAS = {"valorar", "sensibilidad", "proyeccion", "del_programa", "nombres_movidos"}


def test_cada_cuenta_de_los_deslizadores_va_en_un_try_con_value_error():
    # `aplicar` rechaza con `ValueError` lo que escribe el usuario y rompe las
    # fórmulas: sin el `try`, un deslizador tumbaría la pantalla entera.
    funcion = _funcion("_deslizadores")
    protegidas = set()
    for nodo in ast.walk(funcion):
        if isinstance(nodo, ast.Try) and any(
            h.type is not None and "ValueError" in ast.unparse(h.type) for h in nodo.handlers
        ):
            for interno in nodo.body:
                protegidas |= {id(n) for n in ast.walk(interno) if isinstance(n, ast.Call)}
    cuentas = [
        n for n in ast.walk(funcion) if isinstance(n, ast.Call) and _nombre_de(n.func) in _CUENTAS
    ]
    assert {_nombre_de(n.func) for n in cuentas} == _CUENTAS
    assert all(id(n) in protegidas for n in cuentas)


def test_con_error_interno_no_se_dibujan_los_deslizadores():
    cuerpo = _cuerpo("_valoracion")
    assert cuerpo.index('"error_interno"') < cuerpo.index("_deslizadores(")


def test_lo_movido_no_sale_del_fragmento():
    # Nada de lo calculado con los deslizadores se guarda en la sesión: lo que
    # va al acta es la valoración del programa.
    for nodo in ast.walk(_funcion("_deslizadores")):
        if isinstance(nodo, ast.Assign):
            assert all("session_state" not in ast.unparse(t) for t in nodo.targets)
        if isinstance(nodo, ast.AugAssign):
            assert "session_state" not in ast.unparse(nodo.target)


def test_restaurar_vuelve_a_los_del_programa_y_los_deslizadores_nacen_sin_valor():
    cuerpo = _cuerpo("_deslizadores")
    assert "on_click=sesion.restaurar_deslizadores" in cuerpo
    for deslizador in [n for n in ast.walk(_funcion("_deslizadores")) if _nombre_de(getattr(n, "func", None)) == "slider"]:
        assert "value" not in {k.arg for k in deslizador.keywords}
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: FAIL con `StopIteration` (no hay `_deslizadores` ni `_valoracion`).

- [ ] **Step 3: Implementar en `vistas/analizador.py`**

1. A las importaciones:

```python
from analizador import deslizadores, grafico, referencia, sesion
from analizador.analisis import analizar, con_precio_nuevo, pilar_valoracion
from analizador.valorar import proyeccion, sensibilidad, valorar
```

(las dos primeras sustituyen a sus versiones anteriores).

2. Antes de `_PESTANAS`:

```python
@st.fragment
def _deslizadores(ticker: str) -> None:
    """Los supuestos con sus deslizadores, y lo que sale de ellos.

    En un fragmento: moverlos sólo rehace esto, y sin red, porque `valorar`,
    `sensibilidad` y `proyeccion` son aritmética pura sobre las `Entradas` que
    se guardaron al analizar. Cada cuenta va en un `try`: `aplicar` rechaza con
    `ValueError` lo que rompe las fórmulas, y el mensaje se enseña. **Lo movido
    no se guarda en ningún sitio**: vive en las claves de los widgets.
    """
    analisis = st.session_state[sesion.CLAVE_ANALISIS][ticker]
    entradas = analisis.entradas
    pilar = pilar_valoracion(analisis.referencia)
    r_f_a_mano = None
    if entradas.r_f is None:
        # Sin Bono M (sin token de Banxico, por ejemplo) no hay valoración hasta
        # que el usuario ponga la tasa: el deslizador «pide el dato».
        st.warning(ma.falta_tasa(entradas))
        puesta = st.number_input(
            "Tasa libre de riesgo (%)",
            value=None,
            step=0.1,
            format="%.2f",
            key=sesion.clave_a_mano(ticker),
        )
        r_f_a_mano = None if puesta is None else puesta / 100
    try:
        programa = deslizadores.del_programa(entradas, r_f_a_mano)
    except ValueError as error:
        st.error(f"Esa tasa no se puede usar: {error}.")
        return
    if programa is None:
        st.markdown(
            medidores_valoracion.resumen(ma.en_moneda_del_precio(analisis.valoracion)),
            unsafe_allow_html=True,
        )
        return

    st.button(
        "Restaurar los del programa",
        key=f"analizador_restaurar_{ticker}",
        icon=":material/restart_alt:",
        on_click=sesion.restaurar_deslizadores,
        args=(st.session_state, ticker),
    )
    en_pantalla = {}
    columnas = st.columns(2)
    for indice, (nombre_, valor) in enumerate(programa.items()):
        if nombre_ == "r_f" and entradas.r_f is None:
            continue  # La pidió la casilla de arriba.
        clave = sesion.clave_deslizador(ticker, nombre_)
        with columnas[indice % 2]:
            if valor is None:
                # El programa no tiene la cifra (sin historia, sin años de ROE):
                # se pide en vez de dibujar un deslizador sin punto de partida.
                en_pantalla[nombre_] = st.number_input(
                    f"{ma.etiqueta_deslizador(nombre_)}, sin cifra del programa",
                    value=None,
                    key=clave,
                )
            else:
                rango = deslizadores.rango(nombre_, valor)
                # Nace en la cifra del programa por su clave y sin `value=`: un
                # `value` que cambia entre pasadas reinicia el widget («El
                # formulario que se quedaba en blanco»).
                st.session_state.setdefault(clave, deslizadores.a_pantalla(nombre_, valor))
                en_pantalla[nombre_] = st.slider(
                    ma.etiqueta_deslizador(nombre_),
                    min_value=rango.minimo,
                    max_value=rango.maximo,
                    step=rango.paso,
                    format=rango.formato,
                    key=clave,
                )

    cambios = deslizadores.cambios(en_pantalla, programa, r_f_a_mano)
    try:
        movida = valorar(entradas, pilar, cambios)
        tabla_sensibilidad = sensibilidad(entradas, cambios)
        tabla_proyeccion = proyeccion(entradas, cambios)
        movidos = deslizadores.nombres_movidos(entradas, cambios)
    except ValueError as error:
        st.error(
            f"Con esos supuestos no hay valoración posible: {error}. Muévelos, o "
            "restaura los del programa."
        )
        return

    divisa = entradas.divisa
    if movidos:
        st.caption(
            f"Moviste: {ma.lista_de_supuestos(movidos)}. Lo movido no se guarda en "
            "ningún sitio: lo que va al acta es siempre la valoración con los "
            "supuestos del programa."
        )
    en_precio = ma.en_moneda_del_precio(movida)
    st.markdown(
        medidores_valoracion.resumen(en_precio, con_tus_supuestos=bool(movidos)),
        unsafe_allow_html=True,
    )
    for nota in medidores_valoracion.pie(en_precio):
        st.caption(nota)
    if tabla_sensibilidad is not None:
        st.markdown(
            "**Sensibilidad del valor base** al coste de capital y al crecimiento "
            f"a perpetuidad, en {divisa.moneda_precio} por acción"
        )
        columnas_s, filas_s = ma.tabla_sensibilidad(tabla_sensibilidad, divisa.tipo_precio, divisa.moneda_precio)
        st.dataframe(pd.DataFrame(filas_s, columns=columnas_s), hide_index=True, width="stretch")
    if tabla_proyeccion is not None:
        with st.expander("La proyección a 10 años del escenario base"):
            columnas_p, filas_p = ma.tabla_proyeccion(tabla_proyeccion, divisa.moneda_valoracion)
            st.dataframe(pd.DataFrame(filas_p, columns=columnas_p), hide_index=True, width="stretch")


def _valoracion(analisis, contexto) -> None:
    """La pestaña Valoración: los deslizadores, o la valoración del programa si no se puede mover nada."""
    valoracion = analisis.valoracion if isinstance(analisis.valoracion, dict) else {}
    if analisis.entradas is None or valoracion.get("motivo") == "error_interno":
        # Sin entradas no hay nada que mover; con `error_interno` la cuenta falló
        # por un defecto y volvería a fallar con cada movimiento.
        st.markdown(
            medidores_valoracion.resumen(ma.en_moneda_del_precio(analisis.valoracion)),
            unsafe_allow_html=True,
        )
        if analisis.entradas is not None:
            st.caption(
                "Los deslizadores no se dibujan: la cuenta falló por un defecto del "
                "programa, y volvería a fallar con cada movimiento."
            )
        return
    aviso = ma.aviso_bono_m(analisis.entradas.procedencia_r_f, date.today())
    if aviso:
        st.warning(aviso)
    _deslizadores(analisis.ticker)
```

3. `_PESTANAS` pasa a ser:

```python
_PESTANAS = {
    "Resumen": _resumen,
    "Valoración": _valoracion,
    "Fundamentales": _fundamentales,
    "Gráfico": _grafico,
}
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: todos pasan.

- [ ] **Step 5: Comprobar en la app**

`preview_start`; en el Analizador, `MU JPM WALMEX.MX`. Expected, en la pestaña Valoración:
- **MU**: siete deslizadores (tasa libre, beta, prima, coste de la deuda, impuestos, crecimiento de referencia, crecimiento a perpetuidad). Mover el crecimiento de referencia cambia el valor base sin ninguna espera de red, la píldora dice «· con tus supuestos» y «Moviste: crecimiento de referencia»; «Restaurar los del programa» lo devuelve. Llevar la prima de riesgo a 0 y la tasa libre a 0 enseña el error con su motivo, no una traza. La sensibilidad lleva su «(base)» y la proyección se despliega.
- **JPM**: seis deslizadores (con ROE de referencia y reparto, sin coste de la deuda ni impuestos), sin tabla de sensibilidad ni proyección.
- **WALMEX.MX**: con token de Banxico, la tasa libre del Bono M en la lista de supuestos con la fecha de su subasta; sin token, la casilla que pide la tasa y, al ponerla, la valoración.

`preview_stop`.

- [ ] **Step 6: Commit**

```bash
git add vistas/analizador.py tests/test_vistas_analizador.py
git commit -m "feat: la pestaña Valoración del Analizador, con sus deslizadores

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: La pantalla, noticias y calendario

> **Ejecutada** (485c059) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10): `consultado` desde el problema de la descarga (484c078), y «Actualizar noticias» repinta «Lo que viene» y «Próximo evento» con el aviso del fallo viajando a esa pasada (c11051b). Del recorrido de la Task 21 (7b7095e): con la prensa o el calendario caídos ya no se dice «Sin noticias recientes» ni «Ninguna fecha próxima», y Seguimiento gana `Resumen.prensa_sin_consultar`. Manda el código vivo.

La última pestaña: lo que hacía Noticias, para un ticker. Lo que viene, los 8-K destacados y plegados (sólo los de la SEC; las demás clases dicen por qué no tienen), la prensa con su medio y su formato, y la hora de cada descarga; y, junto a los 8-K, «Interpretar con IA» con el bloque compartido de la Task 13, sobre los seis destacados más recientes, sin cartera y guardado en `analisis/<TICKER>.json`.

**Files:**
- Modify: `vistas/analizador.py`
- Test: `tests/test_vistas_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_vistas_analizador.py`:

```python
# --- Noticias y calendario ------------------------------------------------------


def test_los_8k_se_interpretan_con_el_bloque_compartido_y_sin_cartera():
    cuerpo = _cuerpo("_hechos")
    assert "panel_ia.interpretar_hechos(" in cuerpo
    assert "pesos=()" in cuerpo and "resumen.TOPE_HECHOS" in cuerpo
    assert "archivo_analizador.ruta_de(" in cuerpo


def test_las_fuentes_salen_de_la_clase_y_la_hora_se_ensena():
    cuerpo = _cuerpo("_noticias")
    for llamada in ("ma.fuentes_de(", "ma.sin_hechos(", "ma.linea_de_hora(", "ma.formato_noticia("):
        assert llamada in cuerpo


def test_todas_las_pestanas_tienen_quien_las_dibuje():
    import medidores_analizador as ma

    (asignacion,) = [
        n for n in ast.walk(ARBOL)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "_PESTANAS" for t in n.targets)
    ]
    assert {k.value for k in asignacion.value.keys} == set(ma.PESTANAS)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: FAIL con `StopIteration` (no hay `_hechos`) y el de las pestañas, porque falta «Noticias y calendario».

- [ ] **Step 3: Implementar en `vistas/analizador.py`**

1. A las importaciones (sustituyen a sus versiones anteriores):

```python
from analizador import archivo as archivo_analizador
from noticias import macro, resumen, texto, traer
from vistas import libros, panel_ia
```

2. Antes de `_PESTANAS`:

```python
def _hechos(ticker: str, hechos: list) -> None:
    """Los 8-K de un ticker de la SEC, y su interpretación con IA."""
    st.caption(
        "Formularios 8-K: lo que la empresa está **obligada** a comunicar a la SEC, "
        "con fecha y firma. No es prensa y no se mezcla con ella. Van desplegados "
        "los tipos que pueden mover los números sobre los que se construyó la "
        "tesis; el resto se pliega, pero no se descarta."
    )
    destacados, plegados = ma.repartir_hechos(hechos)
    visibles, fuera = ma.recorte(destacados)
    for hecho in visibles:
        st.markdown(texto.linea_de_hecho(hecho))
    if fuera:
        st.caption(f"Quedan {fuera} hechos destacados sin mostrar, más antiguos que los de arriba.")
    if plegados:
        with st.expander(f"Otros {len(plegados)} expedientes de trámite"):
            st.caption(
                "Ninguno de estos toca los números de la tesis: votaciones, anexos, "
                "cambios de estatutos. Se enseñan igual, porque plegar no es descartar."
            )
            visibles_p, fuera_p = ma.recorte(plegados)
            for hecho in visibles_p:
                st.markdown(texto.linea_de_hecho(hecho))
            if fuera_p:
                st.caption(f"Y {fuera_p} más, más antiguos.")
    if not destacados and plegados:
        # Que no haya nada destacado habiendo trámite es una respuesta: hubo
        # movimiento y nada de lo que importa. Un hueco vacío parece que no se miró.
        st.caption("Sin hechos materiales en el periodo; sólo trámite.")
    elif not hechos:
        st.caption(
            "Ningún 8-K en la ventana consultada. Si arriba hay un aviso de esta "
            "fuente, es que no se pudo preguntar: no es lo mismo que no haya nada."
        )
    st.markdown("**Qué dicen estos 8-K**")
    st.caption(
        f"Se leen los {resumen.TOPE_HECHOS} hechos destacados más recientes, como en "
        "Seguimiento. El modelo no ve nada de tu cartera: ni pesos ni importes."
    )
    panel_ia.interpretar_hechos(
        st,
        tuple(destacados[: resumen.TOPE_HECHOS]),
        archivo_analizador.ruta_de(ticker),
        {ticker},
        pesos=(),
        clave=f"analizador_ia_{ticker}",
        con_enlace_a_perfil=True,
    )


def _noticias(analisis, contexto) -> None:
    """La pestaña Noticias y calendario: lo que hacía la pantalla de Noticias, para un ticker."""
    ticker = analisis.ticker
    fuentes = ma.fuentes_de(analisis.clase)
    izquierda, derecha = st.columns([3, 1], vertical_alignment="center")
    izquierda.caption(
        "Los hechos que la empresa está obligada a presentar van separados de la "
        "prensa, que no lo está. Aquí no se recomienda nada."
    )
    forzar = derecha.button(
        "Actualizar noticias",
        key=f"analizador_noticias_{ticker}",
        icon=":material/refresh:",
        width="stretch",
        help="Vuelve a pedir las fuentes ahora mismo, sin esperar a que caduque lo guardado.",
    )
    recogido, horas = {}, {}
    with st.spinner(f"Consultando las fuentes de {ticker}…"):
        for fuente in fuentes:
            datos, problema, cuando, vigente = traer.traer(fuente, ticker, traer.DESCARGA[fuente], forzar)
            recogido[fuente] = list(datos)
            horas[fuente] = (cuando, vigente)
            if problema:
                st.warning(f"**{ma.ETIQUETA_FUENTE[fuente]}** — no se pudo traer. {texto.plano(problema)}")

    st.markdown("##### Lo que viene")
    proximos = ma.proximos(recogido["agenda"])
    for evento in proximos:
        st.markdown(
            f"**{texto.plano(evento.detalle)}** — {evento.cuando:%d/%m/%Y} · "
            f"{texto.cuanto_falta(evento.cuando)}"
        )
    if not proximos:
        st.caption(
            "Ninguna fecha próxima. El calendario sólo trae resultados y dividendos, "
            "y no todas las empresas los tienen publicados: que esto esté vacío no "
            "significa que no vaya a pasar nada."
        )

    st.markdown("##### Lo que pasó — hechos")
    if "hechos" in fuentes:
        _hechos(ticker, recogido["hechos"])
    else:
        st.caption(ma.sin_hechos(analisis.clase))

    st.markdown("##### Lo que pasó — prensa")
    st.caption(
        "Titulares que otros escribieron. Nadie responde de ellos y el programa no "
        "los filtra: no hay forma defendible de decidir cuál importa. Se enseña el "
        "medio y el formato para que puedas descartarlos tú."
    )
    prensa = sorted(recogido["prensa"], key=lambda n: n.cuando, reverse=True)
    visibles, fuera = ma.recorte(prensa)
    if not visibles:
        st.caption("Sin noticias recientes.")
    for noticia in visibles:
        firma = " · ".join(
            p for p in (texto.plano(noticia.medio), texto.plano(ma.formato_noticia(noticia.clase))) if p
        )
        st.markdown(
            texto.enlace(texto.plano(noticia.titular), noticia.url)
            + f"  \n{firma} · {noticia.cuando.astimezone():%d/%m/%Y %H:%M}"
        )
        if noticia.resumen:
            st.caption(texto.plano(noticia.resumen[:240]))
    if fuera:
        st.caption(f"Quedan {fuera} noticias sin mostrar, más antiguas que las de arriba.")

    st.divider()
    for fuente in fuentes:
        cuando, vigente = horas[fuente]
        st.caption(ma.linea_de_hora(fuente, cuando, vigente))
    st.caption(
        "La hora se enseña siempre, esté el dato fresco o no. Un dato que se lee "
        "como recién traído sin serlo es peor que no tener dato."
    )
```

3. `_PESTANAS` pasa a ser:

```python
_PESTANAS = {
    "Resumen": _resumen,
    "Valoración": _valoracion,
    "Fundamentales": _fundamentales,
    "Gráfico": _grafico,
    "Noticias y calendario": _noticias,
}
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_vistas_analizador.py tests/test_panel_ia.py -q`
Expected: todos pasan, también el del escapado: lo que llega de Yahoo y de la SEC pasa por `texto`.

- [ ] **Step 5: Comprobar en la app**

`preview_start`; en el Analizador, `MU TSM WALMEX.MX SPY`. Expected, en «Noticias y calendario»: MU con lo que viene, sus 8-K destacados y plegados, la prensa y la hora de cada fuente, y el botón «Interpretar estos hechos (N nuevos)» con su coste «como mucho» (**no se pulsa**: gasta saldo del usuario); TSM y WALMEX.MX sin hechos y con su frase; SPY con calendario y prensa. `preview_stop`.

- [ ] **Step 6: Commit**

```bash
git add vistas/analizador.py tests/test_vistas_analizador.py
git commit -m "feat: la pestaña de noticias y calendario del Analizador, con la IA de los 8-K

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: «Analizar a fondo» y «Añadir a la revisión»

> **Ejecutada** (e1e3d03) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10): el motivo sigue a la valoración mientras no se edite (a2839b2), y sin candidatos no se añade a la revisión, y se dice por qué (c11051b). Manda el código vivo.

El gate del spec: desde el Resumen del Analizador, «Añadir a la revisión» mete el ticker, con su motivo ya redactado y editable y con la valoración del programa, en los añadidos de Revisar candidatos, y salta allí; siguen en pie sus reglas. Y desde Revisar candidatos, «Analizar a fondo» manda los candidatos al Analizador (D6).

**Files:**
- Modify: `vistas/analizador.py`
- Modify: `vistas/candidatos.py`
- Test: `tests/test_vistas_analizador.py`

- [ ] **Step 1: Escribir los tests**

Al final de `tests/test_vistas_analizador.py`:

```python
# --- El gate --------------------------------------------------------------------

CANDIDATOS = (RAIZ / "vistas" / "candidatos.py").read_text(encoding="utf-8")


def test_lo_que_va_al_acta_es_la_valoracion_del_programa():
    # Lo movido con los deslizadores no viaja nunca (decisión 4 del plan de N2).
    (llamada,) = [
        n for n in ast.walk(ARBOL) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Anadido"
    ]
    valoracion = next(k for k in llamada.keywords if k.arg == "valoracion")
    assert ast.unparse(valoracion.value) == "analisis.valoracion"


def test_sin_puerta_no_hay_boton_y_las_reglas_son_las_de_candidatos():
    cuerpo = _cuerpo("_a_la_revision")
    assert cuerpo.index("ma.puerta(") < cuerpo.index("st.form(")
    assert "problema_al_anadir(" in cuerpo
    assert 'st.switch_page("vistas/candidatos.py")' in cuerpo


def test_la_revision_usa_la_lista_de_revisar_candidatos():
    assert "st.session_state.anadidos" in CANDIDATOS
    assert 'st.session_state.setdefault("anadidos", [])' in _cuerpo("_a_la_revision")


def test_el_resumen_acaba_en_anadir_a_la_revision():
    assert "_a_la_revision(analisis)" in _cuerpo("_resumen")


def test_candidatos_manda_al_analizador_por_el_canal():
    assert CANDIDATOS.count("sesion.encargar(") == 2
    assert CANDIDATOS.count('st.switch_page("vistas/analizador.py")') == 2
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_vistas_analizador.py -q`
Expected: FAIL con `ValueError: not enough values to unpack` (no hay `Anadido`) y `StopIteration` (no hay `_a_la_revision`).

- [ ] **Step 3: «Añadir a la revisión», en `vistas/analizador.py`**

1. A las importaciones (la de `aprobacion.carga` sustituye a la de la Task 15):

```python
from aprobacion.acta import Anadido, problema_al_anadir
from aprobacion.carga import ContratoRoto, FaltanFichas, cargar_candidatos, kpis_con_dato
```

2. Antes de `_resumen`:

```python
def _a_la_revision(analisis) -> None:
    """«Añadir a la revisión»: el ticker entra en los añadidos de Revisar candidatos.

    Hay un solo gate y una sola acta: el Analizador no aprueba nada, lo lleva a
    Revisar candidatos, donde siguen sus reglas (si ya está en el ranking se
    rechaza, el motivo es obligatorio, y regenerar vacía los añadidos y lo
    avisa).
    """
    st.markdown("**Añadir a la revisión**")
    razon = ma.puerta(analisis)
    if razon:
        st.caption(razon)
        return
    clave = f"analizador_motivo_{analisis.ticker}"
    # Por su clave y sin `value=`, como el campo de tickers: lo que el usuario
    # edite sobrevive a las pasadas.
    st.session_state.setdefault(clave, ma.motivo_para_la_revision(analisis.valoracion, date.today()))
    with st.form(f"analizador_revision_{analisis.ticker}"):
        st.text_area(
            "Motivo: es la única justificación que va a constar en el acta, y lo puedes editar",
            key=clave,
        )
        enviado = st.form_submit_button("Añadir a la revisión", type="primary", icon=":material/fact_check:")
    st.caption(
        "Al acta va la valoración con los supuestos del programa, aunque hayas "
        "movido alguno: así se puede comparar entre actas. Si los moviste, dilo en "
        "el motivo."
    )
    if not enviado:
        return
    try:
        del_ranking = {f["ticker"] for f in cargar_candidatos().fichas}
    except (FaltanFichas, ContratoRoto):
        del_ranking = set()
    # La misma lista que pinta Revisar candidatos (`st.session_state.anadidos`).
    anadidos = st.session_state.setdefault("anadidos", [])
    motivo = st.session_state[clave]
    problema = problema_al_anadir(analisis.ticker, motivo, del_ranking, anadidos)
    if problema:
        st.error(problema)
        return
    # La del programa, y no la de los deslizadores: lo movido no se guarda.
    anadidos.append(Anadido(ticker=analisis.ticker, motivo=motivo, valoracion=analisis.valoracion))
    st.switch_page("vistas/candidatos.py")
```

3. En `_resumen`, después del `if analisis.clase == "etf": … else: _valor_y_sector(analisis)`, al final de la función:

```python
    st.divider()
    _a_la_revision(analisis)
```

- [ ] **Step 4: «Analizar a fondo», en `vistas/candidatos.py`**

1. A las importaciones:

```python
from analizador import sesion
```

2. Después del `st.caption(...)` que dice que el orden «**no está validado empíricamente**», y antes de `st.markdown(medidores.CSS, ...)`:

```python
# «Analizar a fondo»: los candidatos al Analizador, con su gráfico, sus noticias
# y los deslizadores de su valoración. Son quince, exactamente su tope
# (`analizador.resolver.MAX_TICKERS`), y van por el canal de `analizador.sesion`.
if st.button(
    f"Analizar a fondo los {len(candidatos.fichas)} candidatos",
    icon=":material/search:",
    help=(
        "Los lleva al Analizador, con su gráfico, sus noticias y los deslizadores "
        "de su valoración. En frío, quince tardan cerca de un minuto."
    ),
):
    sesion.encargar(st.session_state, [f["ticker"] for f in candidatos.fichas])
    st.switch_page("vistas/analizador.py")
```

3. Dentro del desplegable de cada ficha, justo antes de `motivo = st.text_input("Motivo si lo descartas (opcional)", ...)`:

```python
        if st.button("Analizar a fondo", key=f"a_fondo_{ticker}", icon=":material/search:"):
            # Los quince, con éste elegido en el detalle.
            sesion.encargar(st.session_state, [f["ticker"] for f in candidatos.fichas], ticker)
            st.switch_page("vistas/analizador.py")
```

- [ ] **Step 5: Comprobar que pasan**

Run: `uv run pytest tests/test_vistas_analizador.py tests/test_noticias_texto.py tests/test_aprobacion_acta.py -q`
Expected: todos pasan.

- [ ] **Step 6: Comprobar en la app**

`preview_start`. En Revisar candidatos, «Analizar a fondo» en la ficha del segundo: aterriza en el Analizador con los quince analizándose (cerca de un minuto en frío) y ése elegido. En el Analizador, con `TSM WALMEX.MX`: TSM tiene el formulario con «Analizador, dd/mm/aaaa: …, supuestos del programa.»; WALMEX.MX no tiene botón y dice por qué. «Añadir a la revisión» con TSM salta a Revisar candidatos, donde TSM sale entre los añadidos con «Valor intrínseco al añadirla: …». **No pulses «Aprobar»**: escribe un acta de verdad en `actas/` (lo hace la Task 21, con permiso). Quita TSM de los añadidos. `preview_stop`.

- [ ] **Step 7: Commit**

```bash
git add vistas/analizador.py vistas/candidatos.py tests/test_vistas_analizador.py
git commit -m "feat: analizar a fondo desde candidatos y añadir a la revisión desde el Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 19: El menú: Noticias sale

> **Ejecutada** (3349555) el 2026-10-27. De la revisión de las Tasks 11-19 (2026-11-10): Primeros pasos presenta el Analizador con el análisis, donde lo pone el menú, y Rebalanceo dice que la clave de Anthropic va en Perfil y ajustes (9e4c1d6); los comentarios que aún nombraban Noticias (be29b02).

«Noticias y calendario» sale de «Cartera» y se borra `vistas/noticias.py`: todo lo que hacía está ya en el Analizador (la tabla de la cabecera de este plan). Se repasan los `st.switch_page` que apuntaban a ella (Seguimiento y Primeros pasos), los textos que la nombraban y el README. Un test nuevo comprueba que ningún `switch_page` va a una pantalla que no está en el menú: ese fallo no sale al arrancar, sale al pulsar el botón.

**Files:**
- Delete: `vistas/noticias.py`
- Modify: `app.py:123-130`
- Modify: `vistas/seguimiento.py` (importaciones; los pies de hechos y titulares; «Ver todas las noticias»)
- Modify: `vistas/inicio.py:108-120`
- Modify: `vistas/libros.py:3`, `seguimiento/libro.py:647`, `tests/test_seguimiento_libro.py:853` (comentarios)
- Modify: `../README.md`
- Test: `tests/test_navegacion.py`

- [ ] **Step 1: Escribir los tests**

`tests/test_navegacion.py`:

```python
"""Ninguna pantalla manda a una que no existe.

`st.switch_page` a un fichero que ya no está en el menú de `app.py` no falla al
arrancar: falla al pulsar el botón, delante del usuario. Al borrar «Noticias y
calendario» había dos botones que apuntaban a ella, en Seguimiento y en
Primeros pasos.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _paginas_declaradas() -> "list[str]":
    arbol = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    return [
        n.args[0].value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and ast.unparse(n.func) == "st.Page"
        and n.args
        and isinstance(n.args[0], ast.Constant)
    ]


def _destinos() -> dict:
    salida = {}
    for ruta in [*sorted((RAIZ / "vistas").glob("*.py")), RAIZ / "app.py"]:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if (
                isinstance(n, ast.Call)
                and ast.unparse(n.func).endswith("switch_page")
                and n.args
                and isinstance(n.args[0], ast.Constant)
            ):
                salida.setdefault(n.args[0].value, []).append(ruta.name)
    return salida


def test_cada_switch_page_va_a_una_pantalla_del_menu_que_existe():
    declaradas = set(_paginas_declaradas())
    destinos = _destinos()
    assert destinos, "no se encontró ningún switch_page: el test no está mirando nada"
    for destino, desde in destinos.items():
        assert destino in declaradas, f"{desde} mandan a {destino}, que no está en el menú"
        assert (RAIZ / destino).exists()


def test_noticias_salio_del_menu_y_del_repositorio():
    assert "vistas/noticias.py" not in _paginas_declaradas()
    assert not (RAIZ / "vistas" / "noticias.py").exists()


def test_el_analizador_va_en_analisis_detras_de_revisar_candidatos():
    fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
    analisis = fuente.split('"Análisis":', 1)[1].split('"Cartera":', 1)[0]
    assert analisis.index("vistas/candidatos.py") < analisis.index("vistas/analizador.py")


def test_ningun_texto_de_pantalla_manda_a_noticias():
    # Sobre las cadenas ya unidas por el parser: «la pantalla " "de **Noticias**»
    # va partida en dos literales en la fuente, y buscarla en el texto no la vería.
    for ruta in (RAIZ / "vistas").glob("*.py"):
        textos = [
            n.value for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        assert not any("**Noticias**" in t for t in textos), ruta.name
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_navegacion.py -q`
Expected: FAIL en `test_noticias_salio_del_menu_y_del_repositorio` y en `test_ningun_texto_de_pantalla_manda_a_noticias`.

- [ ] **Step 3: Quitar Noticias del menú y borrarla**

En `app.py`, se quita el `st.Page("vistas/noticias.py", title="Noticias y calendario", icon=":material/newspaper:")` del bloque «Cartera». Después:

Run: `git rm vistas/noticias.py`

- [ ] **Step 4: Seguimiento**

En `vistas/seguimiento.py`:

1. A las importaciones: `from analizador import sesion`.

2. El pie de los hechos que sobran (el que decía «En **Noticias** caben cuarenta») pasa a ser, con su comentario:

```python
                # No dice «están todos en el Analizador» de una vez: allí van
                # activo a activo, cuarenta por pestaña. Lo que sí es verdad es
                # dónde está cada uno.
                st.caption(
                    f"Y {sobran} más, más antiguos. En el **Analizador** están los "
                    "de cada activo, en su pestaña «Noticias y calendario»."
                )
```

3. El de los titulares que sobran:

```python
                st.caption(
                    f"Y {sobran} titulares más. En el **Analizador** van los de cada "
                    "activo, con su medio y su formato."
                )
```

4. El final de la pestaña (el pie «Esto es un resumen…» y el botón «Ver todas las noticias») pasa a ser:

```python
    st.caption(
        "Esto es un resumen. El calendario de resultados y dividendos, los "
        "expedientes de trámite y el resto de la prensa están en el "
        "**Analizador**, activo a activo."
    )
    if st.button("Abrir en el Analizador", icon=":material/query_stats:"):
        # Por el mismo canal que «Analizar a fondo» (`analizador.sesion`). Con
        # más de quince activos, el Analizador rellena el campo y pide quitar
        # alguno antes de analizar.
        sesion.encargar(st.session_state, tickers)
        st.switch_page("vistas/analizador.py")
```

- [ ] **Step 5: Primeros pasos**

En `vistas/inicio.py`, la tarjeta `seis` pasa a ser:

```python
with seis:
    with st.container(border=True):
        st.markdown("#### 6 · Analizador")
        st.markdown(
            "Cualquier acción —esté o no entre los candidatos, de la SEC, "
            "extranjera o de la BMV— con la misma ficha frente a su sector y el "
            "mismo valor intrínseco, con supuestos que puedes mover, un gráfico y "
            "sus noticias.\n\n"
            "«Cargar de un libro» trae lo que tienes y lo que deberías tener. Los "
            "**8-K** —lo que la empresa está obligada a presentar, con fecha y "
            "firma— van separados de los titulares. Aquí no se recomienda nada."
        )
        if st.button("Abrir el analizador", width="stretch",
                     icon=":material/query_stats:"):
            st.switch_page("vistas/analizador.py")
```

- [ ] **Step 6: Los comentarios que nombraban Noticias**

- `vistas/libros.py`, primera línea del docstring: «Seguimiento, Rebalanceo y Noticias empiezan igual» pasa a «Seguimiento, Rebalanceo y el Analizador («Cargar de un libro») empiezan igual».
- `seguimiento/libro.py`, el comentario de `CLAVE_SELECCION`: «Seguimiento, Rebalanceo y Noticias pintan el mismo desplegable» pasa a «Seguimiento, Rebalanceo y el Analizador pintan el mismo desplegable».
- `tests/test_seguimiento_libro.py`, el comentario «Tres pantallas --Seguimiento, Rebalanceo y Noticias--» pasa a «Tres pantallas --Seguimiento, Rebalanceo y el Analizador--».

Los docstrings de `noticias/texto.py` y `noticias/traer.py` dicen que aquello «vivía dentro de `vistas/noticias.py`»: es historia y sigue siendo verdad; no se tocan.

- [ ] **Step 7: El README**

En `../README.md` (la raíz del repo):

1. En «Lo primero que verás», después de «generar candidatos, aprobarlos, y repartir el capital.»:

```markdown
Para mirar a fondo cualquier acción —esté o no entre los candidatos— está el
**Analizador**, en el mismo menú: su ficha frente a su sector, su valor
intrínseco con supuestos que puedes mover, un gráfico y sus noticias. El
gráfico es un widget de TradingView que se carga de su web: TradingView sabe
qué ticker estás mirando, y sin conexión no se ve.
```

2. En la tabla de «Lo que cuesta dinero», la fila «Interpretar las noticias de tu cartera» pasa a «Interpretar los 8-K de tu cartera (Seguimiento) o de una empresa (Analizador)», con las mismas cifras.

3. En «Cómo conseguir el token de Banxico», después de «sale con «—» en vez de romperse.»:

```markdown
Y el Analizador no valora las empresas que presentan sus cuentas en pesos
(WALMEX, por ejemplo) hasta que pongas a mano la tasa libre: el token le da la
del Bono M a 10 años.
```

4. En «Tus posiciones», «Lo mismo vale para `programa/actas/` y `programa/portafolios/`, aunque esos guardan decisiones y pesos, no importes.» pasa a «Lo mismo vale para `programa/actas/`, `programa/portafolios/` y `programa/analisis/` —lo que la IA del Analizador dijo de cada empresa—, aunque esos guardan decisiones, pesos y lecturas, no importes.»

- [ ] **Step 8: Comprobar que pasan**

Run: `uv run pytest tests/test_navegacion.py tests/test_vistas_analizador.py tests/test_panel_ia.py -q`
Expected: todos pasan. Y `grep -rn "vistas/noticias.py" --include=*.py . | grep -v .venv` sólo devuelve docstrings y comentarios que cuentan la historia (`noticias/texto.py`, `noticias/traer.py`, algún test) y `tests/test_navegacion.py`: ni un `st.Page` ni un `switch_page`.

- [ ] **Step 9: Commit**

```bash
git add app.py vistas/seguimiento.py vistas/inicio.py vistas/libros.py seguimiento/libro.py tests/test_seguimiento_libro.py tests/test_navegacion.py ../README.md
git commit -m "feat: Noticias y calendario sale del menú; lo que hacía está en el Analizador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`git rm` ya dejó el borrado de `vistas/noticias.py` en el índice.)

---

### Task 20: Sabotaje de las guardas

> **Ejecutada** el 2026-11-12, sin commit: ninguna guarda estaba sin test. 58 filas —las 35 de abajo y 23 con las guardas de la revisión de las Tasks 11-19—, y las 58 tumban al menos un test. La 17 no tumba el test que nombra la tabla: lo ve `test_el_redondeo_de_ida_y_vuelta_no_cuenta_como_movido`. La tabla con su resultado está en CONTEXTO.

El punto 10 de «Cómo se prueba», con el formato de la Task 16 de N1. Antes de cada sabotaje se copia el fichero fuera del repo (al scratchpad); se aplica el cambio, se corre el fichero de tests indicado, se comprueba que **falla** el test de la tabla, y se restaura copiando la copia de vuelta. No se commitea nada. Si un sabotaje no tumba ningún test, el trabajo no es repetirlo: es averiguar qué otra cosa está devolviendo la respuesta correcta y escribir el test que falta (ése sí se commitea). Un sabotaje inerte es una pregunta.

| # | Sabotaje | Test que debe caer |
|---|---|---|
| 1 | En `ma.en_moneda_del_precio`, deja el precio sin dividir (`"precio": valoracion.get("precio")`) | `test_los_valores_se_ensenan_en_la_moneda_del_precio` |
| 2 | En `ma.en_moneda_del_precio`, escribe en `valoracion` en vez de en una copia | `test_los_valores_se_ensenan_en_la_moneda_del_precio` (lo guardado no se toca) |
| 3 | En `ma.puerta`, quita la comparación con `"USD"` (devuelve None salvo a un ETF) | `test_lo_que_cotiza_en_pesos_no_y_se_explica` |
| 4 | En `ma.aviso_sin_prima_pais`, quita `or analisis.fuente_sector == "sp500"` | `test_sin_prima_pais_solo_fuera_del_sp500` |
| 5 | En `ma.aviso_misma_empresa`, acepta cualquier sufijo (`base = ticker.rpartition(".")[0]`) | `test_la_misma_empresa_solo_en_el_sic_de_la_bmv` |
| 6 | En `ma.aviso_bono_m`, compara con 0 días en vez de con `SEPARACION_MAXIMA_SUBASTAS` | `test_el_bono_m_viejo_se_avisa_y_el_reciente_no` |
| 7 | En `ma.texto_exclusion`, quita la rama de `filas_posteriores` | `test_historia_corta_con_el_panel_atrasado_culpa_al_panel` |
| 8 | En `ma.detalle_pares`, quita la rama del pilar de valoración vacío | `test_brk_b_no_vota_por_sus_multiplos_y_no_por_falta_de_pares` |
| 9 | En `ma.fila`, el valor base sale de `analisis.valoracion` sin pasar por `en_moneda_del_precio` | `test_el_valor_de_la_fila_va_en_la_moneda_del_precio` |
| 10 | En `ma.motivo_de_la_valoracion`, quita la rama del Bono M | `test_una_fallida_por_el_bono_m_dice_el_motivo_concreto` |
| 11 | En `referencia.frente_al_sector`, `posteriores = 0` siempre | `test_las_filas_posteriores_al_panel_se_cuentan` |
| 12 | En `Frescura.panel_posterior`, compara con `timedelta(0)` | `test_un_panel_escrito_con_sus_candidatos_no_es_posterior` |
| 13 | En `referencia.construir_panel`, escribe directamente en `ruta` (sin temporal ni `os.replace`) | `test_un_corte_al_escribir_deja_el_panel_de_antes_y_ningun_temporal` |
| 14 | En `referencia.construir_panel`, llama a `ranking.run.guardar(resultado, ruta.parent)` en vez de escribir el panel | `test_construir_el_panel_solo_escribe_el_panel` |
| 15 | En `analisis._analizar`, quita el `try` de `_frente_al_sector` | `test_un_defecto_en_la_ficha_no_se_lleva_la_identidad_ni_la_valoracion` |
| 16 | En `analisis.con_precio_nuevo`, devuelve siempre `analizar(...)` | `test_actualizar_el_precio_no_rehace_la_ficha_frente_al_sector` |
| 17 | En `deslizadores.cambios`, compara con `!=` en vez de `math.isclose` | `test_un_deslizador_sin_tocar_no_cuenta_como_movido` |
| 18 | En `deslizadores.rango`, no ensancha el recorrido | `test_el_recorrido_se_ensancha_para_que_quepa_la_cifra_del_programa` |
| 19 | En `deslizadores.movibles`, devuelve `_SUPUESTOS_DE[metodo_]` entero | `test_lo_derivado_nunca_tiene_deslizador` |
| 20 | En `dcf.proyeccion`, descuenta con `(1 + wacc) ** (ano - 1)` | `test_dos_etapas_contra_un_valor_presente_escrito_a_mano` y `test_la_proyeccion_son_diez_anos_con_los_crecimientos_del_dcf` |
| 21 | En `grafico.simbolo`, no quita el sufijo de bolsa | `test_el_simbolo_de_tradingview[WALMEX.MX-MEX-BMV:WALMEX]` |
| 22 | En `grafico.html`, quita el `.replace("</", "<\\/")` | `test_nada_del_simbolo_puede_cerrar_la_etiqueta_del_script` |
| 23 | En `sesion.recoger`, `estado.get(CANAL)` en vez de `pop` | `test_un_encargo_se_consume_al_usarlo` |
| 24 | En `sesion.preparar`, no vacía la caché al cambiar el panel | `test_los_analisis_valen_mientras_no_cambie_el_panel` |
| 25 | En `sesion.pendientes`, sólo los que faltan (quita la condición de la clase) | `test_se_analiza_lo_que_falta_y_lo_que_fallo_en_su_orden` |
| 26 | En `sesion.restaurar_deslizadores`, borra también la tasa puesta a mano | `test_restaurar_borra_lo_movido_y_deja_la_tasa_puesta_a_mano` |
| 27 | En `acta.construir_acta`, no escribe `"valoracion"` en los manuales | `test_el_anadido_desde_el_analizador_llega_al_acta_con_su_valoracion` |
| 28 | En `acta.problema_al_anadir`, quita la comprobación del ranking | `test_problema_al_anadir_dice_lo_mismo_que_dira_el_acta` |
| 29 | En `acta.valoracion_de_entrada`, `entrada["valoracion"]` en vez de `.get` | `test_un_acta_vieja_sin_valoracion_en_sus_anadidos_se_sigue_leyendo` |
| 30 | En `posiciones.tickers_a_mirar`, sin los del objetivo | `test_los_tickers_de_un_libro_son_lo_que_tiene_mas_lo_que_deberia_tener` |
| 31 | En `vistas/analizador.py`, `_a_la_revision` añade `valoracion=None` | `test_lo_que_va_al_acta_es_la_valoracion_del_programa` |
| 32 | En `vistas/analizador.py`, saca `sensibilidad(entradas, cambios)` del `try` | `test_cada_cuenta_de_los_deslizadores_va_en_un_try_con_value_error` |
| 33 | En `vistas/analizador.py`, `_resumen` pinta `ma.nombre(analisis)` sin `texto.plano` | `test_lo_que_no_escribio_el_programa_se_escapa_antes_de_pintarlo` |
| 34 | En `vistas/panel_ia.py`, `interpretar_hechos` desempaqueta lo de `preparar` en `leidas` | `test_tras_un_fallo_lo_guardado_se_sigue_pintando` |
| 35 | En `vistas/seguimiento.py`, el botón vuelve a `st.switch_page("vistas/noticias.py")` | `test_cada_switch_page_va_a_una_pantalla_del_menu_que_existe` |

- [ ] **Step 1: Aplicar cada sabotaje, correr su test y deshacerlo**

Para cada fila: copia el fichero al scratchpad, aplica el cambio, corre `uv run pytest <fichero del test> -q`, anota qué cae, y copia el original de vuelta.

- [ ] **Step 2: Comprobar que todo quedó como estaba**

Run: `git status --short`
Expected: vacío, salvo un test nuevo commiteado si algún sabotaje no tumbó nada.

Run: `uv run pytest tests/ -q -m "not red"`
Expected: el mismo total que antes de empezar la tarea.

---

### Task 21: Suite completa y recorrido con la app arrancada

> **Ejecutada** el 2026-11-12 con MU, WALMEX.MX, TSM, JPM y SPY, más «Cargar de un libro» y «Analizar a fondo» (SNDK). No se pulsó la IA ni «Aprobar»: no se escribió ningún acta. Salieron tres defectos, arreglados con test: el `$` del coste (a88e486), el detalle que volvía al primero (98ab58c) y «Sin noticias recientes» con Yahoo caído (7b7095e). El recorrido entero está en CONTEXTO.

El punto 12 de «Cómo se prueba». Con el navegador integrado (`preview_start` con `markowitz-app`, de `.claude/launch.json` en la raíz del repo) y los tickers MU, WALMEX.MX, TSM, JPM y SPY.

**Dos reglas que no se saltan:**
- **Los botones de IA gastan saldo del usuario.** «Interpretar estos hechos» no se pulsa sin su permiso, pedido en el chat y con la cifra «como mucho» que enseña el botón.
- **«Aprobar N empresas» escribe un acta de verdad en `actas/`**, que es el registro del usuario y no se borra desde la app (D15). Se le pide permiso antes de pulsarlo; si no lo da, el recorrido llega hasta los añadidos de Revisar candidatos y la comprobación del acta se hace con los tests de la Task 12.

Nada se escribe en `salidas/` salvo lo que haga la app por su cuenta al construir el panel, y eso sólo si no hay panel.

- [ ] **Step 1: La suite entera**

Run: `uv run pytest tests/ -q -m "not red"`
Expected: todo verde. El total es el de antes del plan (3166 pasando, 5 omitidos) más los tests nuevos. Si algo que no es del Analizador falla, es una regresión de este trabajo: se arregla antes de seguir. N2 no añade tests `red`.

- [ ] **Step 2: Lo que hay en disco antes de empezar**

Run: `ls -l --time-style=full-iso salidas/ actas/ 2>/dev/null; ls analisis/ 2>/dev/null`
Expected: se anota, para compararlo al final.

- [ ] **Step 3: Arrancar y recorrer el Analizador**

`preview_start` con `markowitz-app`. En el menú, «Análisis» tiene Optimizador, Revisar candidatos y **Analizador**; «Cartera» ya no tiene «Noticias y calendario».

En el Analizador, `MU WALMEX.MX TSM JPM SPY` y «Analizar». Expected:
- La barra de progreso, y cinco filas, cada una con su nombre largo y la hora del precio.
- Si no hay panel, el aviso y «Construir el panel». Si se pulsa: unos dos minutos, y al terminar se rehacen las fichas; en `salidas/` cambia **sólo** `panel.parquet` (las horas de `fichas.json`, `corrida.json`, `ranking.csv` e `informe.md` siguen como en el paso 2).
- **MU**: SEC (10-K), en su sector con «N de 423» (o su exclusión), veredicto y valor base en dólares. Valoración: siete deslizadores, sensibilidad y proyección; mover uno cambia el valor al instante, sin red, con «· con tus supuestos»; «Restaurar los del programa» lo deshace. Fundamentales: los cuatro pilares y «Comparada con las otras N empresas…». Gráfico: `NASDAQ:MU`, el texto del estudio D. Noticias: lo que viene, sus 8-K, la prensa, la hora de cada fuente y el botón de interpretar con su coste (**no se pulsa sin permiso**).
- **WALMEX.MX**: Fuera de la SEC, en pesos; con token de Banxico, la tasa libre del Bono M con la fecha de la subasta (y el aviso si pasa de 56 días); sin token, la casilla que pide la tasa. Fundamentales con la frase del riesgo país; Gráfico: el aviso de que TradingView sólo lo enseña en su web, el enlace a su página y el retraso de la BMV (D22); Noticias sin hechos y con su frase. En Resumen, en vez del botón, por qué no puede ir a la revisión.
- **TSM**: SEC, extranjera; estados en TWD convertidos a USD; «de 424» con la nota de que se cuenta a sí misma; el aviso de «sin prima por riesgo país» (Taiwan); sin hechos (presenta 20-F).
- **JPM**: SEC; la exclusión de las guardas («sin datos para algún pilar entero») y, en el voto de pares, que vota aunque la guarda la dejaría fuera; Valoración por beneficio residual, sin sensibilidad ni proyección.
- **SPY**: ETF; sólo Resumen, Gráfico (`AMEX:SPY`) y Noticias y calendario; sin valoración ni botón de revisión, con la frase de añadirlo a mano.
- «Lo que viene» bajo el resumen con las fechas de todos y los punteros macro.
- «Actualizar precios» rehace las filas sin volver a calcular las fichas (rápido) y la hora del precio sólo cambia si han pasado quince minutos.

Anota en el informe la fila de cada ticker y lo que llamó la atención.

- [ ] **Step 4: «Cargar de un libro»**

Abre «Cargar de un libro». Con algún libro en `libros/`: elige uno, «Cargar en el campo», y el campo se rellena con sus tickers (lo que tiene más lo del objetivo), sin pesos ni importes; si son más de quince, el aviso de cuántos sobran. Sin libros: «Todavía no llevas ningún libro». No hace falta analizar.

- [ ] **Step 5: «Analizar a fondo»**

En Revisar candidatos, «Analizar a fondo» dentro de la ficha de un candidato: aterriza en el Analizador con los quince analizándose y ése elegido en el detalle; su ficha coincide con la de candidatos salvo el puesto, que es el global (y, si el panel es más nuevo que los candidatos, el aviso de que puede diferir).

- [ ] **Step 6: «Añadir a la revisión» hasta el acta**

En el Analizador, con un ticker que esté en el ranking (el primero de los candidatos), «Añadir a la revisión» se rechaza con «ya está en el ranking: apruébalo con su casilla». Con TSM: el motivo ya redactado («Analizador, dd/mm/aaaa: …, supuestos del programa.»), editable; al añadir, salta a Revisar candidatos y TSM sale entre los añadidos con su valor intrínseco.

**Pide permiso al usuario** para pulsar «Aprobar 1 empresas y pasar al optimizador». Con su permiso: se escribe el acta y se salta al optimizador con TSM; en «Actas de aprobación», el acta nueva tiene TSM con su «Valor intrínseco»; abre el fichero (`actas/<fecha>.json`) y comprueba que `aprobados[0]["valoracion"]` lleva `moneda`, `divisa` y `version`. Anota el nombre del fichero en el informe. Sin permiso, quita TSM de los añadidos y sigue.

- [ ] **Step 7: El resto de la app**

- Seguimiento, pestaña Noticias: el botón «Abrir en el Analizador» lleva los tickers del libro; el bloque de interpretar sigue ahí con su coste (sin pulsar).
- Perfil y ajustes, «Dónde vive todo»: la fila de `analisis/` y las cachés.
- Primeros pasos: la tarjeta «6 · Analizador» abre el Analizador.

- [ ] **Step 8: Lo que hay en disco al terminar**

Run: `ls -l --time-style=full-iso salidas/ actas/ 2>/dev/null; git status --short`
Expected: en `salidas/`, como mucho `panel.parquet` cambiado; en `actas/`, como mucho el acta que el usuario permitió; `git status` limpio (cachés y datos están en `.gitignore`).

`preview_stop`.

- [ ] **Step 9: Si algo salió distinto**

Un ticker o una pantalla que no sale como se esperaba **no se arregla aquí**: se anota, se mira por qué y, si es un defecto, se arregla con su test (y su commit) antes de la Task 22.

---

### Task 22: El spec, CONTEXTO.md y las notas de cada tarea

> **Ejecutada** el 2026-11-12, en el commit que la acompaña.

**Files:**
- Modify: `docs/superpowers/specs/2026-10-12-analizador-individual-design.md`
- Modify: `CONTEXTO.md`
- Modify: `docs/superpowers/plans/2026-10-26-analizador-n2-pantalla.md` (este plan)

- [ ] **Step 1: Enmiendas al spec**

1. **Estado**, en la cabecera:

```
**Estado:** N1 (los datos) y N2 (la pantalla) implementados en la rama
`feat/analizador-individual`; N3 (la IA) pendiente
```

2. Al final del spec, una sección nueva:

```markdown
## Enmiendas del 2026-10-26, al planear y ejecutar N2

El plan es `docs/superpowers/plans/2026-10-26-analizador-n2-pantalla.md`. Lo
que cambia de lo de arriba:
```

seguida de estos puntos, uno por párrafo, con sus porqués tal como están en la cabecera del plan:

- **El panel se construye aparte** (`referencia.construir_panel`), sin tocar los candidatos: «Si el panel no existe, la pestaña Fundamentales ofrece construirlo gratis: la misma corrida que Generar gratis» pasa a ser un botón del Analizador que sólo escribe `panel.parquet`. La pantalla enseña las dos fechas y avisa si el panel es más nuevo que los candidatos (por la hora de los ficheros, con un minuto de holgura) o si se quedó atrás de los trimestres de algún ticker (`Referencia.filas_posteriores`).
- **Los valores se enseñan en la moneda del precio** (`valor / divisa.tipo_precio`); lo que va al acta, en la de la valoración, con `moneda` y `divisa`.
- **`sin_prima_pais` sólo se avisa fuera del S&P 500**, que es la tabla congelada de sectores y no el panel.
- **«La misma empresa» sólo con `.MX`** (el SIC de la BMV): T.TO es TELUS y T es AT&T.
- **Las preferentes se avisan** por su forma (`-P` y la serie) y no se bloquean.
- **El Bono M avisa pasados 56 días** (`divisas.SEPARACION_MAXIMA_SUBASTAS`).
- **El resumen** lleva además «Nombre», «Hora del precio» y «Avisos», y **el detalle se elige con un desplegable**, no pulsando la fila.
- **Un ETF no va a la revisión** desde el Analizador.
- **«Analizar a fondo»** manda los quince candidatos y deja elegido el de la ficha.
- **«Actualizar precios»** respeta la caché de quince minutos de `mercado`.
- **«Interpretar con IA» junto a los 8-K** es el bloque de Seguimiento, compartido (`vistas/panel_ia.interpretar_hechos`), sobre los seis destacados más recientes, con `pesos=()`, guardado en `analisis/<TICKER>.json` con el formato de `interprete/archivo.py`. Sin confirmación adicional, como en Seguimiento: N3 la añade a los cuatro bloques. `interprete.archivo.anotar_hechos` reescribe el fichero sólo con `hechos` y `rebalanceo`: N3 tiene que cambiar cómo se escribe antes de guardar otras claves ahí.
- **«Noticias y calendario» salió del menú.** Su lista conjunta de 8-K de un libro pasa a ser ticker a ticker en el Analizador; el resumen conjunto sigue en la pestaña Noticias de Seguimiento.
- **El gráfico no deja cambiar de símbolo**, y se incrusta con `st.iframe` a toda la altura del marco (`html,body{height:100%}`: con `autosize`, TradingView reescribe el contenedor y sin eso salía de 150 píxeles).
- **La BMV no se ve en el widget de TradingView** («Símbolo solo disponible en TradingView», con `BMV:WALMEX`): para esas bolsas, un enlace a la página del símbolo en vez del gráfico (`grafico.SOLO_EN_TRADINGVIEW`).
- **«Errores»**: la fila de un ticker que Yahoo no conoce dice «Yahoo no devolvió datos (sin conexión o un símbolo que no conoce)», como ya anunciaba la enmienda del 2026-10-14.

Más lo que salga al ejecutar el plan, cada punto con su cifra o su caso.

- [ ] **Step 2: CONTEXTO.md**

1. En «Descomposición en sub-proyectos», la fila de N:

```markdown
| N | Analizador individual | La mecánica de candidatos para cualquier ticker, con gráfico, noticias e IA | 🔨 **en curso**: N1 (datos) y N2 (pantalla) hechos; N3 (IA) pendiente |
```

2. Después de «Sub-proyecto N, parte 1», una sección `## Sub-proyecto N, parte 2: la pantalla` con:
   - **Qué entrega**: `vistas/analizador.py` (el resumen, «Lo que viene», las cinco pestañas, los deslizadores en un fragmento, el gráfico de TradingView, «Cargar de un libro», «Añadir a la revisión»), `medidores_analizador.py`, `analizador/sesion.py`, `deslizadores.py`, `grafico.py`, `archivo.py`; `referencia.construir_panel` y `frescura`; `analisis.con_precio_nuevo`; `dcf.proyeccion`; `Anadido.valoracion` en el acta; `panel_ia.interpretar_hechos` compartido con Seguimiento; Noticias fuera del menú.
   - **Decisiones que no hay que relitigar**: las doce del usuario y las D1–D21 de la cabecera de este plan, en una línea cada una.
   - **Defectos encontrados**: los que salgan al ejecutar este plan, en una tabla «Defecto | Cómo se detectó», empezando por el que se vio al planear: tras una lectura de 8-K fallida, Seguimiento no pintaba lo ya guardado (`_leidas` reasignado; Task 13).
   - **El recorrido de la Task 21**: la línea de cada ticker, y si se escribió un acta, cuál.
   - **Lo que queda para N3**: la pestaña IA con sus tres bloques y su confirmación; añadir la confirmación también a los 8-K; `anotar_hechos` y las claves nuevas de `analisis/<TICKER>.json`; con `pesos=()` el prompt de `interprete/noticias.py` dice «sólo puedes nombrar los activos de la cartera de abajo» con la cartera vacía: mirar cómo lee el modelo eso con un ticker suelto.
   - **Lo que N2 no resuelve**: el gráfico de una bolsa fuera de la tabla va sin prefijo y TradingView puede resolverlo a otra cotización (SHEL.L puede salir como la ADR de Nueva York); la BMV sólo se ve en la web de TradingView, y otras bolsas pueden estar igual sin que se sepa hasta mirarlas; el precio de la fila (la identidad) y el de la valoración (el perfil) salen de dos `.info` con cachés de quince minutos separadas y pueden diferir unos céntimos (MU, 910,74 y 910,83 el 2026-10-26); el mensaje de un supuesto imposible lleva la clave interna de `supuestos.exigir_costes_positivos` («k_e: con esos supuestos…»); `analizar_varios` sigue sin uso en pantalla.

3. La cabecera: «Última actualización», el número de tests, la rama, y el bloque «Al retomar» (N1 y N2 en `feat/analizador-individual`, sin fusionar; lo siguiente es el plan de N3).

4. En «Comandos», el número de tests de la primera línea.

- [ ] **Step 3: Las notas «Ejecutada» de este plan**

Debajo del título de cada tarea de este plan, una nota como las de N1: `> **Ejecutada** (<sha>, …) el <fecha>: …`, con lo que encontró su revisión y lo que cambió respecto del plan. «Manda el código vivo» cuando difieran.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-10-12-analizador-individual-design.md CONTEXTO.md docs/superpowers/plans/2026-10-26-analizador-n2-pantalla.md
git commit -m "docs: N2 hecho, con sus enmiendas al spec y CONTEXTO al día

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cobertura del spec

| Sección del spec (con sus enmiendas) | Dónde |
|---|---|
| La pantalla, arriba: el campo hasta `MAX_TICKERS`, «Cargar de un libro» (sólo tickers), «Analizar», tickers en `st.session_state` | Tasks 10, 14 |
| El resumen: la tabla, «Lo que viene» y los punteros macro; el precio que no se refresca solo con su hora y «Actualizar precios»; un ticker que falla sólo en su fila | Tasks 9, 11, 14 |
| Las pestañas: Resumen, Valoración, Fundamentales, Gráfico, Noticias y calendario; un ETF sólo con tres; `sin_sec` con todas y diciendo lo que le falta | Tasks 11, 14–17 |
| Los deslizadores: `st.fragment`, `aplicar`, `sensibilidad`, «Restaurar», «con tus supuestos», lo movido no se guarda | Tasks 5, 6, 7, 16 |
| La proyección a 10 años plegada, el beneficio residual, la nota de «criterio transparente» | Tasks 6, 16 (`medidores_valoracion.pie`) |
| El gráfico: Advanced Chart, tabla de bolsas, el símbolo, el tema, el texto del estudio D, lo que se sabe y se dice | Tasks 8, 15 |
| El menú: Analizador en «Análisis» tras Revisar candidatos; Noticias fuera; `switch_page`, Primeros pasos, README | Tasks 14, 19 |
| El gate: `Anadido.valoracion`, actas viejas, reglas de candidatos, sólo dólares, motivo redactado y editable | Tasks 12, 18 |
| «Analizar a fondo» | Task 18 |
| Cachés y frescura: la hora de cada dato | Tasks 11 (`linea_de_hora`, `hora_del_precio`), 14 (fechas del panel) |
| Errores: Yahoo sin datos, tipo no soportado, red, sin panel, sin token de Banxico, sin clave de Anthropic (bloque de 8-K), `sin_sec`, sin conexión (gráfico) | Tasks 1, 7, 8, 13, 14, 16, 17 |
| La referencia sectorial: la fecha del panel siempre; construirlo si no existe; no-EE. UU. y riesgo país | Tasks 2, 3, 11, 14, 15 |
| Cómo se prueba, punto 9 (el gate) | Task 12 (tests) y Task 21 (recorrido) |
| Cómo se prueba, punto 10 (sabotajes) | Task 20 |
| Cómo se prueba, punto 12 (recorrido con la app) | Task 21 |
| La IA (los tres bloques nuevos y su archivo), la pestaña IA | **N3** |
| Lo que N no resuelve | Se dice en pantalla donde toca (dólares en el gate, pares de EE. UU., TradingView) y en CONTEXTO (Task 22) |

## Autorrevisión del plan (2026-10-26)

Hecha al terminar de escribirlo, contra el spec, las notas de N1 y el código vivo.

**Cobertura.** Cada sección del spec que toca a N2 tiene su tarea (tabla de arriba); cada nota «Para N2» y de la revisión final de N1 tiene su sitio (tabla de la cabecera). Lo que el spec deja a N3 —la pestaña IA, sus tres bloques nuevos, su confirmación y el resto de `analizador/archivo.py`— queda fuera a propósito, y el aviso sobre `anotar_hechos` va en el docstring de `analizador/archivo.py`, en la D7 y en la Task 22.

**Nombres contra el código vivo.** Comprobados antes de escribirlos: `analizar(ticker, panel, tabla_sectores=None)`, `Analisis` y sus diez campos, `Referencia` y sus seis (más el que añade la Task 2), `cargar_panel(ruta=None)`, `RUTA_PANEL`, `frente_al_sector(ticker, panel, sector=None, propias=None)`, `Entradas` (`r_f`, `procedencia_r_f`, `motivo_r_f`, `divisa`, `cociente_adr`…), `valorar(entradas, pilar_valoracion, cambios=None, hoy=None)`, `supuestos_de(entradas, cambios=None)`, `sensibilidad(entradas, cambios=None)`, `Divisa.a_dict()` y su `tipo_precio`, `divisas.adr_dudosa`, `supuestos.MOVIBLES`, `aplicar`, `movidos`, `exigir_costes_positivos`, `dcf.Sensibilidad(waccs, gs, valores)`, `motor.puente` y `datos_dcf`, `MAX_TICKERS`, `separar`, `normalizar`, `tiene_sufijo`, `Identidad` y sus once campos, `mercado.VALIDEZ`, `construir_ranking(..., con_llm, ..., con_valoracion)`, `aprobacion.carga.MOTIVOS_EN_CASTELLANO`, `SALIDAS`, `valoracion_de`, `kpis_con_dato`, `acta.Anadido`, `construir_acta`, `normalizar`, `listar_actas`, `tickers_aprobados`, `generacion.disponibilidad()` y `motivo_generacion`, `medidores.tarjeta_candidato`, `tabla_de_tramos`, `medidores_valoracion.resumen`, `distintivo`, `pie`, `glosario`, `etiqueta_motivo`, `VEREDICTO`, y los privados `_dinero`, `_pct`, `_numero`, `_NOMBRE_SUPUESTO`, `_SUPUESTOS_DE`; `interprete.archivo` (`cargar`, `anotar_hechos`, `urls_leidas`, `Archivo`, `Anotada`), `interprete.noticias.leer` y su firma, `vistas/panel_ia` (`preparar`, `anotadas`, `avisos`, `pintar_lectura`, `pintar_archivo`, `coste_peor_caso`, `coste_estimado`), `noticias.traer.traer`, `DESCARGA`, `cache.VALIDEZ`, `texto.plano`, `enlace`, `hace`, `cada`, `linea_de_hecho`, `macro.PUNTEROS`, `resumen.TOPE_HECHOS`, `posiciones.estado`, `libro.pesos_objetivo`, `libros.disponibles`, `desplegable`, y Streamlit 1.62 con `st.fragment`, `st.context.theme` y `st.tabs(key=)`.

**Coherencia entre tareas.** Lo que define una tarea y usa otra lleva el mismo nombre y la misma firma: `ma.fila(analisis, proximo_evento, sp500, trimestre_panel, hoy)`, `ma.avisos(analisis, sp500, trimestre_panel, hoy)`, `ma.contra_quien(analisis, pares_del_sector, fecha_panel)`, `deslizadores.cambios(en_pantalla, programa, r_f_a_mano=None)`, `sesion.encargar(estado, tickers, elegido=None)`, `panel_ia.interpretar_hechos(st, a_leer, ruta_archivo, tickers, pesos, clave, con_enlace_a_perfil=False)`, y el `contexto` de la pantalla con sus cuatro claves (`panel`, `fecha_panel`, `sp500`, `trimestre`).

**Lo que se corrigió en la autorrevisión:** `sesion.pendientes` vuelve a intentar los tickers que salieron sin clase (si no, un corte de red al primer «Analizar» se quedaba en la caché de la sesión); el país de Yahoo pasa por `plano` en el aviso de la prima; el test de los textos que mandan a Noticias mira las cadenas ya unidas por el parser; el motivo redactado de `_fija()` lleva «(pares a favor)», porque su voto de pares es «barata».

**Lo que corrigió aplicarlo en un worktree.** Las diecinueve tareas de código se aplicaron tal cual, en orden, sobre una copia de la rama: cada tarea dejó sus tests en verde y la suite entera acabó en 3376 pasando. Con la pantalla arrancada salieron tres cosas que ningún test veía y que ya están corregidas arriba: el gráfico de TradingView salía de 150 píxeles (Task 8, `html,body{height:100%}`), la BMV no se ve en el widget (D22, Tasks 8 y 15) y Streamlit 1.62 da por obsoletos `components.v1.html` y `use_container_width` (D23, Tasks 14 a 19). Y dos que quedan anotadas para la Task 22 en vez de arreglarse: el precio de la fila y el de la valoración pueden diferir unos céntimos, y el mensaje de un supuesto imposible enseña la clave `k_e`.
