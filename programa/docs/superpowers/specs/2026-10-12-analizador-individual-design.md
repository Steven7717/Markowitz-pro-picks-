# Analizador individual — sub-proyecto N

**Fecha:** 2026-10-12
**Estado:** N1 (los datos de cualquier ticker) implementado en la rama
`feat/analizador-individual`; N2 (la pantalla) y N3 (la IA) pendientes
**Depende de:** el sub-proyecto M, el valor intrínseco
(`2026-10-12-valor-intrinseco-design.md`). N no empieza hasta que M esté en
`master`.

## Qué entrega

Una pantalla nueva, **Analizador**, que aplica a cualquier acción la mecánica de
Revisar candidatos —la ficha frente al sector, el valor intrínseco de M y la
IA— y le añade un gráfico en tiempo real y las noticias y el calendario.

**Absorbe Noticias y calendario**, que sale del menú. Lo que esa pantalla hacía
para un libro entero se hace aquí con «Cargar de un libro», y la pestaña de
noticias del panel de Seguimiento se queda como está.

Decisiones tomadas con el usuario el 2026-10-12:

| Pregunta | Decisión |
|---|---|
| Qué tickers acepta | Empresas de la SEC, emisoras extranjeras y de la BMV, y ETFs (estos sin valoración) |
| Supuestos de la valoración | Los deduce el programa, y se pueden mover con deslizadores |
| Qué hace la IA | Tesis y riesgos, interpretar 8-K, explicar la valoración y contrastar los supuestos con el MD&A |
| Gráfico | Widget de TradingView |
| Distribución | Resumen de todos los tickers y detalle del elegido en pestañas |
| Del Analizador al optimizador | Por Revisar candidatos, como añadido a mano: hay un solo gate y una sola acta |

## Las cuatro clases de ticker

`analizador/resolver.py` decide qué es cada ticker con el `quoteType` de
yfinance y el registro de la SEC. La clase determina de dónde salen los números
y qué puede leer la IA:

| Clase | Ejemplo | Números | Documentos para la IA |
|---|---|---|---|
| `sec` (presenta 10-K/10-Q) | MU, VEEV | EDGAR, con el mismo motor que los candidatos | 10-K: Item 1A y MD&A. 8-K |
| `extranjera_sec` (20-F/40-F) | TSM | yfinance. Su XBRL es IFRS y anual, y las cadenas de `fundamentals/concepts.py` son US-GAAP | 20-F: Item 3.D y Item 5. No presenta 8-K, y se dice |
| `sin_sec` | WALMEX.MX | yfinance | Ninguno |
| `etf` | SPY, GLD | — | — |

Si `quoteType` no es `EQUITY` ni `ETF` (fondo, índice, cripto) o Yahoo no conoce
el ticker, la fila del resumen lo dice y ese ticker no tiene detalle.

### La forma del ticker — una trampa en dos sitios

El código actual **rompe los tickers de la BMV** antes de llegar a ninguna
fuente:

- `research.universe.normalise_ticker` cambia el punto por un guion porque así
  escribe Yahoo las clases de acción (`BRK.B` → `BRK-B`). Con `WALMEX.MX` daría
  `WALMEX-MX`, que Yahoo no conoce.
- `aprobacion.acta._FORMA_TICKER` (`^[A-Z]+(-[A-Z]+)*$`) rechaza cualquier punto.

`analizador/resolver.normalizar` distingue los dos usos del punto con una
**tabla cerrada de sufijos de bolsa de Yahoo** (`.MX`, `.L`, `.TO`, `.DE`,
`.PA`, `.HK`, `.T`…). Si lo que hay detrás del último punto está en la tabla, se
conserva. Si no, el punto es de clase de acción y pasa a guion. `BRK.B` da
`BRK-B` y `WALMEX.MX` da `WALMEX.MX`. **Las dos funciones existentes no se
tocan**: sirven al universo del S&P 500 y al acta, y ahí están bien.

## Los números

### Empresas de la SEC

Los mismos que M: `valoracion.fundamentos` desde EDGAR, y los KPIs del panel
desde `fundamentals`.

### Las demás: `analizador/lineas_yf.py`

Las filas de los estados de yfinance se traducen a **las mismas columnas** que
produce `fundamentals.concepts.resolve_lines`, y de ahí pasan por las mismas
funciones de `fundamentals/kpis.py`. Así el ROE de WALMEX y el de MU salen de
la misma fórmula y en la misma base trimestral.

| Columna del motor | Fila de yfinance |
|---|---|
| `ingresos` | `Total Revenue` |
| `coste_de_ventas` | `Cost Of Revenue` |
| `beneficio_operativo` | `Operating Income`, o `EBIT` si falta |
| `beneficio_neto` | `Net Income Common Stockholders` |
| `bpa_diluido` | `Diluted EPS` |
| `depreciacion_amortizacion` | `Reconciled Depreciation` |
| `gasto_por_intereses` | `Interest Expense` |
| `activos_totales`, `activos_corrientes`, `pasivos_corrientes` | `Total Assets`, `Current Assets`, `Current Liabilities` |
| `patrimonio_neto` | `Stockholders Equity` |
| `deuda_total` | `Total Debt` |
| `efectivo` | `Cash And Cash Equivalents` |
| `flujo_operativo` | `Operating Cash Flow` |
| `capex` | `Capital Expenditure`, **cambiado de signo**: yfinance lo da negativo y la SEC positivo |
| `acciones_diluidas` | `Diluted Average Shares` |

Los nombres exactos de fila se fijan contra lo que yfinance devuelve de verdad
(test `red` con MU, WALMEX.MX, TSM y JPM), no contra esta tabla.

