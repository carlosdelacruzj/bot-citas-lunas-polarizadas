# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-09-08 01:16:50 America/Lima`.
- Ventana solicitada: mes activo 2026-09 (America/Lima).
- Rango real de eventos indexados: `2026-09-01 09:04:52` a `2026-09-07 18:00:11` (America/Lima).
- Cobertura temporal verificable: 467/467 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 467
- Reservas registradas: 61
- Reservas no confirmadas: 0
- Disponibilidades completas: 327
- Disponibilidades parciales: 36
- Senales de defensa: 3

## Origen de deteccion
- fetch_probe: 22
- normal: 433
- reload_probe: 4
- slot_lost_reobservation: 8

## Ultimos eventos utiles
- 2026-09-07 18:00:11 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:59:58 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:59:07 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:58:54 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:58:03 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:57:50 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:56:59 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:56:46 | sin orden | available | normal | 21/10/2026 09:00 | sin outcome
- 2026-09-07 17:55:26 | sin orden | available | normal | 20/10/2026 09:00 | sin outcome
- 2026-09-07 17:55:13 | sin orden | available | normal | 20/10/2026 09:00 | sin outcome

## Senales de defensa
- 2026-09-03 13:02:34 | order-*** | http_429 | La reserva fue confirmada por mensaje de exito del portal.
- 2026-09-02 15:02:23 | order-*** | network | Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#MainContent_idUcitas_cbosede") to be visible
- 2026-09-01 09:59:40 | order-*** | http_429 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
