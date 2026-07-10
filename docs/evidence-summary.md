# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 78
- Reservas registradas: 10
- Reservas no confirmadas: 5
- Disponibilidades completas: 5
- Disponibilidades parciales: 30
- Senales de defensa: 4

## Origen de deteccion
- fetch_probe: 12
- normal: 66

## Ultimos eventos utiles
- 2026-07-10 14:44:49 | order-*** | unavailable | normal | 15/07/2026 12:00 | slot_lost
- 2026-07-10 14:38:10 | order-*** | registered | normal | 27/07/2026 09:00 | confirmed
- 2026-07-10 14:37:16 | order-*** | unavailable | normal | 30/07/2026 12:00 | slot_lost
- 2026-07-10 14:02:29 | order-*** | completed | normal | 10/07/2026 09:00 | sin outcome
- 2026-07-10 14:01:47 | order-*** | unavailable | normal | 27/07/2026 12:00 | slot_lost
- 2026-07-10 14:01:34 | order-*** | registered | normal | 27/07/2026 12:00 | confirmed
- 2026-07-09 15:27:14 | order-*** | unavailable | normal | 17/07/2026 11:00 | slot_lost
- 2026-07-09 15:26:37 | order-*** | unavailable | normal | 30/07/2026 08:00 | slot_lost
- 2026-07-09 15:21:15 | order-*** | partial | fetch_probe | 15/07/2026 Sin Cupos | sin outcome
- 2026-07-09 15:19:32 | order-*** | completed | normal | 30/07/2026 11:00 | sin outcome

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