**Lo que dio el sondeo del 2026-10-12, y lo que cambia:**

- **yfinance sólo da 5 o 6 trimestres, y con huecos.** A WALMEX le falta el
  3T 2025 en el flujo de caja. Los KPIs frente a pares se calculan con los
  trimestres que haya. Los de crecimiento interanual tendrán como mucho uno o
  dos puntos, y la cobertura lo dice. **El TTM sólo se suma con cuatro
  trimestres consecutivos**; si no los hay, se usa el último ejercicio anual.
- **Para la valoración** se usa la `historia` anual (4–5 ejercicios), con el
  mismo `Fundamentos` que M.
- **La moneda de los estados es `financialCurrency`**, no `currency`. En TSM son
  TWD y USD respectivamente.

### Divisas: `analizador/divisas.py`

| Caso | Cómo se valora |
|---|---|
| Estados en USD | Como en M |
| Estados en MXN | En pesos. `r_f` = rendimiento del Bono M a 10 años del SIE de Banxico, y beta contra el IPC (`^MXX`) |
| Cualquier otra moneda | Los estados se convierten a USD al tipo del día (`<MON>USD=X`) y se valora como en M. La procedencia dice «sin prima por riesgo país» |

- **El Bono M.** Se reutiliza el transporte de `seguimiento/banxico.py`, con el
  token en la cabecera y nunca en la URL, su caché y sus fallos con nombre. El id
  de la serie **no se escribe de memoria**: se busca en el catálogo del SIE y se
  fija con un test `red` que comprueba el título de sus metadatos, como se hizo
  con `SF43718`. **Sin token de Banxico**, `r_f` sale vacío para las emisoras en
  pesos, el deslizador pide el dato, y el voto de flujos dice `sin_tasa_libre`
  hasta que se meta.
- **Se usa el Bono M tal cual, sin restar el diferencial soberano.** Damodaran
  propone quitarle al bono local su prima de impago y sumar una prima de riesgo
  país a la del mercado. Con una beta cercana a 1 la diferencia es de décimas, y
  el supuesto se puede mover. Queda dicho en la procedencia.
- **El precio se lleva a la moneda de los estados** para votar, y el resultado se
  enseña en la del precio.
- **La trampa de las ADR.** En TSM, `sharesOutstanding` (5.186 millones) está en
  base ADR, 1/5 del recuento de acciones ordinarias de los estados. Por eso el
  valor por acción se divide siempre por **capitalización ÷ precio**, como en M.
  Si ese recuento y el de los estados no cuadran con un cociente cercano a 1
  después de la conversión de divisa, se avisa de que puede ser una ADR con un
  ratio distinto de 1.

## La referencia sectorial

Para comparar con los pares hace falta el panel del S&P 500.

**`ranking/run.guardar` escribe además `salidas/panel.parquet`**: los KPIs crudos,
el trimestre natural y el sector de cada fila. Pesa en torno a un megabyte.

`analizador/referencia.py`:

- **Si el ticker está en el panel**, se usan sus z tal cual, y la ficha sale
  idéntica a la de Revisar candidatos.
- **Si no está**, sus filas se insertan en su sector, trimestre a trimestre, y se
  le aplican **las mismas funciones**: `zscore_within_sector` (con el mismo
  `TOPE_Z` y `MIN_PARES`), `ranking.score.media_ventana`,
  `puntuaciones_por_pilar` y `aplicar_guardas`. Se obtiene una ficha con la
  forma de `ranking.fichas.ficha_numerica`, la nota compuesta y el **puesto que
  tendría** entre los supervivientes del ranking. Si alguna guarda lo dejaría
  fuera, se dice cuál.
- **Si el panel no existe**, la pestaña Fundamentales ofrece construirlo gratis:
  la misma corrida que «Generar gratis», unos dos minutos con la caché llena y
  once la primera vez. Sin panel, el voto de pares es `no_aplica` con
  `sin_pares`.
- La fecha del panel se enseña siempre: la referencia es la de la última vez que
  se generaron candidatos.

**El sector fuera del S&P 500** sale de `info["sector"]` de Yahoo y se traduce a
GICS con una tabla congelada en `analizador/sectores.py`:

| Yahoo | GICS |
|---|---|
| Technology | Information Technology |
| Healthcare | Health Care |
| Financial Services | Financials |
| Consumer Cyclical | Consumer Discretionary |
| Consumer Defensive | Consumer Staples |
| Basic Materials | Materials |
| Communication Services, Industrials, Energy, Utilities, Real Estate | El mismo nombre |

Un sector que no esté en la tabla se queda **sin pares, y se dice**, en vez de
adivinarse. A una empresa del S&P 500 se le sigue sacando el sector de
`fundamentals/data/sectores_2026-08-10.csv`, como hoy.

**Para las que no son de EE. UU.** la ficha lo dice: «comparada con las empresas
del S&P 500 de su sector. Márgenes y rentabilidad son comparables; los múltiplos
lo son menos, porque no incluyen el riesgo país».

## La pantalla — `vistas/analizador.py`

Widgets sin lógica, como el resto de `vistas/`.

### Arriba

- Un campo de tickers, separados por comas o espacios. Hasta **15**, que es el
  tamaño del top de candidatos: cada ticker cuesta varias consultas de red.
- **«Cargar de un libro»**: el mismo desplegable de `vistas/libros.py` que usaba
  Noticias. Trae lo que se tiene más lo que el objetivo dice que se debería
  tener. **Sólo viajan los tickers**: ni pesos ni importes salen del libro.
- El botón **Analizar**.

