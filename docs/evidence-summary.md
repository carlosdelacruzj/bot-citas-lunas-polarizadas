# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 67
- Reservas registradas: 8
- Reservas no confirmadas: 5
- Disponibilidades completas: 5
- Disponibilidades parciales: 29
- Senales de defensa: 4

## Origen de deteccion
- fetch_probe: 11
- normal: 56

## Ultimos eventos utiles
- 2026-07-09 14:02:17 | order-*** | registered | normal | 30/07/2026 10:00 | confirmed
- 2026-07-09 12:15:57 | order-*** | unavailable | normal | 24/07/2026 12:00 | slot_lost
- 2026-07-09 10:59:20 | order-*** | unavailable | normal | 24/07/2026 11:00 | slot_lost
- 2026-07-09 10:58:30 | order-*** | partial | normal | 24/07/2026 10:00 | blocked_by_order_rule
- 2026-07-09 10:26:58 | order-*** | partial | normal | 20/07/2026 12:00 | blocked_by_order_rule
- 2026-07-09 10:06:49 | order-*** | registered | normal | 30/07/2026 09:00 | confirmed
- 2026-07-09 08:28:21 | order-*** | registered | normal | 24/07/2026 12:00 | confirmed
- 2026-07-09 08:28:06 | order-*** | registered | normal | 24/07/2026 12:00 | confirmed
- 2026-07-09 07:36:51 | order-*** | completed | normal | 20/07/2026 10:00 | sin outcome
- 2026-07-08 14:17:15 | order-*** | completed | normal | 30/07/2026 10:00 | sin outcome

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
