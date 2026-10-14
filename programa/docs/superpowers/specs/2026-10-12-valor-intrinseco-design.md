# Valor intrínseco — sub-proyecto M

**Fecha:** 2026-10-12
**Estado:** implementado en la rama `feat/valor-intrinseco` (2026-10-14), pendiente de fusionar
**Le sigue:** el sub-proyecto N, el Analizador individual
(`2026-10-12-analizador-individual-design.md`), que usa este motor para
cualquier ticker.

## Qué entrega

Revisar candidatos dice hoy cómo está una empresa **frente a sus pares del
sector**: calidad, crecimiento, valoración y solidez, en z-scores. No dice si el
precio está por encima o por debajo de lo que el negocio vale. El pilar de
valoración sólo compara múltiplos con el sector, así que si todo el sector está
caro no lo ve.

M añade esa pregunta: **¿la acción está infravalorada, en rango o
sobrevalorada?** La respuesta sale de cuatro lecturas que se contrastan entre
sí. En la tarjeta de cada candidato aparece un distintivo, en su ficha el
detalle, y la valoración se guarda en `fichas.json`, así que el acta registra qué
decía el día que se aprobó.

**No toca el orden de los candidatos.** El score es un criterio pre-registrado y
congelado. Meter la valoración en la nota exigiría una enmienda fechada y dejaría
de poder compararse un acta nueva con una vieja.

## La decisión central: cuatro lecturas, tres votos

Ningún método de valoración está validado para predecir rentabilidades, y un DCF
suelto da un número muy sensible a dos supuestos. Por eso se triangula:

| # | Lectura | Qué contesta |
|---|---|---|
| 1 | **DCF** de flujo de caja libre en dos etapas, con tres escenarios | ¿Cuánto vale si crece como se espera? Da un **rango**, no un punto |
| 2 | **DCF inverso** | ¿Qué crecimiento tiene que cumplir para justificar el precio de hoy? |
| 3 | **Valor sin crecimiento** (EPV de Greenwald) | ¿Cuánto vale si deja de crecer mañana? |
| 4 | **Múltiplos frente a pares**: el pilar de valoración que ya existe | ¿Está cara o barata frente a su sector? |

Para bancos y aseguradoras el flujo de caja libre no significa nada, así que la
1 y la 2 se sustituyen por el **beneficio residual** y su inverso, el ROE que el
precio exige. La 3 no aplica.

**El DCF y su inverso son la misma ecuación leída en las dos direcciones.** Si el
precio cae por debajo del escenario pesimista, el crecimiento implícito cae por
debajo del pesimista casi por construcción. Si votaran por separado, una sola
lectura contaría dos veces y bastaría ella sola para declarar una acción
infravalorada. Así que las cuatro lecturas dan **tres votos**: flujos (1 y 2
juntas), sin crecimiento (3) y pares (4).

## Alcance de M frente a N

M es el motor y su sitio en Revisar candidatos. Calcula **en dólares**, que es lo
único que necesitan los candidatos: el universo es el S&P 500.

El motor no sabe de divisas: recibe cifras en una sola moneda y devuelve cifras
en esa moneda. Lo que N añade encima es la capa de divisas (pesos, conversión,
ADRs), las líneas contables desde yfinance y la pantalla.

## Componentes

Paquete nuevo `valoracion/`, sin Streamlit. Sólo `mercado.py` toca la red.

### 1. `valoracion/criterio.py` — congelado

Se escribe y se commitea **antes de medir nada**, en un commit propio, como el
criterio de D y el de B. Si algo cambia después, se anexa una enmienda fechada
debajo de este documento y no se edita el original.

| Constante | Valor | Por qué |
|---|---|---|
| `ANOS_ALTO_CRECIMIENTO` | 5 | Primera etapa del DCF |
| `ANOS_CONVERGENCIA` | 5 | El crecimiento baja en línea recta hasta el de perpetuidad; en el año 10 ya es el de perpetuidad |
| `PRIMA_RIESGO` | 0,0420 | Damodaran, prima implícita a 2026-10-01, base *trailing 12 months, adjusted payout*. Va con `PRIMA_RIESGO_FECHA` al lado. La fuente la nombra la procedencia del supuesto (`"damodaran"`), no una constante |
| `CRECIMIENTO_PERPETUO` | `{"USD": 0.025, "MXN": 0.035}` | Crecimiento nominal de largo plazo. MXN lleva encima la diferencia de objetivos de inflación (3 % frente a 2 %). Nunca puede superar la tasa libre de riesgo: si la supera, se recorta a ella |
| `TASA_LEGAL` | `{"US": 0.21, "MX": 0.30, "otros": 0.24}` | Respaldo cuando no hay tasa efectiva, por el país de `info["country"]`. `otros` es el tipo combinado medio de la OCDE, redondeado; la procedencia lo dice |
| `TASA_EFECTIVA_TOPES` | (0,00; 0,35) | Una tasa efectiva fuera de ahí es un año raro, no un régimen |
| `BETA_SEMANAS` | 104 | Dos años de rendimientos semanales |
| `BETA_SEMANAS_MIN` | 52 | Por debajo, beta = 1,0 y se dice |
| `BLUME` | (0,67; 0,33) | β ajustada = 0,67·β + 0,33: la beta medida tiende a 1 con el tiempo |
| `CRECIMIENTO_REF_TOPES` | (−0,10; +0,40) | Ni un desplome de un año ni un año de euforia se proyectan cinco años enteros |
| `CRECIMIENTO_REF_ANOS` | 3 | Años del CAGR histórico de ingresos, o los que haya si son menos |
| `PAYOUT_SIN_DATO` | 0,5 | Reparto de beneficios supuesto en el beneficio residual cuando yfinance no da `payoutRatio`. La procedencia lo dice |
| `MARGEN_MINIMO` | 0,05 | El margen del voto de flujos es `max(0,05; ½·|g_ref|)` |
| `MARGEN_ROE_MINIMO` | 0,03 | Igual para el beneficio residual: `max(0,03; ½·|ROE_ref|)` |
| `DELTA_WACC_ESCENARIOS` | 0,01 | ±1 punto de coste de capital entre escenarios |
| `INVERSO_LIMITES` | (−0,30; +0,80) | Intervalo de la bisección del crecimiento implícito |
| `INVERSO_ROE_LIMITES` | (−0,20; +0,60) | Intervalo de la bisección del ROE implícito |
| `COSTE_DEUDA_PRIMA_MAXIMA` | 0,08 | El coste de la deuda se acota entre r_f y r_f + 0,08: no baja de la tasa libre de riesgo ni sube como el de un bono basura. Se guarda la prima y no el intervalo porque r_f no es una constante |
| `HOLGURA_GORDON` | 0,01 | El coste de capital debe superar al crecimiento perpetuo en al menos un punto; si no, el valor terminal explota y la lectura no aplica |
| `UMBRAL_PARES` | 0,5 | El pilar de valoración vota «barata» desde +0,5 y «cara» desde −0,5: el mismo corte que `ranking.fichas.descriptor` usa para «por encima de sus pares» |
| `MIN_ANOS_HISTORIA` | 2 | Años de margen necesarios para normalizarlo |
| `MIN_VOTOS` | 2 | Por debajo, el veredicto es «sin datos suficientes» |
| `INDUSTRIAS_FINANCIERAS` | lista cerrada de cadenas de industria de Yahoo | Las que se valoran por beneficio residual. Ver abajo |
| `VERSION` | `"m1"` | Viaja dentro de cada valoración guardada |

