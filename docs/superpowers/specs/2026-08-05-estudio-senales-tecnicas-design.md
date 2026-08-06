# Estudio de valor predictivo de señales técnicas — Especificación de Diseño

**Fecha:** 2026-08-05
**Estado:** Aprobado
**Tipo:** Estudio de investigación offline (no es una feature de la app)
**Sub-proyecto:** D

---

## 1. Objetivo

Determinar si alguna familia de señales técnicas tiene poder predictivo real sobre retornos futuros en el S&P 500, y si mejora el momento de entrada en una canasta de acciones.

El entregable es un **veredicto por familia de señales**, no una funcionalidad. Sólo si alguna familia pasa el criterio se diseña el sub-proyecto E (módulo de timing de entrada).

Un resultado de "ninguna señal tiene ventaja" es un resultado **exitoso**: ahorra construir un módulo que no aporta.

---

## 2. Contexto y decisiones de alcance previas

El objetivo de negocio a largo plazo es un sistema donde uno o más agentes de IA analizan un universo de activos con análisis fundamental, entregan un top 10–15 razonado, el usuario lo aprueba, y esa lista alimenta la herramienta de optimización Markowitz Pro Picks existente.

Ese objetivo se descompuso en cinco sub-proyectos:

| # | Sub-proyecto | Entrega | Depende de |
|---|---|---|---|
| A | Universo + motor de fundamentales | Ingesta determinista de KPIs trimestrales | — |
| B | Agente(s) de análisis y ranking | Top 10–15 con razones trazables | A |
| C | Handoff + gate de aprobación | UI de revisión → tickers al optimizador | B |
| **D** | **Estudio: ¿el técnico aporta ventaja?** | **Veredicto reproducible** | **—** |
| E | Módulo de timing de entrada | Sólo existe si D dice que sí | D |

**Este spec cubre únicamente D.**

### Decisiones ya tomadas

**Enfoque escalonado (Enfoque 3).** El estudio corre primero sobre los miembros actuales del S&P 500, aceptando el sesgo de supervivencia. La dirección del sesgo es conocida: *infla* los resultados. Eso permite un atajo válido:

- Señal **negativa o plana** con el sesgo a favor → conclusión firme, se descarta E sin más trabajo.
- Señal **positiva** → se activa una fase 2 con universo point-in-time para verificar que la ventaja no era el sesgo disfrazado.

Se paga la precisión sólo en el escenario donde importa.

**Reutilización de herramientas.** Se investigaron las alternativas del ecosistema. Se reutiliza `alphalens-reloaded` para el análisis de factores (IC, quintiles, decaimiento). Se descarta usar TradingAgents o ai-hedge-fund como dependencia: producen señales buy/sell por ticker en lugar de rankings de candidatos, son no deterministas, y no tienen evidencia publicada de rentabilidad.

**Los LLM quedan fuera de D por diseño.** Los modelos de lenguaje ya conocen lo que ocurrió con estas acciones en su periodo de entrenamiento, lo que contamina cualquier backtest sobre datos históricos (ver *Look-Ahead-Bench*, arXiv 2601.13770). D mide señales deterministas y reproducibles, y es por tanto la única parte del sistema completo que admite validación honesta.

---

## 3. Criterio pre-registrado

Esta sección se congela y se commitea **antes** de escribir código de medición. La fecha del commit es lo que hace creíble el resultado: demuestra que los umbrales no se movieron después de ver los números.

### 3.1 Familias de señales

| Familia | Señal | Definición | Disparo (para Puerta B) |
|---|---|---|---|
| **F1** Momentum medio plazo | `mom_12_1` | Retorno acumulado de t−252 a t−21 | Señal en el quintil superior del universo ese día |
| **F2** Reversión corto plazo | `rev_1m` | Retorno de los últimos 21 días, con signo invertido | Señal en el quintil superior del universo ese día |
| **F3** Timing de entrada | `rsi_14` | RSI de 14 periodos, con signo invertido (sobreventa = señal alta) | RSI < 30 |
| | `macd_cross` | Histograma MACD(12,26,9) | Histograma cruza de negativo a positivo |
| | `dist_sma200` | (Precio − SMA200) / SMA200 | Precio cruza por encima de la SMA200 |
| | `breakout_52w` | Precio / máximo de 252 días | Precio supera el máximo de 252 días |
| | `bollinger_pos` | Posición en la banda de Bollinger(20, 2σ), invertida | Precio toca o perfora la banda inferior |

