# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 1673
- Reservas registradas: 99
- Reservas no confirmadas: 5
- Disponibilidades completas: 1186
- Disponibilidades parciales: 212
- Senales de defensa: 10

## Origen de deteccion
- normal: 1670
- slot_lost_reobservation: 3

## Ultimos eventos utiles
- 2026-08-17 11:11:12 | sin orden | available | normal | 07/09/2026 08:00 | sin outcome
- 2026-08-17 10:58:02 | order-*** | registered | normal | 01/09/2026 12:00 | confirmed
- 2026-08-17 10:57:58 | order-*** | registered | normal | 01/09/2026 12:00 | confirmed
- 2026-08-17 10:00:49 | order-*** | available | normal | 11/09/2026 10:00 | sin outcome
- 2026-08-17 10:00:43 | order-*** | available | normal | 11/09/2026 10:00 | sin outcome
- 2026-08-17 10:00:36 | order-*** | available | normal | 11/09/2026 10:00 | sin outcome
- 2026-08-17 10:00:31 | order-*** | available | normal | 11/09/2026 10:00 | sin outcome
- 2026-08-17 09:56:31 | order-*** | available | normal | 27/08/2026 10:00 | sin outcome
- 2026-08-17 09:56:25 | order-*** | available | normal | 27/08/2026 10:00 | sin outcome
- 2026-08-17 09:56:19 | order-*** | available | normal | 27/08/2026 10:00 | sin outcome

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
