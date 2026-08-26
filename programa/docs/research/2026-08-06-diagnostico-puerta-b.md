# Diagnóstico de la Puerta B — por qué el control aleatorio la pasó

**Fecha:** 2026-08-06
**Naturaleza:** Análisis **posterior** a ver los resultados. No forma parte del criterio pre-registrado y no modifica ningún umbral ni ningún veredicto.

Este documento existe porque el veredicto ([2026-08-06-veredicto-senales-tecnicas.md](2026-08-06-veredicto-senales-tecnicas.md)) contiene un resultado que exige explicación: el **control aleatorio pasó la Puerta B** (Δ Sharpe 0.042 contra un error estándar de 0.028). Una señal de ruido puro no debería mejorar el momento de entrada.

Se deja constancia separada, fechada y etiquetada como post-hoc en vez de editar el criterio o el veredicto, por la misma razón por la que el criterio se congeló antes de escribir código: lo que hace creíble un pre-registro es poder auditar qué se decidió antes y qué después.

## Las dos explicaciones posibles

**(a) Retraso sistemático.** Entrar N días más tarde bate a entrar ahora, por motivos ajenos a cualquier señal.

**(b) Dispersión de entradas.** Repartir las compras de la canasta en días distintos reduce la varianza del retorno de la canasta, lo que sube el Sharpe sin subir el retorno — diversificación temporal, no habilidad.

Implican lecturas muy distintas de cada número de la Puerta B, así que se midieron por separado con disparadores construidos a propósito, sobre el mismo panel de 500 tickers y el mismo protocolo.

## Medición

| Disparador construido | Δ Sharpe | Error est. | ¿Pasa? | Dispersión de entradas |
|---|---|---|---|---|
| Nunca dispara → todos entran el día 10 | **−0.0066** | 0.0598 | no | ninguna |
| Dispara siempre → todos entran el día 1 | **0.0000** | 0.0000 | no | ninguna |
| Aleatorio, 20% por día y acción | **+0.0379** | 0.0278 | **sí** | alta |
| Aleatorio, 50% por día y acción | **+0.0069** | 0.0134 | no | baja |

## Conclusión

**La explicación es (b), dispersión.** El caso que retrasa la entrada diez días sin dispersarla no produce ninguna mejora — de hecho es ligeramente negativo. El caso que dispersa las entradas sí la produce. Y el caso al 50% confirma el mecanismo por la dirección contraria: dispara antes, concentra más las entradas, y el efecto casi desaparece.

El caso "dispara siempre" devolviendo exactamente 0.0000 confirma además que la enmienda E2 del criterio quedó bien implementada: esperar a una señal que dice "ahora" es idéntico a no esperar.

## Qué implica para leer el veredicto

**El cero no es la referencia correcta de la Puerta B. Lo es el control aleatorio.**

Cualquier señal que reparta sus entradas en el tiempo hereda una prima de ~0.04 de Sharpe que no tiene nada que ver con su capacidad predictiva. Comparadas contra esa referencia en vez de contra cero:

| Señal | Δ Sharpe | Δ contra el control (0.042) |
|---|---|---|
| `rev_1m` | 0.043 | +0.001 |
| `mom_12_1` | 0.031 | −0.011 |
| `macd_cross` | 0.030 | −0.012 |
| `bollinger_pos` | 0.020 | −0.022 |
| `breakout_52w` | 0.016 | −0.026 |
| `rsi_14` | 0.011 | −0.031 |
| `dist_sma200` | −0.001 | −0.043 |

**Ninguna señal técnica supera al ruido.** La mejor, `rev_1m`, le saca 0.001 de Sharpe con errores estándar en torno a 0.045 — cuarenta y cinco veces la diferencia. Seis de las siete quedan por debajo del control.

Esto **refuerza** el veredicto negativo en vez de debilitarlo: no sólo ninguna señal pasó las dos puertas, sino que ninguna mejoró el timing de entrada por encima de lo que consigue elegir el día al azar.

## Fallo de diseño que esto revela

La Puerta B se especificó contra un nulo equivocado. El criterio (§3.5) pide que la mejora «supere su propio error estándar», es decir, que se distinga de cero. Debió pedir que se distinguiera **del control aleatorio**, porque el cero no es lo que consigue no tener señal.

Además, la alarma del control sólo cubre la Puerta A: `report.py` marca `control_alarm` cuando el ruido pasa la puerta estadística, pero no cuando pasa la de timing. Por eso el estudio terminó con código de salida 0 pese a que el control pasó B.

**Ninguna de estas dos cosas se corrige ahora.** Cambiar el criterio después de ver los resultados es exactamente lo que el pre-registro existe para impedir, y además no haría falta: bajo el criterio tal y como se congeló, ninguna señal real pasó la Puerta B, así que el veredicto no cambia. Quedan anotadas para una eventual fase 2, que tendría que congelar su propio criterio antes de correr nada.
