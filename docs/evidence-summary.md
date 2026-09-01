# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-08-31 15:36:03 America/Lima`.
- Ventana solicitada: mes activo 2026-08 (America/Lima).
- Rango real de eventos indexados: `2026-08-01 08:09:51` a `2026-08-31 15:36:02` (America/Lima).
- Cobertura temporal verificable: 2081/2081 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 2081
- Reservas registradas: 139
- Reservas no confirmadas: 0
- Disponibilidades completas: 1293
- Disponibilidades parciales: 517
- Senales de defensa: 9

## Origen de deteccion
- normal: 2073
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-08-31 15:36:02 | order-*** | unavailable | normal | 22/09/2026 12:00 | slot_lost
- 2026-08-31 15:35:59 | order-*** | unavailable | normal | 22/09/2026 12:00 | slot_lost
- 2026-08-31 15:35:49 | order-*** | registered | normal | 22/09/2026 12:00 | confirmed
- 2026-08-31 15:35:35 | order-*** | partial | normal | 22/09/2026 12:00 | blocked_by_order_rule
- 2026-08-31 15:24:35 | order-*** | unavailable | normal | 22/09/2026 11:00 | slot_lost
- 2026-08-31 15:24:32 | order-*** | unavailable | normal | 22/09/2026 11:00 | slot_lost
- 2026-08-31 15:24:23 | order-*** | registered | normal | 22/09/2026 11:00 | confirmed
- 2026-08-31 15:24:07 | order-*** | partial | normal | 22/09/2026 11:00 | blocked_by_order_rule
- 2026-08-31 15:21:50 | order-*** | unavailable | normal | 22/09/2026 12:00 | slot_lost
- 2026-08-31 15:21:43 | order-*** | registered | normal | 22/09/2026 12:00 | confirmed

## Senales de defensa
- 2026-08-28 09:22:52 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-26 15:11:29 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-26 08:54:58 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-08-18 17:22:49 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-17 12:22:53 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
- 2026-08-13 14:43:58 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
- 2026-08-12 16:22:56 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
- 2026-08-07 16:11:51 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-06 15:22:59 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
