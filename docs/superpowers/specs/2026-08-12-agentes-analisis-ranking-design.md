# Sub-proyecto B — Agente(s) de análisis y ranking

**Fecha:** 2026-08-12
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Un top de **hasta 15** empresas, razonado y trazable, a partir del panel que
produce el sub-proyecto A. El orden lo decide un score determinista sobre los
z-scores sectoriales; el LLM redacta el porqué de cada candidato y no puede
reordenar nada. Salen menos de 15 sólo si menos de 15 superan las guardas.

Alimenta al sub-proyecto C (gate humano de aprobación) a través de
`fichas.json`, que es el contrato entre ambos.

La app Streamlit, `research/` y `fundamentals/` no se tocan.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Quién ordena | Score determinista | Misma entrada → misma salida, auditable, inmune a la contaminación de look-ahead de los LLM |
| Papel del LLM | Sólo redacta | Aporta lenguaje, no alfa. Nunca reordena, nunca escribe cifras |
| Pesos | Cuatro pilares al 25%, congelados antes de ver un ranking | Estándar #1 del proyecto. Cero riesgo de sobreajuste. Se declara que el score **no está validado**: es un criterio de selección transparente, no una promesa de rentabilidad |
| Ventana | Media de los 4 trimestres más recientes | Amortigua el trimestre extraordinario y premia la consistencia |
| Selección | Orden global con tope de 3 por sector | Garantiza ≥5 sectores en 15 nombres sin cuotas fijas. Markowitz concentra pesos aguas abajo |
| Contexto cualitativo | Item 1A (factores de riesgo) del último 10-K, con tope duro | Es lo que los KPIs no ven: litigios, concentración de clientes, dependencia regulatoria |
| Modelo | `claude-sonnet-5` | Basta de sobra para resumir con esquema fijo. Coste: ver abajo |
| Sin clave de API | Ranking igual, fichas de plantilla | El ranking nunca depende de la red |

### Lo que cambia respecto a la restricción heredada