Los tickers analizados viven en `st.session_state` y sobreviven a la navegación.
**«Analizar a fondo»** en Revisar candidatos los mete ahí y salta a esta
pantalla.

### El resumen

Una tabla, una fila por ticker:

| Ticker | Clase | Precio | Valor base | Margen de seguridad | Veredicto | Frente al sector | Próximo evento |
|---|---|---|---|---|---|---|---|

Debajo, **«Lo que viene»** de todos los tickers juntos y los punteros macro,
heredados de `vistas/noticias.py`. Al elegir una fila se abre su detalle.

**El precio no se refresca solo, a propósito.** Un veredicto que cambia cada
minuto con el precio es ruido. Lleva la hora de la cotización y un botón
«Actualizar precios». El tiempo real vive en el gráfico.

Si un ticker falla, sólo su fila lo dice. Los demás se analizan igual.

### Las pestañas del detalle

| Pestaña | Contenido | Sale de |
|---|---|---|
| **Resumen** | Nombre, sector, clase, moneda y fuente de los datos. El veredicto con sus tres votos, la tarjeta de candidato y el puesto hipotético. **«Añadir a la revisión»** | `valoracion/`, `medidores.tarjeta_candidato` |
| **Valoración** | Los supuestos, cada uno con su procedencia y su deslizador, y «Restaurar los del programa». Las cuatro lecturas, la proyección a 10 años (plegada) y la tabla de sensibilidad. En las financieras, el beneficio residual. La nota de «criterio transparente, no previsión» | `valoracion/` |
| **Fundamentales** | La ficha de candidatos: los cuatro pilares, la cobertura, los tres puntos más fuertes y los tres más flojos, contra qué pares se compara y la fecha de la referencia | `medidores.py`, sin cambios |
| **Gráfico** | TradingView | ver abajo |
| **Noticias y calendario** | Lo que viene, los 8-K destacados y plegados, la prensa y la hora de cada descarga, más **«Interpretar con IA»** junto a los 8-K | `noticias/`, `interprete/` |
| **IA** | Tres bloques con su botón: tesis y riesgos, contraste con el MD&A y explicación de la valoración | ver «La IA» |

**Los deslizadores** viven en un `st.fragment`. Moverlos rehace la cuenta, que
es aritmética pura, sin volver a pedir nada a la red. N añade a
`valoracion/supuestos.py` la función `aplicar(supuestos, cambios)`, que devuelve
otros supuestos con lo que se movió y marca qué fue. M no la tenía porque en
candidatos no hay nada que mover. Por la misma razón, N añade también
`valoracion.dcf.sensibilidad`, la tabla de coste de capital frente a
crecimiento perpetuo que describe el spec de M. El distintivo pasa a decir
«con tus supuestos» y la lista de supuestos marca cuáles se movieron. **Lo
movido no se guarda en ningún sitio.**

**Un ETF** sólo tiene Resumen (precio y clase), Gráfico y Noticias y
calendario. Las demás pestañas no se dibujan, en vez de salir vacías. **Una
emisora `sin_sec`** tiene todas las pestañas. En Noticias sólo hay prensa y
calendario, y en IA sólo funciona la explicación de la valoración; las dos cosas
se dicen.

### El gráfico

El *Advanced Chart* de TradingView, incrustado con
`streamlit.components.v1.html`, con el tema claro u oscuro de la app.

- **El símbolo** se traduce desde el `exchange` de yfinance con una tabla
  congelada: `NMS`/`NGM`/`NCM` → `NASDAQ:`, `NYQ` → `NYSE:`, `ASE`/`PCX` →
  `AMEX:`, `MEX` → `BMV:`. Para el símbolo, el sufijo de bolsa se quita y el
  guion de clase vuelve a ser punto: `BRK-B` → `NYSE:BRK.B`, `WALMEX.MX` →
  `BMV:WALMEX`. Si la bolsa no está en la tabla, se pasa el símbolo sin prefijo y
  TradingView lo resuelve.
- **Bajo el gráfico:**
  > El sub-proyecto D midió siete señales técnicas sobre el S&P 500 —momentum,
  > RSI, MACD, medias, máximos de 52 semanas, Bollinger y reversión— y ninguna
  > mostró ventaja después de costes. El gráfico está para quien quiera mirarlo;
  > el programa no lo usa para nada.
- **Lo que se sabe y se dice:** el gráfico es un script de TradingView, así que
  TradingView sabe qué ticker se mira, y sin conexión no se ve. Sus datos no son
  los del programa ni se reutilizan en ningún cálculo. Para la BMV los datos
  llevan unos 15–20 minutos de retraso.

### El menú

`app.py`: **Analizador** entra en «Análisis», después de Revisar candidatos.
**«Noticias y calendario» sale de «Cartera»** y se borra `vistas/noticias.py`.
Se revisan todos los `st.switch_page` que apunten a ella, la guía de Primeros
pasos y el README.

## La IA

Las cuatro lecturas comparten el cliente de `interprete/cliente.py`: el mismo
modelo, el mismo `TOPE_USD_POR_PULSACION` y los mismos precios para la
estimación.

- **Nunca se llama sin botón.** La etiqueta del botón dice cuánto puede costar
  como mucho, calculado con los topes de caracteres y los precios de
  `cliente.py`.
- **Hay confirmación** con una bandera que no es de un widget y se desarma antes
  de llamar, como en Revisar candidatos, para que un fallo no deje el gasto a un
  clic.
- **Al terminar** se dice lo que costó de verdad.
- **El modelo no ve nada de la cartera.**

### 1. Tesis y riesgos