**`INDUSTRIAS_FINANCIERAS`.** Entran bancos, aseguradoras de riesgo
(vida, daños, diversificadas, reaseguro, especialidad), *Capital Markets* y
*Mortgage Finance*. **No entra *Credit Services***, aunque Yahoo meta ahí a
lenders como COF y SYF, porque también mete a Visa, Mastercard y PayPal, cuyo
flujo de caja sí significa algo. **Los corredores de seguros tampoco entran**:
son negocios de servicios sin balance de riesgo. Las cadenas exactas se copian de
lo que Yahoo devuelve de verdad (test `red`), no de memoria. Que COF y SYF se
valoren por DCF es una imperfección conocida y queda dicha en «Lo que M no
resuelve».

### 2. `valoracion/fundamentos.py` — la entrada, en una sola moneda

`Fundamentos`, una dataclase congelada con todo lo que el motor necesita, en la
moneda de los estados:

- `ejercicios`: una tupla de `Ejercicio`, del más reciente al más antiguo. Cada
  uno son doce meses que terminan en `fin`, con los flujos sumados (ingresos,
  flujo operativo, capex, gasto financiero, beneficio operativo y beneficio
  neto) y el patrimonio a esa fecha. `ultimo` es el primero. De ahí salen los
  márgenes normalizados, el ROE de referencia y el crecimiento histórico.
- `deuda_total` y `efectivo`, del último balance.
- `moneda` y `fuente` (`"sec"` en M; N añade `"yfinance"`).

**Los ejercicios distan de verdad un año**, y por eso se pueden leer por
posición. La revisión del 2026-10-12 midió sobre las 503 cachés que un trimestre
que falta en el panel hacía que el muestreo cada cuatro filas saltara un año
(AMCR, DPZ) o se desplazara (KR, WAT), sin decir nada. Ahora la serie se corta
en el primer hueco en vez de saltárselo. **Los ejercicios se anclan en los
ingresos, y sólo si la empresa no declara ninguno, en el beneficio neto**: JPM no
tiene línea de ingresos, y el beneficio residual sólo necesita beneficio neto y
patrimonio. Anclar en «cualquiera de los dos» le quitaba el DCF a una empresa
normal cuyo último 10-Q traía el beneficio pero no la etiqueta de ingresos. NaN
significa «no declarado», nunca cero.

**El constructor de M lee de EDGAR**, del mismo motor que los candidatos:
`fundamentals.panel.quarterly_panel` y `fundamentals.concepts.resolve_lines`,
con las mismas reconciliaciones. Pide **20 trimestres** en vez de 12: los hechos
en caché ya traen la historia entera desde 2007 (comprobado el 2026-10-12 sobre
tres cachés reales), así que pedir más no cuesta red. El flujo de caja de la SEC
viene acumulado en el año; el motor ya lo desacumula y esto no lo repite.

**El flujo libre para la empresa** es
`flujo_operativo − capex + gasto_financiero × (1 − t)`. La SEC da el capex en
positivo; yfinance, en negativo. Esa conversión vive en el constructor de cada
fuente, y cada uno tiene su test.

### 3. `valoracion/mercado.py` — lo único que toca la red

Para un ticker en dólares:

| Dato | Fuente |
|---|---|
| Precio, capitalización, industria, `payoutRatio` | `yf.Ticker(t).info` |
| Tasa libre de riesgo | `^TNX`, último cierre ÷ 100 |
| Beta | Regresión de rendimientos semanales del ticker contra `^GSPC`, 104 semanas |
| Tasa efectiva | `Tax Rate For Calcs` del estado de resultados anual de yfinance; si falta, `TASA_LEGAL` |
| Crecimiento del consenso | `revenue_estimate.loc["+1y", "growth"]`, sólo si su `currency` coincide con la de los estados |

**La beta se calcula aquí y nunca se lee de Yahoo.** El sondeo del 2026-10-12
dio para WALMEX.MX una beta de **0,016** en `info["beta"]`: Yahoo la mide contra
el S&P 500 con el precio en pesos. Para una empresa de EE. UU. la de Yahoo sería
razonable, pero dos caminos para el mismo dato se separan, y el que se queda
atrás no da error: da un número plausible.

**El consenso a largo plazo no existe.** `growth_estimates` trae `LTG` en NaN
para las acciones. Sólo hay este año (`0y`) y el siguiente (`+1y`). Se usa `+1y`
porque `0y` suele estar ya medio publicado.

**La divisa del consenso se comprueba fila a fila.** En TSM, `revenue_estimate`
viene en TWD y `earnings_estimate` en USD, en la misma consulta. En M no
aparece, porque el S&P 500 reporta en dólares, pero la comprobación se escribe
ya porque N la necesita.

**Caché** en `valoracion/.cache/` (se añade a `.gitignore`). La tasa libre de
riesgo y la beta valen un día. El precio, quince minutos. La hora de cada dato
viaja con él.

*Enmienda del 2026-10-14, en la revisión final.* La caché es también el
**respaldo cuando la red falla**: lo guardado caducado se sirve hasta
`mercado.ANTIGUEDAD_MAXIMA` —el precio y la tasa libre, 7 días; la beta, 90; la
tasa efectiva, 400; el consenso, 30— y sólo pasado eso el motivo es `sin_red`.
La revisión final, con la red de yfinance cortada, calculó 422 de 423. El precio
enseña su hora en la ficha; no hay aviso arriba de que vino de la caché.

