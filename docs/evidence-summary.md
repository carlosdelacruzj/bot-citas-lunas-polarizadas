# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-08-30 16:00:24 America/Lima`.
- Ventana solicitada: mes activo 2026-08 (America/Lima).
- Rango real de eventos indexados: `2026-08-01 08:09:51` a `2026-08-29 12:00:24` (America/Lima).
- Cobertura temporal verificable: 2053/2053 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 2053
- Reservas registradas: 133
- Reservas no confirmadas: 0
- Disponibilidades completas: 1293
- Disponibilidades parciales: 510
- Senales de defensa: 9

## Origen de deteccion
- normal: 2045
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-08-29 12:00:24 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 12:00:19 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 12:00:14 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 12:00:10 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 12:00:05 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 11:59:59 | order-*** | partial | normal | 23/09/2026 11:00 | blocked_by_order_rule
- 2026-08-29 11:59:53 | order-*** | partial | normal | 23/09/2026 10:00 | blocked_by_order_rule
- 2026-08-29 11:59:49 | order-*** | partial | normal | 23/09/2026 10:00 | blocked_by_order_rule
- 2026-08-29 11:59:44 | order-*** | partial | normal | 23/09/2026 10:00 | blocked_by_order_rule
- 2026-08-29 11:59:39 | order-*** | partial | normal | 23/09/2026 10:00 | blocked_by_order_rule

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
