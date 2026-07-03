# Version con mas cupos detectados - 03/07/2026

Este checkpoint documenta la version funcional que, hasta ahora, deja mas evidencia
consolidada de cupos reales detectados por el bot en `LIMA-LA VICTORIA`. No debe leerse
como una version con todas las reservas concretadas: varias detecciones llegaron hasta
envio de reserva o CAPTCHA, pero quedaron como `reservation_unconfirmed` o fueron
rechazadas por CAPTCHA.

## Version registrada

- Branch: `codex/observer-multiclient-flow`.
- Commit base antes de guardar este checkpoint: `1f66865` (`Classify portal captcha rejection`).
- Estado de trabajo al registrar este checkpoint: cambios locales sin commit en codigo,
  pruebas existentes y documentacion de evidencia.
- Archivo principal de evidencia acumulada: `docs/reservation-optimization-log.md`.
- Checkpoints previos relacionados:
  - `docs/version-que-detecto-cupos-2026-06-25.md`.
  - `docs/version-primera-reserva-automatica-2026-06-30.md`.

## Resumen de evidencia

| Fecha operativa | Orden | Cita observada | Origen | Resultado |
| --- | --- | --- | --- | --- |
| 25/06/2026 09:43:59 | `order-70569448` | 13/07/2026 10:00 | normal | Cupo detectado y alerta enviada. |
| 25/06/2026 09:44:07 | `order-09329652` | 13/07/2026 11:00 | normal | Cupo detectado y alerta enviada. |
| 25/06/2026 09:44:16 | `order-42334486` | 13/07/2026 11:00 | normal | Cupo detectado y alerta enviada. |
| 25/06/2026 09:44:24 | `order-70569448` | 13/07/2026 12:00 | normal | Cupo detectado y alerta enviada. |
| 25/06/2026 09:44:32 | `order-09329652` | 13/07/2026 12:00 | normal | Cupo detectado y alerta enviada. |
| 30/06/2026 08:39 | `order-42334486` | 15/07/2026 11:00 | normal | Reserva enviada; luego confirmada como `Programado` en pasada posterior. |
| 01/07/2026 12:03:52 | `order-70569448` | 06/07/2026 08:00 | reload_probe | CAPTCHA rechazado; no concreto `Programado`. |
| 02/07/2026 11:31:32 | `order-70569448` | 14/07/2026 11:00 | normal | Reserva enviada; quedo `reservation_unconfirmed`. |
| 02/07/2026 12:47:45 | `order-70569448` | 17/07/2026 09:00 | normal | CAPTCHA rechazado; no concreto `Programado`. |

## Lectura practica

Esta version es la mejor referencia para estudiar deteccion de cupos porque combina:

- Detecciones reales por flujo normal.
- Deteccion por `reload_probe`.
- Captura de screenshot antes y despues del envio.
- Imagen exacta enviada a 2captcha.
- Resultado del intento de CAPTCHA por intento.
- Registro de `reservation_unconfirmed` separado de `Programado` real.

El mejor resultado confirmado sigue siendo el del 30/06/2026: el bot envio la reserva
para `order-42334486` y una pasada posterior encontro la etapa `Programado`. Las
detecciones del 01/07/2026 y 02/07/2026 sirven para optimizar velocidad, CAPTCHA y
revalidacion, pero no prueban una reserva completada.

## Cambios funcionales que conviene conservar

- Preservar evidencia exacta del CAPTCHA enviado a 2captcha.
- Reintentar solo cuando el portal rechaza explicitamente el CAPTCHA y el cupo todavia
  puede validarse.
- Registrar diagnosticos sanitizados en `details_json` y en el log de optimizacion.
- Limpiar estados `pending_submission` cuando una revalidacion de solo lectura demuestra
  que la orden no esta realmente `Programado`.
- Mantener la seleccion y validacion estricta de sede, fecha y hora esperadas antes de
  pulsar `Reservar`.

## Riesgos pendientes

- `reservation_unconfirmed` no equivale a reserva concretada.
- CAPTCHA sigue siendo el tramo mas lento, alrededor de 33 a 34 segundos en los eventos
  recientes documentados.
- Una confirmacion fiable todavia depende de encontrar `Programado` con fecha y hora
  esperadas en una lectura posterior.
- La comparacion exacta de rendimiento debe hacerse con nuevos cupos reales, no solo con
  pruebas locales.

## No versionar

No guardar en Git:

- `.env`
- tokens de Telegram
- claves de 2captcha
- contrasenas de clientes
- dumps o backups reales de PostgreSQL
- logs completos con datos sensibles
- screenshots o videos reales de clientes
