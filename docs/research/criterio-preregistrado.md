# Criterio pre-registrado — Estudio de señales técnicas

**Congelado el:** 2026-08-05
**Estado:** INMUTABLE

Este documento se commitea antes de escribir cualquier código de medición.
La fecha del commit es la prueba de que los umbrales no se movieron después
de ver los resultados. Modificarlo invalida el estudio.

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

## Enmiendas

Esta sección se añade **por debajo** del criterio original, que no se modifica. El texto de arriba es el que se congeló en el commit `cd4db7e` (2026-08-05) y sigue siendo palabra por palabra el mismo. Cualquiera puede verificarlo con:

```bash
git show cd4db7e:docs/research/criterio-preregistrado.md
```

Cada enmienda registra qué decía el texto original, qué hace el código, por qué difieren, y en qué dirección afecta a la conclusión. Se anotan aquí en vez de editar el criterio precisamente porque el valor de un pre-registro está en poder auditar lo que cambió y cuándo.

### E1 — Unidades de la longitud de bloque del bootstrap (2026-08-06)

**Texto original (§3.5):** «bootstrap por bloques (longitud de bloque 63 días, 1.000 remuestreos)».

**Implementación:** `research/timing.py` usa `BOOTSTRAP_BLOCK = 8`.

**Por qué:** el bootstrap no opera sobre días de calendario, sino sobre el vector de ~500 observaciones emparejadas ordenadas por fecha de decisión. Un bloque se mide en observaciones consecutivas, no en días. Las 500 fechas se muestrean de ~4.100 días hábiles, así que están separadas ~8,2 días en promedio; los 63 días de solapamiento que el texto quiere preservar equivalen a 63 / 8,2 ≈ 8 observaciones. El código implementa la intención del texto en las unidades correctas; el texto original fue ambiguo sobre las unidades, no sobre la sustancia.

**Dirección del efecto:** un bloque de 63 observaciones sobre una muestra de 500 degeneraría el bootstrap (los bloques cubrirían el 12,6% de la muestra cada uno) y *reduciría* artificialmente el error estándar, haciendo la Puerta B más fácil de pasar. La corrección es la conservadora.

### E2 — Qué significa «el día del disparo» (2026-08-06)

**Texto original (§3.5):** «Entrar en la apertura del día siguiente al disparo».

**Implementación:** `research/timing.py` entra en la apertura del **mismo día** en que el disparo está marcado.

**Por qué:** el texto original no dijo si «el disparo» se refiere a la fila ya desplazada o a la fecha del indicador crudo, y las dos lecturas imponen retrasos distintos. Todos los disparos pasan por `_as_of` en `research/signals.py`, que los desplaza un período: el disparo fechado *d* se calcula únicamente con datos hasta el cierre de *d−1*. Entrar en la apertura de *d* ya es un día completo después de la información. Entrar en *d+1* aplicaría el retraso dos veces, y sólo al brazo de la señal — el brazo inmediato nunca lo sufre. Eso no mide timing, mide un handicap que la propia medición inventa.

**Dirección del efecto:** quitar el retraso duplicado hace la Puerta B **más fácil** de pasar. Se registra explícitamente porque es la dirección incómoda: si el estudio acaba concluyendo que el análisis técnico no aporta ventaja, esa conclusión se habrá alcanzado con el listón más bajo, no más alto.

### Estado de los resultados en el momento de estas enmiendas

**Ninguno.** El estudio no se había ejecutado cuando se escribieron E1 y E2. No existía ningún IC, ningún spread, ningún Sharpe ni ningún veredicto — ni siquiera parcial. Ambas enmiendas salieron de revisiones de código sobre datos sintéticos, no de mirar resultados y ajustar el criterio para que salieran mejor. El historial de git lo respalda: el primer documento de veredicto es posterior a este commit.
