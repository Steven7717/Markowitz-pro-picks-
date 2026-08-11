# Sub-proyecto A — Universo + motor de fundamentales

**Fecha:** 2026-08-10
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Ingesta determinista de KPIs fundamentales trimestrales para un universo
configurable de empresas. Sin IA. Alimenta al sub-proyecto B, que rankeará
candidatos, y a través de él al optimizador que ya existe.

La app Streamlit y el paquete `research/` no se tocan.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Profundidad histórica | 12 trimestres | Menos no permite calcular tendencias, y B necesita razonar sobre trayectoria, no sobre una foto |
| Fuente | edgartools (XBRL de SEC) | Gratis, sin API key, autoritativa, y trae fecha de presentación |
| Ratios de mercado | Precios propios | Los calcula el motor con los precios que ya baja `research/loader.py` |
| Universo | S&P 500 congelado + lista arbitraria | La lista desde noticias es problema de B; A sólo acepta lo que le den |
| Sectores | GICS Sector (11 grupos) | Medido: SIC deja 87 empresas solas en su grupo, GICS ninguna |
| Fuera del índice | KPIs sí, z-score ausente | Nunca imputar; se decide con casos reales delante |
| Refresco de caché | Explícito, no automático | Igual que el snapshot del universo: cambiar los números es un acto revisable |

### La medición que decidió la taxonomía

Sobre las 502 empresas del S&P 500 cuyo SIC resolvió contra EDGAR:

| Taxonomía | Grupos | Mediana | En grupos de 1 | En grupos ≤5 |
|---|---:|---:|---:|---:|
| **GICS Sector** | 11 | 34 | **0** | **0** |
| GICS Sub-Industry | 127 | 3 | 27 (5,4%) | 245 (48,8%) |
| SIC 2 dígitos | 54 | 5 | 6 (1,2%) | 111 (22,1%) |
| SIC 4 dígitos | 183 | 2 | 87 (17,3%) | 308 (61,4%) |

El z-score de una empresa contra un grupo que sólo la contiene a ella vale 0 por
construcción. Con SIC de 4 dígitos eso son 87 ceros indistinguibles de "esta
empresa es exactamente el promedio de su sector".

Descartadas en el camino, con su razón:

- **SIC**, pese a clasificar mejor de lo que se le atribuye: distingue AAPL
  (3571, computadoras) de MSFT (7372, software) de NVDA (3674, semiconductores),
  donde GICS mete a las tres en un solo balde. Pierde por fragmentación, no por
  imprecisión. Sus errores reales son de desactualización: IBM figura como
  "Computer & Office Equipment" y NFLX como "Services-Video Tape Rental".
- **Crosswalk SIC→GICS**: la traducción es ambigua en varios rangos — SIC 28
  mezcla farmacéuticas con químicas industriales y a 2 dígitos no se separan — y
  sería código escrito a mano sin referencia contra la cual validarlo.
- **yfinance como fuente**: no publica la fecha en que cada cifra estuvo
  disponible, así que no permite verificar ausencia de look-ahead. Queda como
  contraste externo en test opcional.
- **OpenBB**: AGPLv3, y sus proveedores buenos piden API key de pago.

## Arquitectura

Paquete nuevo `fundamentals/`, hermano de `research/`. El estudio está cerrado;
esto es un componente de producto.

```
fundamentals/
├── universe.py    resolución de universo → lista de tickers
├── concepts.py    KPI → cadena ordenada de conceptos XBRL
├── fetch.py       identidad SEC, descarga, caché parquet, CoverageReport
├── kpis.py        cálculo de los 16 KPIs sobre el panel crudo
├── sectors.py     carga de GICS y z-score dentro del sector
└── run.py         orquestación
scripts/bootstrap_sectors.py   genera el fichero de sectores (una sola vez)
fundamentals/data/sectores_<fecha>.csv
```

### `universe.py`

`resolve(source)` donde `source` es `"sp500"` — delega en
`research.universe.sp500_members` — o una lista de tickers. Sin estado.

### `concepts.py`

Cada renglón financiero se declara como una **cadena ordenada de conceptos
XBRL**: se prueba el primero, si falta se pasa al siguiente, y si ninguno
aparece el valor queda ausente. Nunca cero.

Esto existe porque los emisores no usan las mismas etiquetas: Apple declara
ingresos como `RevenueFromContractWithCustomerExcludingAssessedTax` y otras
empresas usan `Revenues`. Es una tabla de datos, no lógica, y por eso se puede
testear renglón por renglón.

### `fetch.py`

Descarga de hechos por ticker con `periods=12, annual=False`. Requiere
`set_identity()` por la política de User-Agent de SEC; el contacto se lee de
variable de entorno, nunca hardcodeado, siguiendo lo que ya hace
`scripts/bootstrap_universe.py`.

La caché replica el patrón ya probado de `research/loader.py`:

- clave con `hashlib.md5`, no `hash()` — Python aleatoriza el hash de strings
  entre procesos y la caché fallaría en cada corrida nueva
- escritura a `.tmp` y rename atómico, para que ningún lector vea un fichero
  a medias
