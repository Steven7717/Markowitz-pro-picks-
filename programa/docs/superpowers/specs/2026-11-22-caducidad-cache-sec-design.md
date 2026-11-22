# Caducidad de la caché de la SEC

**Fecha:** 2026-11-22
**Estado:** diseño, pendiente de plan
**Sub-proyecto:** Q (va antes que R, el ranking value, que se apoya en él)

## El problema

`fundamentals.fetch.load_facts` descarga los hechos XBRL de cada empresa una vez
y después los lee siempre de `fundamentals/.cache`. `refresh=False` es el valor
por defecto, y ninguna pantalla pide nunca `refresh=True`. El docstring lo
defiende: refrescar es «un acto deliberado», para que dos corridas no cambien de
cifras sin que nadie lo pida. Pero ese acto no existe en ningún sitio, así que
en la práctica la caché no caduca nunca.

Medido en la máquina del autor el 2026-11-22: los **503** ficheros de
`fundamentals/.cache` tienen fecha del **2026-08-30**. El ranking no ve ningún
10-Q del tercer trimestre de 2026.

Ninguna guarda lo detecta. `datos_rancios` (`ranking/score.py`) mide el rezago
de cada empresa contra el trimestre más reciente del **panel**, no contra la
fecha de hoy. Eso es deliberado y correcto para comparar empresas entre sí,
pero si todo el panel está viejo, nadie queda marcado.

Lo heredan todos los que llaman a `load_facts`: el ranking (B), la valoración
(`valoracion/fundamentos.desde_sec`, M) y el Analizador (N).

## La regla

Un fichero de caché se vuelve a pedir a la SEC cuando se cumplen **las dos**
condiciones:

1. **Probablemente hay un informe nuevo.** El último cierre de periodo del
   fichero (`period_end` máximo entre las filas con `fiscal_period` en
   Q1–Q4/FY) tiene más de **75 días**. Un 10-Q se presenta en los 40–45 días
   siguientes al cierre del trimestre y un 10-K en 60–90; 75 días cubre el 10-Q
   de cualquier tipo de empresa sin ir a buscar antes de tiempo.
2. **No se preguntó hace poco.** El fichero (su `mtime`) tiene más de **7
   días**. Sin esta condición, una empresa que se retrasa en presentar se
   volvería a pedir en cada corrida. Con ella, se pide como mucho una vez por
   semana.

Las dos constantes viven en `fundamentals/fetch.py` como
`DIAS_HASTA_INFORME_NUEVO = 75` y `DIAS_ENTRE_COMPROBACIONES = 7`. La fecha de
hoy entra por un parámetro (`hoy: date | None`), para que los tests no dependan
del reloj.

Si la SEC devuelve lo mismo que ya había, se reescribe el fichero igualmente:
el `mtime` nuevo es lo que marca «comprobado hoy».

`refresh=True` sigue existiendo y sigue forzando la descarga de todo.

## Cuando la SEC no contesta

Una empresa caducada **tiene datos**: los de su fichero. Que falle la nueva
descarga no puede costar la empresa, ni la corrida.

- Si falla la descarga de una empresa caducada, se usa su fichero viejo y se
  anota en un campo nuevo de `CoverageReport`, `servidas_caducadas`. La empresa
  sigue en `included`.
- Si salta un cortacircuitos (`RACHA_MAXIMA` o `SIN_RESPUESTA_MAXIMO`), la
  corrida **no** aborta mientras queden ficheros que servir. Deja de preguntar a
  la red durante el resto de la corrida (`sin_red_en_esta_corrida = True`) y
  sirve todos los caducados desde la caché. Solo aborta con `CorridaAbortada`,
  como hoy, si el cortacircuitos salta y las empresas que faltan **no** tienen
  fichero.
- Un intento sobre un caducado que falla **sí** cuenta para la racha y para los
  segundos sin respuesta, porque sí se preguntó a la red. Servir el fichero
  después no la reinicia, igual que hoy un acierto de caché no la reinicia.

Sin esto, con la caché llena y sin conexión, las primeras diez empresas
caducadas harían abortar una corrida que tenía todos sus datos.

## Que se vea

- `corrida.json` gana un bloque `datos_sec`: el trimestre natural más reciente
  del panel, la fecha de descarga más antigua y la más reciente entre los
  ficheros usados, cuántas empresas se actualizaron en esta corrida y cuántas se
  sirvieron caducadas.
- La pantalla de Candidatos enseña una línea debajo del resumen de la corrida,
  por ejemplo: «Datos de la SEC hasta el 3T 2026 · 41 empresas actualizadas en
  esta corrida · 0 servidas sin actualizar». Si hay servidas caducadas, la línea
  sale como aviso (`st.warning`) y dice cuántas y por qué.
- El docstring de `load_facts` se corrige: el refresco deja de ser solo un acto
  deliberado y pasa a ser una regla declarada. La reproducibilidad se conserva
  de otra forma: dos corridas con el mismo bloque `datos_sec` usan los mismos
  datos.

## Qué no cambia

- La caché de precios (`research/loader.py`) va por ventana de fechas. Un
  trimestre nuevo pide fechas nuevas y se descarga solo; los precios ya
  guardados son históricos y no envejecen.
- La guarda `datos_rancios` sigue midiendo contra el panel.
- Los riesgos del 10-K (`ranking/filings.py`) siguen sin caducar. Son anuales y
  solo alimentan la narrativa.

## Tests

- La regla con `hoy` fijo: cierre a 74/76 días × fichero de 6/8 días. Solo pide
  cuando las dos condiciones se cumplen.
- El último cierre ignora las filas sin `fiscal_period` trimestral o anual.
- Un caducado cuya descarga falla se sirve desde la caché, queda en
  `servidas_caducadas` y en `included`.
- El cortacircuitos salta con caducados pendientes: deja de pedir y no aborta.
  Salta con empresas sin fichero: aborta como hoy.
- Un fallo sobre un caducado cuenta para la racha.
- El bloque `datos_sec` de `corrida.json` y la línea de la pantalla.
- Los tests actuales de `test_fundamentals_fetch.py` siguen pasando. Los que
  crean ficheros de caché fijan `hoy` para que no caduquen solos.
