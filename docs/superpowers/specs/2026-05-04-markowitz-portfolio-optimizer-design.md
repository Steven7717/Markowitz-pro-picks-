# Markowitz Pro Picks — Especificación de Diseño

**Fecha:** 2026-05-04  
**Estado:** Aprobado  
**Tipo:** Web app (Streamlit)

---

## 1. Objetivo

Aplicación web que recibe una lista de tickers y un horizonte de inversión, y devuelve la distribución óptima de pesos de un portafolio usando el método de máximo Sharpe Ratio de Markowitz, junto con visualizaciones y un reporte exportable.

---

## 2. Stack tecnológico

| Componente | Librería |
|---|---|
| UI / web app | `streamlit` |
| Datos de mercado | `yfinance` |
| Álgebra lineal / estadística | `numpy`, `pandas` |
| Optimización | `scipy.optimize` |
| Gráficas interactivas | `plotly` |
| Exportación PDF | `fpdf2` |
| Exportación CSV/Excel | `openpyxl` |
| Exportación gráficas a PNG | `kaleido` |

---

## 3. Estructura del proyecto

```
Markowits Pro picks/
├── app.py                  # UI Streamlit (solo presentación)
├── data.py                 # Descarga y preparación de precios
├── optimizer.py            # Lógica Markowitz + Sharpe
├── charts.py               # Gráficas con Plotly
├── exporter.py             # Exportación CSV + PDF
├── requirements.txt        # Dependencias
└── .streamlit/
    └── config.toml         # Tema visual oscuro
```

---

## 4. Entradas del usuario

| Campo | Tipo | Descripción |
|---|---|---|
| Tickers | Texto libre | Separados por coma o espacio. Acepta acciones, ETFs, criptomonedas, índices |
| Horizonte de inversión | Selector | Opciones predefinidas (ver tabla abajo). Default: 1 Mes |
| Short selling | Toggle On/Off | Permite pesos negativos en la optimización. Default: Off |
| Peso mínimo por activo | Slider 0–20% | Límite inferior por activo. Default: 0% |
| Peso máximo por activo | Slider 20–100% | Límite superior por activo. Default: 100% |

### Horizontes de inversión y datos históricos

| Horizonte | Historia descargada | Frecuencia de retornos |
|---|---|---|
| 1 Semana | 1 año | Diaria |
| 1 Mes | 2 años | Diaria |
| 3 Meses | 3 años | Semanal |
| 6 Meses | 5 años | Semanal |
| 1 Año | 10 años | Mensual |
| 3 Años | 15 años | Mensual |

---

## 5. Pipeline de datos (`data.py`)

1. Recibe lista de tickers + horizonte
2. Descarga precios de cierre ajustados (`Adj Close`) en batch con un solo llamado a `yfinance`
3. Descarga `^IRX` (T-Bill 3 meses) para tasa libre de riesgo → convierte a tasa equivalente según frecuencia del horizonte
4. Descarga `^GSPC` (S&P 500) como benchmark silencioso para comparación en la frontera eficiente
5. Valida que cada ticker tenga datos suficientes para el horizonte seleccionado
6. Retorna: DataFrame de precios limpios, tasa libre de riesgo escalar, serie de precios del benchmark

---

## 6. Optimización (`optimizer.py`)

### Simulación Monte Carlo
- Genera **10,000 portafolios** con pesos aleatorios (Dirichlet distribution)
- Calcula retorno esperado, volatilidad y Sharpe Ratio para cada portafolio
- Estos puntos forman la nube de la frontera eficiente

### Optimización Max Sharpe
- Función objetivo: maximizar `(retorno_portafolio - tasa_libre_riesgo) / volatilidad_portafolio`
- Solver: `scipy.optimize.minimize` con método `SLSQP`
- Restricciones:
  - Suma de pesos = 1
  - Peso mínimo ≥ límite configurado por usuario
  - Peso máximo ≤ límite configurado por usuario
  - Si short selling Off: todos los pesos ≥ 0
- Retorna: array de pesos óptimos, Sharpe Ratio, retorno esperado anualizado, volatilidad anualizada

### Portafolio Equal Weight
- Calcula métricas del portafolio con pesos iguales (1/N por activo) para comparación

### Contribución al riesgo
- Calcula la contribución marginal al riesgo de cada activo usando la descomposición de la varianza del portafolio

---

## 7. Caché

- `@st.cache_data(ttl=3600)` en la función de descarga de datos de `data.py`
- Si el usuario modifica parámetros de optimización (límites, short selling) sin cambiar tickers ni horizonte, la optimización se recalcula sin volver a llamar a Yahoo Finance

