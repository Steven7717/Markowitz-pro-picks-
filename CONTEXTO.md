# Contexto del proyecto — para retomar en una sesión nueva

**Última actualización:** 2026-08-06
**Rama:** `master` · **Tests:** 290 pasando (`pytest tests/ -q`)

---

## ⚠️ Lo primero: hay trabajo sin commitear que se puede perder

`git status` muestra archivos **sin trackear** que contienen mejoras reales al optimizador y que no están en ningún commit:

```
?? estimators.py          Ledoit-Wolf + James-Stein (shrinkage)
?? validation.py          walk-forward out-of-sample + error estándar del Sharpe
?? tests/test_estimators.py
?? tests/test_strategies.py
?? tests/test_validation.py
 M app.py, optimizer.py, charts.py, data.py, exporter.py, y sus tests
```

Un `git clean` o un checkout descuidado los borra. **Antes de cualquier otra cosa, commitéalos.** El estudio del sub-proyecto D depende de `validation.py`, así que el repo no está completo sin ellos.

---

## Qué es este proyecto

**Markowitz Pro Picks** es una app Streamlit que recibe una lista de tickers y devuelve la asignación óptima de pesos (máximo Sharpe, mínima varianza, paridad de riesgo), con validación out-of-sample y exportación a PDF/Excel.

El objetivo mayor es construir, **aguas arriba de esa app**, un sistema donde uno o más agentes de IA analicen un universo de activos con análisis fundamental, entreguen un top 10–15 razonado, el usuario lo apruebe, y esa lista alimente el optimizador.

## Descomposición en sub-proyectos

| # | Sub-proyecto | Entrega | Estado |
|---|---|---|---|
| A | Universo + motor de fundamentales | Ingesta determinista de KPIs trimestrales | **pendiente — siguiente** |
| B | Agente(s) de análisis y ranking | Top 10–15 con razones trazables | pendiente |
| C | Handoff + gate de aprobación | UI de revisión → tickers al optimizador | pendiente |
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

## Qué hay en el repo

### La app (no la toca el estudio)
```
app.py           UI Streamlit
data.py          descarga de precios (yfinance, @st.cache_data, sólo Close)
optimizer.py     Markowitz: max Sharpe / mín varianza / paridad de riesgo
estimators.py    Ledoit-Wolf + James-Stein          ← SIN COMMITEAR
validation.py    walk-forward out-of-sample          ← SIN COMMITEAR
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

---

## Decisiones ya tomadas — no relitigar

- **Enfoque escalonado.** D se corrió primero, con universo actual y sesgo de supervivencia documentado, porque el sesgo infla resultados: un negativo es concluyente sin pagar la corrección cara.
- **`alphalens-reloaded` descartado.** No trae Newey-West, sub-periodos ni Benjamini-Hochberg — la matemática hay que escribirla igual. `scipy.stats.spearmanr` sirve de referencia cruzada del IC.
- **TradingAgents / ai-hedge-fund: referencia arquitectónica, no dependencia.** Producen señales buy/sell por ticker en vez de rankings de candidatos, son no deterministas (misma entrada → distinta salida) y no tienen evidencia publicada de rentabilidad.
- **Herramientas investigadas y validadas para A:** [edgartools](https://github.com/dgunning/edgartools) (XBRL de 10-Q/10-K, gratis, sin API key) y [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) (AGPLv3 — ojo con la licencia si el proyecto se distribuye).
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

---

## Lo siguiente: sub-proyecto A

**Universo + motor de fundamentales.** Ingesta determinista de KPIs del último trimestre para un universo configurable, cacheada, sin IA todavía.

Preguntas de diseño abiertas:
- ¿Qué universos? (S&P 500 ya resuelto; falta lista personalizada desde noticias, y multi-capitalización)
- ¿Qué KPIs concretos, y de qué fuente? edgartools da XBRL crudo; hay que decidir el conjunto y cómo normalizarlo entre sectores
- ¿Cómo se cachean los fundamentales y con qué política de refresco? (los trimestrales llegan escalonados)
- ¿Cuántas acciones debería tener el portafolio final? Quedó pendiente de responder con datos en el diseño de B — interactúa con el hecho de que Markowitz concentra pesos, así que 15 candidatos no son 15 posiciones

Reutilizable de D: `research/loader.py` (patrón de caché + reporte de cobertura), `research/universe.py` (snapshot congelado), y todo el patrón de tests.

---

## Comandos

```bash
pytest tests/ -q                    # 290 tests
python -m research.run              # correr el estudio (~5 min, luego caché)
streamlit run app.py                # la app
python scripts/bootstrap_universe.py   # regenerar el snapshot del universo
```