El de B, sin tocar: `ranking/llm.redactar_con_cache` sobre el Item 1A, con el
contexto en palabras de `ranking/run._contexto`, que pasa a ser una función
pública para poder importarla. Las citas se verifican con
`ranking/verificacion.py` y la caché es la de siempre.

**Para el 20-F** hace falta un cargador del Item 3.D (*Risk Factors*) al lado de
`ranking/filings.cargar_riesgos`. **`SISTEMA` no cambia**, y así la caché de
fichas sigue valiendo: cambiar el prompt la invalida entera.

### 2. Interpretar los 8-K

El de I, sin tocar: `interprete/noticias.leer` sobre exactamente los 8-K que hay
en pantalla, con `pesos=()`, porque aquí no hay cartera. Los documentos se bajan
con `interprete/documentos.py`.

### 3. Explicar la valoración — nueva, `analizador/ia_valoracion.py`

**Qué lee.** Nada de la empresa: sólo los votos y los supuestos, que **el código
traduce a palabras**. Por ejemplo: «el precio exige un crecimiento muy por
encima de su referencia», «la mayor parte del precio es apuesta por el
crecimiento», «la beta es poco fiable: el ajuste de la regresión es débil»,
«múltiplos por debajo de los de su sector». Con eso, la clase y el sector. Si el
usuario movió supuestos, cuáles.

**El guardarraíl** es el de la mitad de rebalanceo de I, porque tampoco aquí hay
texto que citar:

- Cada observación va dirigida a una **letra**: `A` = flujos, `B` = sin
  crecimiento, `C` = pares. Una letra que no esté en el conjunto se descarta.
- **Cero dígitos**, con `ranking.verificacion.sin_digitos`. Una observación con
  un dígito se tira entera, como hace I con sus juicios.
- **Sin recomendaciones.** El prompt prohíbe recomendar comprar, vender o
  esperar, y lo impone el código: una observación con una de las raíces de una
  lista cerrada (`compr`, `vend`, `recomiend`, `aconsej`) sale marcada, igual
  que una cita sin verificar. No se borra en silencio.
- Un párrafo **«en conjunto»** que, como en I, se vacía entero si falla, nunca a
  trozos.

### 4. Contrastar con la empresa — nueva, `analizador/ia_mdna.py`

**Qué lee.** El MD&A —Item 7 del 10-K o Item 5 del 20-F—, recortado con
`interprete.documentos.aplicar_tope`. El supuesto de crecimiento le llega **en
palabras** («el escenario base supone que los ingresos crecen muy por encima de
su ritmo de los últimos años»).

**Qué devuelve.** Juicios con tres campos: la afirmación; si la empresa
**respalda**, **contradice** o **matiza** el escenario base; y la cita. La cita
se verifica carácter a carácter con `ranking/verificacion.verificar_cita`. Si no
verifica, se enseña marcada «Cita SIN VERIFICAR», como en candidatos.

**La IA no mueve ningún deslizador.** Señala, y decide el usuario: los agentes
proponen y nunca ejecutan.

**El MD&A tiene una trampa conocida.** Algunas empresas, sobre todo bancos, no lo
escriben en el Item 7: lo incorporan por referencia al anexo EX-13, con el
informe anual. El plan **empieza sondeando EDGAR en vivo** con media docena de
casos (MU, VEEV, JPM, una aseguradora, un 20-F como TSM y una empresa pequeña)
antes de escribir el extractor. Si no se localiza, el bloque lo dice. Nunca se
manda otra sección haciéndola pasar por MD&A.

### El archivo — `analizador/archivo.py`

Todo lo que devuelve la IA se guarda en `analisis/<TICKER>.json`, en la raíz del
programa. Se añade `analisis/` a `.gitignore`, junto a `actas/` y `libros/`.

- **Append-only**, como el archivo de I: volver a leer añade una sesión. Un
  juicio es una opinión fechada, y reescribirlo borraría que cambió.
- **Un archivo ilegible no se trata como vacío** ni se toca: se levanta
  `ArchivoIlegible` y la pantalla lo dice. Lo perdido sería historial, no caché.
- **Al abrir un ticker ya leído** se pinta lo guardado **sin pagar**, con su
  fecha. Si hay un 10-K o un 20-F más reciente que el leído, se avisa y se
  ofrece volver a leer.
- **La explicación de la valoración se guarda con los votos que tenía delante.**
  Si los de hoy son otros, se pinta como «explicación del 12/10/2026, con los
  números de entonces», sin aparentar que habla de los de hoy.
- **Un juicio guardado conserva su `verificada` y no se re-verifica**, porque el
  documento ya no está delante. Es la regla de I.
- **Los 8-K** se guardan en el mismo archivo, con el formato de
  `interprete/archivo.py`, de modo que un 8-K ya leído para ese ticker no se paga
  dos veces.

## El gate: «Añadir a la revisión»

El botón del Resumen mete el ticker en `st.session_state.anadidos` de Revisar
candidatos y salta a esa pantalla. Lleva un motivo ya redactado y editable:

> Analizador, 12/10/2026: infravalorada (flujos y pares a favor), supuestos del
> programa.

- **`aprobacion.acta.Anadido` gana `valoracion: dict | None = None`**, así que
  el acta registra la valoración de lo añadido a mano. Siempre es la calculada
  con los supuestos del programa: si el usuario movió alguno, el motivo puede
  decirlo, pero lo guardado sigue siendo comparable entre actas. **Las actas
  viejas siguen leyéndose**: la clave es opcional al leer.
- **Siguen en pie las reglas de candidatos:** si el ticker ya está en el ranking,
  se rechaza y se remite a su casilla; el motivo es obligatorio; regenerar vacía
  los añadidos, y avisa.
