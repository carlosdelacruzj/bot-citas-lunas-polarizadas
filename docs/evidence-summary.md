# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 849
- Reservas registradas: 87
- Reservas no confirmadas: 5
- Disponibilidades completas: 423
- Disponibilidades parciales: 173
- Senales de defensa: 8

## Origen de deteccion
- normal: 849

## Ultimos eventos utiles
- 2026-08-08 11:08:13 | order-*** | unavailable | normal | 22/08/2026 10:00 | slot_lost
- 2026-08-08 11:07:24 | order-*** | unavailable | normal | 13/08/2026 09:00 | slot_lost
- 2026-08-08 11:05:13 | order-*** | unavailable | normal | 29/08/2026 09:00 | slot_lost
- 2026-08-08 10:39:00 | order-*** | unavailable | normal | 31/08/2026 12:00 | slot_lost
- 2026-08-08 10:36:30 | order-*** | unavailable | normal | 31/08/2026 11:00 | slot_lost
- 2026-08-08 10:35:28 | order-*** | unavailable | normal | 31/08/2026 08:00 | slot_lost
- 2026-08-08 10:19:00 | order-*** | unavailable | normal | 10/08/2026 12:00 | slot_lost
- 2026-08-08 10:06:43 | order-*** | unavailable | normal | 31/08/2026 09:00 | slot_lost
- 2026-08-08 10:05:21 | order-*** | partial | normal | 31/08/2026 12:00 | blocked_by_order_rule
- 2026-08-08 10:03:18 | order-*** | partial | normal | 31/08/2026 11:00 | blocked_by_order_rule

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
