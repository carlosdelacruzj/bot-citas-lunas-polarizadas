# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 902
- Reservas registradas: 92
- Reservas no confirmadas: 5
- Disponibilidades completas: 430
- Disponibilidades parciales: 211
- Senales de defensa: 8

## Origen de deteccion
- normal: 899
- slot_lost_reobservation: 3

## Ultimos eventos utiles
- 2026-08-11 15:05:57 | sin orden | available | normal | 26/08/2026 10:00 | sin outcome
- 2026-08-11 14:59:01 | sin orden | available | normal | 22/08/2026 11:00 | sin outcome
- 2026-08-11 14:45:05 | sin orden | available | normal | 26/08/2026 12:00 | sin outcome
- 2026-08-11 13:05:01 | sin orden | available | normal | 02/09/2026 08:00 | sin outcome
- 2026-08-11 13:04:51 | sin orden | available | normal | 02/09/2026 08:00 | sin outcome
- 2026-08-11 13:01:45 | sin orden | available | normal | 26/08/2026 10:00 | sin outcome
- 2026-08-11 12:32:33 | sin orden | available | normal | 17/08/2026 08:00 | sin outcome
- 2026-08-11 12:29:12 | order-*** | registered | normal | 21/08/2026 10:00 | confirmed
- 2026-08-11 12:08:01 | order-*** | partial | normal | 27/08/2026 12:00 | blocked_by_order_rule
- 2026-08-11 12:07:55 | order-*** | partial | normal | 27/08/2026 12:00 | blocked_by_order_rule

## Senales de defensa
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
