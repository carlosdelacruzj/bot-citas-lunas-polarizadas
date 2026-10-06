# Resumen digerido de evidencia

Este archivo es la lectura rapida antes de abrir HTML, screenshots o logs largos.

## Corte y cobertura
- Generado: `2026-10-05 17:59:35 America/Lima`.
- Ventana solicitada: mes activo 2026-10 (America/Lima).
- Rango real de eventos indexados: `2026-10-01 07:30:32` a `2026-10-02 17:30:11` (America/Lima).
- Cobertura temporal verificable: 1436/1436 eventos con hora de cierre.
- Fuente: filas sanitizadas del indice compacto de evidencia.

## Limites
- Es un snapshot generado; no representa el runtime ni PostgreSQL en vivo.
- Incluye solo eventos utiles definidos por la politica de evidencia, no todos los runs.
- Una ruta indexada no prueba que el artefacto siga retenido; verificarla antes de citarla.
- La ausencia de un evento no demuestra que el portal no haya sido consultado.

## Totales
- Eventos indexados: 1436
- Reservas registradas: 0
- Reservas no confirmadas: 0
- Disponibilidades completas: 1436
- Disponibilidades parciales: 0
- Senales de defensa: 0

## Origen de deteccion
- normal: 1436

## Ultimos eventos utiles
- 2026-10-02 17:30:11 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:29:26 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:28:41 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:27:55 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:27:09 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:26:24 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:25:38 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:24:53 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:24:07 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome
- 2026-10-02 17:23:19 | sin orden | available | normal | 30/12/2026 12:00 | sin outcome

## Senales de defensa
- No se registraron senales de defensa en estos eventos.

## Lectura recomendada
- Usar `docs/evidence-index.csv` para filtrar el caso exacto.
- Abrir las rutas de evidencia solo cuando este resumen apunte a un evento.
- Comparar cambios contra `docs/contracts/optimization.md`.
