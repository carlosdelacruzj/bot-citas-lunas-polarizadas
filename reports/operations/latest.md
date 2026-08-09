# Reporte semanal de operacion

- Rango actual: `2026-08-01` a `2026-08-08` (America/Lima, inclusivo).
- Rango comparable anterior: `2026-07-24` a `2026-07-31`.
- Runs medidos: 5299 actuales; 4234 anteriores.
- Intentos medidos: 78 actuales; 21 anteriores.

`registered` significa reserva confirmada por esta ejecucion. `Programado/completed` se informa aparte y nunca se suma a `registered`.

## Resultados exactos

| Resultado | Actual | Anterior |
| --- | ---: | ---: |
| registered | 20 | 5 |
| Programado/completed | 1 | 0 |
| completed sin Programado | 0 | 0 |
| reservation_unconfirmed | 0 | 0 |
| slot_lost | 57 | 15 |
| bloqueado por regla | 121 | 4 |
| senales de defensa | 2 | 0 |

## Tiempos

| Tramo | n | p50 | p90 |
| --- | ---: | ---: | ---: |
| Deteccion a fin | 198 | 3.000s | 15.900s |
| CAPTCHA | 77 | 1.641s | 7.256s |
| Seleccion | 198 | 1.968s | 2.031s |
| Cambio de usuario | 23 | 2.000s | 104.000s |

## Variabilidad CAPTCHA

- Mas de 3s: 34.
- Mas de 5s: 34.
- Mas de 10s: 0.
- Mas de 20s: 0.

## Alertas

- Sin alertas para este rango.

## Acumulado historico

El acumulado historico no se mezcla en esta tabla semanal. Consultar PostgreSQL o generar otro rango explicito cuando se necesite.
