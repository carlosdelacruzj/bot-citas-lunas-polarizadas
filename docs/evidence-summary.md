# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 2663
- Reservas registradas: 193
- Reservas no confirmadas: 5
- Disponibilidades completas: 1716
- Disponibilidades parciales: 535
- Senales de defensa: 15

## Origen de deteccion
- normal: 2655
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-08-28 14:28:17 | order-*** | registered | normal | 25/09/2026 08:00 | confirmed
- 2026-08-28 13:44:09 | order-*** | registered | normal | 23/09/2026 09:00 | confirmed
- 2026-08-28 13:44:07 | order-*** | registered | normal | 23/09/2026 09:00 | confirmed
- 2026-08-28 11:45:25 | sin orden | available | normal | 14/09/2026 12:00 | sin outcome
- 2026-08-28 11:45:17 | sin orden | available | normal | 14/09/2026 12:00 | sin outcome
- 2026-08-28 10:46:52 | sin orden | available | normal | 21/09/2026 08:00 | sin outcome
- 2026-08-28 10:46:43 | sin orden | available | normal | 21/09/2026 08:00 | sin outcome
- 2026-08-28 10:46:35 | sin orden | available | normal | 21/09/2026 08:00 | sin outcome
- 2026-08-28 10:46:26 | sin orden | available | normal | 21/09/2026 08:00 | sin outcome
- 2026-08-28 10:46:17 | sin orden | available | normal | 21/09/2026 08:00 | sin outcome

## Senales de defensa
- 2026-08-28 09:22:52 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-26 15:11:29 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-26 08:54:58 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-08-18 17:22:49 | order-***-1be4d862e11fa4c6 | network | Locator.wait_for: Timeout 30000ms exceeded.
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
- 2026-07-24 11:30:36 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