- **Sólo para tickers que coticen en dólares.** El optimizador
  (`data.fetch_market_data`) baja precios sin convertir divisas, y los libros
  llevan `moneda = "USD"`. Una serie en pesos metida entre series en dólares
  mezclaría dos monedas en la misma covarianza: es el mismo error que el
  sub-proyecto L evitó al convertir antes de aplicar Fisher. Para WALMEX.MX el
  botón no aparece, y en su lugar se explica por qué. Una ADR como TSM cotiza en
  dólares y sí puede pasar.
- **La forma del ticker en el acta.** Como sólo pasan tickers en dólares, ninguno
  lleva sufijo de bolsa, y `_FORMA_TICKER` no hace falta tocarla. Un ticker con
  clase llega ya como `BRK-B`.

## Cachés y frescura

| Qué | Dónde | Validez |
|---|---|---|
| Hechos de EDGAR | `fundamentals/.cache/`, la de siempre | — |
| Estados de yfinance | `valoracion/.cache/`, la de M (ver «Enmiendas del 2026-10-14») | 1 día |
| Formularios de EDGAR: qué informe anual presenta | `analizador/.cache/` (nueva, en `.gitignore`; ver «Enmiendas del 2026-10-14») | 30 días; «no presenta ninguno», 1 día |
| Precio, beta, `r_f`, tipos de cambio | `valoracion/.cache/`, la de M | 15 minutos el precio, 1 día lo demás |
| Bono M | `seguimiento/.cache/banxico/`, la de L | 1 día |
| Noticias, hechos y calendario | `noticias/.cache/`, la de H | La de H |

La hora de cada dato se enseña siempre, esté fresco o no. Es la regla de
Noticias.

## Errores

| Situación | Qué se ve |
|---|---|
| Ticker que Yahoo no conoce | En su fila: «Yahoo no conoce este ticker». No hay detalle |
| Fondo, índice, cripto | «Tipo no soportado: sólo acciones y ETFs». No hay detalle |
| Falla la red para un ticker | Sólo su fila lo dice, con el motivo con nombre |
| Sin panel de referencia | Pares `no_aplica`, y el botón para construirlo |
| Emisora en pesos sin token de Banxico | Flujos `sin_tasa_libre`, y el deslizador de `r_f` pide el dato |
| Sin `ANTHROPIC_API_KEY` | Los bloques de IA lo dicen y enlazan a Perfil |
| `sin_sec` | Los tres bloques con documento dicen que no hay documento oficial que citar |
| Sin conexión | El gráfico no carga y lo dice; el resto enseña lo que tenga en caché, con su hora |

## Cómo se prueba

1. **Sondeo antes del extractor del MD&A** (ver arriba) y antes de fijar las
   filas de yfinance.
2. **`resolver.normalizar`**: `BRK.B`, `BF.B`, `WALMEX.MX`, `GFNORTEO.MX`,
   `RY.TO`, `brk-b` y `walmex.mx`, más los rechazos.
3. **`lineas_yf`**: el signo del capex, el TTM con un trimestre que falta (el
   hueco de WALMEX), `financialCurrency` distinto de `currency` (TSM) y un
   `revenue_estimate` en otra moneda que se descarta.
4. **La ADR**: con las cifras del sondeo de TSM, el valor por acción con
   capitalización ÷ precio frente al que daría el recuento de los estados (5
   veces más bajo), y el aviso.
5. **La referencia sectorial**: un ticker del panel da exactamente su ficha de
   candidatos; uno insertado da los mismos z que si hubiera estado en el panel
   desde el principio (se comprueba sacando uno del panel y volviendo a
   meterlo); y el puesto hipotético de un candidato real coincide con su puesto.
6. **El guardarraíl de `ia_valoracion`**: una letra inexistente, un dígito, una
   recomendación y un «en conjunto» roto. Con un cliente doble, sin red.
7. **`ia_mdna`**: una cita que verifica, una que no, y un MD&A no localizado.
8. **El archivo**: append-only, ilegible sin tocar, lo guardado pintado sin
   llamar, y el aviso de documento más reciente.
9. **El gate**: «Añadir a la revisión» con un ticker del ranking (se rechaza),
   uno en pesos (no aparece el botón) y uno en dólares (llega al acta con su
   valoración). Más un acta vieja sin `valoracion` en sus añadidos.
10. **Sabotaje de cada guarda**, con la regla de siempre: un sabotaje inerte es
    una pregunta.
11. **Tests `red`**: las cuatro clases con casos reales (MU, TSM, WALMEX.MX,
    SPY), el id del Bono M por sus metadatos y las filas reales de yfinance.
12. **Recorrido con la app arrancada**: MU, WALMEX.MX, TSM, JPM y SPY en el
    Analizador, con las seis pestañas; «Cargar de un libro»; «Analizar a fondo»
    desde candidatos; «Añadir a la revisión» hasta el acta; y comprobar que el
    menú ya no tiene Noticias. **Los cuatro botones de IA gastan saldo del
    usuario**: se pide permiso antes de pulsarlos.

## Lo que N no resuelve

- **El optimizador y los libros siguen en dólares.** Una emisora en pesos se
  analiza, pero no puede pasar al gate. Abrirlo exigiría convertir divisas en el
  optimizador y en el libro, que es un sub-proyecto aparte.
- **Los pares son estadounidenses.** No existe un panel de la BMV con el que
  comparar a WALMEX contra empresas mexicanas.
- **Los datos de yfinance no tienen fecha de publicación.** No hay forma de saber
  si una cifra es la publicada o una corregida después.
