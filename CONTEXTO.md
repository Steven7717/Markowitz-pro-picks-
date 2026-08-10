# Contexto del proyecto — para retomar en una sesión nueva

**Última actualización:** 2026-08-10
**Rama:** `master` · **Tests:** 290 pasando (`pytest tests/ -q`) · árbol limpio

---

## Qué es este proyecto

**Markowitz Pro Picks** es una app Streamlit que recibe una lista de tickers y devuelve la asignación óptima de pesos (máximo Sharpe, mínima varianza, paridad de riesgo), con validación out-of-sample y exportación a PDF/Excel.

El objetivo mayor es construir, **aguas arriba de esa app**, un sistema donde uno o más agentes de IA analicen un universo de activos con análisis fundamental, entreguen un top 10–15 razonado, el usuario lo apruebe, y esa lista alimente el optimizador.

## Descomposición en sub-proyectos

| # | Sub-proyecto | Entrega | Estado |
|---|---|---|---|
| A | Universo + motor de fundamentales | Ingesta determinista de KPIs trimestrales | **diseñado y planificado — sin implementar** |
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
estimators.py    Ledoit-Wolf + James-Stein
validation.py    walk-forward out-of-sample
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

---

## Lo siguiente: implementar el sub-proyecto A

El diseño está cerrado y el plan escrito. **No hay ni una línea de código todavía: el paquete `fundamentals/` no existe.**

- [`docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md`](docs/superpowers/specs/2026-08-10-motor-fundamentales-design.md) — el diseño, con las decisiones y lo que se descartó.
- [`docs/superpowers/plans/2026-08-10-motor-fundamentales.md`](docs/superpowers/plans/2026-08-10-motor-fundamentales.md) — 12 tareas en TDD, con el código de cada test y de cada implementación.

**Empezar por la Task 1**, que es un spike de verificación: `edgartools` no está instalado y ninguno de los supuestos sobre su API se ha comprobado ejecutando. El plan asume que `periods=12, annual=False` devuelve 12 columnas, que el índice trae conceptos XBRL crudos y no etiquetas legibles, y que las columnas de periodo son fechas de cierre de trimestre. Si algo de eso falla, la Task 1 dice qué ajustar.

Lo que el motor entregará: 16 KPIs por trimestre, 12 trimestres de profundidad, desde el XBRL de SEC, con z-score dentro del sector GICS y reporte de cobertura que declara cada ausencia en vez de imputarla.

Las cadenas de conceptos XBRL de `concepts.py` son conjeturas informadas sobre qué etiquetas usa cada emisor. La corrida real de la Task 12 mide la cobertura por KPI: **cualquiera por debajo del 50% significa que falta una etiqueta en la cadena**, no que las empresas no la reporten.

Reutilizable de D: `research/loader.py` (patrón de caché + reporte de cobertura), `research/universe.py` (snapshot congelado), y todo el patrón de tests.

Sigue sin responder, y es de B: **¿cuántas acciones debería tener el portafolio final?** Interactúa con que Markowitz concentra pesos, así que 15 candidatos no son 15 posiciones.

---

## Comandos

```bash
pytest tests/ -q                    # 290 tests
python -m research.run              # correr el estudio (~5 min, luego caché)
streamlit run app.py                # la app
python scripts/bootstrap_universe.py   # regenerar el snapshot del universo
```
