# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 2600
- Reservas registradas: 171
- Reservas no confirmadas: 5
- Disponibilidades completas: 1699
- Disponibilidades parciales: 525
- Senales de defensa: 14

## Origen de deteccion
- normal: 2595
- slot_lost_reobservation: 5

## Ultimos eventos utiles
- 2026-08-26 15:11:29 | order-*** | error | normal | sin cita | sin outcome
- 2026-08-26 13:09:49 | sin orden | available | normal | 24/09/2026 09:00 | sin outcome
- 2026-08-26 13:09:40 | sin orden | available | normal | 24/09/2026 09:00 | sin outcome
- 2026-08-26 13:09:32 | sin orden | available | normal | 24/09/2026 09:00 | sin outcome
- 2026-08-26 13:09:22 | sin orden | available | normal | 24/09/2026 09:00 | sin outcome
- 2026-08-26 13:09:14 | sin orden | available | normal | 24/09/2026 09:00 | sin outcome
- 2026-08-26 13:09:05 | sin orden | available | normal | 24/09/2026 08:00 | sin outcome
- 2026-08-26 13:08:57 | sin orden | available | normal | 24/09/2026 08:00 | sin outcome
- 2026-08-26 13:08:49 | sin orden | available | normal | 24/09/2026 08:00 | sin outcome
- 2026-08-26 13:08:40 | sin orden | available | normal | 24/09/2026 08:00 | sin outcome

## Senales de defensa
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
- 2026-07-21 15:46:08 | order-*** | http_403 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
