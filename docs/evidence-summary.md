# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Totales
- Eventos indexados: 2149
- Reservas registradas: 122
- Reservas no confirmadas: 5
- Disponibilidades completas: 1485
- Disponibilidades parciales: 358
- Senales de defensa: 12

## Origen de deteccion
- normal: 2144
- slot_lost_reobservation: 5

## Ultimos eventos utiles
- 2026-08-20 12:13:01 | sin orden | available | normal | 14/09/2026 08:00 | sin outcome
- 2026-08-20 11:42:46 | sin orden | available | normal | 11/09/2026 12:00 | sin outcome
- 2026-08-20 11:42:37 | sin orden | available | normal | 11/09/2026 12:00 | sin outcome
- 2026-08-20 11:42:29 | sin orden | available | normal | 11/09/2026 12:00 | sin outcome
- 2026-08-20 11:42:19 | sin orden | available | normal | 11/09/2026 12:00 | sin outcome
- 2026-08-20 11:42:11 | sin orden | available | normal | 11/09/2026 11:00 | sin outcome
- 2026-08-20 11:42:02 | sin orden | available | normal | 11/09/2026 11:00 | sin outcome
- 2026-08-20 11:41:54 | sin orden | available | normal | 11/09/2026 11:00 | sin outcome
- 2026-08-20 11:41:44 | sin orden | available | normal | 11/09/2026 11:00 | sin outcome
- 2026-08-20 11:41:36 | sin orden | available | normal | 11/09/2026 11:00 | sin outcome

## Senales de defensa
- 2026-08-18 17:22:49 | order-***-1be4d862e11fa4c6 | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-08-17 12:22:53 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
- 2026-08-13 14:43:58 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
- 2026-08-12 16:22:56 |  | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede")
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

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/optimization.md`.
