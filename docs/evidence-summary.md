# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 55
- Reservas registradas: 4
- Reservas no confirmadas: 5
- Disponibilidades completas: 5
- Disponibilidades parciales: 27
- Senales de defensa: 4

## Origen de deteccion
- fetch_probe: 11
- normal: 44

## Ultimos eventos utiles
- 2026-07-07 12:55:31 | order-*** | partial | normal | 22/07/2026 10:00 | blocked_by_order_rule
- 2026-07-07 12:55:15 | order-*** | partial | normal | 22/07/2026 09:00 | blocked_by_order_rule
- 2026-07-07 12:55:04 | order-*** | registered | normal | 22/07/2026 08:00 | confirmed
- 2026-07-07 12:46:28 | order-*** | partial | normal | 14/07/2026 10:00 | blocked_by_order_rule
- 2026-07-07 12:30:34 | order-*** | unavailable | normal | 20/07/2026 09:00 | slot_lost
- 2026-07-07 08:29:05 | order-*** | registered | normal | 21/07/2026 10:00 | confirmed
- 2026-07-07 08:28:48 | order-*** | partial | normal | 21/07/2026 10:00 | blocked_by_order_rule
- 2026-07-07 08:28:40 | order-*** | unavailable | normal | 21/07/2026 08:00 | slot_lost
- 2026-07-06 23:49:42 | order-*** | partial | fetch_probe | 06/07/2026 Sin Cupos | sin outcome
- 2026-07-06 23:39:33 | order-*** | partial | fetch_probe | 06/07/2026 Sin Cupos | sin outcome

## Senales de defensa
- 2026-07-01 09:43:19 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-06-30 08:27:37 | order-*** | network | Page.goto: Timeout 60000ms exceeded.
Call log:
  - navigating to "https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx", waiting until "domcontentloaded"
- 2026-06-29 12:30:08 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-06-22 12:19:00 | order-*** | network | Page.goto: net::ERR_NETWORK_CHANGED at https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx
Call log:
  - navigating to "https://sistemas.policia.gob.pe/lunasoscurecidas/solicitud_menu.aspx", waiting until "domcontentloaded"

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization-review-guide.md`.