**Fallos con nombre**, como en `seguimiento/banxico.py`: cada función devuelve
`(dato | None, motivo)`. Si falta el `^TNX`, ninguna valoración se puede
calcular y todas lo dicen con el mismo motivo. Si falla un ticker, sólo esa
ficha lo dice.

### 4. `valoracion/supuestos.py` — los supuestos y su procedencia

`Supuestos`: cada campo es un `Supuesto(valor, procedencia)`. La procedencia es
**dato estructurado, no texto**. Por ejemplo,
`{"fuente": "regresion", "indice": "^GSPC", "semanas": 104, "r2": 0.41}`, que la
pantalla traduce al pintarlo. Es la regla que dejó la familia de «La etiqueta de
pantalla que se guardaba en disco»: a un fichero de datos no se escribe nada
cuyo valor sea una decisión de redacción.

| Supuesto | Cálculo |
|---|---|
| `r_f` | `^TNX` |
| `beta` | Blume sobre la regresión; con menos de 52 semanas, 1,0 |
| `prima` | `PRIMA_RIESGO` |
| `k_e` | `r_f + beta × prima` |
| `k_d` | `gasto_financiero_ttm / deuda_total`, acotado entre `r_f` y `r_f + COSTE_DEUDA_PRIMA_MAXIMA` |
| `t` | Tasa efectiva acotada, o la legal |
| `wacc` | `E/(E+D)·k_e + D/(E+D)·k_d·(1 − t)`, con E = capitalización y D = deuda contable. Sin deuda, `wacc = k_e`. En bancos y aseguradoras, `wacc` y `k_d` quedan vacíos (`financiera`): sus intereses incluyen los depósitos, y el beneficio residual sólo usa `k_e` |
| `g_ref` | Media del CAGR histórico de ingresos (hasta 3 años) y del consenso `+1y`. Si sólo existe uno, ése. Acotado por `CRECIMIENTO_REF_TOPES` |
| `g_perpetuo` | `CRECIMIENTO_PERPETUO[moneda]`, recortado a `r_f` |

*Enmienda del 2026-10-14, en la revisión final.* Cuando falta el dato de
mercado de la beta, de la tasa efectiva o del consenso, la procedencia guarda
**por qué**: `{"fuente": "por_defecto", "motivo": "sin_red"}` en la beta,
`{"fuente": "legal", "pais": …, "motivo": …}` en la tasa y `motivo_consenso` en
`g_ref`. Antes el motor descartaba el motivo, y una beta que Yahoo no llegó a
devolver se pintaba como «historial corto»: con CF, el coste del capital propio
pasaba del 5,6 % al 9,4 % con una causa falsa en pantalla. Una beta con menos de
52 semanas sigue sin motivo, porque la red sí contestó.

M no tiene forma de cambiar supuestos: en Revisar candidatos no hay
deslizadores. La función que aplica los cambios del usuario la añade N, que es
quien la usa. Una función que no importa nadie es la que acaba borrada, como
`interprete/cache.py`.

### 5. `valoracion/dcf.py` y `valoracion/inverso.py`

**Proyección.** Ingresos a 10 años: del año 1 al 5 crecen a `g`; del 6 al 10,
el crecimiento baja en línea recta hasta `g_perpetuo`, al que llega en el año
10. El flujo libre de cada año es ingresos × **margen de flujo libre
normalizado**, que es el margen **agregado** de los ejercicios disponibles
(al menos `MIN_ANOS_HISTORIA`): la suma de sus flujos libres entre la suma de sus
ingresos.

**Agregado y no mediana: decisión del usuario del 2026-10-12, antes de medir.**
El texto aprobado decía «la mediana del margen anual». La revisión de la Task 6
la midió con MU: sus años de ciclo bajo pesaban lo mismo que el actual, el
margen salía en un 6,8 % frente al 29 % del último año, y aplicado a unos
ingresos 2,7 veces los del año anterior daba 334 $ por acción frente a un precio
de 989 $. El agregado sigue amortiguando el ciclo de inversión, que es por lo
que no se usa el último año, pero pesa cada año por su tamaño: MU ≈ 14 %.

Se proyectan los ingresos y no el flujo libre directamente porque el flujo libre
baila con cada ciclo de inversión. En MU, un año de capex fuerte lo hunde; en el
siguiente se dispara. Proyectar desde un año u otro daría valores distintos para
el mismo negocio.

**Valor.**
`VE = Σ FCFF_t / (1 + wacc)^t + VT / (1 + wacc)^10`, con
`VT = FCFF_10 × (1 + g_perpetuo) / (wacc − g_perpetuo)`. Convención de fin de
año. `Valor del capital = VE − deuda_total + efectivo`. Por acción, dividido por
**capitalización ÷ precio**, que es el recuento en la base en la que está el
precio.

**Escenarios.** Pesimista: `g_ref − margen` y `wacc + 1 punto`. Base: `g_ref` y
`wacc`. Optimista: `g_ref + margen` y `wacc − 1 punto`. El `margen` es
`max(MARGEN_MINIMO; ½·|g_ref|)`, el mismo del voto. Así el rango del DCF y el
voto de flujos dicen lo mismo con dos dibujos.

Si un escenario no cumple `HOLGURA_GORDON` —típicamente el optimista, que baja
el coste de capital—, su valor queda en `null` y el rango se pinta incompleto,
diciendo por qué. No se recorta el coste de capital para que cuadre: eso sería
cambiar el escenario sin decirlo.

**Sensibilidad.** Una tabla del valor base por acción con el coste de capital en
`wacc` ±2 puntos (paso de 1) en las filas y el crecimiento perpetuo ±1 punto
(paso de 0,5) en las columnas. Las celdas donde no se cumple `HOLGURA_GORDON` se
dejan vacías y se explica por qué. **La escribe N**, junto a la pantalla que la
pinta: en Revisar candidatos no se enseña, y una función que no llama nadie es
la que acaba borrada.

**Inverso.** Bisección sobre el `g` de la primera etapa, con todo lo demás en su
valor base, hasta que el valor por acción iguala el precio. Con margen de flujo
libre positivo, el valor crece con `g`, así que la bisección converge. Si ni con +80 % se
llega al precio, el resultado es «exige más del 80 %» y vota «cara». Si ni con
−30 % se baja hasta él, vota «barata».

**No aplica** si el margen de flujo libre normalizado es ≤ 0. La empresa quema
caja, y valorarla exigiría inventar cuándo deja de hacerlo. Tampoco aplica si
`wacc − g_perpetuo < HOLGURA_GORDON`, o si faltan años de historia.

### 6. `valoracion/epv.py` — valor sin crecimiento