- si la lectura del parquet falla, se borra el fichero y se trata como fallo de
  caché, en vez de envenenar todas las corridas siguientes

Un fichero por ticker, no uno por universo: los trimestrales llegan escalonados,
así que una caché con clave sobre el universo entero se invalidaría completa cada
vez que una sola empresa presenta.

El refresco es un parámetro explícito, apagado por defecto. Una caché que se
refrescara sola cambiaría los números entre dos corridas sin que nadie lo pida.

### `kpis.py`

Funciones puras del panel crudo a los 16 KPIs:

| Grupo | KPIs |
|---|---|
| Rentabilidad | margen bruto, operativo y neto; ROE; ROIC |
| Crecimiento (YoY) | ingresos, BPA, flujo de caja libre |
| Solidez | deuda neta/EBITDA, cobertura de intereses, razón corriente |
| Calidad del beneficio | margen de FCF, FCF/beneficio neto |
| Valoración | P/E, EV/EBITDA, P/FCF, P/B |

Cada división lleva guarda explícita con umbral, y cada guarda lleva su test con
entrada degenerada. En D hubo una guarda de varianza que nunca disparaba y
devolvía `t = 3.6e16`; el defecto era invisible leyendo el código y sólo apareció
al ejecutarlo con una serie constante.

Los cuatro KPIs de valoración necesitan precio y no salen del XBRL. `run.py` los
obtiene llamando a `research.loader.load_ohlcv` sobre los mismos tickers. El
número de acciones sí sale del XBRL. Un ticker sin precio en esa fecha recibe sus
cuatro KPIs de valoración ausentes, y los otros doce normales.

**El precio se toma en la fecha en que los resultados se hicieron públicos, no al
cierre del trimestre.** Un trimestre que cierra el 31 de marzo no se conoce hasta
que el 10-Q se presenta, semanas después; cotizar el múltiplo al 31 de marzo usa
cifras que el mercado todavía no tenía, que es look-ahead. Tampoco se usa el
precio de hoy, que emparejaría una cotización actual con fundamentales de hace
tres años y produciría un múltiplo que nunca existió.

Si edgartools expone la fecha de presentación real, se usa. Si no, se aproxima
con cierre de trimestre + 45 días, apenas por encima del plazo de 40 días que la
SEC concede a los grandes emisores. **La aproximación yerra hacia tarde a
propósito:** un precio posterior a la publicación es sólo información algo
rancia, mientras que uno anterior es información que nadie tenía.

Un trimestre necesita su homólogo de hace cuatro trimestres para tener KPI de
crecimiento. Los tres trimestres más antiguos de cada empresa, y cualquiera cuyo
homólogo falte, quedan con los tres KPIs de crecimiento ausentes. No se
extrapola.

### `sectors.py`

Carga el fichero de sectores y expone `zscore_within_sector()` como función pura,
separada de la ingesta. Una empresa sin sector conocido recibe z-score ausente,
declarado en el reporte de cobertura.

`scripts/bootstrap_sectors.py` genera el fichero desde la tabla de Wikipedia que
`bootstrap_universe.py` ya descarga y descarta.

**El snapshot de D no se toca.** `research/data/sp500_members_2026-08-05.csv` es
de lo que depende la reproducibilidad del estudio terminado; regenerarlo hoy
cambiaría la membresía. Los sectores van en un fichero nuevo y aparte.

## Flujo

```
universo → hechos crudos (caché) → KPIs por trimestre → z-scores sectoriales
        → panel + reporte de cobertura
```

Salida: un DataFrame indexado por `(ticker, trimestre_fiscal)` con los 16 KPIs,
más una tabla de metadatos con `cik`, `sic`, `industria`, `sector_gics` y
`fecha_de_presentación`.

## Errores

Nada se imputa y nada se descarta en silencio. El `CoverageReport` —análogo al de
`research/loader.py`— declara, por KPI y por ticker, si el valor falta por
concepto XBRL ausente, por historia corta, por fallo de descarga, por sector
desconocido, por CIK no resuelto o por falta de precio.

"Historia corta" significa menos de 5 trimestres declarados: por debajo de eso no
hay ni un solo KPI de crecimiento y la empresa aporta sólo niveles. Entra igual
al panel, marcada.

Una empresa con 3 de 16 KPIs entra al panel con 13 ausentes explícitos. No se
elimina.

La resolución ticker→CIK no puede asumirse total: al medir, **AEP no aparece en
el mapa oficial de SEC**. Una de 503, pero suficiente para que el fallo tenga que
contarse y atribuirse en vez de propagarse.

## Tests

Aplicando los estándares que hicieron creíble el resultado de D:

- **Control negativo.** Empresa sintética con estados financieros inventados y los
  16 KPIs calculados a mano. Si alguno no coincide con su valor esperado, el
  motor está mal.
- **Contraste externo opcional.** Los KPIs contra los que publica yfinance, en un
  test que se omite solo si no está instalado — mismo patrón que ya se usa con
  Ledoit-Wolf/scikit-learn y con RSI/pandas-ta-classic.
