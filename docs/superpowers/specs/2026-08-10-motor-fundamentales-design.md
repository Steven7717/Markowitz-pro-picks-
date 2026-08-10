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
obtiene llamando a `research.loader.load_ohlcv` sobre los mismos tickers, y toma
el cierre de la fecha de presentación de cada trimestre — no el cierre de hoy,
que mezclaría un precio actual con unos fundamentales de hace tres años. El
número de acciones sí sale del XBRL. Un ticker sin precio en esa fecha recibe sus
cuatro KPIs de valoración ausentes, y los otros doce normales.

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
