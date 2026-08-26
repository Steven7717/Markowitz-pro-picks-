# Sub-proyecto C — Handoff y gate de aprobación

**Fecha:** 2026-08-15
**Estado:** diseño aprobado, sin implementar

## Qué entrega

Una pantalla donde un humano revisa los candidatos que produjo el sub-proyecto B,
aprueba o rechaza cada uno, puede añadir empresas a mano, y deja constancia
fechada de la decisión. Los tickers aprobados llegan al optimizador que ya
existe.

Cierra la cadena del proyecto: A ingiere, B ordena y razona, **C decide**, y el
optimizador reparte pesos. La decisión sigue siendo humana — es la restricción
que `CONTEXTO.md` recoge como no negociable: *los agentes proponen, nunca
ejecutan*.

## Decisiones tomadas

| Decisión | Elección | Por qué |
|---|---|---|
| Dónde vive | Página nueva en la app actual | El traspaso al optimizador es el punto; compartir sesión elimina un formato de fichero y un copiar y pegar |
| Traspaso | `st.session_state["tickers_aprobados"]` | Streamlit comparte la sesión entre páginas |
| Poder del revisor | Aprobar, rechazar y **añadir a mano** | El criterio de B no puede evaluar a un banco; sin añadir, ese sesgo medido no tiene corrección posible |
| Rastro | Acta fechada **con las fichas dentro**, de aprobados y no aprobados | `fichas.json` se sobrescribe en cada corrida: una referencia no valdría nada |
| Origen de datos | Lee `salidas/`, no ejecuta B | Mantiene el ranking como acto deliberado y deja C probable sin red ni credenciales |
| Estructura | Paquete `aprobacion/` + página fina | Igual que `research/`, `fundamentals/` y `ranking/`: la lógica se prueba sin arrancar Streamlit |

## Arquitectura

```
salidas/fichas.json  ─┐
salidas/corrida.json ─┴─→ aprobacion.carga ─→ pages/1_Revisar_candidatos.py
                                                        │
                                       ┌────────────────┴────────────────┐
                                       ▼                                 ▼
                            actas/<fecha>.json              st.session_state
                            (el rastro duradero)          (→ app.py, optimizador)
```

Paquete nuevo `aprobacion/`, hermano de `ranking/`:

- **`aprobacion/carga.py`** — lee y valida `salidas/fichas.json` y
  `salidas/corrida.json`. Devuelve un `Candidatos`. Si el contrato está roto,
  falla nombrando el campo que falta.
- **`aprobacion/acta.py`** — fusiona aprobados con añadidos a mano, resuelve
  duplicados, construye el acta y la escribe.

La página es `pages/1_Revisar_candidatos.py`, con la convención `pages/` de
Streamlit. **`app.py` no se toca salvo una línea**: sigue siendo la página de
inicio y el optimizador tal cual está, y su campo de tickers pasa a leer un valor
por defecto de la sesión.

```python
value=", ".join(st.session_state.get("tickers_aprobados", TICKERS_POR_DEFECTO))
```

### Lo que cambia en el sub-proyecto B

`ranking/run.py:guardar()` escribe además **`salidas/corrida.json`** con los
metadatos que el acta necesita y que hoy sólo existen como prosa dentro de
`informe.md`: fecha, universo, empresas con fila en el panel, supervivientes,
recuento de exclusiones por motivo, tope sectorial, tamaño del top y si hubo LLM.

Es un cambio **aditivo**: `fichas.json` no cambia de forma, así que el `salidas/`
que ya está en el repo sigue siendo válido.

Se descartaron dos alternativas de estructura:

- **Todo dentro de la página de Streamlit.** Menos ficheros, pero la lógica sólo
  se podría probar arrancando la app. Con 537 tests detrás, sería el primer trozo
  del proyecto sin cobertura real.
- **Extender `ranking/`.** Evita un paquete nuevo, pero mezcla responsabilidades:
  `ranking/` produce candidatos y no debería saber que existe un humano que los
  aprueba.

## El acta

Vive en **`actas/`, en la raíz, no en `salidas/`**. La distinción no es
cosmética: `salidas/` se regenera corriendo B otra vez, y un acta no se regenera
nunca. Mezclarlas invita a borrar `salidas/` un día y llevarse por delante el
registro.