`EPV = beneficio_operativo_normalizado × (1 − t) / wacc − deuda_total + efectivo`,
por acción en la base del precio. El beneficio operativo normalizado es el
margen operativo **agregado** de los ejercicios (suma de beneficios operativos
entre suma de ingresos) por los ingresos TTM, por la misma razón que en el DCF:
dos lecturas del mismo motor no pueden promediar distinto.

Además del valor, devuelve **qué parte del precio es apuesta por el
crecimiento**: `1 − EPV / precio`, cuando el EPV es positivo.

Greenwald ajusta también la diferencia entre la amortización y el capex de
mantenimiento. Aquí no se hace, porque ninguna fuente separa el capex de
mantenimiento del de expansión. Se dice en la pantalla.

**No aplica** con beneficio operativo normalizado ≤ 0, ni en las financieras.

### 7. `valoracion/residual.py` — bancos y aseguradoras

`k_e` es el de los supuestos. `BV_0` es el patrimonio neto. El ROE se mantiene
constante los diez años. El patrimonio crece con lo que se retiene:
`BV_t = BV_{t−1} × (1 + ROE × (1 − payout))`, con el payout de yfinance acotado
entre 0 y 1. Una pérdida reduce el patrimonio entera, sin repartir nada.

`Valor = BV_0 + Σ_{t=1..10} (ROE − k_e) × BV_{t−1} / (1 + k_e)^t + VT / (1 + k_e)^10`,
con `VT = (ROE − k_e) × BV_10 / (k_e − g_perpetuo)`. Sin `HOLGURA_GORDON` entre
`k_e` y `g_perpetuo`, no aplica, igual que el DCF.

**El exceso de rentabilidad persiste: decisión del usuario del 2026-10-12, antes
de medir.** El texto aprobado hacía converger el ROE al coste del capital en
diez años y no dejaba valor terminal. La revisión de la Task 7 lo midió:
valoraba JPM, GS, MET y PGR entre 1,1 y 2,0 veces su valor contable frente a
2,1–3,7 en el mercado, y las votaba «caras» por construcción. Era además
incoherente con el DCF, que mantiene el margen para siempre. Ahora el exceso
sobre el coste del capital persiste y crece al ritmo perpetuo, como el margen
del DCF.

`ROE_ref` es la mediana del ROE anual de `historia`: beneficio neto TTM sobre
patrimonio. **No es el KPI `roe` del panel**, que es trimestral.

Los escenarios y el inverso funcionan igual que en el DCF, con el ROE en lugar
de `g` y `k_e` en lugar de `wacc`. El inverso despeja el **ROE que el precio
exige**.

### 8. `valoracion/votos.py` — el veredicto

Cada voto es `barata`, `neutra`, `cara` o `no_aplica`, y el `no_aplica` lleva su
motivo como **clave** (`quema_caja`, `ebit_negativo`, `sin_historia`,
`sin_beneficio_operativo`, `sin_flujo_libre`, `wacc_bajo_crecimiento`, `sin_pares`, `sin_precio`,
`sin_tasa_libre`, `financiera`, `patrimonio_negativo`). Una valoración que no llega a calcularse
lleva su motivo en el nivel de arriba (`sin_estados`, `sin_historia`,
`sin_precio`, `sin_red`, `sin_tasa_libre`, `error_interno`). `sin_tasa_libre` no es de una empresa sino
de la fuente: al primero, `ranking/run.py` deja de preguntar por las demás,
porque con una red que no contesta cada intento tarda unos 21 s. `sin_red`
significa que Yahoo no devolvió nada utilizable, y eso también lo da un símbolo
que no conoce (medido con ZZZZQ y la red sana), así que el corte espera a dos
seguidos.

| Voto | Barata | Cara | Neutra |
|---|---|---|---|
| **Flujos** (DCF + inverso) | `g` implícito < `g_ref − margen` | `g` implícito > `g_ref + margen` | Dentro |
| **Flujos**, en financieras | `ROE` implícito < `ROE_ref − margen` | `ROE` implícito > `ROE_ref + margen` | Dentro |
| **Sin crecimiento** (EPV) | precio < EPV | **Nunca** | precio ≥ EPV |
| **Pares** | pilar de valoración ≥ +0,5 | ≤ −0,5 | Entre medias |

**El EPV nunca vota «cara», a propósito.** Pagar por el crecimiento no es estar
cara: casi todo el S&P 500 cotiza por encima de lo que valdría si dejara de
crecer. Que el EPV votara «cara» declararía sobrevalorado medio índice por ser
un índice de empresas que crecen. La consecuencia es que **«sobrevalorada» exige
que coincidan flujos y pares**: cara frente a sus propios números y frente a su
sector.

**La regla** (con `n` votos aplicables, `B` «barata» y `C` «cara»):

| Condición | Veredicto (clave) |
|---|---|
| `n < MIN_VOTOS` | `sin_datos` |
| `B ≥ 2` y `C = 0` | `infravalorada` |
| `C ≥ 2` y `B = 0` | `sobrevalorada` |
| `B ≥ 1` y `C ≥ 1` | `mixtas` |
| Cualquier otro | `en_rango` |

En las financieras sólo hay dos votos, así que el veredicto sólo es firme si
coinciden.

El veredicto se calcula siempre con los supuestos del programa. Un veredicto
calculado con supuestos cambiados por el usuario es cosa de N, y nunca se guarda.

### 9. `valoracion/plano.py` — la valoración como diccionario

Lo que se guarda en `ficha["valoracion"]`:

```json
{
  "version": "m1",
  "fecha": "2026-10-12",
  "estados_hasta": "2026-08-31",
  "moneda": "USD",
  "precio": 989.04,
  "precio_hora": "2026-10-12T15:59:00-04:00",
  "metodo": "flujos",
  "valor": {"pesimista": 610.0, "base": 870.0, "optimista": 1190.0},
  "margen_seguridad": -0.12,
  "implicito": {"magnitud": "crecimiento", "valor": 0.38, "referencia": 0.22,
                "margen": 0.11, "fuera_de_limites": null},
  "epv": {"por_accion": 410.0, "parte_crecimiento": 0.59},
  "votos": {"flujos": {"voto": "cara", "motivo": null},
            "sin_crecimiento": {"voto": "neutra", "motivo": null},
            "pares": {"voto": "barata", "motivo": null}},
  "veredicto": "mixtas",
  "supuestos": {"beta": {"valor": 1.42, "procedencia": {"fuente": "regresion",
                "indice": "^GSPC", "semanas": 104, "r2": 0.41}}}
}
```