- **Lo que mueves en los deslizadores no se guarda.** No hay escenarios con
  nombre.
- **La prensa sigue sin deduplicar**, que es deuda de H.
- **El 6-K de los emisores extranjeros no se interpreta**: no lleva códigos de
  item, y el criterio de materialidad de H se construyó sobre ellos.
- **Los datos de TradingView no son los del programa**: lo que se ve en el
  gráfico no se puede reutilizar en ningún cálculo.

## Enmiendas del 2026-10-14, al planear y ejecutar N1

N se parte en tres planes que se ejecutan en orden: **N1, los datos**
(`docs/superpowers/plans/2026-10-14-analizador-n1-datos.md`), **N2, la
pantalla** y **N3, la IA**. El sondeo de yfinance, EDGAR y Banxico del
2026-10-14 cambió esto:

- **TSM: yfinance ya da el recuento en base ADR.** `Diluted Average Shares` =
  5.186 millones, igual que `sharesOutstanding`, y el BPA en TWD por ADR. La
  trampa de la ADR que cuenta «Divisas» (un recuento cinco veces mayor en los
  estados) no aparece con yfinance; sí aparecería con el XBRL del 20-F, que N no
  usa. El cociente se sigue calculando y avisando (`divisas.cociente_adr`), como
  guarda. Donde «La trampa de las ADR» y el punto 4 de «Cómo se prueba» dan por
  hecho que el recuento de los estados de TSM es cinco veces el de
  capitalización ÷ precio, manda esta enmienda.
- **yfinance da 5 o 6 trimestres, a veces con un hueco** (a WALMEX le falta el
  3T 2025 en resultados y flujos; su balance trae la columna vacía).
  `fundamentals.kpis` compara con `shift(4)` y suma con `rolling(4)`, que
  cuentan filas: con un hueco, el «mismo trimestre del año pasado» caería en
  otro. `lineas_yf.rejilla_trimestral` da una fila a cada trimestre natural y
  `lineas_yf.rellenar_desde_anual` recupera el flujo del trimestre que falta
  como el año menos los otros tres, que es la aritmética de
  `fundamentals.panel._cuartos_derivados`. La resta no se fía de cifras de Yahoo
  que no cuadran: unos 0,0 que son falta de desglose, un negativo en una línea
  que no puede serlo, o un ejercicio con un trimestre de ingresos negativos.
- **BRK-B no trae `Operating Income`, sólo `EBIT`; JPM no trae ni coste de
  ventas ni beneficio operativo.** La cadena `Operating Income` → `EBIT` de la
  tabla de «Las demás» se resuelve fila a fila, como
  `fundamentals.concepts.resolve_lines`.
- **La valoración de yfinance usa ejercicios fiscales completos**, no un TTM
  trimestral: con cinco trimestres sólo cabe un TTM, y mezclarlo con los
  ejercicios anuales rompería que `ejercicios[i]` sea «hace i años», que es lo
  que `supuestos._cagr` da por hecho. `estados_hasta` lo dice en pantalla.
- **La clase sale de los formularios que la empresa presenta en EDGAR**, no del
  atributo `is_foreign` de edgartools: RY presenta 40-F y edgartools la marca
  `is_foreign = False`. 10-K → `sec`; 20-F o 40-F → `extranjera_sec`; ninguno, o
  no está en EDGAR → `sin_sec`. Un ticker con sufijo de bolsa (`.MX`) no se
  pregunta a EDGAR.
- **El Bono M a 10 años es la serie `SF44071`** del SIE: «Valores
  Gubernamentales. Resultados de la subasta semanal. Tasa de rendimiento. Bono
  tasa fija 10 años», en porcentaje. Es de subasta y no de mercado secundario,
  así que el último dato puede tener semanas (el 2026-10-14, el del
  24/09/2026); su fecha va en la procedencia. Lo fija un test `red` contra el
  título de sus metadatos.
- **Los pares de divisa de Yahoo existen en los dos sentidos** (`TWDUSD=X` y
  `USDTWD=X`, `MXNUSD=X`, `CADUSD=X`); se usa `<ORIGEN><DESTINO>=X`. `^MXX` es
  el IPC.
- **La identidad, los estados y el tipo de cambio se guardan en la caché de
  `valoracion/mercado.py`** (`valoracion/.cache/`), no en una
  `analizador/.cache/` aparte: `mercado` ya es la única puerta a yfinance, con
  su caché, su respaldo y sus motivos con nombre, y una segunda puerta sería la
  que se queda atrás. `analizador/.cache/` sólo guarda los formularios de EDGAR.
- **El puesto hipotético es el global** —el orden por nota compuesta entre las
  que pasan las guardas, sin el tope por sector—, que es el único que existe
  para un ticker que no compite por las quince plazas. Para el primero de los
  candidatos coincide con su puesto; para los demás puede no coincidir (con un
  tope de 2 por sector difería en 11 de 96 candidatas; en la corrida real del
  16/10 los quince coincidían). Donde el punto 5 de «Cómo se prueba» dice que el
  puesto hipotético de un candidato real coincide con su puesto, manda esta
  enmienda.
- **Las filas de un ticker posteriores al último trimestre del panel no entran
  en la comparación**: en ese trimestre no tiene pares, y su z saldría vacía y le
  quitaría un trimestre de la ventana.
- **Si el precio y los estados van en monedas distintas** (TSM: dólares y TWD),
  los múltiplos del panel trimestral se calculan con el precio de cada fecha
  convertido al tipo de cambio de esa misma fecha, que se baja con el mismo
  cargador de precios.
