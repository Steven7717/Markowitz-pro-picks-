# Qué método de VaR pasa más tiempo en verde en carteras reales

**Descarga:** 2026-11-17, Yahoo Finance vía `yfinance`, 5 años de cierres diarios
ajustados, sin caché (`retornos_diarios.__wrapped__`). Script:
`scripts/medir_var.py`. Cada cartera es a **pesos iguales y constantes**; las
sesiones son las comunes a todos sus tickers (1.254 retornos: 500 de estimación,
754 de backtest, 505 ventanas de 250 días). COIN y PLTR, los dos tickers
recientes, tienen las 1.255 sesiones completas, así que no hizo falta sustituir
ninguno. «VaR medio» es el VaR 99 % medio de todo el backtest, en fracción del
valor. Bajo cada título, la asimetría y la curtosis en exceso muestrales de las
últimas 500 sesiones de esa cartera.

La regla de elección es la de la aplicación: mayor fracción de ventanas de 250
días en verde; después, tasa de excepciones más cercana al 1 %; después, menor
VaR medio.

Sesiones por ticker: {'AAPL': 1255, 'MSFT': 1255, 'GOOGL': 1255, 'AMZN': 1255, 'NVDA': 1255}

## Tecnológicas (1254 sesiones) — gana Histórica filtrada (EWMA)

Últimas 500 sesiones: asimetría 0.87, curtosis en exceso 10.85

| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES | VaR medio |
|---|---|---|---|---|---|---|
| Simulación histórica | 50% | verde | 1.19% | 0.60 | 1.03 | 4.11% |
| Paramétrico normal | 46% | verde | 1.72% | 0.07 | 1.10 | 3.73% |
| t de Student | 51% | verde | 1.06% | 0.87 | 1.00 | 4.13% |
| EWMA (RiskMetrics) | 31% | amarilla | 2.79% | 0.00 | 1.12 | 3.30% |
| Histórica filtrada (EWMA) | 64% | verde | 1.46% | 0.24 | 1.03 | 3.84% |
| Cornish-Fisher | 60% | verde | 0.66% | 0.32 | 0.86 | 4.82% |

Sesiones por ticker: {'KO': 1255, 'PG': 1255, 'JNJ': 1255, 'XOM': 1255, 'WMT': 1255}

## Defensivas (1254 sesiones) — gana Paramétrico normal

Últimas 500 sesiones: asimetría 0.03, curtosis en exceso 2.83

| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES | VaR medio |
|---|---|---|---|---|---|---|
| Simulación histórica | 85% | amarilla | 1.33% | 0.39 | 0.99 | 1.70% |
| Paramétrico normal | 100% | verde | 1.06% | 0.87 | 1.09 | 1.72% |
| t de Student | 100% | verde | 0.66% | 0.32 | 1.02 | 1.89% |
| EWMA (RiskMetrics) | 100% | verde | 0.66% | 0.32 | 1.08 | 1.78% |
| Histórica filtrada (EWMA) | 100% | verde | 0.80% | 0.56 | 1.02 | 1.76% |
| Cornish-Fisher | 100% | verde | 0.53% | 0.15 | 0.98 | 2.35% |

Sesiones por ticker: {'SPY': 1255, 'TLT': 1255, 'GLD': 1255, 'VNQ': 1255}

## Mixta con bonos (1254 sesiones) — gana Cornish-Fisher

Últimas 500 sesiones: asimetría 0.21, curtosis en exceso 6.19

| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES | VaR medio |
|---|---|---|---|---|---|---|
| Simulación histórica | 98% | verde | 0.93% | 0.84 | 1.00 | 1.87% |
| Paramétrico normal | 20% | amarilla | 1.72% | 0.07 | 1.13 | 1.65% |
| t de Student | 98% | verde | 0.80% | 0.56 | 0.97 | 1.83% |
| EWMA (RiskMetrics) | 39% | verde | 1.99% | 0.02 | 1.14 | 1.57% |
| Histórica filtrada (EWMA) | 89% | verde | 1.19% | 0.60 | 0.99 | 1.83% |
| Cornish-Fisher | 100% | verde | 0.66% | 0.32 | 0.83 | 2.30% |

Sesiones por ticker: {'TSLA': 1255, 'AMD': 1255, 'COIN': 1255, 'PLTR': 1255}

## Volátiles (1254 sesiones) — gana Paramétrico normal

Últimas 500 sesiones: asimetría 0.31, curtosis en exceso 4.14

| Método | Tiempo en verde | Zona hoy | Tasa | Kupiec p | Cola/ES | VaR medio |
|---|---|---|---|---|---|---|
| Simulación histórica | 50% | verde | 1.59% | 0.13 | 1.03 | 6.73% |
| Paramétrico normal | 100% | verde | 1.06% | 0.87 | 1.04 | 7.11% |
| t de Student | 100% | verde | 0.66% | 0.32 | 0.95 | 7.70% |
| EWMA (RiskMetrics) | 83% | amarilla | 1.59% | 0.13 | 1.13 | 6.79% |
| Histórica filtrada (EWMA) | 69% | amarilla | 1.86% | 0.03 | 1.08 | 6.72% |
| Cornish-Fisher | 85% | verde | 0.93% | 0.84 | 0.88 | 7.91% |