F1 funciona además como **referencia positiva**: es la señal basada en precio mejor documentada de la literatura. Si el harness no la detecta, el harness está roto y ningún otro resultado es interpretable.

F1 y F2 apuntan en direcciones opuestas a propósito. Medirlas por separado evita que se cancelen y produzcan un falso "el técnico no sirve".

### 3.2 Controles

| Control | Naturaleza | Definición | Resultado esperado |
|---|---|---|---|
| **Negativo** | Señal (vive en `signals.py`) | Señal aleatoria uniforme, con la misma rotación media que la señal evaluada, semilla fija | Debe **fallar** el criterio. Si lo pasa, el criterio está mal calibrado y hay que corregirlo antes de creer cualquier otro resultado. |
| **Pasivo** | Línea base (vive en `report.py`) | Equal-weight del universo elegible, comprar y mantener | Comparación económica de referencia |
| **Oráculo** | Sólo fixture de test | Señal construida como el retorno futuro real | IC ≈ 1. Demuestra que el medidor funciona. Espía a propósito, así que **queda excluido del test de truncamiento**. |

`signals.py` produce por tanto **8 series de señal**: las 7 evaluadas más el control negativo. El pasivo es una línea base, no una señal; el oráculo no sale nunca del código de test.

### 3.3 Grilla

**7 señales × 4 horizontes de retorno futuro (1, 5, 21, 63 días de negociación) = 28 tests.**

La grilla es fija. **No hay ajuste de parámetros**: los periodos de los indicadores (14, 12/26/9, 200, 252, 20/2σ) son los valores convencionales y no se optimizan.

Si tras el estudio se quiere explorar otros parámetros, eso constituye una fase exploratoria separada, etiquetada como tal, cuyos resultados **no cuentan como evidencia** y requerirían su propia validación fuera de muestra.

### 3.4 Puerta A — estadística

Una señal pasa la Puerta A en un horizonte dado si cumple **las cuatro** condiciones:

1. **IC medio ≥ 0.03.** El IC es la correlación de rangos de Spearman entre el valor de la señal en la fecha *t* y el retorno futuro sobre el horizonte *h*, calculada de forma transversal en cada fecha y promediada sobre todas las fechas.
2. **t-stat del IC ≥ 2 y supervivencia a la corrección por multiplicidad.** Con horizontes de más de un día, las observaciones de IC se solapan y están autocorrelacionadas; el error estándar se ajusta con **Newey-West con lag = h − 1**. El t-stat ajustado debe alcanzar 2, y además el p-value correspondiente debe sobrevivir **Benjamini-Hochberg con FDR = 10%** aplicado al conjunto completo de los 28 p-values. Son dos condiciones acumulativas, no una sola.
3. **Spread quintil 5 − quintil 1 positivo neto de costes.** Cinco carteras por valor de señal, equal-weight dentro de cada quintil, rebalanceadas a la frecuencia del horizonte.
4. **Persistencia:** las condiciones 1 y 3 se sostienen en al menos **3 de los 4 sub-periodos**.

Con 28 tests, aproximadamente 1.4 pasarían el corte por puro azar sin la corrección BH. Por eso la corrección no es opcional.

### 3.5 Puerta B — utilitaria

Mide directamente la pregunta de negocio: *¿esperar a que la señal dispare mejora la entrada frente a entrar de inmediato?*

**Protocolo:**

- Se muestrean **500 fechas de decisión** al azar del periodo de estudio (semilla fija y documentada).
- En cada fecha se toma una canasta de **20 tickers** al azar del universo elegible en esa fecha.
- **Brazo inmediato:** entrar equal-weight en la apertura del día siguiente. Mantener 63 días de negociación.
- **Brazo señal:** para cada ticker, esperar hasta **W = 10 días hábiles** a que la señal dispare. Entrar en la apertura del día siguiente al disparo. **Si no dispara dentro de W días, se entra igualmente el día W.** Mantener 63 días desde la entrada.
- Métrica: Sharpe anualizado de la distribución de retornos de canasta de cada brazo.

La regla de entrada forzosa al día W es deliberada: comparar sólo las entradas que llegaron a disparar seleccionaría a posteriori los casos favorables e inventaría una ventaja inexistente.

**Condición de aprobación:** la mejora de Sharpe del brazo señal sobre el inmediato debe superar su propio error estándar.

