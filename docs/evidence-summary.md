# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-09-02 08:08:44 America/Lima`.
- Ventana solicitada: mes activo 2026-09 (America/Lima).
- Rango real de eventos indexados: `2026-09-01 09:04:52` a `2026-09-02 05:00:01` (America/Lima).
- Cobertura temporal verificable: 41/41 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 41
- Reservas registradas: 17
- Reservas no confirmadas: 0
- Disponibilidades completas: 3
- Disponibilidades parciales: 3
- Senales de defensa: 1

## Origen de deteccion
- normal: 37
- slot_lost_reobservation: 4

## Ultimos eventos utiles
- 2026-09-02 05:00:01 | sin orden | available | normal | 01/09/2026 10:30 | sin outcome
- 2026-09-01 12:47:30 | sin orden | available | normal | 29/09/2026 11:00 | sin outcome
- 2026-09-01 12:47:22 | sin orden | available | normal | 29/09/2026 11:00 | sin outcome
- 2026-09-01 12:23:33 | order-*** | registered | normal | 28/09/2026 08:00 | confirmed
- 2026-09-01 12:16:26 | order-*** | unavailable | normal | 29/09/2026 10:00 | slot_lost
- 2026-09-01 12:16:16 | order-*** | registered | normal | 29/09/2026 10:00 | confirmed
- 2026-09-01 12:15:03 | order-*** | unavailable | normal | 28/09/2026 12:00 | slot_lost
- 2026-09-01 12:15:02 | order-*** | unavailable | normal | 28/09/2026 12:00 | slot_lost
- 2026-09-01 12:14:52 | order-*** | registered | normal | 28/09/2026 12:00 | confirmed
- 2026-09-01 12:05:40 | order-*** | unavailable | normal | 29/09/2026 09:00 | slot_lost

## Senales de defensa
- 2026-09-01 09:59:40 | order-*** | http_429 | La reserva fue confirmada por mensaje de exito del portal.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
