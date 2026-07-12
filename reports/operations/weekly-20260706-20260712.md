# Reporte semanal de operacion

- Rango actual: `2026-07-06` a `2026-07-12` (America/Lima, inclusivo).
- Rango comparable anterior: `2026-06-29` a `2026-07-05`.
- Runs medidos: 4339 actuales; 1704 anteriores.
- Intentos medidos: 56 actuales; 13 anteriores.

`registered` significa reserva confirmada por esta ejecucion. `Programado/completed` se informa aparte y nunca se suma a `registered`.

## Resultados exactos

| Resultado | Actual | Anterior |
| --- | ---: | ---: |
| registered | 15 | 2 |
| Programado/completed | 6 | 1 |
| completed sin Programado | 0 | 0 |
| reservation_unconfirmed | 0 | 5 |
| slot_lost | 16 | 1 |
| bloqueado por regla | 18 | 4 |
| senales de defensa | 0 | 3 |

## Tiempos

| Tramo | n | p50 | p90 |
| --- | ---: | ---: | ---: |
| Deteccion a fin | 50 | 6.977s | 11.283s |
| CAPTCHA | 31 | 1.359s | 3.047s |
| Seleccion | 50 | 1.719s | 1.891s |
| Cambio de usuario | 19 | 2.000s | 73.800s |

## Variabilidad CAPTCHA

- Mas de 3s: 4.
- Mas de 5s: 3.
- Mas de 10s: 3.
- Mas de 20s: 1.

## Alertas

- CAPTCHA: 3 respuestas superaron 10 segundos.
- slot_lost: aumento sostenido de 7.7% a 28.6% sobre intentos compatibles.

## Acumulado historico

El acumulado historico no se mezcla en esta tabla semanal. Consultar PostgreSQL o generar otro rango explicito cuando se necesite.