Sobre el cálculo de ese error estándar: las 500 fechas de decisión se muestrean de ~4.100 días de negociación con horizontes de 63 días, así que las canastas se solapan fuertemente y las observaciones no son independientes. La fórmula de Lo (2002) que implementa `validation.sharpe_standard_error` supone independencia y subestimaría el error en estas condiciones. Por eso el error estándar de la Puerta B se calcula por **bootstrap por bloques** (longitud de bloque 63 días, 1.000 remuestreos), y `sharpe_standard_error` se usa únicamente como contraste de cordura: si el bootstrap devuelve un error *menor* que la fórmula i.i.d., hay un fallo en la implementación.

### 3.6 Veredicto

Una señal tiene ventaja **sólo si pasa ambas puertas**. Pasar A sin B significa que rankea bien pero no se traduce en mejor timing. Pasar B sin A significa que el resultado no se distingue del ruido.

### 3.7 Periodo y sub-periodos

Periodo total: **2010-01-01 a 2026-06-30**.

| Sub-periodo | Rango | Régimen |
|---|---|---|
| P1 | 2010-01-01 → 2013-12-31 | Expansión cuantitativa |
| P2 | 2014-01-01 → 2017-12-31 | Baja volatilidad |
| P3 | 2018-01-01 → 2021-12-31 | Selloff de 2018 + COVID |
| P4 | 2022-01-01 → 2026-06-30 | Subida de tipos + recuperación |

Sin solapamiento. Una señal que sólo funciona en un régimen no pasa.

### 3.8 Costes

**Caso base: 10 puntos básicos por operación ida y vuelta.** Análisis de sensibilidad a **5 bps** y **25 bps**.

F3 tiene rotación alta por diseño, así que los costes son la variable con más capacidad de decidir su veredicto. El reporte debe presentar retorno bruto y neto por separado, junto con la rotación medida de cada señal.

---

## 4. Arquitectura

### 4.1 Ubicación

Paquete `research/` dentro del repositorio actual. Motivos:

- Reutiliza `validation.sharpe_standard_error` como contraste de cordura en la Puerta B (sección 3.5).
- Mantiene el historial del proyecto junto.
- El sub-proyecto E, si llega a existir, nacería aquí.

Se ejecuta **offline como script** (`python -m research.run`). Nunca dentro de Streamlit.

### 4.2 Módulos

```
research/
├── __init__.py
├── universe.py       # Quiénes son los miembros del universo
├── loader.py         # Panel OHLCV con caché en disco
├── signals.py        # Las 7 señales evaluadas + el control aleatorio
├── costs.py          # Costes de transacción y rotación
├── evaluation.py     # Puerta A: IC, quintiles, sub-periodos, BH
├── timing.py         # Puerta B: entrar ya vs esperar señal
├── report.py         # Aplica ambas puertas y emite veredicto
├── run.py            # Punto de entrada del estudio
└── data/
    └── sp500_members_2026-08-05.csv   # Snapshot congelado, commiteado
```

Cada módulo tiene una responsabilidad única y se puede entender y probar por separado.

### 4.3 Interfaces

| Módulo | Función principal | Contrato |
|---|---|---|
| `universe.py` | `sp500_members() -> list[str]` | Lee el snapshot congelado del CSV commiteado. No consulta la red: la reproducibilidad del estudio depende de que el universo no cambie entre corridas. |
| `loader.py` | `load_ohlcv(tickers, start, end) -> tuple[pd.DataFrame, CoverageReport]` | Panel con columnas MultiIndex (campo, ticker). El reporte de cobertura lista tickers excluidos y el motivo. |
| `signals.py` | `SIGNALS: dict[str, Callable]` | 8 entradas. Cada señal: `(panel) -> pd.DataFrame` indexado por fecha, columnas tickers, **ya desplazada**. |
| `costs.py` | `apply_costs(returns, turnover, bps) -> pd.Series` | Retornos netos. |
| `evaluation.py` | `evaluate(signal, forward_returns, horizon) -> GateAResult` | IC medio, t-stat Newey-West, p-value, spread por quintil, resultados por sub-periodo, rotación. |
| `timing.py` | `compare_entry_timing(signal, panel, seed) -> GateBResult` | Sharpe de ambos brazos, diferencia, y error estándar por bootstrap por bloques. |
| `report.py` | `verdict(gate_a_results, gate_b_results) -> dict` | Veredicto por señal y por familia; genera el markdown final. |

El registro `SIGNALS` replica el patrón de `_STRATEGIES` en `optimizer.py:317`, de modo que añadir una señal sigue el mismo procedimiento que ya existe para añadir una estrategia de optimización.

### 4.4 Por qué `data.py` no se reutiliza