Las cifras son ilustrativas. `estados_hasta` es el cierre del último ejercicio
con el que se valoró: la revisión del 2026-10-12 encontró empresas cuyo último
ejercicio válido va de uno a doce meses por detrás de su panel (PSKY, TAP,
FERG), y un valor sin la fecha de sus cifras se lee como de hoy. *Enmienda del
2026-10-14, en la revisión final:* aquí se decía que en candidatos no ocurre,
porque la guarda `MAX_ANTIGUEDAD_TRIMESTRES` del ranking los excluye, y es
falso. Esa guarda mira el último trimestre con KPIs del panel, no el último
ejercicio válido de la valoración, y además deja pasar dos trimestres de
retraso: PSKY, TAP y FERG sobreviven al ranking, y en la medida 83 de las 422
valoraciones calculadas llevan más de 137 días de retraso (TAP 287, PSKY 471).
En la corrida de la Task 16, EIX, GRMN e INCY salieron con 196–199 días. Por eso
`estados_hasta` se enseña siempre; en N, además, cualquiera puede traer uno. Se guardan **claves, nunca textos de pantalla**: las
etiquetas («Infravalorada», «Señales mixtas», «quema caja») viven en un
diccionario aparte que sólo lee la vista. Todo NaN se escribe como `null`, porque
`fichas.json` se escribe con `allow_nan=False` y ese es su contrato. La lectura
de vuelta la hace `aprobacion.carga.valoracion_de` (ver abajo), que tolera
claves ausentes: una versión futura del formato no puede romper la lectura de
una ficha vieja.

## Integración en Revisar candidatos

**`ranking/run.py`.** Después de construir las fichas, y con o sin IA (la
valoración no cuesta dinero), se llama a `valoracion.valorar(ticker,
pilar_valoracion)` para cada una de las 15 y se guarda el resultado en
`ficha["valoracion"]`. Si falla una, esa ficha lleva `{"version": "m1",
"motivo": "<clave>"}` y la corrida sigue: es la política de la descarga de
fundamentales, donde una empresa que falla se anota y se salta. El texto del
indicador de progreso pasa a mencionar la valoración.

**`aprobacion/carga.py`.** `valoracion` **no** entra en `_CAMPOS_FICHA`: es
opcional. Un `fichas.json` viejo y el de `salidas_ejemplo/` siguen cargando. Hay
un lector con `.get`, en el mismo estilo que `kpis_con_dato`, que devuelve `None`
si la clave falta o está corrupta. Es el defecto que ya pagó `kpis_por_pilar`:
validar la existencia de un campo y no su contenido dejaba reventar la lista a
la mitad, con tarjetas ya pintadas encima.

**`medidores_valoracion.py`** (nuevo, junto a `medidores.py`, que ya pasa de
las 450 líneas). Contiene las etiquetas de pantalla de cada clave y dos
funciones:
- `distintivo(valoracion)`: el veredicto con los colores semánticos del tema
  (verde para infravalorada, rojo para sobrevalorada, ámbar para mixtas y gris
  para en rango o sin datos). Sin valoración, una cadena vacía.
- `resumen(valoracion)`: los tres votos en una línea cada uno, el rango, el
  margen de seguridad y la procedencia de los supuestos.

`medidores.tarjeta_candidato` pinta el distintivo en la cabecera de la tarjeta.

**`vistas/candidatos.py`.** Dentro del desplegable de cada ficha, un bloque
«Valor intrínseco» con `medidores_valoracion.resumen` y esta nota:

> Un criterio transparente, no una previsión: no hay forma honesta de probar
> hacia atrás si acierta, porque las cifras guardadas son las últimas que
> publicó cada empresa, no las que se conocían en su día, y el universo arrastra
> sesgo de supervivencia.

*Enmienda del 2026-10-14, en la revisión final.* La nota decía que «las cifras
de yfinance no dicen cuándo se publicaron», pero en M los estados vienen de la
SEC. La causa real es que `fundamentals/panel.py` se queda con la última cifra
publicada de cada periodo (`drop_duplicates(..., keep="last")`): una
reexpresión pisa a la original.

La nota del orden («el score no está validado empíricamente») ya existe y no se
toca.

*Enmienda del 2026-10-13, en la revisión de la Task 13.* El bloque se llamaba
«Valoración», y tres líneas más arriba de la misma ficha está el pilar
«valoración» del score, que además es el voto «Frente a sus pares». Pasa a
llamarse «Valor intrínseco», que es como lo pidió el usuario. Además:
- La nota y la lectura del margen sólo salen cuando hay números. Con una
  fallida no hay margen ni votos que explicar, y la del margen tiene una
  variante para el beneficio residual, que compara ROE y no crecimiento.
- El aviso común deja la vista y pasa a `medidores_valoracion`, con tests.
  Avisa también del corte a mitad de corrida («11 de 15 candidatos sin
  valorar»), no sólo de que fallen todas.
- Un motivo que no es texto en un `fichas.json` editado a mano ya no tumba la
  pantalla entera.

**El acta** copia las fichas dentro, así que registra la valoración sin tocar
`aprobacion/acta.py`.

## Errores

| Situación | Qué se ve |
|---|---|
| Sin red al generar | Con datos guardados de menos de `ANTIGUEDAD_MAXIMA`, se valora con ellos y el precio enseña su hora. Sin ellos, las dos primeras fichas seguidas dicen `sin_red` y las demás heredan ese motivo sin volver a preguntar; el ranking sale igual |
| Falla la red sólo para la beta, la tasa efectiva o el consenso | Se valora con el valor por defecto, la tasa legal o sólo la historia, y la procedencia dice que fue porque Yahoo no devolvió datos |
| Un escenario no cumple la holgura de Gordon | El rango sale incompleto y dice cuál falta y por qué |
| `^TNX` no responde | Todas las fichas dicen `sin_tasa_libre`. Un aviso, no quince; si falla a mitad, el aviso dice cuántas quedaron sin valorar |
| Empresa que quema caja | El voto de flujos es `no_aplica`, con «quema caja: valorarla exigiría inventar cuándo deja de hacerlo», nunca un cero |
| Coste de capital por debajo del crecimiento perpetuo + 1 punto | El voto de flujos es `no_aplica`, por `wacc_bajo_crecimiento` |
| Ficha de una versión anterior | «Sin valoración: ficha de una versión anterior» |

## Cómo se prueba

1. **El criterio se congela en su propio commit**, antes de escribir ninguna
   medida.