## Qué ganó en cada cartera

| Cartera | Gana | Tiempo en verde | Tasa del ganador | Cómo se decide |
|---|---|---|---|---|
| Tecnológicas | Histórica filtrada (EWMA) | 64 % | 1,46 % | Primer criterio: Cornish-Fisher queda en 60 % |
| Defensivas | Paramétrico normal | 100 % | 1,06 % | Seis métodos menos la histórica empatan en 100 %; gana la tasa más cercana al 1 % |
| Mixta con bonos | Cornish-Fisher | 100 % | 0,66 % | Primer criterio: histórica y t quedan en 98 % |
| Volátiles | Paramétrico normal | 100 % | 1,06 % | Empata con la t de Student en 100 %; gana la tasa más cercana al 1 % |

Lo que sale sólo en parte es lo que la literatura haría esperar:

- La histórica filtrada gana en una cartera de cuatro, no en la mayoría.
- El **normal gana en dos** (Defensivas y Volátiles), las dos veces por
  desempate y no por estar más tiempo en verde que los demás. En la mixta con
  bonos, en cambio, es el peor (20 % en verde).
- EWMA a secas no gana nunca y es el que menos tiempo pasa en verde en la
  tecnológica (31 %), y el segundo peor en la mixta (39 %). La histórica simple y
  la t de Student tampoco ganan en ninguna. Ninguno de los tres queda segundo de
  forma sistemática, así que son candidatos a quitarse; eso se decide con el
  usuario, no en esta nota.

## Cornish-Fisher y la conservaduría

Cornish-Fisher tiene **la tasa de excepciones por debajo del 1 % en las cuatro
carteras** (0,66 %, 0,53 %, 0,66 %, 0,93 %), **el VaR medio más alto en las
cuatro** (4,82 %, 2,35 %, 2,30 %, 7,91 %) y un cociente cola/ES **por debajo de
1 en las cuatro** (0,86, 0,98, 0,83, 0,88): su ES previsto es mayor que la
pérdida realizada en los días de cola. En la mixta con bonos gana con un VaR
medio 23 % por encima del de la histórica (2,30 % frente a 1,87 %) y 26 % por
encima del de la t (1,83 %), por 100 % frente a 98 % de tiempo en verde.

**Sobre la cesta tecnológica en concreto:** en esta cartera a pesos iguales
Cornish-Fisher *no* gana (60 % frente al 64 % de la histórica filtrada), pero sí
es el que más capital inmoviliza (4,82 % frente a 3,84 %). La observación de que
Cornish-Fisher gana en la cesta tecnológica por conservador viene de la
revisión sobre la cartera tecnológica real del usuario (asimetría 0,98, curtosis
en exceso 14,8; 83,6 % en verde, tasa 0,80 %, VaR medio ≈ 10 % sobre el
histórico, con histórica y t en ≈ 50 % de verde). **Esta corrida no la
reproduce**: los pesos iguales de esta cesta dan asimetría 0,87, curtosis 10,85
y otro resultado. Aquella cartera no se ha vuelto a medir aquí.

**Tasa del ganador por debajo del 1 %:** en 1 de las 4 carteras (la mixta con
bonos, Cornish-Fisher, 0,66 %). En las otras tres el ganador la excede (1,46 %,
1,06 %, 1,06 %). Ninguno de los cuatro ganadores se rechaza con Kupiec al 5 %
(p = 0,24, 0,87, 0,32 y 0,87). Con 754 días de backtest, 0,66 % son 5
excepciones frente a las 7,5 esperadas, y tampoco se rechaza.

## Lo que esto dice del criterio de elección

Esto es descriptivo; el criterio lo eligió el usuario y no se toca aquí.

- La regla premia **estar en verde**, y estar en verde le cuesta poco al
  conservador: un método que sobrestima la cola tiene pocas excepciones por
  construcción. Cornish-Fisher es el más conservador de los seis en las cuatro
  carteras y gana en una, queda segundo o tercero en las demás por el tiempo en
  verde (60 %, 100 %, 85 %).
- El desempate por tasa cercana al 1 % sólo actúa cuando el primer criterio
  empata, y sólo empata de verdad cuando varios métodos están en 100 %
  (Defensivas y Volátiles). Cuando no empata, la tasa no entra: en la mixta con
  bonos gana Cornish-Fisher con 0,66 % porque 100 % supera a 98 %, aunque la
  histórica (0,93 %) y la t (0,80 %) están más cerca del 1 %.
- El coste de la conservaduría (el VaR medio) es el último criterio y no llegó a
  decidir en ninguna de las cuatro carteras.
- Con 754 días las diferencias de tasa entre 0,66 % y 1,2 % no se distinguen
  estadísticamente: Kupiec rechaza al 5 % sólo EWMA en Tecnológicas (p 0,00) y en
  la mixta (0,02), y la histórica filtrada en Volátiles (0,03).
- Si el usuario quisiera que la regla no premiara la conservaduría, las
  opciones evidentes son poner la tasa o el p de Kupiec antes de la fracción
  verde, o añadir un criterio que penalice también el exceso de capital. Es
  decisión suya.
