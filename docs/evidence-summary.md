# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 646
- Reservas registradas: 67
- Reservas no confirmadas: 5
- Disponibilidades completas: 423
- Disponibilidades parciales: 52
- Senales de defensa: 6

## Origen de deteccion
- normal: 646

## Ultimos eventos utiles
- 2026-07-31 15:30:40 | order-*** | unavailable | normal | 08/08/2026 10:00 | slot_lost
- 2026-07-31 15:02:43 | order-*** | unavailable | normal | 07/08/2026 11:00 | slot_lost
- 2026-07-31 14:59:45 | order-*** | unavailable | normal | 03/08/2026 08:00 | slot_lost
- 2026-07-31 14:58:24 | order-*** | unavailable | normal | 03/08/2026 12:00 | slot_lost
- 2026-07-31 14:58:10 | order-*** | partial | normal | 03/08/2026 12:00 | blocked_by_order_rule
- 2026-07-31 13:20:51 | order-*** | error | normal | 24/08/2026 10:00 | captcha_invalid
- 2026-07-31 13:20:25 | order-*** | partial | normal | 24/08/2026 10:00 | blocked_by_order_rule
- 2026-07-31 11:47:58 | order-*** | partial | normal | 03/08/2026 11:00 | blocked_by_order_rule
- 2026-07-31 11:47:34 | order-*** | unavailable | normal | 03/08/2026 08:00 | slot_lost
- 2026-07-31 09:35:46 | order-*** | unavailable | normal | 07/08/2026 12:00 | slot_lost

## Senales de defensa
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
