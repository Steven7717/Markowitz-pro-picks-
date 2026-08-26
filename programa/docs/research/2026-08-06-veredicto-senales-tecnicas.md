# Veredicto — Estudio de señales técnicas

**Cobertura del universo:** Tickers solicitados: 503 | incluidos: 500 | excluidos por historia corta: 3 | fallos de descarga: 0

**Línea base pasiva** (equal-weight del universo, comprar y mantener): Sharpe 1.03

## Resultados

| Señal | Puerta A | Puerta B | Δ Sharpe | Error estándar | Ventaja |
|---|---|---|---|---|---|
| `mom_12_1` | no | no | 0.031 | 0.047 | no |
| `rev_1m` | no | no | 0.043 | 0.045 | no |
| `rsi_14` | no | no | 0.011 | 0.056 | no |
| `macd_cross` | no | no | 0.030 | 0.052 | no |
| `dist_sma200` | no | no | -0.001 | 0.055 | no |
| `breakout_52w` | no | no | 0.016 | 0.053 | no |
| `bollinger_pos` | no | no | 0.020 | 0.049 | no |
| `random_control` | no | PASA | 0.042 | 0.028 | no |

## Detalle por horizonte

| Señal | Horizonte | IC medio | t-stat | Sobrevive BH | Spread bruto | Spread neto | Rotación | Sub-periodos |
|---|---|---|---|---|---|---|---|---|
| `mom_12_1` | 1d | 0.0152 | 4.26 | sí | 0.0466 | 0.0206 | 0.10 | 0/4 |
| `mom_12_1` | 5d | 0.0159 | 2.56 | sí | 0.0467 | 0.0349 | 0.23 | 0/4 |
| `mom_12_1` | 21d | 0.0125 | 1.14 | no | 0.0307 | 0.0248 | 0.49 | 2/4 |
| `mom_12_1` | 63d | 0.0087 | 0.51 | no | 0.0080 | 0.0046 | 0.83 | 1/4 |
| `rev_1m` | 1d | 0.0045 | 1.59 | no | 0.0540 | -0.0294 | 0.33 | 0/4 |
| `rev_1m` | 5d | 0.0094 | 2.04 | no | 0.0329 | -0.0054 | 0.76 | 0/4 |
| `rev_1m` | 21d | 0.0098 | 1.25 | no | 0.0402 | 0.0211 | 1.59 | 1/4 |
| `rev_1m` | 63d | 0.0110 | 1.15 | no | 0.0331 | 0.0270 | 1.54 | 0/4 |
| `rsi_14` | 1d | 0.0023 | 0.81 | no | 0.0660 | -0.0310 | 0.39 | 0/4 |
| `rsi_14` | 5d | 0.0090 | 1.97 | no | 0.0331 | -0.0098 | 0.85 | 0/4 |
| `rsi_14` | 21d | 0.0107 | 1.41 | no | 0.0329 | 0.0158 | 1.42 | 0/4 |
| `rsi_14` | 63d | 0.0156 | 1.55 | no | 0.0428 | 0.0364 | 1.60 | 0/4 |
| `macd_cross` | 1d | -0.0075 | -3.29 | sí | -0.0690 | -0.1347 | 0.26 | 0/4 |
| `macd_cross` | 5d | -0.0112 | -2.92 | sí | -0.0526 | -0.1006 | 0.95 | 0/4 |
| `macd_cross` | 21d | -0.0089 | -1.60 | no | -0.0288 | -0.0483 | 1.63 | 0/4 |
| `macd_cross` | 63d | -0.0066 | -1.21 | no | -0.0453 | -0.0511 | 1.46 | 0/4 |
| `dist_sma200` | 1d | 0.0067 | 1.92 | no | -0.0224 | -0.0543 | 0.13 | 0/4 |
| `dist_sma200` | 5d | 0.0018 | 0.30 | no | -0.0014 | -0.0162 | 0.29 | 0/4 |
| `dist_sma200` | 21d | -0.0026 | -0.24 | no | 0.0032 | -0.0043 | 0.62 | 0/4 |
| `dist_sma200` | 63d | -0.0046 | -0.32 | no | -0.0088 | -0.0132 | 1.09 | 0/4 |
| `breakout_52w` | 1d | 0.0048 | 1.33 | no | -0.0919 | -0.1487 | 0.23 | 0/4 |
| `breakout_52w` | 5d | -0.0038 | -0.59 | no | -0.0773 | -0.1009 | 0.47 | 0/4 |
| `breakout_52w` | 21d | -0.0112 | -0.94 | no | -0.0651 | -0.0747 | 0.80 | 0/4 |
| `breakout_52w` | 63d | -0.0203 | -1.16 | no | -0.0707 | -0.0752 | 1.13 | 0/4 |
| `bollinger_pos` | 1d | 0.0049 | 1.90 | no | 0.0744 | -0.0674 | 0.56 | 0/4 |
| `bollinger_pos` | 5d | 0.0124 | 3.02 | sí | 0.0531 | -0.0076 | 1.20 | 0/4 |
| `bollinger_pos` | 21d | 0.0113 | 1.79 | no | 0.0361 | 0.0168 | 1.60 | 0/4 |
| `bollinger_pos` | 63d | 0.0141 | 1.95 | no | 0.0433 | 0.0369 | 1.60 | 0/4 |
| `random_control` | 1d | -0.0001 | -0.13 | no | -0.0032 | -0.4065 | 1.60 | 0/4 |
| `random_control` | 5d | -0.0004 | -0.55 | no | 0.0045 | -0.0763 | 1.60 | 0/4 |
| `random_control` | 21d | 0.0009 | 1.15 | no | 0.0100 | -0.0092 | 1.60 | 0/4 |
| `random_control` | 63d | -0.0007 | -1.05 | no | 0.0065 | 0.0001 | 1.61 | 0/4 |