- **Guardas degeneradas.** Patrimonio ~0, EBITDA negativo, ingresos 0, deuda 0.
- **Caché.** Parquet truncado a propósito, verificando que se trata como fallo y
  no contamina la corrida siguiente.
- **Cadena de conceptos.** Que el primer concepto gana; que el segundo entra si
  falta el primero; que sin ninguno el resultado es ausente y no cero.
- **Cobertura.** Que un ticker sin CIK, uno sin sector y uno sin historia
  suficiente aparecen cada uno en su categoría del reporte.

## Fuera de alcance

- Ranking de candidatos y cualquier uso de LLM — eso es B.
- Universo point-in-time. D concluyó que no hace falta, y B no admite backtest
  honesto de todos modos: los LLM ya conocen lo que pasó con estas acciones
  (Look-Ahead-Bench, arXiv 2601.13770).
- Universos multi-capitalización.
- Cuántas posiciones debe tener el portafolio final. Sigue pendiente para B, y
  interactúa con que Markowitz concentra pesos: 15 candidatos no son 15
  posiciones.

---

## Enmienda 1 — 2026-08-11: la API real de edgartools

El texto de arriba queda intacto. Esto anota en qué difiere el código, por qué, y
en qué dirección afecta a lo que el motor entrega.

Se escribió antes de instalar edgartools. Al ejecutarlo por primera vez —el spike
que el plan puso como primera tarea justamente para esto— cinco supuestos
resultaron falsos.

### Qué decía el diseño y qué hace el código

**1. La fuente de los estados financieros.** El diseño asumía
`income_statement(periods=12, annual=False)`. Ese método devuelve 18 columnas, de
las cuales 6 son metadatos, y etiqueta los periodos por **trimestre fiscal**
(`'Q3 2026'`) en vez de por fecha. El código usa `facts.to_dataframe()`, que
entrega la tabla larga de hechos con `period_start` y `period_end` reales.

**2. La alineación entre empresas.** Consecuencia de lo anterior, y el defecto más
serio que se evitó. El año fiscal de Apple termina en septiembre y el de
JPMorgan en diciembre: su `Q3 2026` no es el mismo periodo natural. Agrupar por
esa etiqueta para el z-score habría comparado trimestres distintos y producido
números plausibles y falsos. El código agrupa por **trimestre natural** derivado
de `period_end`.

**3. Un módulo nuevo, `panel.py`.** El diseño no previó el trabajo de convertir la
tabla larga en panel trimestral. Son cuatro operaciones que no estaban:

- filtrar por duración, porque cada presentación repite el mismo renglón para el
  trimestre, el semestre, los nueve meses y el año — confundirlos multiplicaría
  cualquier magnitud de flujo;
- deduplicar reexpresiones, quedándose con la versión más reciente. Apple tiene
  72 filas de ingresos trimestrales, 25 de ellas repitiendo concepto y fecha;
- **derivar el cuarto trimestre**, que nadie presenta porque va dentro del 10-K
  como cifra anual. Sin esto, uno de cada cuatro trimestres quedaría vacío en
  todos los KPIs de flujo. Se calcula restando los tres trimestres al año, y sólo
  si los tres están: con dos daría un Q4 inflado que parece un dato real;
- restringir los instantes de balance a la rejilla de trimestres, porque los 10-K
  traen instantes en fechas sueltas que inventarían trimestres falsos.

**4. Son 17 KPIs, no 16.** La tabla del diseño lista 5 de rentabilidad, 3 de
crecimiento, 3 de solidez, 2 de calidad del beneficio y 4 de valoración. Suman
17. El «16» era una suma mal hecha, y lo atrapó un test que comparaba el recuento
contra el número prometido. **El conjunto de KPIs no cambió.**

**5. La fecha de publicación sigue siendo aproximada.** El diseño decía que si
edgartools exponía la fecha de presentación real se usaría. No la expone en esta
tabla, así que se mantiene el desfase de 45 días sobre `period_end` — pero ahora
anclado a una fecha natural real en vez de a una etiqueta fiscal.

### En qué dirección afecta a la conclusión

Ninguno de los cinco cambia lo que el motor promete entregar. Los tres primeros
corrigen defectos que habrían producido números incorrectos sin avisar; el cuarto
es aritmética; el quinto deja la aproximación donde ya estaba, mejor anclada.

Un hallazgo sí matiza el alcance, y hacia abajo: **las financieras salen mucho más
vacías de lo previsto.** JPMorgan resuelve 9 de las 17 líneas contables. No es un
fallo de las cadenas sino de cómo reportan los bancos — no publican coste de
ventas, ni beneficio operativo, ni activo o pasivo corriente, y dejaron de
etiquetar `Revenues` trimestral en 2014. El reporte de cobertura lo declara
empresa por empresa, que era exactamente el propósito de tenerlo.

Decisión relacionada, tomada en contra de la cobertura: el beneficio antes de
impuestos **no** entra como alternativa del beneficio operativo. Subiría la
cobertura de 13 a 17 de cada 20 empresas, pero ya tiene los intereses restados y
haría que la cobertura de intereses fuese el cociente de otra magnitud. Un hueco
declarado vale más que un número plausible y equivocado.