Un fichero por aprobación, nombrado por marca de tiempo
(`actas/2026-08-15-1842.json`), en lugar de un fichero que crece — mismo motivo
por el que `fundamentals` cachea un fichero por ticker: una corrida que muere a
mitad de escritura no puede corromper el historial entero. Se escribe con el
patrón que el repo ya usa dos veces (temporal y `replace()`, atómico) y en JSON
estricto, `allow_nan=False`, igual que el contrato de B.

Los campos `corrida` y `ficha` llevan copiado entero el contenido de
`corrida.json` y de la ficha correspondiente; van abreviados aquí para que se lea
la estructura.

```json
{
  "fecha": "2026-08-15T18:42:00",
  "corrida": {"fecha": "2026-08-15", "universo": "sp500", "n_panel": 502,
              "n_supervivientes": 425, "exclusiones": {"pilar_sin_datos": 72},
              "tope_por_sector": 3, "tamano_top": 15, "con_llm": false},
  "aprobados": [
    {"ticker": "CPRT", "origen": "ranking", "puesto": 1, "ficha": {"…": "…"}},
    {"ticker": "JPM",  "origen": "manual", "puesto": null, "ficha": null,
     "motivo": "el criterio no puede evaluar bancos; entra por decisión propia"}
  ],
  "no_aprobados": [
    {"ticker": "PLTR", "puesto": 2, "ficha": {"…": "…"},
     "motivo": "concentración de clientes públicos"}
  ]
}
```

Tres decisiones que no son obvias:

**Las fichas viajan copiadas dentro del acta.** Es el punto entero: `fichas.json`
se sobrescribe en la siguiente corrida, así que una referencia no valdría nada.
Son unos 19 KB las quince; un acta ronda los 25 KB.

**La segunda lista se llama `no_aprobados`, no `rechazados`.** Como las casillas
nacen desmarcadas, no marcar una puede significar dos cosas muy distintas: que se
miró y se descartó, o que no se llegó a mirar. Llamarlas rechazadas afirmaría un
juicio que quizá nunca ocurrió, y meses después el acta estaría mintiendo sobre
lo que pasó. **El `motivo` es lo que distingue una cosa de la otra**: si está
escrito, hubo descarte deliberado; si no, sólo consta que no entró.

**Esa lista se guarda con su ficha, igual que los aprobados.** "Por qué no tengo
X" es tan buena pregunta como la contraria. Y hay una razón más fuerte: si con el
tiempo se descarta sistemáticamente lo que el score pone arriba, **eso es
información sobre el criterio**, y sólo es visible si queda escrito. Mismo
principio que hizo útil medir las exclusiones de B en vez de suponerlas.

**El motivo es obligatorio en los añadidos a mano**, opcional en los no
aprobados. Un
ticker que entra sin ranking no tiene ningún respaldo cuantitativo: la razón
humana es la única justificación que va a existir, y si no se escribe en el
momento, no se reconstruye. Es la misma disciplina que el proyecto aplica con las
enmiendas fechadas. Reversible en una línea si en la práctica estorba.

**Lo que el acta no hace:** no guarda los pesos que calcule Markowitz después. El
acta responde "qué empresas aprobé y por qué"; lo que el optimizador haga con
ellas depende de horizonte, estrategia y límites que cambian a cada rato, y ya
tiene su propia exportación a PDF y Excel. Meterlo aquí ataría el gate a los
parámetros del optimizador sin ganar nada.

## La página

**Arriba, el contexto de la corrida**, leído de `corrida.json`:

> Estas 15 salen de 502 empresas con datos. **77 quedaron excluidas** por las
> guardas — 50 de ellas financieras, 13 inmobiliarias. El criterio no puede
> evaluar el pilar de solidez de un banco.

Ese sesgo está hoy enterrado en un documento de diseño. Ponerlo delante en el
momento de decidir es lo que convierte un sesgo documentado en un sesgo **tenido
en cuenta**.

Después, una fila por candidato: casilla de aprobación, puesto, ticker, sector y
compuesto; y un desplegable con la ficha entera — los cuatro pilares, los tres
KPIs fuertes y los tres flojos con su valor, la cobertura, a quién desplazó por
el tope sectorial, y la narrativa con sus citas si la hay. Cuando `generada_por`
sea `"plantilla"`, se dice sin rodeos: no hay narrativa, se juzga por los
números.

Tres reglas que le dan sentido al gate:

**Las casillas nacen desmarcadas.** Si llegaran marcadas, aprobar los quince
sería un clic y el gate pasaría a ser decorado. Desmarcadas, cada empresa exige
un acto deliberado. Es más fricción a propósito.

**Una cita sin verificar se ve, o no sirve de nada.** Es la restricción que
arrastra B entera — todo su trabajo de verificación existe para que "trazable"
signifique algo. La cita no verificada sale marcada junto al riesgo que sostiene,
no en una nota al pie ni en un color suave. **Si el revisor puede leer la ficha
entera sin enterarse de que una cita es inventada, C ha fallado.**

**Añadir a mano pide el motivo antes de dejar añadir.** El campo de ticker y el
de motivo van juntos; sin el segundo, el botón no hace nada. Se valida sólo la
forma del ticker (letras y guion, en mayúsculas) y se avisa de que, si no tiene
precio, el optimizador fallará más adelante. **No se llama a yfinance desde el
gate**: mantenerlo sin red es lo que permite probarlo entero sin depender de
nada externo.

Abajo, el botón de aprobar, deshabilitado mientras no haya nada seleccionado
—aprobar una lista vacía no significa nada—. Al pulsarlo escribe el acta, deja
los tickers en la sesión y dice explícitamente que ya se puede pasar a la página
del optimizador.

## Fallos previstos

| Situación | Qué hace |
|---|---|
| No existe `salidas/fichas.json` | La página explica qué comando correr. Sin rastro de pila |
| Esquema viejo o fichero truncado | Falla visible, nombrando el campo que falta |
| Falta `corrida.json` pero hay fichas | **Deja revisar igual**, avisando de que no hay contexto de corrida |
| Ticker añadido que ya está en el ranking | Se rechaza con un mensaje; **no se deduplica en silencio** |
| Nada aprobado | El botón está deshabilitado |
| `actas/` no se puede escribir | Falla al aprobar y **no traspasa nada a la sesión** |

Tres de esas filas son decisiones y no detalles:

- **La tercera es real, no hipotética:** el `salidas/` que existe hoy se generó
  antes de que `corrida.json` existiera, así que ese camino se ejercita desde el
  primer día.
- **La cuarta:** deduplicar en silencio es peor de lo que parece. Si se añade
  `JPM` a mano con su motivo escrito y el sistema lo absorbe porque ya estaba, el
  motivo desaparece sin aviso.
- **La sexta fija un orden:** el acta se escribe primero, y el traspaso al
  optimizador sólo ocurre si esa escritura salió bien. El peor resultado posible
  sería aprobar, perder el registro y seguir adelante creyendo que quedó
  constancia.

## Pruebas

Todo `aprobacion/` se prueba **sin Streamlit y sin red**: cargar y validar,
fusionar aprobados con añadidos, construir el acta, serializar en JSON estricto,
escribir de forma atómica y sanear un fichero corrupto. La página se queda lo
bastante fina como para que lo único sin cubrir sea el cableado de widgets.

Dos tests llevan el peso:

- **El acta sobrevive a que B se vuelva a correr.** Se escribe un acta, se
  sobrescribe `fichas.json` con otra cosa, y se comprueba que el acta sigue
  conteniendo las fichas originales. Es la promesa entera del artefacto; si eso
  no muerde, el resto es decorado.
- **Sin motivo no hay añadido a mano.** La regla que impide que un ticker sin
  respaldo cuantitativo entre sin dejar dicho por qué.

Y la disciplina que dejó B: cada test se demuestra **rompiendo a propósito lo que
dice verificar** y enseñando el fallo literal. En las quince tareas de B eso
encontró un defecto real en diez de las once revisiones, y casi siempre era un
test que no podía fallar.

## Lo que este sub-proyecto hereda y no puede arreglar

La lista corta llega con un **ladeo sectorial medido**: Financials perdió el
65,8% de sus empresas y Real Estate el 41,9%, porque el pilar `solidez`
(`deuda_neta_ebitda`, `cobertura_intereses`, `razon_corriente`) está indefinido
para un banco por construcción. Está en la enmienda 3 del diseño de B.

C no lo corrige — no puede: el criterio de B es un artefacto de pre-registro
congelado. Lo que C hace es **hacerlo visible en el momento de decidir** y dar la
única palanca disponible, que es añadir a mano con el motivo escrito.
