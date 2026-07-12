# Resumen de evidencia - ultimos 14 dias

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 43
- Reservas registradas: 2
- Reservas no confirmadas: 5
- Disponibilidades completas: 5
- Disponibilidades parciales: 19
- Senales de defensa: 4

## Origen de deteccion
- fetch_probe: 9
- normal: 34

## Ultimos eventos utiles
- 2026-07-06 10:09:41 | order-*** | unavailable | normal | 11/07/2026 11:00 | slot_lost
- 2026-07-06 09:26:57 | order-*** | partial | normal | 21/07/2026 10:00 | blocked_by_order_rule
- 2026-07-06 09:26:44 | order-*** | partial | normal | 21/07/2026 10:00 | blocked_by_order_rule
- 2026-07-06 09:26:32 | order-*** | partial | normal | 21/07/2026 10:00 | blocked_by_order_rule
- 2026-07-06 09:25:59 | order-*** | partial | normal | 20/07/2026 12:00 | blocked_by_order_rule
- 2026-07-06 09:22:24 | order-*** | partial | normal | 20/07/2026 10:00 | blocked_by_order_rule
- 2026-07-06 09:21:52 | order-*** | partial | normal | 20/07/2026 09:00 | blocked_by_order_rule
- 2026-07-04 13:07:35 | order-*** | partial | normal | 20/07/2026 11:00 | blocked_by_order_rule
- 2026-07-04 13:06:45 | order-*** | partial | normal | 20/07/2026 11:00 | blocked_by_order_rule
- 2026-07-04 13:05:53 | order-*** | partial | normal | 06/07/2026 09:00 | blocked_by_order_rule

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
- Comparar cambios contra `docs/roadmap/04-optimization.md`.