## Sensibilidad a los costes

Spread neto anualizado bajo los tres escenarios pre-registrados.

| Señal | Horizonte | Optimista (5 bps) | Base (10 bps) | Conservador (25 bps) |
|---|---|---|---|---|
| `mom_12_1` | 1d | 0.0336 | 0.0206 | -0.0184 |
| `mom_12_1` | 5d | 0.0408 | 0.0349 | 0.0173 |
| `mom_12_1` | 21d | 0.0277 | 0.0248 | 0.0159 |
| `mom_12_1` | 63d | 0.0063 | 0.0046 | -0.0004 |
| `rev_1m` | 1d | 0.0123 | -0.0294 | -0.1544 |
| `rev_1m` | 5d | 0.0137 | -0.0054 | -0.0629 |
| `rev_1m` | 21d | 0.0306 | 0.0211 | -0.0076 |
| `rev_1m` | 63d | 0.0301 | 0.0270 | 0.0177 |
| `rsi_14` | 1d | 0.0175 | -0.0310 | -0.1766 |
| `rsi_14` | 5d | 0.0117 | -0.0098 | -0.0741 |
| `rsi_14` | 21d | 0.0243 | 0.0158 | -0.0097 |
| `rsi_14` | 63d | 0.0396 | 0.0364 | 0.0268 |
| `macd_cross` | 1d | -0.1019 | -0.1347 | -0.2333 |
| `macd_cross` | 5d | -0.0766 | -0.1006 | -0.1727 |
| `macd_cross` | 21d | -0.0386 | -0.0483 | -0.0777 |
| `macd_cross` | 63d | -0.0482 | -0.0511 | -0.0599 |
| `dist_sma200` | 1d | -0.0384 | -0.0543 | -0.1021 |
| `dist_sma200` | 5d | -0.0088 | -0.0162 | -0.0383 |
| `dist_sma200` | 21d | -0.0006 | -0.0043 | -0.0155 |
| `dist_sma200` | 63d | -0.0110 | -0.0132 | -0.0197 |
| `breakout_52w` | 1d | -0.1203 | -0.1487 | -0.2338 |
| `breakout_52w` | 5d | -0.0891 | -0.1009 | -0.1364 |
| `breakout_52w` | 21d | -0.0699 | -0.0747 | -0.0892 |
| `breakout_52w` | 63d | -0.0729 | -0.0752 | -0.0820 |
| `bollinger_pos` | 1d | 0.0035 | -0.0674 | -0.2802 |
| `bollinger_pos` | 5d | 0.0228 | -0.0076 | -0.0985 |
| `bollinger_pos` | 21d | 0.0265 | 0.0168 | -0.0120 |
| `bollinger_pos` | 63d | 0.0401 | 0.0369 | 0.0273 |
| `random_control` | 1d | -0.2048 | -0.4065 | -1.0114 |
| `random_control` | 5d | -0.0359 | -0.0763 | -0.1976 |
| `random_control` | 21d | 0.0004 | -0.0092 | -0.0380 |
| `random_control` | 63d | 0.0033 | 0.0001 | -0.0096 |

## Limitaciones

- **Sesgo de supervivencia.** El universo son los miembros actuales del índice;
  las empresas expulsadas o quebradas no aparecen. El sesgo *infla* los resultados,
  así que un veredicto negativo es firme y uno positivo exige la fase 2 con
  universo point-in-time antes de creerse.
- **Costes.** El caso base son 10 bps por operación ida y vuelta. Las señales de
  rotación alta son las más sensibles a este supuesto.
- **Periodo.** 2010-01-01 a 2026-06-30. No cubre la crisis de 2008.
- **Sin ajuste de parámetros.** Los periodos de los indicadores son los
  convencionales. Optimizarlos requeriría validación fuera de muestra propia.
