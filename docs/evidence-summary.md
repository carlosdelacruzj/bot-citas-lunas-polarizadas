# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 590
- Reservas registradas: 51
- Reservas no confirmadas: 5
- Disponibilidades completas: 418
- Disponibilidades parciales: 41
- Senales de defensa: 5

## Origen de deteccion
- normal: 590

## Ultimos eventos utiles
- 2026-07-21 15:47:00 | order-*** | completed | normal | 24/07/2026 11:00 | sin outcome
- 2026-07-21 15:46:42 | order-*** | registered | normal | 18/08/2026 12:00 | confirmed
- 2026-07-21 15:46:24 | order-*** | registered | normal | 18/08/2026 12:00 | confirmed
- 2026-07-21 15:46:08 | order-*** | registered | normal | 18/08/2026 12:00 | confirmed
- 2026-07-21 14:15:41 | order-*** | unavailable | normal | 18/08/2026 09:00 | slot_lost
- 2026-07-21 14:14:45 | order-*** | registered | normal | 18/08/2026 10:00 | confirmed
- 2026-07-21 13:32:40 | order-*** | unavailable | normal | 30/07/2026 08:00 | slot_lost
- 2026-07-21 11:17:58 | order-*** | unavailable | normal | 15/08/2026 11:00 | slot_lost
- 2026-07-21 09:23:54 | order-*** | unavailable | normal | 18/08/2026 09:00 | slot_lost
- 2026-07-20 17:22:36 | sin orden | error | normal | sin cita | sin outcome

## Senales de defensa
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
