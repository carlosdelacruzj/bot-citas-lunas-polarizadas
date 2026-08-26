# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 2503
- Reservas registradas: 168
- Reservas no confirmadas: 5
- Disponibilidades completas: 1673
- Disponibilidades parciales: 460
- Senales de defensa: 13

## Origen de deteccion
- normal: 2498
- slot_lost_reobservation: 5

## Ultimos eventos utiles
- 2026-08-26 09:12:16 | sin orden | available | normal | 23/09/2026 12:00 | sin outcome
- 2026-08-26 09:12:08 | sin orden | available | normal | 23/09/2026 12:00 | sin outcome
- 2026-08-26 09:11:59 | sin orden | available | normal | 23/09/2026 12:00 | sin outcome
- 2026-08-26 09:11:50 | sin orden | available | normal | 23/09/2026 12:00 | sin outcome
- 2026-08-26 09:10:08 | sin orden | available | normal | 23/09/2026 11:00 | sin outcome
- 2026-08-26 09:10:00 | sin orden | available | normal | 23/09/2026 11:00 | sin outcome
- 2026-08-26 09:09:50 | sin orden | available | normal | 23/09/2026 11:00 | sin outcome
- 2026-08-26 09:09:41 | sin orden | available | normal | 23/09/2026 11:00 | sin outcome
- 2026-08-26 09:02:44 | sin orden | available | normal | 07/09/2026 08:00 | sin outcome
- 2026-08-26 09:02:36 | sin orden | available | normal | 07/09/2026 08:00 | sin outcome

## Senales de defensa
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
- 2026-07-20 17:22:36 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
