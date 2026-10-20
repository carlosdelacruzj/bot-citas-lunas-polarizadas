# Reporte semanal de operacion

- Rango actual: `2026-07-13` a `2026-07-18` (America/Lima, inclusivo).
- Rango comparable anterior: `2026-07-07` a `2026-07-12`.
- Runs medidos: 5356 actuales; 3918 anteriores.
- Intentos medidos: 61 actuales; 36 anteriores.

`registered` significa reserva confirmada por esta ejecucion. `Programado/completed` se informa aparte y nunca se suma a `registered`.

## Resultados exactos

| Resultado | Actual | Anterior |
| --- | ---: | ---: |
| registered | 28 | 15 |
| Programado/completed | 4 | 6 |
| completed sin Programado | 0 | 0 |
| reservation_unconfirmed | 0 | 0 |
| slot_lost | 29 | 15 |
| bloqueado por regla | 16 | 10 |
| senales de defensa | 1 | 0 |

## Tiempos

| Tramo | n | p50 | p90 |
| --- | ---: | ---: | ---: |
| Deteccion a fin | 75 | 7.485s | 18.559s |
| CAPTCHA | 57 | 1.406s | 12.046s |
| Seleccion | 75 | 1.703s | 1.797s |
| Cambio de usuario | 29 | 2.000s | 62.800s |

## Variabilidad CAPTCHA

- Mas de 3s: 19.
- Mas de 5s: 19.
- Mas de 10s: 19.
- Mas de 20s: 2.

## Alertas

- CAPTCHA: 19 respuestas superaron 10 segundos.

## Acumulado historico

El acumulado historico no se mezcla en esta tabla semanal. Consultar PostgreSQL o generar otro rango explicito cuando se necesite.
