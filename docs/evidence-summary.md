# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-09-07 15:55:08 America/Lima`.
- Ventana solicitada: mes activo 2026-09 (America/Lima).
- Rango real de eventos indexados: `2026-09-01 09:04:52` a `2026-09-07 13:54:20` (America/Lima).
- Cobertura temporal verificable: 366/366 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 366
- Reservas registradas: 56
- Reservas no confirmadas: 0
- Disponibilidades completas: 231
- Disponibilidades parciales: 36
- Senales de defensa: 3

## Origen de deteccion
- fetch_probe: 17
- normal: 337
- reload_probe: 4
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-09-07 13:54:20 | sin orden | available | normal | 07/10/2026 08:00 | sin outcome
- 2026-09-07 13:29:46 | sin orden | available | normal | 09/10/2026 09:00 | sin outcome
- 2026-09-07 12:54:23 | sin orden | available | normal | 08/10/2026 10:00 | sin outcome
- 2026-09-07 12:51:27 | order-*** | registered | fetch_probe | 07/10/2026 10:00 | confirmed
- 2026-09-07 11:35:50 | order-*** | registered | fetch_probe | 06/10/2026 11:00 | confirmed
- 2026-09-07 11:35:35 | order-*** | partial | fetch_probe | 06/10/2026 11:00 | blocked_by_order_rule
- 2026-09-07 10:02:58 | sin orden | available | normal | 06/10/2026 10:00 | sin outcome
- 2026-09-07 10:01:57 | order-*** | registered | fetch_probe | 06/10/2026 10:00 | confirmed
- 2026-09-07 10:01:39 | order-*** | unavailable | fetch_probe | 03/10/2026 10:00 | slot_lost
- 2026-09-07 10:01:02 | order-*** | registered | fetch_probe | 03/10/2026 10:00 | confirmed

## Senales de defensa
- 2026-09-03 13:02:34 | order-*** | http_429 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-02 15:02:23 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-09-01 09:59:40 | order-*** | http_429 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
