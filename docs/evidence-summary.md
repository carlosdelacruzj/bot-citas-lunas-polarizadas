# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-10-17 17:59:30 America/Lima`.
- Ventana solicitada: mes activo 2026-10 (America/Lima).
- Rango real de eventos indexados: `2026-10-01 07:30:32` a `2026-10-17 17:59:29` (America/Lima).
- Cobertura temporal verificable: 3691/3691 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 3691
- Reservas registradas: 21
- Reservas no confirmadas: 1
- Disponibilidades completas: 3667
- Disponibilidades parciales: 0
- Senales de defensa: 0

## Origen de deteccion
- normal: 3691

## Ultimos eventos utiles
- 2026-10-17 17:59:29 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:58:44 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:57:59 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:57:13 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:56:28 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:55:42 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:54:56 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:54:11 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:53:25 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome
- 2026-10-17 17:52:40 | sin orden | available | normal | 31/12/2026 08:00 | sin outcome

## Senales de defensa
- No se registraron senales de defensa en estos eventos.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