`CONTEXTO.md` recoge que **B no admite backtest honesto**, porque los LLM ya
conocen lo que pasó con estas acciones ([Look-Ahead-Bench](https://arxiv.org/abs/2601.13770)).
Esa restricción sigue en pie **para las fichas**, que es donde interviene el
modelo. No aplica al score, que es aritmética sobre XBRL: un compuesto de
z-scores sí sería validable con la maquinaria de la Puerta A que ya existe en
`research/evaluation.py`.

No se valida ahora, por dos razones medibles y no por comodidad:

- El panel tiene 12 trimestres (`PERIODOS = 12` en `fundamentals/fetch.py`), es
  decir ~12 cortes transversales. Newey-West sobre 12 observaciones no distingue
  una señal fundamental del ruido.
- El universo es el S&P 500 **actual**. En el sub-proyecto D el sesgo de
  supervivencia fue inocuo porque el veredicto salió negativo; aquí jugaría a
  favor y habría que corregirlo de verdad.

Queda anotado como trabajo posterior: ampliar el panel a ~40 trimestres con
universo point-in-time y medir el IC de cada KPI y del compuesto. Podrá
confirmar o corregir los pesos; hasta entonces son una premisa declarada.

### Medición pendiente al implementar

Las guardas de cobertura (abajo) excluyen empresas. **Cuántas, y de qué
sectores, se mide y se reporta** —no se supone. Financials tiene 51,1% de
cobertura media frente al 76,7% de tecnología, así que la exclusión no será
uniforme. Si el resultado es inaceptable, se documenta como enmienda fechada
con su dirección de efecto; no se ajusta el umbral hasta que el número guste.

## Arquitectura

Paquete nuevo `ranking/`, hermano de `fundamentals/` y `research/`.

```
fundamentals.run.build_panel(con_zscore=True)
        │  panel: (ticker, periodo) × 17 KPIs + 17 z_KPIs + trimestre
        ▼
ranking/criterio.py    congelado en su propio commit, ANTES de ver un ranking
        │  pilares, signos, ventana, mínimos de cobertura, tope sectorial, N
        ▼
ranking/score.py       media de 4 trimestres → 4 pilares → compuesto
        │  tabla por ticker: 4 pilares + compuesto + motivo de exclusión
        ▼
ranking/seleccion.py   orden global + tope de 3 por sector
        │  top 15 + registro de quién quedó desplazado por el tope
        ▼
ranking/fichas.py      ficha determinista (siempre) + narrativa (si hay LLM)
        │      ├── ranking/filings.py  Item 1A vía edgartools, cacheado y recortado
        │      └── ranking/llm.py      Sonnet 5, esquema fijo, cita verificada
        ▼
ranking/run.py         → ranking.csv · fichas.json · informe.md
```

Se descartaron dos alternativas:

- **Extender `fundamentals/`**: rompe una frontera hoy limpia. A es un motor
  determinista de ingesta, sin criterio de inversión y sin LLM. Mezclarlos haría
  convivir sus 391 tests con un componente que depende de una API de pago.
- **Un paquete `agents/` con el LLM al centro**: refleja mal quién decide.
  Estructurar alrededor del LLM entierra la pieza que carga el peso.

## El criterio pre-registrado (`ranking/criterio.py`)

Datos, no lógica. Se congela en un commit propio antes de calcular ningún
ranking; la fecha del commit es la prueba de que los umbrales no se movieron al
ver los números.

### Pilares y pesos

| Pilar | Peso | KPIs |
|---|---:|---|
| Calidad | 25% | `margen_bruto`, `margen_operativo`, `margen_neto`, `roe`, `roic`, `margen_fcf`, `fcf_sobre_beneficio` |
| Crecimiento | 25% | `crecimiento_ingresos`, `crecimiento_bpa`, `crecimiento_fcf` |
| Valoración | 25% | `per`, `ev_ebitda`, `precio_fcf`, `precio_valor_libro` |
| Solidez | 25% | `deuda_neta_ebitda`, `cobertura_intereses`, `razon_corriente` |

Los 17 KPIs, cada uno en exactamente un pilar.

### Signos

Un z-score alto de PER significa **caro**, no bueno. Se invierten los cuatro de
valoración y `deuda_neta_ebitda`; los doce restantes van en su signo natural.

El signo vive en el criterio, no escondido en la aritmética del score, para que
un test pueda comprobar que los 17 tienen signo declarado. Un error de signo es
invisible al leer y produce un ranking plausible y al revés — la misma clase de
defecto que en A agrupaba empresas por trimestre fiscal y habría producido
z-scores entre trimestres distintos: plausibles y falsos.

### Umbrales

| Parámetro | Valor |
|---|---:|
| Trimestres de la ventana | 4 |
| Trimestres mínimos de historia | 4 |
| Frescura: antigüedad máxima del último trimestre | 2 trimestres naturales |
| Pilares con dato exigidos | 4 de 4 |
| KPIs con dato exigidos | 8 de 17 |
| Tope por sector GICS | 3 |
| Tamaño del top | 15 |

Dos precisiones para que estos números no admitan dos lecturas:

- **"Los 4 trimestres más recientes"** son las 4 filas más recientes que la
  empresa tiene en el panel, que no son necesariamente 4 trimestres
  consecutivos: si a una empresa le falta una presentación, la ventana salta el
  hueco. La guarda de frescura acota cuánto puede desplazarse el extremo
  reciente; el hueco interior se acepta, porque el z-score de cada fila ya es
  relativo a los pares de **su** trimestre.
- **"Dos trimestres naturales"** se mide contra el bucket `trimestre` máximo del
  panel completo, no contra la fecha de hoy ni contra el historial de la propia
  empresa.

## El score (`ranking/score.py`)

Por empresa: media de sus 4 trimestres más recientes por KPI → media de los KPIs
**con dato** dentro de cada pilar → media de los 4 pilares.

### Las cuatro guardas

1. **Historia.** Menos de 4 trimestres en el panel → excluida. No hay ventana
   que promediar.
2. **Frescura.** Si el último trimestre de la empresa no cae dentro de los dos
   trimestres naturales más recientes del panel, queda excluida. Sin esto, una
   empresa que dejó de presentar entra al ranking con cifras de hace un año y no
   se nota.
3. **Cobertura.** Un pilar sin ningún KPI con dato es un pilar **no medido**, no
   un pilar mediocre; promediar tres y llamarlo compuesto compara cosas
   distintas. Se exigen los 4 pilares presentes y ≥8 de los 17 KPIs. Las
   excluidas se cuentan y se reportan por sector.
4. **Re-estandarización del compuesto dentro de sector-trimestre**, antes del
   orden global.

### Por qué existe la cuarta guarda

Un pilar promediado sobre 2 KPIs tiene **más varianza** que uno promediado sobre
7: promediar menos cosas dispersa más. Las empresas a las que les faltan KPIs
son justamente bancos, aseguradoras y REITs, así que sus compuestos serían
sistemáticamente más extremos y aparecerían de más tanto en la cabeza como en la
cola del orden global. El ranking parecería normal y estaría midiendo **cuántos
KPIs publica cada empresa**.

Re-estandarizar el compuesto dentro de cada sector-trimestre elimina el
artefacto por construcción y no descarta información: los insumos ya eran
relativos a su sector, así que no había nivel entre sectores que preservar.

## Selección (`ranking/seleccion.py`)

Se recorre el orden global de mayor a menor y se admite cada empresa salvo que
su sector ya tenga 3, hasta llegar a 15.

- Las desplazadas por el tope se registran con su puesto en el orden puro, para
  que se vea qué hizo la regla en vez de tener que deducirlo.
- **Los empates se rompen por ticker alfabético.** Sin eso, dos corridas con los
  mismos datos pueden devolver listas distintas y el sistema deja de ser
  auditable por una razón tonta.
- Si menos de 15 candidatos superan las guardas, se entregan los que haya con el
  motivo de cada exclusión.

## Fichas (`ranking/fichas.py`, `filings.py`, `llm.py`)

La ficha tiene dos mitades con dueños distintos.

### Mitad de cifras — la escribe el código, siempre

Puesto, compuesto, los cuatro pilares, los KPIs más fuertes y más débiles con su
valor y su z, y la cobertura efectiva (cuántos KPIs con dato, cuántos pilares).
Existe aunque no haya red ni clave.

### Mitad narrativa — la escribe Sonnet 5, con esquema fijo

Una tesis de dos o tres frases y una lista de riesgos, cada uno con una cita
literal del Item 1A. Dos reglas la hacen verificable:

- **La cita se comprueba por código** contra el texto que se envió al modelo:
  normalizando espacios y mayúsculas, subcadena, tope de 200 caracteres. Si no
  aparece, se reintenta una vez nombrando la cita que falló; si vuelve a fallar,
  el riesgo se entrega con `verificada: false`, visible en la ficha y en el
  informe. Nunca se descarta en silencio: una afirmación sin respaldo que se ve
  es mejor que una que desaparece.
- **La narrativa no puede contener dígitos.** Los números salen del panel, no del
  modelo. Es una regla dura, comprobable con un test de una línea, y cuesta algo
  de expresividad —"márgenes por encima del 30%" hay que decirlo sin la cifra—.
  El cambio es deliberado: a cambio, nunca hay que verificar un número inventado.

### Extracción del informe (`filings.py`)

`TenK` de edgartools expone `risk_factors` y `management_discussion` directamente
sobre el objeto de la presentación, así que la extracción es una propiedad.

Medido sobre tres emisores el 2026-08-12, con edgartools 5.47.0. Los tokens son
una **estimación a 4 caracteres por token**, no una cuenta real; al implementar
se sustituye por `client.messages.count_tokens`, que es lo único que cuenta
tokens de Claude de verdad:

| Empresa | Factores de riesgo | MD&A |
|---|---:|---:|
| AAPL | 68k car. (~17k tok.) | 18k car. (~4,5k tok.) |
| XOM | 36k car. (~8,9k tok.) | 130k car. (~33k tok.) |
| JPM | 113k car. (~28k tok.) | **414k car. (~104k tok.)** |

Sólo se envía el Item 1A, con **tope duro de 20k tokens** por empresa y registro
de cuánto se recortó. El MD&A queda fuera: es en buena parte una narración de
las cifras que el panel ya tiene, y en emisores como JPM un tope descartaría el
85% de la sección, con lo que lo que llegara sería el principio del documento y
no lo importante.

### Coste por corrida

15 candidatos × 20k tokens de tope ≈ 300k tokens de entrada, más una salida
pequeña por el esquema fijo. Con la tarifa de Sonnet 5 ($3/M de entrada, $2/M
promocional hasta el 2026-08-31) eso son **0,60–0,90 $ por corrida completa**, y
0 $ en las siguientes mientras la caché siga válida.

La diferencia con Opus 5 ($5/M) es de **1,7×, no del 5× que se estimó al
elegir**: unos 1,50 $ por corrida. El argumento de coste es por tanto débil. La
elección de Sonnet 5 se sostiene igualmente porque la tarea —resumir una sección
acotada con esquema fijo y citar literalmente— es de las que no distinguen
tiers, y porque el componente no decide nada del ranking. Si en la práctica las
fichas salen flojas, subir a `claude-opus-5` cuesta menos de un dólar por
corrida y es un cambio de una constante.

### Reproducibilidad

Sonnet 5 ya no acepta `temperature`, así que dos llamadas idénticas pueden
diferir. Lo resuelve la caché: clave `sha256` de (versión del prompt + id del
modelo + bloque numérico del candidato serializado canónicamente + accession del
informe + hash del texto recortado). Segunda corrida con los mismos datos →
mismas fichas, cero llamadas, cero coste.

`hashlib`, no `hash()`: Python aleatoriza el hash de strings entre procesos. Es
una de las lecciones explícitas que dejó el sub-proyecto D.

La caché vive en `ranking/.cache/`, que va a `.gitignore`.

## Manejo de errores

| Fallo | Comportamiento |
|---|---|
| Sin `ANTHROPIC_API_KEY` | Ranking completo, fichas de plantilla, marcadas `generada_por: "plantilla"` |
| API caída, 429 o timeout | Reintento con backoff del SDK; agotado, esa ficha cae a plantilla y las demás siguen |
| edgartools no encuentra Item 1A | Ficha con cifras y sin narrativa de riesgos; se cuenta y se reporta |
| Sección más larga que el tope | Se recorta y se registra cuántos caracteres se descartaron |
| Cita no verificable tras el reintento | Riesgo entregado con `verificada: false` |
| Menos de 15 candidatos superan las guardas | Se entregan los que haya, con el motivo de cada exclusión |

Ninguna empresa que falla aborta la corrida, igual que en `fundamentals/`.

## Salidas

- `ranking.csv` — tabla completa: ticker, sector, cuatro pilares, compuesto,
  puesto, cobertura, motivo de exclusión, desplazada por el tope.
- `fichas.json` — **el contrato con el sub-proyecto C.** Es lo que la UI de
  aprobación va a leer.
- `informe.md` — legible por humanos, con la cobertura y las exclusiones al pie.

Forma de cada ficha, fijada aquí porque C se construye contra ella:

```json
{
  "ticker": "AAPL",
  "sector_gics": "Information Technology",
  "puesto": 3,
  "compuesto": 1.42,
  "pilares": {"calidad": 1.9, "crecimiento": 0.4, "valoracion": -0.2, "solidez": 1.1},
  "destacados": [{"kpi": "roic", "valor": 0.31, "z": 2.4}],
  "flojos":     [{"kpi": "per",  "valor": 34.2, "z": -1.1}],
  "cobertura": {"kpis_con_dato": 14, "pilares_con_dato": 4},
  "desplazo_a": [],
  "generada_por": "sonnet-5",
  "narrativa": {
    "tesis": "...",
    "riesgos": [{"afirmacion": "...", "cita": "...", "verificada": true}],
    "fuente": {
      "formulario": "10-K", "fecha": "2025-10-31", "accession": "0000320193-25-...",
      "seccion": "Item 1A", "caracteres_enviados": 68163, "recortado": false
    }
  }
}
```

`narrativa` es `null` cuando `generada_por` es `"plantilla"`. `desplazo_a` lista
los tickers que esta empresa dejó fuera al consumir un hueco del tope sectorial.

## Pruebas

Por módulo:

- **criterio**: los 17 KPIs aparecen exactamente una vez; los 17 tienen signo
  declarado; los pesos suman 1.
- **score**: paneles sintéticos para la ventana, cada guarda por separado, la
  inversión de valoración, la re-estandarización.
- **seleccion**: el tope dispara, los empates son deterministas, menos de 15
  candidatos.
- **filings**: fixture grabado; el recorte queda registrado.
- **llm**: respuestas grabadas; sin clave → plantilla; el camino de reintento.
- **run**: extremo a extremo sobre una lista corta con fixtures.

Y tres que responden a los estándares metodológicos del proyecto:

- **Control negativo** (estándar #2): panel barajado dentro de sector-trimestre
  **conservando el patrón de NaN**. Las cabeceras del ranking barajado no pueden
  ser sistemáticamente las empresas de menor cobertura. Si lo son, el score
  premia la cobertura y no la calidad, y ese resultado es indistinguible a ojo de
  uno correcto.
- **Referencia positiva** (estándar #3): una empresa sintética que domina los 17
  KPIs sale primera. Si no, el aparato no detecta lo que debería.
- **Cita fabricada rechazada**: el test que decide si "trazable" significa algo.

Un test marcado `red`, opcional como los de contraste de A, hace una llamada
real a la API para comprobar que el esquema y el modelo siguen encajando.

## Fuera de alcance

- La UI de revisión y aprobación: es el sub-proyecto C.
- La validación empírica de los pesos: requiere panel point-in-time de ~40
  trimestres, anotado arriba como trabajo posterior.
- El MD&A y la búsqueda de noticias como contexto del LLM: descartados con su
  razón arriba.
- Cuántas posiciones debe tener la cartera final. B entrega 15 candidatos;
  cuántos sobreviven al optimizador es una decisión de C y del optimizador.

---

## Enmienda 1 — 2026-08-12: la re-estandarización es por sector, no por sector-trimestre

**Qué decía el diseño:** la cuarta guarda re-estandariza el compuesto "dentro de
sector-trimestre" antes del orden global.

**Qué es posible:** re-estandarizar **dentro de sector**, sin dimensión temporal.

**Por qué difieren:** después de promediar la ventana de 4 trimestres queda una
sola fila por empresa, así que ya no hay eje de trimestre sobre el que agrupar.
Agrupar por (sector, último trimestre de la empresa) tampoco sirve: los cierres
fiscales no coinciden, así que produciría grupos diminutos —el mismo problema
que en A descartó SIC de 4 dígitos, donde 87 empresas quedaban solas.

**En qué dirección afecta:** en ninguna, respecto al propósito de la guarda. El
artefacto que corrige es la varianza inflada de los compuestos calculados sobre
pocos KPIs, y esa comparación es entre empresas del mismo sector, no entre
trimestres. Los insumos ya venían normalizados por sector **y** trimestre desde
A, así que el eje temporal ya estaba tratado aguas arriba.

**Consecuencia operativa:** se reutiliza `zscore_within_sector` de
`fundamentals/sectors.py`, que ya devuelve NaN —nunca 0— cuando el grupo tiene
menos de 3 pares o dispersión nula. Un sector con menos de 3 empresas
supervivientes deja a las suyas con compuesto NaN, y eso **se registra como
motivo de exclusión explícito**, no como una caída silenciosa del ranking.

---

## Enmienda 2 — 2026-08-13: la cita verificada necesita una longitud mínima

**Qué decía el diseño:** una cita cuenta como verificada si aparece literalmente
en el texto que se le pasó al modelo, con un tope máximo para que "citar" no
degenere en copiar la sección entera.

**Qué faltaba:** el tope por abajo. Medido sobre la implementación de la tarea
10, antes de esta enmienda:

```
verificar_cita("we", item1a)    -> True
verificar_cita("risks", item1a) -> True
```

**Por qué importa:** el sello "verificada" es la promesa central del
sub-proyecto. Un modelo que emita una cita de dos letras la obtiene, y la ficha
resultante es indistinguible a ojo de una con una cita real. Era la mayor
superficie de falsa aceptación que quedaba en pie — mayor que la que abría
cualquiera de las decisiones de normalización que sí se discutieron.

**Qué se añade:** `MIN_CARACTERES_CITA = 25`, aplicado al texto normalizado,
simétrico con el máximo. Las tres citas de ejemplo del plan miden 39, 30 y 31
caracteres normalizados, así que ninguna se ve afectada.

**En qué dirección afecta:** endurece. Una cita real e inusualmente corta pasa a
rechazarse, lo que degrada esa ficha a plantilla — el lado barato de la
asimetría que gobierna todo este módulo: un falso rechazo cuesta una narrativa,
una falsa aceptación cuesta la promesa.

**Lo que esta enmienda NO consigue, y conviene no creer que sí:** una longitud
mínima no hace que una cita sea **relevante**. Un fragmento de 25 caracteres
verdadero y sin relación con lo que la ficha afirma sigue pasando la
verificación. Lo que se cierra es que dos palabras se hagan pasar por cita. Que
la cita sostenga la afirmación no es comprobable por código, y no hay en este
diseño ningún mecanismo que lo compruebe.

**El 25 es un juicio, no una medida.** Es aproximadamente una cláusula corta, por
debajo de la cita más corta que el propio plan usa como ejemplo válido. Los tests
fijan el mecanismo de frontera —comparación estricta contra el texto
normalizado—, no el número: mover la constante no hace fallar la suite por sí
solo. Es reversible si la corrida real de la tarea 15 muestra que el modelo cita
más corto de lo esperado.

---

## Enmienda 3 — 2026-08-15: cobertura real de las guardas, medida

Primera corrida completa sobre el universo real, sin LLM
(`construir_ranking(con_llm=False)`), con el panel cacheado del sub-proyecto A.
**Todos los números de esta sección están medidos, ninguno estimado.** No se ha
tocado ningún umbral de `ranking/criterio.py` para mejorarlos.

### La cadena de mermas, entera

| Etapa | Empresas |
|---|---:|
| Universo pedido (`sp500_members_2026-08-05.csv`) | 503 |
| Con hechos descargados de la SEC | 503 |
| **Con fila en el panel** | **502** |
| Sobreviven a las guardas | 425 |
| Entran en el top tras el tope sectorial | 15 |

`FDXF` se pide y no llega al panel: se cae aguas arriba, en el sub-proyecto A,
que lo reporta por su propia vía (`historia corta: 2`, `sin precio: 2`). El
invariante que sí se cumple es **425 + 77 = 502**, contra el panel, no contra el
universo pedido. Conviene saberlo antes de restar 503 y encontrarse una empresa
de menos.

### Qué guarda excluye, y a quién

| Motivo | Empresas |
|---|---:|
| `pilar_sin_datos` | 72 |
| `datos_rancios` | 2 |
| `cobertura_insuficiente` | 2 |
| `historia_corta` | 1 |
| `sector_desconocido` | 0 |
| `sin_dispersion_sectorial` | 0 |

**Una sola guarda hace el 94% del trabajo**, y no excluye al azar:

| Sector | Total | Excluidas | % |
|---|---:|---:|---:|
| Financials | 76 | 50 | **65,8%** |
| Real Estate | 31 | 13 | **41,9%** |
| Consumer Discretionary | 47 | 4 | 8,5% |
| Consumer Staples | 34 | 2 | 5,9% |
| Industrials | 82 | 4 | 4,9% |
| Energy | 21 | 1 | 4,8% |
| Utilities | 31 | 1 | 3,2% |
| Health Care | 59 | 1 | 1,7% |
| Information Technology | 73 | 1 | 1,4% |
| Communication Services | 23 | 0 | 0% |
| Materials | 25 | 0 | 0% |

**La causa es estructural, no un fallo de datos.** De las 72 exclusiones por
`pilar_sin_datos`, **65 son el pilar `solidez` vacío**, y 46 de las 48 de
Financials. Sus tres KPIs son `deuda_neta_ebitda`, `cobertura_intereses` y
`razon_corriente`, y los tres están **indefinidos para un banco por
construcción**: no publica EBITDA, su "gasto por intereses" es materia prima y no
carga financiera, y su balance no se clasifica en corriente y no corriente.
Cobertura media del pilar: **0,74 KPIs en Financials frente a 2,01 en
tecnología**.

El diseño anticipó que la exclusión no sería uniforme. Lo que no anticipó es su
tamaño: **dos de cada tres bancos y aseguradoras no pueden ser evaluados por este
criterio**, y no por ser peores, sino por reportar distinto. El único financiero
del top 15 es CBOE —un operador de mercados, no un banco— con 17 de 17 KPIs.

**En qué dirección afecta:** el sesgo no está en el orden de los supervivientes,
sino en quién llega a ser comparable. La lista corta infrarrepresenta a Financials
y Real Estate frente a su peso en el índice, y **eso se hereda al sub-proyecto C**:
una cartera optimizada sobre esta lista corta llevará un ladeo sectorial que no
decidió el optimizador. Debe saberlo antes de interpretar sus pesos.

### El hallazgo que no se buscaba: los z-scores no están acotados

Se descubrió leyendo la salida real, no con un test.

El número 1 de la corrida es **CPRT, con un compuesto de +5,70** frente al +4,18
del segundo. Su pilar `solidez` vale **+6,37**, exactamente el z de
`razon_corriente` — es decir, ese pilar tiene **un solo KPI de tres con dato**, y
ese KPI es un valor extremo. Como los cuatro pilares pesan igual, **una cuarta
parte del compuesto del primer clasificado sale de un único indicador sin
acotar**.

No es un caso aislado. En el panel **no hay winsorización en ninguna parte**: el
|z| máximo llega a 8,62, y **201 celdas de 69.048 superan |z| > 6**.

Es una consecuencia no examinada del diseño, no un defecto del código: se eligió
promediar z-scores sectoriales y nunca se dijo qué hacer con las colas. El
control negativo del estándar #2 no lo detecta porque mide sesgo por cobertura,
no dominancia de un valor extremo.

**No se corrige aquí**, porque `ranking/criterio.py` es un artefacto de
pre-registro congelado y cambiarlo después de ver el resultado es exactamente lo
que el pre-registro existe para impedir. Queda anotado como el primer candidato a
revisar cuando el criterio se reabra, junto con la validación empírica de los
pesos: recortar los z a ±3, o exigir un mínimo de KPIs por pilar y no sólo por
ficha, son las dos palancas obvias.

### El tope del Item 1A muerde más de lo previsto

Medido sobre los quince filings del top, descargados de EDGAR:

- **Los 15 tienen Item 1A extraíble.** Ningún `None`.
- **9 de 15 (60%) se recortan** en el tope de 80.000 caracteres.
- Mediana **101.344** caracteres; mínimo 7.494 (INCY), máximo **298.634** (PLTR).
- **El 31% del texto total nunca llega al modelo** (481.058 de 1.564.181).

El diseño estimó el tope a partir del Item 1A de Apple (68.163 caracteres), que
resulta estar en el extremo bajo. La consecuencia práctica: para nueve de quince
empresas, un riesgo tratado sólo en el último tramo del documento **no se puede
citar**, y `verificar_cita` lo rechazaría con razón por comparar contra lo que se
envió. La narrativa se construye sobre el primer tercio largo del documento, y
eso no se ve en la ficha.

No se sube el tope: duplicarlo duplicaría el coste por ficha y sigue sin cubrir a
PLTR. La salida honesta es que la ficha declare `recortado`, que ya lo hace.

### Salidas de esta corrida

`salidas/ranking.csv` (502 filas con pilares, compuesto y motivo), 
`salidas/fichas.json` (las 15, sin narrativa) y `salidas/informe.md`. Son una
instantánea de esta corrida fechada, no un artefacto vivo.