---

## 8. Dashboard UI (`app.py`)

Layout de una sola página con scroll vertical:

### Panel de configuración (siempre visible arriba)
- Input de tickers
- Selector de horizonte (default: 1 Mes)
- Toggle short selling
- Sliders de peso mínimo/máximo
- Botón "▶ Optimizar"

### KPIs (fila de 4 tarjetas)
- Sharpe Ratio (azul/violeta)
- Retorno Anual Esperado (verde)
- Volatilidad Anual (naranja)
- Tasa Libre de Riesgo actual (azul claro)

### Botones de exportación
- "⬇ Descargar CSV" (verde)
- "⬇ Descargar PDF" (naranja)
- Alineados a la derecha, entre KPIs y gráficas

### Alertas contextuales
- ⚠️ Advertencia amarilla si algún activo recibe más del 50% del peso óptimo
- 🔴 Error rojo para tickers inválidos, datos insuficientes, optimización no convergente

### Gráficas (cuadrícula 2×2)
1. **Frontera Eficiente** — nube de 10,000 portafolios coloreada por Sharpe Ratio + punto del portafolio óptimo (estrella) + punto del S&P 500 (triángulo) + punto Equal Weight (círculo)
2. **Distribución de Pesos** — pie chart interactivo con porcentaje de cada activo
3. **Matriz de Correlación** — heatmap con valores numéricos, escala de color divergente (rojo = correlación positiva, azul = negativa)
4. **Óptimo vs. Equal Weight** — barras horizontales agrupadas comparando pesos, retorno esperado y volatilidad entre ambas estrategias

### Tabla de pesos óptimos
Columnas: Ticker · Peso Óptimo (%) · Retorno Esperado (%) · Volatilidad (%) · Contribución al Riesgo (%)

---

## 9. Exportación (`exporter.py`)

### Excel (.xlsx) — botón "Descargar CSV"
- Hoja 1 "Pesos": tabla de pesos óptimos (ticker, peso, retorno esperado, volatilidad, contribución al riesgo)
- Hoja 2 "Métricas": métricas del portafolio (Sharpe, retorno anual, volatilidad anual, tasa libre de riesgo, horizonte, fecha de generación)

### PDF (con `fpdf2`)
- Encabezado: título "Markowitz Pro Picks", fecha, horizonte de inversión
- Sección 1: tabla de métricas clave
- Sección 2: tabla de pesos óptimos
- Sección 3: imágenes PNG de las 4 gráficas (exportadas en memoria con `kaleido`)
- Pie de página: *"Este reporte es de carácter informativo y no constituye asesoramiento financiero. Los resultados pasados no garantizan rendimientos futuros."*

---

## 10. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Ticker inválido o no encontrado en Yahoo Finance | Alerta roja con el ticker fallido; continúa con los válidos |
| Menos de 2 tickers válidos tras filtrar | Bloquea la optimización con mensaje explicativo |
| Datos insuficientes para el horizonte seleccionado | Sugiere reducir el horizonte o cambiar el ticker |
| `^IRX` no disponible | Usa 5.0% anual como fallback; notifica al usuario con alerta amarilla |
| Optimización no converge | Mensaje descriptivo + sugerencia de revisar activos muy correlacionados o ajustar límites de posición |
| Restricciones infactibles (ej. peso_mín × n_activos > 100% o peso_máx × n_activos < 100%) | Alerta roja explicando el conflicto matemático antes de intentar la optimización |
| Sin conexión a internet | Error descriptivo en pantalla |

---

## 11. Funcionalidades incluidas

- [x] Distribución óptima de pesos (Max Sharpe Ratio)
- [x] Tasa libre de riesgo automática desde `^IRX`
- [x] Límites de posición mínimo/máximo por activo
- [x] Comparación vs. S&P 500 en frontera eficiente
- [x] Caché inteligente de datos (TTL 1 hora)
- [x] Advertencia de concentración > 50%
- [x] Toggle short selling
- [x] Exportación CSV + PDF con gráficas
- [x] Comparación Equal Weight vs. Óptimo
- [x] Contribución al riesgo por activo
- [x] Matriz de correlación

---

## 12. Funcionalidades fuera de alcance (v1)

- Portafolios con restricciones sectoriales
- Datos en tiempo real (intraday)
- Backtesting histórico del portafolio
- Autenticación de usuarios / guardado de portafolios
- Optimización multi-objetivo (ej. mínima varianza + máximo Sharpe simultáneo)