- **Un motivo nuevo para una valoración que no se calcula**: `sin_bono_m`
  (una emisora en pesos sin el Bono M, normalmente por no tener token de
  Banxico; el deslizador de la tasa libre lo resuelve). `sin_tasa_libre` no
  servía: su etiqueta culpa a Yahoo. Un tipo de cambio que no llega es
  `sin_red`. Donde «Divisas» y «Errores» dicen `sin_tasa_libre` para una
  emisora en pesos sin token, manda esta enmienda. El motivo concreto
  (`sin_token`, `token_invalido`, `sin_red`, `sin_dato`) no cabe en la
  valoración fallida y viaja en `Entradas.motivo_r_f`.
- **La tabla de «Cachés y frescura»**: los estados de yfinance, la identidad y
  los tipos de cambio van en `valoracion/.cache/` (estados un día, identidad
  quince minutos, tipos de cambio un día), y `analizador/.cache/` sólo guarda
  los formularios de EDGAR (treinta días). Comprobado en el código el
  2026-10-25: es `mercado.VALIDEZ`, donde la beta, también la que se regresa con
  un par de divisas, sigue en un día, como en M; y en `resolver`, un «no
  presenta ningún informe anual» vale un día y no treinta, también sin red,
  porque puede ser una salida a bolsa a punto de presentar su primer 10-K o una
  lista de tickers de la SEC que no se pudo bajar. Sin red, `mercado` sirve lo
  guardado hasta `ANTIGUEDAD_MAXIMA`: los estados 30 días, la identidad y los
  tipos de cambio 7, la beta 90.

Al ejecutar N1 salió además esto, que también cambia lo que el spec dice o
promete:

- **Los KPIs de yfinance se calculan en dólares, con un único tipo.** Después de
  llevar el precio de cada trimestre a la moneda de los estados (ver arriba «Si
  el precio y los estados van en monedas distintas»), `kpis.kpis_yf` pasa las
  líneas y el precio a dólares con **un solo** tipo, el último cierre. Los
  suelos económicos de `fundamentals.kpis` están pensados en dólares —1e8 de
  partida de balance y 1e6 de gasto financiero—, y en wones el del gasto financiero valdría 745 $: una pequeña de
  la BMV o de KOSDAQ sacaría márgenes y coberturas que el panel de referencia le
  taparía a una empresa de EE. UU. de su tamaño. Un tipo constante no cambia
  ningún cociente ni ningún crecimiento; con el de cada fecha, la divisa
  entraría en el crecimiento interanual. Vale también para una emisora en pesos:
  sus KPIs van en dólares aunque se valore en pesos.
- **Sin precio, las filas propias dicen `sin_precio`**, y no culpan a la
  empresa ni a la SEC. Con un universo de uno, que Yahoo no dé el precio hace
  abortar a `build_panel`, y `kpis.kpis_sec` dice `sin_precio` y no
  `sin_estados`. `kpis.kpis_yf` devuelve `(filas, motivo)` y dice `sin_precio`
  si no hay ni un precio en dólares, en vez de unas filas sin valoración que la
  guarda excluiría por «pilar sin datos». Y sin ninguna moneda en la identidad,
  `sin_precio` en vez de pedir `NoneUSD=X`, un 404 que culparía a la red. Sin
  trimestres, en cambio, es `sin_historia`, aunque la serie de precios también
  salga vacía.
- **`sector_sin_pares` se comprueba antes de bajar nada.** Un sector que, con
  el ticker dentro, no llega a `MIN_PARES` (3) empresas en el panel no tiene z,
  y la ficha saldría «pilar sin datos», que culparía a la empresa.
  `analizador.analisis` lo mira antes de bajar ninguna fila y dice
  `sector_sin_pares`, la clave del ranking; `sin_sector` también sale sin bajar
  nada. Amplía lo que «La referencia sectorial» dice de un sector que no está en
  la tabla: también se queda sin pares, y se dice, el que está en la tabla y no
  tiene pares en el panel.
- **La beta con par usa el semanal de Yahoo sin sus picos, filtrado con el
  diario.** El precio se regresa en la moneda del índice: AMX cotiza en dólares
  y se valora en pesos contra el IPC, y regresar su precio en dólares contra un
  índice en pesos mezcla dos monedas (medido el 2026-10-19 a 104 semanas: AMX
  da 1,036 y AMXB.MX 0,834; FMX 0,841 y FEMSAUBD.MX 0,644; unos 0,2 de beta, un
  punto de coste del capital). Así que `mercado.beta` gana un par con que
  convertir el precio, y el par no se puede tomar tal cual: su **semanal** trae
  velas corruptas (CADUSD=X marcaba 0,911 entre dos semanas de 0,70, y RY.TO
  salía con beta 0,27 en vez de 0,46), y su **diario** no trae el cierre del día
  sino una foto a medianoche de Londres, un día por detrás (con él, AMX daba
  0,90 en vez de 0,79). Se usa el semanal, y el diario sólo para descartar las
  semanas en que el semanal se aparta de él más de un 5 %
  (`mercado.tipo_sin_picos`): en USDTRY, USDARS o el USDMXN de marzo de 2020 no
  descarta ninguna buena, y a NPN.JO le quita seis picos de ZARUSD. El diario se
  pide desde una semana antes, porque con `period="2y"` empieza una semana
  después que el semanal y la primera semana se perdía siempre. Sin diario no
  hay beta, y no se guarda. El activo y el índice siguen en semanal, como en M.
