# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 156
- Reservas registradas: 41
- Reservas no confirmadas: 5
- Disponibilidades completas: 19
- Disponibilidades parciales: 38
- Senales de defensa: 2

## Origen de deteccion
- normal: 156

## Ultimos eventos utiles
- 2026-07-17 10:44:12 | order-*** | partial | normal | 21/07/2026 12:00 | blocked_by_order_rule
- 2026-07-17 10:42:42 | order-*** | partial | normal | 21/07/2026 12:00 | blocked_by_order_rule
- 2026-07-17 09:29:44 | sin orden | available | normal | 21/07/2026 12:00 | sin outcome
- 2026-07-17 08:58:16 | sin orden | available | normal | 10/08/2026 08:00 | sin outcome
- 2026-07-17 08:58:03 | sin orden | available | normal | 10/08/2026 08:00 | sin outcome
- 2026-07-17 08:57:48 | sin orden | available | normal | 10/08/2026 09:00 | sin outcome
- 2026-07-17 08:57:36 | sin orden | available | normal | 10/08/2026 09:00 | sin outcome
- 2026-07-17 08:53:26 | order-*** | registered | normal | 10/08/2026 12:00 | confirmed
- 2026-07-17 08:53:10 | order-*** | registered | normal | 10/08/2026 11:00 | confirmed
- 2026-07-17 08:52:41 | order-*** | partial | normal | 10/08/2026 09:00 | priority_deferred

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