2. **Identidades exactas**, la referencia positiva de este sub-proyecto:
   - con `g` igual a `g_perpetuo` desde el año 1, el DCF coincide con
     Gordon, `FCFF_1 / (wacc − g)`;
   - `inverso(precio = dcf(g))` devuelve `g`;
   - con `ROE_ini = k_e`, el beneficio residual vale exactamente `BV_0`;
   - con el precio igual al valor base de cada empresa, el voto de flujos es
     `neutra` en el 100 % de los casos.
3. **La regla del veredicto, entera**: las 64 combinaciones de tres votos con
   cuatro estados cada uno, contra una tabla escrita a mano.
4. **Contraste externo**: el valor presente nativo frente a `numpy_financial.npv`,
   en un test que se omite si no está instalado, igual que
   `test_contraste_contra_numpy_financial` de Seguimiento. `numpy_financial` no
   es dependencia del proyecto, así que en la suite normal se omite; se corrió
   una vez el 2026-10-14 con `uv run --with numpy-financial` y pasa. (El de
   Seguimiento no: llama a `xirr`, que esa librería no tiene; es un defecto de
   F, anotado aparte.)
5. **Trampas medidas, con su test**: el signo del capex de cada fuente; la beta de
   Yahoo que no se lee; el consenso cuya divisa no coincide con la de los
   estados; el NaN en el JSON; la ficha vieja sin `valoracion`; Visa por DCF y
   JPM por beneficio residual.
6. **Sabotaje de cada guarda.** Si al quitarla no cae ningún test, el trabajo
   no es repetir el sabotaje sino averiguar qué otra cosa está devolviendo la
   respuesta correcta.
7. **Tests `red`**: `^TNX`, una regresión de beta real, el `revenue_estimate` de
   MU, y las cadenas reales de industria de JPM, MET, GS, V y COF para fijar
   `INDUSTRIAS_FINANCIERAS`.
8. **Una medida, no un ajuste.** Con el criterio ya congelado, se pasa el motor
   por el S&P 500 desde la caché y se anexa aquí, con fecha, el reparto de
   veredictos y de votos `no_aplica` por sector. Sirve para ver, por ejemplo, si
   el criterio declara cara a medio índice. **Los listones no se mueven para
   corregirlo**: si hiciera falta moverlos, sería una enmienda fechada, no un
   retoque.
9. **Recorrido con la app arrancada**: generar candidatos sin IA, ver los
   distintivos y el detalle, aprobar y abrir el acta, y abrir un `fichas.json`
   viejo.

## Lo que M no resuelve

- **No predice.** No hay backtest honesto: yfinance no fecha las cifras y el
  universo tiene sesgo de supervivencia. Es la decisión, dicha en pantalla.
- **No ajusta arrendamientos, minoritarios ni opciones sobre acciones.** El valor
  del capital es VE − deuda + efectivo. En empresas con muchos arrendamientos
  operativos o con filiales en parte ajenas, el valor sale algo alto.
- **El capex de mantenimiento no se separa** del de expansión en el EPV.
- **COF, SYF, AXP y otros lenders de *Credit Services*, y RJF (*Asset
  Management*), van por DCF**, que no les sienta bien, porque la misma
  industria de Yahoo contiene a Visa y Mastercard. Su coste de la deuda choca
  con el techo y su coste de capital sale entre 0 y 0,4 puntos por encima del
  del capital propio (medido en la revisión de la Task 5).
- **La prima de riesgo está congelada** a 2026-10-01. Actualizarla es una
  enmienda fechada, no un cambio silencioso, porque mueve todos los veredictos a
  la vez.
- **Sólo dólares.** Pesos, otras divisas y ADRs son de N.
- **Fusiones y escisiones deforman el crecimiento histórico.** El CAGR de tres
  años de una empresa que compró otra mide la compra, no el negocio: en la
  revisión de la Task 5, AMCR, SW y FITB salían recortadas en +40 %, y DD o FTV
  en −10 %. El tope lo acota; no lo corrige.
- **El coste de la deuda casi nunca lleva diferencial.** Sobre 500 empresas,
  el 79 % sale con `k_d` igual a la tasa libre, por el suelo o por no declarar
  gasto financiero. Es inmaterial con poca deuda y de unas cuatro décimas de
  coste de capital en una empresa como T, con un 47 % de deuda.
- **Las betas de R² casi nulo** (KO, XOM y T, por debajo del 1,5 %) quedan en
  0,3–0,4 tras Blume, así que su coste de capital queda cerca de la tasa libre.
  En T (coste de capital del 5,8 % y diferencial de Gordon de 3,3 puntos) el
  valor sale 4,1 veces el precio: `HOLGURA_GORDON` sólo exige un punto y deja
  pasar múltiplos terminales de hasta unas cien veces el flujo. El R² viaja en
  la procedencia y la pantalla lo enseña.
- **El margen agregado pesa cada año por sus ingresos**, así que un año atípico
  tira de él. CCL 2022 (el 6 % de los ingresos de la ventana, con un margen del
  −96 %) baja su margen del 14,9 % al 6,1 % y le cambia el voto de flujos de
  «barata» a «cara»; KO 2025, con un flujo operativo de 1.075 millones frente a
  12.000–15.000 los demás años, lo baja del 24,5 % al 20,7 %. Si el agregado
  llegara a ser ≤ 0, una empresa con años recientes sanos saldría como que
  quema caja. Quitar siempre el peor año lo arreglaba en esos casos pero
  sesgaba todos los márgenes hacia arriba, y por eso no se hizo.
- **36 empresas no financieras no tienen DCF** (LLY, COST, NEE, VZ, PEP, COP…):
  tienen cinco años de historia pero no declaran capex, así que no hay flujo
  libre. Su voto de flujos sale `sin_flujo_libre`. Con el EPV también sin
  beneficio operativo (LLY), sólo les queda el voto de pares y el veredicto es
  «sin datos suficientes».
- **Diez empresas salen con valor por acción negativo** (SO, WEC, ETR, PEG, BA,
  DOW…): la deuda supera el valor de la empresa que da el DCF. Es coherente con
  el puente, y el margen de seguridad baja de −100 %.
- **«Sobrevalorada» exige que coincidan flujos y pares**, así que AAPL, AMZN, GE,
  PLD o CAT salen «en rango» con márgenes de seguridad de −40 % a −95 %: sus
  flujos dicen «cara» y sus múltiplos están en línea con el sector. Al otro lado,
  CHTR y CMCSA salen infravaloradas con valores 6–13 veces el precio, por el
  apalancamiento de una deuda alta sobre un capital pequeño.
