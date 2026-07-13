# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 84
- Reservas registradas: 17
- Reservas no confirmadas: 5
- Disponibilidades completas: 0
- Disponibilidades parciales: 35
- Senales de defensa: 3

## Origen de deteccion
- fetch_probe: 12
- normal: 72

## Ultimos eventos utiles
- 2026-07-11 12:14:02 | order-*** | partial | normal | 31/07/2026 09:00 | blocked_by_order_rule
- 2026-07-11 10:22:20 | order-*** | partial | normal | 31/07/2026 08:00 | blocked_by_order_rule
- 2026-07-11 09:52:20 | order-***-e42b7af400a8b1fa | completed | normal | 01/08/2026 10:00 | sin outcome
- 2026-07-11 09:51:59 | order-*** | unavailable | normal | 01/08/2026 10:00 | slot_lost
- 2026-07-11 09:51:43 | order-***-513a3ad12166355b | registered | normal | 01/08/2026 10:00 | confirmed
- 2026-07-11 09:18:29 | order-***-e42b7af400a8b1fa | partial | normal | 31/07/2026 10:00 | priority_deferred
- 2026-07-11 08:36:20 | order-*** | completed | normal | 27/07/2026 09:00 | sin outcome
- 2026-07-11 08:35:58 | order-*** | registered | normal | 25/07/2026 09:00 | confirmed
- 2026-07-11 08:35:42 | order-*** | registered | normal | 25/07/2026 09:00 | confirmed
- 2026-07-11 08:35:26 | order-*** | registered | normal | 25/07/2026 09:00 | confirmed

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


## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