- **La tasa libre puesta a mano pasa por las mismas guardas que un supuesto
  movido.** Sin Bono M, la que pone el usuario entra por `deducir` y no por
  `aplicar`, y las guardas de `aplicar` no la veían: con un −5 %, WALMEX salía
  con un coste del capital propio negativo y un valor base. Ahora se le exige un
  coste del capital propio y un WACC positivos
  (`supuestos.exigir_costes_positivos`), juzgados sobre el resultado, después de
  los demás cambios: con la beta movida a la vez, el coste intermedio con la
  beta del programa no es el que se usa. Lo
  que no pasa lanza `ValueError`, como en `aplicar`, y la procedencia dice
  «puesto por ti».
- **El panel de referencia se borra antes de escribir.** `ranking.run.guardar`
  convierte el panel a bytes antes de escribir nada y borra el
  `salidas/panel.parquet` viejo nada más crear la carpeta: cualquier fallo deja
  «sin panel», y nunca uno ajeno a las fichas de al lado. Una corrida sin panel
  —con un universo vacío `build_panel` no trae el índice `(ticker, periodo)` y
  `Resultado.panel` es `None`— también borra el de la anterior, porque
  compararía contra unos candidatos que ya no son estos. El ranking no cambia:
  los cuatro ficheros de siempre salen iguales byte a byte.
- **`cargar_panel` trata cualquier fallo como «no hay panel».** Con un fichero
  alterado, pyarrow lanza su `ArrowException` base, `KeyError` o `TypeError`, no
  sólo `ValueError` u `OSError`; como el panel se regenera gratis,
  `referencia.cargar_panel` trata cualquier excepción como ausencia. Se queda
  sólo con sus columnas, y un panel vacío o con filas repetidas también cuenta
  como ausente. Amplía «Si el panel no existe»: vale igual para uno que no se
  puede leer.
- **Los cierres de ejercicio son sólo los años con ancla.** El precio de cada
  trimestre es el del día en que se publicaron sus cuentas, 45 días después del
  cierre de un trimestre y 65 después del de un ejercicio. Cuenta como cierre de
  ejercicio sólo un año con ancla —los ingresos si algún año los tiene, y si no
  el beneficio, que es lo que declara un banco—: el anual de yfinance de RY y TM
  trae además columnas de doce meses móviles con sólo el BPA y el recuento (RY:
  2025-01-31, 04-30 y 07-31; TM: 06-30 y 09-30), y tomadas por cierres esos
  trimestres cotizaban con 65 días en vez de 45. La misma ancla decide qué
  ejercicios entran en los `Fundamentos` anuales.
- **Los plazos de la SEC son una aproximación fuera de ella.** Los 45 y 65 días
  son los del 10-Q y el 10-K; Tencent publicó su ejercicio 77 días después del
  cierre, y su precio queda 12 días antes de la publicación. «Los datos de
  yfinance no tienen fecha de publicación» sigue valiendo para las cifras; la
  fecha de los resultados sí la trae yfinance (`get_earnings_dates`), y N1 no la
  usa.
- **`sec` exige 10-K.** La clase sale del último informe anual (10-K, 20-F o
  40-F) de la ventana reciente de EDGAR, sin enmiendas, y no de «alguna vez
  presentó»: una emisora que pasó del 10-K al 20-F es extranjera hoy. Una salida
  a bolsa que sólo ha presentado 10-Q cae en `sin_sec` y se analiza con
  yfinance hasta su primer 10-K. Donde la tabla de «Las cuatro clases de ticker»
  dice «`sec` (presenta 10-K/10-Q)», manda esta enmienda.
- **El beneficio de yfinance es el de los accionistas comunes, y el EBIT de las
  aseguradoras lleva las ganancias de inversiones.** `Net Income Common
  Stockholders` cuadra con el BPA, y la SEC usa primero `NetIncomeLoss`: para
  los emisores con preferentes, el ROE y el margen neto de las dos fuentes
  difieren entre un 2 y un 8 % (JPM −1,9 %, RY −2,4 %, MFC −8 %), y una
  extranjera queda comparada con pares medidos con la otra línea. Y el `EBIT`
  que entra cuando falta `Operating Income` incluye, en las aseguradoras (MFC,
  BRK-B), las ganancias de las inversiones. Matiza «el ROE de WALMEX y el de MU
  salen de la misma fórmula»: la fórmula es la misma; la línea, no siempre.
- **La prima por riesgo país la decide el país, no la moneda de los estados.**
  `valorar` añade `sin_prima_pais`, verdadero cuando se valora en dólares una
  empresa de fuera de EE. UU.: TSM, que presenta en TWD, pero también NPN.JO o
  TEVA.TA, que presentan en dólares. En pesos nunca, porque el Bono M ya lleva
  el riesgo de México, y sin país conocido no se afirma. `Divisa.a_dict` dice
  aparte si los estados se convirtieron (`estados_convertidos`). Donde la tabla
  de «Divisas» ata la falta de prima a convertir los estados, manda esta
  enmienda. Sale verdadero también en las del S&P 500 domiciliadas fuera (ACN,
  MDT, LIN…), que se valoran igual que en M: cómo se redacta lo decide N2.
- **Un ticker que Yahoo no conoce sale `sin_red`.** Es el contrato de
  `mercado`: desde fuera no se distingue de una conexión que falla (ZZZZQ, en el
  recorrido de N1). La fila de «Errores» que enseña «Yahoo no conoce este
  ticker» no se puede afirmar; N2 rotula «Yahoo no devolvió datos (sin conexión
  o un símbolo que no conoce)».

Donde estas enmiendas contradicen el texto de arriba, mandan ellas. El texto de
arriba no se reescribe, salvo el estado de la cabecera y las dos filas de
«Cachés y frescura» que remiten aquí.
