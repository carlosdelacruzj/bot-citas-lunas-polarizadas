# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 973
- Reservas registradas: 97
- Reservas no confirmadas: 5
- Disponibilidades completas: 493
- Disponibilidades parciales: 211
- Senales de defensa: 10

## Origen de deteccion
- normal: 970
- slot_lost_reobservation: 3

## Ultimos eventos utiles
- 2026-08-13 15:17:11 | sin orden | available | normal | 04/09/2026 09:00 | sin outcome
- 2026-08-13 14:43:58 | sin orden | error | normal | sin cita | sin outcome
- 2026-08-13 13:41:28 | sin orden | available | normal | 04/09/2026 12:00 | sin outcome
- 2026-08-13 13:41:19 | sin orden | available | normal | 04/09/2026 12:00 | sin outcome
- 2026-08-13 13:41:03 | sin orden | available | normal | 04/09/2026 11:00 | sin outcome
- 2026-08-13 13:40:54 | sin orden | available | normal | 04/09/2026 09:00 | sin outcome
- 2026-08-13 13:40:38 | sin orden | available | normal | 04/09/2026 09:00 | sin outcome
- 2026-08-13 13:40:28 | sin orden | available | normal | 04/09/2026 10:00 | sin outcome
- 2026-08-13 13:39:39 | order-*** | registered | normal | 04/09/2026 09:00 | confirmed
- 2026-08-13 11:43:36 | sin orden | available | normal | 04/09/2026 08:00 | sin outcome

## Senales de defensa
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
- 2026-07-18 08:00:14 |  | network | Page.goto: net::ERR_NETWORK_CHANGED at https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx
Call log:
  - navigating to "https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx", waiting until "domcontentloaded"
- 2026-07-01 09:43:19 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-06-30 08:27:37 | order-*** | network | Page.goto: Timeout 60000ms exceeded.
Call log:
  - navigating to "https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx", waiting until "domcontentloaded"

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
