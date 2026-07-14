# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 109
- Reservas registradas: 29
- Reservas no confirmadas: 5
- Disponibilidades completas: 8
- Disponibilidades parciales: 31
- Senales de defensa: 2

## Origen de deteccion
- normal: 109

## Ultimos eventos utiles
- 2026-07-14 13:09:38 | order-*** | partial | normal | 21/07/2026 10:00 | blocked_by_order_rule
- 2026-07-14 12:37:05 | order-*** | registered | normal | 05/08/2026 09:00 | confirmed
- 2026-07-14 12:35:48 | order-*** | registered | normal | 05/08/2026 08:00 | confirmed
- 2026-07-14 10:44:36 | order-*** | unavailable | normal | 04/08/2026 11:00 | slot_lost
- 2026-07-14 10:41:00 | order-*** | partial | normal | 22/07/2026 09:00 | blocked_by_order_rule
- 2026-07-14 10:01:47 | sin orden | available | normal | 31/07/2026 08:00 | sin outcome
- 2026-07-14 10:01:35 | sin orden | available | normal | 31/07/2026 08:00 | sin outcome
- 2026-07-14 09:57:33 | sin orden | available | normal | 20/07/2026 08:00 | sin outcome
- 2026-07-14 09:57:20 | sin orden | available | normal | 21/07/2026 09:00 | sin outcome
- 2026-07-14 09:53:36 | order-*** | partial | normal | 21/07/2026 12:00 | blocked_by_order_rule

## Senales de defensa
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