Dos bloqueos:

1. `fetch_market_data` está decorada con `@st.cache_data`, lo que acopla la descarga a Streamlit. El estudio corre fuera de la app.
2. Descarta OHLCV y conserva sólo `Close` (`data.py:73`). RSI, Bollinger y breakouts necesitan High, Low y Volume.

`loader.py` es código nuevo. **`data.py` no se modifica**: la app existente sigue funcionando sin cambios.

---

## 5. Flujo de datos

```
universe.py          → lista de tickers (snapshot congelado)
        ↓
loader.py            → panel OHLCV + reporte de cobertura
        ↓                     (caché parquet en research/.cache/)
signals.py           → 8 DataFrames (7 señales + control aleatorio), ya desplazados
        ↓
        ├──→ evaluation.py  → Puerta A por señal × horizonte
        └──→ timing.py      → Puerta B por señal
                    ↓
report.py            → veredicto + documento markdown
```

---

## 6. Validez

### 6.1 Look-ahead: tres defensas

Es el modo de fallo que arruina un estudio así sin que nadie lo note.

1. **Convención de desplazamiento.** Toda señal devuelve valores ya desplazados: el valor en la fecha *t* usa exclusivamente información disponible al cierre de *t−1*.
2. **Retardo de ejecución.** La entrada se simula en la **apertura de t+1**, no en el cierre de *t*.
3. **Test de truncamiento.** Para cada señal: calcularla sobre la historia completa, calcularla de nuevo sobre la historia truncada en *t*, y verificar que el valor en *t* es idéntico. Si cambia al añadir datos posteriores, la señal está espiando. Es una propiedad verificable automáticamente, no una inspección visual, y cubre las 8 señales del registro sin trabajo adicional por señal. El oráculo queda fuera: espía por definición, y su función es la contraria — demostrar que el medidor detecta información futura cuando la hay.

Los controles refuerzan la verificación desde el otro extremo: una señal oráculo construida como el retorno futuro real debe producir IC ≈ 1 (demuestra que el medidor funciona), y la señal aleatoria debe producir IC ≈ 0 (demuestra que no hay fuga de información en el pipeline).

### 6.2 Sesgo de supervivencia

Presente y **no corregido en esta fase**, por decisión explícita (sección 2). El reporte final debe nombrarlo en su sección de limitaciones, junto con su dirección conocida (infla resultados) y la regla de escalado a fase 2.

Atenuante específico de este caso de uso: el técnico se aplicaría sobre una lista que el análisis fundamental ya consideró sólida — empresas que no se espera que quiebren. El sesgo de supervivencia y la condición de despliegue apuntan en la misma dirección, lo que hace el test más representativo aquí que para un fondo cuantitativo genérico. Atenúa el problema; no lo elimina.

### 6.3 Multiplicidad

28 tests pre-registrados, corrección Benjamini-Hochberg a FDR 10% (sección 3.4).

### 6.4 Costes

Tres niveles de sensibilidad (sección 3.8). Retorno bruto, retorno neto y rotación se reportan por separado para cada señal.

---

## 7. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Ticker con historia insuficiente (< 252 observaciones antes de su primera fecha de evaluación) | Excluido del universo elegible, **contado y listado** en el reporte de cobertura. Nunca desaparece en silencio. |
| Fallo de descarga de yfinance | 3 reintentos con backoff exponencial. Los fallos permanentes se registran en el reporte de cobertura como tales, distinguidos de las exclusiones por historia corta. |
| Descarga masiva (≈500 tickers × 16 años) | Lotes de ~50 tickers. Caché parquet en `research/.cache/` (gitignored) para que las corridas posteriores no dependan de la red. |
| Splits y dividendos | `auto_adjust=True`, consistente con el comportamiento actual de `data.py`. |
| Compañías deslistadas | Ausentes por construcción en esta fase. Documentado como la limitación principal del estudio. |
| Fecha sin suficientes tickers elegibles para formar quintiles | La fecha se omite del cálculo de IC y se cuenta en el reporte. |

---

## 8. Plan de tests

Desarrollo guiado por tests, siguiendo el estilo del repositorio: tests que describen comportamiento observable, no implementación.