- **Cinco empresas con cinco años de historia salen `sin_historia`** (APA, DTE,
  EQR, SYF, XEL): el motor de fundamentales no reconoce su etiqueta de ingresos.
  La medida de la Task 17 añade FERG, PSKY y WAT, sin diagnosticar.
  Es la misma clase de rótulo inexacto que `sin_flujo_libre` arregló, con otra
  causa, y se deja anotado.
- **Una de cada siete empresas no tiene valor sin crecimiento.** 69 empresas no
  financieras del S&P 500 no etiquetan `OperatingIncomeLoss` (XOM, JNJ, LLY,
  MRK, PFE, IBM, GE…), y el motor de fundamentales no sustituye ese concepto a
  propósito (ver `fundamentals/concepts.py`). Su voto de EPV sale
  `sin_beneficio_operativo`, que es lo que pasa, y no «sin historia».
- **Los rangos del beneficio residual son muy anchos.** Los escenarios mueven
  el ROE ±½ y el coste del capital ±1 punto, y con el exceso persistente eso es
  ±130 % del exceso sobre el coste del capital: JPM va de 81 a 1.182 $ con un
  precio de 337 $ (14,6 veces entre extremos, frente a 2,4 de AAPL o 3,4 de KO
  en el DCF). En el pesimista, el ROE de JPM (7,9 %) cae por debajo de su
  coste del capital (9,7 %) y el exceso es negativo para siempre. El voto no
  usa el rango sino el ROE implícito, así que sólo afecta a lo que se dibuja;
  N decidirá si para las financieras lo pinta. Por debajo de un ROE de un 2 %
  el valor sale negativo, y por debajo de unos −7 % deja de crecer con el ROE;
  el inverso no se ve afectado, porque con un precio positivo la raíz está
  siempre en la zona creciente (comprobado analíticamente y en 336
  combinaciones de parámetros en la revisión de la Task 7).
- **El payout es sólo el dividendo, y es el dato menos fiable del residual.**
  Las recompras no cuentan, así que el patrimonio se proyecta creciendo más de
  lo que crece, y con el exceso persistente eso se nota: con payout 1 el valor
  de JPM baja un 35 % (372 → 242 $) y su ROE implícito sube del 15,1 % al
  21,6 %; PGR baja un 43 %, MET un 18 % y GS un 13 %. Usar dividendos más
  recompras del estado de flujos sería más correcto y queda como mejora.
- **El margen agregado también pesa los años de saneamiento**: el año 2023 de T,
  con 2.700 millones de beneficio operativo negativo por un deterioro, baja su
  margen operativo del 20,1 % al 14,1 % y le cambia el voto de EPV de «barata»
  a «neutra».
- **Simplificaciones conocidas del DCF**, con su dirección:
  - el descuento a fin de año infravalora entre un 3 % y un 7 %;
  - el flujo operativo suma las compensaciones en acciones y las acciones no se
    diluyen, lo que sobrevalora (NVDA, MU);
  - el flujo operativo ya incluye los intereses del efectivo que el puente
    vuelve a sumar, una doble cuenta pequeña;
  - los intereses que se suman son los devengados, no los pagados;
  - un gasto financiero no declarado suma cero (AAPL no lo declara en 3 de 5
    años: unas cinco décimas de margen y un 2 % de valor);
  - el TTM acaba en `estados_hasta`, que puede ir hasta unos cuatro meses y medio
    por detrás de la fecha de la valoración.
- **Las empresas con trimestres de dieciséis semanas** (KR) salen sin
  fundamentos: el panel del motor descarta ese trimestre por durar más de cien
  días, ningún año queda completo, y es mejor `sin_historia` que el TTM de 448
  días que salía antes. La causa está en `fundamentals/panel.py`.
- **No hay listón de antigüedad de los estados.** Se enseña `estados_hasta` en
  vez de inventar uno después de congelar el criterio. Y hace falta también en
  candidatos: una de cada cinco valoraciones de la medida va más de 137 días por
  detrás, y en una misma ficha los pilares y la valoración pueden hablar de
  periodos distintos (TAP: panel a 2026-06-30, estados a 2025-12-31). Un listón
  sería una enmienda que decide el usuario.
- **Sin red, la valoración sale de lo guardado** hasta `ANTIGUEDAD_MAXIMA`, sin
  un aviso arriba que lo diga; sólo el precio enseña su hora.

## Medida preliminar de la revisión de la Task 9 (2026-10-13)

La revisión de calidad del motor lo pasó por las 503 empresas del S&P 500 con
precios y betas reales, **después** de congelar el criterio y de las dos
decisiones de método (margen agregado y exceso persistente en el residual), que
se tomaron con casos sueltos y antes de este barrido. Reparto de veredictos: en
rango 338, sin datos suficientes 80, infravalorada 41, sobrevalorada 33, señales
mixtas 8, y 3 sin calcular. Ningún listón se movió al verlo. La medida oficial,
con los pilares reales del ranking, es la de la Task 17.

## Resultado de la medida (2026-10-14)

Corrida del 2026-10-14 con `scripts/medir_valoracion.py`, con el criterio `m1`
sin tocar, sobre las 423 empresas del S&P 500 que sobreviven a las guardas del
ranking (`construir_ranking(con_llm=False, con_valoracion=False)`), cada una con
su pilar de valoración real. Tardó unos diez minutos. Las tablas son la salida
del script tal cual, con los títulos bajados un nivel. La fila `nan` de los
votos es KR, que no llegó a calcularse, y la tabla de motivos cuenta votos, no
empresas: una empresa `sin_historia` aporta dos.

### Veredictos

| veredicto     |   count |
|:--------------|--------:|
| en_rango      |     329 |
| infravalorada |      38 |
| sobrevalorada |      33 |
| sin_datos     |      13 |
| mixtas        |       9 |
| no_calculada  |       1 |

### Veredictos por sector

| sector                 |   en_rango |   infravalorada |   mixtas |   no_calculada |   sin_datos |   sobrevalorada |
|:-----------------------|-----------:|----------------:|---------:|---------------:|------------:|----------------:|
| Communication Services |         15 |               4 |        1 |              0 |           1 |               2 |
| Consumer Discretionary |         36 |               5 |        1 |              0 |           0 |               1 |
| Consumer Staples       |         24 |               4 |        0 |              1 |           0 |               3 |
| Energy                 |         12 |               3 |        0 |              0 |           3 |               2 |
| Financials             |         18 |               4 |        1 |              0 |           0 |               2 |
| Health Care            |         43 |               6 |        3 |              0 |           2 |               4 |
| Industrials            |         65 |               4 |        2 |              0 |           2 |               5 |
| Information Technology |         56 |               6 |        1 |              0 |           1 |               8 |
| Materials              |         20 |               1 |        0 |              0 |           0 |               3 |
| Real Estate            |         15 |               1 |        0 |              0 |           0 |               1 |
| Utilities              |         25 |               0 |        0 |              0 |           4 |               2 |

