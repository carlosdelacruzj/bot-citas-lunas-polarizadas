# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 872
- Reservas registradas: 91
- Reservas no confirmadas: 5
- Disponibilidades completas: 423
- Disponibilidades parciales: 190
- Senales de defensa: 8

## Origen de deteccion
- normal: 869
- slot_lost_reobservation: 3

## Ultimos eventos utiles
- 2026-08-10 15:05:11 | order-*** | partial | normal | 22/08/2026 10:00 | blocked_by_order_rule
- 2026-08-10 15:04:41 | order-*** | partial | normal | 22/08/2026 11:00 | blocked_by_order_rule
- 2026-08-10 15:03:48 | order-*** | partial | normal | 26/08/2026 09:00 | blocked_by_order_rule
- 2026-08-10 15:02:35 | order-*** | partial | normal | 26/08/2026 08:00 | blocked_by_order_rule
- 2026-08-10 13:28:23 | order-*** | partial | normal | 01/09/2026 12:00 | blocked_by_order_rule
- 2026-08-10 13:27:54 | order-*** | partial | normal | 01/09/2026 12:00 | blocked_by_order_rule
- 2026-08-10 13:27:22 | order-*** | partial | normal | 01/09/2026 11:00 | blocked_by_order_rule
- 2026-08-10 13:26:52 | order-*** | partial | normal | 01/09/2026 11:00 | blocked_by_order_rule
- 2026-08-10 13:26:41 | order-*** | partial | normal | 01/09/2026 11:00 | blocked_by_order_rule
- 2026-08-10 13:26:30 | order-*** | partial | normal | 01/09/2026 11:00 | blocked_by_order_rule

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