| Archivo | Cubre |
|---|---|
| `tests/test_research_universe.py` | El snapshot se lee del CSV commiteado; formato y recuento; no hay llamadas de red |
| `tests/test_research_loader.py` | Acierto y fallo de caché; troceado en lotes; exclusión por historia corta; el reporte de cobertura cuadra con los tickers realmente devueltos; los fallos de red se distinguen de las exclusiones |
| `tests/test_research_signals.py` | Valores conocidos sobre series sintéticas (RSI de una rampa monótona, momentum de una recta, Bollinger de una serie constante); **test de truncamiento sobre las 8 señales del registro**; el oráculo se excluye y tiene su propio test que verifica que sí espía |
| `tests/test_research_costs.py` | Aplicar coste reduce el retorno en la cantidad esperada dada la rotación; coste cero es identidad |
| `tests/test_research_evaluation.py` | Señal oráculo → IC ≈ 1; señal aleatoria → IC ≈ 0; Newey-West amplía el error estándar cuando hay solape; BH correcto sobre p-values conocidos; los sub-periodos particionan sin solape ni huecos |
| `tests/test_research_timing.py` | La entrada forzosa al día W ocurre cuando la señal no dispara; ambos brazos mantienen el mismo horizonte; la semilla fija hace la corrida reproducible |
| `tests/test_research_report.py` | Tabla de casos: el veredicto exige **ambas** puertas; una señal que pasa A y falla B es rechazada, y viceversa |

Test opcional adicional, siguiendo el patrón ya establecido en `requirements.txt` con scikit-learn: contrastar los indicadores implementados nativamente contra `pandas-ta-classic` como referencia, omitiéndose si la librería no está instalada.

---

## 9. Dependencias

| Paquete | Uso | Obligatoria |
|---|---|---|
| `alphalens-reloaded` | IC, retornos por quintil, decaimiento de factor | Sí |
| `pyarrow` | Caché parquet del panel OHLCV | Sí |
| `pandas-ta-classic` | Referencia cruzada de los indicadores en tests | Sólo tests |

`numpy`, `pandas`, `scipy` y `yfinance` ya están en el proyecto.

**Los 5 indicadores de F3 se implementan nativamente** (≈60 líneas de pandas) en lugar de depender de una librería de indicadores en el camino crítico. Da control total sobre la disciplina de desplazamiento y sigue el patrón que el repositorio ya usa con Ledoit-Wolf.

**Se descarta `vectorbt`.** Con 7 señales y una grilla fija no hace falta un motor vectorizado con numba, y evita arrastrar una dependencia pesada. Si una fase exploratoria posterior necesita barridos grandes de parámetros, se reevalúa entonces.

---

## 10. Entregables y orden de trabajo

1. **Commitear el criterio pre-registrado** en `docs/research/criterio-preregistrado.md` (contenido de la sección 3). Antes de escribir código de medición.
2. Construir los módulos con TDD.
3. Correr el estudio **una vez**.
4. Publicar `docs/research/<fecha-de-la-corrida>-veredicto-senales-tecnicas.md`: tabla de veredictos por señal y familia, tear sheets de alphalens, rotación y costes, y una sección de limitaciones que nombre explícitamente el sesgo de supervivencia, el rango de costes evaluado y el periodo cubierto.

### Ramificación posterior

- **Alguna señal pasa ambas puertas** → activar fase 2 (universo point-in-time reconstruido) para confirmar que la ventaja no es sesgo de supervivencia. Sólo tras confirmarla se diseña E.
- **Ninguna señal pasa** → E se descarta. El trabajo continúa con A, B y C sin componente de análisis técnico.

---

## 11. Fuera de alcance

Explícitamente **no** forma parte de este sub-proyecto:

- Optimización o barrido de parámetros de los indicadores
- Señales intradía, de volumen exótico, de order flow o de microestructura
- Modelos de machine learning
- Universo point-in-time (es la fase 2, condicional al resultado)
- Cualquier integración con la app Streamlit
- Cualquier componente de LLM o agente (queda en B, y por las razones de la sección 2 no admite este tipo de validación)
- Modificaciones a `data.py`, `optimizer.py`, `estimators.py`, `validation.py`, `charts.py` o `exporter.py`

---

## 12. Criterio de éxito del sub-proyecto

El estudio es exitoso si entrega un **veredicto reproducible** — no si encuentra una señal ganadora.

Concretamente:

- El criterio se commiteó antes de correr el estudio.
- El control aleatorio falló el criterio.
- La referencia positiva (momentum 12-1) se comportó de forma coherente con la literatura.
- Los tests de truncamiento pasan para las 8 señales del registro.
- Una segunda corrida desde la caché reproduce los mismos números.
- El documento final permite a un tercero entender qué se midió, con qué supuestos, y con qué limitaciones.