### Voto flujos

| voto_flujos   |   count |
|:--------------|--------:|
| neutra        |     137 |
| cara          |     129 |
| barata        |      99 |
| no_aplica     |      57 |
| nan           |       1 |

### Voto sin_crecimiento

| voto_sin_crecimiento   |   count |
|:-----------------------|--------:|
| neutra                 |     334 |
| no_aplica              |      64 |
| barata                 |      24 |
| nan                    |       1 |

### Voto pares

| voto_pares   |   count |
|:-------------|--------:|
| neutra       |     322 |
| cara         |      58 |
| barata       |      42 |
| nan          |       1 |

### Motivos de no aplica

|                         |   count |
|:------------------------|--------:|
| sin_beneficio_operativo |      46 |
| quema_caja              |      26 |
| sin_flujo_libre         |      25 |
| sin_historia            |      12 |
| ebit_negativo           |      11 |
| financiera              |       1 |

### Valoraciones que no se calcularon

| motivo       |   count |
|:-------------|--------:|
| sin_historia |       1 |

**Qué proporción sale en cada veredicto.** De las 423, 329 salen en rango
(77,8 %), 38 infravaloradas (9,0 %), 33 sobrevaloradas (7,8 %), 13 sin datos
suficientes (3,1 %) y 9 con señales mixtas (2,1 %). Una no se calculó: KR, por
sus trimestres de dieciséis semanas, ya anotados en «Lo que M no resuelve».
Veredictos firmes, en un sentido u otro, hay 71: uno de cada seis. Las 33
sobrevaloradas son todas flujos «cara» más pares «cara», porque el EPV no vota
«cara»; las 38 infravaloradas llegan por más caminos (18 por flujos y pares, 9
por los tres votos, 9 por flujos y EPV con los pares neutros y 2 con un voto que
no aplica). «En rango» no quiere decir que los votos coincidan: en 149 de las
329, los flujos votan «barata» (56) o «cara» (93) y los pares se quedan
neutros. Frente a la medida preliminar de la Task 9 (503 empresas: en rango 338,
sin datos 80, infravalorada 41, sobrevalorada 33, mixtas 8 y 3 sin calcular),
los cuatro veredictos con votos apenas se mueven y la diferencia está casi
entera en «sin datos», que baja de 80 a 13. Coincide con el cambio de universo:
las 80 empresas que el ranking excluye (75 por `pilar_sin_datos`) son 51
financieras, entre ellas todos los bancos y todas las aseguradoras de riesgo
salvo MET, 14 inmobiliarias y 15 de otros sectores. Aquí todas las calculadas
tienen voto de pares, así que «sin datos» exige que fallen a la vez flujos y
EPV.

**Qué sectores concentran los `no_aplica` y por qué.** Hay 121 votos que no
aplican, 57 de flujos y 64 de EPV; ninguno de pares. **Utilities** reúne 28 con
sólo 31 empresas, y 24 de ellas se quedan sin voto de flujos: 17 por
`quema_caja` (AEE, DUK, EXC, PCG, SRE…: en su mayoría eléctricas reguladas, que
invierten más de lo que genera su flujo operativo y financian la diferencia con
deuda, así que su margen de flujo libre agregado no es positivo por modelo de
negocio y no por apuro), 5 por `sin_flujo_libre` (AEP, CMS, D, ED y NEE no
declaran capex) y 2 por `sin_historia` (DTE, XEL). Por eso Utilities no tiene
ninguna infravalorada y reúne 4 de los 13 «sin datos». Le siguen **Health Care**
con 19 votos, **Energy** con 13 en sólo 20 empresas e **Industrials** con 13. El
motivo más frecuente es `sin_beneficio_operativo` (46, todo del EPV), repartido
por las empresas que no etiquetan `OperatingIncomeLoss`: 9 en Health Care (JNJ,
LLY, MRK, PFE, BMY…), 8 en Industrials (GE, ETN, EMR…), 6 en Energy (XOM, CVX,
COP…), 6 en Materials y 4 en Communication Services (FOX, FOXA, NWS, NWSA).
`sin_flujo_libre` (25) se reparte entre Energy (COP, EOG, FANG, PSX, VLO),
Health Care y Utilities, con 5 cada uno. `ebit_negativo` (11) es un beneficio
operativo normalizado que no llega a positivo (BA, INTC, CRWD, DDOG, WBD…). Los
`sin_historia` son 6 empresas: APA, DTE y XEL, ya anotadas, y FERG, PSKY y WAT,
nuevas. El único `financiera` es MET, la única superviviente que se valora por
beneficio residual.

**Si algún reparto sugiere un listón mal calibrado.** No se cambia ninguno
aquí; quedan tres cosas para que el usuario decida. Primera, `UMBRAL_PARES`:
entre las supervivientes, el pilar de valoración tiene una desviación típica de
0,505 y su percentil 90 es 0,496, así que ±0,5 es cerca de una desviación
entera y no media. Los pares sólo votan en el 24 % de los casos (42 «barata» y
58 «cara»), frente al 62 % de los votos de flujos que aplican, y como
«sobrevalorada» necesita pares «cara», es ese listón el que deja en rango a 93
empresas con flujos «cara». Se eligió para coincidir con el «por encima de sus
pares» de `ranking.fichas.descriptor`; bajarlo (con 0,25 votarían el 56 %)
rompería esa coincidencia, y es una enmienda fechada que sólo el usuario puede
pedir. Segunda, no es un listón sino un método: 24 de las 31 utilities no
tienen voto de flujos, y como el EPV nunca vota «cara», una utility sin flujos
no puede salir sobrevalorada; un tratamiento propio para las reguladas, como el
residual para los bancos, sería otra enmienda. Tercera, esta medida no dice nada
de los listones del beneficio residual (`MARGEN_ROE_MINIMO`,
`INVERSO_ROE_LIMITES`): con los bancos y las aseguradoras fuera del ranking,
sólo se midió MET. `MARGEN_MINIMO` no parece mal puesto: los flujos votan a
menudo y en los dos sentidos (99 «barata», 129 «cara», 137 neutros).
